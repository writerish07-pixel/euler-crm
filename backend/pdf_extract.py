"""Read insurance / RTO PDFs for premium, RTO fee, chassis, policy number.

Used by the PDF agent. Suggests Price Structure `rto` / `insuranceAmount` only.
Never writes Scheme `insuranceBenefit` / `rtoBenefit` — those come from Scheme Master.
"""
from __future__ import annotations

import io
import re

import commercial as ce

# VIN-like (17) plus shorter OEM chassis tokens after a label.
_CHASSIS_LABELED = re.compile(
    r"(?:chassis(?:\s*(?:no|number|#))?|vin|chasis|frame\s*no)[^\nA-Z0-9]{0,24}"
    r"([A-HJ-NPR-Z0-9]{10,21})",
    re.I,
)
_VIN = re.compile(r"\b([A-HJ-NPR-Z0-9]{17})\b")
_POLICY = re.compile(
    r"(?:policy\s*(?:no|number|#)|policy\s*id)[^\nA-Z0-9]{0,16}([A-Z0-9][A-Z0-9/-]{5,28})",
    re.I,
)
_AMOUNT = re.compile(
    r"(?:rs\.?|inr|₹)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+|[0-9]{3,7})(?:\.[0-9]{1,2})?"
)
_GST_NEAR = re.compile(r"\b(?:c?gst|s?gst|igst|ugst|gst\s*@)\b", re.I)


def make_simple_pdf(text: str) -> bytes:
    """Minimal one-page PDF with `text` drawn as a single line (tests + fixtures)."""
    safe = (
        str(text or "")
        .replace("\\", "\\\\")
        .replace("(", "\\(")
        .replace(")", "\\)")
        .replace("\r", " ")
        .replace("\n", "  ")
    )[:400]
    stream = f"BT /F1 12 Tf 50 720 Td ({safe}) Tj ET\n".encode("latin-1", "replace")
    parts = [
        b"%PDF-1.4\n",
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n",
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n",
        (
            b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>\nendobj\n"
        ),
    ]
    stream_obj = (
        f"4 0 obj\n<< /Length {len(stream)} >>\nstream\n".encode("ascii")
        + stream
        + b"endstream\nendobj\n"
    )
    font = b"5 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>\nendobj\n"
    body = b"".join(parts) + stream_obj + font
    offsets = []
    pos = 0
    # Object 1 starts after the header line.
    for chunk in (parts[0], parts[1], parts[2], parts[3], stream_obj, font):
        if chunk.startswith(b"%PDF"):
            pos += len(chunk)
            continue
        offsets.append(pos)
        pos += len(chunk)
    xref_pos = len(body)
    xref = [b"xref\n0 6\n0000000000 65535 f \n"]
    for off in offsets:
        xref.append(f"{off:010d} 00000 n \n".encode("ascii"))
    trailer = (
        f"trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n"
    ).encode("ascii")
    return body + b"".join(xref) + trailer


def pdf_text(data: bytes, content_type: str = "") -> str:
    """Best-effort text. Empty when the file is an image or a scanned PDF with no text layer."""
    ctype = str(content_type or "").lower()
    raw = bytes(data or b"")
    if not raw:
        return ""
    if ctype.startswith("image/"):
        return ""
    text = _pypdf_text(raw)
    if len(text.strip()) >= 8:
        return text
    fallback = _raw_pdf_strings(raw)
    return fallback if len(fallback.strip()) > len(text.strip()) else text


def _pypdf_text(raw: bytes) -> str:
    try:
        from pypdf import PdfReader
    except Exception:
        return ""
    try:
        reader = PdfReader(io.BytesIO(raw))
        bits = []
        for page in reader.pages:
            bits.append(page.extract_text() or "")
        return "\n".join(bits)
    except Exception:
        return ""


def _raw_pdf_strings(raw: bytes) -> str:
    """Pull `(literal)` PDF strings when pypdf has nothing."""
    found = re.findall(rb"\((?:\\.|[^\\)]){3,200}\)", raw)
    out = []
    for chunk in found:
        s = chunk[1:-1].replace(b"\\(", b"(").replace(b"\\)", b")").replace(b"\\\\", b"\\")
        try:
            out.append(s.decode("latin-1"))
        except Exception:
            continue
    return " ".join(out)


def parse_amount(token) -> float:
    s = str(token or "").replace(",", "").replace("₹", "").strip()
    return ce.round2(ce.num(s))


def _label_amount(text: str, labels) -> float:
    blob = str(text or "")
    if not blob:
        return 0.0
    best = 0.0
    for label in labels:
        for m in re.finditer(label, blob, re.I):
            window = blob[m.end(): m.end() + 80]
            if _GST_NEAR.search(blob[max(0, m.start() - 24): m.end() + 80]):
                continue
            am = _AMOUNT.search(window)
            if not am:
                continue
            val = parse_amount(am.group(1))
            if 100 <= val <= 9_99_999 and val > best:
                best = val
    return best


def extract_insurance(text: str) -> dict:
    blob = str(text or "")
    premium = _label_amount(blob, (
        r"total\s*premium",
        r"gross\s*premium",
        r"net\s*premium",
        r"package\s*premium",
        r"premium\s*payable",
        r"\bpremium\b",
    ))
    return {
        "premium": premium,
        "policyNumber": _first_group(_POLICY, blob),
        "chassis": extract_chassis(blob),
    }


def extract_rto(text: str) -> dict:
    blob = str(text or "")
    fee = _label_amount(blob, (
        r"registration\s*(?:fee|amount|charges?)",
        r"road\s*tax",
        r"hypothecation\s*(?:fee|charges?)",
        r"\brto\b",
        r"mv\s*tax",
        r"tax\s*amount",
    ))
    return {
        "rto": fee,
        "chassis": extract_chassis(blob),
        "registrationNumber": _first_group(
            re.compile(
                r"(?:reg(?:istration)?(?:n|n\.|istration)?(?:\s*(?:no|number|#))?)"
                r"[^\nA-Z0-9]{0,16}([A-Z]{2}[0-9]{1,2}[A-Z]{0,3}[0-9]{3,4})",
                re.I,
            ),
            blob,
        ),
    }


def extract_chassis(text: str) -> str:
    blob = str(text or "")
    m = _CHASSIS_LABELED.search(blob)
    if m:
        return re.sub(r"\s+", "", m.group(1)).upper()
    m = _VIN.search(blob.upper())
    return (m.group(1) if m else "").upper()


def _first_group(rx, text: str) -> str:
    m = rx.search(text or "")
    return (m.group(1) if m else "").strip()


def amounts_differ(a, b, rupees=1.0) -> bool:
    return abs(ce.round2(ce.num(a)) - ce.round2(ce.num(b))) > rupees
