"""Iteration 13-14 parity & regression tests.

Covers: INS-1 insurance rate consistency, C1 extra-income + dealer earnings, H4 audit-log,
H1 dashboard KPIs (financeOutstanding/followupDue/followupOverdue), H3 claim lifecycle
(submitted/approved/ageing), H5 rsaAmc in price-structure, U4 double-submit guard,
ERP production-audit engine, owner-vs-executive gating regression, U1 end-to-end recon.

Baseline discipline: all mutations on LD26000002/003/005/006 are reverted; any docs created
in insurance/claims/finance/payments collections are removed. audit_log entries are
append-only and intentionally left in place.
"""
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "euler_crm")

OWNER = {"email": "owner@euler.com", "password": "euler@123"}
EXEC = {"email": "executive@euler.com", "password": "euler@123"}


# ------------------------------ session helpers
def _login(creds):
    r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
    assert r.status_code == 200, f"login failed for {creds['email']}: {r.status_code} {r.text}"
    j = r.json()
    return j.get("access_token") or j.get("token")


@pytest.fixture(scope="session")
def owner_token():
    return _login(OWNER)


@pytest.fixture(scope="session")
def exec_token():
    return _login(EXEC)


@pytest.fixture(scope="session")
def owner():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_login(OWNER)}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def executive():
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {_login(EXEC)}", "Content-Type": "application/json"})
    return s


@pytest.fixture(scope="session")
def mongo():
    c = MongoClient(MONGO_URL)
    return c[DB_NAME]


# =========================================================== INS-1
class TestInsuranceRate:
    """INS-1: payoutRate is stored as fraction; UI-style percent input is normalized (/100).
       Turbo Max defaults to 0.49; Hi-Load defaults to 0.365. No doc ever has rate>1."""

    created_ids = []

    def _create(self, owner, body):
        body = {"customerName": "TEST_INS", **body}
        r = owner.post(f"{API}/insurance", json=body)
        assert r.status_code == 200, f"insurance create failed: {r.status_code} {r.text}"
        return r.json()

    def test_percent_49_normalized_to_fraction(self, owner):
        body = {"model": "Turbo Max", "insuranceCompany": "TEST_ICICI", "insuranceAmount": 20000,
                "payoutRate": 49, "policyDate": "2026-01-01"}
        doc = self._create(owner, body)
        self.created_ids.append(doc["entryId"])
        assert doc["payoutRate"] == 0.49, f"expected 0.49, got {doc['payoutRate']}"
        assert doc["expectedPayout"] == 9800.0, f"expected 9800, got {doc['expectedPayout']}"

    def test_decimal_percent_365(self, owner):
        body = {"model": "HiLoad", "insuranceCompany": "TEST_ICICI",
                "insuranceAmount": 20000, "payoutRate": 36.5}
        doc = self._create(owner, body)
        self.created_ids.append(doc["entryId"])
        assert abs(doc["payoutRate"] - 0.365) < 1e-6
        assert doc["expectedPayout"] == 7300.0

    def test_turbo_max_auto_default(self, owner):
        body = {"model": "Turbo Max", "insuranceCompany": "TEST_ICICI", "insuranceAmount": 10000, "payoutRate": 0}
        doc = self._create(owner, body)
        self.created_ids.append(doc["entryId"])
        assert doc["payoutRate"] == 0.49, f"Turbo Max default should be 0.49, got {doc['payoutRate']}"

    def test_hiload_auto_default(self, owner):
        body = {"model": "Hi-Load", "insuranceCompany": "TEST_ICICI", "insuranceAmount": 10000, "payoutRate": 0}
        doc = self._create(owner, body)
        self.created_ids.append(doc["entryId"])
        assert abs(doc["payoutRate"] - 0.365) < 1e-3, f"Hi-Load default should be 0.365, got {doc['payoutRate']}"

    def test_no_doc_has_rate_over_1(self, mongo):
        bad = list(mongo.insurance.find({"payoutRate": {"$gt": 1}}))
        assert bad == [], f"Found insurance docs with payoutRate>1: {[b.get('entryId') for b in bad]}"

    def test_cleanup(self, owner):
        for eid in self.created_ids:
            r = owner.delete(f"{API}/insurance/{eid}")
            assert r.status_code == 200


