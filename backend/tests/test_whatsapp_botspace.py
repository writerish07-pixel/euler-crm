"""WhatsApp / BotSpace — Euler-lead filter and booking/delivery stay safe."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "whatsapp_botspace")
os.environ.setdefault("JWT_SECRET", "whatsapp-botspace-secret-ok")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

OWNER_EMAIL = "wa-owner@euler.com"
OWNER_PASSWORD = "wa-owner-pass"
AUTH_DB = server.db


def test_phone_and_followup_rules():
    assert wa.digits10("+91 98765 43210") == "9876543210"
    assert wa.e164_in("9876543210") == "+919876543210"
    assert wa.followup_due({
        "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-08-15",
    }, "2026-08-18")
    assert not wa.followup_due({
        "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-08-15",
    }, "2026-08-16")
    assert not wa.followup_due({
        "accountStatus": "Active", "currentStatus": "Booked",
        "createdDate": "2026-08-15", "bookingDate": "2026-08-16",
    }, "2026-08-18")
    assert wa.inbound_is_stop("STOP")
    assert wa.inbound_is_stop("stop please")
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert wa.session_open(recent)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert not wa.session_open(old)


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["whatsapp_botspace_isolated"]
    for name in ("leads", "settings", "whatsapp_messages", "whatsapp_outbox",
                 "activities", "bookings", "payments", "price_master"):
        await isolated[name].delete_many({})
    monkeypatch.setattr(server, "db", isolated)
    monkeypatch.delenv("BOTSPACE_API_KEY", raising=False)
    monkeypatch.delenv("BOTSPACE_CHANNEL_ID", raising=False)

    async def boom(*a, **k):
        raise RuntimeError("BotSpace must not be called in this test")

    monkeypatch.setattr(wa, "send_template", boom)
    monkeypatch.setattr(wa, "send_session_text", boom)

    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "WA Owner", "role": "owner",
                  "userId": "wa-owner", "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
        upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


@pytest.mark.asyncio
async def test_webhook_ignores_unknown_phone(client):
    r = await client.post("/api/integrations/botspace/webhook", json={
        "event": "message-event", "direction": "incoming",
        "phone": {"countryCode": "91", "phone": "9000000000"},
        "payload": {"type": "text", "payload": {"text": "hello from tata"}},
    })
    assert r.status_code == 200
    assert r.json().get("ignored") is True
    assert await server.db.whatsapp_messages.count_documents({}) == 0


@pytest.mark.asyncio
async def test_webhook_keeps_euler_lead_only(client):
    await server.db.leads.insert_one({
        "leadId": "LDWA1", "customerName": "Euler Customer", "mobile": "9876543210",
        "accountStatus": "Active", "currentStatus": "New", "createdDate": "2026-08-10",
    })
    r = await client.post("/api/integrations/botspace/webhook", json={
        "event": "message-event", "direction": "incoming",
        "id": "msg-1",
        "phone": {"countryCode": "91", "phone": "9876543210"},
        "payload": {"type": "text", "payload": {"text": "हाँ, कॉल करें"}},
    })
    assert r.status_code == 200
    assert r.json().get("leadId") == "LDWA1"
    assert await server.db.whatsapp_messages.count_documents({"leadId": "LDWA1"}) == 1
    thread = (await client.get("/api/leads/LDWA1/whatsapp")).json()
    assert thread["sessionOpen"] is True
    assert thread["messages"][0]["text"] == "हाँ, कॉल करें"


@pytest.mark.asyncio
async def test_stop_opts_out(client):
    await server.db.leads.insert_one({
        "leadId": "LDWA2", "customerName": "Stop Me", "mobile": "9123456780",
        "accountStatus": "Active", "currentStatus": "New",
    })
    r = await client.post("/api/integrations/botspace/webhook", json={
        "event": "message-event", "direction": "incoming",
        "phone": {"phone": "9123456780", "countryCode": "91"},
        "payload": {"type": "text", "payload": {"text": "STOP"}},
    })
    assert r.json().get("optOut") is True
    lead = await server.db.leads.find_one({"leadId": "LDWA2"})
    assert lead.get("whatsappOptOut") is True
    assert not wa.followup_due({**lead, "createdDate": "2026-08-01"}, "2026-08-18")


@pytest.mark.asyncio
async def test_booking_still_succeeds_when_whatsapp_broken(client, monkeypatch):
    await server.db.price_master.insert_one({
        "priceId": "PM-WA", "model": "Turbo Max", "variant": "Maxx (PV)",
        "exShowroom": 770000, "rto": 8000, "insurance": 12000, "status": "active",
    })

    async def fail_notify(lead_id):
        raise RuntimeError("BotSpace down")

    monkeypatch.setattr(wa, "notify_booking", fail_notify)
    r = await client.post("/api/leads", json={
        "customerName": "Book Safe", "mobile": "9111122233",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    if pv.json().get("found"):
        await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    booked = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-18", "bookingAmount": 0, "paymentMode": "Cash",
        "executive": "Amit", "financeRequired": "No", "exchangeRequired": "No",
    })
    assert booked.status_code == 200, booked.text
    assert booked.json()["bookingId"]


@pytest.mark.asyncio
async def test_settings_masks_key(client):
    r = await client.put("/api/integrations/botspace", json={
        "apiKey": "botspace_secret_key_value", "channelId": "chan-1",
    })
    assert r.status_code == 200
    assert "secret_key_value" not in r.text
    assert r.json()["hasKey"] is True
    assert r.json()["channelId"] == "chan-1"
    got = await client.get("/api/integrations/botspace")
    assert "secret_key_value" not in got.text
