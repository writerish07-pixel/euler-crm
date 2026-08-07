"""Iteration 11 backend tests — receipt flows + over-payment guard.

Covers:
1. Payment over-cap guard (422) + valid within-cap (200), with cleanup.
2. Financer Receipt: 404 on unknown file, then create finance file via a Finance
   payment on a booked lead, record a receipt, verify Disbursed↑ / Outstanding↓ /
   status, verify customer outstanding did NOT change by the receipt,
   verify receipts[] history array persists. Cleanup: delete finance file,
   delete finance payment, recompute lead.
3. OEM Claim Receipt: baseline schemes are ₹0 so we mutate one lead's scheme to
   create eligible outstanding, POST /claims/receipt, verify accrual + status +
   receipts[] history, then RESET scheme to zero and delete claim doc.
4. Insurer Payout Receipt: create test insurance entry, record payout, verify
   accrual + status + receipts[] history, then DELETE the entry.

Baseline preservation: all created docs are removed & any lead we mutate is
recomputed / reset before finish.
"""
import os
import time
import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"

OWNER = {"email": "owner@euler.com", "password": "euler@123"}
EXEC = {"email": "executive@euler.com", "password": "euler@123"}

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "euler_crm")


# -------- infra --------
@pytest.fixture(scope="session")
def mdb():
    return MongoClient(MONGO_URL)[DB_NAME]


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
def oc(owner_token):
    s = requests.Session()
    s.headers.update({"Authorization": f"Bearer {owner_token}",
                      "Content-Type": "application/json"})
    return s


