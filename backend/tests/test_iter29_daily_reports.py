"""Staff master + the daily WhatsApp reports.

Executives were a bare list of names in masters_list, with a SECOND hand-typed
name+mobile list in the WhatsApp settings. The two drifted silently: a mismatched
name meant that executive was never messaged, with no error anywhere. The staff
master holds name, mobile, role, target and report subscriptions in one place.

Reports (English, Utility templates):
  morning -> exec_day_ahead        each executive
  eod     -> exec_eod_scorecard    each executive
             manager_eod_volume    RM + ASM, volume only, NO money
             owner_eod_summary     owner, volume + money

The hard constraint throughout: a WhatsApp template variable may not contain a
newline, tab, or 4+ consecutive spaces — Meta rejects the send. Every variable
these jobs build is asserted single-line.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter29reports")
os.environ.setdefault("JWT_SECRET", "iter29-daily-report-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def booked_lead(c, mobile, executive, plate, deliver=False):
    r = await c.post("/api/leads", json={
        "customerName": f"ITER29 {mobile[-4:]}", "mobile": mobile,
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": executive})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": server.today(), "bookingAmount": 0})
    if deliver:
        lead = await server.db.leads.find_one({"leadId": lid})
        await c.post(f"/api/leads/{lid}/payments",
                     json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
        agents = (await c.get("/api/insurance-agents")).json()
        r = await c.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
            "rc": "Yes", "insurerName": "ICICI Lombard",
            "insuranceAgentId": agents[0]["agentId"],
            "invoiceNumber": f"INV-{plate}", "chassisNumber": f"CH-{plate}",
            "numberPlate": plate, "delivered": "Yes"})
        assert r.status_code == 200, r.text
    return lid


# ============================================================== staff master
@pytest.mark.asyncio
async def test_executives_are_seeded_onto_the_staff_master(client):
    staff = (await client.get("/api/staff")).json()
    names = {s["name"] for s in staff}
    assert "Amit" in names and "Sanjay" in names
    assert all(s["role"] == "executive" for s in staff)
    assert all("exec_morning" in s["reports"] for s in staff)


@pytest.mark.asyncio
async def test_seeding_is_idempotent(client):
    before = len((await client.get("/api/staff")).json())
    await client.post("/api/admin/seed-staff", json={})
    await client.post("/api/admin/seed-staff", json={})
    assert len((await client.get("/api/staff")).json()) == before


@pytest.mark.asyncio
async def test_executive_dropdown_now_reads_the_staff_master(client):
    """One source of truth: the dropdown and the WhatsApp list can no longer drift."""
    masters = (await client.get("/api/masters")).json()
    staff_names = {s["name"] for s in (await client.get("/api/staff")).json()
                   if s["status"] == "Active"}
    assert set(masters["executives"]) == staff_names


@pytest.mark.asyncio
async def test_staff_carries_mobile_role_and_target(client):
    r = await client.post("/api/staff", json={
        "name": "ITER29 Manager", "mobile": "9812340001", "role": "RM",
        "monthlyTarget": 40})
    assert r.status_code == 200, r.text
    row = r.json()
    assert row["mobile"] == "9812340001"
    assert row["reports"] == ["manager_eod"], "role should pick its default report"
    await client.delete(f"/api/staff/{row['staffId']}")


@pytest.mark.asyncio
async def test_unknown_role_and_report_are_rejected(client):
    bad = await client.post("/api/staff", json={"name": "ITER29 Bad", "role": "wizard"})
    assert bad.status_code == 422
    bad2 = await client.post("/api/staff", json={
        "name": "ITER29 Bad2", "role": "executive", "reports": ["not_a_report"]})
    assert bad2.status_code == 422


@pytest.mark.asyncio
async def test_renaming_an_executive_with_leads_is_refused(client):
    """lead.executive stores the NAME — a rename would orphan every one of them."""
    await booked_lead(client, "9812349001", "Amit", "RJ29-I29R")
    staff = (await client.get("/api/staff")).json()
    amit = next(s for s in staff if s["name"] == "Amit")
    r = await client.put(f"/api/staff/{amit['staffId']}", json={
        "name": "Amit Kumar", "role": "executive"})
    assert r.status_code == 409
    assert "orphan" in r.json()["detail"]


@pytest.mark.asyncio
async def test_staff_is_owner_only_to_write(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    tok = r.json()["token"]
    res = await client.post("/api/staff", json={"name": "ITER29 Sneaky", "role": "owner"},
                            headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 403


# ================================================================== reports
@pytest.mark.asyncio
async def test_owner_report_has_volume_and_money(client):
    await booked_lead(client, "9812349002", "Amit", "RJ29-I29A")
    await booked_lead(client, "9812349003", "Amit", "RJ29-I29B", deliver=True)
    d = (await client.get("/api/reports/daily/owner")).json()
    assert d["bookingsToday"] >= 2 and d["bookingsMtd"] >= 2
    assert d["deliveriesToday"] >= 1
    assert d["revenueMtd"] > 0
    for k in ("customerOutstanding", "financePendingAmount", "financePendingFiles",
              "financeByFinancer", "topExecutives"):
        assert k in d


@pytest.mark.asyncio
async def test_manager_report_carries_no_money(client):
    """RM/ASM see volume only — that was an explicit requirement."""
    d = (await client.get("/api/reports/daily/manager")).json()
    for banned in ("revenueMtd", "collectedMtd", "customerOutstanding",
                   "financePendingAmount", "financeByFinancer"):
        assert banned not in d, f"{banned} must not reach a manager report"
    assert "bookingsToday" in d and "deliveriesMtd" in d
    for e in d["executives"]:
        assert "pendingCollection" not in e


@pytest.mark.asyncio
async def test_executive_report_is_scoped_to_that_person(client):
    await booked_lead(client, "9812349004", "Sanjay", "RJ29-I29C")
    d = (await client.get("/api/reports/daily/executive/Sanjay")).json()
    assert d["name"] == "Sanjay"
    assert d["bookingsToday"] >= 1
    for k in ("pendingBookings", "pendingCollection", "followupsDue", "followupsOverdue"):
        assert k in d


@pytest.mark.asyncio
async def test_unknown_executive_is_a_404(client):
    r = await client.get("/api/reports/daily/executive/Nobody")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_executive_with_no_bookings_still_reports(client):
    """An executive who booked nothing must see zeros, not vanish."""
    d = (await client.get("/api/reports/daily/executive/Dharmendra")).json()
    assert d["name"] == "Dharmendra"
    assert d["bookingsToday"] == 0


@pytest.mark.asyncio
async def test_target_attainment_is_computed(client):
    staff = (await client.get("/api/staff")).json()
    amit = next(s for s in staff if s["name"] == "Amit")
    await client.put(f"/api/staff/{amit['staffId']}", json={
        "name": "Amit", "role": "executive", "monthlyTarget": 10,
        "mobile": amit.get("mobile", "")})
    await booked_lead(client, "9812349005", "Amit", "RJ29-I29D", deliver=True)
    d = (await client.get("/api/reports/daily/executive/Amit")).json()
    assert d["monthlyTarget"] == 10
    assert d["attainmentPct"] == round(100.0 * d["deliveriesMtd"] / 10, 1)


@pytest.mark.asyncio
async def test_no_target_leaves_attainment_null(client):
    d = (await client.get("/api/reports/daily/executive/Prasun")).json()
    assert d["monthlyTarget"] == 0
    assert d["attainmentPct"] is None


# =================================== the Meta constraint: single-line variables
def test_currency_formatting_is_indian_and_single_line():
    assert wa._inr(0) == "0"
    assert wa._inr(1500) == "1,500"
    assert wa._inr(184500000) == "18,45,00,000"
    assert wa._inr(None) == "0"
    assert "\n" not in wa._inr(1234567)


def test_one_line_strips_newlines_tabs_and_runs_of_spaces():
    """Meta rejects a variable containing any of these."""
    assert wa._one_line("a\nb") == "a b"
    assert wa._one_line("a\tb") == "a b"
    assert wa._one_line("a     b") == "a b"
    assert wa._one_line("") == "-"
    assert wa._one_line(None) == "-"


def test_top_line_is_one_line_and_capped_at_three():
    rows = [{"name": f"Exec {i}", "bookingsToday": i} for i in range(6)]
    out = wa._top_line(rows)
    assert out.count("(") == 3
    assert "\n" not in out and "\t" not in out
    assert wa._top_line([]) == "-"


def test_target_line_handles_both_shapes():
    assert wa._target_line(4, 0, None) == "4"
    assert wa._target_line(12, 15, 80.0) == "12 of 15 (80.0%)"


# ============================================================ sending the slots
@pytest_asyncio.fixture
async def wired(client, monkeypatch):
    """Give two executives + a manager + the owner a mobile, and capture sends."""
    staff = (await client.get("/api/staff")).json()
    for name, mob in (("Amit", "9812341111"), ("Sanjay", "9812342222")):
        st = next(s for s in staff if s["name"] == name)
        await client.put(f"/api/staff/{st['staffId']}", json={
            "name": name, "role": "executive", "mobile": mob, "monthlyTarget": 10})
    await client.post("/api/staff", json={
        "name": "ITER29 RM", "role": "RM", "mobile": "9812343333"})
    await client.post("/api/staff", json={
        "name": "ITER29 Owner", "role": "owner", "mobile": "9812344444"})

    # Every module shares one mongomock DB and the send-once marker persists,
    # so clear today's markers or the second test in this file sends nothing.
    for slot in ("morning", "eod"):
        await server.db.settings.delete_one({"_id": f"report_{slot}_{wa.today_ist()}"})

    sends = []

    async def fake_enqueue(*, lead, kind, phone, template_id, variables, text, customer_hours):
        sends.append({"name": lead.get("customerName"), "kind": kind, "phone": phone,
                      "template": template_id, "variables": variables,
                      "customerHours": customer_hours})
        return {"ok": True}

    monkeypatch.setattr(wa, "_enqueue_or_send", fake_enqueue)
    monkeypatch.setattr(wa, "get_config", lambda: _cfg())
    return client, sends


async def _cfg():
    return {"enabled": True, "templates": dict(wa.DEFAULT_TEMPLATES)}


@pytest.mark.asyncio
async def test_morning_slot_messages_every_executive(wired):
    _c, sends = wired
    res = await wa.run_daily_reports("morning")
    assert res["ok"] and res["sent"] >= 2
    kinds = {s["kind"] for s in sends}
    assert kinds == {"exec_morning"}, "morning must not send EOD reports"
    assert {s["phone"] for s in sends} >= {"9812341111", "9812342222"}
    assert all(s["template"] == "exec_day_ahead" for s in sends)


@pytest.mark.asyncio
async def test_eod_slot_messages_execs_manager_and_owner(wired):
    _c, sends = wired
    res = await wa.run_daily_reports("eod")
    assert res["ok"]
    by_kind = {}
    for s in sends:
        by_kind.setdefault(s["kind"], []).append(s)
    assert set(by_kind) == {"exec_eod", "manager_eod", "owner_eod"}
    assert by_kind["manager_eod"][0]["template"] == "manager_eod_volume"
    assert by_kind["owner_eod"][0]["template"] == "owner_eod_summary"


@pytest.mark.asyncio
async def test_every_variable_sent_is_single_line(wired):
    """The whole design constraint, asserted on real payloads."""
    _c, sends = wired
    await wa.run_daily_reports("eod")
    assert sends
    for s in sends:
        for v in s["variables"]:
            assert isinstance(v, str), f"{s['kind']}: {v!r} is not a string"
            assert "\n" not in v and "\t" not in v, f"{s['kind']}: newline/tab in {v!r}"
            assert "    " not in v, f"{s['kind']}: 4+ spaces in {v!r}"
            assert v != "", f"{s['kind']}: empty variable"


@pytest.mark.asyncio
async def test_reports_bypass_customer_quiet_hours(wired):
    """An EOD report at 20:00 is a staff message and must not go to the outbox."""
    _c, sends = wired
    await wa.run_daily_reports("eod")
    assert all(s["customerHours"] is False for s in sends)


@pytest.mark.asyncio
async def test_a_slot_is_sent_only_once_a_day(wired):
    """Cron retries and a second worker must not double-message anyone."""
    _c, sends = wired
    first = await wa.run_daily_reports("eod")
    n = len(sends)
    second = await wa.run_daily_reports("eod")
    assert second["alreadySent"] is True and second["sent"] == 0
    assert len(sends) == n, "a re-run must send nothing"
    assert first["sent"] > 0


@pytest.mark.asyncio
async def test_opted_out_staff_are_skipped(wired):
    c, sends = wired
    staff = (await c.get("/api/staff")).json()
    amit = next(s for s in staff if s["name"] == "Amit")
    await c.put(f"/api/staff/{amit['staffId']}", json={
        "name": "Amit", "role": "executive", "mobile": "9812341111",
        "whatsappOptIn": False})
    await wa.run_daily_reports("morning")
    assert "9812341111" not in {s["phone"] for s in sends}


@pytest.mark.asyncio
async def test_staff_without_a_mobile_is_skipped_not_crashed(wired):
    c, sends = wired
    await c.post("/api/staff", json={"name": "ITER29 NoPhone", "role": "executive"})
    res = await wa.run_daily_reports("morning")
    assert res["ok"] is True
    assert all(s["phone"] for s in sends)


@pytest.mark.asyncio
async def test_unknown_slot_is_rejected(wired):
    res = await wa.run_daily_reports("teatime")
    assert res["ok"] is False and res["sent"] == 0


# ============================================ why a slot failed (reported live)
# The morning slot worked while every EOD send failed. Nothing in the app could
# explain it: report messages carry no leadId, so they are excluded from the
# WhatsApp inbox AND the Sent box, and the run marker recorded only ok/not-ok.
def test_a_template_error_is_translated_into_an_action():
    for err in ("BotSpace 400: template not found",
                "Template exec_eod_scorecard is not approved",
                "error 132001 template does not exist"):
        hint = wa.diagnose_report_failure(err)
        assert "approved and active on Meta" in hint, err


def test_a_variable_count_error_is_told_apart_from_an_approval_error():
    hint = wa.diagnose_report_failure("132000: number of parameters does not match")
    assert "different number of variables" in hint
    assert "approved and active" not in hint


def test_a_credential_error_points_at_the_settings_page():
    assert "API key" in wa.diagnose_report_failure("BotSpace 401: unauthorized")


def test_an_empty_error_produces_no_guess():
    assert wa.diagnose_report_failure("") == ""
    assert wa.diagnose_report_failure(None) == ""


@pytest.mark.asyncio
async def test_report_status_names_the_template_behind_every_report(client):
    d = (await client.get("/api/integrations/botspace/report-status")).json()
    # The template a send actually uses, so a mismatch with Meta is visible.
    assert d["templates"]["exec_morning"]["templateId"] == "exec_day_ahead"
    assert d["templates"]["exec_eod"]["templateId"] == "exec_eod_scorecard"
    assert d["templates"]["manager_eod"]["templateId"] == "manager_eod_volume"
    assert d["templates"]["owner_eod"]["templateId"] == "owner_eod_summary"
    assert "morning" in d["slots"] and "eod" in d["slots"]


@pytest.mark.asyncio
async def test_report_status_surfaces_the_recipients_and_the_provider_error(client):
    """A failed run must say who, which template, and the provider's own words."""
    day = wa.today_ist()
    await server.db.settings.update_one({"_id": f"report_eod_{day}"}, {"$set": {
        "slot": "eod", "day": day, "sent": 0, "failed": 2,
        "sentAt": "2026-08-27T14:30:00+00:00",
        "recipients": [
            {"name": "ITER29 Owner", "kind": "owner_eod", "ok": False,
             "templateId": "owner_eod_summary", "mobile": "9812340009",
             "error": "BotSpace 400: {'error': 'template not found'}"},
            {"name": "ITER29 Exec", "kind": "exec_eod", "ok": False,
             "templateId": "exec_eod_scorecard", "mobile": "9812340008",
             "error": "BotSpace 400: {'error': 'template not approved'}"},
        ],
    }}, upsert=True)

    d = (await client.get("/api/integrations/botspace/report-status")).json()
    eod = d["slots"]["eod"]
    assert eod["lastRun"]["failed"] == 2
    assert len(eod["failures"]) == 2
    f = eod["failures"][0]
    assert f["templateId"] == "owner_eod_summary"
    assert "template not found" in f["error"]
    assert "approved and active on Meta" in f["hint"]
    await server.db.settings.delete_one({"_id": f"report_eod_{day}"})


@pytest.mark.asyncio
async def test_report_status_is_owner_only(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "executive@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        assert (await c.get("/api/integrations/botspace/report-status")).status_code == 403


@pytest.mark.asyncio
async def test_a_run_records_the_template_and_error_against_each_recipient(client):
    """The marker itself must carry enough to diagnose without the provider console."""
    day = "2026-07-15"
    await server.db.settings.delete_one({"_id": f"report_eod_{day}"})
    await wa.run_daily_reports("eod", day)
    marker = await server.db.settings.find_one({"_id": f"report_eod_{day}"})
    if marker and marker.get("recipients"):
        for r in marker["recipients"]:
            assert "templateId" in r and "variableCount" in r and "error" in r
    await server.db.settings.delete_one({"_id": f"report_eod_{day}"})
