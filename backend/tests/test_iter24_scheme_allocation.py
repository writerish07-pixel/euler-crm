"""The Scheme Allocation Engine — one authoritative calculation.

Every scheme component carries a SCHEME ENTITLEMENT (what the circular makes
available) and a DEALER ALLOCATION (how much of it is passed to the customer):

    dealerRetained = schemeAvailable - customerBenefit      (never negative)
    oemClaimable   = oemShare                               (never schemeAvailable)

Customer Payable falls only by customerBenefit. Dealer Earnings takes only
dealerRetained. The OEM Claim Register takes only oemClaimable. Nothing is
special-cased — entitlements allocate exactly like staff-entered offers.

Scheme Master rows here come from the LIVE workbook's Turbo Aug'26 rows, which match
circular EM/08-2026/001: Loyalty 0/10,000/10,000 and Insurance 10,000/10,000/20,000.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter24alloc")
os.environ.setdefault("JWT_SECRET", "iter24-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Turbo Max", "Maxx (PV)"


def turbo_rows():
    """Turbo Aug'26 exactly as the live Scheme Master holds it."""
    base = {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08",
            "effectiveTo": "2026-08-31", "model": "Turbo", "variant": "",
            "status": "Active"}
    return [
        {**base, "componentKey": "loyaltyBonus", "component": "Loyalty",
         "dealerShare": 0.0, "companyShare": 10000.0, "totalBenefit": 10000.0},
        {**base, "componentKey": "insuranceBenefit", "component": "Insurance Benefit",
         "dealerShare": 10000.0, "companyShare": 10000.0, "totalBenefit": 20000.0},
    ]


def allocate(**allocation):
    """Run the engine for a Turbo lead with an explicit dealer allocation."""
    snap = {"model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
            "loyaltyBonus": 10000, "benefitMode": "Full Benefit",
            "schemeAllocation": allocation}
    return ce.compute_scheme_allocation(snap, turbo_rows())


def comp(res, key):
    return res["byKey"][key]


# ------------------------------------------------------------------ CASES 1-2
def test_case1_loyalty_pass_zero():
    c = comp(allocate(loyaltyBonus=0, insuranceBenefit=0), "loyaltyBonus")
    assert (c["schemeAvailable"], c["customerBenefit"], c["dealerRetained"], c["oemClaimable"]) \
        == (10000, 0, 10000, 10000)


def test_case2_loyalty_pass_full():
    c = comp(allocate(loyaltyBonus=10000, insuranceBenefit=0), "loyaltyBonus")
    assert (c["schemeAvailable"], c["customerBenefit"], c["dealerRetained"], c["oemClaimable"]) \
        == (10000, 10000, 0, 10000)


# ------------------------------------------------------------------ CASES 3-5
@pytest.mark.parametrize("passed,retained", [(0, 20000), (5000, 15000),
                                             (10000, 10000), (20000, 0)])
def test_cases3to5_insurance_allocation_across_the_full_range(passed, retained):
    c = comp(allocate(loyaltyBonus=0, insuranceBenefit=passed), "insuranceBenefit")
    assert c["schemeAvailable"] == 20000
    assert c["oemShare"] == 10000
    assert c["dealerFundedShare"] == 10000
    assert c["customerBenefit"] == passed
    assert c["dealerRetained"] == retained
    # OEM claimable never tracks what the dealer chose to pass on.
    assert c["oemClaimable"] == 10000


# -------------------------------------------------------------------- CASE 6
def test_case6_multiple_components():
    res = allocate(loyaltyBonus=0, insuranceBenefit=5000)
    t = res["totals"]
    assert t["customerBenefit"] == 5000
    assert t["dealerRetained"] == 25000        # 10,000 loyalty + 15,000 insurance
    assert t["oemClaimable"] == 20000          # 10,000 + 10,000
    assert t["schemeAvailable"] == 30000


# -------------------------------------------------- validation (section 15)
def test_retained_is_never_negative_and_benefit_is_clamped():
    over = comp(allocate(insuranceBenefit=999999), "insuranceBenefit")
    assert over["customerBenefit"] == 20000 and over["dealerRetained"] == 0
    under = comp(allocate(insuranceBenefit=-5000), "insuranceBenefit")
    assert under["customerBenefit"] == 0 and under["dealerRetained"] == 20000


