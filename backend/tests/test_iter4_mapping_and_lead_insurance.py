"""Iteration 4 backend tests:
- Lead Import column-mapping (custom headers + explicit mapping form field)
- Insurance-from-Lead (leadId filter + create with leadId)
- GSheets read-only regression
"""
import io
import json
import os
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


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "owner@euler.com", "password": "euler@123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


@pytest.fixture(scope="session")
def exec_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "executive@euler.com", "password": "euler@123"})
    assert r.status_code == 200, r.text
    return r.json()["token"]


# Bulk import validates Executive against Settings and Interested Model against
# Price Master, so these fixtures must use values the live app actually has —
# an unknown name/model is reported and skipped instead of imported.
CUSTOM_CSV = (
    "Name,Phone,Town,Vehicle,Sales Person,Budget\n"
    "Mohan Lal,9811110001,Jaipur,Turbo Max,Amit,220000\n"
    "Sita Rani,9811110002,Kota,Turbo Max,Amit,280000\n"
).encode()

STD_CSV = (
    "Customer Name,Mobile,City,Interested Model,Executive,Budget\n"
    "TEST_Std_A,9711110001,Delhi,Turbo Max,Amit,190000\n"
).encode()

MAPPING = {
    "customerName": "Name",
    "mobile": "Phone",
    "city": "Town",
    "interestedModel": "Vehicle",
    "executive": "Sales Person",
}


