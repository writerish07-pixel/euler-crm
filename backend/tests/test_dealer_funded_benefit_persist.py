"""MASTER FINAL FIX — dealer-funded benefit + Insurance Benefit persistence.

Authoritative engine remains compute_scheme_allocation(). These tests prove:

  * dealerFundedBenefit is derived from allocation (OEM-share-first of CB)
  * Dealer Earnings deducts only that cost (not full CB, not OEM claim)
  * Insurance Benefit persists independently from Loyalty (Mongo + sheet payloads)
  * Scheme Claim Register keeps separate component rows
  * Re-save is idempotent; historical leads without V2 are not rewritten
  * Insurance payout stays a separate ledger

No production Google Sheet writes — sheet_sync is stubbed / captured.
"""
import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ["MONGO_URL"] = "mongodb://localhost:27017"
os.environ["DB_NAME"] = "funded_benefit_persist"
os.environ["JWT_SECRET"] = "funded-benefit-test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Turbo Max", "Maxx (PV)"
EX_SHOWROOM = 770000  # marginNetExGst = 27936.50 → displays as ₹27,937


def turbo_rows():
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
    snap = {"model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
            "loyaltyBonus": 10000, "benefitMode": "Full Benefit",
            "schemeAllocationExplicit": True, "schemeAllocationV2": True,
            "schemeAllocation": allocation,
            "benefitPassedBreakup": allocation,
            "schemeComponentsUsed": {k: True for k in allocation}}
    return ce.compute_scheme_allocation(snap, turbo_rows())


# ================================================================== UNIT MATRIX
def test1_turbo_no_benefit():
    t = allocate(loyaltyBonus=0, insuranceBenefit=0)["totals"]
    assert t["customerBenefit"] == 0
    assert t["dealerRetained"] == 20000
    assert t["oemClaimable"] == 20000
    assert t["dealerFundedBenefit"] == 0


def test2_loyalty_full():
    t = allocate(loyaltyBonus=10000, insuranceBenefit=0)["totals"]
    assert t["customerBenefit"] == 10000
    assert t["dealerRetained"] == 10000
    assert t["oemClaimable"] == 20000
    assert t["dealerFundedBenefit"] == 0  # loyalty is 100% OEM-funded


def test3_insurance_full():
    t = allocate(loyaltyBonus=0, insuranceBenefit=20000)["totals"]
    assert t["customerBenefit"] == 20000
    assert t["dealerRetained"] == 10000
    assert t["oemClaimable"] == 20000
    assert t["dealerFundedBenefit"] == 10000


def test4_both_full():
    t = allocate(loyaltyBonus=10000, insuranceBenefit=20000)["totals"]
    assert t["customerBenefit"] == 30000
    assert t["dealerRetained"] == 0
    assert t["oemClaimable"] == 20000
    assert t["dealerFundedBenefit"] == 10000


def test6_partial_insurance():
    t = allocate(loyaltyBonus=0, insuranceBenefit=15000)["totals"]
    assert t["dealerFundedBenefit"] == 5000
    assert t["dealerRetained"] == 10000  # 10000 loyalty kept + 0 ins kept
    assert t["oemClaimable"] == 20000


def test7_partial_loyalty():
    t = allocate(loyaltyBonus=5000, insuranceBenefit=0)["totals"]
    assert t["dealerFundedBenefit"] == 0
    assert t["dealerRetained"] == 15000  # loy 5k kept + ins 10k kept
    assert t["oemClaimable"] == 20000


def test8_change_insurance_only_leaves_loyalty():
    a = allocate(loyaltyBonus=10000, insuranceBenefit=5000)
    b = allocate(loyaltyBonus=10000, insuranceBenefit=15000)
    assert a["byKey"]["loyaltyBonus"]["customerBenefit"] == b["byKey"]["loyaltyBonus"]["customerBenefit"] == 10000
    assert a["byKey"]["insuranceBenefit"]["customerBenefit"] == 5000
    assert b["byKey"]["insuranceBenefit"]["customerBenefit"] == 15000
    assert b["totals"]["dealerFundedBenefit"] == 5000


