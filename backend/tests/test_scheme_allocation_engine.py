"""Authoritative scheme allocation engine — permanent contract test matrix.

Circular EM/08-2026/001 · Turbo Aug'26 Scheme Master values.

Formulas (every component, no special-case for Insurance):
  customerBenefit ∈ [0, schemeAvailable]
  dealerRetained  = schemeAvailable − customerBenefit
  oemClaimable    = OEM/company share (Scheme Master)
  Customer Payable reduction = Σ customerBenefit
  Dealer Scheme Retained     = Σ dealerRetained
  OEM Claim                  = Σ oemClaimable

Benefit Mode applies identically to Loyalty, Insurance, RTO, and every other component.
Insurance Payout (premium × rate) is a SEPARATE ledger from Insurance Scheme Benefit.
"""
import json
import os
import re
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scheme_alloc_engine_v2")
os.environ.setdefault("JWT_SECRET", "scheme-alloc-v2-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

TURBO_SCHEME = [
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
     "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
     "dealerShare": 0, "companyShare": 10000, "totalBenefit": 10000, "status": "Active"},
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
     "model": "Turbo", "variant": "", "componentKey": "insuranceBenefit",
     "component": "Insurance Benefit", "dealerShare": 10000, "companyShare": 10000,
     "totalBenefit": 20000, "status": "Active"},
]

MODEL, VARIANT = "Turbo Max", "Maxx (PV)"
BASE = {
    "model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
    "loyaltyBonus": 10000, "exShowroom": 770000, "insurance": 22000,
    "schemeAllocationV2": True,
}


def _by(alloc):
    return {c["key"]: c for c in alloc["components"]}


def _assert_invariants(alloc):
    for c in alloc["components"]:
        assert c["customerBenefit"] >= 0
        assert c["dealerRetained"] >= 0
        assert c["customerBenefit"] <= c["schemeAvailable"] + 0.01
        assert abs(c["schemeAvailable"] - (c["customerBenefit"] + c["dealerRetained"])) < 0.01
        assert c["oemClaimable"] <= c["schemeAvailable"] + 0.01
        assert c["oemClaimable"] == c["oemShare"]
    t = alloc["totals"]
    assert abs(t["customerBenefit"] - sum(c["customerBenefit"] for c in alloc["components"])) < 0.01
    assert abs(t["dealerRetained"] - sum(c["dealerRetained"] for c in alloc["components"])) < 0.01
    assert abs(t["oemClaimable"] - sum(c["oemClaimable"] for c in alloc["components"])) < 0.01


# ============================================================ unit matrix
def test_A_no_benefit():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    _assert_invariants(alloc)
    assert alloc["totals"] == {
        "schemeAvailable": 30000.0, "customerBenefit": 0.0, "dealerRetained": 30000.0,
        "oemClaimable": 20000.0, "dealerFundedShare": 10000.0, "oemShare": 20000.0,
    }


def test_B_loyalty_full_insurance_zero_via_breakup():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 10000, "insuranceBenefit": 0}}
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    _assert_invariants(alloc)
    assert alloc["totals"]["customerBenefit"] == 10000
    assert alloc["totals"]["dealerRetained"] == 20000
    assert alloc["totals"]["oemClaimable"] == 20000


def test_C_insurance_partial_5k():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    _assert_invariants(alloc)
    assert alloc["totals"]["customerBenefit"] == 5000
    assert alloc["totals"]["dealerRetained"] == 25000
    assert alloc["totals"]["oemClaimable"] == 20000
    assert _by(alloc)["insuranceBenefit"]["dealerRetained"] == 15000


def test_D_both_full_via_benefit_mode_full_benefit():
    """MUST pass through Benefit Mode = Full Benefit (not only a manual breakup)."""
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "Full Benefit"}, TURBO_SCHEME)
    _assert_invariants(alloc)
    by = _by(alloc)
    assert by["loyaltyBonus"]["customerBenefit"] == 10000
    assert by["insuranceBenefit"]["customerBenefit"] == 20000  # Full Benefit applies to Insurance
    assert alloc["totals"]["customerBenefit"] == 30000
    assert alloc["totals"]["dealerRetained"] == 0
    assert alloc["totals"]["oemClaimable"] == 20000


