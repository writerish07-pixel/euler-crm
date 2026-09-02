"""TCS 1% above ₹10L after discount, and Coulson Sold-tab chassis by mobile."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "tcs_sold_chassis_test")
os.environ.setdefault("JWT_SECRET", "tcs-sold-secret")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import oem_sync  # noqa: E402
import coulson as coulson_client  # noqa: E402
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


def test_tcs_not_charged_at_exactly_10_lakh():
    assert ce.calculate_tcs(1_000_000) == 0
    assert ce.calculate_tcs(1_000_000.01) == ce.round2(1_000_000.01 * 0.01)


def test_tcs_is_1_percent_of_full_consideration():
    assert ce.calculate_tcs(1_200_000) == 12_000
    assert ce.calculate_tcs(950_000) == 0


def test_tcs_mandatory_even_when_flag_is_no():
    totals = ce.compute_commercial_totals({
        "exShowroom": 1_200_000, "insurance": 0, "tcsApplicable": "No",
    })
    assert totals["tcs"] == 12_000
    assert totals["tcsApplicable"] == "Yes"
    assert totals["tcsBase"] == 1_200_000


def test_tcs_uses_after_discount_price():
    """Discount on the invoice can bring a 12L vehicle under the threshold."""
    over = ce.compute_commercial_totals({
        "exShowroom": 1_200_000, "additionalDiscount": 100_000, "tcsApplicable": "No",
    })
    assert over["tcsBase"] == 1_100_000
    assert over["tcs"] == 11_000

    under = ce.compute_commercial_totals({
        "exShowroom": 1_200_000, "additionalDiscount": 250_000, "tcsApplicable": "Yes",
    })
    assert under["tcsBase"] == 950_000
    assert under["tcs"] == 0
    assert under["tcsApplicable"] == "No"


def test_vehicle_mobile_reads_nested_customer():
    assert oem_sync.vehicle_mobile({"customer_mobile": "919876543210"}) == "9876543210"
    assert oem_sync.vehicle_mobile({"customer_phone": "+91 98765-43210"}) == "9876543210"
    assert oem_sync.vehicle_mobile({"billed_customer_phone": "9876543210"}) == "9876543210"
    assert oem_sync.vehicle_mobile({"customer": {"phone": "+91 98765-43210"}}) == "9876543210"
    assert oem_sync.vehicle_mobile({"chassis": "X"}) == ""


def test_sold_match_score_requires_mobile():
    lead = {"mobile": "9876543210", "interestedModel": "Turbo Max", "variant": "Maxx (PV)"}
    row = {"mobile": "9876543210", "model": "Turbo Max", "variant": "Maxx (PV)"}
    assert oem_sync.sold_match_score(row, lead) >= 1
    assert oem_sync.sold_match_score({"mobile": "1111111111"}, lead) == 0


@pytest.mark.asyncio
async def test_price_list_charges_tcs_over_threshold_without_flag(client):
    await server.db.price_master.update_one(
        {"model": "Storm", "variant": {"$regex": "DV260"}},
        {"$set": {"tcsApplicable": "No", "exShowroom": 1_100_000, "rto": 0, "insurance": 0,
                  "accessories": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
                  "extendedWarranty": 0, "otherCharges": 0, "status": "active"}},
    )
    body = (await client.get("/api/price-list", params={"q": "DV260"})).json()
    rows = [r for g in body["models"] for r in g["rows"]]
    assert rows
    hit = next(r for r in rows if r["exShowroom"] >= 1_100_000)
    assert hit["tcsApplies"] is True
    assert hit["tcs"] == ce.round2(hit["exShowroom"] * 0.01)
    assert "tcsReview" not in body


@pytest.mark.asyncio
async def test_sold_chassis_autofills_when_outstanding_is_cleared(client):
    mobile = "9811100999"
    chassis = "MD9SOLDAUTO0001"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.insurance_agents.update_one(
        {"agentId": "IA-SOLD-1"},
        {"$set": {"agentId": "IA-SOLD-1", "agentName": "Sold Test Agent", "status": "Active"}},
        upsert=True,
    )
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-AUTO", "customerName": "Sold Match", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-02",
        "deliveryStatus": "Pending", "customerOutstanding": 0, "customerPayable": 785000,
        "totalReceived": 785000, "exShowroom": 785000, "insuranceArrangedBy": "dealer",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-9001",
        "numberPlate": "RJ14AB9001", "model": "Turbo Max", "variant": "Maxx (PV)",
        "coulsonStatus": "SOLD",
    })

    match = (await client.get("/api/leads/LD-SOLD-AUTO/oem-sold")).json()
    assert match["matched"] is True
    assert match["chassis"] == chassis
    assert match["outstandingCleared"] is True

    r = await client.put("/api/leads/LD-SOLD-AUTO/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "rc": "Yes", "insurerName": "ICICI", "insuranceAgentId": "IA-SOLD-1",
        "invoiceNumber": "", "chassisNumber": "", "numberPlate": "",
        "delivered": "Yes", "deliveryDate": "2026-09-02",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": "LD-SOLD-AUTO"})
    assert lead["chassisNumber"] == chassis
    assert lead["invoiceNumber"] == "CINV-9001"
    assert server._is_delivered(lead) is True


@pytest.mark.asyncio
async def test_sold_chassis_not_applied_while_outstanding_remains(client):
    mobile = "9811100888"
    chassis = "MD9SOLDWAIT0002"
    await server.db.leads.delete_many({"leadId": "LD-SOLD-WAIT"})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.insurance_agents.update_one(
        {"agentId": "IA-SOLD-1"},
        {"$set": {"agentId": "IA-SOLD-1", "agentName": "Sold Test Agent", "status": "Active"}},
        upsert=True,
    )
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-WAIT", "customerName": "Still Owing", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-02",
        "deliveryStatus": "Pending", "customerOutstanding": 50000, "customerPayable": 785000,
        "totalReceived": 735000,
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-9002",
        "model": "Turbo Max", "variant": "Maxx (PV)", "coulsonStatus": "SOLD",
    })
    match = (await client.get("/api/leads/LD-SOLD-WAIT/oem-sold")).json()
    assert match["matched"] is True
    assert match["outstandingCleared"] is False

    r = await client.put("/api/leads/LD-SOLD-WAIT/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "rc": "Yes", "insurerName": "ICICI", "insuranceAgentId": "IA-SOLD-1",
        "invoiceNumber": "", "chassisNumber": "", "delivered": "Yes",
        "deliveryDate": "2026-09-02",
    })
    assert r.status_code == 422
    lead = await server.db.leads.find_one({"leadId": "LD-SOLD-WAIT"})
    assert not lead.get("chassisNumber")


@pytest.mark.asyncio
async def test_coulson_sync_stores_sold_by_mobile(client, monkeypatch):
    oem_models = [{
        "id": "oem-maxx-pv", "model": "Turbo", "variant": "Range Maxx", "load_body": "PV",
        "sap_product_id": "CD00001500", "sap_product_name": "TURBO RANGEMAXX PV",
        "showroom_price_non_delhi": 770000, "showroom_price_delhi": 770000,
    }]
    present = []
    sold = [{
        "chassis": "MD9SOLDSYNC0003", "model": "Turbo", "variant": "Range Maxx",
        "updated_load_body": "PV", "sap_vehicle_model_id": "oem-maxx-pv",
        "customer_mobile": "919812309876", "invoice_number": "CINV-SYNC",
        "_coulsonStatus": "SOLD",
    }]
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: oem_models)
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200: present)
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200: sold)
    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    assert r.json()["soldCount"] == 1
    row = await server.db.oem_sold.find_one({"chassis": "MD9SOLDSYNC0003"})
    assert row["mobile"] == "9812309876"
    assert row["invoiceNumber"] == "CINV-SYNC"
    assert row["model"] == "Turbo Max"
    assert r.json()["leadsVehicleIds"]["updated"] == 0


@pytest.mark.asyncio
async def test_coulson_sync_writes_sold_ids_onto_matching_leads(client, monkeypatch):
    mobile = "9812301111"
    chassis = "MD9SOLDBACKFILL01"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-BF-1", "customerName": "Backfill One", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-02",
        "invoiceNumber": "WRONG-INV", "chassisNumber": "WRONG-CH",
    })
    await server.db.deliveries.insert_one({
        "leadId": "LD-SOLD-BF-1", "invoiceNumber": "WRONG-INV", "chassisNumber": "WRONG-CH",
    })
    oem_models = [{
        "id": "oem-maxx-pv", "model": "Turbo", "variant": "Range Maxx", "load_body": "PV",
        "sap_product_id": "CD00001500", "sap_product_name": "TURBO RANGEMAXX PV",
        "showroom_price_non_delhi": 770000, "showroom_price_delhi": 770000,
    }]
    sold = [{
        "chassis": chassis, "model": "Turbo", "variant": "Range Maxx",
        "updated_load_body": "PV", "sap_vehicle_model_id": "oem-maxx-pv",
        "customer_mobile": "91" + mobile, "invoice_number": "CINV-BF-1",
        "registration_number": "RJ14BF0001",
        "_coulsonStatus": "SOLD",
    }]
    monkeypatch.setattr(coulson_client, "login", lambda u, p: "fake-token")
    monkeypatch.setattr(coulson_client, "fetch_sap_models", lambda token: oem_models)
    monkeypatch.setattr(coulson_client, "fetch_present_inventory", lambda token, limit=200: [])
    monkeypatch.setattr(coulson_client, "fetch_sold_inventory", lambda token, limit=200: sold)
    await server.oem_sync.save_credentials(server.db, "dealer.user", "secret")
    r = await client.post("/api/integrations/coulson/sync")
    assert r.status_code == 200, r.text
    assert r.json()["leadsVehicleIds"]["updated"] >= 1
    lead = await server.db.leads.find_one({"leadId": "LD-SOLD-BF-1"})
    assert lead["chassisNumber"] == chassis
    assert lead["invoiceNumber"] == "CINV-BF-1"
    assert lead["numberPlate"] == "RJ14BF0001"
    delivery = await server.db.deliveries.find_one({"leadId": "LD-SOLD-BF-1"})
    assert delivery["chassisNumber"] == chassis
    assert delivery["invoiceNumber"] == "CINV-BF-1"


@pytest.mark.asyncio
async def test_sold_id_backfill_skips_ambiguous_same_mobile(client):
    mobile = "9812302222"
    chassis = "MD9SOLDAMBIG0001"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-A", "customerName": "Twin A", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-B", "customerName": "Twin B", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-AMB",
        "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    assert stats["updated"] == 0
    assert stats["skippedAmbiguous"] >= 2
    a = await server.db.leads.find_one({"leadId": "LD-SOLD-A"})
    b = await server.db.leads.find_one({"leadId": "LD-SOLD-B"})
    assert not a.get("chassisNumber")
    assert not b.get("chassisNumber")


@pytest.mark.asyncio
async def test_sold_id_backfill_prefers_delivered_when_mobile_is_shared(client):
    mobile = "9812303333"
    chassis = "MD9SOLDPREF0001"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-NEW", "customerName": "Open Twin", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "New",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-DEL", "customerName": "Delivered Twin", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-02",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-PREF",
        "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    assert stats["updated"] == 1
    del_lead = await server.db.leads.find_one({"leadId": "LD-SOLD-DEL"})
    new_lead = await server.db.leads.find_one({"leadId": "LD-SOLD-NEW"})
    assert del_lead["chassisNumber"] == chassis
    assert del_lead["invoiceNumber"] == "CINV-PREF"
    assert not new_lead.get("chassisNumber")


@pytest.mark.asyncio
async def test_sold_id_backfill_does_not_steal_live_chassis(client):
    mobile = "9812304444"
    chassis = "MD9SOLDTAKEN0001"
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-SOLD-WANT", "LD-SOLD-HAS"]}})
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-WANT", "customerName": "Wants Chassis", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
    })
    await server.db.leads.insert_one({
        "leadId": "LD-SOLD-HAS", "customerName": "Already Has", "mobile": "9812305555",
        "interestedModel": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "deliveryDate": "2026-09-02",
        "chassisNumber": chassis, "invoiceNumber": "CINV-HAS-KEEP",
    })
    await server.db.oem_sold.insert_one({
        "chassis": chassis, "mobile": mobile, "invoiceNumber": "CINV-TAKE",
        "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    assert stats["updated"] == 0
    assert stats["skippedConflict"] >= 1
    want = await server.db.leads.find_one({"leadId": "LD-SOLD-WANT"})
    assert not want.get("chassisNumber")
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-SOLD-WANT", "LD-SOLD-HAS"]}})


def test_name_match_needs_two_words():
    assert oem_sync._name_key_usable("sakil ali")
    assert oem_sync._name_key_usable("prakash chand ranwa")
    assert not oem_sync._name_key_usable("ali")
    assert not oem_sync._name_key_usable("")
    assert oem_sync._norm_person_name("Prakash  chand Ranwa") == "prakash chand ranwa"


def test_vehicle_customer_name_reads_nested():
    assert oem_sync.vehicle_customer_name({"customer_name": "Roshan Sharma"}) == "Roshan Sharma"
    assert oem_sync.vehicle_customer_name({"customer": {"name": "Sakil Ali"}}) == "Sakil Ali"
    assert oem_sync.vehicle_customer_name({"chassis": "X"}) == ""


@pytest.mark.asyncio
async def test_blank_or_wrong_mobile_fills_from_unique_sold_name(client):
    """The four sheet names: unique OEM name → copy mobile then chassis/invoice."""
    rows = [
        ("LD-NM-1", "Roshan Sharma", "", "9777099101", "MD9NMROSHAN0001", "INV-NM-1"),
        ("LD-NM-2", "Prakash chand Ranwa", "9000000002", "9777099102", "MD9NMPRAKASH01", "INV-NM-2"),
        ("LD-NM-3", "Vivan point", "", "9777099103", "MD9NMVIVAN00001", "INV-NM-3"),
        ("LD-NM-4", "Sakil Ali", "NA", "9777099104", "MD9NMSAKIL00001", "INV-NM-4"),
    ]
    await server.db.leads.delete_many({"leadId": {"$in": [r[0] for r in rows]}})
    await server.db.oem_sold.delete_many({"chassis": {"$in": [r[4] for r in rows]}})
    keys = {oem_sync._norm_person_name(r[1]) for r in rows}
    async for existing in server.db.leads.find({}):
        if oem_sync._norm_person_name(existing.get("customerName")) in keys:
            await server.db.leads.delete_one({"leadId": existing["leadId"]})
    for lid, name, crm_mobile, oem_mobile, chassis, invoice in rows:
        await server.db.leads.insert_one({
            "leadId": lid, "customerName": name, "mobile": crm_mobile,
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "accountStatus": "Active", "currentStatus": "Booked",
        })
        await server.db.oem_sold.insert_one({
            "chassis": chassis, "mobile": oem_mobile, "invoiceNumber": invoice,
            "customerName": name, "model": "Turbo Max", "variant": "Maxx (PV)",
        })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    assert stats["updated"] == 4
    assert stats["mobilesUpdated"] == 4
    for lid, name, crm_mobile, oem_mobile, chassis, invoice in rows:
        lead = await server.db.leads.find_one({"leadId": lid})
        assert lead["mobile"] == oem_mobile, lid
        assert lead["chassisNumber"] == chassis
        assert lead["invoiceNumber"] == invoice
        if crm_mobile == "9000000002":
            assert lead.get("altMobile") == "9000000002"
    await server.db.leads.delete_many({"leadId": {"$in": [r[0] for r in rows]}})


@pytest.mark.asyncio
async def test_duplicate_sold_name_does_not_copy_mobile(client):
    await server.db.leads.delete_many({"leadId": "LD-NM-DUP"})
    await server.db.oem_sold.delete_many({"customerName": "Roshan Sharma"})
    await server.db.leads.insert_one({
        "leadId": "LD-NM-DUP", "customerName": "Roshan Sharma", "mobile": "",
        "accountStatus": "Active", "currentStatus": "Booked",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NMDUPA", "mobile": "9811110091", "invoiceNumber": "A",
        "customerName": "Roshan Sharma",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NMDUPB", "mobile": "9811110092", "invoiceNumber": "B",
        "customerName": "Roshan Sharma",
    })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    lead = await server.db.leads.find_one({"leadId": "LD-NM-DUP"})
    assert not lead.get("chassisNumber")
    assert not lead.get("mobile")
    assert stats["updated"] == 0
    await server.db.leads.delete_many({"leadId": "LD-NM-DUP"})


@pytest.mark.asyncio
async def test_unique_mobile_still_wins_over_name(client):
    await server.db.leads.delete_many({"leadId": "LD-NM-MOB"})
    await server.db.oem_sold.delete_many({"chassis": {"$in": ["MD9NMMOB1", "MD9NMMOB2"]}})
    await server.db.leads.insert_one({
        "leadId": "LD-NM-MOB", "customerName": "Roshan Sharma", "mobile": "9811110088",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NMMOB1", "mobile": "9811110088", "invoiceNumber": "MOB-WIN",
        "customerName": "Someone Else", "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NMMOB2", "mobile": "9811110077", "invoiceNumber": "NAME-ROW",
        "customerName": "Roshan Sharma", "model": "Turbo Max", "variant": "Maxx (PV)",
    })
    stats = await oem_sync.apply_sold_vehicle_ids_to_leads(server.db)
    lead = await server.db.leads.find_one({"leadId": "LD-NM-MOB"})
    assert lead["chassisNumber"] == "MD9NMMOB1"
    assert lead["invoiceNumber"] == "MOB-WIN"
    assert lead["mobile"] == "9811110088"
    assert stats["mobilesUpdated"] == 0
    await server.db.leads.delete_many({"leadId": "LD-NM-MOB"})
