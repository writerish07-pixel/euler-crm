"""Go-live fresh start: reset clears every transactional collection and sheet mirrors."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "fresh_start_reset")
os.environ.setdefault("JWT_SECRET", "fresh-start-secret")
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import gsheets  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client(monkeypatch):
    await server.startup()
    monkeypatch.setattr(gsheets, "clear_operational_register_rows",
                        lambda: _ok_sheet())
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _ok_sheet():
    return {"ok": True, "tabs": ["Lead Register"], "clearedRanges": ["'Lead Register'!A2:ZZ"]}


@pytest.mark.asyncio
async def test_reset_clears_incentive_register_and_resets_lead_counter(client):
    # Leftover incentive rows (the gap the old reset left behind), on top of any seed.
    await server.db.incentive_register.insert_many([
        {"incentiveId": "INC1", "leadId": "LD26000099"},
        {"incentiveId": "INC2", "leadId": "LD26000098"},
    ])
    await server.db.counters.update_one({"_id": "lead"}, {"$set": {"seq": 99}}, upsert=True)
    before_incentives = await server.db.incentive_register.count_documents({})
    assert before_incentives >= 2

    r = await client.post("/api/admin/reset-transactions")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["cleared"]["incentive_register"] == before_incentives
    assert body["cleared"]["leads"] >= 1
    assert body["nextLeadId"] == "LD26000001"
    assert body["sheetClear"]["ok"] is True

    assert await server.db.incentive_register.count_documents({}) == 0
    assert await server.db.leads.count_documents({}) == 0
    ctr = await server.db.counters.find_one({"_id": "lead"})
    assert ctr["seq"] == 0
    seed = await server.db["system"].find_one({"_id": "seed_state"})
    assert seed["sampleCleared"] is True

    # Next created lead must be lead 1 in product numbering.
    created = await client.post("/api/leads", json={
        "customerName": "Fresh Start One", "mobile": "9000011111",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit",
        "leadSource": "Walk-in"})
    assert created.status_code == 200, created.text
    assert created.json()["leadId"] == "LD26000001"


def test_operational_clear_tabs_exclude_masters():
    masters = {"PRICE MASTER", "Scheme Master", "Incentive Master", "Masters", "Settings"}
    assert masters.isdisjoint(gsheets.OPERATIONAL_CLEAR_TABS)
    assert "Lead Register" in gsheets.OPERATIONAL_CLEAR_TABS
    assert "Dealer Earnings Register" in gsheets.OPERATIONAL_CLEAR_TABS
    assert "Incentive Register" in gsheets.OPERATIONAL_CLEAR_TABS
