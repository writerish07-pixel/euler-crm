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

import auth as authmod  # noqa: E402
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
    # Agreed price sits above today's GVC after a large RTO / insurance cut.
    # That is this unit's deal, not the pack total.
    reduced = {
        "model": "Turbo Max", "variant": "Maxx (PV)",
        "exShowroom": 785000, "registrationRto": 0, "insurance": 10000,
        "accessories": 0, "fastag": 0, "handlingCharges": 0, "trc": 0,
        "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
    }
    agreed = {"additionalDiscount": 4500, "cxDemand": 805000, "exShowroom": 785000}
    assert ce.pack_unit_cx_is_pack_rollup(805000, reduced, agreed) is False
    assert ce.pack_unit_locked_cx_demand(reduced, agreed) == 805000


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


@pytest.mark.asyncio
async def test_confirmed_rto_cut_leaves_additional_200(client):
    """Extra discount 4,500 on list RTO 5,500 / insurance 19,000.

    RTO 2,200 and insurance 18,000 cut 4,300, so Additional becomes 200.
    Payable stays. Same on one vehicle, on pack unit 2, and when the cut
    is larger than the discount (Additional goes to 0, payable stays).
    """
    ex, list_rto, list_ins = 785000, 5500, 19000
    pay = ex + list_rto + list_ins - 4500  # 805000

    async def make(lid, *, pack=False):
        await server.db.leads.delete_many({"leadId": lid})
        await server.db.price_master.delete_many({"priceId": f"PM-{lid}"})
        await server.db.price_master.insert_one({
            "priceId": f"PM-{lid}", "model": "Turbo Max", "variant": "Maxx Confirmed",
            "exShowroom": ex, "rto": list_rto, "insurance": list_ins,
            "status": "active", "oemSyncedAt": "2026-11-01T00:00:00",
        })
        unit = {
            "model": "Turbo Max", "variant": "Maxx Confirmed",
            "exShowroom": ex, "rto": list_rto, "insuranceAmount": list_ins, "insurance": list_ins,
            "additionalDiscount": 4500, "customerPayable": pay, "cxDemand": pay,
            "useDealPrice": True, "priceStructureSaved": True,
            "schemeAllocationExplicit": True, "benefitPassedBreakup": "{}",
        }
        doc = {
            "leadId": lid, "customerName": lid, "mobile": "9000003344",
            "interestedModel": "Turbo Max", "variant": "Maxx Confirmed",
            "executive": "Amit", "accountStatus": "Active", "currentStatus": "Booked",
            "bookingDate": "2026-11-06", "priceStructureSaved": True,
            "schemeAllocationExplicit": True, "benefitPassedBreakup": "{}",
            "exShowroom": ex, "rto": list_rto, "insuranceAmount": list_ins, "insurance": list_ins,
            "additionalDiscount": 4500, "customerPayable": pay, "cxDemand": pay, "useDealPrice": True,
            "units": [dict(unit, sno=1)],
        }
        if pack:
            doc["sameOrderMultiUnit"] = True
            doc["units"] = [dict(unit, sno=1), dict(unit, sno=2)]
            doc["customerPayable"] = pay * 2
            doc["cxDemand"] = pay * 2
        await server.db.leads.insert_one(doc)

    await make("LD-CONF-RTO")
    saved = await client.put("/api/leads/LD-CONF-RTO/price-structure", json={
        "exShowroom": ex, "rto": 2200, "insuranceAmount": 18000,
    })
    assert saved.status_code == 200, saved.text
    one = saved.json()
    assert ce.num(one["customerPayable"]) == pay
    assert ce.num(one["additionalDiscount"]) == 200

    await make("LD-CONF-RTO-PACK", pack=True)
    pack_saved = await client.put("/api/leads/LD-CONF-RTO-PACK/price-structure", json={
        "exShowroom": ex, "rto": 2200, "insuranceAmount": 18000, "unitSno": 2,
    })
    assert pack_saved.status_code == 200, pack_saved.text
    after = await server.db.leads.find_one({"leadId": "LD-CONF-RTO-PACK"})
    u1, u2 = after["units"][0], after["units"][1]
    assert ce.num(u2["customerPayable"]) == pay
    assert ce.num(u2["additionalDiscount"]) == 200
    assert ce.num(u1["additionalDiscount"]) == 4500
    assert ce.num(u1["rto"]) == list_rto

    await make("LD-CONF-RTO-OF", pack=True)
    rto = await client.put("/api/leads/LD-CONF-RTO-OF/owner-field", json={
        "field": "rto", "value": 2200, "unitSno": 2,
    })
    assert rto.status_code == 200, rto.text
    ins = await client.put("/api/leads/LD-CONF-RTO-OF/owner-field", json={
        "field": "insuranceAmount", "value": 18000, "unitSno": 2,
    })
    assert ins.status_code == 200, ins.text
    edited = await server.db.leads.find_one({"leadId": "LD-CONF-RTO-OF"})
    edited_u1, edited_u2 = edited["units"][0], edited["units"][1]
    assert ce.num(edited_u2["rto"]) == 2200
    assert ce.num(edited_u2["insuranceAmount"]) == 18000
    assert ce.num(edited_u2["customerPayable"]) == pay
    assert ce.num(edited_u2["additionalDiscount"]) == 200
    assert ce.num(edited_u1["additionalDiscount"]) == 4500
    assert ce.num(edited["rto"]) == list_rto

    # Cut 14,500 is larger than Additional 4,500. Discount goes to 0.
    # Payable stays; the rest is extra from the customer, not a cheaper price.
    await make("LD-CONF-RTO-BIG", pack=True)
    big = await client.put("/api/leads/LD-CONF-RTO-BIG/price-structure", json={
        "exShowroom": ex, "rto": 0, "insuranceAmount": 10000, "unitSno": 2,
    })
    assert big.status_code == 200, big.text
    big_doc = await server.db.leads.find_one({"leadId": "LD-CONF-RTO-BIG"})
    big_u2 = big_doc["units"][1]
    assert ce.num(big_u2["customerPayable"]) == pay
    assert ce.num(big_u2["cxDemand"]) == pay
    assert ce.num(big_u2["additionalDiscount"]) == 0
    assert ce.num(big_u2.get("extraIncomeFromCustomer")) == 10000
    base_margin = ce.compute_dealer_margin({"exShowroom": ex})["marginNetExGst"]
    assert ce.num(big_doc.get("extraIncomeFromCustomer")) == 10000
    assert ce.num(big_doc.get("dealerMarginNetExGst")) == ce.round2(base_margin + 10000)


