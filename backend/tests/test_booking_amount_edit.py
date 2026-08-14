"""Booking advance defaults to 0; Edit Lead can correct bookingAmount (e.g. 5000 → 0)."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "booking_amount_edit")
os.environ.setdefault("JWT_SECRET", "booking-amount-edit-secret-32ch!")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client(monkeypatch):
    async def noop_sync(*a, **k):
        return {"ok": True, "skipped": True}

    monkeypatch.setattr(server, "sheet_sync", noop_sync)
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _priced_lead(client, mobile):
    r = await client.post("/api/leads", json={
        "customerName": "Booking Amt", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    return lid


@pytest.mark.asyncio
async def test_booking_with_zero_advance_creates_no_payment(client):
    lid = await _priced_lead(client, "9222200001")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 0,
        "paymentMode": "UPI", "financeRequired": "No", "exchangeRequired": "No",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("bookingAmount")) == 0
    pays = await server.db.payments.find({"leadId": lid}).to_list(20)
    assert pays == []


@pytest.mark.asyncio
async def test_edit_booking_amount_5000_to_zero_removes_advance(client):
    lid = await _priced_lead(client, "9222200002")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 5000,
        "paymentMode": "Cash", "financeRequired": "No", "exchangeRequired": "No",
    })
    assert r.status_code == 200, r.text
    pays = await server.db.payments.find({"leadId": lid}).to_list(20)
    assert len(pays) == 1
    assert ce.num(pays[0].get("amount")) == 5000

    r = await client.put(f"/api/leads/{lid}", json={"bookingAmount": 0})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("bookingAmount")) == 0
    booking = await server.db.bookings.find_one({"leadId": lid})
    assert ce.num(booking.get("bookingAmount")) == 0
    pays = await server.db.payments.find({"leadId": lid}).to_list(20)
    assert pays == []
