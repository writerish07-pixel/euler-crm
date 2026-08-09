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
    # entity -> (tab, stable ID field, CRM fields we own, header row hint)
    # Tab names and header rows are overridable by env var. header_row=None means
    # auto-detect (the row carrying the most text labels in the first few rows).
    # Verified against Euler Master (2).xlsx: the Lead Register's real database
    # header row is row 3 starting at column J — rows 1-2 are the SEARCH/helper
    # area, which we never touch.
    "leads": (_tab("GSHEET_TAB_LEADS", "Lead Register"), "leadId",
              ["leadId", "createdDate", "customerName", "mobile", "altMobile", "village", "city",
               "leadSource", "interestedModel", "variant", "executive", "currentStatus", "priority",
               "budget", "nextFollowupDate", "bookingDate", "bookingAmount", "financeRequired",
               "exchangeRequired", "deliveryStatus", "deliveryDate", "outstandingAmount", "remarks",
               "lastUpdated", "accountStatus", "exShowroom", "rto", "insuranceAmount",
               "accessoriesAmount", "handlingCharges", "trc", "fastag", "extendedWarranty",
               "otherCharges", "grossVehicleCost", "customerPayable", "financerName",
               "financeFileNumber", "lastPaymentMode", "totalReceived", "consumerDiscount",
               "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount", "additionalDiscount",
               "totalDiscount", "oemSchemeAmount", "dealerSchemeAmount", "customerOutstanding",
               "companyOutstanding", "insurerName", "invoiceNumber", "chassisNumber", "numberPlate",
               "dealerTotalEarnings"], 3),
    "activities": (_tab("GSHEET_TAB_ACTIVITIES", "Activity Log"), "activityId",
                   ["activityId", "leadId", "date", "time", "activityType", "discussion",
                    "executive", "customerName", "mobile", "model"], None),
    "bookings": (_tab("GSHEET_TAB_BOOKINGS", "Booking Register"), "bookingId",
                 ["bookingId", "leadId", "customerName", "bookingDate", "model", "variant",
                  "bookingAmount", "financeRequired", "exchangeRequired", "snapshotId",
                  "bookingStatus", "createdDate", "amountReceived", "paymentMode"], None),
    "payments": (_tab("GSHEET_TAB_PAYMENTS", "Payment Ledger"), "receiptNumber",
                 ["receiptNumber", "leadId", "customerName", "date", "amount", "paymentMode",
                  "narration", "runningTotal", "outstandingBalance", "paymentId",
                  "financerName", "financeFileNumber"], None),
    "deliveries": (_tab("GSHEET_TAB_DELIVERIES", "Delivery Tracker"), "leadId",
                   ["leadId", "customerName", "insurance", "registration", "invoice", "accessories",
                    "rc", "numberPlate", "pdi", "delivered", "deliveryDate", "insurerName",
                    "invoiceNumber", "chassisNumber"], None),
    "claims": (_tab("GSHEET_TAB_CLAIMS", "Scheme Claim Register"), "claimId",
               ["claimId", "leadId", "customer", "model", "variant", "bookingDate", "component",
                "componentKey", "eligibleClaim", "claimAmount", "receivedAmount", "claimStatus",
                "claimReference", "submittedDate", "approvedDate"], None),
    "insurance": (_tab("GSHEET_TAB_INSURANCE", "Insurance Register"), "entryId",
                  ["entryId", "leadId", "customerName", "mobile", "model", "variant",
                   "insuranceCompany", "policyNumber", "insuranceAmount", "payoutRatePct",
                   "expectedPayout", "receivedPayout", "payoutOutstanding", "status"], None),
    "finance": (_tab("GSHEET_TAB_FINANCE", "Finance Register"), "financeFileNumber",
                ["financeFileNumber", "leadId", "customerName", "financerName",
                 "committedAmount", "disbursedAmount", "financeOutstanding", "status"], None),
    "dealer_earnings": (_tab("GSHEET_TAB_DEALER_EARNINGS", "Dealer Earnings Register"), "leadId",
                        ["leadId", "bookingId", "customerName", "executive", "model", "variant",
                         "bookingDate", "deliveryDate", "invoiceNumber", "customerPayable",
                         "oemEligible", "customerSchemeBenefitPassed", "dealerSchemeRetained",
                         "insurancePayout", "customerInsuranceBenefitPassed", "dealerInsuranceIncome",
                         "financeIncentive", "accessoriesMargin", "exchangeMargin",
                         "documentationIncome", "warrantyIncome", "rsaIncome", "referralIncome",
                         "campaignIncentive", "otherIncome", "dealerTotalEarnings",
                         "dealerMarginNetExGst", "oemExtraSupportRetained"], None),
}

