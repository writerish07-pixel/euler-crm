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
    assert after["exShowroom"] == 800000
    assert after["units"][0]["exShowroom"] == 800000
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
async def test_a_paid_unit_takes_the_new_variant_price(client):
    """Changing unit 2's variant replaces the price, even when that unit is paid."""
    lid = await _pack(client, "9813307105")
    before = await server.db.leads.find_one({"leadId": lid})
    units = before["units"]
    old_ex = units[1].get("exShowroom")
    old_pay = units[1].get("customerPayable") or old_ex
    units[1]["cxDemand"] = old_pay
    units[1]["useDealPrice"] = True
    units[1]["customerPayable"] = old_pay
    units[1]["totalReceived"] = old_pay
    units[1]["customerOutstanding"] = 0
    units[1]["chassisNumber"] = "MD9UNIT2KEEP"
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"units": units}})
    r = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    unit2 = after["units"][1]
    assert unit2["variant"] == "Unit Edit C"
    assert unit2["exShowroom"] == 800000
    assert unit2["exShowroom"] != old_ex
    assert unit2["rto"] == 5000
    assert unit2["insuranceAmount"] == 6000
    assert unit2.get("useDealPrice") is not True
    assert unit2.get("cxDemand") in (None, 0, 0.0)
    assert unit2["customerPayable"] != old_pay
    assert unit2["customerPayable"] >= 800000
    assert unit2["chassisNumber"] == "MD9UNIT2KEEP"
    assert after["units"][0].get("exShowroom") == before["units"][0].get("exShowroom")


@pytest.mark.asyncio
async def test_resaving_the_same_variant_releases_the_old_price(client):
    """Unit 2 already says DV, but the customer price is still the previous deal."""
    lid = await _pack(client, "9813307106")
    before = await server.db.leads.find_one({"leadId": lid})
    units = before["units"]
    units[1]["model"] = "Storm"
    units[1]["variant"] = "Unit Edit C"
    units[1]["exShowroom"] = 700000
    units[1]["cxDemand"] = 707000
    units[1]["useDealPrice"] = True
    units[1]["customerPayable"] = 707000
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"units": units}})
    r = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    unit2 = after["units"][1]
    assert unit2["variant"] == "Unit Edit C"
    assert unit2["exShowroom"] == 800000
    assert unit2["customerPayable"] != 707000
    assert unit2.get("useDealPrice") is not True


@pytest.mark.asyncio
async def test_resaving_same_variant_drops_a_locked_cx_when_ex_already_matches(client):
    """Ex-showroom can already be the new variant while the payable is still the old deal."""
    lid = await _pack(client, "9813307107")
    before = await server.db.leads.find_one({"leadId": lid})
    units = before["units"]
    units[1]["model"] = "Storm"
    units[1]["variant"] = "Unit Edit C"
    units[1]["exShowroom"] = 800000
    units[1]["rto"] = 5000
    units[1]["insuranceAmount"] = 6000
    units[1]["cxDemand"] = 707000
    units[1]["useDealPrice"] = False
    units[1]["customerPayable"] = 707000
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"units": units}})
    r = await client.put(f"/api/leads/{lid}/units/2/vehicle", json={
        "model": "Storm", "variant": "Unit Edit C",
    })
    assert r.status_code == 200, r.text
    unit2 = (await server.db.leads.find_one({"leadId": lid}))["units"][1]
    assert unit2["exShowroom"] == 800000
    assert unit2["customerPayable"] != 707000
    assert unit2.get("cxDemand") in (None, 0, 0.0)


@pytest.mark.asyncio
async def test_booked_unit_1_price_save_uses_its_own_variant_not_the_header(client):
    """Unit 1 is variant C. The lead header still has variant A's ex-showroom.

    Saving price must write C's Price Master price. A later RTO edit keeps
    that customer price and moves Additional.
    """
    lid = await _pack(client, "9813307108")
    before = await server.db.leads.find_one({"leadId": lid})
    units = before["units"]
    units[0]["model"] = "Storm"
    units[0]["variant"] = "Unit Edit C"
    units[0]["exShowroom"] = 500000
    units[0]["rto"] = 1000
    units[0]["insuranceAmount"] = 2000
    units[0]["cxDemand"] = 503000
    units[0]["useDealPrice"] = True
    units[0]["customerPayable"] = 503000
    units[0]["additionalDiscount"] = 0
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "currentStatus": "Booked",
        "bookingDate": "2026-11-06",
        "exShowroom": 500000,
        "interestedModel": "Turbo Max",
        "variant": "Unit Edit A",
    }})
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 500000, "rto": 5000, "insuranceAmount": 6000, "unitSno": 1,
    })
    assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    unit1 = after["units"][0]
    assert unit1["exShowroom"] == 800000
    assert unit1["customerPayable"] != 503000
    assert unit1["customerPayable"] >= 800000
    assert after["exShowroom"] == 800000
    assert after["units"][1]["exShowroom"] == before["units"][1].get("exShowroom")
    pay = unit1["customerPayable"]
    cut = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 800000, "rto": 2000, "insuranceAmount": 6000, "unitSno": 1,
    })
    assert cut.status_code == 200, cut.text
    recut = (await server.db.leads.find_one({"leadId": lid}))["units"][0]
    assert recut["exShowroom"] == 800000
    assert recut["customerPayable"] == pay
    assert recut["rto"] == 2000


