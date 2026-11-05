"""Built → billed body banner (live from Coulson) and the Model + Variant editor.

Regression: a Turbo Max file whose chassis was built PV and converted / billed
as FB on Coulson showed "(was Storm LR200)" — a stale originalModel left by a
wrong chassis that had been on the file earlier.
"""
import os
import sys

import httpx
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_oem_billing import client, _no_live_coulson_sold, oem_sync, server  # noqa: E402,F401

CHASSIS = "MD9EVDAD26K0BODY1"
CONVERTED = {
    "chassis": CHASSIS, "mobile": "9024111001", "invoiceNumber": "AF-BODY-1",
    "customerName": "Body Change", "model": "Turbo Max", "variant": "Maxx (PV)",
    "oemSkuKey": "turbo.maxx.pv", "loadBody": "PV", "updatedLoadBody": "FB",
    "coulsonStatus": "SOLD", "soldDate": "2026-11-03",
}
STORM_ROW = {
    "chassis": "MD9EMSDL26E0BODY2", "mobile": "9024111001", "model": "Storm",
    "variant": "Storm LR (PV) Reg C7 6.6kWh", "coulsonStatus": "SOLD",
}


def _lead(**kw):
    return {
        "leadId": "LD-BODY", "customerName": "Body Change", "mobile": "9024111001",
        "accountStatus": "Active", "currentStatus": "Booked",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", "chassisNumber": CHASSIS, **kw,
    }


# ------------------------------------------------------------------ banner notes
def test_converted_chassis_reads_built_pv_billed_fb():
    (note,) = oem_sync.body_change_notes(_lead(), [CONVERTED])
    assert (note["builtBody"], note["billedBody"]) == ("PV", "FB")
    assert note["chassis"] == CHASSIS and note["unitSno"] == 1


def test_stale_original_vehicle_is_ignored():
    """originalModel / originalVariant from an earlier wrong chassis do not leak in."""
    notes = oem_sync.body_change_notes(
        _lead(originalModel="Storm", originalVariant="LR200"), [CONVERTED])
    assert [(n["builtBody"], n["billedBody"]) for n in notes] == [("PV", "FB")]


def test_no_note_when_body_was_not_changed():
    same = {**CONVERTED, "updatedLoadBody": ""}
    assert oem_sync.body_change_notes(_lead(variant="Maxx (PV)"), [same]) == []


def test_no_note_for_a_wrong_model_chassis_or_no_sold_row():
    assert oem_sync.body_change_notes(_lead(chassisNumber=STORM_ROW["chassis"]), [STORM_ROW]) == []
    assert oem_sync.body_change_notes(_lead(), []) == []


def test_pack_notes_are_per_unit():
    other = {**CONVERTED, "chassis": "MD9EVDAD26K0BODY3", "updatedLoadBody": ""}
    pack = _lead(sameOrderMultiUnit=True, units=[
        {"sno": 1, "model": "Turbo Max", "variant": "Maxx (FB)", "chassisNumber": CHASSIS},
        {"sno": 2, "model": "Turbo Max", "variant": "Maxx (PV)", "chassisNumber": "MD9EVDAD26K0BODY3"},
    ])
    notes = oem_sync.body_change_notes(pack, [CONVERTED, other])
    assert [(n["unitSno"], n["builtBody"], n["billedBody"]) for n in notes] == [(1, "PV", "FB")]


# ------------------------------------------------------------------ 360 + vehicle API
@pytest_asyncio.fixture(autouse=True)
async def _clean():
    yield
    await server.db.leads.delete_many({"$or": [{"mobile": {"$regex": "^9024111"}},
                                               {"leadId": {"$regex": "^LD-VEH-"}}]})
    await server.db.oem_sold.delete_many({"chassis": {"$regex": "BODY"}})


async def _new_lead(c, mobile, variant="Maxx (PV)"):
    # Own id, not POST /leads: other modules insert real-looking LD26… ids
    # without bumping the counter, so a minted id can collide in a full run.
    lid = f"LD-VEH-{mobile[-4:]}"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": f"Vehicle Edit {mobile[-4:]}", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": variant, "executive": "Amit",
        "leadSource": "Walk-in", "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-11-05",
    })
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    assert (await c.put(f"/api/leads/{lid}/price-structure", json=ps)).status_code == 200
    return lid


async def _login_as(role, email):
    await server.db.users.update_one(
        {"email": email},
        {"$set": {"email": email, "name": role.upper(), "role": role, "userId": f"uid-{role}-body",
                  "passwordHash": server.authmod.hash_password("body-pass-1")}},
        upsert=True)
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": "body-pass-1"})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


@pytest.mark.asyncio
async def test_360_carries_the_live_body_change(client):
    lid = await _new_lead(client, "9024111002", variant="Maxx (FB)")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "chassisNumber": CHASSIS, "originalModel": "Storm", "originalVariant": "LR200"}})
    await server.db.oem_sold.delete_many({"chassis": CHASSIS})
    await server.db.oem_sold.insert_one({**CONVERTED, "mobile": "9024111002"})
    body = (await client.get(f"/api/leads/{lid}/360")).json()
    notes = body["lead"]["oemBodyChanges"]
    assert [(n["builtBody"], n["billedBody"]) for n in notes] == [("PV", "FB")]


@pytest.mark.asyncio
async def test_vehicle_change_reprices_and_moves_the_unit(client):
    lid = await _new_lead(client, "9024111003")
    before = await server.db.leads.find_one({"leadId": lid})
    variants = (await client.get("/api/price-master/variants", params={"model": "Turbo Max"})).json()
    other = next(v for v in variants if v["variant"] != "Maxx (PV)"
                 and abs(float(v.get("exShowroom") or 0) - float(before["exShowroom"])) > 1)
    r = await client.put(f"/api/leads/{lid}/vehicle",
                         json={"model": "Turbo Max", "variant": other["variant"]})
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["variant"] == other["variant"]
    assert after["exShowroom"] != before["exShowroom"]          # auto-repriced
    preview = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert preview["variant"] == other["variant"]              # unit 1 moved too
    assert after["exShowroom"] == preview["priceStructure"]["exShowroom"]


@pytest.mark.asyncio
async def test_vehicle_change_refuses_a_variant_not_in_price_master(client):
    lid = await _new_lead(client, "9024111004")
    r = await client.put(f"/api/leads/{lid}/vehicle", json={"model": "Storm", "variant": "Maxx (FB)"})
    assert r.status_code == 422
    assert "Price Master" in r.json()["detail"]
    r = await client.put(f"/api/leads/{lid}/vehicle", json={"model": "Turbo Max", "variant": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_showroom_admin_can_change_vehicle_executive_cannot(client):
    lid = await _new_lead(client, "9024111005")
    variants = (await client.get("/api/price-master/variants", params={"model": "Turbo Max"})).json()
    other = next(v["variant"] for v in variants if v["variant"] != "Maxx (PV)")
    tl = await _login_as("tl", "tl-body@euler.com")
    try:
        r = await tl.put(f"/api/leads/{lid}/vehicle", json={"model": "Turbo Max", "variant": other})
        assert r.status_code == 200, r.text
    finally:
        await tl.aclose()
    ex = await _login_as("executive", "exec-body@euler.com")
    try:
        r = await ex.put(f"/api/leads/{lid}/vehicle", json={"model": "Turbo Max", "variant": "Maxx (PV)"})
        assert r.status_code == 403
    finally:
        await ex.aclose()
