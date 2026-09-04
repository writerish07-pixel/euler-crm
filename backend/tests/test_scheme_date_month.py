"""Changing Scheme Date / Scheme Master date must load that month's circular."""
import json
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "scheme_date_month_v1")
os.environ.setdefault("JWT_SECRET", "scheme-date-month-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL = "CargoKing"
AUG = [
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-01", "effectiveTo": "2026-08-31",
     "model": MODEL, "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
     "dealerShare": 0, "companyShare": 8000, "totalBenefit": 8000, "status": "Active"},
    {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-01", "effectiveTo": "2026-08-31",
     "model": MODEL, "variant": "", "componentKey": "consumerDiscount", "component": "Consumer",
     "dealerShare": 2000, "companyShare": 3000, "totalBenefit": 5000, "status": "Active"},
]
SEP = [
    {"schemeMonth": "2026-09", "effectiveFrom": "2026-09-01", "effectiveTo": "2026-09-30",
     "model": MODEL, "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
     "dealerShare": 0, "companyShare": 15000, "totalBenefit": 15000, "status": "Active"},
]
ROWS = AUG + SEP


def test_prior_month_does_not_leak_when_new_month_has_no_circular():
    """When September has no rows, August's scheme must not still apply."""
    empty = ce.get_scheme_shares_for_lead(MODEL, "", "2026-09-10", AUG)
    assert empty == {}
    rules = ce.get_scheme_offer_rules_for_vehicle(MODEL, "", "2026-09-10", AUG)
    assert not any((rules.get("rules") or {}).get(k, {}).get("allowed") for k in
                   ("loyaltyBonus", "consumerDiscount"))


def test_shares_switch_when_date_crosses_month():
    aug = ce.get_scheme_shares_for_lead(MODEL, "", "2026-08-15", ROWS)
    sep = ce.get_scheme_shares_for_lead(MODEL, "", "2026-09-10", ROWS)
    assert aug["loyaltyBonus"]["companyShare"] == 8000
    assert sep["loyaltyBonus"]["companyShare"] == 15000
    assert "consumerDiscount" in aug
    assert "consumerDiscount" not in sep


def test_offer_rules_report_the_requested_month():
    aug = ce.get_scheme_offer_rules_for_vehicle(MODEL, "", "2026-08-20", ROWS)
    sep = ce.get_scheme_offer_rules_for_vehicle(MODEL, "", "2026-09-02", ROWS)
    assert aug["schemeMonth"] == "2026-08"
    assert sep["schemeMonth"] == "2026-09"
    assert aug["rules"]["loyaltyBonus"]["maxAmount"] == 8000
    assert sep["rules"]["loyaltyBonus"]["maxAmount"] == 15000
    assert aug["rules"]["consumerDiscount"]["allowed"] is True
    assert sep["rules"]["consumerDiscount"]["allowed"] is False


def test_scheme_as_of_prefers_explicit_then_saved_then_booking():
    assert server._scheme_as_of({"schemeAsOf": "2026-08-08", "bookingDate": "2026-07-01"}, "2026-09-15") == "2026-09-15"
    assert server._scheme_as_of({"schemeAsOf": "2026-08-08", "bookingDate": "2026-07-01"}) == "2026-08-08"
    assert server._scheme_as_of({"bookingDate": "2026-07-01"}) == "2026-07-01"
    assert server._scheme_as_of({}) == server.today()
    assert server._scheme_as_of(None, "not-a-date") == server.today()


def test_normalize_scheme_row_derives_month_from_valid_to():
    out = server._normalize_scheme_row({
        "model": MODEL, "effectiveTo": "2026-10-31", "schemeMonth": None,
        "dealerShare": 0, "companyShare": 1000,
    })
    assert out["schemeMonth"] == "2026-10"
    assert out["effectiveFrom"] == "2026-10-01"


def test_scheme_row_filter_by_as_of_date():
    aug_row = AUG[0]
    sep_row = SEP[0]
    assert server._scheme_row_matches_as_of(aug_row, "2026-08-15") is True
    assert server._scheme_row_matches_as_of(aug_row, "2026-09-01") is False
    assert server._scheme_row_matches_as_of(sep_row, "2026-09-01") is True
    assert server._scheme_row_matches_as_of(sep_row, "2026-08-31") is False


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _cargoking_lead(c, mobile="9000011266"):
    await server.db.scheme_master.delete_many({"model": MODEL})
    for i, row in enumerate(ROWS):
        await server.db.scheme_master.insert_one({**row, "schemeId": f"SCM-DATE-{i}"})
    r = await c.post("/api/leads", json={
        "customerName": "Scheme Date Switch", "mobile": mobile,
        "interestedModel": MODEL, "variant": "Standard",
        "executive": "Amit", "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


@pytest.mark.asyncio
async def test_scheme_rules_on_query_switches_month(client):
    lid = await _cargoking_lead(client)
    aug = (await client.get(f"/api/leads/{lid}/scheme-rules", params={"on": "2026-08-15"})).json()
    sep = (await client.get(f"/api/leads/{lid}/scheme-rules", params={"on": "2026-09-10"})).json()
    assert aug["schemeMonth"] == "2026-08"
    assert sep["schemeMonth"] == "2026-09"
    assert aug["asOf"] == "2026-08-15"
    assert sep["asOf"] == "2026-09-10"
    assert aug["rules"]["loyaltyBonus"]["maxAmount"] == 8000
    assert sep["rules"]["loyaltyBonus"]["maxAmount"] == 15000
    assert aug["rules"]["consumerDiscount"]["allowed"] is True
    assert sep["rules"]["consumerDiscount"]["allowed"] is False


@pytest.mark.asyncio
async def test_save_scheme_date_does_not_invent_booking(client):
    lid = await _cargoking_lead(client, mobile="9000011267")
    r = await client.put(f"/api/leads/{lid}/scheme", json={
        "schemeDate": "2026-09-05",
        "benefitMode": "Partial Benefit",
        "benefitPassedBreakup": json.dumps({"loyaltyBonus": 0}),
        "schemeComponentsUsed": json.dumps({"loyaltyBonus": False}),
    })
    assert r.status_code == 200, r.text
    lead = r.json()
    assert lead.get("schemeAsOf") == "2026-09-05"
    assert not lead.get("bookingDate")
    assert not lead.get("bookingId")
    again = (await client.get(f"/api/leads/{lid}/scheme-rules")).json()
    assert again["schemeMonth"] == "2026-09"
    assert again["asOf"] == "2026-09-05"
    assert again["rules"]["loyaltyBonus"]["maxAmount"] == 15000


@pytest.mark.asyncio
async def test_scheme_master_create_tags_month_from_valid_to(client):
    r = await client.post("/api/scheme-master", json={
        "model": MODEL, "variant": "", "component": "Loyalty", "componentKey": "loyaltyBonus",
        "dealerShare": 0, "companyShare": 1111, "effectiveTo": "2026-11-30", "status": "Active",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schemeMonth"] == "2026-11"
    assert body["effectiveFrom"] == "2026-11-01"
    listed = (await client.get("/api/scheme-master", params={"on": "2026-11-15"})).json()
    assert any(row.get("schemeId") == body["schemeId"] for row in listed)
    other = (await client.get("/api/scheme-master", params={"on": "2026-08-15"})).json()
    assert all(row.get("schemeId") != body["schemeId"] for row in other)
