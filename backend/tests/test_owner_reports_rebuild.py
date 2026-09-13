"""Owner commercial reports use scheme allocation, period, and Rebuild."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "owner_reports_rebuild")
os.environ.setdefault("JWT_SECRET", "owner-reports-rebuild-secret")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.claims.delete_many({})
    await server.db.scheme_master.delete_many({})
    await server.db.scheme_master.insert_many([
        {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-01", "effectiveTo": "2026-08-31",
         "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
         "dealerShare": 5000, "companyShare": 10000, "totalBenefit": 15000, "status": "Active"},
        {"schemeMonth": "2026-08", "effectiveFrom": "2026-08-01", "effectiveTo": "2026-08-31",
         "model": "Turbo", "variant": "", "componentKey": "insuranceBenefit", "component": "Insurance Benefit",
         "dealerShare": 0, "companyShare": 20000, "totalBenefit": 20000, "status": "Active"},
    ])
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _booked(lead_id, *, booking_date, breakup, received=0):
    await server.db.leads.insert_one({
        "leadId": lead_id, "customerName": lead_id, "mobile": "98" + lead_id[-8:].zfill(8),
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit",
        "accountStatus": "Active", "currentStatus": "Booked", "bookingDate": booking_date,
        "customerPayable": 485000, "totalReceived": received,
        "schemeAllocation": {
            "benefitPassedBreakup": breakup,
            "schemeComponentsUsed": {k: (v > 0) for k, v in breakup.items()},
        },
        "schemeAllocationExplicit": True,
        "benefitPassedBreakup": breakup,
        "schemeComponentsUsed": {k: (v > 0) for k, v in breakup.items()},
    })
    if received:
        await server.db.claims.insert_one({
            "leadId": lead_id, "received": received, "receivedAmount": received,
            "claimStatus": "Received", "statuses": ["Received"],
        })


@pytest.mark.asyncio
async def test_owner_commercial_uses_allocation_not_offer_boxes(client):
    await _booked("LD-OCR-1", booking_date="2026-08-10",
                  breakup={"loyaltyBonus": 10000, "insuranceBenefit": 20000})
    r = await client.get("/api/reports/owner-commercial")
    assert r.status_code == 200, r.text
    o = r.json()["discountOwnership"]
    assert o["totalBookings"] == 1
    assert o["totalDiscountGiven"] > 0
    # Customer benefit + scheme retained = OEM share + dealer-funded given.
    assert o["totalDiscountGiven"] + o["schemeIncomeRetained"] == pytest.approx(
        o["oemFunded"] + o["dealerShareGiven"])
    # Staff-typed offer boxes are not the source — OEM-funded must include
    # entitlement components (Insurance Benefit), not only Loyalty.
    assert o["oemFunded"] >= 10000


@pytest.mark.asyncio
async def test_owner_commercial_period_and_pending_remainder(client):
    await _booked("LD-OCR-AUG", booking_date="2026-08-10",
                  breakup={"loyaltyBonus": 10000, "insuranceBenefit": 0}, received=4000)
    await _booked("LD-OCR-SEP", booking_date="2026-09-02",
                  breakup={"loyaltyBonus": 10000, "insuranceBenefit": 0})
    all_time = (await client.get("/api/reports/owner-commercial")).json()
    assert all_time["bookings"] == 2
    aug = (await client.get("/api/reports/owner-commercial", params={"month": "2026-08"})).json()
    assert aug["bookings"] == 1
    assert aug["period"]["month"] == "2026-08"
    assert aug["claimPosition"]["receivedValue"] == 4000
    pending = max(0.0, aug["discountOwnership"]["oemReceivable"] - 4000)
    assert aug["claimPosition"]["pendingValue"] == pytest.approx(pending)
    assert aug["claimPosition"]["pendingClaims"] == (1 if pending > 0.01 else 0)


@pytest.mark.asyncio
async def test_rebuild_recomputes_commercial_leads(client):
    await _booked("LD-REB-1", booking_date="2026-08-12",
                  breakup={"loyaltyBonus": 0, "insuranceBenefit": 0})
    r = await client.post("/api/reports/rebuild")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert body["recomputed"] >= 1
    assert body["failed"] == 0


@pytest.mark.asyncio
async def test_need_to_order_is_open_booking_without_yard(client):
    await server.db.oem_inventory.delete_many({})
    await server.db.leads.insert_one({
        "leadId": "LD-NTO-1", "customerName": "Need Order",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-01", "customerPayable": 480000,
    })
    await server.db.leads.insert_one({
        "leadId": "LD-NTO-HAS", "customerName": "Has Stock",
        "interestedModel": "Storm", "variant": "Storm LR",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-01",
    })
    await server.db.oem_inventory.insert_one({
        "chassis": "MD9HAS1", "model": "Storm", "variant": "Storm LR"})
    rows = (await client.get("/api/inventory/need-to-order")).json()
    ids = [r["leadId"] for r in rows]
    assert "LD-NTO-1" in ids
    assert "LD-NTO-HAS" not in ids
    summary = (await client.get("/api/inventory/summary")).json()
    assert summary["needToOrder"] >= 1
    transit = (await client.get("/api/inventory/transit")).json()
    assert isinstance(transit, list)
