"""Nov 2026 Retail Consumer Scheme EM/11-2026/001 — sold date and future bookings."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "nov_2026_schemes_v1")
os.environ.setdefault("JWT_SECRET", "nov-2026-schemes-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import nov_2026_schemes as novs  # noqa: E402
import oct_2026_schemes as octs  # noqa: E402
import scheme_circulars  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def db():
    await server.startup()
    await server.db.scheme_master.delete_many({})
    yield server.db
    await server.db.scheme_master.delete_many({})


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _shares(rows, model, variant, on):
    return ce.get_scheme_shares_for_lead(model, variant, on, rows)


@pytest.mark.asyncio
async def test_nov_circular_amounts_do_not_use_october(db):
    await octs.ensure_oct_2026_schemes(db)
    first = await novs.ensure_nov_2026_schemes(db)
    assert first["inserted"] == len(novs.nov_2026_scheme_rows())
    second = await novs.ensure_nov_2026_schemes(db)
    assert second["inserted"] == 0
    assert second["unchanged"] == first["inserted"]

    rows = [r async for r in db.scheme_master.find()]
    storm = _shares(rows, "Storm", "Storm LR (PV)", "2026-11-06")
    assert storm["consumerDiscount"]["companyShare"] == 25000
    assert storm["consumerDiscount"]["dealerShare"] == 0
    assert storm["loyaltyBonus"]["companyShare"] == 10000
    assert "insuranceBenefit" not in storm

    hiload = _shares(rows, "HiLoad", "Non-GBT", "2026-11-04")
    assert hiload["insuranceBenefit"]["companyShare"] == 10000
    assert hiload["loyaltyBonus"]["companyShare"] == 10000
    assert "consumerDiscount" not in hiload

    hicity = _shares(rows, "Hi-Load", "XR", "2026-11-18")
    assert hicity["insuranceBenefit"]["totalBenefit"] == 10000
    assert hicity["loyaltyBonus"]["totalBenefit"] == 10000

    turbo = _shares(rows, "Turbo", "Maxx", "2026-11-12")
    assert turbo == {}
    after = _shares(rows, "Storm", "Storm LR (PV)", "2026-12-01")
    assert after == {}

    stored = await db.scheme_master.find_one({
        "schemeMonth": "2026-11", "model": "Storm", "componentKey": "consumerDiscount",
    })
    assert stored["circularRef"] == "EM/11-2026/001"
    assert stored["effectiveFrom"] == "2026-11-01"
    assert stored["effectiveTo"] == "2026-11-30"


def test_november_circular_picture():
    pic = scheme_circulars.for_date("2026-11-04")
    assert pic["ref"] == "EM/11-2026/001"
    assert pic["imageUrl"].endswith("/scheme-circulars/2026-11.png")
    assert pic["pdfUrl"].endswith("/scheme-circulars/2026-11.pdf")
    assert scheme_circulars.for_date("2026-10-31")["ref"] == "EM/10-2026/003"
    assert scheme_circulars.for_date("2026-12-01") is None


@pytest.mark.asyncio
async def test_sold_and_future_leads_take_november_scheme(client):
    await novs.ensure_nov_2026_schemes(server.db)
    sold_id = "LD-NOV-SOLD"
    future_id = "LD-NOV-FUTURE"
    oct_id = "LD-NOV-STILL-OCT"
    await server.db.leads.delete_many({"leadId": {"$in": [sold_id, future_id, oct_id]}})
    await server.db.leads.insert_many([
        {
            "leadId": sold_id, "customerName": "Nov Sold", "mobile": "9811101101",
            "interestedModel": "Storm", "variant": "Storm LR (PV)",
            "accountStatus": "Active", "currentStatus": "Booked",
            "bookingDate": "2026-10-20",
            "units": [{"sno": 1, "model": "Storm", "variant": "Storm LR (PV)",
                       "soldDate": "2026-11-06"}],
        },
        {
            "leadId": future_id, "customerName": "Nov Future", "mobile": "9811101102",
            "interestedModel": "HiLoad", "variant": "Non-GBT",
            "accountStatus": "Active", "currentStatus": "New",
            "bookingDate": "2026-11-20",
        },
        {
            "leadId": oct_id, "customerName": "Still Oct", "mobile": "9811101103",
            "interestedModel": "Storm", "variant": "Storm LR (PV)",
            "accountStatus": "Active", "currentStatus": "Booked",
            "bookingDate": "2026-10-09",
            "units": [{"sno": 1, "model": "Storm", "variant": "Storm LR (PV)",
                       "soldDate": "2026-10-09"}],
        },
    ])
    sold = (await client.get(f"/api/leads/{sold_id}/scheme-rules")).json()
    future = (await client.get(f"/api/leads/{future_id}/scheme-rules")).json()
    october = (await client.get(f"/api/leads/{oct_id}/scheme-rules")).json()
    assert sold["asOf"] == "2026-11-06"
    assert sold["schemeMonth"] == "2026-11"
    assert sold["rules"]["consumerDiscount"]["maxAmount"] == 25000
    assert sold["rules"]["loyaltyBonus"]["maxAmount"] == 10000
    assert sold["circular"]["ref"] == "EM/11-2026/001"
    assert future["asOf"] == "2026-11-20"
    assert future["schemeMonth"] == "2026-11"
    insurance = next(e for e in future["entitlements"] if e["key"] == "insuranceBenefit")
    assert insurance["companyShare"] == 10000
    assert future["rules"]["loyaltyBonus"]["maxAmount"] == 10000
    assert future["circular"]["imageUrl"] == "/scheme-circulars/2026-11.png"
    assert october["asOf"][:7] == "2026-10"
    assert (october.get("circular") or {}).get("ref") == "EM/10-2026/003"
    listed = (await client.get("/api/scheme-circulars", params={"on": "2026-11-15"})).json()
    assert listed["ref"] == "EM/11-2026/001"
    assert listed["pdfUrl"] == "/scheme-circulars/2026-11.pdf"


@pytest.mark.asyncio
async def test_boot_maintenance_upserts_nov_circular(db):
    await novs.ensure_nov_2026_schemes(db)
    before = await db.scheme_master.count_documents({"schemeMonth": "2026-11"})
    await server._run_boot_maintenance()
    after = await db.scheme_master.count_documents({"schemeMonth": "2026-11"})
    assert after == before
    rows = [r async for r in db.scheme_master.find({"schemeMonth": "2026-11"})]
    storm = _shares(rows, "Storm", "", "2026-11-20")
    assert storm["consumerDiscount"]["companyShare"] == 25000
    assert storm["loyaltyBonus"]["companyShare"] == 10000
