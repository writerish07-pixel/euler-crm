"""Dealer Trade Advance — tranche register, FIFO consume on Finance receipts,
day-25 / ₹10L WhatsApp gates, and 10:30 IST daily slot. Existing finance /
payment / morning+EOD WhatsApp paths must keep working.
"""
from __future__ import annotations

import os
import sys
from datetime import date, datetime, timedelta

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "trade_advance_test")
os.environ.setdefault("JWT_SECRET", "trade-advance-secret-ok")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402
import trade_advance as ta  # noqa: E402

OWNER_EMAIL = "ta-owner@euler.com"
OWNER_PASSWORD = "ta-owner-pass"
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["trade_advance_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "TA Owner", "role": "owner",
                  "userId": "ta-owner",
                  "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
        upsert=True)

    async def noop_sync(*a, **k):
        return {"ok": True, "operation": "skipped"}

    monkeypatch.setattr(server, "sheet_sync", noop_sync)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PASSWORD})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_due_on_is_drawn_plus_30():
    assert ta.due_on("2026-11-01") == "2026-12-01"
    assert ta.days_since_drawn("2026-11-01", "2026-11-26") == 25
    assert ta.DAY25_ALERT == 25
    assert ta.LOW_BALANCE_RS == 1_000_000.0


def test_slots_due_ta_at_1030_ist_not_before():
    before = datetime(2026, 11, 26, 10, 29, tzinfo=wa.IST)
    assert "ta" not in wa.slots_due(before)
    at = datetime(2026, 11, 26, 10, 30, tzinfo=wa.IST)
    assert "ta" in wa.slots_due(at)
    # Morning exec stays at 08:00 — TA must not ride that slot.
    morning = datetime(2026, 11, 26, 8, 30, tzinfo=wa.IST)
    assert wa.slots_due(morning) == ["morning"]


@pytest.mark.asyncio
async def test_create_consume_fifo_and_release(client):
    drawn = (date.today() - timedelta(days=2)).isoformat()
    r = await client.post("/api/trade-advances", json={
        "financer": "Shriram", "amount": 1_000_000, "drawnOn": drawn,
    })
    assert r.status_code == 200, r.text
    t1 = r.json()
    assert t1["balance"] == 1_000_000
    assert t1["dueOn"] == ta.due_on(drawn)

    r2 = await client.post("/api/trade-advances", json={
        "financer": "Shriram", "amount": 500_000, "drawnOn": date.today().isoformat(),
    })
    assert r2.status_code == 200, r2.text

    # FIFO: first tranche consumed first.
    res = await ta.consume_for_finance(
        financer="Shriram", amount=200_000, lead_id="LDTA1",
        receipt_number="RC-TA-1", customer_name="Test")
    assert res["adjusted"] == 200_000
    assert res["splits"][0]["trancheId"] == t1["trancheId"]

    open_rows = await ta.list_open("Shriram")
    by_id = {x["trancheId"]: x for x in open_rows}
    assert by_id[t1["trancheId"]]["balance"] == 800_000
    assert by_id[r2.json()["trancheId"]]["balance"] == 500_000

    released = await ta.release_for_receipt("RC-TA-1")
    assert released == 200_000
    open_rows = await ta.list_open("Shriram")
    by_id = {x["trancheId"]: x for x in open_rows}
    assert by_id[t1["trancheId"]]["balance"] == 1_000_000


async def _booked_lead(client, mobile):
    r = await client.post("/api/leads", json={
        "customerName": f"TA {mobile[-4:]}", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.json().get("found"), pv.text
    await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 1000, "paymentMode": "Cash",
        "financeRequired": "Yes", "exchangeRequired": "No"})
    assert r.status_code == 200, r.text
    return lid


