"""KYC / delivery / Tally / refund documents, lead-scoped payments, header search."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "lead_docs_tests")
os.environ.setdefault("JWT_SECRET", "lead-docs-secret-32chars!!xx")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
PNG = b"\x89PNG\r\n\x1a\n" + b"doc-bytes" * 16
MOBILE = 9622200000


def next_mobile():
    global MOBILE
    MOBILE += 1
    return str(MOBILE)


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.lead_requests.delete_many({})
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    await server.db.payments.delete_many({})
    await server.db.activities.delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _as(email, password=PW):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest_asyncio.fixture
async def exec_client(client):
    async for c in _as("executive@euler.com"):
        yield c


@pytest_asyncio.fixture
async def accounts_client(client):
    if not await server.db.users.find_one({"email": "accounts@euler.com"}):
        await server.db.users.insert_one({
            "userId": "acct-docs-1",
            "email": "accounts@euler.com",
            "passwordHash": authmod.hash_password(PW),
            "name": "Accounts",
            "role": "accounts",
        })
    else:
        await server.db.users.update_one(
            {"email": "accounts@euler.com"},
            {"$set": {"passwordHash": authmod.hash_password(PW), "role": "accounts"}},
        )
    async for c in _as("accounts@euler.com"):
        yield c


@pytest_asyncio.fixture
async def oem(client):
    email = "docs.oem@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "oemDesk#2026", "name": "OEM Docs",
        "role": "oem_finance"})
    assert r.status_code == 200, r.text
    async for c in _as(email, "oemDesk#2026"):
        yield c


def _png(name="scan.png"):
    return (name, io.BytesIO(PNG), "image/png")


async def upload(c, url, kind, name="scan.png"):
    return await c.post(url, files={"file": _png(name)}, data={"kind": kind})


async def attach_kyc(c, request_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await upload(c, f"/api/lead-requests/{request_id}/documents", kind)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_approve_without_kyc_is_rejected(exec_client, client):
    r = await exec_client.post("/api/leads", json={
        "customerName": "No KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    rid = r.json()["requestId"]
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 422, ap.text
    assert "KYC" in ap.json()["detail"]
    assert await server.db.leads.count_documents({"customerName": "No KYC"}) == 0
    req = await server.db.lead_requests.find_one({"requestId": rid})
    assert req["status"] == "pending"


@pytest.mark.asyncio
async def test_kyc_then_approve_copies_docs_onto_the_lead(exec_client, client):
    r = await exec_client.post("/api/leads", json={
        "customerName": "With KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000, "customerType": "Individual"})
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    assert row["kycComplete"] is True
    assert len(row["documents"]) == 3
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lid = ap.json()["leadId"]
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    kinds = {d["kind"] for d in docs}
    assert kinds == {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"}
    file_id = docs[0]["documentId"]
    raw = await client.get(f"/api/documents/{file_id}/file")
    assert raw.status_code == 200
    assert raw.content == PNG


@pytest.mark.asyncio
async def test_b2b_needs_gst_and_gstin(exec_client, client):
    r = await exec_client.post("/api/leads", json={
        "customerName": "B2B Co", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 200000,
        "customerType": "B2B"})
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 422
    gst = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "kyc_gst")
    assert gst.status_code == 200, gst.text
    # still missing gstin
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 422
    await server.db.lead_requests.update_one(
        {"requestId": rid}, {"$set": {"payload.gstin": "22AAAAA0000A1Z5", "payload.customerType": "B2B"}})
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text


@pytest.mark.asyncio
async def test_oem_cannot_read_documents(client, exec_client, oem):
    r = await exec_client.post("/api/leads", json={
        "customerName": "Secret KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    rid = r.json()["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    lid = ap.json()["leadId"]
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    assert (await oem.get(f"/api/leads/{lid}/documents")).status_code == 403
    assert (await oem.get(f"/api/documents/{docs[0]['documentId']}/file")).status_code == 403
    assert (await oem.post(f"/api/leads/{lid}/documents",
                           files={"file": _png()}, data={"kind": "tally_invoice"})).status_code == 403


@pytest.mark.asyncio
async def test_cheque_refund_requires_scan(client):
    r = await client.post("/api/leads", json={
        "customerName": "Refund Cheque", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    if pv.json().get("found"):
        await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-08-01", "bookingAmount": 0, "paymentMode": "Cash"})
    lead = await server.db.leads.find_one({"leadId": lid})
    pay = server.ce.num(lead.get("customerPayable")) + 500
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": pay, "paymentMode": "Cash", "allowExcess": True})
    bad = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 500, "paymentMode": "Cheque"})
    assert bad.status_code == 422, bad.text
    up = await upload(client, f"/api/leads/{lid}/documents", "refund_cheque")
    assert up.status_code == 200, up.text
    ok = await client.post(f"/api/leads/{lid}/refund", json={
        "amount": 500, "paymentMode": "Cheque", "documentId": up.json()["documentId"]})
    assert ok.status_code == 200, ok.text
    assert ok.json()["refund"]["entryType"] == "Refund"


@pytest.mark.asyncio
async def test_payments_lead_id_isolates_rows(client):
    a = await client.post("/api/leads", json={
        "customerName": "Pay A", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    b = await client.post("/api/leads", json={
        "customerName": "Pay B", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    la, lb = a.json()["leadId"], b.json()["leadId"]
    await client.post(f"/api/leads/{la}/payments", json={"amount": 100, "paymentMode": "Cash"})
    await client.post(f"/api/leads/{lb}/payments", json={"amount": 250, "paymentMode": "Cash"})
    only_a = (await client.get("/api/payments", params={"lead_id": la})).json()
    assert {p["leadId"] for p in only_a} == {la}
    assert all(p["amount"] == 100 or p.get("entryType") == "Refund" for p in only_a)


@pytest.mark.asyncio
async def test_search_q_finds_name_mobile_id(client):
    r = await client.post("/api/leads", json={
        "customerName": "Searchable Singh", "mobile": "9876543210",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    by_name = (await client.get("/api/leads", params={"q": "Searchable", "limit": 8})).json()
    assert any(l["leadId"] == lid for l in by_name)
    by_mob = (await client.get("/api/leads", params={"q": "9876543210", "limit": 8})).json()
    assert any(l["leadId"] == lid for l in by_mob)
    by_id = (await client.get("/api/leads", params={"q": lid, "limit": 8})).json()
    assert any(l["leadId"] == lid for l in by_id)


@pytest.mark.asyncio
async def test_tally_invoice_replace_and_accounts_download(client, accounts_client):
    r = await client.post("/api/leads", json={
        "customerName": "Tally Inv", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    first = await upload(client, f"/api/leads/{lid}/documents", "tally_invoice", "one.pdf")
    assert first.status_code == 200, first.text
    second = await upload(accounts_client, f"/api/leads/{lid}/documents", "tally_invoice", "two.pdf")
    assert second.status_code == 200, second.text
    docs = (await accounts_client.get(f"/api/leads/{lid}/documents")).json()
    tally = [d for d in docs if d["kind"] == "tally_invoice"]
    assert len(tally) == 1
    assert tally[0]["filename"].startswith("two")
    dash = (await accounts_client.get("/api/accounts/dashboard")).json()
    assert "cancelledRefundQueue" in dash
    assert "cancelledRefundDue" in dash["kpis"]


@pytest.mark.asyncio
async def test_delivery_upload_is_deal_desk(client, exec_client, accounts_client):
    r = await client.post("/api/leads", json={
        "customerName": "Deliv Docs", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Executive"})
    lid = r.json()["leadId"]
    denied = await upload(exec_client, f"/api/leads/{lid}/documents", "delivery_insurance")
    assert denied.status_code in (403, 422)
    ok = await upload(client, f"/api/leads/{lid}/documents", "delivery_rto")
    assert ok.status_code == 200, ok.text
    # Accounts may download delivery scans, not upload them.
    acc_up = await upload(accounts_client, f"/api/leads/{lid}/documents", "delivery_rto")
    assert acc_up.status_code == 403
    listed = (await accounts_client.get(f"/api/leads/{lid}/documents")).json()
    assert any(d["kind"] == "delivery_rto" for d in listed)