def test9_change_loyalty_only_leaves_insurance():
    a = allocate(loyaltyBonus=0, insuranceBenefit=20000)
    b = allocate(loyaltyBonus=10000, insuranceBenefit=20000)
    assert a["byKey"]["insuranceBenefit"]["customerBenefit"] == b["byKey"]["insuranceBenefit"]["customerBenefit"] == 20000
    assert a["byKey"]["loyaltyBonus"]["customerBenefit"] == 0
    assert b["byKey"]["loyaltyBonus"]["customerBenefit"] == 10000
    assert a["totals"]["dealerFundedBenefit"] == b["totals"]["dealerFundedBenefit"] == 10000


def test_income_breakdown_matches_allocation_funded_cost():
    snap = {"model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
            "loyaltyBonus": 10000, "schemeAllocationExplicit": True,
            "schemeAllocation": {"loyaltyBonus": 0, "insuranceBenefit": 15000},
            "schemeComponentsUsed": {"loyaltyBonus": True, "insuranceBenefit": True}}
    income = ce.compute_scheme_income_breakdown(snap, turbo_rows())
    assert income["dealerFundedBenefit"] == 5000
    assert income["dealerCostPassed"] == 5000
    assert income["retainedIncomeTotal"] == 10000


# ================================================================== API / E2E
@pytest_asyncio.fixture
async def client(monkeypatch):
    sync_calls = []

    async def capture_sync(entity, doc, *, entity_id=""):
        sync_calls.append({"entity": entity, "doc": dict(doc)})
        return {"ok": True, "skipped": True, "reason": "test-capture"}

    async def turbo_scheme_rows():
        return turbo_rows()

    monkeypatch.setattr(server, "sheet_sync", capture_sync)
    monkeypatch.setattr(server, "get_scheme_rows", turbo_scheme_rows)
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        c.sync_calls = sync_calls
        yield c


async def turbo_booked(c, mobile, allocation=None, deliver=False, insurance_payout=None):
    r = await c.post("/api/leads", json={
        "customerName": "FUNDED TEST", "mobile": mobile, "interestedModel": MODEL,
        "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    await c.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": EX_SHOWROOM, "rto": 10000, "insuranceAmount": 19000})
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    await c.put(f"/api/leads/{lid}/scheme",
                json={"loyaltyBonus": 10000, "benefitMode": "No Benefit",
                      "schemeDate": "2026-08-09"})
    if allocation is not None:
        r = await c.put(f"/api/leads/{lid}/scheme-allocation",
                        json={"allocation": allocation})
        assert r.status_code == 200, r.text
    if deliver:
        lead = await server.db.leads.find_one({"leadId": lid})
        await c.post(f"/api/leads/{lid}/payments",
                     json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
        await c.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
            "insuranceAgentId": "IA26AGENT1", "insurerName": "ICICI Lombard", "invoiceNumber": f"INV-{mobile[-4:]}",
            "chassisNumber": f"CH-{mobile[-4:]}", "numberPlate": f"RJ14-{mobile[-4:]}",
            "delivered": "Yes"})
        if insurance_payout is not None:
            await server.db.insurance.update_one(
                {"leadId": lid}, {"$set": {"expectedPayout": insurance_payout}})
            await server.recompute_lead(lid)
    return lid


