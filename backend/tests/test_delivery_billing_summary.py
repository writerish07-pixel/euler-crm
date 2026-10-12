"""Delivery Billing Summary — Tally cross-check snapshot on Mark Delivered."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "delivery_billing_summary")
os.environ.setdefault("JWT_SECRET", "billing-summary-secret")
os.environ.setdefault("BILLING_GST_RATE", "5")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402


def test_build_summary_passed_discounts_only():
    lead = {
        "leadId": "LD_BILL_1",
        "customerName": "Roshan Test",
        "exShowroom": 809999,
        "rto": 5500,
        "insuranceAmount": 19000,
        "grossVehicleCost": 834499,
        "customerPayable": 825000,
        "totalReceived": 825000,
        "customerOutstanding": 0,
        "invoiceNumber": "118",
        "deliveryDate": "2026-08-08",
        "dealerSchemeRetained": 10000,
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 0,
        "oemExtraSupportRetained": 7000,
        "companyOutstanding": 17000,
        "dealerFundedBenefit": 9499,
        "schemeAllocationSummary": {
            "components": [
                {"key": "loyaltyBonus", "label": "Loyalty", "customerBenefit": 0,
                 "oemShare": 10000, "dealerFundedBenefit": 0, "used": False},
                {"key": "additionalDiscount", "label": "Additional Discount",
                 "customerBenefit": 9499, "oemShare": 0, "dealerFundedBenefit": 9499},
                {"key": "insuranceBenefit", "label": "Insurance Benefit",
                 "customerBenefit": 0, "oemShare": 10000, "dealerFundedBenefit": 0,
                 "dealerRetained": 10000},
            ],
        },
    }
    s = ce.build_delivery_billing_summary(lead)
    assert s["kind"] == "delivery_billing_summary"
    assert "Tally" in s["disclaimer"]
    assert "vehicle" in s["disclaimer"].lower()
    assert s["totals"]["customerPayable"] == 825000
    assert s["totals"]["customerBenefitPassed"] == 9499
    assert s["totals"]["tallyBillTotal"] == 800500
    assert s["totals"]["offTallyTotal"] == 24500
    assert s["totals"]["customerCollectTotal"] == 825000
    assert s["noBenefitPassed"] is False
    codes = [d["code"] for d in s["discountLines"]]
    assert "additionalDiscount" in codes
    assert "loyaltyBonus" not in codes  # Use=No / not passed
    assert any("retained" in x["label"].lower() or "claim" in x["label"].lower()
               for x in s["doNotPostInTally"])
    assert s["gstReference"]["ratePct"] == 5.0


def test_build_summary_zero_passed_has_no_discount_line():
    lead = {
        "leadId": "LD_BILL_0",
        "customerName": "No Pass",
        "exShowroom": 770000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "additionalDiscount": 0,
        "loyaltyBonus": 10000,
        "benefitPassedBreakup": {"loyaltyBonus": 0},
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 0,
        "customerPayable": 794500,
        "totalReceived": 0,
    }
    s = ce.build_delivery_billing_summary(lead)
    assert s["discountLines"] == []
    assert s["noBenefitPassed"] is True
    assert s["totals"]["tallyBillTotal"] == 770000
    assert s["totals"]["offTallyTotal"] == 24500
    assert s["totals"]["customerCollectTotal"] == 794500
    assert s["totals"]["grossVehicleCost"] == 794500


def test_build_summary_uses_lead_additional_discount_when_breakup_empty():
    lead = {
        "leadId": "LD_BILL_ADD",
        "exShowroom": 770000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "additionalDiscount": 4500,
        "benefitPassedBreakup": {"loyaltyBonus": 0},
        "customerPayable": 790000,
        "totalReceived": 790000,
    }
    s = ce.build_delivery_billing_summary(lead)
    assert s["totals"]["customerBenefitPassed"] == 4500
    assert s["totals"]["tallyBillTotal"] == 765500
    assert s["totals"]["offTallyTotal"] == 24500
    assert s["totals"]["customerCollectTotal"] == 790000
    assert any(d["code"] == "additionalDiscount" for d in s["discountLines"])


def test_build_summary_vaibhav_style_two_passed_benefits():
    lead = {
        "leadId": "LD_BILL_2",
        "customerName": "vaibhav",
        "exShowroom": 770000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "grossVehicleCost": 794500,
        "customerPayable": 764500,
        "totalReceived": 764500,
        "schemeAllocationSummary": {
            "components": [
                {"key": "loyaltyBonus", "label": "Loyalty", "customerBenefit": 10000,
                 "oemShare": 10000, "dealerFundedBenefit": 0},
                {"key": "insuranceBenefit", "label": "Insurance Benefit",
                 "customerBenefit": 20000, "oemShare": 10000, "dealerFundedBenefit": 10000},
            ],
        },
        "companyOutstanding": 20000,
    }
    s = ce.build_delivery_billing_summary(lead)
    assert s["totals"]["customerBenefitPassed"] == 30000
    assert s["totals"]["customerPayable"] == 764500
    assert s["totals"]["tallyBillTotal"] == 740000
    assert s["totals"]["offTallyTotal"] == 24500
    assert s["totals"]["customerCollectTotal"] == 764500
    assert abs(s["totals"]["grossVehicleCost"] - s["totals"]["customerBenefitPassed"]
               - s["totals"]["customerPayable"]) < 0.05


def test_tally_bill_is_vehicle_only_gst_not_on_rto_insurance():
    """Turbo deal ₹8,05,000: Tally invoice is Ex − discount; RTO/insurance off-invoice.

    House rates: RTO ₹5,500 on 3W and 4W; insurance ₹19,000 (4W) / ₹10,000 (3W).
    """
    lead = {
        "leadId": "LD_TURBO_805",
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "exShowroom": 785000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "additionalDiscount": 4500,
        "customerPayable": 805000,
        "totalReceived": 805000,
    }
    s = ce.build_delivery_billing_summary(lead)
    assert s["totals"]["tallyBillTotal"] == 780500
    assert s["totals"]["offTallyTotal"] == 24500
    assert s["totals"]["customerCollectTotal"] == 805000
    assert s["totals"]["customerPayable"] == 805000
    gst = s["gstReference"]
    assert gst["netVehicleInclGst"] == 780500
    assert abs(gst["taxableValue"] - round(780500 / 1.05, 2)) < 0.02
    assert abs((gst["cgst"] + gst["sgst"]) - (780500 - gst["taxableValue"])) < 0.02
    off = {ln["code"]: ln["amount"] for ln in s["offTallyLines"]}
    assert off == {"rto": 5500, "insurance": 19000}
    tally_codes = {ln["code"] for ln in s["tallyChargeLines"]}
    assert tally_codes == {"exShowroom"}
    assert "do not charge gst on rto" in gst["note"].lower()


def test_stored_oem_extra_passed_is_not_a_tally_discount():
    lead = {
        "leadId": "LD_BILL_NO_EXTRA_PASS",
        "exShowroom": 785000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "additionalDiscount": 4500,
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 2000,
        "customerPayable": 805000,
        "totalReceived": 805000,
    }
    s = ce.build_delivery_billing_summary(lead)
    codes = [d["code"] for d in s["discountLines"]]
    assert "oemExtraSupport" not in codes
    assert "additionalDiscount" in codes
    assert s["totals"]["tallyBillTotal"] == 780500
    assert s["totals"]["oemExtraSupportPassed"] == 0
    assert s["totals"]["oemExtraSupportRetained"] == 7000


def test_fold_existing_passed_keeps_tally_payable():
    before = {
        "leadId": "LD_BILL_FOLD",
        "exShowroom": 785000,
        "rto": 5500,
        "insuranceAmount": 19000,
        "additionalDiscount": 4500,
        "oemExtraSupportReceived": 7000,
        "oemExtraSupportPassed": 2000,
        "customerPayable": 803000,
    }
    # Historical engine treated Passed as a discount. After fold, Additional holds it.
    folded = ce.fold_oem_extra_passed_into_additional(before)
    after = {**before, **{k: folded[k] for k in (
        "additionalDiscount", "oemExtraSupportPassed", "oemExtraSupportRetained")}}
    s = ce.build_delivery_billing_summary(after)
    assert folded["moved"] == 2000
    assert folded["additionalDiscount"] == 6500
    assert s["totals"]["tallyBillTotal"] == 778500
    assert s["totals"]["customerCollectTotal"] == 803000
    assert "oemExtraSupport" not in [d["code"] for d in s["discountLines"]]


def test_three_wheeler_same_rto_lower_insurance():
    lead = {
        "leadId": "LD_3W",
        "interestedModel": "Hi-Load",
        "variant": "XR (PV)",
        "exShowroom": 456134,
        "rto": 5500,
        "insuranceAmount": 10000,
        "customerPayable": 471634,
    }
    s = ce.build_delivery_billing_summary(lead)
    off = {ln["code"]: ln["amount"] for ln in s["offTallyLines"]}
    assert off["rto"] == 5500
    assert off["insurance"] == 10000
    assert s["totals"]["tallyBillTotal"] == 456134
    assert s["totals"]["offTallyTotal"] == 15500
    assert s["totals"]["customerCollectTotal"] == 471634


@pytest_asyncio.fixture
async def client(monkeypatch):
    await server.startup()

    async def noop_sync(*a, **k):
        return {"ok": True, "operation": "skipped"}

    monkeypatch.setattr(server, "sheet_sync", noop_sync)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked_priced_lead(client, mobile="9111100099"):
    r = await client.post("/api/leads", json={
        "customerName": "Bill Summary", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.status_code == 200 and pv.json().get("found"), pv.text
    ps = pv.json()["priceStructure"]
    r = await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-09", "bookingAmount": 1000,
        "paymentMode": "Cash", "financeRequired": "No", "exchangeRequired": "No",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    os_amt = ce.num(lead.get("customerOutstanding"))
    if os_amt > 0:
        await client.post(f"/api/leads/{lid}/payments", json={
            "amount": os_amt, "paymentMode": "Cash", "date": "2026-08-10"})
    return lid


@pytest.mark.asyncio
async def test_price_structure_insurance_change_recomputes_payable_and_tally(client):
    """Edited insurance on Price Structure must move GVC, payable and Tally off-invoice."""
    lid = await _booked_priced_lead(client, "9111100095")
    before = await server.db.leads.find_one({"leadId": lid})
    old_ins = ce.round2(ce.num(before.get("insuranceAmount") or before.get("insurance")))
    assert old_ins > 0
    new_ins = 15000.0
    assert new_ins != old_ins
    r = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": ce.num(before.get("exShowroom")),
        "rto": ce.num(before.get("rto")),
        "insuranceAmount": new_ins,
        "insuranceArrangedBy": before.get("insuranceArrangedBy") or "dealer",
        "accessoriesAmount": ce.num(before.get("accessoriesAmount")),
        "handlingCharges": ce.num(before.get("handlingCharges")),
        "trc": ce.num(before.get("trc")),
        "fastag": ce.num(before.get("fastag")),
        "extendedWarranty": ce.num(before.get("extendedWarranty")),
        "otherCharges": ce.num(before.get("otherCharges")),
        "rsaAmc": ce.num(before.get("rsaAmc")),
        "tcsApplicable": before.get("tcsApplicable") or "No",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("insuranceAmount")) == new_ins
    delta = ce.round2(new_ins - old_ins)
    assert ce.num(after.get("grossVehicleCost")) == ce.round2(
        ce.num(before.get("grossVehicleCost")) + delta)
    if after.get("useDealPrice") and ce.num(after.get("cxDemand")) > 0:
        assert ce.num(after.get("customerPayable")) == ce.num(before.get("customerPayable"))
        assert ce.num(after.get("additionalDiscount")) == ce.round2(
            ce.num(before.get("additionalDiscount")) + delta)
    else:
        assert ce.num(after.get("customerPayable")) == ce.round2(
            ce.num(before.get("customerPayable")) + delta)

    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-95",
        "chassisNumber": "CH-BILL-95",
        "numberPlate": "RJ14-BILL-95",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text
    summary = (await client.get(f"/api/leads/{lid}/billing-summary")).json()
    off = {ln["code"]: ln["amount"] for ln in summary.get("offTallyLines") or []}
    assert off.get("insurance") == new_ins
    assert summary["totals"]["tallyBillTotal"] == ce.round2(
        ce.num(after.get("exShowroom")) - ce.num(after.get("additionalDiscount")))
    ins_row = await server.db.insurance.find_one({"leadId": lid})
    assert ins_row is not None
    assert ce.num(ins_row.get("insuranceAmount")) == new_ins

    later = 12000.0
    r = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": ce.num(after.get("exShowroom")),
        "rto": ce.num(after.get("rto")),
        "insuranceAmount": later,
        "insuranceArrangedBy": after.get("insuranceArrangedBy") or "dealer",
    })
    assert r.status_code == 200, r.text
    summary = (await client.get(f"/api/leads/{lid}/billing-summary")).json()
    off = {ln["code"]: ln["amount"] for ln in summary.get("offTallyLines") or []}
    assert off.get("insurance") == later
    ins_row = await server.db.insurance.find_one({"leadId": lid})
    assert ce.num(ins_row.get("insuranceAmount")) == later


def test_showroom_admin_can_price_after_delivery():
    lead = {
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "accountStatus": "Active", "bookingDate": "2026-08-09",
        "priceStructureSaved": True,
    }
    admin = server.lead_actions(lead, {"role": "tl"})
    assert admin["canPrice"] is True
    assert admin["canScheme"] is False
    team = server.lead_actions(lead, {"role": "team_lead"})
    assert team["canPrice"] is False
    exec_acts = server.lead_actions(lead, {"role": "executive"})
    assert exec_acts["canPrice"] is False


@pytest.mark.asyncio
async def test_showroom_admin_reedits_price_and_tally_syncs(client):
    lid = await _booked_priced_lead(client, "9111100096")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-96",
        "chassisNumber": "CH-BILL-96",
        "numberPlate": "RJ14-BILL-96",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    await server.db.users.delete_many({"email": "admin.price@euler.com"})
    cr = await client.post("/api/auth/users", json={
        "email": "admin.price@euler.com", "password": "euler@123",
        "name": "Showroom Admin", "role": "tl"})
    assert cr.status_code == 200, cr.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as admin:
        login = await admin.post("/api/auth/login",
                                 json={"email": "admin.price@euler.com", "password": "euler@123"})
        assert login.status_code == 200, login.text
        admin.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        r = await admin.put(f"/api/leads/{lid}/price-structure", json={
            "exShowroom": ce.num(lead.get("exShowroom")),
            "rto": ce.num(lead.get("rto")),
            "insuranceAmount": 16000,
            "insuranceArrangedBy": "dealer",
        })
        assert r.status_code == 200, r.text
        acts = (await admin.get(f"/api/leads/{lid}/360")).json()["actions"]
        assert acts["canPrice"] is True
        summary = (await admin.get(f"/api/leads/{lid}/billing-summary")).json()
    off = {ln["code"]: ln["amount"] for ln in summary.get("offTallyLines") or []}
    assert off.get("insurance") == 16000
    stored = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(stored.get("insuranceAmount")) == 16000


@pytest.mark.asyncio
async def test_delivery_creates_billing_summary(client):
    lid = await _booked_priced_lead(client, "9111100091")
    r = await client.get(f"/api/leads/{lid}/billing-summary")
    assert r.status_code == 409

    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-91",
        "chassisNumber": "CH-BILL-91",
        "numberPlate": "RJ14-BILL-91",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text

    stored = await server.db.billing_summaries.find_one({"leadId": lid})
    assert stored is not None
    assert stored["totals"]["customerPayable"] > 0
    assert "Tally" in stored["disclaimer"]
    assert stored["kind"] == "delivery_billing_summary"

    r = await client.get(f"/api/leads/{lid}/billing-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["leadId"] == lid
    assert body["invoiceNumber"] == "INV-BILL-91"

    r = await client.get(f"/api/leads/{lid}/360")
    assert r.status_code == 200
    bs = r.json().get("billingSummary") or {}
    assert bs.get("leadId") == lid


@pytest.mark.asyncio
async def test_scheme_additional_discount_refreshes_billing_summary(client):
    """Dealer extra changed after delivery must show on Tally summary (not frozen snapshot)."""
    lid = await _booked_priced_lead(client, "9111100092")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-92",
        "chassisNumber": "CH-BILL-92",
        "numberPlate": "RJ14-BILL-92",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text

    # Stale snapshot with old Additional Discount
    await server.db.billing_summaries.update_one(
        {"leadId": lid},
        {"$set": {
            "discountLines": [{"code": "additionalDiscount", "label": "Less: Additional Discount",
                               "amount": -3500, "fundHint": "Dealer-funded"}],
            "totals.customerBenefitPassed": 3500,
        }},
    )

    lead = await server.db.leads.find_one({"leadId": lid})
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "loyaltyBonus": ce.num(lead.get("loyaltyBonus")),
        "consumerDiscount": 0, "exchangeBonus": 0, "referralBonus": 0, "dsaDiscount": 0,
        "additionalDiscount": 8500,
        "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": "{}",
        "schemeComponentsUsed": "{}",
        "oemExtraSupportReceived": ce.num(lead.get("oemExtraSupportReceived")),
        "oemExtraSupportPassed": ce.num(lead.get("oemExtraSupportPassed")),
    })
    assert r.status_code == 200, r.text

    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead.get("additionalDiscount")) == 8500

    r = await client.get(f"/api/leads/{lid}/billing-summary")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"]["customerBenefitPassed"] == 8500
    codes = {d["code"]: d for d in body["discountLines"]}
    assert "additionalDiscount" in codes
    assert abs(codes["additionalDiscount"]["amount"] + 8500) < 0.05

    r = await client.get(f"/api/leads/{lid}/360")
    bs = (r.json().get("billingSummary") or {})
    assert bs.get("totals", {}).get("customerBenefitPassed") == 8500


@pytest.mark.asyncio
async def test_billing_summary_upsert_no_set_setoninsert_conflict(client):
    """Re-upsert must not use overlapping $set / $setOnInsert paths (Mongo code 40)."""
    lid = await _booked_priced_lead(client, "9111100093")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-93",
        "chassisNumber": "CH-BILL-93",
        "numberPlate": "RJ14-BILL-93",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text

    first = await server.db.billing_summaries.find_one({"leadId": lid})
    assert first is not None
    created = first.get("createdAt")

    # Second rebuild (same path as GET /billing-summary and /360 for Delivered).
    summary = await server._upsert_delivery_billing_summary(lid)
    assert summary["summaryId"] == f"BILL-{lid}"
    stored = await server.db.billing_summaries.find_one({"leadId": lid})
    assert stored["createdAt"] == created
    assert stored.get("updatedAt")

    r = await client.get(f"/api/leads/{lid}/billing-summary")
    assert r.status_code == 200, r.text
    r = await client.get(f"/api/leads/{lid}/360")
    assert r.status_code == 200, r.text
    assert (r.json().get("billingSummary") or {}).get("leadId") == lid


@pytest.mark.asyncio
async def test_rebuild_overwrites_old_full_amount_tally(client):
    """Existing stored summaries that taxed the full deal are rewritten."""
    lid = await _booked_priced_lead(client, "9111100094")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes",
        "rc": "Yes", "pdi": "Yes", "delivered": "Yes",
        "deliveryDate": "2026-08-10",
        "invoiceNumber": "INV-BILL-94",
        "chassisNumber": "CH-BILL-94",
        "numberPlate": "RJ14-BILL-94",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    ex = ce.round2(ce.num(lead.get("exShowroom")))
    rto = ce.round2(ce.num(lead.get("rto")))
    ins = ce.round2(ce.num(lead.get("insuranceAmount") or lead.get("insurance")))
    stale_total = ce.round2(ex + rto + ins)
    await server.db.billing_summaries.update_one(
        {"leadId": lid},
        {"$set": {
            "disclaimer": "Tally customer bill = full amount taken from customer",
            "totals.tallyBillTotal": stale_total,
        },
         "$unset": {"totals.offTallyTotal": "", "offTallyLines": ""}},
    )
    n = await server._rebuild_all_delivery_billing_summaries()
    assert n >= 1
    stored = await server.db.billing_summaries.find_one({"leadId": lid})
    assert "offTallyTotal" in (stored.get("totals") or {})
    assert stored["totals"]["tallyBillTotal"] == ex
    assert stored["totals"]["offTallyTotal"] == ce.round2(rto + ins)
    assert stored["totals"]["customerCollectTotal"] == stale_total
    assert "vehicle" in (stored.get("disclaimer") or "").lower()
