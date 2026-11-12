"""Bring new OEM models, prices, and schemes into Price Master and Scheme Master.

The dealer order screen reads `sap-vehicle-models/catalog`. The scheme screen
reads `dealer/scheme` and `dealer/scheme-package`. A model that is not in the
frozen catalog is still a vehicle the showroom can order, so it gets a Price
Master row when Euler sent a price. Scheme rupees are stored when Euler sent
them. A hand-typed circular row is left as the owner saved it.
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

import commercial as ce
import oem_catalog as cat

try:
    from zoneinfo import ZoneInfo
    IST = ZoneInfo("Asia/Kolkata")
except Exception:  # pragma: no cover
    IST = timezone(timedelta(hours=5, minutes=30))

# Name fragments Euler uses, in the order that should win.
_SCHEME_KEYS = (
    ("insurance", "insuranceBenefit", "Free Insurance Up To"),
    ("loyalty", "loyaltyBonus", "Loyalty Bonus"),
    ("referral", "referralBonus", "Referral Bonus"),
    ("exchange", "exchangeBonus", "Exchange Bonus"),
    ("dsa", "dsaDiscount", "DSA Bonus"),
    ("rto", "rtoBenefit", "Free RTO Up To"),
    ("consumer", "consumerDiscount", "Consumer Discount"),
    ("subsidy", "consumerDiscount", "Consumer Discount"),
    ("fame", "consumerDiscount", "Consumer Discount"),
)


def _norm(value) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).casefold()


def _text(value) -> str:
    return str(value or "").strip()


def _num(value) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if number != number or number in (float("inf"), float("-inf")):
        return 0.0
    return number


def _date(item, *keys) -> str:
    if not isinstance(item, dict):
        return ""
    for key in keys:
        raw = _text(item.get(key))[:10]
        if len(raw) >= 10 and raw[4] == "-":
            return raw
    return ""


def today_iso() -> str:
    return datetime.now(IST).strftime("%Y-%m-%d")


def _model_name(row) -> str:
    if not isinstance(row, dict):
        return ""
    return _text(row.get("model") or row.get("model_name") or row.get("model_registered_name"))


def _variant_name(row) -> str:
    if not isinstance(row, dict):
        return ""
    return _text(row.get("variant") or row.get("variant_name"))


def flatten_order_catalog(payload) -> list:
    """Order-catalog JSON, nested or flat, into one row per load body."""
    rows = payload
    if isinstance(payload, dict):
        rows = payload.get("data") or payload.get("models") or payload.get("variants") or []
    if not isinstance(rows, list):
        return []
    out = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        nested = row.get("variants") or row.get("variant_options")
        if isinstance(nested, list) and nested and isinstance(nested[0], dict):
            model = _model_name(row) or _text(row.get("name"))
            vehicle_type = _text(row.get("vehicle_type") or row.get("vehicleType"))
            for variant_row in nested:
                if not isinstance(variant_row, dict):
                    continue
                variant = _variant_name(variant_row) or _text(variant_row.get("name"))
                bodies = (variant_row.get("load_bodies") or variant_row.get("loadBodies")
                          or variant_row.get("load_body_options") or [variant_row])
                if not isinstance(bodies, list):
                    bodies = [variant_row]
                for body in bodies:
                    if isinstance(body, dict):
                        out.append(_flat_body(model, variant, body, vehicle_type))
            continue
        out.append(_flat_body(_model_name(row), _variant_name(row), row,
                              _text(row.get("vehicle_type") or row.get("vehicleType"))))
    return [row for row in out if row.get("model") or row.get("variant")]


def _flat_body(model, variant, body, vehicle_type) -> dict:
    load_body = _text(body.get("load_body") or body.get("loadBody") or body.get("load_body_name"))
    # A nested load-body object uses `name` for the body, not the variant.
    if not load_body and (body.get("invoice_amount") is not None or body.get("load_body_id")):
        load_body = _text(body.get("name"))
    return {
        "id": _text(body.get("id") or body.get("sap_vehicle_model_id") or body.get("load_body_id")),
        "model": model or _model_name(body),
        "variant": variant or _variant_name(body),
        "load_body": load_body,
        "sap_product_id": _text(body.get("sap_product_id")),
        "sap_product_name": _text(body.get("sap_product_name")),
        "charger_type": _text(body.get("charger_type")),
        "chimera_type": _text(body.get("chimera_type") or body.get("chimera")),
        "vehicle_type": vehicle_type or _text(body.get("vehicle_type") or body.get("vehicleType")),
        "showroom_price_non_delhi": body.get("showroom_price_non_delhi"),
        "showroom_price_delhi": body.get("showroom_price_delhi"),
        "ex_showroom_price": body.get("ex_showroom_price"),
        "base_price": body.get("base_price"),
        "showroom_price": body.get("showroom_price"),
        "invoice_amount": body.get("invoice_amount") if body.get("invoice_amount") not in (None, "") else body.get("price"),
    }


def rows_from_metadata(payload) -> list:
    """`sap-vehicle-models/metadata`: {Model: [{variant_name, sub_variants}]}."""
    data = payload
    if isinstance(payload, dict) and "data" in payload and "model" not in payload:
        data = payload.get("data")
    rows = []
    if isinstance(data, dict):
        for model, variants in data.items():
            if str(model) in ("success", "message", "extras"):
                continue
            if not isinstance(variants, list):
                continue
            for variant in variants:
                if isinstance(variant, str):
                    rows.append({"model": str(model), "variant": variant, "load_body": ""})
                    continue
                if not isinstance(variant, dict):
                    continue
                name = _text(variant.get("variant_name") or variant.get("variant") or variant.get("name"))
                subs = variant.get("sub_variants") or []
                if isinstance(subs, list) and subs:
                    for sub in subs:
                        sub_name = sub if isinstance(sub, str) else _text(
                            (sub or {}).get("name") or (sub or {}).get("sub_variant") or (sub or {}).get("variant_name"))
                        label = name
                        if sub_name and _norm(sub_name) != _norm(name):
                            label = f"{name} {sub_name}".strip()
                        rows.append({"model": str(model), "variant": label, "load_body": ""})
                else:
                    rows.append({"model": str(model), "variant": name, "load_body": ""})
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict) and (_model_name(item) or _variant_name(item)):
                rows.append({
                    "model": _model_name(item),
                    "variant": _variant_name(item),
                    "load_body": _text(item.get("load_body") or ""),
                })
    return [row for row in rows if row.get("model")]


def rows_from_variants(payload) -> list:
    rows = payload if isinstance(payload, list) else []
    out = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        model = _model_name(item)
        variant = _variant_name(item)
        if model:
            out.append({"model": model, "variant": variant, "load_body": _text(item.get("load_body") or "")})
    return out


def _identity(row) -> tuple:
    return (
        _norm(row.get("model")),
        _norm(row.get("variant")),
        _norm(row.get("load_body")),
        _norm(row.get("chimera_type")),
        _norm(row.get("charger_type")),
    )


def merge_model_rows(*groups) -> list:
    """One row per model / variant / body. Keep the copy that has a price."""
    best = {}
    order = []
    for group in groups:
        for row in group or []:
            if not isinstance(row, dict):
                continue
            model = _model_name(row)
            variant = _variant_name(row)
            if not model and not variant:
                continue
            item = {**row, "model": model, "variant": variant}
            key = _identity(item)
            if key not in best:
                order.append(key)
                best[key] = item
                continue
            if cat.jaipur_price(best[key]) <= 0 < cat.jaipur_price(item):
                filled = {k: v for k, v in item.items() if v not in (None, "")}
                best[key] = {**best[key], **filled}
    return [best[key] for key in order]


def live_sku_key(row) -> str:
    parts = [
        _norm(row.get("model")),
        _norm(row.get("variant")),
        _norm(row.get("load_body")),
        _norm(row.get("chimera_type")),
        _norm(row.get("charger_type")),
    ]
    return "oem." + "|".join(parts)


def live_labels(row) -> tuple:
    """CRM model and variant for a vehicle the frozen catalog does not know."""
    model = _text(row.get("model"))
    bits = [_text(row.get("variant"))]
    body = _text(row.get("load_body"))
    if body and cat.body_class(body) != "STANDARD":
        bits.append(f"({body})")
    extra = []
    chimera = _text(row.get("chimera_type"))
    charger = _text(row.get("charger_type"))
    if chimera:
        extra.append(f"C{chimera}")
    if charger:
        extra.append(charger)
    variant = " ".join(bit for bit in bits if bit).strip()
    if extra:
        variant = f"{variant} {' '.join(extra)}".strip()
    return model, variant or "Standard"


def unmatched_rows(rows) -> list:
    """Rows the frozen catalog cannot place on an existing Price Master SKU."""
    out = []
    seen = set()
    for row in rows or []:
        if not isinstance(row, dict) or not _text(row.get("model")):
            continue
        if cat.sku_for_oem_row(row):
            continue
        key = live_sku_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def _scheme_name(item) -> str:
    return _text(item.get("scheme_name") or item.get("name") or item.get("scheme"))


def _component_for(name) -> tuple:
    folded = re.sub(r"[^a-z0-9]+", " ", (name or "").lower())
    for needle, key, label in _SCHEME_KEYS:
        if needle in folded:
            return key, label
    slug = re.sub(r"[^a-z0-9]+", "", (name or "").lower())[:24] or "offer"
    return f"oem_{slug}", name or "OEM scheme"


def items_from_packages(packages) -> list:
    out = []
    for package in packages or []:
        if not isinstance(package, dict):
            continue
        start = _date(package, "start_date", "effective_from", "effectiveFrom")
        end = _date(package, "end_date", "effective_to", "effectiveTo")
        prices = package.get("variant_prices") or package.get("mappings") or []
        if not isinstance(prices, list):
            continue
        for price in prices:
            if not isinstance(price, dict):
                continue
            out.append({
                "scheme_name": _scheme_name(price) or _text(package.get("scheme_package_name")),
                "scheme_type": price.get("scheme_type") or "",
                "amount_type": price.get("amount_type") or "",
                "model": _text(price.get("model")),
                "variant": _text(price.get("variant") or price.get("sub_variant")),
                "dealer_share": price.get("dealer_share"),
                "company_share": price.get("company_share"),
                "amount": price.get("amount") or price.get("scheme_amount"),
                "start_date": _date(price, "start_date", "effective_from") or start,
                "end_date": _date(price, "end_date", "effective_to") or end,
            })
    return out


def _shares(item) -> tuple:
    if str(item.get("amount_type") or "").upper() == "PERCENTAGE":
        return 0.0, 0.0
    dealer = _num(item.get("dealer_share"))
    company = _num(item.get("company_share"))
    amount = _num(item.get("amount") or item.get("scheme_amount") or item.get("max_amount"))
    if dealer <= 0 and company <= 0 and amount > 0:
        if str(item.get("scheme_type") or "").upper() == "COMMISSION":
            dealer = amount
        else:
            company = amount
    return max(0.0, dealer), max(0.0, company)


def scheme_has_money(items) -> bool:
    return any(sum(_shares(item)) > 0 and _text(item.get("model")) for item in items or [] if isinstance(item, dict))


def scheme_rows_from_items(items, *, today="") -> list:
    """Rupee schemes only. Percentage names are kept off the deal sheet."""
    today = today or today_iso()
    month_today = today[:7]
    rows = []
    seen = set()
    for item in items or []:
        if not isinstance(item, dict):
            continue
        model = _text(item.get("model"))
        if not model:
            continue
        dealer, company = _shares(item)
        if dealer <= 0 and company <= 0:
            continue
        name = _scheme_name(item)
        key, label = _component_for(name)
        variant = _text(item.get("variant") or item.get("sub_variant"))
        start = _date(item, "start_date", "effective_from", "effectiveFrom")
        end = _date(item, "end_date", "effective_to", "effectiveTo")
        month = (start or end or today)[:7] or month_today
        ident = (month, _norm(model), _norm(variant), key)
        if ident in seen:
            continue
        seen.add(ident)
        rows.append({
            "schemeMonth": month,
            "effectiveFrom": start or f"{month}-01",
            "effectiveTo": end,
            "circularRef": "OEM",
            "model": model,
            "variant": variant,
            "component": label,
            "componentKey": key,
            "dealerShare": round(dealer, 2),
            "companyShare": round(company, 2),
            "totalBenefit": round(dealer + company, 2),
            "status": "Active",
            "oemSource": "coulson",
            "oemSchemeName": name,
            "notes": f"From Euler scheme {name}".strip(),
        })
    return rows


def scheme_queries(rows) -> list:
    pairs = []
    seen = set()
    for row in unmatched_rows(rows):
        model, variant = live_labels(row)
        # Ask with the OEM model and variant, not the CRM label.
        pair = (_text(row.get("model")), _text(row.get("variant")))
        if not pair[0] or pair in seen:
            continue
        seen.add(pair)
        pairs.append(pair)
        if len(pairs) >= 25:
            break
    return pairs


def plan_live_import(sap_models, desk) -> dict:
    desk = desk or {}
    catalog_rows = flatten_order_catalog(desk.get("catalog"))
    meta_rows = rows_from_metadata(desk.get("metadata"))
    variant_rows = rows_from_variants(desk.get("variants"))
    merged = merge_model_rows(sap_models or [], catalog_rows, meta_rows, variant_rows)
    fresh = unmatched_rows(merged)
    scheme_items = [item for item in (desk.get("schemes") or []) if isinstance(item, dict)]
    scheme_items.extend(items_from_packages(desk.get("packages")))
    queries = [] if scheme_has_money(scheme_items) else scheme_queries(merged)
    return {
        "rows": fresh,
        "schemeItems": scheme_items,
        "schemeQueries": queries,
        "checks": list(desk.get("checks") or []),
        "showroomId": desk.get("showroomId") or "",
    }


def _same_scheme(row, model, variant, key, month) -> bool:
    return (
        _norm(row.get("model")) == _norm(model)
        and _norm(row.get("variant")) == _norm(variant)
        and _text(row.get("componentKey")) == key
        and _text(row.get("schemeMonth"))[:7] == month
    )


async def _next_price_id(db) -> str:
    number = 0
    async for row in db.price_master.find({}, {"priceId": 1}):
        match = re.search(r"(\d+)$", str(row.get("priceId") or ""))
        if match:
            number = max(number, int(match.group(1)))
    return f"PM{number + 1:04d}"


async def _next_scheme_id(db) -> str:
    number = 0
    async for row in db.scheme_master.find({}, {"schemeId": 1}):
        match = re.search(r"(\d+)$", str(row.get("schemeId") or ""))
        if match:
            number = max(number, int(match.group(1)))
    return f"SCM-OEM-{number + 1:04d}"


async def apply_live_import(db, planned, *, today="") -> dict:
    """Insert new Price Master and Scheme Master rows. Do not replace a hand scheme."""
    planned = planned or {}
    added = updated = unpriced = 0
    unpriced_names = []
    for row in planned.get("rows") or []:
        model, variant = live_labels(row)
        if not model:
            continue
        price = round(cat.jaipur_price(row), 2)
        key = live_sku_key(row)
        existing = await db.price_master.find_one({"oemSkuKey": key})
        if existing is None:
            existing = await db.price_master.find_one({
                "model": {"$regex": f"^{re.escape(model)}$", "$options": "i"},
                "variant": {"$regex": f"^{re.escape(variant)}$", "$options": "i"},
            })
        if price <= 0:
            unpriced += 1
            if len(unpriced_names) < 30:
                unpriced_names.append({"model": model, "variant": variant})
            continue
        rto_ins = ce.default_rto_insurance_for_model(model, variant) or (0, 0)
        patch = {
            "model": model,
            "variant": variant,
            "bodyType": _text(row.get("load_body")) or "Standard",
            "oemSkuKey": key,
            "oemModel": _text(row.get("model")),
            "oemVariant": _text(row.get("variant")),
            "exShowroom": price,
            "priceSource": "oem",
            "status": "active",
            "oemSyncedAt": datetime.now(IST).isoformat(timespec="seconds"),
            "remarks": "Added from the Euler order catalog",
        }
        if existing and str(existing.get("oemSkuKey") or "").startswith("oem."):
            await db.price_master.update_one({"priceId": existing["priceId"]}, {"$set": patch})
            updated += 1
            continue
        if existing:
            # Same label as a frozen catalog row. Leave that price list entry alone.
            continue
        price_id = await _next_price_id(db)
        await db.price_master.insert_one({
            "priceId": price_id,
            "rto": rto_ins[0], "insurance": rto_ins[1],
            "accessories": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
            "extendedWarranty": 0, "otherCharges": 0,
            "gstPercent": 0, "tcsApplicable": "No", "priceVersion": "OEM",
            **patch,
        })
        added += 1

    schemes_added = schemes_updated = schemes_kept = 0
    for item in scheme_rows_from_items(planned.get("schemeItems"), today=today):
        held = None
        async for row in db.scheme_master.find({
            "schemeMonth": item["schemeMonth"],
            "componentKey": item["componentKey"],
        }):
            if _same_scheme(row, item["model"], item["variant"], item["componentKey"], item["schemeMonth"]):
                held = row
                break
        if held and held.get("oemSource") != "coulson":
            schemes_kept += 1
            continue
        if held:
            await db.scheme_master.update_one({"_id": held["_id"]}, {"$set": item})
            schemes_updated += 1
            continue
        scheme_id = await _next_scheme_id(db)
        await db.scheme_master.insert_one({"schemeId": scheme_id, **item})
        schemes_added += 1

    checks = list(planned.get("checks") or [])
    ok = sum(1 for check in checks if check.get("ok"))
    return {
        "liveModelsAdded": added,
        "liveModelsUpdated": updated,
        "unpricedModels": unpriced,
        "unpricedModelNames": unpriced_names,
        "schemesAdded": schemes_added,
        "schemesUpdated": schemes_updated,
        "schemesKept": schemes_kept,
        "oemReadsOk": ok,
        "oemReadsFailed": len(checks) - ok,
        "oemEndpointChecks": checks,
        "showroomId": planned.get("showroomId") or "",
    }
