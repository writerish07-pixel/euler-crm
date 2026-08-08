"""Iteration 15: PUT /api/leads/{lead_id} partial-update regression tests.

Reproduces and closes the production data-loss bug: Swagger's "Try it out" panel
pre-fills the full LeadIn body with placeholder defaults ("string", "", 0) and,
because every field was technically present in the JSON, exclude_unset=True
included all of them -- silently overwriting every untouched field on the lead.

Fix under test: LeadUpdateIn (all fields Optional, no non-null defaults, extra
forbidden) + explicit LEAD_SYSTEM_FIELDS stripping + rejection of the literal
"string" placeholder. These tests prove: (a-d) partial updates only touch the
fields sent, (e) an allowed field can still be intentionally cleared, and
(f) system/financial fields can't be corrupted through this endpoint.
"""
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
LEAD_ID = "LD26000001"


@pytest.fixture(scope="module")
def owner_token():
    r = requests.post(f"{BASE}/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"}, timeout=15)
    assert r.status_code == 200, r.text
    j = r.json()
    for k in ("accessToken", "access_token", "token"):
        if k in j:
            return j[k]
    raise AssertionError(f"no token in {j}")


@pytest.fixture()
def hdr(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture()
def snapshot(hdr):
    """Snapshot the lead before each test and restore every profile field after,
    regardless of pass/fail, so tests don't leak state into each other."""
    before = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    yield before
    restore = {k: before.get(k) for k in (
        "customerName", "mobile", "altMobile", "village", "city", "leadSource",
        "interestedModel", "variant", "executive", "currentStatus", "priority",
        "budget", "remarks", "financeRequired", "exchangeRequired", "nextFollowupDate",
    )}
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=restore, headers=hdr, timeout=20)
    assert r.status_code == 200, f"restore failed: {r.text}"


def _profile_fields_except(before, changed_keys):
    """Every profile field NOT part of this update, for asserting no-drift."""
    keys = ("customerName", "mobile", "altMobile", "village", "city", "leadSource",
            "interestedModel", "variant", "executive", "currentStatus", "priority",
            "budget", "remarks", "financeRequired", "exchangeRequired", "nextFollowupDate")
    return {k: before.get(k) for k in keys if k not in changed_keys}


# ---- 8a: updating only currentStatus preserves every other field ----
def test_partial_update_only_status(hdr, snapshot):
    before = snapshot
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"currentStatus": "Contacted"}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["currentStatus"] == "Contacted"
    unchanged = _profile_fields_except(before, {"currentStatus"})
    for k, v in unchanged.items():
        assert after.get(k) == v, f"field '{k}' drifted: {v!r} -> {after.get(k)!r}"


# ---- 8b: updating only executive preserves every other field ----
def test_partial_update_only_executive(hdr, snapshot):
    before = snapshot
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"executive": "Lokesh"}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["executive"] == "Lokesh"
    unchanged = _profile_fields_except(before, {"executive"})
    for k, v in unchanged.items():
        assert after.get(k) == v, f"field '{k}' drifted: {v!r} -> {after.get(k)!r}"


# ---- 8c: updating only nextFollowupDate preserves every other field ----
def test_partial_update_only_followup_date(hdr, snapshot):
    before = snapshot
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"nextFollowupDate": "2026-09-01"}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["nextFollowupDate"] == "2026-09-01"
    unchanged = _profile_fields_except(before, {"nextFollowupDate"})
    for k, v in unchanged.items():
        assert after.get(k) == v, f"field '{k}' drifted: {v!r} -> {after.get(k)!r}"


# ---- 8d: updating multiple selected fields preserves all remaining fields ----
def test_partial_update_multiple_fields(hdr, snapshot):
    before = snapshot
    changed = {"priority": "High", "remarks": "TEST_iter15 multi-field update"}
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=changed, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    assert after["priority"] == "High"
    assert after["remarks"] == "TEST_iter15 multi-field update"
    unchanged = _profile_fields_except(before, set(changed.keys()))
    for k, v in unchanged.items():
        assert after.get(k) == v, f"field '{k}' drifted: {v!r} -> {after.get(k)!r}"


