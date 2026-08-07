"""Iteration 9 backend tests: scheme-rules availability + validation, delivery/close
gating, duplicate mobile block, dealer-earnings OEM Extra Support, step-gating regression.

Rules for baseline preservation:
- Any lead we mutate for scheme MUST be reset to all-zero + Full Benefit at the end.
- Any lead we create for duplicate-mobile test MUST be deleted at the end.
- Do NOT actually close or deliver a baseline lead.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = {"email": "owner@euler.com", "password": "euler@123"}
EXEC = {"email": "executive@euler.com", "password": "euler@123"}


# ---------------- fixtures ----------------
@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login", json=OWNER, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def exec_token():
    r = requests.post(f"{API}/auth/login", json=EXEC, timeout=15)
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture()
def owner_client(owner_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {owner_token}",
                      "Content-Type": "application/json"})
    return s


@pytest.fixture()
def exec_client(exec_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {exec_token}",
                      "Content-Type": "application/json"})
    return s


def _reset_scheme(owner_client, lead_id):
    payload = {"consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0,
               "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
               "benefitMode": "Full Benefit", "customerBenefitPassed": 0,
               "benefitPassedBreakup": None,
               "oemExtraSupportReceived": 0, "oemExtraSupportPassed": 0}
    return owner_client.put(f"{API}/leads/{lead_id}/scheme", json=payload)


# =====================================================================
# A. SCHEME AVAILABILITY (scheme-rules endpoint)
# =====================================================================
class TestSchemeRules:
    def test_turbo_max_hides_consumer_discount(self, owner_client):
        r = owner_client.get(f"{API}/leads/LD26000001/scheme-rules")
        assert r.status_code == 200, r.text
        js = r.json()
        rules = js.get("rules") or {}
        assert "consumerDiscount" in rules
        cd = rules["consumerDiscount"]
        # Turbo has 0 for consumerDiscount in Scheme Master -> allowed False
        assert cd.get("allowed") is False, f"expected consumerDiscount NOT allowed for Turbo Max; got {cd}"
        # Other OEM components should be allowed with maxAmount > 0
        for key in ("exchangeBonus", "dsaDiscount", "referralBonus", "loyaltyBonus"):
            assert key in rules, f"missing {key}"
            rule = rules[key]
            assert rule.get("allowed") is True, f"{key} should be allowed for Turbo Max: {rule}"
            assert float(rule.get("maxAmount") or 0) > 0, f"{key} maxAmount must be >0 for Turbo Max: {rule}"
        # additionalDiscount always allowed
        assert rules["additionalDiscount"]["allowed"] is True

    def test_hi_load_all_five_allowed(self, owner_client):
        r = owner_client.get(f"{API}/leads/LD26000008/scheme-rules")
        assert r.status_code == 200, r.text
        rules = r.json().get("rules") or {}
        for key in ("consumerDiscount", "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount"):
            assert rules.get(key, {}).get("allowed") is True, \
                f"{key} should be allowed for Hi-Load; got {rules.get(key)}"
            assert float(rules[key].get("maxAmount") or 0) > 0


# =====================================================================
# B. SCHEME VALIDATION (PUT /scheme)
# =====================================================================
class TestSchemeValidation:
    def test_reject_unavailable_component_turbo(self, owner_client):
        # LD26000001 = Turbo Max, consumerDiscount not available
        payload = {"consumerDiscount": 5000, "exchangeBonus": 0, "loyaltyBonus": 0,
                   "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
                   "benefitMode": "Full Benefit", "customerBenefitPassed": 0}
        r = owner_client.put(f"{API}/leads/LD26000001/scheme", json=payload)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "Consumer" in detail or "consumer" in detail.lower() or "not in Scheme Master" in detail

    def test_reject_exchangebonus_above_cap(self, owner_client):
        # get cap from scheme-rules
        rules = owner_client.get(f"{API}/leads/LD26000001/scheme-rules").json()["rules"]
        cap = float(rules["exchangeBonus"]["maxAmount"])
        payload = {"consumerDiscount": 0, "exchangeBonus": cap + 5000, "loyaltyBonus": 0,
                   "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
                   "benefitMode": "Full Benefit", "customerBenefitPassed": 0}
        r = owner_client.put(f"{API}/leads/LD26000001/scheme", json=payload)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"

    def test_valid_scheme_computes_company_share(self, owner_client):
        # Use LD26000001 (Turbo Max) — exchangeBonus is allowed with cap
        rules = owner_client.get(f"{API}/leads/LD26000001/scheme-rules").json()["rules"]
        cap = float(rules["exchangeBonus"]["maxAmount"])
        # pick amount at or below cap
        offer = min(5000, cap)
        assert offer > 0
        try:
            payload = {"consumerDiscount": 0, "exchangeBonus": offer, "loyaltyBonus": 0,
                       "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
                       "benefitMode": "Full Benefit", "customerBenefitPassed": 0}
            r = owner_client.put(f"{API}/leads/LD26000001/scheme", json=payload)
            assert r.status_code == 200, r.text
            lead = r.json()
            company = float(lead.get("companyOutstanding") or 0)
            # companyOutstanding should be the company-share portion (<= offer)
            assert company <= offer + 0.01, \
                f"companyOutstanding {company} must be <= raw offer {offer} (company-share-first cap)"
            # If company share < total, the value should be strictly < offer
            company_share = float(rules["exchangeBonus"].get("companyShare") or 0)
            total = float(rules["exchangeBonus"].get("maxAmount") or 0)
            if company_share > 0 and company_share < total:
                # Not necessarily strictly less; but company side is capped
                assert company <= company_share + 0.01, \
                    f"companyOutstanding {company} exceeds Scheme Master companyShare {company_share} (company-share-first)"
        finally:
            _reset_scheme(owner_client, "LD26000001")
            back = owner_client.get(f"{API}/leads/LD26000001").json()
            assert float(back.get("exchangeBonus") or 0) == 0


# =====================================================================
# C. DELIVERY VALIDATION
# =====================================================================
class TestDeliveryValidation:
    def test_delivery_missing_checklist_returns_422(self, owner_client):
        # LD26000003 is Booked in baseline — pushing delivered=Yes with empty fields
        # must return 422 (checklist + outstanding). We do NOT persist.
        payload = {"delivered": "Yes"}
        r = owner_client.put(f"{API}/leads/LD26000003/delivery", json=payload)
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        # Ensure it references at least one checklist item OR outstanding
        keywords = ["Insurance", "insurer", "Registration", "Invoice", "invoice number",
                    "chassis", "PDI", "outstanding"]
        assert any(k.lower() in detail.lower() for k in keywords), \
            f"detail should list missing items; got: {detail}"


# =====================================================================
# D. CLOSE VALIDATION
# =====================================================================
class TestCloseValidation:
    def test_close_empty_reason_422(self, owner_client):
        # LD26000009 is a New Active lead per baseline. Empty body -> 422 (reason required).
        r = owner_client.post(f"{API}/leads/LD26000009/close", json={})
        assert r.status_code == 422, f"expected 422, got {r.status_code}: {r.text}"
        detail = r.json().get("detail", "")
        assert "reason" in detail.lower()


# =====================================================================
# E. DUPLICATE MOBILE
# =====================================================================
class TestDuplicateMobile:
    def test_duplicate_mobile_returns_409(self, owner_client):
        leads = owner_client.get(f"{API}/leads").json()
        # Find any lead with a 10-digit mobile
        target_mobile = None
        target_id = None
        import re as _re
        for l in leads:
            m = _re.sub(r"\D", "", l.get("mobile") or "")
            if len(m) >= 10:
                target_mobile = m[-10:]
                target_id = l.get("leadId")
                break
        assert target_mobile, "no existing lead with 10-digit mobile"
        payload = {"customerName": "TEST_DupMob", "mobile": target_mobile,
                   "interestedModel": "Hi-Load", "executive": "Test", "leadSource": "Walk-in"}
        r = owner_client.post(f"{API}/leads", json=payload)
        assert r.status_code == 409, f"expected 409, got {r.status_code}: {r.text}"
        # If for some reason it created, delete it
        if r.status_code == 200:
            new_id = r.json().get("leadId")
            if new_id:
                owner_client.delete(f"{API}/leads/{new_id}")


# =====================================================================
# F. DEALER EARNINGS (OEM Extra Support)
# =====================================================================
class TestDealerEarnings:
    def test_owner_dealer_earnings(self, owner_client):
        r = owner_client.get(f"{API}/reports/dealer-earnings")
        assert r.status_code == 200, r.text
        js = r.json()
        assert "byMonth" in js and "components" in js and "totals" in js
        # components is a list of {label, amount}, filtered to non-zero. Ensure the
        # structure supports 'OEM Extra Support' when present. It may be absent when 0.
        comps = js["components"]
        assert isinstance(comps, list)
        labels = [c.get("label") for c in comps]
        # Verify no error and that computation succeeded
        # If any OEM extra support retained > 0 was booked, it should appear.
        # Otherwise verify byMonth entries include 'other' key (the OEM Extra Support
        # bucket) even if 0.
        if js["byMonth"]:
            assert "other" in js["byMonth"][0], "byMonth must include 'other' (OEM Extra Support) bucket"
        # Log presence
        print(f"dealer-earnings components labels: {labels}")

    def test_exec_denied_dealer_earnings(self, exec_client):
        r = exec_client.get(f"{API}/reports/dealer-earnings")
        assert r.status_code in (401, 403), f"exec should be denied; got {r.status_code}"


# =====================================================================
# G. STEP GATING REGRESSION
# =====================================================================
class TestStepGating:
    def test_ld26000003_360_actions(self, owner_client):
        r = owner_client.get(f"{API}/leads/LD26000003/360")
        assert r.status_code == 200
        acts = r.json()["actions"]
        assert acts["isBooked"] is True
        assert acts["canBook"] is False
        assert acts["canClose"] is True

    def test_ld26000003_convert_booking_409(self, owner_client):
        r = owner_client.post(f"{API}/leads/LD26000003/convert-booking",
                              json={"bookingAmount": 1, "paymentMode": "Cash"})
        assert r.status_code == 409

    def test_ld26000009_360_actions(self, owner_client):
        r = owner_client.get(f"{API}/leads/LD26000009/360")
        assert r.status_code == 200
        acts = r.json()["actions"]
        assert acts["canBook"] is True
        assert acts["canDeliver"] is False
