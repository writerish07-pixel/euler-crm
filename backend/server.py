import io
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field

import commercial as ce
import seed as seeder
import auth as authmod
import gsheets

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Euler CRM API")

auth_router = authmod.build_router(db)
current_user = auth_router.current_user
owner_only = auth_router.owner_only

api = APIRouter(prefix="/api", dependencies=[Depends(current_user)])
public = APIRouter(prefix="/api")


# ---------------------------------------------------------------- helpers
def clean(doc):
    if not doc:
        return doc
    doc.pop("_id", None)
    return doc


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def this_month():
    return datetime.now(timezone.utc).strftime("%Y-%m")


async def next_id(kind, prefix, width=6):
    doc = await db.counters.find_one_and_update(
        {"_id": kind}, {"$inc": {"seq": 1}}, upsert=True, return_document=True
    )
    return f"{prefix}{str(doc['seq']).zfill(width)}"


async def get_lead_or_404(lead_id):
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        raise HTTPException(404, f"Lead {lead_id} not found")
    return clean(lead)


async def get_scheme_rows():
    return [clean(s) for s in await db.scheme_master.find().to_list(1000)]


# ---------------------------------------------------------------- step eligibility (LeadPickerService PICKER_STAGE + requireActiveLead_)
def _is_booked(lead):
    cs = (lead.get("currentStatus") or "").lower()
    return ("book" in cs or cs == "delivered" or "finance" in cs
            or bool(lead.get("bookingDate")) or ce.num(lead.get("bookingAmount")) > 0)


def _is_delivered(lead):
    return (lead.get("deliveryStatus") or "").lower() == "delivered" or (lead.get("currentStatus") or "").lower() == "delivered"


def _acct(lead):
    return (lead.get("accountStatus") or "Active").strip() or "Active"


def lead_actions(lead):
    """Which workflow steps a lead is eligible for (faithful to PICKER_STAGE + requireActiveLead_)."""
    active = _acct(lead) == "Active"
    booked = _is_booked(lead)
    delivered = _is_delivered(lead)
    not_archived = _acct(lead) != "Archived"
    return {
        "canBook": active and not booked,                 # booking stage: exclude booked/delivered
        "canPrice": active,                               # requires Active
        "canScheme": active,                              # requires Active
        "canPayment": active,                             # customer payment requires Active
        "canFinanceReceipt": not_archived,               # finance receipt allowed after close
        "canDeliver": active and booked and not delivered,# delivery stage: exclude delivered
        "canClose": active and not delivered,             # close stage: exclude delivered / non-active
        "isBooked": booked, "isDelivered": delivered, "isActive": active,
    }


def _require_action(lead, key, verb):
    acts = lead_actions(lead)
    if not acts.get(key):
        raise HTTPException(409, f"This lead is not eligible for {verb} (status: {lead.get('currentStatus') or 'New'} / {_acct(lead)}).")


def lead_to_snapshot(lead):
    """Build a commercial-engine snapshot dict from a lead document."""
    return {
        "bookingDate": lead.get("bookingDate", ""),
        "benefitPassedBreakup": lead.get("benefitPassedBreakup", ""),
        "exShowroom": lead.get("exShowroom", 0),
        "accessories": lead.get("accessoriesAmount", 0),
        "insurance": lead.get("insuranceAmount", 0),
        "registrationRto": lead.get("rto", 0),
        "fastag": lead.get("fastag", 0),
        "handlingCharges": lead.get("handlingCharges", 0),
        "trc": lead.get("trc", 0),
        "extendedWarranty": lead.get("extendedWarranty", 0),
        "rsaAmc": 0,
        "otherCharges": lead.get("otherCharges", 0),
        "tcsApplicable": lead.get("tcsApplicable", "No"),
        "consumerDiscount": lead.get("consumerDiscount", 0),
        "exchangeBonus": lead.get("exchangeBonus", 0),
        "loyaltyBonus": lead.get("loyaltyBonus", 0),
        "referralBonus": lead.get("referralBonus", 0),
        "dsaDiscount": lead.get("dsaDiscount", 0),
        "additionalDiscount": lead.get("additionalDiscount", 0),
        "benefitMode": lead.get("benefitMode", "Full Benefit"),
        "customerBenefitPassed": lead.get("customerBenefitPassed", 0),
        "finalExchangeValue": lead.get("finalExchangeValue", 0),
        "oemExtraSupportReceived": lead.get("oemExtraSupportReceived", 0),
        "oemExtraSupportPassed": lead.get("oemExtraSupportPassed", 0),
        "model": lead.get("interestedModel", ""),
        "variant": lead.get("variant", ""),
    }