def test_identity_holds_for_every_component():
    res = allocate(loyaltyBonus=3000, insuranceBenefit=7000)
    for c in res["components"]:
        assert c["dealerRetained"] == ce.round2(c["schemeAvailable"] - c["customerBenefit"])
        assert c["oemClaimable"] == c["oemShare"]
        assert c["dealerRetained"] >= 0
    assert len({c["key"] for c in res["components"]}) == len(res["components"]), "component counted twice"


def test_no_component_is_special_cased():
    """Insurance allocates by exactly the same rule as Loyalty."""
    res = allocate(loyaltyBonus=5000, insuranceBenefit=5000)
    for key in ("loyaltyBonus", "insuranceBenefit"):
        c = comp(res, key)
        assert c["customerBenefit"] == 5000
        assert c["dealerRetained"] == c["schemeAvailable"] - 5000


# ============================ end-to-end through the API ====================
@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def turbo_lead(c, mobile):
    r = await c.post("/api/leads", json={
        "customerName": "ITER24 ALLOC", "mobile": mobile, "interestedModel": MODEL,
        "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    await c.put(f"/api/leads/{lid}/scheme",
                json={"loyaltyBonus": 10000, "benefitMode": "No Benefit"})
    return lid


# ------------------------------------------------------------- CASES 7 and 8
@pytest.mark.asyncio
async def test_case7_customer_payable_moves_only_by_customer_benefit(client):
    lid = await turbo_lead(client, "9888800001")
    before = await server.db.leads.find_one({"leadId": lid})

    r = await client.put(f"/api/leads/{lid}/scheme-allocation",
                         json={"allocation": {"loyaltyBonus": 0, "insuranceBenefit": 5000}})
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})

    # payable falls by the 5,000 actually passed - not by 20,000, not by 10,000
    assert after["customerPayable"] == ce.round2(before["customerPayable"] - 5000)
    assert after["schemeCustomerBenefitTotal"] == 5000


@pytest.mark.asyncio
async def test_case8_dealer_earnings_take_the_retained_portion(client):
    lid = await turbo_lead(client, "9888800002")
    await client.put(f"/api/leads/{lid}/scheme-allocation",
                     json={"allocation": {"loyaltyBonus": 0, "insuranceBenefit": 5000}})
    lead = await server.db.leads.find_one({"leadId": lid})

    assert lead["dealerSchemeRetained"] == 25000          # 10,000 + 15,000
    assert lead["schemeOemClaimableTotal"] == 20000       # separate from earnings
    # Insurance CB ₹5,000 ≤ OEM share ₹10,000 → dealer-funded benefit cost ₹0
    assert lead["dealerFundedBenefit"] == 0
    assert lead["dealerTotalEarnings"] == ce.round2(
        lead["dealerMarginNetExGst"] + 25000
        + lead["oemExtraSupportRetained"] + lead["extraDealerIncomeTotal"]
        - lead["dealerFundedBenefit"])
    # OEM claim receivable is NOT dealer income
    assert lead["dealerSchemeRetained"] != lead["schemeOemClaimableTotal"]


# ------------------------------------------------------------ CASES 9 and 10
@pytest.mark.asyncio
async def test_case9_claim_register_keeps_components_separate(client):
    lid = await turbo_lead(client, "9888800003")
    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert set(claims) == {"loyaltyBonus", "insuranceBenefit"}
    assert claims["loyaltyBonus"]["eligibleClaim"] == 10000
    assert claims["insuranceBenefit"]["eligibleClaim"] == 10000


@pytest.mark.asyncio
async def test_case10_receiving_one_component_leaves_the_other_outstanding(client):
    lid = await turbo_lead(client, "9888800004")
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text
    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert claims["loyaltyBonus"]["receivedAmount"] == 10000
    assert claims["insuranceBenefit"]["receivedAmount"] == 0
    assert claims["insuranceBenefit"]["claimStatus"] == "Pending"


