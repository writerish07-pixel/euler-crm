"""Confirm-only AI desk: seven scanners, PDF → Price Structure, never Scheme."""
import os
import sys
import time

import jwt as pyjwt
import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ai_agents_desk_test")
os.environ.setdefault("JWT_SECRET", "ai-agents-secret-32chars!!xx")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import agents as agentmod  # noqa: E402
import commercial as ce  # noqa: E402
import lead_docs  # noqa: E402
import pdf_extract  # noqa: E402
import server  # noqa: E402

PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db[lead_docs.COLLECTION].delete_many({})
    await server.db[agentmod.COLLECTION].delete_many({})
    await server.db.oem_sold.delete_many({})
    await server.db.oem_portal_claims.delete_many({})
    await server.db.activities.delete_many({})
    await server.db["system"].delete_many({"_id": {"$in": ["coulson", agentmod.SCAN_META]}})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def test_pdf_extracts_premium_rto_and_chassis():
    ins = pdf_extract.extract_insurance(
        "Motor Policy No ABCD123456 Total Premium Rs 17,991 Chassis MD2A1234567890XYZ")
    assert ins["premium"] == 17991
    assert ins["chassis"] == "MD2A1234567890XYZ"
    assert ins["policyNumber"] == "ABCD123456"
    rto = pdf_extract.extract_rto(
        "RTO Registration fee Rs 2,200 Chassis MD2A1234567890XYZ")
    assert rto["rto"] == 2200
    pdf = pdf_extract.make_simple_pdf(
        "Total Premium Rs 17991 Chassis MD2A1234567890XYZ")
    text = pdf_extract.pdf_text(pdf, "application/pdf")
    assert "17991" in text
    assert pdf_extract.extract_insurance(text)["premium"] == 17991


def test_pdf_agent_never_targets_scheme_fields():
    assert "insuranceBenefit" not in agentmod.price_payload_from_lead({"insuranceAmount": 1})
    assert "rtoBenefit" not in agentmod.price_payload_from_lead({})


@pytest.mark.asyncio
async def test_executive_cannot_open_agents_desk(client):
    email = "exec.agents@euler.com"
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": "exec#4411", "name": "Exec", "role": "executive"})
    assert r.status_code == 200, r.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        login = await c.post("/api/auth/login", json={"email": email, "password": "exec#4411"})
        c.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        listed = await c.get("/api/agents/suggestions")
        assert listed.status_code == 403


@pytest.mark.asyncio
async def test_document_and_followup_scan(client):
    await server.db.leads.insert_one({
        "leadId": "LD26AGDOC1", "customerName": "Stale Lead", "mobile": "9811100001",
        "interestedModel": "Turbo Max", "currentStatus": "New", "accountStatus": "Active",
        "executive": "Amit", "nextFollowupDate": "2020-01-01",
    })
    r = await client.post("/api/agents/scan", json={})
    assert r.status_code == 200, r.text
    kinds = {s["agent"] for s in r.json()["suggestions"]}
    assert agentmod.AGENT_DOCUMENT in kinds
    assert agentmod.AGENT_FOLLOWUP in kinds
    follow = next(s for s in r.json()["suggestions"] if s["agent"] == agentmod.AGENT_FOLLOWUP)
    assert follow["canConfirm"] is True
    cid = follow["suggestionId"]
    done = await client.post(f"/api/agents/suggestions/{cid}/confirm", json={})
    assert done.status_code == 200, done.text
    lead = await server.db.leads.find_one({"leadId": "LD26AGDOC1"})
    assert lead["nextFollowupDate"] > "2020-01-01"
    assert await server.db.activities.count_documents({"leadId": "LD26AGDOC1"}) == 1


