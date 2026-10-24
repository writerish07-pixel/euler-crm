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
import coulson as coulson_client  # noqa: E402
import oem_sync  # noqa: E402
import server  # noqa: E402


@pytest.fixture(autouse=True)
def _no_live_coulson_sold(monkeypatch):
    """OEM Billing tests seed oem_sold themselves. Do not hit Euler."""
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: [])
    monkeypatch.setattr(coulson_client, "fetch_transit_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "fetch_held_inventory", lambda token, limit=200, **k: [])
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "test-token")


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await oem_sync.save_credentials(server.db, "dealer.user", "secret")
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


def test_vehicle_sold_date_reads_coulson_invoice_spa_date():
    """Vehicle Invoices `#/dealer-inventory-list` prints '16 Oct 2026'."""
    assert oem_sync.vehicle_sold_date({"date": "16 Oct 2026"}) == "2026-10-16"
    assert oem_sync.vehicle_sold_date({"_created_at": "2 Sep 2026 13:34:38"}) == "2026-09-02"
    assert oem_sync._iso_date("16 Oct 2026") == "2026-10-16"
    assert oem_sync._iso_date("05-10-2026") == "2026-10-05"
    assert oem_sync.vehicle_sold_date({
        "invoice_creation_ts": "2026-10-16T13:34:38.000Z",
    }) == "2026-10-16"
    assert oem_sync._iso_date("1792108800") == "2026-10-16"
    assert oem_sync._iso_date("1792108800000") == "2026-10-16"


def test_iso_date_uses_india_calendar_not_utc_slice():
    """14 Oct 01:00 IST is 13 Oct 19:30 UTC — Coulson still prints 14 Oct."""
    assert oem_sync._iso_date("2026-10-13T19:30:00.000Z") == "2026-10-14"
    assert oem_sync._iso_date("2026-10-13T18:30:00.000Z") == "2026-10-14"
    assert oem_sync._iso_date("2026-10-13T18:29:00.000Z") == "2026-10-13"
    assert oem_sync.vehicle_sold_date({
        "invoice_creation_ts": "2026-10-13T20:15:00.000Z",
        "created_at": "2026-10-11",
    }) == "2026-10-14"
    assert oem_sync.vehicle_sold_date({
        "date": "14 Oct 2026",
        "invoice_creation_ts": "2026-10-13T20:15:00.000Z",
    }) == "2026-10-14"


def test_billing_day_counts_match_oem_invoice_list():
    rows = [
        {"soldDate": "2026-10-14", "invoiceNumber": "AF-1"},
        {"soldDate": "2026-10-14", "invoiceNumber": "AF-2"},
        {"soldDate": "2026-10-14", "invoiceNumber": "AF-3"},
        {"soldDate": "2026-10-14", "invoiceNumber": "AF-4"},
        {"soldDate": "2026-10-14", "invoiceNumber": "AF-5"},
        {"soldDate": "2026-10-13", "invoiceNumber": "AF-YDAY"},
    ]
    days = {d["date"]: d["count"] for d in oem_sync.billing_day_counts(rows)}
    assert days["2026-10-14"] == 5
    assert days["2026-10-13"] == 1


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


def test_sold_doc_reads_nested_invoice_model():
    row = oem_sync._sold_doc({
        "chassis": "MD9EVDAD26K217428",
        "vehicle": {"model": "Turbo", "variant": "Range Maxx"},
        "invoice_number": "AF-TODAY-1",
        "_coulsonStatus": "INVOICED",
    }, None, 0)
    assert row["model"] == "Turbo"
    assert row["variant"] == "Range Maxx"


def test_sold_doc_falls_back_to_sap_product_name():
    row = oem_sync._sold_doc({
        "chassis": "MD9EVDAD26K217428",
        "sap_product_name": "TURBO RANGEMAXX PV",
        "invoice_number": "AF-TODAY-1",
        "_coulsonStatus": "INVOICED",
    }, None, 0)
    assert row["model"] == "TURBO RANGEMAXX PV"


