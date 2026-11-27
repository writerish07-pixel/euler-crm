"""TA cover vs pending Remaining, settle-in-finance, and Lead Outstanding register.

Guarantees:
- fileOutstanding (cash) is unchanged by TA consume; taCoveredAmount stamps coverage
- effective open = cash OS − settledInFinance − TA cover; pending uses that
- settle mode=finance writes down without reopening customer OS or fake receipts
- settle mode=customer still uses the shortfall → customer path
- GET /leads?outstanding=1 returns only leads with customerOutstanding > 0
"""
from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ta_cover_settle_test")
os.environ.setdefault("JWT_SECRET", "ta-cover-settle-secret-ok")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402
import trade_advance as ta  # noqa: E402

OWNER_EMAIL = "tacov-owner@euler.com"
OWNER_PASSWORD = "tacov-owner-pass"
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["ta_cover_settle_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "TA Cover Owner", "role": "owner",
                  "userId": "tacov-owner",
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


async def _booked_lead(client, mobile):
    r = await client.post("/api/leads", json={
        "customerName": f"TACov {mobile[-4:]}", "mobile": mobile,
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


def test_effective_file_open_math():
    assert ta.effective_file_open({
        "fileOutstanding": 50000, "taCoveredAmount": 20000,
        "settledInFinanceAmount": 0,
    }) == pytest.approx(30000)
    assert ta.effective_file_open({
        "fileOutstanding": 50000, "taCoveredAmount": 50000,
    }) == pytest.approx(0)
    # When cash OS is 0 but sanctioned is present, derive then subtract cover.
    assert ta.effective_file_open({
        "sanctionedAmount": 100000, "receivedAgainstFile": 40000,
        "settledInFinanceAmount": 10000, "taCoveredAmount": 20000,
        "fileOutstanding": 0,
    }) == pytest.approx(30000)
    # When fileOutstanding missing, derive from sanctioned − received − settled
    assert ta.effective_file_open({
        "sanctionedAmount": 100000, "receivedAgainstFile": 40000,
        "settledInFinanceAmount": 10000, "taCoveredAmount": 20000,
    }) == pytest.approx(30000)


@pytest.mark.asyncio
async def test_ta_cover_shrinks_pending_not_cash_os(client):
    drawn = date.today().isoformat()
    tr = await client.post("/api/trade-advances", json={
        "financer": "Cholamandalam", "amount": 2_000_000, "drawnOn": drawn,
    })
    assert tr.status_code == 200, tr.text

    lid = await _booked_lead(client, "9812000001")
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    finance_amt = min(150_000.0, max(due, 150_000.0))
    assert finance_amt > 10_000

    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": finance_amt, "paymentMode": "Finance", "financerName": "Cholamandalam",
        "date": drawn, "allowExcess": True})
    assert pay.status_code == 200, pay.text
    body = pay.json()
    fn = body["financeFileNumber"]
    assert fn
    assert ce.num(body.get("tradeAdvanceAdjusted")) == pytest.approx(finance_amt, abs=1.0)

    f = await server.db.finance.find_one({"fileNumber": fn})
    cash_os = ce.num(f.get("fileOutstanding"))
    covered = ce.num(f.get("taCoveredAmount"))
    # Cash OS stays on the file; TA cover is stamped separately.
    assert cash_os == pytest.approx(finance_amt, abs=1.0)
    assert covered == pytest.approx(finance_amt, abs=1.0)
    assert ta.effective_file_open(f) == pytest.approx(0, abs=1.0)

    pending = await client.get("/api/finance", params={"view": "pending"})
    assert pending.status_code == 200, pending.text
    pending_fns = {row["fileNumber"] for row in pending.json()}
    assert fn not in pending_fns


@pytest.mark.asyncio
async def test_settle_finance_does_not_reopen_customer(client):
    lid = await _booked_lead(client, "9812000002")
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    finance_amt = 50_000.0
    assert due > finance_amt + 1000

    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": finance_amt, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]

    rem = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 30_000, "date": "2026-08-12", "reference": "NEFT-PART"})
    assert rem.status_code == 200, rem.text
    leftover = 20_000.0
    assert ce.num(rem.json()["fileOutstanding"]) == pytest.approx(leftover, abs=0.5)

    before = await server.db.leads.find_one({"leadId": lid})
    before_os = ce.num(before.get("customerOutstanding"))
    before_recv = ce.num(before.get("totalReceived"))

    settled = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": leftover, "mode": "finance", "date": "2026-08-16",
        "reason": "Financer write-down agreed"})
    assert settled.status_code == 200, settled.text
    body = settled.json()
    assert body["ok"] is True
    assert body["mode"] == "finance"
    assert ce.num(body["settledAmount"]) == pytest.approx(leftover, abs=0.5)

    f = await server.db.finance.find_one({"fileNumber": fn})
    assert ce.num(f.get("settledInFinanceAmount")) == pytest.approx(leftover, abs=0.5)
    assert ce.num(f.get("fileOutstanding")) == pytest.approx(0, abs=0.5)
    assert ta.effective_file_open(f) == pytest.approx(0, abs=0.5)

    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("customerOutstanding")) == pytest.approx(before_os, abs=0.5)
    assert ce.num(after.get("totalReceived")) == pytest.approx(before_recv, abs=0.5)
    # No FinanceShortfall ledger row
    short = await server.db.payments.find_one({
        "leadId": lid, "entryType": "FinanceShortfall", "financeFileNumber": fn})
    assert short is None


