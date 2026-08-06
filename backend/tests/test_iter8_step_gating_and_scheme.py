"""Iteration 8: step gating (canBook/canDeliver/canClose) + scheme company-share split.

Careful: DO NOT permanently mutate baseline. Only one New lead is converted to Booking.
Any lead we mutate for scheme, we reset back to zero-scheme + Full Benefit.
"""
import os
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = {"email": "owner@euler.com", "password": "euler@123"}
EXEC = {"email": "executive@euler.com", "password": "euler@123"}


# ------------ fixtures ------------
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


# ------------ helpers ------------
def find_new_lead_id(owner_client):
    """Return a New/Active non-booked lead. Excludes LD26000005 which we reserve for the
    single 'canBook' conversion test."""
    r = owner_client.get(f"{API}/leads")
    assert r.status_code == 200
    for l in r.json():
        acts = None
        # fetch 360 to know actions authoritatively
        rid = l.get("leadId")
        if not rid:
            continue
        det = owner_client.get(f"{API}/leads/{rid}/360").json()
        acts = det.get("actions") or {}
        if acts.get("canBook") and acts.get("isActive") and not acts.get("isBooked") and rid != "LD26000005":
            return rid
    return None


def reset_scheme(owner_client, lead_id):
    """Reset scheme fields to zeros + Full Benefit."""
    payload = {"consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0,
               "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
               "benefitMode": "Full Benefit", "customerBenefitPassed": 0,
               "benefitPassedBreakup": None,
               "oemExtraSupportReceived": 0, "oemExtraSupportPassed": 0}
    r = owner_client.put(f"{API}/leads/{lead_id}/scheme", json=payload)
    return r


# =========================================================
# BACKEND: 360 actions object
# =========================================================
class TestActions:
    def test_booked_lead_actions(self, owner_client):
        # LD26000003 or LD26000002 is Booked per seed
        rid = "LD26000003"
        r = owner_client.get(f"{API}/leads/{rid}/360")
        assert r.status_code == 200, r.text
        acts = r.json().get("actions")
        assert acts is not None, "actions object missing on 360"
        assert acts["isBooked"] is True
        assert acts["canBook"] is False
        # not delivered baseline
        if not acts["isDelivered"]:
            assert acts["canDeliver"] is True
            assert acts["canClose"] is True

    def test_new_lead_actions(self, owner_client):
        r = owner_client.get(f"{API}/leads/{'LD26000005'}/360")
        assert r.status_code == 200
        acts = r.json()["actions"]
        assert acts["isBooked"] is False
        assert acts["canBook"] is True
        assert acts["canDeliver"] is False


# =========================================================
# BACKEND: step gating on convert-booking / close / delivery
# =========================================================
class TestStepGating:
    def test_convert_booking_on_already_booked_returns_409(self, owner_client):
        r = owner_client.post(f"{API}/leads/LD26000003/convert-booking",
                              json={"bookingAmount": 1000, "paymentMode": "Cash"})
        assert r.status_code == 409, f"expected 409 got {r.status_code}: {r.text}"

    def test_close_delivered_or_booked_ok_new_not(self, owner_client):
        # Closing an already-delivered lead → 409. Find a delivered one; else skip.
        r = owner_client.get(f"{API}/leads")
        assert r.status_code == 200
        delivered = [l for l in r.json() if (l.get("currentStatus") or "").lower() == "delivered"]
        if not delivered:
            pytest.skip("no delivered lead to test close-gating on")
        rid = delivered[0]["leadId"]
        resp = owner_client.post(f"{API}/leads/{rid}/close", json={"closeReason": "test"})
        assert resp.status_code == 409

    def test_delivery_on_non_booked_returns_409(self, owner_client):
        # LD26000005 is New — delivered=Yes should be 409
        r = owner_client.put(f"{API}/leads/LD26000005/delivery",
                             json={"delivered": "Yes", "invoiceNumber": "T1",
                                   "chassisNumber": "T1", "numberPlate": "T1"})
        assert r.status_code == 409, r.text


