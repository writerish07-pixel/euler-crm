"""Iteration 2 backend tests: JWT auth, roles, master CRUD, share board, export, gsheets no-op."""
import os
import uuid
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
if not BASE_URL:
    envf = Path("/app/frontend/.env")
    if envf.exists():
        for line in envf.read_text().splitlines():
            if line.startswith("REACT_APP_BACKEND_URL="):
                BASE_URL = line.split("=", 1)[1].strip()
                break

assert BASE_URL, "REACT_APP_BACKEND_URL must be set"
BASE_URL = BASE_URL.rstrip("/")
API = f"{BASE_URL}/api"


# ---------------------------- fixtures
@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "owner@euler.com", "password": "euler@123"})
    assert r.status_code == 200, f"owner login failed: {r.status_code} {r.text}"
    d = r.json()
    assert d["user"]["role"] == "owner"
    assert isinstance(d["token"], str) and len(d["token"]) > 20
    return d["token"]


@pytest.fixture(scope="session")
def exec_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "executive@euler.com", "password": "euler@123"})
    assert r.status_code == 200, f"exec login failed: {r.text}"
    d = r.json()
    assert d["user"]["role"] == "executive"
    return d["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


# ---------------------------- AUTH backend
class TestAuth:
    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "owner@euler.com", "password": "WRONG"})
        assert r.status_code == 401

    def test_login_unknown_user(self):
        r = requests.post(f"{API}/auth/login",
                          json={"email": "nobody@euler.com", "password": "x"})
        assert r.status_code == 401

    def test_business_route_requires_auth(self):
        r = requests.get(f"{API}/leads")
        assert r.status_code in (401, 403)

    def test_business_route_with_token(self, owner_token):
        r = requests.get(f"{API}/leads", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_me_endpoint(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers=H(owner_token))
        assert r.status_code == 200
        assert r.json()["role"] == "owner"

    def test_invalid_token(self):
        r = requests.get(f"{API}/leads", headers={"Authorization": "Bearer garbage"})
        assert r.status_code == 401


# ---------------------------- ROLE-based restrictions
class TestRoles:
    def test_dealer_earnings_owner_ok(self, owner_token):
        r = requests.get(f"{API}/dealer-earnings", headers=H(owner_token))
        assert r.status_code == 200
        assert "rows" in r.json() and "total" in r.json()

    def test_dealer_earnings_exec_forbidden(self, exec_token):
        r = requests.get(f"{API}/dealer-earnings", headers=H(exec_token))
        assert r.status_code == 403

    def test_users_list_owner_ok(self, owner_token):
        r = requests.get(f"{API}/auth/users", headers=H(owner_token))
        assert r.status_code == 200
        emails = [u["email"] for u in r.json()]
        assert "owner@euler.com" in emails

    def test_users_list_exec_forbidden(self, exec_token):
        r = requests.get(f"{API}/auth/users", headers=H(exec_token))
        assert r.status_code == 403

    def test_users_create_exec_forbidden(self, exec_token):
        r = requests.post(f"{API}/auth/users", headers=H(exec_token),
                          json={"email": "x@x.com", "password": "y", "role": "executive"})
        assert r.status_code == 403

    def test_users_create_and_delete_owner(self, owner_token):
        email = f"test_{uuid.uuid4().hex[:8]}@euler.com"
        r = requests.post(f"{API}/auth/users", headers=H(owner_token),
                          json={"email": email, "password": "pass123",
                                "name": "TEST User", "role": "executive"})
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["email"] == email
        assert created["role"] == "executive"
        uid = created["userId"]

        # verify listing
        listing = requests.get(f"{API}/auth/users", headers=H(owner_token)).json()
        assert any(u["userId"] == uid for u in listing)

        # can now login as this user
        r2 = requests.post(f"{API}/auth/login", json={"email": email, "password": "pass123"})
        assert r2.status_code == 200
        assert r2.json()["user"]["role"] == "executive"

        # delete
        rd = requests.delete(f"{API}/auth/users/{uid}", headers=H(owner_token))
        assert rd.status_code == 200
        # verify removed
        listing2 = requests.get(f"{API}/auth/users", headers=H(owner_token)).json()
        assert not any(u["userId"] == uid for u in listing2)


# ---------------------------- MASTERS CRUD
class TestPriceMasterCRUD:
    _created = []

    def test_create_price_row(self, owner_token):
        payload = {"model": "TEST_Model", "variant": "TEST_V1", "bodyType": "Cargo",
                   "exShowroom": 111111, "rto": 5000, "insurance": 4000, "status": "active"}
        r = requests.post(f"{API}/price-master", headers=H(owner_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "priceId" in d
        assert d["model"] == "TEST_Model"
        assert d["exShowroom"] == 111111
        TestPriceMasterCRUD._created.append(d["priceId"])

        # verify via GET
        rows = requests.get(f"{API}/price-master", headers=H(owner_token),
                            params={"model": "TEST_Model"}).json()
        assert any(x["priceId"] == d["priceId"] for x in rows)

    def test_update_price_row(self, owner_token):
        assert TestPriceMasterCRUD._created, "need created row"
        pid = TestPriceMasterCRUD._created[-1]
        payload = {"model": "TEST_Model", "variant": "TEST_V1_upd", "exShowroom": 222222}
        r = requests.put(f"{API}/price-master/{pid}", headers=H(owner_token), json=payload)
        assert r.status_code == 200
        assert r.json()["exShowroom"] == 222222
        assert r.json()["variant"] == "TEST_V1_upd"

    def test_delete_price_row(self, owner_token):
        pid = TestPriceMasterCRUD._created.pop()
        r = requests.delete(f"{API}/price-master/{pid}", headers=H(owner_token))
        assert r.status_code == 200
        rows = requests.get(f"{API}/price-master", headers=H(owner_token),
                            params={"model": "TEST_Model"}).json()
        assert not any(x["priceId"] == pid for x in rows)


class TestSchemeMasterCRUD:
    _created = []

    def test_create_scheme_row(self, owner_token):
        payload = {"model": "TEST_Model", "company": "Euler",
                   "component": "TEST Consumer Discount", "componentKey": "consumerDiscount",
                   "dealerShare": 500, "companyShare": 1500, "status": "Active"}
        r = requests.post(f"{API}/scheme-master", headers=H(owner_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "schemeId" in d
        # totalBenefit auto = dealerShare+companyShare
        assert d["totalBenefit"] == 2000
        TestSchemeMasterCRUD._created.append(d["schemeId"])

    def test_update_scheme_row(self, owner_token):
        sid = TestSchemeMasterCRUD._created[-1]
        payload = {"model": "TEST_Model", "component": "Updated",
                   "componentKey": "consumerDiscount",
                   "dealerShare": 1000, "companyShare": 2000, "status": "Active"}
        r = requests.put(f"{API}/scheme-master/{sid}", headers=H(owner_token), json=payload)
        assert r.status_code == 200
        assert r.json()["totalBenefit"] == 3000

    def test_delete_scheme_row(self, owner_token):
        sid = TestSchemeMasterCRUD._created.pop()
        r = requests.delete(f"{API}/scheme-master/{sid}", headers=H(owner_token))
        assert r.status_code == 200


# ---------------------------- GSHEETS status + graceful no-op
class TestGSheetsIntegration:
    def test_status_not_configured(self, owner_token):
        r = requests.get(f"{API}/integrations/gsheets", headers=H(owner_token))
        assert r.status_code == 200
        d = r.json()
        assert d.get("enabled") is False
        assert "reason" in d or "message" in d
        # spreadsheetId key should be present (may be empty string)
        assert "spreadsheetId" in d

    def test_create_lead_succeeds_despite_disabled_sync(self, owner_token):
        r = requests.post(f"{API}/leads", headers=H(owner_token), json={
            "customerName": "TEST_GSheetsNoop", "mobile": "9999900099",
            "interestedModel": "Turbo Max", "variant": "Standard", "executive": "TEST",
        })
        assert r.status_code == 200
        lead_id = r.json()["leadId"]
        # payment also triggers append -> should still work
        rp = requests.post(f"{API}/leads/{lead_id}/payments", headers=H(owner_token),
                           json={"amount": 100, "paymentMode": "Cash"})
        assert rp.status_code == 200


# ---------------------------- EXCEL export
class TestExport:
    def test_export_xlsx(self, owner_token):
        r = requests.get(f"{API}/export", headers=H(owner_token))
        assert r.status_code == 200
        ct = r.headers.get("content-type", "")
        assert "spreadsheet" in ct or "xlsx" in ct or "openxmlformats" in ct
        assert len(r.content) > 500  # non-empty xlsx blob
        # xlsx files are zip -> start with PK
        assert r.content[:2] == b"PK"


# ---------------------------- PUBLIC share board
class TestShareBoard:
    def test_share_dashboard_public_no_auth(self):
        r = requests.get(f"{API}/share/dashboard")
        assert r.status_code == 200, r.text
        d = r.json()
        for k in ("activeBookings", "newThisMonth", "byModel"):
            assert k in d
        assert isinstance(d["byModel"], list)

    def test_share_dashboard_also_with_auth(self, owner_token):
        r = requests.get(f"{API}/share/dashboard", headers=H(owner_token))
        assert r.status_code == 200