@pytest.mark.asyncio
async def test_actual_rto_and_insurance_cut_additional_not_payable(client):
    """Lower real RTO and insurance shrink Additional. Payable and excess stay."""
    lid = "LD-ACTUAL-RTO"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.payments.delete_many({"leadId": lid})
    await server.db.price_master.delete_many({"model": "Plain Haul", "variant": "Bare"})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Actual RTO", "mobile": "9001112233",
        "interestedModel": "Plain Haul", "variant": "Bare", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-01-15", "priceStructureSaved": False,
        "exShowroom": 785000, "rto": 5500, "insuranceAmount": 19000, "insurance": 19000,
        "additionalDiscount": 19500, "customerPayable": 790000,
        "cxDemand": 0, "useDealPrice": False,
    })
    await server.db.payments.insert_one({
        "leadId": lid, "amount": 790000, "paymentMode": "Cash",
        "date": "2026-10-14", "receiptNumber": "RCPT-ACTUAL-RTO",
    })
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 785000, "rto": 4500, "insuranceAmount": 15000,
    })
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert ce.num(body["customerPayable"]) == 790000
    assert ce.num(body["cxDemand"]) == 790000
    assert ce.num(body["additionalDiscount"]) == 14500
    assert ce.num(body.get("excessReceived")) == 0
    preview = await client.post("/api/commercial/compute", json={
        "exShowroom": 785000, "registrationRto": 4500, "insurance": 15000,
        "additionalDiscount": 19500, "cxDemand": 790000,
    })
    assert preview.status_code == 200, preview.text
    card = preview.json()
    assert ce.num(card["customerPayable"]) == 790000
    assert ce.num(card["additionalDiscount"]) == 14500
    assert ce.num(card.get("extraIncomeFromCustomer")) == 0


