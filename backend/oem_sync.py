"""Apply the OEM catalog to Price Master and pull live Coulson stock/prices.

Ex-showroom is overwritten from Coulson (or the frozen expected OEM price when
offline). RTO, insurance, and other charges are never copied from OEM.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone

import oem_catalog as cat
import coulson as coulson_client

log = logging.getLogger("oem_sync")

OEM_PRICE_SOURCE = "oem"
MANUAL_CHARGES = ("rto", "insurance", "accessories", "handlingCharges", "trc",
                  "fastag", "extendedWarranty", "otherCharges")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _norm(s):
    return str(s or "").strip().lower()


async def _next_price_id(db):
    n = 0
    async for r in db.price_master.find({}, {"priceId": 1}):
        m = re.search(r"(\d+)$", str(r.get("priceId") or ""))
        if m:
            n = max(n, int(m.group(1)))
    return f"PM{n + 1:04d}"


async def _find_row_for_sku(db, sku: cat.CatalogSku):
    pairs = [(sku.crm_model, sku.crm_variant), *list(sku.aliases)]
    for model, variant in pairs:
        row = await db.price_master.find_one({
            "model": {"$regex": f"^{re.escape(model)}$", "$options": "i"},
            "variant": {"$regex": f"^{re.escape(variant)}$", "$options": "i"},
        })
        if row:
            return row
    row = await db.price_master.find_one({"oemSkuKey": sku.key})
    return row


def _active_status(row):
    return str((row or {}).get("status") or "active").lower() == "active"


async def apply_catalog(db, *, overwrite_ex_showroom=True):
    """Idempotent rename / drop / add. Does not call Coulson.

    overwrite_ex_showroom: set ex-showroom from catalog.expected_price when the
    row has never been live-synced. Live sync always overwrites later.
    """
    added = updated = deactivated = migrated_leads = 0
    changed_ids = []
    for sku in cat.CATALOG:
        existing = await _find_row_for_sku(db, sku)
        live_synced = bool((existing or {}).get("oemSyncedAt"))
        ex = float(sku.expected_price or 0)
        patch = {
            "model": sku.crm_model,
            "variant": sku.crm_variant,
            "bodyType": sku.body_type,
            "oemSkuKey": sku.key,
            "oemModel": sku.oem_model,
            "oemVariant": sku.oem_variant,
            "priceSource": OEM_PRICE_SOURCE,
            "status": "active",
        }
        if existing is None or (overwrite_ex_showroom and not live_synced):
            patch["exShowroom"] = ex
        if existing is None:
            pid = await _next_price_id(db)
            doc = {
                "priceId": pid,
                "rto": 0, "insurance": 0, "accessories": 0, "handlingCharges": 0,
                "trc": 0, "fastag": 0, "extendedWarranty": 0, "otherCharges": 0,
                "gstPercent": 0, "tcsApplicable": "No", "priceVersion": "OEM",
                "remarks": "Added from Euler OEM catalog",
                **patch,
            }
            await db.price_master.insert_one(doc)
            added += 1
        else:
            # Never clobber manual RTO/insurance.
            await db.price_master.update_one({"priceId": existing["priceId"]}, {"$set": patch})
            updated += 1
            if "exShowroom" in patch and abs(float(existing.get("exShowroom") or 0) - float(patch["exShowroom"])) > 0.005:
                changed_ids.append(existing["priceId"])
            old_m, old_v = existing.get("model"), existing.get("variant")
            if _norm(old_m) != _norm(sku.crm_model) or _norm(old_v) != _norm(sku.crm_variant):
                res = await db.leads.update_many(
                    {"interestedModel": old_m, "variant": old_v},
                    {"$set": {"interestedModel": sku.crm_model, "variant": sku.crm_variant}},
                )
                migrated_leads += int(res.modified_count or 0)
        # Alias lead names → canonical even when the row was already canonical.
        for am, av in sku.aliases:
            if _norm(am) == _norm(sku.crm_model) and _norm(av) == _norm(sku.crm_variant):
                continue
            res = await db.leads.update_many(
                {"interestedModel": am, "variant": av},
                {"$set": {"interestedModel": sku.crm_model, "variant": sku.crm_variant}},
            )
            migrated_leads += int(res.modified_count or 0)

    drop_set = {(_norm(m), _norm(v)) for m, v in cat.DROP_VARIANTS}
    catalog_keys = {(_norm(s.crm_model), _norm(s.crm_variant)) for s in cat.CATALOG}
    async for row in db.price_master.find({}):
        pair = (_norm(row.get("model")), _norm(row.get("variant")))
        if pair in drop_set and pair not in catalog_keys:
            if _active_status(row):
                await db.price_master.update_one(
                    {"priceId": row["priceId"]},
                    {"$set": {"status": "inactive", "remarks": "Dropped — no OEM SKU"}},
                )
                deactivated += 1

    await db["system"].update_one(
        {"_id": "oem_catalog"},
        {"$set": {"appliedAt": now_iso(), "added": added, "updated": updated,
                  "deactivated": deactivated, "migratedLeads": migrated_leads,
                  "catalogSize": len(cat.CATALOG)}},
        upsert=True,
    )
    return {"added": added, "updated": updated, "deactivated": deactivated,
            "migratedLeads": migrated_leads, "catalogSize": len(cat.CATALOG),
            "changedPriceIds": changed_ids}


def looks_masked_username(username):
    """True if this is our hidden hint (va***r), not a real Coulson login."""
    return "***" in str(username or "")


def _credential_from_env():
    user = (os.environ.get("COULSON_USERNAME") or "").strip()
    pw = (os.environ.get("COULSON_PASSWORD") or "").strip()
    if user and pw and not looks_masked_username(user):
        return user, pw, "env"
    return "", "", ""


def _credential_from_doc(doc):
    user = (doc.get("username") or "").strip()
    pw = doc.get("password") or ""
    if user and pw and not looks_masked_username(user):
        return user, pw, "settings"
    return "", "", ""


async def resolve_credentials(db):
    """Settings win. Railway env is only used when Settings has no real login."""
    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    user, pw, src = _credential_from_doc(doc)
    if src:
        return user, pw, src
    return _credential_from_env()


def credentials_configured(username, password):
    return bool(username and password) and not looks_masked_username(username)


def mask_username(username):
    u = str(username or "")
    if looks_masked_username(u):
        return ""
    if len(u) <= 3:
        return "*" * len(u) if u else ""
    return u[:2] + "***" + u[-1]


async def save_credentials(db, username, password):
    """Store owner-entered Coulson login. Empty password keeps the previous one."""
    existing = await db["system"].find_one({"_id": "coulson"}) or {}
    user = (username or "").strip() or existing.get("username") or ""
    if looks_masked_username(user):
        raise coulson_client.CoulsonError(
            "Type the full Coulson username from coulson.eulerlogistics.com — "
            "not the hidden va***r hint")
    pw = password if password not in (None, "") else existing.get("password") or ""
    await db["system"].update_one(
        {"_id": "coulson"},
        {"$set": {"username": user, "password": pw, "updatedAt": now_iso()}},
        upsert=True,
    )
    return user, pw


async def _record_sync(db, ok, error="", extra=None):
    patch = {
        "lastSyncAt": now_iso(),
        "lastSyncOk": bool(ok),
        "lastError": (error or "")[:500],
    }
    if extra:
        patch.update(extra)
    await db["system"].update_one({"_id": "coulson"}, {"$set": patch}, upsert=True)


def _inventory_doc(vehicle, sku, price):
    return {
        "chassis": vehicle.get("chassis") or "",
        "emch": vehicle.get("emch") or vehicle.get("registration_number") or "",
        "colour": vehicle.get("colour") or "",
        "model": sku.crm_model if sku else (vehicle.get("model") or ""),
        "variant": sku.crm_variant if sku else (vehicle.get("variant") or ""),
        "bodyType": sku.body_type if sku else (vehicle.get("updated_load_body") or vehicle.get("load_body_assembly") or ""),
        "oemSkuKey": sku.key if sku else "",
        "oemModelId": vehicle.get("sap_vehicle_model_id") or "",
        "sapProductName": vehicle.get("sap_product_name") or "",
        "modelRegisteredName": vehicle.get("model_registered_name") or "",
        "plantStatus": vehicle.get("plant_status") or "",
        "readyForAllocation": bool(vehicle.get("ready_for_allocation")),
        "pdiDone": bool(vehicle.get("is_pdi_done")),
        "inventoryAgeing": vehicle.get("current_inventory_ageing") or 0,
        "showroomCity": vehicle.get("showroom_city") or "",
        "exShowroom": price,
        "syncedAt": now_iso(),
    }


async def sync_from_coulson(db, *, username=None, password=None):
    """Pull OEM prices + PRESENT inventory. Fail-soft: raises CoulsonError on auth/API failure."""
    catalog_result = await apply_catalog(db)
    if username and password:
        user, pw, src = username, password, "inline"
    else:
        user, pw, src = await resolve_credentials(db)
    if not credentials_configured(user, pw):
        await _record_sync(db, False, "Coulson credentials not configured")
        return {"ok": False, "reason": "not_configured", "catalog": catalog_result,
                "changedPriceIds": catalog_result.get("changedPriceIds") or []}

    token = coulson_client.login(user, pw)
    oem_models = coulson_client.fetch_sap_models(token)
    vehicles = coulson_client.fetch_present_inventory(token)

    # Index OEM rows by catalog sku key (multiple SAP ids can share a SKU).
    by_key = {s.key: [] for s in cat.CATALOG}
    unmatched_oem = 0
    for oem in oem_models:
        sku = cat.sku_for_oem_row(oem)
        if not sku:
            unmatched_oem += 1
            continue
        by_key[sku.key].append(oem)

    prices_updated = 0
    changed_ids = []
    for sku in cat.CATALOG:
        oems = by_key.get(sku.key) or []
        if not oems:
            continue
        # Prefer a row with sap_product_id; Jaipur price.
        oems_sorted = sorted(oems, key=lambda r: (0 if r.get("sap_product_id") else 1))
        price = cat.jaipur_price(oems_sorted[0])
        ids = [r.get("id") for r in oems if r.get("id")]
        existing = await _find_row_for_sku(db, sku)
        if not existing:
            continue
        old_ex = float(existing.get("exShowroom") or 0)
        await db.price_master.update_one(
            {"priceId": existing["priceId"]},
            {"$set": {
                "exShowroom": price,
                "oemModelIds": ids,
                "oemSyncedAt": now_iso(),
                "priceSource": OEM_PRICE_SOURCE,
                "status": "active",
            }},
        )
        prices_updated += 1
        if abs(old_ex - float(price or 0)) > 0.005:
            changed_ids.append(existing["priceId"])

    inv_docs = []
    oem_by_id = {m.get("id"): m for m in oem_models if m.get("id")}
    for v in vehicles:
        sku = None
        price = 0.0
        oem_full = oem_by_id.get(v.get("sap_vehicle_model_id"))
        if oem_full:
            sku = cat.sku_for_oem_row(oem_full)
            if sku:
                price = cat.jaipur_price(oem_full)
        if not sku:
            oem_stub = {
                "model": v.get("model"),
                "variant": v.get("variant"),
                "load_body": v.get("updated_load_body") or v.get("load_body_assembly"),
                "sap_product_name": v.get("sap_product_name"),
                "model_registered_name": v.get("model_registered_name"),
            }
            sku = cat.sku_for_oem_row(oem_stub)
            if sku and by_key.get(sku.key):
                price = cat.jaipur_price(by_key[sku.key][0])
        inv_docs.append(_inventory_doc(v, sku, price))

    await db.oem_inventory.delete_many({})
    if inv_docs:
        await db.oem_inventory.insert_many(inv_docs)

    extra = {
        "inventoryCount": len(inv_docs),
        "oemModelCount": len(oem_models),
        "pricesUpdated": prices_updated,
        "unmatchedOemSkus": unmatched_oem,
        "credentialSource": src,
        "changedPriceIds": list(dict.fromkeys(
            (catalog_result.get("changedPriceIds") or []) + changed_ids)),
    }
    await _record_sync(db, True, "", extra)
    return {"ok": True, "catalog": catalog_result, **extra}


async def inventory_counts(db):
    counts = {}
    async for v in db.oem_inventory.find({}):
        key = (v.get("model") or "", v.get("variant") or "")
        counts[key] = counts.get(key, 0) + 1
    return counts


async def list_inventory(db, model=None):
    q = {}
    if model:
        q["model"] = model
    return [r async for r in db.oem_inventory.find(q).sort("model", 1)]
