"""Two-way-safe sync into the EXISTING Euler Master Google Sheet.

Design rules (the existing spreadsheet is the business template and is FINAL):
  * We never create, rename, reorder or delete tabs or columns.
  * We never write by column position. Every write resolves its destination column
    from the tab's ACTUAL header row at runtime (GS-1). If a header we need is not
    present we refuse to write and report a sync error rather than guessing.
  * Every transactional write is an UPSERT keyed on a stable ID (GS-2/GS-3):
    the ID column is scanned, and an existing row is UPDATED in place; only a
    genuinely new ID appends a row. Running the same sync twice is a no-op.
  * We only ever write the specific cells we own. Any column not in our field map
    is left completely untouched, and any mapped cell that currently holds a
    formula is skipped so dashboard/derived columns survive (formula protection).
  * Callers get a structured result so a failed write can be logged and retried
    instead of vanishing (GS-4). Because writes are upserts, a retry after a
    "succeeded but timed out" call finds the ID and updates it — never duplicates.

Uses a Google Service Account. Activates once a credentials JSON is present at
GSHEET_CREDENTIALS_PATH and the sheet is shared with the service account email as
Editor. If not configured, every call is a safe no-op.
"""
import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# entity -> (tab name, stable ID field, ordered CRM fields we own in that tab).
# Tab names are overridable by env var so the CRM can be pointed at the existing
# sheet's real tab names without any code change (GS-5).
def _tab(env_key, default):
    return os.environ.get(env_key, "").strip() or default


SYNC_MAP = {
    "leads": (_tab("GSHEET_TAB_LEADS", "Lead Register"), "leadId",
              ["leadId", "createdDate", "customerName", "mobile", "leadSource",
               "interestedModel", "variant", "executive", "currentStatus"]),
    "bookings": (_tab("GSHEET_TAB_BOOKINGS", "Booking Register"), "bookingId",
                 ["bookingId", "leadId", "customerName", "bookingDate", "model",
                  "variant", "bookingAmount", "paymentMode", "bookingStatus"]),
    "payments": (_tab("GSHEET_TAB_PAYMENTS", "Payment Ledger"), "receiptNumber",
                 ["receiptNumber", "paymentId", "leadId", "customerName", "date", "amount",
                  "paymentMode", "narration", "runningTotal", "outstandingBalance"]),
    "deliveries": (_tab("GSHEET_TAB_DELIVERIES", "Delivery Tracker"), "leadId",
                   ["leadId", "customerName", "deliveryDate", "delivered",
                    "invoiceNumber", "chassisNumber", "numberPlate"]),
    "claims": (_tab("GSHEET_TAB_CLAIMS", "Scheme Claim Register"), "claimId",
               ["claimId", "leadId", "customer", "model", "component",
                "claimAmount", "claimStatus", "receivedAmount", "claimReference"]),
    "insurance": (_tab("GSHEET_TAB_INSURANCE", "Insurance Register"), "entryId",
                  ["entryId", "leadId", "customerName", "insuranceCompany",
                   "policyNumber", "insuranceAmount", "payoutRatePct",
                   "expectedPayout", "receivedPayout", "payoutOutstanding", "status"]),
    # GS-5 — previously had no Sheet destination at all.
    "finance": (_tab("GSHEET_TAB_FINANCE", "Finance Register"), "financeFileNumber",
                ["financeFileNumber", "leadId", "customerName", "financerName",
                 "committedAmount", "disbursedAmount", "financeOutstanding", "status"]),
    "exchange": (_tab("GSHEET_TAB_EXCHANGE", "Exchange Register"), "leadId",
                 ["leadId", "customerName", "exchangeRequired", "finalExchangeValue",
                  "exchangeBonus", "exchangeMargin"]),
    "dealer_earnings": (_tab("GSHEET_TAB_DEALER_EARNINGS", "Dealer Earnings"), "leadId",
                        ["leadId", "customerName", "model", "dealerMarginNetExGst",
                         "dealerSchemeRetained", "customerInsuranceBenefitPassed",
                         "financeIncentive", "accessoriesMargin", "exchangeMargin",
                         "documentationIncome", "warrantyIncome", "rsaIncome",
                         "referralIncome", "campaignIncentive", "otherIncome",
                         "oemExtraSupportRetained", "extraDealerIncomeTotal",
                         "dealerTotalEarnings"]),
}

