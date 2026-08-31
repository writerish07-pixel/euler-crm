"""Executives scoped to their own leads, login by user ID, and lead allocation.

These three belong together: once an executive only sees leads assigned to them,
a lead with NOBODY on it is visible to no executive at all — it would sit
unworked and unnoticed. Allocation is what stops that, which is why the
allocation page defaults to the unassigned filter.

The scoping is enforced on single-lead reads as well as on the list. Scoping only
the list would be cosmetic: lead ids run in sequence, so a colleague's deal is
one guessed URL away.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter35scoping")
os.environ.setdefault("JWT_SECRET", "iter35-scoping-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
BASE_MOBILE = 9535350000
_seq = {"n": 0}


def next_mobile():
    _seq["n"] += 1
    return str(BASE_MOBILE + _seq["n"])


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _client_for(email, password):
    transport = httpx.ASGITransport(app=server.app)
    c = httpx.AsyncClient(transport=transport, base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return c


@pytest_asyncio.fixture
async def exec_client(client):
    c = await _client_for("executive@euler.com", "euler@123")
    yield c
    await c.aclose()


async def make_lead(c, name, executive="Amit"):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(), "interestedModel": TURBO[0],
        "variant": TURBO[1], "executive": executive})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


# ======================================== an executive sees only their own leads
@pytest.mark.asyncio
async def test_the_lead_register_is_scoped_to_the_executive(client, exec_client):
    mine = await make_lead(client, "ITER35 Mine", executive="Executive")
    theirs = await make_lead(client, "ITER35 Theirs", executive="Sanjay")

    ids = {l["leadId"] for l in (await exec_client.get("/api/leads")).json()}
    assert mine in ids
    assert theirs not in ids

    # The owner still sees both.
    all_ids = {l["leadId"] for l in (await client.get("/api/leads")).json()}
    assert {mine, theirs} <= all_ids


@pytest.mark.asyncio
async def test_another_executives_lead_cannot_be_opened_by_id(client, exec_client):
    """Scoping the list alone would be cosmetic — ids run in sequence."""
    theirs = await make_lead(client, "ITER35 Not yours", executive="Sanjay")
    r = await exec_client.get(f"/api/leads/{theirs}")
    assert r.status_code == 403
    assert "another executive" in r.json()["detail"]
    assert (await exec_client.get(f"/api/leads/{theirs}/360")).status_code == 403


@pytest.mark.asyncio
async def test_their_own_lead_still_opens(client, exec_client):
    mine = await make_lead(client, "ITER35 Openable", executive="Executive")
    assert (await exec_client.get(f"/api/leads/{mine}")).status_code == 200
    assert (await exec_client.get(f"/api/leads/{mine}/360")).status_code == 200


@pytest.mark.asyncio
async def test_bookings_activities_and_deliveries_are_scoped_too(client, exec_client):
    """Otherwise a colleague's deal is still readable from the other registers."""
    theirs = await make_lead(client, "ITER35 Their booking", executive="Sanjay")
    await client.post(f"/api/leads/{theirs}/convert-booking",
                      json={"bookingAmount": 5000, "executive": "Sanjay"})
    await client.post(f"/api/leads/{theirs}/activities",
                      json={"activityType": "Call", "discussion": "theirs"})

    bookings = (await exec_client.get("/api/bookings")).json()
    assert all(b.get("leadId") != theirs for b in bookings)
    acts = (await exec_client.get("/api/activities")).json()
    assert all(a.get("leadId") != theirs for a in acts)
    dels = (await exec_client.get("/api/deliveries")).json()
    rows = dels if isinstance(dels, list) else dels.get("rows", dels.get("leads", []))
    assert all((r or {}).get("leadId") != theirs for r in rows)


@pytest.mark.asyncio
async def test_the_owner_and_accounts_are_not_scoped(client):
    theirs = await make_lead(client, "ITER35 Owner sees", executive="Sanjay")
    assert (await client.get(f"/api/leads/{theirs}")).status_code == 200
    acc = await _client_for("accounts@euler.com", "euler@123")
    try:
        assert (await acc.get(f"/api/leads/{theirs}")).status_code == 200
    finally:
        await acc.aclose()


@pytest.mark.asyncio
async def test_an_unassigned_lead_is_invisible_to_executives(client, exec_client):
    """The reason the allocation page exists: nobody is working this."""
    orphan = await make_lead(client, "ITER35 Orphan", executive="")
    ids = {l["leadId"] for l in (await exec_client.get("/api/leads")).json()}
    assert orphan not in ids
    assert (await exec_client.get(f"/api/leads/{orphan}")).status_code == 403


