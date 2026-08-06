"""Iteration 7: LEAD EDIT + /api/share/dashboard (All Leads panel) regression tests."""
import os
import requests
import pytest

def _load_base():
    v = os.environ.get("REACT_APP_BACKEND_URL")
    if not v:
        try:
            for line in open("/app/frontend/.env"):
                if line.startswith("REACT_APP_BACKEND_URL="):
                    v = line.split("=", 1)[1].strip()
                    break
        except Exception:
            pass
    assert v, "REACT_APP_BACKEND_URL missing"
    return v.rstrip("/")

BASE = _load_base()


def _login(email, password):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": password}, timeout=15)
    assert r.status_code == 200, f"login {email}: {r.status_code} {r.text}"
    return r.json()["accessToken"] if "accessToken" in r.json() else r.json().get("token") or r.json().get("access_token")


@pytest.fixture(scope="module")
def owner_token():
    # figure out token key
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("accessToken", "access_token", "token"):
        if k in j:
            return j[k]
    raise AssertionError(f"no token in {j}")


@pytest.fixture(scope="module")
def exec_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "executive@euler.com", "password": "euler@123"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("accessToken", "access_token", "token"):
        if k in j:
            return j[k]
    raise AssertionError(f"no token in {j}")


# ---- LEAD EDIT ----
LEAD_ID = "LD26000001"


def test_get_lead_baseline(owner_token):
    r = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers={"Authorization": f"Bearer {owner_token}"}, timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["leadId"] == LEAD_ID
    assert "customerName" in d


def test_update_lead_requires_auth():
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"customerName": "X"}, timeout=15)
    assert r.status_code in (401, 403), f"expected auth error, got {r.status_code}"


def test_update_lead_owner_success(owner_token):
    hdr = {"Authorization": f"Bearer {owner_token}"}
    # snapshot original
    orig = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    orig_payable = orig.get("customerPayable")
    orig_received = orig.get("totalReceived")
    orig_outstanding = orig.get("customerOutstanding")

    # send FULL body (as the frontend does — prefilled)
    body = {
        "customerName": orig.get("customerName", ""),
        "mobile": orig.get("mobile", ""),
        "altMobile": orig.get("altMobile", ""),
        "village": orig.get("village", ""),
        "city": orig.get("city", ""),
        "leadSource": orig.get("leadSource", "Walk-in"),
        "interestedModel": orig.get("interestedModel", ""),
        "variant": orig.get("variant", ""),
        "executive": orig.get("executive", ""),
        "currentStatus": orig.get("currentStatus", "New"),
        "priority": orig.get("priority", "Normal"),
        "budget": orig.get("budget", 0),
        "remarks": orig.get("remarks", ""),
        "financeRequired": orig.get("financeRequired", "No"),
        "exchangeRequired": orig.get("exchangeRequired", "No"),
        "nextFollowupDate": orig.get("nextFollowupDate"),
    }
    # make edits
    body["customerName"] = "TEST_Edited Name"
    body["currentStatus"] = "In Progress"
    body["mobile"] = "9876500001"

    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=body, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    upd = r.json()
    assert upd["customerName"] == "TEST_Edited Name"
    assert upd["currentStatus"] == "In Progress"
    assert upd["mobile"] == "9876500001"

    # GET to verify persistence
    g = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    assert g["customerName"] == "TEST_Edited Name"
    assert g["currentStatus"] == "In Progress"
    assert g["mobile"] == "9876500001"

    # commercials should not be wiped -- may be recomputed but must be consistent
    if orig_payable is not None:
        assert "customerPayable" in g, "customerPayable dropped after edit!"
    if orig_received is not None:
        assert g.get("totalReceived") == orig_received, f"totalReceived changed: {orig_received}->{g.get('totalReceived')}"
    if orig_outstanding is not None:
        assert "customerOutstanding" in g

    # restore original
    body["customerName"] = orig.get("customerName", "")
    body["currentStatus"] = orig.get("currentStatus", "New")
    body["mobile"] = orig.get("mobile", "")
    rr = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=body, headers=hdr, timeout=20)
    assert rr.status_code == 200


# ---- SHARE DASHBOARD ----
def test_share_dashboard_public():
    r = requests.get(f"{BASE}/api/share/dashboard", timeout=15)
    assert r.status_code == 200, r.text
    d = r.json()
    assert "totalLeads" in d
    assert "allLeads" in d and isinstance(d["allLeads"], list)
    assert d["totalLeads"] >= 1
    assert len(d["allLeads"]) == d["totalLeads"]
    row = d["allLeads"][0]
    assert "name" in row
    assert "status" in row


# ---- REGRESSION ----
def test_owner_dashboard(owner_token):
    r = requests.get(f"{BASE}/api/dashboard", headers={"Authorization": f"Bearer {owner_token}"}, timeout=15)
    assert r.status_code == 200


def test_owner_only_reports_owner(owner_token):
    for path in ("/api/reports/insurance-payout", "/api/reports/dealer-earnings"):
        r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {owner_token}"}, timeout=15)
        assert r.status_code == 200, f"{path}: {r.status_code} {r.text}"


def test_owner_only_reports_denied_for_exec(exec_token):
    for path in ("/api/reports/insurance-payout", "/api/reports/dealer-earnings"):
        r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {exec_token}"}, timeout=15)
        assert r.status_code in (401, 403), f"{path}: exec should be denied, got {r.status_code}"


def test_price_master(owner_token):
    r = requests.get(f"{BASE}/api/price-master", headers={"Authorization": f"Bearer {owner_token}"}, timeout=15)
    assert r.status_code == 200


def test_backfill_owner_only(owner_token, exec_token):
    r = requests.post(f"{BASE}/api/integrations/gsheets/backfill", headers={"Authorization": f"Bearer {owner_token}"}, timeout=30)
    assert r.status_code == 200
    r2 = requests.post(f"{BASE}/api/integrations/gsheets/backfill", headers={"Authorization": f"Bearer {exec_token}"}, timeout=30)
    assert r2.status_code in (401, 403)