# Entities the CRM computes but which have NO destination in the existing workbook.
# Per the integration rule we do NOT create a tab for them — they are recorded here as
# intentionally unmapped. Exchange values still reach the sheet via the Dealer Earnings
# Register ("Exchange Margin") and the Lead Register ("Exchange Bonus"/"Exchange Required").
INTENTIONALLY_UNMAPPED = {
    "exchange": "No Exchange Register tab exists in the workbook; exchange data is carried by "
                "Lead Register (Exchange Required / Exchange Bonus) and Dealer Earnings Register "
                "(Exchange Margin). No tab is created.",
}

# Explicit, approved aliases: CRM field -> the ACTUAL header text in Euler Master (2).xlsx.
# Normalisation (lowercase, strip non-alphanumerics) already resolves the majority
# (e.g. "Customer Name"<->customerName, "BookingID"<->bookingId, "RTO"<->rto).
# Only genuinely different wording is listed. No fuzzy matching is used anywhere.
HEADER_ALIASES = {
    # Lead Register
    "altMobile": ["alternate mobile"],
    "dsaDiscount": ["dsa bonus", "dsa discount"],
    "dealerTotalEarnings": ["dealer earnings", "total dealer earnings"],
    "nextFollowupDate": ["next follow-up date", "next followup date"],
    # Booking Register
    "model": ["vehicle model", "model", "interested model"],
    "interestedModel": ["interested model", "vehicle model", "model"],
    "snapshotId": ["commercialsnapshotid", "commercial snapshot id"],
    "createdDate": ["created date"],
    "amountReceived": ["amount received"],
    # Payment Ledger
    "date": ["date", "payment date", "receipt date"],
    "amount": ["amount", "payment amount", "receipt amount"],
    # Finance Register — headers differ substantially from CRM field names
    "financeFileNumber": ["file number", "finance file number"],
    "financerName": ["financer", "financer name"],
    "committedAmount": ["sanctioned amount"],
    "disbursedAmount": ["received against file"],
    "financeOutstanding": ["file outstanding"],
    # Insurance Register
    "insuranceCompany": ["insurance company"],
    "payoutRatePct": ["payout rate %", "payout rate"],
    # Scheme Claim Register
    "claimReference": ["claim reference number", "claim reference"],
    "submittedDate": ["claim submitted date"],
    "approvedDate": ["claim approved date"],
    "customer": ["customer", "customer name"],
    # Dealer Earnings Register — note "Customer Insurance Benefit Passed" (S) and
    # "Dealer Insurance Income" (T) are DIFFERENT columns and must not be conflated.
    "customerInsuranceBenefitPassed": ["customer insurance benefit passed"],
    "dealerInsuranceIncome": ["dealer insurance income"],
    "oemEligible": ["oem eligible scheme"],
    "customerSchemeBenefitPassed": ["customer scheme benefit passed"],
    "insurancePayout": ["insurance payout"],
    "dealerSchemeRetained": ["dealer scheme retained"],
    "dealerMarginNetExGst": ["dealer margin net (ex gst)", "dealer margin net ex gst"],
    "oemExtraSupportRetained": ["oem extra support retained"],
    "rsaIncome": ["rsa income"],
}

MASTERS_TAB = _tab("GSHEET_TAB_MASTERS", "Masters")
MASTERS_HEADER = ["Category", "Value", "Status"]

_service = None
_status = {"enabled": False, "reason": "not configured", "email": None}
_health = {"lastWriteOk": None, "lastWriteAt": None, "lastError": None, "writes": 0, "failures": 0}
_header_cache = {}
_headerrow_cache = {}
_idrow_cache = {}   # (tab, header_row) -> {id_value: row_number}
_formula_cache = {}  # (tab, row) -> set of formula-holding column indexes


_RETRY_STATUSES = (429, 500, 503)


