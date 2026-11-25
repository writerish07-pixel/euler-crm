"""Turbo +₹15,000 ex-showroom from 1 Sep 2026. August bookings keep OEM."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "turbo_sept_uplift_tests")
os.environ.setdefault("JWT_SECRET", "turbo-sept-uplift-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
OEM_MAXX_PV = 770000
UPLIFT = 15000


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(c, name, mobile):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": mobile,
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": "Amit"})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


def test_turbo_overlay_math():
    row = {"model": "Turbo Max", "variant": "Maxx (PV)", "exShowroom": OEM_MAXX_PV}
    assert server._turbo_selling_ex(row, "2026-08-31") == OEM_MAXX_PV
    assert server._turbo_selling_ex(row, "2026-09-01") == OEM_MAXX_PV + UPLIFT
    storm = {"model": "Storm", "variant": "Storm (PV)", "exShowroom": 640000}
    assert server._turbo_selling_ex(storm, "2026-09-02") == 640000


def test_live_oem_sync_skips_turbo_overlay():
    """Coulson writes today's list — do not add the overlay again for current quotes."""
    live = {
        "model": "Turbo Max", "variant": "Maxx (DV220)",
        "exShowroom": 785713.33, "oemSyncedAt": "2026-09-04T08:00:00+00:00",
    }
    assert server._turbo_selling_ex(live, "2026-09-04") == 785713.33
    # August billed day peels the Sept uplift off a post-Sept synced list.
    assert server._turbo_selling_ex(live, "2026-08-31") == 785713.33 - UPLIFT
    # Sync before 1 Sep already stored the August list — do not peel again.
    aug_sync = {
        "model": "Turbo Max", "variant": "Maxx (DV220)",
        "exShowroom": 809999, "oemSyncedAt": "2026-08-20T10:00:00+00:00",
    }
    assert server._turbo_selling_ex(aug_sync, "2026-08-31") == 809999
    unsynced = {"model": "Turbo Max", "variant": "Maxx (DV220)", "exShowroom": 809999}
    assert server._turbo_selling_ex(unsynced, "2026-09-04") == 809999 + UPLIFT
    assert server._turbo_selling_ex(unsynced, "2026-08-20") == 809999


@pytest.mark.asyncio
async def test_price_list_quotes_turbo_with_sept_uplift(client):
    body = (await client.get("/api/price-list", params={"model": "Turbo Max"})).json()
    rows = [r for g in body["models"] for r in g["rows"]]
    maxx = next(r for r in rows if r["variant"] == "Maxx (PV)")
    pm = next(r for r in (await client.get("/api/price-master", params={"model": "Turbo Max"})).json()
              if r["variant"] == "Maxx (PV)")
    assert pm["exShowroom"] == OEM_MAXX_PV
    assert pm["sellingExShowroom"] == OEM_MAXX_PV + UPLIFT
    assert maxx["exShowroom"] == OEM_MAXX_PV + UPLIFT


@pytest.mark.asyncio
async def test_august_booking_keeps_oem_price(client):
    lid = await _lead(client, "Aug Turbo", "9535010001")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-20", "bookingAmount": 0})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["exShowroom"] == OEM_MAXX_PV
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV
    assert preview["asOf"] == "2026-08-20"


@pytest.mark.asyncio
async def test_september_booking_adds_uplift(client):
    lid = await _lead(client, "Sep Turbo", "9535010002")
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-09-01", "bookingAmount": 0})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["exShowroom"] == OEM_MAXX_PV + UPLIFT
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV + UPLIFT


