"""Price Master RTO/insurance families + auto Additional (Dealer) + GM vs Owner approve."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "rto_ins_deal_approval")
os.environ.setdefault("JWT_SECRET", "rto-ins-deal-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
MOBILE = 9633300000
PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8
EX, RTO, INS = 785000, 5500, 19000
MY_TOTAL = EX + RTO + INS  # 809500


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.lead_requests.delete_many({})
    await server.db.price_master.delete_many({"priceId": {"$in": [
        "PM-DEAL-STORM", "PM-DEAL-3W", "PM-DEAL-OTHER", "PM-DEAL-TURBO",
    ]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-DEAL-STORM",
        "model": "Storm",
        "variant": "Deal Gate LR",
        "exShowroom": EX,
        "rto": 9999,
        "insurance": 1,
        "handlingCharges": 0,
        "accessories": 0, "trc": 0, "fastag": 0, "extendedWarranty": 0, "otherCharges": 0,
        "status": "active",
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


@pytest_asyncio.fixture
async def gm_client(client):
    async for c in _as("salesgm@euler.com"):
        yield c


async def attach_kyc(http, request_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await http.post(
            f"/api/lead-requests/{request_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert r.status_code == 200, r.text


def test_rto_insurance_families():
    assert ce.default_rto_insurance_for_model("Storm", "Storm LR") == (5500, 19000)
    assert ce.default_rto_insurance_for_model("Turbo Max", "Maxx (PV)") == (5500, 19000)
    assert ce.default_rto_insurance_for_model("Turbo", "City") == (5500, 19000)
    assert ce.default_rto_insurance_for_model("Hi-Load", "XR (PV)") == (5500, 10000)
    assert ce.default_rto_insurance_for_model("Neo HiRange", "XR") == (5500, 10000)
    assert ce.default_rto_insurance_for_model("HiCity", "SR") == (5500, 10000)
    assert ce.default_rto_insurance_for_model("Unknown Van", "") is None


def test_exact_deal_has_no_additional_and_gm_ok():
    deal = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, MY_TOTAL)
    assert deal["priceTotal"] == MY_TOTAL
    assert deal["additionalDiscount"] == 0
    assert deal["needsOwnerApproval"] is False


def test_lower_deal_fills_additional_and_owner_only():
    deal = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 790000)
    assert deal["priceTotal"] == MY_TOTAL
    assert deal["additionalDiscount"] == 19500
    assert deal["needsOwnerApproval"] is True


def test_higher_deal_no_additional_still_owner_only():
    deal = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 820000)
    assert deal["additionalDiscount"] == 0
    assert deal["needsOwnerApproval"] is True


@pytest.mark.asyncio
async def test_startup_sets_storm_turbo_and_three_wheeler_charges(client):
    n = await server._apply_rto_insurance_defaults()
    assert n >= 1
    storm = await server.db.price_master.find_one({"priceId": "PM-DEAL-STORM"})
    assert storm["rto"] == 5500
    assert storm["insurance"] == 19000
    await server.db.price_master.insert_many([
        {"priceId": "PM-DEAL-TURBO", "model": "Turbo Max", "variant": "Deal Gate (PV)",
         "exShowroom": EX, "rto": 1, "insurance": 1, "status": "active"},
        {"priceId": "PM-DEAL-3W", "model": "Hi-Load", "variant": "XR (PV)",
         "exShowroom": 400000, "rto": 1, "insurance": 1, "status": "active"},
        {"priceId": "PM-DEAL-OTHER", "model": "Some Other", "variant": "X",
         "exShowroom": 100000, "rto": 333, "insurance": 444, "status": "active"},
    ])
    await server._apply_rto_insurance_defaults()
    turbo = await server.db.price_master.find_one({"priceId": "PM-DEAL-TURBO"})
    three = await server.db.price_master.find_one({"priceId": "PM-DEAL-3W"})
    other = await server.db.price_master.find_one({"priceId": "PM-DEAL-OTHER"})
    assert turbo["rto"] == 5500 and turbo["insurance"] == 19000
    assert three["rto"] == 5500 and three["insurance"] == 10000
    assert other["rto"] == 333 and other["insurance"] == 444


@pytest.mark.asyncio
async def test_deal_preview_auto_additional(client):
    await server._apply_rto_insurance_defaults()
    low = await client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Deal Gate LR", "cxDemand": 790000,
    })
    assert low.status_code == 200, low.text
    body = low.json()
    assert body["priceTotal"] == MY_TOTAL
    assert body["additionalDiscount"] == 19500
    assert body["needsOwnerApproval"] is True
    exact = await client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Deal Gate LR", "cxDemand": MY_TOTAL,
    })
    assert exact.json()["additionalDiscount"] == 0
    assert exact.json()["needsOwnerApproval"] is False


@pytest.mark.asyncio
async def test_exec_submit_stores_additional(exec_client, client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "Low Deal", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 790000,
    })
    assert r.status_code == 200, r.text
    rid = r.json()["requestId"]
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    assert row["additionalDiscount"] == 19500
    assert row["needsOwnerApproval"] is True
    assert row["dealFormat"]["priceTotal"] == MY_TOTAL


@pytest.mark.asyncio
async def test_gm_forbidden_when_deal_differs(exec_client, gm_client, client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "GM Blocked", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 790000,
    })
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await gm_client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 403, ap.text
    assert "Owner" in ap.text
    pending = await server.db.lead_requests.find_one({"requestId": rid})
    assert pending["status"] == "pending"
    owner = await client.post(f"/api/lead-requests/{rid}/approve")
    assert owner.status_code == 200, owner.text
    lead = await server.db.leads.find_one({"leadId": owner.json()["leadId"]})
    assert ce.num(lead["additionalDiscount"]) == 19500
    assert ce.num(lead["customerPayable"]) == 790000


@pytest.mark.asyncio
async def test_gm_can_approve_exact_deal(exec_client, gm_client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "GM Exact", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": MY_TOTAL,
    })
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await gm_client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lead = await server.db.leads.find_one({"leadId": ap.json()["leadId"]})
    assert ce.num(lead["additionalDiscount"]) == 0
    assert ce.num(lead["customerPayable"]) == MY_TOTAL
