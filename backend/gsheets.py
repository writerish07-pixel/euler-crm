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
               # OEM Extra Support trio (Received / Passed / Retained) — same meaning as
               # Dealer Earnings + OEM Extra Support Register. Headers must exist on the tab.
               "oemExtraSupportReceived", "oemExtraSupportPassed", "oemExtraSupportRetained",
               "totalDiscount", "oemSchemeAmount", "dealerSchemeAmount", "customerOutstanding",
               # Insurer Name is the insurance COMPANY (ICICI etc.); Insurance Agent is
               # the broker the payout is claimed from. Two different things, two columns.
               "companyOutstanding", "insurerName", "insuranceAgentName",
               "invoiceNumber", "chassisNumber", "numberPlate",
               # Dealer Earnings LAST among commercial totals — includes OEM Extra Retained.
               "dealerTotalEarnings",
               # Closure + delivery-checklist columns. All of these were already
               # persisted on the lead by close_lead / mark_delivery; they simply had
               # no Sheet mapping, so the register showed blanks for closed leads.
               "closedDate", "closeReason", "finalOutstanding",
               "insuranceStatus", "registrationStatus", "invoiceStatus", "rcStatus", "pdiStatus",
               # Newly sourced: attribution and activity summary (see SOURCE_REQUIRED
               # below for the Lead Register columns that still have no source).
               "lastActivity", "lastUpdatedBy", "closedBy", "closeTimestamp",
               # Cancellation stamp. Kept separate from the Close columns above
               # because Close = won and Cancel = lost, and a lead can be
               # cancelled several times before it is ever closed.
               "cancelCount", "lastCancelDate", "lastCancelReason", "lastCancelStage",
               "reviveOn",
               # Price / TCS / exchange fields the app now persists on every lead.
               # Headers are pending on Euler Master until Settings ensure / Backfill
               # appends them — sync skips a field until its header exists.
               "rsaAmc", "tcs", "tcsBase", "tcsApplicable",
               "insuranceArrangedBy", "finalExchangeValue", "schemeAsOf",
               "dealCancelled"], 1),
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
                "source", "dsaApproval", "claimReceivedDate", "claimRemarks",
                # Euler filing, copied from OEM Claim Settlements — not money.
                "chassisNumber", "invoiceNumber", "oemMatchState", "oemStatus",
                "oemStageLabel"], None),
    "insurance": (_tab("GSHEET_TAB_INSURANCE", "Insurance Register"), "entryId",
                  ["entryId", "leadId", "customerName", "mobile", "model", "variant",
                   "insuranceCompany", "policyNumber", "insuranceAmount", "payoutRatePct",
                   "expectedPayout", "receivedPayout", "payoutOutstanding", "status",
                   "policyDate", "deliveryDate", "lastUpdated", "remarks",
                   # Already captured by InsuranceIn and stored via model_dump().
                   "insuranceExecutive",
                   # Insurance agent (broker) the payout is claimed from, and how the
                   # rate was decided (agent slab / manual override / legacy default).
                   "insuranceAgentName", "payoutRateSource", "lastPayoutDate"], None),
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
                         "campaignIncentive", "otherIncome",
                         "dealerMarginNetExGst", "dealerMarginGrossInclGst", "dealerMarginGst",
                         "consumerRetained", "exchangeRetained", "loyaltyRetained",
                         "referralRetained", "dsaRetained", "schemeRetainedBreakup",
                         # OEM Extra trio, then TOTAL (final calc includes Retained).
                         "oemExtraSupportReceived", "oemExtraSupportPassed", "oemExtraSupportRetained",
                         "oemUnpayableWriteOff",
                         "dealerTotalEarnings",
                         "leadSource", "claimStatus", "insuranceStatus",
                         "lastUpdated", "createdBy", "timestamp", "remarks",
                         "modifiedBy", "currentStage"], None),
    # Incentive Register — created on Mark Delivered; Mark Paid also upserts an OEM claim.
    "incentive_register": (_tab("GSHEET_TAB_INCENTIVE_REGISTER", "Incentive Register"), "incentiveId",
                           ["incentiveId", "schemeMonth", "executive", "leadId", "bookingId",
                            "model", "variant", "productCategory", "deliveryDate", "incentiveAmount",
                            "status", "paidDate", "remarks", "lastUpdated"], 1),
    # OEM Extra Support Register — one row per lead when Received > 0.
    # Received = full OEM claim; Passed = customer portion; Retained = Received − Passed.
    "oem_extra_support": (_tab("GSHEET_TAB_OEM_EXTRA_SUPPORT", "OEM Extra Support Register"), "leadId",
                          ["leadId", "bookingId", "customerName", "model", "variant", "bookingDate",
                           "oemExtraSupportReceived", "oemExtraSupportPassed", "oemExtraSupportRetained",
                           "chassisNumber", "invoiceNumber", "claimReference",
                           "status", "lastUpdated", "remarks"], 1),
    "dropped_oem_extra_support": (
        _tab("GSHEET_TAB_DROPPED_EXTRA_SUPPORT", "Dropped Extra Support Register"), "dropId",
        ["dropId", "leadId", "claimId", "customerName", "model", "variant", "bookingDate",
         "droppedAmount", "chassisNumber", "invoiceNumber", "claimReference",
         "reason", "droppedAt", "droppedBy", "executive"], 1),
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
    "cancelCount": ["cancel count", "cancelled count", "times cancelled"],
    "lastCancelDate": ["last cancel date", "cancel date", "cancelled on"],
    "lastCancelReason": ["last cancel reason", "cancel reason", "cancellation reason"],
    "lastCancelStage": ["last cancel stage", "cancel stage", "cancelled at stage"],
    "reviveOn": ["revive on", "follow-up restarts", "revive date"],
    "rsaAmc": ["rsa / amc", "rsa amc", "rsa/amc"],
    "tcs": ["tcs"],
    "tcsBase": ["tcs base", "tcs base (after discount)", "tcs after discount"],
    "tcsApplicable": ["tcs applicable"],
    "insuranceArrangedBy": ["insurance arranged by", "insurance arranged"],
    "finalExchangeValue": ["final exchange value", "exchange value"],
    "schemeAsOf": ["scheme as of", "scheme date", "scheme as-of"],
    "dealCancelled": ["deal cancelled", "cancelled deal"],
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
    "insuranceAgentName": ["insurance agent", "agent", "agent name"],
    "payoutRateSource": ["rate source", "payout rate source"],
    "lastPayoutDate": ["last payout date", "last receipt date"],
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
    "rsaIncome": ["rsa income"],
    # Margin components — the register spells out the GST treatment in the header.
    "dealerMarginGrossInclGst": ["dealer margin gross (incl gst)", "dealer margin gross incl gst"],
    "dealerMarginGst": ["dealer margin gst (5%)", "dealer margin gst"],
    # OEM extra support: Received / Passed / Retained are DIFFERENT columns and must
    # not collapse onto each other (same class of bug as the S/T insurance columns).
    "oemExtraSupportReceived": ["oem extra support received"],
    "oemExtraSupportPassed": ["oem extra support passed to customer"],
    "oemExtraSupportRetained": ["oem extra support retained"],
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
    "chassisNumber": ["chassis number", "chassis"],
    "invoiceNumber": ["invoice number", "invoice"],
    "oemMatchState": ["in euler", "oem match", "in coulson"],
    "oemStatus": ["euler status", "oem status"],
    "oemStageLabel": ["euler stage", "oem stage"],
}

