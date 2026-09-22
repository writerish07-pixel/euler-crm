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
