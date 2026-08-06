"""Iteration 3 backend tests: Insurance CRUD + Lead Bulk Import (CSV/XLSX)."""
import io
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


# ---------------------------- fixtures
@pytest.fixture(scope="session")
def owner_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "owner@euler.com", "password": "euler@123"})
    assert r.status_code == 200, f"owner login failed: {r.text}"
    return r.json()["token"]


@pytest.fixture(scope="session")
def exec_token():
    r = requests.post(f"{API}/auth/login",
                      json={"email": "executive@euler.com", "password": "euler@123"})
    assert r.status_code == 200
    return r.json()["token"]


def H(tok):
    return {"Authorization": f"Bearer {tok}"}


CSV_HEADERS = "Customer Name,Mobile,City,Interested Model,Executive,Budget\n"


def _csv_bytes(rows):
    body = CSV_HEADERS
    for r in rows:
        body += ",".join(str(x) for x in r) + "\n"
    return body.encode("utf-8")


def _xlsx_bytes(rows):
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Customer Name", "Mobile", "City", "Interested Model", "Executive", "Budget"])
    for r in rows:
        ws.append(list(r))
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ---------------------------- INSURANCE
class TestInsurance:
    _created = []

    def test_requires_auth(self):
        r = requests.get(f"{API}/insurance")
        assert r.status_code in (401, 403)
        r2 = requests.post(f"{API}/insurance", json={"customerName": "x"})
        assert r2.status_code in (401, 403)

    def test_create_percent_rate(self, owner_token):
        payload = {"customerName": "TEST_InsCust1", "mobile": "9000000001",
                   "insuranceCompany": "ACKO", "insuranceAmount": 10000, "payoutRate": 15}
        r = requests.post(f"{API}/insurance", headers=H(owner_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert "entryId" in d and d["entryId"].startswith("INS26")
        assert d["payoutRate"] == 0.15
        assert d["expectedPayout"] == 1500
        assert d["payoutOutstanding"] == 1500
        assert d["status"] == "Pending"
        TestInsurance._created.append(d["entryId"])

    def test_create_fraction_rate(self, owner_token):
        payload = {"customerName": "TEST_InsCust2", "insuranceAmount": 10000, "payoutRate": 0.15}
        r = requests.post(f"{API}/insurance", headers=H(owner_token), json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["payoutRate"] == 0.15
        assert d["expectedPayout"] == 1500
        TestInsurance._created.append(d["entryId"])

    def test_status_received_when_paid(self, owner_token):
        payload = {"customerName": "TEST_InsCust3", "insuranceAmount": 10000,
                   "payoutRate": 15, "receivedPayout": 1500}
        r = requests.post(f"{API}/insurance", headers=H(owner_token), json=payload)
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "Received"
        assert d["payoutOutstanding"] == 0
        TestInsurance._created.append(d["entryId"])

    def test_list_contains_created(self, owner_token):
        r = requests.get(f"{API}/insurance", headers=H(owner_token))
        assert r.status_code == 200
        ids = [x["entryId"] for x in r.json()]
        for eid in TestInsurance._created:
            assert eid in ids

    def test_update_recomputes(self, owner_token):
        eid = TestInsurance._created[0]
        payload = {"customerName": "TEST_InsCust1", "insuranceAmount": 20000, "payoutRate": 10}
        r = requests.put(f"{API}/insurance/{eid}", headers=H(owner_token), json=payload)
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["payoutRate"] == 0.10
        assert d["expectedPayout"] == 2000
        assert d["payoutOutstanding"] == 2000

    def test_update_missing_404(self, owner_token):
        r = requests.put(f"{API}/insurance/INS_NOPE", headers=H(owner_token),
                         json={"customerName": "x", "insuranceAmount": 100, "payoutRate": 1})
        assert r.status_code == 404

    def test_delete_all_created(self, owner_token):
        for eid in TestInsurance._created:
            r = requests.delete(f"{API}/insurance/{eid}", headers=H(owner_token))
            assert r.status_code == 200
        # verify gone
        remaining = [x["entryId"] for x in
                     requests.get(f"{API}/insurance", headers=H(owner_token)).json()]
        for eid in TestInsurance._created:
            assert eid not in remaining
        TestInsurance._created.clear()


# ---------------------------- LEAD IMPORT
class TestLeadImport:
    _imported_ids = []

    def test_preview_requires_auth(self):
        r = requests.post(f"{API}/leads/import/preview",
                          files={"file": ("t.csv", b"a,b\n1,2\n", "text/csv")})
        assert r.status_code in (401, 403)

    def test_preview_csv(self, owner_token):
        data = _csv_bytes([
            ["TEST_Imp_Alice", "9111111111", "Delhi", "Turbo Max", "TEST_Exec", 250000],
            ["TEST_Imp_Bob", "9222222222", "Mumbai", "HiLoad EV", "TEST_Exec", 300000],
            ["", "9333333333", "Chennai", "Turbo Max", "TEST_Exec", 200000],  # skipped no name
        ])
        r = requests.post(f"{API}/leads/import/preview", headers=H(owner_token),
                          files={"file": ("leads.csv", data, "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["rowCount"] == 2
        assert isinstance(d["sample"], list) and len(d["sample"]) == 2
        s0 = d["sample"][0]
        assert s0["customerName"] == "TEST_Imp_Alice"
        assert s0["mobile"] == "9111111111"
        assert s0["city"] == "Delhi"
        assert s0["interestedModel"] == "Turbo Max"
        assert s0["executive"] == "TEST_Exec"
        assert float(s0["budget"]) == 250000

    def test_commit_csv(self, owner_token):
        data = _csv_bytes([
            ["TEST_Imp_Csv_A", "9444444441", "Pune", "Turbo Max", "TEST_Exec", 100000],
            ["TEST_Imp_Csv_B", "9444444442", "Pune", "HiLoad EV", "TEST_Exec", 150000],
        ])
        r = requests.post(f"{API}/leads/import/commit", headers=H(owner_token),
                          files={"file": ("leads.csv", data, "text/csv")})
        assert r.status_code == 200, r.text
        d = r.json()
        assert d["created"] == 2
        # verify appears in list
        leads = requests.get(f"{API}/leads", headers=H(owner_token),
                             params={"q": "TEST_Imp_Csv"}).json()
        names = [l["customerName"] for l in leads]
        assert "TEST_Imp_Csv_A" in names
        assert "TEST_Imp_Csv_B" in names
        for l in leads:
            if l["customerName"].startswith("TEST_Imp_Csv"):
                assert l["leadId"].startswith("LD26")
                assert l["currentStatus"] == "New"
                TestLeadImport._imported_ids.append(l["leadId"])

    def test_commit_xlsx(self, owner_token):
        data = _xlsx_bytes([
            ["TEST_Imp_Xlsx_A", 9555555551, "Bengaluru", "Turbo Max", "TEST_Exec", 175000],
            ["", 9555555552, "Bengaluru", "HiLoad EV", "TEST_Exec", 175000],  # skipped
        ])
        # preview
        rp = requests.post(f"{API}/leads/import/preview", headers=H(owner_token),
                          files={"file": ("leads.xlsx", data,
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert rp.status_code == 200, rp.text
        assert rp.json()["rowCount"] == 1
        # commit
        r = requests.post(f"{API}/leads/import/commit", headers=H(owner_token),
                          files={"file": ("leads.xlsx", data,
                                          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
        assert r.status_code == 200, r.text
        assert r.json()["created"] == 1
        leads = requests.get(f"{API}/leads", headers=H(owner_token),
                             params={"q": "TEST_Imp_Xlsx"}).json()
        assert any(l["customerName"] == "TEST_Imp_Xlsx_A" for l in leads)
        for l in leads:
            if l["customerName"].startswith("TEST_Imp_Xlsx"):
                TestLeadImport._imported_ids.append(l["leadId"])

    def test_cleanup_imported(self, owner_token):
        # No delete lead endpoint; note ids for main agent reseed. Best-effort: mark close.
        for lid in TestLeadImport._imported_ids:
            requests.post(f"{API}/leads/{lid}/close", headers=H(owner_token),
                          json={"closeReason": "TEST cleanup"})
        # Leave in place; main agent can reseed if needed.