MASTERS_TAB = _tab("GSHEET_TAB_MASTERS", "Masters")
MASTERS_HEADER = ["Category", "Value", "Status"]

_service = None
_status = {"enabled": False, "reason": "not configured", "email": None}
_health = {
    "lastWriteOk": None, "lastWriteAt": None, "lastError": None,
    "lastErrorClass": None, "hardFailure": False, "writes": 0, "failures": 0,
}


def classify_write_error(msg: str) -> str:
    """How the top-bar badge should treat a failed sheet write.

    Connection is fine (Settings shows Live) even when an optional tab or a
    pending header is missing. Those used to flip lastWriteOk=false and the
    whole app screamed Sync Error.
    """
    e = (msg or "").lower()
    if not e:
        return "write"
    if any(x in e for x in ("429", "quota", "rate limit")):
        return "quota"
    if any(x in e for x in ("401", "unauth", "invalid_grant", "credential")):
        return "permission"
    if "403" in e or "permission" in e:
        return "permission"
    if any(x in e for x in ("500", "502", "503", "unavailable", "timeout",
                            "timed out", "deadline")):
        return "google"
    if any(x in e for x in (
        "unable to parse range", "unable to parse", "no matching headers",
        "required id header", "stable id", "tab not found", "no such tab",
        "does not exist", "unable to find", "header",
    )):
        return "sheet_shape"
    return "write"


def _mark_health(ok: bool, error: str = ""):
    """Record a write outcome. Shape misses do not turn the badge red."""
    now = datetime.now(timezone.utc).isoformat()
    if ok:
        _health.update({
            "lastWriteOk": True, "lastWriteAt": now, "lastError": None,
            "lastErrorClass": None, "hardFailure": False,
            "writes": _health["writes"] + 1,
        })
        return
    klass = classify_write_error(error)
    hard = klass in ("quota", "permission", "google", "write")
    _health["failures"] = int(_health.get("failures") or 0) + 1
    _health["lastWriteAt"] = now
    _health["lastError"] = (error or "")[:300]
    _health["lastErrorClass"] = klass
    if hard:
        _health["lastWriteOk"] = False
        _health["hardFailure"] = True
    else:
        _health["hardFailure"] = False
        _health["lastWriteOk"] = True
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


def _sheet_value(v):
    """Coerce a CRM value into something the sheet can display.

    Bools become Yes/No so Deal Cancelled matches TCS Applicable / Finance Required.
    None stays blank rather than the literal string 'None'.
    """
    if v is None:
        return ""
    if isinstance(v, bool):
        return "Yes" if v else "No"
    return v


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
# nothing else. Railway / other hosts often inject the key as GSHEET_CREDENTIALS_JSON
# (raw JSON string) instead of a file — that is materialised under /tmp when present.
# The credential is never committed; these are runtime locations only.
_SECRET_FILE_NAME = "gsheets_credentials.json"
_JSON_ENV_TMP = Path("/tmp") / _SECRET_FILE_NAME


def _materialize_credentials_json_env():
    """If GSHEET_CREDENTIALS_JSON is set, write it to /tmp and return that path."""
    raw = os.environ.get("GSHEET_CREDENTIALS_JSON", "").strip()
    if not raw:
        return ""
    try:
        import json as _json
        info = _json.loads(raw)
        if not isinstance(info, dict) or info.get("type") != "service_account":
            return ""
        _JSON_ENV_TMP.write_text(_json.dumps(info), encoding="utf-8")
        try:
            os.chmod(_JSON_ENV_TMP, 0o600)
        except OSError:
            pass
        return str(_JSON_ENV_TMP)
    except Exception:
        return ""


