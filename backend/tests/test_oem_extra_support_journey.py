"""OEM Extra Support — full financial journey.

Received = amount from OEM against the lead → ALWAYS the OEM claim amount.
Passed   = portion given to customer from Received → reduces payable, not earnings.
Retained = Received − Passed → dealer earnings (full Received when Passed = 0).
Additional (Dealer) stays a separate dealer-funded discount and is not tested here.
"""
import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "oem_extra_support_journey")
os.environ.setdefault("JWT_SECRET", "oem-extra-support-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import gsheets  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Turbo Max", "Maxx (PV)"
TURBO = [
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-01", "effectiveTo": "2026-08-31",
     "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
     "dealerShare": 0, "companyShare": 10000, "totalBenefit": 10000, "status": "Active"},
]


def test_compute_oem_extra_support_math():
    full = ce.compute_oem_extra_support({
        "oemExtraSupportReceived": 7000, "oemExtraSupportPassed": 0})
    assert full["oemClaimable"] == 7000
    assert full["oemExtraSupportRetained"] == 7000
    assert full["customerBenefit"] == 0

    split = ce.compute_oem_extra_support({
        "oemExtraSupportReceived": 7000, "oemExtraSupportPassed": 2500})
    assert split["oemClaimable"] == 7000  # full Received is always the claim
    assert split["oemExtraSupportPassed"] == 2500
    assert split["oemExtraSupportRetained"] == 4500

    clamped = ce.compute_oem_extra_support({
        "oemExtraSupportReceived": 5000, "oemExtraSupportPassed": 9000})
    assert clamped["oemExtraSupportPassed"] == 5000
    assert clamped["oemExtraSupportRetained"] == 0
    assert clamped["oemClaimable"] == 5000


def test_passed_reduces_payable_and_claim_shares_include_full_received():
    snap = {
        "exShowroom": 400000, "rto": 0, "insurance": 0,
        "oemExtraSupportReceived": 7000, "oemExtraSupportPassed": 2000,
        "loyaltyBonus": 10000, "schemeAllocationExplicit": True, "schemeAllocationV2": True,
        "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": {"loyaltyBonus": 0},
        "schemeComponentsUsed": {"loyaltyBonus": True},
        "model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
    }
    totals = ce.compute_commercial_totals(snap, TURBO)
    # Payable reduced by Passed only (not by full Received).
    base = ce.compute_commercial_totals({**snap, "oemExtraSupportPassed": 0}, TURBO)
    assert totals["customerPayable"] == ce.round2(base["customerPayable"] - 2000)
    assert totals["oemExtraSupportRetained"] == 5000

    shares = ce.compute_scheme_claim_shares(snap, TURBO)
    assert shares["displayByComponent"]["oemExtraSupport"] == 7000
    assert shares["eligibleByComponent"]["oemExtraSupport"] == 7000
    # Loyalty Use=Yes CB=0 → claim 10000 + OEM Extra 7000
    assert shares["eligibleTotal"] == 17000


def test_gsheet_maps_oem_extra_on_related_tabs():
    assert "oem_extra_support" in gsheets.SYNC_MAP
    lead_fields = gsheets.SYNC_MAP["leads"][2]
    for f in ("oemExtraSupportReceived", "oemExtraSupportPassed", "oemExtraSupportRetained"):
        assert f in lead_fields
        assert f in gsheets.SYNC_MAP["dealer_earnings"][2]
        assert f in gsheets.SYNC_MAP["oem_extra_support"][2]
    assert gsheets.SYNC_MAP["oem_extra_support"][0] == "OEM Extra Support Register"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    # Ensure Turbo August loyalty exists without wiping other masters other suites use.
    for row in TURBO:
        await server.db.scheme_master.update_one(
            {"componentKey": row["componentKey"], "schemeMonth": row["schemeMonth"],
             "model": row["model"]},
            {"$set": row}, upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked_lead(c, mobile="9777712345"):
    r = await c.post("/api/leads", json={
        "customerName": "OEM Extra Test", "mobile": mobile,
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json().get("priceStructure") or {
        "exShowroom": 435000, "rto": 10000, "insuranceAmount": 10000}
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    return lid


@pytest.mark.asyncio
async def test_scheme_save_wires_claim_earnings_and_payable(client):
    lid = await _booked_lead(client)
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 2000,
        "additionalDiscount": 4500,  # dealer-funded — separate; must not change OEM claim
        "loyaltyBonus": 10000,
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": True}),
        "consumerDiscount": 0, "exchangeBonus": 0, "referralBonus": 0, "dsaDiscount": 0,
    })
    assert r.status_code == 200, r.text
    lead = r.json()

    assert lead["oemExtraSupportReceived"] == 7000
    assert lead["oemExtraSupportPassed"] == 2000
    assert lead["oemExtraSupportRetained"] == 5000
    # Full Received is in company outstanding / OEM claimable.
    assert lead["companyOutstanding"] >= 7000
    assert lead["oemClaimCompanyShare"] >= 7000
    # Retained is inside dealer earnings.
    assert lead["dealerTotalEarnings"] >= 5000
    assert lead["oemExtraSupportRetained"] == 5000

    claims = (await client.get("/api/claims")).json()
    oem_rows = [c for c in claims
                if c.get("leadId") == lid and c.get("componentKey") == "oemExtraSupport"]
    assert len(oem_rows) == 1
    assert oem_rows[0]["claimAmount"] == 7000
    assert oem_rows[0]["eligibleClaim"] == 7000
    assert oem_rows[0]["component"] == "OEM Extra Support"

    # Passed=0 → full Received retained.
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 0,
        "additionalDiscount": 4500,
        "loyaltyBonus": 10000,
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": True}),
        "consumerDiscount": 0, "exchangeBonus": 0, "referralBonus": 0, "dsaDiscount": 0,
    })
    assert r.status_code == 200, r.text
    lead2 = r.json()
    assert lead2["oemExtraSupportRetained"] == 7000
    claims2 = (await client.get("/api/claims")).json()
    oem2 = [c for c in claims2
            if c.get("leadId") == lid and c.get("componentKey") == "oemExtraSupport"]
    assert oem2[0]["claimAmount"] == 7000


@pytest.mark.asyncio
async def test_passed_above_received_is_clamped(client):
    lid = await _booked_lead(client, mobile="9777712346")
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "oemExtraSupportReceived": 5000,
        "oemExtraSupportPassed": 9000,
        "additionalDiscount": 0,
        "benefitPassedBreakup": json.dumps({}),
        "schemeComponentsUsed": json.dumps({}),
        "consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0,
        "referralBonus": 0, "dsaDiscount": 0,
    })
    assert r.status_code == 200, r.text
    lead = r.json()
    assert lead["oemExtraSupportPassed"] == 5000
    assert lead["oemExtraSupportRetained"] == 0
    assert lead["oemClaimCompanyShare"] >= 5000