@pytest.mark.asyncio
async def test_opening_an_august_lead_keeps_the_saved_price_after_oem_sync(client):
    """Price Master is overwritten by Coulson. August billed day still peels to OEM."""
    lid = await _lead(client, "Aug Keep", "9535010003")
    booked = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-20", "bookingAmount": 0})
    assert booked.status_code == 200, booked.text
    before = await server.db.leads.find_one({"leadId": lid})
    assert before["exShowroom"] == OEM_MAXX_PV
    await server.db.price_master.update_one(
        {"model": TURBO[0], "variant": TURBO[1]},
        {"$set": {
            "exShowroom": OEM_MAXX_PV + 15000,
            "oemSyncedAt": "2026-11-22T05:36:53+00:00",
        }},
    )
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV
    assert preview.get("keptSavedEx") is True
    # masterExShowroom is the billed-day list (peeled), not raw synced base.
    assert preview.get("masterExShowroom") == OEM_MAXX_PV
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["exShowroom"] == OEM_MAXX_PV


@pytest.mark.asyncio
async def test_august_file_stuck_on_todays_list_is_corrected(client):
    """LD26000185-style: file holds synced Nov list; OEM billed Aug → show Aug list."""
    lid = await _lead(client, "Aug Stuck", "9535010007")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked",
        "bookingDate": "2026-08-31",
        "soldDate": "2026-08-31",
        "interestedModel": TURBO[0],
        "variant": "Maxx (DV220)",
        "exShowroom": 824999,
        "priceStructureSaved": True,
        "cxDemand": 830000,
        "useDealPrice": True,
        "customerPayable": 830000,
        "units": [{
            "sno": 1, "model": TURBO[0], "variant": "Maxx (DV220)",
            "soldDate": "2026-08-31", "exShowroom": 824999,
            "priceStructureSaved": True, "cxDemand": 830000, "useDealPrice": True,
        }],
    }})
    await server.db.price_master.update_one(
        {"model": TURBO[0], "variant": "Maxx (DV220)"},
        {"$set": {
            "exShowroom": 824999,
            "oemSyncedAt": "2026-11-25T06:11:09+00:00",
            "status": "active",
        }},
        upsert=True,
    )
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["asOf"] == "2026-08-31"
    assert preview.get("keptSavedEx") is False
    assert preview["priceStructure"]["exShowroom"] == 824999 - UPLIFT
    assert preview.get("masterExShowroom") == 824999 - UPLIFT
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 824999, "rto": 700, "insuranceAmount": 18049,
    })
    assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["exShowroom"] == 824999 - UPLIFT


def test_oem_billed_date_decides_price_as_of():
    lead = {"bookingDate": "2026-08-20", "soldDate": "2026-08-31"}
    assert server._lead_price_as_of(lead) == "2026-08-31"
    unit = {"soldDate": "2026-09-15"}
    assert server._lead_price_as_of(lead, unit=unit) == "2026-09-15"
    assert server._lead_price_as_of({"bookingDate": "2026-08-20"}) == "2026-08-20"


@pytest.mark.asyncio
async def test_pack_unit_without_its_own_ex_does_not_take_unit1_price(client):
    """Unit 2 must take Price Master for its billed day, not Unit 1's saved ex."""
    created = await client.post("/api/leads", json={
        "customerName": "Pack Price", "mobile": "9535010004",
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": "Amit",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "model": TURBO[0], "variant": TURBO[1]},
            {"sno": 2, "model": TURBO[0], "variant": "Maxx (FB)"},
        ],
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "bookingDate": "2026-08-20",
        "soldDate": "2026-08-31",
        "exShowroom": OEM_MAXX_PV,
        "priceStructureSaved": True,
        "sameOrderMultiUnit": True,
        "vehicleCount": 2,
        "units": [
            {
                "sno": 1, "model": TURBO[0], "variant": TURBO[1],
                "soldDate": "2026-08-31", "exShowroom": OEM_MAXX_PV,
                "priceStructureSaved": True,
            },
            {
                "sno": 2, "model": TURBO[0], "variant": "Maxx (FB)",
                "soldDate": "2026-08-31",
            },
        ],
    }})
    u1 = (await client.get(f"/api/leads/{lid}/price-preview", params={"unit": 1})).json()
    u2 = (await client.get(f"/api/leads/{lid}/price-preview", params={"unit": 2})).json()
    assert u1["asOf"] == "2026-08-31"
    assert u1["keptSavedEx"] is True
    assert u1["priceStructure"]["exShowroom"] == OEM_MAXX_PV
    assert u2["asOf"] == "2026-08-31"
    assert u2.get("keptSavedEx") is False
    assert abs(float(u2["priceStructure"]["exShowroom"]) - OEM_MAXX_PV) > 1