async def recompute_lead(lead_id):
    """Recompute all derived commercial + payment fields for a lead and persist."""
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return None
    snap = lead_to_snapshot(lead)
    scheme_rows = await get_scheme_rows()
    totals = ce.compute_commercial_totals(snap)
    margin = ce.compute_dealer_margin(snap)
    income = ce.compute_scheme_income_breakdown(snap, scheme_rows)
    shares = ce.compute_scheme_claim_shares(snap, scheme_rows)
    # total received from payments
    agg = await db.payments.aggregate([
        {"$match": {"leadId": lead_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_received = ce.round2(agg[0]["total"]) if agg else 0.0
    customer_payable = totals["customerPayable"]
    customer_outstanding = ce.round2(max(0.0, customer_payable - total_received)) if customer_payable > 0 else 0.0
    updates = {
        "grossVehicleCost": totals["grossVehicleCost"],
        "customerPayable": customer_payable,
        "totalDiscount": totals["totalDiscount"],
        "oemSchemeAmount": totals["oemEligible"],
        "dealerSchemeAmount": totals["dealerDiscount"],
        "totalReceived": total_received,
        "customerOutstanding": customer_outstanding,
        "outstandingAmount": customer_outstanding,
        # OEM claimable = OEM COMPANY share (per Scheme Master), not the raw offer sum
        "companyOutstanding": shares["eligibleTotal"],
        "oemClaimCompanyShare": shares["eligibleTotal"],
        "schemeCompanyTotal": shares["displayTotal"],
        "dealerSchemeRetained": income["retainedIncomeTotal"],
        "dealerMarginNetExGst": margin["marginNetExGst"],
        "lastUpdated": now_iso(),
    }
    await db.leads.update_one({"leadId": lead_id}, {"$set": updates})
    return {**lead, **updates}


# ---------------------------------------------------------------- models
class LeadIn(BaseModel):
    customerName: str
    mobile: str = ""
    altMobile: str = ""
    village: str = ""
    city: str = ""
    leadSource: str = "Walk-in"
    interestedModel: str = ""
    variant: str = ""
    executive: str = ""
    currentStatus: str = "New"
    priority: str = "Normal"
    budget: float = 0
    remarks: str = ""
    financeRequired: str = "No"
    exchangeRequired: str = "No"
    nextFollowupDate: Optional[str] = None


class BookingIn(BaseModel):
    bookingDate: Optional[str] = None
    bookingAmount: float = 0
    executive: str = ""
    paymentMode: str = "Cash"
    financeRequired: str = "No"
    exchangeRequired: str = "No"


class PriceStructureIn(BaseModel):
    exShowroom: float = 0
    rto: float = 0
    insuranceAmount: float = 0
    accessoriesAmount: float = 0
    handlingCharges: float = 0
    trc: float = 0
    fastag: float = 0
    extendedWarranty: float = 0
    otherCharges: float = 0
    tcsApplicable: str = "No"
    finalExchangeValue: float = 0


class SchemeIn(BaseModel):
    consumerDiscount: float = 0
    exchangeBonus: float = 0
    loyaltyBonus: float = 0
    referralBonus: float = 0
    dsaDiscount: float = 0
    additionalDiscount: float = 0
    benefitMode: str = "Full Benefit"
    customerBenefitPassed: float = 0
    benefitPassedBreakup: Optional[str] = None
    oemExtraSupportReceived: float = 0
    oemExtraSupportPassed: float = 0


class PaymentIn(BaseModel):
    amount: float
    paymentMode: str = "Cash"
    date: Optional[str] = None
    narration: str = ""
    financerName: str = ""
    financeFileNumber: str = ""


class DeliveryIn(BaseModel):
    insurance: str = ""
    registration: str = ""
    invoice: str = ""
    accessories: str = ""
    rc: str = ""
    pdi: str = ""
    delivered: str = ""
    deliveryDate: Optional[str] = None
    invoiceNumber: str = ""
    chassisNumber: str = ""
    numberPlate: str = ""
    insurerName: str = ""
    feedback: str = ""


class CloseIn(BaseModel):
    closeReason: str = ""


class ActivityIn(BaseModel):
    activityType: str = "Note"
    discussion: str = ""
    executive: str = ""
    nextFollowup: str = ""


class SnapshotComputeIn(BaseModel):
    exShowroom: float = 0
    accessories: float = 0
    insurance: float = 0
    registrationRto: float = 0
    fastag: float = 0
    handlingCharges: float = 0
    trc: float = 0
    extendedWarranty: float = 0
    otherCharges: float = 0
    tcsApplicable: str = "No"
    consumerDiscount: float = 0
    exchangeBonus: float = 0
    loyaltyBonus: float = 0
    referralBonus: float = 0
    dsaDiscount: float = 0
    additionalDiscount: float = 0
    benefitMode: str = "Full Benefit"
    finalExchangeValue: float = 0


# ---------------------------------------------------------------- misc
@api.get("/")
async def root():
    return {"app": "Euler CRM", "status": "ok"}


@api.get("/masters")
async def masters():
    models = await db.price_master.distinct("model")
    return {**seeder.MASTERS, "models": sorted([m for m in models if m])}


@api.post("/admin/reseed")
async def reseed():
    res = await seeder.run_seed(db, force=True)
    for l in await db.leads.find().to_list(2000):
        await recompute_lead(l["leadId"])
    return res


# ---------------------------------------------------------------- dashboard
@api.get("/dashboard")
async def dashboard():
    leads = await db.leads.find().to_list(5000)
    payments = await db.payments.find().to_list(5000)
    ym = this_month()
    td = today()

    def in_month(d):
        return bool(d) and str(d).startswith(ym)

    def is_today(d):
        return str(d) == td

    booked = [l for l in leads if "book" in (l.get("currentStatus") or "").lower()]
    delivered = [l for l in leads if (l.get("deliveryStatus") or "").lower() == "delivered" or (l.get("currentStatus") or "").lower() == "delivered"]
    active_booked = [l for l in booked if (l.get("deliveryStatus") or "").lower() != "delivered"]

    monthly_leads = [l for l in leads if in_month(l.get("createdDate"))]
    monthly_bookings = [l for l in booked if in_month(l.get("bookingDate"))]

    pay_by_mode = {"Cash": 0.0, "UPI": 0.0, "Finance": 0.0, "Other": 0.0}
    month_payments = [p for p in payments if in_month(p.get("date"))]
    for p in month_payments:
        mode = (p.get("paymentMode") or "").strip()
        key = mode if mode in ("Cash", "UPI", "Finance") else "Other"
        pay_by_mode[key] += ce.num(p.get("amount"))

    cust_os = sum(ce.num(l.get("customerOutstanding")) for l in leads)
    company_os = sum(ce.num(l.get("companyOutstanding")) for l in leads)

    # model performance
    models = {}
    for l in leads:
        m = l.get("interestedModel") or "Unknown"
        row = models.setdefault(m, {"model": m, "leads": 0, "bookings": 0, "deliveries": 0, "pending": 0, "customerOs": 0.0, "revenue": 0.0})
        row["leads"] += 1
        if l in booked:
            row["bookings"] += 1
        if l in delivered:
            row["deliveries"] += 1
        row["customerOs"] += ce.num(l.get("customerOutstanding"))
    for l in active_booked:
        m = l.get("interestedModel") or "Unknown"
        if m in models:
            models[m]["pending"] += 1
    for p in payments:
        lead = next((x for x in leads if x.get("leadId") == p.get("leadId")), None)
        if lead:
            m = lead.get("interestedModel") or "Unknown"
            if m in models:
                models[m]["revenue"] += ce.num(p.get("amount"))
    model_perf = sorted(models.values(), key=lambda x: -x["leads"])

    return {
        "kpis": {
            "todayLeads": len([l for l in leads if is_today(l.get("createdDate"))]),
            "todayBookings": len([l for l in booked if is_today(l.get("bookingDate"))]),
            "todayDeliveries": len([l for l in delivered if is_today(l.get("deliveryDate"))]),
            "monthlyLeads": len(monthly_leads),
            "monthlyBookings": len(monthly_bookings),
            "activeBookings": len(active_booked),
            "monthlyDeliveries": len([l for l in delivered if in_month(l.get("deliveryDate"))]),
            "pendingDeliveries": len(active_booked),
            "totalLeads": len(leads),
            "conversion": round((len(monthly_bookings) / len(monthly_leads) * 100), 1) if monthly_leads else 0,
            "revenue": ce.round2(sum(ce.num(p.get("amount")) for p in month_payments)),
        },
        "payments": {k: ce.round2(v) for k, v in pay_by_mode.items()},
        "outstanding": {
            "customer": ce.round2(cust_os),
            "company": ce.round2(company_os),
            "total": ce.round2(cust_os + company_os),
        },
        "modelPerformance": model_perf,
        "lastUpdated": now_iso(),
    }


# ---------------------------------------------------------------- leads
@api.get("/leads")
async def list_leads(status: Optional[str] = None, q: Optional[str] = None):
    query = {}
    if status and status != "all":
        query["currentStatus"] = status
    if q:
        query["$or"] = [
            {"customerName": {"$regex": q, "$options": "i"}},
            {"mobile": {"$regex": q, "$options": "i"}},
            {"leadId": {"$regex": q, "$options": "i"}},
        ]
    leads = await db.leads.find(query).sort("leadId", -1).to_list(3000)
    return [clean(l) for l in leads]


@api.post("/leads")
async def create_lead(body: LeadIn):
    lead_id = await next_id("lead", "LD26")
    doc = {
        "leadId": lead_id,
        "createdDate": today(),
        **body.model_dump(),
        "accountStatus": "Active",
        "deliveryStatus": "",
        "outstandingAmount": 0, "customerOutstanding": 0, "companyOutstanding": 0,
        "totalReceived": 0, "customerPayable": 0, "grossVehicleCost": 0, "totalDiscount": 0,
        "consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0, "referralBonus": 0,
        "dsaDiscount": 0, "additionalDiscount": 0, "exShowroom": 0, "rto": 0, "insuranceAmount": 0,
        "accessoriesAmount": 0, "handlingCharges": 0, "trc": 0, "fastag": 0, "extendedWarranty": 0,
        "otherCharges": 0, "bookingAmount": 0, "lastUpdated": now_iso(),
    }
    await db.leads.insert_one(doc)
    await db.activities.insert_one({
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": today(),
        "time": datetime.now(timezone.utc).strftime("%H:%M"), "activityType": "Note",
        "discussion": "Lead created from CRM", "executive": body.executive,
        "customerName": body.customerName, "mobile": body.mobile, "model": body.interestedModel,
    })
    await gsheets.append("leads", doc)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.get("/leads/{lead_id}")
async def get_lead(lead_id: str):
    return await get_lead_or_404(lead_id)


@api.get("/leads/{lead_id}/360")
async def customer_360(lead_id: str):
    lead = await get_lead_or_404(lead_id)
    snap = lead_to_snapshot(lead)
    scheme_rows = await get_scheme_rows()
    commercials = ce.compute_full_commercials(snap, scheme_rows)
    payments = [clean(p) for p in await db.payments.find({"leadId": lead_id}).sort("date", 1).to_list(500)]
    activities = [clean(a) for a in await db.activities.find({"leadId": lead_id}).sort("activityId", -1).to_list(500)]
    delivery = clean(await db.deliveries.find_one({"leadId": lead_id}) or {})
    booking = clean(await db.bookings.find_one({"leadId": lead_id}) or {})
    claims = [clean(c) for c in await db.claims.find({"leadId": lead_id}).to_list(100)]
    return {
        "lead": lead, "commercials": commercials, "payments": payments,
        "activities": activities, "delivery": delivery, "booking": booking,
        "claims": claims, "actions": lead_actions(lead),
    }


@api.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadIn):
    await get_lead_or_404(lead_id)
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**body.model_dump(exclude_unset=True), "lastUpdated": now_iso()}})
    await recompute_lead(lead_id)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.post("/leads/{lead_id}/convert-booking")