# =========================================================== C1 extra-income
class TestExtraIncome:
    LEAD = "LD26000002"

    def test_put_extra_income_folds_to_earnings(self, owner):
        # baseline
        r0 = owner.get(f"{API}/leads/{self.LEAD}")
        base_earnings = r0.json().get("dealerTotalEarnings", 0)

        payload = {"documentationIncome": 1500, "warrantyIncome": 800, "rsaIncome": 600, "referralIncome": 1000}
        r = owner.put(f"{API}/leads/{self.LEAD}/extra-income", json=payload)
        assert r.status_code == 200, f"{r.status_code} {r.text}"
        lead = r.json()
        assert lead["extraDealerIncomeTotal"] == 3900, f"got {lead['extraDealerIncomeTotal']}"
        assert lead["dealerTotalEarnings"] >= base_earnings + 3899, \
            f"earnings did not increase by 3900 (base={base_earnings}, new={lead['dealerTotalEarnings']})"

    def test_dealer_earnings_report_reflects_extra(self, owner):
        r = owner.get(f"{API}/reports/dealer-earnings")
        assert r.status_code == 200
        rep = r.json()
        assert rep["totals"]["extra"] >= 3899.99, f"extra total {rep['totals']['extra']}"
        comps = {c["label"]: c["amount"] for c in rep["components"]}
        for lbl in ("Documentation", "Warranty", "RSA", "Referral"):
            assert lbl in comps, f"missing component {lbl}"

    def test_reset_extra_income(self, owner):
        r = owner.put(f"{API}/leads/{self.LEAD}/extra-income",
                      json={"documentationIncome": 0, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})
        assert r.status_code == 200
        assert r.json()["extraDealerIncomeTotal"] == 0


# =========================================================== H4 audit-log
class TestAuditLog:
    LEAD = "LD26000002"

    def test_executive_blocked(self, executive):
        r = executive.get(f"{API}/audit-log")
        assert r.status_code == 403, f"executive should be blocked, got {r.status_code}"

    def test_owner_lists_and_module_filter(self, owner):
        # Trigger an audit entry (extra-income update) then verify it exists
        owner.put(f"{API}/leads/{self.LEAD}/extra-income",
                  json={"documentationIncome": 100, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})
        owner.put(f"{API}/leads/{self.LEAD}/extra-income",
                  json={"documentationIncome": 0, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})

        r = owner.get(f"{API}/audit-log")
        assert r.status_code == 200
        entries = r.json()
        assert len(entries) > 0
        # Structural fields
        for k in ("timestamp", "user", "role", "ip", "action", "module", "oldValue", "newValue"):
            assert k in entries[0], f"audit entry missing {k}"

        r2 = owner.get(f"{API}/audit-log?module=extra-income")
        assert r2.status_code == 200
        assert all(e["module"] == "extra-income" for e in r2.json()), "module filter not applied"
        assert len(r2.json()) >= 2

    def test_audit_written_for_payment_and_scheme(self, owner, mongo):
        LEAD = "LD26000002"
        # scheme edit (no-op values same as current — but audit is written unconditionally)
        cur = owner.get(f"{API}/leads/{LEAD}").json()
        scheme_body = {k: cur.get(k, 0) for k in ("consumerDiscount", "exchangeBonus", "loyaltyBonus",
                                                  "referralBonus", "dsaDiscount", "additionalDiscount",
                                                  "oemExtraSupportReceived", "oemExtraSupportPassed",
                                                  "customerBenefitPassed")}
        scheme_body["benefitMode"] = cur.get("benefitMode") or "Full Benefit"
        r = owner.put(f"{API}/leads/{LEAD}/scheme", json=scheme_body)
        assert r.status_code == 200, r.text

        # payment (within cap): first delete any leftover then add one
        r2 = owner.post(f"{API}/leads/{LEAD}/payments",
                        json={"amount": 100, "paymentMode": "Cash", "narration": "TEST_audit"})
        assert r2.status_code == 200, r2.text
        rec = r2.json()

        time.sleep(0.3)
        entries = owner.get(f"{API}/audit-log?leadId=" + LEAD).json()
        modules = {e["module"] for e in entries}
        assert "payment" in modules, f"payment audit missing: {modules}"
        assert "scheme" in modules, f"scheme audit missing: {modules}"

        # cleanup created payment via Mongo (no DELETE API)
        mongo.payments.delete_one({"receiptNumber": rec["receiptNumber"]})
        # force recompute
        owner.put(f"{API}/leads/{LEAD}/extra-income",
                  json={"documentationIncome": 0, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})


