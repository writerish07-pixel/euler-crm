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
    assert wa.lead_is_delivered({"currentStatus": "Delivered"})
    assert wa.lead_is_delivered({"deliveryStatus": "Delivered", "currentStatus": "Booked"})
    assert not wa.lead_is_delivered({"currentStatus": "Booked"})
    assert wa.lead_is_booked({"currentStatus": "Booked"})
    assert wa.lead_is_booked({"bookingDate": "2026-08-10", "currentStatus": "New"})
    assert wa.lead_is_booked({"currentStatus": "Delivered"})
    assert not wa.lead_is_booked({"currentStatus": "New"})
    assert not wa.lead_is_delivered({"currentStatus": "Delivery pending"})
    recent = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    assert wa.session_open(recent)
    old = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    assert not wa.session_open(old)


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["whatsapp_botspace_isolated"]
    for name in ("leads", "settings", "whatsapp_messages", "whatsapp_outbox",
                 "activities", "bookings", "payments", "price_master",
                 "staff", "finance"):
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
    url = got.json().get("webhookUrl") or ""
    assert url.startswith("http"), url
    assert url.endswith("/api/integrations/botspace/webhook")
    assert "onrender.com" not in url


@pytest.mark.asyncio
async def test_webhook_get_and_head_are_public(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as anon:
        g = await anon.get("/api/integrations/botspace/webhook")
        assert g.status_code == 200
        assert g.json().get("ok") is True
        h = await anon.head("/api/integrations/botspace/webhook")
        assert h.status_code == 200
        p = await anon.post("/api/integrations/botspace/webhook", json={})
        assert p.status_code == 200
        assert p.json().get("ok") is True


async def _seed_delivered(lead_id, **extra):
    doc = {
        "leadId": lead_id, "customerName": "Lal Chand Sharma", "mobile": "9988776655",
        "accountStatus": "Active", "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": "2026-08-10", "interestedModel": "Turbo Max", "executive": "Amit",
    }
    doc.update(extra)
    await server.db.leads.insert_one(doc)
    return doc


async def _enable_whatsapp(client):
    r = await client.put("/api/integrations/botspace", json={
        "apiKey": "botspace_test_key", "channelId": "chan-review",
        "reviewUrl": "https://g.page/r/example", "enabled": True,
    })
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_google_review_rejects_undelivered(client, monkeypatch):
    await _enable_whatsapp(client)
    await server.db.leads.insert_one({
        "leadId": "LDNEW1", "customerName": "New Lead", "mobile": "9000011111",
        "accountStatus": "Active", "currentStatus": "New",
    })
    r = await client.post("/api/leads/LDNEW1/whatsapp/google-review", json={})
    assert r.status_code == 422
    assert "Delivered" in r.text


@pytest.mark.asyncio
async def test_google_review_send_then_skip_unless_force(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append({"phone": phone, "template_id": template_id, "variables": variables, "name": name})
        return {"ok": True, "data": {"id": f"wamid.{len(calls)}"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await _seed_delivered("LD26000013", mobile="9876500013")

    thread = (await client.get("/api/leads/LD26000013/whatsapp")).json()
    assert thread["delivered"] is True
    assert thread["canSendReview"] is True
    assert not thread["deliveryReviewSentAt"]

    r = await client.post("/api/leads/LD26000013/whatsapp/google-review", json={"force": False})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("ok") is True
    assert not body.get("skipped")
    assert len(calls) == 1
    assert calls[0]["template_id"] == "delivery_review"
    assert calls[0]["phone"] == "9876500013" or "9876500013" in str(calls[0]["phone"])

    lead = await server.db.leads.find_one({"leadId": "LD26000013"})
    assert lead.get("whatsappDeliverySentAt")

    r2 = await client.post("/api/leads/LD26000013/whatsapp/google-review", json={})
    assert r2.status_code == 200, r2.text
    assert r2.json().get("skipped") is True
    assert r2.json().get("reason") == "already-sent"
    assert len(calls) == 1

    r3 = await client.post("/api/leads/LD26000013/whatsapp/google-review", json={"force": True})
    assert r3.status_code == 200, r3.text
    assert r3.json().get("ok") is True
    assert not r3.json().get("skipped")
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_google_review_opt_out_blocked(client, monkeypatch):
    async def fake_send(*a, **k):
        raise AssertionError("must not send to opted-out customer")

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await _seed_delivered("LDOPT1", whatsappOptOut=True, mobile="9000022222")
    r = await client.post("/api/leads/LDOPT1/whatsapp/google-review", json={})
    assert r.status_code == 422
    assert "STOP" in r.text


@pytest.mark.asyncio
async def test_bulk_google_review_skips_already_sent(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append(phone)
        return {"ok": True, "data": {"id": "wamid.bulk"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await _seed_delivered("LDDEL1", mobile="9111100001")
    await _seed_delivered("LDDEL2", mobile="9111100002",
                          whatsappDeliverySentAt="2026-08-01T10:00:00+00:00")
    await server.db.leads.insert_one({
        "leadId": "LDNEW2", "customerName": "Not Delivered", "mobile": "9111100003",
        "accountStatus": "Active", "currentStatus": "Booked",
    })

    r = await client.post("/api/integrations/botspace/send-delivery-reviews", json={"force": False})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sent"] == 1
    assert out["skipped"] == 1
    assert out["failed"] == 0
    assert len(calls) == 1
    lead1 = await server.db.leads.find_one({"leadId": "LDDEL1"})
    assert lead1.get("whatsappDeliverySentAt")
    lead_new = await server.db.leads.find_one({"leadId": "LDNEW2"})
    assert not lead_new.get("whatsappDeliverySentAt")


async def _seed_booked(lead_id, **extra):
    doc = {
        "leadId": lead_id, "customerName": "Booked Customer", "mobile": "9988770011",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-08-10", "interestedModel": "Turbo Max", "executive": "Amit",
    }
    doc.update(extra)
    await server.db.leads.insert_one(doc)
    return doc


@pytest.mark.asyncio
async def test_booking_whatsapp_rejects_unbooked(client):
    await _enable_whatsapp(client)
    await server.db.leads.insert_one({
        "leadId": "LDUNBK", "customerName": "Not Booked", "mobile": "9000033333",
        "accountStatus": "Active", "currentStatus": "New",
    })
    r = await client.post("/api/leads/LDUNBK/whatsapp/booking-confirm", json={})
    assert r.status_code == 422
    assert "Booking" in r.text


@pytest.mark.asyncio
async def test_booking_whatsapp_send_then_skip_unless_force(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append({"phone": phone, "template_id": template_id, "variables": variables})
        return {"ok": True, "data": {"id": f"wamid.b{len(calls)}"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await _seed_booked("LDBK13", mobile="9876500044")

    thread = (await client.get("/api/leads/LDBK13/whatsapp")).json()
    assert thread["booked"] is True
    assert thread["canSendBooking"] is True
    assert not thread["bookingConfirmSentAt"]

    r = await client.post("/api/leads/LDBK13/whatsapp/booking-confirm", json={"force": False})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    assert not r.json().get("skipped")
    assert len(calls) == 1
    assert calls[0]["template_id"] == "booking_confirm"

    lead = await server.db.leads.find_one({"leadId": "LDBK13"})
    assert lead.get("whatsappBookingSentAt")

    r2 = await client.post("/api/leads/LDBK13/whatsapp/booking-confirm", json={})
    assert r2.status_code == 200
    assert r2.json().get("skipped") is True
    assert len(calls) == 1

    r3 = await client.post("/api/leads/LDBK13/whatsapp/booking-confirm", json={"force": True})
    assert r3.status_code == 200
    assert r3.json().get("ok") is True
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_bulk_booking_whatsapp_skips_already_sent(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append(phone)
        return {"ok": True, "data": {"id": "wamid.bk"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await _seed_booked("LDBK1", mobile="9111100101")
    await _seed_booked("LDBK2", mobile="9111100102",
                       whatsappBookingSentAt="2026-08-01T10:00:00+00:00")
    await server.db.leads.insert_one({
        "leadId": "LDNEW3", "customerName": "Not Booked", "mobile": "9111100103",
        "accountStatus": "Active", "currentStatus": "New",
    })

    r = await client.post("/api/integrations/botspace/send-booking-confirms", json={"force": False})
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["sent"] == 1
    assert out["skipped"] == 1
    assert out["failed"] == 0
    assert len(calls) == 1
    lead1 = await server.db.leads.find_one({"leadId": "LDBK1"})
    assert lead1.get("whatsappBookingSentAt")
    lead_new = await server.db.leads.find_one({"leadId": "LDNEW3"})
    assert not lead_new.get("whatsappBookingSentAt")


async def _seed_stale_disabled_config():
    """Production bug: Settings form saved enabled:false with no visible toggle."""
    await server.db.settings.insert_one({
        "_id": wa.SETTINGS_ID,
        "apiKey": "botspace_test_key",
        "channelId": "chan-review",
        "reviewUrl": "https://g.page/r/example",
        "enabled": False,
    })


@pytest.mark.asyncio
async def test_get_config_ignores_mongo_enabled_false(client):
    await _seed_stale_disabled_config()
    cfg = await wa.get_config()
    assert cfg["configured"] is True
    assert cfg["enabled"] is True
    r = await client.get("/api/integrations/botspace")
    assert r.status_code == 200
    body = r.json()
    assert body["configured"] is True
    assert body["enabled"] is True


@pytest.mark.asyncio
async def test_booking_whatsapp_sends_when_mongo_enabled_false(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append({"phone": phone, "template_id": template_id})
        return {"ok": True, "data": {"id": "wamid.healed"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _seed_stale_disabled_config()
    await _seed_booked("LDBKHEAL", mobile="9928880107")

    r = await client.post("/api/leads/LDBKHEAL/whatsapp/booking-confirm", json={"force": False})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    assert not r.json().get("skipped")
    assert len(calls) == 1
    assert calls[0]["template_id"] == "booking_confirm"


@pytest.mark.asyncio
async def test_google_review_sends_when_mongo_enabled_false(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append(template_id)
        return {"ok": True, "data": {"id": "wamid.del"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _seed_stale_disabled_config()
    await _seed_delivered("LDDELHEAL", mobile="9928880108")

    r = await client.post("/api/leads/LDDELHEAL/whatsapp/google-review", json={"force": False})
    assert r.status_code == 200, r.text
    assert r.json().get("ok") is True
    assert calls == ["delivery_review"]


@pytest.mark.asyncio
async def test_save_heals_enabled_false_when_key_and_channel_present(client):
    await _seed_stale_disabled_config()
    r = await client.put("/api/integrations/botspace", json={
        "channelId": "chan-review",
        "enabled": False,
    })
    assert r.status_code == 200, r.text
    assert r.json()["enabled"] is True
    doc = await server.db.settings.find_one({"_id": wa.SETTINGS_ID})
    assert doc.get("enabled") is True


@pytest.mark.asyncio
async def test_booking_whatsapp_422_when_key_missing(client):
    await _seed_booked("LDBKNOCFG", mobile="9000044444")
    r = await client.post("/api/leads/LDBKNOCFG/whatsapp/booking-confirm", json={})
    assert r.status_code == 422
    assert "not configured" in r.text.lower()


@pytest.mark.asyncio
async def test_env_kill_switch_blocks_send(client, monkeypatch):
    monkeypatch.setenv("BOTSPACE_ENABLED", "false")
    await _seed_stale_disabled_config()
    await _seed_booked("LDBKKILL", mobile="9000055555")
    r = await client.post("/api/leads/LDBKKILL/whatsapp/booking-confirm", json={})
    assert r.status_code == 422
    assert "not configured" in r.text.lower()


@pytest.mark.asyncio
async def test_finance_overdue_uses_staff_mobile_and_skips_cancelled(client, monkeypatch):
    calls = []

    async def fake_send(phone, template_id, variables, name=""):
        calls.append({"phone": phone, "template_id": template_id})
        return {"ok": True, "data": {"id": "wamid.fin"}}

    monkeypatch.setattr(wa, "send_template", fake_send)
    await _enable_whatsapp(client)
    await server.db.staff.insert_one({
        "staffId": "ST-FIN", "name": "Amit", "role": "executive",
        "mobile": "9111100999", "status": "Active", "whatsappOptIn": True,
        "reports": [],
    })
    await server.db.leads.insert_one({
        "leadId": "LDFINCANCEL", "customerName": "Dead Deal", "mobile": "9000066666",
        "accountStatus": "Cancelled", "currentStatus": "Lost", "executive": "Amit",
        "dealCancelled": True, "deliveryDate": "2026-08-01",
        "financeFileNumber": "FN26000001",
    })
    await server.db.finance.insert_one({
        "fileNumber": "FN26000001", "leadId": "LDFINCANCEL",
        "fileOutstanding": 50000, "status": "Pending", "financer": "HDFC",
    })
    out = await wa.run_finance_reminders("2026-08-28")
    assert out.get("skippedCancelled") >= 1
    assert calls == []

    await server.db.leads.insert_one({
        "leadId": "LDFINLIVE", "customerName": "Live Deal", "mobile": "9000077777",
        "accountStatus": "Active", "currentStatus": "Delivered", "executive": "Amit",
        "dealCancelled": False, "deliveryDate": "2026-08-01",
        "financeFileNumber": "FN26000002",
    })
    await server.db.finance.insert_one({
        "fileNumber": "FN26000002", "leadId": "LDFINLIVE",
        "fileOutstanding": 40000, "status": "Pending", "financer": "HDFC",
    })
    out2 = await wa.run_finance_reminders("2026-08-28")
    assert out2.get("sent") >= 1
    assert any(c["phone"] == "9111100999" or "9111100999" in str(c["phone"]) for c in calls)
