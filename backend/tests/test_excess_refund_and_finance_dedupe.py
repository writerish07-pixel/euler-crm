"""Excess payment + refund, and the double-posted financer receipt.

Excess: collecting more than Customer Payable is a real situation and must be
recordable (deliberately, not by accident), then refundable — including after
delivery and after the lead is closed, because the surplus is the customer's money.

Finance: a double-clicked financer receipt pushed two identical entries into the
file and doubled receivedAgainstFile, while the Finance tab still showed one row
(that sheet sync upserts on file number) — so the app looked wrong, the sheet right.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "excess_refund")
os.environ.setdefault("JWT_SECRET", "excess-refund-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

OWNER_EMAIL = "refund-owner@euler.com"
OWNER_PASSWORD = "refund-owner-pass"
# The database the auth router captured at import time — users must be written here.
# Not client[DB_NAME]: another test module reassigns DB_NAME, so that lookup can point
# at a different database than the one auth actually reads. Captured at import, before
# any fixture repoints server.db.
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Own mongomock database — every test module shares one `server` import (and one
    DB_NAME), so leads/payments created here would otherwise collide with theirs.
    Auth keeps using the original database because the auth router captured it at
    import time."""
    isolated = server.client["excess_refund_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    # Own owner account: the shared owner@euler.com password is rotated by the
    # change-password tests and seed_users never resets an existing owner.
    await AUTH_DB.users.update_one(
        {"email": OWNER_EMAIL},
        {"$set": {"email": OWNER_EMAIL, "name": "Refund Owner", "role": "owner",
                  "userId": "refund-owner", "passwordHash": server.authmod.hash_password(OWNER_PASSWORD)}},
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


async def _booked_lead(client, mobile, *, pay_full=True):
    r = await client.post("/api/leads", json={
        "customerName": f"Refund Case {mobile[-4:]}", "mobile": mobile,
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


async def _deliver(client, lid):
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "rc": "Yes", "pdi": "Yes",
        "delivered": "Yes", "deliveryDate": "2026-08-11",
        "invoiceNumber": f"INV-{lid}", "chassisNumber": f"CH-{lid}",
        "numberPlate": f"RJ14-{lid[-4:]}", "insurerName": "TestIns"})
    assert r.status_code == 200, r.text


# ------------------------------------------------------------------ excess
@pytest.mark.asyncio
async def test_excess_needs_confirmation_then_records(client):
    lid = await _booked_lead(client, "9700000001")

    over = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 5000, "paymentMode": "Cash", "date": "2026-08-10"})
    assert over.status_code == 422, over.text
    assert "excess payment" in over.json()["detail"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("excessReceived")) == 0

    ok = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 5000, "paymentMode": "Cash", "date": "2026-08-10", "allowExcess": True})
    assert ok.status_code == 200, ok.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 5000
    # A surplus must never read as money still owed.
    assert ce.num(lead["customerOutstanding"]) == 0


@pytest.mark.asyncio
async def test_excess_does_not_block_delivery_but_short_payment_does(client):
    short = await _booked_lead(client, "9700000002", pay_full=False)
    r = await client.put(f"/api/leads/{short}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "rc": "Yes", "pdi": "Yes",
        "delivered": "Yes", "deliveryDate": "2026-08-11", "invoiceNumber": "INV-SHORT",
        "chassisNumber": "CH-SHORT", "numberPlate": "RJ14-SHRT", "insurerName": "TestIns"})
    assert r.status_code == 422
    assert "outstanding must be cleared" in r.text

    paid = await _booked_lead(client, "9700000003")
    await client.post(f"/api/leads/{paid}/payments", json={
        "amount": 2500, "paymentMode": "UPI", "date": "2026-08-10", "allowExcess": True})
    await _deliver(client, paid)
    lead = await server.db.leads.find_one({"leadId": paid})
    assert lead["deliveryStatus"] == "Delivered"
    assert ce.num(lead["excessReceived"]) == 2500


