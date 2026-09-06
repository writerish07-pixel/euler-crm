"""Sept 2026 Festival Dhamaka circular EM/09-2026/001 — Scheme Master upsert.

Last month does not carry forward. Production Mongo only has July/August until
this runs on boot (or after a local seed). Idempotent on
(schemeMonth, model, variant, componentKey).
"""
from __future__ import annotations

import logging
import re

SCHEME_MONTH = "2026-09"
EFFECTIVE_FROM = "2026-09-01"
EFFECTIVE_TO = "2026-09-30"
CIRCULAR_REF = "EM/09-2026/001"
NOTES = "Sept 2026 Festival Dhamaka — EM/09-2026/001 (05-09-2026). Insurance/RTO are circular caps (upto)."

# (model, variant) -> list of (component label, componentKey, dealer, company)
# HiLoad 2.0 shares the Non-GBT circular. Empty Storm/Turbo variant matches any.
_PACKAGES = [
    (("HiLoad", "Non-GBT"), [
        ("Loyalty", "loyaltyBonus", 0, 10000),
        ("Free Insurance Up To", "insuranceBenefit", 0, 10000),
    ]),
    (("HiCity", "XR"), [
        ("Consumer Scheme", "consumerDiscount", 0, 25000),
        ("Loyalty", "loyaltyBonus", 0, 10000),
        ("Free RTO Up To", "rtoBenefit", 0, 10000),
        ("Free Insurance Up To", "insuranceBenefit", 0, 10000),
    ]),
    (("Hirange", "XR"), [
        ("Consumer Scheme", "consumerDiscount", 0, 25000),
        ("Loyalty", "loyaltyBonus", 0, 10000),
        ("Free RTO Up To", "rtoBenefit", 0, 10000),
        ("Free Insurance Up To", "insuranceBenefit", 0, 10000),
    ]),
    (("Hirange", "TR"), [
        ("Consumer Scheme", "consumerDiscount", 0, 25000),
        ("Loyalty", "loyaltyBonus", 0, 10000),
        ("Free RTO Up To", "rtoBenefit", 0, 10000),
        ("Free Insurance Up To", "insuranceBenefit", 0, 10000),
    ]),
    (("Storm", ""), [
        ("Loyalty", "loyaltyBonus", 0, 10000),
        ("Free Insurance Up To", "insuranceBenefit", 0, 30000),
    ]),
    (("Turbo", ""), [
        ("Loyalty", "loyaltyBonus", 0, 10000),
    ]),
]


def _slug(value, fallback="ALL"):
    s = re.sub(r"[^A-Za-z0-9]+", "", str(value or "")).upper()
    return s or fallback


def _stable_id(model, variant, key):
    return f"SCM-202609-{_slug(model)}-{_slug(variant)}-{key}"


def _month_of(value):
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m")
    s = str(value or "").strip()
    return s[:7] if len(s) >= 7 else s


def sept_2026_scheme_rows():
    """Canonical circular rows (no Mongo ids)."""
    rows = []
    for (model, variant), comps in _PACKAGES:
        for label, key, dealer, company in comps:
            rows.append({
                "schemeMonth": SCHEME_MONTH,
                "effectiveFrom": EFFECTIVE_FROM,
                "effectiveTo": EFFECTIVE_TO,
                "circularRef": CIRCULAR_REF,
                "model": model,
                "variant": variant,
                "component": label,
                "componentKey": key,
                "dealerShare": float(dealer),
                "companyShare": float(company),
                "totalBenefit": float(dealer + company),
                "status": "Active",
                "notes": NOTES,
            })
    return rows


async def _find_existing(db, model, variant, key):
    cursor = db.scheme_master.find({
        "componentKey": key,
        "model": {"$regex": f"^{re.escape(model)}$", "$options": "i"},
    })
    for row in await cursor.to_list(200):
        if _month_of(row.get("schemeMonth")) != SCHEME_MONTH:
            continue
        if str(row.get("variant") or "").strip().lower() != str(variant or "").strip().lower():
            continue
        return row
    return None


async def ensure_sept_2026_schemes(db):
    """Insert or refresh EM/09-2026/001 rows. Extra owner-added Sept lines are left alone."""
    inserted = 0
    updated = 0
    unchanged = 0
    for raw in sept_2026_scheme_rows():
        payload = {k: raw[k] for k in raw}
        existing = await _find_existing(db, raw["model"], raw["variant"], raw["componentKey"])
        if existing:
            fields = ("dealerShare", "companyShare", "totalBenefit", "component",
                      "circularRef", "effectiveFrom", "effectiveTo", "schemeMonth",
                      "status", "notes")
            patch = {k: payload[k] for k in fields}
            same = all(existing.get(k) == patch[k] for k in fields)
            if same:
                unchanged += 1
                continue
            await db.scheme_master.update_one({"_id": existing["_id"]}, {"$set": patch})
            updated += 1
            continue
        doc = {"schemeId": _stable_id(raw["model"], raw["variant"], raw["componentKey"]), **payload}
        clash = await db.scheme_master.find_one({"schemeId": doc["schemeId"]})
        if clash:
            doc["schemeId"] = f"{doc['schemeId']}-{inserted + updated + 1}"
        await db.scheme_master.insert_one(doc)
        inserted += 1
    result = {"inserted": inserted, "updated": updated, "unchanged": unchanged,
              "circularRef": CIRCULAR_REF, "schemeMonth": SCHEME_MONTH}
    logging.getLogger("euler.server").info("SEPT_2026_SCHEMES: %s", result)
    return result
