"""OEM Coulson catalog mapping, Price Master apply, and mocked live sync."""
import json
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


def test_inventory_reads_motor_and_battery_aliases():
    row = {
        "chassis": "MD9MOTORBATT01",
        "motor_no": " mtr-9901 ",
        "vehicle": {"battery_serial_number": "BAT-PACK-12"},
    }
    assert oem_sync.vehicle_motor(row) == "mtr-9901"
    assert oem_sync.vehicle_battery(row) == "BAT-PACK-12"
    doc = oem_sync._inventory_doc(row, None, 0)
    assert doc["motorNumber"] == "mtr-9901"
    assert doc["batteryNumber"] == "BAT-PACK-12"


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


def test_jaipur_price_keeps_paise_and_falls_back():
    assert cat.jaipur_price({
        "showroom_price_non_delhi": "785713.33",
        "showroom_price_delhi": 1,
    }) == 785713.33
    assert cat.jaipur_price({"base_price": 785713.33}) == 785713.33
    assert cat.jaipur_price({"showroom_price_non_delhi": 0, "ex_showroom_price": 100.5}) == 100.5
    assert cat.jaipur_price({}) == 0.0
    dv = {"model": "Turbo", "variant": "Range Maxx", "load_body": "DV220",
          "sap_product_name": "TURBO RANGEMAXX DV220"}
    assert cat.sku_for_oem_row(dv).key == "turbo.maxx.dv220"


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
        "motor_number": "MTR-77821", "battery_serial_number": "BAT-44190",
    }]

    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: oem_models)
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: vehicles)
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])

    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["inventoryCount"] == 1
    assert body["pricesUpdated"] >= 2

    inv = (await client.get("/api/inventory")).json()
    assert len(inv) == 1
    assert inv[0]["chassis"] == "MD9TESTCHASSIS0001"
    assert inv[0]["motorNumber"] == "MTR-77821"
    assert inv[0]["batteryNumber"] == "BAT-44190"
    assert inv[0]["model"] == "Turbo Max"
    assert inv[0]["variant"] == "Maxx (PV)"
    assert inv[0]["exShowroom"] == 770000

    summary = (await client.get("/api/inventory/summary")).json()
    assert summary["total"] == 1

    st = (await client.get("/api/integrations/coulson")).json()
    assert st["configured"] is True
    assert "secret" not in str(st)
    assert st["username"].startswith("de")

    pm = next(r for r in (await client.get("/api/price-master", params={"model": "Turbo Max"})).json()
              if r["variant"] == "Maxx (PV)")
    assert pm["exShowroom"] == 770000
    assert pm["oemSyncedAt"]
    assert pm["sellingExShowroom"] == 770000
    assert pm["turboUplift"] == 0
    plist = next(r for g in (await client.get("/api/price-list", params={"model": "Turbo Max"})).json()["models"]
                 for r in g["rows"] if r["variant"] == "Maxx (PV)")
    assert plist["exShowroom"] == 770000


OEM_MAXX_DV220 = 785713.33


@pytest.mark.asyncio
async def test_sync_writes_oem_invoice_price_to_master_and_list(client, monkeypatch):
    """Price List hero must match Coulson Base Price, including paise, and Price Master too."""
    oem_models = [{
        "id": "oem-maxx-dv220", "model": "Turbo", "variant": "Range Maxx", "load_body": "DV220",
        "sap_product_id": "CD00002200", "sap_product_name": "TURBO RANGEMAXX DV220",
        "showroom_price_non_delhi": OEM_MAXX_DV220, "showroom_price_delhi": OEM_MAXX_DV220,
    }]
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: oem_models)
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])

    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["pricesUpdated"] >= 1

    pm = next(row for row in (await client.get("/api/price-master", params={"model": "Turbo Max"})).json()
              if row["variant"] == "Maxx (DV220)")
    assert pm["exShowroom"] == OEM_MAXX_DV220
    assert pm["oemSyncedAt"]
    assert pm["sellingExShowroom"] == OEM_MAXX_DV220
    assert pm["turboUplift"] == 0

    plist = next(row for g in (await client.get("/api/price-list", params={"model": "Turbo Max"})).json()["models"]
                 for row in g["rows"] if row["variant"] == "Maxx (DV220)")
    assert plist["exShowroom"] == OEM_MAXX_DV220
    assert plist["oemSyncedAt"]


@pytest.mark.asyncio
async def test_coulson_status_hides_password(client):
    r = await client.get("/api/integrations/coulson")
    assert r.status_code == 200
    assert "password" not in r.json()
    assert "sessionToken" not in r.json()


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
    assert body["username"] == "dealer.user"
    assert "secret" not in str(body)


def test_basic_auth_matches_browser_btoa():
    import base64
    expected = base64.b64encode(b"user:pass:coulson").decode("ascii")
    assert coulson_client.basic_auth_value("user", "pass") == expected


def test_masked_username_is_not_a_login():
    assert oem_sync.looks_masked_username("va***r")
    assert not oem_sync.looks_masked_username("vaibhav.akar")
    assert oem_sync.mask_username("va***r") == ""