_CRED_CANDIDATES = [
    ("env:GSHEET_CREDENTIALS_JSON", _materialize_credentials_json_env),
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
    preview env; production sets ENVIRONMENT=production. Reads are always allowed.

    Pytest / Cloud Agent test runs must never write to a live spreadsheet — that is
    how Lead Register got refilled with ITER24 / Step Lock / Fresh Start One rows
    after go-live resets (tests used mongomock for Mongo but real GSHEET_ID + creds).
    """
    env = os.environ.get("ENVIRONMENT", "").strip().lower()
    prod_id = os.environ.get("PRODUCTION_GSHEET_ID", "").strip()
    cur_id = os.environ.get("GSHEET_ID", "").strip()
    is_preview = env in ("preview", "dev", "development", "test", "staging")
    reason = None
    # Hard stop: any pytest process, unless an explicit opt-in for a dedicated test sheet.
    if os.environ.get("PYTEST_CURRENT_TEST") and not os.environ.get("GSHEET_ALLOW_TEST_WRITES", "").strip():
        reason = ("TEST WRITE BLOCKED — pytest must not write to Google Sheets "
                  "(set GSHEET_ALLOW_TEST_WRITES=1 only for a disposable test spreadsheet).")
    elif is_preview and prod_id and cur_id and cur_id == prod_id:
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
                   "reason": f"credentials JSON not found — looked at: {tried}. "
                             f"On Railway set GSHEET_CREDENTIALS_JSON to the full service-account "
                             f"JSON (and remove a bad GSHEET_CREDENTIALS_PATH). On Render add a "
                             f"Secret File named {_SECRET_FILE_NAME} or set GSHEET_CREDENTIALS_PATH "
                             f"to a real file path."}
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


# ---------------------------------------------------------------- OEM Extra Support column ensure
OEM_EXTRA_CANONICAL_HEADERS = (
    "OEM Extra Support Received",
    "OEM Extra Support Passed To Customer",
    "OEM Extra Support Retained",
)

OEM_EXTRA_REGISTER_COLS = (
    "Lead ID", "Booking ID", "Customer Name", "Vehicle Model", "Variant", "Booking Date",
    *OEM_EXTRA_CANONICAL_HEADERS,
    "Chassis Number", "Invoice Number", "Claim Reference Number",
    "Status", "Last Updated", "Remarks",
)

DROPPED_EXTRA_REGISTER_COLS = (
    "Drop ID", "Lead ID", "Claim ID", "Customer Name", "Vehicle Model", "Variant", "Booking Date",
    "Dropped Amount", "Chassis Number", "Invoice Number", "Claim Reference Number",
    "Reason", "Dropped At", "Dropped By", "Executive",
)


def _sheet_titles():
    sheet_id = os.environ.get("GSHEET_ID", "")
    meta = _with_retry(lambda: _service.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets(properties(title))").execute())
    return {sh["properties"]["title"] for sh in meta.get("sheets", [])}


def _create_sheet_tab(title):
    sheet_id = os.environ.get("GSHEET_ID", "")
    _with_retry(lambda: _service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{"addSheet": {"properties": {"title": title}}}]},
    ).execute())


def _append_missing_headers(tab, required_headers, header_row=1):
    """Append any missing header labels to the end of the header row. Never renames."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    existing = _read_header_row(tab, header_row)
    by_norm = {_norm(h): h for h in existing if str(h or "").strip()}
    to_add = []
    for h in required_headers:
        if _norm(h) not in by_norm:
            to_add.append(h)
    if not to_add:
        return {"tab": tab, "added": [], "alreadyPresent": list(required_headers)}
    start_col = len(existing)  # 0-based index of first empty header cell
    # Prefer trailing blanks in the header row if present.
    while start_col > 0 and not str(existing[start_col - 1] or "").strip():
        start_col -= 1
    letter = _col_letter(start_col)
    end_letter = _col_letter(start_col + len(to_add) - 1)
    rng = f"'{tab}'!{letter}{header_row}:{end_letter}{header_row}"
    _with_retry(lambda: _service.spreadsheets().values().update(
        spreadsheetId=sheet_id, range=rng, valueInputOption="RAW",
        body={"values": [to_add]},
    ).execute())
    invalidate_header_cache(tab)
    return {"tab": tab, "added": to_add, "headerRow": header_row,
            "startColumn": letter}


def _header_index(headers, *names):
    """0-based index of the first matching header name, else None."""
    by_norm = {_norm(h): i for i, h in enumerate(headers) if str(h or "").strip()}
    for name in names:
        if _norm(name) in by_norm:
            return by_norm[_norm(name)]
    return None


def _ensure_oem_extra_before_total_earnings(tab, total_header_names, header_row=1):
    """Ensure OEM Extra trio sits immediately BEFORE the total Dealer Earnings column.

    Final layout: … | OEM Extra Received | Passed | Retained | Dealer Earnings (total) |
    So the earnings column is last and holds the final calculation (includes Retained).
    """
    gid = _gid_for_tab(tab)
    if gid is None:
        return {"tab": tab, "ok": False, "error": "tab not found"}
    sheet_id = os.environ.get("GSHEET_ID", "")
    headers = _read_header_row(tab, header_row)
    total_idx = _header_index(headers, *total_header_names)
    missing = [h for h in OEM_EXTRA_CANONICAL_HEADERS if _header_index(headers, h) is None]
    changed = False
    added = []
    moved_total = False

    if missing:
        # Insert blank columns just before Dealer Earnings (or at end if total missing).
        insert_at = total_idx if total_idx is not None else len([h for h in headers if str(h or "").strip()])
        _with_retry(lambda: _service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "insertDimension": {
                    "range": {
                        "sheetId": gid,
                        "dimension": "COLUMNS",
                        "startIndex": insert_at,
                        "endIndex": insert_at + len(missing),
                    },
                    "inheritFromBefore": insert_at > 0,
                }
            }]},
        ).execute())
        letter = _col_letter(insert_at)
        end_letter = _col_letter(insert_at + len(missing) - 1)
        rng = f"'{tab}'!{letter}{header_row}:{end_letter}{header_row}"
        _with_retry(lambda: _service.spreadsheets().values().update(
            spreadsheetId=sheet_id, range=rng, valueInputOption="RAW",
            body={"values": [missing]},
        ).execute())
        added = list(missing)
        changed = True
        invalidate_header_cache(tab)
        headers = _read_header_row(tab, header_row)
        total_idx = _header_index(headers, *total_header_names)

    # If Dealer Earnings is still LEFT of OEM Extra, move it to after Retained.
    oem_idxs = [_header_index(headers, h) for h in OEM_EXTRA_CANONICAL_HEADERS]
    oem_idxs = [i for i in oem_idxs if i is not None]
    total_idx = _header_index(headers, *total_header_names)
    if total_idx is not None and oem_idxs and total_idx < min(oem_idxs):
        dest = max(oem_idxs) + 1  # after last OEM Extra column (pre-removal coords)
        _with_retry(lambda: _service.spreadsheets().batchUpdate(
            spreadsheetId=sheet_id,
            body={"requests": [{
                "moveDimension": {
                    "source": {
                        "sheetId": gid,
                        "dimension": "COLUMNS",
                        "startIndex": total_idx,
                        "endIndex": total_idx + 1,
                    },
                    "destinationIndex": dest,
                }
            }]},
        ).execute())
        moved_total = True
        changed = True
        invalidate_header_cache(tab)

    return {"tab": tab, "changed": changed, "added": added, "movedTotalAfterOemExtra": moved_total,
            "totalHeader": total_header_names[0]}