async def convert_booking(lead_id: str, body: BookingIn):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canBook", "conversion to booking")
    booking_id = await next_id("booking", "BK26")
    snapshot_id = await next_id("snapshot", "SN26")
    bdate = body.bookingDate or today()
    await db.leads.update_one({"leadId": lead_id}, {"$set": {
        "currentStatus": "Booked", "bookingDate": bdate, "bookingAmount": body.bookingAmount,
        "executive": body.executive or lead.get("executive"), "financeRequired": body.financeRequired,
        "exchangeRequired": body.exchangeRequired, "lastPaymentMode": body.paymentMode, "lastUpdated": now_iso(),
    }})
    await db.bookings.insert_one({
        "bookingId": booking_id, "leadId": lead_id, "customerName": lead.get("customerName"),
        "bookingDate": bdate, "model": lead.get("interestedModel"), "variant": lead.get("variant"),
        "bookingAmount": body.bookingAmount, "amountReceived": body.bookingAmount, "paymentMode": body.paymentMode,
        "financeRequired": body.financeRequired, "exchangeRequired": body.exchangeRequired,
        "snapshotId": snapshot_id, "bookingStatus": "Booked", "createdBy": "crm", "createdDate": today(),
    })
    await gsheets.append("bookings", {
        "bookingId": booking_id, "leadId": lead_id, "customerName": lead.get("customerName"),
        "bookingDate": bdate, "model": lead.get("interestedModel"), "variant": lead.get("variant"),
        "bookingAmount": body.bookingAmount, "paymentMode": body.paymentMode, "bookingStatus": "Booked",
    })
    if body.bookingAmount > 0:
        await _add_payment_internal(lead_id, PaymentIn(
            amount=body.bookingAmount, paymentMode=body.paymentMode, date=bdate,
            narration="Booking advance"))
    await db.activities.insert_one({
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": bdate,
        "time": datetime.now(timezone.utc).strftime("%H:%M"), "activityType": "Booking",
        "discussion": "Booking converted.", "executive": lead.get("executive"),
        "customerName": lead.get("customerName"), "mobile": lead.get("mobile"), "model": lead.get("interestedModel"),
    })
    await recompute_lead(lead_id)
    return {"bookingId": booking_id, "snapshotId": snapshot_id, "lead": clean(await db.leads.find_one({"leadId": lead_id}))}


@api.put("/leads/{lead_id}/price-structure")
async def set_price_structure(lead_id: str, body: PriceStructureIn):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canPrice", "price-structure edits (only Active leads)")
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**body.model_dump(), "lastUpdated": now_iso()}})
    lead = await recompute_lead(lead_id)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.put("/leads/{lead_id}/scheme")
async def set_scheme(lead_id: str, body: SchemeIn):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canScheme", "scheme edits (only Active leads)")
    payload = body.model_dump()
    if payload.get("benefitPassedBreakup") is None:
        payload.pop("benefitPassedBreakup", None)
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**payload, "lastUpdated": now_iso()}})
    await recompute_lead(lead_id)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.post("/leads/{lead_id}/close")