@pytest.mark.asyncio
async def test_pack_unit2_charge_edit_keeps_saved_ex_after_oem_hike(client):
    """Saving insurance on unit 2 must not write today's master or drop Cx Demand."""
    created = await client.post("/api/leads", json={
        "customerName": "Pack Charge", "mobile": "9535010005",
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": "Amit",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "model": TURBO[0], "variant": TURBO[1]},
            {"sno": 2, "model": TURBO[0], "variant": TURBO[1]},
        ],
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked",
        "bookingDate": "2026-08-20",
        "soldDate": "2026-08-31",
        "exShowroom": OEM_MAXX_PV,
        "priceStructureSaved": True,
        "sameOrderMultiUnit": True,
        "vehicleCount": 2,
        "units": [
            {
                "sno": 1, "model": TURBO[0], "variant": TURBO[1],
                "soldDate": "2026-08-31", "exShowroom": OEM_MAXX_PV,
                "priceStructureSaved": True, "rto": 5000, "insuranceAmount": 8000,
                "cxDemand": 783000, "useDealPrice": True, "customerPayable": 783000,
            },
            {
                "sno": 2, "model": TURBO[0], "variant": TURBO[1],
                "soldDate": "2026-08-31", "exShowroom": OEM_MAXX_PV,
                "priceStructureSaved": True, "rto": 5000, "insuranceAmount": 8000,
                "cxDemand": 783000, "useDealPrice": True, "customerPayable": 783000,
            },
        ],
    }})
    await server.db.price_master.update_one(
        {"model": TURBO[0], "variant": TURBO[1]},
        {"$set": {
            "exShowroom": OEM_MAXX_PV + 15000,
            "oemSyncedAt": "2026-11-22T05:36:53+00:00",
        }},
    )
    preview = (await client.get(
        f"/api/leads/{lid}/price-preview", params={"unit": 2})).json()
    assert preview["keptSavedEx"] is True
    assert preview["priceStructure"]["exShowroom"] == OEM_MAXX_PV
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": OEM_MAXX_PV, "rto": 5000, "insuranceAmount": 9000, "unitSno": 2,
    })
    assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    u2 = after["units"][1]
    assert u2["exShowroom"] == OEM_MAXX_PV
    assert u2["insuranceAmount"] == 9000
    assert u2.get("useDealPrice") is True
    assert abs(float(u2.get("cxDemand") or 0) - 783000) < 1


@pytest.mark.asyncio
async def test_sept_unit_on_aug_pack_keeps_sept_list(client):
    """Adding a September-billed unit to an August booking must not take August price."""
    created = await client.post("/api/leads", json={
        "customerName": "Pack Mixed Dates", "mobile": "9535010008",
        "interestedModel": TURBO[0], "variant": "Maxx (DV220)", "executive": "Amit",
        "sameOrderMultiUnit": True, "vehicleCount": 1,
        "units": [{"sno": 1, "model": TURBO[0], "variant": "Maxx (DV220)"}],
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    await server.db.price_master.update_one(
        {"model": TURBO[0], "variant": "Maxx (DV220)"},
        {"$set": {
            "exShowroom": 824999,
            "oemSyncedAt": "2026-11-25T06:11:09+00:00",
            "status": "active",
        }},
        upsert=True,
    )
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked",
        "bookingDate": "2026-08-31",
        "soldDate": "2026-08-31",
        "exShowroom": 824999 - UPLIFT,
        "priceStructureSaved": True,
        "sameOrderMultiUnit": True,
        "units": [{
            "sno": 1, "model": TURBO[0], "variant": "Maxx (DV220)",
            "soldDate": "2026-08-31", "exShowroom": 824999 - UPLIFT,
            "priceStructureSaved": True,
        }],
    }})
    added = await client.post(f"/api/leads/{lid}/units", json={
        "model": TURBO[0], "variant": "Maxx (DV220)", "soldDate": "2026-09-02",
    })
    assert added.status_code == 200, added.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert len(after["units"]) == 2
    assert after["units"][0]["exShowroom"] == 824999 - UPLIFT
    assert after["units"][1]["exShowroom"] == 824999
    assert after["units"][1].get("soldDate") == "2026-09-02"