@pytest.mark.asyncio
async def test_settle_customer_still_reopens_os(client):
    lid = await _booked_lead(client, "9812000003")
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    finance_amt = 40_000.0
    assert due > finance_amt + 1000

    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": finance_amt, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]

    rem = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 25_000, "date": "2026-08-12", "reference": "NEFT-PART2"})
    assert rem.status_code == 200, rem.text
    leftover = 15_000.0

    before_os = ce.num((await server.db.leads.find_one({"leadId": lid})).get("customerOutstanding"))
    moved = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": leftover, "mode": "customer", "date": "2026-08-17",
        "reason": "Customer will pay"})
    assert moved.status_code == 200, moved.text
    assert moved.json().get("ok") is True
    assert "shortfall" in moved.json()

    after_os = ce.num((await server.db.leads.find_one({"leadId": lid})).get("customerOutstanding"))
    assert after_os == pytest.approx(before_os + leftover, abs=1.0)


@pytest.mark.asyncio
async def test_leads_outstanding_register(client):
    with_os = await _booked_lead(client, "9812000004")
    cleared = await _booked_lead(client, "9812000005")

    lead = await server.db.leads.find_one({"leadId": cleared})
    due = ce.num(lead.get("customerOutstanding"))
    assert due > 0
    pay = await client.post(f"/api/leads/{cleared}/payments", json={
        "amount": due, "paymentMode": "Cash", "date": "2026-08-20"})
    assert pay.status_code == 200, pay.text
    cleared_lead = await server.db.leads.find_one({"leadId": cleared})
    assert ce.num(cleared_lead.get("customerOutstanding")) <= 0.01

    open_lead = await server.db.leads.find_one({"leadId": with_os})
    assert ce.num(open_lead.get("customerOutstanding")) > 0.01

    rows = await client.get("/api/leads", params={"outstanding": "1"})
    assert rows.status_code == 200, rows.text
    ids = {r["leadId"] for r in rows.json()}
    assert with_os in ids
    assert cleared not in ids
    assert all(ce.num(r.get("customerOutstanding")) > 0.01 for r in rows.json())


@pytest.mark.asyncio
async def test_settle_finance_requires_reason(client):
    lid = await _booked_lead(client, "9812000006")
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    finance_amt = min(30_000.0, due - 500)
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": finance_amt, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]
    await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": finance_amt - 5000, "date": "2026-08-12", "reference": "X"})
    bad = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": 5000, "mode": "finance", "date": "2026-08-18", "reason": ""})
    assert bad.status_code == 422


@pytest.mark.asyncio
async def test_settle_customer_without_date_ok(client):
    """LeadDrawer settle omits date — must not 422 on FinanceShortfallIn(date=None)."""
    lid = await _booked_lead(client, "9812000007")
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    finance_amt = 40_000.0
    assert due > finance_amt + 1000
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": finance_amt, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]
    await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 25_000, "date": "2026-08-12", "reference": "NEFT"})
    moved = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": 15_000, "mode": "customer", "reason": "Customer pays"})
    assert moved.status_code == 200, moved.text
    assert moved.json().get("ok") is True


