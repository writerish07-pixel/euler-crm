"""OEM "Sold, PDI pending" list (Coulson vehicle-inventory/pending-tasks tile).

The sync stores chassis whose OEM PDI is not done; GET /oem-pdi-pending joins
them to CRM files. Nothing is written to Coulson or to leads, and the OEM row's
customer name / phone is never stored.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "oem_pdi_pending")
os.environ.setdefault("JWT_SECRET", "oem-pdi-pending-secret-32-chars-x")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import coulson  # noqa: E402
import oem_sync  # noqa: E402
import server  # noqa: E402

OWNER = ("pdi-owner@euler.com", "pdi-owner-pass-1")
EXEC = ("pdi-exec@euler.com", "pdi-exec-pass-1")
AUTH_DB = server.db


def _oem_row(chassis, **extra):
    return {
        "chassis": chassis, "invoice_number": f"INV-{chassis[-4:]}",
        "invoice_date": "2026-08-14T10:00:00", "model": "Turbo", "variant": "Range Maxx",
        "sap_product_name": "TURBO RANGEMAXX PV", "delivery_date": "2026-08-20",
        "customer_name": "Should Not Be Stored", "customer_phone": "9000000000",
        "is_pdi_done": False, **extra,
    }


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["oem_pdi_pending_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    for (email, pw), role, uid, name in ((OWNER, "owner", "pdi-owner", "PDI Owner"),
                                         (EXEC, "executive", "pdi-exec", "Amit")):
        await AUTH_DB.users.update_one(
            {"email": email},
            {"$set": {"email": email, "name": name, "role": role, "userId": uid,
                      "passwordHash": server.authmod.hash_password(pw)}}, upsert=True)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest.mark.real_coulson_pdi
def test_fetch_uses_the_coulson_pdi_pending_filter(monkeypatch):
    seen = {}

    def fake_page_rows(token, path, params=None, **kw):
        seen["path"], seen["params"] = path, dict(params or {})
        return []

    monkeypatch.setattr(coulson, "_page_rows", fake_page_rows)
    coulson.fetch_pdi_pending_sold("tok")
    assert seen["path"] == "vehicle-inventory/transfer"
    assert seen["params"]["vehicle_status"] == "SOLD"
    assert seen["params"]["is_pdi_done"] == "false"


@pytest.mark.asyncio
async def test_store_keeps_no_customer_data_and_partial_pull_keeps_last_list(client):
    db = server.db
    await db.oem_pdi_pending.delete_many({})
    n = await oem_sync.replace_pdi_pending(
        db, [_oem_row("MD9PDI0001"), _oem_row("md9 pdi0001"), _oem_row("MD9PDI0002")], complete=True)
    assert n == 2
    doc = await db.oem_pdi_pending.find_one({"chassis": "MD9PDI0001"})
    assert doc["soldDate"] and doc["oemModel"] == "Turbo"
    assert "customer_name" not in doc and "customerName" not in doc
    assert "customer_phone" not in doc and "mobile" not in doc
    kept = await oem_sync.replace_pdi_pending(db, [_oem_row("MD9PDI0009")], complete=False)
    assert kept == 2
    assert await db.oem_pdi_pending.find_one({"chassis": "MD9PDI0009"}) is None


@pytest.mark.asyncio
async def test_endpoint_joins_single_and_pack_units_and_is_desk_only(client):
    db = server.db
    await db.oem_pdi_pending.delete_many({})
    await oem_sync.replace_pdi_pending(
        db, [_oem_row("MD9PDI1001"), _oem_row("MD9PDI1002"), _oem_row("MD9PDI1003")], complete=True)
    await db.leads.delete_many({"leadId": {"$in": ["LD-PDI-1", "LD-PDI-2"]}})
    await db.leads.insert_one({
        "leadId": "LD-PDI-1", "customerName": "Delivered Single", "mobile": "9815600001",
        "chassisNumber": "MD9PDI1001", "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": "2026-08-21", "accountStatus": "Active", "executive": "Amit"})
    await db.leads.insert_one({
        "leadId": "LD-PDI-2", "customerName": "Pack Booked", "mobile": "9815600002",
        "currentStatus": "Booked", "accountStatus": "Active", "sameOrderMultiUnit": True,
        "units": [{"sno": 1, "chassisNumber": "MD9OTHER01"}, {"sno": 2, "chassisNumber": "MD9PDI1002"}]})
    r = await client.get("/api/oem-pdi-pending")
    assert r.status_code == 200, r.text
    body = r.json()
    by = {x["chassis"]: x for x in body["rows"]}
    assert by["MD9PDI1001"]["leadId"] == "LD-PDI-1" and by["MD9PDI1001"]["deliveredInCrm"] is True
    assert by["MD9PDI1002"]["leadId"] == "LD-PDI-2" and by["MD9PDI1002"]["deliveredInCrm"] is False
    assert by["MD9PDI1003"]["leadId"] == ""
    assert body["counts"] == {"total": 3, "onLead": 2, "delivered": 1, "notInCrm": 1}
    assert body["rows"][0]["chassis"] == "MD9PDI1001"  # delivered-but-PDI-pending first
    lead = await db.leads.find_one({"leadId": "LD-PDI-1"})
    assert "oemPdiPending" not in lead  # read-only join, lead untouched

    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ex:
        lg = await ex.post("/api/auth/login", json={"email": EXEC[0], "password": EXEC[1]})
        ex.headers.update({"Authorization": f"Bearer {lg.json()['token']}"})
        assert (await ex.get("/api/oem-pdi-pending")).status_code == 403
