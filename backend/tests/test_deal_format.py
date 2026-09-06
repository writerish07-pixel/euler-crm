"""Scheme-free deal format: quote card, outstanding = Cx Demand, booking UTR."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "deal_format_v1")
os.environ.setdefault("JWT_SECRET", "deal-format-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
MOBILE = 9622200000
PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8


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
    await server.db.price_master.delete_many({"priceId": "PM-DEAL-STORM"})
    await server.db.price_master.insert_one({
        "priceId": "PM-DEAL-STORM",
        "model": "Storm",
        "variant": "Storm LR Deal Test",
        "exShowroom": 1410000,
        "rto": 10000,
        "insurance": 30000,
        "handlingCharges": 10000,
        "accessories": 0, "trc": 0, "fastag": 0, "extendedWarranty": 0, "otherCharges": 0,
        "status": "active",
    })
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_deal_format_is_scheme_free_and_uses_billing_tcs():
    deal = ce.compute_deal_format({
        "exShowroom": 1410000, "rto": 10000, "insurance": 30000, "handlingCharges": 10000,
    }, 1400000)
    assert deal["schemeIncluded"] is False
    assert "consumerDiscount" not in deal
    assert deal["grossVehicleCost"] == 1460000
    assert deal["tcs"] == 14600
    assert deal["netToCx"] == 1474600
    assert deal["supportRequired"] == 74600
    assert deal["extraMargin"] == 0


def test_cx_demand_above_net_is_extra_margin():
    deal = ce.compute_deal_format({
        "exShowroom": 1410000, "rto": 10000, "insurance": 30000, "handlingCharges": 10000,
    }, 1500000)
    assert deal["supportRequired"] == -25400
    assert deal["extraMargin"] == 25400


@pytest.mark.asyncio
async def test_deal_preview_api_matches_engine(client):
    r = await client.get("/api/commercial/deal-preview", params={
        "model": "Storm", "variant": "Storm LR Deal Test", "cxDemand": 1400000,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["schemeIncluded"] is False
    assert body["priceFound"] is True
    assert body["tcs"] == 14600
    assert body["netToCx"] == 1474600
    assert body["supportRequired"] == 74600
    assert body["transport"] == 10000


@pytest.mark.asyncio
async def test_owner_create_sets_outstanding_to_cx_demand(client):
    r = await client.post("/api/leads", json={
        "customerName": "Deal Owner", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Storm LR Deal Test",
        "executive": "Amit", "budget": 1400000,
    })
    assert r.status_code == 200, r.text
    lead = r.json()
    assert lead["useDealPrice"] is True
    assert ce.num(lead["cxDemand"]) == 1400000
    assert ce.num(lead["customerPayable"]) == 1400000
    assert ce.num(lead["customerOutstanding"]) == 1400000
    assert lead["dealFormat"]["schemeIncluded"] is False
    assert ce.num(lead["grossVehicleCost"]) == 1460000


@pytest.mark.asyncio
async def test_approve_sets_outstanding_to_deal_price(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ex:
        login = await ex.post("/api/auth/login", json={"email": "executive@euler.com", "password": PW})
        ex.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        sub = await ex.post("/api/leads", json={
            "customerName": "Deal Approve", "mobile": next_mobile(),
            "interestedModel": "Storm", "variant": "Storm LR Deal Test",
            "executive": "Executive", "budget": 1400000,
        })
        assert sub.status_code == 200, sub.text
        rid = sub.json()["requestId"]
        listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
        row = next(x for x in listed if x["requestId"] == rid)
        assert row["dealFormat"]["schemeIncluded"] is False
        assert row["dealFormat"]["supportRequired"] == 74600
        for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
            up = await ex.post(
                f"/api/lead-requests/{rid}/documents",
                files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
                data={"kind": kind},
            )
            assert up.status_code == 200, up.text
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lead = await server.db.leads.find_one({"leadId": ap.json()["leadId"]})
    assert ce.num(lead["customerOutstanding"]) == 1400000
    assert ce.num(lead["customerPayable"]) == 1400000
    assert lead["useDealPrice"] is True


@pytest.mark.asyncio
async def test_booking_stores_payment_reference(client):
    created = await client.post("/api/leads", json={
        "customerName": "Deal Book", "mobile": next_mobile(),
        "interestedModel": "Storm", "variant": "Storm LR Deal Test",
        "executive": "Amit", "budget": 1400000,
    })
    lid = created.json()["leadId"]
    book = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingAmount": 25000, "paymentMode": "UPI", "paymentReference": "UTR123456789",
        "executive": "Amit",
    })
    assert book.status_code == 200, book.text
    pay = await server.db.payments.find_one({"leadId": lid})
    assert pay["paymentReference"] == "UTR123456789"
    assert "UTR123456789" in (pay.get("narration") or "")
    bk = await server.db.bookings.find_one({"leadId": lid})
    assert bk["paymentReference"] == "UTR123456789"
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["customerOutstanding"]) == 1375000