@pytest.mark.asyncio
async def test_pack_charge_edit_keeps_cx_when_correcting_billed_day_list(client):
    """Correcting today's synced list on save must not clear the agreed payable."""
    created = await client.post("/api/leads", json={
        "customerName": "Pack Cx Keep", "mobile": "9535010009",
        "interestedModel": TURBO[0], "variant": "Maxx (DV220)", "executive": "Amit",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "model": TURBO[0], "variant": "Maxx (DV220)"},
            {"sno": 2, "model": TURBO[0], "variant": "Maxx (DV220)"},
        ],
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    await server.db.price_master.update_one(
        {"model": TURBO[0], "variant": "Maxx (DV220)"},
        {"$set": {
            "exShowroom": 824999,
            "oemSyncedAt": "2026-11-25T06:11:09+00:00",
            "status": "active",
        }},
        upsert=True,
    )
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked",
        "bookingDate": "2026-08-31",
        "soldDate": "2026-08-31",
        "exShowroom": 824999,
        "priceStructureSaved": True,
        "sameOrderMultiUnit": True,
        "vehicleCount": 2,
        "units": [
            {
                "sno": 1, "model": TURBO[0], "variant": "Maxx (DV220)",
                "soldDate": "2026-08-31", "exShowroom": 824999,
                "priceStructureSaved": True, "rto": 700, "insuranceAmount": 18049,
                "cxDemand": 830000, "useDealPrice": True, "customerPayable": 830000,
            },
            {
                "sno": 2, "model": TURBO[0], "variant": "Maxx (DV220)",
                "soldDate": "2026-08-31", "exShowroom": 824999,
                "priceStructureSaved": True, "rto": 700, "insuranceAmount": 18049,
                "cxDemand": 830000, "useDealPrice": True, "customerPayable": 830000,
            },
        ],
    }})
    saved = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 824999, "rto": 700, "insuranceAmount": 18049, "unitSno": 2,
    })
    assert saved.status_code == 200, saved.text
    after = await server.db.leads.find_one({"leadId": lid})
    u2 = after["units"][1]
    assert u2["exShowroom"] == 824999 - UPLIFT
    assert u2.get("useDealPrice") is True
    assert abs(float(u2.get("cxDemand") or 0) - 830000) < 1


@pytest.mark.asyncio
async def test_field_role_price_preview_hides_deal_prices(client):
    """ASM / RM field view must not receive stored deal commercials."""
    lid = await _lead(client, "Field Hide", "9535010006")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "bookingDate": "2026-08-20", "exShowroom": OEM_MAXX_PV,
        "priceStructureSaved": True,
    }})
    await server.db.users.update_one(
        {"email": "asm@euler.com"},
        {"$set": {
            "email": "asm@euler.com", "role": "ASM", "name": "ASM",
            "passwordHash": (await server.db.users.find_one(
                {"email": "owner@euler.com"}))["passwordHash"],
            "active": True,
        }},
        upsert=True,
    )
    login = await client.post("/api/auth/login", json={
        "email": "asm@euler.com", "password": "euler@123"})
    assert login.status_code == 200, login.text
    token = login.json()["token"]
    r = await client.get(
        f"/api/leads/{lid}/price-preview",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("found") is False
    assert body.get("fieldView") is True
    assert "priceStructure" not in body or not body.get("priceStructure")
