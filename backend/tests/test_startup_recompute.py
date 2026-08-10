"""Regression: backend startup must not crash while recomputing seeded leads.

Render deploy of 0bfd091 failed at:
  startup() -> recompute_lead() -> compute_scheme_income_breakdown()
  KeyError: 'shareSplitAvailable'

Cause: a second compute_scheme_allocation definition (from a merge) overwrote
the authoritative engine and omitted shareSplitAvailable from its return value.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "startup_recompute_reg")
os.environ.setdefault("JWT_SECRET", "startup-recompute-secret-ok")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import server  # noqa: E402


def test_allocation_return_includes_share_split_available():
    alloc = ce.compute_scheme_allocation(
        {"model": "Turbo Max", "variant": "Maxx (PV)", "bookingDate": "2026-08-09",
         "loyaltyBonus": 10000, "benefitMode": "No Benefit"},
        [{"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
          "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
          "dealerShare": 0, "companyShare": 10000, "totalBenefit": 10000, "status": "Active"}],
    )
    assert "shareSplitAvailable" in alloc
    assert "totals" in alloc and "components" in alloc
    income = ce.compute_scheme_income_breakdown(
        {"model": "Turbo Max", "variant": "Maxx (PV)", "bookingDate": "2026-08-09",
         "loyaltyBonus": 10000, "benefitMode": "No Benefit"},
        [{"schemeMonth": "2026-08", "effectiveFrom": "2026-08-08", "effectiveTo": "2026-08-31",
          "model": "Turbo", "variant": "", "componentKey": "loyaltyBonus", "component": "Loyalty",
          "dealerShare": 0, "companyShare": 10000, "totalBenefit": 10000, "status": "Active"}],
    )
    assert "shareSplitAvailable" in income


def test_only_one_compute_scheme_allocation_definition():
    import inspect
    src = inspect.getsource(ce)
    assert src.count("\ndef compute_scheme_allocation(") == 1


@pytest.mark.asyncio
async def test_startup_recomputes_seeded_leads_without_raising():
    await server.startup()
    n = await server.db.leads.count_documents({})
    assert n >= 1
    for l in await server.db.leads.find().to_list(3000):
        await server.recompute_lead(l["leadId"])
        lead = await server.db.leads.find_one({"leadId": l["leadId"]})
        assert "dealerSchemeRetained" in lead
        assert "customerPayable" in lead
        assert isinstance(lead.get("schemeAllocationSummary"), dict)
        assert "totals" in lead["schemeAllocationSummary"]
        assert "components" in lead["schemeAllocationSummary"]