@pytest.mark.asyncio
async def test_showroom_admin_sets_real_rto_and_insurance(client):
    lid = "LD-SA-RTO"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.payments.delete_many({"leadId": lid})
    await server.db.users.delete_many({"email": {"$in": [
        "showroom.actual@euler.com", "working.tl.actual@euler.com",
    ]}})
    for email, role, name in (
        ("showroom.actual@euler.com", "tl", "Showroom Admin"),
        ("working.tl.actual@euler.com", "team_lead", "Working TL"),
    ):
        await server.db.users.insert_one({
            "userId": email, "email": email, "name": name, "role": role,
            "passwordHash": authmod.hash_password(PW), "passwordPlain": PW,
        })
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Showroom Actual", "mobile": "9001112244",
        "interestedModel": "Plain Haul", "variant": "Bare", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-10-14",
        "bookingDate": "2026-01-15",
        "exShowroom": 785000, "rto": 5500, "insuranceAmount": 19000, "insurance": 19000,
        "additionalDiscount": 19500, "customerPayable": 790000,
        "cxDemand": 790000, "useDealPrice": True,
    })
    await server.db.payments.insert_one({
        "leadId": lid, "amount": 790000, "paymentMode": "Cash",
        "date": "2026-10-14", "receiptNumber": "RCPT-SA-RTO",
    })

    async def login(email):
        r = await client.post("/api/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 200, r.text
        client.headers["Authorization"] = f"Bearer {r.json()['token']}"

    await login("working.tl.actual@euler.com")
    blocked_tl = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "rto", "value": 4500})
    assert blocked_tl.status_code == 403, blocked_tl.text

    await login("showroom.actual@euler.com")
    rto = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "rto", "value": 4500})
    assert rto.status_code == 200, rto.text
    ins = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "insuranceAmount", "value": 15000})
    assert ins.status_code == 200, ins.text
    body = ins.json()
    assert ce.num(body["rto"]) == 4500
    assert ce.num(body["insuranceAmount"]) == 15000
    assert ce.num(body["customerPayable"]) == 790000
    assert ce.num(body["additionalDiscount"]) == 14500
    assert ce.num(body.get("excessReceived")) == 0
    addl = await client.put(f"/api/leads/{lid}/owner-field", json={
        "field": "additionalDiscount", "value": 1000,
    })
    assert addl.status_code == 403

    await login("owner@euler.com")
    owner_addl = await client.put(f"/api/leads/{lid}/owner-field", json={
        "field": "additionalDiscount", "value": 10000,
    })
    assert owner_addl.status_code == 200, owner_addl.text


@pytest.mark.asyncio
async def test_lower_rto_and_insurance_do_not_reduce_gross(client):
    """Pawan Kumar: RTO 2,200 and insurance 17,955 must not pull Gross below list."""
    lid = "LD-GROSS-HELD"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Pawan Kumar", "mobile": "9571964334",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-11-06",
        "bookingDate": "2026-09-15", "priceStructureSaved": True,
        "exShowroom": 775000, "rto": 5500, "insuranceAmount": 19000, "insurance": 19000,
        "additionalDiscount": 9500, "customerPayable": 790000,
        "cxDemand": 790000, "useDealPrice": True,
    })
    await server.recompute_lead(lid)
    before = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(before.get("grossVehicleCost")) == 799500
    cut = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "rto", "value": 2200})
    assert cut.status_code == 200, cut.text
    ins = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "insuranceAmount", "value": 17955})
    assert ins.status_code == 200, ins.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("rto")) == 2200
    assert ce.num(after.get("insuranceAmount")) == 17955
    assert ce.num(after.get("grossVehicleCost")) == 799500
    assert ce.num(after.get("rtoInsuranceHeldInGross")) == 4345
    assert ce.num(after.get("customerPayable")) == 790000
    assert ce.num(after.get("additionalDiscount")) == 5155
    view = await client.get(f"/api/leads/{lid}/360")
    assert view.status_code == 200, view.text
    card = view.json()["commercials"]
    assert ce.num(card.get("grossVehicleCost")) == 799500
    assert ce.num(card.get("rtoInsuranceHeldInGross")) == 4345
    higher = await client.put(f"/api/leads/{lid}/owner-field", json={"field": "rto", "value": 6500})
    assert higher.status_code == 200, higher.text
    raised = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(raised.get("grossVehicleCost")) == 800500
    assert ce.num(raised.get("customerPayable")) == 790000
    assert ce.num(raised.get("additionalDiscount")) == 9455


