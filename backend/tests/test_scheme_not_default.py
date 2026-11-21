"""Scheme Master amounts do not change the price until someone selects them."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scheme_not_default_v1")
os.environ.setdefault("JWT_SECRET", "scheme-not-default-secret-32chars")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

EX = 824999
RTO = 5500
INS = 19000
ON_ROAD = EX + RTO + INS


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _unit(sno, sold, loyalty=0, payable=None, lock=False, **extra):
    row = {
        "sno": sno,
        "model": "Turbo Max",
        "variant": "Maxx (DV220)",
        "soldDate": sold,
        "exShowroom": EX,
        "rto": RTO,
        "insuranceAmount": INS,
        "loyaltyBonus": loyalty,
        "customerPayable": ON_ROAD - loyalty if payable is None else payable,
    }
    if lock:
        row["cxDemand"] = row["customerPayable"]
        row["useDealPrice"] = True
        row["budget"] = row["customerPayable"]
    row.update(extra)
    return row


@pytest.mark.asyncio
async def test_price_master_quote_does_not_include_loyalty(client):
    priced = await server._price_unit_from_master("Turbo Max", "Maxx (DV220)", "2026-09-15")
    assert ce.num(priced.get("loyaltyBonus")) == 0
    assert ce.num(priced.get("exShowroom")) > 0
    assert ce.num(priced["customerPayable"]) == ce.round2(
        ce.num(priced["exShowroom"]) + ce.num(priced["rto"]) + ce.num(priced["insuranceAmount"]))


@pytest.mark.asyncio
async def test_unselected_september_loyalty_does_not_cut_the_price(client):
    lid = (await client.post("/api/leads", json={
        "customerName": "Messenger", "mobile": "9800143558",
        "interestedModel": "Turbo Max", "variant": "Maxx (DV220)", "executive": "Amit",
    })).json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "sameOrderMultiUnit": True,
        "loyaltyBonus": 10000,
        "benefitMode": "Full Benefit",
        "exShowroom": EX,
        "rto": RTO,
        "insuranceAmount": INS,
        "customerPayable": ON_ROAD - 10000,
        "units": [
            _unit(1, "2026-09-15", loyalty=10000, lock=True),
            _unit(2, "2026-10-11", loyalty=0),
        ],
    }})
    await server.recompute_lead(lid)
    lead = await server.db.leads.find_one({"leadId": lid})
    units = lead["units"]
    assert ce.num(units[0].get("loyaltyBonus")) == 0
    assert units[0].get("useDealPrice") is not True
    assert ce.num(units[0]["customerPayable"]) == ON_ROAD
    assert ce.num(units[1]["customerPayable"]) == ON_ROAD
    assert ce.num(lead["customerPayable"]) == ON_ROAD * 2
    assert not ce.scheme_choice_recorded({"loyaltyBonus": 10000, "benefitMode": "Full Benefit"})


@pytest.mark.asyncio
async def test_selected_loyalty_still_reduces_that_unit(client):
    lid = (await client.post("/api/leads", json={
        "customerName": "Selected", "mobile": "9800143559",
        "interestedModel": "Turbo Max", "variant": "Maxx (DV220)", "executive": "Amit",
    })).json()["leadId"]
    chosen = _unit(
        1, "2026-09-15", loyalty=10000, payable=ON_ROAD - 10000,
        schemeAllocationExplicit=True, schemeAllocationV2=True,
        benefitPassedBreakup='{"loyaltyBonus": 10000}',
        schemeComponentsUsed='{"loyaltyBonus": true}',
        benefitMode="Partial Benefit",
    )
    plain = _unit(2, "2026-09-15", loyalty=10000, lock=True)
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "sameOrderMultiUnit": True,
        "exShowroom": EX, "rto": RTO, "insuranceAmount": INS,
        "units": [chosen, plain],
    }})
    await server.recompute_lead(lid)
    units = (await server.db.leads.find_one({"leadId": lid}))["units"]
    assert ce.num(units[0]["loyaltyBonus"]) == 10000
    assert ce.num(units[0]["customerPayable"]) == ON_ROAD - 10000
    assert ce.num(units[1].get("loyaltyBonus")) == 0
    assert ce.num(units[1]["customerPayable"]) == ON_ROAD
