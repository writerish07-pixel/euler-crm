"""Change password for owner and executive (own account only)."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "change_password_tests")
os.environ.setdefault("JWT_SECRET", "change-password-secret-32chars!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402


DEMO_ACCOUNTS = (("owner@euler.com", "euler@123"), ("executive@euler.com", "euler@123"))


async def _restore_demo_passwords():
    for email, pw in DEMO_ACCOUNTS:
        await server.db.users.update_one(
            {"email": email},
            {"$set": {"passwordHash": authmod.hash_password(pw)}},
        )


@pytest_asyncio.fixture
async def client():
    await server.startup()
    # Reset both demo accounts to known passwords so tests are order-independent.
    await _restore_demo_passwords()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
    # ...and restore them on the way out.
    #
    # server.py binds `db = client[os.environ["DB_NAME"]]` at import time, and every
    # test module sets DB_NAME with os.environ.setdefault — so only the first module
    # imported wins and ALL test files share one mongomock database. This file is the
    # only one that rotates a demo password; without this teardown it leaves
    # owner@euler.com on "ownerNew1", and every later module whose fixture logs in
    # with the default password gets no token and errors with KeyError: 'token'.
    await _restore_demo_passwords()


async def _login(c, email, password="euler@123"):
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return r.json()


@pytest.mark.asyncio
async def test_owner_can_change_password(client):
    await _login(client, "owner@euler.com")
    r = await client.post("/api/auth/change-password", json={
        "currentPassword": "euler@123", "newPassword": "ownerNew1",
    })
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True

    bad = await client.post("/api/auth/login",
                            json={"email": "owner@euler.com", "password": "euler@123"})
    assert bad.status_code == 401

    ok = await client.post("/api/auth/login",
                           json={"email": "owner@euler.com", "password": "ownerNew1"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_executive_can_change_password(client):
    await _login(client, "executive@euler.com")
    r = await client.post("/api/auth/change-password", json={
        "currentPassword": "euler@123", "newPassword": "execNew99",
    })
    assert r.status_code == 200, r.text

    ok = await client.post("/api/auth/login",
                           json={"email": "executive@euler.com", "password": "execNew99"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_wrong_current_password_rejected(client):
    await _login(client, "executive@euler.com")
    r = await client.post("/api/auth/change-password", json={
        "currentPassword": "wrong", "newPassword": "another1",
    })
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_short_password_rejected(client):
    await _login(client, "owner@euler.com")
    r = await client.post("/api/auth/change-password", json={
        "currentPassword": "euler@123", "newPassword": "ab",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_seed_does_not_reset_changed_owner_password(client):
    """Regression: startup used to force owner back to OWNER_PASSWORD."""
    await _login(client, "owner@euler.com")
    r = await client.post("/api/auth/change-password", json={
        "currentPassword": "euler@123", "newPassword": "ownerKept9",
    })
    assert r.status_code == 200, r.text
    await authmod.seed_users(server.db)
    still = await client.post("/api/auth/login",
                              json={"email": "owner@euler.com", "password": "ownerKept9"})
    assert still.status_code == 200, still.text
    old = await client.post("/api/auth/login",
                            json={"email": "owner@euler.com", "password": "euler@123"})
    assert old.status_code == 401
