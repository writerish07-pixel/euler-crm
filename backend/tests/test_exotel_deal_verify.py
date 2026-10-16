"""Akar Euler Exotel deal-verify — amount parse, retry, mismatch, webhooks."""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "exotel_deal_verify")
os.environ.setdefault("JWT_SECRET", "exotel-deal-verify-secret-32ch")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import exotel as exo  # noqa: E402
import server  # noqa: E402

OWNER_EMAIL = "exo-owner@euler.com"
OWNER_PASSWORD = "exo-owner-pass"
AUTH_DB = server.db
IST = timezone(timedelta(hours=5, minutes=30))


def test_parse_amount_dtmf_and_hindi():
    assert exo.parse_amount("486933") == 486933
    assert exo.parse_amount("486933#") == 486933
    assert exo.parse_amount("4.87 lakh") == 487000
    assert exo.parse_amount("4.87 लाख") == 487000
    assert exo.parse_amount("चार लाख") == 400000
    assert exo.parse_amount(400000.0) == 400000
    assert exo.parse_amount("") is None
    assert exo.parse_amount("abc") is None


def test_mismatch_vs_receipts():
    assert exo.amounts_match(10000, 10000) is True
    assert exo.amounts_match(486933, 486000) is True
    assert exo.mismatch_kind(500000, 10000) == "over"
    assert exo.mismatch_kind(5000, 10000) == "under"
    assert exo.mismatch_kind(10000, 10000) == ""


def test_quiet_hours_and_next_slot():
    cfg = {"quietStart": 10, "quietEnd": 19}
    morning = datetime(2026, 10, 16, 9, 0, tzinfo=IST)
    noon = datetime(2026, 10, 16, 12, 0, tzinfo=IST)
    evening = datetime(2026, 10, 16, 19, 30, tzinfo=IST)
    assert exo.in_quiet_hours(morning, cfg) is False
    assert exo.in_quiet_hours(noon, cfg) is True
    assert exo.in_quiet_hours(evening, cfg) is False
    nxt = exo.next_slot(evening, cfg)
    assert nxt.hour == 10
    assert nxt.date() > evening.date()


def test_exoml_is_hindi_flow():
    cfg = {
        "webhookSecret": "",
        "quietStart": 10, "quietEnd": 19,
    }
    xml = exo.exoml_start(cfg)
    assert "Gather" in xml
    assert "Record" in xml
    assert "Akar Euler" in xml or "intro.mp3" in xml
    assert "hash" in xml.lower() or "prompt.mp3" in xml


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["exotel_deal_verify_isolated"]
    for name in ("leads", "settings", "deal_verify_calls", "users",
                 "bookings", "payments", "activities", "price_master"):
        await isolated[name].delete_many({})
    monkeypatch.setattr(server, "db", isolated)
    monkeypatch.delenv("EXOTEL_API_KEY", raising=False)
    monkeypatch.delenv("EXOTEL_API_TOKEN", raising=False)

    async def fake_place(cfg, customer, lead_id):
        return {"ok": True, "statusCode": 200, "callSid": f"sid-{lead_id}", "status": "queued", "body": {}}

    monkeypatch.setattr(exo, "_place_call_http", fake_place)
    await isolated.settings.update_one(
        {"_id": "exotel"},
        {"$set": {
            "apiKey": "test-key", "apiToken": "test-token",
            "accountSid": "shubhammotors1", "exoPhone": "01414937655",
            "enabled": True, "quietStart": 10, "quietEnd": 19,
        }},
        upsert=True,
    )

    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "Exo Owner", "role": "owner",
                  "userId": "exo-owner", "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
        upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