def test_billing_row_uses_lead_model_when_sold_has_none():
    sold = [{
        "chassis": "MD9NOM01", "mobile": "9811100555", "invoiceNumber": "INV-N",
        "customerName": "Radhe Plastics", "soldDate": "2026-10-16",
    }]
    leads = [{
        "leadId": "LD-NOM", "customerName": "Radhe Plastics", "mobile": "9811100555",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9NOM01",
        "deliveryDate": "2026-10-16",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["model"] == "Turbo Max"
    assert rows[0]["variant"] == "Maxx (PV)"


def test_billing_row_prefers_converted_dv_on_single_file():
    sold = [{
        "chassis": "MD9SOLODV01", "mobile": "9811100777",
        "invoiceNumber": "INV-SOLO", "customerName": "Solo Convert",
        "soldDate": "2026-10-16",
        "model": "Turbo Max", "variant": "Maxx (FB)", "oemSkuKey": "turbo.maxx.fb",
        "updatedLoadBody": "DV220",
    }]
    leads = [{
        "leadId": "LD-SOLO", "customerName": "Solo Convert", "mobile": "9811100777",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9SOLODV01",
        "deliveryDate": "2026-10-16",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["model"] == "Turbo Max"
    assert rows[0]["variant"] == "Maxx (DV220)"
    assert rows[0]["billedBodyType"] == "DV220"
    assert rows[0]["availableBodyType"] == "FB"


def test_billing_row_prefers_pack_dv_over_sold_fb():
    """Chassis sat as FB, converted and billed DV — OEM Billing follows the pack DV."""
    sold = [{
        "chassis": "MD9J217750", "mobile": "8980143558",
        "invoiceNumber": "AF-122-I26270230",
        "customerName": "MessengerSCS", "soldDate": "2026-10-16",
        "model": "Turbo Max", "variant": "Maxx (FB)", "oemSkuKey": "turbo.maxx.fb",
    }]
    leads = [{
        "leadId": "LD26000554", "customerName": "MessengerSCS", "mobile": "8980143558",
        "interestedModel": "Turbo Max", "variant": "Maxx (DV220)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9UNITA01",
        "deliveryDate": "2026-10-16",
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "chassisNumber": "MD9UNITA01", "model": "Turbo Max", "variant": "Maxx (DV220)"},
            {"sno": 6, "chassisNumber": "MD9J217750", "model": "", "variant": ""},
        ],
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["model"] == "Turbo Max"
    assert rows[0]["variant"] == "Maxx (DV220)"


def test_billing_row_uses_pack_unit_model_for_that_chassis():
    sold = [{
        "chassis": "MD9UNITB01", "mobile": "9811100666", "invoiceNumber": "INV-U",
        "customerName": "MessengerSCS", "soldDate": "2026-10-16",
    }]
    leads = [{
        "leadId": "LD-PACK", "customerName": "MessengerSCS", "mobile": "9811100666",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9UNITA01",
        "deliveryDate": "2026-10-16",
        "units": [
            {"sno": 1, "chassisNumber": "MD9UNITA01", "model": "Turbo Max", "variant": "Maxx (PV)"},
            {"sno": 2, "chassisNumber": "MD9UNITB01", "model": "Storm", "variant": "Storm LR (PV)"},
        ],
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["model"] == "Storm"
    assert rows[0]["variant"] == "Storm LR (PV)"


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
    assert lead["currentStatus"] == "Booked"
    assert (lead.get("deliveryStatus") or "") != "Delivered"
    assert lead.get("oemAutoDelivered") is not True
    assert lead.get("oemInvoiced") is True
    assert lead.get("bookingDate") == "2026-09-05"
    assert lead["invoiceNumber"] == "CINV-MAKE"
    assert server._is_booked_lead(lead) is True
    assert server._is_delivered(lead) is False
    assert server._is_followup_enquiry(lead) is False
    listed = (await client.get("/api/leads")).json()
    follow = (await client.get("/api/leads", params={"followup": True})).json()
    assert any(row.get("leadId") == lead["leadId"] for row in listed)
    assert not any(row.get("leadId") == lead["leadId"] for row in follow)
    billed = await client.get("/api/oem-billing?month=2026-09")
    assert billed.status_code == 200, billed.text
    hit = next(x for x in billed.json()["rows"] if x["chassis"] == chassis)
    assert hit["bucket"] == oem_sync.BUCKET_PENDING
    tl = server.lead_actions(lead, {"role": "tl"})
    assert tl["canDeliver"] is True
    assert tl["isLocked"] is False
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
    live = await server.db.leads.find_one({"leadId": "LD-BILL-EXIST"})
    assert live["currentStatus"] == "Booked"
    assert live.get("oemAutoDelivered") is not True
    assert live.get("oemInvoiced") is True
    assert server._is_delivered(live) is False


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
    live = await server.db.leads.find_one({"leadId": "LD-BILL-UNIT1"})
    assert chassis in set(oem_sync.lead_chassis_list(live))
    hit = next(row for row in r.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == "LD-BILL-UNIT1"
    assert hit["bucket"] in ("matched_delivered", "pending_delivery")


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


def test_pair_empty_new_ignores_executive_mismatch():
    pairs = oem_sync.pair_oem_billing_stubs([
        {
            "leadId": "LD26000011", "customerName": "Mohan Singh",
            "mobile": "9251418190", "accountStatus": "Closed",
            "currentStatus": "Close Won", "executive": "Devang",
            "totalReceived": 785000, "chassisNumber": "MD09EMVDL2662191313",
        },
        {
            "leadId": "LD26000505", "customerName": "Mohan Singh",
            "mobile": "9251418190", "accountStatus": "Active",
            "currentStatus": "New", "executive": "Prerna",
            "totalReceived": 0, "chassisNumber": "MD09EMVDL2662191313",
        },
    ])
    assert len(pairs) == 1
    assert pairs[0]["action"] == "safe"
    assert pairs[0]["match"] in ("mobile", "chassis")
    assert pairs[0]["stub"]["leadId"] == "LD26000505"
    assert pairs[0]["original"]["leadId"] == "LD26000011"


def test_classify_two_holders_keeps_close_won():
    sold = [{
        "chassis": "MD09EMVDL2662191313", "mobile": "9251418190",
        "invoiceNumber": "AF-122-126270120", "customerName": "Mohan Singh",
        "soldDate": "2026-08-12",
    }]
    leads = [
        {
            "leadId": "LD26000011", "customerName": "Mohan Singh",
            "mobile": "9251418190", "accountStatus": "Closed",
            "currentStatus": "Close Won", "deliveryStatus": "Delivered",
            "deliveryDate": "2026-08-12", "executive": "Devang",
            "chassisNumber": "MD09EMVDL2662191313", "totalReceived": 785000,
        },
        {
            "leadId": "LD26000505", "customerName": "Mohan Singh",
            "mobile": "9251418190", "accountStatus": "Active",
            "currentStatus": "New", "executive": "Prerna",
            "chassisNumber": "MD09EMVDL2662191313", "totalReceived": 0,
        },
    ]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["bucket"] == oem_sync.BUCKET_DELIVERED
    assert rows[0]["leadId"] == "LD26000011"


@pytest.mark.asyncio
async def test_oem_billing_merges_empty_new_different_executive(client):
    stub_id = "LD26000505"
    orig_id = "LD26000011"
    chassis = "MD9MOHAN0001"
    mobile = "9251418190"
    await server.db.leads.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.payments.delete_many({"leadId": {"$in": [stub_id, orig_id]}})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": orig_id, "customerName": "Mohan Singh", "mobile": mobile,
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-08-12",
        "executive": "Devang", "totalReceived": 785000, "customerPayable": 785000,
        "chassisNumber": chassis, "invoiceNumber": "AF-122-126270120",
    })
    await server.db.payments.insert_one({
        "leadId": orig_id, "receiptNumber": "RC-MOHAN-1", "amount": 785000,
        "entryType": "Receipt",
    })
    await server.db.leads.insert_one({
        "leadId": stub_id, "customerName": "Mohan Singh", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
        "executive": "Prerna", "totalReceived": 0,
        "chassisNumber": chassis,
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "AF-122-126270120",
        "customerName": "Mohan Singh", "soldDate": "2026-08-12",
        "coulsonStatus": "SOLD",
    })
    merged = await client.post("/api/oem-billing/repair-merge", json={
        "pairs": [{"stubLeadId": stub_id, "originalLeadId": orig_id}],
    })
    assert merged.status_code == 200, merged.text
    assert merged.json()["mergedCount"] == 1
    assert await server.db.leads.find_one({"leadId": stub_id}) is None
    original = await server.db.leads.find_one({"leadId": orig_id})
    assert original["executive"] == "Devang"
    assert original["totalReceived"] == 785000
    assert original["chassisNumber"] == chassis
    billed = await client.get("/api/oem-billing", params={"month": "2026-08"})
    hit = next(row for row in billed.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == orig_id
    assert hit["bucket"] != "needs_review"


def test_classify_oem_created_delivered_lead_is_delivered():
    sold = [{
        "chassis": "MD9OEMDEL01", "mobile": "9811199008", "invoiceNumber": "INV-D",
        "customerName": "Billed New", "soldDate": "2026-10-16",
    }]
    leads = [{
        "leadId": "LD-OEM-DEL", "customerName": "Billed New", "mobile": "9811199008",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-10-16",
        "bookingDate": "2026-10-16", "oemBillingCreated": True,
        "oemAutoDelivered": True, "chassisNumber": "MD9OEMDEL01",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["bucket"] == oem_sync.BUCKET_DELIVERED
    assert rows[0]["leadId"] == "LD-OEM-DEL"


def test_classify_oem_created_lead_is_pending_delivery():
    sold = [{
        "chassis": "MD9OEMNEW01", "mobile": "9811199001", "invoiceNumber": "INV-N",
        "customerName": "Kapoor", "soldDate": "2026-09-03",
    }]
    leads = [{
        "leadId": "LD-OEM-NEW", "customerName": "Kapoor", "mobile": "9811199001",
        "accountStatus": "Active", "currentStatus": "New",
        "oemBillingCreated": True, "chassisNumber": "MD9OEMNEW01",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["bucket"] == oem_sync.BUCKET_PENDING
    assert rows[0]["leadId"] == "LD-OEM-NEW"


def test_classify_close_won_is_delivered():
    sold = [{
        "chassis": "MD9CLOSE01", "mobile": "9811199002", "invoiceNumber": "INV-C",
        "customerName": "Hrithik", "soldDate": "2026-09-03",
    }]
    leads = [{
        "leadId": "LD-CLOSE", "customerName": "Hrithik", "mobile": "9811199002",
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "chassisNumber": "MD9CLOSE01",
    }]
    rows = oem_sync.classify_oem_billing(sold, leads)
    assert rows[0]["bucket"] == oem_sync.BUCKET_DELIVERED


@pytest.mark.asyncio
async def test_oem_create_connects_existing_open_lead(client):
    chassis = "MD9CONNECT01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"mobile": "9812299001"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812299001", "invoiceNumber": "CINV-CONN",
        "customerName": "Open File", "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-OPEN-CONN", "customerName": "Open File", "mobile": "9812299001",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-01",
        "executive": "Payal",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    live = await server.db.leads.find_one({"leadId": "LD-OPEN-CONN"})
    assert live["chassisNumber"] == chassis
    assert live.get("oemBillingCreated") is not True
    minted = await server.db.leads.count_documents({"mobile": "9812299001"})
    assert minted == 1
    hit = next(x for x in r.json()["rows"] if x["chassis"] == chassis)
    assert hit["leadId"] == "LD-OPEN-CONN"
    assert hit["bucket"] == oem_sync.BUCKET_PENDING
    assert live["currentStatus"] == "Booked"
    assert live.get("oemAutoDelivered") is not True
    assert live.get("oemInvoiced") is True
    assert server._is_delivered(live) is False


@pytest.mark.asyncio
async def test_oem_create_mints_new_lead_when_prior_file_is_desk_delivered(client):
    chassis = "MD9CONNECT02"
    await server.db.oem_sold.delete_many({"chassis": {"$in": [chassis, "MD9CONNECT01B"]}})
    await server.db.leads.delete_many({"mobile": "9812299008"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812299008", "invoiceNumber": "CINV-CONN2",
        "customerName": "Repeat Buyer", "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-09-08", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-DEL-CONN", "customerName": "Repeat Buyer", "mobile": "9812299008",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-01",
        "chassisNumber": "MD9CONNECT01B", "invoiceNumber": "CINV-OLD",
        "insuranceStatus": "Yes", "registrationStatus": "Yes",
        "executive": "Payal",
    })
    r = await client.post("/api/oem-billing/create", json={"chassis": chassis})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("created") is True
    assert body["leadId"] != "LD-DEL-CONN"
    assert await server.db.leads.count_documents({"mobile": "9812299008"}) == 2
    live = await server.db.leads.find_one({"leadId": body["leadId"]})
    assert chassis in set(oem_sync.lead_chassis_list(live))
    old = await server.db.leads.find_one({"leadId": "LD-DEL-CONN"})
    assert chassis not in set(oem_sync.lead_chassis_list(old))


@pytest.mark.asyncio
async def test_oem_sync_relinks_safe_stub(client):
    chassis = "MD9RELINK01"
    await server.db.oem_sold.delete_many({
        "$or": [{"chassis": chassis}, {"mobile": "9812299002"}],
    })
    await server.db.leads.delete_many({
        "$or": [{"leadId": {"$in": ["LD-ORIG-RL", "LD-STUB-RL"]}},
                {"mobile": "9812299002"}, {"chassisNumber": chassis}],
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812299002", "invoiceNumber": "CINV-RL",
        "customerName": "Hrithik Chopra", "soldDate": "2026-09-05", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-ORIG-RL", "customerName": "Hrithik Chopra", "mobile": "9812299002",
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "totalReceived": 80000, "bookingDate": "2026-09-01",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-STUB-RL", "customerName": "Hrithik Chopra", "mobile": "9812299002",
        "accountStatus": "Active", "currentStatus": "New", "oemBillingCreated": True,
        "chassisNumber": chassis, "invoiceNumber": "CINV-RL", "leadSource": "OEM Billing",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json().get("relinkedCount", 0) >= 1
    assert await server.db.leads.find_one({"leadId": "LD-STUB-RL"}) is None
    orig = await server.db.leads.find_one({"leadId": "LD-ORIG-RL"})
    assert orig["chassisNumber"] == chassis
    hit = next(x for x in r.json()["rows"] if x["chassis"] == chassis)
    assert hit["leadId"] == "LD-ORIG-RL"
    assert hit["bucket"] == oem_sync.BUCKET_DELIVERED


@pytest.mark.asyncio
async def test_oem_sync_attaches_unconverted_lead_and_marks_delivered(client):
    chassis = "MD9AUTODEL01"
    mobile = "9812211001"
    await server.db.oem_sold.delete_many({"$or": [{"chassis": chassis}, {"mobile": mobile}]})
    await server.db.leads.delete_many({
        "$or": [{"leadId": "LD-ENQ-AUTO"}, {"mobile": mobile}, {"chassisNumber": chassis}],
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-AUTO",
        "customerName": "Enquiry One", "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-09-10", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-ENQ-AUTO", "customerName": "Enquiry One", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Follow-up", "executive": "Amit",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 0
    lead = await server.db.leads.find_one({"leadId": "LD-ENQ-AUTO"})
    assert lead["chassisNumber"] == chassis
    assert lead["invoiceNumber"] == "CINV-AUTO"
    assert lead["currentStatus"] == "Booked"
    assert (lead.get("deliveryStatus") or "") != "Delivered"
    assert lead.get("oemAutoDelivered") is not True
    assert lead.get("oemInvoiced") is True
    assert lead.get("bookingDate") == "2026-09-10"
    hit = next(x for x in r.json()["rows"] if x["chassis"] == chassis)
    assert hit["leadId"] == "LD-ENQ-AUTO"
    assert hit["bucket"] == "pending_delivery"
    tl = server.lead_actions(lead, {"role": "tl"})
    assert tl["canScheme"] is True
    assert tl["canPayment"] is True
    assert tl["canDeliver"] is True
    assert tl["isLocked"] is False
    assert tl["isDelivered"] is False
    exec_acts = server.lead_actions(lead, {"role": "executive"})
    assert exec_acts["canBook"] is False
    assert exec_acts["canPayment"] is True


@pytest.mark.asyncio
async def test_oem_sold_cancel_delinks_auto_delivered_then_restamps(client):
    chassis = "MD9CANCELINV01"
    mobile = "9812211002"
    await server.db.oem_sold.delete_many({
        "$or": [{"chassis": chassis}, {"mobile": mobile},
                {"invoiceNumber": {"$in": ["CINV-OLD", "CINV-NEW"]}}],
    })
    await server.db.leads.delete_many({
        "$or": [{"leadId": "LD-CAN-INV"}, {"mobile": mobile},
                {"chassisNumber": chassis},
                {"invoiceNumber": {"$in": ["CINV-OLD", "CINV-NEW"]}}],
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-OLD",
        "customerName": "Cancel Then Rebill", "soldDate": "2026-09-11",
        "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-CAN-INV", "customerName": "Cancel Then Rebill", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "New",
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    first = await server.db.leads.find_one({"leadId": "LD-CAN-INV"})
    assert first.get("oemInvoiced") is True, (
        first, r.json().get("leadsVehicleIds"),
        [x for x in (r.json().get("rows") or []) if x.get("chassis") == chassis],
    )
    assert first.get("oemAutoDelivered") is not True
    assert first["currentStatus"] == "Booked"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    gone = await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert gone["cleared"] >= 1
    cleared = await server.db.leads.find_one({"leadId": "LD-CAN-INV"})
    assert not oem_sync._norm_chassis(cleared.get("chassisNumber"))
    assert cleared.get("oemAutoDelivered") is not True
    assert cleared["currentStatus"] != "Delivered"
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-NEW",
        "customerName": "Cancel Then Rebill", "soldDate": "2026-09-12",
        "coulsonStatus": "SOLD",
    })
    await server._apply_sold_vehicle_ids()
    again = await server.db.leads.find_one({"leadId": "LD-CAN-INV"})
    assert again["chassisNumber"] == chassis
    assert again["invoiceNumber"] == "CINV-NEW"
    assert again.get("oemInvoiced") is True
    assert again.get("oemAutoDelivered") is not True
    assert again["currentStatus"] == "Booked"
    assert again.get("cancelledInvoiceNumber") == "CINV-OLD"
    assert again.get("rebilledInvoiceNumber") == "CINV-NEW"


@pytest.mark.asyncio
async def test_staff_delivered_missing_sold_is_flagged_not_cleared(client):
    chassis = "MD9STAFFDEL01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"leadId": "LD-STAFF-DEL"})
    await server.db.leads.insert_one({
        "leadId": "LD-STAFF-DEL", "customerName": "Staff Done", "mobile": "9812211003",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-01",
        "chassisNumber": chassis, "invoiceNumber": "CINV-STAFF",
    })
    stats = await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert stats["flagged"] >= 1
    lead = await server.db.leads.find_one({"leadId": "LD-STAFF-DEL"})
    assert lead["chassisNumber"] == chassis
    assert lead.get("oemInvoiceMissing") is True


def test_sold_rows_replacing_gone_returns_rebill_not_held():
    lead = {
        "customerName": "Hrithik Chopra", "mobile": "7297021177",
        "sameOrderMultiUnit": True,
        "chassisNumber": "MD9WRONG01",
        "units": [
            {"sno": 1, "chassisNumber": "MD9WRONG01", "invoiceNumber": "OLD-1"},
            {"sno": 2, "chassisNumber": "MD9WRONG02", "invoiceNumber": "OLD-2"},
        ],
    }
    sold = [
        {"chassis": "MD9RIGHT01", "mobile": "7297021177", "invoiceNumber": "NEW-1",
         "customerName": "Hrithik Chopra"},
        {"chassis": "MD9RIGHT02", "mobile": "7297021177", "invoiceNumber": "NEW-2",
         "customerName": "Hrithik Chopra"},
    ]
    rows = oem_sync.sold_rows_replacing_gone(lead, sold)
    got = {oem_sync._norm_chassis(r.get("chassis")) for r in rows}
    assert got == {"MD9RIGHT01", "MD9RIGHT02"}


def test_stamp_family_fills_empty_pack_slots_without_growing():
    lead = {
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Maxx (FB)"},
            {"sno": 2, "model": "Turbo Max", "variant": "Maxx (FB)"},
        ],
    }
    family = [
        {"chassis": "MD9RIGHT01", "invoiceNumber": "NEW-1", "soldDate": "2026-10-05"},
        {"chassis": "MD9RIGHT02", "invoiceNumber": "NEW-2", "soldDate": "2026-10-05"},
    ]
    units = oem_sync.stamp_family_vehicle_ids(lead, family)
    assert len(units) == 2
    assert {oem_sync._norm_chassis(u.get("chassisNumber")) for u in units} == {
        "MD9RIGHT01", "MD9RIGHT02"}


@pytest.mark.asyncio
async def test_staff_delivered_rebill_replaces_cancelled_pack_chassis(client):
    """Wrong chassis cancelled next month, correct ones billed — keep the pack size."""
    old = ["MD9HRITHIKOLD1", "MD9HRITHIKOLD2"]
    new = ["MD9HRITHIKNEW1", "MD9HRITHIKNEW2"]
    mobile = "7297021177"
    lid = "LD26000068"
    await server.db.oem_sold.delete_many({
        "$or": [{"chassis": {"$in": old + new}}, {"mobile": mobile}],
    })
    await server.db.leads.delete_many({"$or": [{"leadId": lid}, {"mobile": mobile}]})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Hrithik Chopra", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-05",
        "insuranceStatus": "Yes", "registrationStatus": "Yes",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "chassisNumber": old[0], "invoiceNumber": "OLD-1",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Maxx (FB)",
             "chassisNumber": old[0], "invoiceNumber": "OLD-1"},
            {"sno": 2, "model": "Turbo Max", "variant": "Maxx (FB)",
             "chassisNumber": old[1], "invoiceNumber": "OLD-2"},
        ],
    })
    for ch, inv in zip(new, ("NEW-1", "NEW-2")):
        await server.db.oem_sold.insert_one({
            "chassis": ch, "mobile": mobile, "invoiceNumber": inv,
            "customerName": "Hrithik Chopra", "soldDate": "2026-10-05",
            "model": "Turbo Max", "variant": "Maxx (FB)", "coulsonStatus": "SOLD",
        })
    gone = await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert gone["cleared"] >= 1
    assert lid in (gone.get("clearedIds") or [])
    cleared = await server.db.leads.find_one({"leadId": lid})
    assert oem_sync.lead_chassis_list(cleared) == []
    assert cleared["currentStatus"] == "Delivered"
    await server._apply_sold_vehicle_ids()
    live = await server.db.leads.find_one({"leadId": lid})
    held = set(oem_sync.lead_chassis_list(live))
    assert held == set(new)
    assert len(live.get("units") or []) == 2
    assert live["currentStatus"] == "Delivered"
    assert live.get("oemInvoiceMissing") is not True


def test_drop_cancelled_empty_units_shrinks_pack_keeps_never_billed():
    shrunk = oem_sync.drop_cancelled_empty_units({
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "chassisNumber": "", "cancelledInvoiceNumber": "AF-122-I26270204"},
            {"sno": 2, "chassisNumber": "MD9EVDAD26J217577", "invoiceNumber": "AF-122-I26270209"},
        ],
    })
    assert shrunk["vehicleCount"] == 1
    assert shrunk["sameOrderMultiUnit"] is False
    assert len(shrunk["units"]) == 1
    assert shrunk["units"][0]["chassisNumber"] == "MD9EVDAD26J217577"
    assert oem_sync._norm_invoice(shrunk["cancelledInvoiceNumber"]) == "AF-122-I26270204"
    assert any(
        oem_sync._norm_invoice((x or {}).get("invoiceNumber")) == "AF-122-I26270204"
        for x in (shrunk.get("cancelledInvoices") or []) if isinstance(x, dict)
    )
    kept = oem_sync.drop_cancelled_empty_units({
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "chassisNumber": "MD9LIVE01"},
            {"sno": 2, "model": "Turbo Max"},
        ],
    })
    assert kept is None
    both = oem_sync.drop_cancelled_empty_units({
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "chassisNumber": "", "cancelledInvoiceNumber": "OLD-1"},
            {"sno": 2, "chassisNumber": "", "cancelledInvoiceNumber": "OLD-2"},
        ],
    })
    assert both is None


@pytest.mark.asyncio
async def test_invoice_list_cancel_drops_pack_unit_even_if_sold_still_lists_it(client):
    """Hrithik: AF-122-I26270204 CANCELLED, 0209 CREATED — one unit remains."""
    live = "MD9EVDAD26J217577"
    dead = "MD9EVDAD26J217760"
    mobile = "7297021177"
    lid = "LD26000068"
    await server.db.oem_sold.delete_many({
        "$or": [{"chassis": {"$in": [live, dead]}}, {"mobile": mobile}],
    })
    await server.db.oem_cancelled_invoices.delete_many({"chassis": {"$in": [live, dead]}})
    await server.db.leads.delete_many({"$or": [{"leadId": lid}, {"mobile": mobile}]})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Hrithik Chopra", "mobile": mobile,
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-28",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "chassisNumber": dead, "invoiceNumber": "AF-122-I26270204",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Maxx (FB)",
             "chassisNumber": dead, "invoiceNumber": "AF-122-I26270204"},
            {"sno": 2, "model": "Turbo Max", "variant": "Maxx (FB)",
             "chassisNumber": live, "invoiceNumber": "AF-122-I26270209"},
        ],
    })
    for ch, inv in ((dead, "AF-122-I26270204"), (live, "AF-122-I26270209")):
        await server.db.oem_sold.insert_one({
            "chassis": ch, "mobile": mobile, "invoiceNumber": inv,
            "customerName": "Hrithik Chopra", "soldDate": "2026-10-05",
            "model": "Turbo Max", "variant": "Maxx (FB)", "coulsonStatus": "SOLD",
        })
    await server.db.oem_cancelled_invoices.insert_one({
        "chassis": dead, "invoiceNumber": "AF-122-I26270204",
        "invoiceStatus": "CANCELLED", "customerName": "Hrithik Chopra",
    })
    gone = await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert gone["cleared"] >= 1
    assert lid in (gone.get("clearedIds") or [])
    lead = await server.db.leads.find_one({"leadId": lid})
    assert oem_sync.lead_chassis_list(lead) == [live]
    assert len(lead.get("units") or []) == 1
    assert oem_sync._norm_chassis(lead["units"][0].get("chassisNumber")) == live
    assert lead["invoiceNumber"] == "AF-122-I26270209"
    assert lead["currentStatus"] == "Delivered"
    assert lead.get("oemInvoiceMissing") is not True
    assert await server.db.oem_sold.find_one({"chassis": dead}) is None


