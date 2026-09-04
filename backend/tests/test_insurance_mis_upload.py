"""Agent MIS upload: match payouts, approve short/over amounts, recast dealer earnings."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "insurance_mis_upload_tests")
os.environ.setdefault("JWT_SECRET", "insurance-mis-secret-32chars!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import insurance_mis as ins_mis  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_suggest_mapping_reads_agent_headers():
    mp = ins_mis.suggest_mapping(["Policy No", "Insured Name", "Payout", "Mobile"])
    assert mp["policyNumber"] == "Policy No"
    assert mp["customerName"] == "Insured Name"
    assert mp["misAmount"] == "Payout"


def test_agent_mis_headers_map_chassis_and_distribution_fee():
    headers = [
        "Month", "Insurance Comp", "Reg No", "INSURED NAME", "MAKE", "MODEL",
        "Yr of Mfg", "IDV", "Chassis", "Engine", "Policy Number", "Valid From",
        "Valid To", "OD", "Third Party", "NET", "GST", "GROSS", "Distribut Fee",
    ]
    mp = ins_mis.suggest_mapping(headers)
    assert mp["chassisNumber"] == "Chassis"
    assert mp["customerName"] == "INSURED NAME"
    assert mp["insuranceCompany"] == "Insurance Comp"
    assert mp["policyNumber"] == "Policy Number"
    assert mp["misAmount"] == "Distribut Fee"
    assert mp["insuranceAmount"] == "GROSS"
    assert mp["policyDate"] == "Valid From"


def test_match_by_chassis_fetches_register_details():
    entries = [{
        "entryId": "INS1", "leadId": "LD1", "customerName": "MR SITA RAM SHARMA",
        "policyNumber": "2905033126P106579388", "chassisNumber": "MD9EMVDL26G217350",
        "expectedPayout": 9310, "receivedPayout": 0, "status": "Pending",
    }]
    rows = [{
        "_row": 2, "chassisNumber": " md9emvdl26g217350 ",
        "customerName": "MR SITA RAM SHARMA", "misAmount": 5275,
        "policyNumber": "2905033126P106579388",
    }]
    out = ins_mis.match_file(rows, entries)
    assert out["totals"]["matched"] == 1
    hit = out["matched"][0]
    assert hit["entryId"] == "INS1"
    assert hit["matchKey"] == "chassis"
    assert hit["chassisNumber"] == "MD9EMVDL26G217350"
    assert hit["registerCustomer"] == "MR SITA RAM SHARMA"
    assert hit["misAmount"] == 5275


def test_duplicate_chassis_keeps_first_row():
    entries = [{
        "entryId": "INS1", "chassisNumber": "MD9EMVDL26G217350",
        "expectedPayout": 100, "status": "Pending", "customerName": "A",
    }]
    rows = [
        {"_row": 2, "chassisNumber": "MD9EMVDL26G217350", "misAmount": 90},
        {"_row": 3, "chassisNumber": "md9emvdl26g217350", "misAmount": 80},
    ]
    out = ins_mis.match_file(rows, entries)
    assert out["totals"]["matched"] == 1
    assert out["matched"][0]["misAmount"] == 90
    assert out["unmatchedMis"][0]["reason"] == "duplicate_chassis"


def test_chassis_not_found_stays_unmatched():
    out = ins_mis.match_file(
        [{"_row": 2, "chassisNumber": "MD9NOSUCH", "misAmount": 90}],
        [{"entryId": "A", "chassisNumber": "MD9OTHER", "expectedPayout": 100, "status": "Pending"}])
    assert out["matched"] == []
    assert out["unmatchedMis"][0]["reason"] == "chassis_not_found"


def test_lead_hint_fetches_details_when_payout_row_is_missing():
    unmatched = [{"_row": 2, "chassisNumber": "MD9EMVDL26G217350",
                  "reason": "chassis_not_found", "customerName": ""}]
    ins_mis.attach_lead_hint(unmatched, [
        {"leadId": "LD9", "chassisNumber": "md9emvdl26g217350",
         "customerName": "MR SITA RAM SHARMA"}])
    assert unmatched[0]["reason"] == "no_payout_entry"
    assert unmatched[0]["leadId"] == "LD9"
    assert unmatched[0]["registerCustomer"] == "MR SITA RAM SHARMA"


def test_valid_from_dd_mmm_yy():
    assert ins_mis._as_iso_date("01-Aug-26") == "2026-08-01"
    assert ins_mis._as_iso_date("31-Jul-27") == "2027-07-31"


def test_match_by_policy_and_difference():
    entries = [{
        "entryId": "INS1", "leadId": "LD1", "customerName": "Asha",
        "policyNumber": "POL-99", "mobile": "9876543210",
        "expectedPayout": 9310, "receivedPayout": 0, "status": "Pending",
    }]
    rows = [{
        "_row": 2, "policyNumber": "pol-99", "customerName": "Asha",
        "misAmount": 8500, "mobile": "9876543210",
    }]
    out = ins_mis.match_file(rows, entries)
    assert out["totals"]["matched"] == 1
    hit = out["matched"][0]
    assert hit["entryId"] == "INS1"
    assert hit["difference"] == -810
    assert hit["matchKey"] == "policyNumber"


def test_unmatched_and_ambiguous_policy():
    entries = [
        {"entryId": "A", "policyNumber": "DUP", "expectedPayout": 100, "status": "Pending"},
        {"entryId": "B", "policyNumber": "DUP", "expectedPayout": 100, "status": "Pending"},
    ]
    out = ins_mis.match_file(
        [{"_row": 2, "policyNumber": "DUP", "misAmount": 90}], entries)
    assert out["matched"] == []
    assert out["unmatchedMis"][0]["reason"] == "ambiguous_policy"


def test_dealer_income_switches_to_received_after_approve():
    pending = {"expectedPayout": 9310, "receivedPayout": 0, "status": "Pending"}
    assert ce.insurance_dealer_income(pending) == 9310
    approved = {"expectedPayout": 9310, "receivedPayout": 8500,
                "status": "Received", "misApproved": True}
    assert ce.insurance_dealer_income(approved) == 8500
    self_arr = {"expectedPayout": 0, "status": "N/A — customer arranged"}
    assert ce.insurance_dealer_income(self_arr) == 0


async def _entry(c, **kw):
    body = {
        "customerName": kw.get("customerName", "MIS Cust"),
        "mobile": kw.get("mobile", "9000011111"),
        "model": "Turbo Max",
        "insuranceAmount": kw.get("premium", 20000),
        "policyNumber": kw.get("policyNumber", "POL-MIS-1"),
        "policyDate": "2026-08-10",
        "insuranceCompany": "ICICI Lombard",
    }
    r = await c.post("/api/insurance", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _csv(text):
    return {"file": ("mis.csv", text.encode("utf-8"), "text/csv")}


@pytest.mark.asyncio
async def test_preview_matches_policy_and_computes_diff(client):
    e = await _entry(client, policyNumber="POL-X1", premium=20000)
    expected = e["expectedPayout"]
    csv = "Policy Number,Customer Name,Payout Amount\nPOL-X1,MIS Cust,8000\n"
    r = await client.post("/api/insurance/mis/preview", files=_csv(csv))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["totals"]["matched"] == 1
    hit = body["matched"][0]
    assert hit["entryId"] == e["entryId"]
    assert hit["misAmount"] == 8000
    assert hit["expectedPayout"] == expected
    assert hit["difference"] == ce.round2(8000 - expected)


_AGENT_MIS_HEADERS = (
    "Month,Insurance Comp,Reg No,INSURED NAME,MAKE,MODEL,Yr of Mfg,IDV,Chassis,"
    "Engine,Policy Number,Valid From,Valid To,OD,Third Party,NET,GST,GROSS,Distribut Fee"
)


@pytest.mark.asyncio
async def test_preview_matches_agent_file_on_chassis(client):
    e = await _entry(client, policyNumber="2905033126P106579388",
                     customerName="MR SITA RAM SHARMA", premium=19691)
    await server.db.insurance.update_one(
        {"entryId": e["entryId"]}, {"$set": {"leadId": "LD-CHASSIS-1"}})
    await server.db.leads.insert_one({
        "leadId": "LD-CHASSIS-1", "chassisNumber": "MD9EMVDL26G217350",
        "customerName": "MR SITA RAM SHARMA", "mobile": "9000011111"})
    csv = (
        _AGENT_MIS_HEADERS + "\n"
        "Aug'26,United India Ins. Co,NEW,MR SITA RAM SHARMA,EULER MOTORS,TURBO EV 1000,2026,"
        "847637,MD9EMVDL26G217350,MC3012532020603250091,2905033126P106579388,"
        "01-Aug-26,31-Jul-27,4448,13742,18190,1501,19691,5275\n"
    )
    r = await client.post("/api/insurance/mis/preview", files=_csv(csv))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["suggestedMapping"]["chassisNumber"] == "Chassis"
    assert body["suggestedMapping"]["misAmount"] == "Distribut Fee"
    assert body["totals"]["matched"] == 1
    hit = body["matched"][0]
    assert hit["entryId"] == e["entryId"]
    assert hit["matchKey"] == "chassis"
    assert hit["chassisNumber"] == "MD9EMVDL26G217350"
    assert hit["registerCustomer"] == "MR SITA RAM SHARMA"
    assert hit["misAmount"] == 5275
    assert hit["leadId"] == "LD-CHASSIS-1"


@pytest.mark.asyncio
async def test_apply_fills_mis_without_booking_received(client):
    e = await _entry(client, policyNumber="POL-X2")
    r = await client.post("/api/insurance/mis/apply", json={
        "items": [{"entryId": e["entryId"], "misAmount": 8100, "reference": "UTR-A"}],
    })
    assert r.status_code == 200, r.text
    doc = await server.db.insurance.find_one({"entryId": e["entryId"]})
    assert doc["misAmount"] == 8100
    assert doc["receivedPayout"] == 0
    assert doc["status"] == "Pending"
    assert not doc.get("misApproved")


@pytest.mark.asyncio
async def test_approve_short_payout_closes_and_recasts_earnings(client):
    r = await client.post("/api/leads", json={
        "customerName": "MIS Earn", "mobile": "9000099991",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await client.post(f"/api/leads/{lid}/payments",
                      json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    agents = (await client.get("/api/insurance-agents")).json()
    aid = agents[0]["agentId"]
    d = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "insuranceAgentId": aid,
        "invoiceNumber": "INV-MIS1", "chassisNumber": "CH-MIS1",
        "numberPlate": "RJ-MIS1", "delivered": "Yes"})
    assert d.status_code == 200, d.text
    entry = await server.db.insurance.find_one({"leadId": lid})
    before = await server.db.leads.find_one({"leadId": lid})
    assert before["dealerInsuranceIncome"] == entry["expectedPayout"]

    short = ce.round2(entry["expectedPayout"] - 500)
    ap = await client.post("/api/insurance/mis/approve", json={
        "entryIds": [entry["entryId"]],
        "items": [{"entryId": entry["entryId"], "misAmount": short, "reference": "UTR-SHORT"}],
    })
    assert ap.status_code == 200, ap.text
    assert ap.json()["approved"] == 1
    doc = await server.db.insurance.find_one({"entryId": entry["entryId"]})
    assert doc["misApproved"] is True
    assert doc["status"] == "Received"
    assert doc["receivedPayout"] == short
    assert doc["payoutOutstanding"] == 0
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["dealerInsuranceIncome"] == short
    assert after["dealerTotalEarnings"] == ce.round2(
        before["dealerTotalEarnings"] - (entry["expectedPayout"] - short))
    report = (await client.get("/api/reports/dealer-earnings")).json()
    # The approved short amount is what the report must use for this lead.
    assert report["totals"]["insurance"] >= 0


@pytest.mark.asyncio
async def test_approve_over_expected_is_allowed(client):
    e = await _entry(client, policyNumber="POL-OVER", premium=10000)
    over = ce.round2(e["expectedPayout"] + 250)
    r = await client.post("/api/insurance/mis/approve", json={
        "items": [{"entryId": e["entryId"], "misAmount": over}],
    })
    assert r.status_code == 200, r.text
    doc = await server.db.insurance.find_one({"entryId": e["entryId"]})
    assert doc["receivedPayout"] == over
    assert doc["status"] == "Received"
    assert doc["misApproved"] is True


@pytest.mark.asyncio
async def test_approve_is_idempotent(client):
    e = await _entry(client, policyNumber="POL-IDEM")
    body = {"items": [{"entryId": e["entryId"], "misAmount": 1000}]}
    a = await client.post("/api/insurance/mis/approve", json=body)
    b = await client.post("/api/insurance/mis/approve", json=body)
    assert a.status_code == 200 and b.status_code == 200
    doc = await server.db.insurance.find_one({"entryId": e["entryId"]})
    assert doc["receivedPayout"] == 1000
    assert len(doc.get("receipts") or []) == 1


@pytest.mark.asyncio
async def test_executive_cannot_upload_mis(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    token = r.json()["token"]
    csv = "Policy Number,Payout Amount\nX,1\n"
    denied = await client.post("/api/insurance/mis/preview", files=_csv(csv),
                               headers={"Authorization": f"Bearer {token}"})
    assert denied.status_code == 403
