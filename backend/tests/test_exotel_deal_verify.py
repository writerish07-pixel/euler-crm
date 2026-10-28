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
    # Call 2 waits for the next morning, not another same-day gap.
    second = exo.next_calling_morning(noon, cfg)
    assert second.hour == 10 and second.minute == 15
    assert second.date() > noon.date()
    early = exo.next_calling_morning(morning, cfg)
    assert early.date() == morning.date() and early.hour == 10 and early.minute == 15
    stored = exo.as_utc_iso(nxt)
    assert "+00:00" in stored or stored.endswith("Z")
    later = datetime(2026, 10, 17, 5, 0, tzinfo=timezone.utc).isoformat()
    assert stored <= later


def test_spoken_scripts_match_first_upload():
    intro = exo.SPOKEN["intro"].lower()
    assert "akar euler" in intro
    assert "booking" in intro
    assert "pushti" in intro
    prompt = exo.SPOKEN["prompt"].lower()
    assert "hash" in prompt
    assert "bhugtan" in prompt
    assert "rashi" in exo.SPOKEN["speak"].lower()
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
    assert posts[0]["data"]["Url"] == "http://my.exotel.com/shubhammotors1/exoml/start_voice/1361923"
    assert posts[0]["data"]["CustomField"] == "LD26EXO1"
    assert any("api.in.exotel.com" in p["url"] for p in posts)


def test_connect_url_uses_app_bazaar_id():
    cfg = {
        "accountSid": "shubhammotors1",
        "flowAppId": "261787",
        "webhookSecret": "",
    }
    url = exo.connect_flow_url(cfg)
    assert url == "http://my.exotel.com/shubhammotors1/exoml/start_voice/261787"


@pytest.mark.asyncio
async def test_review_call_uses_crm_voice_not_amount_flow(monkeypatch):
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
            return FakeResp(200, {"Call": {"Sid": "rev-sid", "Status": "queued"}})

    monkeypatch.setattr(exo.httpx, "AsyncClient", FakeClient)
    cfg = {
        "accountSid": "shubhammotors1", "subdomain": "api.in.exotel.com",
        "exoPhone": "01414937655", "apiKey": "k", "apiToken": "t",
        "flowAppId": "1361923", "webhookSecret": "tok",
    }
    res = await exo._place_call_http(cfg, "9667991287", "LD26REV", purpose="review")
    assert res["ok"] is True
    data = posts[0]["data"]
    assert data["CustomField"] == "review:LD26REV"
    assert "purpose=review" in data["Url"]
    assert "/voice" in data["Url"]
    assert "start_voice" not in data["Url"]
    assert "purpose=review" in data["StatusCallback"]
    assert "Record" not in data


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["exotel_deal_verify_isolated"]
    for name in ("leads", "settings", "deal_verify_calls", "users",
                 "bookings", "payments", "activities", "price_master"):
        await isolated[name].delete_many({})
    monkeypatch.setattr(server, "db", isolated)
    monkeypatch.delenv("EXOTEL_API_KEY", raising=False)
    monkeypatch.delenv("EXOTEL_API_TOKEN", raising=False)

    async def fake_place(cfg, customer, lead_id, **kwargs):
        return {"ok": True, "statusCode": 200, "callSid": f"sid-{lead_id}", "status": "queued", "body": {},
                "purpose": kwargs.get("purpose") or "verify"}

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
async def test_recording_without_digits_stops_auto_calls(client):
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
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True

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
async def test_auto_calls_queues_historical_booked(client, monkeypatch):
    """Scheduler / cron enqueue every unverified booked file, then place."""
    placed = []

    async def capture(lead_id, *, force=False):
        placed.append(lead_id)
        return {"ok": True, "leadId": lead_id, "callSid": f"sid-{lead_id}"}

    monkeypatch.setattr(exo, "place_verify_call", capture)
    await server.db.leads.insert_one({
        "leadId": "LD26HIST", "customerName": "Old Booked Auto", "mobile": "9876500099",
        "currentStatus": "Booked", "bookingDate": "2026-02-01",
        "accountStatus": "Active",
    })
    skipped = await exo.run_due_calls(limit=25, force=True)
    assert "LD26HIST" not in placed
    assert skipped.get("ok") is True
    res = await exo.run_auto_calls(limit=25, force=True)
    assert res.get("queued") == 1
    assert "LD26HIST" in placed
    lead = await server.db.leads.find_one({"leadId": "LD26HIST"})
    assert lead["dealVerifyStatus"] == "pending"


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