# ------------------------------------------------------------------ refund
@pytest.mark.asyncio
async def test_refund_reduces_excess_and_shows_in_the_ledger(client):
    lid = await _booked_lead(client, "9700000004")
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 8000, "paymentMode": "Cash", "date": "2026-08-10", "allowExcess": True})

    pos = (await client.get(f"/api/leads/{lid}/refund-position")).json()
    assert pos["excessReceived"] == 8000 and pos["refundedAmount"] == 0

    r = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 3000, "paymentMode": "NEFT", "date": "2026-08-12", "reference": "UTR-1"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["excessReceived"] == 5000 and body["refundedAmount"] == 3000

    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 5000
    assert ce.num(lead["refundedAmount"]) == 3000
    assert ce.num(lead["customerOutstanding"]) == 0

    ledger = (await client.get("/api/payments", params={"lead_id": lid})).json()
    refunds = [p for p in ledger if p.get("entryType") == "Refund"]
    assert len(refunds) == 1
    assert refunds[0]["amount"] == -3000
    assert refunds[0]["receiptNumber"].startswith("RF26")
    assert "UTR-1" in refunds[0]["narration"]


@pytest.mark.asyncio
async def test_refund_cannot_exceed_excess_or_run_without_one(client):
    lid = await _booked_lead(client, "9700000005")
    none = await client.post(f"/api/leads/{lid}/refund", json={"amount": 100})
    assert none.status_code == 422 and "no excess payment" in none.json()["detail"]

    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 4000, "paymentMode": "Cash", "date": "2026-08-10", "allowExcess": True})
    too_much = await client.post(f"/api/leads/{lid}/refund", json={"amount": 4500})
    assert too_much.status_code == 422 and "more than the excess" in too_much.json()["detail"]
    assert (await client.post(f"/api/leads/{lid}/refund", json={"amount": 0})).status_code == 422

    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["excessReceived"]) == 4000
    assert ce.num(lead.get("refundedAmount")) == 0


@pytest.mark.asyncio
async def test_refund_allowed_after_delivery_and_after_close(client):
    lid = await _booked_lead(client, "9700000006")
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 6000, "paymentMode": "Cash", "date": "2026-08-10", "allowExcess": True})
    await _deliver(client, lid)

    after_delivery = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 1000, "paymentMode": "Cash", "date": "2026-08-12"})
    assert after_delivery.status_code == 200, after_delivery.text
    assert after_delivery.json()["excessReceived"] == 5000

    r = await client.post(f"/api/leads/{lid}/close", json={"closeReason": "Delivered and settled"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["accountStatus"] == "Closed"
    # A normal receipt is refused on a closed lead...
    blocked = await client.post(f"/api/leads/{lid}/payments", json={"amount": 10, "paymentMode": "Cash"})
    assert blocked.status_code == 409
    # ...but returning the customer's own surplus is not.
    after_close = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 5000, "paymentMode": "NEFT", "date": "2026-08-20"})
    assert after_close.status_code == 200, after_close.text
    assert after_close.json()["excessReceived"] == 0
    assert after_close.json()["refundedAmount"] == 6000


# ------------------------------------------------------------------ finance dedupe
async def _finance_file(client, mobile):
    lid = await _booked_lead(client, mobile, pay_full=False)
    lead = await server.db.leads.find_one({"leadId": lid})
    due = ce.num(lead.get("customerOutstanding"))
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": due, "paymentMode": "Finance", "financerName": "HDFC BANK", "date": "2026-08-10"})
    assert r.status_code == 200, r.text
    return lid, r.json()["financeFileNumber"], due


