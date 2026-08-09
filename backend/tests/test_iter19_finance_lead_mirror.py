"""Finance linkage is mirrored onto the lead, and reconciliation detects the
four sheet-vs-app defect classes.

Defect C: the Lead Register maps `financerName` / `financeFileNumber` as LEAD
columns, but a Finance payment only ever wrote them onto the finance file, so the
lead row in the sheet stayed blank while the Finance Register showed the file.

Runs the real app in-process against mongomock, so the actual route handlers
execute — no HTTP server and no Google needed (sheet sync is disabled here).
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter19mirror")
os.environ.setdefault("JWT_SECRET", "iter19-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Hi-Load", "XR"          # the HiCity row in Price Master


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked_lead(c, mobile):
    r = await c.post("/api/leads", json={
        "customerName": "ITER19 Finance Mirror", "mobile": mobile,
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    lead_id = r.json()["leadId"]
    await c.put(f"/api/leads/{lead_id}/price-structure", json={
        "exShowroom": 300000, "rto": 20000, "insuranceAmount": 15000})
    await c.post(f"/api/leads/{lead_id}/convert-booking",
                 json={"bookingDate": "2026-08-08", "bookingAmount": 0})
    return lead_id


@pytest.mark.asyncio
async def test_finance_payment_mirrors_financer_and_file_onto_the_lead(client):
    """DEFECT C: after a Finance receipt the LEAD must carry the financer and file
    number, because those are Lead Register columns."""
    lead_id = await _booked_lead(client, "9333300001")

    r = await client.post(f"/api/leads/{lead_id}/payments", json={
        "amount": 200000, "paymentMode": "Finance", "financerName": "HDFC Bank"})
    assert r.status_code == 200, r.text
    file_number = r.json()["financeFileNumber"]
    assert file_number

    lead = (await client.get(f"/api/leads/{lead_id}")).json()
    assert lead["financerName"] == "HDFC Bank"
    assert lead["financeFileNumber"] == file_number
    assert lead["financeRequired"] == "Yes"


@pytest.mark.asyncio
async def test_finance_file_and_lead_agree_after_a_financer_receipt(client):
    """A receipt against the file must not desynchronise the lead mirror."""
    lead_id = await _booked_lead(client, "9333300002")
    r = await client.post(f"/api/leads/{lead_id}/payments", json={
        "amount": 200000, "paymentMode": "Finance", "financerName": "ICICI Bank"})
    file_number = r.json()["financeFileNumber"]

    r = await client.post(f"/api/finance/{file_number}/receipt",
                          json={"amount": 80000, "date": "2026-08-08"})
    assert r.status_code == 200, r.text
    assert r.json()["receivedAgainstFile"] == 80000
    assert r.json()["fileOutstanding"] == 120000

    lead = (await client.get(f"/api/leads/{lead_id}")).json()
    assert lead["financeFileNumber"] == file_number
    assert lead["financerName"] == "ICICI Bank"


@pytest.mark.asyncio
async def test_finance_payment_without_a_financer_is_still_refused(client):
    """The mirror fix must not weaken the existing requirement."""
    lead_id = await _booked_lead(client, "9333300003")
    r = await client.post(f"/api/leads/{lead_id}/payments",
                          json={"amount": 1000, "paymentMode": "Finance"})
    assert r.status_code == 422
    assert "Financer is required" in r.text


@pytest.mark.asyncio
async def test_rebuild_finance_views_is_a_noop_when_sync_is_disabled(client):
    """Sheets is not configured in tests — rebuilding must not raise, so finance
    payments keep working when the sheet is unreachable."""
    lead_id = await _booked_lead(client, "9333300004")
    await client.post(f"/api/leads/{lead_id}/payments", json={
        "amount": 150000, "paymentMode": "Finance", "financerName": "Axis Bank"})
    out = await server.rebuild_finance_views()
    assert out["pending"] >= 1
    assert out["syncedPending"] is False        # disabled, not crashed
    assert out["syncedOverdue"] is False


@pytest.mark.asyncio
async def test_env_safety_endpoint_is_owner_gated(client):
    r = await client.get("/api/integrations/gsheets/env-safety")
    assert r.status_code == 200
    assert "writeBlocked" in r.json()

    r2 = await client.post("/api/auth/login",
                           json={"email": "executive@euler.com", "password": "euler@123"})
    exec_hdr = {"Authorization": f"Bearer {r2.json()['token']}"}
    for path in ("env-safety", "inventory", "reconcile"):
        r3 = await client.get(f"/api/integrations/gsheets/{path}", headers=exec_hdr)
        assert r3.status_code == 403, f"{path} must be owner-only, got {r3.status_code}"
