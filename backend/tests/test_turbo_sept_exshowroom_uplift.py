"""Turbo +₹15,000 ex-showroom from 1 Sep 2026. August bookings keep OEM."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "turbo_sept_uplift_tests")
os.environ.setdefault("JWT_SECRET", "turbo-sept-uplift-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
OEM_MAXX_PV = 770000
UPLIFT = 15000


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(c, name, mobile):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": mobile,
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": "Amit"})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


def test_turbo_overlay_math():
    row = {"model": "Turbo Max", "variant": "Maxx (PV)", "exShowroom": OEM_MAXX_PV}
    assert server._turbo_selling_ex(row, "2026-08-31") == OEM_MAXX_PV
    assert server._turbo_selling_ex(row, "2026-09-01") == OEM_MAXX_PV + UPLIFT
    storm = {"model": "Storm", "variant": "Storm (PV)", "exShowroom": 640000}
    assert server._turbo_selling_ex(storm, "2026-09-02") == 640000


def test_live_oem_sync_skips_turbo_overlay():
    """Coulson invoice base price is already the list — overlay would double-count."""
    live = {
        "model": "Turbo Max", "variant": "Maxx (DV220)",
        "exShowroom": 785713.33, "oemSyncedAt": "2026-09-04T08:00:00+00:00",
    }
    assert server._turbo_selling_ex(live, "2026-09-04") == 785713.33
    unsynced = {"model": "Turbo Max", "variant": "Maxx (DV220)", "exShowroom": 809999}
    assert server._turbo_selling_ex(unsynced, "2026-09-04") == 809999 + UPLIFT


@pytest.mark.asyncio
async def test_price_list_quotes_turbo_with_sept_uplift(client):
    body = (await client.get("/api/price-list", params={"model": "Turbo Max"})).json()
    rows = [r for g in body["models"] for r in g["rows"]]
    maxx = next(r for r in rows if r["variant"] == "Maxx (PV)")
    pm = next(r for r in (await client.get("/api/price-master", params={"model": "Turbo Max"})).json()
              if r["variant"] == "Maxx (PV)")
    assert pm["exShowroom"] == OEM_MAXX_PV
    assert pm["sellingExShowroom"] == OEM_MAXX_PV + UPLIFT
    assert maxx["exShowroom"] == OEM_MAXX_PV + UPLIFT


@pytest.mark.asyncio
async def test_august_booking_keeps_oem_price(client):
    lid = await _lead(client, "Aug Turbo", "9535010001")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-20", "bookingAmount": 0})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["exShowroom"] == OEM_MAXX_PV
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV
    assert preview["asOf"] == "2026-08-20"


@pytest.mark.asyncio
async def test_september_booking_adds_uplift(client):
    lid = await _lead(client, "Sep Turbo", "9535010002")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-09-01", "bookingAmount": 0})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["exShowroom"] == OEM_MAXX_PV + UPLIFT
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV + UPLIFT
