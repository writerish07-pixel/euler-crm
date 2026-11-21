"""Each vehicle on a multi-unit file has its own model and variant.

Unit 1 used to be the only vehicle the edit form could change. Unit 2 and
later stayed on the model they were added with.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pack_unit_vehicle_test")
os.environ.setdefault("JWT_SECRET", "pack-unit-vehicle-secret")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
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


async def _login(role, email):
    await server.db.users.update_one(
        {"email": email},
        {"$set": {
            "email": email, "name": role, "role": role, "userId": f"uid-{role}-puv",
            "passwordHash": server.authmod.hash_password("unit-pass-1"),
        }},
        upsert=True)
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": "unit-pass-1"})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


async def _pack(client, mobile="9813307101"):
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-PUV-A", "PM-PUV-B", "PM-PUV-C"]}})
    await server.db.price_master.insert_many([
        {"priceId": "PM-PUV-A", "model": "Turbo Max", "variant": "Unit Edit A",
         "exShowroom": 500000, "rto": 1000, "insurance": 2000, "handlingCharges": 0, "status": "active"},
        {"priceId": "PM-PUV-B", "model": "Turbo Max", "variant": "Unit Edit B",
         "exShowroom": 700000, "rto": 3000, "insurance": 4000, "handlingCharges": 0, "status": "active"},
        {"priceId": "PM-PUV-C", "model": "Storm", "variant": "Unit Edit C",
         "exShowroom": 800000, "rto": 5000, "insurance": 6000, "handlingCharges": 0, "status": "active"},
    ])
    first = await client.post("/api/leads", json={
        "customerName": "Pack Vehicle",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Unit Edit A",
        "executive": "Amit",
        "budget": 500000,
        "leadSource": "Walk-in",
    })
    assert first.status_code == 200, first.text
    lid = first.json()["leadId"]
    add = await client.post(f"/api/leads/{lid}/units", json={
        "model": "Turbo Max", "variant": "Unit Edit B",
    })
    assert add.status_code == 200, add.text
    return lid


@pytest.mark.asyncio
async def test_unit_2_model_and_variant_change_without_touching_unit_1(client):
    lid = await _pack(client)
    before = await server.db.leads.find_one({"leadId": lid})
    unit1 = dict(before["units"][0])
    r = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["units"][1]["model"] == "Storm"
    assert after["units"][1]["variant"] == "Unit Edit C"
    assert after["units"][1]["exShowroom"] != unit1.get("exShowroom")
    preview = (await client.get(f"/api/leads/{lid}/price-preview", params={"unit": 2})).json()
    assert preview["model"] == "Storm"
    assert preview["variant"] == "Unit Edit C"
    assert after["units"][1]["exShowroom"] == preview["priceStructure"]["exShowroom"]
    assert after["units"][0]["model"] == unit1.get("model") or before["interestedModel"]
    assert after["units"][0]["variant"] == unit1.get("variant") or before["variant"]
    assert after["units"][0].get("exShowroom") == unit1.get("exShowroom")
    assert after["interestedModel"] == before["interestedModel"]
    assert after["variant"] == before["variant"]
    file_edit = await client.put(f"/api/leads/{lid}/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert file_edit.status_code == 422


@pytest.mark.asyncio
async def test_unit_1_change_updates_the_file_header_only(client):
    lid = await _pack(client, "9813307102")
    before = await server.db.leads.find_one({"leadId": lid})
    r = await client.put(f"/api/leads/{lid}/units/1/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["interestedModel"] == "Storm"
    assert after["variant"] == "Unit Edit C"
    assert after["units"][0]["variant"] == "Unit Edit C"
    assert after["units"][1]["variant"] == before["units"][1]["variant"]
    assert after["units"][1]["model"] == before["units"][1]["model"]


@pytest.mark.asyncio
async def test_variant_must_be_in_price_master_and_executives_cannot_edit(client):
    lid = await _pack(client, "9813307103")
    bad = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Not A Real Variant",
    })
    assert bad.status_code == 422
    assert "Price Master" in bad.json()["detail"]
    ex = await _login("executive", "exec-puv@euler.com")
    try:
        denied = await ex.put(f"/api/leads/{lid}/units/2/vehicle", json={
            "model": "Storm", "variant": "Unit Edit C",
        })
        assert denied.status_code == 403
    finally:
        await ex.aclose()


@pytest.mark.asyncio
async def test_showroom_admin_can_edit_an_open_unit(client):
    lid = await _pack(client, "9813307104")
    tl = await _login("tl", "tl-puv@euler.com")
    try:
        r = await tl.put(f"/api/leads/{lid}/units/2/vehicle", json={
            "model": "Storm", "variant": "Unit Edit C",
        })
        assert r.status_code == 200, r.text
    finally:
        await tl.aclose()
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["units"][1]["variant"] == "Unit Edit C"


@pytest.mark.asyncio
async def test_a_paid_unit_keeps_its_price_when_the_name_changes(client):
    lid = await _pack(client, "9813307105")
    before = await server.db.leads.find_one({"leadId": lid})
    units = before["units"]
    kept = units[1].get("exShowroom")
    units[1]["totalReceived"] = units[1].get("customerPayable") or 1
    units[1]["customerOutstanding"] = 0
    units[1]["chassisNumber"] = "MD9UNIT2KEEP"
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"units": units}})
    r = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["units"][1]["variant"] == "Unit Edit C"
    assert after["units"][1]["exShowroom"] == kept
    assert after["units"][1]["chassisNumber"] == "MD9UNIT2KEEP"
