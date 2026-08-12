"""Executive dashboard + shared ASM/RM field dashboard."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "exec_field_dashboard_tests")
os.environ.setdefault("JWT_SECRET", "exec-field-dashboard-secret-32ch!")
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
    for email, name, role in (
        ("owner@euler.com", "Owner", "owner"),
        ("executive@euler.com", "Executive", "executive"),
        ("accounts@euler.com", "Accounts", "accounts"),
        ("asm@euler.com", "ASM", "asm"),
        ("rm@euler.com", "RM", "rm"),
    ):
        existing = await server.db.users.find_one({"email": email})
        if existing:
            await server.db.users.update_one(
                {"email": email},
                {"$set": {"passwordHash": authmod.hash_password("euler@123"), "role": role, "name": name}},
            )
        else:
            await server.db.users.insert_one({
                "userId": f"u-{role}",
                "email": email,
                "passwordHash": authmod.hash_password("euler@123"),
                "name": name,
                "role": role,
                "createdAt": "2026-01-01T00:00:00+00:00",
            })
    # Seed a lead assigned to Executive for scoped dashboard
    await server.db.leads.delete_many({})
    await server.db.leads.insert_one({
        "leadId": "LD26009999",
        "customerName": "Field Test",
        "mobile": "9000000999",
        "executive": "Executive",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "currentStatus": "Follow-up",
        "accountStatus": "Active",
        "createdDate": "2026-08-01",
        "nextFollowupDate": "2026-08-01",
        "customerOutstanding": 5000,
        "companyOutstanding": 0,
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
async def test_asm_and_rm_login(client):
    asm = await _login(client, "asm@euler.com")
    assert asm["user"]["role"] == "asm"
    rm = await _login(client, "rm@euler.com")
    assert rm["user"]["role"] == "rm"


@pytest.mark.asyncio
async def test_field_dashboard_shared_by_asm_and_rm(client):
    await _login(client, "asm@euler.com")
    a = await client.get("/api/field/dashboard")
    assert a.status_code == 200, a.text
    body = a.json()
    assert "kpis" in body and "executiveScoreboard" in body and "funnel" in body

    await _login(client, "rm@euler.com")
    b = await client.get("/api/field/dashboard")
    assert b.status_code == 200, b.text
    assert "leadsMtd" in b.json()["kpis"]


@pytest.mark.asyncio
async def test_executive_dashboard_scoped(client):
    await _login(client, "executive@euler.com")
    r = await client.get("/api/executive/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["scope"]["matchedLeads"] >= 1
    assert "myLeadsMtd" in body["kpis"]
    assert "worklist" in body


@pytest.mark.asyncio
async def test_accounts_cannot_open_field_or_executive_dashboard(client):
    await _login(client, "accounts@euler.com")
    assert (await client.get("/api/field/dashboard")).status_code == 403
    assert (await client.get("/api/executive/dashboard")).status_code == 403


@pytest.mark.asyncio
async def test_asm_blocked_from_create_lead_and_payment(client):
    await _login(client, "asm@euler.com")
    lead = await client.post("/api/leads", json={
        "customerName": "No Write",
        "mobile": "9111111111",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "executive": "Executive",
    })
    assert lead.status_code == 403, lead.text

    await _login(client, "owner@euler.com")
    created = await client.post("/api/leads", json={
        "customerName": "Pay Block",
        "mobile": "9222222222",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "executive": "Executive",
    })
    assert created.status_code == 200, created.text
    lead_id = created.json()["leadId"]

    await _login(client, "asm@euler.com")
    pay = await client.post(f"/api/leads/{lead_id}/payments", json={
        "amount": 1000, "paymentMode": "Cash",
    })
    assert pay.status_code == 403, pay.text


@pytest.mark.asyncio
async def test_asm_can_list_leads_readonly(client):
    await _login(client, "asm@euler.com")
    r = await client.get("/api/leads")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


@pytest.mark.asyncio
async def test_owner_can_create_asm_user(client):
    await _login(client, "owner@euler.com")
    email = "asm2@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "euler@123", "name": "ASM Two", "role": "asm",
    })
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "asm"