def _with_retry(fn, attempts=4):
    """Google Sheets enforces a per-minute read/write quota; a burst of dealership
    activity legitimately returns 429. Retry with backoff instead of dropping the
    write. Combined with the header/ID caches this keeps a normal lifecycle well
    inside quota, and a genuine overload recovers instead of failing."""
    import random
    import time as _t
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as e:
            code = getattr(getattr(e, "resp", None), "status", None)
            try:
                code = int(code)
            except (TypeError, ValueError):
                code = None
            if code not in _RETRY_STATUSES or i == attempts - 1:
                raise
            last = e
            _t.sleep(min(2 ** i, 8) + random.random())
    raise last


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def _col_letter(idx0):
    """0-based column index -> A1 letter (0->A, 26->AA)."""
    s, n = "", idx0 + 1
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


# Where the service-account JSON may live, in priority order. Render Secret Files are
# mounted read-only at /etc/secrets/<filename>, which is why an unset
# GSHEET_CREDENTIALS_PATH previously produced "credentials JSON not found" on Render
# even though the secret file was correctly configured — the old resolver looked at
# nothing else. The credential is never committed; these are runtime locations only.
_SECRET_FILE_NAME = "gsheets_credentials.json"
_CRED_CANDIDATES = [
    ("env:GSHEET_CREDENTIALS_PATH", lambda: os.environ.get("GSHEET_CREDENTIALS_PATH", "").strip()),
    ("render-secret-file", lambda: f"/etc/secrets/{_SECRET_FILE_NAME}"),
    ("backend-local", lambda: str(Path(__file__).resolve().parent / _SECRET_FILE_NAME)),
    ("repo-root-local", lambda: str(Path(__file__).resolve().parent.parent / _SECRET_FILE_NAME)),
]


def resolve_credentials_path():
    """First existing, readable credential file. Returns (path, source_label) or
    (None, None). Only ever returns a PATH — never file contents."""
    for label, getter in _CRED_CANDIDATES:
        try:
            raw = getter()
        except Exception:
            continue
        if not raw:
            continue
        try:
            pth = Path(raw)
            if pth.is_file():
                return str(pth), label
        except (OSError, ValueError):
            continue
    return None, None


def credential_diagnostics():
    """Safe, loggable credential state. Never includes JSON contents or the key."""
    path, source = resolve_credentials_path()
    checked = []
    for label, getter in _CRED_CANDIDATES:
        try:
            raw = getter()
        except Exception:
            raw = ""
        if raw:
            checked.append({"source": label, "path": str(raw), "exists": Path(raw).is_file()})
    return {
        "credential_found": bool(path),
        "credential_source": source,
        "credential_path": path,
        "gsheet_id_present": bool(os.environ.get("GSHEET_ID", "").strip()),
        "candidates_checked": checked,
    }


def _init():
    global _service, _status
    path, source = resolve_credentials_path()
    sheet_id = os.environ.get("GSHEET_ID", "").strip()
    if not path:
        tried = ", ".join(f"{lbl}" for lbl, _ in _CRED_CANDIDATES)
        _status = {"enabled": False, "email": None, "credentialFound": False, "credentialSource": None,
                   "reason": f"credentials JSON not found — looked at: {tried}. On Render add a Secret "
                             f"File named {_SECRET_FILE_NAME} (mounted at /etc/secrets/{_SECRET_FILE_NAME}) "
                             f"or set GSHEET_CREDENTIALS_PATH."}
        _service = None
        return
    if not sheet_id:
        _status = {"enabled": False, "email": None, "credentialFound": True, "credentialSource": source,
                   "reason": "GSHEET_ID missing"}
        _service = None
        return
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import json
        info = json.loads(Path(path).read_text())
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        _status = {"enabled": True, "reason": "connected", "email": info.get("client_email"),
                   "credentialFound": True, "credentialSource": source}
    except Exception as e:
        # Deliberately does NOT interpolate the file contents — only the exception type
        # and the resolved PATH, so a malformed key can never be echoed into logs.
        _service = None
        _status = {"enabled": False, "email": None, "credentialFound": True, "credentialSource": source,
                   "reason": f"credential at {path} could not be loaded ({type(e).__name__})"}


