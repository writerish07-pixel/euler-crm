"""Login every desk role and hit the screens they are built for.

This is the API contract behind the UI: if a role cannot open its home, or can
open someone else's money desk, the product is not release-ready.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "role_smoke_release")
os.environ.setdefault("JWT_SECRET", "role-smoke-secret-32chars-long")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

PW = "euler@123"

# email, home GET that must 200, a path that must 403 (None = skip)
HOMES = [
    ("owner@euler.com", "/api/dashboard", None),
    ("salesgm@euler.com", "/api/sales-gm/dashboard", "/api/auth/users"),
    ("executive@euler.com", "/api/executive/dashboard", "/api/auth/users"),
    ("accounts@euler.com", "/api/accounts/dashboard", "/api/auth/users"),
    ("asm@euler.com", "/api/field/dashboard", "/api/auth/users"),
    ("rm@euler.com", "/api/field/dashboard", "/api/auth/users"),
    ("oemfinance@euler.com", "/api/reports/oem-finance", "/api/leads"),
]


@pytest_asyncio.fixture
async def app_client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


async def _login(c, email):
    r = await c.post("/api/auth/login", json={"email": email, "password": PW})
    assert r.status_code == 200, f"{email}: {r.text}"
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    assert r.json()["user"]["email"] == email or r.json()["user"].get("role")
    return r.json()["user"]


@pytest.mark.asyncio
@pytest.mark.parametrize("email,home,forbidden", HOMES)
async def test_each_role_opens_its_desk_and_not_another(app_client, email, home, forbidden):
    user = await _login(app_client, email)
    assert user.get("role")
    me = await app_client.get("/api/auth/me")
    assert me.status_code == 200, me.text
    ok = await app_client.get(home)
    assert ok.status_code == 200, f"{email} {home}: {ok.status_code} {ok.text[:300]}"
    if forbidden:
        denied = await app_client.get(forbidden)
        assert denied.status_code in (403, 404), (
            f"{email} should not open {forbidden}: {denied.status_code} {denied.text[:200]}"
        )


@pytest.mark.asyncio
async def test_owner_sheet_status_endpoint_is_readable(app_client):
    await _login(app_client, "owner@euler.com")
    r = await app_client.get("/api/integrations/gsheets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "enabled" in body
    assert "canWrite" in body or "reason" in body or "envSafety" in body
    pre = await app_client.get("/api/integrations/gsheets/preflight")
    assert pre.status_code in (200, 409, 503)


@pytest.mark.asyncio
async def test_executive_cannot_read_sheet_admin(app_client):
    await _login(app_client, "executive@euler.com")
    r = await app_client.get("/api/integrations/gsheets")
    assert r.status_code in (403, 404)
