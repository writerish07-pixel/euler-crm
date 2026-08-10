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
    # Lead Register is a normal register (same shape as Booking / Claims / etc.):
    # header permanently in row 1 starting at column A; lead rows below in sequence.
    # (Legacy SEARCH/helper block in A:I + header at J3 was removed from the live sheet.)
    "leads": (_tab("GSHEET_TAB_LEADS", "Lead Register"), "leadId",
              ["leadId", "createdDate", "customerName", "mobile", "altMobile", "village", "city",
               "leadSource", "interestedModel", "variant", "executive", "currentStatus", "priority",
               "budget", "nextFollowupDate", "bookingDate", "bookingAmount", "financeRequired",
               "exchangeRequired", "deliveryStatus", "deliveryDate", "outstandingAmount", "remarks",
               "lastUpdated", "accountStatus", "exShowroom", "rto", "insuranceAmount",
               "accessoriesAmount", "handlingCharges", "trc", "fastag", "extendedWarranty",
               "otherCharges", "grossVehicleCost", "customerPayable", "financerName",
               "financeFileNumber", "lastPaymentMode", "totalReceived", "consumerDiscount",
               "exchangeBonus", "loyaltyBonus", "insuranceBenefit", "referralBonus", "dsaDiscount",
               "additionalDiscount",
               "totalDiscount", "oemSchemeAmount", "dealerSchemeAmount", "customerOutstanding",
               "companyOutstanding", "insurerName", "invoiceNumber", "chassisNumber", "numberPlate",
               "dealerTotalEarnings",
               # Closure + delivery-checklist columns. All of these were already
               # persisted on the lead by close_lead / mark_delivery; they simply had
               # no Sheet mapping, so the register showed blanks for closed leads.
               "closedDate", "closeReason", "finalOutstanding",
               "insuranceStatus", "registrationStatus", "invoiceStatus", "rcStatus", "pdiStatus",
               # Newly sourced: attribution and activity summary (see SOURCE_REQUIRED
               # below for the Lead Register columns that still have no source).
               "lastActivity", "lastUpdatedBy", "closedBy", "closeTimestamp"], 1),
    "activities": (_tab("GSHEET_TAB_ACTIVITIES", "Activity Log"), "activityId",
                   ["activityId", "leadId", "date", "time", "activityType", "discussion",
                    "executive", "customerName", "mobile", "model",
                    # Already captured by ActivityIn and stored via model_dump().
                    "nextFollowup"], None),
    "bookings": (_tab("GSHEET_TAB_BOOKINGS", "Booking Register"), "bookingId",
                 ["bookingId", "leadId", "customerName", "bookingDate", "model", "variant",
                  "bookingAmount", "financeRequired", "exchangeRequired", "snapshotId",
                  "bookingStatus", "createdDate", "amountReceived", "paymentMode",
                  "createdBy", "lastUpdated", "dealerTotalEarnings"], None),
    "payments": (_tab("GSHEET_TAB_PAYMENTS", "Payment Ledger"), "receiptNumber",
                 ["receiptNumber", "leadId", "customerName", "date", "amount", "paymentMode",
                  "narration", "runningTotal", "outstandingBalance", "paymentId",
                  "financerName", "financeFileNumber"], None),
    "deliveries": (_tab("GSHEET_TAB_DELIVERIES", "Delivery Tracker"), "leadId",
                   ["leadId", "customerName", "insurance", "registration", "invoice", "accessories",
                    "rc", "numberPlate", "pdi", "delivered", "deliveryDate", "insurerName",
                    "invoiceNumber", "chassisNumber", "deliveryId", "dealerTotalEarnings",
                    # Already captured by DeliveryIn and stored via model_dump().
                    "feedback"], None),
    "claims": (_tab("GSHEET_TAB_CLAIMS", "Scheme Claim Register"), "claimId",
               ["claimId", "leadId", "customer", "model", "variant", "bookingDate", "component",
                "componentKey", "eligibleClaim", "claimAmount", "receivedAmount", "claimStatus",
                "claimReference", "submittedDate", "approvedDate",
                # Already derivable from the lead / booking / scheme split — these were
                # simply never mapped, which is why Scheme Month was blank on all 17 rows.
                "bookingId", "schemeMonth", "executive", "consumerDiscount", "exchangeBonus",
                "loyaltyBonus", "insuranceBenefit", "referralBonus", "dsaDiscount",
                "additionalDiscount", "rtoBenefit", "rtoInsuranceBenefit",
                "totalDiscount", "dealerDiscount", "oemDiscount", "claimRequired",
                "ageingDays",
                # Newly sourced on the claim record itself.
                "source", "dsaApproval", "claimReceivedDate", "claimRemarks"], None),
    "insurance": (_tab("GSHEET_TAB_INSURANCE", "Insurance Register"), "entryId",
                  ["entryId", "leadId", "customerName", "mobile", "model", "variant",
                   "insuranceCompany", "policyNumber", "insuranceAmount", "payoutRatePct",
                   "expectedPayout", "receivedPayout", "payoutOutstanding", "status",
                   "policyDate", "deliveryDate", "lastUpdated", "remarks",
                   # Already captured by InsuranceIn and stored via model_dump().
                   "insuranceExecutive"], None),
    "finance": (_tab("GSHEET_TAB_FINANCE", "Finance Register"), "financeFileNumber",
                ["financeFileNumber", "leadId", "customerName", "financerName",
                 "committedAmount", "disbursedAmount", "financeOutstanding", "status",
                 "lastPaymentDate", "lastUpdated"], None),
    "dealer_earnings": (_tab("GSHEET_TAB_DEALER_EARNINGS", "Dealer Earnings Register"), "leadId",
                        ["leadId", "bookingId", "customerName", "executive", "model", "variant",
                         "bookingDate", "deliveryDate", "invoiceNumber", "customerPayable",
                         "oemEligible", "customerSchemeBenefitPassed", "dealerSchemeRetained",
                         "insurancePayout", "customerInsuranceBenefitPassed", "dealerInsuranceIncome",
                         "financeIncentive", "accessoriesMargin", "exchangeMargin",
                         "documentationIncome", "warrantyIncome", "rsaIncome", "referralIncome",
                         "campaignIncentive", "otherIncome", "dealerTotalEarnings",
                         "dealerMarginNetExGst", "oemExtraSupportRetained",
                         # Margin components and per-component scheme retention: both are
                         # returned by commercial.py today and are now persisted on the lead
                         # by recompute_lead, so they are mappings, not new calculations.
                        "dealerMarginGrossInclGst", "dealerMarginGst",
                        "consumerRetained", "exchangeRetained", "loyaltyRetained",
                        "referralRetained", "dsaRetained", "schemeRetainedBreakup",
                        "oemExtraSupportReceived", "oemExtraSupportPassed",
                        "leadSource", "claimStatus", "insuranceStatus",
                        "lastUpdated", "createdBy", "timestamp", "remarks",
                        # Newly sourced: attribution + lifecycle position.
                        "modifiedBy", "currentStage"], None),
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

