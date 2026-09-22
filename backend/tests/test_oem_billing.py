"""OEM Billing tab: Sold vs CRM, pending delivery, auto-create missing leads."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "oem_billing_tab_test")
os.environ.setdefault("JWT_SECRET", "oem-billing-secret")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import oem_sync  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_vehicle_sold_date_reads_iso_and_nested():
    assert oem_sync.vehicle_sold_date({"invoice_date": "2026-09-04T11:22:00Z"}) == "2026-09-04"
    assert oem_sync.vehicle_sold_date({"created_at": "2026-08-01"}) == "2026-08-01"
    assert oem_sync.vehicle_sold_date({"billing": {"invoice_date": "05/09/2026"}}) == "2026-09-05"
    assert oem_sync.vehicle_sold_date({"chassis": "X"}) == ""


def test_sold_doc_keeps_sold_date():
    row = oem_sync._sold_doc({
        "chassis": "MD9BILLDATE0001",
        "customer_mobile": "9811100111",
        "invoice_number": "CINV-DATE",
        "customer_name": "Date Customer",
        "invoice_date": "2026-09-08T08:00:00Z",
        "_coulsonStatus": "SOLD",
    }, None, 0)
    assert row["soldDate"] == "2026-09-08"
    assert row["mobile"] == "9811100111"
    assert row["invoiceNumber"] == "CINV-DATE"


def test_classify_pending_delivery_when_lead_is_booked():
    sold = [{
        "chassis": "MD9PEND0001", "mobile": "9811100222", "invoiceNumber": "INV-P",
        "customerName": "Booked One", "model": "Turbo Max", "soldDate": "2026-09-03",
    }]
    leads = [{
        "leadId": "LD-PEND", "customerName": "Booked One", "mobile": "9811100222",
        "accountStatus": "Active", "currentStatus": "Booked",
        "interestedModel": "Turbo Max",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert len(rows) == 1
    assert rows[0]["bucket"] == oem_sync.BUCKET_PENDING
    assert rows[0]["leadId"] == "LD-PEND"
    assert rows[0]["chassis"] == "MD9PEND0001"


def test_classify_unmatched_when_no_crm_lead():
    sold = [{
        "chassis": "MD9MISS0001", "mobile": "9811100333", "invoiceNumber": "INV-M",
        "customerName": "Missing", "soldDate": "2026-09-03",
    }]
    rows = oem_sync.classify_oem_billing(sold, [])
    assert rows[0]["bucket"] == oem_sync.BUCKET_UNMATCHED
    assert not rows[0]["leadId"]


def test_classify_another_vehicle_same_mobile_is_unmatched():
    sold = [{
        "chassis": "MD9SECOND01", "mobile": "9811100444", "invoiceNumber": "INV-2",
        "customerName": "Fleet", "soldDate": "2026-09-03",
    }]
    leads = [{
        "leadId": "LD-FIRST", "customerName": "Fleet", "mobile": "9811100444",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9FIRST01",
        "deliveryDate": "2026-09-02",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["bucket"] == oem_sync.BUCKET_UNMATCHED


@pytest.mark.asyncio
async def test_oem_billing_lists_pending_delivery(client):
    await server.db.oem_sold.delete_many({})
    await server.db.leads.delete_many({"leadId": "LD-BILL-PEND"})
    await server.db.oem_sold.insert_one({
        "chassis": "MD9BILLPEND01", "mobile": "9812200111", "invoiceNumber": "CINV-PEND",
        "customerName": "Pending Bill", "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-09-04", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-BILL-PEND", "customerName": "Pending Bill", "mobile": "9812200111",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-01",
        "deliveryStatus": "Pending",
    })
    r = await client.get("/api/oem-billing", params={"month": "2026-09"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["counts"]["pending_delivery"] >= 1
    hit = next(row for row in body["rows"] if row["chassis"] == "MD9BILLPEND01")
    assert hit["bucket"] == "pending_delivery"
    assert hit["leadId"] == "LD-BILL-PEND"
    assert hit["crmStatus"] == "Booked"


@pytest.mark.asyncio
async def test_oem_billing_sync_creates_missing_lead(client):
    chassis = "MD9BILLNEW0001"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"chassisNumber": chassis})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812200222", "invoiceNumber": "CINV-NEW",
        "customerName": "New From Oem", "model": "Hi-Load", "variant": "XR",
        "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] >= 1
    lead = await server.db.leads.find_one({"chassisNumber": chassis})
    assert lead is not None
    assert lead["leadSource"] == "OEM Billing"
    assert lead["oemBillingCreated"] is True
    assert lead["currentStatus"] == "New"
    assert lead["invoiceNumber"] == "CINV-NEW"
    assert not server._is_delivered(lead)
    created = next(row for row in body["rows"] if row["chassis"] == chassis)
    assert created["bucket"] == "created_from_oem"
    assert created["leadId"] == lead["leadId"]


@pytest.mark.asyncio
async def test_oem_billing_sync_does_not_duplicate_existing_lead(client):
    chassis = "MD9BILLEXIST01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"leadId": "LD-BILL-EXIST"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812200333", "invoiceNumber": "CINV-EX",
        "customerName": "Already Here", "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-BILL-EXIST", "customerName": "Already Here", "mobile": "9812200333",
        "accountStatus": "Active", "currentStatus": "Booked",
        "chassisNumber": chassis, "invoiceNumber": "CINV-EX",
    })
    before = await server.db.leads.count_documents({"mobile": "9812200333"})
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0 or "LD-BILL-EXIST" not in (r.json().get("createdLeadIds") or [])
    after = await server.db.leads.count_documents({"mobile": "9812200333"})
    assert after == before
    hit = next(row for row in r.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == "LD-BILL-EXIST"
    assert hit["bucket"] == "pending_delivery"


@pytest.mark.asyncio
async def test_oem_billing_creates_second_unit_on_same_mobile(client):
    chassis = "MD9BILLUNIT2"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-BILL-UNIT1"]}})
    await server.db.leads.delete_many({"chassisNumber": chassis})
    await server.db.leads.insert_one({
        "leadId": "LD-BILL-UNIT1", "customerName": "Two Units", "mobile": "9812200444",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-02",
        "chassisNumber": "MD9BILLUNIT1", "invoiceNumber": "CINV-U1",
    })
    await server.db.oem_sold.delete_many({"chassis": "MD9BILLUNIT1"})
    await server.db.oem_sold.insert_one({
        "chassis": "MD9BILLUNIT1", "mobile": "9812200444", "invoiceNumber": "CINV-U1",
        "customerName": "Two Units", "soldDate": "2026-09-02", "coulsonStatus": "SOLD",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812200444", "invoiceNumber": "CINV-U2",
        "customerName": "Two Units", "soldDate": "2026-09-06", "coulsonStatus": "SOLD",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] >= 1
    second = await server.db.leads.find_one({"chassisNumber": chassis})
    assert second is not None
    assert second["leadId"] != "LD-BILL-UNIT1"
    assert second["mobile"] == "9812200444"
    assert second["currentStatus"] == "New"


def test_classify_same_name_fleet_leaves_remaining_unmatched():
    sold = [
        {
            "chassis": f"MD9MSC{i:02d}", "customerName": "Messenger SCS",
            "model": "Turbo Max" if i == 1 else "Hi-Load",
            "variant": "Maxx (PV)" if i == 1 else "XR",
            "soldDate": "2026-09-03",
        }
        for i in range(1, 6)
    ]
    leads = [{
        "leadId": "LD-MSC-1", "customerName": "Messenger SCS",
        "accountStatus": "Active", "currentStatus": "New",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert len(rows) == 5
    pending = [r for r in rows if r["bucket"] == oem_sync.BUCKET_PENDING]
    unmatched = [r for r in rows if r["bucket"] == oem_sync.BUCKET_UNMATCHED]
    assert len(pending) == 1
    assert pending[0]["leadId"] == "LD-MSC-1"
    assert len(unmatched) == 4
    assert all(not r["leadId"] for r in unmatched)


@pytest.mark.asyncio
async def test_oem_billing_creates_remaining_same_name_units(client):
    name = "Messenger SCS"
    first_id = "LD-MSC-LIVE"
    await server.db.leads.delete_many({"customerName": name})
    await server.db.leads.delete_many({"leadId": first_id})
    await server.db.oem_sold.delete_many({"customerName": name})
    await server.db[server.lead_docs.COLLECTION].delete_many({"leadId": first_id})
    await server.db.leads.insert_one({
        "leadId": first_id, "customerName": name, "mobile": "9812200555",
        "accountStatus": "Active", "currentStatus": "New",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Amit", "additionalDiscount": 50000, "exShowroom": 999999,
        "customerType": "Individual",
    })
    await server.db[server.lead_docs.COLLECTION].insert_one({
        "documentId": "DC-MSC-PAN", "leadId": first_id, "requestId": "",
        "kind": "kyc_pan", "filename": "pan.png", "contentType": "image/png",
        "size": 12, "uploadedBy": "owner@euler.com", "uploadedByName": "Owner",
        "uploadedAt": "2026-09-01T00:00:00+00:00", "refundReceiptNumber": "",
        "data": b"pan-bytes-ok",
    })
    await server.db[server.lead_docs.COLLECTION].insert_one({
        "documentId": "DC-MSC-RTO", "leadId": first_id, "requestId": "",
        "kind": "delivery_rto", "filename": "rto.pdf", "contentType": "application/pdf",
        "size": 12, "uploadedBy": "owner@euler.com", "uploadedByName": "Owner",
        "uploadedAt": "2026-09-01T00:00:00+00:00", "refundReceiptNumber": "",
        "data": b"rto-bytes-no",
    })
    chassis_rows = [
        ("MD9MSCFLEET01", "Turbo Max", "Maxx (PV)"),
        ("MD9MSCFLEET02", "Hi-Load", "XR"),
        ("MD9MSCFLEET03", "Hi-Load", "XR"),
        ("MD9MSCFLEET04", "Turbo Max", "Maxx (PV)"),
        ("MD9MSCFLEET05", "Hi-Load", "XR"),
    ]
    for chassis, model, variant in chassis_rows:
        await server.db.leads.delete_many({"chassisNumber": chassis})
        await server.db.oem_sold.delete_many({"chassis": chassis})
        await server.db.oem_sold.insert_one({
            "chassis": chassis, "customerName": name, "mobile": "",
            "invoiceNumber": f"CINV-{chassis[-2:]}", "model": model, "variant": variant,
            "soldDate": "2026-09-07", "coulsonStatus": "SOLD",
        })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] >= 4
    created = []
    async for lead in server.db.leads.find({"customerName": name}):
        created.append(lead)
    assert len(created) == 5
    first = await server.db.leads.find_one({"leadId": first_id})
    assert first["additionalDiscount"] == 50000
    assert not server._is_delivered(first)
    extras = [l for l in created if l["leadId"] != first_id]
    assert len(extras) == 4
    for lead in extras:
        assert lead["currentStatus"] == "New"
        assert lead["oemBillingCreated"] is True
        assert not server._is_delivered(lead)
        assert float(lead.get("additionalDiscount") or 0) == 0
        assert float(lead.get("exShowroom") or 0) != 999999
        assert lead.get("executive") == "Amit"
        docs = [d async for d in server.db[server.lead_docs.COLLECTION].find(
            {"leadId": lead["leadId"]})]
        kinds = {d["kind"] for d in docs}
        assert "kyc_pan" in kinds
        assert "delivery_rto" not in kinds
        assert all(d.get("copiedFromLeadId") == first_id for d in docs if d["kind"] == "kyc_pan")
        assert all(d.get("documentId") != "DC-MSC-PAN" for d in docs)
    hiload = [l for l in extras if (l.get("interestedModel") or "").lower().startswith("hi")]
    turbo = [l for l in extras if "turbo" in (l.get("interestedModel") or "").lower()]
    assert hiload and turbo
    if hiload and turbo and float(hiload[0].get("exShowroom") or 0) and float(turbo[0].get("exShowroom") or 0):
        assert float(hiload[0]["exShowroom"]) != float(turbo[0]["exShowroom"])


@pytest.mark.asyncio
async def test_oem_billing_accounts_can_read_not_sync(client):
    email = "acct.billing@euler.com"
    await server.client[os.environ["DB_NAME"]].users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "euler@123", "name": "Accounts", "role": "accounts",
        "loginId": "acct.billing"})
    assert created.status_code == 200, created.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as acct:
        login = await acct.post("/api/auth/login", json={"email": email, "password": "euler@123"})
        assert login.status_code == 200, login.text
        acct.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        listed = await acct.get("/api/oem-billing")
        assert listed.status_code == 200, listed.text
        sync = await acct.post("/api/oem-billing/sync")
        assert sync.status_code == 403


@pytest.mark.asyncio
async def test_oem_billing_executive_forbidden(client):
    email = "exec.billing@euler.com"
    await server.client[os.environ["DB_NAME"]].users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "euler@123", "name": "Exec", "role": "executive",
        "loginId": "exec.billing"})
    assert created.status_code == 200, created.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ex:
        login = await ex.post("/api/auth/login", json={"email": email, "password": "euler@123"})
        assert login.status_code == 200, login.text
        ex.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        r = await ex.get("/api/oem-billing")
        assert r.status_code == 403
