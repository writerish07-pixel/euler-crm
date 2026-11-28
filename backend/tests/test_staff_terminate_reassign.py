"""Terminate staff: leads move to Showroom Admin; other paths stay intact."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "staff_terminate_reassign")
os.environ.setdefault("JWT_SECRET", "staff-terminate-secret")

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
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _ensure_showroom_admin(client, name="Desk Admin"):
    await server.db.staff.delete_many({"name": name})
    r = await client.post("/api/staff", json={
        "name": name, "role": "TL", "status": "Active", "mobile": "9811100001"})
    assert r.status_code == 200, r.text
    return r.json()


async def _add_exec(client, name, *, email=""):
    await server.db.staff.delete_many({"name": name})
    body = {"name": name, "role": "executive", "status": "Active", "mobile": "9811100002"}
    if email:
        body["email"] = email
    r = await client.post("/api/staff", json=body)
    assert r.status_code == 200, r.text
    return r.json()


async def _lead_for(executive, *, lead_id, mobile):
    await server.db.leads.delete_many({"leadId": lead_id})
    await server.db.leads.insert_one({
        "leadId": lead_id, "customerName": "Term Cust", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": executive, "accountStatus": "Active", "currentStatus": "New",
    })


@pytest.mark.asyncio
async def test_terminate_staff_moves_leads_to_showroom_admin(client):
    admin = await _ensure_showroom_admin(client)
    exec_row = await _add_exec(client, "Gone Exec")
    await _lead_for("Gone Exec", lead_id="LD-TERM-1", mobile="9811999001")
    await _lead_for("gone exec", lead_id="LD-TERM-2", mobile="9811999002")  # fold match

    r = await client.delete(f"/api/staff/{exec_row['staffId']}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["reassignedCount"] == 2
    assert body["reassignedTo"] == admin["name"]

    for lid in ("LD-TERM-1", "LD-TERM-2"):
        lead = await server.db.leads.find_one({"leadId": lid})
        assert lead["executive"] == admin["name"]
        hist = lead.get("allocationHistory") or []
        assert hist and hist[-1]["to"] == admin["name"]
        assert hist[-1]["remarks"] == "staff-terminate"

    gone = await server.db.staff.find_one({"staffId": exec_row["staffId"]})
    assert gone is None


@pytest.mark.asyncio
async def test_terminate_without_showroom_admin_is_refused(client):
    await server.db.staff.delete_many({"role": "TL"})
    exec_row = await _add_exec(client, "Orphan Exec")
    await _lead_for("Orphan Exec", lead_id="LD-TERM-NO-TL", mobile="9811999011")

    r = await client.delete(f"/api/staff/{exec_row['staffId']}")
    assert r.status_code == 409, r.text
    assert "Showroom Admin" in r.json()["detail"]
    still = await server.db.staff.find_one({"staffId": exec_row["staffId"]})
    assert still is not None
    lead = await server.db.leads.find_one({"leadId": "LD-TERM-NO-TL"})
    assert lead["executive"] == "Orphan Exec"


@pytest.mark.asyncio
async def test_terminate_staff_without_leads_still_deletes(client):
    await _ensure_showroom_admin(client)
    exec_row = await _add_exec(client, "No Leads Exec")
    r = await client.delete(f"/api/staff/{exec_row['staffId']}")
    assert r.status_code == 200, r.text
    assert r.json()["reassignedCount"] == 0
    assert await server.db.staff.find_one({"staffId": exec_row["staffId"]}) is None


@pytest.mark.asyncio
async def test_rename_with_leads_still_blocked(client):
    """Working rename guard must not change — Inactive + new name remains the path."""
    await _ensure_showroom_admin(client)
    exec_row = await _add_exec(client, "Keep Name")
    await _lead_for("Keep Name", lead_id="LD-TERM-RENAME", mobile="9811999021")
    r = await client.put(f"/api/staff/{exec_row['staffId']}", json={
        "name": "Keep Name Renamed", "role": "executive"})
    assert r.status_code == 409, r.text
    assert "orphan" in r.json()["detail"].lower() or "Renaming" in r.json()["detail"]
    lead = await server.db.leads.find_one({"leadId": "LD-TERM-RENAME"})
    assert lead["executive"] == "Keep Name"


@pytest.mark.asyncio
async def test_allocate_still_requires_active_executive(client):
    """Allocate must not start accepting Showroom Admin as an executive target."""
    admin = await _ensure_showroom_admin(client)
    await _lead_for("", lead_id="LD-TERM-ALLOC", mobile="9811999031")
    r = await client.post("/api/leads/allocate", json={
        "executive": admin["name"], "leadIds": ["LD-TERM-ALLOC"]})
    assert r.status_code == 422, r.text
    assert "not an active executive" in r.json()["detail"]


@pytest.mark.asyncio
async def test_terminate_rewrites_pending_approval_executive(client):
    """Approve prefers payload.executive — must not restore the deleted name."""
    admin = await _ensure_showroom_admin(client)
    exec_row = await _add_exec(client, "Pending Exec")
    await _lead_for("Pending Exec", lead_id="LD-TERM-PEND", mobile="9811999051")
    await server.db.leads.update_one(
        {"leadId": "LD-TERM-PEND"}, {"$set": {"assignmentPending": True}})
    await server.db.lead_requests.delete_many({"requestId": "LR-TERM-PEND"})
    await server.db.lead_requests.insert_one({
        "requestId": "LR-TERM-PEND",
        "status": "pending",
        "source": "split-assignment",
        "existingLeadId": "LD-TERM-PEND",
        "payload": {
            "customerName": "Term Cust", "mobile": "9811999051",
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "executive": "Pending Exec", "budget": 700000,
        },
        "assignedExecutive": "Pending Exec",
        "assignedExecutiveFold": "pending exec",
        "submittedByName": "Pending Exec",
        "createdAt": "2026-11-28T00:00:00+00:00",
    })

    r = await client.delete(f"/api/staff/{exec_row['staffId']}")
    assert r.status_code == 200, r.text
    assert r.json()["requestsPatched"] >= 1

    req = await server.db.lead_requests.find_one({"requestId": "LR-TERM-PEND"})
    assert req["assignedExecutive"] == admin["name"]
    assert req["assignedExecutiveFold"] == server._norm_name(admin["name"])
    assert req["payload"]["executive"] == admin["name"]
    lead = await server.db.leads.find_one({"leadId": "LD-TERM-PEND"})
    assert lead["executive"] == admin["name"]


@pytest.mark.asyncio
async def test_terminate_removes_matching_login_email(client):
    await _ensure_showroom_admin(client)
    email = "gone.exec@euler.test"
    import auth as authmod
    await server.db.users.delete_many({"email": email})
    await server.db[authmod.DELETED_USERS].delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "desk#441", "name": "Gone Login",
        "role": "executive", "loginId": "gone.login"})
    assert created.status_code == 200, created.text
    exec_row = await _add_exec(client, "Gone Login", email=email)
    await _lead_for("Gone Login", lead_id="LD-TERM-LOGIN", mobile="9811999041")

    r = await client.delete(f"/api/staff/{exec_row['staffId']}")
    assert r.status_code == 200, r.text
    assert r.json()["loginRemoved"] is True
    assert await server.db.users.find_one({"email": email}) is None
    lead = await server.db.leads.find_one({"leadId": "LD-TERM-LOGIN"})
    assert lead["executive"]
    assert lead["executive"] != "Gone Login"