# Operational columns that exist in the workbook but have NO source of truth anywhere
# in the CRM — no Mongo field, no computation, no frontend input. These are declared
# explicitly rather than left silently blank, so nobody has to re-derive the finding.
#
# They are NOT filled with invented values. Each stays blank until the stated source is
# built, and blank/null is preserved as meaningful ("not captured"), never coerced to 0
# or "". `preflight()` reports them so the gap stays visible.
SOURCE_REQUIRED = {
    ("Lead Register", "Next Follow-up Time"): {
        "field": "nextFollowupTime",
        "why": "Only the follow-up DATE is captured (LeadIn.nextFollowupDate). There is no "
               "time-of-day input anywhere in the frontend or API.",
        "needs": "Add a time field to the lead follow-up UI and LeadIn, then map it.",
    },
    ("Activity Log", "Reminder"): {
        "field": "reminder",
        "why": "ActivityIn captures nextFollowup but has no reminder flag/mechanism; the CRM "
               "sends no reminders, so there is nothing to record.",
        "needs": "A reminder feature (opt-in flag + delivery). Until then the column stays blank.",
    },
    ("Scheme Claim Register", "Claim Remarks"): {
        "field": "claimRemarks",
        "why": "No free-text remark is captured on a claim; ClaimReceiptIn carries only a "
               "reference. Mapped so a value flows once entered, but nothing writes it yet.",
        "needs": "A remarks input on the claim screen.",
    },
    ("Dealer Earnings Register", "Team Leader"): {
        "field": "teamLeader",
        "why": "The CRM models executives as a flat list of names; there is no reporting "
               "hierarchy, so a lead's team leader cannot be derived.",
        "needs": "An executive -> team-leader mapping in master data.",
    },
    ("Dealer Earnings Register", "Colour"): {
        "field": "colour",
        "why": "Vehicle colour is not part of Price Master, the lead, or the booking. It is "
               "not captured at any point in the lifecycle.",
        "needs": "A colour field on Price Master or the booking, chosen at booking time.",
    },
}

