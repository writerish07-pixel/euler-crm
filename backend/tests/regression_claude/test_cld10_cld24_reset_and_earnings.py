"""CLD-10 and CLD-24 regression guards.

CLD-10: the go-live reset restarts lead ids at LD26000001. A new LD26000001
must not inherit the previous holder's KYC documents or WhatsApp history.

CLD-24: Dealer Earnings is computed twice — on the lead (recompute_lead) and in
GET /dealer-earnings. The two totals must agree for the same lead.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld10_cld24")
os.environ.setdefault("JWT_SECRET", "cld10-cld24-reset-earnings-secret-32")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

OWNER = ("cld1024-owner@euler.com", "cld1024-owner-pass")
AUTH_DB = server.db


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["cld10_cld24_isolated"]
    monkeypatch.setattr(server, "db", isolated)
    await server.startup()
    await AUTH_DB.users.update_one(
        {"email": OWNER[0]},
        {"$set": {"email": OWNER[0], "name": "CLD Owner", "role": "owner",
                  "userId": "cld1024-owner",
                  "passwordHash": server.authmod.hash_password(OWNER[1])}},
        upsert=True)

    async def noop_sync(*a, **k):
        return {"ok": True, "operation": "skipped"}

    monkeypatch.setattr(server, "sheet_sync", noop_sync)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": OWNER[0], "password": OWNER[1]})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked_lead(client, mobile):
    r = await client.post("/api/leads", json={
        "customerName": f"CLD {mobile[-4:]}", "mobile": mobile,
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Amit", "leadSource": "Walk-in"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    pv = await client.get(f"/api/leads/{lid}/price-preview")
    assert pv.json().get("found"), pv.text
    r = await client.put(f"/api/leads/{lid}/price-structure", json=pv.json()["priceStructure"])
    assert r.status_code == 200, r.text
    r = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-11-09", "bookingAmount": 1000, "paymentMode": "Cash",
        "financeRequired": "No", "exchangeRequired": "No"})
    assert r.status_code == 200, r.text
    return lid


@pytest.mark.asyncio
async def test_cld24_lead_and_report_dealer_earnings_agree(client):
    lid = await _booked_lead(client, "9814400101")
    r = await client.put(f"/api/leads/{lid}/extra-income",
                         json={"documentationIncome": 1500, "warrantyIncome": 2000})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(lead["extraDealerIncomeTotal"]) == 3500
    report = (await client.get("/api/dealer-earnings")).json()
    row = next(x for x in report["rows"] if x["leadId"] == lid)
    assert ce.round2(ce.num(row["totalDealerEarnings"])) == ce.round2(ce.num(lead["dealerTotalEarnings"]))
    assert ce.num(lead["dealerTotalEarnings"]) > 0


@pytest.mark.asyncio
async def test_cld10_reset_leaves_no_documents_or_chats_for_reused_id(client):
    await _booked_lead(client, "9814400102")
    old = "LD26000001"
    await server.db[server.lead_docs.COLLECTION].insert_one(
        {"leadId": old, "kind": "kyc_pan", "filename": "previous-holder.png"})
    await server.db.whatsapp_messages.insert_one({"leadId": old, "text": "previous holder chat"})
    await server.db.whatsapp_threads.insert_one({"leadId": old})
    await server.db.lead_requests.insert_one({"leadId": old, "requestId": "REQ-OLD"})
    r = await client.post("/api/admin/reset-transactions")
    assert r.status_code == 200, r.text
    created = await client.post("/api/leads", json={
        "customerName": "After Reset", "mobile": "9814400103",
        "interestedModel": "Hi-Load", "variant": "SR (FB120)",
        "executive": "Amit", "leadSource": "Walk-in"})
    assert created.status_code == 200, created.text
    new_id = created.json()["leadId"]
    assert new_id == old
    assert await server.db[server.lead_docs.COLLECTION].count_documents({"leadId": new_id}) == 0
    assert await server.db.whatsapp_messages.count_documents({"leadId": new_id}) == 0
    assert await server.db.whatsapp_threads.count_documents({"leadId": new_id}) == 0
    assert await server.db.lead_requests.count_documents({"leadId": new_id}) == 0
