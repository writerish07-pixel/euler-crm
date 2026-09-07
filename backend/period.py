"""Calendar period helpers for month/year registers (MTD / YTD / any month)."""
from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime, timezone

_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
_YEAR_RE = re.compile(r"^\d{4}$")


@dataclass(frozen=True)
class Period:
    kind: str  # all | month | year
    month: str = ""  # YYYY-MM
    year: str = ""  # YYYY
    start: str = ""  # YYYY-MM-DD inclusive
    end: str = ""  # YYYY-MM-DD inclusive
    label: str = "All"

    @property
    def is_all(self) -> bool:
        return self.kind == "all"


def utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def utc_month() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


def utc_year() -> str:
    return datetime.now(timezone.utc).strftime("%Y")


def month_end(ym: str) -> str:
    y, m = map(int, ym.split("-"))
    return f"{ym}-{calendar.monthrange(y, m)[1]:02d}"


def parse_period(month: str = "", year: str = "") -> Period:
    """month=YYYY-MM wins over year=YYYY. Both empty → all time."""
    month = str(month or "").strip()
    year = str(year or "").strip()
    if month:
        if not _MONTH_RE.match(month):
            raise ValueError("month must be YYYY-MM")
        y = month[:4]
        return Period(
            kind="month", month=month, year=y,
            start=f"{month}-01", end=month_end(month),
            label=month,
        )
    if year:
        if not _YEAR_RE.match(year):
            raise ValueError("year must be YYYY")
        return Period(
            kind="year", year=year,
            start=f"{year}-01-01", end=f"{year}-12-31",
            label=year,
        )
    return Period(kind="all", label="All")


def this_month_period() -> Period:
    return parse_period(month=utc_month())


def this_year_period() -> Period:
    return parse_period(year=utc_year())


def ytd_period(year: str = "") -> Period:
    y = str(year or "").strip() or utc_year()
    p = parse_period(year=y)
    if y == utc_year():
        return Period(
            kind="year", year=y, start=p.start, end=utc_today(),
            label=f"{y} YTD",
        )
    return Period(
        kind="year", year=y, start=p.start, end=p.end,
        label=f"{y} YTD",
    )


def in_period(raw, period: Period) -> bool:
    if period.is_all:
        return True
    d = str(raw or "").strip()
    if len(d) < 7:
        return False
    if period.kind == "month":
        return d[:7] == period.month
    return d[:4] == period.year


def lead_register_date(lead: dict, status_filter: str = "") -> str:
    """Date the Lead Register uses for month / year filters.

    Delivered / Close Won tabs use the retail date, Booked / Finance use the
    booking date, otherwise createdDate. lastUpdated covers imported rows that
    never got a createdDate so This month does not go blank.
    """
    row = lead or {}
    st = (status_filter or row.get("currentStatus") or "").strip().lower()
    if "deliver" in st or "close won" in st:
        return str(
            row.get("deliveryDate")
            or row.get("closedDate")
            or row.get("createdDate")
            or row.get("lastUpdated")
            or ""
        )
    if "book" in st or "finance" in st:
        return str(row.get("bookingDate") or row.get("createdDate") or row.get("lastUpdated") or "")
    return str(row.get("createdDate") or row.get("lastUpdated") or "")


def as_dict(period: Period) -> dict:
    return {
        "kind": period.kind,
        "month": period.month,
        "year": period.year,
        "start": period.start,
        "end": period.end,
        "label": period.label,
    }


def year_months(year: str) -> list:
    y = str(year or "").strip() or utc_year()
    return [f"{y}-{m:02d}" for m in range(1, 13)]


def focus_year(period: Period) -> str:
    return period.year or utc_year()
