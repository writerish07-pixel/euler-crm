"""OEM Coulson catalog mapping, Price Master apply, and mocked live sync."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "coulson_oem_test")
os.environ.setdefault("JWT_SECRET", "coulson-oem-secret")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import oem_catalog as cat  # noqa: E402
import oem_sync  # noqa: E402
import coulson as coulson_client  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_catalog_keys_unique():
    keys = [s.key for s in cat.CATALOG]
    assert len(keys) == len(set(keys))
    pairs = [(s.crm_model, s.crm_variant) for s in cat.CATALOG]
    assert len(pairs) == len(set(pairs))


def test_alias_hi_load_xr_is_hicity():
    sku = cat.resolve_sku("Hi-Load", "XR")
    assert sku is not None
    assert sku.crm_model == "HiCity"
    assert sku.crm_variant == "XR"


def test_alias_dv200_renames():
    assert cat.resolve_sku("Turbo Max", "Maxx (DV200)").crm_variant == "Maxx (DV220)"
    assert cat.resolve_sku("Turbo Max", "FastCharge (DV200)").crm_variant == "FastCharge (DV220)"


def test_storm_hd_c10_is_t1250():
    sku = cat.resolve_sku("Storm", "Storm TR (HD) Reg C10 3.3kWh")
    assert sku.crm_variant == "Storm T1250 (HD) Reg C10 3.3kWh"
    assert sku.oem_variant == "T1250"


def test_city_dac_is_dropped():
    assert ("Turbo Max", "City (DAC)") in cat.DROP_VARIANTS
    assert cat.resolve_sku("Turbo Max", "City (DAC)") is None


def test_oem_fingerprint_turbo_city_fb():
    oem = {"model": "Turbo", "variant": "City", "load_body": "FB",
           "showroom_price_non_delhi": 625000, "sap_product_name": "TURBO CITY FB 7.6 Ft"}
    sku = cat.sku_for_oem_row(oem)
    assert sku and sku.crm_variant == "City (FB)"
    assert cat.jaipur_price(oem) == 625000


def test_tipper_dav_not_plain_tipper():
    city = {"model": "Turbo", "variant": "City", "load_body": "Tipper",
            "sap_product_name": "TURBO CITY TIPPER"}
    dav = {"model": "Turbo", "variant": "City", "load_body": "Tipper",
           "sap_product_name": "TURBO CITY TIPPER DAV"}
    assert cat.sku_for_oem_row(city).key == "turbo.city.tipper"
    assert cat.sku_for_oem_row(dav).key == "turbo.city.tipper_dav"


@pytest.mark.asyncio
async def test_apply_catalog_renames_and_drops(client):
    rows = (await client.get("/api/price-master")).json()
    variants = {(r["model"], r["variant"]): r for r in rows}

    assert ("Turbo Max", "City (DAC)") in {(r["model"], r["variant"]) for r in rows}
    dac = next(r for r in rows if r["variant"] == "City (DAC)")
    assert str(dac["status"]).lower() == "inactive"

    assert ("Turbo Max", "Maxx (DV220)") in variants
    assert ("Turbo Max", "Maxx (DV200)") not in variants
    assert variants[("Turbo Max", "City (FB)")]["exShowroom"] == 625000
    assert variants[("Turbo Max", "FastCharge (PV)")]["exShowroom"] == 870000

    assert ("Hi-Load", "TR-NC (FB120)") in variants
    assert ("Hi-Load", "TR With GBT (DV120)") in variants
    assert ("HiCity", "XR") in variants
    assert ("HiCity", "SR") in variants
    assert ("HiCity", "TR") in variants
    assert variants[("HiCity", "XR")]["exShowroom"] == 435000

    assert ("Turbo Max", "City (Tipper)") in variants
    assert ("Turbo Max", "Maxx (Tipper)") in variants
    assert ("Hi-Load", "SR (FB120)") in variants
    assert ("Storm", "Storm T1250 (HD) Reg C10 3.3kWh") in variants
    assert ("Storm", "Storm TR (DV220) Reg C7 3.3kWh") in variants
    assert ("Storm", "Storm TR (Tipper)") in variants
    dropped = next(r for r in rows if r["variant"] == "Storm TR (FB) Reg C10 3.3kWh")
    assert str(dropped["status"]).lower() == "inactive"

    # New OEM SKUs have blank RTO / insurance
    sr = variants[("Hi-Load", "SR (FB120)")]
    assert sr["rto"] == 0 and sr["insurance"] == 0
    assert sr["exShowroom"] == 421156
    tipper = variants[("Turbo Max", "City (Tipper)")]
    assert tipper["rto"] == 0 and tipper["insurance"] == 0

    dac_variants = (await client.get("/api/price-master/variants", params={"model": "Turbo Max"})).json()
    assert all(r["variant"] != "City (DAC)" for r in dac_variants)


@pytest.mark.asyncio
async def test_old_names_still_preview(client):
    r = await client.post("/api/leads", json={
        "customerName": "OEM Alias QA", "mobile": "9000011199",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit",
        "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.status_code == 200
    assert pv.json()["found"] is True
    assert pv.json()["priceStructure"]["exShowroom"] == 435000


@pytest.mark.asyncio
async def test_oem_exshowroom_locked_rto_manual(client):
    rows = (await client.get("/api/price-master")).json()
    city = next(r for r in rows if r["model"] == "Turbo Max" and r["variant"] == "City (PV)")
    assert city["priceSource"] == "oem"
    old_ex = city["exShowroom"]
    r = await client.put(f"/api/price-master/{city['priceId']}", json={
        "model": city["model"], "variant": city["variant"], "bodyType": city.get("bodyType") or "",
        "exShowroom": 1, "rto": 12345, "insurance": city.get("insurance") or 0,
        "tcsApplicable": city.get("tcsApplicable") or "No", "status": "active",
    })
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["exShowroom"] == old_ex
    assert updated["rto"] == 12345


@pytest.mark.asyncio
async def test_mocked_coulson_sync(client, monkeypatch):
    oem_models = [
        {"id": "oem-city-fb", "model": "Turbo", "variant": "City", "load_body": "FB",
         "sap_product_id": "CD00000500", "sap_product_name": "TURBO CITY FB 7.6 Ft",
         "showroom_price_non_delhi": 625000, "showroom_price_delhi": 625000},
        {"id": "oem-maxx-pv", "model": "Turbo", "variant": "Range Maxx", "load_body": "PV",
         "sap_product_id": "CD00001500", "sap_product_name": "TURBO RANGEMAXX PV",
         "showroom_price_non_delhi": 770000, "showroom_price_delhi": 770000},
    ]
    vehicles = [{
        "chassis": "MD9TESTCHASSIS0001", "emch": "EMCS-1", "registration_number": "EMCS-1",
        "model": "Turbo", "variant": "Range Maxx", "updated_load_body": "PV",
        "sap_vehicle_model_id": "oem-maxx-pv", "sap_product_name": "TURBO RANGEMAXX PV",
        "is_pdi_done": True, "ready_for_allocation": True, "current_inventory_ageing": 4,
        "colour": "White",
    }]

    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: oem_models)
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200: vehicles)

    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["inventoryCount"] == 1

    inv = (await client.get("/api/inventory")).json()
    assert len(inv) == 1
    assert inv[0]["chassis"] == "MD9TESTCHASSIS0001"
    assert inv[0]["model"] == "Turbo Max"
    assert inv[0]["variant"] == "Maxx (PV)"
    assert inv[0]["exShowroom"] == 770000

    summary = (await client.get("/api/inventory/summary")).json()
    assert summary["total"] == 1

    st = (await client.get("/api/integrations/coulson")).json()
    assert st["configured"] is True
    assert "secret" not in str(st)
    assert st["username"].startswith("de")


@pytest.mark.asyncio
async def test_coulson_status_hides_password(client):
    r = await client.get("/api/integrations/coulson")
    assert r.status_code == 200
    assert "password" not in r.json()


@pytest.mark.asyncio
async def test_save_rejects_invalid_coulson_login(client, monkeypatch):
    def _boom(u, p):
        raise coulson_client.CoulsonError("Username/password is not valid, Please try again", status=203)

    monkeypatch.setattr(coulson_client, "login", _boom)
    r = await client.put("/api/integrations/coulson",
                         json={"username": "vaibhav.akar", "password": "nope"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loginOk"] is False
    assert "not valid" in (body.get("lastError") or "").lower()
    assert "nope" not in str(body)


@pytest.mark.asyncio
async def test_save_verifies_valid_coulson_login(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    r = await client.put("/api/integrations/coulson",
                         json={"username": "dealer.user", "password": "secret"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loginOk"] is True
    assert body["configured"] is True
    assert "secret" not in str(body)