@pytest.mark.asyncio
async def test_lost_lead_is_revived_when_oem_bills_that_mobile(client):
    chassis = "MD9LOSTREV01"
    mobile = "9812211004"
    await server.db.oem_sold.delete_many({"$or": [{"chassis": chassis}, {"mobile": mobile}]})
    await server.db.leads.delete_many({
        "$or": [{"leadId": "LD-LOST-REV"}, {"mobile": mobile}, {"chassisNumber": chassis}],
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-LOST",
        "customerName": "Was Lost", "soldDate": "2026-09-13", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-LOST-REV", "customerName": "Was Lost", "mobile": mobile,
        "accountStatus": "Cancelled", "currentStatus": "Lost", "dealCancelled": True,
    })
    r = await client.post("/api/oem-billing/sync?month=2026-09")
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": "LD-LOST-REV"})
    assert lead["chassisNumber"] == chassis
    assert lead["accountStatus"] == "Active"
    assert lead.get("dealCancelled") is not True
    assert lead.get("oemInvoiced") is True
    assert lead.get("oemAutoDelivered") is not True
    assert lead["currentStatus"] == "Booked"
    assert server._is_delivered(lead) is False


def test_clear_gone_sold_chassis_only_drops_missing_ids():
    lead = {
        "chassisNumber": "MD9GONE01", "invoiceNumber": "OLD",
        "units": [
            {"chassisNumber": "MD9GONE01", "invoiceNumber": "OLD"},
            {"chassisNumber": "MD9KEEP01", "invoiceNumber": "KEEP"},
        ],
    }
    patch = oem_sync.clear_gone_sold_chassis(lead, {"MD9KEEP01"})
    assert patch["chassisNumber"] == "MD9KEEP01"
    assert patch["invoiceNumber"] == "KEEP"
    assert not oem_sync._norm_chassis(patch["units"][0]["chassisNumber"])