def _ensure_oem_extra_support_columns_sync():
    """Create/place OEM Extra Support headers so Dealer Earnings is the final total column.

    Lead Register + Dealer Earnings Register: Received / Passed / Retained, then total.
    OEM Extra Support Register: create tab if missing.
    """
    titles = _sheet_titles()
    results = []
    lead_tab = SYNC_MAP["leads"][0]
    earn_tab = SYNC_MAP["dealer_earnings"][0]
    oem_tab = SYNC_MAP["oem_extra_support"][0]

    if lead_tab in titles:
        results.append(_ensure_oem_extra_before_total_earnings(
            lead_tab, ["Dealer Earnings", "TOTAL DEALER EARNINGS"], 1))
    else:
        results.append({"tab": lead_tab, "ok": False, "error": "tab not found"})

    if earn_tab in titles:
        results.append(_ensure_oem_extra_before_total_earnings(
            earn_tab, ["TOTAL DEALER EARNINGS", "Dealer Earnings"], 1))
    else:
        results.append({"tab": earn_tab, "ok": False, "error": "tab not found"})

    if oem_tab not in titles:
        _create_sheet_tab(oem_tab)
        sheet_id = os.environ.get("GSHEET_ID", "")
        _with_retry(lambda: _service.spreadsheets().values().update(
            spreadsheetId=sheet_id, range=f"'{oem_tab}'!A1",
            valueInputOption="RAW", body={"values": [list(OEM_EXTRA_REGISTER_COLS)]},
        ).execute())
        invalidate_header_cache(oem_tab)
        results.append({"tab": oem_tab, "created": True, "changed": True,
                        "added": list(OEM_EXTRA_REGISTER_COLS)})
    else:
        results.append(_append_missing_headers(oem_tab, OEM_EXTRA_REGISTER_COLS, 1))

    added_any = any(r.get("added") or r.get("created") or r.get("changed")
                    or r.get("movedTotalAfterOemExtra") for r in results)
    return {"ok": True, "changed": added_any, "tabs": results}


# Headers the Insurance Register needs before the insurance-agent fields can write.
# The labels must match HEADER_ALIASES for insuranceAgentName / payoutRateSource /
# lastPayoutDate, or the sync will still not find them.
INSURANCE_AGENT_HEADERS = ["Insurance Agent", "Rate Source", "Last Payout Date"]
# Lead Register carries only the agent name, alongside the existing Insurer Name.
LEAD_INSURANCE_AGENT_HEADERS = ["Insurance Agent"]


# Lead Register columns the cancellation stamp needs. Labels must match the
# HEADER_ALIASES above or the sync resolves nothing and the columns stay blank.
LEAD_CANCEL_HEADERS = ["Cancel Count", "Last Cancel Date", "Last Cancel Reason",
                       "Last Cancel Stage", "Revive On"]

# Lead Register columns for price / TCS / exchange fields the app now stores.
# Labels must match HEADER_ALIASES (or camelCase normalisation) or the sync
# resolves nothing and the columns stay blank. Append-only — never rename.
LEAD_COMMERCIAL_HEADERS = [
    "RSA / AMC", "TCS", "TCS Applicable", "TCS Base",
    "Insurance Arranged By", "Final Exchange Value", "Scheme As Of",
    "Deal Cancelled",
]

# Scheme Claim Register columns so Euler filing (chassis / In Euler / status)
# actually has a header to land in. Append-only. Claim Reference Number already
# exists on the tab and is filled with the Coulson debit-note number.
CLAIM_OEM_HEADERS = [
    "Chassis Number", "Invoice Number", "In Euler", "Euler Status", "Euler Stage",
]


def _ensure_cancel_columns_sync():
    titles = _sheet_titles()
    tab = SYNC_MAP["leads"][0]
    if tab not in titles:
        return {"ok": False, "changed": False,
                "tabs": [{"tab": tab, "ok": False, "error": "tab not found", "added": []}]}
    detail = _append_missing_headers(tab, LEAD_CANCEL_HEADERS, _header_row_for("leads", tab))
    return {"ok": True, "changed": bool(detail.get("added")), "tabs": [detail]}


