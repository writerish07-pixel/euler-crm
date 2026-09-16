"""Same mobile, many vehicles — confirm anotherVehicle, never a lifetime lock."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "same_mobile_multi_unit")
os.environ.setdefault("JWT_SECRET", "same-mobile-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
MOBILE = 9622200000
PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


def _enquiry(name="Unit Buyer", **over):
    body = {
        "customerName": name,
        "mobile": next_mobile(),
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
        "budget": 185000,
        "leadSource": "Walk-in",
    }
    body.update(over)
    return body


async def attach_kyc(client, request_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await client.post(
            f"/api/lead-requests/{request_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert r.status_code == 200, r.text


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["same_mobile_multi_unit_isolated"]
    for name in ("leads", "lead_requests", "activities", "lead_documents",
                 "counters", "price_master"):
        await isolated[name].delete_many({})
    monkeypatch.setattr(server, "db", isolated)
    await server.authmod.seed_users(server.client[os.environ["DB_NAME"]])
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _as(email):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest_asyncio.fixture
async def exec_client(client):
    async for c in _as("executive@euler.com"):
        yield c


def _detail(r):
    body = r.json()
    d = body.get("detail")
    return d if isinstance(d, dict) else {"message": d, "code": ""}


@pytest.mark.asyncio
async def test_second_lead_same_mobile_needs_confirm(client):
    mobile = next_mobile()
    first = await client.post("/api/leads", json=_enquiry("Ramesh", mobile=mobile))
    assert first.status_code == 200, first.text
    second = await client.post("/api/leads", json=_enquiry("Ramesh", mobile=mobile))
    assert second.status_code == 409, second.text
    d = _detail(second)
    assert d["code"] == "mobile_active_deal"
    assert d["existing"][0]["leadId"] == first.json()["leadId"]
    ok = await client.post("/api/leads", json=_enquiry("Ramesh", mobile=mobile, anotherVehicle=True))
    assert ok.status_code == 200, ok.text
    assert ok.json()["leadId"] != first.json()["leadId"]
    assert await server.db.leads.count_documents({"mobile": mobile}) == 2


@pytest.mark.asyncio
async def test_mobile_matches_lists_siblings_not_as_lead_id(client):
    mobile = next_mobile()
    a = await client.post("/api/leads", json=_enquiry("Fleet A", mobile=mobile))
    b = await client.post("/api/leads", json=_enquiry("Fleet A", mobile=mobile, anotherVehicle=True))
    assert a.status_code == 200 and b.status_code == 200
    r = await client.get("/api/leads/mobile-matches", params={"mobile": mobile})
    assert r.status_code == 200, r.text
    ids = {x["leadId"] for x in r.json()["existing"]}
    assert ids == {a.json()["leadId"], b.json()["leadId"]}
    captured = await client.get("/api/leads/mobile-matches")
    assert captured.status_code == 200


@pytest.mark.asyncio
async def test_closed_file_uses_new_purchase_code(client):
    mobile = next_mobile()
    first = await client.post("/api/leads", json=_enquiry("Old Deal", mobile=mobile))
    await server.db.leads.update_one(
        {"leadId": first.json()["leadId"]},
        {"$set": {"currentStatus": "Close Won", "accountStatus": "Closed"}},
    )
    second = await client.post("/api/leads", json=_enquiry("Old Deal", mobile=mobile))
    assert second.status_code == 409
    assert _detail(second)["code"] == "mobile_previous_deal"


@pytest.mark.asyncio
async def test_name_clash_is_other_customer(client):
    mobile = next_mobile()
    await client.post("/api/leads", json=_enquiry("Ramesh Kumar", mobile=mobile))
    r = await client.post("/api/leads", json=_enquiry("Someone Else", mobile=mobile))
    assert r.status_code == 409
    assert _detail(r)["code"] == "mobile_other_customer"


@pytest.mark.asyncio
async def test_exec_needs_flag_then_gm_can_approve(exec_client, client):
    mobile = next_mobile()
    live = await client.post(
        "/api/leads", json=_enquiry("Live", mobile=mobile, executive="Executive"))
    assert live.status_code == 200
    blocked = await exec_client.post(
        "/api/leads", json=_enquiry("Second Unit", mobile=mobile, executive="Executive"))
    assert blocked.status_code == 409
    pending = await exec_client.post(
        "/api/leads", json=_enquiry(
            "Second Unit", mobile=mobile, executive="Executive", anotherVehicle=True))
    assert pending.status_code == 200, pending.text
    rid = pending.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    assert ap.json()["leadId"] != live.json()["leadId"]


@pytest.mark.asyncio
async def test_other_executive_cannot_open_a_second_file(exec_client, client):
    mobile = next_mobile()
    live = await client.post("/api/leads", json=_enquiry("Amit Cust", mobile=mobile, executive="Amit"))
    assert live.status_code == 200
    blocked = await exec_client.post("/api/leads", json=_enquiry("Poach", mobile=mobile))
    assert blocked.status_code == 409, blocked.text
    d = _detail(blocked)
    assert d["code"] == "mobile_other_executive"
    assert "Amit" in d["message"]
    assert d.get("executive") == "Amit"
    still = await exec_client.post(
        "/api/leads", json=_enquiry("Poach", mobile=mobile, anotherVehicle=True))
    assert still.status_code == 409
    assert _detail(still)["code"] == "mobile_other_executive"
    owner_other = await client.post(
        "/api/leads", json=_enquiry("Poach", mobile=mobile, executive="Rahul", anotherVehicle=True))
    assert owner_other.status_code == 409
    assert _detail(owner_other)["code"] == "mobile_other_executive"
    same = await client.post(
        "/api/leads", json=_enquiry("Amit Cust", mobile=mobile, executive="Amit", anotherVehicle=True))
    assert same.status_code == 200, same.text


@pytest.mark.asyncio
async def test_approve_same_mobile_without_flag_does_not_stick(client):
    """GM Approve must not 409 just because the live register already has the mobile."""
    mobile = next_mobile()
    live = await client.post("/api/leads", json=_enquiry("Already Live", mobile=mobile))
    assert live.status_code == 200
    body = server.LeadIn(**_enquiry("Approved Twin", mobile=mobile))
    created = await server._insert_live_lead(
        body, source_note="test", allow_same_mobile=True)
    assert created["leadId"] != live.json()["leadId"]


@pytest.mark.asyncio
async def test_update_mobile_needs_confirm(client):
    a_m, b_m = next_mobile(), next_mobile()
    a = await client.post("/api/leads", json=_enquiry("A", mobile=a_m))
    b = await client.post("/api/leads", json=_enquiry("B", mobile=b_m))
    clash = await client.put(f"/api/leads/{b.json()['leadId']}", json={"mobile": a_m})
    assert clash.status_code == 409
    ok = await client.put(
        f"/api/leads/{b.json()['leadId']}",
        json={"mobile": a_m, "anotherVehicle": True})
    assert ok.status_code == 200, ok.text
    assert await server.db.leads.count_documents({"mobile": a_m}) == 2


@pytest.mark.asyncio
async def test_pending_same_mobile_blocked_without_flag(exec_client):
    mobile = next_mobile()
    first = await exec_client.post("/api/leads", json=_enquiry("P1", mobile=mobile))
    assert first.status_code == 200
    second = await exec_client.post("/api/leads", json=_enquiry("P2", mobile=mobile))
    assert second.status_code == 409
    ok = await exec_client.post(
        "/api/leads", json=_enquiry("P2", mobile=mobile, anotherVehicle=True))
    assert ok.status_code == 200, ok.text
    assert ok.json()["requestId"] != first.json()["requestId"]