def test_lead_for_viewer_hides_deal_verify_from_executive():
    lead = {
        "leadId": "LD-HIDE", "customerName": "Cx",
        "dealVerifyMismatch": True, "dealVerifyMismatchKind": "over",
        "dealVerifyAmount": 500000, "dealVerifyStatus": "answered",
        "dealVerifyRecordingUrl": "https://example/a.mp3",
        "totalReceived": 10000,
    }
    exec_row = server._lead_for_viewer(lead, {"role": "executive"})
    assert "dealVerifyMismatch" not in exec_row
    assert "dealVerifyAmount" not in exec_row
    assert "dealVerifyRecordingUrl" not in exec_row
    team = server._lead_for_viewer(lead, {"role": "team_lead"})
    assert "dealVerifyMismatch" not in team
    accounts = server._lead_for_viewer(lead, {"role": "accounts"})
    assert "dealVerifyMismatch" not in accounts
    owner = server._lead_for_viewer(lead, {"role": "owner"})
    assert owner["dealVerifyMismatch"] is True
    assert owner["dealVerifyAmount"] == 500000
    tl = server._lead_for_viewer(lead, {"role": "tl"})
    assert tl["dealVerifyMismatch"] is True
    gm = server._lead_for_viewer(lead, {"role": "sales_gm"})
    assert gm["dealVerifyMismatch"] is True


@pytest.mark.asyncio
async def test_executive_360_hides_deal_verify_mismatch(client):
    lid = "LD26EXO-HIDE"
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Hidden Mismatch", "mobile": "9876500099",
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "executive": "Ravi",
        "dealVerifyMismatch": True, "dealVerifyMismatchKind": "over",
        "dealVerifyAmount": 500000, "dealVerifyStatus": "answered",
        "totalReceived": 10000, "customerPayable": 486933,
    })
    owner_list = await client.get("/api/leads")
    assert owner_list.status_code == 200, owner_list.text
    owner_row = next(r for r in owner_list.json() if r["leadId"] == lid)
    assert owner_row.get("dealVerifyMismatch") is True

    email = "ravi-exec-hide@euler.com"
    await AUTH_DB.users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "desk#441", "name": "Ravi", "role": "executive",
    })
    assert created.status_code == 200, created.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as exec_c:
        login = await exec_c.post("/api/auth/login", json={"email": email, "password": "desk#441"})
        assert login.status_code == 200, login.text
        exec_c.headers["Authorization"] = f"Bearer {login.json()['token']}"
        listed = await exec_c.get("/api/leads")
        assert listed.status_code == 200, listed.text
        exec_row = next((r for r in listed.json() if r["leadId"] == lid), None)
        if exec_row is not None:
            assert "dealVerifyMismatch" not in exec_row
            assert "dealVerifyAmount" not in exec_row
        body = await exec_c.get(f"/api/leads/{lid}/360")
        assert body.status_code == 200, body.text
        lead = (body.json() or {}).get("lead") or {}
        assert "dealVerifyMismatch" not in lead
        assert "dealVerifyAmount" not in lead
        assert "dealVerifyRecordingUrl" not in lead


def _ist_of(iso: str) -> datetime:
    dt = datetime.fromisoformat(iso)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


def _freeze_ist(monkeypatch, when: datetime):
    monkeypatch.setattr(exo, "now_ist", lambda: when)
    monkeypatch.setattr(exo, "today_ist", lambda: when.strftime("%Y-%m-%d"))


def _booked(lead_id, mobile):
    return {
        "leadId": lead_id, "customerName": "Call Cx", "mobile": mobile,
        "currentStatus": "Booked", "bookingDate": "2026-10-16",
        "accountStatus": "Active", "totalReceived": 10000, "customerPayable": 400000,
    }


