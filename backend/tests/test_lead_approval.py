"""Executive enquiries wait for GM / Owner Approve. No live lead until then."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "lead_approval_tests")
os.environ.setdefault("JWT_SECRET", "lead-approval-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402
import web_push  # noqa: E402

GM_EMAIL = "salesgm@euler.com"
PW = "euler@123"
MOBILE = 9611100000


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.lead_requests.delete_many({})
    await server.db.activities.delete_many({})
    await server.db.push_subscriptions.delete_many({})
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


@pytest_asyncio.fixture
async def gm_client(client):
    async for c in _as(GM_EMAIL):
        yield c


def _enquiry(name="Wait Approve", **over):
    body = {
        "customerName": name,
        "mobile": next_mobile(),
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Executive",
        "budget": 185000,
        "leadSource": "Walk-in",
    }
    body.update(over)
    return body


PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8


async def attach_kyc(client, request_id, extra=()):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", *extra):
        r = await client.post(
            f"/api/lead-requests/{request_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_executive_without_deal_amount_is_rejected(exec_client):
    r = await exec_client.post("/api/leads", json=_enquiry(budget=0))
    assert r.status_code == 422, r.text
    assert await server.db.leads.count_documents({}) == 0
    assert await server.db.lead_requests.count_documents({}) == 0


@pytest.mark.asyncio
async def test_executive_submit_is_pending_not_a_live_lead(exec_client, client):
    payload = _enquiry("Pending Cust")
    r = await exec_client.post("/api/leads", json=payload)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["pending"] is True
    assert body["status"] == "pending"
    assert body["requestId"].startswith("LR26")
    assert "leadId" not in body or not body.get("leadId")

    leads = (await client.get("/api/leads")).json()
    assert all(l.get("customerName") != "Pending Cust" for l in leads)
    assert await server.db.leads.count_documents({"customerName": "Pending Cust"}) == 0

    waiting = (await exec_client.get("/api/lead-requests", params={"status": "pending"})).json()
    assert any(x["requestId"] == body["requestId"] for x in waiting)
    summary = (await client.get("/api/lead-requests/summary")).json()
    assert summary["pending"] >= 1
    assert summary["canApprove"] is True


@pytest.mark.asyncio
async def test_owner_approve_creates_the_live_lead(exec_client, client):
    r = await exec_client.post("/api/leads", json=_enquiry("Approved Cust"))
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lid = ap.json()["leadId"]
    assert lid.startswith("LD26")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["customerName"] == "Approved Cust"
    assert server.ce.num(lead.get("budget")) == 185000
    listed = (await exec_client.get("/api/leads")).json()
    assert any(l["leadId"] == lid for l in listed)
    again = await client.post(f"/api/lead-requests/{rid}/approve")
    assert again.status_code == 200
    assert again.json().get("already") is True
    assert again.json()["leadId"] == lid
    act = await server.db.activities.find_one({"leadId": lid})
    assert "approval" in (act.get("discussion") or "").lower()


@pytest.mark.asyncio
async def test_sales_gm_can_approve(exec_client, gm_client, client):
    r = await exec_client.post("/api/leads", json=_enquiry("GM Approves"))
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await gm_client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lid = ap.json()["leadId"]
    assert await server.db.leads.find_one({"leadId": lid})


@pytest.mark.asyncio
async def test_reject_creates_no_lead(exec_client, client):
    r = await exec_client.post("/api/leads", json=_enquiry("Rejected Cust"))
    rid = r.json()["requestId"]
    rej = await client.post(f"/api/lead-requests/{rid}/reject", json={"reason": "price too low"})
    assert rej.status_code == 200, rej.text
    assert await server.db.leads.count_documents({"customerName": "Rejected Cust"}) == 0
    listed = (await client.get("/api/lead-requests", params={"status": "rejected"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    assert row["rejectReason"] == "price too low"
    assert (await client.post(f"/api/lead-requests/{rid}/approve")).status_code == 409


@pytest.mark.asyncio
async def test_executive_cannot_approve_or_reject(exec_client, client):
    r = await exec_client.post("/api/leads", json=_enquiry("No Self Approve"))
    rid = r.json()["requestId"]
    assert (await exec_client.post(f"/api/lead-requests/{rid}/approve")).status_code == 403
    assert (await exec_client.post(f"/api/lead-requests/{rid}/reject")).status_code == 403
    assert await server.db.leads.count_documents({"customerName": "No Self Approve"}) == 0


@pytest.mark.asyncio
async def test_duplicate_pending_mobile_is_blocked(exec_client):
    mobile = next_mobile()
    first = await exec_client.post("/api/leads", json=_enquiry("First", mobile=mobile))
    assert first.status_code == 200, first.text
    second = await exec_client.post("/api/leads", json=_enquiry("Second", mobile=mobile))
    assert second.status_code == 409, second.text


@pytest.mark.asyncio
async def test_owner_and_gm_still_create_live_leads(client, gm_client):
    owner = await client.post("/api/leads", json=_enquiry("Owner Direct", executive="Amit"))
    assert owner.status_code == 200, owner.text
    assert owner.json()["leadId"].startswith("LD26")
    gm = await gm_client.post("/api/leads", json=_enquiry("GM Direct", executive="Sales GM"))
    assert gm.status_code == 200, gm.text
    assert gm.json()["leadId"].startswith("LD26")
    assert await server.db.lead_requests.count_documents({"payload.customerName": "Owner Direct"}) == 0


@pytest.mark.asyncio
async def test_approve_duplicate_live_mobile_stays_pending(exec_client, client):
    mobile = next_mobile()
    live = await client.post("/api/leads", json=_enquiry("Already Live", mobile=mobile, executive="Amit"))
    assert live.status_code == 200
    pending = await exec_client.post("/api/leads", json=_enquiry("Clash", mobile=mobile))
    # live mobile is already taken at submit
    assert pending.status_code == 409, pending.text


@pytest.mark.asyncio
async def test_push_vapid_and_subscribe_are_approver_only(client, exec_client, gm_client):
    vapid = await client.get("/api/push/vapid-public")
    assert vapid.status_code == 200, vapid.text
    assert vapid.json().get("publicKey")
    sub = {
        "endpoint": "https://push.example/owner",
        "keys": {"p256dh": "abc", "auth": "def"},
    }
    assert (await client.post("/api/push/subscribe", json=sub)).status_code == 200
    assert (await gm_client.post("/api/push/subscribe", json={
        "endpoint": "https://push.example/gm", "keys": {"p256dh": "g", "auth": "h"},
    })).status_code == 200
    assert (await exec_client.post("/api/push/subscribe", json=sub)).status_code == 403
    sent = await web_push.notify_lead_approvers(
        server.db, title="t", body="b", url="/approvals")
    # Fake endpoints fail send; notify must swallow that.
    assert sent >= 0


@pytest.mark.asyncio
async def test_notify_never_breaks_submit(exec_client, monkeypatch):
    async def boom(*_a, **_k):
        raise RuntimeError("push down")

    monkeypatch.setattr(server.web_push, "notify_lead_approvers", boom)
    r = await exec_client.post("/api/leads", json=_enquiry("Push Fail"))
    assert r.status_code == 200, r.text
    assert r.json()["pending"] is True
    assert await server.db.leads.count_documents({"customerName": "Push Fail"}) == 0