async def ensure_cancel_columns():
    """Owner helper: append the cancellation headers to Lead Register.

    Append-only and idempotent — never renames or reorders an existing column,
    and re-running it adds nothing the second time. Until these headers exist the
    cancel fields simply do not write, because the sync resolves columns by name.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "tabs": []}
    try:
        detail = await asyncio.to_thread(_ensure_cancel_columns_sync)
        _mark_health(True)
        return detail
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300], "tabs": []}


def _ensure_insurance_agent_columns_sync():
    titles = _sheet_titles()
    tabs = []
    for entity, headers in (("insurance", INSURANCE_AGENT_HEADERS),
                            ("leads", LEAD_INSURANCE_AGENT_HEADERS)):
        tab = SYNC_MAP[entity][0]
        if tab not in titles:
            tabs.append({"tab": tab, "ok": False, "error": "tab not found", "added": []})
            continue
        tabs.append(_append_missing_headers(tab, headers, _header_row_for(entity, tab)))
    return {"ok": True, "changed": any(t.get("added") for t in tabs), "tabs": tabs}


async def ensure_insurance_agent_columns():
    """Owner helper: append the insurance-agent headers to the live workbook.

    Insurance Register: Insurance Agent / Rate Source / Last Payout Date.
    Lead Register:      Insurance Agent (next to the existing Insurer Name, which
                        keeps holding the insurance COMPANY).

    Append-only — never renames or reorders an existing column, and re-running it
    is a no-op once the headers are present.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "tabs": []}
    try:
        detail = await asyncio.to_thread(_ensure_insurance_agent_columns_sync)
        _mark_health(True)
        return detail
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300], "tabs": []}


def _ensure_lead_commercial_columns_sync():
    titles = _sheet_titles()
    tab = SYNC_MAP["leads"][0]
    if tab not in titles:
        return {"ok": False, "changed": False,
                "tabs": [{"tab": tab, "ok": False, "error": "tab not found", "added": []}]}
    detail = _append_missing_headers(tab, LEAD_COMMERCIAL_HEADERS, _header_row_for("leads", tab))
    return {"ok": True, "changed": bool(detail.get("added")), "tabs": [detail]}


async def ensure_lead_commercial_columns():
    """Owner helper: append TCS / RSA / exchange / deal-cancelled headers.

    Append-only and idempotent. Until these headers exist the new commercial
    fields simply do not write, because the sync resolves columns by name.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "tabs": []}
    try:
        detail = await asyncio.to_thread(_ensure_lead_commercial_columns_sync)
        _mark_health(True)
        return detail
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300], "tabs": []}


def _ensure_scheme_claim_oem_columns_sync():
    titles = _sheet_titles()
    tab = SYNC_MAP["claims"][0]
    if tab not in titles:
        return {"ok": False, "changed": False,
                "tabs": [{"tab": tab, "ok": False, "error": "tab not found", "added": []}]}
    detail = _append_missing_headers(tab, CLAIM_OEM_HEADERS, _header_row_for("claims", tab))
    return {"ok": True, "changed": bool(detail.get("added")), "tabs": [detail]}


async def ensure_scheme_claim_oem_columns():
    """Append chassis / In Euler / Euler status headers on Scheme Claim Register.

    Append-only. Until these exist, OEM filing fields do not write to the sheet.
    Claim Reference Number is already on the tab and holds the Coulson claim no.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "tabs": []}
    try:
        detail = await asyncio.to_thread(_ensure_scheme_claim_oem_columns_sync)
        _mark_health(True)
        return detail
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300], "tabs": []}


