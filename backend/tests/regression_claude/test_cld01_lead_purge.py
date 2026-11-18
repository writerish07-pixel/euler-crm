"""CLD-01: the lead register and boot must not delete genuine leads."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld01_lead_purge")
os.environ.setdefault("JWT_SECRET", "cld01-lead-purge-secret-32chars")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("SEED_DEMO_USERS", "1")

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
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(lid, **extra):
    doc = {
        "leadId": lid, "customerName": "Ramesh Kumar", "mobile": "",
        "interestedModel": "Hi-Load", "variant": "SR",
        "accountStatus": "Active", "currentStatus": "New",
        "createdDate": "2026-08-02",
    }
    doc.update(extra)
    await server.db.leads.insert_one(doc)


@pytest.mark.asyncio
async def test_same_name_blank_mobile_months_apart_survives_register_and_boot(client, monkeypatch):
    await server.db.leads.delete_many({"customerName": "Ramesh Kumar"})
    await _lead("LD26CLD01A", createdDate="2026-08-02", lastUpdated="2026-08-02T04:00:00+00:00")
    await _lead("LD26CLD01B", createdDate="2026-11-10", lastUpdated="2026-11-10T04:00:00+00:00")
    await server.db.activities.insert_one({"activityId": "A1", "leadId": "LD26CLD01B", "note": "visit"})
    await server.db[server.lead_docs.COLLECTION].insert_one({"leadId": "LD26CLD01B", "kind": "kyc_pan"})
    listed = await client.get("/api/leads", params={"q": "Ramesh Kumar", "scope": "all"})
    assert listed.status_code == 200
    await client.get("/api/leads", params={"q": "Ramesh Kumar", "scope": "all"})
    monkeypatch.setenv("ENVIRONMENT", "production")
    await server._run_boot_maintenance()
    ids = [l["leadId"] async for l in server.db.leads.find({"customerName": "Ramesh Kumar"})]
    assert sorted(ids) == ["LD26CLD01A", "LD26CLD01B"]
    assert await server.db.activities.count_documents({"leadId": "LD26CLD01B"}) == 1


@pytest.mark.asyncio
async def test_same_mobile_months_apart_both_remain(client):
    mobile = "9822200011"
    await server.db.leads.delete_many({"mobile": {"$in": [mobile, "+91 98222 00011"]}})
    await _lead("LD26CLD01C", customerName="Storm One", mobile=mobile,
                interestedModel="Storm EV", variant="City",
                createdDate="2026-06-01", lastUpdated="2026-06-01T04:00:00+00:00")
    await _lead("LD26CLD01D", customerName="Storm One", mobile="+91 98222 00011",
                interestedModel="Storm EV", variant="City",
                createdDate="2026-11-01", lastUpdated="2026-11-01T04:00:00+00:00")
    await client.get("/api/leads", params={"scope": "all"})
    ids = [l["leadId"] async for l in server.db.leads.find({"leadId": {"$in": ["LD26CLD01C", "LD26CLD01D"]}})]
    assert sorted(ids) == ["LD26CLD01C", "LD26CLD01D"]


@pytest.mark.asyncio
async def test_true_retry_is_dry_run_then_archived(client):
    mobile = "9811100011"
    await server.db.leads.delete_many({"mobile": mobile})
    for i, lid in enumerate(("LD26CLD01E", "LD26CLD01F", "LD26CLD01G")):
        await _lead(lid, customerName="Retry", mobile=mobile,
                    interestedModel="Turbo Max", variant="Maxx (PV)",
                    createdDate="2026-11-18",
                    lastUpdated=["2026-11-18T09:00:00+00:00", "2026-11-18T09:00:30+00:00", "2026-11-18T09:01:00+00:00"][i])
    dry = await client.post("/api/leads/repair-retry-duplicates")
    assert dry.status_code == 200, dry.text
    assert dry.json()["dryRun"] is True
    assert any(c.get("action") == "delete-retry" for c in dry.json()["clusters"])
    assert await server.db.leads.count_documents({"mobile": mobile}) == 3
    live = await client.post("/api/leads/repair-retry-duplicates", params={"dryRun": "false"})
    assert live.status_code == 200, live.text
    left = [l["leadId"] async for l in server.db.leads.find({"mobile": mobile})]
    assert left == ["LD26CLD01E"]
    archived = await server.db.leads_purged_archive.count_documents({"keptLeadId": "LD26CLD01E"})
    assert archived == 2
    audit = await server.db.audit_log.count_documents({"action": "purge-duplicate", "leadId": "LD26CLD01F"})
    assert audit == 1


@pytest.mark.asyncio
async def test_non_owner_cannot_purge(client):
    tok = (await client.post("/api/auth/login", json={"email": "executive@euler.com", "password": "euler@123"})).json()["token"]
    r = await client.post("/api/leads/repair-retry-duplicates", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
