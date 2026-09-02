"""Railway deploy health: startup must bind PORT before sheet/OEM backfills.

Production used to await Close-Won / cancel / booking-advance / finance-repair
backfills (each recompute_lead writes Google Sheets) inside FastAPI startup().
The process does not listen until that returns, so Railway healthchecks 502 and
kill the replica — RAM spikes then drops, several crashes, 5+ minute 'start'.
"""
import asyncio
import os
import sys
import time

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "boot_health_tests")
os.environ.setdefault("JWT_SECRET", "boot-health-secret-32chars-ok!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

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
        yield c


@pytest.mark.asyncio
async def test_health_is_public_and_ok(client):
    for path in ("/health", "/"):
        r = await client.get(path)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "up"


@pytest.mark.asyncio
async def test_health_does_not_need_a_token(client):
    r = await client.get("/health")
    assert r.status_code == 200
    r2 = await client.get("/api/leads")
    assert r2.status_code == 401


@pytest.mark.asyncio
async def test_production_startup_returns_before_maintenance_finishes(monkeypatch):
    """The whole point: Railway can healthcheck while sheet backfills still run."""
    monkeypatch.setenv("ENVIRONMENT", "production")
    started = asyncio.Event()
    finished = asyncio.Event()

    async def slow_maintenance():
        started.set()
        await asyncio.sleep(30)
        finished.set()

    monkeypatch.setattr(server, "_run_boot_maintenance", slow_maintenance)
    server._boot_maintenance_task = None
    t0 = time.monotonic()
    await server.startup()
    elapsed = time.monotonic() - t0
    assert elapsed < 8, f"startup still blocked on maintenance ({elapsed:.1f}s)"
    await asyncio.wait_for(started.wait(), timeout=2)
    assert not finished.is_set()
    task = server._boot_maintenance_task
    assert task is not None and not task.done()
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass


def test_boot_maintenance_is_scheduled_not_inlined_in_production_source():
    import inspect
    src = inspect.getsource(server.startup)
    assert "_schedule_boot_maintenance()" in src
    assert "await _backfill_close_won_status()" not in src
    maint = inspect.getsource(server._run_boot_maintenance)
    assert "await _backfill_close_won_status()" in maint
    assert "await _oem_catalog_boot()" in maint
