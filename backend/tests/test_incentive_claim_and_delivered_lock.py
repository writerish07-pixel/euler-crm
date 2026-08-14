"""Incentive sheet sync + paid → OEM claim; delivered/closed lead freeze."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "incentive_claim_delivered_lock")
os.environ.setdefault("JWT_SECRET", "incentive-claim-lock-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import gsheets  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402


def test_incentive_register_is_in_sync_map():
    assert "incentive_register" in gsheets.SYNC_MAP
    tab, id_field, cols, _hdr = gsheets.SYNC_MAP["incentive_register"]
    assert tab == "Incentive Register"
    assert id_field == "incentiveId"
    for required in ("incentiveId", "executive", "leadId", "incentiveAmount", "status", "paidDate"):
        assert required in cols


@pytest_asyncio.fixture
async def client(monkeypatch):
    sync_calls = []

    async def capture_sync(entity, doc, *, entity_id=""):
        sync_calls.append({"entity": entity, "doc": dict(doc)})
        return {"ok": True, "skipped": True, "reason": "test-capture"}

    monkeypatch.setattr(server, "sheet_sync", capture_sync)
    await server.startup()
    await server.db.incentive_master.delete_many({})
    await server.db.incentive_master.insert_one({
        "incentiveId": "IM-TEST", "productCategory": "Turbo",
        "incentivePerRetail": 3000, "minRetails": 0, "maxSlab": 0,
        "schemeMonth": "2026-08", "effectiveFrom": "2026-08-01",
        "effectiveTo": "2026-08-31", "status": "Active", "circularRef": "TEST",
    })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c._sync_calls = sync_calls
        yield c


async def _login(c, email="owner@euler.com"):
    r = await c.post("/api/auth/login", json={"email": email, "password": "euler@123"})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})


async def _booked_priced_lead(c, mobile):
    r = await c.post("/api/leads", json={
        "customerName": "Inc Lead", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await c.post(f"/api/leads/{lid}/payments",
                 json={"amount": lead["customerOutstanding"], "paymentMode": "Cash", "date": "2026-08-10"})
    return lid


@pytest.mark.asyncio
async def test_delivery_syncs_incentive_register_to_sheet(client):
    await _login(client)
    lid = await _booked_priced_lead(client, "9111100001")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI", "invoiceNumber": "INV-INC-1", "chassisNumber": "CH-INC-1",
        "numberPlate": "RJ14-INC-1", "delivered": "Yes", "deliveryDate": "2026-08-11",
    })
    assert r.status_code == 200, r.text
    row = await server.db.incentive_register.find_one({"leadId": lid})
    assert row is not None
    assert ce.num(row["incentiveAmount"]) == 3000
    assert row["status"] == "Pending"
    synced = [s for s in client._sync_calls if s["entity"] == "incentive_register"]
    assert synced, "Incentive Register must sync to Google Sheet on create"
    assert synced[-1]["doc"]["incentiveId"] == row["incentiveId"]
    assert synced[-1]["doc"]["incentiveAmount"] == 3000


@pytest.mark.asyncio
async def test_mark_paid_opens_oem_claim_and_syncs_sheet(client):
    await _login(client)
    lid = await _booked_priced_lead(client, "9111100002")
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI", "invoiceNumber": "INV-INC-2", "chassisNumber": "CH-INC-2",
        "numberPlate": "RJ14-INC-2", "delivered": "Yes", "deliveryDate": "2026-08-11",
    })
    inc = await server.db.incentive_register.find_one({"leadId": lid})
    r = await client.put(f"/api/incentive-register/{inc['incentiveId']}/pay",
                         json={"paidDate": "2026-08-12"})
    assert r.status_code == 200, r.text
    paid = await server.db.incentive_register.find_one({"incentiveId": inc["incentiveId"]})
    assert paid["status"] == "Paid"
    claim = await server.db.claims.find_one({
        "leadId": lid, "componentKey": f"executiveIncentive-{inc['incentiveId']}"})
    assert claim is not None
    assert claim["manual"] is True
    assert claim["eligibleClaim"] == 3000
    assert claim["claimAmount"] == 3000
    assert claim["oemDiscount"] == 3000
    assert claim["totalDiscount"] == 3000
    assert claim["claimStatus"] == "Pending"
    assert claim["receivedAmount"] == 0

    claims = (await client.get("/api/claims")).json()
    match = [c for c in claims if c.get("componentKey", "").startswith("executiveIncentive")
             and c["leadId"] == lid]
    assert len(match) == 1
    assert match[0]["eligibleClaim"] == 3000

    dash = (await client.get("/api/reports/oem-claim-dashboard")).json()
    assert dash["valueSummary"]["executiveIncentiveClaim"] >= 3000
    assert any(s["scheme"] == "Executive Incentive" for s in dash["schemeWise"])

    synced_inc = [s for s in client._sync_calls
                  if s["entity"] == "incentive_register" and s["doc"].get("status") == "Paid"]
    assert synced_inc
    synced_claims = [s for s in client._sync_calls
                     if s["entity"] == "claims"
                     and str(s["doc"].get("componentKey", "")).startswith("executiveIncentive")]
    assert synced_claims


@pytest.mark.asyncio
async def test_delivered_lead_locked_for_staff_editable_for_owner(client):
    await _login(client)
    lid = await _booked_priced_lead(client, "9111100003")
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI", "invoiceNumber": "INV-LOCK-1", "chassisNumber": "CH-LOCK-1",
        "numberPlate": "RJ14-LOCK-1", "delivered": "Yes", "deliveryDate": "2026-08-11",
    })
    lead = await server.db.leads.find_one({"leadId": lid})

    # Staff / no-role view: still frozen after delivery
    staff = server.lead_actions(lead, {"role": "executive"})
    assert staff["isLocked"] is True
    assert staff["canEditLead"] is False
    assert staff["canPrice"] is False
    assert staff["canScheme"] is False
    assert staff["canPayment"] is False
    assert staff["canClose"] is True

    # Owner: editable until closed
    owner = server.lead_actions(lead, {"role": "owner"})
    assert owner["isLocked"] is False
    assert owner["canEditLead"] is True
    assert owner["canPrice"] is True
    assert owner["canScheme"] is True
    assert owner["canPayment"] is True
    assert owner["canClose"] is True
    assert owner["isDelivered"] is True

    r = await client.put(f"/api/leads/{lid}", json={"customerName": "Owner Fix"})
    assert r.status_code == 200, r.text
    r = await client.put(f"/api/leads/{lid}/price-structure",
                         json={"exShowroom": lead.get("exShowroom") or 1, "rto": lead.get("rto") or 0,
                               "insuranceAmount": lead.get("insuranceAmount") or 0,
                               "accessoriesAmount": 0, "handlingCharges": 0, "trc": 0,
                               "fastag": 0, "extendedWarranty": 0, "otherCharges": 0,
                               "rsaAmc": 0, "tcsApplicable": "No", "finalExchangeValue": 0})
    assert r.status_code == 200, r.text
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI", "invoiceNumber": "INV-LOCK-1", "chassisNumber": "CH-LOCK-1",
        "numberPlate": "RJ14-LOCK-1", "delivered": "Yes", "deliveryDate": "2026-08-11",
    })
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_closed_lead_cannot_be_edited(client):
    await _login(client)
    lid = await _booked_priced_lead(client, "9111100004")
    r = await client.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Lost — test", "closedDate": "2026-08-11"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["accountStatus"] == "Closed"
    assert lead["currentStatus"] == "Close Won"
    acts = server.lead_actions(lead, {"role": "owner"})
    assert acts["isLocked"] is True
    assert acts["canEditLead"] is False
    r = await client.put(f"/api/leads/{lid}", json={"remarks": "nope"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_active_non_delivered_still_editable(client):
    await _login(client)
    lid = await _booked_priced_lead(client, "9111100005")
    lead = await server.db.leads.find_one({"leadId": lid})
    acts = server.lead_actions(lead, {"role": "owner"})
    assert acts["isLocked"] is False
    assert acts["canEditLead"] is True
    r = await client.put(f"/api/leads/{lid}", json={"remarks": "ok"})
    assert r.status_code == 200, r.text
