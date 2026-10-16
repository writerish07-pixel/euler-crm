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
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"):
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
    assert deal["needsApproval"] is False


def test_lower_deal_fills_additional_and_owner_only():
    deal = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 790000)
    assert deal["priceTotal"] == MY_TOTAL
    assert deal["additionalDiscount"] == 19500
    assert deal["needsOwnerApproval"] is True
    assert deal["needsApproval"] is True


def test_higher_deal_no_additional_still_owner_only():
    deal = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 820000)
    assert deal["additionalDiscount"] == 0
    assert deal["needsOwnerApproval"] is True
    assert deal["needsApproval"] is False


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
    assert exact.json()["needsApproval"] is False
    high = await client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Deal Gate LR", "cxDemand": 820000,
    })
    assert high.json()["additionalDiscount"] == 0
    assert high.json()["needsApproval"] is False
    assert high.json()["needsOwnerApproval"] is True


@pytest.mark.asyncio
async def test_exec_deal_preview_keeps_needs_approval(exec_client):
    await server._apply_rto_insurance_defaults()
    low = await exec_client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Deal Gate LR", "cxDemand": 790000,
    })
    assert low.status_code == 200, low.text
    body = low.json()
    assert "additionalDiscount" not in body
    assert body["needsApproval"] is True
    exact = await exec_client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Deal Gate LR", "cxDemand": MY_TOTAL,
    })
    assert exact.json()["needsApproval"] is False


@pytest.mark.asyncio
async def test_exec_submit_stores_additional(exec_client, client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "Low Deal", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 790000,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("pending") is True
    assert not body.get("leadId")
    req = await server.db.lead_requests.find_one({"requestId": body["requestId"]})
    assert ce.num((req.get("dealFormat") or {}).get("additionalDiscount")) == 19500
    assert ce.num(req.get("cxDemand") or req.get("dealAmount")) == 790000
    listed = (await client.get("/api/leads")).json()
    assert not any(l.get("customerName") == "Low Deal" for l in listed)


@pytest.mark.asyncio
async def test_gm_forbidden_when_deal_differs(exec_client, gm_client, client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "GM Blocked", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 0,
    })
    lid = r.json()["leadId"]
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        up = await exec_client.post(
            f"/api/leads/{lid}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert up.status_code == 200, up.text
    wait = await exec_client.post(
        f"/api/leads/{lid}/convert-booking",
        json={
            "bookingAmount": 0, "executive": "Executive", "bookingDate": "2026-10-10",
            "budget": 790000,
        })
    assert wait.status_code == 409, wait.text
    req = await server.db.lead_requests.find_one(
        {"existingLeadId": lid, "requestKind": "booking_deal", "status": "pending"})
    assert req is not None
    ap = await gm_client.post(f"/api/lead-requests/{req['requestId']}/approve")
    assert ap.status_code == 403, ap.text
    assert "Owner" in ap.text
    owner = await client.post(f"/api/lead-requests/{req['requestId']}/approve")
    assert owner.status_code == 200, owner.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["additionalDiscount"]) == 19500
    assert ce.num(lead["customerPayable"]) == 790000