# Header aliases for the few CRM fields whose natural sheet header does not
# normalise to the same token. Normalisation (lowercase, strip non-alphanumerics)
# already matches e.g. "Customer Name" <-> customerName, "Lead ID" <-> leadId.
HEADER_ALIASES = {
    "payoutRatePct": ["payout rate", "payout rate %", "payoutrate", "payout %"],
    "interestedModel": ["model", "interested model"],
    "customer": ["customer name", "customer"],
    "customerName": ["customer name", "customer"],
    "date": ["payment date", "date", "receipt date"],
    "amount": ["amount", "payment amount", "receipt amount"],
    "dealerMarginNetExGst": ["dealer margin", "dealer margin net ex gst", "dealer margin (net ex gst)"],
    "dealerSchemeRetained": ["dealer scheme retained", "scheme retained"],
    "customerInsuranceBenefitPassed": ["dealer insurance income", "customer insurance benefit passed"],
    "extraDealerIncomeTotal": ["extra dealer income", "extra income total"],
    "dealerTotalEarnings": ["dealer total earnings", "total earnings"],
    "financeFileNumber": ["finance file number", "file number", "finance file no"],
    "committedAmount": ["committed amount", "finance committed"],
    "disbursedAmount": ["disbursed amount", "finance disbursed"],
    "financeOutstanding": ["finance outstanding", "outstanding"],
}

MASTERS_TAB = _tab("GSHEET_TAB_MASTERS", "Masters")
MASTERS_HEADER = ["Category", "Value", "Status"]

_service = None
_status = {"enabled": False, "reason": "not configured", "email": None}
_health = {"lastWriteOk": None, "lastWriteAt": None, "lastError": None, "writes": 0, "failures": 0}
_header_cache = {}


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _col_letter(idx0):
    """0-based column index -> A1 letter (0->A, 26->AA)."""
    s, n = "", idx0 + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _init():
    global _service, _status
    path = os.environ.get("GSHEET_CREDENTIALS_PATH", "")
    sheet_id = os.environ.get("GSHEET_ID", "")
    if not path or not Path(path).exists():
        _status = {"enabled": False, "reason": "credentials JSON not found — add the service account key to enable sync", "email": None}
        _service = None
        return
    if not sheet_id:
        _status = {"enabled": False, "reason": "GSHEET_ID missing", "email": None}
        return
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import json
        info = json.loads(Path(path).read_text())
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        _status = {"enabled": True, "reason": "connected", "email": info.get("client_email")}
    except Exception as e:
        _service = None
        _status = {"enabled": False, "reason": f"init failed: {e}", "email": None}


def status():
    global _status
    if _service is None:
        _init()
    if _service is None:
        return {**_status, "spreadsheetId": os.environ.get("GSHEET_ID", ""), "health": _health}
    sheet_id = os.environ.get("GSHEET_ID", "")
    try:
        _service.spreadsheets().get(spreadsheetId=sheet_id, fields="properties.title").execute()
        _status["canRead"] = True
    except Exception:
        _status.update({"enabled": False, "canRead": False, "canWrite": False,
                        "reason": "cannot access sheet — share it with the service account email"})
        return {**_status, "spreadsheetId": sheet_id, "health": _health}
    try:
        _service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": []}).execute()
        _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
    except Exception as e:
        code = getattr(getattr(e, "resp", None), "status", None)
        msg = str(e)
        if str(code) == "400" or "at least one request" in msg:
            _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
        else:
            _status.update({"enabled": False, "canWrite": False,
                            "reason": "read-only — share the sheet with the service account email as EDITOR to enable syncing"})
    return {**_status, "spreadsheetId": sheet_id, "health": _health}


# ---------------------------------------------------------------- header mapping (GS-1)
def _read_header_row(tab):
    sheet_id = os.environ.get("GSHEET_ID", "")
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!1:1").execute()
    vals = res.get("values", [])
    return vals[0] if vals else []


def _resolve_columns(tab, fields, use_cache=True):
    """Map each CRM field -> 0-based column index using the tab's ACTUAL headers.
    Returns (mapping, missing_fields). Never guesses a position."""
    if use_cache and tab in _header_cache:
        headers = _header_cache[tab]
    else:
        headers = _read_header_row(tab)
        _header_cache[tab] = headers
    by_norm = {}
    for i, h in enumerate(headers):
        n = _norm(h)
        if n and n not in by_norm:
            by_norm[n] = i
    mapping, missing = {}, []
    for f in fields:
        idx = by_norm.get(_norm(f))
        if idx is None:
            for alias in HEADER_ALIASES.get(f, []):
                idx = by_norm.get(_norm(alias))
                if idx is not None:
                    break
        if idx is None:
            missing.append(f)
        else:
            mapping[f] = idx
    return mapping, missing