@pytest.mark.asyncio
async def test_blank_unit_1_of_another_variant_does_not_copy_the_header_price(client):
    lid = await _pack(client, "9813307109")
    lead = await server.db.leads.find_one({"leadId": lid})
    units = lead["units"]
    units[0]["model"] = "Storm"
    units[0]["variant"] = "Unit Edit C"
    units[0]["exShowroom"] = 0
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "exShowroom": 500000,
        "interestedModel": "Turbo Max",
        "variant": "Unit Edit A",
    }})
    await server.recompute_lead(lid)
    unit1 = (await server.db.leads.find_one({"leadId": lid}))["units"][0]
    assert unit1["exShowroom"] == 800000


@pytest.mark.asyncio
async def test_same_variant_list_rise_does_not_drop_the_agreed_price(client):
    """Recording actual RTO must not rebill a booked unit from a newer list price."""
    lid = await _pack(client, "9813307110")
    lead = await server.db.leads.find_one({"leadId": lid})
    pay = 498500
    units = []
    for u in lead["units"]:
        rec = dict(u)
        rec["model"] = "Turbo Max"
        rec["variant"] = "Unit Edit A"
        rec["exShowroom"] = 500000
        rec["rto"] = 1000
        rec["insuranceAmount"] = 2000
        rec["cxDemand"] = pay
        rec["useDealPrice"] = True
        rec["customerPayable"] = pay
        rec["additionalDiscount"] = 4500
        units.append(rec)
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "currentStatus": "Booked",
        "bookingDate": "2026-11-06",
        "interestedModel": "Turbo Max",
        "variant": "Unit Edit A",
        "exShowroom": 500000,
        "additionalDiscount": 4500,
        "cxDemand": pay,
        "useDealPrice": True,
    }})
    await server.db.price_master.update_one(
        {"priceId": "PM-PUV-A"}, {"$set": {"exShowroom": 520000}})
    cut = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 520000, "rto": 0, "insuranceAmount": 2000, "unitSno": 1,
    })
    assert cut.status_code == 200, cut.text
    unit1 = (await server.db.leads.find_one({"leadId": lid}))["units"][0]
    assert unit1["exShowroom"] == 500000
    assert unit1["customerPayable"] == pay
    assert unit1["rto"] == 0
    assert unit1["additionalDiscount"] == 3500


@pytest.mark.asyncio
async def test_variant_correction_does_not_restore_header_additional(client):
    """A zeroed Additional must stay zero when the header still has the old discount."""
    lid = await _pack(client, "9813307111")
    lead = await server.db.leads.find_one({"leadId": lid})
    units = lead["units"]
    units[0]["model"] = "Storm"
    units[0]["variant"] = "Unit Edit C"
    units[0]["exShowroom"] = 500000
    units[0]["rto"] = 1000
    units[0]["insuranceAmount"] = 2000
    units[0]["cxDemand"] = 498000
    units[0]["useDealPrice"] = True
    units[0]["customerPayable"] = 498000
    units[0]["additionalDiscount"] = 5000
    units[1]["model"] = "Storm"
    units[1]["variant"] = "Unit Edit C"
    units[1]["exShowroom"] = 800000
    units[1]["additionalDiscount"] = 0
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "currentStatus": "Booked",
        "bookingDate": "2026-11-06",
        "interestedModel": "Turbo Max",
        "variant": "Unit Edit A",
        "exShowroom": 500000,
        "additionalDiscount": 5000,
    }})
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 500000, "rto": 5000, "insuranceAmount": 6000, "unitSno": 1,
    })
    assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    unit1 = after["units"][0]
    assert unit1["exShowroom"] == 800000
    assert unit1["additionalDiscount"] == 0
    assert unit1["customerPayable"] == 811000


@pytest.mark.asyncio
async def test_blank_unit_price_save_drops_the_stale_payable(client):
    """A unit with no ex-showroom must not lock an old payable onto the new price."""
    lid = await _pack(client, "9813307112")
    lead = await server.db.leads.find_one({"leadId": lid})
    units = lead["units"]
    units[0]["model"] = "Storm"
    units[0]["variant"] = "Unit Edit C"
    units[0]["exShowroom"] = 0
    units[0]["customerPayable"] = 503000
    units[0].pop("cxDemand", None)
    units[0]["useDealPrice"] = False
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "currentStatus": "Booked",
        "bookingDate": "2026-11-06",
        "additionalDiscount": 0,
    }})
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 800000, "rto": 5000, "insuranceAmount": 6000, "unitSno": 1,
    })
    assert saved.status_code == 200, saved.text
    unit1 = (await server.db.leads.find_one({"leadId": lid}))["units"][0]
    assert unit1["exShowroom"] == 800000
    assert unit1["customerPayable"] == 811000
    assert unit1.get("cxDemand") in (None, 0, 0.0)


@pytest.mark.asyncio
async def test_alias_variant_keeps_the_booked_header_price(client):
    """Maxx (DV200) is the same vehicle as Maxx (DV220). A blank unit keeps the booked price."""
    lid = await _pack(client, "9813307113")
    await server.db.price_master.delete_many({"priceId": "PM-PUV-DV"})
    await server.db.price_master.insert_one({
        "priceId": "PM-PUV-DV", "model": "Turbo Max", "variant": "Maxx (DV220)",
        "exShowroom": 809999, "rto": 5500, "insurance": 19000, "handlingCharges": 0,
        "status": "active",
    })
    lead = await server.db.leads.find_one({"leadId": lid})
    units = lead["units"]
    units[0]["model"] = "Turbo Max"
    units[0]["variant"] = "Maxx (DV200)"
    units[0]["exShowroom"] = 0
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "units": units,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (DV220)",
        "exShowroom": 825000,
        "currentStatus": "Booked",
        "bookingDate": "2026-11-06",
    }})
    await server.recompute_lead(lid)
    unit1 = (await server.db.leads.find_one({"leadId": lid}))["units"][0]
    assert unit1["exShowroom"] == 825000