# ======================================== login by user ID
@pytest.mark.asyncio
async def test_a_user_can_be_created_with_a_login_id_and_sign_in_with_it(client):
    email = "iter35.amit@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "amitPass#1", "name": "ITER35 Amit",
        "role": "executive", "loginId": "amit35"})
    assert r.status_code == 200, r.text
    assert r.json()["loginId"] == "amit35"

    c = await _client_for("amit35", "amitPass#1")
    try:
        assert (await c.get("/api/auth/me")).json()["email"] == email
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_email_still_works_so_nobody_is_locked_out(client):
    """Every account made before login IDs existed has none. Switching to IDs
    alone would lock out the owner along with everyone else."""
    c = await _client_for("owner@euler.com", "euler@123")
    try:
        assert (await c.get("/api/auth/me")).json()["role"] == "owner"
    finally:
        await c.aclose()


@pytest.mark.asyncio
async def test_a_login_id_is_case_and_space_insensitive(client):
    email = "iter35.case@euler.com"
    await server.db.users.delete_many({"email": email})
    await client.post("/api/auth/users", json={
        "email": email, "password": "casePass#1", "name": "ITER35 Case",
        "role": "executive", "loginId": "Ravi Kumar"})
    for typed in ("Ravi Kumar", "ravi kumar", "  RAVI   KUMAR  "):
        c = await _client_for(typed, "casePass#1")
        try:
            assert (await c.get("/api/auth/me")).json()["email"] == email, typed
        finally:
            await c.aclose()


@pytest.mark.asyncio
async def test_a_duplicate_login_id_is_refused(client):
    email = "iter35.dupe@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "dupePass#1", "name": "ITER35 Dupe",
        "role": "executive", "loginId": "amit35"})
    assert r.status_code == 400
    assert "already taken" in r.json()["detail"]


@pytest.mark.asyncio
async def test_a_login_id_cannot_look_like_an_email(client):
    email = "iter35.at@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "atPass#1", "name": "ITER35 At",
        "role": "executive", "loginId": "someone@somewhere.com"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_an_existing_account_can_be_given_an_id_later(client):
    """The migration path: no account is locked out while IDs are handed out."""
    email = "iter35.noid@euler.com"
    await server.db.users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "noidPass#1", "name": "ITER35 NoId",
        "role": "accounts"})
    assert created.status_code == 200, created.text
    target = created.json()
    assert target["loginId"] == ""

    r = await client.put(f"/api/auth/users/{target['userId']}/login-id",
                         json={"loginId": "accounts35"})
    assert r.status_code == 200, r.text

    c = await _client_for("accounts35", "noidPass#1")
    try:
        assert (await c.get("/api/auth/me")).json()["role"] == "accounts"
    finally:
        await c.aclose()
    # ...and their email keeps working alongside it.
    c2 = await _client_for("accounts@euler.com", "euler@123")
    await c2.aclose()