@pytest.mark.asyncio
async def test_exec_exact_deal_creates_live_without_approval(exec_client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "No Discount Exec", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": MY_TOTAL,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body.get("pending")
    assert body.get("leadId")
    lead = await server.db.leads.find_one({"leadId": body["leadId"]})
    assert ce.num(lead["additionalDiscount"]) == 0
    assert ce.num(lead["customerPayable"]) == MY_TOTAL
    assert await server.db.lead_requests.count_documents(
        {"payload.customerName": "No Discount Exec"}) == 0


@pytest.mark.asyncio
async def test_tl_discount_waits_for_owner_gm(client):
    await server._apply_rto_insurance_defaults()
    await client.post("/api/auth/users", json={
        "email": "deal.tl@euler.com", "password": PW, "name": "Deal TL", "role": "tl"})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as tl:
        login = await tl.post("/api/auth/login",
                              json={"email": "deal.tl@euler.com", "password": PW})
        tl.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        r = await tl.post("/api/leads", json={
            "customerName": "TL Discount", "mobile": next_mobile(),
            "interestedModel": "Storm", "variant": "Deal Gate LR",
            "executive": "Amit", "budget": 790000,
        })
        assert r.status_code == 200, r.text
        assert r.json().get("pending") is True
        assert r.json().get("requestId")
        assert not r.json().get("leadId")
        assert await server.db.leads.count_documents({"customerName": "TL Discount"}) == 0
        exact = await tl.post("/api/leads", json={
            "customerName": "TL Exact", "mobile": next_mobile(),
            "interestedModel": "Storm", "variant": "Deal Gate LR",
            "executive": "Amit", "budget": MY_TOTAL,
        })
        assert exact.status_code == 200, exact.text
        assert exact.json().get("leadId")
        assert not exact.json().get("pending")
        extra = await tl.post("/api/leads", json={
            "customerName": "TL Extra Margin", "mobile": next_mobile(),
            "interestedModel": "Storm", "variant": "Deal Gate LR",
            "executive": "Amit", "budget": 820000,
        })
        assert extra.status_code == 200, extra.text
        assert extra.json().get("leadId")
        assert not extra.json().get("pending")


@pytest.mark.asyncio
async def test_exec_extra_margin_creates_live_without_approval(exec_client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "Exec Extra Margin", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 820000,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert not body.get("pending")
    assert body.get("leadId")
    lead = await server.db.leads.find_one({"leadId": body["leadId"]})
    assert ce.num(lead["additionalDiscount"]) == 0
    assert ce.num(lead["customerPayable"]) == 820000
    assert await server.db.lead_requests.count_documents(
        {"payload.customerName": "Exec Extra Margin"}) == 0


@pytest.mark.asyncio
async def test_exec_exact_blocked_when_pending_same_mobile(exec_client):
    await server._apply_rto_insurance_defaults()
    mobile = next_mobile()
    first = await exec_client.post("/api/leads", json={
        "customerName": "Pending Disc", "mobile": mobile,
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": 790000,
    })
    assert first.status_code == 200, first.text
    assert first.json().get("pending") is True
    assert first.json().get("requestId")
    blocked = await exec_client.post("/api/leads", json={
        "customerName": "Pending Disc", "mobile": mobile,
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": MY_TOTAL,
    })
    assert blocked.status_code == 409, blocked.text
    assert (blocked.json().get("detail") or {}).get("code") == "mobile_active_deal"
    ok = await exec_client.post("/api/leads", json={
        "customerName": "Pending Disc", "mobile": mobile,
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": MY_TOTAL, "anotherVehicle": True,
    })
    assert ok.status_code == 200, ok.text
    assert ok.json().get("leadId")
    assert not ok.json().get("pending")


@pytest.mark.asyncio
async def test_exec_partial_pack_waits_for_approval(exec_client):
    await server._apply_rto_insurance_defaults()
    r = await exec_client.post("/api/leads", json={
        "customerName": "Partial Pack", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Deal Gate LR",
        "executive": "Executive", "budget": MY_TOTAL,
        "sameOrderMultiUnit": True,
        "units": [{"model": "No Price Van", "variant": "X"}],
    })
    assert r.status_code == 200, r.text
    assert r.json().get("pending") is True
    assert r.json().get("requestId")
    assert not r.json().get("leadId")
    assert await server.db.leads.count_documents({"customerName": "Partial Pack"}) == 0


def test_quoted_deal_needs_approval_only_for_discount():
    exact = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, MY_TOTAL)
    low = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 790000)
    high = ce.compute_deal_format(
        {"exShowroom": EX, "rto": RTO, "insurance": INS}, 820000)
    assert server._quoted_deal_needs_approval(exact, MY_TOTAL) is False
    assert server._quoted_deal_needs_approval(low, 790000) is True
    assert server._quoted_deal_needs_approval(high, 820000) is False
    assert server._quoted_deal_needs_approval(None, 0) is False
    assert server._quoted_deal_needs_approval(None, 185000) is True
    assert server._quoted_deal_needs_approval({"priceFound": False}, 185000) is True
    assert server._quoted_deal_needs_approval(
        {"priceFound": False, "exShowroom": EX, "priceTotal": MY_TOTAL, "pack": True},
        MY_TOTAL) is True
