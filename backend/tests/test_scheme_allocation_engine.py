"""Authoritative scheme allocation engine — permanent test matrix.

Formulas under test (every scheme component):
  customerBenefit ∈ [0, schemeAvailable]
  dealerRetained  = schemeAvailable − customerBenefit
  oemClaimable    = authoritative OEM/company share (Scheme Master)
  Customer Payable reduction = Σ customerBenefit
  Dealer Scheme Earnings     = Σ dealerRetained
  OEM Claim                  = Σ oemClaimable

Insurance Payout (premium × rate) is a SEPARATE ledger from Insurance Scheme Benefit.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scheme_alloc_engine")
os.environ.setdefault("JWT_SECRET", "scheme-alloc-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

# Real Turbo Aug'26 Scheme Master values (circular EM/08-2026/001) — not hardcoded
# business invention; mirrors seed data.
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
}


def _by(alloc):
    return {c["key"]: c for c in alloc["components"]}


# ------------------------------------------------------------------ unit matrix
def test_1_loyalty_pass_zero():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    loy = _by(alloc)["loyaltyBonus"]
    assert (loy["schemeAvailable"], loy["customerBenefit"], loy["dealerRetained"], loy["oemClaimable"]) == \
        (10000, 0, 10000, 10000)


def test_2_loyalty_pass_full():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "Full Benefit"}, TURBO_SCHEME)
    loy = _by(alloc)["loyaltyBonus"]
    assert (loy["schemeAvailable"], loy["customerBenefit"], loy["dealerRetained"], loy["oemClaimable"]) == \
        (10000, 10000, 0, 10000)


def test_3_insurance_pass_zero():
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    ins = _by(alloc)["insuranceBenefit"]
    assert ins["schemeAvailable"] == 20000
    assert ins["oemShare"] == 10000
    assert ins["dealerFundedShare"] == 10000
    assert ins["customerBenefit"] == 0
    assert ins["dealerRetained"] == 20000
    assert ins["oemClaimable"] == 10000


def test_4_insurance_pass_10000():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 10000}}
    ins = _by(ce.compute_scheme_allocation(s, TURBO_SCHEME))["insuranceBenefit"]
    assert (ins["customerBenefit"], ins["dealerRetained"], ins["oemClaimable"]) == (10000, 10000, 10000)


def test_5_insurance_pass_20000():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 20000}}
    ins = _by(ce.compute_scheme_allocation(s, TURBO_SCHEME))["insuranceBenefit"]
    assert (ins["customerBenefit"], ins["dealerRetained"], ins["oemClaimable"]) == (20000, 0, 10000)


def test_6_multiple_components():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    t = alloc["totals"]
    assert t["customerBenefit"] == 5000
    assert t["dealerRetained"] == 25000
    assert t["oemClaimable"] == 20000


def test_7_customer_payable_uses_only_customer_benefit():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}
    totals = ce.compute_commercial_totals(s, TURBO_SCHEME)
    # Gross = 770000 + 22000 = 792000; reduction = 5000 → payable 787000
    assert totals["totalPassedToCustomer"] == 5000
    assert totals["customerPayable"] == 787000
    assert totals["totalPassedToCustomer"] != 30000
    assert totals["totalPassedToCustomer"] != 25000
    assert totals["totalPassedToCustomer"] != 20000


def test_8_dealer_earnings_uses_dealer_retained():
    s = {**BASE, "benefitMode": "Partial Benefit",
         "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": 5000}}
    income = ce.compute_scheme_income_breakdown(s, TURBO_SCHEME)
    assert income["retainedIncomeTotal"] == 25000


def test_9_oem_claim_separate_components():
    s = {**BASE, "benefitMode": "No Benefit"}
    shares = ce.compute_scheme_claim_shares(s, TURBO_SCHEME)
    assert shares["displayByComponent"]["loyaltyBonus"] == 10000
    assert shares["displayByComponent"]["insuranceBenefit"] == 10000
    assert shares["displayTotal"] == 20000


def test_11_insurance_payout_is_not_oem_claim():
    premium = 22000
    rate = ce.suggested_insurance_payout_rate(MODEL, VARIANT)
    expected = ce.round2(premium * rate)
    assert rate == 0.49
    assert expected == 10780
    # Payout must not appear in scheme allocation oemClaimable
    alloc = ce.compute_scheme_allocation({**BASE, "benefitMode": "No Benefit"}, TURBO_SCHEME)
    assert alloc["totals"]["oemClaimable"] == 20000  # loyalty+insurance scheme only
    assert expected not in [c["oemClaimable"] for c in alloc["components"]]


def test_no_benefit_loyalty_no_longer_cancels_to_zero():
    """The production bug: Loyalty No Benefit showed Dealer Scheme Retained ₹0
    because insurance entitlement retained was −dealerShare (−10000)."""
    s = {**BASE, "benefitMode": "No Benefit"}
    income = ce.compute_scheme_income_breakdown(s, TURBO_SCHEME)
    assert income["retainedByComponent"]["loyaltyBonus"] == 10000
    assert income["retainedByComponent"]["insuranceBenefit"] == 20000
    assert income["retainedIncomeTotal"] == 30000
    assert all(v >= 0 for v in income["retainedByComponent"].values())


def test_adapters_share_the_same_allocation():
    s = {**BASE, "benefitMode": "Full Benefit"}
    alloc = ce.compute_scheme_allocation(s, TURBO_SCHEME)
    income = ce.compute_scheme_income_breakdown(s, TURBO_SCHEME)
    shares = ce.compute_scheme_claim_shares(s, TURBO_SCHEME)
    assert income["retainedIncomeTotal"] == alloc["totals"]["dealerRetained"]
    assert income["oemClaimTotal"] == alloc["totals"]["oemClaimable"]
    assert shares["displayTotal"] == alloc["totals"]["oemClaimable"]
    assert income["allocation"]["totals"] == alloc["totals"]


# ----------------------------------------------------------- integration matrix
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
        import json
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
async def test_10_partial_claim_receipt_isolates_components(client):
    lid = await turbo_booked(client, "9888800001")
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text
    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert claims["loyaltyBonus"]["receivedAmount"] == 10000
    assert claims["loyaltyBonus"]["claimStatus"] == "Received"
    assert claims["insuranceBenefit"]["receivedAmount"] == 0
    assert claims["insuranceBenefit"]["claimStatus"] == "Pending"


@pytest.mark.asyncio
async def test_12_idempotent_recompute_and_delivery(client):
    lid = await turbo_booked(client, "9888800002", deliver=True)
    before = await server.db.leads.find_one({"leadId": lid})
    await server.recompute_lead(lid)
    await server.recompute_lead(lid)
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["dealerSchemeRetained"] == before["dealerSchemeRetained"]
    assert after["customerPayable"] == before["customerPayable"]
    assert after["companyOutstanding"] == before["companyOutstanding"]
    assert await server.db.insurance.count_documents({"leadId": lid}) == 1
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "invoiceNumber": "INV-ALLOC",
        "chassisNumber": "CH-ALLOC", "numberPlate": "RJ14-AL", "delivered": "Yes"})
    assert await server.db.insurance.count_documents({"leadId": lid}) == 1


@pytest.mark.asyncio
async def test_13_historical_impact_report_is_read_only(client):
    lid = await turbo_booked(client, "9888800003")
    before = await server.db.leads.find_one({"leadId": lid})
    r = await client.get("/api/reports/scheme-allocation-impact")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["readOnly"] is True
    assert body["modified"] is False
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before["customerPayable"]
    assert after["dealerSchemeRetained"] == before["dealerSchemeRetained"]


@pytest.mark.asyncio
async def test_modules_reconcile_on_turbo_no_benefit(client):
    """Lead / Dealer Earnings / Claim Register / Claim Dashboard / Earnings Report agree."""
    await server.db.leads.delete_many({})
    await server.db.claims.delete_many({})
    await server.db.insurance.delete_many({})
    await server.db.dealer_earnings.delete_many({})
    lid = await turbo_booked(client, "9888800004", benefit_mode="No Benefit", deliver=True)
    lead = await server.db.leads.find_one({"leadId": lid})

    assert lead["dealerSchemeRetained"] == 30000
    assert lead["schemeCustomerBenefit"] == 0
    assert lead["companyOutstanding"] == 20000
    assert lead["schemeAllocation"]["totals"]["oemClaimable"] == 20000

    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert sorted(c["componentKey"] for c in claims) == ["insuranceBenefit", "loyaltyBonus"]
    assert ce.round2(sum(ce.num(c["eligibleClaim"]) for c in claims)) == 20000

    dash = (await client.get("/api/reports/oem-claim-dashboard")).json()
    scheme_wise = {s["scheme"]: s["value"] for s in dash["schemeWise"]}
    assert scheme_wise["Loyalty"] == 10000
    assert scheme_wise["Insurance Benefit"] == 10000
    assert ce.round2(sum(s["value"] for s in dash["schemeWise"])) == \
        ce.round2(dash["valueSummary"]["eligibleClaim"])
    assert dash["bookings"] == 1

    de = (await client.get("/api/dealer-earnings")).json()
    row = next(r for r in de["rows"] if r["leadId"] == lid)
    assert row["dealerSchemeRetained"] == 30000

    report = (await client.get("/api/reports/dealer-earnings")).json()
    assert report["totals"]["scheme"] == 30000
    # Insurance PAYOUT (not scheme benefit) flows to insurance column
    entry = await server.db.insurance.find_one({"leadId": lid})
    assert entry["expectedPayout"] == ce.round2(ce.num(lead["insuranceAmount"]) * 0.49)
    assert report["totals"]["insurance"] == entry["expectedPayout"]
    # Payout is not folded into OEM claim
    assert lead["companyOutstanding"] == 20000


@pytest.mark.asyncio
async def test_entitlement_customer_benefit_reduces_payable_only_when_allocated(client):
    lid = await turbo_booked(client, "9888800005", breakup={"loyaltyBonus": 0, "insuranceBenefit": 5000})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["schemeCustomerBenefit"] == 5000
    assert lead["dealerSchemeRetained"] == 25000
    assert lead["companyOutstanding"] == 20000
    # Payable reduced by 5000 vs No-Benefit baseline for same price structure
    baseline = await turbo_booked(client, "9888800006", benefit_mode="No Benefit")
    base_lead = await server.db.leads.find_one({"leadId": baseline})
    assert ce.round2(base_lead["customerPayable"] - lead["customerPayable"]) == 5000