@pytest.mark.asyncio
async def test_save_rejects_masked_username(client, monkeypatch):
    called = []
    monkeypatch.setattr(coulson_client, "login", lambda u, p: called.append(u) or "tok")
    r = await client.put("/api/integrations/coulson",
                         json={"username": "va***r", "password": "secret"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loginOk"] is False
    assert "hint" in (body.get("lastError") or "").lower()
    assert called == []
    assert "secret" not in str(body)


@pytest.mark.asyncio
async def test_owner_status_returns_full_username(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "tok")
    await client.put("/api/integrations/coulson",
                     json={"username": "vaibhav.akar", "password": "secret"})
    r = await client.get("/api/integrations/coulson")
    assert r.status_code == 200
    body = r.json()
    assert body["username"] == "vaibhav.akar"
    assert "secret" not in str(body)


@pytest.mark.asyncio
async def test_executive_status_masks_username(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "tok")
    await client.put("/api/integrations/coulson",
                     json={"username": "vaibhav.akar", "password": "secret"})
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    assert r.status_code == 200, r.text
    token = r.json()["token"]
    r = await client.get("/api/integrations/coulson",
                         headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == oem_sync.mask_username("vaibhav.akar")
    assert r.json()["username"] != "vaibhav.akar"


@pytest.mark.asyncio
async def test_settings_credentials_win_over_env(client, monkeypatch):
    monkeypatch.setenv("COULSON_USERNAME", "env.user")
    monkeypatch.setenv("COULSON_PASSWORD", "env-secret")
    await oem_sync.save_credentials(server.db, "dealer.user", "secret")
    user, pw, src = await oem_sync.resolve_credentials(server.db)
    assert src == "settings"
    assert user == "dealer.user"
    assert pw == "secret"


@pytest.mark.asyncio
async def test_save_verifies_typed_password_not_env(client, monkeypatch):
    monkeypatch.setenv("COULSON_USERNAME", "env.user")
    monkeypatch.setenv("COULSON_PASSWORD", "env-secret")
    seen = []
    monkeypatch.setattr(coulson_client, "login", lambda u, p: seen.append((u, p)) or "tok")
    r = await client.put("/api/integrations/coulson",
                         json={"username": "vaibhav.akar", "password": "typed-secret"})
    assert r.status_code == 200, r.text
    assert r.json()["loginOk"] is True
    assert seen == [("vaibhav.akar", "typed-secret")]
    assert "typed-secret" not in str(r.json())
    assert "env-secret" not in str(r.json())


@pytest.mark.asyncio
async def test_retry_without_password_after_failure(client, monkeypatch):
    def _boom(u, p):
        raise coulson_client.CoulsonError("Username/password is not valid, Please try again", status=203)
    monkeypatch.setattr(coulson_client, "login", _boom)
    r = await client.put("/api/integrations/coulson",
                         json={"username": "vaibhav.akar", "password": "wrong"})
    assert r.json()["loginOk"] is False
    called = {"n": 0}

    def _count(u, p):
        called["n"] += 1
        raise coulson_client.CoulsonError("nope")

    monkeypatch.setattr(coulson_client, "login", _count)
    r = await client.put("/api/integrations/coulson",
                         json={"username": "vaibhav.akar", "password": ""})
    assert r.json()["loginOk"] is False
    assert called["n"] == 0
    assert "password" in (r.json().get("lastError") or "").lower()


# ============================ reported live: correct credentials still refused
def test_a_pasted_password_is_trimmed_before_it_is_encoded():
    """A password pasted from a note carries a trailing space or newline, and
    Coulson then answers "Username/password is not valid" — which reads exactly
    like getting the secret wrong. The username was already trimmed; the
    password was not."""
    import base64
    expected = base64.b64encode(b"user:pass:coulson").decode("ascii")
    assert coulson_client.basic_auth_value(
        coulson_client.clean_credential("  user "),
        coulson_client.clean_credential("pass\n")) == expected


def test_clean_credential_leaves_the_middle_alone():
    """Only the ends. A space inside a password is part of the password."""
    assert coulson_client.clean_credential("  a b c  ") == "a b c"
    assert coulson_client.clean_credential("") == ""
    assert coulson_client.clean_credential(None) == ""


def test_a_redirect_is_reported_rather_than_read_as_a_bad_password(monkeypatch):
    """A 302 must not be followed and must not be reported as a bad password."""
    capture = {}

    class FakeResp:
        status_code = 302
        headers = {"location": "https://elsewhere.example/api/v1/login"}
        content = b""
        reason_phrase = "Found"

        def json(self):
            return {}

    class FakeClient:
        def __init__(self, **kw):
            capture["follow"] = kw.get("follow_redirects")
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, headers=None, **kw):
            return FakeResp()

    monkeypatch.setattr(coulson_client.httpx, "Client", FakeClient)
    with pytest.raises(coulson_client.CoulsonError) as err:
        coulson_client.login("user", "pass")
    assert capture["follow"] is False
    assert "redirected" in str(err.value)
    assert "credentials" in str(err.value)


def test_login_posts_an_empty_body_like_the_coulson_spa(monkeypatch):
    """The dealer site is `new Request(url, {method:'POST'})` — no body, no Content-Type."""
    capture = {}

    class FakeResp:
        status_code = 200
        headers = {}
        content = b'{"success":true,"data":{"token":"tok"}}'
        reason_phrase = "OK"

        def json(self):
            return {"success": True, "data": {"token": "tok"}}

    class FakeClient:
        def __init__(self, **kw):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def post(self, url, headers=None, content=None, data=None, json=None, **kw):
            capture["url"] = url
            capture["headers"] = headers or {}
            capture["content"] = content
            capture["data"] = data
            capture["json"] = json
            capture["extra"] = kw
            return FakeResp()

    monkeypatch.setattr(coulson_client.httpx, "Client", FakeClient)
    assert coulson_client.login("vaibhav.akar", "secret") == "tok"
    assert capture["content"] is None
    assert capture["data"] is None
    assert capture["json"] is None
    hdrs = capture["headers"]
    assert "Content-Type" not in hdrs and "content-type" not in hdrs
    assert hdrs["Authorization"].startswith("Basic ")
    assert hdrs["Origin"] == "https://coulson.eulerlogistics.com"
    assert "/login" in capture["url"]


def test_diagnose_treats_http_203_as_a_refused_login(monkeypatch):
    def boom(user, pw):
        raise coulson_client.CoulsonError(
            "Username/password is not valid, Please try again", status=203)
    monkeypatch.setattr(coulson_client, "login", boom)
    d = coulson_client.diagnose("vaibhav.akar", "secret")
    assert d["ok"] is False
    assert d["status"] == 203
    assert "not valid" in (d["coulsonSaid"] or "").lower()
    assert "secret" not in json.dumps(d)



def test_diagnose_reports_what_was_sent_without_the_password(monkeypatch):
    def boom(user, pw):
        raise coulson_client.CoulsonError("Username/password is not valid", status=401)
    monkeypatch.setattr(coulson_client, "login", boom)

    d = coulson_client.diagnose("vaibhav.akar", "s3cr3t-value")
    assert d["ok"] is False
    assert d["status"] == 401
    assert d["usernameSent"] == "vaibhav.akar"
    assert d["passwordLength"] == len("s3cr3t-value")
    assert d["appSegment"] == "coulson"
    assert "base64" in d["encoding"]
    # The secret must never travel back to the browser or into an audit row.
    assert "s3cr3t-value" not in json.dumps(d)
    # A 401 with a clean password from this server is Euler refusing a
    # login that already works on their own site — not an app-segment mixup.
    assert "Railway" in d["hint"] or "paste" in d["hint"].lower()


def test_diagnose_calls_out_a_pasted_password(monkeypatch):
    def boom(user, pw):
        raise coulson_client.CoulsonError("Username/password is not valid", status=401)
    monkeypatch.setattr(coulson_client, "login", boom)

    d = coulson_client.diagnose("vaibhav.akar", " s3cr3t \n")
    assert d["passwordHadWhitespace"] is True
    assert d["passwordLength"] == len("s3cr3t")
    assert "trimmed" in d["hint"]


def test_diagnose_tells_unreachable_apart_from_rejected(monkeypatch):
    def boom(user, pw):
        raise coulson_client.CoulsonError("Coulson unreachable: timed out")
    monkeypatch.setattr(coulson_client, "login", boom)

    d = coulson_client.diagnose("vaibhav.akar", "whatever")
    assert d["status"] is None
    assert "not a password problem" in d["hint"]


def test_diagnose_makes_exactly_one_attempt(monkeypatch):
    """A retry loop against a real portal locks the account out."""
    calls = []

    def boom(user, pw):
        calls.append((user, pw))
        raise coulson_client.CoulsonError("Username/password is not valid", status=401)
    monkeypatch.setattr(coulson_client, "login", boom)

    coulson_client.diagnose("vaibhav.akar", "nope")
    assert len(calls) == 1


def test_diagnose_reports_success_plainly(monkeypatch):
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "token")
    d = coulson_client.diagnose("vaibhav.akar", "right")
    assert d["ok"] is True and d["status"] is None
    assert "accepted" in d["hint"]


@pytest.mark.asyncio
async def test_the_diagnose_endpoint_is_owner_only(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    tok = r.json()["token"]
    res = await client.post("/api/integrations/coulson/diagnose", json={},
                            headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_the_diagnose_endpoint_falls_back_to_the_saved_login(client, monkeypatch):
    """Pressing Test with the password box empty should still test the stored
    credentials rather than reporting an empty username."""
    seen = {}

    def fake_login(user, pw):
        seen["user"], seen["pw"] = user, pw
        return "token"
    monkeypatch.setattr(coulson_client, "login", fake_login)

    await client.put("/api/integrations/coulson",
                     json={"username": "vaibhav.akar", "password": "storedpass"})
    r = await client.post("/api/integrations/coulson/diagnose", json={})
    assert r.status_code == 200, r.text
    assert r.json()["usernameSent"] == "vaibhav.akar"
    assert seen["user"] == "vaibhav.akar" and seen["pw"] == "storedpass"


def test_only_the_login_refuses_redirects():
    """Blast radius: a dropped credential is misreported as a bad password only
    on the LOGIN. Breaking a data GET that legitimately redirects would trade one
    failure for another, so the data calls keep urllib's default behaviour."""
    import inspect
    src = inspect.getsource(coulson_client.login)
    assert "follow_redirects=False" in src
    assert "follow_redirects" not in inspect.getsource(coulson_client.get_json)
    # ...and the default is still to follow.
    sig = inspect.signature(coulson_client._request)
    assert sig.parameters["follow_redirects"].default is True


def _coulson_jwt(username="vaibhav.akar", exp_offset=3600, application="coulson"):
    import time
    import jwt as pyjwt
    return pyjwt.encode(
        {"application": application, "username": username, "sub": username,
         "exp": int(time.time()) + exp_offset},
        "not-euler-secret", algorithm="HS256")


def test_session_token_strips_paste_artefacts_and_reads_claims():
    raw = _coulson_jwt()
    wrapped = f'  "Bearer {raw}"  '
    claims = coulson_client.parse_session_token(wrapped)
    assert claims["application"] == "coulson"
    assert coulson_client.session_username(claims) == "vaibhav.akar"
    assert coulson_client.clean_session_token(wrapped) == raw


def test_session_token_rejects_expiry_and_the_wrong_app():
    with pytest.raises(coulson_client.CoulsonError) as expired:
        coulson_client.parse_session_token(_coulson_jwt(exp_offset=-10))
    assert "expired" in str(expired.value).lower()
    with pytest.raises(coulson_client.CoulsonError) as other:
        coulson_client.parse_session_token(_coulson_jwt(application="other-app"))
    assert "coulson" in str(other.value).lower()
    with pytest.raises(coulson_client.CoulsonError):
        coulson_client.parse_session_token("not-a-jwt")


@pytest.mark.asyncio
async def test_save_session_does_not_call_euler_login(client, monkeypatch):
    """A pasted coulson_auth is already issued. Hitting /login would only
    risk locking the password Euler already refused from this server."""
    calls = {"login": 0, "models": 0}

    def boom(*a, **k):
        calls["login"] += 1
        raise AssertionError("euler-auth login must not run for a pasted session")

    monkeypatch.setattr(coulson_client, "login", boom)
    monkeypatch.setattr(
        coulson_client, "fetch_sap_models",
        lambda token: calls.__setitem__("models", calls["models"] + 1) or [])

    tok = _coulson_jwt()
    r = await client.put("/api/integrations/coulson",
                         json={"sessionToken": f"Bearer {tok}"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loginOk"] is True
    assert body["hasSession"] is True
    assert body["configured"] is True
    assert body["username"] == "vaibhav.akar"
    assert calls["login"] == 0 and calls["models"] == 1
    dumped = json.dumps(body)
    assert "sessionToken" not in body
    assert tok not in dumped
    assert "not-euler-secret" not in dumped
    assert "deliveredMissingVehicleIds" not in body


@pytest.mark.asyncio
async def test_save_session_still_saves_when_coulson_ping_is_down(client, monkeypatch):
    """A valid JWT must persist even when Coulson's inventory API hangs."""
    monkeypatch.setattr(
        coulson_client, "login",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("login")))
    monkeypatch.setattr(
        coulson_client, "fetch_sap_models",
        lambda token: (_ for _ in ()).throw(
            coulson_client.CoulsonError("Coulson unreachable: timed out")))
    tok = _coulson_jwt()
    r = await client.put("/api/integrations/coulson", json={"sessionToken": tok})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loginOk"] is True
    assert body["hasSession"] is True
    assert body["username"] == "vaibhav.akar"
    stored = await server.db["system"].find_one({"_id": "coulson"})
    assert stored.get("sessionToken") == tok


@pytest.mark.asyncio
async def test_sync_uses_pasted_session_and_skips_password_login(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])

    def boom(*a, **k):
        raise AssertionError("login must not run when a live session is stored")

    monkeypatch.setattr(coulson_client, "login", boom)
    tok = _coulson_jwt()
    saved = await client.put("/api/integrations/coulson", json={"sessionToken": tok})
    assert saved.json()["loginOk"] is True
    r = await client.post("/api/integrations/coulson/sync", json={})
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True
    assert r.json()["credentialSource"] == "session"
    assert tok not in r.text


@pytest.mark.asyncio
async def test_expired_session_is_not_sent_to_coulson(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    tok = _coulson_jwt()
    await client.put("/api/integrations/coulson", json={"sessionToken": tok})
    # Overwrite with an expired JWT as if time passed.
    expired = _coulson_jwt(exp_offset=-60)
    await server.db["system"].update_one(
        {"_id": "coulson"}, {"$set": {"sessionToken": expired}})
    st = (await client.get("/api/integrations/coulson")).json()
    assert st["sessionExpired"] is True
    assert st["hasSession"] is False
    r = await client.post("/api/integrations/coulson/sync", json={})
    assert r.status_code == 502
    assert "expired" in r.text.lower()
    assert expired not in r.text


@pytest.mark.asyncio
async def test_delivered_chassis_is_dropped_from_yard(client):
    await server.db.oem_inventory.insert_one({
        "chassis": "MD9GONE001", "model": "Turbo Max", "variant": "City (PV)", "exShowroom": 650000})
    await server.db.leads.insert_one({
        "leadId": "LD-INV-DROP", "chassisNumber": "MD9GONE001",
        "deliveryStatus": "Delivered", "currentStatus": "Delivered",
        "accountStatus": "Active", "deliveryDate": "2026-09-02"})
    n = await oem_sync.drop_delivered_from_inventory(server.db)
    assert n == 1
    assert await server.db.oem_inventory.find_one({"chassis": "MD9GONE001"}) is None


@pytest.mark.asyncio
async def test_august_booking_is_not_repriced_for_sept_turbo(client):
    """Turbo +15k from 1 Sep must not move last month's booked files."""
    await server.db.leads.insert_one({
        "leadId": "LD-AUG-TURBO", "customerName": "Aug Book",
        "interestedModel": "Turbo Max", "variant": "City (PV)",
        "accountStatus": "Active", "deliveryStatus": "Pending",
        "currentStatus": "Booked", "bookingDate": "2026-08-20",
        "exShowroom": 650000, "customerPayable": 650000,
        "customerOutstanding": 20000, "totalReceived": 0,
        "priceStructureSaved": True,
    })
    row = {"model": "Turbo Max", "variant": "City (PV)", "exShowroom": 665000}
    out = await server.reprice_leads_for_price_row(row, {"exShowroom"}, None)
    assert out["repricedCount"] == 0
    reasons = " ".join(s.get("reason") or "" for s in out["skipped"])
    assert "1 Sep" in reasons
    lead = await server.db.leads.find_one({"leadId": "LD-AUG-TURBO"})
    assert lead["exShowroom"] == 650000


def test_storm_lr_yard_row_matches_storm_lead():
    row = {"model": "Storm LR", "variant": "Storm LR200", "chassis": "MD9STORMYARD1"}
    assert oem_sync.inventory_row_matches_lead(row, "Storm", "Storm LR (PV) Reg C7 6.6kWh")
    turbo = {"model": "Turbo Max", "variant": "City (PV)", "chassis": "MD9TURBO1"}
    assert not oem_sync.inventory_row_matches_lead(turbo, "Storm", "Storm LR (PV) Reg C7 6.6kWh")
    canonical = {"model": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh"}
    assert oem_sync.inventory_row_matches_lead(canonical, "Storm", "Storm LR (PV) Reg C7 6.6kWh")


@pytest.mark.asyncio
async def test_inventory_family_filter_returns_unmatched_storm_lr(client):
    await server.db.oem_inventory.delete_many({})
    await server.db.oem_inventory.insert_many([
        {"chassis": "MD9STORMFAM01", "model": "Storm LR", "variant": "Storm LR200"},
        {"chassis": "MD9TURBOFAM01", "model": "Turbo Max", "variant": "City (PV)"},
    ])
    fam = (await client.get("/api/inventory", params={
        "model": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh", "family": True,
    })).json()
    chassis = [r["chassis"] for r in fam]
    assert "MD9STORMFAM01" in chassis
    assert "MD9TURBOFAM01" not in chassis

    exact = (await client.get("/api/inventory", params={"model": "Storm"})).json()
    assert all(r.get("model") == "Storm" for r in exact)


@pytest.mark.asyncio
async def test_august_delivered_does_not_drop_live_yard(client):
    await server.db.oem_inventory.insert_one({
        "chassis": "MD9AUGSTILL", "model": "Storm LR", "variant": "Storm LR200"})
    await server.db.leads.insert_one({
        "leadId": "LD-AUG-DEL", "chassisNumber": "MD9AUGSTILL",
        "deliveryStatus": "Delivered", "currentStatus": "Delivered",
        "accountStatus": "Active", "deliveryDate": "2026-08-20"})
    n = await oem_sync.drop_delivered_from_inventory(server.db)
    assert n == 0
    assert await server.db.oem_inventory.find_one({"chassis": "MD9AUGSTILL"}) is not None


@pytest.mark.asyncio
async def test_cancelled_sept_delivery_does_not_drop_yard(client):
    await server.db.oem_inventory.insert_one({
        "chassis": "MD9CANCELLED", "model": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh"})
    await server.db.leads.insert_one({
        "leadId": "LD-SEP-CANCEL", "chassisNumber": "MD9CANCELLED",
        "deliveryStatus": "Delivered", "currentStatus": "Lost",
        "accountStatus": "Cancelled", "dealCancelled": True,
        "deliveryDate": "2026-09-02"})
    n = await oem_sync.drop_delivered_from_inventory(server.db)
    assert n == 0
    assert await server.db.oem_inventory.find_one({"chassis": "MD9CANCELLED"}) is not None


@pytest.mark.asyncio
async def test_expired_session_renews_with_saved_password(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])

    renewed = _coulson_jwt(exp_offset=3600)
    monkeypatch.setattr(coulson_client, "login", lambda user, pw: renewed)

    await server.db["system"].update_one(
        {"_id": "coulson"},
        {"$set": {
            "username": "vaibhav.akar", "password": "saved-pass",
            "sessionToken": _coulson_jwt(exp_offset=-60),
        }},
        upsert=True)
    token, src = await oem_sync._access_token(server.db)
    assert src == "password-renew"
    assert token == renewed
    stored = await server.db["system"].find_one({"_id": "coulson"})
    assert stored.get("sessionToken") == renewed


def test_claim_statuses_include_expansion_team_and_bill_posted():
    assert "Expansion Team Approval Pending" in coulson_client.CLAIM_STATUSES
    assert "Bill Posted in SAP" in coulson_client.CLAIM_STATUSES
    assert "Dealer Development Department Approval Pending" in coulson_client.CLAIM_STATUSES


def test_status_counts_prefers_claim_analytics_path(monkeypatch):
    seen = []

    def fake_get_json(token, path, params=None):
        seen.append(path)
        if path == "claim-analytics/status-counts":
            return {"success": True, "data": {"RM Approval Pending": 4}}
        raise coulson_client.CoulsonError("nope", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    assert coulson_client.fetch_claim_status_counts("tok") == {"RM Approval Pending": 4}
    assert seen[0] == "claim-analytics/status-counts"


def test_status_counts_falls_back_to_legacy_path(monkeypatch):
    def fake_get_json(token, path, params=None):
        if path == "claim-analytics/status-counts":
            raise coulson_client.CoulsonError("missing", status=404)
        if path == "status-counts":
            return {"success": True, "data": {"Settled": 9}}
        raise coulson_client.CoulsonError("nope", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    assert coulson_client.fetch_claim_status_counts("tok") == {"Settled": 9}


def test_page_rows_uses_page_index_when_offset_one_is_a_new_page(monkeypatch):
    pages = {
        0: [{"id": "a"}, {"id": "b"}],
        1: [{"id": "c"}, {"id": "d"}],
        2: [{"id": "e"}],
    }

    def fake_get_json(token, path, params=None):
        off = int((params or {}).get("offset") or 0)
        return {"success": True, "data": pages.get(off, []), "extras": {"total_count": 5}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client._page_rows("tok", "debit-note", limit=2)
    assert [r["id"] for r in rows] == ["a", "b", "c", "d", "e"]


def test_data_timeout_is_longer_than_login():
    assert coulson_client.LOGIN_TIMEOUT == 25
    assert coulson_client.DATA_TIMEOUT >= 90
    assert coulson_client.INVENTORY_MAX_ROWS > 5000


def test_timeouterror_becomes_coulson_error(monkeypatch):
    def boom(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(coulson_client.urllib.request, "urlopen", boom)
    with pytest.raises(coulson_client.CoulsonError, match="timed out"):
        coulson_client.get_json("tok", "sap-vehicle-models")


def test_inventory_keeps_first_page_when_later_page_fails(monkeypatch):
    def fake_get_json(token, path, params=None):
        offset = int((params or {}).get("offset") or 0)
        if offset == 0:
            return {"success": True, "data": [{"chassis": "MD9PAGE1"}],
                    "extras": {"total_count": 400}}
        raise coulson_client.CoulsonError("Coulson timed out after 90s")

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_inventory_by_status("tok", "SOLD", limit=1)
    assert [r["chassis"] for r in rows] == ["MD9PAGE1"]


def test_inventory_pages_past_the_old_5000_cap(monkeypatch):
    def fake_get_json(token, path, params=None):
        offset = int((params or {}).get("offset") or 0)
        limit = int((params or {}).get("limit") or 200)
        if offset >= 5600:
            return {"success": True, "data": [], "extras": {"total_count": 5600}}
        chunk = [{"chassis": f"MD9P{offset + i:05d}"} for i in range(limit)]
        return {"success": True, "data": chunk, "extras": {"total_count": 5600}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_inventory_by_status("tok", "SOLD", limit=200)
    assert len(rows) == 5600


def test_merge_overlays_invoice_onto_sold_tab_chassis():
    rows = [{
        "chassis": "MD9EVDAD26K217183",
        "model": "Turbo", "variant": "Range Maxx",
        "load_body": "FB", "updated_load_body": "DV220",
        "_coulsonStatus": "SOLD",
    }]
    coulson_client._merge_vehicle_rows(rows, [{
        "chassis": "MD9EVDAD26K217183",
        "invoice_number": "AF-122-I26270228",
        "customer_name": "MessengerSCS",
        "status": "CREATED",
    }], "INVOICED")
    assert len(rows) == 1
    assert rows[0]["invoice_number"] == "AF-122-I26270228"
    assert rows[0]["updated_load_body"] == "DV220"
    assert rows[0]["_coulsonStatus"] == "INVOICED"


def test_sold_inventory_merges_vehicle_invoices(monkeypatch):
    """Chassis billed today live on Vehicle Invoices, not only the Sold tab."""
    def fake_get_json(token, path, params=None):
        if path == "vehicle-inventory/transfer":
            return {"success": True, "data": [{
                "chassis": "MD9EVDAD26J17964",
                "customer_name": "Nanag Ram Prajapat",
                "invoice_number": "AF-122-I26278215",
                "created_at": "2026-10-15",
            }], "extras": {"total_count": 1}}
        if path == "dealer/invoice/vehicle":
            return {"success": True, "data": [{
                "chassis": "MD9EVDAD26K217428",
                "registration_number": "EMCS-8598",
                "customer_name": "RADHE RADHE PLASTIC",
                "customer_phone": "9352347959",
                "invoice_creation_ts": "2026-10-16T13:34:38.000Z",
                "invoice_number": "AF-TODAY-1",
                "status": "CREATED",
            }], "extras": {"total_count": 1}}
        raise coulson_client.CoulsonError("not found", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_sold_inventory("tok", limit=200)
    chassis = {r["chassis"] for r in rows}
    assert "MD9EVDAD26J17964" in chassis
    assert "MD9EVDAD26K217428" in chassis
    today = next(r for r in rows if r["chassis"] == "MD9EVDAD26K217428")
    assert today["_coulsonStatus"] == "INVOICED"
    assert oem_sync.vehicle_sold_date(today) == "2026-10-16"
    assert oem_sync.vehicle_mobile(today) == "9352347959"


def test_invoice_model_filled_from_chassis_transfer(monkeypatch):
    """Vehicle Invoices omit model; transfer still has it after billing."""
    def fake_get_json(token, path, params=None):
        params = params or {}
        if path == "vehicle-inventory/transfer":
            if str(params.get("chassis") or "") == "MD9EVDAD26K217428":
                return {"success": True, "data": [{
                    "chassis": "MD9EVDAD26K217428",
                    "model": "Turbo", "variant": "Range Maxx",
                    "sap_vehicle_model_id": "oem-maxx-pv",
                    "sap_product_name": "TURBO RANGEMAXX PV",
                }]}
            return {"success": True, "data": [], "extras": {"total_count": 0}}
        if path == "dealer/invoice/vehicle":
            return {"success": True, "data": [{
                "chassis": "MD9EVDAD26K217428",
                "customer_name": "RADHE RADHE PLASTIC",
                "customer_phone": "9352347959",
                "invoice_creation_ts": "2026-10-16T13:34:38.000Z",
                "invoice_number": "AF-TODAY-1",
                "status": "CREATED",
            }], "extras": {"total_count": 1}}
        raise coulson_client.CoulsonError("not found", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_sold_inventory("tok", limit=200)
    hit = next(r for r in rows if r["chassis"] == "MD9EVDAD26K217428")
    assert hit["model"] == "Turbo"
    assert hit["variant"] == "Range Maxx"
    assert hit["sap_product_name"] == "TURBO RANGEMAXX PV"


def test_sold_inventory_reraises_when_every_source_fails(monkeypatch):
    def boom(token, path, params=None):
        raise coulson_client.CoulsonError("Coulson timed out after 90s")

    monkeypatch.setattr(coulson_client, "get_json", boom)
    with pytest.raises(coulson_client.CoulsonError, match="timed out"):
        coulson_client.fetch_sold_inventory("tok")


def test_sold_inventory_can_skip_model_fill(monkeypatch):
    calls = {"n": 0}

    def fake_get_json(token, path, params=None):
        if path == "vehicle-inventory/transfer":
            if (params or {}).get("chassis"):
                calls["n"] += 1
            return {"success": True, "data": [
                {"chassis": "MD9SOLDONLY01", "invoice_number": "AF-1"},
            ], "extras": {"total_count": 1}}
        if path == "dealer/invoice/vehicle":
            return {"success": True, "data": [
                {"chassis": "MD9INVONLY01", "invoice_number": "AF-2", "status": "CREATED"},
            ], "extras": {"total_count": 1}}
        raise coulson_client.CoulsonError("nope", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_sold_inventory("tok", fill_models=False)
    assert calls["n"] == 0
    assert {r["chassis"] for r in rows} == {"MD9SOLDONLY01", "MD9INVONLY01"}


def test_invoice_max_rows_stops_paging(monkeypatch):
    pages = {
        0: [{"chassis": "MD9A"}, {"chassis": "MD9B"}],
        1: [{"chassis": "MD9C"}, {"chassis": "MD9D"}],
        2: [{"chassis": "MD9E"}],
    }
    hits = {"n": 0}

    def fake_get_json(token, path, params=None):
        hits["n"] += 1
        off = int((params or {}).get("offset") or 0)
        return {"success": True, "data": pages.get(off, []), "extras": {"total_count": 5}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows, ok = coulson_client.fetch_raw_vehicle_invoices("tok", limit=2, max_rows=2)
    assert [r["chassis"] for r in rows] == ["MD9A", "MD9B"]
    assert ok is False
    assert hits["n"] == 1


def test_vehicle_invoices_skip_cancelled(monkeypatch):
    def fake_get_json(token, path, params=None):
        if path == "dealer/invoice/vehicle":
            return {"success": True, "data": [
                {"chassis": "MD9CANCEL01", "invoice_number": "AF-C",
                 "status": "CANCELLED", "invoice_creation_ts": "2026-10-16T10:00:00Z"},
                {"chassis": "MD9EVDAD26K217428", "invoice_number": "AF-OK",
                 "status": "CREATED", "invoice_creation_ts": "2026-10-16T11:00:00Z",
                 "customer_phone": "9352347959"},
            ], "extras": {"total_count": 2}}
        raise coulson_client.CoulsonError("nope", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_vehicle_invoices("tok")
    assert [r["chassis"] for r in rows] == ["MD9EVDAD26K217428"]
    assert rows.invoice_list_ok is True
    assert [r["chassis"] for r in rows.cancelled] == ["MD9CANCEL01"]


def test_dealer_invoices_page_by_index(monkeypatch):
    pages = {
        0: [{"chassis": "MD9P00"}, {"chassis": "MD9P01"}],
        1: [{"chassis": "MD9P10"}, {"chassis": "MD9P11"}],
        2: [{"chassis": "MD9P20"}],
    }

    def fake_get_json(token, path, params=None):
        assert path == "dealer/invoice/vehicle"
        off = int((params or {}).get("offset") or 0)
        return {"success": True, "data": pages.get(off, []), "extras": {"total_count": 5}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_vehicle_invoices("tok", limit=2)
    assert [r["chassis"] for r in rows] == [
        "MD9P00", "MD9P01", "MD9P10", "MD9P11", "MD9P20",
    ]


def test_dealer_invoices_row_skip_when_offset_slides(monkeypatch):
    all_rows = [{"chassis": f"MD9R{i:03d}"} for i in range(5)]

    def fake_get_json(token, path, params=None):
        off = int((params or {}).get("offset") or 0)
        lim = int((params or {}).get("limit") or 2)
        return {"success": True, "data": all_rows[off:off + lim],
                "extras": {"total_count": 5}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_vehicle_invoices("tok", limit=2)
    assert [r["chassis"] for r in rows] == [f"MD9R{i:03d}" for i in range(5)]


def test_vehicle_invoices_404_is_not_fatal(monkeypatch):
    def fake_get_json(token, path, params=None):
        if path == "vehicle-inventory/transfer":
            return {"success": True, "data": [{"chassis": "MD9SOLDONLY01"}],
                    "extras": {"total_count": 1}}
        raise coulson_client.CoulsonError("nope", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_sold_inventory("tok")
    assert [r["chassis"] for r in rows] == ["MD9SOLDONLY01"]


@pytest.mark.asyncio
async def test_sync_empty_sold_does_not_wipe_oem_sold(client, monkeypatch):
    chassis = "MD9SYNCKEEP01"
    await server.db.oem_sold.delete_many({})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9811100777", "invoiceNumber": "CINV-KEEP2",
        "model": "Turbo Max", "variant": "Maxx (PV)", "coulsonStatus": "SOLD",
    })
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])
    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    row = await server.db.oem_sold.find_one({"chassis": chassis})
    assert row is not None
    assert row["invoiceNumber"] == "CINV-KEEP2"


@pytest.mark.asyncio
async def test_short_invoice_pull_upserts_today_without_wiping(client):
    """Vehicle Invoices (234 billed) must add today's chassis onto yesterday's Sold list."""
    await server.db.oem_sold.delete_many({})
    await server.db.oem_sold.insert_many([
        {"chassis": "MD9EVDAD26J17964", "mobile": "9602689086",
         "invoiceNumber": "AF-OLD", "soldDate": "2026-10-15", "coulsonStatus": "SOLD"},
        {"chassis": "MD9EVDAD26J17194", "mobile": "9929968641",
         "invoiceNumber": "AF-OLD2", "soldDate": "2026-10-11", "coulsonStatus": "SOLD"},
    ])
    n = await oem_sync.replace_sold_inventory(server.db, [{
        "chassis": "MD9EVDAD26K217428",
        "customer_name": "RADHE RADHE PLASTIC",
        "customer_phone": "9352347959",
        "invoice_number": "AF-TODAY-1",
        "date": "16 Oct 2026",
        "_coulsonStatus": "INVOICED",
    }], {}, {}, complete=False)
    assert n == 3
    today = await server.db.oem_sold.find_one({"chassis": "MD9EVDAD26K217428"})
    assert today["soldDate"] == "2026-10-16"
    assert today["mobile"] == "9352347959"
    assert today["invoiceNumber"] == "AF-TODAY-1"
    kept = await server.db.oem_sold.find_one({"chassis": "MD9EVDAD26J17964"})
    assert kept["invoiceNumber"] == "AF-OLD"


@pytest.mark.asyncio
async def test_replace_sold_keeps_yard_model_on_invoice_row(client):
    chassis = "MD9YARDMODEL01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.oem_inventory.delete_many({"chassis": chassis})
    await server.db.oem_inventory.insert_one({
        "chassis": chassis, "model": "Turbo Max", "variant": "Maxx (PV)",
        "oemSkuKey": "turbo.maxx.pv",
    })
    await oem_sync.replace_sold_inventory(server.db, [{
        "chassis": chassis, "customer_name": "Yard Keep",
        "invoice_number": "AF-YARD-1", "_coulsonStatus": "INVOICED",
    }], {}, {}, complete=True)
    row = await server.db.oem_sold.find_one({"chassis": chassis})
    assert row["model"] == "Turbo Max"
    assert row["variant"] == "Maxx (PV)"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.oem_inventory.delete_many({"chassis": chassis})


def test_sold_inventory_drops_cancelled_even_when_sold_tab_still_lists_it(monkeypatch):
    """Invoice List CANCELLED wins over the Sold tab still showing the chassis."""
    dead = "MD9EVDAD26J217760"
    live = "MD9EVDAD26J217577"

    def fake_get_json(token, path, params=None):
        if path == "vehicle-inventory/transfer":
            return {"success": True, "data": [
                {"chassis": dead, "customer_name": "Hrithik Chopra",
                 "customer_phone": "7297021177", "invoice_number": "AF-122-I26270204"},
                {"chassis": live, "customer_name": "Hrithik Chopra",
                 "customer_phone": "7297021177", "invoice_number": "AF-122-I26270209"},
            ], "extras": {"total_count": 2}}
        if path == "dealer/invoice/vehicle":
            return {"success": True, "data": [
                {"chassis": dead, "invoice_number": "AF-122-I26270204",
                 "status": "CANCELLED", "invoiceStatus": "CANCELLED",
                 "customer_name": "HRITHIK CHOPRA", "customer_phone": "7297821177",
                 "registration_number": "EMCS-7684",
                 "invoice_creation_ts": "2026-09-28T15:09:38.000Z"},
                {"chassis": live, "invoice_number": "AF-122-I26270209",
                 "status": "CREATED",
                 "customer_name": "HRITHIK CHOPRA", "customer_phone": "7297821177",
                 "registration_number": "RJ14GV5082",
                 "invoice_creation_ts": "2026-10-05T12:48:29.000Z"},
            ], "extras": {"total_count": 2}}
        raise coulson_client.CoulsonError("not found", status=404)

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_sold_inventory("tok", limit=200)
    chassis_ids = {r["chassis"] for r in rows}
    assert live in chassis_ids
    assert dead not in chassis_ids
    assert rows.invoice_list_ok is True
    assert {r["chassis"] for r in rows.cancelled} == {dead}


def test_held_inventory_merges_booked_pilot_demo(monkeypatch):
    def fake_get_json(token, path, params=None):
        assert path == "vehicle-inventory/transfer"
        status = str((params or {}).get("vehicle_status") or "")
        if status == "BOOKED":
            return {"success": True, "data": [
                {"chassis": "MD9BOOKED01", "model": "Turbo"},
            ], "extras": {"total_count": 1}}
        if status == "PILOT":
            return {"success": True, "data": [
                {"chassis": "MD9PILOT01", "model": "Storm"},
            ], "extras": {"total_count": 1}}
        if status == "DEMO":
            return {"success": True, "data": [
                {"chassis": "MD9DEMO01", "model": "HiCity"},
            ], "extras": {"total_count": 1}}
        return {"success": True, "data": [], "extras": {"total_count": 0}}

    monkeypatch.setattr(coulson_client, "get_json", fake_get_json)
    rows = coulson_client.fetch_held_inventory("tok")
    by = {r["chassis"]: r.get("_coulsonStatus") for r in rows}
    assert by == {
        "MD9BOOKED01": "BOOKED",
        "MD9PILOT01": "PILOT",
        "MD9DEMO01": "DEMO",
    }


@pytest.mark.asyncio
async def test_replace_cancelled_strips_sold_and_held_sync(client):
    dead = "MD9CANCELSTILL01"
    booked = "MD9HELDBOOK01"
    yard = "MD9YARDPRESENT01"
    await server.db.oem_sold.delete_many({"chassis": dead})
    await server.db.oem_inventory.delete_many({"chassis": {"$in": [booked, yard]}})
    await server.db.oem_inventory.insert_one({
        "chassis": yard, "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    await server.db.oem_sold.insert_one({
        "chassis": dead, "invoiceNumber": "AF-DEAD", "coulsonStatus": "SOLD",
    })
    kept_old = "MD9OLDCANCEL01"
    await server.db.oem_cancelled_invoices.delete_many({"chassis": kept_old})
    await server.db.oem_cancelled_invoices.insert_one({
        "chassis": kept_old, "invoiceNumber": "AF-OLD-C", "invoiceStatus": "CANCELLED",
    })
    n = await oem_sync.replace_cancelled_invoices(server.db, [{
        "chassis": dead, "invoice_number": "AF-DEAD", "status": "CANCELLED",
    }], ok=False)
    assert await server.db.oem_cancelled_invoices.find_one({"chassis": kept_old})
    assert await server.db.oem_cancelled_invoices.find_one({"chassis": dead})
    n = await oem_sync.replace_cancelled_invoices(server.db, [{
        "chassis": dead, "invoice_number": "AF-DEAD", "status": "CANCELLED",
    }], ok=True)
    assert n == 1
    assert await server.db.oem_sold.find_one({"chassis": dead}) is None
    held_n = await oem_sync.replace_held_inventory(server.db, [
        {"chassis": booked, "model": "Turbo", "variant": "Range Maxx",
         "_coulsonStatus": "BOOKED"},
        {"chassis": yard, "model": "Turbo", "variant": "Range Maxx",
         "_coulsonStatus": "BOOKED"},
    ], {}, {})
    assert held_n == 1
    assert await server.db.oem_inventory.find_one({"chassis": yard}) is not None
    held = await oem_sync.list_held_inventory(server.db)
    assert [r["chassis"] for r in held] == [booked]
    assert held[0]["coulsonStatus"] == "BOOKED"

