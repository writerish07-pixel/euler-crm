"""One complete dealership lifecycle, asserted at every step.

LEAD -> BOOKING -> PRICE -> SCHEME -> PAYMENT -> FINANCE -> DELIVERY -> CLAIM
-> DEALER EARNINGS -> CLOSE

This is the go-live rehearsal, run in-process against mongomock so it never touches
the production workbook. It asserts the separation the business depends on:

  Customer Payable / Customer Outstanding  (what the customer owes)
  Company Outstanding                      (what the OEM owes the dealer)
  Finance Outstanding                      (what the financer owes the dealer)
  Dealer Earnings                          (dealer margin + retained income)

are four independent quantities, and dealer earnings never move customer outstanding.
"""
import os
import re
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter21golive")
os.environ.setdefault("JWT_SECRET", "iter21-golive-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

# The HiCity row in Price Master: model "Hi-Load", variant "XR", ex-showroom 435000.
MODEL, VARIANT = "Hi-Load", "XR"
QA_NAME = "ZZ QA GOLIVE LIFECYCLE"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest.mark.asyncio
async def test_complete_golive_lifecycle(client):
    steps = []

    # ---------------------------------------------------------------- 1. LEAD
    r = await client.post("/api/leads", json={
        "customerName": QA_NAME, "mobile": "9666600099", "interestedModel": MODEL,
        "variant": VARIANT, "executive": "Amit", "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    assert lid.startswith("LD26")
    steps.append(("lead", lid))

    # ------------------------------------------------------ 2. PRICE (Price Master)
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.status_code == 200
    assert pv.json()["found"] is True, "Price Master lookup failed for the HiCity row"
    ex_showroom = pv.json()["priceStructure"]["exShowroom"]
    assert ex_showroom == 435000, f"Price Master ex-showroom drifted: {ex_showroom}"

    r = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": ex_showroom, "rto": 10000, "insuranceAmount": 10000})
    assert r.status_code == 200, r.text
    lead = r.json()
    gvc = lead["grossVehicleCost"]
    assert gvc == 455000, f"GVC should be 435000+10000+10000, got {gvc}"

    # ------------------------------------------------------------- 3. BOOKING
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-08", "bookingAmount": 5000,
        "paymentMode": "Cash", "financeRequired": "No", "exchangeRequired": "No"})
    assert r.status_code == 200, r.text
    booking_id = r.json()["bookingId"]
    assert booking_id.startswith("BK26")

    # -------------------------------------------------------------- 4. SCHEME
    # HiCity Aug'26 per circular EM/08-2026/001: consumer 25,000 + loyalty 10,000
    # company-funded, plus auto RTO + Insurance entitlements = 55,000 company total.
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "consumerDiscount": 25000, "loyaltyBonus": 10000, "benefitMode": "Full Benefit"})
    assert r.status_code == 200, r.text
    lead = r.json()
    assert lead["companyOutstanding"] == 55000, \
        f"August HiCity company share must be 55000, got {lead['companyOutstanding']}"

    payable_after_scheme = lead["customerPayable"]
    received_so_far = lead["totalReceived"]

    # ------------------------------------------------------------- 5. PAYMENT
    cash = 100000
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": cash, "paymentMode": "Cash", "narration": "Part payment"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["totalReceived"] == received_so_far + cash
    assert lead["customerOutstanding"] == ce.round2(payable_after_scheme - lead["totalReceived"])

    # ------------------------------------------------------------- 6. FINANCE
    # Finance was NOT selected at booking. Staff type no file number.
    outstanding_before_finance = lead["customerOutstanding"]
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": outstanding_before_finance, "paymentMode": "Finance",
        "financerName": "SHRIRAM"})
    assert r.status_code == 200, r.text
    fn = r.json()["financeFileNumber"]
    assert re.match(r"^FN26\d{6}$", fn), f"file number breaks the contract: {fn}"

    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["financeRequired"] == "Yes"
    assert lead["financerName"] == "SHRIRAM"
    assert lead["financeFileNumber"] == fn
    assert lead["customerOutstanding"] == 0, "customer should be fully covered"

    fin = await server.db.finance.find_one({"fileNumber": fn})
    assert fin["financer"] == "SHRIRAM"
    assert fin["sanctionedAmount"] == outstanding_before_finance
    assert fin["fileOutstanding"] == outstanding_before_finance
    assert fin["status"] == "Pending"

    views = await server.rebuild_finance_views()
    assert views["pending"] >= 1

    # ------------------------------------------------------------ 7. DELIVERY
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ABC Insurers", "invoiceNumber": "INV-GOLIVE-1",
        "chassisNumber": "CH-GOLIVE-1", "numberPlate": "RJ14-GL-0001", "delivered": "Yes"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["currentStatus"] == "Delivered"
    for f in ("insuranceStatus", "registrationStatus", "invoiceStatus", "rcStatus", "pdiStatus"):
        assert lead.get(f), f"{f} not set at delivery"

    # --------------------------------------------------------------- 8. CLAIM
    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert claims, "no claims generated for a delivered scheme lead"
    eligible = ce.round2(sum(ce.num(c["eligibleClaim"]) for c in claims))
    assert eligible == 55000, f"claimable total must equal company share 55000, got {eligible}"
    assert lead["companyOutstanding"] == eligible, \
        "Company Outstanding must equal the claimable OEM total"
    keys = sorted(c["componentKey"] for c in claims)
    assert "rtoInsuranceBenefit" not in keys, "July-only component leaked into an August lead"

    # ------------------------------------------------- 9. DEALER EARNINGS (P0)
    de = lead["dealerTotalEarnings"]
    assert de == ce.round2(
        lead["dealerMarginNetExGst"] + lead["dealerSchemeRetained"]
        + lead["oemExtraSupportRetained"] + lead["extraDealerIncomeTotal"]), \
        "dealer total earnings must be the sum of its components"
    # Independence: dealer earnings are not the customer's money.
    assert de != lead["customerPayable"]
    assert lead["customerOutstanding"] == 0
    # schemeRetainedBreakup spans EVERY component, including entitlements which have
    # no dedicated column; the five offer columns are a subset of it.
    breakup = {}
    for part in str(lead.get("schemeRetainedBreakup") or "").split(";"):
        if "=" in part:
            k, v = part.split("=", 1)
            breakup[k.strip()] = float(v)
    assert ce.round2(sum(breakup.values())) == ce.round2(lead["dealerSchemeRetained"])

    # Recording a financer disbursement must not touch the customer.
    r = await client.post(f"/api/finance/{fn}/receipt",
                          json={"amount": 50000, "date": "2026-08-09"})
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerOutstanding"] == 0
    assert after["customerPayable"] == lead["customerPayable"]
    assert after["dealerTotalEarnings"] == de, "a financer receipt must not move dealer earnings"

    # --------------------------------------------------------------- 10. CLOSE
    r = await client.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Delivered and settled", "rc": "Yes", "numberPlate": "RJ14-GL-0001"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["accountStatus"] == "Closed"
    assert lead["closedDate"] and lead["closeTimestamp"]
    assert lead["closedBy"] == "owner@euler.com"
    assert lead["closeReason"] == "Delivered and settled"

    # ------------------------------------------------- 11. REGISTERS RECONCILE
    assert await server.db.bookings.count_documents({"leadId": lid}) == 1
    assert await server.db.finance.count_documents({"leadId": lid}) == 1
    assert await server.db.deliveries.count_documents({"leadId": lid}) == 1
    payments = await server.db.payments.find({"leadId": lid}).to_list(50)
    assert ce.round2(sum(ce.num(p["amount"]) for p in payments)) == lead["totalReceived"]

    # ------------------------------------------------------ 12. QA CLEANUP ONLY
    r = await client.delete(f"/api/leads/{lid}")
    assert r.status_code == 200, r.text
    assert (await client.get(f"/api/leads/{lid}")).status_code == 404
    assert await server.db.leads.count_documents({"customerName": QA_NAME}) == 0


