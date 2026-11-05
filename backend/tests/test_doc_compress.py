"""Uploaded photos / scanned PDFs are shrunk before they are stored in MongoDB."""
import io
import os
import random
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "doc_compress_tests")
os.environ.setdefault("JWT_SECRET", "doc-compress-secret-32chars!!x")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
from bson.binary import Binary  # noqa: E402
from PIL import Image  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

import doc_compress  # noqa: E402
import server  # noqa: E402

OWNER_EMAIL = "doc-compress-owner@euler.com"
OWNER_PASSWORD = "doc-compress-pass"


def _photo(w=3000, h=4000, fmt="JPEG", mode="RGB"):
    """A noisy 'camera photo' — noise keeps the encoder honest about size."""
    rnd = random.Random(7)
    img = Image.new(mode, (w, h), "white")
    px = img.load()
    for y in range(0, h, 4):
        for x in range(0, w, 4):
            v = rnd.randint(0, 255)
            px[x, y] = (v, v // 2, 255 - v) if mode == "RGB" else (v, v // 2, 255 - v, 200)
    out = io.BytesIO()
    img.save(out, fmt, quality=95) if fmt == "JPEG" else img.save(out, fmt)
    return out.getvalue()


def _scanned_pdf():
    img = Image.open(io.BytesIO(_photo(2480, 3508)))
    out = io.BytesIO()
    img.save(out, "PDF", resolution=300)
    return out.getvalue()


# ------------------------------------------------------------------ unit rules
def test_big_photo_becomes_a_small_1600px_jpeg():
    raw = _photo()
    packed, ctype = doc_compress.compress_image(raw, "image/jpeg")
    assert ctype == "image/jpeg"
    assert len(packed) < len(raw) / 3
    with Image.open(io.BytesIO(packed)) as img:
        assert max(img.size) == doc_compress.MAX_EDGE


def test_png_with_transparency_becomes_jpeg_on_white():
    raw = _photo(2000, 2000, fmt="PNG", mode="RGBA")
    packed, ctype = doc_compress.compress_image(raw, "image/png")
    assert ctype == "image/jpeg" and len(packed) < len(raw)
    out, ctype2, name = doc_compress.compress_document(raw, "image/png", "pan_card.png")
    assert ctype2 == "image/jpeg" and name == "pan_card.jpg"


def test_small_files_and_zips_and_heic_are_left_alone():
    tiny = _photo(200, 200)
    assert doc_compress.compress_image(tiny, "image/jpeg") == (tiny, "image/jpeg")
    zipped = b"PK\x03\x04" + b"x" * 500_000
    assert doc_compress.compress_document(zipped, "application/zip", "bills.zip")[0] == zipped
    heic = b"\x00\x00\x00\x18ftypheic" + b"x" * 500_000
    assert doc_compress.compress_document(heic, "image/heic", "a.heic")[0] == heic


def test_broken_image_never_fails_the_upload():
    junk = b"\xff\xd8\xff" + b"not really a jpeg" * 40_000
    assert doc_compress.compress_image(junk, "image/jpeg") == (junk, "image/jpeg")


def test_scanned_pdf_shrinks_and_stays_a_valid_pdf():
    raw = _scanned_pdf()
    packed = doc_compress.compress_pdf(raw)
    assert len(packed) < len(raw) * 0.6
    reader = PdfReader(io.BytesIO(packed))
    assert len(reader.pages) == 1


def test_tally_pdfs_keep_their_text_and_images_untouched():
    writer = PdfWriter()
    writer.add_blank_page(595, 842)
    out = io.BytesIO()
    writer.write(out)
    raw = out.getvalue()
    # Under the PDF floor: returned byte-for-byte.
    assert doc_compress.compress_pdf(raw, lossless_only=True) == raw
    scan = _scanned_pdf()
    lossless = doc_compress.compress_pdf(scan, lossless_only=True)
    # No resampling for Tally kinds, so the embedded scan is not shrunk.
    assert len(lossless) > len(doc_compress.compress_pdf(scan))


# ------------------------------------------------------------------ API
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "Doc Owner", "role": "owner",
                  "userId": "doc-compress-owner",
                  "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
        upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(c, mobile):
    r = await c.post("/api/leads", json={
        "customerName": "Doc Compress", "mobile": mobile, "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)", "executive": "Amit", "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


@pytest.mark.asyncio
async def test_upload_stores_the_compressed_photo(client):
    lid = await _lead(client, "9733300001")
    raw = _photo()
    r = await client.post(f"/api/leads/{lid}/documents", data={"kind": "kyc_aadhaar_front"},
                          files={"file": ("aadhaar.png", raw, "image/jpeg")})
    assert r.status_code == 200, r.text
    row = await server.db[server.lead_docs.COLLECTION].find_one({"documentId": r.json()["documentId"]})
    assert row["size"] == len(bytes(row["data"])) < len(raw) / 3
    assert row["contentType"] == "image/jpeg" and row["filename"] == "aadhaar.jpg"
    assert row.get("compressedAt")
    # The stored file still opens as an image.
    f = await client.get(f"/api/documents/{row['documentId']}/file")
    assert f.status_code == 200
    with Image.open(io.BytesIO(f.content)) as img:
        assert max(img.size) == doc_compress.MAX_EDGE


@pytest.mark.asyncio
async def test_owner_backfill_shrinks_old_documents_once(client):
    lid = await _lead(client, "9733300002")
    raw = _photo()
    coll = server.db[server.lead_docs.COLLECTION]
    await coll.insert_one({"documentId": "DC26OLD0001", "leadId": lid, "kind": "kyc_pan",
                           "filename": "pan.jpg", "contentType": "image/jpeg",
                           "size": len(raw), "data": Binary(raw)})
    r = await client.post("/api/admin/compress-documents")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["shrunk"] == 1 and body["bytesSaved"] > len(raw) / 2 and body["remaining"] == 0
    row = await coll.find_one({"documentId": "DC26OLD0001"})
    assert row["originalSize"] == len(raw) and row["size"] < len(raw) / 3
    again = (await client.post("/api/admin/compress-documents")).json()
    assert again["processed"] == 0 and again["bytesSaved"] == 0


@pytest.mark.asyncio
async def test_backfill_is_owner_only(client):
    await AUTH_DB.users.update_one(
        {"email": "doc-compress-exec@euler.com"},
        {"$set": {"email": "doc-compress-exec@euler.com", "name": "Exec", "role": "executive",
                  "userId": "doc-compress-exec",
                  "passwordHash": server.authmod.hash_password("exec-pass-1")}},
        upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        tok = (await c.post("/api/auth/login", json={
            "email": "doc-compress-exec@euler.com", "password": "exec-pass-1"})).json()["token"]
        r = await c.post("/api/admin/compress-documents", headers={"Authorization": f"Bearer {tok}"})
        assert r.status_code == 403