def invalidate_header_cache(tab=None):
    if tab:
        _header_cache.pop(tab, None)
    else:
        _header_cache.clear()


# ---------------------------------------------------------------- upsert (GS-2/GS-3)
def _find_row_by_id(tab, id_col_idx, id_value):
    """Return the 1-based sheet row number holding id_value in the ID column, else None."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(id_col_idx)
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute()
    target = str(id_value).strip()
    for i, row in enumerate(res.get("values", []), start=1):
        if row and str(row[0]).strip() == target:
            return i
    return None


def _formula_cells(tab, row_num, mapping):
    """Which mapped columns in this existing row currently hold a formula.
    Those cells are never overwritten (formula protection)."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    idxs = sorted(mapping.values())
    if not idxs:
        return set()
    rng = f"'{tab}'!{_col_letter(idxs[0])}{row_num}:{_col_letter(idxs[-1])}{row_num}"
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=rng, valueRenderOption="FORMULA").execute()
    vals = (res.get("values") or [[]])
    row = vals[0] if vals else []
    protected = set()
    base = idxs[0]
    for col_idx in idxs:
        off = col_idx - base
        if off < len(row) and isinstance(row[off], str) and row[off].startswith("="):
            protected.add(col_idx)
    return protected


def _upsert_sync(entity, doc):
    """Header-mapped, ID-keyed upsert. Returns a structured result dict."""
    tab, id_field, fields = SYNC_MAP[entity]
    sheet_id = os.environ.get("GSHEET_ID", "")

    mapping, missing = _resolve_columns(tab, fields)
    if id_field in missing:
        # Without the ID column we cannot be idempotent — refuse rather than guess.
        invalidate_header_cache(tab)
        return {"ok": False, "operation": "refused", "tab": tab,
                "error": f"required ID header for '{id_field}' not found in tab '{tab}' — "
                         f"cannot upsert without it (no positional guessing)", "missingHeaders": missing}
    if not mapping:
        invalidate_header_cache(tab)
        return {"ok": False, "operation": "refused", "tab": tab,
                "error": f"no matching headers found in tab '{tab}'", "missingHeaders": missing}

    id_value = str(doc.get(id_field, "") or "").strip()
    if not id_value:
        return {"ok": False, "operation": "refused", "tab": tab,
                "error": f"record has no value for stable ID field '{id_field}'"}

    row_num = _find_row_by_id(tab, mapping[id_field], id_value)

    if row_num:
        protected = _formula_cells(tab, row_num, mapping)
        data = []
        for f, col_idx in mapping.items():
            if col_idx in protected:
                continue          # formula-controlled cell: leave intact
            if f not in doc:
                continue          # field not supplied on this update: don't blank it
            data.append({"range": f"'{tab}'!{_col_letter(col_idx)}{row_num}",
                         "values": [[doc.get(f, "")]]})
        if data:
            _service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data}).execute()
        return {"ok": True, "operation": "updated", "tab": tab, "row": row_num,
                "id": id_value, "cellsWritten": len(data),
                "formulaCellsPreserved": len(protected), "missingHeaders": missing}

    # New record -> append exactly one row, positioned by header mapping.
    width = max(mapping.values()) + 1
    row = [""] * width
    for f, col_idx in mapping.items():
        row[col_idx] = doc.get(f, "")
    _service.spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [row]}).execute()
    return {"ok": True, "operation": "appended", "tab": tab, "id": id_value,
            "cellsWritten": len(mapping), "missingHeaders": missing}