@pytest.mark.asyncio
async def test_pickup_stops_and_three_misses_stop(client, monkeypatch):
    noon = datetime(2026, 10, 16, 11, 0, tzinfo=IST)
    _freeze_ist(monkeypatch, noon)
    await server.db.leads.insert_one(_booked("LD26PICK", "9876500101"))
    await exo.enqueue_after_booking("LD26PICK")
    placed = await exo.place_verify_call("LD26PICK")
    assert placed.get("ok") is True
    await exo.handle_status({
        "CustomField": "LD26PICK", "Status": "completed", "CallSid": "sid-pick",
    })
    lead = await server.db.leads.find_one({"leadId": "LD26PICK"})
    assert lead["dealVerifyStatus"] == "picked-up"
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True
    assert not lead.get("dealVerifyAmount")

    forced = await exo.place_verify_call("LD26PICK", force=True)
    assert forced.get("ok") is True
    lead = await server.db.leads.find_one({"leadId": "LD26PICK"})
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True
    await exo.handle_status({"CustomField": "LD26PICK", "Status": "no-answer", "CallSid": "sid-force"})
    lead = await server.db.leads.find_one({"leadId": "LD26PICK"})
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True

    dialed = []

    async def capture(lead_id, *, force=False):
        dialed.append((lead_id, force))
        return {"ok": True, "leadId": lead_id}

    monkeypatch.setattr(exo, "place_verify_call", capture)
    due = await exo.run_due_calls(limit=25, force=True)
    assert due.get("ok") is True
    assert "LD26PICK" not in [row[0] for row in dialed]


@pytest.mark.asyncio
async def test_three_unanswered_calls_then_never_again(client, monkeypatch):
    _freeze_ist(monkeypatch, datetime(2026, 10, 16, 11, 0, tzinfo=IST))
    await server.db.leads.insert_one(_booked("LD26CAP", "9876500102"))
    await exo.enqueue_after_booking("LD26CAP")

    assert (await exo.place_verify_call("LD26CAP")).get("ok") is True
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert lead["dealVerifyAttempts"] == 1
    first = _ist_of(lead["dealVerifyNextAt"])
    assert first.hour == 14 and first.date().day == 16
    await exo.handle_status({"CustomField": "LD26CAP", "Status": "no-answer", "CallSid": "c1"})
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert lead["dealVerifyStatus"] == "pending"
    assert _ist_of(lead["dealVerifyNextAt"]).hour == 14

    _freeze_ist(monkeypatch, datetime(2026, 10, 16, 14, 0, tzinfo=IST))
    assert (await exo.place_verify_call("LD26CAP")).get("ok") is True
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert lead["dealVerifyAttempts"] == 2
    second = _ist_of(lead["dealVerifyNextAt"])
    assert (second.hour, second.minute, second.day) == (10, 15, 17)
    await exo.handle_status({"CustomField": "LD26CAP", "Status": "busy", "CallSid": "c2"})
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    second = _ist_of(lead["dealVerifyNextAt"])
    assert (second.hour, second.minute, second.day) == (10, 15, 17)
    assert second.month == 10

    _freeze_ist(monkeypatch, datetime(2026, 10, 17, 10, 20, tzinfo=IST))
    assert (await exo.place_verify_call("LD26CAP")).get("ok") is True
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert lead["dealVerifyAttempts"] == 3
    assert not lead.get("dealVerifyNextAt")
    await exo.handle_status({"CustomField": "LD26CAP", "Status": "no-answer", "CallSid": "c3"})
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert lead["dealVerifyStatus"] == "exhausted"
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True

    blocked = await exo.place_verify_call("LD26CAP")
    assert blocked.get("reason") == "attempt-cap"
    forced = await exo.place_verify_call("LD26CAP", force=True)
    assert forced.get("ok") is True
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True
    await exo.handle_status({"CustomField": "LD26CAP", "Status": "no-answer", "CallSid": "c-force"})
    lead = await server.db.leads.find_one({"leadId": "LD26CAP"})
    assert not lead.get("dealVerifyNextAt")
    assert lead.get("dealVerifyAutoStop") is True

    dialed = []

    async def capture(lead_id, *, force=False):
        dialed.append(lead_id)
        return {"ok": True}

    monkeypatch.setattr(exo, "place_verify_call", capture)
    await exo.run_due_calls(limit=25, force=True)
    await exo.run_auto_calls(limit=25, force=True)
    assert "LD26CAP" not in dialed


