"""Booking register is open-only; finance joins executive; deliveries include Close Won."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "open_booking_finance_test")
os.environ.setdefault("JWT_SECRET", "open-booking-finance-secret")
os.environ["ENVIRONMENT"] = "test"

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
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest.mark.asyncio
async def test_bookings_only_open_not_delivered(client):
    await server.db.bookings.delete_many({"bookingId": {"$in": ["BK-OPEN-1", "BK-DEL-1"]}})
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-BK-OPEN", "LD-BK-DEL"]}})
    await server.db.leads.insert_one({
        "leadId": "LD-BK-OPEN", "customerName": "Open Book", "mobile": "9813300001",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-02",
        "executive": "Payal", "interestedModel": "Turbo Max",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-BK-DEL", "customerName": "Done Book", "mobile": "9813300002",
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "bookingDate": "2026-09-01",
        "executive": "Ravi", "interestedModel": "Turbo Max",
    })
    await server.db.bookings.insert_one({
        "bookingId": "BK-OPEN-1", "leadId": "LD-BK-OPEN", "customerName": "Open Book",
        "bookingDate": "2026-09-02", "bookingStatus": "Booked", "bookingAmount": 11000,
        "model": "Turbo Max",
    })
    await server.db.bookings.insert_one({
        "bookingId": "BK-DEL-1", "leadId": "LD-BK-DEL", "customerName": "Done Book",
        "bookingDate": "2026-09-01", "bookingStatus": "Booked", "bookingAmount": 11000,
        "model": "Turbo Max",
    })
    rows = (await client.get("/api/bookings")).json()
    ids = {r["bookingId"] for r in rows}
    assert "BK-OPEN-1" in ids
    assert "BK-DEL-1" not in ids
    hit = next(r for r in rows if r["bookingId"] == "BK-OPEN-1")
    assert hit["executive"] == "Payal"


@pytest.mark.asyncio
async def test_deliveries_include_close_won(client):
    await server.db.leads.delete_many({"leadId": "LD-DEL-CW"})
    await server.db.leads.insert_one({
        "leadId": "LD-DEL-CW", "customerName": "Closed Retail", "mobile": "9813300003",
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-10",
        "executive": "Payal", "interestedModel": "Turbo Max", "chassisNumber": "MD9DELCW01",
    })
    rows = (await client.get("/api/deliveries")).json()
    hit = next(r for r in rows if r["leadId"] == "LD-DEL-CW")
    assert hit["delivered"] in ("Yes", "yes", True) or str(hit["delivered"]).lower() in ("yes", "true")
    assert hit["executive"] == "Payal"
    assert hit["chassisNumber"] == "MD9DELCW01"


@pytest.mark.asyncio
async def test_finance_pending_view_and_executive(client):
    await server.db.finance.delete_many({"fileNumber": {"$in": ["FN-PEND-1", "FN-DONE-1"]}})
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-FN-PEND", "LD-FN-DONE"]}})
    await server.db.leads.insert_one({
        "leadId": "LD-FN-PEND", "customerName": "Pending File", "executive": "Payal",
        "accountStatus": "Active", "currentStatus": "Finance Process",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-FN-DONE", "customerName": "Settled File", "executive": "Ravi",
        "accountStatus": "Active", "currentStatus": "Finance Process",
    })
    await server.db.finance.insert_one({
        "fileNumber": "FN-PEND-1", "leadId": "LD-FN-PEND", "customerName": "Pending File",
        "financer": "HDFC", "sanctionedAmount": 100000, "receivedAgainstFile": 20000,
        "fileOutstanding": 80000, "status": "Pending",
    })
    await server.db.finance.insert_one({
        "fileNumber": "FN-DONE-1", "leadId": "LD-FN-DONE", "customerName": "Settled File",
        "financer": "HDFC", "sanctionedAmount": 90000, "receivedAgainstFile": 90000,
        "fileOutstanding": 0, "status": "Received",
    })
    all_rows = (await client.get("/api/finance")).json()
    pending = (await client.get("/api/finance", params={"view": "pending"})).json()
    numbers = {r["fileNumber"] for r in pending}
    assert "FN-PEND-1" in numbers
    assert "FN-DONE-1" not in numbers
    hit = next(r for r in all_rows if r["fileNumber"] == "FN-PEND-1")
    assert hit["executive"] == "Payal"