# ------------------------------------------------------------------ CASE 11
@pytest.mark.asyncio
async def test_case11_insurance_payout_is_not_an_oem_scheme_claim(client):
    """Premium x rate is DEALER INSURANCE INCOME. It must never appear as an OEM
    scheme claim, and the insurance SCHEME benefit must never appear as a payout."""
    lid = await turbo_lead(client, "9888800005")
    lead = await server.db.leads.find_one({"leadId": lid})
    await client.post(f"/api/leads/{lid}/payments",
                      json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "invoiceNumber": "INV-24",
        "chassisNumber": "CH-24", "numberPlate": "RJ14-24", "delivered": "Yes"})

    entry = await server.db.insurance.find_one({"leadId": lid})
    assert entry["payoutRate"] == 0.49                       # Turbo
    assert entry["expectedPayout"] == ce.round2(entry["insuranceAmount"] * 0.49)

    claims = {c["componentKey"] for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert "insurancePayout" not in claims
    ins_claim = [c for c in (await client.get("/api/claims")).json()
                 if c["leadId"] == lid and c["componentKey"] == "insuranceBenefit"][0]
    assert ins_claim["eligibleClaim"] == 10000               # scheme share, not the payout
    assert ins_claim["eligibleClaim"] != entry["expectedPayout"]


# ------------------------------------------------------------------ CASE 12
@pytest.mark.asyncio
async def test_case12_repeat_operations_create_no_duplicates(client):
    lid = await turbo_lead(client, "9888800006")
    lead = await server.db.leads.find_one({"leadId": lid})
    await client.post(f"/api/leads/{lid}/payments",
                      json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    delivery = {"insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
                "rc": "Yes", "insurerName": "ICICI Lombard", "invoiceNumber": "INV-24",
                "chassisNumber": "CH-24", "numberPlate": "RJ14-24", "delivered": "Yes"}
    for _ in range(3):
        await client.put(f"/api/leads/{lid}/delivery", json=delivery)
        await server.recompute_lead(lid)

    assert await server.db.insurance.count_documents({"leadId": lid}) == 1
    assert await server.db.deliveries.count_documents({"leadId": lid}) == 1
    assert await server.db.finance.count_documents({"leadId": lid}) == 0
    # Derived claims are computed live from the scheme split, so the register is the
    # thing to check for duplication (db.claims only persists receipts/manual claims).
    keys = [c["componentKey"] for c in (await client.get("/api/claims")).json()
            if c["leadId"] == lid]
    assert sorted(keys) == ["insuranceBenefit", "loyaltyBonus"], keys
    assert len(keys) == len(set(keys)), f"duplicate claim components: {keys}"
    # dealer earnings are recomputed, never accumulated
    a = (await server.db.leads.find_one({"leadId": lid}))["dealerTotalEarnings"]
    await server.recompute_lead(lid)
    b = (await server.db.leads.find_one({"leadId": lid}))["dealerTotalEarnings"]
    assert a == b


# ------------------------------------------------------------------ CASE 13
@pytest.mark.asyncio
async def test_case13_historical_lead_payable_is_not_silently_rewritten(client):
    """A lead with no explicit allocation must keep its customer payable when the new
    engine runs. Only an explicit dealer decision may move customer accounting."""
    lid = await turbo_lead(client, "9888800007")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert not lead.get("schemeAllocation")
    before = lead["customerPayable"]

    for _ in range(3):
        await server.recompute_lead(lid)
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before, "recompute silently moved historical payable"
    assert after["schemeCustomerBenefitTotal"] == 0


@pytest.mark.asyncio
async def test_allocation_is_validated_against_scheme_master(client):
    lid = await turbo_lead(client, "9888800008")
    r = await client.put(f"/api/leads/{lid}/scheme-allocation",
                         json={"allocation": {"insuranceBenefit": 25000}})
    assert r.status_code == 422 and "exceeds" in r.text
    r = await client.put(f"/api/leads/{lid}/scheme-allocation",
                         json={"allocation": {"insuranceBenefit": -1}})
    assert r.status_code == 422 and "negative" in r.text
    r = await client.put(f"/api/leads/{lid}/scheme-allocation",
                         json={"allocation": {"notAComponent": 100}})
    assert r.status_code == 422 and "not a scheme component" in r.text


@pytest.mark.asyncio
async def test_scheme_rules_exposes_the_same_allocation_the_engine_produces(client):
    """The Lead Drawer must consume the engine, not reconstruct scheme maths."""
    lid = await turbo_lead(client, "9888800009")
    await client.put(f"/api/leads/{lid}/scheme-allocation",
                     json={"allocation": {"insuranceBenefit": 7500}})
    rules = (await client.get(f"/api/leads/{lid}/scheme-rules")).json()
    ins = rules["allocation"]["byKey"]["insuranceBenefit"]
    assert ins["customerBenefit"] == 7500
    assert ins["dealerRetained"] == 12500
    assert ins["oemClaimable"] == 10000
    lead = await server.db.leads.find_one({"leadId": lid})
    assert rules["allocation"]["totals"]["dealerRetained"] == lead["dealerSchemeRetained"]
