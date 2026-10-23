"""KYC / delivery / Tally / refund documents, lead-scoped payments, header search."""
import io
import os
import sys
import zipfile

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


def test_normalize_customer_type_maps_desk_labels():
    assert server.lead_docs.normalize_customer_type("B2B") == "B2B"
    assert server.lead_docs.normalize_customer_type("company") == "B2B"
    assert server.lead_docs.normalize_customer_type("B2C") == "Individual"
    assert server.lead_docs.normalize_customer_type("Individual") == "Individual"
    assert server.lead_docs.normalize_customer_type("") == "Individual"


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
async def tl_client(client):
    email = "docs.tl@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "desk#441", "name": "Docs TL", "role": "tl"})
    assert r.status_code == 200, r.text
    async for c in _as(email, "desk#441"):
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


async def seed_pending(payload, user=None):
    body = server.LeadIn(**payload)
    dumped = body.model_dump()
    another = bool(dumped.pop("anotherVehicle", False))
    dumped.pop("sameOrderMultiUnit", None)
    dumped.pop("units", None)
    scheme_pass_on = server._parse_scheme_pass_on(dumped.pop("schemePassOn", None))
    deal_amount = server.ce.round2(server.ce.num(body.budget))
    deal_format = await server._deal_format_for(
        dumped.get("interestedModel"), dumped.get("variant"), deal_amount,
        dumped.get("createdDate"), scheme_pass_on)
    dumped["customerType"] = server.lead_docs.normalize_customer_type(dumped.get("customerType"))
    actor = user or {
        "email": "executive@euler.com", "name": "Executive", "role": "executive",
    }
    return await server._create_pending_lead_request(
        body, actor, deal_format=deal_format, deal_amount=deal_amount,
        scheme_pass_on=scheme_pass_on, payload=dumped, another=another)