def test_full_benefit_identical_for_loyalty_and_insurance():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "Full Benefit"}, TURBO_SCHEME)
    by = _by(alloc)
    assert by["loyaltyBonus"]["customerBenefit"] == by["loyaltyBonus"]["schemeAvailable"]
    assert by["insuranceBenefit"]["customerBenefit"] == by["insuranceBenefit"]["schemeAvailable"]


def test_historical_pre_v2_full_benefit_does_not_silently_pass_entitlements():
    """Pre-fix leads without schemeAllocationV2 keep entitlement CB=0 under Full Benefit."""
    s = {**BASE, "benefitMode": "Full Benefit"}
    del s["schemeAllocationV2"]
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    by = _by(alloc)
    assert by["loyaltyBonus"]["customerBenefit"] == 10000
    assert by["insuranceBenefit"]["customerBenefit"] == 0
    assert alloc["totals"]["dealerRetained"] == 20000
    assert alloc["totals"]["oemClaimable"] == 20000


def test_dealer_funded_share_is_not_dealer_retained():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    ins = _by(alloc)["insuranceBenefit"]
    assert ins["dealerFundedShare"] == 10000
    assert ins["dealerRetained"] == 20000
    assert ins["dealerFundedShare"] != ins["dealerRetained"]


def test_customer_payable_uses_only_customer_benefit():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}
    totals = ce.compute_commercial_totals(s, TURBO_SCHEME)
    assert totals["totalPassedToCustomer"] == 5000
    assert totals["customerPayable"] == 787000


def test_insurance_payout_is_not_oem_claim():
    premium, rate = 22000, ce.suggested_insurance_payout_rate(MODEL, VARIANT)
    expected = ce.round2(premium * rate)
    assert expected == 10780
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    assert alloc["totals"]["oemClaimable"] == 20000
    assert expected not in [c["oemClaimable"] for c in alloc["components"]]


def test_non_scheme_commercials_unchanged_without_scheme_rows():
    t = ce.compute_commercial_totals({
        "exShowroom": 640000, "insurance": 22000, "tcsApplicable": "No", "benefitMode": "Full Benefit"})
    assert t["grossVehicleCost"] == 662000
    assert t["customerPayable"] == 662000
    m = ce.compute_dealer_margin({"exShowroom": 640000})
    assert abs(m["marginNetExGst"] - 23220) < 1