@pytest.mark.asyncio
async def test5_raghav_exact_case(client):
    """Raghav: both fully passed, payout ₹9,310 → total earnings ₹27,246.50 (displays ₹27,247)."""
    lid = await turbo_booked(
        client, "9888820005",
        allocation={"loyaltyBonus": 10000, "insuranceBenefit": 20000},
        deliver=True, insurance_payout=9310)
    lead = await server.db.leads.find_one({"leadId": lid})
    margin = lead["dealerMarginNetExGst"]
    assert abs(margin - 27936.5) < 0.01
    assert lead["dealerSchemeRetained"] == 0
    assert lead["dealerFundedBenefit"] == 10000
    assert lead["dealerInsuranceIncome"] == 9310
    assert lead["schemeCustomerBenefitTotal"] == 30000
    assert lead["schemeOemClaimableTotal"] == 20000
    expected = ce.round2(margin + 0 + 9310 - 10000)
    assert lead["dealerTotalEarnings"] == expected
    assert expected == 27246.5
    # UI inr() uses Intl half-up → ₹27,247 (Python round() is bankers).
    assert f"{expected:,.1f}" == "27,246.5"

    de = (await client.get("/api/dealer-earnings")).json()
    row = next(r for r in de["rows"] if r["leadId"] == lid)
    assert row["dealerFundedBenefit"] == 10000
    assert row["totalDealerEarnings"] == expected
    assert row["dealerSchemeRetained"] == 0


@pytest.mark.asyncio
async def test10_save_twice_idempotent(client):
    lid = await turbo_booked(
        client, "9888820010",
        allocation={"loyaltyBonus": 10000, "insuranceBenefit": 20000})
    before = await server.db.leads.find_one({"leadId": lid})
    for _ in range(2):
        r = await client.put(f"/api/leads/{lid}/scheme-allocation",
                             json={"allocation": {"loyaltyBonus": 10000, "insuranceBenefit": 20000}})
        assert r.status_code == 200
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before["customerPayable"]
    assert after["dealerFundedBenefit"] == 10000
    assert after["dealerTotalEarnings"] == before["dealerTotalEarnings"]
    assert after["dealerSchemeRetained"] == 0

    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    keys = [c["componentKey"] for c in claims]
    assert sorted(keys) == ["insuranceBenefit", "loyaltyBonus"]
    assert len(keys) == len(set(keys))

    de_n = await server.db.dealer_earnings.count_documents({"leadId": lid})
    assert de_n == 1


@pytest.mark.asyncio
async def test11_lead_and_earnings_insurance_benefit_persist(client):
    """Insurance Benefit CB must land on Mongo + Dealer Earnings sheet payload,
    independently from Loyalty Bonus."""
    client.sync_calls.clear()
    lid = await turbo_booked(
        client, "9888820011",
        allocation={"loyaltyBonus": 10000, "insuranceBenefit": 20000})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["loyaltyBonus"] == 10000
    assert lead["insuranceBenefit"] == 20000
    assert lead["customerInsuranceBenefitPassed"] == 20000
    assert lead["dealerFundedBenefit"] == 10000

    de_syncs = [s for s in client.sync_calls if s["entity"] == "dealer_earnings"]
    assert de_syncs, "dealer_earnings sheet_sync never fired"
    last_de = de_syncs[-1]["doc"]
    assert last_de["customerInsuranceBenefitPassed"] == 20000
    assert last_de["dealerFundedBenefit"] == 10000
    assert last_de["dealerSchemeRetained"] == 0

    lead_syncs = [s for s in client.sync_calls if s["entity"] == "leads"]
    assert lead_syncs
    # Loyalty + Insurance Benefit are independently present on the Lead Register payload.
    assert lead_syncs[-1]["doc"].get("loyaltyBonus") == 10000
    assert lead_syncs[-1]["doc"].get("insuranceBenefit") == 20000


@pytest.mark.asyncio
async def test12_claim_register_separate_rows(client):
    lid = await turbo_booked(
        client, "9888820012",
        allocation={"loyaltyBonus": 10000, "insuranceBenefit": 20000})
    client.sync_calls.clear()
    await server.recompute_lead(lid)

    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert set(claims) == {"loyaltyBonus", "insuranceBenefit"}
    assert claims["loyaltyBonus"]["eligibleClaim"] == 10000
    assert claims["insuranceBenefit"]["eligibleClaim"] == 10000

    claim_syncs = [s for s in client.sync_calls if s["entity"] == "claims"]
    keys = sorted({s["doc"]["componentKey"] for s in claim_syncs})
    assert keys == ["insuranceBenefit", "loyaltyBonus"]
    by_key = {s["doc"]["componentKey"]: s["doc"] for s in claim_syncs}
    assert by_key["loyaltyBonus"]["component"] == "Loyalty"
    assert by_key["insuranceBenefit"]["component"] == "Insurance Benefit"
    assert by_key["loyaltyBonus"]["claimAmount"] == 10000
    assert by_key["insuranceBenefit"]["claimAmount"] == 10000


