"""Cx Demand is the deal. Extra Passed / Additional fill the leftover after scheme."""
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


def test_derive_leftover_after_scheme_uses_extra_then_additional():
    out = ce.derive_deal_customer_pass(1000500, 960000, 30000, 15000)
    assert out["oemExtraSupportPassed"] == 10500
    assert out["additionalDiscount"] == 0
    assert out["extraFromCustomer"] == 0
    short = ce.derive_deal_customer_pass(989500, 960000, 0, 15000)
    assert short["oemExtraSupportPassed"] == 15000
    assert short["additionalDiscount"] == 14500
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
