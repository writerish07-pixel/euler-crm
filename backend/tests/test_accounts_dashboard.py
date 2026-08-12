"""Accounts role: money-desk login, dashboard KPIs, sales-edit blocked."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "accounts_dashboard_tests")
os.environ.setdefault("JWT_SECRET", "accounts-dashboard-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    for email, pw in (
        ("owner@euler.com", "euler@123"),
        ("executive@euler.com", "euler@123"),
        ("accounts@euler.com", "euler@123"),
    ):
        await server.db.users.update_one(
            {"email": email},
            {"$set": {"passwordHash": authmod.hash_password(pw)}},
            upsert=False,
        )
    # Ensure accounts user exists even if seed ran before role was added.
    if not await server.db.users.find_one({"email": "accounts@euler.com"}):
        await server.db.users.insert_one({
            "userId": "acct-test-1",
            "email": "accounts@euler.com",
            "passwordHash": authmod.hash_password("euler@123"),
            "name": "Accounts",
            "role": "accounts",
            "createdAt": "2026-01-01T00:00:00+00:00",
        })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(c, email, password="euler@123"):
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    data = r.json()
    c.headers.update({"Authorization": f"Bearer {data['token']}"})
    return data


@pytest.mark.asyncio
async def test_accounts_login_and_me(client):
    data = await _login(client, "accounts@euler.com")
    assert data["user"]["role"] == "accounts"
    me = await client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "accounts"


@pytest.mark.asyncio
async def test_accounts_dashboard_ok(client):
    await _login(client, "accounts@euler.com")
    r = await client.get("/api/accounts/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kpis" in body
    assert "tallyQueue" in body
    assert "doNotPost" in body
    k = body["kpis"]
    for key in (
        "customerOutstanding", "financeOutstanding", "oemClaimsOpen",
        "insurancePayoutDue", "deliveredForTally",
    ):
        assert key in k


@pytest.mark.asyncio
async def test_owner_can_open_accounts_dashboard(client):
    await _login(client, "owner@euler.com")
    r = await client.get("/api/accounts/dashboard")
    assert r.status_code == 200


@pytest.mark.asyncio
async def test_accounts_blocked_from_create_lead(client):
    await _login(client, "accounts@euler.com")
    r = await client.post("/api/leads", json={
        "customerName": "Acct Blocked",
        "mobile": "9898989898",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "priority": "Warm",
        "executive": "Test",
    })
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_accounts_blocked_from_scheme(client):
    await _login(client, "owner@euler.com")
    create = await client.post("/api/leads", json={
        "customerName": "Scheme Gate",
        "mobile": "9777777777",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "priority": "Warm",
        "executive": "Test",
    })
    assert create.status_code == 200, create.text
    lead_id = create.json()["leadId"]

    await _login(client, "accounts@euler.com")
    r = await client.put(f"/api/leads/{lead_id}/scheme", json={
        "schemeName": "X", "schemeAmount": 1000, "schemeUse": "Yes",
    })
    assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_accounts_can_list_payments_and_claims(client):
    await _login(client, "accounts@euler.com")
    pay = await client.get("/api/payments")
    assert pay.status_code == 200, pay.text
    claims = await client.get("/api/claims")
    assert claims.status_code == 200, claims.text
    fin = await client.get("/api/finance")
    assert fin.status_code == 200, fin.text


@pytest.mark.asyncio
async def test_owner_can_create_accounts_user(client):
    await _login(client, "owner@euler.com")
    email = "accounts2@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "euler@123", "name": "Accounts Two", "role": "accounts",
    })
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "accounts"
