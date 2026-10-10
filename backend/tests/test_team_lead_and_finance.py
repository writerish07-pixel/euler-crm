"""Team-scoped Team Leader + executive Finance receipts."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "team_lead_v1")
os.environ.setdefault("JWT_SECRET", "team-lead-secret-32ch!!xx")
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


async def _login(email, password):
    transport = httpx.ASGITransport(app=server.app)
    c = httpx.AsyncClient(transport=transport, base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return c


@pytest.mark.asyncio
async def test_team_lead_sees_only_own_team(client):
    await server.db.users.delete_many({"email": {"$in": ["tl.amit@euler.com", "ex.ravi@euler.com", "ex.neha@euler.com"]}})
    await server.db.staff.delete_many({"name": {"$in": ["Amit TL", "Ravi Exec", "Neha Exec"]}})
    await client.post("/api/staff", json={"name": "Amit TL", "role": "team_lead"})
    await client.post("/api/staff", json={"name": "Ravi Exec", "role": "executive", "reportsTo": "Amit TL"})
    await client.post("/api/staff", json={"name": "Neha Exec", "role": "executive", "reportsTo": ""})
    await client.post("/api/auth/users", json={
        "email": "tl.amit@euler.com", "password": PW, "name": "Amit TL", "role": "team_lead"})
    await client.post("/api/auth/users", json={
        "email": "ex.ravi@euler.com", "password": PW, "name": "Ravi Exec", "role": "executive"})
    mine = await client.post("/api/leads", json={
        "customerName": "Team Cust", "mobile": "9811100001", "executive": "Ravi Exec",
        "interestedModel": "Turbo Max", "createdDate": "2026-10-10"})
    other = await client.post("/api/leads", json={
        "customerName": "Other Cust", "mobile": "9811100002", "executive": "Neha Exec",
        "interestedModel": "Storm", "createdDate": "2026-10-10"})
    assert mine.status_code == 200 and other.status_code == 200
    tl = await _login("tl.amit@euler.com", PW)
    try:
        rows = (await tl.get("/api/leads")).json()
        names = {r["customerName"] for r in rows}
        assert "Team Cust" in names
        assert "Other Cust" not in names
        assert (await tl.get(f"/api/leads/{other.json()['leadId']}")).status_code == 403
        dash = (await tl.get("/api/executive/dashboard")).json()
        assert dash["scope"]["teamView"] is True
        assert "team" in dash["scope"]["note"].lower()
        blocked = await tl.get("/api/scheme-master")
        assert blocked.status_code == 403
        assert (await tl.post("/api/staff", json={"name": "Nope", "role": "executive"})).status_code == 403
        assert (await tl.post("/api/inventory/check", json={"items": [
            {"chassis": "X", "status": "present"}]})).status_code == 403
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_executive_can_post_finance_receipt(client):
    await server.db.users.delete_many({"email": "ex.pay@euler.com"})
    await client.post("/api/auth/users", json={
        "email": "ex.pay@euler.com", "password": PW, "name": "Payal Exec", "role": "executive"})
    created = await client.post("/api/leads", json={
        "customerName": "Finance Cust", "mobile": "9811100003", "executive": "Payal Exec",
        "interestedModel": "Turbo Max", "createdDate": "2026-10-10", "budget": 100000})
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        up = await client.post(
            f"/api/leads/{lid}/documents",
            files={"file": ("scan.png", io.BytesIO(b"\x89PNG kyc"), "image/png")},
            data={"kind": kind},
        )
        assert up.status_code == 200, up.text
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked", "accountStatus": "Active", "customerPayable": 100000}})
    exec_c = await _login("ex.pay@euler.com", PW)
    try:
        acts = (await exec_c.get(f"/api/leads/{lid}/360")).json()["actions"]
        assert acts["canFinanceReceipt"] is True
        pay = await exec_c.post(f"/api/leads/{lid}/payments", json={
            "amount": 50000, "paymentMode": "Finance", "financerName": "IDFC",
            "date": "2026-10-10"})
        assert pay.status_code == 200, pay.text
        assert pay.json()["paymentMode"] == "Finance"
    finally:
        await exec_c.aclose()


@pytest.mark.asyncio
async def test_daily_inventory_check_hides_missing_from_counts(client):
    await server.db.oem_inventory.delete_many({})
    await server.db.inventory_checks.delete_many({})
    await server.db.oem_inventory.insert_many([
        {"chassis": "CH-PRESENT", "model": "Turbo Max", "variant": "Maxx"},
        {"chassis": "CH-MISSING", "model": "Turbo Max", "variant": "Maxx"},
    ])
    before = await oem_counts()
    assert before[("Turbo Max", "Maxx")] == 2
    r = await client.post("/api/inventory/check", json={
        "items": [
            {"chassis": "CH-PRESENT", "model": "Turbo Max", "variant": "Maxx", "status": "present"},
            {"chassis": "CH-MISSING", "model": "Turbo Max", "variant": "Maxx", "status": "missing"},
        ]})
    assert r.status_code == 200, r.text
    after = await oem_counts()
    assert after[("Turbo Max", "Maxx")] == 1
    listed = (await client.get("/api/inventory")).json()
    by = {row["chassis"]: row.get("physicalStatus") for row in listed}
    assert by["CH-MISSING"] == "missing"
    assert by["CH-PRESENT"] == "present"


async def oem_counts():
    import oem_sync
    return await oem_sync.inventory_counts(server.db)
