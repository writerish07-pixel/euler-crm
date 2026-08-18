"""Owner can delete a wrongly posted payment; staff cannot.

Delete recalculates lead totals and remaining receipt running totals. A Finance
receipt cannot be removed once the financer has disbursed more than would remain
committed.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "owner_payment_delete")
os.environ.setdefault("JWT_SECRET", "owner-payment-delete-secret-ok")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

OWNER_EMAIL = "paydel-owner@euler.com"
OWNER_PASSWORD = "paydel-owner-pass"
EXEC_EMAIL = "paydel-exec@euler.com"
EXEC_PASSWORD = "paydel-exec-pass"
ACCT_EMAIL = "paydel-acct@euler.com"
ACCT_PASSWORD = "paydel-acct-pass"
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["owner_payment_delete_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "PayDel Owner", "role": "owner",
                  "userId": "paydel-owner", "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
        upsert=True)
    await AUTH_DB.users.update_one(
        {"email": EXEC_EMAIL},
        {"$set": {"email": EXEC_EMAIL, "name": "PayDel Exec", "role": "executive",
                  "userId": "paydel-exec", "passwordHash": server.authmod.hash_password(EXEC_PASSWORD)}},
        upsert=True)
    await AUTH_DB.users.update_one(
        {"email": ACCT_EMAIL},
        {"$set": {"email": ACCT_EMAIL, "name": "PayDel Acct", "role": "accounts",
                  "userId": "paydel-acct", "passwordHash": server.authmod.hash_password(ACCT_PASSWORD)}},
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


async def _login(client, email, password):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


async def _booked_lead(client, mobile, *, pay_full=True):
    r = await client.post("/api/leads", json={
        "customerName": f"PayDel {mobile[-4:]}", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.json().get("found"), pv.text
    await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 1000, "paymentMode": "Cash",
        "financeRequired": "No", "exchangeRequired": "No"})
    assert r.status_code == 200, r.text
    if pay_full:
        lead = await server.db.leads.find_one({"leadId": lid})
        due = ce.num(lead.get("customerOutstanding"))
        if due > 0:
            r = await client.post(f"/api/leads/{lid}/payments", json={
                "amount": due, "paymentMode": "Cash", "date": "2026-08-10"})
            assert r.status_code == 200, r.text
    return lid


@pytest.mark.asyncio
async def test_owner_deletes_receipt_and_recomputes(client):
    lid = await _booked_lead(client, "9800000001")
    before = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(before.get("customerOutstanding")) == 0
    received = ce.num(before.get("totalReceived"))

    extra = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 2500, "paymentMode": "UPI", "date": "2026-08-11", "allowExcess": True,
        "narration": "wrong extra"})
    assert extra.status_code == 200, extra.text
    rec = extra.json()["receiptNumber"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 2500

    gone = await client.delete(f"/api/payments/{rec}")
    assert gone.status_code == 200, gone.text
    body = gone.json()
    assert body["ok"] is True and body["deleted"] == rec
    assert await server.db.payments.find_one({"receiptNumber": rec}) is None

    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["totalReceived"]) == received
    assert ce.num(lead["excessReceived"]) == 0
    assert ce.num(lead["customerOutstanding"]) == 0

    ledger = (await client.get("/api/payments", params={"lead_id": lid})).json()
    assert all(p["receiptNumber"] != rec for p in ledger)


@pytest.mark.asyncio
async def test_delete_rebuilds_running_totals_on_remaining(client):
    lid = await _booked_lead(client, "9800000002", pay_full=False)
    first = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 2000, "paymentMode": "Cash", "date": "2026-08-10", "narration": "first"})
    second = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 3000, "paymentMode": "Cash", "date": "2026-08-11", "narration": "second"})
    assert first.status_code == 200 and second.status_code == 200
    rec1 = first.json()["receiptNumber"]

    r = await client.delete(f"/api/payments/{rec1}")
    assert r.status_code == 200, r.text

    remaining = [p for p in (await client.get("/api/payments", params={"lead_id": lid})).json()
                 if p.get("narration") == "second"]
    assert len(remaining) == 1
    # Booking advance 1000 + 3000 remaining = 4000 running on the later receipt.
    assert remaining[0]["runningTotal"] == 4000


@pytest.mark.asyncio
async def test_executive_and_accounts_cannot_delete(client):
    lid = await _booked_lead(client, "9800000003", pay_full=False)
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1500, "paymentMode": "Cash", "date": "2026-08-10"})
    rec = pay.json()["receiptNumber"]

    exec_tok = await _login(client, EXEC_EMAIL, EXEC_PASSWORD)
    r = await client.delete(f"/api/payments/{rec}", headers={"Authorization": f"Bearer {exec_tok}"})
    assert r.status_code == 403, r.text

    acct_tok = await _login(client, ACCT_EMAIL, ACCT_PASSWORD)
    r = await client.delete(f"/api/payments/{rec}", headers={"Authorization": f"Bearer {acct_tok}"})
    assert r.status_code == 403, r.text

    assert await server.db.payments.find_one({"receiptNumber": rec})


@pytest.mark.asyncio
async def test_unknown_receipt_is_404(client):
    r = await client.delete("/api/payments/RC26NOPE00")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_finance_receipt_delete_rebuilds_file(client):
    lid = await _booked_lead(client, "9800000004", pay_full=False)
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 5000, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    rec = pay.json()["receiptNumber"]
    fn = pay.json()["financeFileNumber"]
    assert fn
    fin = await server.db.finance.find_one({"fileNumber": fn})
    assert ce.num(fin.get("sanctionedAmount")) == 5000

    r = await client.delete(f"/api/payments/{rec}")
    assert r.status_code == 200, r.text
    assert await server.db.payments.find_one({"receiptNumber": rec}) is None
    assert await server.db.finance.find_one({"fileNumber": fn}) is None


@pytest.mark.asyncio
async def test_cannot_delete_finance_receipt_after_disbursement(client):
    lid = await _booked_lead(client, "9800000005", pay_full=False)
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 4000, "paymentMode": "Finance", "financerName": "HDFC BANK",
        "date": "2026-08-10"})
    assert pay.status_code == 200, pay.text
    rec = pay.json()["receiptNumber"]
    fn = pay.json()["financeFileNumber"]

    recvd = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": 4000, "date": "2026-08-12", "reference": "NEFT-1"})
    assert recvd.status_code == 200, recvd.text

    blocked = await client.delete(f"/api/payments/{rec}")
    assert blocked.status_code == 422, blocked.text
    assert "disbursed" in blocked.text.lower() or "financer" in blocked.text.lower()
    assert await server.db.payments.find_one({"receiptNumber": rec})


@pytest.mark.asyncio
async def test_owner_can_delete_a_refund_row(client):
    lid = await _booked_lead(client, "9800000006")
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 4000, "paymentMode": "Cash", "date": "2026-08-10", "allowExcess": True})
    rf = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 1500, "paymentMode": "NEFT", "date": "2026-08-12"})
    assert rf.status_code == 200, rf.text
    rec = rf.json()["refund"]["receiptNumber"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 2500

    r = await client.delete(f"/api/payments/{rec}")
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 4000
    assert ce.num(lead.get("refundedAmount") or 0) == 0