@pytest.mark.asyncio
async def test_finance_payment_auto_deducts_ta(client):
    drawn = date.today().isoformat()
    r = await client.post("/api/trade-advances", json={
        "financer": "Cholamandalam", "amount": 2_000_000, "drawnOn": drawn,
    })
    assert r.status_code == 200, r.text
    tranche_id = r.json()["trancheId"]

    lid = await _booked_lead(client, "9811100001")

    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 150000, "paymentMode": "Finance", "date": drawn,
        "financerName": "Cholamandalam", "narration": "TA test finance",
        "allowExcess": True,
    })
    assert pay.status_code == 200, pay.text
    body = pay.json()
    assert ce.num(body.get("tradeAdvanceAdjusted")) == 150000
    assert body.get("tradeAdvanceTrancheId") == tranche_id

    open_rows = await ta.list_open("Cholamandalam")
    assert open_rows[0]["balance"] == 1_850_000
    assert open_rows[0]["consumed"] == 150000

    # Customer payable path still recorded the Finance receipt.
    assert body["paymentMode"] == "Finance"
    assert ce.num(body["amount"]) == 150000

    # Delete releases TA without breaking payment delete.
    rn = body["receiptNumber"]
    deleted = await client.delete(f"/api/payments/{rn}")
    assert deleted.status_code == 200, deleted.text
    open_rows = await ta.list_open("Cholamandalam")
    assert open_rows[0]["balance"] == 2_000_000


@pytest.mark.asyncio
async def test_repay_closes_tranche(client):
    r = await client.post("/api/trade-advances", json={
        "financer": "Mahindra", "amount": 100000, "drawnOn": date.today().isoformat(),
    })
    tid = r.json()["trancheId"]
    await ta.consume_for_finance(financer="Mahindra", amount=40000,
                                 receipt_number="RC-REP-1", lead_id="LDx")
    rep = await client.post(f"/api/trade-advances/{tid}/repay", json={"amount": 60000})
    assert rep.status_code == 200, rep.text
    assert rep.json()["status"] == "Closed"
    assert rep.json()["balance"] == 0
    assert await ta.list_open("Mahindra") == []


@pytest.mark.asyncio
async def test_whatsapp_one_message_all_open_tas(client, monkeypatch):
    """Daily slot: one ta_daily per recipient listing every open tranche."""
    today = date.today()
    # Isolate from leftover tranches created by earlier tests on this DB.
    await server.db.trade_advances.delete_many({})
    await client.post("/api/trade-advances", json={
        "financer": "Shriram", "amount": 5_000_000,
        "drawnOn": (today - timedelta(days=26)).isoformat(),
    })
    await client.post("/api/trade-advances", json={
        "financer": "Cholamandalam", "amount": 800_000,
        "drawnOn": today.isoformat(),
    })
    # Day-25 on first; low-balance on second (< ₹10L).
    await server.db.staff.delete_many({})
    await server.db.staff.insert_one({
        "staffId": "ST-TA-OWNER", "name": "TA Owner", "role": "owner",
        "mobile": "9812347777", "status": "Active", "whatsappOptIn": True,
        "reports": ["owner_eod"],
    })
    await server.db.settings.update_one(
        {"_id": "botspace"},
        {"$set": {"financeManagerMobile": "9812348888", "apiKey": "k", "channelId": "c",
                  "enabled": True}},
        upsert=True)

    sends = []

    async def fake_send(staff, kind, variables, text, body_text=""):
        sends.append({
            "mobile": wa.digits10(staff.get("mobile")),
            "kind": kind, "variables": variables, "text": text,
        })
        return {"ok": True, "templateId": kind}

    monkeypatch.setattr(wa, "_send_report", fake_send)
    await server.db.settings.delete_one({"_id": f"report_ta_{wa.today_ist()}"})
    res = await wa.run_daily_reports("ta", force=True)
    assert res.get("ok") is True

    daily = [s for s in sends if s["kind"] == "ta_daily"]
    day25 = [s for s in sends if s["kind"] == "ta_day25"]
    low = [s for s in sends if s["kind"] == "ta_low"]

    # One daily message per recipient (owner + finance manager), both listing all TAs.
    assert len(daily) == 2
    summary = daily[0]["variables"][1]
    assert "Shriram" in summary and "Cholamandalam" in summary
    assert daily[0]["mobile"] != daily[1]["mobile"]

    assert day25, "day-25 alert expected for 26-day-old tranche"
    assert all(s["variables"][0] == "Shriram" for s in day25)
    assert low, "low-balance alert expected for ₹8L tranche"
    assert all(s["variables"][0] == "Cholamandalam" for s in low)

    # Idempotent: second run same day does not re-send.
    sends.clear()
    res2 = await wa.run_daily_reports("ta", force=False)
    assert res2.get("alreadySent") or len(sends) == 0