@pytest.mark.asyncio
async def test_dealer_earnings_never_move_customer_outstanding(client):
    """Explicit guard: editing dealer income lines must not change what the customer owes."""
    r = await client.post("/api/leads", json={
        "customerName": "ZZ QA DE ISOLATION", "mobile": "9666600098",
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    await client.put(f"/api/leads/{lid}/price-structure",
                     json={"exShowroom": 435000, "rto": 10000, "insuranceAmount": 10000})
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-08", "bookingAmount": 0})
    before = await server.db.leads.find_one({"leadId": lid})

    r = await client.put(f"/api/leads/{lid}/extra-income", json={
        "financeIncentive": 5000, "accessoriesMargin": 3000, "documentationIncome": 1500,
        "warrantyIncome": 1000, "rsaIncome": 500, "referralIncome": 750,
        "campaignIncentive": 2000, "otherIncome": 250})
    assert r.status_code == 200, r.text

    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before["customerPayable"], "dealer income changed customer payable"
    assert after["customerOutstanding"] == before["customerOutstanding"], \
        "dealer income changed customer outstanding"
    assert after["dealerTotalEarnings"] > before["dealerTotalEarnings"]
    assert after["extraDealerIncomeTotal"] == 14000

    await client.delete(f"/api/leads/{lid}")
