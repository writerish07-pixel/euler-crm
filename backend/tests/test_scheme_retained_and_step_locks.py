"""Company-kept scheme retained + staff step locks + owner cascade."""
import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scheme_retained_step_locks")
os.environ.setdefault("JWT_SECRET", "scheme-retained-step-locks")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

TURBO = [
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
     "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
     "dealerShare": 0, "companyShare": 10000, "totalBenefit": 10000, "status": "Active"},
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
     "model": "Turbo", "variant": "", "componentKey": "insuranceBenefit",
     "component": "Insurance Benefit", "dealerShare": 10000, "companyShare": 10000,
     "totalBenefit": 20000, "status": "Active"},
]
MODEL, VARIANT = "Turbo Max", "Maxx (PV)"


def test_user_bug_loyalty_passed_insurance_unused_retains_oem_share_only():
    """Screenshot case: loyalty → customer, insurance CB=0 → retained ₹10k not ₹20k."""
    snap = {
        "model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
        "loyaltyBonus": 10000, "schemeAllocationExplicit": True, "schemeAllocationV2": True,
        "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": {"loyaltyBonus": 10000, "insuranceBenefit": 0},
        "schemeComponentsUsed": {"loyaltyBonus": True, "insuranceBenefit": True},
    }
    alloc = ce.compute_scheme_allocation(snap, TURBO)
    by = {c["key"]: c for c in alloc["components"]}
    assert by["loyaltyBonus"]["dealerRetained"] == 0
    assert by["insuranceBenefit"]["dealerRetained"] == 10000
    assert by["insuranceBenefit"]["oemClaimable"] == 10000
    assert by["insuranceBenefit"]["dealerFundedBenefit"] == 0
    assert alloc["totals"]["dealerRetained"] == 10000
    assert alloc["totals"]["oemClaimable"] == 20000


def test_unused_dealer_share_is_never_income_across_cb_ladder():
    for cb, retained, funded in (
        (0, 10000, 0),
        (5000, 5000, 0),
        (10000, 0, 0),
        (15000, 0, 5000),
        (20000, 0, 10000),
    ):
        snap = {
            "model": MODEL, "variant": VARIANT, "bookingDate": "2026-08-09",
            "loyaltyBonus": 0, "schemeAllocationExplicit": True,
            "benefitPassedBreakup": {"loyaltyBonus": 0, "insuranceBenefit": cb},
        }
        ins = ce.compute_scheme_allocation(snap, TURBO)["byKey"]["insuranceBenefit"]
        assert ins["dealerRetained"] == retained, cb
        assert ins["dealerFundedBenefit"] == funded, cb
        assert ins["oemClaimable"] == 10000


@pytest_asyncio.fixture
async def client(monkeypatch):
    async def turbo_rows():
        return TURBO

    monkeypatch.setattr(server, "get_scheme_rows", turbo_rows)
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(c, email):
    r = await c.post("/api/auth/login", json={"email": email, "password": "euler@123"})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})


async def _lead(c, mobile):
    r = await c.post("/api/leads", json={
        "customerName": "Step Lock", "mobile": mobile,
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    return r.json()["leadId"]


@pytest.mark.asyncio
async def test_staff_cannot_reedit_price_or_scheme(client):
    await _login(client, "executive@euler.com")
    lid = await _lead(client, "9777700001")
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    r = await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    assert r.status_code == 200, r.text
    # Second price save by staff → 403
    r = await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    assert r.status_code == 403
    assert "owner" in r.text.lower()

    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": 10000, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 10000, "insuranceBenefit": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": True, "insuranceBenefit": True}),
    })
    assert r.status_code == 200, r.text
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": 10000, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 0, "insuranceBenefit": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": False, "insuranceBenefit": False}),
    })
    assert r.status_code == 403

    # Owner can still re-edit
    await _login(client, "owner@euler.com")
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": 10000, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 10000, "insuranceBenefit": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": True, "insuranceBenefit": True}),
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["dealerSchemeRetained"] == 10000


@pytest.mark.asyncio
async def test_owner_model_change_refreshes_exshowroom_and_realigns_scheme(client):
    await _login(client, "owner@euler.com")
    lid = await _lead(client, "9777700002")
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": 10000, "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 10000, "insuranceBenefit": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": True, "insuranceBenefit": True}),
    })
    before = await server.db.leads.find_one({"leadId": lid})
    assert before["dealerSchemeRetained"] == 10000

    # Pick another active price-master variant if available; else re-save same vehicle.
    variants = (await client.get("/api/price-master/variants", params={"model": MODEL})).json()
    other = next((v for v in variants if v.get("variant") and v["variant"] != VARIANT), None)
    new_variant = other["variant"] if other else VARIANT
    r = await client.put(f"/api/leads/{lid}", json={
        "interestedModel": MODEL, "variant": new_variant,
        "customerName": "Step Lock",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    if preview.get("found"):
        assert after["exShowroom"] == preview["priceStructure"]["exShowroom"]
    # Actions expose completion flags for the UI
    acts = server.lead_actions(after)
    assert acts["priceCompleted"] is True
    assert acts["schemeCompleted"] is True


@pytest.mark.asyncio
async def test_booking_autofill_does_not_lock_price_for_staff(client):
    await _login(client, "executive@euler.com")
    lid = await _lead(client, "9777700003")
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("exShowroom")) > 0
    assert lead.get("priceStructureSaved") is False
    assert server.lead_actions(lead)["priceCompleted"] is False
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    r = await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    assert r.status_code == 200, r.text
