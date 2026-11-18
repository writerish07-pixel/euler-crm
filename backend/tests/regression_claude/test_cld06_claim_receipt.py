"""CLD-06: a claim receipt cannot be posted twice or past the eligible amount."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld06_receipts")
os.environ.setdefault("JWT_SECRET", "cld06-receipt-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("SEED_DEMO_USERS", "1")

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
async def test_duplicate_and_over_eligible_are_rejected(client):
    await server.db.claims.delete_many({"leadId": "LD26CLD06"})
    await server.db.claims.insert_one({
        "leadId": "LD26CLD06", "componentKey": "consumer", "manual": True,
        "eligibleClaim": 10000, "claimAmount": 10000, "receivedAmount": 0, "receipts": [],
    })
    body = {"leadId": "LD26CLD06", "componentKey": "consumer", "amount": 10000, "date": "2026-11-18", "reference": "UTR1"}
    first = await client.post("/api/claims/receipt", json=body)
    assert first.status_code == 200, first.text
    dup = await client.post("/api/claims/receipt", json=body)
    assert dup.status_code == 409, dup.text
    over = await client.post("/api/claims/receipt", json={**body, "amount": 5000, "reference": "UTR2"})
    assert over.status_code == 422, over.text
    allowed = await client.post("/api/claims/receipt", json={**body, "amount": 5000, "reference": "UTR2", "allowExcess": True})
    assert allowed.status_code == 200, allowed.text
    claim = await server.db.claims.find_one({"leadId": "LD26CLD06", "componentKey": "consumer"})
    assert claim["receivedAmount"] == 15000
    assert len(claim["receipts"]) == 2


@pytest.mark.asyncio
async def test_four_receipts_sum(client):
    await server.db.claims.delete_many({"leadId": "LD26CLD06B"})
    await server.db.claims.insert_one({
        "leadId": "LD26CLD06B", "componentKey": "loyalty", "manual": True,
        "eligibleClaim": 0, "receivedAmount": 0, "receipts": [],
    })
    for i, amount in enumerate((100, 200, 300, 400)):
        r = await client.post("/api/claims/receipt", json={
            "leadId": "LD26CLD06B", "componentKey": "loyalty", "amount": amount,
            "date": "2026-11-18", "reference": f"R{i}",
        })
        assert r.status_code == 200, r.text
    claim = await server.db.claims.find_one({"leadId": "LD26CLD06B"})
    assert claim["receivedAmount"] == 1000
    assert sum(x["amount"] for x in claim["receipts"]) == 1000
