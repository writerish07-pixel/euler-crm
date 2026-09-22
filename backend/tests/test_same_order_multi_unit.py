"""Same-order fleet: one lead id, many units, one payment, OEM S.No. fill."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "same_order_multi_unit_test")
os.environ.setdefault("JWT_SECRET", "same-order-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import oem_sync  # noqa: E402
import period as periodmod  # noqa: E402
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


def test_vehicle_count_reads_units():
    assert oem_sync.vehicle_count({"interestedModel": "Turbo Max"}) == 1
    assert oem_sync.vehicle_count({
        "sameOrderMultiUnit": True,
        "units": [{"model": "Turbo Max"}, {"model": "Storm"}, {"model": "Hi-Load"}],
    }) == 3


def test_volume_slice_counts_vehicles_not_just_leads():
    p = periodmod.parse_period(month="2026-09")
    pack = {
        "createdDate": "2026-09-02", "bookingDate": "2026-09-03",
        "deliveryDate": "2026-09-04", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "accountStatus": "Active",
        "sameOrderMultiUnit": True,
        "units": [{"model": "Turbo Max"} for _ in range(5)],
    }
    out = server._volume_slice([pack], [], p, [])
    assert out["leads"] == 5
    assert out["bookings"] == 5
    assert out["deliveries"] == 5


@pytest.mark.asyncio
async def test_same_order_create_one_lead_many_units(client):
    mobile = "9813300111"
    await server.db.leads.delete_many({"mobile": mobile})
    r = await client.post("/api/leads", json={
        "customerName": "Fleet Pack",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "sameOrderMultiUnit": True,
        "units": [
            {"model": "Turbo Max", "variant": "Maxx (PV)"},
            {"model": "Storm", "variant": "Storm LR (PV)"},
            {"model": "Hi-Load", "variant": "XR"},
        ],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["leadId"]
    assert body.get("sameOrderMultiUnit") is True
    assert body.get("vehicleCount") == 3
    units = body.get("units") or []
    assert len(units) == 3
    assert units[0]["model"] == "Turbo Max"
    assert units[1]["model"] == "Storm"
    assert units[2]["model"] == "Hi-Load"
    listed = await client.get("/api/leads", params={"q": "Fleet Pack"})
    assert listed.status_code == 200
    hit = next(l for l in listed.json() if l["leadId"] == body["leadId"])
    assert hit["vehicleCount"] == 3
    n = await server.db.leads.count_documents({"mobile": mobile})
    assert n == 1


@pytest.mark.asyncio
async def test_same_order_create_autofills_pack_cx_demand(client):
    mobile = "9813300666"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-PACK-A", "PM-PACK-B"]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-PACK-A", "model": "Turbo Max", "variant": "Pack A",
        "exShowroom": 600000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.price_master.insert_one({
        "priceId": "PM-PACK-B", "model": "Storm", "variant": "Pack B",
        "exShowroom": 1200000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    r = await client.post("/api/leads", json={
        "customerName": "Pack Calc",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Pack A",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "sameOrderMultiUnit": True,
        "units": [
            {"model": "Turbo Max", "variant": "Pack A"},
            {"model": "Storm", "variant": "Pack B"},
        ],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("sameOrderMultiUnit") is True
    assert body.get("vehicleCount") == 2
    deal = body.get("dealFormat") or {}
    assert deal.get("pack") is True
    assert len(deal.get("units") or []) == 2
    assert ce.num(body.get("cxDemand")) == ce.num(deal.get("suggestedCxDemand") or deal.get("netToCx"))
    assert ce.num(body.get("customerPayable")) == ce.num(body.get("cxDemand"))
    assert ce.num(body.get("cxDemand")) > 1200000
    unit_tcs = sum(ce.num(u.get("tcs")) for u in (deal.get("units") or []))
    assert ce.num(deal.get("tcs")) == unit_tcs
    assert unit_tcs >= 12000


@pytest.mark.asyncio
async def test_add_unit_to_existing_lead_recalculates_pack(client):
    mobile = "9813300777"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-ADD-A", "PM-ADD-B"]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-ADD-A", "model": "Turbo Max", "variant": "Add A",
        "exShowroom": 600000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.price_master.insert_one({
        "priceId": "PM-ADD-B", "model": "Storm", "variant": "Add B",
        "exShowroom": 600000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    first = await client.post("/api/leads", json={
        "customerName": "Add Unit",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Add A",
        "executive": "Amit",
        "budget": 600000,
        "leadSource": "Walk-in",
    })
    assert first.status_code == 200, first.text
    lid = first.json()["leadId"]
    add = await client.post(f"/api/leads/{lid}/units", json={
        "model": "Storm", "variant": "Add B",
    })
    assert add.status_code == 200, add.text
    body = add.json()
    assert body.get("vehicleCount") == 2
    assert body.get("sameOrderMultiUnit") is True
    deal = body.get("dealFormat") or {}
    assert deal.get("pack") is True
    assert ce.num(body.get("cxDemand")) == ce.num(deal.get("suggestedCxDemand") or deal.get("netToCx"))
    assert ce.num(body.get("cxDemand")) > 600000
    assert await server.db.leads.count_documents({"mobile": mobile}) == 1


@pytest.mark.asyncio
async def test_repair_deletes_same_sku_retry_triples(client):
    mobile = "9813300888"
    await server.db.leads.delete_many({"mobile": mobile})
    for i, lid in enumerate(("LD26RPAIR01", "LD26RPAIR02", "LD26RPAIR03")):
        await server.db.leads.insert_one({
            "leadId": lid, "customerName": "Retry Triple", "mobile": mobile,
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "accountStatus": "Active", "currentStatus": "New",
            "createdDate": "2026-09-22", "lastUpdated": "2026-09-22T08:00:00+00:00",
            "executive": "Amit",
        })
    repaired = await server._repair_retry_duplicate_leads()
    assert len(repaired) == 1
    left = [l async for l in server.db.leads.find({"mobile": mobile})]
    assert len(left) == 1
    assert left[0]["leadId"] == "LD26RPAIR01"


@pytest.mark.asyncio
async def test_repair_same_mobile_without_created_date(client):
    mobile = "9813301010"
    await server.db.leads.delete_many({"mobile": mobile})
    for lid in ("LD26NODATE1", "LD26NODATE2", "LD26NODATE3"):
        await server.db.leads.insert_one({
            "leadId": lid, "customerName": "No Date Triple", "mobile": mobile,
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "accountStatus": "Active", "currentStatus": "New",
        })
    server._retry_dup_repair_done = True
    server._retry_dup_last_clean_at = 0.0
    listed = await client.get("/api/leads", params={"q": "No Date Triple"})
    assert listed.status_code == 200, listed.text
    left = [l async for l in server.db.leads.find({"mobile": mobile})]
    assert len(left) == 1
    assert left[0]["leadId"] == "LD26NODATE1"


@pytest.mark.asyncio
async def test_repair_merges_same_day_different_skus(client):
    mobile = "9813300999"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-MRG-A", "PM-MRG-B"]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-MRG-A", "model": "Turbo Max", "variant": "Mrg A",
        "exShowroom": 500000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.price_master.insert_one({
        "priceId": "PM-MRG-B", "model": "Storm", "variant": "Mrg B",
        "exShowroom": 500000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.leads.insert_one({
        "leadId": "LD26MERGE01", "customerName": "Merge Pack", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Mrg A",
        "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-09-22", "lastUpdated": "2026-09-22T08:00:00+00:00",
        "exShowroom": 500000,
    })
    await server.db.leads.insert_one({
        "leadId": "LD26MERGE02", "customerName": "Merge Pack", "mobile": mobile,
        "interestedModel": "Storm", "variant": "Mrg B",
        "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-09-22", "lastUpdated": "2026-09-22T08:01:00+00:00",
        "exShowroom": 500000,
    })
    repaired = await server._repair_retry_duplicate_leads()
    assert len(repaired) == 1
    left = [l async for l in server.db.leads.find({"mobile": mobile})]
    assert len(left) == 1
    assert left[0]["leadId"] == "LD26MERGE01"
    assert left[0].get("sameOrderMultiUnit") is True
    assert left[0].get("vehicleCount") == 2


@pytest.mark.asyncio
async def test_create_lead_retry_returns_same_id(client):
    mobile = "9813300444"
    await server.db.leads.delete_many({"mobile": mobile})
    payload = {
        "customerName": "Retry One Tap",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
    }
    first = await client.post("/api/leads", json=payload)
    assert first.status_code == 200, first.text
    second = await client.post("/api/leads", json=payload)
    assert second.status_code == 200, second.text
    assert second.json()["leadId"] == first.json()["leadId"]
    assert await server.db.leads.count_documents({"mobile": mobile}) == 1


@pytest.mark.asyncio
async def test_another_vehicle_still_mints_a_new_id(client):
    mobile = "9813300555"
    await server.db.leads.delete_many({"mobile": mobile})
    first = await client.post("/api/leads", json={
        "customerName": "Repeat Buyer",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert first.status_code == 200, first.text
    second = await client.post("/api/leads", json={
        "customerName": "Repeat Buyer",
        "mobile": mobile,
        "interestedModel": "Storm",
        "variant": "Storm LR (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "anotherVehicle": True,
    })
    assert second.status_code == 200, second.text
    assert second.json()["leadId"] != first.json()["leadId"]
    assert await server.db.leads.count_documents({"mobile": mobile}) == 2


@pytest.mark.asyncio
async def test_delivery_fills_pack_serial_rows(client):
    lid = "LD-PACK-DEL"
    mobile = "9813300222"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.oem_sold.delete_many({"mobile": mobile})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Pack Delivery", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-01", "customerOutstanding": 0,
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Maxx (PV)"},
            {"sno": 2, "model": "Turbo Max", "variant": "Maxx (PV)"},
            {"sno": 3, "model": "Storm", "variant": "Storm LR (PV)"},
        ],
    })
    for i, (ch, inv, model, variant) in enumerate((
        ("MD9PACKDEL01", "CINV-P1", "Turbo Max", "Maxx (PV)"),
        ("MD9PACKDEL02", "CINV-P2", "Turbo Max", "Maxx (PV)"),
        ("MD9PACKDEL03", "CINV-P3", "Storm", "Storm LR (PV)"),
    ), start=1):
        await server.db.oem_sold.insert_one({
            "chassis": ch, "mobile": mobile, "invoiceNumber": inv,
            "customerName": "Pack Delivery", "model": model, "variant": variant,
            "soldDate": "2026-09-08", "coulsonStatus": "SOLD",
        })
    sold = await client.get(f"/api/leads/{lid}/oem-sold")
    assert sold.status_code == 200, sold.text
    family = sold.json()
    assert family["matched"] is True
    assert len(family.get("units") or []) == 3
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Done", "registration": "Done", "invoice": "Done",
        "pdi": "Done", "insurerName": "TestIns",
        "delivered": "", "invoiceNumber": "", "chassisNumber": "",
    })
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    chassis = set(oem_sync.lead_chassis_list(lead))
    assert chassis == {"MD9PACKDEL01", "MD9PACKDEL02", "MD9PACKDEL03"}
    units = lead.get("units") or []
    assert len(units) == 3
    assert all(u.get("chassisNumber") for u in units)
    assert all(u.get("invoiceNumber") for u in units)


@pytest.mark.asyncio
async def test_repair_same_model_ignores_variant_split(client):
    mobile = "9813301111"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.leads.insert_one({
        "leadId": "LD26VAR001", "customerName": "Guman Kanwar", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "City (F)",
        "accountStatus": "Active", "currentStatus": "New",
    })
    await server.db.leads.insert_one({
        "leadId": "LD26VAR002", "customerName": "Guman Kanwar", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "",
        "accountStatus": "Active", "currentStatus": "New",
    })
    await server.db.leads.insert_one({
        "leadId": "LD26VAR003", "customerName": "Guman Kanwar", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "New",
    })
    repaired = await server._repair_retry_duplicate_leads()
    assert repaired
    left = [l async for l in server.db.leads.find({"mobile": mobile})]
    assert len(left) == 1
    assert left[0]["leadId"] == "LD26VAR001"


@pytest.mark.asyncio
async def test_another_vehicle_is_not_purged_as_retry(client):
    mobile = "9813301222"
    await server.db.leads.delete_many({"mobile": mobile})
    first = await client.post("/api/leads", json={
        "customerName": "Keep Sibling",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert first.status_code == 200, first.text
    second = await client.post("/api/leads", json={
        "customerName": "Keep Sibling",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "anotherVehicle": True,
    })
    assert second.status_code == 200, second.text
    assert second.json()["leadId"] != first.json()["leadId"]
    assert second.json().get("anotherVehicle") is True
    repaired = await server._repair_retry_duplicate_leads()
    assert not any(
        first.json()["leadId"] in (r.get("removed") or [])
        or second.json()["leadId"] in (r.get("removed") or [])
        for r in repaired
    )
    assert await server.db.leads.count_documents({"mobile": mobile}) == 2


@pytest.mark.asyncio
async def test_pack_units_own_price_and_scheme(client):
    mobile = "9813301333"
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-U1", "PM-U2"]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-U1", "model": "Turbo Max", "variant": "Unit A",
        "exShowroom": 500000, "rto": 10000, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.price_master.insert_one({
        "priceId": "PM-U2", "model": "Storm", "variant": "Unit B",
        "exShowroom": 700000, "rto": 20000, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    created = await client.post("/api/leads", json={
        "customerName": "Per Unit Deal",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Unit A",
        "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    added = await client.post(f"/api/leads/{lid}/units", json={
        "model": "Storm", "variant": "Unit B",
    })
    assert added.status_code == 200, added.text
    p1 = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 500000, "rto": 10000, "unitSno": 1,
    })
    assert p1.status_code == 200, p1.text
    s1 = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "additionalDiscount": 5000,
        "benefitPassedBreakup": "{}",
        "schemeComponentsUsed": "{}",
        "unitSno": 1,
    })
    assert s1.status_code == 200, s1.text
    mid = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(mid.get("packUnitsPending")) >= 1
    units_mid = mid.get("units") or []
    unit1_pay = ce.num(units_mid[0].get("customerPayable"))
    unit2_pay = ce.num(units_mid[1].get("customerPayable"))
    assert unit1_pay > 0
    assert unit2_pay > 0
    assert ce.num(mid.get("customerPayable")) == ce.round2(unit1_pay + unit2_pay)

    p2 = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 700000, "rto": 20000, "unitSno": 2,
    })
    assert p2.status_code == 200, p2.text
    s2 = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "Partial Benefit",
        "additionalDiscount": 25000,
        "benefitPassedBreakup": "{}",
        "schemeComponentsUsed": "{}",
        "unitSno": 2,
    })
    assert s2.status_code == 200, s2.text
    done = await server.db.leads.find_one({"leadId": lid})
    units = done.get("units") or []
    assert len(units) == 2
    assert units[0].get("priceStructureSaved") is True
    assert units[1].get("priceStructureSaved") is True
    assert ce.num(units[0].get("additionalDiscount")) == 5000
    assert ce.num(units[1].get("additionalDiscount")) == 25000
    assert ce.num(units[0].get("customerPayable")) != ce.num(units[1].get("customerPayable"))
    assert ce.num(done.get("packUnitsPending")) == 0
    assert ce.num(done.get("customerPayable")) == ce.round2(
        ce.num(units[0].get("customerPayable")) + ce.num(units[1].get("customerPayable")))
    assert ce.num(done.get("customerOutstanding")) == ce.num(done.get("customerPayable"))


@pytest.mark.asyncio
async def test_pack_360_hydrates_unit_amounts_and_sums_payable(client):
    lid = "LD-PACK-ZERO"
    mobile = "9813301444"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.price_master.delete_many({"priceId": "PM-ZERO-A"})
    await server.db.price_master.insert_one({
        "priceId": "PM-ZERO-A", "model": "Turbo Max", "variant": "Zero A",
        "exShowroom": 600000, "rto": 10000, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Zero Units", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Zero A",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-01",
        "exShowroom": 600000, "rto": 10000,
        "priceStructureSaved": True,
        "additionalDiscount": 5000000,
        "schemeAllocationExplicit": True,
        "benefitPassedBreakup": "{}",
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Zero A",
             "exShowroom": 600000, "rto": 10000, "priceStructureSaved": True},
            {"sno": 2, "model": "Turbo Max", "variant": "Zero A"},
            {"sno": 3, "model": "Turbo Max", "variant": "Zero A"},
        ],
    })
    r = await client.get(f"/api/leads/{lid}/360")
    assert r.status_code == 200, r.text
    body = r.json()
    lead = body["lead"]
    c = body["commercials"]
    units = lead.get("units") or []
    assert len(units) == 3
    assert all(ce.num(u.get("exShowroom")) > 0 for u in units)
    assert all(ce.num(u.get("customerPayable")) > 0 for u in units)
    assert ce.num(c.get("customerPayable")) > 0
    assert ce.num(c.get("customerPayable")) == ce.num(lead.get("customerPayable"))
    assert ce.num(c.get("grossVehicleCost")) >= 1800000
    # Lead-level additionalDiscount must not turn pack payable negative.
    assert ce.num(c.get("customerPayable")) > 0