@pytest.mark.asyncio
async def test_settle_customer_keeps_fitting_ta_cover(client):
    drawn = date.today().isoformat()
    tr = await client.post("/api/trade-advances", json={
        "financer": "Cholamandalam", "amount": 2_000_000, "drawnOn": drawn,
    })
    assert tr.status_code == 200, tr.text

    lid = await _booked_lead(client, "9812000008")
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 80_000, "paymentMode": "Finance", "financerName": "Cholamandalam",
        "date": drawn, "allowExcess": True})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]
    assert ce.num(pay.json().get("tradeAdvanceAdjusted")) == pytest.approx(80_000, abs=1.0)

    # Partial financer receipt leaves cash OS 50k with TA cover still 80k → peel to 50k on sync.
    rem = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 30_000, "date": drawn, "reference": "PART"})
    assert rem.status_code == 200, rem.text
    f = await server.db.finance.find_one({"fileNumber": fn})
    cash_os = ce.num(f.get("fileOutstanding"))
    assert cash_os == pytest.approx(50_000, abs=1.0)
    # Ensure cover is at most cash OS after receipt peel.
    covered = ce.num(f.get("taCoveredAmount"))
    if covered > cash_os + 0.01:
        await ta.sync_file_ta_cover(fn)
        # If adjustments still exceed cash OS, peel manually like the receipt path.
        covered = await ta._ta_covered_for_file(fn)
        excess = ce.round2(max(0.0, covered - cash_os))
        if excess > 0.01:
            await ta.release_for_file_amount(fn, excess)
        f = await server.db.finance.find_one({"fileNumber": fn})
        covered = ce.num(f.get("taCoveredAmount"))
    # Force a partial cover scenario: keep 30k cover on 50k cash → effective 20k.
    await server.db.finance.update_one(
        {"fileNumber": fn}, {"$set": {"taCoveredAmount": 30_000}})
    # And trim TA adjustments to match (so sync does not rewrite cover).
    # If adjustments disagree, settle still uses stamped taCoveredAmount via effective_file_open.
    f = await server.db.finance.find_one({"fileNumber": fn})
    assert ta.effective_file_open(f) == pytest.approx(20_000, abs=1.0)

    before_os = ce.num((await server.db.leads.find_one({"leadId": lid})).get("customerOutstanding"))
    moved = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": 20_000, "mode": "customer", "date": drawn, "reason": "Uncovered slice"})
    assert moved.status_code == 200, moved.text

    f2 = await server.db.finance.find_one({"fileNumber": fn})
    # Cash OS shrunk by 20k → 30k; fitting TA cover of 30k must remain (effective 0).
    assert ce.num(f2.get("fileOutstanding")) == pytest.approx(30_000, abs=1.0)
    assert ce.num(f2.get("taCoveredAmount")) == pytest.approx(30_000, abs=1.0)
    assert ta.effective_file_open(f2) == pytest.approx(0, abs=1.0)
    after_os = ce.num((await server.db.leads.find_one({"leadId": lid})).get("customerOutstanding"))
    assert after_os == pytest.approx(before_os + 20_000, abs=1.0)


@pytest.mark.asyncio
async def test_receipt_after_finance_settle_keeps_writeoff(client):
    lid = await _booked_lead(client, "9812000009")
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 100_000, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10", "allowExcess": True})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]

    settled = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": 20_000, "mode": "finance", "date": "2026-08-16",
        "reason": "Agreed write-down"})
    assert settled.status_code == 200, settled.text

    rem = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 30_000, "date": "2026-08-17", "reference": "NEFT"})
    assert rem.status_code == 200, rem.text
    # 100k − 20k write-off − 30k receipt = 50k open (not 70k).
    assert ce.num(rem.json()["fileOutstanding"]) == pytest.approx(50_000, abs=1.0)
    f = await server.db.finance.find_one({"fileNumber": fn})
    assert ce.num(f.get("settledInFinanceAmount")) == pytest.approx(20_000, abs=0.5)

    # Cannot book more than net commitment remaining (50k).
    too_much = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 60_000, "date": "2026-08-18", "reference": "OVER"})
    assert too_much.status_code == 422


@pytest.mark.asyncio
async def test_settle_after_floaty_receipt_balance(client):
    lid = await _booked_lead(client, "9812000010")
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 100_000, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10", "allowExcess": True})
    assert pay.status_code == 200, pay.text
    fn = pay.json()["financeFileNumber"]
    # Leave a non-exact double on disk (as Mongo $subtract can).
    await server.db.finance.update_one({"fileNumber": fn}, {"$set": {
        "receivedAgainstFile": 75000.99,
        "fileOutstanding": 24999.009999999995,
        "status": "Partial",
    }})
    settled = await client.post(f"/api/finance/{fn}/settle", json={
        "amount": 24999.01, "mode": "finance", "date": "2026-08-19",
        "reason": "Clear float remainder"})
    assert settled.status_code == 200, settled.text
    f = await server.db.finance.find_one({"fileNumber": fn})
    assert ce.num(f.get("fileOutstanding")) == pytest.approx(0, abs=0.02)