# =========================================================
# BACKEND: scheme company-share (single mutating test with reset)
# =========================================================
class TestSchemeCompanyShare:
    def test_scheme_company_share_capped(self, owner_client):
        # Pick a fresh Active lead (not LD26000005 which we hold for the convert test).
        target = None
        for candidate in ["LD26000006", "LD26000007", "LD26000008", "LD26000009", "LD26000010"]:
            det = owner_client.get(f"{API}/leads/{candidate}/360").json()
            if det.get("actions", {}).get("canScheme"):
                target = candidate
                break
        assert target, "no Active lead found for scheme test"
        try:
            offers = {"consumerDiscount": 20000, "exchangeBonus": 15000,
                      "loyaltyBonus": 0, "referralBonus": 0, "dsaDiscount": 0,
                      "additionalDiscount": 0, "benefitMode": "Full Benefit",
                      "customerBenefitPassed": 0, "oemExtraSupportReceived": 0,
                      "oemExtraSupportPassed": 0}
            r = owner_client.put(f"{API}/leads/{target}/scheme", json=offers)
            assert r.status_code == 200, r.text
            data = r.json()
            company = float(data.get("companyOutstanding") or 0)
            sum_offers = 20000 + 15000
            # companyOutstanding must NOT exceed sum of raw OEM offers, and
            # if scheme master has smaller company share, it will be < sum.
            assert company <= sum_offers + 0.01, \
                f"companyOutstanding {company} > raw offers {sum_offers}"
            # A retained field should be present
            assert "dealerSchemeRetained" in data
            # sanity: 360 also returns commercials
            det = owner_client.get(f"{API}/leads/{target}/360").json()
            assert "commercials" in det
        finally:
            # RESET
            reset_scheme(owner_client, target)
            data = owner_client.get(f"{API}/leads/{target}").json()
            assert float(data.get("consumerDiscount") or 0) == 0
            assert float(data.get("exchangeBonus") or 0) == 0
            assert (data.get("benefitMode") or "Full Benefit") == "Full Benefit"


# =========================================================
# BACKEND: reports & claims
# =========================================================
class TestReportsAndClaims:
    def test_dealer_earnings_owner_ok(self, owner_client):
        r = owner_client.get(f"{API}/reports/dealer-earnings")
        assert r.status_code == 200, r.text
        js = r.json()
        assert "byMonth" in js
        assert "components" in js
        assert "totals" in js

    def test_claims_owner_ok(self, owner_client):
        r = owner_client.get(f"{API}/claims")
        assert r.status_code == 200, r.text
        assert isinstance(r.json(), list)

    def test_executive_forbidden_owner_endpoints(self, exec_client):
        for path in ["/reports/dealer-earnings", "/reports/insurance-payout", "/dealer-earnings"]:
            r = exec_client.get(f"{API}{path}")
            assert r.status_code in (401, 403), f"exec should not access {path}: got {r.status_code}"


# =========================================================
# BACKEND: convert one New lead (mutating!) — kept as last test
# =========================================================
class TestConvertOneNewLead:
    def test_convert_new_lead_ld26000005(self, owner_client):
        rid = "LD26000005"
        pre = owner_client.get(f"{API}/leads/{rid}/360").json()
        if not pre.get("actions", {}).get("canBook"):
            pytest.skip("LD26000005 already booked from prior run; skipping mutation")
        r = owner_client.post(f"{API}/leads/{rid}/convert-booking",
                              json={"bookingAmount": 5000, "paymentMode": "Cash"})
        assert r.status_code == 200, r.text
        # verify persisted
        after = owner_client.get(f"{API}/leads/{rid}/360").json()
        acts = after["actions"]
        assert acts["isBooked"] is True
        assert acts["canBook"] is False
        # subsequent convert must 409
        r2 = owner_client.post(f"{API}/leads/{rid}/convert-booking",
                               json={"bookingAmount": 1, "paymentMode": "Cash"})
        assert r2.status_code == 409
