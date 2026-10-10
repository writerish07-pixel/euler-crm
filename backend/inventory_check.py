"""Daily physical yard confirmation — overlay on OEM/Coulson stock."""
from __future__ import annotations

from datetime import datetime, timezone

STATUSES = ("present", "missing", "damaged")
COLLECTION = "inventory_checks"


def today_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _norm_status(value) -> str:
    s = str(value or "").strip().lower()
    return s if s in STATUSES else ""


async def latest_check(db, date=None):
    day = str(date or today_iso())[:10]
    return await db[COLLECTION].find_one({"date": day}) or {}


async def status_by_chassis(db, date=None) -> dict:
    doc = await latest_check(db, date)
    out = {}
    for item in (doc.get("items") or []):
        chassis = str(item.get("chassis") or "").strip()
        st = _norm_status(item.get("status"))
        if chassis and st:
            out[chassis] = st
    return out


async def present_chassis(db, date=None):
    """Chassis marked present on that day's check, or None if no check yet."""
    doc = await latest_check(db, date)
    if not doc or not doc.get("submittedAt"):
        last = await db[COLLECTION].find({"submittedAt": {"$exists": True, "$ne": ""}}).sort("date", -1).to_list(1)
        if not last:
            return None
        doc = last[0]
    present = {
        str(i.get("chassis") or "").strip()
        for i in (doc.get("items") or [])
        if _norm_status(i.get("status")) == "present" and str(i.get("chassis") or "").strip()
    }
    return present


async def apply_to_rows(db, rows, date=None):
    by = await status_by_chassis(db, date)
    doc = await latest_check(db, date)
    day = str((doc or {}).get("date") or date or "")[:10]
    submitted = bool((doc or {}).get("submittedAt"))
    for row in rows or []:
        chassis = str(row.get("chassis") or "").strip()
        row["physicalStatus"] = by.get(chassis) or ""
        row["physicalCheckDate"] = day if chassis in by else ""
        row["physicalConfirmed"] = submitted and chassis in by
    return rows


async def submit(db, *, date, items, user):
    day = str(date or today_iso())[:10]
    cleaned = []
    seen = set()
    for raw in items or []:
        chassis = str((raw or {}).get("chassis") or "").strip()
        st = _norm_status((raw or {}).get("status"))
        if not chassis or not st or chassis in seen:
            continue
        seen.add(chassis)
        cleaned.append({
            "chassis": chassis,
            "model": str((raw or {}).get("model") or ""),
            "variant": str((raw or {}).get("variant") or ""),
            "status": st,
        })
    if not cleaned:
        raise ValueError("Tick each vehicle Present, Missing or Damaged.")
    doc = {
        "date": day,
        "items": cleaned,
        "submittedAt": now_iso(),
        "submittedBy": (user or {}).get("name") or (user or {}).get("email") or "",
        "submittedByUserId": (user or {}).get("userId") or "",
        "presentCount": sum(1 for i in cleaned if i["status"] == "present"),
        "missingCount": sum(1 for i in cleaned if i["status"] == "missing"),
        "damagedCount": sum(1 for i in cleaned if i["status"] == "damaged"),
    }
    await db[COLLECTION].update_one({"date": day}, {"$set": doc}, upsert=True)
    return await latest_check(db, day)


def public_check(doc) -> dict:
    doc = doc or {}
    return {
        "date": doc.get("date") or "",
        "submittedAt": doc.get("submittedAt") or "",
        "submittedBy": doc.get("submittedBy") or "",
        "presentCount": doc.get("presentCount") or 0,
        "missingCount": doc.get("missingCount") or 0,
        "damagedCount": doc.get("damagedCount") or 0,
        "items": list(doc.get("items") or []),
        "confirmed": bool(doc.get("submittedAt")),
    }