async def close_lead(lead_id: str, body: CloseIn):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canClose", "closing (delivered or non-active leads cannot be closed here)")
    await db.leads.update_one({"leadId": lead_id}, {"$set": {
        "accountStatus": "Closed", "closedDate": today(), "closeReason": body.closeReason,
        "finalOutstanding": lead.get("customerOutstanding", 0), "lastUpdated": now_iso(),
    }})
    return clean(await db.leads.find_one({"leadId": lead_id}))


# ---------------------------------------------------------------- lead bulk import
IMPORT_COLUMNS = [
    ("Customer Name", "customerName"), ("Mobile", "mobile"), ("Alternate Mobile", "altMobile"),
    ("Village", "village"), ("City", "city"), ("Lead Source", "leadSource"),
    ("Interested Model", "interestedModel"), ("Variant", "variant"), ("Executive", "executive"),
    ("Current Status", "currentStatus"), ("Priority", "priority"), ("Budget", "budget"),
    ("Remarks", "remarks"), ("Finance Required", "financeRequired"), ("Exchange Required", "exchangeRequired"),
]


def _read_rows(filename: str, content: bytes):
    name = (filename or "").lower()
    if name.endswith(".csv"):
        import csv, io as _io
        text = content.decode("utf-8-sig", errors="replace")
        return [r for r in csv.reader(_io.StringIO(text))]
    import openpyxl, io as _io
    wb = openpyxl.load_workbook(_io.BytesIO(content), data_only=True, read_only=True)
    ws = wb.active
    return [[c for c in r] for r in ws.iter_rows(values_only=True)]


def _suggest_mapping(headers):
    """Auto-match detected headers to target fields by (case-insensitive) label/name."""
    lower = {str(h).strip().lower(): str(h).strip() for h in headers if h not in (None, "")}
    mapping = {}
    for label, field in IMPORT_COLUMNS:
        if label.lower() in lower:
            mapping[field] = lower[label.lower()]
        elif field.lower() in lower:
            mapping[field] = lower[field.lower()]
        else:
            mapping[field] = ""
    return mapping


def _coerce(field, v):
    if field == "budget":
        try:
            return float(v) if v not in (None, "") else 0
        except (ValueError, TypeError):
            return 0
    if field in ("mobile", "altMobile"):
        if isinstance(v, float):
            v = str(int(v))
        return str(v).strip() if v not in (None, "None") else ""
    return str(v).strip() if v not in (None, "None") else ""


def _parse_import_bytes(filename: str, content: bytes, mapping: dict = None):
    """Return (headers, rows). If mapping {field: headerName} given, use it; else auto-suggest."""
    rows = _read_rows(filename, content)
    if not rows:
        return [], []
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    header_idx = {h.lower(): i for i, h in enumerate(header)}
    if not mapping:
        mapping = _suggest_mapping(header)
    out = []
    for r in rows[1:]:
        if not any(c not in (None, "", "None") for c in r):
            continue
        d = {}
        for _, field in IMPORT_COLUMNS:
            src = mapping.get(field)
            i = header_idx.get(str(src).strip().lower()) if src else None
            v = r[i] if (i is not None and i < len(r)) else None
            d[field] = _coerce(field, v)
        if not d.get("customerName"):
            continue
        out.append(d)
    return header, out


@api.post("/leads/import/preview")
async def import_preview(file: UploadFile = File(...), mapping: Optional[str] = Form(None)):
    import json as _json
    content = await file.read()
    try:
        headers = [str(h).strip() if h is not None else "" for h in (_read_rows(file.filename, content) or [[]])[0]]
        mp = _json.loads(mapping) if mapping else _suggest_mapping(headers)
        _, rows = _parse_import_bytes(file.filename, content, mp)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")
    return {"detectedHeaders": [h for h in headers if h],
            "targetFields": [{"label": lbl, "field": fld} for lbl, fld in IMPORT_COLUMNS],
            "suggestedMapping": mp, "rowCount": len(rows), "sample": rows[:8]}


@api.post("/leads/import/commit")
async def import_commit(file: UploadFile = File(...), mapping: Optional[str] = Form(None)):
    import json as _json
    content = await file.read()
    try:
        mp = _json.loads(mapping) if mapping else None
        _, rows = _parse_import_bytes(file.filename, content, mp)
    except Exception as e:
        raise HTTPException(400, f"Could not parse file: {e}")
    created = 0
    for d in rows:
        lead_id = await next_id("lead", "LD26")
        doc = {
            "leadId": lead_id, "createdDate": today(),
            "customerName": d.get("customerName", ""), "mobile": d.get("mobile", ""),
            "altMobile": d.get("altMobile", ""), "village": d.get("village", ""), "city": d.get("city", ""),
            "leadSource": d.get("leadSource") or "Import", "interestedModel": d.get("interestedModel", ""),
            "variant": d.get("variant", ""), "executive": d.get("executive", ""),
            "currentStatus": d.get("currentStatus") or "New", "priority": d.get("priority") or "Normal",
            "budget": d.get("budget", 0), "remarks": d.get("remarks", ""),
            "financeRequired": d.get("financeRequired") or "No", "exchangeRequired": d.get("exchangeRequired") or "No",
            "accountStatus": "Active", "deliveryStatus": "",
            "outstandingAmount": 0, "customerOutstanding": 0, "companyOutstanding": 0, "totalReceived": 0,
            "customerPayable": 0, "grossVehicleCost": 0, "totalDiscount": 0,
            "consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0, "referralBonus": 0,
            "dsaDiscount": 0, "additionalDiscount": 0, "exShowroom": 0, "rto": 0, "insuranceAmount": 0,
            "accessoriesAmount": 0, "handlingCharges": 0, "trc": 0, "fastag": 0, "extendedWarranty": 0,
            "otherCharges": 0, "bookingAmount": 0, "lastUpdated": now_iso(), "importedBatch": today(),
        }
        await db.leads.insert_one(doc)
        await gsheets.append("leads", doc)
        created += 1
    return {"created": created}


# ---------------------------------------------------------------- payments
async def _add_payment_internal(lead_id, body: PaymentIn):
    lead = await db.leads.find_one({"leadId": lead_id})
    receipt = await next_id("receipt", "RC26")
    prior = await db.payments.aggregate([
        {"$match": {"leadId": lead_id}}, {"$group": {"_id": None, "t": {"$sum": "$amount"}}}
    ]).to_list(1)
    running = ce.round2((prior[0]["t"] if prior else 0) + body.amount)
    snap = lead_to_snapshot(lead) if lead else {}
    payable = ce.compute_commercial_totals(snap)["customerPayable"] if lead else 0
    outstanding = ce.round2(max(0.0, payable - running)) if payable > 0 else 0.0
    doc = {
        "receiptNumber": receipt, "leadId": lead_id, "customerName": lead.get("customerName") if lead else "",
        "date": body.date or today(), "amount": ce.round2(body.amount), "paymentMode": body.paymentMode,
        "narration": body.narration, "runningTotal": running, "outstandingBalance": outstanding,
        "paymentId": f"PY{uuid.uuid4().hex[:12]}", "financerName": body.financerName,
        "financeFileNumber": body.financeFileNumber,
    }
    await db.payments.insert_one(doc)
    await gsheets.append("payments", doc)
    if body.paymentMode == "Finance" and body.financeFileNumber:
        await _upsert_finance_file(lead_id, body)
    return clean(doc)