def status():
    global _status
    if _service is None:
        _init()
    if _service is None:
        return {**_status, "spreadsheetId": os.environ.get("GSHEET_ID", ""),
                **credential_diagnostics(), "health": _health}
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
def _header_row_for(entity, tab):
    """Which sheet row carries this tab's real header labels.
    Env override GSHEET_HEADERROW_<ENTITY> wins; then the per-entity hint; then
    auto-detect by picking the row (of the first 5) with the most text labels.
    The Lead Register's real database header is row 3 — rows 1-2 are the
    SEARCH/helper area, which the CRM must never write into."""
    env = os.environ.get(f"GSHEET_HEADERROW_{entity.upper()}", "").strip()
    if env.isdigit():
        return int(env)
    hint = SYNC_MAP.get(entity, (None, None, None, None))[3] if entity in SYNC_MAP else None
    if hint:
        return int(hint)
    if entity in _headerrow_cache:
        return _headerrow_cache[entity]
    sheet_id = os.environ.get("GSHEET_ID", "")
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!1:5").execute()
    rows = res.get("values", [])
    best, best_n = 1, -1
    for i, row in enumerate(rows, start=1):
        n = sum(1 for c in row if isinstance(c, str) and c.strip())
        if n > best_n:
            best_n, best = n, i
    _headerrow_cache[entity] = best
    return best


def _read_header_row(tab, header_row=1):
    sheet_id = os.environ.get("GSHEET_ID", "")
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{header_row}:{header_row}").execute())
    vals = res.get("values", [])
    return vals[0] if vals else []


def _resolve_columns(tab, fields, use_cache=True, header_row=1):
    """Map each CRM field -> 0-based column index using the tab's ACTUAL headers.
    Returns (mapping, missing_fields). Never guesses a position."""
    ck = (tab, header_row)
    if use_cache and ck in _header_cache:
        headers = _header_cache[ck]
    else:
        headers = _read_header_row(tab, header_row)
        _header_cache[ck] = headers
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
        for k in [k for k in _header_cache if k[0] == tab]:
            _header_cache.pop(k, None)
        for k in [k for k in _idrow_cache if k[0] == tab]:
            _idrow_cache.pop(k, None)
        for k in [k for k in _formula_cache if k[0] == tab]:
            _formula_cache.pop(k, None)
    else:
        _header_cache.clear()
        _idrow_cache.clear()
        _headerrow_cache.clear()
        _formula_cache.clear()


# ---------------------------------------------------------------- upsert (GS-2/GS-3)
def _load_id_rows(tab, id_col_idx, start_row):
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(id_col_idx)
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute())
    out = {}
    for i, row in enumerate(res.get("values", []), start=1):
        if i < start_row:
            continue
        if row and str(row[0]).strip():
            out.setdefault(str(row[0]).strip(), i)
    _idrow_cache[(tab, start_row)] = out
    return out


def _find_row_by_id(tab, id_col_idx, id_value, start_row=2):
    """Return the 1-based sheet row number holding id_value in the ID column, else None."""
    target = str(id_value).strip()
    cache = _idrow_cache.get((tab, start_row))
    if cache is not None and target in cache:
        return cache[target]
    # miss -> one refresh read (also primes the cache for the rest of this burst)
    cache = _load_id_rows(tab, id_col_idx, start_row)
    return cache.get(target)


