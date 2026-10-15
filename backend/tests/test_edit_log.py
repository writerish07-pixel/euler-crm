"""Edit Log Register — desk edits by GM, Showroom Admin, TL, Executive."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "edit_log_register_v1")
os.environ.setdefault("JWT_SECRET", "edit-log-register-secret-32ch")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _login(email, password=PW):
    transport = httpx.ASGITransport(app=server.app)
    c = httpx.AsyncClient(transport=transport, base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return c


def test_edit_field_summary_shows_old_to_new():
    text = server._edit_field_summary(
        {"city": "", "customerName": "Ram"},
        {"city": "Jaipur", "lastUpdated": "x"},
        action="update", module="lead",
    )
    assert "City" in text
    assert "Jaipur" in text
    assert "lastUpdated" not in text


@pytest.mark.asyncio
async def test_accounts_cannot_open_edit_log(client):
    acc = await _login("accounts@euler.com")
    try:
        assert (await acc.get("/api/edit-log")).status_code == 403
    finally:
        await acc.aclose()


@pytest.mark.asyncio
async def test_gm_and_tl_edits_appear_executive_sees_own_activity(client):
    await server.db.users.delete_many({"email": {"$in": [
        "edit.tl@euler.com", "edit.exec@euler.com", "edit.sa@euler.com"]}})
    await server.db.staff.delete_many({"name": {"$in": ["Edit TL", "Edit Exec"]}})
    assert (await client.post("/api/staff", json={"name": "Edit TL", "role": "team_lead"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Edit Exec", "role": "executive", "reportsTo": "Edit TL"})).status_code in (200, 201)
    assert (await client.post("/api/auth/users", json={
        "email": "edit.tl@euler.com", "password": PW, "name": "Edit TL",
        "role": "team_lead"})).status_code in (200, 201)
    assert (await client.post("/api/auth/users", json={
        "email": "edit.exec@euler.com", "password": PW, "name": "Edit Exec",
        "role": "executive"})).status_code in (200, 201)
    assert (await client.post("/api/auth/users", json={
        "email": "edit.sa@euler.com", "password": PW, "name": "Edit SA",
        "role": "tl"})).status_code in (200, 201)

    made = await client.post("/api/leads", json={
        "customerName": "Edit Cust", "mobile": "9822200091",
        "executive": "Edit Exec", "interestedModel": "Turbo Max",
        "city": "Kota"})
    assert made.status_code == 200, made.text
    lid = made.json()["leadId"]

    tl = await _login("edit.tl@euler.com")
    gm = await _login("salesgm@euler.com")
    sa = await _login("edit.sa@euler.com")
    ex = await _login("edit.exec@euler.com")
    try:
        tl_edit = await tl.put(f"/api/leads/{lid}", json={"city": "Jaipur"})
        assert tl_edit.status_code == 200, tl_edit.text
        gm_edit = await gm.put(f"/api/leads/{lid}", json={"remarks": "GM note"})
        assert gm_edit.status_code == 200, gm_edit.text
        sa_edit = await sa.put(f"/api/leads/{lid}", json={"village": "Sanganer"})
        assert sa_edit.status_code == 200, sa_edit.text
        blocked = await ex.put(f"/api/leads/{lid}", json={"city": "Ajmer"})
        assert blocked.status_code == 403
        logged = await ex.post(f"/api/leads/{lid}/activities", json={
            "activityType": "Call", "discussion": "Followed up",
            "nextFollowup": "2026-10-20"})
        assert logged.status_code == 200, logged.text

        owner_rows = (await client.get("/api/edit-log")).json()
        summaries = " | ".join(r.get("summary") or "" for r in owner_rows)
        assert any(r["leadId"] == lid and r["role"] == "team_lead" for r in owner_rows)
        assert any(r["leadId"] == lid and r["role"] == "sales_gm" for r in owner_rows)
        assert any(r["leadId"] == lid and r["role"] == "tl" for r in owner_rows)
        assert any(r["leadId"] == lid and r["role"] == "executive" and r["module"] == "activity"
                   for r in owner_rows)
        assert "Jaipur" in summaries
        assert "GM note" in summaries
        assert "Sanganer" in summaries

        tl_rows = (await tl.get("/api/edit-log")).json()
        assert any(r["leadId"] == lid for r in tl_rows)

        gm_rows = (await gm.get("/api/edit-log")).json()
        assert any(r["leadId"] == lid and r["role"] == "team_lead" for r in gm_rows)

        sa_rows = (await sa.get("/api/edit-log")).json()
        assert any(r["leadId"] == lid and r["role"] == "team_lead" for r in sa_rows)
        assert any(r["leadId"] == lid and r["role"] == "sales_gm" for r in sa_rows)

        ex_rows = (await ex.get("/api/edit-log")).json()
        assert all(r["role"] == "executive" for r in ex_rows)
        assert any(r["leadId"] == lid and "Followed up" in (r.get("summary") or "") for r in ex_rows)
        live = (await ex.get(f"/api/leads/{lid}")).json()
        assert str(live.get("nextFollowupDate") or "")[:10] == "2026-10-20"
    finally:
        await tl.aclose()
        await gm.aclose()
        await sa.aclose()
        await ex.aclose()
