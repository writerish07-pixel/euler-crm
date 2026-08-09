"""Finance P0 contract, end to end against the real route handlers.

The scenario that must work without staff inventing anything:

    lead booked with Finance = No
    -> later payment: mode Finance, financer chosen, file number BLANK
    -> system generates FN26xxxxxx and wires it through every register.

Runs in-process against mongomock. Sheets sync is disabled here, so these assert the
Mongo + API side; the Sheet mapping for the same fields is asserted separately in
test_iter20_column_contract.py against the live workbook headers.
"""
import asyncio
import os
import re
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter21finance")
os.environ.setdefault("JWT_SECRET", "iter21-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Hi-Load", "XR"
FN26 = re.compile(r"^FN26\d{6}$")


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def lead_booked_without_finance(c, mobile):
    """Step A of the contract: booking created with Finance = NO."""
    r = await c.post("/api/leads", json={
        "customerName": "ITER21 FINANCE QA", "mobile": mobile,
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    await c.put(f"/api/leads/{lid}/price-structure",
                json={"exShowroom": 300000, "rto": 20000, "insuranceAmount": 15000})
    r = await c.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-08", "bookingAmount": 0, "financeRequired": "No"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead.get("financeRequired") != "Yes"
    return lid


# ------------------------------------------------------- B: finance added later
@pytest.mark.asyncio
async def test_finance_payment_with_blank_file_number_wires_everything(client):
    """THE P0 scenario. Staff pick mode + financer and type no file number."""
    lid = await lead_booked_without_finance(client, "9555500001")

    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 200000, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    assert r.status_code == 200, r.text
    payment = r.json()

    # 2 + 3: generated in contract format and saved onto the payment
    fn = payment["financeFileNumber"]
    assert FN26.match(fn), f"generated file number {fn!r} breaks the FN26 contract"

    # 9: Payment Ledger row carries it
    pay_doc = await server.db.payments.find_one({"receiptNumber": payment["receiptNumber"]})
    assert pay_doc["financeFileNumber"] == fn
    assert pay_doc["financerName"] == "SHRIRAM"

    # 4 + 5 + 6: Finance Register created, with financer and file number
    fin = await server.db.finance.find_one({"fileNumber": fn})
    assert fin is not None, "Finance Register row was not created"
    assert fin["leadId"] == lid
    assert fin["financer"] == "SHRIRAM"
    assert fin["sanctionedAmount"] == 200000

    # 1 + 7 + 8: Lead Register mirror
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["financeRequired"] == "Yes"
    assert lead["financerName"] == "SHRIRAM"
    assert lead["financeFileNumber"] == fn

    # 10 + 11 + 12: derived views recalculated from the register
    views = await server.rebuild_finance_views()
    assert views["pending"] >= 1
    assert fin["fileOutstanding"] == 200000


# ------------------------------------------------------- C: subsequent payments
@pytest.mark.asyncio
async def test_second_finance_payment_reuses_the_same_file(client):
    lid = await lead_booked_without_finance(client, "9555500002")
    r1 = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 100000, "paymentMode": "Finance", "financerName": "SUNDARAM"})
    fn = r1.json()["financeFileNumber"]

    r2 = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 50000, "paymentMode": "Finance", "financerName": "SUNDARAM"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["financeFileNumber"] == fn, "second payment created a different file"

    files = await server.db.finance.find({"leadId": lid}).to_list(10)
    assert len(files) == 1, f"duplicate Finance Register rows: {[f['fileNumber'] for f in files]}"
    assert files[0]["sanctionedAmount"] == 150000
    assert files[0]["fileOutstanding"] == 150000


# ------------------------------------------------------- D + E: supplied numbers
def test_legacy_file_number_classification():
    """Pure classification — historical numbers are recognised, contract ones are not."""
    assert server.is_legacy_finance_file_number("55") is True
    assert server.is_legacy_finance_file_number("LEGACY-2025-07") is True
    assert server.is_legacy_finance_file_number("FN26000101") is False
    assert server.is_legacy_finance_file_number("") is False


@pytest.mark.asyncio
async def test_an_existing_legacy_file_is_still_usable(client):
    """Historical files like the live '55' must keep working — renumbering them would
    orphan every payment and sheet row that references them. Uses its own number so
    it cannot collide with the rejection test below."""
    lid = await lead_booked_without_finance(client, "9555500012")
    await server.db.finance.insert_one({
        "fileNumber": "LEGACY-77", "leadId": lid, "customerName": "Legacy",
        "financer": "SUNDARAM", "sanctionedAmount": 0.0, "receivedAgainstFile": 0.0,
        "fileOutstanding": 0.0, "status": "Pending", "receipts": []})
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 5000, "paymentMode": "Finance", "financerName": "SUNDARAM",
        "financeFileNumber": "LEGACY-77"})
    assert r.status_code == 200, r.text
    assert r.json()["financeFileNumber"] == "LEGACY-77"
    assert await server.db.finance.count_documents({"leadId": lid}) == 1


@pytest.mark.asyncio
async def test_new_file_with_a_non_contract_number_is_rejected(client):
    """A hand-typed '55' on a NEW file is refused — this is how it reached production."""
    lid = await lead_booked_without_finance(client, "9555500003")
    for bad in ("55", "123", "ABC", "FN2612", "fn26000101"):
        r = await client.post(f"/api/leads/{lid}/payments", json={
            "amount": 1000, "paymentMode": "Finance", "financerName": "SHRIRAM",
            "financeFileNumber": bad})
        assert r.status_code == 422, f"{bad!r} was accepted: {r.text}"
        assert "not a valid Finance File Number" in r.text
    assert await server.db.finance.count_documents({"leadId": lid}) == 0