@pytest.mark.asyncio
async def test_review_clip_hangs_up_without_amount_prompt(client):
    xml = exo.exoml_review({"webhookSecret": "", "quietStart": 10, "quietEnd": 19})
    assert "Hangup" in xml
    assert "Gather" not in xml
    assert "Record" not in xml
    assert "review.mp3" in xml or "Google review" in xml
    r = await client.get("/api/integrations/exotel/voice", params={"purpose": "review"})
    assert r.status_code == 200
    assert "Gather" not in r.text
    assert "Hangup" in r.text
    verify = await client.get("/api/integrations/exotel/voice")
    assert "Gather" in verify.text


@pytest.mark.asyncio
async def test_review_call_is_separate_from_booking_calls(client, monkeypatch):
    seen = []
    original = exo._place_call_http

    async def wrap(cfg, customer, lead_id, **kwargs):
        seen.append(kwargs.get("purpose") or "verify")
        return await original(cfg, customer, lead_id, **kwargs)

    monkeypatch.setattr(exo, "_place_call_http", wrap)
    _freeze_ist(monkeypatch, datetime(2026, 10, 16, 11, 0, tzinfo=IST))
    await server.db.leads.insert_one({
        "leadId": "LD26REV", "customerName": "Review Cx", "mobile": "9876500103",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": "2026-10-16", "accountStatus": "Active",
        "dealVerifyStatus": "pending", "dealVerifyAttempts": 1,
        "dealVerifyNextAt": "2026-10-16T08:30:00+00:00",
    })
    res = await exo.place_review_call("LD26REV")
    assert res.get("ok") is True
    assert seen == ["review"]
    lead = await server.db.leads.find_one({"leadId": "LD26REV"})
    assert lead["reviewCallAttempts"] == 1
    assert not lead.get("reviewCallNextAt")
    assert lead["dealVerifyAttempts"] == 1
    assert lead["dealVerifyStatus"] == "pending"

    again = await exo.enqueue_review_call("LD26REV")
    assert again.get("skipped") in ("already-called", "already-queued")
    assert seen == ["review"]

    r = await client.post("/api/integrations/exotel/status", data={
        "CustomField": "review:LD26REV", "Status": "no-answer", "CallSid": "rev-sid",
        "purpose": "review",
    })
    assert r.status_code == 200
    lead = await server.db.leads.find_one({"leadId": "LD26REV"})
    assert lead["reviewCallStatus"] == "missed"
    assert not lead.get("reviewCallNextAt")
    assert lead["dealVerifyStatus"] == "pending"
    assert lead["dealVerifyAttempts"] == 1

    rdone = await client.post(
        "/api/integrations/exotel/status",
        params={"purpose": "review"},
        data={"CustomField": "review:LD26REV", "Status": "completed", "CallSid": "rev-sid"},
    )
    assert rdone.status_code == 200
    lead = await server.db.leads.find_one({"leadId": "LD26REV"})
    assert lead["reviewCallStatus"] == "done"
    assert lead["dealVerifyStatus"] == "pending"
    assert lead.get("dealVerifyAmount") in (None, 0, "")


@pytest.mark.asyncio
async def test_review_call_waits_for_morning_window(client, monkeypatch):
    _freeze_ist(monkeypatch, datetime(2026, 10, 16, 20, 30, tzinfo=IST))
    await server.db.leads.insert_one({
        "leadId": "LD26REVM", "customerName": "Morning", "mobile": "9876500104",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active",
    })
    queued = await exo.enqueue_review_call("LD26REVM")
    assert queued.get("queued") is True
    lead = await server.db.leads.find_one({"leadId": "LD26REVM"})
    assert lead["reviewCallStatus"] == "pending"
    assert int(lead.get("reviewCallAttempts") or 0) == 0
    nxt = _ist_of(lead["reviewCallNextAt"])
    assert (nxt.hour, nxt.minute, nxt.day) == (10, 15, 17)

    _freeze_ist(monkeypatch, datetime(2026, 10, 17, 10, 20, tzinfo=IST))
    ran = await exo.run_due_review_calls(limit=10)
    assert ran.get("placed") == 1
    lead = await server.db.leads.find_one({"leadId": "LD26REVM"})
    assert lead["reviewCallAttempts"] == 1
    assert lead["reviewCallStatus"] == "calling"
    ran_again = await exo.run_due_review_calls(limit=10)
    assert ran_again.get("placed") == 0


