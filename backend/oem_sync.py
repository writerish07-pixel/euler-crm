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


async def _access_token(db, username=None, password=None):
    """Prefer a pasted Coulson session. Only call euler-auth /login when there is none.

    Euler accepts the dealer password in a browser on coulson.eulerlogistics.com and
    refuses the same password from this server. A live session skips that login.
    Returns (token, source) — source is session / settings / env / inline, or empty.
    """
    if username and password:
        return coulson_client.login(username, password), "inline"
    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    token = session_from_doc(doc)
    if token:
        return token, "session"
    if session_expired(doc):
        raise coulson_client.CoulsonError(
            "Coulson session expired — sign in at coulson.eulerlogistics.com and paste a new session")
    user, pw, src = await resolve_credentials(db)
    if not credentials_configured(user, pw):
        return "", ""
    return coulson_client.login(user, pw), src or "settings"


async def sync_from_coulson(db, *, username=None, password=None):
    """Pull OEM prices + PRESENT inventory. Fail-soft: raises CoulsonError on auth/API failure."""
    catalog_result = await apply_catalog(db)
    token, src = await _access_token(db, username, password)
    if not token:
        await _record_sync(db, False, "Coulson credentials not configured")
        return {"ok": False, "reason": "not_configured", "catalog": catalog_result,
                "changedPriceIds": catalog_result.get("changedPriceIds") or []}

    oem_models = coulson_client.fetch_sap_models(token)
    vehicles = coulson_client.fetch_present_inventory(token)
    sold_vehicles = []
    try:
        sold_vehicles = coulson_client.fetch_sold_inventory(token) or []
    except coulson_client.CoulsonError as e:
        log.warning("Coulson sold inventory skipped: %s", e)
    except Exception:
        log.exception("Coulson sold inventory failed")

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
    dropped = await drop_delivered_from_inventory(db)
    yard_count = await db.oem_inventory.count_documents({})
    sold_count = await replace_sold_inventory(db, sold_vehicles, oem_by_id, by_key)

    extra = {
        "inventoryCount": yard_count,
        "soldCount": sold_count,
        "deliveredDropped": dropped,
        "oemModelCount": len(oem_models),
        "pricesUpdated": prices_updated,
        "unmatchedOemSkus": unmatched_oem,
        "credentialSource": src,
        "changedPriceIds": list(dict.fromkeys(
            (catalog_result.get("changedPriceIds") or []) + changed_ids)),
    }
    await _record_sync(db, True, "", extra)
    return {"ok": True, "catalog": catalog_result, **extra}


# Live yard chassis pick / uniqueness / drop-from-inventory apply from this date.
# Last-month Euler deliveries (and last-month Coulson PRESENT gaps) must not hide
# live stock or block a recreated lead delivered on/after 1 Sep.
YARD_LIVE_FROM = "2026-09-01"


def _norm_chassis(s):
    return re.sub(r"\s+", "", str(s or "")).strip().upper()


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
    "registration_number", "emch", "number_plate", "numberPlate",
    "vehicle_number", "reg_no",
)
_CHASSIS_KEYS = ("chassis", "chassis_number", "chassisNumber", "vin")


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


def vehicle_invoice(row):
    return _first_str(row, _INVOICE_KEYS)


def vehicle_plate(row):
    return _first_str(row, _PLATE_KEYS)


def _sold_doc(vehicle, sku, price):
    inv = _inventory_doc(vehicle, sku, price)
    mobile = vehicle_mobile(vehicle)
    return {
        **inv,
        "chassis": vehicle_chassis(vehicle) or inv.get("chassis") or "",
        "mobile": mobile,
        "invoiceNumber": vehicle_invoice(vehicle),
        "numberPlate": vehicle_plate(vehicle) or inv.get("emch") or "",
        "customerName": str(
            vehicle.get("customer_name") or vehicle.get("customerName")
            or vehicle.get("billed_customer_name")
            or (vehicle.get("customer") or {}).get("name")
            or ""
        ).strip(),
        "coulsonStatus": vehicle.get("_coulsonStatus") or "SOLD",
        "source": "coulson_sold",
    }


async def replace_sold_inventory(db, vehicles, oem_by_id, by_key):
    """Replace oem_sold with the latest Coulson Sold/Billed list."""
    docs = []
    seen = set()
    for v in vehicles or []:
        sku = None
        price = 0.0
        oem_full = oem_by_id.get(v.get("sap_vehicle_model_id")) if oem_by_id else None
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
        doc = _sold_doc(v, sku, price)
        ch = _norm_chassis(doc.get("chassis"))
        if not ch or ch in seen:
            continue
        seen.add(ch)
        docs.append(doc)
    await db.oem_sold.delete_many({})
    if docs:
        await db.oem_sold.insert_many(docs)
    return len(docs)


async def refresh_sold_inventory(db):
    """Live Sold-tab pull without rewriting yard PRESENT stock."""
    token, _src = await _access_token(db)
    if not token:
        return 0
    sold_vehicles = coulson_client.fetch_sold_inventory(token) or []
    oem_models = []
    try:
        oem_models = coulson_client.fetch_sap_models(token) or []
    except coulson_client.CoulsonError:
        oem_models = []
    oem_by_id = {m.get("id"): m for m in oem_models if m.get("id")}
    by_key = {s.key: [] for s in cat.CATALOG}
    for oem in oem_models:
        sku = cat.sku_for_oem_row(oem)
        if sku:
            by_key[sku.key].append(oem)
    return await replace_sold_inventory(db, sold_vehicles, oem_by_id, by_key)


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


async def match_sold_for_lead(db, lead):
    """Unique CRM mobile → Coulson sold vehicle. None when missing or ambiguous."""
    mobile = _digits10((lead or {}).get("mobile") or (lead or {}).get("altMobile"))
    if len(mobile) != 10:
        return None
    candidates = []
    async for row in db.oem_sold.find({"mobile": mobile}):
        score = sold_match_score(row, lead)
        if score:
            candidates.append((score, row))
    if not candidates:
        async for row in db.oem_sold.find({}):
            if _digits10(row.get("mobile")) == mobile:
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
    row = top[0]
    return {
        "matched": True,
        "chassis": row.get("chassis") or "",
        "invoiceNumber": row.get("invoiceNumber") or "",
        "numberPlate": row.get("numberPlate") or "",
        "mobile": mobile,
        "model": row.get("model") or "",
        "variant": row.get("variant") or "",
        "customerName": row.get("customerName") or "",
        "coulsonStatus": row.get("coulsonStatus") or "SOLD",
        "source": "coulson_sold",
    }


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
    async for l in db.leads.find({"chassisNumber": {"$exists": True, "$nin": ["", None]}}):
        if not _lead_holds_live_yard_chassis(l):
            continue
        ch = _norm_chassis(l.get("chassisNumber"))
        if ch:
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
    counts = {}
    async for v in db.oem_inventory.find({}):
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