@api.get("/payments")
async def list_payments(lead_id: Optional[str] = None):
    q = {"leadId": lead_id} if lead_id else {}
    return [clean(p) for p in await db.payments.find(q).sort("date", -1).to_list(2000)]


@api.post("/leads/{lead_id}/payments")
async def add_payment(lead_id: str, body: PaymentIn):
    lead = await get_lead_or_404(lead_id)
    if body.paymentMode == "Finance":
        _require_action(lead, "canFinanceReceipt", "finance receipt (lead is archived)")
    else:
        _require_action(lead, "canPayment", "customer payment (only Active leads)")
    rec = await _add_payment_internal(lead_id, body)
    await recompute_lead(lead_id)
    return rec


# ---------------------------------------------------------------- finance
async def _upsert_finance_file(lead_id, body: PaymentIn):
    lead = await db.leads.find_one({"leadId": lead_id})
    existing = await db.finance.find_one({"fileNumber": body.financeFileNumber})
    if existing:
        received = ce.round2(ce.num(existing.get("receivedAgainstFile")) + body.amount)
        outstanding = ce.round2(max(0.0, ce.num(existing.get("sanctionedAmount")) - received))
        await db.finance.update_one({"fileNumber": body.financeFileNumber}, {"$set": {
            "receivedAgainstFile": received, "fileOutstanding": outstanding,
            "status": "Closed" if outstanding <= 0 else "Open", "lastPaymentDate": body.date or today(),
        }})
    else:
        sanctioned = ce.num(lead.get("customerPayable")) if lead else 0
        await db.finance.insert_one({
            "fileNumber": body.financeFileNumber, "leadId": lead_id,
            "customerName": lead.get("customerName") if lead else "", "financer": body.financerName,
            "sanctionedAmount": sanctioned, "receivedAgainstFile": ce.round2(body.amount),
            "fileOutstanding": ce.round2(max(0.0, sanctioned - body.amount)), "status": "Open",
            "lastPaymentDate": body.date or today(),
        })


@api.get("/finance")
async def list_finance(view: str = "all"):
    files = [clean(f) for f in await db.finance.find().to_list(1000)]
    if view == "pending":
        files = [f for f in files if ce.num(f.get("fileOutstanding")) > 0]
    elif view == "overdue":
        files = [f for f in files if ce.num(f.get("fileOutstanding")) > 0 and f.get("status") != "Closed"]
    return files


# ---------------------------------------------------------------- deliveries
@api.get("/deliveries")
async def list_deliveries():
    # active-booked leads that are not delivered = pending deliveries; plus delivered ones
    leads = await db.leads.find({"currentStatus": {"$in": ["Booked", "Finance Process", "Delivered"]}}).to_list(2000)
    result = []
    for l in leads:
        d = await db.deliveries.find_one({"leadId": l["leadId"]}) or {}
        result.append({
            "leadId": l["leadId"], "customerName": l.get("customerName"), "mobile": l.get("mobile"),
            "model": l.get("interestedModel"), "variant": l.get("variant"),
            "insurance": d.get("insurance", ""), "registration": d.get("registration", ""),
            "invoice": d.get("invoice", ""), "rc": d.get("rc", ""), "pdi": d.get("pdi", ""),
            "delivered": d.get("delivered", "") or ("Yes" if (l.get("deliveryStatus") or "").lower() == "delivered" else ""),
            "deliveryDate": d.get("deliveryDate") or l.get("deliveryDate"),
            "chassisNumber": d.get("chassisNumber", ""), "numberPlate": d.get("numberPlate", ""),
        })
    return result


@api.put("/leads/{lead_id}/delivery")
async def mark_delivery(lead_id: str, body: DeliveryIn):
    lead = await get_lead_or_404(lead_id)
    delivered = (body.delivered or "").lower() in ("yes", "true", "delivered", "1")
    if delivered and not _is_delivered(lead):
        _require_action(lead, "canDeliver", "delivery (not booked/active)")
    doc = {"leadId": lead_id, "customerName": lead.get("customerName"), **body.model_dump(),
           "deliveryId": f"DL{uuid.uuid4().hex[:8]}"}
    await db.deliveries.update_one({"leadId": lead_id}, {"$set": doc}, upsert=True)
    lead_updates = {
        "insuranceStatus": body.insurance, "registrationStatus": body.registration,
        "invoiceStatus": body.invoice, "rcStatus": body.rc, "pdiStatus": body.pdi,
        "invoiceNumber": body.invoiceNumber, "chassisNumber": body.chassisNumber,
        "numberPlate": body.numberPlate, "insurerName": body.insurerName, "lastUpdated": now_iso(),
    }
    if delivered:
        lead_updates.update({"deliveryStatus": "Delivered", "currentStatus": "Delivered",
                             "deliveryDate": body.deliveryDate or today()})
    await db.leads.update_one({"leadId": lead_id}, {"$set": lead_updates})
    if delivered:
        await gsheets.append("deliveries", {
            "leadId": lead_id, "customerName": lead.get("customerName"),
            "deliveryDate": body.deliveryDate or today(), "delivered": "Yes",
            "invoiceNumber": body.invoiceNumber, "chassisNumber": body.chassisNumber, "numberPlate": body.numberPlate,
        })
    return clean(await db.leads.find_one({"leadId": lead_id}))


# ---------------------------------------------------------------- price master
@api.get("/price-master")
async def list_price_master(model: Optional[str] = None):
    q = {"model": model} if model else {}
    return [clean(p) for p in await db.price_master.find(q).to_list(2000)]


@api.get("/price-master/variants")
async def price_variants(model: str):
    rows = await db.price_master.find({"model": model}).to_list(500)
    return [clean(r) for r in rows]


# ---------------------------------------------------------------- masters registers
@api.get("/scheme-master")
async def list_scheme_master():
    return [clean(s) for s in await db.scheme_master.find().to_list(1000)]


@api.get("/incentive-master")
async def list_incentive_master():
    return [clean(s) for s in await db.incentive_master.find().to_list(1000)]


@api.get("/bookings")
async def list_bookings():
    return [clean(b) for b in await db.bookings.find().sort("bookingId", -1).to_list(1000)]


