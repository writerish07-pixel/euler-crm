"""Approved business rules that were only covered by live-HTTP tests.

The live-HTTP modules (test_iter8/9/15 …) skip when REACT_APP_BACKEND_URL is
unset, so CI never ran them. These in-process tests lock the same rules.

Sources:
- memory/PRD.md Iteration 8-9: delivery needs a cleared customer outstanding;
  close needs a Close Reason; closing a delivered lead needs RC + number plate.
- PR #3: PUT /leads/{id} is a partial update.
- PR #41 / Iteration 15-16 and CLD-09: staff never receive owner P&L keys.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "approved_invariants")
os.environ.setdefault("JWT_SECRET", "approved-invariants-secret-32chars-x")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

OWNER = ("inv-owner@euler.com", "inv-owner-pass-1")
EXEC = ("inv-exec@euler.com", "inv-exec-pass-1")
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["approved_invariants_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    for (email, pw), role, uid, name in ((OWNER, "owner", "inv-owner", "Inv Owner"),
                                         (EXEC, "executive", "inv-exec", "Amit")):
        await AUTH_DB.users.update_one(
            {"email": email},
            {"$set": {"email": email, "name": name, "role": role, "userId": uid,
                      "passwordHash": server.authmod.hash_password(pw)}}, upsert=True)

    async def noop_sync(*a, **k):
        return {"ok": True, "operation": "skipped"}

    monkeypatch.setattr(server, "sheet_sync", noop_sync)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked_lead(client, mobile, executive="Amit"):
    r = await client.post("/api/leads", json={
        "customerName": f"Inv {mobile[-4:]}", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": executive, "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.json().get("found"), pv.text
    r = await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-11-09", "bookingAmount": 1000, "paymentMode": "Cash",
        "financeRequired": "No", "exchangeRequired": "No"})
    assert r.status_code == 200, r.text
    return lid


def _delivery_body(lid):
    return {"insurance": "Yes", "registration": "Yes", "invoice": "Yes", "rc": "Yes", "pdi": "Yes",
            "delivered": "Yes", "deliveryDate": "2026-11-11", "invoiceNumber": f"INV-{lid}",
            "chassisNumber": f"MD9INV{lid[-6:]}", "numberPlate": f"RJ14-{lid[-4:]}",
            "insuranceAgentId": "IA26AGENT1", "insurerName": "TestIns"}


@pytest.mark.asyncio
async def test_delivery_refused_while_customer_owes(client):
    lid = await _booked_lead(client, "9815500001")
    r = await client.put(f"/api/leads/{lid}/delivery", json=_delivery_body(lid))
    assert r.status_code == 422, r.text
    assert "outstanding" in str(r.json().get("detail")).lower()
    lead = await server.db.leads.find_one({"leadId": lid})
    assert str(lead.get("deliveryStatus") or "").lower() != "delivered"
    assert ce.num(lead["customerOutstanding"]) > 0


@pytest.mark.asyncio
async def test_close_rules_reason_then_rc_and_plate(client):
    lid = await _booked_lead(client, "9815500002")
    lead = await server.db.leads.find_one({"leadId": lid})
    pay = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": ce.num(lead["customerOutstanding"]), "paymentMode": "Cash", "date": "2026-11-10"})
    assert pay.status_code == 200, pay.text
    r = await client.put(f"/api/leads/{lid}/delivery", json=_delivery_body(lid))
    assert r.status_code == 200, r.text
    no_reason = await client.post(f"/api/leads/{lid}/close", json={})
    assert no_reason.status_code == 422, no_reason.text
    assert "reason" in str(no_reason.json().get("detail")).lower()
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"rcStatus": "", "numberPlate": ""}})
    await server.db.deliveries.update_one({"leadId": lid}, {"$set": {"rc": "", "numberPlate": ""}})
    no_rc = await client.post(f"/api/leads/{lid}/close", json={"closeReason": "Delivered and settled"})
    assert no_rc.status_code == 422, no_rc.text
    detail = str(no_rc.json().get("detail")).lower()
    assert "rc" in detail and "number plate" in detail
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead.get("currentStatus") != "Close Won"


@pytest.mark.asyncio
async def test_put_lead_is_partial_update(client):
    lid = await _booked_lead(client, "9815500003")
    before = await server.db.leads.find_one({"leadId": lid})
    r = await client.put(f"/api/leads/{lid}", json={"remarks": "partial update check"})
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after.get("remarks") == "partial update check"
    for key in ("customerName", "mobile", "interestedModel", "variant", "exShowroom",
                "customerPayable", "bookingDate", "currentStatus", "totalReceived"):
        assert after.get(key) == before.get(key), key


@pytest.mark.asyncio
async def test_staff_payloads_never_carry_owner_pnl_keys(client):
    lid = await _booked_lead(client, "9815500004", executive="Amit")
    owner_keys = (set(server.OWNER_PNL_LEAD_KEYS) | set(server.OWNER_PNL_COMMERCIAL_KEYS)
                  | set(server.OWNER_PNL_SHARE_KEYS))
    owner_view = (await client.get(f"/api/leads/{lid}")).json()
    assert "schemeAllocationSummary" in owner_view or "dealerTotalEarnings" in owner_view

    found = []

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                here = f"{path}.{k}" if path else k
                if k in owner_keys:
                    found.append(here)
                walk(v, here)
        elif isinstance(obj, list):
            for v in obj:
                walk(v, f"{path}[]")

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ex:
        r = await ex.post("/api/auth/login", json={"email": EXEC[0], "password": EXEC[1]})
        assert r.status_code == 200, r.text
        ex.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        for path in (f"/api/leads/{lid}", "/api/leads", f"/api/leads/{lid}/360"):
            resp = await ex.get(path)
            assert resp.status_code == 200, (path, resp.text)
            walk(resp.json(), path)
        assert (await ex.get("/api/dealer-earnings")).status_code == 403
    assert found == [], found


@pytest.mark.asyncio
async def test_rto_edit_never_moves_saved_ex_on_unsynced_turbo_row(client):
    """PR #299 / #306 vs #307: a booked file keeps its saved ex-showroom.

    The raw base of an unsynced Turbo catalog row is a valid booked price; an
    RTO / insurance edit or opening Price Structure must not add ₹15,000.
    """
    await server.db.price_master.delete_many({"priceId": "PM-INV-UNSYNC"})
    await server.db.price_master.insert_one({
        "priceId": "PM-INV-UNSYNC", "model": "Turbo Max", "variant": "Maxx Inv Unsynced",
        "exShowroom": 800000, "rto": 5500, "insurance": 19000, "status": "active"})
    lid = "LD-INV-UNSYNC"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Unsynced Turbo", "mobile": "9815500099",
        "interestedModel": "Turbo Max", "variant": "Maxx Inv Unsynced", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": "2026-09-20",
        "priceStructureSaved": True, "exShowroom": 800000, "rto": 5500, "insuranceAmount": 19000})
    pv = (await client.get(f"/api/leads/{lid}/price-preview")).json()
    assert ce.num(pv["priceStructure"]["exShowroom"]) == 800000, pv
    r = await client.put(f"/api/leads/{lid}/price-structure", json={
        "exShowroom": 800000, "rto": 2200, "insuranceAmount": 17000})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["exShowroom"]) == 800000