class TestImportMapping:
    _committed_ids = []

    def test_preview_custom_headers_auto_suggests(self, owner_token):
        r = requests.post(f"{API}/leads/import/preview", headers=H(owner_token),
                          files={"file": ("custom.csv", CUSTOM_CSV, "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        # detected headers preserved
        for h in ["Name", "Phone", "Town", "Vehicle", "Sales Person", "Budget"]:
            assert h in d["detectedHeaders"], d
        # target fields present
        fields = {tf["field"] for tf in d["targetFields"]}
        for f in ("customerName", "mobile", "city", "interestedModel", "executive"):
            assert f in fields
        # suggested mapping should be dict (may be empty for custom headers)
        assert isinstance(d["suggestedMapping"], dict)
        # rowCount without mapping should be 0 (no customerName can be inferred)
        assert d["rowCount"] == 0

    def test_preview_with_explicit_mapping(self, owner_token):
        r = requests.post(
            f"{API}/leads/import/preview",
            headers=H(owner_token),
            files={"file": ("custom.csv", CUSTOM_CSV, "text/csv")},
            data={"mapping": json.dumps(MAPPING)},
        )
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rowCount"] == 2, d
        s0 = d["sample"][0]
        assert s0["customerName"] == "Mohan Lal"
        assert s0["mobile"] == "9811110001"
        assert s0["city"] == "Jaipur"
        assert s0["interestedModel"] == "Turbo Max"
        assert s0["executive"] == "TEST_Sam"

    def test_commit_with_mapping_creates_leads(self, owner_token):
        r = requests.post(
            f"{API}/leads/import/commit",
            headers=H(owner_token),
            files={"file": ("custom.csv", CUSTOM_CSV, "text/csv")},
            data={"mapping": json.dumps(MAPPING)},
        )
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 2
        leads = requests.get(f"{API}/leads", headers=H(owner_token),
                             params={"q": "Mohan Lal"}).json()
        found = [l for l in leads if l["customerName"] == "Mohan Lal"]
        assert found, "Mohan Lal lead not created"
        assert found[0]["leadId"].startswith("LD26")
        assert found[0]["currentStatus"] == "New"
        assert found[0]["city"] == "Jaipur"
        assert found[0]["interestedModel"] == "Turbo Max"
        TestImportMapping._committed_ids.append(found[0]["leadId"])
        # find Sita too
        leads2 = requests.get(f"{API}/leads", headers=H(owner_token),
                              params={"q": "Sita Rani"}).json()
        f2 = [l for l in leads2 if l["customerName"] == "Sita Rani"]
        assert f2
        TestImportMapping._committed_ids.append(f2[0]["leadId"])

    def test_preview_standard_headers_auto_map(self, owner_token):
        """Standard-header CSV auto-maps with NO mapping provided."""
        r = requests.post(f"{API}/leads/import/preview", headers=H(owner_token),
                          files={"file": ("std.csv", STD_CSV, "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["suggestedMapping"], "suggestedMapping empty for standard headers"
        # Should map customerName -> Customer Name
        assert d["suggestedMapping"].get("customerName", "").lower() == "customer name"
        assert d["rowCount"] >= 1
        assert d["sample"][0]["customerName"] == "TEST_Std_A"

    def test_cleanup_close(self, owner_token):
        for lid in TestImportMapping._committed_ids:
            requests.post(f"{API}/leads/{lid}/close", headers=H(owner_token),
                          json={"closeReason": "TEST cleanup"})


class TestInsuranceFromLead:
    _created = []
    _lead_id = "LD26000001"

    def test_create_with_leadId(self, owner_token):
        # get lead's insuranceAmount (premium) to pre-fill baseline
        lead = requests.get(f"{API}/leads/{self._lead_id}", headers=H(owner_token)).json()
        assert lead.get("leadId") == self._lead_id, lead
        premium = float(lead.get("insuranceAmount") or 10000) or 10000
        payload = {
            "leadId": self._lead_id,
            "customerName": lead.get("customerName") or "TEST_LeadIns",
            "mobile": lead.get("mobile") or "",
            "insuranceCompany": "TEST_ACKO",
            "insuranceAmount": premium,
            "payoutRate": 15,
        }
        r = requests.post(f"{API}/insurance", headers=H(owner_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["leadId"] == self._lead_id
        assert d["payoutRate"] == 0.15
        assert d["expectedPayout"] == round(premium * 0.15, 2)
        assert d["entryId"].startswith("INS26")
        TestInsuranceFromLead._created.append(d["entryId"])

    def test_list_filter_by_lead_id(self, owner_token):
        r = requests.get(f"{API}/insurance", headers=H(owner_token),
                         params={"lead_id": self._lead_id})
        assert r.status_code == 200
        arr = r.json()
        assert len(arr) >= 1
        assert all(x.get("leadId") == self._lead_id for x in arr), \
            f"filter leaked other leads: {arr}"
        ids = [x["entryId"] for x in arr]
        for eid in TestInsuranceFromLead._created:
            assert eid in ids

    def test_list_filter_isolates_other_lead(self, owner_token):
        # LD26000002 should NOT contain our LD26000001 entries
        r = requests.get(f"{API}/insurance", headers=H(owner_token),
                         params={"lead_id": "LD26000002"})
        assert r.status_code == 200
        ids = [x["entryId"] for x in r.json()]
        for eid in TestInsuranceFromLead._created:
            assert eid not in ids

    def test_cleanup(self, owner_token):
        for eid in TestInsuranceFromLead._created:
            r = requests.delete(f"{API}/insurance/{eid}", headers=H(owner_token))
            assert r.status_code == 200
        TestInsuranceFromLead._created.clear()


class TestGSheetsRegression:
    def test_status_read_only(self, owner_token):
        r = requests.get(f"{API}/integrations/gsheets", headers=H(owner_token))
        assert r.status_code == 200
        d = r.json()
        # canWrite must be False; enabled False (per problem statement)
        assert d.get("canWrite") is False, d
        assert d.get("enabled") is False, d

    def test_create_lead_still_200(self, owner_token):
        r = requests.post(f"{API}/leads", headers=H(owner_token), json={
            "customerName": "TEST_GS_Lead", "mobile": "9700000001",
            "interestedModel": "Turbo Max", "executive": "TEST_Sam",
            "leadSource": "Test",
        })
        assert r.status_code == 200, r.text
        lid = r.json().get("leadId")
        assert lid and lid.startswith("LD26")
        # cleanup best-effort
        requests.post(f"{API}/leads/{lid}/close", headers=H(owner_token),
                      json={"closeReason": "TEST cleanup"})

    def test_create_insurance_still_200(self, owner_token):
        r = requests.post(f"{API}/insurance", headers=H(owner_token), json={
            "customerName": "TEST_GS_Ins", "insuranceAmount": 5000, "payoutRate": 10,
        })
        assert r.status_code == 200, r.text
        eid = r.json()["entryId"]
        requests.delete(f"{API}/insurance/{eid}", headers=H(owner_token))


class TestRegression:
    def test_owner_login_and_me(self, owner_token):
        r = requests.get(f"{API}/auth/me", headers=H(owner_token))
        assert r.status_code == 200
        assert r.json().get("role") == "owner"

    def test_executive_blocked_dealer_earnings(self, exec_token):
        r = requests.get(f"{API}/dealer-earnings", headers=H(exec_token))
        assert r.status_code == 403

    def test_public_share(self):
        r = requests.get(f"{API}/share/dashboard")
        assert r.status_code == 200

    def test_price_master(self, owner_token):
        r = requests.get(f"{API}/price-master", headers=H(owner_token))
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_scheme_master(self, owner_token):
        r = requests.get(f"{API}/scheme-master", headers=H(owner_token))
        assert r.status_code == 200