@pytest.mark.asyncio
async def test13_claim_receipt_independent(client):
    lid = await turbo_booked(
        client, "9888820013",
        allocation={"loyaltyBonus": 10000, "insuranceBenefit": 20000})
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text
    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert claims["loyaltyBonus"]["claimStatus"] == "Received"
    assert claims["insuranceBenefit"]["claimStatus"] == "Pending"
    assert claims["insuranceBenefit"]["receivedAmount"] == 0


@pytest.mark.asyncio
async def test14_insurance_payout_separate_from_benefit(client):
    lid = await turbo_booked(
        client, "9888820014",
        allocation={"loyaltyBonus": 0, "insuranceBenefit": 20000},
        deliver=True, insurance_payout=9310)
    lead = await server.db.leads.find_one({"leadId": lid})
    entry = await server.db.insurance.find_one({"leadId": lid})
    assert lead["dealerInsuranceIncome"] == 9310
    assert lead["customerInsuranceBenefitPassed"] == 20000
    assert lead["dealerFundedBenefit"] == 10000
    assert entry["expectedPayout"] == 9310
    # Payout must never appear as an OEM scheme claim component.
    claim_keys = {c["componentKey"] for c in (await client.get("/api/claims")).json()
                  if c["leadId"] == lid}
    assert "insurancePayout" not in claim_keys
    assert "insuranceBenefit" in claim_keys
    # Net of the two insurance concepts: +9310 − 10000 = −690
    assert ce.round2(lead["dealerInsuranceIncome"] - lead["dealerFundedBenefit"]) == -690


@pytest.mark.asyncio
async def test15_historical_lead_without_v2_not_invented(client):
    lid = await turbo_booked(client, "9888820015", allocation=None)
    # Strip V2/explicit markers to simulate a historical lead.
    await server.db.leads.update_one({"leadId": lid}, {"$unset": {
        "schemeAllocationV2": "", "schemeAllocationExplicit": "", "schemeAllocation": "",
        "benefitPassedBreakup": "", "schemeComponentsUsed": ""},
        "$set": {"benefitMode": "No Benefit", "customerInsuranceBenefitPassed": 0}})
    before = await server.db.leads.find_one({"leadId": lid})
    payable_before = before["customerPayable"]
    for _ in range(3):
        await server.recompute_lead(lid)
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == payable_before
    assert after["dealerFundedBenefit"] == 0
    # Must not invent Insurance Benefit CB on a historical non-V2 lead.
    assert ce.num(after.get("insuranceBenefit")) == 0
    assert ce.num(after.get("customerInsuranceBenefitPassed")) == 0


@pytest.mark.asyncio
async def test_partial_insurance_earnings_deducts_exactly_5000(client):
    lid = await turbo_booked(
        client, "9888820006",
        allocation={"loyaltyBonus": 0, "insuranceBenefit": 15000})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["dealerFundedBenefit"] == 5000
    # Loyalty unused keeps ₹10k OEM; insurance CB ₹15k keeps ₹0 company (₹5k dealer-funded).
    assert lead["dealerSchemeRetained"] == 10000
    assert lead["dealerTotalEarnings"] == ce.round2(
        lead["dealerMarginNetExGst"] + 10000 - 5000
        + lead["oemExtraSupportRetained"] + lead["extraDealerIncomeTotal"]
        + lead["dealerInsuranceIncome"])
