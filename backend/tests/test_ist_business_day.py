"""Business dates follow India time, not UTC.

From 00:00 to 05:29 IST the UTC date is still yesterday. A receipt posted at
1 a.m. on the 1st used to be dated the last day of the previous month, so it
also took that month's scheme and landed in that month's reports.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "ist_business_day")
os.environ.setdefault("JWT_SECRET", "ist-business-day-secret-32chars")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import period as periodmod  # noqa: E402
import server  # noqa: E402

# 1 Nov 2026, 01:15 IST == 31 Oct 2026, 19:45 UTC.
EARLY_FIRST = datetime(2026, 10, 31, 19, 45, tzinfo=timezone.utc).astimezone(periodmod.IST)


def test_today_and_month_are_india_dates(monkeypatch):
    monkeypatch.setattr(periodmod, "ist_now", lambda: EARLY_FIRST)
    assert server.today() == "2026-11-01"
    assert server.this_month() == "2026-11"
    assert server.now_hhmm() == "01:15"
    assert periodmod.this_month_period().month == "2026-11"


def test_non_finite_amounts_count_as_zero():
    import commercial as ce
    for bad in (float("nan"), float("inf"), float("-inf"), "NaN", "Infinity"):
        assert ce.num(bad) == 0.0
        assert ce.round2(bad) == 0.0
    assert ce.round2("1234.567") == 1234.57