@pytest.mark.asyncio
async def test_review_api_failure_does_not_ring_forever(client, monkeypatch):
    async def fail_place(cfg, customer, lead_id, **kwargs):
        return {"ok": False, "statusCode": 400, "callSid": "", "status": "", "reason": "bad-flow", "body": {}}

    monkeypatch.setattr(exo, "_place_call_http", fail_place)
    _freeze_ist(monkeypatch, datetime(2026, 10, 16, 11, 0, tzinfo=IST))
    await server.db.leads.insert_one({
        "leadId": "LD26REVF", "customerName": "Fail", "mobile": "9876500109",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active",
    })
    first = await exo.place_review_call("LD26REVF")
    assert first.get("ok") is False
    lead = await server.db.leads.find_one({"leadId": "LD26REVF"})
    assert lead["reviewCallStatus"] == "pending"
    assert lead["reviewCallApiTries"] == 1
    assert int(lead.get("reviewCallAttempts") or 0) == 0
    await server.db.leads.update_one({"leadId": "LD26REVF"}, {"$set": {"reviewCallApiTries": 5}})
    second = await exo.place_review_call("LD26REVF")
    assert second.get("ok") is False
    lead = await server.db.leads.find_one({"leadId": "LD26REVF"})
    assert lead["reviewCallStatus"] == "missed"
    assert not lead.get("reviewCallNextAt")
    assert int(lead.get("reviewCallAttempts") or 0) == 0


@pytest.mark.asyncio
async def test_review_call_only_after_whatsapp_is_sent(client, monkeypatch):
    import botspace as wa
    queued = []

    async def capture(lead_id):
        queued.append(lead_id)
        return {"ok": True, "skipped": "test"}

    async def fake_send(phone, template_id, variables, name=""):
        return {"ok": True, "data": {"id": "wamid.1"}}

    monkeypatch.setattr(exo, "enqueue_review_call", capture)
    monkeypatch.setattr(wa, "send_template", fake_send)
    monkeypatch.setattr(wa, "in_customer_hours", lambda when=None: True)
    await server.db.settings.update_one(
        {"_id": "botspace"},
        {"$set": {"apiKey": "bot-key", "channelId": "chan-1", "reviewUrl": "https://g.page/akar"}},
        upsert=True,
    )
    await server.db.leads.insert_one({
        "leadId": "LD26WON", "customerName": "Won", "mobile": "9876500105",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": "2026-10-16", "interestedModel": "Hi-Load",
        "accountStatus": "Active",
    })
    sent = await wa.notify_delivery("LD26WON")
    assert sent.get("ok") is True
    assert queued == ["LD26WON"]

    opted = {
        "leadId": "LD26WOUT", "customerName": "Out", "mobile": "9876500106",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active", "whatsappOptOut": True,
    }
    await server.db.leads.insert_one(opted)
    blocked = await wa.notify_delivery("LD26WOUT")
    assert blocked.get("reason") == "opted-out"
    assert queued == ["LD26WON"]

    failed = []

    async def fail_send(*a, **k):
        failed.append(True)
        return {"ok": False, "error": "provider"}

    monkeypatch.setattr(wa, "send_template", fail_send)
    await server.db.leads.insert_one({
        "leadId": "LD26WFAIL", "customerName": "Fail", "mobile": "9876500107",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active",
    })
    bad = await wa.notify_delivery("LD26WFAIL")
    assert bad.get("ok") is False
    assert queued == ["LD26WON"]

    # Outside WhatsApp hours the link is only queued, so the call waits.
    monkeypatch.setattr(wa, "send_template", fake_send)
    monkeypatch.setattr(wa, "in_customer_hours", lambda when=None: False)
    await server.db.leads.insert_one({
        "leadId": "LD26WQUE", "customerName": "Queue", "mobile": "9876500108",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active",
    })
    held = await wa.notify_delivery("LD26WQUE")
    assert held.get("queued") is True
    assert "LD26WQUE" not in queued
    monkeypatch.setattr(wa, "in_customer_hours", lambda when=None: True)
    flushed = await wa.flush_outbox()
    assert flushed.get("flushed", 0) >= 1
    assert queued[-1] == "LD26WQUE"

    # A second delivery notice does not place another review call.
    again = await wa.notify_delivery("LD26WON")
    assert again.get("skipped") is True
    assert queued.count("LD26WON") == 1