def test_oem_billing_lead_proj_skips_scheme_and_docs():
    proj = oem_sync.OEM_BILLING_LEAD_PROJ
    assert proj["chassisNumber"] == 1
    assert proj["units"] == 1
    assert proj["oemBillingCreated"] == 1
    assert "schemeUse" not in proj
    assert "documents" not in proj
    assert "kycDocs" not in proj


@pytest.mark.asyncio
async def test_oem_billing_get_loads_leads_once_with_projection(client, monkeypatch):
    calls = {"n": 0}
    real = oem_sync.load_oem_billing_leads

    async def wrapped(db):
        calls["n"] += 1
        return await real(db)

    monkeypatch.setattr(oem_sync, "load_oem_billing_leads", wrapped)
    r = await client.get("/api/oem-billing")
    assert r.status_code == 200, r.text
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_oem_billing_get_matches_without_scheme_blob(client):
    chassis = "MD9PROJBLOB01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"leadId": "LD-PROJ-BLOB"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "9812299001", "invoiceNumber": "CINV-PROJ",
        "customerName": "Proj Person", "soldDate": "2026-09-04", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-PROJ-BLOB", "customerName": "Proj Person", "mobile": "9812299001",
        "accountStatus": "Active", "currentStatus": "Booked",
        "chassisNumber": chassis, "invoiceNumber": "CINV-PROJ",
        "schemeUse": {"blob": "x" * 20000, "nested": {"a": list(range(200))}},
        "documents": [{"data": "y" * 8000}],
    })
    r = await client.get("/api/oem-billing", params={"month": "2026-09"})
    assert r.status_code == 200, r.text
    hit = next(row for row in r.json()["rows"] if row["chassis"] == chassis)
    assert hit["leadId"] == "LD-PROJ-BLOB"
    assert hit["bucket"] == "pending_delivery"


