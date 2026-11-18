"""CLD-13: Sales GM does not post customer or Finance receipts."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld13_gm")
os.environ.setdefault("JWT_SECRET", "cld13-sales-gm-secret-32chars")
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
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _as(email):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        return c, r


@pytest.mark.asyncio
async def test_sales_gm_cannot_post_cash_or_finance(client):
    created = await client.post("/api/leads", json={
        "customerName": "GM Block", "mobile": "9812300013",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "leadSource": "Walk-in",
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    transport = httpx.ASGITransport(app=server.app)
    import auth as authmod
    await server.db.users.update_one(
        {"email": "salesgm@euler.com"},
        {"$set": {"email": "salesgm@euler.com", "loginId": "salesgm", "loginIdNorm": "salesgm",
                  "name": "Sales GM", "role": "sales_gm", "userId": "salesgm-cld13",
                  "passwordHash": authmod.hash_password("euler@123")}},
        upsert=True)
    login = await client.post("/api/auth/login", json={"email": "salesgm@euler.com", "password": "euler@123"})
    assert login.status_code == 200, login.text
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["Authorization"] = f"Bearer {login.json()['token']}"
        cash = await c.post(f"/api/leads/{lid}/payments", json={"amount": 1000, "paymentMode": "Cash"})
        finance = await c.post(f"/api/leads/{lid}/payments", json={"amount": 1000, "paymentMode": "Finance"})
        unknown = await c.post("/api/leads/x/payments", json={"amount": 1000, "paymentMode": "Cash"})
    assert cash.status_code == 403
    assert finance.status_code == 403
    assert unknown.status_code == 403


@pytest.mark.asyncio
async def test_accounts_can_still_post(client):
    created = await client.post("/api/leads", json={
        "customerName": "Acct Ok", "mobile": "9812300014",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "leadSource": "Walk-in",
    })
    lid = created.json()["leadId"]
    import auth as authmod
    await server.db.users.update_one(
        {"email": "accounts@euler.com"},
        {"$set": {"email": "accounts@euler.com", "loginId": "accounts", "loginIdNorm": "accounts",
                  "name": "Accounts", "role": "accounts", "userId": "accounts-cld13",
                  "passwordHash": authmod.hash_password("euler@123")}},
        upsert=True)
    login = await client.post("/api/auth/login", json={"email": "accounts@euler.com", "password": "euler@123"})
    assert login.status_code == 200, login.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers["Authorization"] = f"Bearer {login.json()['token']}"
        pay = await c.post(f"/api/leads/{lid}/payments", json={"amount": 500, "paymentMode": "Cash", "date": "2026-11-18"})
    assert pay.status_code == 200, pay.text