@pytest.mark.asyncio
async def test_file_number_belonging_to_another_lead_is_rejected(client):
    lid_a = await lead_booked_without_finance(client, "9555500004")
    r = await client.post(f"/api/leads/{lid_a}/payments", json={
        "amount": 10000, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    fn_a = r.json()["financeFileNumber"]

    lid_b = await lead_booked_without_finance(client, "9555500005")
    r = await client.post(f"/api/leads/{lid_b}/payments", json={
        "amount": 10000, "paymentMode": "Finance", "financerName": "SHRIRAM",
        "financeFileNumber": fn_a})
    assert r.status_code == 422
    assert "another lead" in r.text


@pytest.mark.asyncio
async def test_a_lead_cannot_get_a_second_conflicting_file(client):
    lid = await lead_booked_without_finance(client, "9555500006")
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 10000, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 5000, "paymentMode": "Finance", "financerName": "SHRIRAM",
        "financeFileNumber": "FN26999999"})
    assert r.status_code == 422
    assert "different finance file number" in r.text


# ------------------------------------------------------------ F + G: idempotency
@pytest.mark.asyncio
async def test_duplicate_retry_creates_no_second_payment_or_file(client):
    lid = await lead_booked_without_finance(client, "9555500007")
    body = {"amount": 75000, "paymentMode": "Finance", "financerName": "SHRIRAM"}
    r1 = await client.post(f"/api/leads/{lid}/payments", json=body)
    assert r1.status_code == 200
    r2 = await client.post(f"/api/leads/{lid}/payments", json=body)
    assert r2.status_code == 409, "identical immediate resubmit must be refused"

    assert await server.db.payments.count_documents({"leadId": lid}) == 1
    assert await server.db.finance.count_documents({"leadId": lid}) == 1


@pytest.mark.asyncio
async def test_concurrent_first_finance_payments_yield_exactly_one_file(client):
    """Two first-time Finance payments racing must not create two Finance Registers."""
    lid = await lead_booked_without_finance(client, "9555500008")
    results = await asyncio.gather(*[
        client.post(f"/api/leads/{lid}/payments", json={
            "amount": 10000 + i, "paymentMode": "Finance", "financerName": "SHRIRAM"})
        for i in range(4)
    ], return_exceptions=True)
    ok = [r for r in results if not isinstance(r, Exception) and r.status_code == 200]
    assert ok, f"no payment succeeded: {[getattr(r, 'text', r) for r in results]}"

    files = await server.db.finance.find({"leadId": lid}).to_list(10)
    assert len(files) == 1, f"race created {len(files)} finance files: {[f['fileNumber'] for f in files]}"
    assert FN26.match(files[0]["fileNumber"])
    numbers = {r.json()["financeFileNumber"] for r in ok}
    assert numbers == {files[0]["fileNumber"]}, f"payments disagree on the file number: {numbers}"


# --------------------------------------------- I: payment vs financer disbursement
@pytest.mark.asyncio
async def test_customer_finance_payment_and_financer_disbursement_stay_separate(client):
    """A Finance payment is the financer's COMMITMENT (customer outstanding drops).
    A receipt against the file is the actual DISBURSEMENT (customer untouched)."""
    lid = await lead_booked_without_finance(client, "9555500009")
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 200000, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    fn = r.json()["financeFileNumber"]
    lead_after_payment = await server.db.leads.find_one({"leadId": lid})
    outstanding_before = lead_after_payment["customerOutstanding"]

    rr = await client.post(f"/api/finance/{fn}/receipt", json={"amount": 80000, "date": "2026-08-09"})
    assert rr.status_code == 200, rr.text
    assert rr.json()["receivedAgainstFile"] == 80000
    assert rr.json()["fileOutstanding"] == 120000

    lead_after_receipt = await server.db.leads.find_one({"leadId": lid})
    assert lead_after_receipt["customerOutstanding"] == outstanding_before, \
        "financer disbursement must NOT change what the customer owes"


@pytest.mark.asyncio
async def test_finance_views_reconcile_with_the_register(client):
    """Finance Pending / Overdue are projections — they must agree with the register."""
    lid = await lead_booked_without_finance(client, "9555500010")
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 120000, "paymentMode": "Finance", "financerName": "SUNDARAM"})
    fn = r.json()["financeFileNumber"]

    views = await server.rebuild_finance_views()
    open_files = [f for f in await server.db.finance.find().to_list(100)
                  if f.get("fileOutstanding", 0) > 0 and f.get("status") != "Received"]
    assert views["pending"] == len(open_files)

    # Fully disburse -> the file must leave Pending.
    await client.post(f"/api/finance/{fn}/receipt", json={"amount": 120000, "date": "2026-08-09"})
    fin = await server.db.finance.find_one({"fileNumber": fn})
    assert fin["status"] == "Received"
    assert fin["fileOutstanding"] == 0
    views2 = await server.rebuild_finance_views()
    assert views2["pending"] == views["pending"] - 1


@pytest.mark.asyncio
async def test_rebuild_finance_views_is_idempotent(client):
    lid = await lead_booked_without_finance(client, "9555500011")
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": 60000, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    a = await server.rebuild_finance_views()
    b = await server.rebuild_finance_views()
    assert a["pending"] == b["pending"] and a["overdue"] == b["overdue"]