@pytest.mark.asyncio
async def test_oem_billing_sync_returns_502_when_coulson_fails(client, monkeypatch):
    async def boom(_db, **_k):
        raise coulson_client.CoulsonError("Coulson unreachable: timed out")

    monkeypatch.setattr(oem_sync, "refresh_sold_inventory", boom)
    r = await client.post("/api/oem-billing/sync")
    assert r.status_code == 502, r.text
    assert "Coulson" in r.json()["detail"]


@pytest.mark.asyncio
async def test_oem_billing_sync_returns_502_when_session_missing(client, monkeypatch):
    async def none(_db, username=None, password=None):
        return "", ""

    monkeypatch.setattr(oem_sync, "_access_token", none)
    r = await client.post("/api/oem-billing/sync")
    assert r.status_code == 502, r.text
    assert "Coulson" in r.json()["detail"]


@pytest.mark.asyncio
async def test_oem_billing_sync_returns_502_on_unexpected_error(client, monkeypatch):
    async def boom(_db, **_k):
        raise RuntimeError("mongo down")

    monkeypatch.setattr(oem_sync, "refresh_sold_inventory", boom)
    r = await client.post("/api/oem-billing/sync")
    assert r.status_code == 502, r.text


@pytest.mark.asyncio
async def test_refresh_sold_raises_without_session(client, monkeypatch):
    async def none(_db, username=None, password=None):
        return "", ""

    monkeypatch.setattr(oem_sync, "_access_token", none)
    with pytest.raises(coulson_client.CoulsonError, match="not configured"):
        await oem_sync.refresh_sold_inventory(server.db)


