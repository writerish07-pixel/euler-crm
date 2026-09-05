"""Insurance mapped≠received, Extra Support drop, unpayable OEM write-off."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "claim_mis_earnings_v1")
os.environ.setdefault("JWT_SECRET", "claim-mis-earnings-secret-32ch")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import oem_claims  # noqa: E402
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


def test_insurance_income_is_cash_only():
    pending = {"expectedPayout": 9310, "receivedPayout": 0, "status": "Pending"}
    assert ce.insurance_dealer_income(pending) == 0
    mapped = {"expectedPayout": 9310, "receivedPayout": 0, "status": "Pending",
              "misApproved": True, "misAmount": 8500}
    assert ce.insurance_dealer_income(mapped) == 0
    adopted = {"expectedPayout": 8500, "receivedPayout": 0, "status": "Pending",
               "misApproved": True, "misAmount": 8500, "misAmountAdopted": True}
    assert ce.insurance_dealer_income(adopted) == 8500
    paid = {"expectedPayout": 9310, "receivedPayout": 8500, "status": "Received"}
    assert ce.insurance_dealer_income(paid) == 8500
    assert ce.insurance_dealer_income({"status": "N/A — customer arranged"}) == 0


def test_unpayable_write_off_uses_register_amount():
    claims = [
        {"componentKey": "loyaltyBonus", "claimStatus": "Rejected",
         "oemMatchState": "rejected", "eligibleClaim": 4000},
        {"componentKey": "oemExtraSupport", "claimStatus": "Dropped",
         "droppedAmount": 7000, "eligibleClaim": 0},
        {"componentKey": "insuranceBenefit", "claimStatus": "Rejected",
         "oemMatchState": "resubmitted", "eligibleClaim": 20000},
    ]
    wo = ce.unpayable_write_off_from_claims(claims)
    assert wo["oemUnpayableScheme"] == 4000
    assert wo["oemUnpayableExtraSupport"] == 7000
    assert wo["oemUnpayableWriteOff"] == 11000
    assert wo["extraSupportUnpayable"] is True


def test_oem_cancelled_maps_to_cancelled():
    assert oem_claims.register_status_from_oem("Cancelled", "Submitted") == "Cancelled"
    assert oem_claims.register_status_from_oem("Rejected", "Dropped") == "Dropped"
    assert oem_claims.register_status_from_oem("Settled", "Pending") == "Approved"


@pytest.mark.asyncio
async def test_mis_approve_maps_without_receiving(client):
    e = await client.post("/api/insurance", json={
        "customerName": "Map Only", "mobile": "9000010001", "model": "Turbo Max",
        "insuranceAmount": 19000, "policyNumber": "POL-MAP-1", "policyDate": "2026-08-10",
        "insuranceCompany": "ICICI Lombard",
    })
    assert e.status_code == 200, e.text
    eid = e.json()["entryId"]
    ap = await client.post("/api/insurance/mis/approve", json={
        "entryIds": [eid],
        "items": [{"entryId": eid, "misAmount": 8000, "reference": "UTR-MAP"}],
    })
    assert ap.status_code == 200, ap.text
    doc = await server.db.insurance.find_one({"entryId": eid})
    assert doc["misApproved"] is True
    assert doc["misAmount"] == 8000
    assert doc["receivedPayout"] == 0
    assert doc["status"] == "Pending"
    assert ce.insurance_dealer_income(doc) == 0


@pytest.mark.asyncio
async def test_repair_undoes_mis_only_received(client):
    e = await client.post("/api/insurance", json={
        "customerName": "Was Fake Received", "mobile": "9000010002", "model": "Turbo Max",
        "insuranceAmount": 19000, "policyNumber": "POL-FAKE-1",
    })
    eid = e.json()["entryId"]
    await server.db.insurance.update_one({"entryId": eid}, {"$set": {
        "misApproved": True, "status": "Received", "receivedPayout": 9310,
        "payoutOutstanding": 0,
        "receipts": [{"amount": 9310, "date": "2026-08-15", "source": "mis",
                      "reference": "MIS approve", "recordedAt": "2026-08-15T00:00:00+00:00"}],
    }})
    n = await server._repair_mis_only_received()
    assert n >= 1
    doc = await server.db.insurance.find_one({"entryId": eid})
    assert doc["status"] == "Pending"
    assert doc["receivedPayout"] == 0
    assert doc["misApproved"] is True


@pytest.mark.asyncio
async def test_drop_extra_support_recasts_earnings(client):
    r = await client.post("/api/leads", json={
        "customerName": "Drop Extra", "mobile": "9000010003",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    await client.put(f"/api/leads/{lid}/scheme", json={
        "oemExtraSupportReceived": 7000, "oemExtraSupportPassed": 0,
        "additionalDiscount": 0, "loyaltyBonus": 0, "consumerDiscount": 0,
        "exchangeBonus": 0, "referralBonus": 0, "dsaDiscount": 0,
    })
    before = await server.db.leads.find_one({"leadId": lid})
    assert before["oemExtraSupportRetained"] == 7000
    claims = (await client.get("/api/claims")).json()
    extra = next(c for c in claims if c["leadId"] == lid and c["componentKey"] == "oemExtraSupport")
    drop = await client.post("/api/claims/drop-extra-support",
                             json={"claimId": extra["claimId"], "reason": "OEM will not approve"})
    assert drop.status_code == 200, drop.text
    assert drop.json()["droppedAmount"] == 7000
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["oemExtraSupportReceived"] == 0
    assert after["oemExtraSupportRetained"] == 0
    assert after["dealerTotalEarnings"] == ce.round2(
        before["dealerTotalEarnings"] - 7000)
    listed = (await client.get("/api/dropped-extra-support")).json()
    assert listed[0]["droppedAmount"] == 7000
    claim = await server.db.claims.find_one({"claimId": extra["claimId"]})
    assert claim["claimStatus"] == "Dropped"


@pytest.mark.asyncio
async def test_rejected_unrefileable_deducts_scheme_claim(client):
    r = await client.post("/api/leads", json={
        "customerName": "Reject Claim", "mobile": "9000010004",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    claim = {
        "claimId": f"CLM-{lid}-loyaltyBonus",
        "leadId": lid, "componentKey": "loyaltyBonus",
        "eligibleClaim": 10000, "claimAmount": 10000,
        "receivedAmount": 0, "claimStatus": "Pending", "manual": False,
    }
    await server.db.claims.insert_one(dict(claim))
    before = await server.db.leads.find_one({"leadId": lid})
    await server.db.claims.update_one({"claimId": claim["claimId"]}, {"$set": {
        "claimStatus": "Rejected", "oemMatchState": "rejected",
    }})
    await server.recompute_lead(lid)
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["oemUnpayableWriteOff"] == 10000
    assert after["dealerTotalEarnings"] == ce.round2(before["dealerTotalEarnings"] - 10000)
    de = (await client.get("/api/dealer-earnings")).json()
    row = next(x for x in de["rows"] if x["leadId"] == lid)
    assert row["oemUnpayableWriteOff"] == 10000