@api.get("/activities")
async def list_activities(lead_id: Optional[str] = None):
    q = {"leadId": lead_id} if lead_id else {}
    return [clean(a) for a in await db.activities.find(q).sort("activityId", -1).to_list(2000)]


@api.post("/leads/{lead_id}/activities")
async def add_activity(lead_id: str, body: ActivityIn):
    lead = await get_lead_or_404(lead_id)
    doc = {
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": today(),
        "time": datetime.now(timezone.utc).strftime("%H:%M"), **body.model_dump(),
        "customerName": lead.get("customerName"), "mobile": lead.get("mobile"), "model": lead.get("interestedModel"),
    }
    await db.activities.insert_one(doc)
    return clean(doc)


@api.get("/insurance")
async def list_insurance(lead_id: Optional[str] = None):
    q = {"leadId": lead_id} if lead_id else {}
    return [clean(i) for i in await db.insurance.find(q).sort("entryId", -1).to_list(1000)]


class InsuranceIn(BaseModel):
    leadId: str = ""
    customerName: str
    mobile: str = ""
    model: str = ""
    variant: str = ""
    insuranceCompany: str = ""
    policyNumber: str = ""
    insuranceAmount: float = 0
    payoutRate: float = 0          # fraction, e.g. 0.15 for 15%
    receivedPayout: float = 0
    status: str = "Pending"
    policyDate: Optional[str] = None
    insuranceExecutive: str = ""
    remarks: str = ""


def _insurance_derive(body: dict):
    premium = ce.num(body.get("insuranceAmount"))
    rate = ce.num(body.get("payoutRate"))
    if rate > 1:  # allow entering 15 meaning 15%
        rate = rate / 100.0
    expected = ce.round2(premium * rate)
    received = ce.num(body.get("receivedPayout"))
    outstanding = ce.round2(max(0.0, expected - received))
    status = body.get("status") or "Pending"
    if expected > 0 and received >= expected:
        status = "Received"
    elif received > 0:
        status = "Partial"
    return {"payoutRate": rate, "expectedPayout": expected, "receivedPayout": received,
            "payoutOutstanding": outstanding, "status": status}


@api.post("/insurance")
async def create_insurance(body: InsuranceIn):
    data = body.model_dump()
    data.update(_insurance_derive(data))
    data["entryId"] = await next_id("insurance", "INS26")
    if data.get("leadId"):
        lead = await db.leads.find_one({"leadId": data["leadId"]})
        if lead:
            data["deliveryDate"] = lead.get("deliveryDate")
    await db.insurance.insert_one(data)
    return clean(data)