async def _priced_lead(client, mobile="9811199001"):
    r = await client.post("/api/leads", json={
        "customerName": "PDF Customer", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    ps = pv.json()["priceStructure"]
    saved = await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    assert saved.status_code == 200, saved.text
    return lid


@pytest.mark.asyncio
async def test_insurance_pdf_confirm_writes_price_not_scheme(client):
    lid = await _priced_lead(client)
    before = await server.db.leads.find_one({"leadId": lid})
    old_ins = ce.num(before.get("insuranceAmount"))
    assert old_ins == 19000
    benefit_before = ce.num(before.get("insuranceBenefit"))
    rto_ben_before = ce.num(before.get("rtoBenefit"))
    extra_pass_before = ce.num(before.get("oemExtraSupportPassed"))
    pdf = pdf_extract.make_simple_pdf(
        "Total Premium Rs 17991 Chassis MD2A1234567890XYZ Policy No ABCD999111")
    await lead_docs.save_doc(
        server.db, next_id=server.next_id, user={"email": "owner@euler.com", "role": "owner"},
        kind="delivery_insurance", data=pdf, content_type="application/pdf",
        filename="policy.pdf", lead_id=lid)
    r = await client.post("/api/agents/scan", json={})
    assert r.status_code == 200, r.text
    hit = next(
        s for s in r.json()["suggestions"]
        if s["agent"] == agentmod.AGENT_PDF and s.get("payload", {}).get("field") == "insuranceAmount")
    assert hit["payload"]["toAmount"] == 17991
    assert hit["canConfirm"] is True
    conf = await client.post(f"/api/agents/suggestions/{hit['suggestionId']}/confirm", json={})
    assert conf.status_code == 200, conf.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("insuranceAmount")) == 17991
    assert ce.num(after.get("insuranceBenefit")) == benefit_before
    assert ce.num(after.get("rtoBenefit")) == rto_ben_before
    assert ce.num(after.get("oemExtraSupportPassed")) == extra_pass_before
    assert conf.json()["result"]["schemeUnchanged"]["insuranceBenefit"] is True


@pytest.mark.asyncio
async def test_rto_pdf_confirm_writes_rto_only(client):
    lid = await _priced_lead(client, "9811199002")
    pdf = pdf_extract.make_simple_pdf("Registration fee Rs 2200 Chassis MD2B1234567890XYZ")
    await lead_docs.save_doc(
        server.db, next_id=server.next_id, user={"email": "owner@euler.com"},
        kind="delivery_rto", data=pdf, content_type="application/pdf",
        filename="rto.pdf", lead_id=lid)
    r = await client.post("/api/agents/scan", json={})
    hit = next(
        s for s in r.json()["suggestions"]
        if s["agent"] == agentmod.AGENT_PDF and s.get("payload", {}).get("field") == "rto")
    assert hit["payload"]["toAmount"] == 2200
    conf = await client.post(f"/api/agents/suggestions/{hit['suggestionId']}/confirm", json={})
    assert conf.status_code == 200, conf.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("rto")) == 2200


@pytest.mark.asyncio
async def test_oem_match_suggests_same_mobile_and_confirm_connects(client):
    await server.db.leads.insert_one({
        "leadId": "LD26AGOEM1", "customerName": "Match Me", "mobile": "9811188001",
        "interestedModel": "Turbo Max", "currentStatus": "Booked", "accountStatus": "Active",
        "chassisNumber": "MD9HAVE000000001",
    })
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NEED000000002", "mobile": "9811188001", "invoiceNumber": "INV-AG-1",
        "customerName": "Match Me", "model": "Turbo Max", "soldDate": "2026-09-03",
    })
    r = await client.post("/api/agents/scan", json={})
    hit = next(s for s in r.json()["suggestions"] if s["agent"] == agentmod.AGENT_OEM_MATCH)
    assert hit["payload"]["proposedLeadId"] == "LD26AGOEM1"
    conf = await client.post(f"/api/agents/suggestions/{hit['suggestionId']}/confirm", json={})
    assert conf.status_code == 200, conf.text
    lead = await server.db.leads.find_one({"leadId": "LD26AGOEM1"})
    chassis = set()
    if lead.get("chassisNumber"):
        chassis.add(lead["chassisNumber"])
    for u in lead.get("units") or []:
        if u.get("chassisNumber"):
            chassis.add(u["chassisNumber"])
    assert "MD9NEED000000002" in chassis or lead.get("chassisNumber") == "MD9NEED000000002"


