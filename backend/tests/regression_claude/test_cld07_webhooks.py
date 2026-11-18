"""CLD-07: Exotel and BotSpace webhooks do not write when no secret is set."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld07_webhooks")
os.environ.setdefault("JWT_SECRET", "cld07-webhook-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.db.settings.delete_many({"_id": {"$in": ["exotel", "botspace"]}})
    await server.db.leads.delete_many({"leadId": "LD26CLD07"})
    await server.db.leads.insert_one({
        "leadId": "LD26CLD07", "customerName": "Hook", "mobile": "9812345678",
        "currentStatus": "Booked", "accountStatus": "Active", "totalReceived": 10000,
    })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest.mark.asyncio
async def test_forged_gather_without_secret_does_not_write(client):
    r = await client.post("/api/integrations/exotel/gather", data={
        "CustomField": "LD26CLD07", "Digits": "123456",
    })
    assert r.status_code == 200
    lead = await server.db.leads.find_one({"leadId": "LD26CLD07"})
    assert not lead.get("dealVerifyAmount")


@pytest.mark.asyncio
async def test_correct_secret_records_and_wrong_secret_is_rejected(client):
    await server.db.settings.update_one(
        {"_id": "exotel"}, {"$set": {"webhookSecret": "exo-ok"}}, upsert=True)
    bad = await client.post("/api/integrations/exotel/gather", data={
        "CustomField": "LD26CLD07", "Digits": "123456",
    }, headers={"x-exotel-token": "nope"})
    assert bad.status_code == 401
    ok = await client.post("/api/integrations/exotel/gather", data={
        "CustomField": "LD26CLD07", "Digits": "123456",
    }, params={"token": "exo-ok"})
    assert ok.status_code == 200, ok.text
    lead = await server.db.leads.find_one({"leadId": "LD26CLD07"})
    assert lead.get("dealVerifyAmount") == 123456


@pytest.mark.asyncio
async def test_botspace_without_secret_returns_200_and_writes_nothing(client):
    r = await client.post("/api/integrations/botspace/webhook", json={
        "event": "message-event", "direction": "incoming",
        "phone": {"countryCode": "91", "phone": "9812345678"},
        "payload": {"type": "text", "payload": {"text": "hello"}},
    })
    assert r.status_code == 200
    assert await server.db.whatsapp_messages.count_documents({"leadId": "LD26CLD07"}) == 0
