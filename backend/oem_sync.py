"""Apply the OEM catalog to Price Master and pull live Coulson stock/prices.

Ex-showroom is overwritten from Coulson (or the frozen expected OEM price when
offline). RTO, insurance, and other charges are never copied from OEM.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, timezone

import oem_catalog as cat
import coulson as coulson_client
import commercial as ce

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
            rto_ins = ce.default_rto_insurance_for_model(sku.crm_model, sku.crm_variant) or (0, 0)
            doc = {
                "priceId": pid,
                "rto": rto_ins[0], "insurance": rto_ins[1], "accessories": 0, "handlingCharges": 0,
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


def session_from_doc(doc) -> str:
    """Return the stored Coulson JWT if it is still usable, else empty.

    Expired or malformed sessions are treated as absent so Sync can say so
    instead of sending a dead Bearer token.
    """
    token = str((doc or {}).get("sessionToken") or "").strip()
    if not token:
        return ""
    try:
        coulson_client.parse_session_token(token)
    except coulson_client.CoulsonError:
        return ""
    return coulson_client.clean_session_token(token)


def session_expired(doc) -> bool:
    token = str((doc or {}).get("sessionToken") or "").strip()
    if not token:
        return False
    return not bool(session_from_doc(doc))


async def save_session(db, token: str, username: str = ""):
    """Store a browser-issued Coulson JWT. Does not overwrite a saved password."""
    token = coulson_client.clean_session_token(token)
    claims = coulson_client.parse_session_token(token)
    existing = await db["system"].find_one({"_id": "coulson"}) or {}
    user = (username or "").strip() or coulson_client.session_username(claims) or existing.get("username") or ""
    if looks_masked_username(user):
        user = coulson_client.session_username(claims) or ""
    patch = {
        "sessionToken": token,
        "sessionSavedAt": now_iso(),
        "sessionExpiresAt": coulson_client.session_expires_iso(claims),
        "updatedAt": now_iso(),
        "loginOk": True,
        "lastError": "",
    }
    if user:
        patch["username"] = user
    await db["system"].update_one({"_id": "coulson"}, {"$set": patch}, upsert=True)
    return user, token


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
        "chassis": vehicle_chassis(vehicle) or vehicle.get("chassis") or "",
        "emch": vehicle.get("emch") or vehicle.get("registration_number")
                or vehicle.get("registration_no") or vehicle.get("registrationNo") or "",
        "colour": vehicle.get("colour") or "",
        "model": sku.crm_model if sku else vehicle_model(vehicle),
        "variant": sku.crm_variant if sku else vehicle_variant(vehicle),
        "bodyType": sku.body_type if sku else (vehicle.get("updated_load_body") or vehicle.get("load_body_assembly") or ""),
        "oemSkuKey": sku.key if sku else "",
        "oemModelId": vehicle.get("sap_vehicle_model_id") or "",
        "updatedLoadBody": vehicle.get("updated_load_body") or vehicle.get("load_body_assembly") or "",
        "loadBody": vehicle.get("load_body") or "",
        "availableBodyType": cat.body_class(vehicle.get("load_body") or "")
            if (vehicle.get("load_body") or "") else "",
        "billedBodyType": sku.body_type if sku else cat.body_class(
            vehicle.get("updated_load_body") or vehicle.get("load_body_assembly") or ""),
        "sapProductName": vehicle.get("sap_product_name") or vehicle.get("sapProductName") or "",
        "modelRegisteredName": vehicle.get("model_registered_name") or "",
        "plantStatus": vehicle.get("plant_status") or "",
        "readyForAllocation": bool(vehicle.get("ready_for_allocation")),
        "pdiDone": bool(vehicle.get("is_pdi_done")),
        "inventoryAgeing": vehicle.get("current_inventory_ageing") or 0,
        "showroomCity": vehicle.get("showroom_city") or "",
        "exShowroom": price,
        "syncedAt": now_iso(),
    }


async def _access_token(db, username=None, password=None):
    """Prefer a pasted Coulson session. Only call euler-auth /login when there is none.

    Euler accepts the dealer password in a browser on coulson.eulerlogistics.com and
    refuses the same password from this server. A live session skips that login.
    Returns (token, source) — source is session / settings / env / inline, or empty.
    """
    if username and password:
        return await asyncio.to_thread(coulson_client.login, username, password), "inline"
    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    token = session_from_doc(doc)
    if token:
        return token, "session"
    user, pw, src = await resolve_credentials(db)
    if credentials_configured(user, pw):
        try:
            new_token = await asyncio.to_thread(coulson_client.login, user, pw)
            try:
                await save_session(db, new_token, user)
            except Exception:
                log.exception("Could not persist renewed Coulson session")
            return new_token, "password-renew"
        except coulson_client.CoulsonError as e:
            if session_expired(doc):
                raise coulson_client.CoulsonError(
                    "Coulson session expired and Euler refused the saved password from this "
                    "server. Sign in at coulson.eulerlogistics.com and paste a new session. "
                    "Their JWT lasts about 3 days; when password login from this app works, "
                    "saved username + password renews it automatically."
                ) from e
            raise
    if session_expired(doc):
        raise coulson_client.CoulsonError(
            "Coulson session expired — sign in at coulson.eulerlogistics.com and paste a new session. "
            "Save the same username and password here so the app can renew the session itself."
        )
    return "", ""


async def sync_from_coulson(db, *, username=None, password=None, on_body_adopted=None):
    """Pull OEM prices + PRESENT inventory. Fail-soft: raises CoulsonError on auth/API failure."""
    catalog_result = await apply_catalog(db)
    token, src = await _access_token(db, username, password)
    if not token:
        await _record_sync(db, False, "Coulson credentials not configured")
        return {"ok": False, "reason": "not_configured", "catalog": catalog_result,
                "changedPriceIds": catalog_result.get("changedPriceIds") or []}

    oem_models = await asyncio.to_thread(coulson_client.fetch_sap_models, token)
    vehicles = await asyncio.to_thread(coulson_client.fetch_present_inventory, token)
    sold_vehicles = []
    sold_error = ""
    try:
        sold_vehicles = await asyncio.to_thread(coulson_client.fetch_sold_inventory, token) or []
    except coulson_client.CoulsonError as e:
        sold_error = str(e)
        log.warning("Coulson sold / invoice inventory skipped: %s", e)
    except Exception as e:
        sold_error = str(e)
        log.exception("Coulson sold / invoice inventory failed")
    transit_vehicles = []
    try:
        transit_vehicles = await asyncio.to_thread(coulson_client.fetch_transit_inventory, token) or []
    except coulson_client.CoulsonError as e:
        log.warning("Coulson transit inventory skipped: %s", e)
    except Exception:
        log.exception("Coulson transit inventory failed")

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
        oems_sorted = sorted(oems, key=lambda r: (
            0 if r.get("sap_product_id") else 1,
            -cat.jaipur_price(r),
        ))
        price = round(cat.jaipur_price(oems_sorted[0]), 2)
        if price <= 0:
            continue
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
            oem_stub = oem_stub_from_vehicle(v)
            sku = cat.sku_for_oem_row(oem_stub)
            if sku and by_key.get(sku.key):
                price = cat.jaipur_price(by_key[sku.key][0])
        inv_docs.append(_inventory_doc(v, sku, price))

    # Snapshot yard/sold models before PRESENT is replaced — billed-today
    # chassis have already left the yard pull but still sit in oem_inventory.
    model_index = await chassis_model_index(db)
    await db.oem_inventory.delete_many({})
    if inv_docs:
        await db.oem_inventory.insert_many(inv_docs)
    dropped = await drop_delivered_from_inventory(db)
    yard_count = await db.oem_inventory.count_documents({})
    sold_count = await replace_sold_inventory(
        db, sold_vehicles, oem_by_id, by_key,
        complete=getattr(sold_vehicles, "complete", True),
        model_index=model_index)
    transit_docs = []
    for v in transit_vehicles:
        sku = None
        price = 0.0
        oem_full = oem_by_id.get(v.get("sap_vehicle_model_id"))
        if oem_full:
            sku = cat.sku_for_oem_row(oem_full)
            if sku:
                price = cat.jaipur_price(oem_full)
        if not sku:
            sku = cat.sku_for_oem_row(oem_stub_from_vehicle(v))
        doc = _inventory_doc(v, sku, price)
        doc["stockStatus"] = "transit"
        transit_docs.append(doc)
    await db.oem_inventory_transit.delete_many({})
    if transit_docs:
        await db.oem_inventory_transit.insert_many(transit_docs)
    transit_count = len(transit_docs)
    leads_vehicle_ids = await apply_sold_vehicle_ids_to_leads(db, on_body_adopted=on_body_adopted)

    extra = {
        "inventoryCount": yard_count,
        "transitCount": transit_count,
        "soldCount": sold_count,
        "leadsVehicleIds": leads_vehicle_ids,
        "deliveredDropped": dropped,
        "oemModelCount": len(oem_models),
        "pricesUpdated": prices_updated,
        "unmatchedOemSkus": unmatched_oem,
        "credentialSource": src,
        "changedPriceIds": list(dict.fromkeys(
            (catalog_result.get("changedPriceIds") or []) + changed_ids)),
    }
    if sold_error:
        extra["soldError"] = sold_error
    await _record_sync(db, True, sold_error, extra)
    return {"ok": True, "catalog": catalog_result, **extra}


# Live yard chassis pick / uniqueness / drop-from-inventory apply from this date.
# Last-month Euler deliveries (and last-month Coulson PRESENT gaps) must not hide
# live stock or block a recreated lead delivered on/after 1 Sep.
YARD_LIVE_FROM = "2026-09-01"


def _norm_chassis(s):
    return re.sub(r"\s+", "", str(s or "")).strip().upper()


def _norm_invoice(s):
    return str(s or "").strip().upper()


def live_occupies_vehicle_id(other):
    """True if this lead still occupies invoice / chassis / plate uniqueness.

    Cancelled files and deliveries before 1 Sep do not count as conflicts.
    """
    if not other:
        return False
    if other.get("dealCancelled"):
        return False
    acct = str(other.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return False
    status = str(other.get("currentStatus") or "").lower()
    ddate = str(other.get("deliveryDate") or "")[:10]
    delivered = (
        str(other.get("deliveryStatus") or "").lower() == "delivered"
        or status == "delivered"
    )
    if delivered and ddate and ddate < YARD_LIVE_FROM:
        return False
    return True


def _digits10(phone):
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-10:] if len(d) >= 10 else d


_MOBILE_KEYS = (
    "customer_mobile", "customer_phone", "customer_phone_number",
    "customerMobile", "customerPhone", "billed_customer_phone",
    "mobile", "phone", "contact_number", "contact_no", "primary_mobile",
    "registered_mobile", "buyer_mobile", "buyer_phone", "customer_contact",
    "mobile_number", "phone_number", "contact", "whatsapp",
)
_NESTED_CUSTOMER_KEYS = (
    "customer", "buyer", "contact", "customer_details", "billing",
    "invoice_customer", "sold_to", "retail_customer",
)
_INVOICE_KEYS = (
    "invoice_number", "invoice_no", "invoiceNumber", "invoice",
    "sap_invoice_number", "bill_number", "billing_number", "tax_invoice_number",
    "retail_invoice_number",
)
_PLATE_KEYS = (
    "registration_number", "registration_no", "registrationNo", "regNo",
    "emch", "number_plate", "numberPlate",
    "vehicle_number", "reg_no",
)
_CHASSIS_KEYS = ("chassis", "chassis_number", "chassisNumber", "vin")
_MODEL_KEYS = (
    "model", "octopus_model", "vehicle_model", "vehicleModel",
    "model_name", "modelName", "crm_model",
)
_VARIANT_KEYS = (
    "variant", "octopus_variant", "vehicle_variant", "vehicleVariant",
    "variant_name", "variantName", "crm_variant", "sub_variant",
)
_NESTED_VEHICLE_KEYS = (
    "vehicle", "sap_vehicle_model", "sapVehicleModel", "sku", "product",
)


def _first_str(row, keys):
    for k in keys:
        v = str((row or {}).get(k) or "").strip()
        if v:
            return v
    return ""


def vehicle_mobile(row):
    """Last 10 digits of the customer mobile on a Coulson inventory/sold row."""
    if not isinstance(row, dict):
        return ""
    for k in _MOBILE_KEYS:
        d = _digits10(row.get(k))
        if len(d) == 10:
            return d
    for nested_key in _NESTED_CUSTOMER_KEYS:
        sub = row.get(nested_key)
        if isinstance(sub, dict):
            d = vehicle_mobile(sub)
            if d:
                return d
        elif isinstance(sub, str):
            d = _digits10(sub)
            if len(d) == 10:
                return d
    for k, v in row.items():
        if k in _MOBILE_KEYS or k in _NESTED_CUSTOMER_KEYS:
            continue
        kl = str(k).lower()
        if "mobile" in kl or kl in ("phone", "contact"):
            if isinstance(v, dict):
                d = vehicle_mobile(v)
            else:
                d = _digits10(v)
            if len(d) == 10:
                return d
    return ""


def vehicle_chassis(row):
    return _norm_chassis(_first_str(row, _CHASSIS_KEYS))


def vehicle_model(row):
    """CRM / OEM model name from a Sold, yard, or Vehicle Invoice row."""
    if not isinstance(row, dict):
        return ""
    n = _first_str(row, _MODEL_KEYS)
    if n:
        return n
    for nested_key in _NESTED_VEHICLE_KEYS:
        sub = row.get(nested_key)
        if isinstance(sub, dict):
            n = vehicle_model(sub)
            if n:
                return n
    return _first_str(row, (
        "model_registered_name", "modelRegisteredName",
        "sap_product_name", "sapProductName",
    ))


def vehicle_variant(row):
    if not isinstance(row, dict):
        return ""
    n = _first_str(row, _VARIANT_KEYS)
    if n:
        return n
    for nested_key in _NESTED_VEHICLE_KEYS:
        sub = row.get(nested_key)
        if isinstance(sub, dict):
            n = vehicle_variant(sub)
            if n:
                return n
    return ""


def oem_stub_from_vehicle(vehicle):
    nested = {}
    if isinstance(vehicle, dict):
        for key in _NESTED_VEHICLE_KEYS:
            sub = vehicle.get(key)
            if isinstance(sub, dict):
                nested = sub
                break
    src = vehicle if isinstance(vehicle, dict) else {}
    return {
        "model": vehicle_model(src) or nested.get("model"),
        "variant": vehicle_variant(src) or nested.get("variant"),
        "load_body": (src.get("updated_load_body") or src.get("load_body_assembly")
                      or src.get("load_body") or nested.get("load_body")),
        "sap_product_name": (src.get("sap_product_name") or src.get("sapProductName")
                             or nested.get("sap_product_name")),
        "model_registered_name": (src.get("model_registered_name")
                                  or nested.get("model_registered_name")),
    }


def sku_for_sold_vehicle(vehicle, oem_by_id=None):
    """Catalog SKU for a billed chassis.

    Conversion (FB → DV) updates `updated_load_body` while SAP model id still
    points at the original FB row. Prefer the vehicle stub so OEM Billing and
    pack units follow what Coulson billed, not the yard SKU.
    """
    vehicle = vehicle or {}
    stub = oem_stub_from_vehicle(vehicle)
    sku_stub = None
    if stub.get("model") or stub.get("variant") or stub.get("load_body") or stub.get("sap_product_name"):
        sku_stub = cat.sku_for_oem_row(stub)
    oem_full = None
    mid = vehicle.get("sap_vehicle_model_id") or vehicle.get("oemModelId")
    if oem_by_id and mid:
        oem_full = oem_by_id.get(mid)
    sku_id = cat.sku_for_oem_row(oem_full) if oem_full else None
    return sku_stub or sku_id


def vehicle_invoice(row):
    return _first_str(row, _INVOICE_KEYS)


def vehicle_plate(row):
    return _first_str(row, _PLATE_KEYS)


_CUSTOMER_NAME_KEYS = (
    "customer_name", "customerName", "billed_customer_name", "buyer_name",
    "retail_customer_name", "billed_to_name",
)


def vehicle_customer_name(row, *, nested=False):
    """Customer name on a Coulson sold row (never the vehicle model)."""
    if not isinstance(row, dict):
        return ""
    keys = _CUSTOMER_NAME_KEYS + (("name",) if nested else ())
    n = _first_str(row, keys)
    if n:
        return n
    for nested_key in _NESTED_CUSTOMER_KEYS:
        sub = row.get(nested_key)
        if isinstance(sub, dict):
            n = vehicle_customer_name(sub, nested=True)
            if n:
                return n
    return ""


_SOLD_DATE_KEYS = (
    "invoice_creation_ts", "invoiceCreationTs", "vehicle_invoice_date",
    "customer_invoice_date", "sap_invoice_date", "sold_at", "soldAt",
    "invoice_date", "invoiceDate", "billed_at", "billedAt",
    "sold_date", "soldDate", "billing_date", "billingDate",
    "retail_date", "retailDate", "date", "Date", "_created_at",
    "created_at", "createdAt",
)
_MONTH_NAME = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "sept": 9, "september": 9,
    "oct": 10, "october": 10, "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _iso_date(raw):
    """Normalize a Coulson timestamp to YYYY-MM-DD."""
    if raw is None:
        return ""
    if hasattr(raw, "strftime"):
        try:
            return raw.strftime("%Y-%m-%d")
        except Exception:
            return ""
    s = str(raw).strip()
    if not s:
        return ""
    s = re.sub(r"\bSept\b", "Sep", s)
    if s.isdigit():
        try:
            ts = int(s)
        except ValueError:
            return ""
        if ts > 10_000_000_000:
            ts //= 1000
        if 1_000_000_000 <= ts <= 2_200_000_000:
            try:
                return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")
            except (OSError, OverflowError, ValueError):
                return ""
        return ""
    if len(s) >= 10 and s[4] == "-" and s[7] == "-":
        return s[:10]
    m = re.match(r"^(\d{1,2})[/-](\d{1,2})[/-](\d{4})", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), m.group(3)
        if a > 12:
            return f"{y}-{b:02d}-{a:02d}"
        if b > 12:
            return f"{y}-{a:02d}-{b:02d}"
        return f"{y}-{b:02d}-{a:02d}"
    # Vehicle Invoices SPA: "16 Oct 2026" / "2 Sep 2026 13:34:38"
    named = re.match(
        r"^(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})", s)
    if named:
        month = _MONTH_NAME.get(named.group(2).lower())
        if month:
            return f"{named.group(3)}-{month:02d}-{int(named.group(1)):02d}"
    return ""


def vehicle_sold_date(row):
    """Invoice / billed date on a Coulson Sold row, if the portal sent one."""
    if not isinstance(row, dict):
        return ""
    for k in _SOLD_DATE_KEYS:
        d = _iso_date(row.get(k))
        if d:
            return d
    for nested_key in _NESTED_CUSTOMER_KEYS + ("invoice", "billing", "sale"):
        sub = row.get(nested_key)
        if isinstance(sub, dict):
            d = vehicle_sold_date(sub)
            if d:
                return d
    return ""


def _sold_doc(vehicle, sku, price):
    inv = _inventory_doc(vehicle, sku, price)
    mobile = vehicle_mobile(vehicle)
    return {
        **inv,
        "chassis": vehicle_chassis(vehicle) or inv.get("chassis") or "",
        "mobile": mobile,
        "invoiceNumber": vehicle_invoice(vehicle),
        "numberPlate": vehicle_plate(vehicle) or inv.get("emch") or "",
        "customerName": vehicle_customer_name(vehicle),
        "soldDate": vehicle_sold_date(vehicle),
        "coulsonStatus": vehicle.get("_coulsonStatus") or "SOLD",
        "source": "coulson_sold",
    }


def _fill_sold_model(doc, index):
    """Keep model/variant when Vehicle Invoices omit them."""
    if not isinstance(doc, dict):
        return doc
    if str(doc.get("model") or "").strip():
        return doc
    hit = (index or {}).get(_norm_chassis(doc.get("chassis"))) or {}
    if not hit.get("model"):
        return doc
    doc["model"] = hit.get("model") or ""
    if not str(doc.get("variant") or "").strip():
        doc["variant"] = hit.get("variant") or ""
    if not doc.get("oemSkuKey"):
        doc["oemSkuKey"] = hit.get("oemSkuKey") or ""
    if not doc.get("bodyType"):
        doc["bodyType"] = hit.get("bodyType") or ""
    if not doc.get("sapProductName"):
        doc["sapProductName"] = hit.get("sapProductName") or ""
    if not doc.get("loadBody"):
        doc["loadBody"] = hit.get("loadBody") or ""
    if not doc.get("updatedLoadBody"):
        doc["updatedLoadBody"] = hit.get("updatedLoadBody") or ""
    if not doc.get("availableBodyType"):
        doc["availableBodyType"] = hit.get("availableBodyType") or ""
    return doc


async def chassis_model_index(db):
    """chassis → last known model from Sold / yard / transit."""
    idx = {}
    for coll in ("oem_sold", "oem_inventory", "oem_inventory_transit"):
        async for row in db[coll].find(
                {}, {"chassis": 1, "model": 1, "variant": 1, "oemSkuKey": 1,
                     "bodyType": 1, "sapProductName": 1,
                     "loadBody": 1, "updatedLoadBody": 1,
                     "availableBodyType": 1}):
            ch = _norm_chassis(row.get("chassis"))
            if not ch or not str(row.get("model") or "").strip():
                continue
            idx.setdefault(ch, {
                "model": row.get("model") or "",
                "variant": row.get("variant") or "",
                "oemSkuKey": row.get("oemSkuKey") or "",
                "bodyType": row.get("bodyType") or "",
                "sapProductName": row.get("sapProductName") or "",
                "loadBody": row.get("loadBody") or "",
                "updatedLoadBody": row.get("updatedLoadBody") or "",
                "availableBodyType": row.get("availableBodyType") or "",
            })
    return idx


async def replace_sold_inventory(db, vehicles, oem_by_id, by_key, *, complete=True,
                                 model_index=None):
    """Write Coulson Sold / Vehicle Invoices into oem_sold.

    An empty pull must not wipe chassis already synced — that is how today's
    billed list vanished after a Coulson timeout. A short pull (Vehicle
    Invoices page, or a partial Sold page) upserts by chassis so older Sold
    rows stay put and today's billed chassis still land.

    Vehicle Invoices do not send model. Fill from yard/sold history, then
    from a chassis lookup already copied onto the live row.
    """
    if model_index is None:
        model_index = await chassis_model_index(db)
    docs = []
    seen = set()
    for v in vehicles or []:
        sku = sku_for_sold_vehicle(v, oem_by_id)
        price = 0.0
        oem_full = oem_by_id.get(v.get("sap_vehicle_model_id")) if oem_by_id else None
        if sku and oem_full and cat.sku_for_oem_row(oem_full) and cat.sku_for_oem_row(oem_full).key == sku.key:
            price = cat.jaipur_price(oem_full)
        elif sku and by_key.get(sku.key):
            price = cat.jaipur_price(by_key[sku.key][0])
        elif oem_full:
            price = cat.jaipur_price(oem_full)
        doc = _sold_doc(v, sku, price)
        _fill_sold_model(doc, model_index)
        ch = _norm_chassis(doc.get("chassis"))
        if not ch or ch in seen:
            continue
        seen.add(ch)
        docs.append(doc)
    existing = await db.oem_sold.count_documents({})
    if not docs:
        return existing
    if not complete and existing:
        for doc in docs:
            await db.oem_sold.update_one({"chassis": doc["chassis"]}, {"$set": doc}, upsert=True)
        return await db.oem_sold.count_documents({})
    await db.oem_sold.delete_many({})
    await db.oem_sold.insert_many(docs)
    return len(docs)


async def refresh_sold_inventory(db):
    """Live Sold + Vehicle Invoices pull without rewriting yard PRESENT stock."""
    token, _src = await _access_token(db)
    if not token:
        return 0
    sold_vehicles = await asyncio.to_thread(coulson_client.fetch_sold_inventory, token) or []
    if not sold_vehicles:
        return await db.oem_sold.count_documents({})
    oem_models = []
    try:
        oem_models = await asyncio.to_thread(coulson_client.fetch_sap_models, token) or []
    except coulson_client.CoulsonError:
        oem_models = []
    oem_by_id = {m.get("id"): m for m in oem_models if m.get("id")}
    by_key = {s.key: [] for s in cat.CATALOG}
    for oem in oem_models:
        sku = cat.sku_for_oem_row(oem)
        if sku:
            by_key[sku.key].append(oem)
    return await replace_sold_inventory(
        db, sold_vehicles, oem_by_id, by_key,
        complete=getattr(sold_vehicles, "complete", True))


def sold_match_score(row, lead):
    """Higher is better. Mobile is required; model family is a tie-break."""
    if not row or not lead:
        return 0
    want_m = _digits10(lead.get("mobile") or lead.get("altMobile"))
    got_m = _digits10(row.get("mobile"))
    if not want_m or len(want_m) != 10 or want_m != got_m:
        return 0
    score = 1
    if inventory_row_matches_lead(row, lead.get("interestedModel"), lead.get("variant") or ""):
        score += 2
    return score


def lead_chassis_list(lead):
    """Every chassis on this file — top-level plus same-order unit lines."""
    out = []
    seen = set()
    for raw in [(lead or {}).get("chassisNumber")] + [
            (u or {}).get("chassisNumber") for u in ((lead or {}).get("units") or [])]:
        ch = _norm_chassis(raw)
        if ch and ch not in seen:
            seen.add(ch)
            out.append(ch)
    return out


def vehicle_count(lead):
    """How many vehicles this lead file represents (pack or one)."""
    units = [u for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    if len(units) > 1:
        return len(units)
    try:
        stored = int((lead or {}).get("vehicleCount") or 0)
    except (TypeError, ValueError):
        stored = 0
    if stored > 1:
        return stored
    if (lead or {}).get("sameOrderMultiUnit"):
        return max(len(units), stored, 1)
    return 1


def is_same_order_pack(lead):
    """True when this file is a same-order fleet (one lead id, many units)."""
    units = [u for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    return bool((lead or {}).get("sameOrderMultiUnit") or len(units) > 1)


def lead_invoice_list(lead):
    out = []
    seen = set()
    for raw in [(lead or {}).get("invoiceNumber")] + [
            (u or {}).get("invoiceNumber") for u in ((lead or {}).get("units") or [])]:
        inv = _norm_invoice(raw)
        if inv and inv not in seen:
            seen.add(inv)
            out.append(inv)
    return out


def invoice_for_chassis(lead, chassis):
    """The live invoice on the vehicle that holds this chassis."""
    ch = _norm_chassis(chassis)
    if ch:
        for u in ((lead or {}).get("units") or []):
            if not isinstance(u, dict):
                continue
            if _norm_chassis(u.get("chassisNumber")) == ch:
                return str(u.get("invoiceNumber") or lead.get("invoiceNumber") or "").strip()
    return str((lead or {}).get("invoiceNumber") or "").strip()


def cancelled_invoices_for_lead(lead):
    """Old tax invoices kept when Coulson cancelled and rebilled the same chassis."""
    out = []
    seen = set()

    def take(raw):
        inv = _norm_invoice(raw)
        if inv and inv not in seen:
            seen.add(inv)
            out.append(str(raw or "").strip())

    take((lead or {}).get("cancelledInvoiceNumber"))
    for row in ((lead or {}).get("cancelledInvoices") or []):
        if isinstance(row, dict):
            take(row.get("invoiceNumber"))
        else:
            take(row)
    for u in ((lead or {}).get("units") or []):
        if not isinstance(u, dict):
            continue
        take(u.get("cancelledInvoiceNumber"))
        for row in (u.get("cancelledInvoices") or []):
            if isinstance(row, dict):
                take(row.get("invoiceNumber"))
            else:
                take(row)
    return out


def _cancelled_invoice_entry(old_invoice, new_invoice="", chassis=""):
    return {
        "invoiceNumber": str(old_invoice or "").strip(),
        "replacedBy": str(new_invoice or "").strip(),
        "chassis": _norm_chassis(chassis),
        "cancelledAt": now_iso(),
    }


def record_cancelled_invoice(target, old_invoice, new_invoice="", chassis=""):
    """Stamp the cancelled bill on a lead or unit so claims can flag the rebill."""
    old = str(old_invoice or "").strip()
    new = str(new_invoice or "").strip()
    if not old or (new and _norm_invoice(old) == _norm_invoice(new)):
        return target
    target = dict(target or {})
    target["cancelledInvoiceNumber"] = old
    if new:
        target["rebilledInvoiceNumber"] = new
    hist = [dict(x) for x in (target.get("cancelledInvoices") or []) if isinstance(x, dict)]
    key = _norm_invoice(old)
    hist = [x for x in hist if _norm_invoice(x.get("invoiceNumber")) != key]
    hist.append(_cancelled_invoice_entry(old, new, chassis))
    target["cancelledInvoices"] = hist[-8:]
    return target


def stamp_unit_vehicle_ids(lead, chassis, invoice="", plate="", sold_date=""):
    """Write chassis / invoice / plate / billed date onto the matching or next empty unit line."""
    units = [dict(u) for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    ch = _norm_chassis(chassis)
    if not ch:
        return units
    date = str(sold_date or "").strip()[:10]

    def _apply(u):
        old_inv = str(u.get("invoiceNumber") or "").strip()
        if invoice and old_inv and _norm_invoice(old_inv) != _norm_invoice(invoice):
            updated = record_cancelled_invoice(u, old_inv, invoice, ch)
            u.clear()
            u.update(updated)
        if invoice:
            u["invoiceNumber"] = invoice
        if plate:
            u["numberPlate"] = plate
        if date:
            u["soldDate"] = date
        return u

    for u in units:
        if _norm_chassis(u.get("chassisNumber")) == ch:
            _apply(u)
            return units
    for u in units:
        if not _norm_chassis(u.get("chassisNumber")):
            u["chassisNumber"] = chassis
            _apply(u)
            return units
    return units


def stamp_family_vehicle_ids(lead, family):
    """Stamp every Sold row onto matching or empty pack units. Never grows the pack."""
    working = dict(lead or {})
    units = [dict(u) for u in (working.get("units") or []) if isinstance(u, dict)]
    working["units"] = units
    for row in family or []:
        ch = _norm_chassis((row or {}).get("chassis"))
        if not ch:
            continue
        units = stamp_unit_vehicle_ids(
            working,
            (row or {}).get("chassis"),
            str((row or {}).get("invoiceNumber") or "").strip(),
            str((row or {}).get("numberPlate") or "").strip(),
            str((row or {}).get("soldDate") or "").strip()[:10],
        )
        working["units"] = units
    return working.get("units") or units


def promote_header_vehicle_ids(lead, units=None):
    """Keep the lead header in sync with the first billed unit after a rebill."""
    units = units if units is not None else list((lead or {}).get("units") or [])
    first = next(
        (u for u in units if isinstance(u, dict) and _norm_chassis(u.get("chassisNumber"))),
        None,
    )
    if not first:
        return {}
    patch = {}
    if _norm_chassis((lead or {}).get("chassisNumber")) != _norm_chassis(first.get("chassisNumber")):
        patch["chassisNumber"] = first.get("chassisNumber") or ""
        patch["invoiceNumber"] = first.get("invoiceNumber") or ""
        patch["numberPlate"] = first.get("numberPlate") or ""
    return patch


def _fold_sku(value):
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _fields_from_sku(sku):
    if not sku:
        return None
    return {
        "model": sku.crm_model,
        "variant": sku.crm_variant,
        "bodyType": sku.body_type,
        "oemSkuKey": sku.key,
    }


def _converted_body_sku(base_sku, load_body):
    """Same OEM family, different load body (FB↔DV, PV, HD, tipper, …)."""
    want = cat.body_class(load_body)
    if not base_sku or not want or want in ("STANDARD", "") or want == base_sku.body_class:
        return None
    return next(
        (s for s in cat.CATALOG
         if s.oem_model == base_sku.oem_model
         and s.oem_variant == base_sku.oem_variant
         and s.body_class == want),
        None,
    )


def sold_body_fields(row):
    """Catalog-mapped CRM model/variant/body from a Sold row, or None.

    Converted chassis often keep the original SAP id / available body on Sold.
    Prefer updated load body (billed body) when it maps to another SKU in the
    same family — FB→DV, FB→PV, PV→DV, HD→DV, and any other body change.
    """
    row = row or {}
    stub_sku = cat.sku_for_oem_row(oem_stub_from_vehicle(row))
    key = str(row.get("oemSkuKey") or "").strip()
    key_sku = next((s for s in cat.CATALOG if s.key == key), None) if key else None
    pair_sku = cat.resolve_sku(row.get("model"), row.get("variant"))
    base = stub_sku or key_sku or pair_sku
    load = (
        row.get("updatedLoadBody") or row.get("updated_load_body")
        or row.get("load_body_assembly") or row.get("loadBody")
        or row.get("load_body") or ""
    )
    converted = _converted_body_sku(base, load)
    return _fields_from_sku(converted or stub_sku or key_sku or pair_sku)


def available_body_fields(row):
    """Yard / factory body the chassis was available as — not the billed body.

    Coulson keeps `load_body` (available) and `updated_load_body` (billed).
    originalVariant on a CRM unit is the same available SKU after a conversion.
    """
    row = row or {}
    orig_var = str(row.get("originalVariant") or row.get("availableVariant") or "").strip()
    orig_model = str(
        row.get("originalModel") or row.get("availableModel")
        or row.get("model") or row.get("interestedModel") or ""
    ).strip()
    if orig_var:
        sku = cat.resolve_sku(orig_model, orig_var)
        if sku:
            return _fields_from_sku(sku)
    load = str(row.get("loadBody") or row.get("load_body") or "").strip()
    if load:
        base = (
            cat.resolve_sku(row.get("model"), row.get("variant"))
            or next((s for s in cat.CATALOG if s.key == str(row.get("oemSkuKey") or "")), None)
        )
        avail = _converted_body_sku(base, load) if base else None
        if avail:
            return _fields_from_sku(avail)
        stub = {
            "model": row.get("model") or orig_model,
            "variant": row.get("variant") or orig_var,
            "load_body": load,
            "sap_product_name": row.get("sapProductName") or row.get("sap_product_name") or "",
        }
        sku = cat.sku_for_oem_row(stub)
        if sku:
            return _fields_from_sku(sku)
    raw = _raw_sold_sku_fields(row)
    billed = sold_body_fields(row)
    if raw and billed and (
            _fold_sku(raw.get("variant")) != _fold_sku(billed.get("variant"))
            or _fold_sku(raw.get("bodyType")) != _fold_sku(billed.get("bodyType"))):
        return raw
    if str(row.get("availableBodyType") or "").strip():
        return {
            "model": orig_model or (raw or {}).get("model") or "",
            "variant": orig_var or str(row.get("availableVariant") or ""),
            "bodyType": str(row.get("availableBodyType") or ""),
            "oemSkuKey": "",
        }
    return raw


def stamp_available_billed_bodies(target, row, *, billed=None, available=None):
    """Write available + billed body onto a lead or unit dict. Working SKU is billed."""
    rec = target if isinstance(target, dict) else {}
    billed = billed if billed is not None else sold_body_fields(row)
    available = available if available is not None else available_body_fields(row)
    if billed:
        rec["oemBilledModel"] = billed.get("model") or rec.get("oemBilledModel") or ""
        rec["oemBilledVariant"] = billed.get("variant") or rec.get("oemBilledVariant") or ""
        rec["oemBilledBodyType"] = billed.get("bodyType") or rec.get("oemBilledBodyType") or ""
    if available:
        rec["availableModel"] = available.get("model") or rec.get("availableModel") or ""
        rec["availableVariant"] = available.get("variant") or rec.get("availableVariant") or ""
        rec["availableBodyType"] = available.get("bodyType") or rec.get("availableBodyType") or ""
        if billed and lead_body_differs(
                {"interestedModel": available.get("model"), "variant": available.get("variant")},
                billed):
            if not rec.get("originalVariant"):
                rec["originalModel"] = available.get("model") or rec.get("originalModel") or ""
                rec["originalVariant"] = available.get("variant") or rec.get("originalVariant") or ""
    return rec


def _sku_body_rank(fields):
    """DV (billed conversion) outranks PV/HD, which outrank original FB."""
    s = re.sub(
        r"\s+", "",
        f"{(fields or {}).get('bodyType') or ''} {(fields or {}).get('variant') or ''}".upper(),
    )
    if "DV" in s:
        return 3
    if "PV" in s or "HD" in s:
        return 2
    if "FB" in s:
        return 1
    return 0


def pick_converted_sku(*candidates):
    """Same-family SKUs: prefer the billed body over the available yard body.

    Do not jump to another OEM family (Turbo Max must not become HiCity).
    """
    rows = [c for c in candidates if isinstance(c, dict) and str(c.get("model") or "").strip()]
    if not rows:
        return None
    def _fam(f):
        return inventory_family_key(f.get("model"), f.get("variant") or "")
    base_fam = _fam(rows[0]) or next((_fam(r) for r in rows if _fam(r)), "")
    same = [r for r in rows if _fam(r) == base_fam] if base_fam else rows
    return max(same or [rows[0]], key=_sku_body_rank)


def available_differs_from_billed(available, billed):
    """True when yard/available body is a different class than billed body."""
    available = available or {}
    billed = billed or {}
    a_body = cat.body_class(available.get("bodyType") or available.get("variant") or "")
    b_body = cat.body_class(billed.get("bodyType") or billed.get("variant") or "")
    if a_body and b_body and a_body not in ("STANDARD", "") and b_body not in ("STANDARD", ""):
        if a_body != b_body:
            return True
    return bool(available.get("variant")) and lead_body_differs(
        {"interestedModel": available.get("model"), "variant": available.get("variant")},
        billed,
    )


def pack_sibling_sku_fields(lead):
    """Booked SKU on a same-order pack — first unit with a model, else the lead."""
    for u in (lead or {}).get("units") or []:
        if not isinstance(u, dict):
            continue
        model = str(u.get("model") or "").strip()
        if not model:
            continue
        sku = cat.resolve_sku(model, u.get("variant"))
        return _fields_from_sku(sku) or {
            "model": model,
            "variant": str(u.get("variant") or "").strip(),
            "bodyType": str(u.get("bodyType") or "").strip(),
            "oemSkuKey": str(u.get("oemSkuKey") or "").strip(),
        }
    model = str((lead or {}).get("interestedModel") or "").strip()
    if not model:
        return None
    sku = cat.resolve_sku(model, (lead or {}).get("variant"))
    return _fields_from_sku(sku) or {
        "model": model,
        "variant": str((lead or {}).get("variant") or "").strip(),
        "bodyType": str((lead or {}).get("bodyType") or "").strip(),
        "oemSkuKey": str((lead or {}).get("oemSkuKey") or "").strip(),
    }


def _raw_sold_sku_fields(row):
    model = str((row or {}).get("model") or "").strip()
    if not model:
        return None
    sku = cat.resolve_sku(model, (row or {}).get("variant"))
    return _fields_from_sku(sku) or {
        "model": model,
        "variant": str((row or {}).get("variant") or "").strip(),
        "bodyType": str((row or {}).get("bodyType") or "").strip(),
        "oemSkuKey": str((row or {}).get("oemSkuKey") or "").strip(),
    }


def resolved_unit_sku(lead, row=None):
    """SKU for one pack unit: billed/converted body, else sibling, else raw Sold."""
    return pick_converted_sku(
        sold_body_fields(row) if row else None,
        pack_sibling_sku_fields(lead),
        _raw_sold_sku_fields(row),
    )


def fill_lead_skus(lead, sold_rows=None):
    """Billed / converted SKU onto every unit and the lead header.

    Applies to every CRM file — single unit or pack, booked or already
    Delivered. Blank invoice lines pick up the billed body or the file's SKU.
    FB that Coulson converted and billed as DV becomes DV; DV is not overwritten
    with a stale yard FB.
    """
    units = fill_pack_unit_skus(lead, sold_rows)
    patch = {}
    if units != list((lead or {}).get("units") or []):
        patch["units"] = units
    by_ch = {}
    for row in sold_rows or []:
        ch = _norm_chassis((row or {}).get("chassis"))
        if ch:
            by_ch[ch] = row
    ch = _norm_chassis((lead or {}).get("chassisNumber"))
    row = by_ch.get(ch) if ch else None
    if row is None and len(by_ch) == 1:
        row = next(iter(by_ch.values()))
    have = None
    if str((lead or {}).get("interestedModel") or "").strip():
        have = {
            "model": (lead or {}).get("interestedModel") or "",
            "variant": (lead or {}).get("variant") or "",
            "bodyType": (lead or {}).get("bodyType") or "",
            "oemSkuKey": (lead or {}).get("oemSkuKey") or "",
        }
    billed = sold_body_fields(row) if row else None
    picked = pick_converted_sku(
        billed,
        have,
        pack_sibling_sku_fields({**(lead or {}), "units": units or (lead or {}).get("units")}),
        _raw_sold_sku_fields(row),
    )
    have_model = str((lead or {}).get("interestedModel") or "").strip()
    if picked and str(picked.get("model") or "").strip() and lead_body_differs(lead, picked):
        if have_model and not same_sold_family(lead, picked):
            picked = None
        else:
            if not (lead or {}).get("originalVariant"):
                patch["originalModel"] = (lead or {}).get("interestedModel") or ""
                patch["originalVariant"] = (lead or {}).get("variant") or ""
            patch["interestedModel"] = picked["model"]
            patch["variant"] = picked.get("variant") or ""
            if picked.get("bodyType"):
                patch["bodyType"] = picked["bodyType"]
            if picked.get("oemSkuKey"):
                patch["oemSkuKey"] = picked["oemSkuKey"]
            patch["oemBodyMismatch"] = False
    avail = available_body_fields(row) if row else None
    use_billed = (picked or billed) if (picked or billed) else None
    if row and available_differs_from_billed(avail, use_billed):
        body_rec = {
            "originalVariant": patch.get("originalVariant") or (lead or {}).get("originalVariant") or "",
            "originalModel": patch.get("originalModel") or (lead or {}).get("originalModel") or "",
        }
        stamp_available_billed_bodies(body_rec, row, billed=use_billed, available=avail)
        for k, v in body_rec.items():
            if v and str((lead or {}).get(k) or "") != str(v):
                patch[k] = v
    return patch


def fill_pack_unit_skus(lead, sold_rows=None):
    """Fill blank unit model/variant and adopt billed DV onto that chassis.

    Invoice-only appends land empty. Yard Sold can still say FB after Coulson
    converted and billed DV. Every unit on every file keeps the converted body
    — including files already marked Delivered.
    """
    units = [dict(u) for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    if not units:
        return units
    by_ch = {}
    for row in sold_rows or []:
        ch = _norm_chassis((row or {}).get("chassis"))
        if ch:
            by_ch[ch] = row
    sibling = pack_sibling_sku_fields(lead)
    out = []
    for u in units:
        rec = dict(u)
        ch = _norm_chassis(rec.get("chassisNumber"))
        row = by_ch.get(ch)
        have = None
        if str(rec.get("model") or "").strip():
            have = {
                "model": rec.get("model") or "",
                "variant": rec.get("variant") or "",
                "bodyType": rec.get("bodyType") or "",
                "oemSkuKey": rec.get("oemSkuKey") or "",
            }
        billed = sold_body_fields(row) if row else None
        picked = pick_converted_sku(
            billed,
            have,
            sibling,
            _raw_sold_sku_fields(row),
        )
        if picked and str(picked.get("model") or "").strip():
            same = (
                _fold_sku(rec.get("model")) == _fold_sku(picked.get("model"))
                and _fold_sku(rec.get("variant")) == _fold_sku(picked.get("variant"))
            )
            if not same:
                if str(rec.get("model") or "").strip() and not rec.get("originalVariant"):
                    rec["originalModel"] = rec.get("model") or ""
                    rec["originalVariant"] = rec.get("variant") or ""
                rec["model"] = picked["model"]
                rec["variant"] = picked.get("variant") or ""
                if picked.get("bodyType"):
                    rec["bodyType"] = picked["bodyType"]
                if picked.get("oemSkuKey"):
                    rec["oemSkuKey"] = picked["oemSkuKey"]
        avail = available_body_fields(row) if row else None
        use_billed = (picked or billed) if (picked or billed) else None
        if row and available_differs_from_billed(avail, use_billed):
            stamp_available_billed_bodies(rec, row, billed=use_billed, available=avail)
        out.append(rec)
    return out


def same_sold_family(lead, fields):
    want = inventory_family_key((lead or {}).get("interestedModel"), (lead or {}).get("variant") or "")
    got = inventory_family_key((fields or {}).get("model"), (fields or {}).get("variant") or "")
    return bool(want) and bool(got) and want == got


def lead_body_differs(lead, fields, unit=None):
    if unit:
        model = unit.get("model") or (lead or {}).get("interestedModel")
        variant = unit.get("variant") or (lead or {}).get("variant")
    else:
        model = (lead or {}).get("interestedModel")
        variant = (lead or {}).get("variant")
    return (
        _fold_sku(model) != _fold_sku((fields or {}).get("model"))
        or _fold_sku(variant) != _fold_sku((fields or {}).get("variant"))
    )


def lead_allows_body_adopt(lead):
    """Rewrite variant/price only on a live, not-yet-delivered file."""
    if _lead_is_cancelled(lead) or _lead_is_delivered(lead) or _lead_is_close_won(lead):
        return False
    acct = str((lead or {}).get("accountStatus") or "Active").strip().lower()
    return acct in ("", "active")


def can_adopt_sold_body(lead, row):
    if _lead_is_cancelled(lead):
        return False
    fields = sold_body_fields(row)
    if not fields or not same_sold_family(lead, fields):
        return False
    return lead_body_differs(lead, fields)


def sold_body_adopt_patch(lead, row, *, adopt=True):
    """Lead $set for a billed-body change. adopt=False only records the mismatch."""
    fields = sold_body_fields(row)
    if not fields:
        return {}
    patch = {
        "oemBilledModel": fields["model"],
        "oemBilledVariant": fields["variant"],
        "oemBilledBodyType": fields["bodyType"],
    }
    stamp_available_billed_bodies(patch, row, billed=fields)
    if not adopt:
        patch["oemBodyMismatch"] = True
        return patch
    if not lead.get("originalVariant") and lead_body_differs(lead, fields):
        patch["originalModel"] = (lead or {}).get("interestedModel") or ""
        patch["originalVariant"] = (lead or {}).get("variant") or ""
    patch["interestedModel"] = fields["model"]
    patch["variant"] = fields["variant"]
    patch["bodyType"] = fields["bodyType"]
    patch["oemSkuKey"] = fields["oemSkuKey"]
    patch["oemBodyAdoptedAt"] = now_iso()
    patch["oemBodyMismatch"] = False
    return patch


def apply_sold_body_to_units(units, row, fields, *, adopt=True):
    ch = _norm_chassis((row or {}).get("chassis"))
    if not ch or not fields:
        return units
    out = [dict(u) for u in (units or []) if isinstance(u, dict)]
    for u in out:
        if _norm_chassis(u.get("chassisNumber")) != ch:
            continue
        if adopt:
            if not u.get("originalVariant") and lead_body_differs(None, fields, unit=u):
                u["originalModel"] = u.get("model") or ""
                u["originalVariant"] = u.get("variant") or ""
            u["model"] = fields["model"]
            u["variant"] = fields["variant"]
        u["oemBilledVariant"] = fields["variant"]
        u["oemBilledModel"] = fields["model"]
        stamp_available_billed_bodies(u, row, billed=fields)
    return out


def occupied_chassis_numbers(leads, except_id=""):
    """Chassis already sitting on another live lead — skip these when matching Sold."""
    out = set()
    for other in leads or []:
        if (other or {}).get("leadId") == except_id:
            continue
        if not live_occupies_vehicle_id(other):
            continue
        for ch in lead_chassis_list(other):
            out.add(ch)
    return out


def sold_rows_for_lead(lead, sold_rows, occupied_chassis=None):
    """Sold rows that belong on this file.

    Held chassis always come back. A same-order pack also picks up leftover
    family Sold (same mobile or usable name) that no other live lead owns.
    A single-unit file stays unique-match only so five Turbos on one mobile
    do not flood a repeat-buyer drawer.
    """
    occupied = set(occupied_chassis or ())
    held = set(lead_chassis_list(lead))
    out = []
    seen = set()
    for row in sold_rows or []:
        ch = _norm_chassis((row or {}).get("chassis"))
        if ch and ch in held and ch not in seen:
            seen.add(ch)
            out.append(row)
    if not is_same_order_pack(lead):
        if out:
            return out
        row = match_sold_row(lead, sold_rows, occupied)
        return [row] if row else []
    mobile = _digits10((lead or {}).get("mobile") or (lead or {}).get("altMobile"))
    name_key = _norm_person_name((lead or {}).get("customerName"))
    name_ok = _name_key_usable(name_key)
    for row in sold_rows or []:
        ch = _norm_chassis((row or {}).get("chassis"))
        if not ch or ch in seen or (ch in occupied and ch not in held):
            continue
        row_m = _digits10((row or {}).get("mobile"))
        if mobile and len(mobile) == 10 and row_m == mobile:
            seen.add(ch)
            out.append(row)
            continue
        if name_ok and _norm_person_name((row or {}).get("customerName")) == name_key:
            seen.add(ch)
            out.append(row)
    return out


def _family_payload(lead, family):
    if not family:
        return None
    first = family[0]
    payload = _sold_match_payload(
        first, _digits10(first.get("mobile") or (lead or {}).get("mobile")))
    payload["units"] = []
    for i, row in enumerate(family):
        item = _sold_match_payload(
            row, _digits10(row.get("mobile") or (lead or {}).get("mobile")))
        item["sno"] = i + 1
        payload["units"].append(item)
    return payload


async def match_sold_for_lead(db, lead):
    """Unique remaining Sold row for this lead (chassis first, then mobile/name)."""
    rows = [r async for r in db.oem_sold.find({})]
    leads = await load_oem_billing_leads(db)
    occupied = occupied_chassis_numbers(leads, (lead or {}).get("leadId"))
    row = match_sold_row(lead, rows, occupied)
    if not row:
        return None
    return _sold_match_payload(row, _digits10(row.get("mobile")))


async def match_sold_family_for_lead(db, lead):
    """Pack-aware Sold match: one row for a single file, every unit for a pack."""
    rows = [r async for r in db.oem_sold.find({})]
    leads = await load_oem_billing_leads(db)
    occupied = occupied_chassis_numbers(leads, (lead or {}).get("leadId"))
    family = sold_rows_for_lead(lead, rows, occupied)
    return _family_payload(lead, family)


def _norm_person_name(s):
    t = str(s or "").casefold()
    t = re.sub(r"[^a-z0-9\s]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _name_key_usable(key):
    """Single-token names are too weak to copy a mobile from OEM."""
    if not key or len(key) < 6:
        return False
    return len(key.split()) >= 2


def _match_sold_by_mobile(lead, sold_rows, occupied_chassis=None):
    have_list = lead_chassis_list(lead)
    have = have_list[0] if have_list else ""
    occupied = set(occupied_chassis or ())
    if have:
        occupied.difference_update(have_list)
        for row in sold_rows or []:
            if _norm_chassis(row.get("chassis")) != have:
                continue
            sold_m = _digits10(row.get("mobile"))
            lead_m = _digits10((lead or {}).get("mobile") or (lead or {}).get("altMobile"))
            if sold_m and lead_m and sold_m != lead_m:
                return None
            return row
    mobile = _digits10((lead or {}).get("mobile") or (lead or {}).get("altMobile"))
    if len(mobile) != 10:
        return None
    candidates = []
    for row in sold_rows or []:
        ch = _norm_chassis(row.get("chassis"))
        if ch and ch in occupied:
            continue
        if _digits10(row.get("mobile")) != mobile:
            continue
        score = sold_match_score(row, lead)
        if score:
            candidates.append((score, row))
    if not candidates:
        return None
    candidates.sort(key=lambda x: -x[0])
    best_score = candidates[0][0]
    top = [r for s, r in candidates if s == best_score]
    if len(top) != 1:
        return None
    return top[0]


def _match_sold_by_name(lead, sold_rows, occupied_chassis=None):
    """Exactly one remaining Sold row and this lead share a usable customer name."""
    key = _norm_person_name((lead or {}).get("customerName"))
    if not _name_key_usable(key):
        return None
    occupied = set(occupied_chassis or ())
    have_list = lead_chassis_list(lead)
    have = have_list[0] if have_list else ""
    if have_list:
        occupied.difference_update(have_list)
    hits = []
    for row in sold_rows or []:
        ch = _norm_chassis(row.get("chassis"))
        if ch and ch in occupied:
            continue
        if _norm_person_name(row.get("customerName")) != key:
            continue
        if not ch:
            continue
        if len(_digits10(row.get("mobile"))) != 10:
            continue
        hits.append(row)
    if len(hits) != 1:
        return None
    return hits[0]


def match_sold_row(lead, sold_rows, occupied_chassis=None):
    """Pick the unique remaining sold row for this lead, or None if missing/ambiguous.

    A chassis already on the lead wins. Otherwise mobile wins when it uniquely
    matches among unoccupied Sold rows. If the CRM mobile is blank or does
    not appear on Sold, a unique customer name is enough — that is how
    Roshan Sharma / Prakash Chand Ranwa style mismatches get a chassis.
    Five identical Turbo Max on one mobile stay unmatched until chassis is set.
    """
    return (
        _match_sold_by_mobile(lead, sold_rows, occupied_chassis)
        or _match_sold_by_name(lead, sold_rows, occupied_chassis)
    )


def _sold_match_payload(row, mobile):
    fields = sold_body_fields(row) or {}
    return {
        "matched": True,
        "chassis": row.get("chassis") or "",
        "invoiceNumber": row.get("invoiceNumber") or "",
        "numberPlate": row.get("numberPlate") or "",
        "mobile": mobile,
        "model": fields.get("model") or row.get("model") or "",
        "variant": fields.get("variant") or row.get("variant") or "",
        "bodyType": fields.get("bodyType") or row.get("bodyType") or "",
        "oemSkuKey": fields.get("oemSkuKey") or row.get("oemSkuKey") or "",
        "customerName": row.get("customerName") or "",
        "coulsonStatus": row.get("coulsonStatus") or "SOLD",
        "source": "coulson_sold",
    }


def _lead_is_cancelled(lead):
    if (lead or {}).get("dealCancelled"):
        return True
    acct = str((lead or {}).get("accountStatus") or "Active").strip().lower()
    return acct in ("cancelled", "inactive", "archived")


def _lead_is_close_won(lead):
    return "close won" in str((lead or {}).get("currentStatus") or "").strip().lower()


def _lead_is_delivered(lead):
    """Retail complete: Mark Delivered or Close Won — same thing on OEM Billing."""
    ds = str((lead or {}).get("deliveryStatus") or "").lower()
    cs = str((lead or {}).get("currentStatus") or "").lower()
    return ds == "delivered" or cs == "delivered" or _lead_is_close_won(lead)


def _sold_apply_rank(lead, chassis):
    """Higher wins when two CRM leads uniquely match the same sold chassis."""
    already = 1 if _norm_chassis((lead or {}).get("chassisNumber")) == chassis else 0
    if _lead_is_cancelled(lead):
        status = 0
    elif _lead_is_delivered(lead):
        status = 4
    elif str((lead or {}).get("currentStatus") or "").lower() in (
            "booked", "finance process", "financeprocess"):
        status = 3
    else:
        status = 2
    return (already, status)


def _mobile_taken(leads, mobile, except_id):
    want = _digits10(mobile)
    if len(want) != 10:
        return False
    for other in leads:
        if (other or {}).get("leadId") == except_id:
            continue
        if not live_occupies_vehicle_id(other):
            continue
        if _digits10(other.get("mobile")) == want:
            return True
    return False


def _field_taken(leads, field, value, except_id, *, chassis=False):
    if not value:
        return False
    want = _norm_chassis(value) if chassis else _norm_invoice(value)
    if not want:
        return False
    for other in leads:
        if (other or {}).get("leadId") == except_id:
            continue
        if not live_occupies_vehicle_id(other):
            continue
        if chassis and want in set(lead_chassis_list(other)):
            return True
        got = other.get(field)
        got_n = _norm_chassis(got) if chassis else _norm_invoice(got)
        if got_n and got_n == want:
            return True
        if not chassis:
            for u in ((other or {}).get("units") or []):
                got_u = (u or {}).get(field)
                got_n = _norm_invoice(got_u)
                if got_n and got_n == want:
                    return True
    return False


# Classify / stamp / repair only need chassis, status, and identity.
# Full lead docs carry scheme JSON and unit price blobs — the same payload
# that pushed /dashboard past 25s after monthly register. OEM Billing GET/POST
# still loaded every field 2–3 times, so Sync from OEM died and the page
# showed zeros.
OEM_BILLING_LEAD_PROJ = {
    "_id": 0,
    "leadId": 1,
    "customerName": 1,
    "mobile": 1,
    "altMobile": 1,
    "chassisNumber": 1,
    "invoiceNumber": 1,
    "numberPlate": 1,
    "units": 1,
    "sameOrderMultiUnit": 1,
    "vehicleCount": 1,
    "currentStatus": 1,
    "accountStatus": 1,
    "deliveryStatus": 1,
    "dealCancelled": 1,
    "oemBillingCreated": 1,
    "oemAutoDelivered": 1,
    "oemStatusBeforeAutoDeliver": 1,
    "oemInvoiceMissing": 1,
    "executive": 1,
    "interestedModel": 1,
    "variant": 1,
    "model": 1,
    "bookingDate": 1,
    "bookingId": 1,
    "deliveryDate": 1,
    "totalReceived": 1,
    "cancelledInvoiceNumber": 1,
    "cancelledInvoices": 1,
    "rebilledInvoiceNumber": 1,
}


async def load_oem_billing_leads(db):
    return [l async for l in db.leads.find({}, OEM_BILLING_LEAD_PROJ)]


async def apply_sold_vehicle_ids_to_leads(db, *, on_body_adopted=None):
    """Write Coulson Sold chassis / invoice / plate onto every uniquely matched lead.

    OEM is the source of truth when the customer mobile maps to exactly one sold
    vehicle, or when a usable customer name is unique on both sides (blank or
    mismatched CRM mobile). Ambiguous matches and live uniqueness conflicts are
    left unchanged. A name match also copies the OEM mobile onto the lead.

    When Coulson billed a different body (FB → DV) on the same chassis, an
    Active file also takes that variant and the caller can reprice it.
    Every file — including already-delivered singles and packs — still takes
    the billed / converted body so registers, the delivery drawer, and OEM
    Billing match Coulson. Prices reprice only on a live not-yet-delivered file.
    """
    stats = {
        "updated": 0,
        "unchanged": 0,
        "skippedNoMatch": 0,
        "skippedAmbiguous": 0,
        "skippedConflict": 0,
        "mobilesUpdated": 0,
        "bodyAdopted": 0,
        "bodyMismatch": 0,
        "bodyUnitsFilled": 0,
        "bodyAdoptedIds": [],
    }
    sold = [r async for r in db.oem_sold.find({})]
    if not sold:
        return stats
    leads = await load_oem_billing_leads(db)
    if not leads:
        return stats

    by_chassis = {}
    no_match = 0
    occupied = occupied_chassis_numbers(leads)
    for lead in leads:
        mine = occupied - set(lead_chassis_list(lead))
        row = match_sold_row(lead, sold, mine)
        ch = _norm_chassis((row or {}).get("chassis"))
        if not row or not ch:
            no_match += 1
            continue
        by_chassis.setdefault(ch, []).append((lead, row))
    stats["skippedNoMatch"] = no_match

    winners = []
    for ch, group in by_chassis.items():
        live = [(l, r) for l, r in group if live_occupies_vehicle_id(l)]
        pool = live or group
        ranked = sorted(pool, key=lambda pair: _sold_apply_rank(pair[0], ch), reverse=True)
        best = _sold_apply_rank(ranked[0][0], ch)
        top = [p for p in ranked if _sold_apply_rank(p[0], ch) == best]
        if len(top) != 1:
            stats["skippedAmbiguous"] += len(group)
            continue
        winners.append(top[0])
        winner_id = (top[0][0] or {}).get("leadId")
        for l, _r in group:
            if (l or {}).get("leadId") == winner_id:
                continue
            if live_occupies_vehicle_id(l):
                stats["skippedAmbiguous"] += 1

    filled_ids = set()
    for lead, row in winners:
        lid = (lead or {}).get("leadId")
        if not lid:
            continue
        chassis = _norm_chassis(row.get("chassis"))
        invoice = str(row.get("invoiceNumber") or "").strip()
        plate = str(row.get("numberPlate") or "").strip()
        oem_mobile = _digits10(row.get("mobile"))
        lead_mobile = _digits10(lead.get("mobile") or lead.get("altMobile"))
        patch = {}
        if chassis and _norm_chassis(lead.get("chassisNumber")) != chassis:
            if not is_same_order_pack(lead) or not lead_chassis_list(lead):
                patch["chassisNumber"] = chassis
        if invoice and _norm_invoice(lead.get("invoiceNumber")) != _norm_invoice(invoice):
            if not is_same_order_pack(lead) or not lead_invoice_list(lead):
                old_inv = str(lead.get("invoiceNumber") or "").strip()
                prior = str(lead.get("cancelledInvoiceNumber") or "").strip()
                if old_inv:
                    hist = record_cancelled_invoice(lead, old_inv, invoice, chassis)
                    patch["cancelledInvoiceNumber"] = hist.get("cancelledInvoiceNumber")
                    patch["rebilledInvoiceNumber"] = hist.get("rebilledInvoiceNumber")
                    patch["cancelledInvoices"] = hist.get("cancelledInvoices")
                elif prior and _norm_invoice(prior) != _norm_invoice(invoice):
                    patch["rebilledInvoiceNumber"] = invoice
                    hist = list(lead.get("cancelledInvoices") or [])
                    if hist and isinstance(hist[-1], dict) and not hist[-1].get("replacedBy"):
                        hist[-1] = {**hist[-1], "replacedBy": invoice}
                        patch["cancelledInvoices"] = hist
                patch["invoiceNumber"] = invoice
        if plate and _norm_invoice(lead.get("numberPlate")) != _norm_invoice(plate):
            if not is_same_order_pack(lead) or not str(lead.get("numberPlate") or "").strip():
                patch["numberPlate"] = plate
        sold_date = str(row.get("soldDate") or "").strip()[:10]
        stamped_units = stamp_unit_vehicle_ids(lead, chassis, invoice, plate, sold_date)
        body_adopted = False
        body_mismatch = False
        if can_adopt_sold_body(lead, row):
            fields = sold_body_fields(row)
            adopt = lead_allows_body_adopt(lead)
            patch.update(sold_body_adopt_patch(lead, row, adopt=adopt))
            stamped_units = apply_sold_body_to_units(
                stamped_units or list((lead or {}).get("units") or []),
                row, fields, adopt=adopt)
            body_adopted = adopt
            body_mismatch = not adopt
        working_units = stamped_units or list((lead or {}).get("units") or [])
        family = sold_rows_for_lead(
            {**lead, "units": working_units}, sold,
            occupied - set(lead_chassis_list({**lead, "units": working_units})))
        if family:
            working_units = stamp_family_vehicle_ids(
                {**lead, "units": working_units}, family) or working_units
            if working_units != list((lead or {}).get("units") or []):
                patch["units"] = working_units
            patch.update(promote_header_vehicle_ids({**lead, **patch}, working_units))
        sku_patch = fill_lead_skus({**lead, "units": working_units}, family)
        units_filled = False
        if sku_patch:
            patch.update(sku_patch)
            units_filled = True
            if sku_patch.get("variant") or sku_patch.get("interestedModel"):
                body_mismatch = False
                patch["oemBodyMismatch"] = False
        if oem_mobile and len(oem_mobile) == 10 and oem_mobile != lead_mobile:
            old = str(lead.get("mobile") or "").strip()
            old10 = _digits10(old)
            if old10 and len(old10) == 10 and old10 != oem_mobile and not str(lead.get("altMobile") or "").strip():
                patch["altMobile"] = old
            patch["mobile"] = oem_mobile
        if not patch:
            stats["unchanged"] += 1
            continue
        conflict = False
        if "chassisNumber" in patch and _field_taken(
                leads, "chassisNumber", patch["chassisNumber"], lid, chassis=True):
            conflict = True
        if "invoiceNumber" in patch and _field_taken(
                leads, "invoiceNumber", patch["invoiceNumber"], lid):
            conflict = True
        if "numberPlate" in patch and _field_taken(
                leads, "numberPlate", patch["numberPlate"], lid):
            conflict = True
        if conflict:
            stats["skippedConflict"] += 1
            continue
        patch["oemSoldSyncedAt"] = now_iso()
        await db.leads.update_one({"leadId": lid}, {"$set": patch})
        await db.deliveries.update_one({"leadId": lid}, {"$set": {
            k: patch[k] for k in ("chassisNumber", "invoiceNumber", "numberPlate") if k in patch
        }})
        if "invoiceNumber" in patch:
            await db.billing_summaries.update_one(
                {"leadId": lid}, {"$set": {"invoiceNumber": patch["invoiceNumber"]}})
        lead.update(patch)
        filled_ids.add(lid)
        stats["updated"] += 1
        if units_filled:
            stats["bodyUnitsFilled"] += 1
        if "mobile" in patch:
            stats["mobilesUpdated"] += 1
        if body_adopted:
            stats["bodyAdopted"] += 1
            stats["bodyAdoptedIds"].append(lid)
            if on_body_adopted:
                await on_body_adopted(lid)
        elif body_mismatch:
            stats["bodyMismatch"] += 1

    occupied = occupied_chassis_numbers(leads)
    for lead in leads:
        lid = (lead or {}).get("leadId")
        if not lid or lid in filled_ids:
            continue
        family = sold_rows_for_lead(
            lead, sold, occupied - set(lead_chassis_list(lead)))
        sku_patch = fill_lead_skus(lead, family) or {}
        units = stamp_family_vehicle_ids(lead, family) if family else list(
            (lead or {}).get("units") or [])
        patch = dict(sku_patch)
        if units and units != list((lead or {}).get("units") or []):
            patch["units"] = units
        patch.update(promote_header_vehicle_ids({**lead, **patch}, units))
        if not patch:
            continue
        patch["lastUpdated"] = now_iso()
        patch["oemSoldSyncedAt"] = now_iso()
        await db.leads.update_one({"leadId": lid}, {"$set": patch})
        lead.update(patch)
        occupied.update(lead_chassis_list(lead))
        filled_ids.add(lid)
        stats["updated"] += 1
        if sku_patch:
            stats["bodyUnitsFilled"] += 1
    return stats


def sold_chassis_set(sold_rows):
    return {
        _norm_chassis((r or {}).get("chassis"))
        for r in (sold_rows or [])
        if _norm_chassis((r or {}).get("chassis"))
    }


def _staff_delivery_locked(lead):
    """A desk-completed delivery / Close Won is not auto-un-delivered."""
    if _lead_is_close_won(lead):
        return True
    if _lead_is_delivered(lead) and not (lead or {}).get("oemAutoDelivered"):
        return True
    return False


def sold_rows_replacing_gone(lead, sold_rows, occupied_chassis=None):
    """Live Sold rows for this customer that can replace cancelled chassis.

    Held ids that Coulson still lists stay. Cancelled ids are treated as empty
    slots so the same-mobile / same-name rebill can attach instead of growing
    the pack with a second set of units.
    """
    occupied = set(occupied_chassis or ())
    held = set(lead_chassis_list(lead))
    sold_ch = sold_chassis_set(sold_rows)
    gone = held - sold_ch
    if not gone:
        return []
    live_held = held & sold_ch
    ghost = dict(lead or {})
    units = []
    for u in (ghost.get("units") or []):
        if not isinstance(u, dict):
            continue
        rec = dict(u)
        if _norm_chassis(rec.get("chassisNumber")) in gone:
            rec["chassisNumber"] = ""
            rec["invoiceNumber"] = ""
            rec["numberPlate"] = ""
        units.append(rec)
    ghost["units"] = units
    if _norm_chassis(ghost.get("chassisNumber")) in gone:
        ghost["chassisNumber"] = next(iter(live_held), "")
        ghost["invoiceNumber"] = ""
        ghost["numberPlate"] = ""
    family = sold_rows_for_lead(ghost, sold_rows, occupied - gone)
    return [
        r for r in family
        if _norm_chassis((r or {}).get("chassis")) not in live_held
    ]


def clear_gone_sold_chassis(lead, sold_chassis):
    """Drop chassis / invoice / plate that Coulson Sold no longer holds."""
    sold_chassis = set(sold_chassis or ())
    held = lead_chassis_list(lead)
    gone = [c for c in held if c not in sold_chassis]
    if not gone:
        return None
    gone_set = set(gone)
    patch = {}
    units = [dict(u) for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    changed_units = False
    for u in units:
        if _norm_chassis(u.get("chassisNumber")) not in gone_set:
            continue
        old_inv = str(u.get("invoiceNumber") or "").strip()
        if old_inv:
            updated = record_cancelled_invoice(u, old_inv, "", u.get("chassisNumber"))
            u.clear()
            u.update(updated)
        u["chassisNumber"] = ""
        u["invoiceNumber"] = ""
        u["numberPlate"] = ""
        changed_units = True
    if changed_units:
        patch["units"] = units
    if _norm_chassis((lead or {}).get("chassisNumber")) in gone_set:
        remaining = [
            _norm_chassis(u.get("chassisNumber"))
            for u in (patch.get("units") or units)
            if _norm_chassis(u.get("chassisNumber"))
        ]
        if remaining:
            patch["chassisNumber"] = remaining[0]
            first = next(
                (u for u in (patch.get("units") or units)
                 if _norm_chassis(u.get("chassisNumber")) == remaining[0]),
                {},
            )
            patch["invoiceNumber"] = (first or {}).get("invoiceNumber") or ""
            patch["numberPlate"] = (first or {}).get("numberPlate") or ""
        else:
            old_inv = str((lead or {}).get("invoiceNumber") or "").strip()
            if old_inv:
                hist = record_cancelled_invoice(lead, old_inv, "", lead.get("chassisNumber"))
                patch["cancelledInvoiceNumber"] = hist.get("cancelledInvoiceNumber")
                patch["cancelledInvoices"] = hist.get("cancelledInvoices")
            patch["chassisNumber"] = ""
            patch["invoiceNumber"] = ""
            patch["numberPlate"] = ""
    return patch


def oem_auto_deliver_revert_patch(lead):
    """Undo OEM-auto delivery when the billed chassis left Sold."""
    if not (lead or {}).get("oemAutoDelivered"):
        return {}
    if lead_chassis_list(lead):
        return {}
    if (lead or {}).get("bookingDate"):
        status = "Booked"
    else:
        status = str((lead or {}).get("oemStatusBeforeAutoDeliver") or "In Progress").strip() or "In Progress"
        if status.lower() in ("delivered", "close won", "closewon"):
            status = "In Progress"
    return {
        "deliveryStatus": "",
        "currentStatus": status,
        "deliveryDate": "",
        "oemAutoDelivered": False,
        "oemInvoiced": False,
    }


async def delink_cancelled_sold_invoices(db):
    """When Coulson drops a billed chassis, free that id on the CRM file.

    Staff-completed Delivered / Close Won files keep their delivery status.
    They still drop cancelled chassis when Sold has a replacement for the
    same customer, so a rebill does not leave both ids on the pack. With no
    replacement they are only flagged. OEM-auto delivered enquiries lose the
    chassis and, if nothing remains, the auto-delivery stamp so a rebill can
    attach again.
    """
    sold = [r async for r in db.oem_sold.find({})]
    sold_ch = sold_chassis_set(sold)
    leads = await load_oem_billing_leads(db)
    occupied = occupied_chassis_numbers(leads)
    stats = {"cleared": 0, "flagged": 0, "reverted": 0, "clearedIds": []}
    for lead in leads:
        if _lead_is_cancelled(lead):
            continue
        held = lead_chassis_list(lead)
        gone = [c for c in held if c not in sold_ch]
        if not gone:
            if lead.get("oemInvoiceMissing"):
                await db.leads.update_one(
                    {"leadId": lead.get("leadId")},
                    {"$unset": {"oemInvoiceMissing": ""}})
            continue
        lid = lead.get("leadId")
        if not lid:
            continue
        replacements = sold_rows_replacing_gone(
            lead, sold, occupied - set(held))
        if _staff_delivery_locked(lead) and not replacements:
            if not lead.get("oemInvoiceMissing"):
                await db.leads.update_one(
                    {"leadId": lid},
                    {"$set": {"oemInvoiceMissing": True}})
                stats["flagged"] += 1
            continue
        patch = clear_gone_sold_chassis(lead, sold_ch) or {}
        merged = {**lead, **patch}
        revert = {}
        if not _staff_delivery_locked(lead):
            revert = oem_auto_deliver_revert_patch(merged)
            patch.update(revert)
        if not patch:
            continue
        patch["oemSoldSyncedAt"] = now_iso()
        unset = {}
        if revert or replacements:
            unset["oemInvoiceMissing"] = ""
            if revert:
                stats["reverted"] += 1
        op = {"$set": patch}
        if unset:
            op["$unset"] = unset
        await db.leads.update_one({"leadId": lid}, op)
        delivery_ids = {k: patch[k] for k in ("chassisNumber", "invoiceNumber", "numberPlate")
                        if k in patch}
        if delivery_ids or revert:
            await db.deliveries.update_one(
                {"leadId": lid},
                {"$set": delivery_ids} if delivery_ids else {"$set": {"chassisNumber": "",
                                                                     "invoiceNumber": "",
                                                                     "numberPlate": ""}},
            )
        lead.update(patch)
        stats["cleared"] += 1
        stats["clearedIds"].append(lid)
    return stats


def _delivered_missing_vehicle_ids(lead):
    if not _lead_is_delivered(lead):
        return False
    if _lead_is_cancelled(lead):
        return False
    units = [u for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    if is_same_order_pack(lead) and units:
        return any(
            not _norm_chassis((u or {}).get("chassisNumber"))
            or not _norm_invoice((u or {}).get("invoiceNumber"))
            for u in units)
    ch = _norm_chassis((lead or {}).get("chassisNumber"))
    inv = _norm_invoice((lead or {}).get("invoiceNumber"))
    return not ch or not inv


_MISSING_VEHICLE_PROJ = {
    "_id": 0,
    "leadId": 1, "customerName": 1, "mobile": 1, "altMobile": 1,
    "chassisNumber": 1, "invoiceNumber": 1, "units": 1,
    "sameOrderMultiUnit": 1, "vehicleCount": 1,
    "deliveryStatus": 1, "currentStatus": 1, "accountStatus": 1, "dealCancelled": 1,
}
_DELIVERED_QUERY = {
    "$or": [
        {"deliveryStatus": {"$regex": r"^deliver", "$options": "i"}},
        {"currentStatus": {"$regex": r"deliver|close won", "$options": "i"}},
    ],
}


async def delivered_missing_vehicle_ids(db):
    """Delivered (not cancelled) leads still missing chassis and/or invoice."""
    rows = []
    async for l in db.leads.find(_DELIVERED_QUERY, _MISSING_VEHICLE_PROJ):
        if not _delivered_missing_vehicle_ids(l):
            continue
        rows.append({
            "leadId": l.get("leadId") or "",
            "customerName": l.get("customerName") or "",
            "mobile": _digits10(l.get("mobile") or l.get("altMobile")),
            "missingChassis": not _norm_chassis(l.get("chassisNumber")),
            "missingInvoice": not _norm_invoice(l.get("invoiceNumber")),
        })
    return rows


BUCKET_PENDING = "pending_delivery"
BUCKET_CREATED = "created_from_oem"
BUCKET_DELIVERED = "matched_delivered"
BUCKET_REVIEW = "needs_review"
BUCKET_UNMATCHED = "unmatched"


def _lead_crm_status(lead):
    return str((lead or {}).get("currentStatus") or "New")


def _bucket_for_matched_lead(lead):
    """Once a Sold row is on a CRM lead, status follows that file.

    Created-from-OEM is not shown: Delivered/Close Won → Delivered, else
    Pending delivery.
    """
    if _lead_is_delivered(lead):
        return BUCKET_DELIVERED
    return BUCKET_PENDING


def _lead_model_variant(lead, chassis=""):
    """Model/variant on the matched CRM file, preferring the unit with this chassis."""
    if not lead:
        return "", ""
    ch = _norm_chassis(chassis)
    if ch:
        for unit in (lead.get("units") or []):
            if not isinstance(unit, dict):
                continue
            if _norm_chassis(unit.get("chassisNumber")) != ch:
                continue
            model = str(unit.get("model") or unit.get("interestedModel") or "").strip()
            variant = str(unit.get("variant") or "").strip()
            if model:
                return model, variant
    model = str(lead.get("interestedModel") or lead.get("model") or "").strip()
    variant = str(lead.get("variant") or "").strip()
    return model, variant


def _billing_row(sold, bucket, lead=None, review_reason="", holder_leads=None):
    sold_date = str((sold or {}).get("soldDate") or "").strip()[:10]
    holders = [_pair_summary(l) for l in (holder_leads or []) if l]
    keeper = resolve_chassis_holders(holder_leads or [])
    chassis = _norm_chassis((sold or {}).get("chassis"))
    lead_model, lead_variant = _lead_model_variant(lead, chassis)
    unit_fields = {"model": lead_model, "variant": lead_variant} if lead_model else None
    picked = pick_converted_sku(
        sold_body_fields(sold),
        unit_fields,
        pack_sibling_sku_fields(lead) if lead else None,
        _raw_sold_sku_fields(sold),
    )
    model = str(
        (picked or {}).get("model")
        or (sold or {}).get("model")
        or lead_model
        or ""
    ).strip()
    variant = str(
        (picked or {}).get("variant")
        or (sold or {}).get("variant")
        or lead_variant
        or ""
    ).strip()
    billed = sold_body_fields(sold)
    available = available_body_fields(sold)
    billed_body = str((billed or {}).get("bodyType") or (sold or {}).get("billedBodyType")
                      or (sold or {}).get("oemBilledBodyType") or "").strip()
    available_body = str((available or {}).get("bodyType") or (sold or {}).get("availableBodyType")
                         or (sold or {}).get("loadBody") or "").strip()
    if available_body and cat.body_class(available_body) == cat.body_class(billed_body):
        available_body = ""
    return {
        "chassis": chassis,
        "invoiceNumber": str((sold or {}).get("invoiceNumber") or "").strip(),
        "mobile": _digits10((sold or {}).get("mobile")),
        "customerName": str((sold or {}).get("customerName") or "").strip(),
        "model": model,
        "variant": variant,
        "billedBodyType": billed_body or str((picked or {}).get("bodyType") or "").strip(),
        "availableBodyType": available_body,
        "availableVariant": str((available or {}).get("variant") or "").strip(),
        "soldDate": sold_date,
        "undated": not sold_date,
        "bucket": bucket,
        "leadId": (lead or {}).get("leadId") or "",
        "crmStatus": _lead_crm_status(lead) if lead else "",
        "crmExecutive": (lead or {}).get("executive") or "",
        "oemBillingCreated": bool((lead or {}).get("oemBillingCreated")),
        "reviewReason": review_reason,
        "holderLeads": holders,
        "keeperLeadId": (keeper or {}).get("leadId") or "",
        "duplicateLeadIds": [
            h["leadId"] for h in holders
            if h.get("leadId") and h.get("leadId") != (keeper or {}).get("leadId")
        ],
    }


def _live_same_mobile(live, mobile):
    want = _digits10(mobile)
    if len(want) != 10:
        return []
    return [
        l for l in live
        if _digits10((l or {}).get("mobile") or (l or {}).get("altMobile")) == want
    ]


def _live_same_name(live, name):
    key = _norm_person_name(name)
    if not _name_key_usable(key):
        return []
    return [l for l in live if _norm_person_name((l or {}).get("customerName")) == key]


def _empty_unclaimed(leads, claimed):
    return [
        l for l in leads
        if not lead_chassis_list(l)
        and (l or {}).get("leadId") not in claimed
    ]


def classify_oem_billing(sold_rows, leads):
    """Join each Sold chassis to a live CRM lead, or mark it unmatched / review.

    One empty CRM file can take only one Sold row. Extra billed chassis on the
    same mobile or the same usable name (Messenger SCS × 5) stay unmatched so
    sync can create the remaining units.
    """
    live = [l for l in (leads or []) if repair_original_lead(l) or is_oem_billing_stub(l)]
    occupied = occupied_chassis_numbers(leads)
    claimed = {}
    out = []

    def take(sold, lead, bucket, reason=""):
        lid = (lead or {}).get("leadId") or ""
        if lid:
            claimed[lid] = _norm_chassis((sold or {}).get("chassis"))
        out.append(_billing_row(sold, bucket, lead, reason))

    remaining = []
    for sold in sold_rows or []:
        chassis = _norm_chassis(sold.get("chassis"))
        if not chassis:
            continue
        holders = [l for l in live if chassis in lead_chassis_list(l)]
        if len(holders) > 1:
            keeper = resolve_chassis_holders(holders)
            if keeper:
                take(sold, keeper, _bucket_for_matched_lead(keeper))
                continue
            out.append(_billing_row(
                sold, BUCKET_REVIEW, holders[0],
                "several live leads hold this chassis — connect the original and delete the empty copy",
                holder_leads=holders))
            continue
        if len(holders) == 1:
            take(sold, holders[0], _bucket_for_matched_lead(holders[0]))
            continue
        remaining.append(sold)

    still = []
    for sold in remaining:
        chassis = _norm_chassis(sold.get("chassis"))
        matches = []
        for lead in live:
            have_set = set(lead_chassis_list(lead))
            if have_set and chassis not in have_set:
                continue
            lid = (lead or {}).get("leadId")
            if lid in claimed and claimed[lid] != chassis:
                continue
            mine = occupied - have_set
            hit = match_sold_row(lead, [sold], mine)
            if hit and _norm_chassis(hit.get("chassis")) == chassis:
                matches.append(lead)
        uniq = {(m or {}).get("leadId"): m for m in matches if (m or {}).get("leadId")}
        if len(uniq) == 1:
            lead = next(iter(uniq.values()))
            take(sold, lead, _bucket_for_matched_lead(lead))
            continue
        if len(uniq) > 1:
            out.append(_billing_row(
                sold, BUCKET_REVIEW, None,
                "more than one lead matches this Sold row"))
            continue
        still.append(sold)

    def _empty_score(sold):
        pool = _empty_unclaimed(_live_same_mobile(live, sold.get("mobile")), claimed)
        if not pool:
            pool = _empty_unclaimed(_live_same_name(live, sold.get("customerName")), claimed)
        if len(pool) != 1:
            return 0
        return sold_match_score(sold, pool[0]) or (
            1 if _norm_person_name(sold.get("customerName"))
            == _norm_person_name(pool[0].get("customerName")) else 0)

    still.sort(key=lambda s: (-_empty_score(s), _norm_chassis(s.get("chassis"))))

    leftover = []
    for sold in still:
        chassis = _norm_chassis(sold.get("chassis"))
        same = _live_same_mobile(live, sold.get("mobile"))
        empty = _empty_unclaimed(same, claimed)
        if len(empty) == 1:
            take(sold, empty[0], _bucket_for_matched_lead(empty[0]))
            continue
        if len(empty) > 1:
            out.append(_billing_row(
                sold, BUCKET_REVIEW, None,
                "same mobile, more than one lead without chassis"))
            continue
        if same:
            if any((l or {}).get("leadId") in claimed for l in same):
                out.append(_billing_row(sold, BUCKET_UNMATCHED))
                continue
            if all(
                    lead_chassis_list(l)
                    and chassis not in lead_chassis_list(l)
                    for l in same):
                out.append(_billing_row(sold, BUCKET_UNMATCHED))
                continue
            out.append(_billing_row(
                sold, BUCKET_REVIEW, None,
                "same mobile already on a live lead"))
            continue
        leftover.append(sold)

    leftover.sort(key=lambda s: (-_empty_score(s), _norm_chassis(s.get("chassis"))))
    for sold in leftover:
        chassis = _norm_chassis(sold.get("chassis"))
        same = _live_same_name(live, sold.get("customerName"))
        empty = _empty_unclaimed(same, claimed)
        if len(empty) == 1:
            take(sold, empty[0], _bucket_for_matched_lead(empty[0]))
            continue
        if len(empty) > 1:
            out.append(_billing_row(
                sold, BUCKET_REVIEW, None,
                "same name, more than one lead without chassis"))
            continue
        if same:
            if any((l or {}).get("leadId") in claimed for l in same):
                out.append(_billing_row(sold, BUCKET_UNMATCHED))
                continue
            if all(
                    lead_chassis_list(l)
                    and chassis not in lead_chassis_list(l)
                    for l in same):
                out.append(_billing_row(sold, BUCKET_UNMATCHED))
                continue
            out.append(_billing_row(
                sold, BUCKET_REVIEW, None,
                "same name already on a live lead"))
            continue
        out.append(_billing_row(sold, BUCKET_UNMATCHED))
    return out


async def list_oem_billing(db, leads=None):
    sold = [r async for r in db.oem_sold.find({})]
    if leads is None:
        leads = await load_oem_billing_leads(db)
    return classify_oem_billing(sold, leads)


_OPEN_DUP_STATUSES = {
    "new", "contacted", "follow-up", "followup", "in progress", "inprogress",
}


def is_oem_billing_stub(lead):
    """New file minted by OEM sync — not a booked original."""
    if not (lead or {}).get("oemBillingCreated"):
        return False
    if _lead_is_cancelled(lead):
        return False
    if _lead_is_delivered(lead):
        return False
    status = str((lead or {}).get("currentStatus") or "New").strip().lower()
    return status not in ("booked", "finance process", "financeprocess", "close won", "closewon")


def is_commercial_original(lead):
    """Booked / delivered / Close Won / paid file — keep this one."""
    if not lead or lead.get("dealCancelled"):
        return False
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return False
    if acct == "closed":
        return True
    status = str(lead.get("currentStatus") or "").strip().lower()
    if "close" in status or "deliver" in status or "book" in status or "finance" in status:
        return True
    if _lead_is_delivered(lead):
        return True
    if lead.get("bookingDate") or lead.get("bookingId"):
        return True
    try:
        if float(lead.get("totalReceived") or 0) > 0.01:
            return True
    except (TypeError, ValueError):
        return False
    return False


def is_empty_duplicate_lead(lead):
    """Open empty file that can be deleted after chassis moves to the original.

    Includes Created-from-OEM stubs and a New enquiry on the same mobile
    (Mohan Singh / Prerna vs Close Won / Devang). Executive is ignored.
    """
    if not lead or lead.get("dealCancelled"):
        return False
    if is_commercial_original(lead):
        return False
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived", "closed"):
        return False
    status = str(lead.get("currentStatus") or "new").strip().lower()
    if status not in _OPEN_DUP_STATUSES:
        return False
    try:
        if float(lead.get("totalReceived") or 0) > 0.01:
            return False
    except (TypeError, ValueError):
        return False
    return True


def resolve_chassis_holders(holders):
    """One commercial file + empty copies → keep the commercial. Else None."""
    rows = [l for l in (holders or []) if l]
    if not rows:
        return None
    commercials = [l for l in rows if is_commercial_original(l)]
    empties = [l for l in rows if is_empty_duplicate_lead(l)]
    if len(commercials) == 1 and len(commercials) + len(empties) == len(rows):
        return commercials[0]
    if len(commercials) == 1 and len(empties) == len(rows) - 1:
        return commercials[0]
    return None


def repair_original_lead(lead):
    """True for the real CRM file an OEM stub should join.

    Close Won sets accountStatus=Closed. August deliveries are also excluded
    from live_occupies_vehicle_id (yard rule from 1 Sep). Those files still
    have the payments and scheme — pairing must see them.
    """
    if not lead:
        return False
    if is_oem_billing_stub(lead):
        return False
    if lead.get("dealCancelled"):
        return False
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return False
    return True


def _original_rank(lead):
    """Prefer the finished deal when two files share a mobile."""
    status = str((lead or {}).get("currentStatus") or "").strip().lower()
    acct = str((lead or {}).get("accountStatus") or "").strip().lower()
    money = 0.0
    try:
        money = float((lead or {}).get("totalReceived") or 0)
    except (TypeError, ValueError):
        money = 0.0
    if acct == "closed" or "close" in status:
        tier = 5
    elif _lead_is_delivered(lead) or "deliver" in status:
        tier = 4
    elif status in ("booked", "finance process", "financeprocess") or "book" in status or "finance" in status:
        tier = 3
    elif money > 0:
        tier = 2
    else:
        tier = 1
    return (tier, money)


def _pair_summary(lead):
    lead = lead or {}
    return {
        "leadId": lead.get("leadId") or "",
        "customerName": lead.get("customerName") or "",
        "mobile": _digits10(lead.get("mobile") or lead.get("altMobile")),
        "currentStatus": _lead_crm_status(lead),
        "chassis": _norm_chassis(lead.get("chassisNumber")),
        "invoiceNumber": str(lead.get("invoiceNumber") or "").strip(),
        "model": lead.get("interestedModel") or lead.get("model") or "",
        "executive": lead.get("executive") or "",
        "totalReceived": lead.get("totalReceived") or 0,
        "oemBillingCreated": bool(lead.get("oemBillingCreated")),
    }


def _originals_for_stub(stub, originals):
    """Prefer unique mobile, then unique usable name. Chassis conflict is review."""
    chassis = _norm_chassis((stub or {}).get("chassisNumber"))
    by_mobile = _live_same_mobile(originals, (stub or {}).get("mobile") or (stub or {}).get("altMobile"))
    by_name = _live_same_name(originals, (stub or {}).get("customerName"))
    same_chassis = [
        l for l in originals
        if chassis and chassis in set(lead_chassis_list(l))
    ]

    def _conflict(lead):
        have = set(lead_chassis_list(lead))
        if not have:
            return False
        return bool(chassis) and chassis not in have

    if same_chassis:
        uniq = {(l or {}).get("leadId"): l for l in same_chassis if (l or {}).get("leadId")}
        if len(uniq) == 1:
            lead = next(iter(uniq.values()))
            return {
                "originals": [lead],
                "match": "chassis",
                "conflict": False,
            }
        return {"originals": list(uniq.values()), "match": "chassis", "conflict": True}

    if by_mobile:
        ranked = sorted(by_mobile, key=_original_rank, reverse=True)
        best = _original_rank(ranked[0])
        top = [l for l in ranked if _original_rank(l) == best]
        if len(top) == 1:
            return {"originals": top, "match": "mobile", "conflict": False}
        return {
            "originals": by_mobile,
            "match": "mobile",
            "conflict": True,
        }

    if by_name:
        free = [l for l in by_name if not _conflict(l)]
        blocked = [l for l in by_name if _conflict(l)]
        if len(free) == 1 and not blocked:
            return {"originals": free, "match": "name", "conflict": False}
        return {
            "originals": by_name,
            "match": "name",
            "conflict": True,
        }
    return {"originals": [], "match": "", "conflict": False}


def pair_oem_billing_stubs(leads):
    """Join Created-from-OEM stubs to the booked file they should have matched.

    Safe = unique mobile (or already-same chassis) and the original does not
    already hold a different chassis. Name-only and second-vehicle stay review.
    """
    stubs = [l for l in (leads or []) if is_empty_duplicate_lead(l) or is_oem_billing_stub(l)]
    originals = [l for l in (leads or []) if is_commercial_original(l)]
    claimed = {}
    rows = []
    for stub in stubs:
        stub_id = (stub or {}).get("leadId") or ""
        others = [l for l in originals if (l or {}).get("leadId") != stub_id]
        found = _originals_for_stub(stub, others)
        cands = found.get("originals") or []
        match = found.get("match") or ""
        conflict = bool(found.get("conflict"))
        if len(cands) == 1 and not conflict and match in ("mobile", "chassis"):
            orig = cands[0]
            oid = (orig or {}).get("leadId") or ""
            if oid and oid in claimed:
                rows.append({
                    "action": "review",
                    "reason": "another Created-from-OEM stub already claims this original",
                    "match": match,
                    "stub": _pair_summary(stub),
                    "original": _pair_summary(orig),
                    "candidates": [_pair_summary(orig)],
                })
                continue
            if oid:
                claimed[oid] = stub_id
            already = bool(
                _norm_chassis(stub.get("chassisNumber"))
                and _norm_chassis(stub.get("chassisNumber")) in set(lead_chassis_list(orig)))
            rows.append({
                "action": "safe",
                "reason": (
                    "same chassis already on original" if already
                    else "unique mobile match" if match == "mobile"
                    else "same chassis"
                ),
                "match": match,
                "stub": _pair_summary(stub),
                "original": _pair_summary(orig),
                "candidates": [_pair_summary(orig)],
            })
            continue
        if not cands:
            rows.append({
                "action": "review",
                "reason": "no CRM lead on this mobile or name",
                "match": match,
                "stub": _pair_summary(stub),
                "original": None,
                "candidates": [],
            })
            continue
        if match == "name" and len(cands) == 1 and not conflict:
            reason = "name-only match — confirm before relink"
        elif conflict and match == "mobile":
            reason = "more than one original lead on this mobile"
        elif len(cands) > 1:
            reason = "more than one original lead matches"
        else:
            reason = "needs review"
        rows.append({
            "action": "review",
            "reason": reason,
            "match": match,
            "stub": _pair_summary(stub),
            "original": _pair_summary(cands[0]) if len(cands) == 1 else None,
            "candidates": [_pair_summary(l) for l in cands],
        })
    return rows


def merge_patch_for_stub(original, stub):
    """Chassis / invoice / plate to copy from the stub onto the original.

    Never rewrites commercials. OEM billed ids win when the original is empty
    or already holds this chassis. A different chassis on a same-order pack
    is stamped onto the next empty unit; a single-unit file keeps its own
    chassis and only fills blank invoice/plate.
    """
    chassis = _norm_chassis((stub or {}).get("chassisNumber"))
    invoice = str((stub or {}).get("invoiceNumber") or "").strip()
    plate = str((stub or {}).get("numberPlate") or "").strip()
    have = set(lead_chassis_list(original))
    patch = {}
    same_or_empty = (not have) or (chassis and chassis in have)
    if chassis and same_or_empty:
        if _norm_chassis((original or {}).get("chassisNumber")) != chassis:
            if not is_same_order_pack(original) or not lead_chassis_list(original):
                patch["chassisNumber"] = chassis
        if invoice and _norm_invoice((original or {}).get("invoiceNumber")) != _norm_invoice(invoice):
            if not is_same_order_pack(original) or not lead_invoice_list(original):
                patch["invoiceNumber"] = invoice
        if plate and _norm_invoice((original or {}).get("numberPlate")) != _norm_invoice(plate):
            if not is_same_order_pack(original) or not str((original or {}).get("numberPlate") or "").strip():
                patch["numberPlate"] = plate
        sold_date = str((stub or {}).get("soldDate") or "").strip()[:10]
        stamped = stamp_unit_vehicle_ids(original, chassis, invoice, plate, sold_date)
        if stamped and stamped != list((original or {}).get("units") or []):
            patch["units"] = stamped
    elif invoice and not _norm_invoice((original or {}).get("invoiceNumber")):
        patch["invoiceNumber"] = invoice
    return patch


def sold_row_in_period(row, period):
    """Undated Sold rows stay visible in every month so they are not hidden."""
    if getattr(period, "is_all", True):
        return True
    d = str((row or {}).get("soldDate") or "").strip()
    if len(d) < 7:
        return True
    import period as periodmod
    return periodmod.in_period(d, period)


def inventory_family_key(model, variant=""):
    """Storm / Turbo / HiLoad / HiCity / HiRange — same families as scheme matching."""
    import commercial as ce
    return ce.normalize_scheme_model_key(model, variant)


def inventory_row_matches_lead(row, model, variant=""):
    """True when a yard row is in the same model family as the lead.

    Unmatched OEM rows keep names like "Storm LR" while the lead is "Storm" +
    "Storm LR (PV) …". Exact `row.model == lead.interestedModel` would hide them.
    """
    if not (model or "").strip():
        return True
    want = inventory_family_key(model, variant)
    got = inventory_family_key(row.get("model"), row.get("variant"))
    if want and got == want:
        return True
    oem = inventory_family_key(row.get("oemModel") or "", row.get("oemVariant") or "")
    return bool(want) and oem == want


def _lead_holds_live_yard_chassis(lead):
    """Only active, on/after-1-Sep CRM deliveries occupy a live yard slot."""
    if not lead:
        return False
    if lead.get("dealCancelled"):
        return False
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return False
    ds = str(lead.get("deliveryStatus") or "").lower()
    cs = str(lead.get("currentStatus") or "").lower()
    if ds != "delivered" and cs != "delivered":
        return False
    ddate = str(lead.get("deliveryDate") or "")[:10]
    if ddate and ddate < YARD_LIVE_FROM:
        return False
    return True


async def drop_delivered_from_inventory(db):
    """Chassis delivered here on/after 1 Sep is not available yard stock.

    Last-month Euler deliveries do not hide Coulson PRESENT units. Cancelled
    files do not occupy the yard either — the chassis can be picked on a
    recreated lead with a delivery date after 1 Sep.
    """
    gone = set()
    async for l in db.leads.find({}):
        if not _lead_holds_live_yard_chassis(l):
            continue
        for ch in lead_chassis_list(l):
            gone.add(ch)
    if not gone:
        return 0
    removed = 0
    async for row in db.oem_inventory.find({}):
        if _norm_chassis(row.get("chassis")) in gone:
            await db.oem_inventory.delete_one({"_id": row["_id"]})
            removed += 1
    return removed


async def take_chassis_from_inventory(db, chassis):
    """Remove one chassis from yard when it is marked delivered here."""
    ch = _norm_chassis(chassis)
    if not ch:
        return 0
    removed = 0
    async for row in db.oem_inventory.find({}):
        if _norm_chassis(row.get("chassis")) == ch:
            await db.oem_inventory.delete_one({"_id": row["_id"]})
            removed += 1
    return removed


async def inventory_counts(db):
    present = None
    try:
        import inventory_check
        present = await inventory_check.present_chassis(db)
    except Exception:
        present = None
    counts = {}
    async for v in db.oem_inventory.find({}):
        chassis = str(v.get("chassis") or "").strip()
        if present is not None and chassis not in present:
            continue
        key = (v.get("model") or "", v.get("variant") or "")
        counts[key] = counts.get(key, 0) + 1
    return counts


async def list_inventory(db, model=None, variant=None, *, family=False):
    rows = [r async for r in db.oem_inventory.find({}).sort("model", 1)]
    if not model:
        return rows
    if family or variant:
        return [r for r in rows if inventory_row_matches_lead(r, model, variant or "")]
    return [r for r in rows if str(r.get("model") or "") == str(model)]


async def list_transit_inventory(db, model=None):
    rows = [r async for r in db.oem_inventory_transit.find({}).sort("model", 1)]
    if not model:
        return rows
    return [r for r in rows if str(r.get("model") or "") == str(model)]


def _is_open_booking(lead):
    if not lead or lead.get("dealCancelled"):
        return False
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return False
    st = str(lead.get("currentStatus") or "").lower()
    if "deliver" in st or "lost" in st or "cancel" in st:
        return False
    return "book" in st or "finance" in st


async def need_to_order_bookings(db):
    """Booked / finance leads with no matching chassis currently in the yard."""
    counts = await inventory_counts(db)
    out = []
    async for l in db.leads.find({}):
        if not _is_open_booking(l):
            continue
        model = l.get("interestedModel") or ""
        variant = l.get("variant") or ""
        if counts.get((model, variant), 0) > 0:
            continue
        out.append({
            "leadId": l.get("leadId"),
            "customerName": l.get("customerName") or "",
            "mobile": l.get("mobile") or "",
            "executive": l.get("executive") or "",
            "model": model,
            "variant": variant,
            "bookingDate": l.get("bookingDate") or "",
            "customerPayable": l.get("customerPayable") or 0,
            "currentStatus": l.get("currentStatus") or "",
        })
    out.sort(key=lambda r: (str(r.get("bookingDate") or ""), r.get("customerName") or ""))
    return out