# -------- helpers --------
def _get_lead(oc, lid):
    r = oc.get(f"{API}/leads/{lid}", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _get_360(oc, lid):
    r = oc.get(f"{API}/leads/{lid}/360", timeout=15)
    assert r.status_code == 200, r.text
    return r.json()


def _pick_booked_lead(oc):
    """Pick a booked lead with payable>0 and some remaining balance.
    Uses totalReceived + customerOutstanding as payable proxy."""
    for lid in ("LD26000002", "LD26000003", "LD26000005"):
        l = _get_lead(oc, lid)
        received = float(l.get("totalReceived") or 0)
        outstanding = float(l.get("customerOutstanding") or 0)
        payable = received + outstanding
        if payable > 100000 and outstanding > 5000:
            return lid, payable, received
    pytest.skip("No suitable booked lead found for over-cap test")


# ====================================================================
# 1) PAYMENT OVER-CAP GUARD
# ====================================================================
class TestOverCapGuard:
    def test_over_cap_rejects_422_and_valid_within_cap_persists_then_cleanup(self, oc, mdb):
        lid, payable, received = _pick_booked_lead(oc)
        remaining = payable - received
        # (a) over cap → 422
        r = oc.post(f"{API}/leads/{lid}/payments", json={
            "amount": 900000, "paymentMode": "Cash",
            "narration": "TEST_OVERCAP_REJECT", "date": ""
        })
        assert r.status_code == 422, f"expected 422 got {r.status_code}: {r.text}"
        assert "exceed" in r.text.lower() or "balance" in r.text.lower()

        # (b) valid within cap → 200
        narration = f"TEST_OVERCAP_OK_{int(time.time())}"
        amt = round(min(1000.0, remaining - 100.0), 2)
        r2 = oc.post(f"{API}/leads/{lid}/payments", json={
            "amount": amt, "paymentMode": "Cash",
            "narration": narration, "date": ""
        })
        assert r2.status_code == 200, r2.text
        rec = r2.json()
        assert rec["amount"] == amt
        assert rec["narration"] == narration

        # Verify persistence via /payments
        gp = oc.get(f"{API}/payments", params={"lead_id": lid})
        assert gp.status_code == 200
        assert any(p.get("narration") == narration for p in gp.json())

        # Cleanup — delete this test payment + recompute
        try:
            res = mdb.payments.delete_many({"narration": narration, "leadId": lid})
            assert res.deleted_count >= 1
        finally:
            # Force recompute by re-getting lead 360 (triggers nothing) — instead
            # invoke recompute via a no-op scheme PUT with current values? Safer:
            # just re-fetch — the lead totals will be re-derived on next payment
            # or recompute call. Use a tiny valid amount then delete to trigger recompute.
            # Simpler: call any endpoint that recomputes. The 360 endpoint does not
            # recompute totals; but /leads/{id} returns stored fields. To force a
            # recompute we can hit the internal via posting/deleting scheme? Easier:
            # since payments collection is source of truth, next add_payment/scheme
            # PUT will recompute. Baseline totalReceived stored on lead may drift.
            pass

        # sanity — final totalReceived should equal baseline received again (since
        # we deleted the test payment). Poll with tolerance.
        # Trigger a recompute by calling put scheme with same values (no-op).
        cur = _get_lead(oc, lid)
        scheme = cur.get("schemeOffers") or {}
        rc = oc.put(f"{API}/leads/{lid}/scheme", json={
            "consumerDiscount": float(scheme.get("consumerDiscount") or 0),
            "exchangeBonus": float(scheme.get("exchangeBonus") or 0),
            "loyaltyBonus": float(scheme.get("loyaltyBonus") or 0),
            "referralBonus": float(scheme.get("referralBonus") or 0),
            "dsaDiscount": float(scheme.get("dsaDiscount") or 0),
            "additionalDiscount": float(scheme.get("additionalDiscount") or 0),
            "benefitMode": scheme.get("benefitMode") or "Full Benefit",
            "customerBenefitPassed": float(scheme.get("customerBenefitPassed") or 0),
            "benefitPassedBreakup": scheme.get("benefitPassedBreakup"),
            "oemExtraSupportReceived": float(scheme.get("oemExtraSupportReceived") or 0),
            "oemExtraSupportPassed": float(scheme.get("oemExtraSupportPassed") or 0),
        })
        # this triggers recompute_lead
        assert rc.status_code in (200, 422), rc.text
        after = _get_lead(oc, lid)
        after_received = float(after.get("totalReceived") or 0)
        assert abs(after_received - received) < 0.5, (
            f"baseline drift on {lid}: was {received}, now {after_received}")


# ====================================================================
# 2) FINANCER RECEIPT
# ====================================================================
class TestFinancerReceipt:
    def test_unknown_file_404(self, oc):
        r = oc.post(f"{API}/finance/NOPE/receipt", json={"amount": 100})
        assert r.status_code == 404

    def test_full_flow_creates_file_receipt_and_no_customer_impact(self, oc, mdb):
        # pick a booked lead with room
        lid, payable, received_before = _pick_booked_lead(oc)
        remaining = payable - received_before
        # Finance-mode entry ~ small chunk of remaining
        commit_amt = round(min(50000.0, remaining - 100.0), 2)
        file_no = f"TESTFF{int(time.time())}"
        narration = f"TEST_FIN_ENTRY_{file_no}"
        r = oc.post(f"{API}/leads/{lid}/payments", json={
            "amount": commit_amt, "paymentMode": "Finance",
            "financeFileNumber": file_no, "financerName": "TEST BANK",
            "narration": narration, "date": ""
        })
        assert r.status_code == 200, r.text

        # finance file created
        fg = oc.get(f"{API}/finance").json()
        f = next((x for x in fg if x.get("fileNumber") == file_no), None)
        assert f is not None, "Finance file not created"
        assert abs(float(f["sanctionedAmount"]) - commit_amt) < 0.5
        assert float(f["receivedAgainstFile"]) == 0.0
        assert abs(float(f["fileOutstanding"]) - commit_amt) < 0.5
        assert f["status"] == "Pending"

        # customer outstanding after Finance entry (should have dropped by commit_amt)
        lead_after_fin = _get_lead(oc, lid)
        cust_after_fin = float(lead_after_fin.get("customerOutstanding") or 0)

        # (a) invalid amount → 422
        r_bad = oc.post(f"{API}/finance/{file_no}/receipt", json={"amount": 0})
        assert r_bad.status_code == 422

        # (b) record partial receipt
        rec_amt = round(commit_amt / 2, 2)
        rr = oc.post(f"{API}/finance/{file_no}/receipt",
                     json={"amount": rec_amt, "reference": "TEST_UTR_1"})
        assert rr.status_code == 200, rr.text
        j = rr.json()
        assert abs(float(j["receivedAgainstFile"]) - rec_amt) < 0.5
        assert abs(float(j["fileOutstanding"]) - (commit_amt - rec_amt)) < 0.5
        assert j["status"] == "Partial"
        assert isinstance(j.get("receipts"), list) and len(j["receipts"]) >= 1
        assert j["receipts"][-1]["reference"] == "TEST_UTR_1"

        # customer outstanding must NOT change from financer receipt
        lead_after_rcpt = _get_lead(oc, lid)
        cust_after_rcpt = float(lead_after_rcpt.get("customerOutstanding") or 0)
        assert abs(cust_after_rcpt - cust_after_fin) < 0.5, (
            f"customer outstanding changed by financer receipt: "
            f"{cust_after_fin} -> {cust_after_rcpt}")

        # (c) top-up to fully close
        rr2 = oc.post(f"{API}/finance/{file_no}/receipt",
                      json={"amount": commit_amt - rec_amt, "reference": "TEST_UTR_2"})
        assert rr2.status_code == 200
        j2 = rr2.json()
        assert j2["status"] == "Received"
        assert float(j2["fileOutstanding"]) <= 0.5
        assert len(j2["receipts"]) >= 2

        # ---- cleanup ----
        # 1) drop finance doc
        mdb.finance.delete_one({"fileNumber": file_no})
        # 2) drop the finance payment on the lead
        del_res = mdb.payments.delete_many({"leadId": lid, "narration": narration})
        assert del_res.deleted_count >= 1
        # 3) recompute lead (via no-op scheme PUT) — restores customerOutstanding
        cur = _get_lead(oc, lid)
        scheme = cur.get("schemeOffers") or {}
        oc.put(f"{API}/leads/{lid}/scheme", json={
            "consumerDiscount": float(scheme.get("consumerDiscount") or 0),
            "exchangeBonus": float(scheme.get("exchangeBonus") or 0),
            "loyaltyBonus": float(scheme.get("loyaltyBonus") or 0),
            "referralBonus": float(scheme.get("referralBonus") or 0),
            "dsaDiscount": float(scheme.get("dsaDiscount") or 0),
            "additionalDiscount": float(scheme.get("additionalDiscount") or 0),
            "benefitMode": scheme.get("benefitMode") or "Full Benefit",
            "customerBenefitPassed": float(scheme.get("customerBenefitPassed") or 0),
            "benefitPassedBreakup": scheme.get("benefitPassedBreakup"),
            "oemExtraSupportReceived": float(scheme.get("oemExtraSupportReceived") or 0),
            "oemExtraSupportPassed": float(scheme.get("oemExtraSupportPassed") or 0),
        })
        after = _get_lead(oc, lid)
        after_received = float(after.get("totalReceived") or 0)
        assert abs(after_received - received_before) < 0.5


# ====================================================================
# 3) OEM CLAIM RECEIPT
# ====================================================================
class TestClaimReceipt:
    def test_claim_receipt_flow_with_scheme_and_cleanup(self, oc, mdb):
        # Use LD26000004 or 6/7 (not booked; New) → won't work since claims need booked
        # scheme. Use a booked lead but capture existing scheme first.
        lid = None
        for cand in ("LD26000002", "LD26000003", "LD26000005"):
            l = _get_lead(oc, cand)
            if (l.get("currentStatus") or "").lower().startswith("book"):
                lid = cand
                break
        if not lid:
            pytest.skip("no booked lead available")

        lead = _get_lead(oc, lid)
        prior_scheme = dict(lead.get("schemeOffers") or {})

        # set a small exchange bonus so eligibleClaim > 0
        payload = {
            "consumerDiscount": 0, "exchangeBonus": 2000, "loyaltyBonus": 0,
            "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
            "benefitMode": "Full Benefit", "customerBenefitPassed": 0,
            "benefitPassedBreakup": None,
            "oemExtraSupportReceived": 0, "oemExtraSupportPassed": 0,
        }
        rs = oc.put(f"{API}/leads/{lid}/scheme", json=payload)
        assert rs.status_code == 200, rs.text

        try:
            # find eligible amount for exchangeBonus
            claims = oc.get(f"{API}/claims").json()
            row = next((c for c in claims if c.get("leadId") == lid and c.get("componentKey") == "exchangeBonus"), None)
            assert row is not None, f"expected exchangeBonus claim row for {lid}"
            eligible = float(row.get("eligibleClaim") or 0)
            assert eligible > 0, "expected non-zero eligible"

            # invalid amount → 422
            rbad = oc.post(f"{API}/claims/receipt",
                           json={"leadId": lid, "componentKey": "exchangeBonus", "amount": 0})
            assert rbad.status_code == 422

            # partial receipt
            amt1 = round(eligible / 2, 2)
            r1 = oc.post(f"{API}/claims/receipt", json={
                "leadId": lid, "componentKey": "exchangeBonus",
                "amount": amt1, "reference": "TEST_CLM_UTR1"
            })
            assert r1.status_code == 200, r1.text
            j1 = r1.json()
            assert abs(float(j1["receivedAmount"]) - amt1) < 0.5
            assert j1["status"] == "Partial"

            # verify receipts[] persists (via mongo since /claims list doesn't return it)
            cdoc = mdb.claims.find_one({"leadId": lid, "componentKey": "exchangeBonus"})
            assert cdoc is not None
            assert isinstance(cdoc.get("receipts"), list) and len(cdoc["receipts"]) >= 1
            assert cdoc["receipts"][-1]["reference"] == "TEST_CLM_UTR1"

            # top up to full
            r2 = oc.post(f"{API}/claims/receipt", json={
                "leadId": lid, "componentKey": "exchangeBonus",
                "amount": eligible - amt1, "reference": "TEST_CLM_UTR2"
            })
            assert r2.status_code == 200
            j2 = r2.json()
            assert j2["status"] == "Received"
        finally:
            # RESET scheme to prior (zero if it was zero) and delete claim doc
            reset = {
                "consumerDiscount": float(prior_scheme.get("consumerDiscount") or 0),
                "exchangeBonus": float(prior_scheme.get("exchangeBonus") or 0),
                "loyaltyBonus": float(prior_scheme.get("loyaltyBonus") or 0),
                "referralBonus": float(prior_scheme.get("referralBonus") or 0),
                "dsaDiscount": float(prior_scheme.get("dsaDiscount") or 0),
                "additionalDiscount": float(prior_scheme.get("additionalDiscount") or 0),
                "benefitMode": prior_scheme.get("benefitMode") or "Full Benefit",
                "customerBenefitPassed": float(prior_scheme.get("customerBenefitPassed") or 0),
                "benefitPassedBreakup": prior_scheme.get("benefitPassedBreakup"),
                "oemExtraSupportReceived": float(prior_scheme.get("oemExtraSupportReceived") or 0),
                "oemExtraSupportPassed": float(prior_scheme.get("oemExtraSupportPassed") or 0),
            }
            oc.put(f"{API}/leads/{lid}/scheme", json=reset)
            # remove the claim doc we created
            mdb.claims.delete_many({"leadId": lid, "componentKey": "exchangeBonus",
                                    "receipts.reference": {"$in": ["TEST_CLM_UTR1", "TEST_CLM_UTR2"]}})
            # also purge any claim doc for this component if prior baseline had none
            mdb.claims.delete_many({"leadId": lid, "componentKey": "exchangeBonus",
                                    "claimId": f"CLM-{lid}-exchangeBonus"})


# ====================================================================
# 4) INSURER PAYOUT RECEIPT
# ====================================================================
class TestInsurerPayout:
    def test_payout_flow_and_cleanup(self, oc):
        # create a test insurance entry
        entry = {
            "leadId": "", "customerName": "TEST_INS_CUSTOMER",
            "mobile": "", "model": "Hi-Load EV", "variant": "",
            "insuranceCompany": "TEST INSURER", "policyNumber": f"TEST-POL-{int(time.time())}",
            "insuranceAmount": 20000, "payoutRate": 10, "receivedPayout": 0,
            "policyDate": "", "insuranceExecutive": "", "remarks": "TEST",
        }
        # backend takes payoutRate as fraction? Check derive: rate = ce.num, expected = premium*rate.
        # frontend converts % → fraction. But server_derive uses raw. Send fraction 0.1.
        entry["payoutRate"] = 0.1
        r = oc.post(f"{API}/insurance", json=entry)
        assert r.status_code == 200, r.text
        e = r.json()
        eid = e["entryId"]
        expected_payout = float(e.get("expectedPayout") or 0)
        assert expected_payout > 0, e

        try:
            # invalid → 422
            rbad = oc.post(f"{API}/insurance/{eid}/receipt", json={"amount": 0})
            assert rbad.status_code == 422

            # partial
            half = round(expected_payout / 2, 2)
            r1 = oc.post(f"{API}/insurance/{eid}/receipt",
                         json={"amount": half, "reference": "TEST_INS_UTR1"})
            assert r1.status_code == 200, r1.text
            j1 = r1.json()
            assert abs(float(j1["receivedPayout"]) - half) < 0.5
            assert j1["status"] == "Partial"
            assert isinstance(j1.get("receipts"), list) and len(j1["receipts"]) >= 1
            assert j1["receipts"][-1]["reference"] == "TEST_INS_UTR1"

            # full
            r2 = oc.post(f"{API}/insurance/{eid}/receipt",
                         json={"amount": expected_payout - half, "reference": "TEST_INS_UTR2"})
            assert r2.status_code == 200
            j2 = r2.json()
            assert j2["status"] == "Received"
            assert float(j2["payoutOutstanding"]) <= 0.5
            assert len(j2["receipts"]) >= 2
        finally:
            oc.delete(f"{API}/insurance/{eid}")


# ====================================================================
# 5) REGRESSION — existing lists load, both roles login
# ====================================================================
class TestRegression:
    def test_both_roles_login(self):
        for creds in (OWNER, EXEC):
            r = requests.post(f"{API}/auth/login", json=creds, timeout=15)
            assert r.status_code == 200, f"{creds}: {r.text}"

    def test_lists_load(self, oc):
        for path in ("/leads", "/finance", "/claims", "/insurance", "/payments"):
            r = oc.get(f"{API}{path}")
            assert r.status_code == 200, f"{path}: {r.status_code} {r.text[:200]}"

    def test_dealer_earnings_owner_only(self, oc, exec_token):
        r_o = oc.get(f"{API}/reports/dealer-earnings")
        assert r_o.status_code == 200
        s = requests.Session()
        s.headers.update({"Authorization": f"Bearer {exec_token}"})
        r_e = s.get(f"{API}/reports/dealer-earnings")
        assert r_e.status_code == 403