async def sync(entity: str, doc: dict):
    """Idempotent upsert of one record into its existing tab.

    Returns {"ok": bool, "operation": appended|updated|refused|skipped|error, ...}
    so the caller can persist a retryable sync-log entry (GS-4). Never raises.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": True, "operation": "skipped", "reason": _status.get("reason", "sync disabled")}
    if entity not in SYNC_MAP:
        return {"ok": False, "operation": "error", "error": f"unknown entity '{entity}'"}
    try:
        res = await asyncio.to_thread(_upsert_sync, entity, doc)
        if res.get("ok"):
            _health.update({"lastWriteOk": True, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                            "lastError": None, "writes": _health["writes"] + 1})
        else:
            _health.update({"lastWriteOk": False, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                            "lastError": str(res.get("error"))[:300], "failures": _health["failures"] + 1})
        return res
    except Exception as e:
        invalidate_header_cache()
        _status["lastError"] = str(e)
        _health.update({"lastWriteOk": False, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                        "lastError": str(e)[:300], "failures": _health["failures"] + 1})
        return {"ok": False, "operation": "error", "tab": SYNC_MAP[entity][0], "error": str(e)[:500]}


async def append(entity: str, doc: dict):
    """Back-compat shim: the old append-only entry point is now an idempotent
    upsert. Kept so no call site can accidentally re-introduce duplicate rows."""
    res = await sync(entity, doc)
    return bool(res.get("ok"))


def preflight():
    """Header-mapping report for every mapped tab. Read-only; no writes.
    Shows exactly which CRM fields resolve to which existing sheet header."""
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"enabled": False, "reason": _status.get("reason", "sync disabled"), "tabs": {}}
    invalidate_header_cache()
    out = {}
    for entity, (tab, id_field, fields) in SYNC_MAP.items():
        try:
            headers = _read_header_row(tab)
        except Exception as e:
            out[entity] = {"tab": tab, "tabFound": False, "error": str(e)[:300],
                           "note": "tab not found or unreadable — CRM will not write here"}
            continue
        mapping, missing = _resolve_columns(tab, fields, use_cache=False)
        out[entity] = {
            "tab": tab, "tabFound": True, "idField": id_field,
            "idColumnResolved": id_field in mapping,
            "sheetHeaders": headers,
            "resolved": {f: _col_letter(i) for f, i in sorted(mapping.items(), key=lambda kv: kv[1])},
            "missingHeaders": missing,
            "willSync": id_field in mapping,
        }
    return {"enabled": True, "spreadsheetId": os.environ.get("GSHEET_ID", ""), "tabs": out}


# ---------------------------------------------------------------- masters (unchanged)
def _sync_masters_sync(rows):
    """Full mirror (not append) — Masters is a small, user-editable list where
    deletes must actually disappear from the sheet, unlike the transactional tabs."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    _service.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"'{MASTERS_TAB}'!A1:Z10000", body={},
    ).execute()
    values = [MASTERS_HEADER] + [[r.get("category", ""), r.get("value", ""), r.get("status", "Active")] for r in rows]
    _service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=f"'{MASTERS_TAB}'!A1",
        valueInputOption="USER_ENTERED", body={"values": values},
    ).execute()


async def sync_masters(rows):
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return False
    try:
        await asyncio.to_thread(_sync_masters_sync, rows)
        _health.update({"lastWriteOk": True, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                        "lastError": None, "writes": _health["writes"] + 1})
        return True
    except Exception as e:
        _status["lastError"] = str(e)
        _health.update({"lastWriteOk": False, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                        "lastError": str(e)[:300], "failures": _health["failures"] + 1})
        return False


async def backfill(datasets):
    """Bulk reconcile: upserts every supplied record. Idempotent by construction —
    existing IDs are updated in place, only genuinely new IDs append."""
    global _service
    if _service is None:
        _init()
    st = status()
    if not st.get("enabled") or not st.get("canWrite"):
        return {"ok": False, "reason": st.get("reason", "sync not enabled"), "canWrite": st.get("canWrite", False)}
    invalidate_header_cache()
    result = {}
    for entity, docs in datasets.items():
        if entity not in SYNC_MAP:
            continue
        appended = updated = failed = 0
        errors = []
        for d in docs:
            r = await sync(entity, d)
            if r.get("operation") == "appended":
                appended += 1
            elif r.get("operation") == "updated":
                updated += 1
            elif not r.get("ok"):
                failed += 1
                if len(errors) < 3:
                    errors.append(r.get("error"))
        result[entity] = {"appended": appended, "updated": updated, "failed": failed}
        if errors:
            result[entity]["errors"] = errors
    return {"ok": True, "result": result}


# initialise on import
_init()


def _read_id_column(tab, id_col_idx):
    """All non-empty values in a tab's ID column (used by the reconciliation report)."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(id_col_idx)
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute()
    out = set()
    for i, row in enumerate(res.get("values", [])):
        if i == 0:
            continue  # header
        if row and str(row[0]).strip():
            out.add(str(row[0]).strip())
    return out
