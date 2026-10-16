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
import team_scope  # noqa: E402

PW = "euler@123"


class _FakeStaff:
    def __init__(self, rows):
        self.rows = rows

    def find(self, *_a, **_k):
        return self

    async def to_list(self, _n):
        return list(self.rows)


class _FakeDb:
    def __init__(self, rows):
        self.staff = _FakeStaff(rows)


def test_team_scope_matches_short_login_to_reports_to():
    assert team_scope.names_match("Amit", "Amit TL")
    assert team_scope.names_match("Ravi", "Ravi Sharma")
    assert not team_scope.names_match("Neha Exec", "Ravi Sharma")


def test_lead_in_names_accepts_short_executive_spelling():
    names = {"amit tl", "ravi sharma"}
    assert team_scope.lead_in_names({"executive": "Ravi"}, names)
    assert team_scope.lead_in_names({"executive": "Ravi Sharma"}, names)
    assert team_scope.lead_in_names({"executive": "Amit TL"}, names)
    assert not team_scope.lead_in_names({"executive": "Neha Exec"}, names)


@pytest.mark.asyncio
async def test_team_member_names_resolve_login_aliases_and_staff_id():
    db = _FakeDb([
        {"name": "Amit TL", "role": "team_lead", "email": "amit.tl@euler.com",
         "staffId": "ST26001", "status": "Active"},
        {"name": "Ravi Sharma", "role": "executive", "reportsTo": "Amit",
         "email": "ravi@euler.com", "status": "Active"},
        {"name": "Pooja", "role": "executive", "reportsTo": "ST26001",
         "status": "Active"},
        {"name": "Neha Exec", "role": "executive", "reportsTo": "Other TL",
         "status": "Active"},
        {"name": "Gone", "role": "executive", "reportsTo": "Amit TL",
         "status": "Inactive"},
    ])
    user = {"name": "Amit", "email": "amit.tl@euler.com", "role": "team_lead",
            "loginId": "amit.tl"}
    names = await team_scope.team_member_names(db, user)
    assert "amit" in names
    assert "amit tl" in names
    assert "ravi sharma" in names
    assert "ravi" in names
    assert "pooja" in names
    assert "neha exec" not in names
    assert "gone" not in names
    assert team_scope.name_allowed_for_team_lead("Ravi", names)
    assert team_scope.name_allowed_for_team_lead("Pooja", names)
    assert not team_scope.name_allowed_for_team_lead("Neha Exec", names)


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
        rows = (await tl.get("/api/leads", params={"followup": True})).json()
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
async def test_team_lead_sees_team_when_login_name_is_short(client):
    """Live TLs often log in as 'Amit' while Staff Reports-to says 'Amit TL'."""
    await server.db.users.delete_many({"email": {"$in": ["tl.short@euler.com"]}})
    await server.db.staff.delete_many({"name": {"$in": ["Amit TL", "Ravi Sharma", "Kiran Other"]}})
    assert (await client.post("/api/staff", json={"name": "Amit TL", "role": "team_lead"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Ravi Sharma", "role": "executive", "reportsTo": "Amit TL"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Kiran Other", "role": "executive", "reportsTo": "Someone Else"})).status_code in (200, 201)
    created = await client.post("/api/auth/users", json={
        "email": "tl.short@euler.com", "password": PW, "name": "Amit", "role": "team_lead"})
    assert created.status_code in (200, 201), created.text
    mine = await client.post("/api/leads", json={
        "customerName": "Short-name Team", "mobile": "9811100011", "executive": "Ravi",
        "interestedModel": "Turbo Max", "createdDate": "2026-10-10"})
    other = await client.post("/api/leads", json={
        "customerName": "Other Team", "mobile": "9811100012", "executive": "Kiran Other",
        "interestedModel": "Storm", "createdDate": "2026-10-10"})
    assert mine.status_code == 200 and other.status_code == 200, (mine.text, other.text)
    tl = await _login("tl.short@euler.com", PW)
    try:
        rows = (await tl.get("/api/leads", params={"followup": True})).json()
        names = {r["customerName"] for r in rows}
        assert "Short-name Team" in names
        assert "Other Team" not in names
        dash = (await tl.get("/api/executive/dashboard")).json()
        assert dash["scope"]["matchedLeads"] >= 1
        assert (await tl.get(f"/api/leads/{mine.json()['leadId']}")).status_code == 200
        assert (await tl.get(f"/api/leads/{other.json()['leadId']}")).status_code == 403
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_team_lead_sees_execs_who_report_to_showroom_admin_same_name(client):
    """Staff Reports-to used to list only team_lead, so many execs report to TL."""
    await server.db.users.delete_many({"email": {"$in": ["tl.showroom@euler.com"]}})
    await server.db.staff.delete_many({"name": {"$in": ["Sunil TL", "Deepak Exec", "Off Team"]}})
    assert (await client.post("/api/staff", json={"name": "Sunil TL", "role": "TL"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Deepak Exec", "role": "executive", "reportsTo": "Sunil TL"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Off Team", "role": "executive", "reportsTo": "Other Desk"})).status_code in (200, 201)
    created = await client.post("/api/auth/users", json={
        "email": "tl.showroom@euler.com", "password": PW, "name": "Sunil", "role": "team_lead"})
    assert created.status_code in (200, 201), created.text
    mine = await client.post("/api/leads", json={
        "customerName": "Showroom Team", "mobile": "9811100021", "executive": "Deepak Exec",
        "interestedModel": "Turbo Max", "createdDate": "2026-10-10"})
    other = await client.post("/api/leads", json={
        "customerName": "Not Sunil", "mobile": "9811100022", "executive": "Off Team",
        "interestedModel": "Storm", "createdDate": "2026-10-10"})
    assert mine.status_code == 200 and other.status_code == 200, (mine.text, other.text)
    tl = await _login("tl.showroom@euler.com", PW)
    try:
        names = {r["customerName"] for r in (await tl.get("/api/leads", params={"followup": True})).json()}
        assert "Showroom Team" in names
        assert "Not Sunil" not in names
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_team_lead_create_appears_on_own_dashboard(client):
    """TL can create for a reporting exec — that file must land on Team Dashboard."""
    await server.db.users.delete_many({"email": {"$in": ["tl.create@euler.com"]}})
    await server.db.staff.delete_many({"name": {"$in": ["Create TL", "Desk Exec"]}})
    assert (await client.post("/api/staff", json={"name": "Create TL", "role": "team_lead"})).status_code in (200, 201)
    assert (await client.post("/api/staff", json={
        "name": "Desk Exec", "role": "executive", "reportsTo": "Create TL"})).status_code in (200, 201)
    created = await client.post("/api/auth/users", json={
        "email": "tl.create@euler.com", "password": PW, "name": "Create TL", "role": "team_lead"})
    assert created.status_code in (200, 201), created.text
    tl = await _login("tl.create@euler.com", PW)
    try:
        made = await tl.post("/api/leads", json={
            "customerName": "Dashboard Visible", "mobile": "9811100033",
            "executive": "Desk Exec", "interestedModel": "Turbo Max"})
        assert made.status_code == 200, made.text
        lid = made.json()["leadId"]
        rows = (await tl.get("/api/leads", params={"followup": True})).json()
        assert any(r["leadId"] == lid for r in rows)
        dash = (await tl.get("/api/executive/dashboard")).json()
        recent = {r["customerName"] for r in (dash.get("recentLeads") or [])}
        assert "Dashboard Visible" in recent
        kinds = {r["kind"] for r in (dash.get("worklist") or []) if r.get("leadId") == lid}
        assert "New lead" in kinds
        assert dash["scope"]["matchedLeads"] >= 1
        assert (await tl.get(f"/api/leads/{lid}")).status_code == 200
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_team_lead_cannot_open_owner_money_or_oem_pages(client):
    """Working TL sidebar matches Executive: no payment ledger, no OEM claim desk."""
    await server.db.users.delete_many({"email": "tl.nav@euler.com"})
    created = await client.post("/api/auth/users", json={
        "email": "tl.nav@euler.com", "password": PW, "name": "Nav TL", "role": "team_lead"})
    assert created.status_code in (200, 201), created.text
    tl = await _login("tl.nav@euler.com", PW)
    try:
        assert (await tl.get("/api/payments")).status_code == 403
        assert (await tl.get("/api/insurance")).status_code == 403
        assert (await tl.get("/api/oem-billing")).status_code == 403
        assert (await tl.get("/api/claims")).status_code == 403
        assert (await tl.get("/api/oem-claims")).status_code == 403
        assert (await tl.get("/api/oem-extra-support")).status_code == 403
        assert (await tl.get("/api/finance")).status_code == 200
        assert (await tl.get("/api/leads")).status_code == 200
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