# =========================================================== H1 Dashboard KPIs
class TestDashboardKPIs:
    def test_all_kpis_present(self, owner):
        r = owner.get(f"{API}/dashboard")
        assert r.status_code == 200
        kpis = r.json()["kpis"]
        for k in ("conversion", "revenue", "financeOutstanding", "followupDue", "followupOverdue"):
            assert k in kpis, f"kpi {k} missing; got {list(kpis.keys())}"
        assert isinstance(kpis["followupDue"], int)
        assert isinstance(kpis["followupOverdue"], int)
        assert isinstance(kpis["financeOutstanding"], (int, float))


# =========================================================== H3 Claim lifecycle
class TestClaimLifecycle:
    LEAD = "LD26000002"

    def test_settle_persists_dates_and_ageing(self, owner, mongo):
        # apply exchangeBonus scheme to generate a claim row
        cur = owner.get(f"{API}/leads/{self.LEAD}").json()
        base_scheme = {k: 0 for k in ("consumerDiscount", "exchangeBonus", "loyaltyBonus",
                                      "referralBonus", "dsaDiscount", "additionalDiscount",
                                      "oemExtraSupportReceived", "oemExtraSupportPassed",
                                      "customerBenefitPassed")}
        try:
            r = owner.put(f"{API}/leads/{self.LEAD}/scheme",
                          json={**base_scheme, "exchangeBonus": 2000, "benefitMode": "Full Benefit"})
            if r.status_code == 422:
                pytest.skip(f"exchangeBonus not available for {self.LEAD} scheme master: {r.text}")
            assert r.status_code == 200, r.text

            claims = owner.get(f"{API}/claims").json()
            row = next((c for c in claims if c["leadId"] == self.LEAD and c["componentKey"] == "exchangeBonus"), None)
            assert row is not None, "no exchangeBonus claim row generated"

            body = {"leadId": self.LEAD, "componentKey": "exchangeBonus",
                    "submittedDate": "2026-01-05", "approvedDate": "2026-01-10",
                    "claimStatus": "Approved", "receivedAmount": 0}
            r2 = owner.post(f"{API}/claims/settle", json=body)
            assert r2.status_code == 200, r2.text

            claims2 = owner.get(f"{API}/claims").json()
            row2 = next(c for c in claims2 if c["leadId"] == self.LEAD and c["componentKey"] == "exchangeBonus")
            assert row2["submittedDate"] == "2026-01-05"
            assert row2["approvedDate"] == "2026-01-10"
            assert row2["ageingDays"] >= 0
        finally:
            # cleanup: reset scheme, remove claim doc
            owner.put(f"{API}/leads/{self.LEAD}/scheme", json={**base_scheme, "benefitMode": "Full Benefit"})
            mongo.claims.delete_many({"leadId": self.LEAD, "componentKey": "exchangeBonus"})


# =========================================================== H5 rsaAmc
class TestRsaAmcPrice:
    LEAD = "LD26000002"

    def test_rsaAmc_flows_into_gvc(self, owner):
        cur = owner.get(f"{API}/leads/{self.LEAD}").json()
        base_gvc = cur.get("grossVehicleCost", 0)
        base_payable = cur.get("customerPayable", 0)
        # capture existing price fields
        ps_keys = ("exShowroom", "rto", "insuranceAmount", "accessoriesAmount", "handlingCharges",
                   "trc", "fastag", "extendedWarranty", "rsaAmc", "otherCharges",
                   "tcsApplicable", "finalExchangeValue")
        base_ps = {k: cur.get(k, 0) for k in ps_keys}
        base_ps["tcsApplicable"] = cur.get("tcsApplicable", "No")

        try:
            new_ps = {**base_ps, "rsaAmc": 1500}
            r = owner.put(f"{API}/leads/{self.LEAD}/price-structure", json=new_ps)
            assert r.status_code == 200, r.text
            after = r.json()
            assert after["grossVehicleCost"] >= base_gvc + 1499.99, \
                f"GVC did not include rsaAmc: base={base_gvc} after={after['grossVehicleCost']}"
            assert after["customerPayable"] >= base_payable + 1499.99
        finally:
            owner.put(f"{API}/leads/{self.LEAD}/price-structure", json={**base_ps, "rsaAmc": 0})


