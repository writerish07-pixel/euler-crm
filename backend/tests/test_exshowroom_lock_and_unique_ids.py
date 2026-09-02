"""Ex-Showroom is Price Master–locked; invoice/chassis/plate must be unique."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "exshowroom_unique_ids")
os.environ.setdefault("JWT_SECRET", "exshowroom-unique-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(client, mobile, name="QA Unique"):
    await server.db.price_master.update_one(
        {"model": "Hi-Load", "variant": "XR"},
        {"$set": {"model": "Hi-Load", "variant": "XR", "exShowroom": 435000, "rto": 10000,
                  "insuranceAmount": 10000, "insurance": 10000, "priceId": "PM-UQ-1",
                  "status": "Active"}},
        upsert=True,
    )
    r = await client.post("/api/leads", json={
        "customerName": name, "mobile": mobile, "interestedModel": "Hi-Load",
        "variant": "XR", "executive": "Amit", "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


@pytest.mark.asyncio
async def test_ex_showroom_is_taken_from_price_master_not_client(client):
    lid = await _lead(client, "9222200001")
    r = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 1,  # staff attempt to override — must be ignored
        "rto": 12000, "insuranceAmount": 11000,
    })
    assert r.status_code == 200, r.text
    lead = r.json()
    assert lead["exShowroom"] == 435000
    assert lead["rto"] == 12000
    assert lead["insuranceAmount"] == 11000


@pytest.mark.asyncio
async def test_duplicate_invoice_chassis_plate_rejected(client):
    a = await _lead(client, "9222200002", "Lead A")
    b = await _lead(client, "9222200003", "Lead B")

    # Book + clear outstanding path is heavy; uniqueness is enforced on delivery save
    # even before mark-delivered. Seed booked status so canDeliver is not required
    # for a non-delivered paperwork save.
    await server.db.leads.update_one({"leadId": a}, {"$set": {
        "currentStatus": "Booked", "accountStatus": "Active", "bookingDate": "2026-08-01",
        "exShowroom": 435000, "customerPayable": 100000, "customerOutstanding": 0,
    }})
    await server.db.leads.update_one({"leadId": b}, {"$set": {
        "currentStatus": "Booked", "accountStatus": "Active", "bookingDate": "2026-08-01",
        "exShowroom": 435000, "customerPayable": 100000, "customerOutstanding": 0,
    }})

    ok = await client.put(f"/api/leads/{a}/delivery", json={
        "invoiceNumber": "INV-UNIQUE-1", "chassisNumber": "CH-UNIQUE-1",
        "numberPlate": "RJ14-UQ-1",
    })
    assert ok.status_code == 200, ok.text

    for field, value, label in [
        ("invoiceNumber", "inv-unique-1", "Invoice number"),  # case-insensitive
        ("chassisNumber", "CH-UNIQUE-1", "Chassis number"),
        ("numberPlate", "rj14-uq-1", "Number plate"),
    ]:
        payload = {"invoiceNumber": "OTHER-INV", "chassisNumber": "OTHER-CH", "numberPlate": "OTHER-PL"}
        payload[field] = value
        bad = await client.put(f"/api/leads/{b}/delivery", json=payload)
        assert bad.status_code == 409, (field, bad.text)
        assert label in bad.json()["detail"]

    # Re-saving the same lead's own identifiers is allowed.
    again = await client.put(f"/api/leads/{a}/delivery", json={
        "invoiceNumber": "INV-UNIQUE-1", "chassisNumber": "CH-UNIQUE-1",
        "numberPlate": "RJ14-UQ-1",
    })
    assert again.status_code == 200, again.text


@pytest.mark.asyncio
async def test_cancelled_lead_does_not_block_chassis_reuse(client):
    a = await _lead(client, "9222200010", "Old Cancelled")
    b = await _lead(client, "9222200011", "Recreated Sept")
    await server.db.leads.update_one({"leadId": a}, {"$set": {
        "currentStatus": "Lost", "accountStatus": "Cancelled", "dealCancelled": True,
        "invoiceNumber": "INV-REUSE-1", "chassisNumber": "CH-REUSE-1",
        "numberPlate": "RJ14-RE-1",
    }})
    await server.db.leads.update_one({"leadId": b}, {"$set": {
        "currentStatus": "Booked", "accountStatus": "Active", "bookingDate": "2026-09-02",
        "exShowroom": 435000, "customerPayable": 100000, "customerOutstanding": 0,
    }})
    ok = await client.put(f"/api/leads/{b}/delivery", json={
        "invoiceNumber": "INV-REUSE-1", "chassisNumber": "CH-REUSE-1",
        "numberPlate": "RJ14-RE-1", "deliveryDate": "2026-09-02",
    })
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_august_delivered_does_not_block_sept_chassis_reuse(client):
    a = await _lead(client, "9222200012", "Aug Delivered")
    b = await _lead(client, "9222200013", "Sept Recreated")
    await server.db.leads.update_one({"leadId": a}, {"$set": {
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active", "deliveryDate": "2026-08-18",
        "invoiceNumber": "INV-AUG-CH", "chassisNumber": "CH-AUG-CH",
        "numberPlate": "RJ14-AUG-1",
    }})
    await server.db.leads.update_one({"leadId": b}, {"$set": {
        "currentStatus": "Booked", "accountStatus": "Active", "bookingDate": "2026-09-02",
        "exShowroom": 435000, "customerPayable": 100000, "customerOutstanding": 0,
    }})
    ok = await client.put(f"/api/leads/{b}/delivery", json={
        "invoiceNumber": "INV-AUG-CH", "chassisNumber": "CH-AUG-CH",
        "numberPlate": "RJ14-AUG-1", "deliveryDate": "2026-09-02",
    })
    assert ok.status_code == 200, ok.text
