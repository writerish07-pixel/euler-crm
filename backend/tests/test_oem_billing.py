"""OEM Billing tab: Sold vs CRM, match-only sync, relink Created-from-OEM stubs."""
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
async def test_oem_billing_sync_does_not_create_missing_lead(client):
    chassis = "MD9BILLNEW0001"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"chassisNumber": chassis})
    await server.db.leads.delete_many({"mobile": "9812200222"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812200222", "invoiceNumber": "CINV-NEW",
        "customerName": "New From Oem", "model": "Hi-Load", "variant": "XR",
        "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 0
    assert await server.db.leads.find_one({"chassisNumber": chassis}) is None
    row = next(x for x in body["rows"] if x["chassis"] == chassis)
    assert row["bucket"] == "unmatched"
    assert not row["leadId"]


@pytest.mark.asyncio
async def test_oem_billing_explicit_create_for_unmatched(client):
    chassis = "MD9BILLMAKE01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"chassisNumber": chassis})
    await server.db.leads.delete_many({"mobile": "9812200888"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812200888", "invoiceNumber": "CINV-MAKE",
        "customerName": "Make After Review", "model": "Hi-Load", "variant": "XR",
        "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    denied = await client.post("/api/oem-billing/create", json={"chassis": chassis})
    # still unmatched — create is allowed
    assert denied.status_code == 200, denied.text
    lead = await server.db.leads.find_one({"chassisNumber": chassis})
    assert lead is not None
    assert lead["oemBillingCreated"] is True
    assert lead["currentStatus"] == "New"
    assert lead["invoiceNumber"] == "CINV-MAKE"
    again = await client.post("/api/oem-billing/create", json={"chassis": chassis})
    assert again.status_code == 409


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
    assert r.json()["created"] == 0
    second = await server.db.leads.find_one({"chassisNumber": chassis})
    assert second is None
    hit = next(row for row in r.json()["rows"] if row["chassis"] == chassis)
    assert hit["bucket"] == "unmatched"
    assert not hit["leadId"]


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
    assert r.json()["created"] == 0
    created = []
    async for lead in server.db.leads.find({"customerName": name}):
        created.append(lead)
    assert len(created) == 1
    first = await server.db.leads.find_one({"leadId": first_id})
    assert first["additionalDiscount"] == 50000
    assert first.get("exShowroom") == 999999
    assert not server._is_delivered(first)
    assert first.get("sameOrderMultiUnit") is True
    units = first.get("units") or []
    assert len(units) == 5
    chassis = {oem_sync._norm_chassis(first.get("chassisNumber"))}
    chassis.update(oem_sync._norm_chassis(u.get("chassisNumber")) for u in units)
    chassis.discard("")
    assert chassis == {row[0] for row in chassis_rows}
    extras = units[1:]
    assert len(extras) == 4
    for unit in extras:
        assert float(unit.get("additionalDiscount") or 0) == 0
        assert float(unit.get("exShowroom") or 0) != 999999
    docs = [d async for d in server.db[server.lead_docs.COLLECTION].find(
        {"leadId": first_id})]
    kinds = {d["kind"] for d in docs}
    assert "kyc_pan" in kinds
    hiload = [u for u in extras if (u.get("model") or "").lower().startswith("hi")]
    turbo = [u for u in extras if "turbo" in (u.get("model") or "").lower()]
    assert hiload and turbo
    if hiload and turbo and float(hiload[0].get("exShowroom") or 0) and float(turbo[0].get("exShowroom") or 0):
        assert float(hiload[0]["exShowroom"]) != float(turbo[0]["exShowroom"])


@pytest.mark.asyncio
async def test_oem_billing_open_lead_one_sold_appends_not_new_id(client):
    name = "Single Leftover"
    lid = "LD-OPEN-ONE"
    mobile = "9812200666"
    chassis = "MD9OPENONE01"
    await server.db.leads.delete_many({"$or": [{"leadId": lid}, {"mobile": mobile}]})
    await server.db.oem_sold.delete_many({"mobile": mobile})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": name, "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-OPEN1",
        "customerName": name, "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-09-08", "coulsonStatus": "SOLD",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    assert await server.db.leads.count_documents({"mobile": mobile}) == 1
    lead = await server.db.leads.find_one({"leadId": lid})
    assert chassis in set(oem_sync.lead_chassis_list(lead))


@pytest.mark.asyncio
async def test_oem_billing_split_siblings_do_not_mint_another_id(client):
    name = "Already Split"
    mobile = "9812200777"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.oem_sold.delete_many({"mobile": mobile})
    await server.db.leads.insert_one({
        "leadId": "LD-SPLIT-A", "customerName": name, "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "interestedModel": "Turbo Max", "chassisNumber": "MD9SPLITA01",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-SPLIT-B", "customerName": name, "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "interestedModel": "Turbo Max", "chassisNumber": "MD9SPLITB01",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9SPLITC01", "mobile": mobile, "invoiceNumber": "CINV-C",
        "customerName": name, "model": "Turbo Max",
        "soldDate": "2026-09-08", "coulsonStatus": "SOLD",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    assert await server.db.leads.count_documents({"mobile": mobile}) == 2


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


def test_pair_stub_to_booked_original_by_mobile():
    pairs = oem_sync.pair_oem_billing_stubs([
        {
            "leadId": "LD-ORIG-BHANA", "customerName": "Bhana Ram Jat",
            "mobile": "9928640160", "accountStatus": "Active",
            "currentStatus": "Booked", "totalReceived": 21000,
        },
        {
            "leadId": "LD26000573", "customerName": "Bhana Ram Jat",
            "mobile": "9928640160", "accountStatus": "Active",
            "currentStatus": "New", "oemBillingCreated": True,
            "chassisNumber": "MD09EVDL26H272002", "invoiceNumber": "AF-122-126270134",
        },
    ])
    assert len(pairs) == 1
    assert pairs[0]["action"] == "safe"
    assert pairs[0]["match"] == "mobile"
    assert pairs[0]["stub"]["leadId"] == "LD26000573"
    assert pairs[0]["original"]["leadId"] == "LD-ORIG-BHANA"


def test_pair_name_only_is_review():
    pairs = oem_sync.pair_oem_billing_stubs([
        {
            "leadId": "LD-ORIG-NAME", "customerName": "Ramsaroop Traders",
            "mobile": "9000000001", "accountStatus": "Active", "currentStatus": "Booked",
        },
        {
            "leadId": "LD-STUB-NAME", "customerName": "Ramsaroop Traders",
            "mobile": "9784285775", "accountStatus": "Active", "currentStatus": "New",
            "oemBillingCreated": True, "chassisNumber": "MD09EVDL26H277440",
        },
    ])
    assert pairs[0]["action"] == "review"
    assert pairs[0]["match"] == "name"
    assert pairs[0]["original"]["leadId"] == "LD-ORIG-NAME"


def test_pair_close_won_august_delivery_is_safe():
    """Close Won + August delivery used to look like 'no booked lead'."""
    pairs = oem_sync.pair_oem_billing_stubs([
        {
            "leadId": "LD26000033", "customerName": "Roshan Sharma",
            "mobile": "9875180032", "accountStatus": "Closed",
            "currentStatus": "Close Won", "deliveryStatus": "Delivered",
            "deliveryDate": "2026-08-11", "totalReceived": 825000,
        },
        {
            "leadId": "LD26000628", "customerName": "ROSHAN SHARMA",
            "mobile": "9875180032", "accountStatus": "Active",
            "currentStatus": "New", "oemBillingCreated": True,
            "chassisNumber": "MD9EMVDL266277773", "invoiceNumber": "AF-122-126270118",
        },
    ])
    assert len(pairs) == 1
    assert pairs[0]["action"] == "safe"
    assert pairs[0]["match"] == "mobile"
    assert pairs[0]["original"]["leadId"] == "LD26000033"
    assert pairs[0]["stub"]["leadId"] == "LD26000628"


def test_pair_second_chassis_on_original_still_unique_mobile():
    pairs = oem_sync.pair_oem_billing_stubs([
        {
            "leadId": "LD-ORIG-FLEET", "customerName": "Fleet",
            "mobile": "9811100444", "accountStatus": "Active", "currentStatus": "Booked",
            "chassisNumber": "MD9FIRST01",
        },
        {
            "leadId": "LD-STUB-FLEET", "customerName": "Fleet",
            "mobile": "9811100444", "accountStatus": "Active", "currentStatus": "New",
            "oemBillingCreated": True, "chassisNumber": "MD9SECOND01",
        },
    ])
    assert pairs[0]["action"] == "safe"
    assert pairs[0]["original"]["leadId"] == "LD-ORIG-FLEET"


@pytest.mark.asyncio
async def test_oem_billing_repair_merges_stub_onto_booked_original(client):
    stub_id = "LD-OEM-STUB-1"
    orig_id = "LD-OEM-ORIG-1"
    chassis = "MD9REPAIR0001"
    mobile = "9812200999"
    await server.db.leads.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.payments.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": orig_id, "customerName": "Kailash Repair", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-08-10", "totalReceived": 21000,
        "customerPayable": 960000, "cxDemand": 960000,
        "additionalDiscount": 11500,
    })
    await server.db.payments.insert_one({
        "leadId": orig_id, "receiptNumber": "RC-REPAIR-1", "amount": 21000,
        "entryType": "Receipt",
    })
    await server.db.leads.insert_one({
        "leadId": stub_id, "customerName": "Kailash Repair", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "oemBillingCreated": True, "leadSource": "OEM Billing",
        "chassisNumber": chassis, "invoiceNumber": "AF-REPAIR-1",
        "totalReceived": 0, "customerPayable": 0,
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "AF-REPAIR-1",
        "customerName": "Kailash Repair", "soldDate": "2026-08-20",
        "coulsonStatus": "SOLD",
    })
    listed = await client.get("/api/oem-billing/repair-pairs")
    assert listed.status_code == 200, listed.text
    body = listed.json()
    pair = next(p for p in body["pairs"] if (p.get("stub") or {}).get("leadId") == stub_id)
    assert pair["action"] == "safe"
    assert pair["original"]["leadId"] == orig_id
    merged = await client.post("/api/oem-billing/repair-merge", json={
        "pairs": [{"stubLeadId": stub_id, "originalLeadId": orig_id}],
    })
    assert merged.status_code == 200, merged.text
    assert merged.json()["mergedCount"] == 1
    original = await server.db.leads.find_one({"leadId": orig_id})
    assert original["chassisNumber"] == chassis
    assert original["invoiceNumber"] == "AF-REPAIR-1"
    assert original["currentStatus"] == "Booked"
    assert original["totalReceived"] == 21000
    assert original["additionalDiscount"] == 11500
    assert await server.db.leads.find_one({"leadId": stub_id}) is None
    assert await server.db.payments.find_one({"leadId": orig_id})
    billed = await client.get("/api/oem-billing", params={"month": "2026-08"})
    hit = next(row for row in billed.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == orig_id
    assert hit["bucket"] == "pending_delivery"


@pytest.mark.asyncio
async def test_oem_billing_repair_merges_onto_august_close_won(client):
    stub_id = "LD-OEM-STUB-ROSHAN"
    orig_id = "LD-OEM-ORIG-ROSHAN"
    chassis = "MD9ROSHAN0001"
    mobile = "9875180032"
    await server.db.leads.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.payments.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": orig_id, "customerName": "Roshan Sharma", "mobile": mobile,
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-08-11",
        "totalReceived": 825000, "customerPayable": 825000,
        "executive": "Amit",
    })
    await server.db.payments.insert_one({
        "leadId": orig_id, "receiptNumber": "RC-ROSHAN-1", "amount": 825000,
        "entryType": "Receipt",
    })
    await server.db.leads.insert_one({
        "leadId": stub_id, "customerName": "ROSHAN SHARMA", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "oemBillingCreated": True, "leadSource": "OEM Billing",
        "chassisNumber": chassis, "invoiceNumber": "AF-122-126270118",
        "totalReceived": 0, "customerPayable": 0,
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "AF-122-126270118",
        "customerName": "ROSHAN SHARMA", "soldDate": "2026-08-11",
        "coulsonStatus": "SOLD",
    })
    listed = await client.get("/api/oem-billing/repair-pairs")
    assert listed.status_code == 200, listed.text
    pair = next(p for p in listed.json()["pairs"] if (p.get("stub") or {}).get("leadId") == stub_id)
    assert pair["action"] == "safe"
    assert pair["original"]["leadId"] == orig_id
    merged = await client.post("/api/oem-billing/repair-merge", json={
        "pairs": [{"stubLeadId": stub_id, "originalLeadId": orig_id}],
    })
    assert merged.status_code == 200, merged.text
    assert merged.json()["mergedCount"] == 1
    original = await server.db.leads.find_one({"leadId": orig_id})
    assert original["chassisNumber"] == chassis
    assert original["invoiceNumber"] == "AF-122-126270118"
    assert original["currentStatus"] == "Close Won"
    assert original["totalReceived"] == 825000
    assert original["executive"] == "Amit"
    assert await server.db.leads.find_one({"leadId": stub_id}) is None
    billed = await client.get("/api/oem-billing", params={"month": "2026-08"})
    hit = next(row for row in billed.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == orig_id
    assert hit["bucket"] == "matched_delivered"
