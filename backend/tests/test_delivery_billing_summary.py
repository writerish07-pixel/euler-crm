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
    assert s["totals"]["customerPayable"] == 825000
    assert s["totals"]["customerBenefitPassed"] == 9499
    codes = [d["code"] for d in s["discountLines"]]
    assert "additionalDiscount" in codes
    assert "loyaltyBonus" not in codes  # Use=No / not passed
    assert any("retained" in x["label"].lower() or "claim" in x["label"].lower()
               for x in s["doNotPostInTally"])
    assert s["gstReference"]["ratePct"] == 5.0


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
    assert abs(s["totals"]["grossVehicleCost"] - s["totals"]["customerBenefitPassed"]
               - s["totals"]["customerPayable"]) < 0.05


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
        "insurerName": "TestIns",
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
