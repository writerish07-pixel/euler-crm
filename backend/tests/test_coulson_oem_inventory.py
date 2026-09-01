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


@pytest.mark.asyncio
async def test_sync_uses_pasted_session_and_skips_password_login(client, monkeypatch):
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200: [])

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