def test_should_oem_auto_deliver_needs_unique_mobile_not_stub():
    lead = {
        "leadId": "LD-X", "mobile": "9812211999", "currentStatus": "New",
        "accountStatus": "Active", "chassisNumber": "MD9X01", "invoiceNumber": "INV",
    }
    sold_ch = {"MD9X01"}
    sold = [{"chassis": "MD9X01", "mobile": "9812211999", "invoiceNumber": "INV"}]
    assert server._should_oem_auto_deliver(lead, sold_ch, sold) is True
    assert server._should_oem_auto_deliver(lead, sold_ch, [
        {"chassis": "MD9X01", "mobile": "", "invoiceNumber": "INV"},
    ]) is False
    stub = {**lead, "oemBillingCreated": True}
    assert server._should_oem_auto_deliver(stub, sold_ch, sold) is False
    assert server._should_oem_auto_deliver(stub, sold_ch, sold, all_leads=[stub]) is True
    original = {**lead, "leadId": "LD-ORIG", "currentStatus": "Booked",
                "bookingDate": "2026-09-01", "oemBillingCreated": False}
    assert server._should_oem_auto_deliver(
        stub, sold_ch, sold, all_leads=[stub, original]) is False


@pytest.mark.asyncio
async def test_sync_promotes_oem_created_new_file_onto_lead_register(client):
    """Yesterday's Create-from-OEM New enquiry is billed — not a follow-up."""
    chassis = "MD9OEMNEWREG01"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"mobile": "8302479825"})
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": "8302479825", "invoiceNumber": "AF-122-I26278232",
        "customerName": "Rakesh kumar bobasya", "model": "Turbo Max", "variant": "Maxx (PV)",
        "soldDate": "2026-10-16", "coulsonStatus": "SOLD",
    })
    await server.db.leads.insert_one({
        "leadId": "LD26000933", "customerName": "Rakesh kumar bobasya",
        "mobile": "8302479825", "accountStatus": "Active", "currentStatus": "New",
        "oemBillingCreated": True, "leadSource": "OEM Billing",
        "chassisNumber": chassis, "invoiceNumber": "AF-122-I26278232",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "createdDate": "2026-10-16",
    })
    n = await server._auto_deliver_oem_sold_leads()
    assert n >= 1
    live = await server.db.leads.find_one({"leadId": "LD26000933"})
    assert live["currentStatus"] == "Booked"
    assert live.get("oemAutoDelivered") is not True
    assert live.get("oemInvoiced") is True
    assert live.get("bookingDate") == "2026-10-16"
    assert server._is_followup_enquiry(live) is False
    assert server._is_delivered(live) is False
    listed = (await client.get("/api/leads")).json()
    follow = (await client.get("/api/leads", params={"followup": True})).json()
    assert any(row.get("leadId") == "LD26000933" for row in listed)
    assert not any(row.get("leadId") == "LD26000933" for row in follow)


