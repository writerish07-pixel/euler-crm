"""Scheme Claim Register is a permanent ledger — never archived.

Even after OEM payment is Received, claim rows stay forever on the Google Sheet
and in GET /claims. Go-live reset and owner lead-delete must not remove them.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "claim_register_permanent")
os.environ.setdefault("JWT_SECRET", "claim-permanent-secret")
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET_CLAIMS_PERM")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import gsheets  # noqa: E402
import server  # noqa: E402


def test_scheme_claim_register_is_permanent_ledger():
    tab = gsheets.SYNC_MAP["claims"][0]
    assert tab == "Scheme Claim Register"
    assert gsheets.is_permanent_ledger_tab(tab)
    assert tab in gsheets.PERMANENT_LEDGER_TABS
    assert tab not in gsheets.OPERATIONAL_CLEAR_TABS
    # Go-live wipe list must never include the claim register.
    assert all(t != tab for t in gsheets.OPERATIONAL_CLEAR_TABS)


@pytest_asyncio.fixture
async def client(monkeypatch):
    await server.startup()
    syncs = []

    async def capture_sync(entity, doc):
        syncs.append({"entity": entity, "doc": dict(doc)})
        return {"ok": True, "operation": "updated", "tab": "Scheme Claim Register"}

    monkeypatch.setattr(server, "sheet_sync", capture_sync)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        c.syncs = syncs
        yield c


@pytest.mark.asyncio
async def test_claim_receipt_updates_status_does_not_delete_row(client):
    """Recording Received money only upserts Status/amounts — never removes the claim."""
    # Manual claim: receipt path does not recompute scheme shares (eligible stays stored).
    await server.db.claims.insert_one({
        "claimId": "CLM-PERM-1", "leadId": "LD_PERM", "componentKey": "CLM-PERM-1",
        "manual": True, "claimAmount": 10000, "eligibleClaim": 10000,
        "claimStatus": "Submitted", "receivedAmount": 0, "submittedDate": "2026-08-01",
        "customer": "Permanent Claim", "model": "Turbo", "component": "OEM Incentive",
    })

    r = await client.post("/api/claims/receipt", json={
        "leadId": "LD_PERM", "componentKey": "CLM-PERM-1",
        "amount": 10000, "date": "2026-08-20", "reference": "OEM-RX-1",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "Received"
    assert body["receivedAmount"] == 10000

    claim_syncs = [s for s in client.syncs if s["entity"] == "claims"]
    assert claim_syncs, "receipt must upsert Scheme Claim Register"
    last = claim_syncs[-1]["doc"]
    assert last["claimId"] == "CLM-PERM-1"
    assert last["claimStatus"] == "Received"
    assert last["receivedAmount"] == 10000
    # No delete / archive signal — sync is always an upsert payload.
    assert "delete" not in last and "archived" not in last

    stored = await server.db.claims.find_one({"claimId": "CLM-PERM-1"})
    assert stored["claimStatus"] == "Received"
    assert stored["receivedAmount"] == 10000

    claims = (await client.get("/api/claims")).json()
    hit = [c for c in claims if c.get("claimId") == "CLM-PERM-1"]
    assert hit, "Received claim must remain in GET /claims forever"
    assert hit[0]["claimStatus"] == "Received"
    assert hit[0]["receivedAmount"] == 10000


@pytest.mark.asyncio
async def test_received_scheme_claim_survives_when_lead_leaves_register_filter(client):
    """Persisted Received scheme claim stays in GET /claims even if lead status drops out."""
    await server.db.claims.insert_one({
        "claimId": "CLM-PERM-SCHEME", "leadId": "LD_GONE", "componentKey": "loyaltyBonus",
        "claimAmount": 8000, "eligibleClaim": 8000, "claimStatus": "Received",
        "receivedAmount": 8000, "submittedDate": "2026-07-01", "claimReceivedDate": "2026-07-15",
        "customer": "Gone Lead", "model": "Turbo", "component": "Loyalty",
    })
    await server.db.leads.insert_one({
        "leadId": "LD_GONE", "customerName": "Gone Lead",
        "interestedModel": "Turbo", "variant": "XR",
        "currentStatus": "Lost", "accountStatus": "Closed",
    })
    claims = (await client.get("/api/claims")).json()
    hit = [c for c in claims if c.get("claimId") == "CLM-PERM-SCHEME"]
    assert hit
    assert hit[0]["claimStatus"] == "Received"
    assert hit[0]["receivedAmount"] == 8000
    assert hit[0].get("permanent") is True