async def ensure_pending_columns():
    """Append every waiting header the live workbook still lacks.

    Backfill runs this first so one click both creates the columns the app now
    writes (OEM Extra, Insurance Agent, Cancellation, TCS/RSA/exchange, Scheme Claim
    Euler filing) and then fills rows. Each step is append-only and safe to re-run.
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "steps": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "steps": []}
    steps = []
    for name, fn in (
        ("oemExtra", ensure_oem_extra_support_columns),
        ("insuranceAgent", ensure_insurance_agent_columns),
        ("cancellation", ensure_cancel_columns),
        ("leadCommercial", ensure_lead_commercial_columns),
        ("schemeClaimOem", ensure_scheme_claim_oem_columns),
    ):
        try:
            detail = await fn()
        except Exception as e:
            detail = {"ok": False, "reason": str(e)[:300], "tabs": []}
        entry = {"step": name}
        if isinstance(detail, dict):
            entry.update(detail)
        else:
            entry["result"] = detail
        steps.append(entry)
    changed = any(s.get("changed") for s in steps)
    hard_fail = any(s.get("ok") is False for s in steps)
    return {"ok": not hard_fail, "changed": changed, "steps": steps}


async def ensure_oem_extra_support_columns():
    """Owner helper: make OEM Extra Support columns visible on the live workbook."""
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled"), "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True, "tabs": []}
    try:
        detail = await asyncio.to_thread(_ensure_oem_extra_support_columns_sync)
        _mark_health(True)
        return detail
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300], "tabs": []}


def _ensure_dropped_extra_support_tab_sync():
    titles = _sheet_titles()
    tab = SYNC_MAP["dropped_oem_extra_support"][0]
    if tab not in titles:
        _create_sheet_tab(tab)
        sheet_id = os.environ.get("GSHEET_ID", "")
        _with_retry(lambda: _service.spreadsheets().values().update(
            spreadsheetId=sheet_id, range=f"'{tab}'!A1",
            valueInputOption="RAW", body={"values": [list(DROPPED_EXTRA_REGISTER_COLS)]},
        ).execute())
        invalidate_header_cache(tab)
        return {"ok": True, "tab": tab, "created": True, "changed": True,
                "added": list(DROPPED_EXTRA_REGISTER_COLS)}
    return _append_missing_headers(tab, DROPPED_EXTRA_REGISTER_COLS, 1)


async def ensure_dropped_extra_support_tab():
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled")}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True}
    try:
        return await asyncio.to_thread(_ensure_dropped_extra_support_tab_sync)
    except Exception as e:
        return {"ok": False, "reason": str(e)[:300]}


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


def _prime_formula_cache(tab, header_row, mapping):
    """One FORMULA read for the mapped columns so a backfill does not GET every row."""
    idxs = sorted(mapping.values())
    if not idxs:
        return
    sheet_id = os.environ.get("GSHEET_ID", "")
    rng = f"'{tab}'!{_col_letter(idxs[0])}{header_row + 1}:{_col_letter(idxs[-1])}"
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=rng, valueRenderOption="FORMULA").execute())
    base = idxs[0]
    for i, row in enumerate(res.get("values") or [], start=header_row + 1):
        protected = set()
        for col_idx in idxs:
            off = col_idx - base
            if off < len(row) and isinstance(row[off], str) and row[off].startswith("="):
                protected.add(col_idx)
        _formula_cache[(tab, i)] = protected


_BACKFILL_UPDATE_CHUNK = 80


def _backfill_entity_sync(entity, docs):
    """Reconcile one entity in a few Sheets calls instead of two per row.

    Live per-lead sync stays one-row-at-a-time (formula protection + ID cache).
    Backfill of hundreds of rows that way hits Google write quota and the
    HTTP proxy times out — which is what Settings showed as 'Backfill failed'.
    """
    tab, id_field, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][1], SYNC_MAP[entity][2]
    sheet_id = os.environ.get("GSHEET_ID", "")
    header_row = _header_row_for(entity, tab)
    mapping, missing = _resolve_columns(tab, fields, header_row=header_row)
    if id_field in missing:
        invalidate_header_cache(tab)
        return {"appended": 0, "updated": 0, "failed": len(docs),
                "errors": [f"required ID header for '{id_field}' not found in tab '{tab}'"],
                "missingHeaders": missing}
    if not mapping:
        invalidate_header_cache(tab)
        return {"appended": 0, "updated": 0, "failed": len(docs),
                "errors": [f"no matching headers found in tab '{tab}'"],
                "missingHeaders": missing}

    by_id = {}
    no_id = 0
    for d in docs or []:
        ident = str(d.get(id_field, "") or "").strip()
        if not ident:
            no_id += 1
            continue
        by_id[ident] = d

    try:
        _prime_formula_cache(tab, header_row, mapping)
    except Exception:
        pass

    id_map = _load_id_rows(tab, mapping[id_field], header_row + 1)
    updates_data = []
    append_rows = []
    n_updated = n_appended = 0
    for ident, doc in by_id.items():
        row_num = id_map.get(ident)
        if row_num:
            n_updated += 1
            protected = _formula_cache.get((tab, row_num), set())
            for f, col_idx in mapping.items():
                if col_idx in protected or f not in doc:
                    continue
                updates_data.append({
                    "range": f"'{tab}'!{_col_letter(col_idx)}{row_num}",
                    "values": [[_sheet_value(doc.get(f, ""))]],
                })
        else:
            n_appended += 1
            width = max(mapping.values()) + 1
            row = [""] * width
            for f, col_idx in mapping.items():
                row[col_idx] = _sheet_value(doc.get(f, ""))
            append_rows.append(row)

    failed = no_id
    errors = []
    if no_id:
        errors.append(f"{no_id} record(s) missing stable ID '{id_field}'")

    for i in range(0, len(updates_data), _BACKFILL_UPDATE_CHUNK):
        chunk = updates_data[i:i + _BACKFILL_UPDATE_CHUNK]
        try:
            _with_retry(lambda c=chunk: _service.spreadsheets().values().batchUpdate(
                spreadsheetId=sheet_id,
                body={"valueInputOption": "USER_ENTERED", "data": c}).execute())
        except Exception as e:
            failed += len(chunk)
            if len(errors) < 3:
                errors.append(str(e)[:300])

    if append_rows:
        first_col = _col_letter(min(mapping.values()))
        try:
            _with_retry(lambda: _service.spreadsheets().values().append(
                spreadsheetId=sheet_id, range=f"'{tab}'!{first_col}{header_row}",
                valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
                body={"values": append_rows}).execute())
        except Exception as e:
            failed += len(append_rows)
            n_appended = 0
            if len(errors) < 3:
                errors.append(str(e)[:300])
        _idrow_cache.pop((tab, header_row + 1), None)

    out = {"appended": n_appended, "updated": n_updated, "failed": failed,
           "missingHeaders": missing}
    if errors:
        out["errors"] = errors
    return out


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
                         "values": [[_sheet_value(doc.get(f, ""))]]})
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
        row[col_idx] = _sheet_value(doc.get(f, ""))
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
            _mark_health(True)
        else:
            _mark_health(False, str(res.get("error") or ""))
        return res
    except Exception as e:
        invalidate_header_cache()
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "operation": "error", "tab": SYNC_MAP[entity][0], "error": str(e)[:500]}


# ---------------------------------------------------------------- delete by lead (owner cascade)
def _gid_for_tab(tab):
    """Numeric sheetId (gid) for deleteDimension requests."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    meta = _with_retry(lambda: _service.spreadsheets().get(
        spreadsheetId=sheet_id, fields="sheets(properties(sheetId,title))").execute())
    for sh in meta.get("sheets", []):
        props = sh.get("properties") or {}
        if props.get("title") == tab:
            return props.get("sheetId")
    return None


