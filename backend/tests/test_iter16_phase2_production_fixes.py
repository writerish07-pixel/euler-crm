"""Iteration 16: regression tests for the 5 approved Phase 2 production fixes.

A. Claim Register must not exclude Delivered (or Finance Process) leads (P0).
B. POST /leads/{id}/payments must reject amount<=0 (P1).
C. Scheme-before-Booking must resolve to the same Company Outstanding as
   Scheme-after-Booking for the same business date (P1) -- proven with the
   real July rtoInsuranceBenefit / August rtoBenefit+insuranceBenefit split.
D. Price Master / Scheme Master mutations must be owner-only (P1).
E. POST /admin/reseed must be owner-only (P1).

Matches the existing integration-test convention: `requests` against a live
deployment (REACT_APP_BACKEND_URL), owner/exec token fixtures. This file does
not touch LD26000012/LD26000013 and does not call DELETE /leads/{id} or any
admin reset/reseed endpoint against real data -- it creates disposable
CLOUD-QA-prefixed leads/rows and leaves master-data rows in place (Price
Master / Scheme Master have no per-row cleanup needed for a create-then-verify
authorization check that fails before any row is written).
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


@pytest.fixture(scope="module")
def owner_token():
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


@pytest.fixture()
def hdr(owner_token):
    return {"Authorization": f"Bearer {owner_token}"}


@pytest.fixture()
def exec_hdr(exec_token):
    return {"Authorization": f"Bearer {exec_token}"}


PRICE = {
    "exShowroom": 300000, "rto": 20000, "insuranceAmount": 15000, "accessoriesAmount": 8000,
    "handlingCharges": 4000, "trc": 1500, "fastag": 600, "extendedWarranty": 6000,
    "rsaAmc": 2500, "otherCharges": 2000, "tcsApplicable": "No", "finalExchangeValue": 0,
}


def _make_lead(hdr, name, model="HiCity", variant="XR", mobile="9555500001"):
    r = requests.post(f"{BASE}/api/leads", json={
        "customerName": name, "mobile": mobile, "interestedModel": model, "variant": variant,
        "executive": "Amit", "leadSource": "Walk-in",
    }, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


# ================================================================
# A. CLAIM REGISTER survives delivery (P0)
# ================================================================
def test_claim_register_survives_delivery(hdr):
    lead_id = _make_lead(hdr, "CLOUD QA ITER16 CLAIM-DELIVERY", mobile="9555500010")
    r = requests.put(f"{BASE}/api/leads/{lead_id}/price-structure", json=PRICE, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    r = requests.post(f"{BASE}/api/leads/{lead_id}/convert-booking",
                       json={"bookingDate": "2026-08-08", "bookingAmount": PRICE["exShowroom"] + 20600, "paymentMode": "Cash"},
                       headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    r = requests.put(f"{BASE}/api/leads/{lead_id}/scheme",
                      json={"consumerDiscount": 25000, "loyaltyBonus": 10000, "benefitMode": "Full Benefit"},
                      headers=hdr, timeout=20)
    assert r.status_code == 200, r.text

    claims_before = requests.get(f"{BASE}/api/claims", headers=hdr, timeout=15).json()
    rows_before = sorted([(c["componentKey"], c["claimAmount"]) for c in claims_before if c["leadId"] == lead_id])
    assert rows_before, "expected claim rows for a booked lead with a real Scheme Master match"
    total_before = sum(amt for _, amt in rows_before)

    # clear outstanding, then deliver
    lead = requests.get(f"{BASE}/api/leads/{lead_id}", headers=hdr, timeout=15).json()
    outstanding = lead.get("customerOutstanding", 0)
    if outstanding > 0:
        r = requests.post(f"{BASE}/api/leads/{lead_id}/payments", json={"amount": outstanding, "paymentMode": "Cash"}, headers=hdr, timeout=20)
        assert r.status_code == 200, r.text
    r = requests.put(f"{BASE}/api/leads/{lead_id}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "insuranceAgentId": "IA26AGENT1", "insurerName": "QA Insurers", "invoiceNumber": "INV-ITER16-1", "chassisNumber": "CH-ITER16-1", "delivered": "Yes",
    }, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["currentStatus"] == "Delivered"

    claims_after = requests.get(f"{BASE}/api/claims", headers=hdr, timeout=15).json()
    rows_after = sorted([(c["componentKey"], c["claimAmount"]) for c in claims_after if c["leadId"] == lead_id])
    assert rows_after, "REGRESSION: claim rows disappeared after Delivery (the P0 defect)"
    assert rows_after == rows_before, f"claim rows changed after delivery: {rows_before} -> {rows_after}"
    assert sum(amt for _, amt in rows_after) == total_before


def test_claim_register_includes_finance_process_leads(hdr):
    """Finance Process leads should also remain visible in the Claim Register,
    matching the same regex used by the Owner Commercial Report / OEM Claim Dashboard."""
    lead_id = _make_lead(hdr, "CLOUD QA ITER16 CLAIM-FINANCE", mobile="9555500011")
    requests.put(f"{BASE}/api/leads/{lead_id}/price-structure", json=PRICE, headers=hdr, timeout=20)
    requests.post(f"{BASE}/api/leads/{lead_id}/convert-booking",
                  json={"bookingDate": "2026-08-08", "bookingAmount": 0}, headers=hdr, timeout=20)
    requests.put(f"{BASE}/api/leads/{lead_id}/scheme",
                 json={"consumerDiscount": 25000, "benefitMode": "Full Benefit"}, headers=hdr, timeout=20)
    r = requests.put(f"{BASE}/api/leads/{lead_id}", json={"currentStatus": "Finance Process"}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    claims = requests.get(f"{BASE}/api/claims", headers=hdr, timeout=15).json()
    assert any(c["leadId"] == lead_id for c in claims), "Finance Process lead should still appear in the Claim Register"


# ================================================================
# B. Negative / zero payments rejected (P1)
# ================================================================
def test_negative_payment_rejected(hdr):
    lead_id = _make_lead(hdr, "CLOUD QA ITER16 NEG-PAYMENT", mobile="9555500020")
    requests.put(f"{BASE}/api/leads/{lead_id}/price-structure", json=PRICE, headers=hdr, timeout=20)
    before = requests.get(f"{BASE}/api/leads/{lead_id}", headers=hdr, timeout=15).json()
    r = requests.post(f"{BASE}/api/leads/{lead_id}/payments", json={"amount": -500, "paymentMode": "Cash"}, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
    after = requests.get(f"{BASE}/api/leads/{lead_id}", headers=hdr, timeout=15).json()
    assert after.get("totalReceived", 0) == before.get("totalReceived", 0)
    payments = requests.get(f"{BASE}/api/payments", params={"lead_id": lead_id}, headers=hdr, timeout=15).json()
    assert not any(p["amount"] < 0 for p in payments), "a negative-amount payment was persisted"


def test_zero_payment_rejected(hdr):
    lead_id = _make_lead(hdr, "CLOUD QA ITER16 ZERO-PAYMENT", mobile="9555500021")
    requests.put(f"{BASE}/api/leads/{lead_id}/price-structure", json=PRICE, headers=hdr, timeout=20)
    r = requests.post(f"{BASE}/api/leads/{lead_id}/payments", json={"amount": 0, "paymentMode": "Cash"}, headers=hdr, timeout=20)
    assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"


def test_valid_positive_payment_still_works(hdr):
    lead_id = _make_lead(hdr, "CLOUD QA ITER16 VALID-PAYMENT", mobile="9555500022")
    requests.put(f"{BASE}/api/leads/{lead_id}/price-structure", json=PRICE, headers=hdr, timeout=20)
    r = requests.post(f"{BASE}/api/leads/{lead_id}/payments", json={"amount": 1000, "paymentMode": "Cash"}, headers=hdr, timeout=20)
    assert r.status_code == 200, r.text
    assert r.json()["amount"] == 1000
    lead = requests.get(f"{BASE}/api/leads/{lead_id}", headers=hdr, timeout=15).json()
    assert lead["totalReceived"] == 1000


# ================================================================
# C. Scheme-before-Booking == Scheme-after-Booking (P1)
# ================================================================
def test_scheme_before_and_after_booking_match():
    """Company Outstanding must be identical (55000) whether Scheme is applied
    before or after Booking, for a model whose entitlement componentKey changed
    between circular months (HiCity/XR: July's combined rtoInsuranceBenefit vs
    August's split rtoBenefit+insuranceBenefit). This does not need auth against
    the live deployment -- it's a pure function test against commercial.py, run
    directly so it also documents the exact expected numbers."""
    import sys
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    import json as _json
    import commercial as ce

    data_path = os.path.join(os.path.dirname(__file__), "..", "data", "euler_raw.json")
    raw = _json.load(open(data_path))
    header = raw["Scheme Master"][0]
    scheme_rows = [dict(zip(header, r)) for r in raw["Scheme Master"][1:]]
    scheme_rows = [{
        "schemeMonth": d["Scheme Month"], "effectiveFrom": d["Effective From"], "effectiveTo": d["Effective To"],
        "model": d["Model"], "variant": d["Variant"], "component": d["Component"], "componentKey": d["Component Key"],
        "dealerShare": d["Dealer Share"], "companyShare": d["Company Share"], "totalBenefit": d["Total Benefit"],
        "status": d["Status"],
    } for d in scheme_rows]

    master_before_booking = ce.get_scheme_shares_for_lead("HiCity", "XR", "", scheme_rows)  # no bookingDate yet
    master_after_booking = ce.get_scheme_shares_for_lead("HiCity", "XR", "2026-08-08", scheme_rows)  # real date

    total_before = sum(v["companyShare"] for v in master_before_booking.values())
    total_after = sum(v["companyShare"] for v in master_after_booking.values())

    assert sorted(master_before_booking.keys()) == sorted(master_after_booking.keys()), \
        f"componentKey sets differ: {sorted(master_before_booking.keys())} vs {sorted(master_after_booking.keys())}"
    assert total_after == 55000, f"expected 55000 for a real booking date, got {total_after}"
    assert total_before == 55000, (
        f"REGRESSION: Scheme-before-Booking produced {total_before}, not 55000 -- "
        f"the RTO+Insurance entitlement is being double-counted (would be 75000 on the pre-fix code)"
    )
    assert total_before == total_after, "Scheme-before-Booking and Scheme-after-Booking must resolve identically"


# ================================================================
# D. Price Master / Scheme Master mutations owner-only (P1)
# ================================================================
PRICE_ROW = {"model": "CLOUD_QA_ITER16", "variant": "TEST", "exShowroom": 100000}
SCHEME_ROW = {"model": "CLOUD_QA_ITER16", "variant": "TEST", "component": "Test", "componentKey": "consumerDiscount",
              "dealerShare": 0, "companyShare": 1000}


def test_price_master_create_owner_only(hdr, exec_hdr):
    r_exec = requests.post(f"{BASE}/api/price-master", json=PRICE_ROW, headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive should be denied, got {r_exec.status_code}: {r_exec.text}"
    r_owner = requests.post(f"{BASE}/api/price-master", json=PRICE_ROW, headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner should succeed, got {r_owner.status_code}: {r_owner.text}"
    price_id = r_owner.json()["priceId"]

    r_exec = requests.put(f"{BASE}/api/price-master/{price_id}", json=PRICE_ROW, headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive PUT should be denied, got {r_exec.status_code}"
    r_owner = requests.put(f"{BASE}/api/price-master/{price_id}", json=PRICE_ROW, headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner PUT should succeed, got {r_owner.status_code}: {r_owner.text}"

    r_exec = requests.delete(f"{BASE}/api/price-master/{price_id}", headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive DELETE should be denied, got {r_exec.status_code}"
    r_owner = requests.delete(f"{BASE}/api/price-master/{price_id}", headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner DELETE should succeed, got {r_owner.status_code}: {r_owner.text}"


def test_price_master_read_unaffected(hdr, exec_hdr):
    r = requests.get(f"{BASE}/api/price-master", headers=exec_hdr, timeout=15)
    assert r.status_code == 200, "GET /price-master must remain open to executives"
    r = requests.get(f"{BASE}/api/price-master", headers=hdr, timeout=15)
    assert r.status_code == 200


def test_scheme_master_create_owner_only(hdr, exec_hdr):
    r_exec = requests.post(f"{BASE}/api/scheme-master", json=SCHEME_ROW, headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive should be denied, got {r_exec.status_code}: {r_exec.text}"
    r_owner = requests.post(f"{BASE}/api/scheme-master", json=SCHEME_ROW, headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner should succeed, got {r_owner.status_code}: {r_owner.text}"
    scheme_id = r_owner.json()["schemeId"]

    r_exec = requests.put(f"{BASE}/api/scheme-master/{scheme_id}", json=SCHEME_ROW, headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive PUT should be denied, got {r_exec.status_code}"
    r_owner = requests.put(f"{BASE}/api/scheme-master/{scheme_id}", json=SCHEME_ROW, headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner PUT should succeed, got {r_owner.status_code}: {r_owner.text}"

    r_exec = requests.delete(f"{BASE}/api/scheme-master/{scheme_id}", headers=exec_hdr, timeout=20)
    assert r_exec.status_code in (401, 403), f"executive DELETE should be denied, got {r_exec.status_code}"
    r_owner = requests.delete(f"{BASE}/api/scheme-master/{scheme_id}", headers=hdr, timeout=20)
    assert r_owner.status_code == 200, f"owner DELETE should succeed, got {r_owner.status_code}: {r_owner.text}"


def test_scheme_master_read_unaffected(hdr, exec_hdr):
    r = requests.get(f"{BASE}/api/scheme-master", headers=exec_hdr, timeout=15)
    assert r.status_code == 200, "GET /scheme-master must remain open to executives"


# ================================================================
# E. /admin/reseed owner-only (P1) -- NEVER actually invoked
# ================================================================
def test_admin_reseed_requires_auth():
    r = requests.post(f"{BASE}/api/admin/reseed", timeout=15)
    assert r.status_code in (401, 403), f"expected auth error with no token, got {r.status_code}"


def test_admin_reseed_denied_for_executive(exec_hdr):
    r = requests.post(f"{BASE}/api/admin/reseed", headers=exec_hdr, timeout=15)
    assert r.status_code in (401, 403), f"executive should be denied, got {r.status_code}: {r.text}"


# NOTE: intentionally NOT testing "owner -> allowed" by actually calling reseed
# (force=True wipes/reseeds master+sample data) -- verifying the owner-only gate
# via the two denial cases above is sufficient without touching real data, per
# the explicit instruction not to run reseed against production.
