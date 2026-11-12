"""New OEM models, their prices, and published schemes land in the CRM."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import coulson as coulson_client  # noqa: E402
import oem_live_catalog as live  # noqa: E402
import oem_sync  # noqa: E402


CATALOG = [{
    "model": "N1",
    "vehicle_type": "L5",
    "variants": [{
        "variant_name": "XR",
        "load_bodies": [
            {"id": "n1-pv", "name": "PV", "invoice_amount": 512000, "charger_type": "3.3"},
            {"id": "n1-fb", "load_body": "FB", "invoice_amount": 498000},
        ],
    }],
}]


def test_nested_order_catalog_becomes_one_row_per_body():
    rows = live.flatten_order_catalog(CATALOG)
    assert len(rows) == 2
    pv = next(row for row in rows if row["load_body"] == "PV")
    assert pv["model"] == "N1" and pv["variant"] == "XR"
    assert pv["invoice_amount"] == 512000
    assert live.live_labels(pv) == ("N1", "XR (PV) 3.3")


def test_a_known_turbo_sku_is_not_imported_again():
    sap = [{
        "model": "Turbo", "variant": "City", "load_body": "FB",
        "showroom_price_non_delhi": 625000,
    }]
    planned = live.plan_live_import(sap, {"catalog": CATALOG, "metadata": {}, "variants": [], "schemes": []})
    models = {row["model"] for row in planned["rows"]}
    assert "Turbo" not in models
    assert "N1" in models


def test_metadata_names_a_model_that_has_no_price_yet():
    meta = {"Storm Plus": [{"variant_name": "LR", "sub_variants": ["HD"]}]}
    rows = live.rows_from_metadata(meta)
    assert rows == [{"model": "Storm Plus", "variant": "LR HD", "load_body": ""}]
    planned = live.plan_live_import([], {"catalog": [], "metadata": meta, "schemes": []})
    assert planned["rows"][0]["model"] == "Storm Plus"
    assert planned["schemeQueries"] == [("Storm Plus", "LR HD")]


def test_insurance_rupees_map_onto_the_insurance_component():
    rows = live.scheme_rows_from_items([{
        "scheme_name": "Free Insurance Up To",
        "model": "N1", "variant": "XR",
        "company_share": 10000, "dealer_share": 0,
        "start_date": "2026-11-01", "end_date": "2026-11-30",
    }], today="2026-11-12")
    assert rows[0]["componentKey"] == "insuranceBenefit"
    assert rows[0]["companyShare"] == 10000
    assert rows[0]["schemeMonth"] == "2026-11"


def test_a_percentage_scheme_is_not_stored_as_rupees():
    assert live.scheme_rows_from_items([{
        "name": "Festival", "model": "N1", "amount_type": "PERCENTAGE", "amount": 5,
    }]) == []


def test_a_named_offer_keeps_its_own_component():
    rows = live.scheme_rows_from_items([{
        "scheme_name": "PM-EDRIVE", "model": "N1", "scheme_type": "DISCOUNT", "amount": 15000,
    }], today="2026-11-12")
    assert rows[0]["componentKey"] == "oem_pmedrive"
    assert rows[0]["companyShare"] == 15000
    assert rows[0]["component"] == "PM-EDRIVE"


def test_session_tokens_are_the_only_ones_that_call_euler():
    assert oem_sync._is_coulson_session("aaaabbbb.ccccdddd.eeeeffff") is True
    assert oem_sync._is_coulson_session("fake-token") is False
    assert oem_sync._is_coulson_session("tok") is False


@pytest.mark.asyncio
async def test_new_model_price_and_scheme_are_saved_and_a_hand_scheme_stays():
    client = AsyncMongoMockClient()
    db = client["oem_live_catalog"]
    await db.scheme_master.insert_one({
        "schemeId": "SCM-HAND",
        "schemeMonth": "2026-11",
        "model": "N1",
        "variant": "XR",
        "componentKey": "loyaltyBonus",
        "companyShare": 8000,
        "dealerShare": 0,
        "status": "Active",
    })
    planned = live.plan_live_import([], {
        "catalog": CATALOG,
        "metadata": {},
        "schemes": [
            {"scheme_name": "Loyalty", "model": "N1", "variant": "XR",
             "company_share": 99999, "start_date": "2026-11-01"},
            {"scheme_name": "Free Insurance Up To", "model": "N1", "variant": "XR",
             "company_share": 10000, "start_date": "2026-11-01", "end_date": "2026-11-30"},
        ],
        "packages": [],
        "checks": [
            {"name": "Order catalog", "path": "sap-vehicle-models/catalog", "ok": True, "status": 200},
            {"name": "Schemes", "path": "dealer/scheme", "ok": False, "status": 403, "detail": "no"},
        ],
    })
    assert planned["schemeQueries"] == []
    result = await live.apply_live_import(db, planned, today="2026-11-12")
    assert result["liveModelsAdded"] == 2
    assert result["schemesAdded"] == 1
    assert result["schemesKept"] == 1
    assert result["oemReadsOk"] == 1
    assert result["oemReadsFailed"] == 1
    prices = await db.price_master.find({}).to_list(10)
    assert {row["variant"] for row in prices} == {"XR (PV) 3.3", "XR (FB)"}
    assert {row["exShowroom"] for row in prices} == {512000, 498000}
    loyalty = await db.scheme_master.find_one({"componentKey": "loyaltyBonus"})
    assert loyalty["companyShare"] == 8000
    insurance = await db.scheme_master.find_one({"componentKey": "insuranceBenefit"})
    assert insurance["companyShare"] == 10000
    assert insurance["oemSource"] == "coulson"


@pytest.mark.asyncio
async def test_a_real_session_imports_the_order_catalog(monkeypatch):
    db = AsyncMongoMockClient()["oem_live_sync"]
    token = "aaaabbbb.ccccdddd.eeeeffff"

    async def access(*_a, **_k):
        return token, "session"

    monkeypatch.setattr(oem_sync, "_access_token", access)
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda _token: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda _token, limit=200, **_k: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda _token, limit=200, **_k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda _token, limit=200, **_k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda _token, limit=200, **_k: [])
    monkeypatch.setattr(coulson_client, "fetch_dealer_desk", lambda _token: {
        "catalog": CATALOG, "metadata": {}, "variants": [], "schemes": [],
        "packages": [], "checks": [{"name": "Order catalog", "ok": True, "status": 200, "path": "sap-vehicle-models/catalog"}],
        "showroomId": "jaipur",
    })
    monkeypatch.setattr(coulson_client, "fetch_scheme_amounts", lambda _token, _pairs: [{
        "scheme_name": "Free Insurance Up To", "model": "N1", "variant": "XR",
        "company_share": 7000, "start_date": "2026-11-01", "end_date": "2026-11-30",
    }])
    result = await oem_sync.sync_from_coulson(db)
    assert result["ok"] is True
    assert result["liveModelsAdded"] == 2
    assert result["schemesAdded"] == 1
    saved = await db.price_master.find_one({"model": "N1", "variant": "XR (PV) 3.3"})
    assert saved["exShowroom"] == 512000
