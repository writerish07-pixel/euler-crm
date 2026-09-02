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
