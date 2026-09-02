"""Owner User Accounts: optional email, visible password, staff change updates it."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "user_account_password_v1")
os.environ.setdefault("JWT_SECRET", "user-account-password-secret-32")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

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


def _row(users, login_id):
    return next(u for u in users if u.get("loginId") == login_id)


@pytest.mark.asyncio
async def test_create_user_without_email_shows_password(client):
    r = await client.post("/api/auth/users", json={
        "name": "Harish Bhatnagar", "loginId": "harish.b", "password": "desk#441",
        "role": "executive",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == ""
    assert body["loginId"] == "harish.b"
    assert body["password"] == "desk#441"

    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "harish.b")
    assert row["email"] == ""
    assert row["password"] == "desk#441"

    login = await client.post("/api/auth/login", json={"email": "harish.b", "password": "desk#441"})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["name"] == "Harish Bhatnagar"
    assert "password" not in login.json()["user"]
    assert "passwordPlain" not in login.json()["user"]


@pytest.mark.asyncio
async def test_blank_email_and_blank_user_id_rejected(client):
    r = await client.post("/api/auth/users", json={
        "name": "No Handle", "password": "desk#441", "role": "executive",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_staff_me_never_includes_password(client):
    await client.post("/api/auth/users", json={
        "name": "Devang", "loginId": "devang.p", "password": "firstPass1",
        "role": "executive",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "devang.p", "password": "firstPass1"})).json()["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert "passwordPlain" not in me.json()
    assert me.json().get("password") in (None, "")


@pytest.mark.asyncio
async def test_staff_change_password_updates_owner_list(client):
    await client.post("/api/auth/users", json={
        "name": "Shelendra", "loginId": "s.mathur", "password": "oldPass1",
        "role": "tl",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "s.mathur", "password": "oldPass1"})).json()["token"]
    r = await client.post("/api/auth/change-password",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"currentPassword": "oldPass1", "newPassword": "newPass9"})
    assert r.status_code == 200, r.text

    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "s.mathur")
    assert row["password"] == "newPass9"

    ok = await client.post("/api/auth/login", json={"email": "s.mathur", "password": "newPass9"})
    assert ok.status_code == 200
    bad = await client.post("/api/auth/login", json={"email": "s.mathur", "password": "oldPass1"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_staff_cannot_list_user_passwords(client):
    await client.post("/api/auth/users", json={
        "name": "Peek", "loginId": "peek.user", "password": "secret99",
        "role": "executive",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "peek.user", "password": "secret99"})).json()["token"]
    r = await client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403
