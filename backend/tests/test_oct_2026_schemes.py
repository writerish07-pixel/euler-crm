"""Oct 2026 Retail Consumer Scheme EM/10-2026/003 — amounts, no Sept leak, billed-date pic."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "oct_2026_schemes_v1")
os.environ.setdefault("JWT_SECRET", "oct-2026-schemes-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import oct_2026_schemes as octs  # noqa: E402
import scheme_circulars  # noqa: E402
import sept_2026_schemes as sept  # noqa: E402
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
async def test_oct_circular_amounts_and_no_sept_leak(db):
    await sept.ensure_sept_2026_schemes(db)
    first = await octs.ensure_oct_2026_schemes(db)
    assert first["inserted"] == len(octs.oct_2026_scheme_rows())
    second = await octs.ensure_oct_2026_schemes(db)
    assert second["inserted"] == 0
    assert second["unchanged"] == first["inserted"]

    rows = [r async for r in db.scheme_master.find()]
    storm_sep = _shares(rows, "Storm", "Storm LR (PV)", "2026-09-15")
    storm_oct = _shares(rows, "Storm", "Storm LR (PV)", "2026-10-09")
    assert storm_sep["insuranceBenefit"]["companyShare"] == 30000
    assert storm_sep["loyaltyBonus"]["companyShare"] == 10000
    assert "consumerDiscount" not in storm_sep
    assert storm_oct["consumerDiscount"]["companyShare"] == 25000
    assert storm_oct["loyaltyBonus"]["companyShare"] == 10000
    assert "insuranceBenefit" not in storm_oct

    hiload = _shares(rows, "HiLoad", "Non-GBT", "2026-10-08")
    assert hiload["insuranceBenefit"]["companyShare"] == 10000
    assert hiload["loyaltyBonus"]["companyShare"] == 10000
    assert "consumerDiscount" not in hiload

    hicity = _shares(rows, "Hi-Load", "XR", "2026-10-08")
    assert hicity["insuranceBenefit"]["totalBenefit"] == 10000
    assert hicity["loyaltyBonus"]["totalBenefit"] == 10000

    turbo = _shares(rows, "Turbo", "Maxx", "2026-10-12")
    assert turbo == {}
    turbo_sep = _shares(rows, "Turbo", "Maxx", "2026-09-12")
    assert turbo_sep["loyaltyBonus"]["companyShare"] == 10000


def test_circular_pic_follows_billed_month():
    oct_pic = scheme_circulars.for_date("2026-10-09")
    assert oct_pic["ref"] == "EM/10-2026/003"
    assert oct_pic["imageUrl"].endswith("/scheme-circulars/2026-10.png")
    assert oct_pic["pdfUrl"].endswith("/scheme-circulars/2026-10.pdf")
    assert scheme_circulars.for_date("2026-09-30") is None
    assert scheme_circulars.for_date("") is None


@pytest.mark.asyncio
async def test_scheme_rules_circular_follows_unit_billed_date(client):
    await octs.ensure_oct_2026_schemes(server.db)
    lid = "LD-OCT-PIC"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Oct Pic", "mobile": "9813302026",
        "interestedModel": "Storm", "variant": "Storm LR (PV)",
        "accountStatus": "Active", "currentStatus": "Booked",
        "bookingDate": "2026-09-30",
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "model": "Storm", "variant": "Storm LR (PV)",
             "soldDate": "2026-09-30", "schemeAsOf": "2026-09-30"},
            {"sno": 2, "model": "Storm", "variant": "Storm LR (PV)",
             "soldDate": "2026-10-09", "schemeAsOf": "2026-10-09"},
        ],
    })
    sept = (await client.get(f"/api/leads/{lid}/scheme-rules", params={"unit": 1})).json()
    octb = (await client.get(f"/api/leads/{lid}/scheme-rules", params={"unit": 2})).json()
    assert sept["asOf"][:7] == "2026-09"
    assert not sept.get("circular")
    assert octb["asOf"][:7] == "2026-10"
    assert octb["circular"]["ref"] == "EM/10-2026/003"
    assert octb["circular"]["imageUrl"] == "/scheme-circulars/2026-10.png"
    assert octb["rules"]["consumerDiscount"]["maxAmount"] == 25000
    listed = (await client.get("/api/scheme-circulars", params={"on": "2026-10-15"})).json()
    assert listed["ref"] == "EM/10-2026/003"
    missing = (await client.get("/api/scheme-circulars", params={"month": "2026-09"})).json()
    assert missing == {}


@pytest.mark.asyncio
async def test_boot_maintenance_upserts_oct_circular(db):
    await octs.ensure_oct_2026_schemes(db)
    before = await db.scheme_master.count_documents({"schemeMonth": "2026-10"})
    await server._run_boot_maintenance()
    after = await db.scheme_master.count_documents({"schemeMonth": "2026-10"})
    assert after == before
    rows = [r async for r in db.scheme_master.find({"schemeMonth": "2026-10"})]
    storm = _shares(rows, "Storm", "", "2026-10-20")
    assert storm["consumerDiscount"]["companyShare"] == 25000
    assert storm["loyaltyBonus"]["companyShare"] == 10000
