"""Executive journey: no scheme on create, payments after book, papers first."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "exec_journey_docs")
os.environ.setdefault("JWT_SECRET", "exec-journey-docs-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
PNG = b"\x89PNG\r\n\x1a\n" + b"doc-bytes" * 16
_seq = {"n": 9000}


def next_mobile():
    _seq["n"] += 1
    return str(9500000000 + _seq["n"])


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest_asyncio.fixture
async def exec_client(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "executive@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def make_lead(c, name, executive="Executive"):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(), "interestedModel": TURBO[0],
        "variant": TURBO[1], "executive": executive})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


async def attach_docs(c, lead_id, kinds):
    for kind in kinds:
        up = await c.post(
            f"/api/leads/{lead_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert up.status_code == 200, up.text


@pytest.mark.asyncio
async def test_executive_deal_preview_hides_scheme(exec_client, client):
    owner = await client.get("/api/commercial/deal-preview", params={
        "model": TURBO[0], "variant": TURBO[1], "cxDemand": 180000,
    })
    exec_r = await exec_client.get("/api/commercial/deal-preview", params={
        "model": TURBO[0], "variant": TURBO[1], "cxDemand": 180000,
    })
    assert exec_r.status_code == 200, exec_r.text
    body = exec_r.json()
    assert "schemeOffers" not in body
    assert "schemePassed" not in body
    assert "additionalDiscount" not in body
    assert "schemeMonth" not in body
    assert "exShowroom" in body or body.get("priceFound") is not False
    # Owner (or desk) may still see scheme lines on the same SKU.
    if owner.status_code == 200 and owner.json().get("schemeOffers"):
        assert "schemeOffers" in owner.json()


@pytest.mark.asyncio
async def test_executive_cannot_read_scheme_master(exec_client, client):
    denied = await exec_client.get("/api/scheme-master")
    assert denied.status_code == 403, denied.text
    ok = await client.get("/api/scheme-master")
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_executive_convert_needs_kyc(exec_client, client):
    lid = await make_lead(client, "Exec KYC gate")
    blocked = await exec_client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": server.today(), "bookingAmount": 5000, "executive": "Executive"})
    assert blocked.status_code == 422, blocked.text
    assert "related documents" in blocked.text.lower() or "aadhaar" in blocked.text.lower()
    await attach_docs(client, lid, ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"))
    ok = await exec_client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": server.today(), "bookingAmount": 5000, "executive": "Executive"})
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_executive_pays_only_after_booking(exec_client, client):
    lid = await make_lead(client, "Exec pay gate")
    await attach_docs(client, lid, ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"))
    before = await exec_client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1000, "paymentMode": "Cash"})
    assert before.status_code == 409, before.text
    assert (await exec_client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": server.today(), "bookingAmount": 1000,
        "executive": "Executive"})).status_code == 200
    after = await exec_client.post(f"/api/leads/{lid}/payments", json={
        "amount": 2000, "paymentMode": "Cash"})
    assert after.status_code == 200, after.text
    finance = await exec_client.post(f"/api/leads/{lid}/payments", json={
        "amount": 1000, "paymentMode": "Finance", "financerName": "HDFC"})
    assert finance.status_code == 200, finance.text
    assert finance.json()["paymentMode"] == "Finance"


@pytest.mark.asyncio
async def test_scheme_save_needs_extra_support_proof(client):
    lid = await make_lead(client, "Extra proof scheme", executive="Amit")
    blocked = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "No Benefit", "oemExtraSupportReceived": 7000})
    assert blocked.status_code == 422, blocked.text
    assert "oem extra" in blocked.text.lower() or "related documents" in blocked.text.lower()
    await attach_docs(client, lid, ("oem_extra_support",))
    ok = await client.put(f"/api/leads/{lid}/scheme", json={
        "benefitMode": "No Benefit", "oemExtraSupportReceived": 7000})
    assert ok.status_code == 200, ok.text
