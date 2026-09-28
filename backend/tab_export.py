"""Per-tab Excel export — one register, chosen columns, optional filters.

GET /export with no tab still dumps the legacy six-sheet workbook. With
tab=leads (or bookings, payments, …) the file is only that register, and
columns / month / year / status / q limit what goes in.
"""
from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from typing import Optional

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

import period as periodmod

MAX_ROWS = 10000
_SAFE_TAB = re.compile(r"^[a-z0-9_]+$")


def _col(key: str, label: str, *, default: bool = False) -> dict:
    return {"key": key, "label": label, "default": default}


@dataclass(frozen=True)
class Tab:
    key: str
    label: str
    collection: str
    columns: tuple
    paths: tuple
    date_fields: tuple = ()
    date_mode: str = ""  # "lead" uses lead_register_date
    status_field: str = ""
    statuses: tuple = ()
    search_fields: tuple = ()
    extra_filter: dict = field(default_factory=dict)
    sort: tuple = ("_id", -1)
    loader: Optional[str] = None  # deliveries | extra_support


LEAD_STATUSES = (
    "New", "Contacted", "Follow-up", "In Progress", "Booked",
    "Finance Process", "Delivered", "Close Won", "Lost",
)

TABS: dict[str, Tab] = {}
PATH_TO_TAB: dict[str, str] = {}


def _register(tab: Tab) -> Tab:
    TABS[tab.key] = tab
    for p in tab.paths:
        PATH_TO_TAB[p] = tab.key
    return tab


