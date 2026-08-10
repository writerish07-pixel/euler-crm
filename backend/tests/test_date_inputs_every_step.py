"""Every lifecycle step accepts an explicit date instead of silently forcing today()."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "date_inputs_every_step")
os.environ.setdefault("JWT_SECRET", "date-inputs-secret")

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


@pytest.mark.asyncio
async def test_lead_booking_payment_activity_close_respect_explicit_dates(client):
    created = await client.post("/api/leads", json={
        "customerName": "Date Input QA", "mobile": "9111100001",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit",
        "leadSource": "Walk-in", "createdDate": "2026-07-01",
    })
    assert created.status_code == 200, created.text
    lead = created.json()
    assert lead["createdDate"] == "2026-07-01"
    lid = lead["leadId"]

    await server.db.price_master.update_one(
        {"model": "Hi-Load", "variant": "XR"},
        {"$set": {"model": "Hi-Load", "variant": "XR", "exShowroom": 435000, "rto": 10000,
                  "insuranceAmount": 10000, "priceId": "PM-DATE-1", "status": "Active"}},
        upsert=True,
    )
    priced = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 435000, "rto": 10000, "insuranceAmount": 10000,
    })
    assert priced.status_code == 200, priced.text

    booked = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingAmount": 5000, "paymentMode": "Cash", "bookingDate": "2026-07-05",
    })
    assert booked.status_code == 200, booked.text
    assert booked.json()["lead"]["bookingDate"] == "2026-07-05"

    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1000, "paymentMode": "Cash", "date": "2026-07-06",
    })
    assert pay.status_code == 200, pay.text
    assert pay.json()["date"] == "2026-07-06"

    act = await client.post(f"/api/leads/{lid}/activities", json={
        "activityType": "Call", "discussion": "Followed up", "date": "2026-07-07",
        "nextFollowup": "2026-07-10",
    })
    assert act.status_code == 200, act.text
    assert act.json()["date"] == "2026-07-07"

    closed = await client.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Lost to competitor", "closedDate": "2026-07-08",
    })
    assert closed.status_code == 200, closed.text
    assert closed.json()["closedDate"] == "2026-07-08"