async def attach_kyc(c, request_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"):
        r = await upload(c, f"/api/lead-requests/{request_id}/documents", kind)
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_approve_without_kyc_is_rejected(exec_client, client):
    seeded = await seed_pending({
        "customerName": "No KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    rid = seeded["requestId"]
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 422, ap.text
    assert "KYC" in ap.json()["detail"]
    assert await server.db.leads.count_documents({"customerName": "No KYC"}) == 0
    req = await server.db.lead_requests.find_one({"requestId": rid})
    assert req["status"] == "pending"


@pytest.mark.asyncio
async def test_kyc_then_approve_copies_docs_onto_the_lead(exec_client, client):
    seeded = await seed_pending({
        "customerName": "With KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000, "customerType": "Individual"})
    rid = seeded["requestId"]
    await attach_kyc(exec_client, rid)
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    assert row["kycComplete"] is True
    assert len(row["documents"]) == 4
    assert row["dealSheetMissing"] is False
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lid = ap.json()["leadId"]
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    kinds = {d["kind"] for d in docs}
    assert kinds == {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"}
    file_id = docs[0]["documentId"]
    raw = await client.get(f"/api/documents/{file_id}/file")
    assert raw.status_code == 200
    assert raw.content == PNG


@pytest.mark.asyncio
async def test_owner_opens_exec_uploaded_request_deal_sheet(exec_client, client):
    seeded = await seed_pending({
        "customerName": "Sheet Open", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000, "customerType": "Individual"})
    rid = seeded["requestId"]
    up = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "deal_sheet", "sheet.png")
    assert up.status_code == 200, up.text
    doc_id = up.json()["documentId"]
    raw = await client.get(f"/api/documents/{doc_id}/file")
    assert raw.status_code == 200, raw.text
    assert raw.content == PNG
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    kinds = {d["kind"] for d in row["documents"]}
    assert "deal_sheet" in kinds
    assert any(d.get("documentId") == doc_id for d in row["documents"])


@pytest.mark.asyncio
async def test_approvals_list_includes_deal_sheet_already_on_the_lead(exec_client, client):
    r = await client.post("/api/leads", json={
        "customerName": "Lead Sheet", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    sheet = await upload(client, f"/api/leads/{lid}/documents", "deal_sheet", "signed.png")
    assert sheet.status_code == 200, sheet.text
    doc_id = sheet.json()["documentId"]
    await server.db.lead_requests.insert_one({
        "requestId": "LR-LEAD-SHEET", "status": "pending",
        "existingLeadId": lid, "requestKind": "booking_deal",
        "submittedBy": "executive@euler.com",
        "payload": {
            "customerName": "Lead Sheet", "mobile": "",
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "budget": 185000, "executive": "Executive",
        },
        "createdAt": "2026-10-17T10:00:00+00:00",
    })
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == "LR-LEAD-SHEET")
    assert row["dealSheetMissing"] is False
    assert any(d.get("documentId") == doc_id and d.get("kind") == "deal_sheet"
               for d in row["documents"])
    raw = await client.get(f"/api/documents/{doc_id}/file")
    assert raw.status_code == 200
    assert raw.content == PNG


@pytest.mark.asyncio
async def test_kyc_on_live_lead_lets_owner_approve_booking_request(exec_client, client):
    """Executive uploaded KYC on the file; Approvals must not show empty / block."""
    r = await client.post("/api/leads", json={
        "customerName": "Parked KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    lid = r.json()["leadId"]
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"):
        up = await upload(exec_client, f"/api/leads/{lid}/documents", kind)
        assert up.status_code == 200, up.text
    await server.db.lead_requests.insert_one({
        "requestId": "LR-PARKED-KYC", "status": "pending",
        "existingLeadId": lid, "requestKind": "booking_deal",
        "submittedBy": "executive@euler.com",
        "payload": {
            "customerName": "Parked KYC", "mobile": "",
            "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
            "budget": 185000, "executive": "Executive",
            "customerType": "Individual",
        },
        "createdAt": "2026-10-20T10:00:00+00:00",
    })
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == "LR-PARKED-KYC")
    assert row["kycComplete"] is True
    assert row["dealSheetMissing"] is False
    kinds = {d["kind"] for d in (row.get("documents") or [])}
    assert {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"} <= kinds
    ap = await client.post("/api/lead-requests/LR-PARKED-KYC/approve")
    assert ap.status_code == 200, ap.text


@pytest.mark.asyncio
async def test_request_upload_also_lands_on_the_live_lead(exec_client, client):
    r = await client.post("/api/leads", json={
        "customerName": "Bind Docs", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    lid = r.json()["leadId"]
    await server.db.lead_requests.insert_one({
        "requestId": "LR-BIND-DOCS", "status": "pending",
        "existingLeadId": lid, "requestKind": "booking_deal",
        "submittedBy": "executive@euler.com",
        "payload": {
            "customerName": "Bind Docs", "executive": "Executive",
            "customerType": "Individual",
        },
        "createdAt": "2026-10-20T10:00:00+00:00",
    })
    up = await upload(exec_client, "/api/lead-requests/LR-BIND-DOCS/documents",
                      "kyc_pan", "pan.png")
    assert up.status_code == 200, up.text
    stored = await server.db[server.lead_docs.COLLECTION].find_one(
        {"documentId": up.json()["documentId"]})
    assert stored["leadId"] == lid
    assert stored["requestId"] == "LR-BIND-DOCS"
    lead_docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    assert any(d["kind"] == "kyc_pan" for d in lead_docs)
    drawer = (await client.get(f"/api/leads/{lid}/360")).json()
    assert any(d["kind"] == "kyc_pan" for d in (drawer.get("documents") or []))


@pytest.mark.asyncio
async def test_b2b_aadhaar_is_optional(exec_client, client):
    seeded = await seed_pending({
        "customerName": "B2B No Aadhaar", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 200000,
        "customerType": "B2B", "gstin": "22AAAAA0000A1Z5"})
    rid = seeded["requestId"]
    pan = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "kyc_pan")
    gst = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "kyc_gst")
    sheet = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "deal_sheet")
    assert pan.status_code == 200 and gst.status_code == 200 and sheet.status_code == 200
    listed = (await client.get("/api/lead-requests", params={"status": "pending"})).json()
    row = next(x for x in listed if x["requestId"] == rid)
    assert row["kycComplete"] is True
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    seeded = await seed_pending({
        "customerName": "B2B Co", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 200000,
        "customerType": "B2B"})
    rid = seeded["requestId"]
    await attach_kyc(exec_client, rid)
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 422
    gst = await upload(exec_client, f"/api/lead-requests/{rid}/documents", "kyc_gst")
    assert gst.status_code == 200, gst.text
    # GST certificate is the GSTIN proof — the 15-digit number is optional.
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text


@pytest.mark.asyncio
async def test_b2b_gst_certificate_books_without_gstin_number(exec_client, client):
    r = await client.post("/api/leads", json={
        "customerName": "Kapoor Freight Carriers", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "customerType": "B2B", "budget": 200000})
    lid = r.json()["leadId"]
    blocked = await exec_client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-10-09", "bookingAmount": 0, "executive": "Executive"})
    assert blocked.status_code == 422, blocked.text
    assert "gstin" in blocked.text.lower() or "gst" in blocked.text.lower()
    pan = await upload(client, f"/api/leads/{lid}/documents", "kyc_pan")
    gst = await upload(client, f"/api/leads/{lid}/documents", "kyc_gst")
    assert pan.status_code == 200 and gst.status_code == 200
    ok = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-10-09", "bookingAmount": 0, "executive": "Executive"})
    assert ok.status_code == 200, ok.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert (lead.get("currentStatus") or "").lower() == "booked"


@pytest.mark.asyncio
async def test_staff_can_save_gstin_on_a_b2b_lead(exec_client, client):
    r = await client.post("/api/leads", json={
        "customerName": "GSTIN Save Co", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "customerType": "B2B"})
    lid = r.json()["leadId"]
    saved = await exec_client.put(f"/api/leads/{lid}/gstin", json={"gstin": "08abcde1234f1z5"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["gstin"] == "08ABCDE1234F1Z5"


@pytest.mark.asyncio
async def test_oem_cannot_read_documents(client, exec_client, oem):
    seeded = await seed_pending({
        "customerName": "Secret KYC", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Executive", "budget": 185000})
    rid = seeded["requestId"]
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
    by_name = (await client.get("/api/leads", params={"q": "Searchable", "limit": 8, "scope": "all"})).json()
    assert any(l["leadId"] == lid for l in by_name)
    by_mob = (await client.get("/api/leads", params={"q": "9876543210", "limit": 8, "scope": "all"})).json()
    assert any(l["leadId"] == lid for l in by_mob)
    by_id = (await client.get("/api/leads", params={"q": lid, "limit": 8, "scope": "all"})).json()
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


@pytest.mark.asyncio
async def test_tl_uploads_kyc_on_a_lead_for_any_executive(tl_client):
    r = await tl_client.post("/api/leads", json={
        "customerName": "TL KYC Other Exec", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Sanjay"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    assert r.json()["executive"] == "Sanjay"
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        up = await upload(tl_client, f"/api/leads/{lid}/documents", kind)
        assert up.status_code == 200, up.text
    docs = (await tl_client.get(f"/api/leads/{lid}/documents")).json()
    assert {d["kind"] for d in docs} == {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"}


@pytest.mark.asyncio
async def test_another_vehicle_copies_create_docs_not_delivery(client):
    mobile = next_mobile()
    first = await client.post("/api/leads", json={
        "customerName": "Fleet Buyer", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    assert first.status_code == 200, first.text
    lid1 = first.json()["leadId"]
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await upload(client, f"/api/leads/{lid1}/documents", kind)
        assert r.status_code == 200, r.text
    extra = await upload(client, f"/api/leads/{lid1}/documents", "oem_extra_support")
    assert extra.status_code == 200, extra.text
    sheet = await upload(client, f"/api/leads/{lid1}/documents", "deal_sheet")
    assert sheet.status_code == 200, sheet.text
    rto = await upload(client, f"/api/leads/{lid1}/documents", "delivery_rto")
    assert rto.status_code == 200, rto.text
    second = await client.post("/api/leads", json={
        "customerName": "Fleet Buyer", "mobile": mobile,
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit",
        "anotherVehicle": True})
    assert second.status_code == 200, second.text
    lid2 = second.json()["leadId"]
    assert lid2 != lid1
    docs2 = (await client.get(f"/api/leads/{lid2}/documents")).json()
    kinds = {d["kind"] for d in docs2}
    assert {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "oem_extra_support"} <= kinds
    assert "delivery_rto" not in kinds
    assert "deal_sheet" not in kinds
    assert all(d.get("copiedFromLeadId") == lid1 for d in docs2)
    assert all(d.get("documentId") for d in docs2)
    src_pan = next(d for d in (await client.get(f"/api/leads/{lid1}/documents")).json()
                   if d["kind"] == "kyc_pan")
    dst_pan = next(d for d in docs2 if d["kind"] == "kyc_pan")
    assert dst_pan["documentId"] != src_pan["documentId"]
    raw1 = await client.get(f"/api/documents/{src_pan['documentId']}/file")
    raw2 = await client.get(f"/api/documents/{dst_pan['documentId']}/file")
    assert raw1.content == raw2.content == PNG


@pytest.mark.asyncio
async def test_another_vehicle_with_extra_amount_copies_support_email(client):
    mobile = next_mobile()
    first = await client.post("/api/leads", json={
        "customerName": "Extra Fleet", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "oemExtraSupportReceived": 7000})
    assert first.status_code == 200, first.text
    lid1 = first.json()["leadId"]
    extra = await upload(client, f"/api/leads/{lid1}/documents", "oem_extra_support")
    assert extra.status_code == 200, extra.text
    second = await client.post("/api/leads", json={
        "customerName": "Extra Fleet", "mobile": mobile,
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit",
        "anotherVehicle": True, "oemExtraSupportReceived": 7000})
    assert second.status_code == 200, second.text
    lid2 = second.json()["leadId"]
    docs2 = (await client.get(f"/api/leads/{lid2}/documents")).json()
    hit = next(d for d in docs2 if d["kind"] == "oem_extra_support")
    assert hit["copiedFromLeadId"] == lid1
    raw = await client.get(f"/api/documents/{hit['documentId']}/file")
    assert raw.status_code == 200
    assert raw.content == PNG
    stored = await server.db.leads.find_one({"leadId": lid2})
    assert float(stored.get("oemExtraSupportReceived") or 0) == 7000


def test_octet_stream_jpeg_is_sniffed_as_photo():
    jpeg = b"\xff\xd8\xff" + b"\x00" * 80
    class Fake:
        content_type = "application/octet-stream"
        filename = "image"
    assert server.lead_docs._content_type(Fake(), kind="oem_extra_support", data=jpeg) == "image/jpeg"
    assert server.lead_docs._sniff_content_type(b"\x89PNG\r\n\x1a\n" + b"x") == "image/png"
    heic = b"\x00\x00\x00\x18ftypheic" + b"\x00" * 40
    assert server.lead_docs._sniff_content_type(heic) == "image/heic"
    assert server.lead_docs._content_type(Fake(), kind="kyc_pan", data=heic) == "image/heic"


@pytest.mark.asyncio
async def test_oem_extra_support_upload_accepts_nameless_jpeg(client):
    r = await client.post("/api/leads", json={
        "customerName": "Extra Proof", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    jpeg = b"\xff\xd8\xff" + b"\x00" * 200
    up = await upload_bytes(
        client, f"/api/leads/{lid}/documents", "oem_extra_support",
        jpeg, "image", "application/octet-stream")
    assert up.status_code == 200, up.text
    assert up.json()["kind"] == "oem_extra_support"
    assert up.json()["contentType"] == "image/jpeg"
    assert up.json()["filename"].endswith(".jpg")
    huge = b"\xff\xd8\xff" + b"\x00" * (8 * 1024 * 1024 + 10)
    denied = await upload_bytes(
        client, f"/api/leads/{lid}/documents", "oem_extra_support",
        huge, "photo.jpg", "image/jpeg")
    assert denied.status_code == 422, denied.text
    assert "8 MB" in denied.json()["detail"]


def test_tl_kyc_permissions_do_not_need_own_lead():
    tl = {"role": "tl", "name": "Docs TL"}
    exec_u = {"role": "executive", "name": "Amit"}
    assert server.lead_docs.can_upload_kind(tl, "kyc_pan", own=False) is True
    assert server.lead_docs.can_read_kind(tl, "kyc_pan", own=False) is True
    assert server.lead_docs.can_upload_kind(exec_u, "kyc_pan", own=False) is False
    assert server.lead_docs.can_upload_kind(exec_u, "kyc_pan", own=True) is True
    assert server.lead_docs.can_upload_kind(exec_u, "oem_extra_support", own=True) is True
    assert server.lead_docs.can_upload_kind(exec_u, "oem_extra_support", own=False) is False
    assert server.lead_docs.can_read_kind(tl, "oem_extra_support", own=False) is True
    assert server.lead_docs.can_upload_kind(exec_u, "deal_sheet", own=True) is True
    assert server.lead_docs.can_upload_kind(exec_u, "deal_sheet", own=False) is False
    assert server.lead_docs.can_read_kind(tl, "deal_sheet", own=False) is True


def _zip_bytes(name="tally-bill.pdf"):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, b"%PDF-1.4 tally")
    return buf.getvalue()


async def upload_bytes(c, url, kind, raw, name, content_type):
    return await c.post(
        url,
        files={"file": (name, io.BytesIO(raw), content_type)},
        data={"kind": kind},
    )


@pytest.mark.asyncio
async def test_tally_invoice_accepts_zip_kyc_rejects_zip(client, accounts_client):
    r = await client.post("/api/leads", json={
        "customerName": "Tally Zip", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    zipped = _zip_bytes()
    ok = await upload_bytes(
        accounts_client, f"/api/leads/{lid}/documents", "tally_invoice",
        zipped, "bills.zip", "application/zip")
    assert ok.status_code == 200, ok.text
    assert ok.json()["contentType"] == "application/zip"
    assert ok.json()["filename"].endswith(".zip")
    docs = (await accounts_client.get(f"/api/leads/{lid}/documents")).json()
    tally = [d for d in docs if d["kind"] == "tally_invoice"]
    assert len(tally) == 1
    raw = await accounts_client.get(f"/api/documents/{tally[0]['documentId']}/file")
    assert raw.status_code == 200
    assert raw.content[:2] == b"PK"
    denied = await upload_bytes(
        client, f"/api/leads/{lid}/documents", "kyc_pan",
        zipped, "kyc.zip", "application/zip")
    assert denied.status_code == 422, denied.text
    fake = await upload_bytes(
        accounts_client, f"/api/leads/{lid}/documents", "tally_invoice",
        b"not-a-zip", "bills.zip", "application/zip")
    assert fake.status_code == 422, fake.text


@pytest.mark.asyncio
async def test_showroom_admin_lead_register_includes_new(client, tl_client):
    """OEM billing / approvals land as New — Showroom Admin must still see them."""
    fresh = await client.post("/api/leads", json={
        "customerName": "OEM Billing New", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    live = await client.post("/api/leads", json={
        "customerName": "Approved Contact", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    new_id, live_id = fresh.json()["leadId"], live.json()["leadId"]
    await server.db.leads.update_one(
        {"leadId": new_id}, {"$set": {"oemBillingCreated": True}})
    await server.db.leads.update_one(
        {"leadId": live_id}, {"$set": {"currentStatus": "Contacted"}})
    tl_all = (await tl_client.get("/api/leads", params={"followup": True})).json()
    tl_ids = {row["leadId"] for row in tl_all}
    assert new_id in tl_ids
    assert live_id in tl_ids
    assert any(row["leadId"] == new_id and row.get("currentStatus") == "New" for row in tl_all)
    only_new = (await tl_client.get("/api/leads", params={"status": "New", "followup": True})).json()
    assert any(row["leadId"] == new_id for row in only_new)
    contacted = (await tl_client.get("/api/leads", params={"status": "Contacted", "followup": True})).json()
    assert any(row["leadId"] == live_id for row in contacted)


@pytest.mark.asyncio
async def test_showroom_admin_register_flags_exact_delivery_gaps(client, tl_client):
    r = await client.post("/api/leads", json={
        "customerName": "Gap Flag", "mobile": next_mobile(),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Booked", "bookingDate": "2026-10-01",
        "exShowroom": 0, "customerOutstanding": 2500,
    }})
    owner = next(row for row in (await client.get("/api/leads")).json() if row["leadId"] == lid)
    assert "needsUpdate" not in owner
    tl_row = next(row for row in (await tl_client.get("/api/leads")).json() if row["leadId"] == lid)
    assert tl_row["needsUpdate"] is True
    messages = [f["message"] for f in tl_row["updateFlags"]]
    assert any("KYC missing" in m for m in messages)
    assert any("Deal sheet" in m for m in messages)
    assert any("Price Structure" in m for m in messages)
    assert any("outstanding" in m.lower() for m in messages)
    dash = (await tl_client.get("/api/executive/dashboard")).json()
    assert dash["kpis"]["needsUpdate"] >= 1
    assert any(q["leadId"] == lid for q in dash.get("updateQueue") or [])
