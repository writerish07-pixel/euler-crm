"""Google Sheet live writes: Scheme Claim Register only, never on the click."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "claims_only_sheet_tests")
os.environ.setdefault("JWT_SECRET", "claims-only-sheet-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import gsheets  # noqa: E402
import server  # noqa: E402


PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.claims.delete_many({})
    await server.db.sheet_sync_log.delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_lives_on_sheet_is_claims_only():
    assert gsheets.lives_on_sheet("claims") is True
    assert gsheets.lives_on_sheet("leads") is False
    assert gsheets.lives_on_sheet("payments") is False
    assert gsheets.LIVE_SHEET_ENTITIES == {"claims"}


@pytest.mark.real_sheet_sync
@pytest.mark.asyncio
async def test_leads_are_not_written_to_google(client, monkeypatch):
    calls = []

    async def boom(entity, doc):
        calls.append(entity)
        raise AssertionError(f"must not write {entity} to Google")

    monkeypatch.setattr(server.gsheets, "sync", boom)
    res = await server.sheet_sync("leads", {"leadId": "LD1", "customerName": "Asha"})
    assert res["operation"] == "skipped"
    assert res["reason"] == "claims-only"
    assert calls == []
    assert await server.db.sheet_sync_log.count_documents({}) == 0


@pytest.mark.real_sheet_sync
@pytest.mark.asyncio
async def test_claims_queue_and_do_not_await_google(client, monkeypatch):
    google = []

    async def capture(entity, doc):
        google.append(entity)
        return {"ok": True, "operation": "updated", "tab": "Scheme Claim Register"}

    scheduled = []

    def capture_sched(docs, entity="leads"):
        scheduled.append((entity, len(docs)))

    monkeypatch.setattr(server.gsheets, "sync", capture)
    monkeypatch.setattr(server, "_schedule_sheet_syncs", capture_sched)
    res = await server.sheet_sync("claims", {
        "claimId": "CLM-1", "leadId": "LD1",
        "componentKey": "loyaltyBonus", "claimAmount": 10000,
    })
    assert res["operation"] == "queued"
    assert google == []
    assert scheduled == [("claims", 1)]
    pending = await server.db.sheet_sync_log.find_one(
        {"entityType": "claims", "entityId": "CLM-1"})
    assert pending["status"] == "PENDING"


@pytest.mark.real_sheet_sync
@pytest.mark.asyncio
async def test_claim_flush_writes_google(client, monkeypatch):
    google = []

    async def capture(entity, doc):
        google.append({"entity": entity, "claimId": doc.get("claimId")})
        return {"ok": True, "operation": "updated", "tab": "Scheme Claim Register"}

    monkeypatch.setattr(server.gsheets, "sync", capture)
    res = await server.sheet_sync(
        "claims", {"claimId": "CLM-2", "leadId": "LD1", "claimAmount": 5000}, flush=True)
    assert res["ok"] is True
    assert google == [{"entity": "claims", "claimId": "CLM-2"}]
    log = await server.db.sheet_sync_log.find_one({"entityType": "claims", "entityId": "CLM-2"})
    assert log["status"] == "OK"


@pytest.mark.real_sheet_sync
@pytest.mark.asyncio
async def test_queue_ignores_lead_rows(client):
    await server.queue_sheet_sync("leads", {"leadId": "LD9"}, entity_id="LD9")
    assert await server.db.sheet_sync_log.count_documents({}) == 0


@pytest.mark.real_sheet_sync
@pytest.mark.asyncio
async def test_retry_skips_stale_lead_pending(client, monkeypatch):
    await server.db.sheet_sync_log.insert_one({
        "entityType": "leads", "entityId": "LD-OLD", "status": "PENDING",
        "payload": {"leadId": "LD-OLD"}, "attempt": 1,
    })
    google = []

    async def capture(entity, doc):
        google.append(entity)
        return {"ok": True, "operation": "updated"}

    monkeypatch.setattr(server.gsheets, "sync", capture)
    r = await client.post("/api/integrations/gsheets/retry")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["skipped"] >= 1
    assert google == []
    row = await server.db.sheet_sync_log.find_one({"entityType": "leads", "entityId": "LD-OLD"})
    assert row["status"] == "SKIPPED"
