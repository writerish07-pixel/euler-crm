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
    assert "incentive" in body
    assert "units" in body["incentive"]


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


@pytest.mark.asyncio
async def test_scoreboard_bookings_survive_delivery(client):
    """Delivered leads must still count as bookings — Conv % must not drop to 0."""
    await server.db.leads.delete_many({})
    ym = "2026-08"
    await server.db.leads.insert_many([
        {
            "leadId": "LD2600BOOK",
            "customerName": "Booked Only",
            "executive": "Riya",
            "leadSource": "Walk-in",
            "interestedModel": "HiLoad",
            "currentStatus": "Booked",
            "accountStatus": "Active",
            "createdDate": f"{ym}-02",
            "bookingDate": f"{ym}-05",
            "deliveryStatus": "",
        },
        {
            "leadId": "LD2600DELV",
            "customerName": "Delivered Deal",
            "executive": "Riya",
            "leadSource": "Walk-in",
            "interestedModel": "Turbo Max",
            "currentStatus": "Delivered",
            "accountStatus": "Active",
            "createdDate": f"{ym}-03",
            "bookingDate": f"{ym}-06",
            "deliveryDate": f"{ym}-10",
            "deliveryStatus": "Delivered",
        },
    ])
    orig_this_month = server.this_month
    server.this_month = lambda: ym
    try:
        await _login(client, "asm@euler.com")
        r = await client.get("/api/field/dashboard")
        assert r.status_code == 200, r.text
        board = {row["executive"]: row for row in r.json()["executiveScoreboard"]}
        riya = board["Riya"]
        assert riya["leadsMtd"] == 2
        assert riya["bookingsMtd"] == 2, riya  # delivered still counts as booked
        assert riya["deliveriesMtd"] == 1
        assert riya["conversion"] == 100.0
        assert riya["deliveryConversion"] == 50.0
        assert r.json()["kpis"]["bookingsMtd"] == 2
        assert r.json()["kpis"]["leadToBookPct"] == 100.0
    finally:
        server.this_month = orig_this_month


@pytest.mark.asyncio
async def test_asm_lead_360_hides_commercials(client):
    await _login(client, "owner@euler.com")
    created = await client.post("/api/leads", json={
        "customerName": "Secret Money",
        "mobile": "9333333333",
        "leadSource": "Walk-in",
        "interestedModel": "HiLoad",
        "variant": "Cargo",
        "executive": "Executive",
    })
    assert created.status_code == 200, created.text
    lead_id = created.json()["leadId"]
    await server.db.leads.update_one(
        {"leadId": lead_id},
        {"$set": {"customerPayable": 790000, "customerOutstanding": 0, "totalReceived": 790000}},
    )

    await _login(client, "asm@euler.com")
    r = await client.get(f"/api/leads/{lead_id}/360")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("fieldView") is True
    assert body["commercials"] == {}
    assert body["payments"] == []
    assert body["claims"] == []
    assert body["billingSummary"] is None
    assert "customerPayable" not in body["lead"]
    assert "customerOutstanding" not in body["lead"]
    assert body["actions"].get("canBook") is False

    listing = await client.get("/api/leads")
    assert listing.status_code == 200
    row = next(x for x in listing.json() if x["leadId"] == lead_id)
    assert "customerPayable" not in row


@pytest.mark.asyncio
async def test_asm_can_view_finance_register_readonly(client):
    """ASM/RM need Finance Register to see financer disbursed vs remaining — read only."""
    import server as srv
    await srv.db.finance.delete_many({"fileNumber": "ASM-FIN-1"})
    await srv.db.finance.insert_one({
        "fileNumber": "ASM-FIN-1",
        "leadId": "LD-ASM-FIN",
        "customerName": "Field View Cust",
        "financer": "HDFC",
        "sanctionedAmount": 100000,
        "receivedAgainstFile": 40000,
        "fileOutstanding": 60000,
        "status": "Partial",
        "lastPaymentDate": "2026-08-10",
    })

    await _login(client, "asm@euler.com")
    r = await client.get("/api/finance")
    assert r.status_code == 200, r.text
    rows = r.json()
    assert any(f.get("fileNumber") == "ASM-FIN-1" for f in rows)
    hit = next(f for f in rows if f["fileNumber"] == "ASM-FIN-1")
    assert hit["receivedAgainstFile"] == 40000
    assert hit["fileOutstanding"] == 60000

    pending = await client.get("/api/finance", params={"view": "pending"})
    assert pending.status_code == 200
    assert any(f.get("fileNumber") == "ASM-FIN-1" for f in pending.json())

    # Writes stay money-desk only
    blocked = await client.post("/api/finance/ASM-FIN-1/receipt", json={
        "amount": 1000, "date": "2026-08-11",
    })
    assert blocked.status_code == 403, blocked.text

    await _login(client, "rm@euler.com")
    assert (await client.get("/api/finance")).status_code == 200


@pytest.mark.asyncio
async def test_executive_finance_register_is_own_files_only(client):
    import server as srv
    await srv.db.finance.delete_many({})
    await srv.db.leads.insert_one({
        "leadId": "LD-FIN-MINE", "customerName": "Mine", "executive": "Executive",
        "currentStatus": "Booked", "accountStatus": "Active",
        "createdDate": "2026-08-01", "mobile": "9000000101",
    })
    await srv.db.leads.insert_one({
        "leadId": "LD-FIN-THEIRS", "customerName": "Theirs", "executive": "Sanjay",
        "currentStatus": "Booked", "accountStatus": "Active",
        "createdDate": "2026-08-01", "mobile": "9000000102",
    })
    await srv.db.finance.insert_one({
        "fileNumber": "FN-MINE", "leadId": "LD-FIN-MINE", "customerName": "Mine",
        "financer": "HDFC", "sanctionedAmount": 80000, "receivedAgainstFile": 0,
        "fileOutstanding": 80000, "status": "Pending",
    })
    await srv.db.finance.insert_one({
        "fileNumber": "FN-THEIRS", "leadId": "LD-FIN-THEIRS", "customerName": "Theirs",
        "financer": "AXIS", "sanctionedAmount": 90000, "receivedAgainstFile": 0,
        "fileOutstanding": 90000, "status": "Pending",
    })
    await _login(client, "executive@euler.com")
    rows = (await client.get("/api/finance")).json()
    ids = {f["fileNumber"] for f in rows}
    assert "FN-MINE" in ids
    assert "FN-THEIRS" not in ids
    await _login(client, "owner@euler.com")
    owner_ids = {f["fileNumber"] for f in (await client.get("/api/finance")).json()}
    assert "FN-MINE" in owner_ids and "FN-THEIRS" in owner_ids