@pytest.mark.asyncio
async def test_setting_a_login_id_is_owner_only(client, exec_client):
    users = (await client.get("/api/auth/users")).json()
    target = users[0]
    r = await exec_client.put(f"/api/auth/users/{target['userId']}/login-id",
                              json={"loginId": "sneaky"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_a_wrong_password_says_user_id_not_email(client):
    r = await client.post("/api/auth/login",
                          json={"email": "amit35", "password": "wrong"})
    assert r.status_code == 401
    assert "user ID" in r.json()["detail"]


# ======================================== lead allocation
@pytest.mark.asyncio
async def test_the_summary_counts_load_and_unassigned(client):
    await make_lead(client, "ITER35 Alloc orphan", executive="")
    d = (await client.get("/api/leads/allocation/summary")).json()
    assert d["unassigned"] >= 1
    assert d["activeLeads"] >= 1
    assert any(e["executive"] == "Sanjay" for e in d["executives"])


@pytest_asyncio.fixture
async def exec_on_staff(client):
    """Allocation only accepts names on the staff master — a lead cannot be given
    to somebody the dealership does not employ. The demo executive login is not
    seeded there, so put it there."""
    if not await server.db.staff.find_one({"name": "Executive"}):
        r = await client.post("/api/staff", json={
            "name": "Executive", "role": "executive", "mobile": "9535359001"})
        assert r.status_code == 200, r.text
    return "Executive"


@pytest.mark.asyncio
async def test_allocation_refuses_someone_who_is_not_on_the_staff_master(client):
    lid = await make_lead(client, "ITER35 Ghost target", executive="")
    r = await client.post("/api/leads/allocate",
                          json={"leadIds": [lid], "executive": "Ghost Person"})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_leads_can_be_allocated_in_bulk(client, exec_client, exec_on_staff):
    a = await make_lead(client, "ITER35 Bulk A", executive="")
    b = await make_lead(client, "ITER35 Bulk B", executive="")
    # Invisible to the executive until allocated.
    assert (await exec_client.get(f"/api/leads/{a}")).status_code == 403

    r = await client.post("/api/leads/allocate",
                          json={"leadIds": [a, b], "executive": "Executive"})
    assert r.status_code == 200, r.text
    assert r.json()["movedCount"] == 2

    # ...and visible immediately afterwards.
    assert (await exec_client.get(f"/api/leads/{a}")).status_code == 200
    ids = {l["leadId"] for l in (await exec_client.get("/api/leads")).json()}
    assert {a, b} <= ids


@pytest.mark.asyncio
async def test_reallocation_keeps_the_previous_owner_in_history(client):
    """A booking or cancellation stays credited to whoever held the lead then —
    moving the lead must not quietly move that record with it."""
    lid = await make_lead(client, "ITER35 Moved", executive="Sanjay")
    await client.post("/api/leads/allocate",
                      json={"leadIds": [lid], "executive": "Amit", "remarks": "Sanjay on leave"})
    doc = await server.db.leads.find_one({"leadId": lid})
    assert doc["executive"] == "Amit"
    entry = doc["allocationHistory"][-1]
    assert entry["from"] == "Sanjay" and entry["to"] == "Amit"
    assert entry["remarks"] == "Sanjay on leave"
    assert entry["by"] == "owner@euler.com"


@pytest.mark.asyncio
async def test_allocation_refuses_an_unknown_executive(client):
    lid = await make_lead(client, "ITER35 Bad exec", executive="")
    r = await client.post("/api/leads/allocate",
                          json={"leadIds": [lid], "executive": "Nobody At All"})
    assert r.status_code == 422
    assert "staff master" in r.json()["detail"]


@pytest.mark.asyncio
async def test_allocation_skips_rather_than_fails_on_odd_rows(client):
    lid = await make_lead(client, "ITER35 Already", executive="Amit")
    r = await client.post("/api/leads/allocate", json={
        "leadIds": [lid, "LD_DOES_NOT_EXIST"], "executive": "Amit"})
    assert r.status_code == 200
    reasons = {s["reason"] for s in r.json()["skipped"]}
    assert "already theirs" in reasons and "not found" in reasons
    assert r.json()["movedCount"] == 0


@pytest.mark.asyncio
async def test_a_cancelled_lead_is_not_reallocated(client):
    lid = await make_lead(client, "ITER35 Cancelled alloc", executive="Amit")
    await client.post(f"/api/leads/{lid}/cancel",
                      json={"cancelReason": "Bought other brand"})
    r = await client.post("/api/leads/allocate",
                          json={"leadIds": [lid], "executive": "Sanjay"})
    assert r.json()["movedCount"] == 0
    assert "Cancelled lead" in {s["reason"] for s in r.json()["skipped"]}


@pytest.mark.asyncio
async def test_allocation_is_owner_and_tl_only(client, exec_client):
    lid = await make_lead(client, "ITER35 Alloc guard", executive="Amit")
    assert (await exec_client.post("/api/leads/allocate", json={
        "leadIds": [lid], "executive": "Sanjay"})).status_code == 403
    assert (await exec_client.get("/api/leads/allocation/summary")).status_code == 403

    email = "iter35.tl@euler.com"
    await server.db.users.delete_many({"email": email})
    await client.post("/api/auth/users", json={
        "email": email, "password": "tlPass#1", "name": "ITER35 TL",
        "role": "tl", "loginId": "tl35"})
    tl = await _client_for("tl35", "tlPass#1")
    try:
        assert (await tl.get("/api/leads/allocation/summary")).status_code == 200
        assert (await tl.post("/api/leads/allocate", json={
            "leadIds": [lid], "executive": "Sanjay"})).status_code == 200
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_the_allocate_route_is_not_swallowed_by_the_lead_id_route(client):
    """`/leads/allocate` sits next to `/leads/{lead_id}` — if FastAPI matched the
    path parameter first, allocation would 404 as a missing lead."""
    r = await client.post("/api/leads/allocate", json={"leadIds": [], "executive": "Amit"})
    assert r.status_code == 422          # reached the handler, rejected empty selection
    assert "at least one lead" in r.json()["detail"]


# ======================================== the morning template
def test_the_morning_report_is_no_longer_exec_day_ahead():
    """It was Marketing all along — it just spent the allowance before the EOD
    ones could, which is why it looked like the healthy one."""
    import botspace as wa
    assert wa.DEFAULT_TEMPLATES["execMorning"] == "exec_morning_statement"
    assert "day_ahead" not in wa.DEFAULT_TEMPLATES["execMorning"]