# Explicit, approved aliases: CRM field -> the ACTUAL header text in Euler Master (2).xlsx.
# Normalisation (lowercase, strip non-alphanumerics) already resolves the majority
# (e.g. "Customer Name"<->customerName, "BookingID"<->bookingId, "RTO"<->rto).
# Only genuinely different wording is listed. No fuzzy matching is used anywhere.
HEADER_ALIASES = {
    # Lead Register
    "altMobile": ["alternate mobile"],
    "dsaDiscount": ["dsa bonus", "dsa discount"],
    "insuranceBenefit": ["insurance benefit"],
    "rtoBenefit": ["rto benefit"],
    "rtoInsuranceBenefit": ["rto insurance benefit"],
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
    # Margin components — the register spells out the GST treatment in the header.
    "dealerMarginGrossInclGst": ["dealer margin gross (incl gst)", "dealer margin gross incl gst"],
    "dealerMarginGst": ["dealer margin gst (5%)", "dealer margin gst"],
    # OEM extra support: Received and Passed To Customer are DIFFERENT columns and must
    # not collapse onto each other (same class of bug as the S/T insurance columns).
    "oemExtraSupportReceived": ["oem extra support received"],
    "oemExtraSupportPassed": ["oem extra support passed to customer"],
    # Per-component scheme retention.
    "consumerRetained": ["consumer retained"],
    "exchangeRetained": ["exchange retained"],
    "loyaltyRetained": ["loyalty retained"],
    "referralRetained": ["referral retained"],
    "dsaRetained": ["dsa retained"],
    "schemeRetainedBreakup": ["scheme retained breakup"],
    # Claim Register
    "ageingDays": ["claim ageing (days)", "claim ageing days"],
    "dealerDiscount": ["dealer discount"],
    "oemDiscount": ["oem discount"],
    "claimRequired": ["claim required"],
    "schemeMonth": ["scheme month"],
    # Delivery Tracker
    "deliveryId": ["delivery id"],
    # Shared audit-ish columns present on several registers.
    "createdBy": ["created by"],
    "lastUpdated": ["last updated"],
    "lastPaymentDate": ["last payment date"],
    "policyDate": ["policy date"],
    "leadSource": ["lead source"],
    "claimStatus": ["claim status"],
    "insuranceStatus": ["insurance status"],
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


# ---------------------------------------------------------------- environment write-safety (Phase 1)
def env_safety():
    """Preview/Production isolation control. Preview must never WRITE to the
    production spreadsheet. Set ENVIRONMENT=preview and PRODUCTION_GSHEET_ID in the
    preview env; production sets ENVIRONMENT=production. Reads are always allowed."""
    env = os.environ.get("ENVIRONMENT", "").strip().lower()
    prod_id = os.environ.get("PRODUCTION_GSHEET_ID", "").strip()
    cur_id = os.environ.get("GSHEET_ID", "").strip()
    is_preview = env in ("preview", "dev", "development", "test", "staging")
    reason = None
    if is_preview and prod_id and cur_id and cur_id == prod_id:
        reason = "PREVIEW WRITE BLOCKED — PREVIEW IS POINTING TO PRODUCTION GOOGLE SHEET."
    elif env == "production" and prod_id and cur_id and cur_id != prod_id:
        reason = "PRODUCTION WRITE BLOCKED — PRODUCTION IS NOT POINTING TO THE PRODUCTION GOOGLE SHEET."
    return {"environment": env or "unset", "isPreview": is_preview,
            "spreadsheetId": cur_id, "productionSheetId": prod_id or None,
            "pointingAtProduction": bool(prod_id and cur_id and cur_id == prod_id),
            "writeBlocked": reason is not None, "blockReason": reason}


def _write_blocked():
    s = env_safety()
    return s["blockReason"] if s["writeBlocked"] else None


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


def classify_google_error(e):
    """Map a Google client exception to a precise, SAFE diagnosis.

    status() previously collapsed every failure into "cannot access sheet -- share it
    with the service account email", which is wrong for most causes and actively
    misleading when the sheet IS shared. In particular a revoked or replaced
    service-account key fails at the OAuth token exchange (invalid_grant / Invalid
    JWT Signature) before any Sheets call is made, and has nothing to do with sharing.

    Returns (code, reason). Never includes key material, tokens or credential JSON --
    only the HTTP status, Google's own reason category, and actionable guidance."""
    status_code = getattr(getattr(e, "resp", None), "status", None)
    try:
        status_code = int(status_code)
    except (TypeError, ValueError):
        status_code = None
    low = str(e).lower()

    if "invalid_grant" in low or "invalid jwt signature" in low:
        return ("credential_rejected",
                "Google rejected the service-account key (invalid_grant / Invalid JWT "
                "Signature). The key has been revoked, deleted or replaced in Google Cloud, "
                "or the JSON belongs to a different/disabled service account. This is NOT a "
                "sharing problem -- install a current key for this service account as the "
                "Render Secret File gsheets_credentials.json.")
    if "invalid_client" in low or "unauthorized_client" in low:
        return ("credential_invalid",
                "Google rejected the service-account client (invalid_client / "
                "unauthorized_client): the credential does not correspond to an active "
                "service account.")
    if status_code == 401:
        return ("unauthenticated",
                "Google returned 401 Unauthenticated -- the credential was not accepted. "
                "Check that the service-account key is current.")
    if status_code == 403:
        if "has not been used" in low or "is disabled" in low or "accessnotconfigured" in low:
            return ("api_disabled",
                    "Google returned 403: the required API is not enabled for this project. "
                    "Enable the Google Sheets API in Google Cloud.")
        if "quota" in low or "rate limit" in low:
            return ("quota_exceeded",
                    "Google returned 403 for quota/rate limits. Transient -- retry shortly.")
        return ("permission_denied",
                "Google returned 403 Permission Denied for this spreadsheet. Share it with "
                "the service account email as Editor.")
    if status_code == 404:
        return ("spreadsheet_not_found",
                "Google returned 404 -- no spreadsheet with the configured GSHEET_ID is "
                "visible to this service account. Check GSHEET_ID.")
    if status_code == 429:
        return ("quota_exceeded",
                "Google returned 429 -- read/write quota exceeded. Transient -- retry shortly.")
    if status_code and status_code >= 500:
        return ("google_unavailable",
                f"Google returned {status_code} -- transient Google-side error. Retry shortly.")
    return ("unknown_error",
            f"Unexpected error contacting Google Sheets ({type(e).__name__}); "
            f"status {status_code if status_code is not None else 'n/a'}.")


def status():
    global _status
    if _service is None:
        _init()
    if _service is None:
        return {**_status, "spreadsheetId": os.environ.get("GSHEET_ID", ""),
                **credential_diagnostics(), "health": _health}
    sheet_id = os.environ.get("GSHEET_ID", "")
    try:
        meta = _service.spreadsheets().get(spreadsheetId=sheet_id, fields="properties.title").execute()
        _status["canRead"] = True
        _status["spreadsheetTitle"] = (meta.get("properties") or {}).get("title", "")
        _status.pop("errorCode", None)
    except Exception as e:
        code, reason = classify_google_error(e)
        _status.update({"enabled": False, "canRead": False, "canWrite": False,
                        "errorCode": code, "reason": reason})
        return {**_status, "spreadsheetId": sheet_id, **credential_diagnostics(), "health": _health}
    try:
        _service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": []}).execute()
        _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
    except Exception as e:
        code = getattr(getattr(e, "resp", None), "status", None)
        msg = str(e)
        if str(code) == "400" or "at least one request" in msg:
            # 400 "Must specify at least one request" means the write PASSED permission
            # and only failed body validation => Editor access confirmed.
            _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
            _status.pop("errorCode", None)
        else:
            ecode, ereason = classify_google_error(e)
            _status.update({"enabled": False, "canWrite": False, "errorCode": ecode,
                            "reason": ("read-only — share the sheet with the service account email "
                                       "as EDITOR to enable syncing")
                            if ecode == "permission_denied" else ereason})
    # Phase-1 environment write-safety overrides Google permission — a preview pointing
    # at the production sheet must report canWrite=False regardless of Google access.
    _es = env_safety()
    if _es["writeBlocked"]:
        _status.update({"canWrite": False, "reason": _es["blockReason"], "errorCode": "env_write_blocked"})
    return {**_status, "spreadsheetId": sheet_id, "envSafety": _es,
            **credential_diagnostics(), "health": _health}


# ---------------------------------------------------------------- header mapping (GS-1)
def _header_row_for(entity, tab):
    """Which sheet row carries this tab's real header labels.
    Env override GSHEET_HEADERROW_<ENTITY> wins; then the per-entity hint; then
    auto-detect by picking the row (of the first 5) with the most text labels.
    Lead Register uses row 1 (normal register — header at top, data below)."""
    env = os.environ.get(f"GSHEET_HEADERROW_{entity.upper()}", "").strip()
    if env.isdigit():
        return int(env)
    if entity in _headerrow_cache:
        return _headerrow_cache[entity]
    hint = SYNC_MAP.get(entity, (None, None, None, None))[3] if entity in SYNC_MAP else None
    fields = SYNC_MAP[entity][2] if entity in SYNC_MAP else []
    if fields:
        # VERIFY the hint against the sheet rather than trusting it. A header that has
        # been shifted (see locate_header_row) would otherwise make the sync read data
        # rows as headers and mis-map every column.
        found = locate_header_row(tab, fields, hint or 1)
        _headerrow_cache[entity] = found
        return found
    if hint:
        return int(hint)
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


# How far down to hunt for a tab's real header row.
_HEADER_SCAN_ROWS = 40


def locate_header_row(tab, fields, hint=1):
    """Find the row that actually carries this tab's headers.

    The row number is NOT trusted as a constant. A Google Sheets `append` with
    insertDataOption=INSERT_ROWS inserts rows wherever its range anchors, which can
    push a header down the sheet (historically happened on Lead Register). With a
    hard-coded hint the sync then reads DATA as headers and every column mapping
    silently becomes garbage.

    So: score each of the first rows by how many expected field names it matches
    (via the same normalisation + alias table the mapping uses) and take the best.
    Falls back to the hint when nothing scores, so behaviour is unchanged on a
    well-formed tab."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!1:{_HEADER_SCAN_ROWS}").execute())
    rows = res.get("values", [])
    if not rows:
        return hint or 1
    wanted = set()
    for f in fields:
        wanted.add(_norm(f))
        for alias in HEADER_ALIASES.get(f, []):
            wanted.add(_norm(alias))
    best_row, best_score = None, 0
    for i, row in enumerate(rows, start=1):
        score = sum(1 for cell in row if _norm(cell) in wanted)
        if score > best_score:
            best_row, best_score = i, score
    # Require a real match, not one incidental cell, before overriding the hint.
    if best_row and best_score >= max(2, len(wanted) // 10):
        return best_row
    return hint or 1


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
    # Anchor the append on the register's header row / first mapped column so
    # Sheets detects the table correctly and INSERT_ROWS lands under the header
    # without shifting it.
    first_col = _col_letter(min(mapping.values()))
    resp = _with_retry(lambda: _service.spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!{first_col}{header_row}",
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
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "operation": "blocked", "error": blocked}
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
            "intentionallyUnmapped": INTENTIONALLY_UNMAPPED,
            "sourceRequired": [{"tab": t, "column": c, **v} for (t, c), v in SOURCE_REQUIRED.items()]}


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
    if _write_blocked():
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


# ---------------------------------------------------------------- derived report tabs
FINANCE_PENDING_TAB = _tab("GSHEET_TAB_FINANCE_PENDING", "Finance Pending")
FINANCE_OVERDUE_TAB = _tab("GSHEET_TAB_FINANCE_OVERDUE", "Finance Overdue")


def _overwrite_report_sync(tab, values):
    sheet_id = os.environ.get("GSHEET_ID", "")
    _service.spreadsheets().values().clear(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1:Z10000", body={},
    ).execute()
    _service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED", body={"values": values},
    ).execute()


async def overwrite_report_tab(tab, values):
    """Full-mirror rewrite of a DERIVED report tab (e.g. Finance Pending / Overdue).
    Safe because these tabs hold no source data — they are projections of the
    authoritative registers and must reflect current state, never accumulate rows.
    Returns True on success, False if sync is disabled or the write failed."""
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return False
    if _write_blocked():
        return False
    try:
        await asyncio.to_thread(_overwrite_report_sync, tab, values)
        _health.update({"lastWriteOk": True, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                        "lastError": None, "writes": _health["writes"] + 1})
        return True
    except Exception as e:
        _status["lastError"] = str(e)
        _health.update({"lastWriteOk": False, "lastWriteAt": datetime.now(timezone.utc).isoformat(),
                        "lastError": str(e)[:300], "failures": _health["failures"] + 1})
        return False


def _classify_tab(name):
    n = name.lower()
    if name in {SYNC_MAP[e][0] for e in SYNC_MAP}:
        return "operational (app-authoritative mirror)"
    if name in ("PRICE MASTER", "Scheme Master", "Incentive Master", "Masters", "Settings", "Quotation Schema", "Navigation Matrix", "RelationshipIndex"):
        return "master / config (sheet-authoritative)"
    if name in ("Finance Pending", "Finance Overdue", "Dashboard", "Dashboard Data") or n.startswith("mp —") \
       or n.startswith("today's") or n.startswith("monthly") or n.startswith("payments —") \
       or n.startswith("obs ") or n.startswith("pep ") or "analytics" in n or "report" in n \
       or "dashboard" in n or "scorecard" in n or name in ("Active Bookings", "Pending Deliveries",
       "Pending Follow-ups", "Outstanding Leads", "OEM Claim Dashboard", "Commercial Snapshot",
       "Commercial Audit", "Booking Status History", "Vehicle Allocation", "Executive Scorecard",
       "Dealer Daily Register", "Performance Log", "Transaction Log"):
        return "derived / report (projection — rebuildable)"
    if name in ("Activity Log",):
        return "operational (app-authoritative mirror)"
    if name in ("Migration Import Log", "Import Log", "Audit Log", "Backup Registry", "Crash Report"):
        return "audit / log"
    return "helper / other"


def inventory():
    """Read-only workbook contract. Enumerates all tabs + headers + classification,
    and the CRM column mapping for synced tabs. Never writes."""
    global _service
    if _service is None:
        _init()
    if _service is None:
        return {"ok": False, "reason": _status.get("reason", "not connected")}
    sheet_id = os.environ.get("GSHEET_ID", "")
    meta = _service.spreadsheets().get(spreadsheetId=sheet_id,
        fields="properties.title,sheets.properties(title,gridProperties)").execute()
    titles = [s["properties"]["title"] for s in meta.get("sheets", [])]
    # Batch-read first 5 rows of every tab to find headers efficiently.
    ranges = [f"'{t}'!1:5" for t in titles]
    batch = _service.spreadsheets().values().batchGet(spreadsheetId=sheet_id, ranges=ranges).execute()
    # batchGet preserves order, so zip with titles is reliable.
    tab_rows = [vr.get("values", []) for vr in batch.get("valueRanges", [])]
    tab_to_entity = {SYNC_MAP[e][0]: e for e in SYNC_MAP}
    tabs = []
    totals = {"tabs": len(titles), "columns": 0, "mappedColumns": 0, "unmappedTabs": 0}
    for title, rows in zip(titles, tab_rows):
        best, bn = 1, -1
        for i, r in enumerate(rows, start=1):
            c = sum(1 for x in r if isinstance(x, str) and x.strip())
            if c > bn:
                bn, best = c, i
        header = rows[best - 1] if len(rows) >= best else []
        header = [h for h in header]
        totals["columns"] += sum(1 for h in header if str(h).strip())
        entity = tab_to_entity.get(title)
        entry = {
            "tab": title, "classification": _classify_tab(title), "headerRow": best,
            "columnCount": sum(1 for h in header if str(h).strip()),
            "headers": [{"col": _col_letter(i), "header": h} for i, h in enumerate(header) if str(h).strip()],
        }
        if entity:
            spec = SYNC_MAP[entity]
            id_field, fields = spec[1], spec[2]
            try:
                mapping, missing = _resolve_columns(title, fields, use_cache=False, header_row=best)
                entry["crmEntity"] = entity
                entry["idField"] = id_field
                entry["syncDirection"] = "APP → SHEET (upsert by stable ID)"
                entry["resolvedColumns"] = {f: _col_letter(i) for f, i in sorted(mapping.items(), key=lambda kv: kv[1])}
                entry["missingHeaders"] = missing
                entry["idColumnResolved"] = id_field in mapping
                totals["mappedColumns"] += len(mapping)
            except Exception as e:
                entry["mappingError"] = str(e)[:200]
        else:
            totals["unmappedTabs"] += 1
        tabs.append(entry)
    return {"ok": True, "spreadsheetId": sheet_id,
            "spreadsheetTitle": (meta.get("properties") or {}).get("title", ""),
            "totals": totals, "envSafety": env_safety(), "tabs": tabs}


async def backfill(datasets):
    """Bulk reconcile: upserts every supplied record. Idempotent by construction —
    existing IDs are updated in place, only genuinely new IDs append."""
    global _service
    if _service is None:
        _init()
    st = status()
    if not st.get("enabled") or not st.get("canWrite"):
        return {"ok": False, "reason": st.get("reason", "sync not enabled"), "canWrite": st.get("canWrite", False)}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "canWrite": False, "writeBlocked": True}
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
    return set(_read_id_column_list(tab, id_col_idx, header_row))


def _read_id_column_list(tab, id_col_idx, header_row=1):
    """List (with duplicates) of non-empty ID-column values below the header row."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(id_col_idx)
    res = _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute()
    out = []
    for i, row in enumerate(res.get("values", []), start=1):
        if i <= header_row:
            continue  # header/helper area
        if row and str(row[0]).strip():
            out.append(str(row[0]).strip())
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
