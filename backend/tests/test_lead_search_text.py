"""Lead search box: phone numbers typed the way staff type them."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "lead_search_text_v1")
os.environ.setdefault("JWT_SECRET", "lead-search-text-secret-32chars")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

LEAD = {
    "leadId": "LD26SRCH01", "customerName": "Ramesh (Kirana) Gupta", "mobile": "9876543210",
    "interestedModel": "HiLoad", "variant": "", "currentStatus": "Booked",
    "accountStatus": "Active", "createdDate": "2026-10-05", "bookingDate": "2026-10-05",
}


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({"leadId": LEAD["leadId"]})
    await server.db.leads.insert_one(dict(LEAD))
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c
    await server.db.leads.delete_many({"leadId": LEAD["leadId"]})


def test_search_or_is_none_for_blank_box():
    assert server._lead_search_or(None) is None
    assert server._lead_search_or("   ") is None


@pytest.mark.asyncio
@pytest.mark.parametrize("typed", [
    "+919876543210", "+91 98765 43210", "98765-43210", "98765 43210", "(98765", "[9876",
])
async def test_phone_typed_with_symbols_finds_the_lead(client, typed):
    r = await client.get("/api/leads", params={"q": typed, "scope": "all"})
    assert r.status_code == 200, r.text
    assert LEAD["leadId"] in [row["leadId"] for row in r.json()]


@pytest.mark.asyncio
async def test_name_with_brackets_is_matched_literally(client):
    r = await client.get("/api/leads", params={"q": "(kirana)", "scope": "all"})
    assert r.status_code == 200, r.text
    assert LEAD["leadId"] in [row["leadId"] for row in r.json()]


@pytest.mark.asyncio
async def test_regex_symbols_do_not_match_everything(client):
    r = await client.get("/api/leads", params={"q": ".*", "scope": "all"})
    assert r.status_code == 200, r.text
    assert LEAD["leadId"] not in [row["leadId"] for row in r.json()]