@pytest.mark.asyncio
async def test_double_clicked_financer_receipt_is_rejected(client):
    _lid, fn, committed = await _finance_file(client, "9700000007")
    first = await client.post(f"/api/finance/{fn}/receipt", json={"amount": 50000, "date": "2026-08-12"})
    assert first.status_code == 200, first.text

    again = await client.post(f"/api/finance/{fn}/receipt", json={"amount": 50000, "date": "2026-08-12"})
    assert again.status_code == 409, again.text
    assert "Duplicate submission" in again.json()["detail"]

    f = await server.db.finance.find_one({"fileNumber": fn})
    assert len(f["receipts"]) == 1
    assert ce.num(f["receivedAgainstFile"]) == 50000
    assert ce.num(f["fileOutstanding"]) == ce.round2(committed - 50000)


@pytest.mark.asyncio
async def test_receipt_cannot_exceed_the_committed_amount(client):
    _lid, fn, committed = await _finance_file(client, "9700000008")
    over = await client.post(f"/api/finance/{fn}/receipt", json={
        "amount": ce.round2(committed + 1000), "date": "2026-08-12"})
    assert over.status_code == 422, over.text
    assert "more than this file still expects" in over.json()["detail"]

    f = await server.db.finance.find_one({"fileNumber": fn})
    assert ce.num(f["receivedAgainstFile"]) == 0
    assert ce.num(f["fileOutstanding"]) == committed

    exact = await client.post(f"/api/finance/{fn}/receipt", json={"amount": committed, "date": "2026-08-12"})
    assert exact.status_code == 200, exact.text
    assert exact.json()["status"] == "Received"
    assert ce.num(exact.json()["fileOutstanding"]) == 0


@pytest.mark.asyncio
async def test_repair_heals_a_file_that_already_recorded_a_receipt_twice(client):
    """The FN26000101 case: two identical entries, receivedAgainstFile doubled."""
    _lid, fn, committed = await _finance_file(client, "9700000009")
    half = ce.round2(committed / 2)
    await server.db.finance.update_one({"fileNumber": fn}, {"$set": {
        "receipts": [
            {"amount": half, "date": "2026-08-12", "reference": "UTR-9", "recordedAt": "2026-08-12T10:00:00+00:00"},
            {"amount": half, "date": "2026-08-12", "reference": "UTR-9", "recordedAt": "2026-08-12T10:00:01+00:00"},
        ],
        "receivedAgainstFile": ce.round2(half * 2), "fileOutstanding": 0.0, "status": "Received",
    }})

    r = await client.post("/api/finance/repair-duplicate-receipts")
    assert r.status_code == 200, r.text
    assert r.json()["filesRepaired"] == 1

    f = await server.db.finance.find_one({"fileNumber": fn})
    assert len(f["receipts"]) == 1
    assert ce.num(f["receivedAgainstFile"]) == half
    assert ce.num(f["fileOutstanding"]) == ce.round2(committed - half)
    assert f["status"] == "Partial"

    # Idempotent: a second run finds nothing left to fix.
    assert (await client.post("/api/finance/repair-duplicate-receipts")).json()["filesRepaired"] == 0


@pytest.mark.asyncio
async def test_repair_keeps_two_genuine_tranches(client):
    """Same amount, different reference/day is two real disbursements — never merged."""
    _lid, fn, committed = await _finance_file(client, "9700000010")
    part = ce.round2(committed / 4)
    await server.db.finance.update_one({"fileNumber": fn}, {"$set": {
        "receipts": [
            {"amount": part, "date": "2026-08-12", "reference": "UTR-A", "recordedAt": "2026-08-12T10:00:00+00:00"},
            {"amount": part, "date": "2026-08-13", "reference": "UTR-B", "recordedAt": "2026-08-13T10:00:00+00:00"},
        ],
        "receivedAgainstFile": ce.round2(part * 2),
    }})
    r = await client.post("/api/finance/repair-duplicate-receipts")
    assert r.json()["filesRepaired"] == 0
    f = await server.db.finance.find_one({"fileNumber": fn})
    assert len(f["receipts"]) == 2