@pytest.mark.asyncio
async def test_unpriced_enquiry_does_not_invent_a_gross(client):
    lid = "LD-GROSS-UNPRICED"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Unpriced", "mobile": "9571964301",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "New",
        "exShowroom": 0, "rto": 0, "insuranceAmount": 0,
        "cxDemand": 790000, "useDealPrice": True,
    })
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 0
    assert ce.num(lead.get("rtoInsuranceHeldInGross")) == 0


@pytest.mark.asyncio
async def test_gross_holds_against_the_quoted_price_not_the_family_list(client):
    lid = "LD-GROSS-QUOTE"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.price_master.delete_many({"priceId": "PM-GROSS-QUOTE"})
    await server.db.price_master.insert_one({
        "priceId": "PM-GROSS-QUOTE", "model": "Turbo Max", "variant": "Maxx (FB)",
        "exShowroom": 775000, "rto": 5500, "insurance": 24000, "status": "active",
    })
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Quoted High", "mobile": "9571964302",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-15",
        "exShowroom": 775000, "rto": 5500, "insuranceAmount": 22000, "insurance": 22000,
        "cxDemand": 790000, "useDealPrice": True,
        "dealFormat": {"rto": 5500, "insurance": 24000, "exShowroom": 775000},
    })
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 804500
    assert ce.num(lead.get("rtoInsuranceHeldInGross")) == 2000
    assert ce.num(lead.get("customerPayable")) == 790000


@pytest.mark.asyncio
async def test_custom_list_at_the_actual_premium_does_not_add_the_family_gap(client):
    lid = "LD-GROSS-CUSTOM"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.price_master.delete_many({"priceId": "PM-GROSS-CUSTOM"})
    await server.db.price_master.insert_one({
        "priceId": "PM-GROSS-CUSTOM", "model": "Turbo Max", "variant": "Gross Hold Custom",
        "exShowroom": 775000, "rto": 5500, "insurance": 15000, "status": "active",
    })
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Custom List", "mobile": "9571964303",
        "interestedModel": "Turbo Max", "variant": "Gross Hold Custom", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-15",
        "exShowroom": 775000, "rto": 5500, "insuranceAmount": 15000, "insurance": 15000,
        "cxDemand": 790000, "useDealPrice": True,
    })
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 795500
    assert ce.num(lead.get("rtoInsuranceHeldInGross")) == 0


@pytest.mark.asyncio
async def test_cancelled_deal_does_not_keep_the_gross_hold(client):
    lid = "LD-GROSS-CANCEL"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Cancelled", "mobile": "9571964304",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "executive": "Amit",
        "accountStatus": "Cancelled", "currentStatus": "Lost", "dealCancelled": True,
        "exShowroom": 775000, "rto": 2200, "insuranceAmount": 17955, "insurance": 17955,
        "cxDemand": 790000, "useDealPrice": True,
    })
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 795155
    assert ce.num(lead.get("rtoInsuranceHeldInGross")) == 0
    preview = await client.post("/api/commercial/compute", json={
        "exShowroom": 775000, "model": "Turbo Max", "variant": "Maxx (FB)",
        "registrationRto": 2200, "insurance": 17955, "cxDemand": 790000,
        "dealCancelled": True,
    })
    assert preview.status_code == 200, preview.text
    assert ce.num(preview.json().get("grossVehicleCost")) == 795155


@pytest.mark.asyncio
async def test_cancelled_pack_does_not_keep_the_gross_hold(client):
    lid = "LD-GROSS-PACK-CANCEL"
    await server.db.leads.delete_many({"leadId": lid})
    unit = {
        "model": "Turbo Max", "variant": "Maxx (FB)",
        "exShowroom": 775000, "insuranceAmount": 19000, "insurance": 19000,
        "cxDemand": 790000, "useDealPrice": True,
    }
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Pack Cancel", "mobile": "9571964305",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "executive": "Amit",
        "accountStatus": "Cancelled", "currentStatus": "Lost", "dealCancelled": True,
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "exShowroom": 775000, "rto": 2200, "insuranceAmount": 19000,
        "cxDemand": 1580000, "useDealPrice": True,
        "units": [
            {**unit, "sno": 1, "rto": 2200},
            {**unit, "sno": 2, "rto": 5500},
        ],
    })
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("grossVehicleCost")) == 1595700
    assert ce.num(lead.get("rtoInsuranceHeldInGross")) == 0


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