def _find_all_rows_by_value(tab, col_idx, value, start_row=2):
    """All 1-based row numbers whose column equals value (exact string match)."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    letter = _col_letter(col_idx)
    target = str(value or "").strip()
    if not target:
        return []
    res = _with_retry(lambda: _service.spreadsheets().values().get(
        spreadsheetId=sheet_id, range=f"'{tab}'!{letter}:{letter}").execute())
    rows = []
    for i, row in enumerate(res.get("values", []), start=1):
        if i < start_row:
            continue
        if row and str(row[0]).strip() == target:
            rows.append(i)
    return rows


def _delete_sheet_rows(tab, row_nums):
    """Physically delete 1-based rows from a tab (bottom → top)."""
    nums = sorted({int(n) for n in row_nums if int(n) >= 2}, reverse=True)
    if not nums:
        return {"ok": True, "operation": "noop", "tab": tab, "rowsDeleted": 0}
    gid = _gid_for_tab(tab)
    if gid is None:
        return {"ok": False, "operation": "refused", "tab": tab,
                "error": f"tab '{tab}' not found in spreadsheet"}
    sheet_id = os.environ.get("GSHEET_ID", "")
    reqs = [{
        "deleteDimension": {
            "range": {
                "sheetId": gid,
                "dimension": "ROWS",
                "startIndex": r - 1,
                "endIndex": r,
            }
        }
    } for r in nums]
    _with_retry(lambda: _service.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id, body={"requests": reqs}).execute())
    invalidate_header_cache(tab)
    # Drop ID-row caches for this tab (row numbers shifted).
    for key in list(_idrow_cache.keys()):
        if key[0] == tab:
            _idrow_cache.pop(key, None)
    for key in list(_formula_cache.keys()):
        if key[0] == tab:
            _formula_cache.pop(key, None)
    return {"ok": True, "operation": "deleted", "tab": tab, "rowsDeleted": len(nums),
            "rows": sorted(nums)}


def _delete_lead_traces_sync(lead_id):
    """Remove every operational register row that belongs to lead_id.

    Walks SYNC_MAP tabs. Prefer the Lead ID column when present (covers multi-row
    entities like payments / activities). Falls back to the entity's
    stable ID column when that column IS leadId (Lead Register, Delivery, Earnings).

    Scheme Claim Register is a permanent ledger: claim rows are never deleted here
    (or on go-live clear / receipt). Status may be Received; the row stays forever.
    """
    lead_id = str(lead_id or "").strip()
    if not lead_id:
        return {"ok": False, "error": "leadId required", "tabs": []}
    per_tab = {}
    for entity, spec in SYNC_MAP.items():
        tab, id_field, fields = spec[0], spec[1], spec[2]
        if is_permanent_ledger_tab(tab):
            per_tab[tab] = {
                "ok": True, "entity": entity, "operation": "preserved",
                "row_nums": [], "rowsDeleted": 0,
                "reason": "permanent ledger — Scheme Claim Register never archives",
            }
            continue
        try:
            header_row = _header_row_for(entity, tab)
            # Resolve with leadId included so we can scan multi-row registers.
            want = list(dict.fromkeys([*fields, "leadId", id_field]))
            mapping, missing = _resolve_columns(tab, want, use_cache=False, header_row=header_row)
            row_nums = []
            if "leadId" in mapping:
                row_nums = _find_all_rows_by_value(
                    tab, mapping["leadId"], lead_id, start_row=header_row + 1)
            elif id_field == "leadId" and id_field in mapping:
                hit = _find_row_by_id(tab, mapping[id_field], lead_id, start_row=header_row + 1)
                if hit:
                    row_nums = [hit]
            else:
                per_tab[tab] = {"ok": False, "entity": entity, "operation": "skipped",
                                "error": "no Lead ID column to match", "missingHeaders": missing}
                continue
        except Exception as e:
            per_tab[tab] = {"ok": False, "entity": entity, "operation": "error",
                            "error": str(e)[:300]}
            continue
        # Same physical tab may appear for one entity only in SYNC_MAP today, but
        # accumulate in case env overrides collide.
        existing = per_tab.get(tab, {"entity": entity, "row_nums": []})
        existing["entity"] = entity
        existing.setdefault("row_nums", [])
        existing["row_nums"].extend(row_nums)
        per_tab[tab] = existing

    results = []
    total = 0
    for tab, info in per_tab.items():
        if info.get("operation") == "preserved":
            results.append({"tab": tab, **info})
            continue
        if "error" in info and "row_nums" not in info:
            results.append({"tab": tab, **info})
            continue
        try:
            res = _delete_sheet_rows(tab, info.get("row_nums") or [])
        except Exception as e:
            res = {"ok": False, "operation": "error", "tab": tab, "error": str(e)[:300],
                   "rowsDeleted": 0}
        res["entity"] = info.get("entity")
        results.append(res)
        total += int(res.get("rowsDeleted") or 0)
    # Walk completed; per-tab failures are reported in tabs[] (do not abort the cascade).
    return {"ok": True, "operation": "deleted" if total else "noop",
            "leadId": lead_id, "rowsDeleted": total, "tabs": results}


async def delete_lead_traces(lead_id: str):
    """Owner lead delete → remove the lead and all related register rows from Sheets.

    Never raises. Honours the same write-safety gates as sync().
    """
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": True, "operation": "skipped", "reason": _status.get("reason", "sync disabled"),
                "rowsDeleted": 0, "tabs": []}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "operation": "blocked", "error": blocked, "rowsDeleted": 0, "tabs": []}
    try:
        res = await asyncio.to_thread(_delete_lead_traces_sync, lead_id)
        if res.get("ok"):
            _mark_health(True)
        else:
            _mark_health(False, str(res.get("error") or ""))
        return res
    except Exception as e:
        invalidate_header_cache()
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "operation": "error", "error": str(e)[:500], "rowsDeleted": 0, "tabs": []}


def _delete_entity_by_id_sync(entity: str, id_value: str):
    """Physically delete the sheet row whose stable ID equals id_value."""
    id_value = str(id_value or "").strip()
    if entity not in SYNC_MAP:
        return {"ok": False, "operation": "error", "error": f"unknown entity '{entity}'",
                "rowsDeleted": 0}
    if not id_value:
        return {"ok": False, "operation": "error", "error": "id required", "rowsDeleted": 0}
    tab, id_field, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][1], SYNC_MAP[entity][2]
    header_row = _header_row_for(entity, tab)
    mapping, missing = _resolve_columns(tab, [id_field, *fields[:1]], use_cache=False,
                                        header_row=header_row)
    if id_field not in mapping:
        return {"ok": False, "operation": "skipped", "tab": tab,
                "error": f"no {id_field} column", "missingHeaders": missing, "rowsDeleted": 0}
    row_nums = _find_all_rows_by_value(
        tab, mapping[id_field], id_value, start_row=header_row + 1)
    res = _delete_sheet_rows(tab, row_nums)
    res["entity"] = entity
    res["entityId"] = id_value
    return res


async def delete_entity_row(entity: str, id_value: str):
    """Owner delete of one register row (e.g. a payment receipt). Never raises."""
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": True, "operation": "skipped", "reason": _status.get("reason", "sync disabled"),
                "rowsDeleted": 0, "entity": entity, "entityId": id_value}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "operation": "blocked", "error": blocked, "rowsDeleted": 0,
                "entity": entity, "entityId": id_value}
    try:
        res = await asyncio.to_thread(_delete_entity_by_id_sync, entity, id_value)
        if res.get("ok"):
            _mark_health(True)
        else:
            _mark_health(False, str(res.get("error") or ""))
        return res
    except Exception as e:
        invalidate_header_cache()
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "operation": "error", "error": str(e)[:500], "rowsDeleted": 0,
                "entity": entity, "entityId": id_value}


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
        _mark_health(True)
        return True
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return False


# ---------------------------------------------------------------- derived report tabs
FINANCE_PENDING_TAB = _tab("GSHEET_TAB_FINANCE_PENDING", "Finance Pending")
FINANCE_OVERDUE_TAB = _tab("GSHEET_TAB_FINANCE_OVERDUE", "Finance Overdue")

# Permanent ledgers — never archived, never cleared on go-live reset, never removed
# when a lead is deleted or when OEM payment is Received. Claim rows are upsert-only
# for life; Status may become Received but the row stays forever.
PERMANENT_LEDGER_TABS = frozenset({
    SYNC_MAP["claims"][0],  # Scheme Claim Register
})


def is_permanent_ledger_tab(tab: str) -> bool:
    return str(tab or "").strip() in PERMANENT_LEDGER_TABS


# Operational mirrors wiped by go-live reset (headers kept). Masters / Settings never
# listed. Permanent ledgers (Scheme Claim Register) are intentionally excluded.
OPERATIONAL_CLEAR_TABS = tuple(dict.fromkeys([
    *(SYNC_MAP[e][0] for e in SYNC_MAP if not is_permanent_ledger_tab(SYNC_MAP[e][0])),
    "Incentive Register",
    "Quotation Log",
    "OEM Extra Support Register",
    FINANCE_PENDING_TAB,
    FINANCE_OVERDUE_TAB,
]))


def _clear_operational_register_rows_sync():
    """Clear data rows (A2:ZZ) on operational registers. Never touches masters."""
    sheet_id = os.environ.get("GSHEET_ID", "")
    meta = _service.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(title))",
    ).execute()
    titles = {sh["properties"]["title"] for sh in meta.get("sheets", [])}
    ranges = [f"'{tab}'!A2:ZZ" for tab in OPERATIONAL_CLEAR_TABS if tab in titles]
    cleared = []
    for i in range(0, len(ranges), 10):
        chunk = ranges[i:i + 10]
        resp = _service.spreadsheets().values().batchClear(
            spreadsheetId=sheet_id, body={"ranges": chunk},
        ).execute()
        cleared.extend(resp.get("clearedRanges", chunk))
    return {"tabs": [t for t in OPERATIONAL_CLEAR_TABS if t in titles], "clearedRanges": cleared}


async def clear_operational_register_rows():
    """Go-live helper: wipe transactional sheet rows while preserving header row 1
    and all master/config tabs. Returns False if sync is disabled / write-blocked."""
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return {"ok": False, "reason": _status.get("reason", "sync disabled")}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "writeBlocked": True}
    try:
        detail = await asyncio.to_thread(_clear_operational_register_rows_sync)
        invalidate_header_cache()
        _mark_health(True)
        return {"ok": True, **detail}
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
        return {"ok": False, "reason": str(e)[:300]}


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
        _mark_health(True)
        return True
    except Exception as e:
        _status["lastError"] = str(e)
        _mark_health(False, str(e)[:300])
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
        env_blocked = bool((st.get("envSafety") or {}).get("writeBlocked"))
        return {"ok": False, "reason": st.get("reason", "sync not enabled"),
                "canWrite": st.get("canWrite", False), "writeBlocked": env_blocked}
    blocked = _write_blocked()
    if blocked:
        return {"ok": False, "reason": blocked, "canWrite": False, "writeBlocked": True}
    invalidate_header_cache()
    headers_ensured = await ensure_pending_columns()
    invalidate_header_cache()
    result = {}
    for entity, docs in datasets.items():
        if entity not in SYNC_MAP:
            continue
        try:
            stats = await asyncio.to_thread(_backfill_entity_sync, entity, docs)
        except Exception as e:
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
            stats = {"appended": appended, "updated": updated, "failed": failed,
                     "errors": (errors or [str(e)[:300]])}
        result[entity] = stats
    failed = sum(int(v.get("failed") or 0) for v in result.values())
    return {"ok": True, "result": result, "failed": failed,
            "headersEnsured": headers_ensured}


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