def test_oem_auto_incomplete_needs_reopen():
    locked = {
        "leadId": "LD26000903", "accountStatus": "Active",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "oemAutoDelivered": True, "oemInvoiced": True,
        "chassisNumber": "MD9RADHE01",
    }
    assert server._oem_auto_file_needs_reopen(locked) is True
    desk_done = {**locked, "insuranceStatus": "Yes", "registrationStatus": "Yes"}
    assert server._oem_auto_file_needs_reopen(desk_done) is False
    closed = {**locked, "currentStatus": "Close Won", "accountStatus": "Closed"}
    assert server._oem_auto_file_needs_reopen(closed) is False
    staff = {
        "leadId": "LD-STAFF", "accountStatus": "Active",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
    }
    assert server._oem_auto_file_needs_reopen(staff) is False
    patch = server._reopen_oem_auto_patch(locked)
    assert patch["currentStatus"] == "Booked"
    assert patch["deliveryStatus"] == ""
    assert patch["oemAutoDelivered"] is False
    assert patch["oemInvoiced"] is True


@pytest.mark.asyncio
async def test_reopen_oem_auto_unlocks_showroom_admin_delivery(client):
    lid = "LD26000903"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.deliveries.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Radhe Radhe Plastic", "mobile": "9352347959",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-01",
        "bookingDate": "2026-08-20", "oemAutoDelivered": True, "oemInvoiced": True,
        "chassisNumber": "MD9RADHE01", "invoiceNumber": "CINV-RADHE",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "executive": "Amit",
    })
    await server.db.deliveries.insert_one({
        "leadId": lid, "delivered": "Yes", "deliveryDate": "2026-09-01",
    })
    n = await server._reopen_incomplete_oem_auto_delivered()
    assert n >= 1
    live = await server.db.leads.find_one({"leadId": lid})
    assert live["currentStatus"] == "Booked"
    assert (live.get("deliveryStatus") or "") != "Delivered"
    assert live.get("oemAutoDelivered") is not True
    assert live.get("oemInvoiced") is True
    assert live.get("chassisNumber") == "MD9RADHE01"
    assert server._is_delivered(live) is False
    tl = server.lead_actions(live, {"role": "tl"})
    assert tl["canDeliver"] is True
    assert tl["isLocked"] is False
    assert tl["isDelivered"] is False
    email = "showroom.oem@euler.com"
    await server.db.users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "desk#441", "name": "Showroom Admin", "role": "tl"})
    assert created.status_code == 200, created.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as admin:
        login = await admin.post("/api/auth/login",
                                 json={"email": email, "password": "desk#441"})
        assert login.status_code == 200, login.text
        admin.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        saved = await admin.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "",
            "insurerName": "UIIC", "delivered": "",
        })
        assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert (after.get("insuranceStatus") or "").lower() in ("yes", "done")
    assert server._is_delivered(after) is False