# ---- 8e: explicitly clearing an allowed field works intentionally ----
def test_explicit_clear_of_nullable_field(hdr, snapshot):
    # first give it a real value
    r1 = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"nextFollowupDate": "2026-09-05"}, headers=hdr, timeout=20)
    assert r1.status_code == 200, r1.text
    assert r1.json()["nextFollowupDate"] == "2026-09-05"
    # then explicitly clear it
    r2 = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"nextFollowupDate": None}, headers=hdr, timeout=20)
    assert r2.status_code == 200, r2.text
    assert r2.json().get("nextFollowupDate") in (None, ""), "explicit clear did not take effect"


# ---- 8f: system-calculated financial fields cannot be corrupted through lead update ----
def test_financial_fields_rejected(hdr, snapshot):
    before = snapshot
    attack = {
        "currentStatus": "Contacted",
        "customerOutstanding": 999999, "companyOutstanding": 999999,
        "totalReceived": 999999, "customerPayable": 999999, "grossVehicleCost": 999999,
        "outstandingAmount": 999999,
    }
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=attack, headers=hdr, timeout=20)
    # extra='forbid' -> 422, unknown/extra fields rejected outright
    assert r.status_code == 422, f"expected 422 rejecting financial fields, got {r.status_code}: {r.text}"
    g = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    for k in ("customerOutstanding", "companyOutstanding", "totalReceived", "customerPayable",
              "grossVehicleCost", "outstandingAmount"):
        assert g.get(k) != 999999, f"financial field '{k}' was corrupted!"


def test_financial_fields_rejected_even_alone(hdr, snapshot):
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"customerPayable": 1}, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


def test_system_fields_rejected(hdr, snapshot):
    for field, val in (("leadId", "LD99999999"), ("createdDate", "2020-01-01"), ("accountStatus", "Closed")):
        r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={field: val}, headers=hdr, timeout=20)
        assert r.status_code == 422, f"{field}: expected 422, got {r.status_code}: {r.text}"
    g = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    assert g["leadId"] == LEAD_ID
    assert g.get("accountStatus") != "Closed"


# ---- Swagger placeholder guard: the exact bug from the report ----
def test_swagger_placeholder_body_rejected(hdr, snapshot):
    """Simulates hitting 'Execute' on Swagger's unedited example body: every field
    present with its auto-generated placeholder. Must be rejected, not persisted."""
    before = snapshot
    swagger_default_body = {
        "customerName": "string", "mobile": "string", "altMobile": "string",
        "village": "string", "city": "string", "leadSource": "string",
        "interestedModel": "string", "variant": "string", "executive": "string",
        "currentStatus": "string", "priority": "string", "budget": 0,
        "remarks": "string", "financeRequired": "string", "exchangeRequired": "string",
        "nextFollowupDate": "string",
    }
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json=swagger_default_body, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422 rejecting placeholder body, got {r.status_code}: {r.text}"
    g = requests.get(f"{BASE}/api/leads/{LEAD_ID}", headers=hdr, timeout=15).json()
    assert g["customerName"] == before["customerName"], "customerName was overwritten with placeholder!"
    assert g.get("mobile") == before.get("mobile"), "mobile was overwritten with placeholder!"


# ---- Empty body is a no-op, not an error ----
def test_empty_body_is_noop(hdr, snapshot):
    before = snapshot
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    after = r.json()
    for k in ("customerName", "mobile", "currentStatus", "executive"):
        assert after.get(k) == before.get(k)


# ---- Master-list validation (requirement 6) ----
def test_invalid_priority_rejected(hdr, snapshot):
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"priority": "NotARealPriority_TEST"}, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422 for invalid priority, got {r.status_code}: {r.text}"


def test_invalid_finance_required_rejected(hdr, snapshot):
    r = requests.put(f"{BASE}/api/leads/{LEAD_ID}", json={"financeRequired": "Maybe"}, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422 for invalid financeRequired, got {r.status_code}: {r.text}"


# ---- Regression: Create Lead and Get Lead still work (requirement 11) ----
def test_create_and_get_lead_still_work(hdr):
    body = {"customerName": "TEST_iter15 Create Regression", "mobile": "9998887770",
            "interestedModel": "HiLoad", "leadSource": "Walk-in"}
    r = requests.post(f"{BASE}/api/leads", json=body, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    created = r.json()
    assert created["customerName"] == "TEST_iter15 Create Regression"
    assert created["leadId"].startswith("LD26")

    g = requests.get(f"{BASE}/api/leads/{created['leadId']}", headers=hdr, timeout=15)
    assert g.status_code == 200
    assert g.json()["mobile"] == "9998887770"

    requests.delete(f"{BASE}/api/leads/{created['leadId']}", headers=hdr, timeout=20)
