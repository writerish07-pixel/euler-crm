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
    stored = exo.as_utc_iso(nxt)
    assert "+00:00" in stored or stored.endswith("Z")
    later = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc).isoformat()
    assert stored <= later


def test_spoken_scripts_are_plain_hindi():
    blob = " ".join(exo.SPOKEN.values()).lower()
    assert "kitne paise" in blob
    assert "gaadi" in blob
    assert "lakeer" in blob
    assert "hash" not in blob
    assert "number" not in blob
    assert "keypad" not in blob
    assert "booking" not in blob
    assert "rashi" not in blob
    assert "bhugtan" not in blob
    assert "pushti" not in blob
    for name in exo.AUDIO_CLIPS:
        assert exo.audio_path(name), name


def test_exoml_is_hindi_flow():
    cfg = {
        "webhookSecret": "",
        "quietStart": 10, "quietEnd": 19,
    }
    xml = exo.exoml_start(cfg)
    gather = xml.split("<Gather", 1)[1]
    assert "prompt.mp3" in gather
    assert "intro.mp3" in gather.split("</Gather>", 1)[0]
    assert "Record" in xml
    assert "Akar Euler" in xml or "intro.mp3" in xml
    empty = exo.exoml_record_then_thanks(cfg)
    assert "Record" in empty
    assert "Hangup" not in empty


def test_gather_config_json_uses_prompt_audio():
    cfg = {"webhookSecret": "", "accountSid": "shubhammotors1"}
    body = exo.gather_config_json(cfg)
    assert body["finish_on_key"] == "#"
    assert body["max_input_digits"] == 8
    assert "prompt.mp3" in body["gather_prompt"]["audio_url"]


@pytest.mark.asyncio
async def test_place_call_skips_record_and_retries_india_host(monkeypatch):
    posts = []

    class FakeResp:
        def __init__(self, code, body):
            self.status_code = code
            self.text = ""
            self._body = body

        def json(self):
            return self._body

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def post(self, url, data=None, auth=None):
            posts.append({"url": url, "data": dict(data or {})})
            if "api.in.exotel.com" in url:
                return FakeResp(200, {"Call": {"Sid": "sid-ok", "Status": "queued"}})
            return FakeResp(401, {"RestException": {"Status": 401, "Message": "Authentication failed"}})

    monkeypatch.setattr(exo.httpx, "AsyncClient", FakeClient)
    cfg = {
        "accountSid": "shubhammotors1", "subdomain": "api.exotel.com",
        "exoPhone": "01414937655", "apiKey": "k", "apiToken": "t",
        "flowAppId": "1361923", "webhookSecret": "",
    }
    res = await exo._place_call_http(cfg, "9667991287", "LD26EXO1")
    assert res["ok"] is True
    assert res["callSid"] == "sid-ok"
    assert "Record" not in posts[0]["data"]
    assert "StatusCallbackEvents[0]" not in posts[0]["data"]
    assert posts[0]["data"]["From"] == "09667991287"
    assert any("api.in.exotel.com" in p["url"] for p in posts)


def test_connect_url_uses_app_bazaar_id():
    cfg = {
        "accountSid": "shubhammotors1",
        "flowAppId": "261787",
        "webhookSecret": "",
    }
    url = exo.connect_flow_url(cfg)
    assert url == "http://my.exotel.com/shubhammotors1/exoml/start_voice/261787"


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
        "flowAppId": "261787",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert "apiToken" not in body
    assert body["configured"] is True
    assert body["exoPhone"].endswith("37655")
    assert "…" in (body.get("apiKeyMasked") or "")
    assert body.get("webhookSecret")
    assert body.get("flowAppId") == "261787"
    assert "start_voice/261787" in (body.get("connectUrl") or "")


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
    assert "+00:00" in (lead.get("dealVerifyNextAt") or "") or str(lead.get("dealVerifyNextAt") or "").endswith("Z")

    placed = await exo.place_verify_call("LD26EXO1", force=True)
    assert placed.get("ok") is True
    assert placed["callSid"] == "sid-LD26EXO1"

    r = await client.get(
        "/api/integrations/exotel/gather",
        params={"CallSid": "sid-LD26EXO1", "CustomField": "LD26EXO1", "digits": '"500000"'},
    )
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


