"""Shrink uploaded documents before they are stored in MongoDB.

Every KYC / delivery / Tally / cheque file lives as BSON binary on its
`lead_documents` row, so stored bytes are the Atlas storage bill. Phones send
4–8 MB camera photos and scanned PDFs whose pages are full-resolution JPEGs;
a 1600 px JPEG at quality 70 is still sharp enough to read an Aadhaar number,
a PAN or a cheque.

Rules:
- Never make a file bigger: if the result is not smaller, keep the original.
- Never fail an upload: any error returns the original bytes unchanged.
- ZIPs are not touched (the Tally checker reads the PDFs inside them).
- HEIC is kept as-is (Pillow cannot decode it without extra codecs).
- Tally invoices / ledgers get lossless PDF compression only, so the text the
  Tally pack checker reads is never resampled.
"""
from __future__ import annotations

import io
import logging

log = logging.getLogger("euler.doc_compress")

MAX_EDGE = 1600
JPEG_QUALITY = 70
# Images already this small are not worth re-encoding.
MIN_IMAGE_BYTES = 300 * 1024
MIN_PDF_BYTES = 200 * 1024
# PDF images: only resample ones that are big on their own.
PDF_IMAGE_MIN_BYTES = 150 * 1024
PDF_MAX_PAGES = 40

RASTER_TYPES = {"image/jpeg", "image/png", "image/webp"}
LOSSLESS_ONLY_KINDS = {"tally_invoice", "tally_ledger"}


def _to_rgb(img):
    from PIL import Image

    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, (255, 255, 255))
        bg.paste(img, mask=img.split()[-1])
        return bg
    if img.mode not in ("RGB", "L"):
        return img.convert("RGB")
    return img


def _shrink(img):
    from PIL import ImageOps

    img = ImageOps.exif_transpose(img)
    img = _to_rgb(img)
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    return img


def compress_image(data: bytes, content_type: str) -> tuple[bytes, str]:
    """Return (bytes, content_type). JPEG out, or the original when not smaller."""
    if content_type not in RASTER_TYPES or len(data) < MIN_IMAGE_BYTES:
        return data, content_type
    try:
        from PIL import Image

        with Image.open(io.BytesIO(data)) as src:
            img = _shrink(src)
            out = io.BytesIO()
            img.save(out, "JPEG", quality=JPEG_QUALITY, optimize=True, progressive=True)
        packed = out.getvalue()
    except Exception:
        log.exception("image compression failed; keeping original")
        return data, content_type
    if len(packed) >= len(data):
        return data, content_type
    return packed, "image/jpeg"


def compress_pdf(data: bytes, *, lossless_only: bool = False) -> bytes:
    """Recompress page streams and downscale large embedded scan images."""
    if len(data) < MIN_PDF_BYTES:
        return data
    try:
        from pypdf import PdfReader, PdfWriter

        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted or len(reader.pages) > PDF_MAX_PAGES:
            return data
        writer = PdfWriter(clone_from=reader)
        for page in writer.pages:
            if not lossless_only:
                for image in page.images:
                    try:
                        if len(image.data) < PDF_IMAGE_MIN_BYTES:
                            continue
                        image.replace(_shrink(image.image), quality=JPEG_QUALITY)
                    except Exception:
                        continue
            page.compress_content_streams()
        writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
        out = io.BytesIO()
        writer.write(out)
        packed = out.getvalue()
    except Exception:
        log.exception("pdf compression failed; keeping original")
        return data
    if len(packed) >= len(data):
        return data
    return packed


def _jpg_name(filename: str) -> str:
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    return f"{stem or 'document'}.jpg"


def compress_document(data: bytes, content_type: str, filename: str,
                      kind: str = "") -> tuple[bytes, str, str]:
    """(bytes, content_type, filename) — smaller when possible, else unchanged."""
    if content_type in RASTER_TYPES:
        packed, ctype = compress_image(data, content_type)
        if packed is not data and not filename.lower().endswith((".jpg", ".jpeg")):
            filename = _jpg_name(filename)
        return packed, ctype, filename
    if content_type == "application/pdf":
        return compress_pdf(data, lossless_only=kind in LOSSLESS_ONLY_KINDS), content_type, filename
    return data, content_type, filename
