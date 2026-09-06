"""Sept 2026 Festival Dhamaka circular is upserted without leaking August."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sept_2026_schemes_v1")
os.environ.setdefault("JWT_SECRET", "sept-2026-schemes-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import sept_2026_schemes as sept  # noqa: E402
import server  # noqa: E402


AUG_STORM = {
    "schemeId": "SCM-AUG-STORM-INS",
    "schemeMonth": "2026-08",
    "effectiveFrom": "2026-08-08",
    "effectiveTo": "2026-08-31",
    "circularRef": "EM/08-2026/001",
    "model": "Storm",
    "variant": "",
    "component": "Insurance Benefits Up to",
    "componentKey": "insuranceBenefit",
    "dealerShare": 0,
    "companyShare": 30000,
    "totalBenefit": 30000,
    "status": "Active",
}

AUG_TURBO_INS = {
    "schemeId": "SCM-AUG-TURBO-INS",
    "schemeMonth": "2026-08",
    "effectiveFrom": "2026-08-08",
    "effectiveTo": "2026-08-31",
    "circularRef": "EM/08-2026/001",
    "model": "Turbo",
    "variant": "",
    "component": "Insurance Benefits Up to",
    "componentKey": "insuranceBenefit",
    "dealerShare": 10000,
    "companyShare": 10000,
    "totalBenefit": 20000,
    "status": "Active",
}

AUG_HILOAD_CONSUMER = {
    "schemeId": "SCM-AUG-HL-CON",
    "schemeMonth": "2026-08",
    "effectiveFrom": "2026-08-08",
    "effectiveTo": "2026-08-31",
    "circularRef": "EM/08-2026/001",
    "model": "HiLoad",
    "variant": "Non-GBT",
    "component": "Consumer Scheme",
    "componentKey": "consumerDiscount",
    "dealerShare": 5000,
    "companyShare": 0,
    "totalBenefit": 5000,
    "status": "Active",
}


@pytest_asyncio.fixture
async def db():
    await server.startup()
    await server.db.scheme_master.delete_many({})
    yield server.db
    await server.db.scheme_master.delete_many({})


def _shares(rows, model, variant, on):
    return ce.get_scheme_shares_for_lead(model, variant, on, rows)


@pytest.mark.asyncio
async def test_sept_circular_amounts_and_no_aug_leak(db):
    await db.scheme_master.insert_many([AUG_STORM, AUG_TURBO_INS, AUG_HILOAD_CONSUMER])
    first = await sept.ensure_sept_2026_schemes(db)
    assert first["inserted"] == len(sept.sept_2026_scheme_rows())
    assert first["updated"] == 0
    second = await sept.ensure_sept_2026_schemes(db)
    assert second["inserted"] == 0
    assert second["unchanged"] == first["inserted"]

    rows = [r async for r in db.scheme_master.find()]
    aug = _shares(rows, "Storm", "LR", "2026-08-20")
    sep = _shares(rows, "Storm", "Storm LR (PV) Reg C7 6.6kWh", "2026-09-15")
    assert aug["insuranceBenefit"]["companyShare"] == 30000
    assert sep["loyaltyBonus"]["companyShare"] == 10000
    assert sep["insuranceBenefit"]["companyShare"] == 30000
    assert "consumerDiscount" not in sep

    hicity = _shares(rows, "HiCity", "XR", "2026-09-10")
    assert hicity["consumerDiscount"]["companyShare"] == 25000
    assert hicity["loyaltyBonus"]["companyShare"] == 10000
    assert hicity["rtoBenefit"]["companyShare"] == 10000
    assert hicity["insuranceBenefit"]["companyShare"] == 10000
    assert hicity["consumerDiscount"]["dealerShare"] == 0

    hirange = _shares(rows, "Hirange", "TR", "2026-09-06")
    assert hirange["consumerDiscount"]["totalBenefit"] == 25000
    assert hirange["rtoBenefit"]["totalBenefit"] == 10000

    turbo = _shares(rows, "Turbo", "Maxx", "2026-09-12")
    assert turbo["loyaltyBonus"]["companyShare"] == 10000
    assert "insuranceBenefit" not in turbo
    turbo_aug = _shares(rows, "Turbo", "Maxx", "2026-08-20")
    assert turbo_aug["insuranceBenefit"]["totalBenefit"] == 20000

    hiload = _shares(rows, "HiLoad", "Non-GBT", "2026-09-05")
    assert hiload["loyaltyBonus"]["companyShare"] == 10000
    assert hiload["insuranceBenefit"]["companyShare"] == 10000
    assert "consumerDiscount" not in hiload
    hiload_aug = _shares(rows, "HiLoad", "Non-GBT", "2026-08-15")
    assert hiload_aug["consumerDiscount"]["totalBenefit"] == 5000


@pytest.mark.asyncio
async def test_sept_upsert_refreshes_amounts_and_keeps_extra_owner_row(db):
    await db.scheme_master.insert_one({
        "schemeId": "SCM-OWNER-STORM-LOY",
        "schemeMonth": "2026-09",
        "effectiveFrom": "2026-09-01",
        "effectiveTo": "2026-09-30",
        "model": "Storm",
        "variant": "",
        "component": "Loyalty",
        "componentKey": "loyaltyBonus",
        "dealerShare": 0,
        "companyShare": 1,
        "totalBenefit": 1,
        "status": "Active",
    })
    await db.scheme_master.insert_one({
        "schemeId": "SCM-OWNER-STORM-DSA",
        "schemeMonth": "2026-09",
        "effectiveFrom": "2026-09-01",
        "effectiveTo": "2026-09-30",
        "model": "Storm",
        "variant": "",
        "component": "DSA",
        "componentKey": "dsaDiscount",
        "dealerShare": 0,
        "companyShare": 3000,
        "totalBenefit": 3000,
        "status": "Active",
    })
    result = await sept.ensure_sept_2026_schemes(db)
    assert result["updated"] == 1
    storm_loy = await db.scheme_master.find_one({
        "schemeId": "SCM-OWNER-STORM-LOY",
    })
    assert storm_loy["companyShare"] == 10000
    assert storm_loy["circularRef"] == "EM/09-2026/001"
    extra = await db.scheme_master.find_one({"schemeId": "SCM-OWNER-STORM-DSA"})
    assert extra["companyShare"] == 3000


@pytest.mark.asyncio
async def test_boot_maintenance_upserts_sept_circular(db):
    await sept.ensure_sept_2026_schemes(db)
    before = await db.scheme_master.count_documents({"schemeMonth": "2026-09"})
    await server._run_boot_maintenance()
    after = await db.scheme_master.count_documents({"schemeMonth": "2026-09"})
    assert after == before
    rows = [r async for r in db.scheme_master.find({"schemeMonth": "2026-09"})]
    storm = _shares(rows, "Storm", "", "2026-09-20")
    assert storm["insuranceBenefit"]["companyShare"] == 30000