def test_scheme_allocation_does_not_alter_non_scheme_commercials():
    """Changing customer benefit must only reduce payable — not charges / GST / TCS."""
    base = {
        "model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
        "loyaltyBonus": 10000, "exShowroom": 770000, "registrationRto": 15000, "insurance": 22000,
        "tcsApplicable": "No", "schemeAllocationV2": True,
    }
    a = ce.compute_commercial_totals({**base, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    b = ce.compute_commercial_totals({
        **base, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}, TURBO_SCHEME)
    # Non-scheme commercial totals unchanged except for customer benefit reduction
    assert a["grossVehicleCost"] == b["grossVehicleCost"] == 807000
    assert a["tcs"] == b["tcs"] == 0
    assert a["oemEligible"] == b["oemEligible"]  # offer pool unchanged
    assert ce.round2(a["customerPayable"] - b["customerPayable"]) == 5000
    assert a["totalPassedToCustomer"] == 0
    assert b["totalPassedToCustomer"] == 5000
    # Margin (ex-showroom based) unchanged by scheme allocation
    ma = ce.compute_dealer_margin(base)
    mb = ce.compute_dealer_margin({**base, "benefitMode": "Full Benefit"})
    assert ma == mb


def test_adapters_share_single_allocation():
    s = {**BASE, "benefitMode": "Full Benefit"}
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    income = ce.compute_scheme_income_breakdown(s, TURBO_SCHEME)
    shares = ce.compute_scheme_claim_shares(s, TURBO_SCHEME)
    assert income["retainedIncomeTotal"] == alloc["totals"]["dealerRetained"] == 0
    assert income["oemClaimTotal"] == shares["displayTotal"] == 20000


# ============================================================ integration
@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def turbo_booked(c, mobile, *, benefit_mode="No Benefit", breakup=None, deliver=False):
    r = await c.post("/api/leads", json={
        "customerName": "ALLOC TURBO", "mobile": mobile, "interestedModel": MODEL,
        "variant": VARIANT, "executive": "Amit", "leadSource": "Walk-in"})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    payload = {"loyaltyBonus": 10000, "benefitMode": benefit_mode}
    if breakup is not None:
        payload["benefitPassedBreakup"] = json.dumps(breakup)
        payload["benefitMode"] = "Partial Benefit"
    await c.put(f"/api/leads/{lid}/scheme", json=payload)
    if deliver:
        lead = (await c.get(f"/api/leads/{lid}")).json()
        await c.post(f"/api/leads/{lid}/payments",
                     json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
        await c.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
            "insurerName": "ICICI Lombard", "invoiceNumber": "INV-ALLOC",
            "chassisNumber": "CH-ALLOC", "numberPlate": "RJ14-AL", "delivered": "Yes"})
    return lid


@pytest.mark.asyncio
async def test_D_api_full_benefit_passes_insurance(client):
    lid = await turbo_booked(client, "9888810001", benefit_mode="Full Benefit")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead.get("schemeAllocationV2") is True
    assert lead["schemeCustomerBenefit"] == 30000
    assert lead["dealerSchemeRetained"] == 0
    assert lead["companyOutstanding"] == 20000
    bk = json.loads(lead["benefitPassedBreakup"])
    assert bk["loyaltyBonus"] == 10000
    assert bk["insuranceBenefit"] == 20000


@pytest.mark.asyncio
async def test_A_api_no_benefit(client):
    lid = await turbo_booked(client, "9888810002", benefit_mode="No Benefit")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["schemeCustomerBenefit"] == 0
    assert lead["dealerSchemeRetained"] == 30000
    assert lead["companyOutstanding"] == 20000


@pytest.mark.asyncio
async def test_E_insurance_5k_to_20k_deltas(client):
    lid = await turbo_booked(client, "9888810003",
                             breakup={"loyaltyBonus": 0, "insuranceBenefit": 5000})
    before = await server.db.leads.find_one({"leadId": lid})
    assert before["schemeCustomerBenefit"] == 5000
    assert before["dealerSchemeRetained"] == 25000
    claim_before = before["companyOutstanding"]

    await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": 10000, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 0, "insuranceBenefit": 20000})})
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.round2(before["customerPayable"] - after["customerPayable"]) == 15000
    assert ce.round2(before["dealerSchemeRetained"] - after["dealerSchemeRetained"]) == 15000
    assert after["companyOutstanding"] == claim_before == 20000


@pytest.mark.asyncio
async def test_F_partial_claim_receipt_isolates_components(client):
    lid = await turbo_booked(client, "9888810004", benefit_mode="No Benefit")
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text
    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert sorted(claims) == ["insuranceBenefit", "loyaltyBonus"]
    assert claims["loyaltyBonus"]["receivedAmount"] == 10000
    assert claims["loyaltyBonus"]["claimStatus"] == "Received"
    assert claims["insuranceBenefit"]["receivedAmount"] == 0
    assert claims["insuranceBenefit"]["claimStatus"] == "Pending"
    total = ce.round2(sum(ce.num(c["eligibleClaim"]) for c in claims.values()))
    received = ce.round2(sum(ce.num(c["receivedAmount"]) for c in claims.values()))
    assert (total, received, ce.round2(total - received)) == (20000, 10000, 10000)


@pytest.mark.asyncio
async def test_earnings_no_double_count_scheme_and_payout(client):
    """Scheme benefit + insurer payout + memo customerInsuranceBenefitPassed must not double-count."""
    await server.db.leads.delete_many({})
    await server.db.insurance.delete_many({})
    await server.db.dealer_earnings.delete_many({})
    lid = await turbo_booked(client, "9888810005",
                             breakup={"loyaltyBonus": 0, "insuranceBenefit": 5000}, deliver=True)
    await client.put(f"/api/leads/{lid}/extra-income", json={
        "customerInsuranceBenefitPassed": 3000, "documentationIncome": 1000})
    lead = await server.db.leads.find_one({"leadId": lid})
    entry = await server.db.insurance.find_one({"leadId": lid})
    payout = ce.num(entry["expectedPayout"])

    # Dealer earnings composition (authoritative):
    # margin + scheme retained + oem extra + extra(without cust ins memo) + insurance payout
    expected_total = ce.round2(
        lead["dealerMarginNetExGst"] + lead["dealerSchemeRetained"]
        + lead["oemExtraSupportRetained"] + lead["extraDealerIncomeTotal"]
        + lead["dealerInsuranceIncome"])
    assert lead["dealerTotalEarnings"] == expected_total
    assert lead["dealerInsuranceIncome"] == payout
    # customerInsuranceBenefitPassed must NOT inflate extraDealerIncomeTotal
    assert lead["extraDealerIncomeTotal"] == 1000
    assert lead["dealerSchemeRetained"] == 25000

    report = (await client.get("/api/reports/dealer-earnings")).json()
    assert report["totals"]["scheme"] == 25000
    assert report["totals"]["insurance"] == payout
    # Memo line may appear for visibility but must not inflate the total beyond
    # margin + scheme retained + insurance payout + real extra (+ oem other in months).
    memo_amt = next((c["amount"] for c in report["components"]
                     if "memo" in c["label"].lower()), 0)
    assert memo_amt == 3000
    reconstructed = ce.round2(
        report["totals"]["margin"] + report["totals"]["scheme"]
        + report["totals"]["insurance"] + report["totals"]["extra"]
        + sum(m.get("other", 0) for m in report["byMonth"]))
    assert report["totals"]["total"] == reconstructed
    # And the memo is NOT inside extra:
    assert report["totals"]["extra"] == 1000


@pytest.mark.asyncio
async def test_finance_fn26_lifecycle(client):
    """Lead → Booking → Payment → Finance with blank file number → FN26xxxxxx."""
    r = await client.post("/api/leads", json={
        "customerName": "FN26 REGRESSION", "mobile": "9888810006",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit"})
    lid = r.json()["leadId"]
    await client.put(f"/api/leads/{lid}/price-structure",
                     json={"exShowroom": 435000, "rto": 10000, "insuranceAmount": 10000})
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-08", "bookingAmount": 0})
    lead = (await client.get(f"/api/leads/{lid}")).json()
    outstanding = lead["customerOutstanding"]
    r = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": outstanding, "paymentMode": "Finance", "financerName": "SHRIRAM"})
    assert r.status_code == 200, r.text
    fn = r.json()["financeFileNumber"]
    assert re.match(r"^FN26\d{6}$", fn), fn
    # Subsequent payment reuses the same FN26
    fin = await server.db.finance.find_one({"fileNumber": fn})
    assert fin["fileOutstanding"] == outstanding
    r2 = await client.post(f"/api/finance/{fn}/receipt",
                           json={"amount": 1000, "date": "2026-08-09"})
    assert r2.status_code == 200
    fin2 = await server.db.finance.find_one({"fileNumber": fn})
    assert fin2["fileOutstanding"] == ce.round2(outstanding - 1000)
    assert await server.db.finance.count_documents({"leadId": lid}) == 1


@pytest.mark.asyncio
async def test_modules_reconcile_turbo_no_benefit(client):
    await server.db.leads.delete_many({})
    await server.db.claims.delete_many({})
    await server.db.insurance.delete_many({})
    lid = await turbo_booked(client, "9888810007", benefit_mode="No Benefit", deliver=True)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["dealerSchemeRetained"] == 30000
    assert lead["schemeCustomerBenefit"] == 0
    assert lead["companyOutstanding"] == 20000
    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert sorted(c["componentKey"] for c in claims) == ["insuranceBenefit", "loyaltyBonus"]
    dash = (await client.get("/api/reports/oem-claim-dashboard")).json()
    assert ce.round2(sum(s["value"] for s in dash["schemeWise"])) == \
        ce.round2(dash["valueSummary"]["eligibleClaim"])
    report = (await client.get("/api/reports/dealer-earnings")).json()
    assert report["totals"]["scheme"] == 30000
    entry = await server.db.insurance.find_one({"leadId": lid})
    assert report["totals"]["insurance"] == entry["expectedPayout"]


@pytest.mark.asyncio
async def test_scheme_screen_still_surfaces_insurance(client):
    lid = await turbo_booked(client, "9888810008", benefit_mode="No Benefit")
    rules = (await client.get(f"/api/leads/{lid}/scheme-rules")).json()
    ents = {e["key"]: e for e in rules["entitlements"]}
    assert "insuranceBenefit" in ents
    assert ents["insuranceBenefit"]["totalBenefit"] == 20000
    assert ents["insuranceBenefit"]["companyShare"] == 10000
    assert ents["insuranceBenefit"]["dealerShare"] == 10000
