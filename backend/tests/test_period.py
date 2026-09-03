"""Month/year period parsing for MTD, YTD and any historic month."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

import period as periodmod


def test_empty_is_all_time():
    p = periodmod.parse_period("", "")
    assert p.kind == "all"
    assert p.is_all
    assert periodmod.in_period("2026-03-15", p)
    assert periodmod.in_period("", p)


def test_month_wins_over_year():
    p = periodmod.parse_period("2026-03", "2025")
    assert p.kind == "month"
    assert p.month == "2026-03"
    assert p.year == "2026"
    assert p.start == "2026-03-01"
    assert p.end == "2026-03-31"
    assert periodmod.in_period("2026-03-09", p)
    assert not periodmod.in_period("2026-02-28", p)
    assert not periodmod.in_period("2025-03-01", p)


def test_year_covers_all_months():
    p = periodmod.parse_period("", "2025")
    assert p.kind == "year"
    assert p.start == "2025-01-01"
    assert p.end == "2025-12-31"
    assert periodmod.in_period("2025-12-31", p)
    assert not periodmod.in_period("2026-01-01", p)


def test_bad_month_and_year_raise():
    with pytest.raises(ValueError, match="YYYY-MM"):
        periodmod.parse_period("2026-13", "")
    with pytest.raises(ValueError, match="YYYY"):
        periodmod.parse_period("", "26")


def test_february_end_on_leap_year():
    p = periodmod.parse_period("2024-02", "")
    assert p.end == "2024-02-29"


def test_year_months_are_twelve():
    months = periodmod.year_months("2026")
    assert months[0] == "2026-01"
    assert months[-1] == "2026-12"
    assert len(months) == 12