@pytest.mark.asyncio
async def test_360_reopens_oem_auto_file_on_open(client):
    lid = "LD-RADHE-360"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Radhe 360", "mobile": "9352347960",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "oemAutoDelivered": True,
        "oemBillingCreated": True, "bookingDate": "2026-09-01",
        "chassisNumber": "MD9RADHE360", "executive": "Amit",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
    })
    body = (await client.get(f"/api/leads/{lid}/360")).json()
    lead = body["lead"]
    assert lead["currentStatus"] == "Booked"
    assert body["actions"]["isDelivered"] is False
    assert body["actions"]["canDeliver"] is True
    assert body["actions"]["isLocked"] is False


@pytest.mark.asyncio
async def test_reopen_leaves_desk_complete_delivered(client):
    lid = "LD-DESK-DONE"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Desk Done", "mobile": "9352347961",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "oemAutoDelivered": True,
        "insuranceStatus": "Yes", "registrationStatus": "Yes",
        "chassisNumber": "MD9DESKDONE",
    })
    n = await server._reopen_incomplete_oem_auto_delivered()
    live = await server.db.leads.find_one({"leadId": lid})
    assert live["currentStatus"] == "Delivered"
    assert live.get("oemAutoDelivered") is True
    assert n == 0 or live["currentStatus"] == "Delivered"