@pytest.mark.asyncio
async def test_gather_timeout_records_speech(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO6", "customerName": "No Digits", "mobile": "9876500066",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 10000,
        "dealVerifyStatus": "calling", "dealVerifyCallSid": "sid-empty",
    })
    r = await client.post("/api/integrations/exotel/gather", data={
        "CallSid": "sid-empty",
        "CustomField": "LD26EXO6",
        "Digits": "",
    })
    assert r.status_code == 200
    xml = r.text
    assert "Record" in xml
    assert "Hangup" not in xml


@pytest.mark.asyncio
async def test_due_calls_skip_unenqueued_booked(client, monkeypatch):
    placed = []

    async def capture(lead_id, *, force=False):
        placed.append(lead_id)
        return {"ok": True, "leadId": lead_id}

    monkeypatch.setattr(exo, "place_verify_call", capture)
    await server.db.leads.insert_one({
        "leadId": "LD26OLD", "customerName": "Old Booked", "mobile": "9876500077",
        "currentStatus": "Booked", "bookingDate": "2026-01-01",
        "accountStatus": "Active",
    })
    await server.db.leads.insert_one({
        "leadId": "LD26NEW", "customerName": "New Booked", "mobile": "9876500088",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active",
        "dealVerifyStatus": "pending", "dealVerifyNextAt": "2020-01-01T00:00:00+00:00",
    })
    res = await exo.run_due_calls(limit=25, force=True)
    assert res.get("ok") is True
    assert "LD26NEW" in placed
    assert "LD26OLD" not in placed


@pytest.mark.asyncio
async def test_run_jobs_queues_existing_booked(client, monkeypatch):
    placed = []

    async def capture(lead_id, *, force=False):
        placed.append(lead_id)
        return {"ok": True, "leadId": lead_id, "callSid": f"sid-{lead_id}"}

    monkeypatch.setattr(exo, "place_verify_call", capture)
    await server.db.leads.insert_one({
        "leadId": "LD26OLD", "customerName": "Old Booked", "mobile": "9876500077",
        "currentStatus": "Booked", "bookingDate": "2026-01-01",
        "accountStatus": "Active",
    })
    queued = await exo.enqueue_unverified_booked(limit=50)
    assert queued["queued"] == 1
    lead = await server.db.leads.find_one({"leadId": "LD26OLD"})
    assert lead["dealVerifyStatus"] == "pending"
    res = await exo.run_due_calls(limit=25, force=True)
    assert res.get("ok") is True
    assert "LD26OLD" in placed

    r = await client.post("/api/integrations/exotel/run-jobs")
    assert r.status_code == 200
    body = r.json()
    assert "queued" in body
    assert "placed" in body


@pytest.mark.asyncio
async def test_recompute_refreshes_mismatch(client):
    await server.db.leads.insert_one({
        "leadId": "LD26EXO5", "customerName": "Later Receipt", "mobile": "9876500055",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 10000, "customerPayable": 200000,
        "dealVerifyAmount": 200000, "dealVerifyMismatch": True, "dealVerifyMismatchKind": "over",
        "dealVerifyStatus": "answered",
    })
    await server.db.payments.insert_one({
        "leadId": "LD26EXO5", "amount": 200000, "paymentMode": "UPI",
        "date": "2026-10-16", "narration": "Balance",
    })
    await server.recompute_lead("LD26EXO5")
    lead = await server.db.leads.find_one({"leadId": "LD26EXO5"})
    assert lead["dealVerifyMismatch"] is False
    assert lead["dealVerifyMismatchKind"] == ""