def _formula_cells(tab, row_num, mapping):
    """Which mapped columns in this existing row currently hold a formula.
    Those cells are never overwritten (formula protection)."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    idxs = sorted(mapping.values())
    if not idxs:
        return set()
    ck = (tab, row_num)
    if ck in _formula_cache:
        return _formula_cache[ck]
    rng = f"'{tab}'!{_col_letter(idxs[0])}{row_num}:{_col_letter(idxs[-1])}{row_num}"
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=rng, valueRenderOption="FORMULA").execute())
    vals = (res.get("values") or [[]])
    row = vals[0] if vals else []
    protected = set()
    base = idxs[0]
    for col_idx in idxs:
        off = col_idx - base
        if off < len(row) and isinstance(row[off], str) and row[off].startswith("="):
            protected.add(col_idx)
    _formula_cache[ck] = protected
    return protected


def _upsert_sync(entity, doc):
    """Header-mapped, ID-keyed upsert. Returns a structured result dict."""
    tab, id_field, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][1], SYNC_MAP[entity][2]
    sheet_id = os.environ.get("GSHEET_ID", "")
    header_row = _header_row_for(entity, tab)

    mapping, missing = _resolve_columns(tab, fields, header_row=header_row)
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

    row_num = _find_row_by_id(tab, mapping[id_field], id_value, start_row=header_row + 1)

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
            _with_retry(lambda: _service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": data}).execute())
        return {"ok": True, "operation": "updated", "tab": tab, "row": row_num,
                "id": id_value, "cellsWritten": len(data),
                "formulaCellsPreserved": len(protected), "missingHeaders": missing}

    # New record -> append exactly one row, positioned by header mapping.
    width = max(mapping.values()) + 1
    row = [""] * width
    for f, col_idx in mapping.items():
        row[col_idx] = doc.get(f, "")
    resp = _with_retry(lambda: _service.spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [row]}).execute())
    # Learn the new row number from the append response so the ID cache stays warm —
    # re-reading the whole ID column after every append is what burned the read quota.
    new_row = None
    try:
        rng = (resp or {}).get("updates", {}).get("updatedRange", "")
        m = re.search(r"![A-Z]+(\d+)", rng)
        if m:
            new_row = int(m.group(1))
    except Exception:
        new_row = None
    ck = (tab, header_row + 1)
    if new_row and ck in _idrow_cache:
        _idrow_cache[ck][id_value] = new_row
        _formula_cache.pop((tab, new_row), None)
    else:
        _idrow_cache.pop(ck, None)
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
        return {"enabled": False, "reason": _status.get("reason", "sync disabled"),
                **credential_diagnostics(), "tabs": {}}
    invalidate_header_cache()
    out = {}
    for entity, spec in SYNC_MAP.items():
        tab, id_field, fields = spec[0], spec[1], spec[2]
        try:
            hr = _header_row_for(entity, tab)
            headers = _read_header_row(tab, hr)
        except Exception as e:
            out[entity] = {"tab": tab, "tabFound": False, "error": str(e)[:300],
                           "note": "tab not found or unreadable — CRM will not write here"}
            continue
        mapping, missing = _resolve_columns(tab, fields, use_cache=False, header_row=hr)
        out[entity] = {
            "tab": tab, "tabFound": True, "idField": id_field, "headerRow": hr,
            "idColumnResolved": id_field in mapping,
            "sheetHeaders": headers,
            "resolved": {f: _col_letter(i) for f, i in sorted(mapping.items(), key=lambda kv: kv[1])},
            "missingHeaders": missing,
            "willSync": id_field in mapping,
        }
    return {"enabled": True, "spreadsheetId": os.environ.get("GSHEET_ID", ""),
            **credential_diagnostics(), "tabs": out,
            "intentionallyUnmapped": INTENTIONALLY_UNMAPPED}


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
    """DISABLED BY DEFAULT. The existing workbook's Masters tab uses a
    column-per-category layout (col A header "Lead Sources" with values beneath),
    NOT the Category|Value|Status shape this mirror writes. Running it would clear
    A1:Z10000 and destroy the dealership's existing Masters structure, which the
    integration rules forbid. Set GSHEET_SYNC_MASTERS=1 only after the Masters tab
    has been confirmed to match this shape."""
    if os.environ.get("GSHEET_SYNC_MASTERS", "").strip() not in ("1", "true", "yes"):
        return False
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


def _read_id_column(tab, id_col_idx, header_row=1):
    """All non-empty values in a tab's ID column (used by the reconciliation report)."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(id_col_idx)
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute()
    out = set()
    for i, row in enumerate(res.get("values", []), start=1):
        if i <= header_row:
            continue  # header/helper area
        if row and str(row[0]).strip():
            out.add(str(row[0]).strip())
    return out


def count_rows_for(entity, id_value):
    """Actual number of rows in the live sheet whose ID column equals id_value.
    Read-only. Used by the go-live verifier to prove idempotency against the real
    spreadsheet rather than trusting an HTTP 200."""
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled")}
    spec = SYNC_MAP.get(entity)
    if not spec:
        return {"ok": False, "reason": f"entity '{entity}' has no sheet destination"}
    tab, id_field, fields = spec[0], spec[1], spec[2]
    try:
        hr = _header_row_for(entity, tab)
        mapping, _ = _resolve_columns(tab, fields, use_cache=False, header_row=hr)
        if id_field not in mapping:
            return {"ok": False, "tab": tab, "reason": f"ID header '{id_field}' not resolvable"}
        letter = _col_letter(mapping[id_field])
        res = _service.spreadsheets().values().get(
            spreadsheetId=os.environ.get("GSHEET_ID", ""), range=f"'{tab}'!{letter}:{letter}").execute()
        target = str(id_value).strip()
        rows = [i for i, r in enumerate(res.get("values", []), start=1)
                if i > hr and r and str(r[0]).strip() == target]
        return {"ok": True, "tab": tab, "idField": id_field, "headerRow": hr,
                "column": letter, "count": len(rows), "rows": rows}
    except Exception as e:
        return {"ok": False, "tab": tab, "reason": str(e)[:200]}
