"""CLD-03: demo accounts are created only when SEED_DEMO_USERS is on."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld03_seed")
os.environ.setdefault("JWT_SECRET", "cld03-seed-secret-32-characters")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import auth as authmod  # noqa: E402
import server  # noqa: E402


@pytest.mark.asyncio
async def test_demos_are_not_created_unless_asked(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_USERS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("OWNER_PASSWORD", "owner-set-once")
    await server.db.users.delete_many({})
    await authmod.seed_users(server.db)
    emails = [u["email"] async for u in server.db.users.find({})]
    assert emails == ["owner@euler.com"]
    assert not any(e.startswith("accounts@") for e in emails)


@pytest.mark.asyncio
async def test_demos_are_created_when_flag_is_on(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERS", "1")
    monkeypatch.setenv("ENVIRONMENT", "production")
    await server.db.users.delete_many({})
    await authmod.seed_users(server.db)
    row = await server.db.users.find_one({"email": "accounts@euler.com"})
    assert row
    assert "passwordPlain" not in row


@pytest.mark.asyncio
async def test_existing_users_are_not_rewritten(monkeypatch):
    monkeypatch.delenv("SEED_DEMO_USERS", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    await server.db.users.delete_many({})
    await server.db.users.insert_one({
        "userId": "keep", "email": "accounts@euler.com", "role": "accounts",
        "passwordHash": authmod.hash_password("custom-pass"), "name": "Kept",
    })
    await authmod.seed_users(server.db)
    row = await server.db.users.find_one({"email": "accounts@euler.com"})
    assert row["name"] == "Kept"
    assert authmod.verify_password("custom-pass", row["passwordHash"])


@pytest.mark.asyncio
async def test_using_default_password_flag(monkeypatch):
    monkeypatch.setenv("SEED_DEMO_USERS", "1")
    monkeypatch.setenv("ENVIRONMENT", "test")
    await server.startup()
    transport_mod = __import__("httpx")
    transport = transport_mod.ASGITransport(app=server.app)
    async with transport_mod.AsyncClient(transport=transport, base_url="http://test") as c:
        login = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert login.status_code == 200, login.text
        c.headers["Authorization"] = f"Bearer {login.json()['token']}"
        listed = await c.get("/api/auth/users")
    row = next(u for u in listed.json() if u["email"] == "executive@euler.com")
    assert row["usingDefaultPassword"] is True
    assert "password" not in row