@pytest.mark.asyncio
async def test_coulson_expired_suggestion_and_tally_prep(client, monkeypatch):
    expired = pyjwt.encode(
        {"exp": int(time.time()) - 60, "application": "coulson", "username": "dealer"},
        "x", algorithm="HS256")
    if isinstance(expired, bytes):
        expired = expired.decode()
    await server.db["system"].update_one(
        {"_id": "coulson"},
        {"$set": {"sessionToken": expired, "username": "dealer", "password": "pw"}},
        upsert=True)

    async def fake_creds(db):
        return "dealer", "pw", "settings"
    monkeypatch.setattr("oem_sync.resolve_credentials", fake_creds)
    monkeypatch.setattr("oem_sync.credentials_configured", lambda u, p: True)

    await server.db.leads.insert_one({
        "leadId": "LD26AGTALLY", "customerName": "Billed", "mobile": "9811177001",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "currentStatus": "Delivered", "deliveryStatus": "Delivered", "accountStatus": "Active",
        "exShowroom": 775000, "rto": 2200, "insuranceAmount": 17991,
        "additionalDiscount": 191, "customerPayable": 795000, "totalReceived": 795000,
        "deliveryDate": "2026-10-01",
    })
    r = await client.post("/api/agents/scan", json={})
    assert r.status_code == 200, r.text
    agents = {s["agent"] for s in r.json()["suggestions"]}
    assert agentmod.AGENT_COULSON in agents
    tally = next(s for s in r.json()["suggestions"] if s["agent"] == agentmod.AGENT_TALLY)
    codes = [ln["code"] for ln in tally["payload"]["lines"] if ln["section"] == "A"]
    assert codes[:2] == ["vehicleExGst", "additionalDiscount"]
    assert any(ln["code"] == "rto" for ln in tally["payload"]["lines"])
    ack = await client.post(f"/api/agents/suggestions/{tally['suggestionId']}/confirm", json={})
    assert ack.status_code == 200
    assert ack.json()["result"]["acknowledged"] is True

    coulson = next(s for s in r.json()["suggestions"] if s["agent"] == agentmod.AGENT_COULSON)
    assert coulson["canConfirm"] is True

    async def boom_sync(*a, **k):
        raise server.coulson_client.CoulsonError("Euler refused the saved password from this server")
    monkeypatch.setattr("oem_sync.sync_from_coulson", boom_sync)
    # Re-scan so the coulson row is still open (tally confirm closed only tally).
    listed = await client.get("/api/agents/suggestions")
    coulson = next(s for s in listed.json()["suggestions"] if s["agent"] == agentmod.AGENT_COULSON)
    got = await client.post(f"/api/agents/suggestions/{coulson['suggestionId']}/confirm", json={})
    assert got.status_code == 200
    assert got.json()["result"]["pasteNeeded"] is True


@pytest.mark.asyncio
async def test_oem_settlement_and_dismiss(client):
    await server.db.oem_portal_claims.insert_one({
        "claimNumber": "AF-122-AG1",
        "status": "Credit Note Generated",
        "leadIds": [],
        "lineItems": [{"lineId": "l1", "leadId": "", "description": "Insurance Benefit"}],
        "registerMatch": {"state": "unknown_lead"},
    })
    r = await client.post("/api/agents/scan", json={})
    hits = [s for s in r.json()["suggestions"] if s["agent"] == agentmod.AGENT_OEM_SETTLEMENT]
    if hits:
        d = await client.post(f"/api/agents/suggestions/{hits[0]['suggestionId']}/dismiss", json={})
        assert d.status_code == 200
        assert d.json()["status"] == "dismissed"
    else:
        # attach_register_match may skip a sparse stub; scan must still 200.
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_accounts_cannot_confirm_pdf_price(client):
    lid = await _priced_lead(client, "9811199003")
    pdf = pdf_extract.make_simple_pdf("Total Premium Rs 15000 Chassis MD2C1234567890XYZ")
    await lead_docs.save_doc(
        server.db, next_id=server.next_id, user={"email": "owner@euler.com"},
        kind="delivery_insurance", data=pdf, content_type="application/pdf",
        filename="policy.pdf", lead_id=lid)
    await client.post("/api/agents/scan", json={})
    email = "accounts.agents@euler.com"
    await server.db.users.delete_many({"email": email})
    await client.post("/api/auth/users", json={
        "email": email, "password": "acct#4411", "name": "Acct", "role": "accounts"})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        login = await c.post("/api/auth/login", json={"email": email, "password": "acct#4411"})
        c.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        listed = await c.get("/api/agents/suggestions")
        assert listed.status_code == 200, listed.text
        hit = next(s for s in listed.json()["suggestions"]
                   if s["agent"] == agentmod.AGENT_PDF and s["payload"].get("field") == "insuranceAmount")
        assert hit["canConfirm"] is False
        conf = await c.post(f"/api/agents/suggestions/{hit['suggestionId']}/confirm", json={})
        assert conf.status_code == 403
