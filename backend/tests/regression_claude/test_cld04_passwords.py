"""CLD-04: passwords are hashed. The owner list does not return them."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld04_passwords")
os.environ.setdefault("JWT_SECRET", "cld04-password-secret-32chars")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("SEED_DEMO_USERS", "1")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
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


@pytest.mark.asyncio
async def test_create_reset_and_change_store_no_plaintext(client):
    created = await client.post("/api/auth/users", json={
        "name": "No Plain", "loginId": "no.plain", "password": "firstPass1", "role": "executive",
    })
    assert created.status_code == 200, created.text
    uid = created.json()["userId"]
    stored = await server.db.users.find_one({"userId": uid})
    assert "passwordPlain" not in stored
    reset = await client.put(f"/api/auth/users/{uid}/password", json={"password": "resetPass1"})
    assert reset.json().get("password") == "resetPass1"
    stored = await server.db.users.find_one({"userId": uid})
    assert not stored.get("passwordPlain")
    tok = (await client.post("/api/auth/login", json={"email": "no.plain", "password": "resetPass1"})).json()["token"]
    changed = await client.post("/api/auth/change-password", headers={"Authorization": f"Bearer {tok}"},
                                json={"currentPassword": "resetPass1", "newPassword": "changedPass1"})
    assert changed.status_code == 200, changed.text
    stored = await server.db.users.find_one({"userId": uid})
    assert not stored.get("passwordPlain")
    listed = await client.get("/api/auth/users")
    assert "password" not in next(u for u in listed.json() if u["userId"] == uid)


@pytest.mark.asyncio
async def test_legacy_plaintext_logs_in_once_then_is_hashed(client):
    await server.db.users.insert_one({
        "userId": "legacy-1", "email": "legacy@euler.com", "loginId": "legacy",
        "loginIdNorm": "legacy", "name": "Legacy", "role": "executive",
        "passwordPlain": "legacyPass1",
    })
    ok = await client.post("/api/auth/login", json={"email": "legacy", "password": "legacyPass1"})
    assert ok.status_code == 200, ok.text
    stored = await server.db.users.find_one({"userId": "legacy-1"})
    assert stored.get("passwordHash")
    assert not stored.get("passwordPlain")
    bad = await client.post("/api/auth/login", json={"email": "legacy", "password": "wrong-pass"})
    assert bad.status_code == 401
    assert authmod.verify_password("legacyPass1", stored["passwordHash"])