# =========================================================== U4 double-submit
class TestDoubleSubmit:
    LEAD = "LD26000002"

    def test_duplicate_payment_within_4s_rejected(self, owner, mongo):
        body = {"amount": 77, "paymentMode": "Cash", "narration": "TEST_dup"}
        r1 = owner.post(f"{API}/leads/{self.LEAD}/payments", json=body)
        assert r1.status_code == 200, r1.text
        r2 = owner.post(f"{API}/leads/{self.LEAD}/payments", json=body)
        assert r2.status_code == 409, f"expected 409 duplicate, got {r2.status_code} {r2.text}"
        # cleanup — only the first went through
        mongo.payments.delete_one({"receiptNumber": r1.json()["receiptNumber"]})
        owner.put(f"{API}/leads/{self.LEAD}/extra-income",
                  json={"documentationIncome": 0, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})


# =========================================================== ERP Production Audit
class TestProductionAudit:
    def test_executive_blocked(self, executive):
        r = executive.get(f"{API}/reports/production-audit")
        assert r.status_code == 403

    def test_owner_returns_full_report(self, owner):
        r = owner.get(f"{API}/reports/production-audit")
        assert r.status_code == 200
        rep = r.json()
        cats = rep.get("categories") or []
        assert len(cats) >= 14, f"expected >=14 categories, got {len(cats)}"
        for k in ("severityCounts", "scoreBreakdown", "blockers", "verdict", "score"):
            assert k in rep, f"missing {k}"
        sev = rep["severityCounts"]
        assert sev.get("Critical", 0) == 0, f"Critical>0: {sev}"
        assert isinstance(rep["blockers"], list)
        assert rep["score"] >= 90, f"score too low: {rep['score']}"


# =========================================================== Regression gating
class TestRegressionGating:
    def test_both_roles_login(self):
        for creds in (OWNER, EXEC):
            r = requests.post(f"{API}/auth/login", json=creds)
            assert r.status_code == 200

    @pytest.mark.parametrize("path", [
        "/reports/owner-commercial",
        "/reports/oem-claim-dashboard",
        "/reports/claim-exceptions",
        "/reports/insurance-payout",
        "/reports/dealer-earnings",
        "/reports/production-audit",
        "/audit-log",
        "/dealer-earnings",
    ])
    def test_owner_only_endpoints(self, owner, executive, path):
        assert executive.get(f"{API}{path}").status_code == 403, f"{path} not gated"
        assert owner.get(f"{API}{path}").status_code == 200, f"{path} owner failed"

    def test_step_gating_book_already_booked(self, owner):
        # LD26000002 is booked -> convert-booking should 409
        r = owner.post(f"{API}/leads/LD26000002/convert-booking",
                       json={"bookingAmount": 5000, "paymentMode": "Cash"})
        assert r.status_code in (409, 422), f"expected 409/422, got {r.status_code}: {r.text}"

    def test_duplicate_mobile_409(self, owner):
        # LD26000002 mobile is already used; creating another lead with same mobile -> 409
        cur = owner.get(f"{API}/leads/LD26000002").json()
        mob = cur.get("mobile")
        if not mob or len(mob) < 10:
            pytest.skip("no 10-digit mobile on LD26000002")
        r = owner.post(f"{API}/leads",
                       json={"customerName": "TEST_dup", "mobile": mob, "interestedModel": "Turbo Max"})
        assert r.status_code == 409, f"expected 409 duplicate mobile, got {r.status_code}: {r.text}"


