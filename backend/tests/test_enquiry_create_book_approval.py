"""Walk-in enquiry creates live; discount + KYC gate Book, not create."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "enquiry_create_book_tests")
os.environ.setdefault("JWT_SECRET", "enquiry-create-secret-32chars!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
MOBILE = 9711100000
PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8
EX, RTO, INS = 785000.0, 5500.0, 19000.0
LIST = EX + RTO + INS


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.lead_requests.delete_many({})
    await server.db.payments.delete_many({})
    await server.db.bookings.delete_many({})
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    await server.db.price_master.delete_many({"variant": "Enquiry LR"})
    await server.db.price_master.insert_one({
        "priceId": "PM-ENQ", "model": "Storm", "variant": "Enquiry LR",
        "exShowroom": EX, "rto": RTO, "insurance": INS, "status": "active",
    })
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


def _walkin(name="Walk In", **over):
    body = {
        "customerName": name,
        "mobile": next_mobile(),
        "interestedModel": "Storm",
        "variant": "Enquiry LR",
        "executive": "Executive",
        "leadSource": "Walk-in",
        "budget": 0,
    }
    body.update(over)
    return body


async def attach_lead_kyc(c, lead_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await c.post(
            f"/api/leads/{lead_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_executive_walkin_without_cx_demand_creates_live(exec_client):
    r = await exec_client.post("/api/leads", json=_walkin("No Budget Walkin"))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("leadId")
    assert not body.get("pending")
    lead = await server.db.leads.find_one({"leadId": body["leadId"]})
    assert lead["currentStatus"] == "New"
    assert server.ce.num(lead.get("budget")) == 0
    assert await server.db.lead_requests.count_documents(
        {"payload.customerName": "No Budget Walkin"}) == 0
    listed = (await exec_client.get("/api/leads")).json()
    assert any(row["leadId"] == body["leadId"] for row in listed)


@pytest.mark.asyncio
async def test_discounted_create_is_still_live_for_whatsapp(exec_client):
    r = await exec_client.post("/api/leads", json=_walkin("Disc Walkin", budget=790000))
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["currentStatus"] == "New"
    assert wa.followup_due({**lead, "createdDate": "2026-10-01"}, "2026-10-04") is True
    assert await server.db.lead_requests.count_documents({"existingLeadId": lid}) == 0


@pytest.mark.asyncio
async def test_book_at_list_price_needs_kyc_not_approval(exec_client, client):
    r = await exec_client.post("/api/leads", json=_walkin("List Book"))
    lid = r.json()["leadId"]
    denied = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={"bookingAmount": 5000, "executive": "Executive", "bookingDate": "2026-10-10"})
    assert denied.status_code == 422, denied.text
    await attach_lead_kyc(exec_client, lid)
    ok = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={"bookingAmount": 5000, "executive": "Executive", "bookingDate": "2026-10-10"})
    assert ok.status_code == 200, ok.text
    assert ok.json().get("bookingId")
    assert await server.db.lead_requests.count_documents({"existingLeadId": lid}) == 0


@pytest.mark.asyncio
async def test_discounted_book_waits_for_owner_then_books(exec_client, client):
    r = await exec_client.post("/api/leads", json=_walkin("Need Approve", budget=790000))
    lid = r.json()["leadId"]
    await attach_lead_kyc(exec_client, lid)
    wait = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={"bookingAmount": 5000, "executive": "Executive", "bookingDate": "2026-10-10"})
    assert wait.status_code == 409, wait.text
    assert "approv" in wait.json()["detail"].lower()
    req = await server.db.lead_requests.find_one(
        {"existingLeadId": lid, "requestKind": "booking_deal", "status": "pending"})
    assert req is not None
    ap = await client.post(f"/api/lead-requests/{req['requestId']}/approve")
    assert ap.status_code == 200, ap.text
    booked = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={"bookingAmount": 5000, "executive": "Executive", "bookingDate": "2026-10-10"})
    assert booked.status_code == 200, booked.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["currentStatus"] == "Booked"


@pytest.mark.asyncio
async def test_book_fills_model_from_body_then_needs_kyc(exec_client):
    r = await exec_client.post("/api/leads", json={
        "customerName": "No Vehicle Yet", "mobile": next_mobile(),
        "executive": "Executive", "leadSource": "Walk-in", "budget": 0,
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    denied = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={
            "bookingAmount": 0, "executive": "Executive", "bookingDate": "2026-10-10",
            "interestedModel": "Storm", "variant": "Enquiry LR",
        })
    assert denied.status_code == 422, denied.text
    assert "Attach" in denied.text or "document" in denied.text.lower() or "KYC" in denied.text or "Aadhaar" in denied.text
    live = await server.db.leads.find_one({"leadId": lid})
    assert live["interestedModel"] == "Storm"
    assert live["variant"] == "Enquiry LR"
    await attach_lead_kyc(exec_client, lid)
    ok = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={
            "bookingAmount": 0, "executive": "Executive", "bookingDate": "2026-10-10",
            "interestedModel": "Storm", "variant": "Enquiry LR",
        })
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_owner_books_discount_without_queue(client):
    r = await client.post("/api/leads", json=_walkin(
        "Owner Disc", executive="Amit", budget=790000))
    lid = r.json()["leadId"]
    await attach_lead_kyc(client, lid)
    booked = await client.post(
        f"/api/leads/{lid}/convert-booking",
        json={"bookingAmount": 5000, "executive": "Amit", "bookingDate": "2026-10-10"})
    assert booked.status_code == 200, booked.text
    assert await server.db.lead_requests.count_documents({"existingLeadId": lid}) == 0