_register(Tab(
    key="leads", label="Lead Register", collection="leads",
    paths=("/leads", "/allocation", "/cancellations", "/whatsapp"),
    date_mode="lead",
    status_field="currentStatus", statuses=LEAD_STATUSES,
    search_fields=("customerName", "mobile", "leadId", "executive", "interestedModel"),
    sort=("leadId", -1),
    columns=(
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("mobile", "Mobile", default=True),
        _col("interestedModel", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("executive", "Executive", default=True),
        _col("currentStatus", "Status", default=True),
        _col("customerPayable", "Payable", default=True),
        _col("totalReceived", "Received", default=True),
        _col("customerOutstanding", "Outstanding", default=True),
        _col("bookingDate", "Booking date", default=True),
        _col("createdDate", "Created"),
        _col("deliveryDate", "Delivery date"),
        _col("leadSource", "Source"),
        _col("customerType", "Customer type"),
        _col("gstin", "GSTIN"),
        _col("cxDemand", "Cx Demand"),
        _col("budget", "Budget"),
        _col("oemExtraSupportReceived", "OEM Extra Support received"),
        _col("chassisNumber", "Chassis"),
        _col("remarks", "Remarks"),
        _col("vehicleCount", "Units"),
    ),
))

_register(Tab(
    key="approvals", label="Lead approvals", collection="lead_requests",
    paths=("/approvals",),
    date_fields=("createdAt",),
    status_field="status",
    statuses=("pending", "approved", "rejected"),
    search_fields=("customerName", "mobile", "requestId", "executive", "leadId"),
    sort=("createdAt", -1),
    columns=(
        _col("requestId", "Request ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("mobile", "Mobile", default=True),
        _col("interestedModel", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("executive", "Executive", default=True),
        _col("budget", "Cx Demand", default=True),
        _col("status", "Status", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("existingLeadId", "Existing lead"),
        _col("createdAt", "Submitted", default=True),
        _col("oemExtraSupportReceived", "OEM Extra Support"),
        _col("customerType", "Customer type"),
    ),
))

_register(Tab(
    key="bookings", label="Booking Register", collection="bookings",
    paths=("/bookings",),
    date_fields=("bookingDate",),
    status_field="bookingStatus",
    statuses=("Active", "Cancelled", "Delivered"),
    search_fields=("customerName", "leadId", "bookingId", "model", "executive"),
    sort=("bookingId", -1),
    columns=(
        _col("bookingId", "Booking ID", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("bookingDate", "Date", default=True),
        _col("bookingAmount", "Advance", default=True),
        _col("paymentMode", "Mode", default=True),
        _col("paymentReference", "UTR / cheque", default=True),
        _col("bookingStatus", "Status", default=True),
        _col("executive", "Executive"),
    ),
))

_register(Tab(
    key="payments", label="Payment Ledger", collection="payments",
    paths=("/payments", "/accounts"),
    date_fields=("date",),
    status_field="paymentMode",
    statuses=("Cash", "UPI", "NEFT", "RTGS", "Cheque", "Finance", "Card"),
    search_fields=("receiptNumber", "leadId", "customerName", "paymentReference", "narration"),
    sort=("date", -1),
    columns=(
        _col("receiptNumber", "Receipt", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("date", "Date", default=True),
        _col("amount", "Amount", default=True),
        _col("paymentMode", "Mode", default=True),
        _col("paymentReference", "Reference", default=True),
        _col("narration", "Narration", default=True),
        _col("runningTotal", "Running total"),
        _col("outstandingBalance", "Outstanding"),
        _col("entryType", "Entry type"),
        _col("financeFileNumber", "Finance file"),
    ),
))

_register(Tab(
    key="finance", label="Finance Register", collection="finance",
    paths=("/finance", "/oem-finance"),
    date_fields=("deliveryDate", "createdAt", "lastUpdated"),
    status_field="status",
    statuses=("Open", "Partial", "Received", "Cancelled"),
    search_fields=("fileNumber", "leadId", "customerName", "financer"),
    sort=("fileNumber", -1),
    columns=(
        _col("fileNumber", "File number", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("financer", "Financer", default=True),
        _col("sanctionedAmount", "Sanctioned", default=True),
        _col("receivedAgainstFile", "Received", default=True),
        _col("fileOutstanding", "Outstanding", default=True),
        _col("status", "Status", default=True),
        _col("deliveryDate", "Delivery date"),
        _col("disbursementDate", "Disbursement date"),
    ),
))

_register(Tab(
    key="claims", label="Scheme Claim Register", collection="claims",
    paths=("/claims", "/oem-claim-dashboard", "/claim-exceptions", "/claim-reconciliation"),
    date_fields=("filedDate", "claimDate", "createdAt"),
    status_field="claimStatus",
    statuses=("Open", "Filed", "Submitted", "Received", "Rejected", "Cancelled"),
    search_fields=("claimId", "leadId", "customer", "component", "claimReference"),
    sort=("claimId", -1),
    columns=(
        _col("claimId", "Claim ID", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("customer", "Customer", default=True),
        _col("component", "Component", default=True),
        _col("claimAmount", "Claim amount", default=True),
        _col("claimStatus", "Status", default=True),
        _col("receivedAmount", "Received", default=True),
        _col("claimReference", "OEM reference"),
        _col("filedDate", "Filed date"),
        _col("chassisNumber", "Chassis"),
    ),
))

_register(Tab(
    key="deliveries", label="Delivery Tracker", collection="deliveries",
    paths=("/deliveries", "/oem-billing"),
    date_fields=("deliveryDate",),
    search_fields=("leadId", "customerName", "chassisNumber", "numberPlate"),
    loader="deliveries",
    columns=(
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("mobile", "Mobile", default=True),
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("deliveryDate", "Delivery date", default=True),
        _col("chassisNumber", "Chassis", default=True),
        _col("numberPlate", "Number plate", default=True),
        _col("insurance", "Insurance", default=True),
        _col("registration", "Registration"),
        _col("invoice", "Invoice"),
        _col("rc", "RC"),
        _col("pdi", "PDI"),
        _col("delivered", "Delivered"),
    ),
))

_register(Tab(
    key="quotations", label="Quotations", collection="quotations",
    paths=("/quotations",),
    date_fields=("date",),
    search_fields=("quoteId", "customerName", "mobile", "model"),
    sort=("quoteId", -1),
    columns=(
        _col("quoteId", "Quote ID", default=True),
        _col("date", "Date", default=True),
        _col("customerName", "Customer", default=True),
        _col("mobile", "Mobile", default=True),
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("customerPayable", "Payable", default=True),
        _col("grossVehicleCost", "GVC"),
        _col("totalDiscount", "Discount"),
        _col("executive", "Executive"),
    ),
))

_register(Tab(
    key="activities", label="Activity Log", collection="activities",
    paths=("/activities",),
    date_fields=("date",),
    status_field="activityType",
    statuses=("Call", "Visit", "WhatsApp", "Follow-up", "Other"),
    search_fields=("activityId", "leadId", "customerName", "discussion", "executive"),
    sort=("activityId", -1),
    columns=(
        _col("activityId", "ID", default=True),
        _col("date", "Date", default=True),
        _col("time", "Time"),
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("activityType", "Type", default=True),
        _col("discussion", "Discussion", default=True),
        _col("executive", "Executive", default=True),
    ),
))

_register(Tab(
    key="insurance", label="Insurance Payouts", collection="insurance",
    paths=("/insurance", "/insurance-report"),
    date_fields=("policyDate", "deliveryDate"),
    status_field="status",
    statuses=("Open", "Pending", "Received", "N/A"),
    search_fields=("entryId", "leadId", "customerName", "policyNumber", "insuranceAgent"),
    sort=("entryId", -1),
    columns=(
        _col("entryId", "Entry ID", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("insuranceAmount", "Premium", default=True),
        _col("expectedPayout", "Expected payout", default=True),
        _col("receivedPayout", "Received", default=True),
        _col("payoutOutstanding", "Outstanding", default=True),
        _col("status", "Status", default=True),
        _col("policyDate", "Policy date"),
        _col("deliveryDate", "Delivery date"),
        _col("insuranceAgent", "Agent"),
        _col("policyNumber", "Policy number"),
    ),
))

_register(Tab(
    key="insurance_agents", label="Insurance Agents", collection="insurance_agents",
    paths=("/insurance-agents",),
    search_fields=("agentId", "name", "mobile"),
    sort=("name", 1),
    columns=(
        _col("agentId", "Agent ID", default=True),
        _col("name", "Name", default=True),
        _col("mobile", "Mobile", default=True),
        _col("payoutRate", "Payout rate", default=True),
        _col("status", "Status", default=True),
    ),
))

_register(Tab(
    key="price_master", label="Price Master", collection="price_master",
    paths=("/price-master", "/price-list"),
    status_field="status",
    statuses=("active", "inactive"),
    search_fields=("model", "variant", "priceId"),
    sort=("model", 1),
    columns=(
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("bodyType", "Body", default=True),
        _col("exShowroom", "Ex-showroom", default=True),
        _col("rto", "RTO", default=True),
        _col("insurance", "Insurance", default=True),
        _col("tcsApplicable", "TCS", default=True),
        _col("status", "Status", default=True),
        _col("priceId", "Price ID"),
        _col("priceSource", "Source"),
        _col("accessories", "Accessories"),
        _col("handlingCharges", "Handling"),
    ),
))

_register(Tab(
    key="scheme_master", label="Scheme Master", collection="scheme_master",
    paths=("/scheme-master",),
    date_fields=("schemeMonth", "effectiveFrom"),
    search_fields=("model", "variant", "schemeMonth"),
    sort=("schemeMonth", -1),
    columns=(
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("schemeMonth", "Month", default=True),
        _col("consumerDiscount", "Consumer", default=True),
        _col("exchangeBonus", "Exchange", default=True),
        _col("loyaltyBonus", "Loyalty", default=True),
        _col("referralBonus", "Referral"),
        _col("dsaDiscount", "DSA"),
        _col("additionalDiscount", "Additional"),
        _col("insuranceBenefit", "Insurance benefit"),
        _col("rtoBenefit", "RTO benefit"),
        _col("effectiveFrom", "From"),
        _col("effectiveTo", "To"),
    ),
))

_register(Tab(
    key="incentive_master", label="Incentive Master", collection="incentive_master",
    paths=("/incentive-master", "/executive-incentive"),
    search_fields=("model", "variant"),
    columns=(
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("amount", "Amount", default=True),
        _col("status", "Status", default=True),
    ),
))

_register(Tab(
    key="inventory", label="Yard Inventory", collection="oem_inventory",
    paths=("/inventory",),
    search_fields=("model", "variant", "chassisNumber", "color"),
    sort=("model", 1),
    columns=(
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("chassisNumber", "Chassis", default=True),
        _col("color", "Colour", default=True),
        _col("status", "Status", default=True),
        _col("ageDays", "Age (days)"),
        _col("invoiceNumber", "Invoice"),
        _col("invoiceDate", "Invoice date"),
    ),
))

_register(Tab(
    key="staff", label="Staff", collection="staff",
    paths=("/staff",),
    status_field="status",
    statuses=("Active", "Inactive"),
    search_fields=("name", "mobile", "email", "staffId", "role"),
    sort=("name", 1),
    columns=(
        _col("staffId", "Staff ID", default=True),
        _col("name", "Name", default=True),
        _col("mobile", "Mobile", default=True),
        _col("email", "Email", default=True),
        _col("role", "Role", default=True),
        _col("monthlyTarget", "Monthly target", default=True),
        _col("status", "Status", default=True),
        _col("whatsappOptIn", "WhatsApp"),
        _col("remarks", "Remarks"),
    ),
))

_register(Tab(
    key="oem_claims", label="OEM Claim Settlements", collection="oem_portal_claims",
    paths=("/oem-claims", "/oem-claims/no-vehicle"),
    date_fields=("claimDate", "updatedAt"),
    status_field="status",
    statuses=("Submitted", "Credit Note Generated", "Sales Invoice Generated",
              "Settled", "Rejected", "Cancelled"),
    search_fields=("claimNumber", "chassisNumber", "customerName", "status"),
    sort=("claimNumber", -1),
    columns=(
        _col("claimNumber", "Claim number", default=True),
        _col("status", "Status", default=True),
        _col("chassisNumber", "Chassis", default=True),
        _col("customerName", "Customer", default=True),
        _col("claimAmount", "Amount", default=True),
        _col("claimDate", "Date", default=True),
        _col("model", "Model"),
        _col("variant", "Variant"),
    ),
))

_register(Tab(
    key="oem_extra_support", label="OEM Extra Support", collection="leads",
    paths=("/oem-extra-support", "/dropped-extra-support"),
    date_mode="lead",
    search_fields=("customerName", "leadId", "interestedModel", "executive"),
    loader="extra_support",
    sort=("leadId", -1),
    columns=(
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("interestedModel", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("executive", "Executive", default=True),
        _col("oemExtraSupportReceived", "Received", default=True),
        _col("oemExtraSupportPassed", "Passed", default=True),
        _col("oemExtraSupportRetained", "Retained", default=True),
        _col("currentStatus", "Status", default=True),
        _col("bookingDate", "Booking date"),
        _col("chassisNumber", "Chassis"),
    ),
))

_register(Tab(
    key="dealer_earnings", label="Dealer Earnings", collection="dealer_earnings",
    paths=("/dealer-earnings", "/earnings-report", "/owner-commercial"),
    date_fields=("deliveryDate", "bookingDate"),
    search_fields=("leadId", "customerName", "model"),
    sort=("leadId", -1),
    columns=(
        _col("leadId", "Lead ID", default=True),
        _col("customerName", "Customer", default=True),
        _col("model", "Model", default=True),
        _col("variant", "Variant", default=True),
        _col("total", "Total", default=True),
        _col("margin", "Margin", default=True),
        _col("scheme", "Scheme retained", default=True),
        _col("insurance", "Insurance", default=True),
        _col("extra", "OEM Extra", default=True),
        _col("deliveryDate", "Delivery date"),
        _col("bookingDate", "Booking date"),
    ),
))

_register(Tab(
    key="audit_log", label="Audit Trail", collection="audit_log",
    paths=("/audit-log", "/erp-audit"),
    date_fields=("timestamp",),
    status_field="module",
    statuses=("payment", "finance", "claim", "insurance", "scheme",
              "price-structure", "extra-income", "lead"),
    search_fields=("leadId", "actor", "module", "action"),
    sort=("timestamp", -1),
    columns=(
        _col("timestamp", "When", default=True),
        _col("actor", "Who", default=True),
        _col("action", "Action", default=True),
        _col("module", "Module", default=True),
        _col("leadId", "Lead ID", default=True),
        _col("summary", "Summary", default=True),
    ),
))


def catalog() -> dict:
    tabs = []
    for tab in TABS.values():
        tabs.append({
            "key": tab.key,
            "label": tab.label,
            "paths": list(tab.paths),
            "columns": list(tab.columns),
            "hasPeriod": bool(tab.date_fields or tab.date_mode),
            "statusField": tab.status_field or "",
            "statuses": list(tab.statuses),
            "hasSearch": bool(tab.search_fields),
        })
    return {"tabs": tabs, "pathToTab": dict(PATH_TO_TAB), "fallbackTab": "leads"}


def tab_for_path(pathname: str) -> str:
    p = str(pathname or "/").rstrip("/") or "/"
    if p.startswith("/oem-claims"):
        return "oem_claims"
    return PATH_TO_TAB.get(p) or "leads"


def _cell(doc: dict, key: str):
    if key == "interestedModel" and not doc.get(key) and doc.get("model"):
        return doc.get("model")
    if key == "customer" and not doc.get(key):
        return doc.get("customerName") or ""
    raw = doc.get(key)
    if raw is None:
        # approvals store some fields on payload
        payload = doc.get("payload") if isinstance(doc.get("payload"), dict) else {}
        raw = payload.get(key)
    if raw is None:
        return ""
    if isinstance(raw, (dict, list)):
        try:
            return json.dumps(raw, default=str)[:400]
        except (TypeError, ValueError):
            return str(raw)[:400]
    return raw


def _match_q(doc: dict, fields: tuple, needle: str) -> bool:
    blob = " ".join(str(_cell(doc, k) or "") for k in fields)
    return needle in blob.lower()


def _row_date(tab: Tab, doc: dict, status: str) -> str:
    if tab.date_mode == "lead":
        return periodmod.lead_register_date(doc, status)
    for k in tab.date_fields:
        v = str(doc.get(k) or "")
        if v:
            return v
    payload = doc.get("payload") if isinstance(doc.get("payload"), dict) else {}
    for k in tab.date_fields:
        v = str(payload.get(k) or "")
        if v:
            return v
    return ""


async def _load_deliveries(db, cap: int) -> list:
    leads = await db.leads.find(
        {"currentStatus": {"$in": ["Booked", "Finance Process", "Delivered"]}}
    ).to_list(cap)
    by_lead = {}
    lids = [l.get("leadId") for l in leads if l.get("leadId")]
    if lids:
        for d in await db.deliveries.find({"leadId": {"$in": lids}}).to_list(cap):
            if d.get("leadId"):
                by_lead[d["leadId"]] = d
    out = []
    for l in leads:
        d = by_lead.get(l.get("leadId")) or {}
        out.append({
            "leadId": l.get("leadId"),
            "customerName": l.get("customerName"),
            "mobile": l.get("mobile"),
            "model": l.get("interestedModel"),
            "variant": l.get("variant"),
            "insurance": d.get("insurance", ""),
            "registration": d.get("registration", ""),
            "invoice": d.get("invoice", ""),
            "rc": d.get("rc", ""),
            "pdi": d.get("pdi", ""),
            "delivered": d.get("delivered", "") or (
                "Yes" if str(l.get("deliveryStatus") or "").lower() == "delivered" else ""),
            "deliveryDate": d.get("deliveryDate") or l.get("deliveryDate") or "",
            "chassisNumber": d.get("chassisNumber") or l.get("chassisNumber") or "",
            "numberPlate": d.get("numberPlate", ""),
        })
    return out


async def _load_extra_support(db, cap: int) -> list:
    rows = []
    async for l in db.leads.find():
        try:
            rec = float(l.get("oemExtraSupportReceived") or 0)
        except (TypeError, ValueError):
            rec = 0
        if rec <= 0.01:
            continue
        rows.append(l)
        if len(rows) >= cap:
            break
    return rows


async def load_rows(db, tab: Tab, *, month: str = "", year: str = "",
                    status: str = "", q: str = "", limit: int = MAX_ROWS) -> list:
    cap = max(1, min(int(limit or MAX_ROWS), MAX_ROWS))
    if tab.loader == "deliveries":
        rows = await _load_deliveries(db, cap)
    elif tab.loader == "extra_support":
        rows = await _load_extra_support(db, cap)
    else:
        query = dict(tab.extra_filter or {})
        if tab.status_field and status and status not in ("", "all"):
            query[tab.status_field] = status
        cursor = db[tab.collection].find(query)
        if tab.sort:
            cursor = cursor.sort(*tab.sort)
        rows = await cursor.to_list(cap)
        if tab.key == "approvals":
            flattened = []
            for r in rows:
                payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
                merged = {**payload, **{k: v for k, v in r.items() if k != "payload"}}
                flattened.append(merged)
            rows = flattened
        elif tab.status_field and status and status not in ("", "all") and tab.loader:
            rows = [r for r in rows if str(r.get(tab.status_field) or "") == status]
    if tab.loader and tab.status_field and status and status not in ("", "all"):
        rows = [r for r in rows if str(r.get(tab.status_field) or "") == status]
    needle = str(q or "").strip().lower()
    if needle and tab.search_fields:
        rows = [r for r in rows if _match_q(r, tab.search_fields, needle)]
    try:
        period = periodmod.parse_period(month or "", year or "")
    except ValueError as e:
        raise HTTPException(422, str(e)) from e
    if not period.is_all and (tab.date_fields or tab.date_mode):
        rows = [r for r in rows if periodmod.in_period(_row_date(tab, r, status), period)]
    return rows[:cap]


def chosen_columns(tab: Tab, columns: str | None) -> list[dict]:
    by_key = {c["key"]: c for c in tab.columns}
    if columns:
        keys = [k.strip() for k in str(columns).split(",") if k.strip()]
        picked = [by_key[k] for k in keys if k in by_key]
        if picked:
            return picked
    return [c for c in tab.columns if c.get("default")] or list(tab.columns)


def sheet_name(label: str) -> str:
    name = re.sub(r"[\\/*?:\[\]]", " ", label).strip() or "Export"
    return name[:31]


async def build_xlsx(db, *, tab_key: str, columns: str = "", month: str = "",
                     year: str = "", status: str = "", q: str = ""):
    import openpyxl
    key = str(tab_key or "").strip().lower()
    if not _SAFE_TAB.match(key) or key not in TABS:
        raise HTTPException(422, "Unknown export tab. Open a register and try Export again.")
    tab = TABS[key]
    cols = chosen_columns(tab, columns)
    rows = await load_rows(db, tab, month=month, year=year, status=status, q=q)
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = sheet_name(tab.label)
    ws.append([c["label"] for c in cols])
    for doc in rows:
        ws.append([_cell(doc, c["key"]) for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    stamp = periodmod.utc_today()
    fname = f"euler_{tab.key}_{stamp}.xlsx"
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