# =========================================================== U1 end-to-end
class TestU1EndToEnd:
    """Build a synthetic deal on LD26000006 (baseline: New), then revert everything."""
    LEAD = "LD26000006"

    def test_reconciliation_and_revert(self, owner, mongo):
        # snapshot for revert
        original = owner.get(f"{API}/leads/{self.LEAD}").json()
        if original.get("currentStatus", "").lower() not in ("new", ""):
            pytest.skip(f"{self.LEAD} not New (baseline changed); status={original.get('currentStatus')}")

        created_payment_receipt = None
        insurance_id = None
        try:
            # 1) convert booking
            r = owner.post(f"{API}/leads/{self.LEAD}/convert-booking",
                           json={"bookingAmount": 5000, "paymentMode": "Cash"})
            assert r.status_code == 200, f"convert-booking: {r.status_code} {r.text}"

            # 2) price structure — ex 640000 + insurance 22000
            ps = {"exShowroom": 640000, "rto": 0, "insuranceAmount": 22000,
                  "accessoriesAmount": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
                  "extendedWarranty": 0, "rsaAmc": 0, "otherCharges": 0,
                  "tcsApplicable": "No", "finalExchangeValue": 0}
            r = owner.put(f"{API}/leads/{self.LEAD}/price-structure", json=ps)
            assert r.status_code == 200, r.text
            after_price = r.json()
            assert after_price["grossVehicleCost"] == 662000, \
                f"GVC expected 662000, got {after_price['grossVehicleCost']}"

            # 3) reconciliation: customerPayable - totalReceived = customerOutstanding
            lead360 = owner.get(f"{API}/leads/{self.LEAD}/360")
            if lead360.status_code == 200:
                data = lead360.json()
                # loose reconciliation
                lead = data.get("lead") or after_price
            else:
                lead = after_price
            payable = lead["customerPayable"]
            received = lead.get("totalReceived", 0)
            outstanding = lead.get("customerOutstanding", 0)
            assert abs(payable - received - outstanding) < 1.0, \
                f"reconciliation off: payable={payable} received={received} outstanding={outstanding}"
            assert lead.get("dealerTotalEarnings") is not None

        finally:
            # revert to baseline: reset price structure to originals, delete created payment (from convert-booking), scheme to zeros
            ps_reset = {"exShowroom": original.get("exShowroom", 0), "rto": original.get("rto", 0),
                        "insuranceAmount": original.get("insuranceAmount", 0),
                        "accessoriesAmount": original.get("accessoriesAmount", 0),
                        "handlingCharges": original.get("handlingCharges", 0),
                        "trc": original.get("trc", 0), "fastag": original.get("fastag", 0),
                        "extendedWarranty": original.get("extendedWarranty", 0),
                        "rsaAmc": original.get("rsaAmc", 0),
                        "otherCharges": original.get("otherCharges", 0),
                        "tcsApplicable": original.get("tcsApplicable", "No"),
                        "finalExchangeValue": original.get("finalExchangeValue", 0)}
            try:
                owner.put(f"{API}/leads/{self.LEAD}/price-structure", json=ps_reset)
            except Exception:
                pass
            # delete convert-booking payment(s) and any test payment
            mongo.payments.delete_many({"leadId": self.LEAD})
            # revert lead's currentStatus/booking fields directly (no un-book API)
            mongo.leads.update_one(
                {"leadId": self.LEAD},
                {"$set": {"currentStatus": original.get("currentStatus", "New"),
                          "bookingDate": original.get("bookingDate", ""),
                          "bookingAmount": original.get("bookingAmount", 0),
                          "totalReceived": 0, "customerOutstanding": 0}})
            # remove any bookings row for this lead
            mongo.bookings.delete_many({"leadId": self.LEAD})
            # force recompute (extra-income noop)
            try:
                owner.put(f"{API}/leads/{self.LEAD}/extra-income",
                          json={"documentationIncome": 0, "warrantyIncome": 0, "rsaIncome": 0, "referralIncome": 0})
            except Exception:
                pass


# =========================================================== Baseline integrity
class TestBaselineAfterAll:
    """Runs last; verifies mutated leads returned to baseline."""

    def test_ld26000002_baseline(self, owner):
        lead = owner.get(f"{API}/leads/LD26000002").json()
        assert lead.get("totalReceived") == 5000, f"LD26000002 totalReceived={lead.get('totalReceived')}"
        assert lead.get("extraDealerIncomeTotal", 0) == 0

    def test_ld26000006_baseline(self, owner):
        lead = owner.get(f"{API}/leads/LD26000006").json()
        assert lead.get("totalReceived", 0) == 0
