"""Payment UTR is stored per receipt and OEM Extra Support has its own register."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "payment_utr_extra_support")
os.environ.setdefault("JWT_SECRET", "payment-utr-extra-support-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
PNG = b"\x89PNG\r\n\x1a\n" + b"proof" * 12
MOBILE = 9333300000


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.payments.delete_many({})
    await server.db.bookings.delete_many({})
    await server.db.claims.delete_many({})
    await server.db.lead_requests.delete_many({})
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _priced_lead(client, name="Utr Cust"):
    r = await client.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    return lid


@pytest.mark.asyncio
async def test_upi_without_utr_is_rejected(client):
    lid = await _priced_lead(client, "No Utr")
    await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 0, "paymentMode": "Cash"})
    bad = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1000, "paymentMode": "UPI", "date": "2026-08-10"})
    assert bad.status_code == 422, bad.text
    assert "utr" in bad.json()["detail"].lower()
    ok = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1000, "paymentMode": "UPI", "date": "2026-08-10",
        "paymentReference": "UTR111AAA"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["paymentReference"] == "UTR111AAA"


@pytest.mark.asyncio
async def test_three_upi_receipts_keep_their_own_utr(client):
    lid = await _priced_lead(client, "Three Upi")
    await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 0, "paymentMode": "Cash"})
    refs = ["UTR-A-1000", "UTR-B-2000", "UTR-C-3000"]
    amounts = [1000, 2000, 3000]
    for amt, ref in zip(amounts, refs):
        r = await client.post(f"/api/leads/{lid}/payments", json={
            "amount": amt, "paymentMode": "UPI", "date": "2026-08-10",
            "paymentReference": ref, "allowExcess": True})
        assert r.status_code == 200, r.text
    ledger = (await client.get("/api/payments", params={"lead_id": lid})).json()
    upi = [p for p in ledger if p.get("paymentMode") == "UPI"]
    assert len(upi) == 3
    assert sorted(p["paymentReference"] for p in upi) == sorted(refs)
    assert sorted(p["amount"] for p in upi) == sorted(amounts)
    found = (await client.get("/api/payments", params={"q": "UTR-B-2000"})).json()
    assert len(found) == 1
    assert found[0]["paymentReference"] == "UTR-B-2000"
    assert found[0]["amount"] == 2000


@pytest.mark.asyncio
async def test_booking_upi_advance_requires_utr(client):
    lid = await _priced_lead(client, "Book Utr")
    bad = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 5000, "paymentMode": "UPI"})
    assert bad.status_code == 422, bad.text
    ok = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 5000, "paymentMode": "UPI",
        "paymentReference": "BK-UTR-5000"})
    assert ok.status_code == 200, ok.text
    pays = await server.db.payments.find({"leadId": lid}).to_list(10)
    assert len(pays) == 1
    assert pays[0]["paymentReference"] == "BK-UTR-5000"


@pytest.mark.asyncio
async def test_oem_extra_support_register_lists_received_and_proof(client):
    r = await client.post("/api/leads", json={
        "customerName": "Extra Reg", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "oemExtraSupportReceived": 7000,
    })
    lid = r.json()["leadId"]
    up = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("asm.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "oem_extra_support"},
    )
    assert up.status_code == 200, up.text
    rows = (await client.get("/api/oem-extra-support")).json()
    row = next(x for x in rows if x["leadId"] == lid)
    assert row["oemExtraSupportReceived"] == 7000
    assert row["hasProof"] is True
    assert row["proofDocumentId"]
    cash = await client.post("/api/leads", json={
        "customerName": "No Extra", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
    })
    other = cash.json()["leadId"]
    assert all(x["leadId"] != other for x in (await client.get("/api/oem-extra-support")).json())
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("oemExtraSupportReceived")) == 7000