@pytest.mark.asyncio
async def test_ta_empty_day_marks_marker(client, monkeypatch):
    await server.db.staff.delete_many({})
    await server.db.staff.insert_one({
        "staffId": "ST-TA-EMPTY", "name": "Empty Owner", "role": "owner",
        "mobile": "9812349999", "status": "Active", "whatsappOptIn": True,
        "reports": ["owner_eod"],
    })
    await server.db.settings.update_one(
        {"_id": "botspace"}, {"$set": {"apiKey": "k", "channelId": "c", "enabled": True}},
        upsert=True)

    async def fake_send(*a, **k):
        return {"ok": True, "templateId": "x"}

    monkeypatch.setattr(wa, "_send_report", fake_send)
    day = wa.today_ist()
    await server.db.settings.delete_one({"_id": f"report_ta_{day}"})
    await server.db.trade_advances.delete_many({})
    res = await wa.run_daily_reports("ta", force=True)
    assert res.get("ok") is True
    marker = await server.db.settings.find_one({"_id": f"report_ta_{day}"})
    assert marker and marker.get("empty") is True


@pytest.mark.asyncio
async def test_backdated_receipt_skips_future_draw(client):
    """Finance receipt dated before a tranche's drawnOn must not consume it."""
    await server.db.trade_advances.delete_many({})
    await client.post("/api/trade-advances", json={
        "financer": "HDFC BANK", "amount": 1_000_000, "drawnOn": "2026-11-26",
    })
    res = await ta.consume_for_finance(
        financer="HDFC BANK", amount=100_000, receipt_number="RC-BACK",
        as_of="2026-11-25")
    assert res["adjusted"] == 0.0
    open_rows = await ta.list_open("HDFC BANK")
    assert open_rows[0]["balance"] == 1_000_000

    res2 = await ta.consume_for_finance(
        financer="HDFC BANK", amount=100_000, receipt_number="RC-OK",
        as_of="2026-11-26")
    assert res2["adjusted"] == 100_000


@pytest.mark.asyncio
async def test_lead_delete_releases_ta(client):
    await server.db.trade_advances.delete_many({})
    await client.post("/api/trade-advances", json={
        "financer": "IDFC", "amount": 500_000, "drawnOn": date.today().isoformat(),
    })
    lid = await _booked_lead(client, "9811100099")
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 50000, "paymentMode": "Finance", "date": date.today().isoformat(),
        "financerName": "IDFC", "allowExcess": True,
    })
    assert pay.status_code == 200, pay.text
    assert (await ta.list_open("IDFC"))[0]["balance"] == 450_000

    gone = await client.delete(f"/api/leads/{lid}")
    assert gone.status_code == 200, gone.text
    assert (await ta.list_open("IDFC"))[0]["balance"] == 500_000


def test_documented_ta_templates_match_sender_variable_counts():
    docs = __import__("re")
    from pathlib import Path
    import re
    doc = (Path(__file__).resolve().parents[2] / "docs" / "whatsapp-meta-templates.md").read_text()
    out = {}
    for sec in re.split(r"\n## ", doc):
        m = re.match(r"[A-Z]\.?\s*`([a-z_0-9]+)`", sec)
        blocks = re.findall(r"```\n(.*?)```", sec, re.S)
        if not m or not blocks:
            continue
        body = blocks[0].strip()
        out[m.group(1)] = sorted({int(n) for n in re.findall(r"\{\{(\d+)\}\}", body)})
    assert out["ta_daily_statement"] == [1, 2, 3]
    assert out["ta_day25_clear"] == [1, 2, 3, 4]
    assert out["ta_low_balance"] == [1, 2, 3, 4]
    # Bodies must not start/end with a variable (Meta rule).
    for name in ("ta_daily_statement", "ta_day25_clear", "ta_low_balance"):
        for sec in re.split(r"\n## ", doc):
            if f"`{name}`" in sec[:80]:
                body = re.findall(r"```\n(.*?)```", sec, re.S)[0].strip()
                assert not body.startswith("{{")
                assert not body.endswith("}}")
