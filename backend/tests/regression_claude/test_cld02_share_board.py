"""CLD-02: the public share board has counts, not customer names."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld02_share")
os.environ.setdefault("JWT_SECRET", "cld02-share-board-secret-32chars")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.leads.insert_one({
        "leadId": "LD26SHARE1", "customerName": "Secret Person", "mobile": "9811111111",
        "interestedModel": "Storm EV", "variant": "City",
        "currentStatus": "Booked", "accountStatus": "Active",
        "bookingDate": server.today(), "createdDate": server.today(),
    })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_anonymous_share_has_counts_and_no_names(client):
    r = await client.get("/api/share/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totalLeads"] == 1
    assert body["activeBookings"] == 1
    text = r.text
    assert "Secret Person" not in text
    assert "9811111111" not in text
    assert "LD26SHARE1" not in text
    assert body["recentBookings"][0]["model"] == "Storm EV"
    assert "name" not in body["recentBookings"][0]
