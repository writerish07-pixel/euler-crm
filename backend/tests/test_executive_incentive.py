"""Owner-set executive incentive ladder (not company Incentive Master)."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "exec_incentive_tests")
os.environ.setdefault("JWT_SECRET", "exec-incentive-secret-32chars!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

PLAN = {
    "minUnits": 5,
    "levels": [
        {"fromUnits": 5, "toUnits": 9, "amount": 500},
        {"fromUnits": 10, "toUnits": 14, "amount": 800},
        {"fromUnits": 15, "toUnits": None, "amount": 1200},
    ],
}


def test_slab_below_min_is_zero():
    r = ce.evaluate_executive_incentive(4, PLAN)
    assert r["total"] == 0
    assert r["started"] is False
    assert r["next"]["fromUnits"] == 5


def test_slab_uses_all_units_at_highest_level():
    assert ce.evaluate_executive_incentive(7, PLAN)["total"] == 3500
    assert ce.evaluate_executive_incentive(12, PLAN)["total"] == 9600
    assert ce.evaluate_executive_incentive(20, PLAN)["total"] == 24000


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.executive_incentive.delete_many({})
    await server.db.leads.delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _as(email):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest.mark.asyncio
async def test_company_incentive_master_is_owner_only(client):
    assert (await client.get("/api/incentive-master")).status_code == 200
    async for exec_c in _as("executive@euler.com"):
        assert (await exec_c.get("/api/incentive-master")).status_code == 403
        assert (await exec_c.get("/api/incentive-register")).status_code == 403
        assert (await exec_c.put("/api/executive-incentive/plan", json=PLAN)).status_code == 403
        assert (await exec_c.get("/api/integrations/gsheets")).status_code == 403


@pytest.mark.asyncio
async def test_owner_saves_plan_and_executive_dashboard_uses_it(client):
    r = await client.put("/api/executive-incentive/plan", json=PLAN)
    assert r.status_code == 200, r.text
    assert r.json()["minUnits"] == 5
    ym = server.this_month()
    for i in range(7):
        await server.db.leads.insert_one({
            "leadId": f"LD-INC-{i}",
            "customerName": f"Cust {i}",
            "executive": "Executive",
            "currentStatus": "Delivered",
            "accountStatus": "Active",
            "deliveryDate": f"{ym}-0{i + 1}" if i < 9 else f"{ym}-10",
            "createdDate": f"{ym}-01",
        })
    async for exec_c in _as("executive@euler.com"):
        dash = await exec_c.get("/api/executive/dashboard")
        assert dash.status_code == 200, dash.text
        inc = dash.json()["incentive"]
        assert inc["units"] == 7
        assert inc["total"] == 3500
        plan = (await exec_c.get("/api/executive-incentive/plan")).json()
        assert plan["minUnits"] == 5
    board = (await client.get("/api/executive-incentive/board")).json()
    row = next(x for x in board["executives"] if x["executive"] == "Executive")
    assert row["total"] == 3500


@pytest.mark.asyncio
async def test_overlapping_levels_rejected(client):
    r = await client.put("/api/executive-incentive/plan", json={
        "minUnits": 1,
        "levels": [
            {"fromUnits": 1, "toUnits": 10, "amount": 100},
            {"fromUnits": 8, "toUnits": 20, "amount": 200},
        ],
    })
    assert r.status_code == 422