@api.put("/insurance/{entry_id}")
async def update_insurance(entry_id: str, body: InsuranceIn):
    data = body.model_dump()
    data.update(_insurance_derive(data))
    res = await db.insurance.update_one({"entryId": entry_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Insurance entry not found")
    return clean(await db.insurance.find_one({"entryId": entry_id}))


@api.delete("/insurance/{entry_id}")
async def delete_insurance(entry_id: str):
    await db.insurance.delete_one({"entryId": entry_id})
    return {"ok": True}


# ---------------------------------------------------------------- claims
@api.get("/claims")
async def list_claims():
    """Derive per-component OEM claims (COMPANY share from Scheme Master) from booked leads."""
    leads = await db.leads.find({"currentStatus": {"$regex": "book", "$options": "i"}}).to_list(2000)
    scheme_rows = await get_scheme_rows()
    result = []
    for l in leads:
        snap = lead_to_snapshot(l)
        shares = ce.compute_scheme_claim_shares(snap, scheme_rows)
        display = shares["displayByComponent"]
        eligible = shares["eligibleByComponent"]
        for key, company_share in display.items():
            if company_share <= 0:
                continue
            existing = await db.claims.find_one({"leadId": l["leadId"], "componentKey": key})
            elig = ce.round2(eligible.get(key, 0))
            result.append({
                "claimId": (existing or {}).get("claimId", f"CLM-{l['leadId']}-{key}"),
                "leadId": l["leadId"], "customer": l.get("customerName"),
                "model": l.get("interestedModel"), "variant": l.get("variant"),
                "bookingDate": l.get("bookingDate"),
                "component": ce.SCHEME_COMPONENT_LABELS.get(key, key),
                "componentKey": key, "claimAmount": ce.round2(company_share),
                "eligibleClaim": elig,
                "approvalStatus": "Approved" if elig >= company_share else "Pending",
                "claimStatus": (existing or {}).get("claimStatus", "Pending"),
                "receivedAmount": (existing or {}).get("receivedAmount", 0),
                "claimReference": (existing or {}).get("claimReference", ""),
            })
    return result


class ClaimSettleIn(BaseModel):
    leadId: str
    componentKey: str
    claimStatus: str = "Received"
    receivedAmount: float = 0
    claimReference: str = ""


@api.post("/claims/settle")
async def settle_claim(body: ClaimSettleIn):
    doc = {"claimId": f"CLM-{body.leadId}-{body.componentKey}", **body.model_dump()}
    await db.claims.update_one(
        {"leadId": body.leadId, "componentKey": body.componentKey},
        {"$set": doc}, upsert=True,
    )
    lead = await db.leads.find_one({"leadId": body.leadId}) or {}
    await gsheets.append("claims", {**doc, "customer": lead.get("customerName", ""),
                                    "model": lead.get("interestedModel", ""), "claimAmount": body.receivedAmount})
    return {"ok": True}


# ---------------------------------------------------------------- masters CRUD (editable)
class PriceRowIn(BaseModel):
    model: str
    variant: str
    bodyType: str = ""
    exShowroom: float = 0
    rto: float = 0
    insurance: float = 0
    accessories: float = 0
    handlingCharges: float = 0
    trc: float = 0
    fastag: float = 0
    extendedWarranty: float = 0
    otherCharges: float = 0
    gstPercent: float = 0
    tcsApplicable: str = "No"
    priceVersion: str = ""
    status: str = "active"
    remarks: str = ""


@api.post("/price-master")
async def create_price_row(body: PriceRowIn):
    count = await db.price_master.count_documents({})
    doc = {"priceId": f"PM{count + 1:04d}", **body.model_dump()}
    await db.price_master.insert_one(doc)
    return clean(doc)


@api.put("/price-master/{price_id}")
async def update_price_row(price_id: str, body: PriceRowIn):
    res = await db.price_master.update_one({"priceId": price_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Price row not found")
    return clean(await db.price_master.find_one({"priceId": price_id}))


@api.delete("/price-master/{price_id}")
async def delete_price_row(price_id: str):
    await db.price_master.delete_one({"priceId": price_id})
    return {"ok": True}


class SchemeRowIn(BaseModel):
    schemeMonth: Optional[str] = None
    effectiveFrom: Optional[str] = None
    effectiveTo: Optional[str] = None
    circularRef: str = ""
    model: str = ""
    variant: str = ""
    component: str = ""
    componentKey: str = ""
    dealerShare: float = 0
    companyShare: float = 0
    totalBenefit: float = 0
    status: str = "Active"
    notes: str = ""


@api.post("/scheme-master")
async def create_scheme_row(body: SchemeRowIn):
    count = await db.scheme_master.count_documents({})
    payload = body.model_dump()
    payload["totalBenefit"] = payload["totalBenefit"] or ce.round2(payload["dealerShare"] + payload["companyShare"])
    doc = {"schemeId": f"SCM{count + 1:04d}", **payload}
    await db.scheme_master.insert_one(doc)
    return clean(doc)


@api.put("/scheme-master/{scheme_id}")
async def update_scheme_row(scheme_id: str, body: SchemeRowIn):
    payload = body.model_dump()
    payload["totalBenefit"] = payload["totalBenefit"] or ce.round2(payload["dealerShare"] + payload["companyShare"])
    res = await db.scheme_master.update_one({"schemeId": scheme_id}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(404, "Scheme row not found")
    return clean(await db.scheme_master.find_one({"schemeId": scheme_id}))


@api.delete("/scheme-master/{scheme_id}")
async def delete_scheme_row(scheme_id: str):
    await db.scheme_master.delete_one({"schemeId": scheme_id})
    return {"ok": True}


# ---------------------------------------------------------------- dealer earnings (owner-only)
@api.get("/dealer-earnings", dependencies=[Depends(owner_only)])
async def list_dealer_earnings():
    rows = await db.dealer_earnings.find().to_list(1000)
    total = ce.round2(sum(ce.num(r.get("totalDealerEarnings")) for r in rows))
    return {"rows": [clean(r) for r in rows], "total": total}


# ---------------------------------------------------------------- integrations status
@api.get("/integrations/gsheets")
async def gsheets_status():
    return gsheets.status()


@api.post("/integrations/gsheets/backfill", dependencies=[Depends(owner_only)])
async def gsheets_backfill():
    leads = [clean(x) for x in await db.leads.find().to_list(5000)]
    payments = [clean(x) for x in await db.payments.find().to_list(5000)]
    bookings = [clean(x) for x in await db.bookings.find().to_list(5000)]
    delivered = [clean(x) for x in await db.leads.find({"deliveryStatus": "Delivered"}).to_list(5000)]
    deliveries = [{"leadId": l.get("leadId"), "customerName": l.get("customerName"),
                   "deliveryDate": l.get("deliveryDate"), "delivered": "Yes",
                   "invoiceNumber": l.get("invoiceNumber", ""), "chassisNumber": l.get("chassisNumber", ""),
                   "numberPlate": l.get("numberPlate", "")} for l in delivered]
    return await gsheets.backfill({"leads": leads, "bookings": bookings, "payments": payments, "deliveries": deliveries})


# ---------------------------------------------------------------- owner reports
@api.get("/reports/insurance-payout", dependencies=[Depends(owner_only)])
async def insurance_payout_report():
    entries = await db.insurance.find().to_list(5000)
    by_month = {}
    by_insurer = {}
    totals = {"premium": 0.0, "expected": 0.0, "received": 0.0, "outstanding": 0.0, "count": 0}
    for e in entries:
        month = str(e.get("policyDate") or e.get("deliveryDate") or "")[:7] or "Unknown"
        premium = ce.num(e.get("insuranceAmount"))
        expected = ce.num(e.get("expectedPayout"))
        received = ce.num(e.get("receivedPayout"))
        outstanding = ce.num(e.get("payoutOutstanding"))
        for bucket, key in ((by_month, month), (by_insurer, e.get("insuranceCompany") or "Unknown")):
            row = bucket.setdefault(key, {"key": key, "premium": 0.0, "expected": 0.0, "received": 0.0, "outstanding": 0.0, "count": 0})
            row["premium"] += premium; row["expected"] += expected
            row["received"] += received; row["outstanding"] += outstanding; row["count"] += 1
        totals["premium"] += premium; totals["expected"] += expected
        totals["received"] += received; totals["outstanding"] += outstanding; totals["count"] += 1

    def norm(bucket, sort_key=False):
        rows = [{**r, "premium": ce.round2(r["premium"]), "expected": ce.round2(r["expected"]),
                 "received": ce.round2(r["received"]), "outstanding": ce.round2(r["outstanding"])} for r in bucket.values()]
        return sorted(rows, key=lambda x: x["key"], reverse=True) if sort_key else sorted(rows, key=lambda x: -x["expected"])

    return {"byMonth": norm(by_month, True), "byInsurer": norm(by_insurer),
            "totals": {k: (ce.round2(v) if isinstance(v, float) else v) for k, v in totals.items()}}


@api.get("/reports/dealer-earnings", dependencies=[Depends(owner_only)])
async def dealer_earnings_report():
    """Live dealer earnings from booked leads: margin + scheme retained + insurance income + other."""
    leads = await db.leads.find({"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}}).to_list(5000)
    scheme_rows = await get_scheme_rows()
    # insurance income (dealer payout) per lead
    ins_by_lead = {}
    for e in await db.insurance.find().to_list(5000):
        lid = e.get("leadId")
        if lid:
            ins_by_lead[lid] = ce.round2(ins_by_lead.get(lid, 0) + ce.num(e.get("expectedPayout")))
    by_month = {}
    components = {"Dealer Margin": 0.0, "Scheme Retained": 0.0, "Insurance Income": 0.0}
    totals = {"margin": 0.0, "scheme": 0.0, "insurance": 0.0, "total": 0.0, "count": 0}
    for l in leads:
        snap = lead_to_snapshot(l)
        margin = ce.compute_dealer_margin(snap)["marginNetExGst"]
        income = ce.compute_scheme_income_breakdown(snap, scheme_rows)
        scheme = income["retainedIncomeTotal"]
        insurance = ins_by_lead.get(l.get("leadId"), 0)
        other = 0.0
        total = ce.round2(margin + scheme + insurance + other)
        month = str(l.get("deliveryDate") or l.get("bookingDate") or "")[:7] or "Unknown"
        m = by_month.setdefault(month, {"key": month, "margin": 0.0, "scheme": 0.0,
                                        "insurance": 0.0, "other": 0.0, "total": 0.0, "count": 0})
        m["margin"] += margin; m["scheme"] += scheme; m["insurance"] += insurance
        m["other"] += other; m["total"] += total; m["count"] += 1
        totals["margin"] += margin; totals["scheme"] += scheme
        totals["insurance"] += insurance; totals["total"] += total; totals["count"] += 1
        components["Dealer Margin"] += margin
        components["Scheme Retained"] += scheme
        components["Insurance Income"] += insurance

    months = sorted(by_month.values(), key=lambda x: x["key"], reverse=True)
    for m in months:
        for k in ("margin", "scheme", "insurance", "other", "total"):
            m[k] = ce.round2(m[k])
    return {
        "byMonth": months,
        "components": [{"label": lbl, "amount": ce.round2(amt)} for lbl, amt in components.items() if amt],
        "totals": {k: (ce.round2(v) if isinstance(v, float) else v) for k, v in totals.items()},
    }


# ---------------------------------------------------------------- excel export
@api.get("/export")
async def export_xlsx():
    import openpyxl
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    exports = {
        "Leads": ("leads", ["leadId", "customerName", "mobile", "interestedModel", "variant", "executive",
                            "currentStatus", "customerPayable", "totalReceived", "customerOutstanding", "bookingDate"]),
        "Payments": ("payments", ["receiptNumber", "leadId", "customerName", "date", "amount", "paymentMode",
                                  "runningTotal", "outstandingBalance"]),
        "Bookings": ("bookings", ["bookingId", "leadId", "customerName", "bookingDate", "model", "variant",
                                  "bookingAmount", "paymentMode", "bookingStatus"]),
        "Claims": ("claims", ["claimId", "leadId", "customer", "component", "claimAmount", "claimStatus", "receivedAmount"]),
        "Finance": ("finance", ["fileNumber", "leadId", "customerName", "financer", "sanctionedAmount",
                                "receivedAgainstFile", "fileOutstanding", "status"]),
        "Price Master": ("price_master", ["model", "variant", "bodyType", "exShowroom", "rto", "insurance", "tcsApplicable", "status"]),
    }
    for sheet_name, (coll, cols) in exports.items():
        ws = wb.create_sheet(sheet_name)
        ws.append(cols)
        for doc in await db[coll].find().to_list(5000):
            ws.append([doc.get(c, "") for c in cols])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    fname = f"euler_crm_export_{today()}.xlsx"
    return StreamingResponse(
        buf, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------------------------------------------------------------- public share board (no auth)
@public.get("/share/dashboard")
async def share_dashboard():
    leads = await db.leads.find().to_list(5000)
    ym = this_month()
    td = today()
    booked = [l for l in leads if "book" in (l.get("currentStatus") or "").lower()]
    active_booked = [l for l in booked if (l.get("deliveryStatus") or "").lower() != "delivered"]
    delivered = [l for l in leads if (l.get("deliveryStatus") or "").lower() == "delivered"]
    new_this_month = [l for l in booked if str(l.get("bookingDate") or "").startswith(ym)]
    retail_this_month = [l for l in delivered if str(l.get("deliveryDate") or "").startswith(ym)]
    today_bookings = [l for l in booked if str(l.get("bookingDate") or "") == td]

    by_model = {}
    for l in active_booked:
        m = l.get("interestedModel") or "Unknown"
        by_model[m] = by_model.get(m, 0) + 1

    def row(l, date_field):
        return {"date": l.get(date_field), "name": l.get("customerName") or "—",
                "model": l.get("interestedModel") or "", "variant": l.get("variant") or ""}

    recent_bookings = sorted(active_booked, key=lambda l: str(l.get("bookingDate") or ""), reverse=True)[:20]
    recent_retail = sorted(retail_this_month, key=lambda l: str(l.get("deliveryDate") or ""), reverse=True)[:20]
    all_leads = sorted(leads, key=lambda l: str(l.get("createdDate") or ""), reverse=True)
    all_leads_rows = [{"date": l.get("createdDate"), "name": l.get("customerName") or "—",
                       "model": l.get("interestedModel") or "", "variant": l.get("variant") or "",
                       "status": l.get("currentStatus") or "New"} for l in all_leads]

    return {
        "activeBookings": len(active_booked),
        "newThisMonth": len(new_this_month),
        "retailThisMonth": len(retail_this_month),
        "todayBookings": len(today_bookings),
        "totalLeads": len(leads),
        "recentBookings": [row(l, "bookingDate") for l in recent_bookings],
        "recentRetail": [row(l, "deliveryDate") for l in recent_retail],
        "allLeads": all_leads_rows,
        "byModel": [{"model": k, "count": v} for k, v in sorted(by_model.items(), key=lambda x: -x[1])],
        "month": datetime.now(timezone.utc).strftime("%B %Y"),
        "lastUpdated": now_iso(),
    }


# ---------------------------------------------------------------- commercial preview + quotation
@api.post("/commercial/compute")
async def commercial_compute(body: SnapshotComputeIn):
    return ce.compute_full_commercials(body.model_dump())


class QuotationIn(BaseModel):
    customerName: str = ""
    mobile: str = ""
    model: str = ""
    variant: str = ""
    exShowroom: float = 0
    insurance: float = 0
    registrationRto: float = 0
    accessories: float = 0
    handlingCharges: float = 0
    trc: float = 0
    fastag: float = 0
    extendedWarranty: float = 0
    otherCharges: float = 0
    consumerDiscount: float = 0
    exchangeBonus: float = 0
    loyaltyBonus: float = 0
    referralBonus: float = 0
    dsaDiscount: float = 0
    additionalDiscount: float = 0
    finalExchangeValue: float = 0
    financer: str = ""
    narration: str = ""


@api.get("/quotations")
async def list_quotations():
    return [clean(q) for q in await db.quotations.find().sort("quoteId", -1).to_list(1000)]


@api.post("/quotations")
async def create_quotation(body: QuotationIn):
    totals = ce.compute_commercial_totals(body.model_dump())
    claim = ce.derive_claim(body.model_dump())
    quote_id = await next_id("snapshot", "QT26")
    doc = {"quoteId": quote_id, "date": today(), **body.model_dump(),
           "grossVehicleCost": totals["grossVehicleCost"], "totalDiscount": totals["totalDiscount"],
           "customerPayable": totals["customerPayable"], "oemShare": claim["claimEligible"]}
    await db.quotations.insert_one(doc)
    return clean(doc)


# ---------------------------------------------------------------- startup
app.include_router(auth_router)
app.include_router(api)
app.include_router(public)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


@app.on_event("startup")
async def startup():
    await authmod.seed_users(db)
    res = await seeder.run_seed(db)
    if res.get("seeded"):
        for l in await db.leads.find().to_list(3000):
            await recompute_lead(l["leadId"])


@app.on_event("shutdown")
async def shutdown():
    client.close()