@pytest.mark.asyncio
async def test_settings_mask_secrets(client):
    r = await client.put("/api/integrations/exotel", json={
        "accountSid": "shubhammotors1",
        "subdomain": "api.exotel.com",
        "exoPhone": "01414937655",
        "apiKey": "key-not-for-git-aaaa",
        "apiToken": "token-not-for-git-bbbb",
        "enabled": True,
        "quietStart": 10,
        "quietEnd": 19,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "apiToken" not in body
    assert body["configured"] is True
    assert body["exoPhone"].endswith("37655")
    assert "…" in (body.get("apiKeyMasked") or "")


@pytest.mark.asyncio
async def test_enqueue_then_dtmf_mismatch(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO1", "customerName": "Verify Cx", "mobile": "9876500011",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 10000, "customerPayable": 486933,
        "executive": "Ravi",
    })
    queued = await exo.enqueue_after_booking("LD26EXO1")
    assert queued["ok"] is True
    lead = await server.db.leads.find_one({"leadId": "LD26EXO1"})
    assert lead["dealVerifyStatus"] == "pending"

    placed = await exo.place_verify_call("LD26EXO1", force=True)
    assert placed.get("ok") is True
    assert placed["callSid"] == "sid-LD26EXO1"

    r = await client.post("/api/integrations/exotel/gather", data={
        "CallSid": "sid-LD26EXO1",
        "CustomField": "LD26EXO1",
        "Digits": "500000",
    })
    assert r.status_code == 200
    assert "xml" in r.headers.get("content-type", "")
    lead = await server.db.leads.find_one({"leadId": "LD26EXO1"})
    assert lead["dealVerifyAmount"] == 500000
    assert lead["dealVerifySource"] == "typed"
    assert lead["dealVerifyMismatch"] is True
    assert lead["dealVerifyMismatchKind"] == "over"
    assert lead["dealVerifyStatus"] == "answered"

    again = await exo.place_verify_call("LD26EXO1", force=True)
    assert again.get("skipped") == "already-answered"


@pytest.mark.asyncio
async def test_recording_without_digits_keeps_retrying(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO2", "customerName": "Spoke Only", "mobile": "9876500022",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 185000, "customerPayable": 185000,
    })
    await exo.enqueue_after_booking("LD26EXO2")
    r = await client.post("/api/integrations/exotel/recorded", data={
        "CallSid": "sid-x",
        "CustomField": "LD26EXO2",
        "RecordingUrl": "https://recordings.example/a.mp3",
    })
    assert r.status_code == 200
    lead = await server.db.leads.find_one({"leadId": "LD26EXO2"})
    assert lead["dealVerifyStatus"] == "listening"
    assert lead["dealVerifyRecordingUrl"].endswith("a.mp3")
    assert lead.get("dealVerifyAmount") in (None, 0, "")
    assert lead.get("dealVerifyNextAt")

    confirm = await client.post("/api/leads/LD26EXO2/deal-verify/amount", json={"amount": "185000"})
    assert confirm.status_code == 200, confirm.text
    lead = await server.db.leads.find_one({"leadId": "LD26EXO2"})
    assert lead["dealVerifySource"] == "listened"
    assert lead["dealVerifyMismatch"] is False


@pytest.mark.asyncio
async def test_spoken_transcription_counts_as_answer(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO3", "customerName": "Lakh", "mobile": "9876500033",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 400000, "customerPayable": 400000,
    })
    r = await client.post("/api/integrations/exotel/recorded", data={
        "CustomField": "LD26EXO3",
        "RecordingUrl": "https://recordings.example/b.mp3",
        "TranscriptionText": "चार लाख",
    })
    assert r.status_code == 200
    lead = await server.db.leads.find_one({"leadId": "LD26EXO3"})
    assert lead["dealVerifyAmount"] == 400000
    assert lead["dealVerifySource"] == "spoken"
    assert lead["dealVerifyMismatch"] is False


@pytest.mark.asyncio
async def test_queue_lists_mismatch(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO4", "customerName": "Gap", "mobile": "9876500044",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 10000, "customerPayable": 200000,
        "dealVerifyAmount": 200000, "dealVerifyMismatch": True, "dealVerifyMismatchKind": "over",
        "dealVerifyStatus": "answered", "dealVerifyLastAt": "2026-10-16T10:00:00+00:00",
    })
    r = await client.get("/api/deal-verify", params={"filter": "mismatch"})
    assert r.status_code == 200
    ids = [x["leadId"] for x in r.json()]
    assert "LD26EXO4" in ids
