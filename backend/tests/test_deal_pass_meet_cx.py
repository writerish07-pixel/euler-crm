"""Cx Demand is the deal. Additional fills the leftover after scheme."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "deal_pass_meet_cx_v1")
os.environ.setdefault("JWT_SECRET", "deal-pass-meet-cx-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import sept_2026_schemes as sept  # noqa: E402
import server  # noqa: E402

PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await sept.ensure_sept_2026_schemes(server.db)
    await server.db.leads.delete_many({})
    await server.db.price_master.delete_many({"priceId": "PM-KAILASH-STORM"})
    await server.db.price_master.insert_one({
        "priceId": "PM-KAILASH-STORM",
        "model": "Storm",
        "variant": "Storm TR (PV) Reg C7 Deal",
        "exShowroom": 965000,
        "rto": 5500,
        "insurance": 19000,
        "handlingCharges": 0,
        "status": "active",
    })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_derive_overshoot_insurance_zeroes_extra_passed():
    """GVC 9,89,500 − deal 9,60,000 = 29,500. Pass insurance 30,000 → Extra Passed 0."""
    out = ce.derive_deal_customer_pass(989500, 960000, 30000, 15000)
    assert out["applied"] is True
    assert out["oemExtraSupportPassed"] == 0
    assert out["additionalDiscount"] == 0
    assert out["extraFromCustomer"] == 500


def test_derive_leftover_after_scheme_uses_additional_only():
    out = ce.derive_deal_customer_pass(1000500, 960000, 30000, 15000)
    assert out["oemExtraSupportPassed"] == 0
    assert out["additionalDiscount"] == 10500
    assert out["extraFromCustomer"] == 0
    short = ce.derive_deal_customer_pass(989500, 960000, 0, 15000)
    assert short["oemExtraSupportPassed"] == 0
    assert short["additionalDiscount"] == 29500
    assert short["extraFromCustomer"] == 0


def test_scheme_passed_excludes_additional_keeps_dealer_share_components():
    alloc = {
        "components": [
            {"key": "insuranceBenefit", "customerBenefit": 30000},
            {"key": "loyaltyBonus", "customerBenefit": 0},
            {"key": "additionalDiscount", "customerBenefit": 14500},
        ],
    }
    assert ce.scheme_customer_benefit_ex_additional(alloc) == 30000


@pytest.mark.asyncio
async def test_create_lead_meets_cx_demand_without_passing_extra(client):
    created = await client.post("/api/leads", json={
        "customerName": "Kailash Deal Pass",
        "mobile": "9950993703",
        "interestedModel": "Storm",
        "variant": "Storm TR (PV) Reg C7 Deal",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "createdDate": "2026-09-23",
        "budget": 960000,
        "oemExtraSupportReceived": 15000,
        "schemePassOn": {"insuranceBenefit": True, "loyaltyBonus": False},
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead.get("useDealPrice") is True
    assert ce.num(lead.get("cxDemand")) == 960000
    assert ce.num(lead.get("grossVehicleCost")) == 989500
    # TL collects the deal. ₹500 scheme overshoot is dealer margin, not a cheaper price.
    assert ce.num(lead.get("customerPayable")) == 960000
    assert ce.num(lead.get("customerOutstanding")) == 960000
    assert ce.num(lead.get("oemExtraSupportReceived")) == 15000
    assert ce.num(lead.get("oemExtraSupportPassed")) == 0
    assert ce.num(lead.get("additionalDiscount")) == 0
    assert ce.num(lead.get("extraIncomeFromCustomer")) == 500
    assert ce.num(lead.get("dealerMarginNetExGst")) == ce.round2(
        ce.compute_dealer_margin(server.lead_to_snapshot(lead))["marginNetExGst"] + 500)
    r360 = await client.get(f"/api/leads/{lid}/360")
    assert r360.status_code == 200, r360.text
    body = r360.json()
    assert ce.num(body["lead"]["cxDemand"]) == 960000
    assert ce.num(body["lead"]["customerPayable"]) == 960000
    assert ce.num(body["lead"]["customerOutstanding"]) == 960000
    assert ce.num(body["lead"]["extraIncomeFromCustomer"]) == 500
    assert ce.num(body["commercials"]["grossVehicleCost"]) == 989500


@pytest.mark.asyncio
async def test_create_lead_leftover_goes_to_additional_not_extra_passed(client):
    created = await client.post("/api/leads", json={
        "customerName": "Kailash Additional Only",
        "mobile": "9950993704",
        "interestedModel": "Storm",
        "variant": "Storm TR (PV) Reg C7 Deal",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "createdDate": "2026-09-23",
        "budget": 960000,
        "oemExtraSupportReceived": 15000,
        "schemePassOn": {},
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 989500
    assert ce.num(lead.get("customerPayable")) == 960000
    assert ce.num(lead.get("oemExtraSupportReceived")) == 15000
    assert ce.num(lead.get("oemExtraSupportPassed")) == 0
    assert ce.num(lead.get("oemExtraSupportRetained")) == 15000
    assert ce.num(lead.get("additionalDiscount")) == 29500


def test_pack_unit_lock_recovers_deal_when_rto_insurance_cut():
    """Messenger SCS: Additional 59,500 was vs list 5,500+19,000. Cutting those
    charges must keep Cx Demand ~7,90,000 and shrink dealer Additional."""
    snap = {
        "model": "Turbo Max", "variant": "Maxx (PV)",
        "exShowroom": 825000, "registrationRto": 2200, "insurance": 17874,
        "accessories": 0, "fastag": 0, "handlingCharges": 0, "trc": 0,
        "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
        "additionalDiscount": 59500,
    }
    lock = ce.pack_unit_locked_cx_demand(snap, {"additionalDiscount": 59500})
    assert lock == 790000
    derived = ce.derive_deal_customer_pass(ce._gvc_from_charges(snap), lock, 0, 48000)
    assert derived["applied"] is True
    assert derived["additionalDiscount"] == 55074
    assert derived["oemExtraSupportPassed"] == 0


def test_pack_unit_lock_ignores_pack_total_cx_on_unit():
    snap = {
        "model": "Turbo Max", "variant": "Maxx (PV)",
        "exShowroom": 825000, "registrationRto": 5500, "insurance": 19000,
        "accessories": 0, "fastag": 0, "handlingCharges": 0, "trc": 0,
        "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
        "additionalDiscount": 59500, "cxDemand": 9645210,
    }
    unit = {"additionalDiscount": 59500, "cxDemand": 9645210, "exShowroom": 825000}
    assert ce.pack_unit_cx_is_pack_rollup(9645210, snap, unit) is True
    assert ce.pack_unit_locked_cx_demand(snap, unit) == 0
    own = {"additionalDiscount": 59500, "cxDemand": 790000, "exShowroom": 825000}
    assert ce.pack_unit_locked_cx_demand(snap, own) == 790000


def test_additional_discount_has_no_maximum():
    rules = ce.get_scheme_offer_rules_for_vehicle("Turbo Max", "Maxx (PV)", "2026-09-15", [])
    add = (rules.get("rules") or {}).get("additionalDiscount") or {}
    assert add.get("allowed") is True
    assert add.get("maxAmount") in (None, 0)
    assert ce.validate_scheme_offers(
        "Turbo Max", "Maxx (PV)", "2026-09-15", {"additionalDiscount": 59500}, []) == []
    assert ce.validate_scheme_offers(
        "Turbo Max", "Maxx (PV)", "2026-09-15", {"additionalDiscount": 200000}, []) == []
    neg = ce.validate_scheme_offers(
        "Turbo Max", "Maxx (PV)", "2026-09-15", {"additionalDiscount": -1}, [])
    assert neg


def test_pack_unit_lock_skips_when_additional_is_smaller_than_the_charge_cut():
    """Per-unit pack test: RTO 10,000 / insurance 0 / Additional 5,000 must stay."""
    snap = {
        "model": "Turbo Max", "variant": "Unit A",
        "exShowroom": 500000, "registrationRto": 10000, "insurance": 0,
        "accessories": 0, "fastag": 0, "handlingCharges": 0, "trc": 0,
        "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
        "additionalDiscount": 5000,
    }
    assert ce.pack_unit_locked_cx_demand(snap, {"additionalDiscount": 5000}) == 0
    storm = {
        "model": "Storm", "variant": "Unit B",
        "exShowroom": 700000, "registrationRto": 20000, "insurance": 0,
        "accessories": 0, "fastag": 0, "handlingCharges": 0, "trc": 0,
        "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
        "additionalDiscount": 25000,
    }
    assert ce.pack_unit_locked_cx_demand(storm, {"additionalDiscount": 25000}) == 0


@pytest.mark.asyncio
async def test_pack_rto_insurance_cut_shrinks_additional_not_payable(client):
    """Same-order pack: cheaper RTO/insurance reduces Additional (Dealer).

    Mirrors messenger scs LD26000554 unit 1: Additional was quoted on list
    5,500 + 19,000; editing those lines must not cheapen Cx Demand.
    """
    lid = "LD-PACK-RTO-INS"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.price_master.delete_many({"priceId": "PM-PACK-RTO-INS"})
    await server.db.price_master.insert_one({
        "priceId": "PM-PACK-RTO-INS",
        "model": "Turbo Max", "variant": "Maxx Pack RTO",
        "exShowroom": 825000, "rto": 5500, "insurance": 19000,
        "handlingCharges": 0, "status": "active",
    })
    unit = {
        "model": "Turbo Max", "variant": "Maxx Pack RTO",
        "exShowroom": 825000, "rto": 5500, "insuranceAmount": 19000,
        "additionalDiscount": 25000, "priceStructureSaved": True,
        "schemeAllocationExplicit": True, "schemeAllocationV2": True,
        "benefitPassedBreakup": "{}", "schemeComponentsUsed": "{}",
    }
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "messenger scs rto", "mobile": "8980143566",
        "interestedModel": "Turbo Max", "variant": "Maxx Pack RTO",
        "executive": "Amit", "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-15", "sameOrderMultiUnit": True,
        "priceStructureSaved": True, "schemeAllocationExplicit": True,
        "schemeAllocationV2": True, "additionalDiscount": 25000,
        "exShowroom": 825000, "rto": 5500, "insuranceAmount": 19000,
        "units": [{**unit, "sno": 1}, {**unit, "sno": 2}],
    })
    cut = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 825000, "rto": 2200, "insuranceAmount": 17874, "unitSno": 1,
    })
    assert cut.status_code == 200, cut.text
    after = await server.db.leads.find_one({"leadId": lid})
    u1 = (after.get("units") or [{}])[0]
    u2 = (after.get("units") or [{}, {}])[1]
    # Bug was 8,20,074 (GVC after the cut minus the old Additional).
    assert ce.num(u1.get("customerPayable")) == 824500
    assert ce.num(u1.get("additionalDiscount")) == 20574
    assert ce.num(u2.get("additionalDiscount")) == 25000
    assert ce.num(u1.get("customerPayable")) != 820074


def test_recut_cx_demand_round_trips_derive_additional():
    gvc, scheme, addl = 989500, 0, 29500
    recut = ce.recut_cx_demand_for_additional(gvc, scheme, addl)
    assert recut["cxDemand"] == 960000
    assert recut["additionalDiscount"] == 29500
    derived = ce.derive_deal_customer_pass(gvc, recut["cxDemand"], scheme, 0)
    assert derived["applied"] is True
    assert derived["additionalDiscount"] == 29500
    bigger = ce.recut_cx_demand_for_additional(gvc, scheme, 50000)
    assert bigger["cxDemand"] == 939500
    assert ce.derive_deal_customer_pass(
        gvc, bigger["cxDemand"], scheme, 0)["additionalDiscount"] == 50000
    capped = ce.recut_cx_demand_for_additional(gvc, 0, 5_000_000)
    assert capped["cxDemand"] == 0
    assert capped["additionalDiscount"] == 989500
    assert capped["useDealPrice"] is False


@pytest.mark.asyncio
async def test_owner_additional_edit_recuts_cx_demand_and_sticks(client):
    created = await client.post("/api/leads", json={
        "customerName": "Owner Additional Edit",
        "mobile": "9950993799",
        "interestedModel": "Storm",
        "variant": "Storm TR (PV) Reg C7 Deal",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "createdDate": "2026-09-23",
        "budget": 960000,
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("additionalDiscount")) == 29500
    assert ce.num(lead.get("customerPayable")) == 960000

    edited = await client.put(f"/api/leads/{lid}/owner-field", json={
        "field": "additionalDiscount", "value": 40000,
    })
    assert edited.status_code == 200, edited.text
    body = edited.json()
    assert ce.num(body["additionalDiscount"]) == 40000
    assert ce.num(body["cxDemand"]) == 949500
    assert ce.num(body["customerPayable"]) == 949500

    scheme = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "additionalDiscount": 10000,
        "benefitPassedBreakup": "{}",
        "schemeComponentsUsed": "{}",
    })
    assert scheme.status_code == 200, scheme.text
    again = scheme.json()
    assert ce.num(again["additionalDiscount"]) == 10000
    assert ce.num(again["cxDemand"]) == 979500
    assert ce.num(again["customerPayable"]) == 979500

    keep = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "additionalDiscount": 10000,
        "benefitPassedBreakup": "{}",
        "schemeComponentsUsed": "{}",
    })
    assert keep.status_code == 200, keep.text
    assert ce.num(keep.json()["additionalDiscount"]) == 10000
    assert ce.num(keep.json()["cxDemand"]) == 979500
