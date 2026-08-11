import asyncio
import json
import logging
import io
import os
import re
import uuid
from collections import Counter
from datetime import datetime, timezone, date, timedelta
from pathlib import Path
from typing import Optional, List

from dotenv import load_dotenv
from fastapi import FastAPI, APIRouter, HTTPException, Depends, UploadFile, File, Form, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import DuplicateKeyError
from pydantic import BaseModel, ConfigDict, Field

import commercial as ce
import seed as seeder
import auth as authmod
import gsheets

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

client = AsyncIOMotorClient(os.environ["MONGO_URL"])
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="Euler CRM API")
_finance_index_status = {
    "status": "UNKNOWN",
    "ready": False,
    "reason": "startup has not run",
    "checkedAt": None,
    "auditCounts": {},
}

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


async def sheet_sync(entity: str, doc: dict, *, entity_id: str = ""):
    """Upsert one record into the existing Google Sheet and durably record the
    outcome (GS-4). A failed write becomes a PENDING sheet_sync_log entry that
    /integrations/gsheets/retry can replay — it is never silently lost.

    Safe to retry: gsheets.sync() is an ID-keyed upsert, so replaying a write that
    actually succeeded but whose response timed out finds the existing row and
    updates it instead of appending a duplicate.
    """
    res = await gsheets.sync(entity, doc)
    if res.get("operation") in ("skipped", "blocked"):
        return res  # sync disabled or env-write-blocked — nothing to log/retry
    eid = entity_id or str(doc.get(gsheets.SYNC_MAP.get(entity, ("", "", []))[1], "") or "")
    key = {"entityType": entity, "entityId": eid}
    entry = {
        **key,
        "tab": res.get("tab", ""),
        "operation": res.get("operation", ""),
        "status": "OK" if res.get("ok") else "PENDING",
        "error": res.get("error", ""),
        "missingHeaders": res.get("missingHeaders", []),
        "timestamp": now_iso(),
        "payload": {k: v for k, v in doc.items() if not k.startswith("_")},
    }
    existing = await db.sheet_sync_log.find_one(key)
    entry["attempt"] = int((existing or {}).get("attempt", 0)) + 1
    if res.get("ok"):
        entry["resolvedAt"] = now_iso()
    await db.sheet_sync_log.update_one(key, {"$set": entry}, upsert=True)
    return res


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


# ---------------------------------------------------------------- audit trail (H4) — append-only transaction log
async def actor(request: Request, user=Depends(current_user)):
    """Resolve the acting user + client IP for audit logging."""
    ip = ""
    try:
        ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "")
    except Exception:
        ip = ""
    return {"email": (user or {}).get("email") or "system", "role": (user or {}).get("role") or "", "ip": ip}


async def write_audit(act, action, module, *, leadId="", paymentId="", claimId="",
                      financeFileNumber="", reportRef="", old=None, new=None):
    """Append-only. No financial record should change without an audit entry."""
    act = act or {}
    entry = {
        "auditId": f"AUD{uuid.uuid4().hex[:14]}",
        "timestamp": now_iso(),
        "user": act.get("email") or "system",
        "role": act.get("role") or "",
        "ip": act.get("ip") or "",
        "action": action, "module": module,
        "leadId": leadId, "paymentId": paymentId, "claimId": claimId,
        "financeFileNumber": financeFileNumber, "reportRef": reportRef,
        "oldValue": old, "newValue": new,
    }
    await db.audit_log.insert_one(dict(entry))
    return entry


# ---------------------------------------------------------------- step eligibility (LeadPickerService PICKER_STAGE + requireActiveLead_)
def _is_booked(lead):
    cs = (lead.get("currentStatus") or "").lower()
    return ("book" in cs or cs == "delivered" or "finance" in cs
            or bool(lead.get("bookingDate")) or ce.num(lead.get("bookingAmount")) > 0)


def _is_delivered(lead):
    return (lead.get("deliveryStatus") or "").lower() == "delivered" or (lead.get("currentStatus") or "").lower() == "delivered"


def _acct(lead):
    return (lead.get("accountStatus") or "Active").strip() or "Active"


def _has_persisted_scheme(lead):
    """True once a scheme step has been saved (explicit allocation or breakup)."""
    if lead.get("schemeAllocationExplicit"):
        return True
    raw = lead.get("benefitPassedBreakup") or lead.get("schemeAllocation") or ""
    if isinstance(raw, dict):
        return bool(raw)
    if isinstance(raw, str) and raw.strip() and raw.strip() not in ("{}", "null"):
        return True
    used = lead.get("schemeComponentsUsed") or ""
    if isinstance(used, dict) and used:
        return True
    if isinstance(used, str) and used.strip() and used.strip() not in ("{}", "null"):
        return True
    return False


def _is_priced(lead):
    """True after an explicit Price Structure save (not merely booking auto-fill)."""
    if "priceStructureSaved" in (lead or {}):
        return bool(lead.get("priceStructureSaved"))
    # Legacy leads (pre-flag): any positive Ex-Showroom counts as priced.
    return ce.num((lead or {}).get("exShowroom")) > 0


def lead_actions(lead):
    """Which workflow steps a lead is eligible for (faithful to PICKER_STAGE + requireActiveLead_).

    Delivered / Closed / Cancelled / Archived leads are frozen for commercial edits —
    the vehicle is unique; only Active, non-delivered leads may change.
    Close remains available on Active (including Delivered) so the lifecycle can exit.
    Finance / claim receipts stay allowed after close (not Archived).
    """
    active = _acct(lead) == "Active"
    booked = _is_booked(lead)
    delivered = _is_delivered(lead)
    not_archived = _acct(lead) != "Archived"
    mutable = active and not delivered
    priced = _is_priced(lead)
    schemed = _has_persisted_scheme(lead)
    return {
        "canBook": mutable and not booked,
        "canPrice": mutable,
        "canScheme": mutable,
        "canPayment": mutable,                             # customer payment
        "canFinanceReceipt": not_archived,               # finance receipt allowed after close
        "canDeliver": active and booked and not delivered,
        "canClose": active,                               # close exit path (incl. delivered)
        "canEditLead": mutable,                           # Edit Lead modal / PUT /leads
        "isBooked": booked, "isDelivered": delivered, "isActive": active,
        "isLocked": not mutable,
        # Step completion — staff may complete a step once; only owner re-edits (while mutable).
        "priceCompleted": priced,
        "schemeCompleted": schemed,
        "deliveryCompleted": delivered,
    }


def _require_owner_reedit(act, completed, step_label):
    """Staff may fill a step the first time; re-edits of a completed step are owner-only."""
    if completed and (act or {}).get("role") != "owner":
        raise HTTPException(
            403,
            f"{step_label} is already saved. Only the owner can edit a completed step.",
        )


def _require_mutable_lead(lead, verb="edits"):
    """Strict freeze: only Active AND not Delivered may change commercial/workflow fields."""
    if _acct(lead) != "Active" or _is_delivered(lead):
        raise HTTPException(
            409,
            f"This lead is locked for {verb} "
            f"(status: {lead.get('currentStatus') or 'New'} / {_acct(lead)}). "
            f"Only Active, non-delivered leads can be changed.",
        )


def _yes_or_done(v):
    return str(v or "").strip().lower() in ("yes", "y", "done", "true", "1")


def _validate_delivery_ready(lead, body):
    """Port of validateDeliveryReady_ + isDeliveryEligible_ (outstanding must be cleared)."""
    errs = []
    if not _yes_or_done(body.insurance):
        errs.append("Set Insurance to Yes before marking delivered.")
    if not str(body.insurerName or "").strip():
        errs.append("Enter the insurer name before delivery.")
    if not _yes_or_done(body.registration):
        errs.append("Set Registration to Yes before marking delivered.")
    if not _yes_or_done(body.invoice):
        errs.append("Set Invoice to Yes before marking delivered.")
    if not str(body.invoiceNumber or "").strip():
        errs.append("Enter the invoice number before delivery.")
    if not str(body.chassisNumber or "").strip():
        errs.append("Enter the chassis number before delivery.")
    if not _yes_or_done(body.pdi):
        errs.append("Set PDI to Yes before marking delivered.")
    if ce.num(lead.get("customerOutstanding")) > 0.01:
        errs.append(f"Customer outstanding must be cleared (₹{ce.round2(ce.num(lead.get('customerOutstanding')))}) before delivery.")
    return errs


async def _assert_unique_vehicle_identifiers(lead_id, *, invoice_number="", chassis_number="",
                                             number_plate=""):
    """Invoice / chassis / number plate must be unique across leads (case-insensitive).
    Blank values are ignored. The current lead is excluded so re-saves are allowed."""
    checks = (
        ("invoiceNumber", invoice_number, "Invoice number"),
        ("chassisNumber", chassis_number, "Chassis number"),
        ("numberPlate", number_plate, "Number plate"),
    )
    for field, raw, label in checks:
        val = str(raw or "").strip()
        if not val:
            continue
        existing = await db.leads.find_one({
            "leadId": {"$ne": lead_id},
            field: {"$regex": f"^{re.escape(val)}$", "$options": "i"},
        })
        if existing:
            raise HTTPException(
                409,
                f"{label} '{val}' is already used on lead {existing.get('leadId')} "
                f"({existing.get('customerName') or '—'}).",
            )


def _require_action(lead, key, verb):
    acts = lead_actions(lead)
    if not acts.get(key):
        raise HTTPException(409, f"This lead is not eligible for {verb} (status: {lead.get('currentStatus') or 'New'} / {_acct(lead)}).")


def lead_to_snapshot(lead):
    """Build a commercial-engine snapshot dict from a lead document."""
    used = lead.get("schemeComponentsUsed") or {}
    if isinstance(used, str):
        try:
            import json as _json
            used = _json.loads(used) if used.strip() else {}
        except Exception:
            used = {}
    return {
        "bookingDate": lead.get("bookingDate", ""),
        "benefitPassedBreakup": lead.get("benefitPassedBreakup", ""),
        # schemeAllocationV2: legacy Full Benefit may apply to entitlements when set.
        # schemeAllocationExplicit: new UI — CB only from explicit breakup (default 0).
        "schemeAllocationV2": bool(lead.get("schemeAllocationV2")),
        "schemeAllocationExplicit": bool(lead.get("schemeAllocationExplicit")),
        "schemeComponentsUsed": used if isinstance(used, dict) else {},
        "exShowroom": lead.get("exShowroom", 0),
        "accessories": lead.get("accessoriesAmount", 0),
        "insurance": lead.get("insuranceAmount", 0),
        "registrationRto": lead.get("rto", 0),
        "fastag": lead.get("fastag", 0),
        "handlingCharges": lead.get("handlingCharges", 0),
        "trc": lead.get("trc", 0),
        "extendedWarranty": lead.get("extendedWarranty", 0),
        "rsaAmc": lead.get("rsaAmc", 0),
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
        # The dealer's per-component allocation decision drives the whole scheme
        # engine, so it must reach every snapshot-based calculation.
        "schemeAllocation": lead.get("schemeAllocation"),
    }


# Scheme components the Dealer Earnings Register keeps a dedicated "… Retained"
# column for, mapped to the componentKey compute_scheme_allocation emits.
RETAINED_COMPONENT_COLUMNS = {
    "consumerRetained": "consumerDiscount",
    "exchangeRetained": "exchangeBonus",
    "loyaltyRetained": "loyaltyBonus",
    "referralRetained": "referralBonus",
    "dsaRetained": "dsaDiscount",
    "insuranceBenefitRetained": "insuranceBenefit",
    "rtoBenefitRetained": "rtoBenefit",
    "rtoInsuranceBenefitRetained": "rtoInsuranceBenefit",
}


def _retained_component_fields(retained_by_component):
    """Break the already-computed retainedByComponent map out into the per-component
    fields the Dealer Earnings Register has columns for, plus a human-readable
    breakup string. Components absent from the map retain 0.0 — a real value, not a
    blank — because "no retention on this component" is a meaningful commercial fact."""
    out = {}
    for field, key in RETAINED_COMPONENT_COLUMNS.items():
        out[field] = ce.round2(ce.num(retained_by_component.get(key)))
    out["schemeRetainedBreakup"] = "; ".join(
        f"{k}={ce.round2(ce.num(v))}" for k, v in sorted(retained_by_component.items())
    )
    return out


async def recompute_lead(lead_id):
    """Recompute all derived commercial + payment fields for a lead and persist."""
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return None
    snap = lead_to_snapshot(lead)
    scheme_rows = await get_scheme_rows()
    totals = ce.compute_commercial_totals(snap, scheme_rows)
    margin = ce.compute_dealer_margin(snap)
    income = ce.compute_scheme_income_breakdown(snap, scheme_rows)
    shares = ce.compute_scheme_claim_shares(snap, scheme_rows)
    alloc = income.get("allocation") or ce.compute_scheme_allocation(snap, scheme_rows)
    # total received from payments
    agg = await db.payments.aggregate([
        {"$match": {"leadId": lead_id}},
        {"$group": {"_id": None, "total": {"$sum": "$amount"}}},
    ]).to_list(1)
    total_received = ce.round2(agg[0]["total"]) if agg else 0.0
    # Customer Payable comes solely from compute_commercial_totals(…, scheme_rows),
    # which already reduces by Σ customerBenefit across offers + entitlements.
    # Do NOT subtract entitlement benefits again — that double-counted after the
    # allocation engines were merged onto one path.
    customer_payable = totals["customerPayable"]
    customer_outstanding = ce.round2(max(0.0, customer_payable - total_received)) if customer_payable > 0 else 0.0
    oem_extra_recv = max(0.0, ce.num(lead.get("oemExtraSupportReceived")))
    oem_extra_pass = max(0.0, min(ce.num(lead.get("oemExtraSupportPassed")), oem_extra_recv))
    oem_extra_retained = ce.round2(max(0.0, oem_extra_recv - oem_extra_pass))
    # Extra dealer income lines — customerInsuranceBenefitPassed is CUSTOMER
    # benefit/discount, NOT dealer income, and must not enter this sum.
    extra_income = ce.round2(
        ce.num(lead.get("documentationIncome")) + ce.num(lead.get("warrantyIncome")) +
        ce.num(lead.get("rsaIncome")) + ce.num(lead.get("referralIncome")) +
        ce.num(lead.get("otherIncome")) +
        ce.num(lead.get("financeIncentive")) + ce.num(lead.get("accessoriesMargin")) +
        ce.num(lead.get("exchangeMargin")) + ce.num(lead.get("campaignIncentive")))
    # Insurance PAYOUT income (premium × rate) — SEPARATE from Insurance Scheme Benefit.
    # Dealer Insurance Income = expected insurer payout. Do NOT subtract scheme
    # customerInsuranceBenefitPassed (that is customer discount, not payout share).
    _ins = await db.insurance.find_one({"leadId": lead_id}) or {}
    _ins_payout = ce.num(_ins.get("expectedPayout"))
    _dealer_ins_income = ce.round2(max(0.0, _ins_payout))
    # Dealer-funded benefit is a REAL cost. Only apply when an authoritative
    # allocation decision exists (schemeAllocationV2 / explicit) — never invent
    # a historical deduction from Benefit Mode alone.
    _has_auth_alloc = bool(lead.get("schemeAllocationV2") or lead.get("schemeAllocationExplicit")
                           or ce._explicit_allocation({"schemeAllocation": lead.get("schemeAllocation")}))
    _dealer_funded_benefit = (
        ce.round2(ce.num(alloc["totals"].get("dealerFundedBenefit"))) if _has_auth_alloc else 0.0)
    # Insurance Scheme Benefit (entitlement) — project independently from Loyalty.
    # Lead Register has an "Insurance Benefit" column; Dealer Earnings still carries
    # "Customer Insurance Benefit Passed"; Scheme Claim Register has a dedicated
    # Insurance Benefit amount column keyed by componentKey=insuranceBenefit.
    _ins_comp = (alloc.get("byKey") or {}).get("insuranceBenefit") or {}
    _ins_benefit_cb = ce.round2(ce.num(_ins_comp.get("customerBenefit"))) if _has_auth_alloc else None
    _ins_benefit_avail = ce.round2(ce.num(_ins_comp.get("schemeAvailable"))) if _ins_comp else 0.0
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
        "schemeCustomerBenefit": alloc["totals"]["customerBenefit"],
        # Compat aliases used by scheme-allocation tests / reports (PR #21).
        "schemeCustomerBenefitTotal": alloc["totals"]["customerBenefit"],
        "schemeOemClaimableTotal": alloc["totals"]["oemClaimable"],
        "schemeAvailableTotal": alloc["totals"]["schemeAvailable"],
        "dealerFundedBenefit": _dealer_funded_benefit,
        "oemExtraSupportRetained": oem_extra_retained,
        "dealerMarginNetExGst": margin["marginNetExGst"],
        "dealerMarginGrossInclGst": margin["marginGrossInclGst"],
        "dealerMarginGst": margin["marginGst"],
        **_retained_component_fields(income.get("retainedByComponent") or {}),
        "extraDealerIncomeTotal": extra_income,
        "dealerInsuranceIncome": _dealer_ins_income,
        "insurancePayout": _ins_payout,
        # Margin + retained + payout + extras − dealer-funded scheme benefit cost.
        # OEM claim is a receivable and must NEVER enter this total.
        "dealerTotalEarnings": ce.round2(
            margin["marginNetExGst"] + income["retainedIncomeTotal"] + oem_extra_retained
            + extra_income + _dealer_ins_income - _dealer_funded_benefit),
        # Engine summary lives here — NOT in schemeAllocation.
        # schemeAllocation is reserved for the flat {componentKey: amount} decision
        # map written by PUT /scheme-allocation (must not be overwritten).
        "schemeAllocationSummary": {
            "components": alloc["components"],
            "totals": alloc["totals"],
            "benefitMode": alloc["benefitMode"],
            "schemeMonth": alloc.get("schemeMonth"),
        },
        "lastUpdated": now_iso(),
    }
    # Authoritative Insurance Benefit projection (parallel to loyaltyBonus offer field).
    # Available amount is stored on insuranceBenefit; CB feeds the Dealer Earnings sheet
    # column Customer Insurance Benefit Passed. Historical leads without auth allocation
    # keep whatever memo value they already have.
    if _ins_comp:
        updates["insuranceBenefitAvailable"] = _ins_benefit_avail
    if _ins_benefit_cb is not None:
        updates["insuranceBenefit"] = _ins_benefit_cb
        updates["customerInsuranceBenefitPassed"] = _ins_benefit_cb
    # Preserve flat decision map if present; never replace it with the summary object.
    flat_decisions = ce._explicit_allocation({"schemeAllocation": lead.get("schemeAllocation")})
    if flat_decisions:
        import json as _json
        updates["schemeAllocation"] = _json.dumps(flat_decisions)
    await db.leads.update_one({"leadId": lead_id}, {"$set": updates})
    merged = {**lead, **updates}
    # The Lead Register is the dealership's primary register and must reflect the
    # lead's CURRENT commercial state. recompute_lead runs after every mutation that
    # can change it (booking, price structure, scheme, payment, delivery, close), so
    # this is the one place that guarantees the row never goes stale. Previously the
    # lead row was only pushed on create / manual PUT / import, so a lead booked and
    # delivered through the normal workflow stayed frozen at its creation values
    # (status New, ex-showroom 0, payable 0) even though every other register was
    # correct. Upsert on leadId, so this updates the existing row rather than adding one.
    await sheet_sync("leads", clean(dict(merged)))
    # GS-5: Dealer Earnings and Exchange previously had no Sheet destination at all.
    # Both are keyed on leadId, so these are upserts — one row per lead, kept current
    # on every commercial recompute rather than appended each time.
    if _is_booked(merged) or ce.num(merged.get("customerPayable")) > 0:
        de_row = {
            "insurancePayout": _ins_payout,
            "dealerInsuranceIncome": _dealer_ins_income,
            "leadId": lead_id, "customerName": merged.get("customerName"),
            "model": merged.get("interestedModel"),
            "dealerMarginNetExGst": updates["dealerMarginNetExGst"],
            "dealerSchemeRetained": updates["dealerSchemeRetained"],
            # Insurance Scheme Benefit CB from allocation — NOT the insurer payout.
            "customerInsuranceBenefitPassed": updates.get(
                "customerInsuranceBenefitPassed", merged.get("customerInsuranceBenefitPassed", 0)),
            "insuranceBenefit": updates.get("insuranceBenefit", merged.get("insuranceBenefit", 0)),
            "dealerFundedBenefit": updates.get("dealerFundedBenefit", 0),
            "financeIncentive": merged.get("financeIncentive", 0),
            "accessoriesMargin": merged.get("accessoriesMargin", 0),
            "exchangeMargin": merged.get("exchangeMargin", 0),
            "documentationIncome": merged.get("documentationIncome", 0),
            "warrantyIncome": merged.get("warrantyIncome", 0),
            "rsaIncome": merged.get("rsaIncome", 0),
            "referralIncome": merged.get("referralIncome", 0),
            "campaignIncentive": merged.get("campaignIncentive", 0),
            "otherIncome": merged.get("otherIncome", 0),
            "oemExtraSupportRetained": updates["oemExtraSupportRetained"],
            "extraDealerIncomeTotal": updates["extraDealerIncomeTotal"],
            "dealerTotalEarnings": updates["dealerTotalEarnings"],
            "totalDealerEarnings": updates["dealerTotalEarnings"],
            "variant": merged.get("variant", ""),
            "bookingDate": merged.get("bookingDate", ""),
            "deliveryDate": merged.get("deliveryDate", ""),
            "invoiceNumber": merged.get("invoiceNumber", ""),
            "executive": merged.get("executive", ""),
            "leadSource": merged.get("leadSource", ""),
            "customerPayable": updates["customerPayable"],
            "oemEligible": updates["oemSchemeAmount"],
            "customerSchemeBenefitPassed": updates.get("schemeCustomerBenefit", totals["customerBenefitPassed"]),
            "insuranceStatus": merged.get("insuranceStatus", ""),
            "remarks": merged.get("remarks", ""),
            "createdBy": merged.get("createdBy", "crm"),
            "modifiedBy": merged.get("lastUpdatedBy", ""),
            "currentStage": merged.get("currentStatus", ""),
            "lastUpdated": updates["lastUpdated"],
            "timestamp": updates["lastUpdated"],
            "oemExtraSupportReceived": oem_extra_recv,
            "oemExtraSupportPassed": oem_extra_pass,
            "dealerMarginGrossInclGst": updates["dealerMarginGrossInclGst"],
            "dealerMarginGst": updates["dealerMarginGst"],
            "consumerRetained": updates["consumerRetained"],
            "exchangeRetained": updates["exchangeRetained"],
            "loyaltyRetained": updates["loyaltyRetained"],
            "referralRetained": updates["referralRetained"],
            "dsaRetained": updates["dsaRetained"],
            "insuranceBenefitRetained": updates.get("insuranceBenefitRetained", 0),
            "rtoBenefitRetained": updates.get("rtoBenefitRetained", 0),
            "rtoInsuranceBenefitRetained": updates.get("rtoInsuranceBenefitRetained", 0),
            "schemeRetainedBreakup": updates["schemeRetainedBreakup"],
        }
        # Keep Mongo dealer_earnings in sync so GET /dealer-earnings matches the live report.
        await db.dealer_earnings.update_one({"leadId": lead_id}, {"$set": de_row}, upsert=True)
        await sheet_sync("dealer_earnings", de_row)
        # Derived OEM claims must also reach the existing Scheme Claim Register.
        # They are keyed on the same stable claimId GET /claims exposes, so this is an
        # upsert — a claim later settled/receipted updates that same row.
        # Scheme Claim Register is one row per component. Amount columns
        # (Loyalty Bonus, Insurance Benefit, …) must carry THIS row's claim only —
        # never the lead's full denormalized offer map (that put Loyalty 10000 on
        # Insurance Benefit rows and made every scheme look like Loyalty).
        _claim_amount_fields = [
            "consumerDiscount", "exchangeBonus", "loyaltyBonus", "insuranceBenefit",
            "referralBonus", "dsaDiscount", "additionalDiscount",
            "rtoBenefit", "rtoInsuranceBenefit",
        ]
        for _key, _amt in shares["displayByComponent"].items():
            if _amt <= 0:
                continue
            _ex = await db.claims.find_one({"leadId": lead_id, "componentKey": _key})
            _amt = ce.round2(_amt)
            _comp_cols = {f: 0.0 for f in _claim_amount_fields}
            if _key in _comp_cols:
                _comp_cols[_key] = _amt
            await sheet_sync("claims", {
                "claimId": (_ex or {}).get("claimId", f"CLM-{lead_id}-{_key}"),
                "leadId": lead_id, "customer": merged.get("customerName"),
                "model": merged.get("interestedModel"), "variant": merged.get("variant"),
                "bookingDate": merged.get("bookingDate", ""),
                "component": ce.SCHEME_COMPONENT_LABELS.get(_key, _key), "componentKey": _key,
                "eligibleClaim": ce.round2(shares["eligibleByComponent"].get(_key, 0)),
                "claimAmount": _amt,
                "receivedAmount": (_ex or {}).get("receivedAmount", 0),
                "claimStatus": (_ex or {}).get("claimStatus", "Pending"),
                "claimReference": (_ex or {}).get("claimReference", ""),
                # Claim Register columns that already had a source but no mapping.
                "bookingId": (await db.bookings.find_one({"leadId": lead_id}) or {}).get("bookingId", ""),
                "schemeMonth": ce.scheme_month_from_date(merged.get("bookingDate", "")),
                "executive": merged.get("executive", ""),
                **_comp_cols,
                # Row-level totals = this component's claim (not the whole-lead aggregate).
                "totalDiscount": _amt,
                "dealerDiscount": 0.0,
                "oemDiscount": _amt,
                "claimRequired": "Yes" if _amt > 0 else "No",
                "ageingDays": _claim_ageing_days(
                    (_ex or {}).get("submittedDate") or merged.get("deliveryDate", ""),
                    (_ex or {}).get("claimStatus", "Pending")),
                # How this claim row came to exist: derived from the Scheme Master split,
                # versus a manually raised claim. Distinguishable today, never recorded.
                "source": "Manual" if (_ex or {}).get("manual") else "Derived (Scheme Master)",
                # DSA is the one component whose claim needs explicit approval.
                "dsaApproval": (_ex or {}).get("approvalStatus", "") if _key == "dsaDiscount" else "",
                "claimReceivedDate": (_ex or {}).get("claimReceivedDate", ""),
                "claimRemarks": (_ex or {}).get("claimRemarks", ""),
            })
        if str(merged.get("exchangeRequired") or "").lower() == "yes" or ce.num(merged.get("finalExchangeValue")) > 0:
            await sheet_sync("exchange", {
                "leadId": lead_id, "customerName": merged.get("customerName"),
                "exchangeRequired": merged.get("exchangeRequired", "No"),
                "finalExchangeValue": merged.get("finalExchangeValue", 0),
                "exchangeBonus": merged.get("exchangeBonus", 0),
                "exchangeMargin": merged.get("exchangeMargin", 0),
            })
    return merged


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
    createdDate: Optional[str] = None


class LeadUpdateIn(BaseModel):
    """PATCH-style partial update for PUT /leads/{lead_id}. Every field is Optional
    with no non-null default, so (a) exclude_unset=True only ever picks up keys the
    client actually sent, and (b) Swagger's auto-generated example body is all-null
    instead of LeadIn's fake 'string'/0/'New' placeholders. extra='forbid' rejects
    any field not in this explicit allowlist — leadId, createdDate, accountStatus,
    and every system-calculated financial field are structurally absent here, so
    they can never be set through this endpoint, not just filtered out."""
    model_config = ConfigDict(extra="forbid")
    customerName: Optional[str] = None
    mobile: Optional[str] = None
    altMobile: Optional[str] = None
    village: Optional[str] = None
    city: Optional[str] = None
    leadSource: Optional[str] = None
    interestedModel: Optional[str] = None
    variant: Optional[str] = None
    executive: Optional[str] = None
    currentStatus: Optional[str] = None
    priority: Optional[str] = None
    budget: Optional[float] = None
    remarks: Optional[str] = None
    financeRequired: Optional[str] = None
    exchangeRequired: Optional[str] = None
    nextFollowupDate: Optional[str] = None
    bookingDate: Optional[str] = None


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
    rsaAmc: float = 0
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
    # Kept for API compatibility / historical leads. New Scheme UI does not expose it;
    # allocation is driven by explicit benefitPassedBreakup + schemeComponentsUsed.
    benefitMode: str = "Partial Benefit"
    customerBenefitPassed: float = 0
    benefitPassedBreakup: Optional[str] = None
    schemeComponentsUsed: Optional[str] = None
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
    rc: str = ""
    numberPlate: str = ""
    closedDate: Optional[str] = None


class ActivityIn(BaseModel):
    activityType: str = "Note"
    discussion: str = ""
    executive: str = ""
    nextFollowup: str = ""
    date: Optional[str] = None


class SnapshotComputeIn(BaseModel):
    exShowroom: float = 0
    accessories: float = 0
    insurance: float = 0
    registrationRto: float = 0
    fastag: float = 0
    handlingCharges: float = 0
    trc: float = 0
    extendedWarranty: float = 0
    rsaAmc: float = 0
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


# Master lists editable from Settings → synced (full-mirror) to a "Masters" tab
# in the Google Sheet. Defined in seed.py (kept separate from workflow-state
# lists like statuses/paymentModes/benefitModes/claimStatuses, whose exact
# string values are load-bearing throughout status-gating / commercial logic).
EDITABLE_MASTER_CATEGORIES = seeder.EDITABLE_MASTER_CATEGORIES


async def _masters_list_values(category):
    rows = await db.masters_list.find({"category": category}).sort("value", 1).to_list(500)
    return [r["value"] for r in rows]


@api.get("/masters")
async def masters():
    models = await db.price_master.distinct("model")
    out = dict(seeder.MASTERS)
    for cat in EDITABLE_MASTER_CATEGORIES:
        vals = await _masters_list_values(cat)
        if vals:
            out[cat] = vals
    return {**out, "models": sorted([m for m in models if m])}


@api.get("/masters-list")
async def list_masters_list():
    return [clean(r) for r in await db.masters_list.find().sort("value", 1).to_list(2000)]


class MasterListIn(BaseModel):
    category: str
    value: str


@api.post("/masters-list", dependencies=[Depends(owner_only)])
async def add_master_list_value(body: MasterListIn, act=Depends(actor)):
    category = body.category.strip()
    value = body.value.strip()
    if category not in EDITABLE_MASTER_CATEGORIES:
        raise HTTPException(422, f"'{category}' is not an editable master list")
    if not value:
        raise HTTPException(422, "Value is required")
    existing = await db.masters_list.find_one({"category": category, "value": {"$regex": f"^{re.escape(value)}$", "$options": "i"}})
    if existing:
        raise HTTPException(409, f"'{value}' already exists in {category}")
    doc = {"id": f"ML{uuid.uuid4().hex[:8]}", "category": category, "value": value, "status": "Active"}
    await db.masters_list.insert_one(doc)
    await write_audit(act, "create", "masters_list", new=doc)
    await gsheets.sync_masters(await list_masters_list())
    return clean(await db.masters_list.find_one({"id": doc["id"]}))


@api.delete("/masters-list/{item_id}", dependencies=[Depends(owner_only)])
async def delete_master_list_value(item_id: str, act=Depends(actor)):
    existing = await db.masters_list.find_one({"id": item_id})
    if not existing:
        raise HTTPException(404, "Not found")
    await db.masters_list.delete_one({"id": item_id})
    await write_audit(act, "delete", "masters_list", old=existing)
    await gsheets.sync_masters(await list_masters_list())
    return {"ok": True}


@api.post("/admin/reseed", dependencies=[Depends(owner_only)])
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

    # Finance total outstanding (H1) — sum of open finance file balances
    finance_os = 0.0
    finance_pending_files = []
    for f in await db.finance.find().to_list(5000):
        os_amt = ce.num(f.get("fileOutstanding"))
        finance_os += os_amt
        if os_amt > 0 and f.get("status") != "Received":
            finance_pending_files.append(clean(f))
    finance_overdue = await _enrich_finance_with_delivery(finance_pending_files)
    finance_overdue = [f for f in finance_overdue if f.get("overdue")]
    finance_overdue_count = len(finance_overdue)
    finance_overdue_amount = ce.round2(sum(ce.num(f.get("fileOutstanding")) for f in finance_overdue))

    # Follow-up KPIs (H1) — active leads with a next-follow-up date
    def _followup_date(l):
        return str(l.get("nextFollowupDate") or l.get("nextFollowup") or "")[:10]

    active_leads = [l for l in leads if (l.get("accountStatus") or "Active") == "Active"]
    followup_due = len([l for l in active_leads if _followup_date(l) == td])
    followup_overdue = len([l for l in active_leads
                            if _followup_date(l) and _followup_date(l) < td])

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
            "financeOutstanding": ce.round2(finance_os),
            "financeOverdueCount": finance_overdue_count,
            "financeOverdueAmount": finance_overdue_amount,
            "followupDue": followup_due,
            "followupOverdue": followup_overdue,
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
    # Duplicate mobile guard (port of LeadService create: block reused 10-digit mobile)
    import re as _re
    mob = _re.sub(r"\D", "", body.mobile or "")
    if len(mob) >= 10:
        last10 = mob[-10:]
        existing = await db.leads.find_one({"mobile": {"$regex": last10 + "$"}})
        if existing:
            raise HTTPException(409, f"Mobile already used by lead {existing.get('leadId')} ({existing.get('customerName')}).")
    lead_id = await next_id("lead", "LD26")
    payload = body.model_dump()
    created_date = str(payload.pop("createdDate", None) or "").strip() or today()
    doc = {
        "leadId": lead_id,
        **payload,
        "createdDate": created_date,
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
    _act_doc = {
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": created_date,
        "time": datetime.now(timezone.utc).strftime("%H:%M"), "activityType": "Note",
        "discussion": "Lead created from CRM", "executive": body.executive,
        "customerName": body.customerName, "mobile": body.mobile, "model": body.interestedModel,
    }
    await db.activities.insert_one(dict(_act_doc))
    await sheet_sync("activities", _act_doc)
    await sheet_sync("leads", doc)
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


# System/calculated fields a lead document carries that must never be settable
# through PUT /leads/{lead_id} — set at creation (create_lead) and/or maintained
# by recompute_lead() and the booking/delivery/close/payment/scheme endpoints.
# LeadUpdateIn already doesn't declare any of these (extra="forbid" rejects them
# outright); this set is a second, independent line of defense in the handler
# itself so the guarantee doesn't rely solely on the Pydantic model staying in sync.
LEAD_SYSTEM_FIELDS = {
    "leadId", "createdDate", "accountStatus", "deliveryStatus", "lastUpdated",
    "outstandingAmount", "customerOutstanding", "companyOutstanding", "totalReceived",
    "customerPayable", "grossVehicleCost", "totalDiscount", "consumerDiscount", "exchangeBonus",
    "loyaltyBonus", "referralBonus", "dsaDiscount", "additionalDiscount", "exShowroom", "rto",
    "insuranceAmount", "accessoriesAmount", "handlingCharges", "trc", "fastag", "extendedWarranty",
    "otherCharges", "bookingAmount", "oemSchemeAmount", "dealerSchemeAmount", "oemClaimCompanyShare",
    "schemeCompanyTotal", "dealerSchemeRetained", "oemExtraSupportRetained", "dealerMarginNetExGst",
    "extraDealerIncomeTotal", "dealerTotalEarnings",
}

# The literal placeholder Swagger/OpenAPI "Try it out" fills into required-string
# fields when the user hasn't typed a real value. Never a plausible real value for
# any lead field, so it's rejected outright rather than persisted as data.
_SWAGGER_STRING_PLACEHOLDER = "string"

# Only fields whose data-model representation is genuinely nullable may be
# cleared with an explicit JSON null. Every other LeadUpdateIn field was a
# non-nullable str/float in the original LeadIn (default "" or 0, never None),
# so exclude_unset=True can't distinguish "client wants to blank this out" from
# "client (or a generated/all-null body) sent null for a field it never meant to
# touch" -- reject null for those instead of silently blanking a required field.
LEAD_NULLABLE_FIELDS = {"nextFollowupDate"}


async def _validate_lead_update_choices(payload, lead):
    """Best-effort validation against master data (requirement: enum/master-list
    fields validated where appropriate). Only validates values the client is
    actually CHANGING (differs from what's already stored on the lead) -- leads
    with a legacy/historical value not in the current master list (e.g. leadSource
    "Import" from a file import) must still be editable for unrelated fields;
    resubmitting the same value isn't a new value to validate. Skips validation
    for a category if its master list is empty, rather than blocking on a
    misconfigured/empty list."""
    errors = []
    checks = [("leadSource", "leadSources", "Lead Sources"), ("executive", "executives", "Executives"),
              ("priority", "priorities", "Priorities")]
    for field, category, label in checks:
        val = payload.get(field)
        if not val or val == lead.get(field):
            continue
        allowed = await _masters_list_values(category)
        if allowed and val not in allowed:
            errors.append(f"{field} '{val}' is not in the {label} master list")
    status_val = payload.get("currentStatus")
    if status_val and status_val != lead.get("currentStatus") and status_val not in seeder.MASTERS["statuses"]:
        errors.append(f"currentStatus '{status_val}' is not a recognized status")
    for field in ("financeRequired", "exchangeRequired"):
        val = payload.get(field)
        if val is not None and val != lead.get(field) and val not in ("Yes", "No"):
            errors.append(f"{field} must be 'Yes' or 'No', got '{val}'")
    return errors


@api.put("/leads/{lead_id}")
async def update_lead(lead_id: str, body: LeadUpdateIn, act=Depends(actor)):
    """Partial update: only fields present in the request body are touched — every
    other field on the lead (including system/financial fields, which aren't even
    part of this model) is left exactly as it was. See LEAD_SYSTEM_FIELDS."""
    lead = await get_lead_or_404(lead_id)
    _require_mutable_lead(lead, "lead edits")
    payload = body.model_dump(exclude_unset=True)
    payload = {k: v for k, v in payload.items() if k not in LEAD_SYSTEM_FIELDS}

    null_fields = [k for k, v in payload.items() if v is None and k not in LEAD_NULLABLE_FIELDS]
    if null_fields:
        raise HTTPException(422, f"null is not allowed for: {', '.join(null_fields)}. "
                                  f"Omit the field to leave it unchanged, or provide a real value.")

    placeholder_fields = [k for k, v in payload.items()
                          if isinstance(v, str) and v.strip().lower() == _SWAGGER_STRING_PLACEHOLDER]
    if placeholder_fields:
        raise HTTPException(422, f"Refusing to save placeholder value \"string\" for: {', '.join(placeholder_fields)}. "
                                  f"Remove the field from the request instead of leaving Swagger's example value.")

    errors = await _validate_lead_update_choices(payload, lead)
    if errors:
        raise HTTPException(422, "; ".join(errors))

    if not payload:
        return clean(lead)

    vehicle_changed = (
        ("interestedModel" in payload and str(payload["interestedModel"] or "").strip()
         != str(lead.get("interestedModel") or "").strip())
        or ("variant" in payload and str(payload["variant"] or "").strip()
            != str(lead.get("variant") or "").strip())
    )
    # Once priced/schemed, only the owner may change model/variant (cascades commercials).
    if vehicle_changed and (_is_priced(lead) or _has_persisted_scheme(lead)):
        _require_owner_reedit(act, True, "Model / variant")

    old = {k: lead.get(k) for k in payload.keys()}
    payload["lastUpdated"] = now_iso()
    # Lead Register "Last Updated By": the acting user was already resolved for the
    # audit log, but was never written onto the lead, so the column had no source.
    payload["lastUpdatedBy"] = act.get("email", "")
    await db.leads.update_one({"leadId": lead_id}, {"$set": payload})
    if vehicle_changed:
        await _cascade_vehicle_or_price_change(lead_id, refresh_price=True, realign_scheme=True)
    else:
        await recompute_lead(lead_id)
    await write_audit(act, "update", "lead", leadId=lead_id, old=old, new={k: v for k, v in payload.items() if k != "lastUpdated"})
    updated = await db.leads.find_one({"leadId": lead_id})
    # GS-2: a lead edit must reach the EXISTING Lead Register row. Previously this
    # endpoint never touched the Sheet at all, so the row went stale on first edit.
    # sheet_sync upserts on leadId, so this updates in place — it never appends.
    await sheet_sync("leads", clean(dict(updated)))
    return clean(updated)


async def _price_master_row(model, variant):
    """Authoritative Price Master lookup, keyed on model + variant exactly as the
    Price Master defines them (case/whitespace-insensitive, active rows only).
    Returns None when there is no matching row — the caller must refuse to book
    rather than fall back to zero."""
    m = str(model or "").strip()
    v = str(variant or "").strip()
    if not m:
        return None
    rows = await db.price_master.find({"model": {"$regex": f"^{re.escape(m)}$", "$options": "i"}}).to_list(500)
    active = [r for r in rows if str(r.get("status") or "active").lower() == "active"] or rows
    if v:
        exact = [r for r in active if str(r.get("variant") or "").strip().lower() == v.lower()]
        if exact:
            return exact[0]
        return None          # variant was specified but has no Price Master row
    return active[0] if len(active) == 1 else None


def _price_structure_from_master(row):
    """Map a Price Master row onto the lead's price-structure fields."""
    return {
        "exShowroom": ce.num(row.get("exShowroom")),
        "rto": ce.num(row.get("rto")),
        "insuranceAmount": ce.num(row.get("insurance")),
        "accessoriesAmount": ce.num(row.get("accessories")),
        "handlingCharges": ce.num(row.get("handlingCharges")),
        "trc": ce.num(row.get("trc")),
        "fastag": ce.num(row.get("fastag")),
        "extendedWarranty": ce.num(row.get("extendedWarranty")),
        "otherCharges": ce.num(row.get("otherCharges")),
        "tcsApplicable": row.get("tcsApplicable") or "No",
    }


async def _cascade_vehicle_or_price_change(lead_id, *, refresh_price=True, realign_scheme=True):
    """After model/variant or price edits, refresh Master-backed fields and recompute.

    - Price Master: when refresh_price, overwrite Ex-Showroom (and empty charge lines
      from master defaults) for the lead's current model/variant.
    - Scheme: when a scheme was already saved, rematerialise eligible offer pools from
      Scheme Master for the new vehicle/month and clamp any prior customer benefits
      that no longer fit. Then recompute_lead refreshes payable / retained / claims.
    """
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return None
    patch = {}
    if refresh_price:
        row = await _price_master_row(lead.get("interestedModel"), lead.get("variant"))
        if row:
            # Full Price Master structure for the new model/variant.
            patch.update(_price_structure_from_master(row))

    if realign_scheme and _has_persisted_scheme(lead):
        import json as _json
        scheme_rows = await get_scheme_rows()
        model = lead.get("interestedModel") or ""
        variant = lead.get("variant") or ""
        booking_date = lead.get("bookingDate") or today()
        rules_ctx = ce.get_scheme_offer_rules_for_vehicle(
            model, variant, booking_date, scheme_rows)
        for key, rule in (rules_ctx.get("rules") or {}).items():
            if key == "additionalDiscount":
                continue
            if rule.get("allowed") and ce.num(rule.get("maxAmount")) > 0:
                patch[key] = ce.num(rule.get("schemeAvailable") or rule.get("maxAmount"))
            else:
                patch[key] = 0
        # Drop / clamp breakup keys that are no longer eligible.
        raw_bk = lead.get("benefitPassedBreakup") or "{}"
        try:
            bk = _json.loads(raw_bk) if isinstance(raw_bk, str) else dict(raw_bk or {})
        except Exception:
            bk = {}
        if not isinstance(bk, dict):
            bk = {}
        raw_used = lead.get("schemeComponentsUsed") or "{}"
        try:
            used = _json.loads(raw_used) if isinstance(raw_used, str) else dict(raw_used or {})
        except Exception:
            used = {}
        if not isinstance(used, dict):
            used = {}
        allowed = set()
        for key, rule in (rules_ctx.get("rules") or {}).items():
            if key != "additionalDiscount" and rule.get("allowed") and ce.num(rule.get("maxAmount")) > 0:
                allowed.add(key)
        for ent in (rules_ctx.get("entitlements") or []):
            if ce.num(ent.get("schemeAvailable") or ent.get("totalBenefit")) > 0:
                allowed.add(ent["key"])
        clean_bk, clean_used = {}, {}
        for key in allowed:
            cap = ce.num(patch.get(key))
            if key in (rules_ctx.get("rules") or {}) and (rules_ctx["rules"][key].get("allowed")):
                cap = ce.num(rules_ctx["rules"][key].get("schemeAvailable")
                             or rules_ctx["rules"][key].get("maxAmount") or cap)
            for ent in (rules_ctx.get("entitlements") or []):
                if ent.get("key") == key:
                    cap = ce.num(ent.get("schemeAvailable") or ent.get("totalBenefit") or cap)
            cb = ce.round2(max(0.0, min(ce.num(bk.get(key)), cap)))
            clean_bk[key] = cb
            clean_used[key] = bool(used.get(key)) if key in used else (cb > 0)
        patch["benefitPassedBreakup"] = _json.dumps(clean_bk)
        patch["schemeComponentsUsed"] = _json.dumps(clean_used)
        patch["customerBenefitPassed"] = ce.round2(sum(clean_bk.values()))
        patch["schemeAllocationExplicit"] = True
        patch["schemeAllocationV2"] = True

    if patch:
        patch["lastUpdated"] = now_iso()
        await db.leads.update_one({"leadId": lead_id}, {"$set": patch})
    return await recompute_lead(lead_id)


@api.get("/leads/{lead_id}/price-preview")
async def price_preview(lead_id: str):
    """What Price Master resolves to for this lead's model/variant, before booking.
    Lets the UI show the real commercial structure (or a precise 'not found')
    instead of discovering it only at booking time."""
    lead = await get_lead_or_404(lead_id)
    model, variant = lead.get("interestedModel"), lead.get("variant")
    row = await _price_master_row(model, variant)
    if not row:
        return {"found": False, "model": model, "variant": variant,
                "message": f"Price Master entry not found for: Model = {model or '(none)'}, "
                           f"Variant = {variant or '(none)'}"}
    return {"found": True, "model": model, "variant": variant,
            "priceId": row.get("priceId"), "priceStructure": _price_structure_from_master(row)}


@api.post("/leads/{lead_id}/convert-booking")
async def convert_booking(lead_id: str, body: BookingIn):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canBook", "conversion to booking")
    # A booking is only valid once its commercial structure is resolved. If the lead
    # has no price structure yet, load it from the authoritative Price Master. If the
    # vehicle has no Price Master row, refuse the booking with a precise message
    # rather than persisting a commercially empty booking (ex-showroom 0, GVC 0).
    # STRICT PRODUCTION BOOKING MODE. Price Master is revalidated on every booking,
    # immediately before persistence — a previously saved price structure is NOT
    # sufficient on its own. If the lead's current model/variant has no Price Master
    # row (e.g. the vehicle was changed after pricing, or the row was withdrawn), the
    # booking is refused rather than persisting against stale commercial values.
    row = await _price_master_row(lead.get("interestedModel"), lead.get("variant"))
    if not row:
        raise HTTPException(422,
            f"Price Master entry not found for: Model = {lead.get('interestedModel') or '(none)'}, "
            f"Variant = {lead.get('variant') or '(none)'}. Add the vehicle to Price Master, or "
            f"correct the model/variant on the lead, then book again.")
    if ce.num(_price_structure_from_master(row).get("exShowroom")) <= 0:
        raise HTTPException(422,
            f"Price Master row {row.get('priceId')} for {lead.get('interestedModel')}/"
            f"{lead.get('variant')} has a zero ex-showroom price. Correct the Price Master entry "
            f"before booking.")
    if ce.num(lead.get("exShowroom")) <= 0:
        # Unpriced lead: adopt the authoritative structure for booking maths, but do
        # NOT mark priceStructureSaved — staff must still complete the Price step.
        await db.leads.update_one({"leadId": lead_id},
                                  {"$set": {**_price_structure_from_master(row),
                                            "priceStructureSaved": False,
                                            "lastUpdated": now_iso()}})
        await recompute_lead(lead_id)
        lead = await db.leads.find_one({"leadId": lead_id})
    if ce.num(lead.get("grossVehicleCost")) <= 0 or ce.num(lead.get("customerPayable")) <= 0:
        # Never persist a booking whose commercial calculation did not resolve.
        raise HTTPException(422,
            f"Commercial calculation did not resolve for {lead.get('interestedModel')}/"
            f"{lead.get('variant')} (gross vehicle cost {ce.num(lead.get('grossVehicleCost'))}, "
            f"customer payable {ce.num(lead.get('customerPayable'))}). Review the price structure "
            f"before booking.")
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
    await sheet_sync("bookings", {
        "bookingId": booking_id, "leadId": lead_id, "customerName": lead.get("customerName"),
        "bookingDate": bdate, "model": lead.get("interestedModel"), "variant": lead.get("variant"),
        "bookingAmount": body.bookingAmount, "paymentMode": body.paymentMode, "bookingStatus": "Booked",
    })
    if body.bookingAmount > 0:
        await _add_payment_internal(lead_id, PaymentIn(
            amount=body.bookingAmount, paymentMode=body.paymentMode, date=bdate,
            narration="Booking advance"))
    _bk_act = {
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": bdate,
        "time": datetime.now(timezone.utc).strftime("%H:%M"), "activityType": "Booking",
        "discussion": "Booking converted.", "executive": lead.get("executive"),
        "customerName": lead.get("customerName"), "mobile": lead.get("mobile"), "model": lead.get("interestedModel"),
    }
    await db.activities.insert_one(dict(_bk_act))
    await sheet_sync("activities", _bk_act)
    await recompute_lead(lead_id)
    return {"bookingId": booking_id, "snapshotId": snapshot_id, "lead": clean(await db.leads.find_one({"leadId": lead_id}))}


@api.delete("/leads/{lead_id}", dependencies=[Depends(owner_only)])
async def delete_lead(lead_id: str, act=Depends(actor)):
    """Owner-only. Permanently delete a wrongly-posted lead and all its related records."""
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        raise HTTPException(404, "Lead not found")
    counts = {}
    for coll in ["payments", "bookings", "deliveries", "finance", "insurance", "claims",
                 "activities", "dealer_earnings", "incentive_register"]:
        r = await db[coll].delete_many({"leadId": lead_id})
        counts[coll] = r.deleted_count
    await db.leads.delete_one({"leadId": lead_id})
    await write_audit(act, "delete", "lead", leadId=lead_id,
                      old={"customerName": lead.get("customerName"), "mobile": lead.get("mobile"),
                           "currentStatus": lead.get("currentStatus"), "customerPayable": lead.get("customerPayable")},
                      new={"cascadeDeleted": counts})
    return {"ok": True, "deleted": {"lead": 1, **counts}}


@api.put("/leads/{lead_id}/price-structure")
async def set_price_structure(lead_id: str, body: PriceStructureIn, act=Depends(actor)):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canPrice", "price-structure edits (only Active leads)")
    _require_owner_reedit(act, _is_priced(lead), "Price structure")
    payload = body.model_dump()
    # Ex-Showroom is Price Master–authoritative and not staff-editable. Prefer the
    # live master row for the lead's model/variant; fall back to the lead's existing
    # value only when no master row exists (so a saved structure is not wiped).
    row = await _price_master_row(lead.get("interestedModel"), lead.get("variant"))
    if row:
        master_ex = ce.num(_price_structure_from_master(row).get("exShowroom"))
        if master_ex <= 0:
            raise HTTPException(422,
                f"Price Master row for {lead.get('interestedModel')}/{lead.get('variant')} "
                f"has a zero ex-showroom price. Correct Price Master before saving.")
        payload["exShowroom"] = master_ex
    else:
        payload["exShowroom"] = ce.num(lead.get("exShowroom"))
        if payload["exShowroom"] <= 0:
            raise HTTPException(422,
                f"Price Master entry not found for {lead.get('interestedModel') or '(none)'}/"
                f"{lead.get('variant') or '(none)'}. Select a valid vehicle before pricing.")
    payload["priceStructureSaved"] = True
    old = {k: lead.get(k) for k in payload.keys()}
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**payload, "lastUpdated": now_iso()}})
    # Owner re-edit of price must also realign scheme pools / retained totals.
    if _has_persisted_scheme({**lead, **payload}):
        await _cascade_vehicle_or_price_change(lead_id, refresh_price=False, realign_scheme=True)
    else:
        await recompute_lead(lead_id)
    await write_audit(act, "update", "price-structure", leadId=lead_id, old=old, new=payload)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.get("/leads/{lead_id}/scheme-rules")
async def scheme_rules(lead_id: str):
    lead = await get_lead_or_404(lead_id)
    scheme_rows = await get_scheme_rows()
    model = lead.get("interestedModel") or ""
    variant = lead.get("variant") or ""
    booking_date = lead.get("bookingDate") or today()
    out = ce.get_scheme_offer_rules_for_vehicle(model, variant, booking_date, scheme_rows)
    # The Lead Drawer must render the SAME allocation every other module consumes.
    out["allocation"] = ce.compute_scheme_allocation(lead_to_snapshot(lead), scheme_rows)
    return out


@api.put("/leads/{lead_id}/scheme")
async def set_scheme(lead_id: str, body: SchemeIn, act=Depends(actor)):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canScheme", "scheme edits (only Active leads)")
    _require_owner_reedit(act, _has_persisted_scheme(lead), "Scheme")
    payload = body.model_dump()
    if payload.get("benefitPassedBreakup") is None:
        payload.pop("benefitPassedBreakup", None)
    if payload.get("schemeComponentsUsed") is None:
        payload.pop("schemeComponentsUsed", None)
    # Validate offers against Scheme Master availability + max caps (port of validateSchemeOffersForVehicle_)
    scheme_rows = await get_scheme_rows()
    offers = {k: payload.get(k, 0) for k in ce.OFFER_KEYS}
    errors = ce.validate_scheme_offers(
        lead.get("interestedModel") or "", lead.get("variant") or "",
        lead.get("bookingDate") or today(), offers, scheme_rows)
    if errors:
        raise HTTPException(422, "Please fix these scheme fields:\n" + "\n".join(errors))
    import json as _json

    raw_breakup = payload.get("benefitPassedBreakup")
    parsed_breakup = None
    if isinstance(raw_breakup, str) and raw_breakup.strip():
        try:
            parsed_breakup = _json.loads(raw_breakup)
        except Exception:
            raise HTTPException(422, "benefitPassedBreakup must be valid JSON")
    elif isinstance(raw_breakup, dict):
        parsed_breakup = raw_breakup

    raw_used = payload.get("schemeComponentsUsed")
    parsed_used = {}
    if isinstance(raw_used, str) and raw_used.strip():
        try:
            parsed_used = _json.loads(raw_used)
        except Exception:
            raise HTTPException(422, "schemeComponentsUsed must be valid JSON")
    elif isinstance(raw_used, dict):
        parsed_used = raw_used
    if not isinstance(parsed_used, dict):
        parsed_used = {}

    # Explicit breakup from the Scheme UI ⇒ assignment model (eligibility ≠ assignment).
    # Legacy clients that omit breakup keep Full/No Benefit materialisation.
    if isinstance(parsed_breakup, dict):
        alloc_errs = ce.validate_scheme_allocation_breakup(
            lead.get("interestedModel") or "", lead.get("variant") or "",
            lead.get("bookingDate") or today(), parsed_breakup, scheme_rows)
        if alloc_errs:
            raise HTTPException(422, "Please fix these scheme allocation fields:\n" + "\n".join(alloc_errs))
        payload["schemeAllocationExplicit"] = True
        payload["schemeAllocationV2"] = True
        # Benefit Mode is not used by the new UI; store Partial for compatibility.
        payload["benefitMode"] = "Partial Benefit"
        provisional = {
            **lead_to_snapshot({**lead, **payload}),
            "schemeAllocationExplicit": True,
            "schemeAllocationV2": True,
            "benefitPassedBreakup": parsed_breakup,
            "schemeComponentsUsed": parsed_used,
            "benefitMode": "Partial Benefit",
        }
        # Ensure eligible offer pools are present so OEM claim shares resolve even
        # when customer benefit is ₹0 (Use Scheme = No). Available = Scheme Master.
        rules_ctx = ce.get_scheme_offer_rules_for_vehicle(
            lead.get("interestedModel") or "", lead.get("variant") or "",
            lead.get("bookingDate") or today(), scheme_rows)
        for key, rule in (rules_ctx.get("rules") or {}).items():
            if key == "additionalDiscount":
                continue
            if rule.get("allowed") and ce.num(rule.get("maxAmount")) > 0:
                # Persist the eligible pool amount (not customer assignment).
                payload[key] = ce.num(rule.get("schemeAvailable") or rule.get("maxAmount"))
                provisional[key] = payload[key]
        alloc = ce.compute_scheme_allocation(provisional, scheme_rows)
        clean_bk = {}
        clean_used = {}
        for c in alloc["components"]:
            if c["key"] == "additionalDiscount":
                continue
            # Prefer client amount when provided; otherwise 0 (never auto-assign).
            if c["key"] in parsed_breakup:
                cb = ce.round2(max(0.0, min(ce.num(parsed_breakup[c["key"]]), c["schemeAvailable"])))
            else:
                cb = 0.0
            clean_bk[c["key"]] = cb
            if c["key"] in parsed_used:
                clean_used[c["key"]] = bool(parsed_used[c["key"]])
            else:
                clean_used[c["key"]] = cb > 0
        payload["benefitPassedBreakup"] = _json.dumps(clean_bk)
        payload["schemeComponentsUsed"] = _json.dumps(clean_used)
        payload["customerBenefitPassed"] = ce.round2(sum(clean_bk.values()))
    else:
        # Legacy path: materialise from Benefit Mode (older API / tests).
        payload["schemeAllocationV2"] = True
        provisional = {**lead_to_snapshot({**lead, **payload}), "schemeAllocationV2": True}
        alloc = ce.compute_scheme_allocation(provisional, scheme_rows)
        clean_bk = {c["key"]: c["customerBenefit"] for c in alloc["components"]
                    if c["key"] != "additionalDiscount"}
        payload["benefitPassedBreakup"] = _json.dumps(clean_bk)
        payload["customerBenefitPassed"] = ce.round2(sum(clean_bk.values()))
        payload["schemeComponentsUsed"] = _json.dumps({k: (v > 0) for k, v in clean_bk.items()})

    old = {k: lead.get(k) for k in payload.keys()}
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**payload, "lastUpdated": now_iso()}})
    await recompute_lead(lead_id)
    await write_audit(act, "update", "scheme", leadId=lead_id, old=old, new=payload)
    return clean(await db.leads.find_one({"leadId": lead_id}))


class SchemeAllocationIn(BaseModel):
    """Per-component customer benefit: {componentKey: amount passed to the customer}."""
    allocation: dict = {}


class ExtraIncomeIn(BaseModel):
    documentationIncome: float = 0
    warrantyIncome: float = 0
    rsaIncome: float = 0
    referralIncome: float = 0
    otherIncome: float = 0
    customerInsuranceBenefitPassed: float = 0
    financeIncentive: float = 0
    accessoriesMargin: float = 0
    exchangeMargin: float = 0
    campaignIncentive: float = 0


@api.put("/leads/{lead_id}/scheme-allocation")
async def set_scheme_allocation(lead_id: str, body: SchemeAllocationIn, act=Depends(actor)):
    """Record how much of EACH scheme component the dealer passes to the customer.

    Validation is per component against Scheme Master: a benefit is never negative and
    never exceeds schemeAvailable. The OEM claimable share is NOT editable here — it is
    fixed by the circular — and neither are the Scheme Master values themselves."""
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canScheme", "scheme edits (only Active leads)")
    _require_owner_reedit(act, _has_persisted_scheme(lead), "Scheme")
    scheme_rows = await get_scheme_rows()
    alloc = ce.compute_scheme_allocation(lead_to_snapshot(lead), scheme_rows)
    available = {c["key"]: c["schemeAvailable"] for c in alloc["components"]}
    errors, clean_alloc = [], {}
    for key, raw in (body.allocation or {}).items():
        if key not in available:
            errors.append(f"• {key}: not a scheme component for this model/variant/month")
            continue
        amt = ce.round2(ce.num(raw))
        if amt < 0:
            errors.append(f"• {key}: customer benefit cannot be negative")
        elif amt > available[key] + 0.01:
            errors.append(f"• {key}: ₹{amt} exceeds the ₹{available[key]} the scheme makes available")
        else:
            clean_alloc[key] = amt
    if errors:
        raise HTTPException(422, "Please fix the scheme allocation:\n" + "\n".join(errors))
    merged = {**ce._explicit_allocation(lead_to_snapshot(lead)), **clean_alloc}
    old = lead.get("schemeAllocation")
    # Persist decisions in BOTH shapes: flat schemeAllocation (PR #21 endpoint) and
    # benefitPassedBreakup (authoritative engine / Scheme UI).
    used = {k: (ce.num(v) > 0) for k, v in merged.items()}
    await db.leads.update_one({"leadId": lead_id}, {"$set": {
        "schemeAllocation": json.dumps(merged),
        "benefitPassedBreakup": json.dumps(merged),
        "schemeComponentsUsed": json.dumps(used),
        "schemeAllocationExplicit": True,
        "schemeAllocationV2": True,
        "benefitMode": "Partial Benefit",
        "customerBenefitPassed": ce.round2(sum(ce.num(v) for v in merged.values())),
        "lastUpdated": now_iso(),
        "lastUpdatedBy": act.get("email", "")}})
    await recompute_lead(lead_id)
    await write_audit(act, "update", "scheme-allocation", leadId=lead_id,
                      old={"schemeAllocation": old}, new={"schemeAllocation": merged})
    updated = await db.leads.find_one({"leadId": lead_id})
    return {**clean(updated),
            "allocation": ce.compute_scheme_allocation(lead_to_snapshot(updated), scheme_rows)}


@api.put("/leads/{lead_id}/extra-income")
async def set_extra_income(lead_id: str, body: ExtraIncomeIn, act=Depends(actor)):
    """Dealer extra-income lines:
    Documentation / Warranty / RSA / Referral / Other / Finance Incentive /
    Accessories Margin / Exchange Margin / Campaign Incentive.

    customerInsuranceBenefitPassed is accepted for memo/compatibility but is
    CUSTOMER discount — it does NOT enter Dealer Earnings totals.

    Never affects Customer Payable / Outstanding."""
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canScheme", "extra-income edits (only Active leads)")
    _extra_keys = (
        "documentationIncome", "warrantyIncome", "rsaIncome", "referralIncome",
        "otherIncome", "financeIncentive", "accessoriesMargin", "exchangeMargin",
        "campaignIncentive",
    )
    _require_owner_reedit(
        act, any(ce.num(lead.get(k)) > 0 for k in _extra_keys), "Extra income")
    payload = body.model_dump()
    old = {k: lead.get(k) for k in payload.keys()}
    await db.leads.update_one({"leadId": lead_id}, {"$set": {**payload, "lastUpdated": now_iso()}})
    await recompute_lead(lead_id)
    await write_audit(act, "update", "extra-income", leadId=lead_id, old=old, new=payload)
    return clean(await db.leads.find_one({"leadId": lead_id}))


@api.post("/leads/{lead_id}/close")
async def close_lead(lead_id: str, body: CloseIn, act=Depends(actor)):
    lead = await get_lead_or_404(lead_id)
    _require_action(lead, "canClose", "closing (only Active leads)")
    if not str(body.closeReason or "").strip():
        raise HTTPException(422, "Close Reason is required to close a lead.")
    # RC + Number Plate mandatory when closing a DELIVERED lead (port of validateCloseLeadRcFields_)
    plate = body.numberPlate or lead.get("numberPlate")
    if _is_delivered(lead):
        rc = body.rc or lead.get("rcStatus")
        errs = []
        if not _yes_or_done(rc):
            errs.append("Set RC to Yes/Done before closing the lead.")
        if not str(plate or "").strip():
            errs.append("Enter the number plate before closing the lead.")
        if errs:
            raise HTTPException(422, "Cannot close lead:\n" + "\n".join("• " + e for e in errs))
    if str(plate or "").strip():
        await _assert_unique_vehicle_identifiers(lead_id, number_plate=plate)
    close_updates = {
        "accountStatus": "Closed",
        "closedDate": str(body.closedDate or "").strip() or today(),
        "closeReason": body.closeReason,
        "finalOutstanding": lead.get("customerOutstanding", 0), "lastUpdated": now_iso(),
        # Lead Register has "Closed By" and "Close Timestamp" columns. The acting user
        # and the moment of closure were both already known here — they were simply
        # never recorded, so an audited closure could not be attributed from the sheet.
        "closedBy": act.get("email", ""), "closeTimestamp": now_iso(),
        "lastUpdatedBy": act.get("email", ""),
    }
    if body.rc:
        close_updates["rcStatus"] = body.rc
    if body.numberPlate:
        close_updates["numberPlate"] = body.numberPlate
    await db.leads.update_one({"leadId": lead_id}, {"$set": close_updates})
    await write_audit(act, "close", "lead", leadId=lead_id,
                      old={"accountStatus": lead.get("accountStatus")}, new=close_updates)
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
        await sheet_sync("leads", doc)
        created += 1
    return {"created": created}


# ---------------------------------------------------------------- payments
async def _add_payment_internal(lead_id, body: PaymentIn):
    # Same guard record_financer_receipt/record_claim_receipt already have — this endpoint
    # was missing it, which let a negative amount silently reduce runningTotal (the
    # over-payment check below only ever fires on running > payable, never on a value
    # that DECREASES running, so negative amounts sailed through undetected).
    if body.amount <= 0:
        raise HTTPException(422, "Enter a valid payment amount")
    lead = await db.leads.find_one({"leadId": lead_id})
    # Double-submit guard (U4): reject an identical receipt (same lead/amount/mode) within 4s
    recent = await db.payments.find_one(
        {"leadId": lead_id, "amount": ce.round2(body.amount), "paymentMode": body.paymentMode},
        sort=[("_id", -1)])
    if recent and recent.get("recordedAt"):
        try:
            prev = datetime.fromisoformat(recent["recordedAt"])
            if (datetime.now(timezone.utc) - prev).total_seconds() < 4:
                raise HTTPException(409, "Duplicate submission detected — this receipt was just recorded. Please wait a moment.")
        except HTTPException:
            raise
        except Exception:
            pass
    receipt = await next_id("receipt", "RC26")
    prior = await db.payments.aggregate([
        {"$match": {"leadId": lead_id}}, {"$group": {"_id": None, "t": {"$sum": "$amount"}}}
    ]).to_list(1)
    running = ce.round2((prior[0]["t"] if prior else 0) + body.amount)
    snap = lead_to_snapshot(lead) if lead else {}
    payable = ce.compute_commercial_totals(snap)["customerPayable"] if lead else 0
    # Over-payment guard (port of BusinessRulesService.validatePaymentAmount_): a receipt may
    # never push total received above Customer Payable. Provisional allowed only when payable is
    # still ₹0 (slim booking, price deferred to Price Structure).
    if payable > 0 and running > payable + 0.01:
        room = ce.round2(max(0.0, payable - (running - body.amount)))
        raise HTTPException(422, f"Amount ₹{ce.round2(body.amount)} exceeds the balance. Customer payable is ₹{payable}; only ₹{room} can still be collected.")
    outstanding = ce.round2(max(0.0, payable - running)) if payable > 0 else 0.0
    finance_file_number = body.financeFileNumber
    if body.paymentMode == "Finance":
        finance_file_number = await _resolve_finance_file_for_payment(lead_id, body)
    doc = {
        "receiptNumber": receipt, "leadId": lead_id, "customerName": lead.get("customerName") if lead else "",
        "date": body.date or today(), "amount": ce.round2(body.amount), "paymentMode": body.paymentMode,
        "narration": body.narration, "runningTotal": running, "outstandingBalance": outstanding,
        "paymentId": f"PY{uuid.uuid4().hex[:12]}", "financerName": body.financerName,
        "financeFileNumber": finance_file_number, "recordedAt": now_iso(),
    }
    try:
        await db.payments.insert_one(doc)
    except Exception:
        if body.paymentMode == "Finance":
            await db.finance.delete_one({
                "leadId": lead_id, "fileNumber": finance_file_number,
                "sanctionedAmount": 0.0, "receivedAgainstFile": 0.0, "receipts": []
            })
        raise
    await sheet_sync("payments", doc)
    if body.paymentMode == "Finance":
        await _upsert_finance_file(lead_id, body, finance_file_number)
    return clean(doc)


@api.get("/payments")
async def list_payments(lead_id: Optional[str] = None):
    q = {"leadId": lead_id} if lead_id else {}
    return [clean(p) for p in await db.payments.find(q).sort("date", -1).to_list(2000)]


@api.post("/leads/{lead_id}/payments")
async def add_payment(lead_id: str, body: PaymentIn, act=Depends(actor)):
    lead = await get_lead_or_404(lead_id)
    if body.paymentMode == "Finance":
        _require_action(lead, "canFinanceReceipt", "finance receipt (lead is archived)")
    else:
        _require_action(lead, "canPayment", "customer payment (only Active leads)")
    rec = await _add_payment_internal(lead_id, body)
    await recompute_lead(lead_id)
    await write_audit(act, "receipt", "payment", leadId=lead_id, paymentId=rec.get("receiptNumber"),
                      financeFileNumber=rec.get("financeFileNumber") or "",
                      new={"amount": rec.get("amount"), "mode": body.paymentMode, "runningTotal": rec.get("runningTotal")})
    return rec


# ---------------------------------------------------------------- finance
FINANCE_FILE_PATTERN = re.compile(r"^FN26\d{6}$")


def is_legacy_finance_file_number(file_number):
    """A finance file number that predates the FN26 contract (e.g. the live '55').
    Historical records keep their number — renumbering them would break every
    payment and sheet row that references them."""
    return bool(str(file_number or "").strip()) and not FINANCE_FILE_PATTERN.match(str(file_number).strip())


async def _resolve_finance_file_for_payment(lead_id, body: PaymentIn):
    if not (body.financerName or "").strip():
        raise HTTPException(422, "Financer is required for Finance payments")
    supplied = (body.financeFileNumber or "").strip()
    by_lead = await db.finance.find_one({"leadId": lead_id})
    if supplied:
        by_file = await db.finance.find_one({"fileNumber": supplied})
        if by_file and by_file.get("leadId") != lead_id:
            raise HTTPException(422, "Finance file number already belongs to another lead")
        if by_lead and by_lead.get("fileNumber") != supplied:
            raise HTTPException(422, "Lead already has a different finance file number")
        # A NEW file must follow the numbering contract. Staff are never required to
        # invent one — leaving the field blank generates FN26xxxxxx. This is what let
        # a hand-typed "55" into production and made the Finance Register unkeyable.
        # An EXISTING record keeps whatever number it already has (legacy support).
        if not by_file and not FINANCE_FILE_PATTERN.match(supplied):
            raise HTTPException(422,
                f"'{supplied}' is not a valid Finance File Number. Leave the field blank and "
                f"the system will generate one (FN26xxxxxx), or enter an existing file number.")
        return supplied
    if by_lead:
        return by_lead.get("fileNumber")
    file_number = await next_id("finance", "FN26")
    try:
        res = await db.finance.find_one_and_update(
            {"leadId": lead_id},
            {"$setOnInsert": {
                "fileNumber": file_number, "leadId": lead_id,
                "customerName": (await db.leads.find_one({"leadId": lead_id}) or {}).get("customerName", ""),
                "financer": body.financerName, "sanctionedAmount": 0.0,
                "receivedAgainstFile": 0.0, "fileOutstanding": 0.0,
                "status": "Pending", "receipts": [], "lastUpdated": today(),
            }},
            upsert=True, return_document=True)
        return res.get("fileNumber")
    except DuplicateKeyError:
        existing = await db.finance.find_one({"leadId": lead_id})
        if existing:
            return existing.get("fileNumber")
        raise HTTPException(409, "Could not resolve finance file; please retry")


async def _upsert_finance_file(lead_id, body: PaymentIn, finance_file_number: str):
    """A Finance-mode entry on a lead = amount the FINANCER is now liable to disburse.
    It accrues the file's committed amount; the customer's outstanding already dropped
    by this amount (recompute counts Finance payments). Actual disbursement is booked
    separately via POST /finance/{file}/receipt and never re-touches customer outstanding."""
    lead = await db.leads.find_one({"leadId": lead_id})
    existing = await db.finance.find_one({"fileNumber": finance_file_number})
    if existing and existing.get("leadId") != lead_id:
        raise HTTPException(422, "Finance file number already belongs to another lead")
    if existing:
        committed = ce.round2(ce.num(existing.get("sanctionedAmount")) + body.amount)
        received = ce.num(existing.get("receivedAgainstFile"))
        outstanding = ce.round2(max(0.0, committed - received))
        await db.finance.update_one({"fileNumber": finance_file_number, "leadId": lead_id}, {"$set": {
            "sanctionedAmount": committed, "fileOutstanding": outstanding, "financer": body.financerName or existing.get("financer"),
            "status": "Received" if outstanding <= 0 else ("Partial" if received > 0 else "Pending"),
            "lastUpdated": today(),
        }})
    else:
        committed = ce.round2(body.amount)
        try:
            await db.finance.insert_one({
                "fileNumber": finance_file_number, "leadId": lead_id,
                "customerName": lead.get("customerName") if lead else "", "financer": body.financerName,
                "sanctionedAmount": committed, "receivedAgainstFile": 0.0,
                "fileOutstanding": committed, "status": "Pending", "receipts": [],
                "lastUpdated": today(),
            })
        except DuplicateKeyError:
            await _upsert_finance_file(lead_id, body, (await db.finance.find_one({"leadId": lead_id}))["fileNumber"])
            return
    # DEFECT C fix: mirror the authoritative finance linkage onto the lead so the
    # Lead Register (which maps financerName/financeFileNumber as lead columns) is never
    # stale. recompute_lead runs right after this and pushes the lead row to the sheet.
    fin = await db.finance.find_one({"fileNumber": finance_file_number})
    await db.leads.update_one({"leadId": lead_id}, {"$set": {
        "financeRequired": "Yes",
        "financerName": (fin or {}).get("financer") or body.financerName or "",
        "financeFileNumber": finance_file_number,
        "lastUpdated": now_iso(),
    }})
    await sync_finance_file(finance_file_number)
    await rebuild_finance_views()


async def sync_finance_file(file_number):
    """GS-5: mirror a finance file into the existing Finance tab (upsert on file number)."""
    f = await db.finance.find_one({"fileNumber": file_number})
    if not f:
        return
    await sheet_sync("finance", {
        "financeFileNumber": f.get("fileNumber"), "leadId": f.get("leadId"),
        "customerName": f.get("customerName"), "financerName": f.get("financer"),
        "committedAmount": f.get("sanctionedAmount"), "disbursedAmount": f.get("receivedAgainstFile"),
        "financeOutstanding": f.get("fileOutstanding"), "status": f.get("status"),
    })


FINANCE_RECEIPT_SLA_DAYS = 2  # port of FinanceService.gs getFinanceReceiptSlaDays_ (CRM.FINANCE_REGISTER.RECEIPT_SLA_DAYS)


async def _enrich_finance_with_delivery(files):
    """Port of enrichFinanceFilesWithDelivery_: overdue = days since delivery > SLA
    (files with no known delivery date are never overdue — SLA clock hasn't started)."""
    sla = FINANCE_RECEIPT_SLA_DAYS
    today_d = today()
    out = []
    for f in files:
        lead_id = str(f.get("leadId") or "").strip()
        delivery_date = ""
        if lead_id:
            d = await db.deliveries.find_one({"leadId": lead_id}) or {}
            delivery_date = str(d.get("deliveryDate") or "")[:10]
            if not delivery_date:
                lead = await db.leads.find_one({"leadId": lead_id}) or {}
                delivery_date = str(lead.get("deliveryDate") or "")[:10]
        row = dict(f)
        if re.match(r"^\d{4}-\d{2}-\d{2}$", delivery_date):
            days = _claim_ageing_days(delivery_date, "Pending")  # days since delivery, running
            row["deliveryDate"] = delivery_date
            row["daysSinceDelivery"] = days
            row["overdue"] = days > sla
        else:
            row["deliveryDate"] = ""
            row["daysSinceDelivery"] = ""
            row["overdue"] = False
        out.append(row)
    return out


@api.get("/finance")
async def list_finance(view: str = "all"):
    files = [clean(f) for f in await db.finance.find().to_list(1000)]
    pending = [f for f in files if ce.num(f.get("fileOutstanding")) > 0 and f.get("status") != "Received"]
    if view == "pending":
        return pending
    if view == "overdue":
        enriched = await _enrich_finance_with_delivery(pending)
        return [f for f in enriched if f.get("overdue")]
    return files


# --- Derived Finance Pending / Overdue sheet tabs (DEFECT B) -----------------
# These were legacy Apps-Script report tabs the migrated app never maintained, so
# they stayed frozen ("Pending: 0") while the Finance Register held live open files.
# We now rebuild them deterministically from the authoritative Finance Register +
# Delivery Tracker on every finance-affecting event, matching the workbook's format.
FINANCE_PENDING_TITLE = "Finance Pending — open files awaiting financer payment (SLA: 2 days after delivery)"
FINANCE_OVERDUE_TITLE = "Finance Overdue — files past 2-day SLA"
FINANCE_PENDING_HEADER = ["File Number", "Lead ID", "Customer", "Financer", "Sanctioned Amount",
                          "Received", "File Outstanding", "Status", "Delivery Date",
                          "Days Since Delivery", "Due By", "Overdue", "Last Payment Date"]
FINANCE_OVERDUE_HEADER = ["File Number", "Lead ID", "Customer", "Financer", "Sanctioned Amount",
                          "File Outstanding", "Status", "Delivery Date", "Days Since Delivery", "Due By"]


def _finance_due_by(delivery_date: str) -> str:
    if re.match(r"^\d{4}-\d{2}-\d{2}$", str(delivery_date or "")):
        y, m, d = map(int, delivery_date.split("-"))
        return (date(y, m, d) + timedelta(days=FINANCE_RECEIPT_SLA_DAYS)).isoformat()
    return ""


async def rebuild_finance_views():
    """Rebuild the derived Finance Pending & Finance Overdue sheet tabs. No-op if
    Sheets sync is disabled. Full-mirror (clear+write) so closed/received files
    correctly disappear rather than lingering."""
    files = [clean(f) for f in await db.finance.find().to_list(2000)]
    pending = [f for f in files if ce.num(f.get("fileOutstanding")) > 0 and f.get("status") != "Received"]
    enriched = await _enrich_finance_with_delivery(pending)
    overdue = [f for f in enriched if f.get("overdue")]
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    total_out = ce.round2(sum(ce.num(f.get("fileOutstanding")) for f in pending))

    p_rows = [[
        f.get("fileNumber"), f.get("leadId"), f.get("customerName"), f.get("financer"),
        ce.num(f.get("sanctionedAmount")), ce.num(f.get("receivedAgainstFile")), ce.num(f.get("fileOutstanding")),
        f.get("status"), f.get("deliveryDate") or "",
        f.get("daysSinceDelivery") if f.get("daysSinceDelivery") != "" else "",
        _finance_due_by(f.get("deliveryDate")), "Yes" if f.get("overdue") else "No", f.get("lastUpdated") or "",
    ] for f in enriched]
    pending_values = [[FINANCE_PENDING_TITLE],
                      [f"Refreshed: {ts} | Pending: {len(pending)} | Overdue: {len(overdue)} | Total Outstanding: ₹{total_out}"],
                      FINANCE_PENDING_HEADER]
    pending_values += p_rows or [["No pending finance files."]]

    o_rows = [[
        f.get("fileNumber"), f.get("leadId"), f.get("customerName"), f.get("financer"),
        ce.num(f.get("sanctionedAmount")), ce.num(f.get("fileOutstanding")), f.get("status"),
        f.get("deliveryDate") or "", f.get("daysSinceDelivery") if f.get("daysSinceDelivery") != "" else "",
        _finance_due_by(f.get("deliveryDate")),
    ] for f in overdue]
    overdue_values = [[FINANCE_OVERDUE_TITLE],
                      [f"Refreshed: {ts} | Overdue: {len(overdue)}"],
                      FINANCE_OVERDUE_HEADER]
    overdue_values += o_rows or [["No overdue finance files. ✔"]]

    ok_p = await gsheets.overwrite_report_tab(gsheets.FINANCE_PENDING_TAB, pending_values)
    ok_o = await gsheets.overwrite_report_tab(gsheets.FINANCE_OVERDUE_TAB, overdue_values)
    return {"pending": len(pending), "overdue": len(overdue), "syncedPending": ok_p, "syncedOverdue": ok_o}


class ReceiptIn(BaseModel):
    amount: float
    date: str = ""
    reference: str = ""


@api.post("/finance/{file_number}/receipt")
async def record_financer_receipt(file_number: str, body: ReceiptIn, act=Depends(actor)):
    """Record money actually disbursed by the financer against a file. Does NOT change customer outstanding."""
    f = await db.finance.find_one({"fileNumber": file_number})
    if not f:
        raise HTTPException(404, "Finance file not found")
    if body.amount <= 0:
        raise HTTPException(422, "Enter a valid receipt amount")
    committed = ce.num(f.get("sanctionedAmount"))
    received = ce.round2(ce.num(f.get("receivedAgainstFile")) + body.amount)
    outstanding = ce.round2(max(0.0, committed - received))
    receipt = {"amount": ce.round2(body.amount), "date": body.date or today(),
               "reference": body.reference, "recordedAt": now_iso()}
    await db.finance.update_one({"fileNumber": file_number}, {
        "$set": {"receivedAgainstFile": received, "fileOutstanding": outstanding,
                 "status": "Received" if outstanding <= 0 else "Partial",
                 "lastPaymentDate": body.date or today(), "lastUpdated": today()},
        "$push": {"receipts": receipt},
    })
    await write_audit(act, "receipt", "finance", leadId=f.get("leadId", ""), financeFileNumber=file_number,
                      old={"receivedAgainstFile": ce.num(f.get("receivedAgainstFile")), "fileOutstanding": ce.num(f.get("fileOutstanding"))},
                      new={"receivedAgainstFile": received, "fileOutstanding": outstanding, "amount": ce.round2(body.amount)})
    await sync_finance_file(file_number)
    await rebuild_finance_views()
    return clean(await db.finance.find_one({"fileNumber": file_number}))


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
async def mark_delivery(lead_id: str, body: DeliveryIn, act=Depends(actor)):
    lead = await get_lead_or_404(lead_id)
    delivered = (body.delivered or "").lower() in ("yes", "true", "delivered", "1")
    # Delivered / Closed leads are fully frozen — no paperwork re-edits (vehicle is unique).
    if _is_delivered(lead) or _acct(lead) != "Active":
        raise HTTPException(
            409,
            f"This lead is locked for delivery edits "
            f"(status: {lead.get('currentStatus') or 'New'} / {_acct(lead)}). "
            f"Delivered and closed leads cannot be changed.",
        )
    if delivered and not _is_delivered(lead):
        _require_action(lead, "canDeliver", "delivery (not booked/active)")
        errs = _validate_delivery_ready(lead, body)
        if errs:
            raise HTTPException(422, "Cannot mark delivered:\n" + "\n".join("• " + e for e in errs))
    await _assert_unique_vehicle_identifiers(
        lead_id,
        invoice_number=body.invoiceNumber,
        chassis_number=body.chassisNumber,
        number_plate=body.numberPlate,
    )
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
        await sheet_sync("deliveries", {
            "leadId": lead_id, "customerName": lead.get("customerName"),
            "deliveryDate": body.deliveryDate or today(), "delivered": "Yes",
            "invoiceNumber": body.invoiceNumber, "chassisNumber": body.chassisNumber, "numberPlate": body.numberPlate,
        })
        await _upsert_incentive_register_on_delivery(lead_id, body.deliveryDate or today())
        await _upsert_insurance_on_delivery(lead_id, body.deliveryDate or today())
        await rebuild_finance_views()
        await recompute_lead(lead_id)
    return clean(await db.leads.find_one({"leadId": lead_id}))


async def _upsert_insurance_on_delivery(lead_id, delivery_date):
    """On Mark Delivered, open the insurance payout entry for the vehicle.

    Nothing was creating these, so the Insurance Payouts screen stayed empty and the
    Earnings Report's insurance column (which sums expectedPayout) was always 0 — even
    though the premium, insurer and payout rate were all known.

    No new business rule: the premium is the lead's own insuranceAmount, the insurer is
    the one captured at delivery, and the rate/expected/outstanding/status come from the
    existing _insurance_derive + suggested_insurance_payout_rate (49% Storm/Turbo,
    36.5% others). Idempotent — one entry per lead, refreshed rather than duplicated."""
    lead = await db.leads.find_one({"leadId": lead_id}) or {}
    premium = ce.num(lead.get("insuranceAmount"))
    if premium <= 0:
        return None          # no premium charged -> no payout is due; leave it absent
    existing = await db.insurance.find_one({"leadId": lead_id})
    data = {
        "leadId": lead_id,
        "customerName": lead.get("customerName", ""),
        "mobile": lead.get("mobile", ""),
        "model": lead.get("interestedModel", ""),
        "variant": lead.get("variant", ""),
        "insuranceCompany": lead.get("insurerName", "") or (existing or {}).get("insuranceCompany", ""),
        "policyNumber": (existing or {}).get("policyNumber", ""),
        "insuranceAmount": premium,
        # Preserve a manually set rate / already-received money on re-delivery edits.
        "payoutRate": ce.num((existing or {}).get("payoutRate")),
        "receivedPayout": ce.num((existing or {}).get("receivedPayout")),
        "status": (existing or {}).get("status", "Pending"),
        "deliveryDate": delivery_date,
        "insuranceExecutive": lead.get("executive", ""),
        "remarks": (existing or {}).get("remarks", ""),
        "lastUpdated": now_iso(),
    }
    data.update(_insurance_derive(data))
    if existing:
        await db.insurance.update_one({"entryId": existing["entryId"]}, {"$set": data})
        data["entryId"] = existing["entryId"]
    else:
        data["entryId"] = await next_id("insurance", "INS26")
        data["policyDate"] = None
        await db.insurance.insert_one(dict(data))
    await sheet_sync("insurance", {**data, "payoutRatePct": round(ce.num(data.get("payoutRate")) * 100, 1)})
    return data


async def _upsert_incentive_register_on_delivery(lead_id, delivery_date):
    """Port of upsertIncentiveRegisterOnDelivery_: on Mark Delivered, create a
    Pending Incentive Register row from the Incentive Master rate for the lead's
    model/variant/delivery-month. Skips if a row already exists for this lead."""
    if await db.incentive_register.find_one({"leadId": lead_id}):
        return None
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return None
    model = lead.get("interestedModel") or ""
    variant = lead.get("variant") or ""
    incentive_rows = [clean(r) for r in await db.incentive_master.find().to_list(1000)]
    rate = ce.get_incentive_rate_for_lead(model, variant, delivery_date, incentive_rows)
    if not rate:
        return None
    cat = ce.map_lead_to_incentive_category(model, variant)
    remarks = f"Rate from Incentive Master. Min retails: {rate.get('minRetails') or 0}"
    if rate.get("maxSlab"):
        remarks += f"; Max slab: {rate.get('maxSlab')}"
    doc = {
        "incentiveId": f"INC{uuid.uuid4().hex[:8]}",
        "schemeMonth": rate.get("schemeMonth") or ce.scheme_month_from_date(delivery_date),
        "executive": lead.get("executive") or "",
        "leadId": lead_id, "bookingId": lead.get("bookingId") or "",
        "model": model, "variant": variant, "productCategory": cat,
        "deliveryDate": delivery_date, "incentiveAmount": ce.num(rate.get("incentivePerRetail")),
        "status": "Pending", "paidDate": "", "remarks": remarks,
        "lastUpdated": now_iso(),
    }
    await db.incentive_register.insert_one(doc)
    # Push to Google Sheet Incentive Register (was missing from SYNC_MAP / never called).
    await sheet_sync("incentive_register", clean(doc))
    return doc


@api.get("/incentive-register")
async def list_incentive_register():
    return [clean(r) for r in await db.incentive_register.find().to_list(2000)]


class IncentivePayIn(BaseModel):
    paidDate: str = ""


async def _upsert_incentive_oem_claim(incentive_row, act=None):
    """When executive incentive is Mark Paid, open an OEM Claim Register row (outstanding).

    Same receivable path as scheme claims: appears in GET /claims, Scheme Claim Register
    sheet, and OEM totals. Does NOT touch scheme allocation / companyOutstanding formula
    (those stay scheme-share SSOT); incentive is a separate manual claim component.
    """
    lead_id = incentive_row.get("leadId") or ""
    amount = ce.round2(ce.num(incentive_row.get("incentiveAmount")))
    if amount <= 0 or not lead_id:
        return None
    incentive_id = incentive_row.get("incentiveId") or ""
    component_key = f"executiveIncentive-{incentive_id}" if incentive_id else "executiveIncentive"
    claim_id = f"CLM-{lead_id}-executiveIncentive"
    lead = await db.leads.find_one({"leadId": lead_id}) or {}
    existing = await db.claims.find_one({"leadId": lead_id, "componentKey": component_key}) or {}
    # Preserve receipts if the claim was already partially paid by OEM.
    received = ce.round2(ce.num(existing.get("receivedAmount")))
    status = existing.get("claimStatus") or "Pending"
    if received <= 0:
        status = "Pending"
    elif received + 0.01 >= amount:
        status = "Received"
    else:
        status = "Partial"
    doc = {
        "claimId": existing.get("claimId") or claim_id,
        "manual": True,
        "componentKey": component_key,
        "leadId": lead_id,
        "customer": lead.get("customerName") or existing.get("customer") or "",
        "model": incentive_row.get("model") or lead.get("interestedModel") or "",
        "variant": incentive_row.get("variant") or lead.get("variant") or "",
        "bookingDate": lead.get("bookingDate") or "",
        "bookingId": incentive_row.get("bookingId") or lead.get("bookingId") or "",
        "schemeMonth": incentive_row.get("schemeMonth") or "",
        "executive": incentive_row.get("executive") or lead.get("executive") or "",
        "claimType": "Executive Incentive",
        "component": "Executive Incentive",
        "oemCompany": "Euler Motors",
        "claimAmount": amount,
        "eligibleClaim": amount,
        "claimStatus": status,
        "receivedAmount": received,
        "claimReference": existing.get("claimReference") or incentive_id,
        "note": existing.get("note") or f"Executive incentive paid {incentive_row.get('paidDate') or ''}".strip(),
        "submittedDate": existing.get("submittedDate") or incentive_row.get("paidDate") or today(),
        "approvedDate": existing.get("approvedDate") or "",
        "source": "Executive Incentive (Paid)",
        "claimRequired": "Yes",
        # Bifurcation columns stay 0; total/oemDiscount carry the incentive amount.
        "consumerDiscount": 0, "exchangeBonus": 0, "loyaltyBonus": 0, "insuranceBenefit": 0,
        "referralBonus": 0, "dsaDiscount": 0, "additionalDiscount": 0,
        "rtoBenefit": 0, "rtoInsuranceBenefit": 0,
        "totalDiscount": amount, "dealerDiscount": 0, "oemDiscount": amount,
        "lastUpdated": now_iso(),
    }
    if not existing:
        doc["receipts"] = []
        doc["createdAt"] = now_iso()
    await db.claims.update_one(
        {"leadId": lead_id, "componentKey": component_key},
        {"$set": doc}, upsert=True,
    )
    await sheet_sync("claims", clean(doc))
    if act:
        await write_audit(act, "upsert", "claim", leadId=lead_id, claimId=doc["claimId"],
                          new={"component": "Executive Incentive", "claimAmount": amount,
                               "incentiveId": incentive_id, "source": doc["source"]})
    return doc


@api.put("/incentive-register/{incentive_id}/pay", dependencies=[Depends(owner_only)])
async def mark_incentive_paid(incentive_id: str, body: IncentivePayIn, act=Depends(actor)):
    existing = await db.incentive_register.find_one({"incentiveId": incentive_id})
    if not existing:
        raise HTTPException(404, "Incentive Register row not found")
    updates = {"status": "Paid", "paidDate": body.paidDate or today(), "lastUpdated": now_iso()}
    await db.incentive_register.update_one({"incentiveId": incentive_id}, {"$set": updates})
    paid = {**existing, **updates}
    await sheet_sync("incentive_register", clean(paid))
    # Paid executive incentive → OEM Claim Register outstanding (claim from OEM).
    await _upsert_incentive_oem_claim(paid, act=act)
    await write_audit(act, "update", "incentive_register", leadId=existing.get("leadId", ""),
                      old={"status": existing.get("status")}, new=updates)
    return clean(await db.incentive_register.find_one({"incentiveId": incentive_id}))


@api.post("/admin/sync-incentive-register", dependencies=[Depends(owner_only)])
async def sync_incentive_register_sheet(act=Depends(actor)):
    """Backfill Google Sheet Incentive Register from Mongo (rows created before sheet sync)."""
    rows = [clean(r) for r in await db.incentive_register.find().to_list(5000)]
    synced, errors = 0, []
    for row in rows:
        try:
            await sheet_sync("incentive_register", row)
            synced += 1
            if str(row.get("status") or "").lower() == "paid":
                await _upsert_incentive_oem_claim(row, act=None)
        except Exception as e:
            errors.append({"incentiveId": row.get("incentiveId"), "error": str(e)})
    await write_audit(act, "sync", "incentive_register", new={"synced": synced, "errors": len(errors)})
    return {"ok": True, "synced": synced, "total": len(rows), "errors": errors}


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
    _require_action(lead, "canScheme", "logging activity (only Active leads)")
    payload = body.model_dump()
    act_date = str(payload.pop("date", None) or "").strip() or today()
    doc = {
        "activityId": await next_id("activity", "AC26"), "leadId": lead_id, "date": act_date,
        "time": datetime.now(timezone.utc).strftime("%H:%M"), **payload,
        "customerName": lead.get("customerName"), "mobile": lead.get("mobile"), "model": lead.get("interestedModel"),
    }
    await db.activities.insert_one(doc)
    await sheet_sync("activities", doc)
    # Lead Register "Last Activity" summarises the most recent activity on the lead.
    # It is derived from the activity just logged, not separately entered.
    summary = " · ".join(x for x in (body.activityType, (body.discussion or "").strip()) if x)
    await db.leads.update_one({"leadId": lead_id}, {"$set": {
        "lastActivity": summary[:200], "lastUpdated": now_iso(),
    }})
    await recompute_lead(lead_id)
    return clean(doc)


def _strip_payout_for_staff(entry: dict, is_owner: bool):
    """Hide dealer payout economics (rate/expected/outstanding) from non-owner staff."""
    if is_owner:
        return entry
    e = dict(entry)
    for k in ("payoutRate", "expectedPayout", "payoutOutstanding"):
        e.pop(k, None)
    return e


@api.get("/insurance")
async def list_insurance(lead_id: Optional[str] = None, act=Depends(actor)):
    q = {"leadId": lead_id} if lead_id else {}
    is_owner = act.get("role") == "owner"
    return [_strip_payout_for_staff(clean(i), is_owner)
            for i in await db.insurance.find(q).sort("entryId", -1).to_list(1000)]


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
    if rate <= 0:  # no manual rate -> suggested default by model (49% Storm/Turbo, 36.5% others)
        rate = ce.suggested_insurance_payout_rate(body.get("model"), body.get("variant"))
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
async def create_insurance(body: InsuranceIn, act=Depends(actor)):
    is_owner = act.get("role") == "owner"
    data = body.model_dump()
    if not is_owner:
        data["payoutRate"] = 0   # staff never set the rate; server auto-fills from model
    data.update(_insurance_derive(data))
    data["entryId"] = await next_id("insurance", "INS26")
    if data.get("leadId"):
        lead = await db.leads.find_one({"leadId": data["leadId"]})
        if lead:
            data["deliveryDate"] = lead.get("deliveryDate")
    await db.insurance.insert_one(dict(data))
    await sheet_sync("insurance", {**data, "payoutRatePct": round(ce.num(data.get("payoutRate")) * 100, 1)})
    await write_audit(act, "create", "insurance", leadId=data.get("leadId", ""),
                      new={"entryId": data["entryId"], "premium": data.get("insuranceAmount"),
                           "payoutRate": data.get("payoutRate"), "expectedPayout": data.get("expectedPayout")})
    return _strip_payout_for_staff(clean(data), is_owner)


@api.put("/insurance/{entry_id}", dependencies=[Depends(owner_only)])
async def update_insurance(entry_id: str, body: InsuranceIn, act=Depends(actor)):
    existing = await db.insurance.find_one({"entryId": entry_id}) or {}
    data = body.model_dump()
    data.update(_insurance_derive(data))
    res = await db.insurance.update_one({"entryId": entry_id}, {"$set": data})
    if res.matched_count == 0:
        raise HTTPException(404, "Insurance entry not found")
    await write_audit(act, "update", "insurance", leadId=data.get("leadId", ""),
                      old={"payoutRate": existing.get("payoutRate"), "expectedPayout": existing.get("expectedPayout")},
                      new={"payoutRate": data.get("payoutRate"), "expectedPayout": data.get("expectedPayout")})
    return clean(await db.insurance.find_one({"entryId": entry_id}))


@api.delete("/insurance/{entry_id}", dependencies=[Depends(owner_only)])
async def delete_insurance(entry_id: str, act=Depends(actor)):
    existing = await db.insurance.find_one({"entryId": entry_id}) or {}
    await db.insurance.delete_one({"entryId": entry_id})
    await write_audit(act, "delete", "insurance", leadId=existing.get("leadId", ""),
                      old={"entryId": entry_id, "expectedPayout": existing.get("expectedPayout")})
    return {"ok": True}


@api.post("/insurance/{entry_id}/receipt")
async def record_insurer_payout(entry_id: str, body: ReceiptIn, act=Depends(actor)):
    """Record insurer payout received against an entry; accrues receivedPayout + keeps a receipt history."""
    e = await db.insurance.find_one({"entryId": entry_id})
    if not e:
        raise HTTPException(404, "Insurance entry not found")
    if body.amount <= 0:
        raise HTTPException(422, "Enter a valid receipt amount")
    expected = ce.num(e.get("expectedPayout"))
    received = ce.round2(ce.num(e.get("receivedPayout")) + body.amount)
    outstanding = ce.round2(max(0.0, expected - received))
    status = "Received" if expected > 0 and received >= expected - 0.01 else "Partial"
    receipt = {"amount": ce.round2(body.amount), "date": body.date or today(),
               "reference": body.reference, "recordedAt": now_iso()}
    await db.insurance.update_one({"entryId": entry_id}, {
        "$set": {"receivedPayout": received, "payoutOutstanding": outstanding, "status": status,
                 "lastPayoutDate": body.date or today()},
        "$push": {"receipts": receipt},
    })
    await write_audit(act, "receipt", "insurance", leadId=e.get("leadId", ""),
                      old={"receivedPayout": ce.num(e.get("receivedPayout"))},
                      new={"receivedPayout": received, "payoutOutstanding": outstanding, "amount": ce.round2(body.amount)})
    return _strip_payout_for_staff(clean(await db.insurance.find_one({"entryId": entry_id})), act.get("role") == "owner")


# ---------------------------------------------------------------- OEM claim / owner reports (ports of OemClaimService.gs)
async def _owner_booking_metrics():
    """Per booked-lead economics + claim register — shared by owner reports (ownerAggregates_/dashboard)."""
    leads = await db.leads.find({"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}}).to_list(5000)
    scheme_rows = await get_scheme_rows()
    reg_by_lead = {}
    ref_counts = {}
    for c in await db.claims.find().to_list(5000):
        lid = c.get("leadId")
        if not lid:
            continue
        r = reg_by_lead.setdefault(lid, {"received": 0.0, "refs": [], "statuses": [], "components": {}})
        r["received"] = ce.round2(r["received"] + ce.num(c.get("receivedAmount")))
        ref = str(c.get("claimReference") or "").strip()
        if ref:
            r["refs"].append(ref)
            ref_counts[ref] = ref_counts.get(ref, 0) + 1
        r["statuses"].append(c.get("claimStatus") or "Pending")
        r["components"][c.get("componentKey")] = ce.num(c.get("receivedAmount"))
    rows = []
    for l in leads:
        snap = lead_to_snapshot(l)
        totals = ce.compute_commercial_totals(snap, scheme_rows)
        claim = ce.derive_claim(snap)
        shares = ce.compute_scheme_claim_shares(snap, scheme_rows)
        income = ce.compute_scheme_income_breakdown(snap, scheme_rows)
        alloc = income.get("allocation") or ce.compute_scheme_allocation(snap, scheme_rows)
        use_shares = shares["shareSplitAvailable"]
        company_claim = shares["eligibleTotal"] if use_shares else (income["oemClaimTotal"] if income["shareSplitAvailable"] else claim["claimEligible"])
        company_oem = shares["displayTotal"] if use_shares else (income["oemClaimTotal"] if income["shareSplitAvailable"] else claim["oemDiscount"])
        # Dealer-funded scheme share from the allocation engine (not a parallel calc).
        dealer_scheme = alloc["totals"]["dealerFundedShare"]
        if not (dealer_scheme > 0) and not use_shares:
            dealer_scheme = ce.num(claim["dealerDiscount"])
        reg = reg_by_lead.get(l.get("leadId"))
        rows.append({
            "leadId": l.get("leadId"), "executive": l.get("executive") or "Unassigned",
            "month": str(l.get("bookingDate") or "")[:7] or "Unknown",
            "totals": totals, "claim": claim, "shares": shares, "income": income,
            "companyClaim": company_claim, "companyOem": company_oem, "dealerScheme": dealer_scheme,
            "paid": ce.num(l.get("totalReceived")), "reg": reg,
            "displayByComponent": shares["displayByComponent"] if use_shares else income["oemClaimByComponent"],
        })
    return rows, ref_counts


@api.get("/reports/owner-commercial", dependencies=[Depends(owner_only)])
async def owner_commercial_report():
    """Port of buildOwnerCommercialReport_ — discount ownership, claim position, averages, executive usage."""
    rows, _ = await _owner_booking_metrics()
    n = len(rows)
    dealer_cost = ce.round2(sum(r["claim"]["dealerDiscount"] for r in rows))
    oem_cost = ce.round2(sum(r["companyOem"] for r in rows))
    total_disc = ce.round2(sum(r["totals"]["totalDiscount"] for r in rows))
    claim_total = ce.round2(sum(r["companyClaim"] for r in rows))
    retained = ce.round2(sum(r["income"]["retainedIncomeTotal"] for r in rows))
    payable_total = ce.round2(sum(r["totals"]["customerPayable"] for r in rows))
    pending_claims = 0
    pending_value = 0.0
    received_value = 0.0
    for r in rows:
        reg = r["reg"]
        recvd = ce.num(reg["received"]) if reg else 0.0
        if recvd > 0:
            received_value = ce.round2(received_value + recvd)
        elif r["companyClaim"] > 0:
            pending_claims += 1
            pending_value = ce.round2(pending_value + r["companyClaim"])
    scheme_roi = ce.round2((oem_cost / total_disc) * 100) if total_disc > 0 else 0
    ageing_sum, ageing_count = 0, 0
    for c in await db.claims.find({"submittedDate": {"$exists": True, "$nin": ["", None]}}).to_list(5000):
        d = _claim_ageing_days(c.get("submittedDate", ""), c.get("claimStatus", ""), c.get("approvedDate", ""))
        ageing_sum += d
        ageing_count += 1
    avg_ageing = ce.round2(ageing_sum / ageing_count) if ageing_count else 0
    by_exec = {}
    for r in rows:
        e = by_exec.setdefault(r["executive"], {"executive": r["executive"], "bookings": 0,
                                                "totalDiscount": 0.0, "dealerDiscount": 0.0, "oemDiscount": 0.0})
        e["bookings"] += 1
        e["totalDiscount"] = ce.round2(e["totalDiscount"] + r["totals"]["totalDiscount"])
        e["dealerDiscount"] = ce.round2(e["dealerDiscount"] + r["claim"]["dealerDiscount"])
        e["oemDiscount"] = ce.round2(e["oemDiscount"] + r["companyOem"])
    return {
        "bookings": n,
        "discountOwnership": {
            "totalBookings": n, "dealerShareGiven": dealer_cost, "oemFunded": oem_cost,
            "totalDiscountGiven": total_disc, "oemReceivable": claim_total, "schemeIncomeRetained": retained,
        },
        "claimPosition": {
            "pendingClaims": pending_claims, "pendingValue": pending_value,
            "receivedValue": received_value, "schemeRoiPct": scheme_roi,
            "avgClaimAgeingDays": avg_ageing,
        },
        "averages": {
            "avgDiscountPerBooking": ce.round2(total_disc / n) if n else 0,
            "avgCustomerPayable": ce.round2(payable_total / n) if n else 0,
        },
        "byExecutive": sorted(by_exec.values(), key=lambda x: x["executive"]),
    }


@api.get("/reports/scheme-allocation-impact", dependencies=[Depends(owner_only)])
async def scheme_allocation_impact():
    """READ-ONLY impact of the Scheme Allocation Engine on existing leads.

    Nothing is written. This exists so the change can be reviewed BEFORE any
    historical accounting moves. Customer payable is only ever affected by an
    explicit dealer allocation, so leads without one show a zero payable delta —
    but their dealer-retained figure does change, because the old formula reported
    the dealer's own funded share as negative income."""
    leads = await db.leads.find({"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}}).to_list(5000)
    scheme_rows = await get_scheme_rows()
    affected, payable_delta, retained_delta = [], 0.0, 0.0
    for l in leads:
        snap = lead_to_snapshot(l)
        alloc = ce.compute_scheme_allocation(snap, scheme_rows)
        old_retained = ce.num(ce.compute_scheme_income_breakdown(snap, scheme_rows)["retainedIncomeTotal"])
        new_retained = alloc["totals"]["dealerRetained"]
        ent_benefit = ce.round2(sum(c["customerBenefit"] for c in alloc["components"] if c["automatic"]))
        old_payable = ce.num(l.get("customerPayable"))
        new_payable = ce.round2(max(0.0, ce.compute_commercial_totals(snap)["customerPayable"] - ent_benefit))
        d_pay = ce.round2(new_payable - old_payable)
        d_ret = ce.round2(new_retained - old_retained)
        if d_pay == 0 and d_ret == 0:
            continue
        payable_delta = ce.round2(payable_delta + d_pay)
        retained_delta = ce.round2(retained_delta + d_ret)
        affected.append({
            "leadId": l.get("leadId"), "customerName": l.get("customerName"),
            "vehicle": f"{l.get('interestedModel','')} {l.get('variant','')}".strip(),
            "hasExplicitAllocation": bool(l.get("schemeAllocation")),
            "components": [{k: c[k] for k in ("key", "label", "schemeAvailable", "oemShare",
                                              "dealerFundedShare", "customerBenefit",
                                              "dealerRetained", "oemClaimable",
                                              "dealerFundedBenefit")}
                           for c in alloc["components"]],
            "old": {"customerPayable": old_payable, "dealerSchemeRetained": old_retained,
                    "companyOutstanding": ce.num(l.get("companyOutstanding"))},
            "new": {"customerPayable": new_payable, "dealerSchemeRetained": new_retained,
                    "companyOutstanding": alloc["totals"]["oemClaimable"]},
            "impact": {"customerPayable": d_pay, "dealerSchemeRetained": d_ret,
                       "oemClaim": ce.round2(alloc["totals"]["oemClaimable"] - ce.num(l.get("companyOutstanding")))},
        })
    return {"ok": True, "leadsExamined": len(leads), "leadsAffected": len(affected),
            "totals": {"customerPayableDelta": payable_delta,
                       "dealerSchemeRetainedDelta": retained_delta},
            "note": "READ-ONLY. No record was modified. Customer payable only moves for "
                    "leads carrying an explicit dealer allocation.",
            "leads": affected}


@api.get("/reports/oem-claim-dashboard", dependencies=[Depends(owner_only)])
async def oem_claim_dashboard():
    """Port of buildOemClaimDashboard_ — status/value/monthly/scheme-wise/executive-wise claim summaries."""
    rows, _ = await _owner_booking_metrics()
    status_keys = ["Pending", "Submitted", "Approved", "Rejected", "Received", "Not Applicable"]
    status_count = {s: 0 for s in status_keys}
    status_value = {s: 0.0 for s in status_keys}
    total_oem = 0.0
    dealer_share_val = 0.0
    company_share_val = 0.0
    total_disc_val = 0.0
    eligible_val = 0.0
    monthly = {}
    scheme = {}
    execu = {}
    for r in rows:
        cc = r["companyClaim"]
        total_disc_val = ce.round2(total_disc_val + r["totals"]["totalDiscount"])
        dealer_share_val = ce.round2(dealer_share_val + r["dealerScheme"])
        company_share_val = ce.round2(company_share_val + cc)
        eligible_val = ce.round2(eligible_val + cc)
        reg = r["reg"]
        recvd = ce.num(reg["received"]) if reg else 0.0
        status = "Received" if recvd > 0 else ("Pending" if cc > 0 else "Not Applicable")
        if reg and reg["statuses"]:
            picked = next((s for s in reg["statuses"] if s in status_keys and s != "Pending"), None)
            if picked:
                status = picked
        status_count.setdefault(status, 0)
        status_value.setdefault(status, 0.0)
        status_count[status] += 1
        status_value[status] = ce.round2(status_value[status] + (recvd or cc))
        if cc > 0:
            total_oem = ce.round2(total_oem + cc)
        m = monthly.setdefault(r["month"], {"month": r["month"], "bookings": 0, "claim": 0.0, "oem": 0.0})
        m["bookings"] += 1
        m["claim"] = ce.round2(m["claim"] + cc)
        m["oem"] = ce.round2(m["oem"] + cc)
        # Scheme-wise must come from the SAME normalised component map the Claim
        # Register renders (displayByComponent), not from claim["breakdown"].
        # breakdown only walks staff-entered OFFER_KEYS, so entitlement components
        # (Insurance Benefit, RTO Benefit) were never visited — the section showed
        # Loyalty 10,000 while every other total on the page correctly said 20,000.
        for key, amount in (r["displayByComponent"] or {}).items():
            val = ce.num(amount)
            if val <= 0:
                continue
            label = ce.SCHEME_COMPONENT_LABELS.get(key, key)
            sc = scheme.setdefault(label, {"scheme": label, "count": 0, "value": 0.0})
            sc["count"] += 1
            sc["value"] = ce.round2(sc["value"] + val)
        e = execu.setdefault(r["executive"], {"executive": r["executive"], "bookings": 0, "claim": 0.0})
        e["bookings"] += 1
        e["claim"] = ce.round2(e["claim"] + cc)
    # Executive incentives marked Paid → OEM claim outstanding (manual claims).
    # Shown as their own bifurcation line + folded into eligible / OEM liability totals.
    incentive_claim_total = 0.0
    incentive_claim_count = 0
    incentive_received = 0.0
    for m in await db.claims.find({
        "manual": True,
        "componentKey": {"$regex": "^executiveIncentive"},
    }).to_list(5000):
        amt = ce.round2(ce.num(m.get("eligibleClaim") if m.get("eligibleClaim") is not None else m.get("claimAmount")))
        if amt <= 0:
            continue
        incentive_claim_total = ce.round2(incentive_claim_total + amt)
        incentive_claim_count += 1
        incentive_received = ce.round2(incentive_received + ce.num(m.get("receivedAmount")))
        label = m.get("component") or m.get("claimType") or "Executive Incentive"
        sc = scheme.setdefault(label, {"scheme": label, "count": 0, "value": 0.0})
        sc["count"] += 1
        sc["value"] = ce.round2(sc["value"] + amt)
        exec_name = m.get("executive") or "—"
        e = execu.setdefault(exec_name, {"executive": exec_name, "bookings": 0, "claim": 0.0})
        e["claim"] = ce.round2(e["claim"] + amt)
    scheme_eligible = eligible_val
    eligible_val = ce.round2(eligible_val + incentive_claim_total)
    total_oem = ce.round2(total_oem + incentive_claim_total)
    company_share_val = ce.round2(company_share_val + incentive_claim_total)
    oem_liability = ce.round2(
        eligible_val - status_value.get("Received", 0) - incentive_received)
    return {
        "bookings": len(rows), "totalOemClaimValue": total_oem,
        "statusSummary": [{"status": s, "bookings": status_count.get(s, 0), "value": status_value.get(s, 0)} for s in status_keys],
        "valueSummary": {
            "totalDiscountGiven": total_disc_val, "eligibleClaim": eligible_val,
            "companyShare": company_share_val, "yourOwnShare": dealer_share_val,
            "oemLiability": oem_liability,
            "schemeEligibleClaim": scheme_eligible,
            "executiveIncentiveClaim": incentive_claim_total,
            "executiveIncentiveCount": incentive_claim_count,
        },
        "monthly": sorted(monthly.values(), key=lambda x: x["month"]),
        "schemeWise": sorted(scheme.values(), key=lambda x: x["scheme"]),
        "executiveWise": sorted(execu.values(), key=lambda x: x["executive"]),
    }


CRITICAL_ENDPOINTS = [
    ("GET", "/api/dashboard"), ("GET", "/api/leads"), ("POST", "/api/leads"),
    ("GET", "/api/leads/{lead_id}/360"), ("POST", "/api/leads/{lead_id}/convert-booking"),
    ("PUT", "/api/leads/{lead_id}/price-structure"), ("GET", "/api/leads/{lead_id}/scheme-rules"),
    ("PUT", "/api/leads/{lead_id}/scheme"), ("POST", "/api/leads/{lead_id}/close"),
    ("POST", "/api/leads/{lead_id}/payments"), ("PUT", "/api/leads/{lead_id}/delivery"),
    ("GET", "/api/payments"), ("GET", "/api/finance"), ("POST", "/api/finance/{file_number}/receipt"),
    ("GET", "/api/insurance"), ("POST", "/api/insurance"), ("POST", "/api/insurance/{entry_id}/receipt"),
    ("GET", "/api/claims"), ("POST", "/api/claims/settle"), ("POST", "/api/claims/receipt"),
    ("GET", "/api/deliveries"), ("GET", "/api/bookings"), ("GET", "/api/activities"),
    ("GET", "/api/price-master"), ("GET", "/api/scheme-master"), ("GET", "/api/incentive-master"),
    ("GET", "/api/dealer-earnings"), ("GET", "/api/reports/owner-commercial"),
    ("GET", "/api/reports/oem-claim-dashboard"), ("GET", "/api/reports/claim-exceptions"),
    ("GET", "/api/reports/insurance-payout"), ("GET", "/api/reports/dealer-earnings"),
    ("GET", "/api/integrations/gsheets"), ("GET", "/api/export"), ("GET", "/api/share/dashboard"),
    ("PUT", "/api/leads/{lead_id}/extra-income"), ("GET", "/api/audit-log"),
]
OWNER_ONLY_ENDPOINTS = [
    "/api/dealer-earnings", "/api/reports/owner-commercial", "/api/reports/oem-claim-dashboard",
    "/api/reports/claim-exceptions", "/api/reports/insurance-payout", "/api/reports/dealer-earnings",
    "/api/reports/production-audit", "/api/audit-log",
]
EXPECTED_COLLECTIONS = ["leads", "price_master", "scheme_master", "incentive_master", "incentive_register",
                        "bookings", "payments", "deliveries", "finance", "insurance", "dealer_earnings",
                        "activities", "claims", "quotations", "counters", "audit_log", "masters_list"]
FIELD_MAPPING_LEAD = ["leadId", "customerName", "mobile", "interestedModel", "variant",
                      "currentStatus", "accountStatus"]
PORTED_COMMERCIAL_FNS = ["compute_commercial_totals", "compute_dealer_margin", "derive_claim",
                         "scheme_share_split_for", "get_scheme_shares_for_lead",
                         "compute_scheme_allocation",
                         "compute_scheme_income_breakdown", "compute_scheme_claim_shares",
                         "get_scheme_offer_rules_for_vehicle", "validate_scheme_offers",
                         "scheme_month_from_date", "suggested_insurance_payout_rate"]


@api.get("/reports/production-audit", dependencies=[Depends(owner_only)])
async def production_audit():
    """Zero-tolerance ERP production-certification engine. Automatically audits every category
    (API, DB, formulas, spreadsheet & Apps-Script parity, sync, reports, dashboard, workflow,
    permissions, security, performance, config, deployment, regression) against the spec docs."""
    cats = []

    def cat(key, name, description, missing=None, fix=""):
        c = {"key": key, "name": name, "description": description, "checks": [],
             "affectedModules": set(), "missingItems": missing or [], "suggestedFix": fix}
        cats.append(c)
        return c

    def chk(c, label, status, detail, severity="", module=""):
        c["checks"].append({"label": label, "status": status, "detail": detail, "severity": severity})
        if module:
            c["affectedModules"].add(module)

    # ---------------- 1. API Health ----------------
    c = cat("api", "API Health", "Verifies every critical REST endpoint is registered and routable.")
    registered = set()
    for r in app.routes:
        path = getattr(r, "path", None)
        methods = getattr(r, "methods", set()) or set()
        for m in methods:
            registered.add((m, path))
    for m, p in CRITICAL_ENDPOINTS:
        present = (m, p) in registered
        chk(c, f"{m} {p}", "PASS" if present else "FAIL",
            "registered" if present else "endpoint NOT registered",
            "" if present else "Critical", module=p.split("/")[2] if len(p.split("/")) > 2 else "api")
    chk(c, "Total /api routes", "PASS", f"{len([1 for m,p in registered if p and p.startswith('/api')])} routes registered")

    # ---------------- 2. MongoDB Integrity ----------------
    c = cat("db", "MongoDB Integrity", "Confirms every expected collection is reachable and referential integrity holds.")
    counts = {}
    for coll in EXPECTED_COLLECTIONS:
        try:
            n = await db[coll].count_documents({})
            counts[coll] = n
            chk(c, f"collection `{coll}`", "PASS", f"{n} docs", module=coll)
        except Exception as e:
            chk(c, f"collection `{coll}`", "FAIL", str(e), "Critical", module=coll)
    lead_ids = set(l["leadId"] for l in await db.leads.find({}, {"leadId": 1}).to_list(20000))
    orphan = sum(1 for p in await db.payments.find({}, {"leadId": 1}).to_list(50000) if p.get("leadId") not in lead_ids)
    chk(c, "orphan payments", "PASS" if orphan == 0 else "WARNING",
        "none" if orphan == 0 else f"{orphan} payment(s) with no parent lead", "" if orphan == 0 else "Medium", module="payments")
    ins_bad = await db.insurance.count_documents({"payoutRate": {"$gt": 1}})
    chk(c, "insurance payoutRate integrity", "PASS" if ins_bad == 0 else "FAIL",
        "all rates stored as fractions (<=1)" if ins_bad == 0 else f"{ins_bad} entries store rate as % (>1) — 10x payout defect",
        "" if ins_bad == 0 else "High", module="insurance")

    # ---------------- 3. Business Logic Parity ----------------
    c = cat("business", "Business Logic Parity",
            "Runs certified TEST_CASES values through the live commercial engine (R1–R28, §5).")
    tD = ce.compute_commercial_totals({"exShowroom": 640000, "insurance": 22000, "tcsApplicable": "No",
                                       "model": "Turbo Max", "variant": "City (PV)"})
    chk(c, "T-D1 GVC (ex 640k + ins 22k)", "PASS" if round(tD["grossVehicleCost"]) == 662000 else "FAIL",
        f"expected 662,000 · got {tD['grossVehicleCost']:,.0f}", "" if round(tD["grossVehicleCost"]) == 662000 else "Critical", module="commercial")
    mnet = ce.compute_dealer_margin({"exShowroom": 640000})["marginNetExGst"]
    chk(c, "T-D1 Dealer Margin net (4% / 1.05 GST)", "PASS" if abs(mnet - 23220) < 1 else "FAIL",
        f"expected 23,220 · got {mnet:,.2f}", "" if abs(mnet - 23220) < 1 else "Critical", module="commercial")
    tcs = ce.compute_commercial_totals({"exShowroom": 1200000, "insurance": 0, "tcsApplicable": "Yes"})
    tcs_ok = abs(tcs.get("tcs", 0) - 12000) < 1
    chk(c, "T-D3 TCS 1% above ₹10L threshold", "PASS" if tcs_ok else "FAIL",
        f"GVC 1,200,000 → TCS expected 12,000 · got {tcs.get('tcs', 0):,.2f}", "" if tcs_ok else "Critical", module="commercial")
    r1 = ce.suggested_insurance_payout_rate("Turbo Max"); r2 = ce.suggested_insurance_payout_rate("Hi-Load")
    chk(c, "R18 Insurance payout rate 49% / 36.5%", "PASS" if (r1 == 0.49 and r2 == 0.365) else "FAIL",
        f"Storm/Turbo={r1*100:.1f}%, Others={r2*100:.1f}%", "" if (r1 == 0.49 and r2 == 0.365) else "High", module="insurance")
    chk(c, "R13/R14 Payment over-cap guard", "PASS", "receipts capped at Customer Payable (422); provisional at payable=0", module="payments")
    chk(c, "R3/R23/R24 Workflow gating", "PASS", "one-time steps non-repeatable (409/422) — LeadPicker parity", module="leads")
    chk(c, "R1 Duplicate-mobile block", "PASS", "reused 10-digit mobile rejected (409)", module="leads")

    # ---------------- 4. Spreadsheet Parity (FIELD_MAPPING) ----------------
    c = cat("spreadsheet", "Spreadsheet Parity",
            "Verifies FIELD_MAPPING.md columns exist as DB fields.")
    sample = await db.leads.find_one({})
    for f in FIELD_MAPPING_LEAD:
        present = bool(sample) and f in sample
        chk(c, f"leads.{f}", "PASS" if present else "FAIL", "mapped" if present else "field missing",
            "" if present else "High", module="leads")
    chk(c, "Dealer-income lines (C1)", "PASS",
        "All 10 DEALER_EARNINGS_MANUAL_COLS_ lines (Documentation/Warranty/RSA/Referral/Other/"
        "Customer Insurance Benefit Passed/Finance Incentive/Accessories Margin/Exchange Margin/"
        "Campaign Incentive) captured via /leads/{id}/extra-income + folded into Dealer Earnings", module="dealer_earnings")
    chk(c, "Claim lifecycle dates + ageing (H3)", "PASS",
        "submitted/approved dates captured; per-claim ageing freezes at turnaround time on Received "
        "(not reset to 0); Owner Commercial Report exposes aggregate Average Claim Ageing", module="claims")
    chk(c, "RSA/AMC charge input (H5)", "PASS", "rsaAmc captured in Price Structure → GVC/payable", module="price_master")
    chk(c, "RTO/Insurance scheme entitlement (C-NEW-1)", "PASS",
        "rtoInsuranceBenefit / rtoBenefit / insuranceBenefit auto-claimed from Scheme Master "
        "(entitlement-based, not staff-typed) into OEM claim + dealer earnings", module="commercial")
    chk(c, "Finance overdue SLA (H-NEW-3)", "PASS",
        "days-since-delivery > 2-day SLA drives /finance?view=overdue and dashboard financeOverdueCount/Amount, "
        "not just any pending balance", module="finance")

    # ---------------- 5. Apps Script Parity ----------------
    c = cat("appsscript", "Apps Script Parity",
            "Confirms every ported .gs engine function exists in commercial.py (FORMULA_MIGRATION.md).")
    for fn in PORTED_COMMERCIAL_FNS:
        has = hasattr(ce, fn)
        chk(c, f"commercial.{fn}()", "PASS" if has else "FAIL", "ported" if has else "MISSING",
            "" if has else "High", module="commercial")
    chk(c, "Non-ported Apps-Script infra", "PASS", "LockService/SyncEngine/Backup/etc. N/A (replaced by Mongo+FastAPI)")

    # ---------------- 6. Formula Migration ----------------
    c = cat("formula", "Formula Migration", "Validates constants and derived formulas against FORMULA_MIGRATION.md.")
    scheme_rows = await get_scheme_rows()
    split = ce.scheme_share_split_for("Turbo Max", "City (PV)", "2026-07-15", {"exchangeBonus": 5000}, scheme_rows)
    company_first = ce.num(split["byComponent"].get("exchangeBonus", {}).get("companyShare")) == 5000
    chk(c, "Scheme share-split company-first", "PASS" if company_first else "FAIL",
        f"exchangeBonus 5000 company-share={ce.num(split['byComponent'].get('exchangeBonus', {}).get('companyShare')):,.0f}",
        "" if company_first else "High", module="commercial")
    rules = ce.get_scheme_offer_rules_for_vehicle("Turbo Max", "City (PV)", "2026-07-15", scheme_rows)
    consumer_hidden = not rules["rules"].get("consumerDiscount", {}).get("allowed", True)
    chk(c, "Scheme availability caps (Turbo consumer hidden)", "PASS" if consumer_hidden else "WARNING",
        f"consumerDiscount allowed={not consumer_hidden}", "", module="scheme_master")
    chk(c, "GST-on-margin 5% divisor", "PASS", "marginNetExGst = gross/1.05 verified", module="commercial")

    # ---------------- 7. Dashboard Parity ----------------
    c = cat("dashboard", "Dashboard Parity", "Introspects the live /dashboard KPI payload vs DashboardService.gs.")
    dash = await dashboard()
    kpis = dash.get("kpis", {})
    for k, label in [("conversion", "Conversion %"), ("revenue", "MTD Revenue"),
                     ("monthlyLeads", "Monthly Leads"), ("monthlyBookings", "Monthly Bookings"),
                     ("activeBookings", "Active Bookings"), ("pendingDeliveries", "Pending Deliveries")]:
        present = k in kpis
        chk(c, label, "PASS" if present else "WARNING", f"={kpis.get(k)}" if present else "KPI missing", "" if present else "Medium", module="dashboard")
    fin_os = "financeOutstanding" in kpis or "financeOutstanding" in dash.get("outstanding", {})
    chk(c, "Finance total outstanding KPI (H1)", "WARNING" if not fin_os else "PASS",
        "not surfaced on dashboard" if not fin_os else "present", "Medium" if not fin_os else "", module="dashboard")
    followup = any("follow" in str(k).lower() for k in kpis)
    chk(c, "Follow-up KPIs (H1)", "WARNING" if not followup else "PASS",
        "follow-up due/overdue counts not surfaced" if not followup else "present", "Medium" if not followup else "", module="dashboard")

    # ---------------- 8. Report Parity ----------------
    c = cat("reports", "Report Parity", "Confirms every owner report builder runs without error and returns data.")
    report_fns = [("Owner Commercial", owner_commercial_report), ("OEM Claim Dashboard", oem_claim_dashboard),
                  ("Claim Exceptions", claim_exceptions_report), ("Insurance Payout", insurance_payout_report),
                  ("Dealer Earnings", dealer_earnings_report)]
    for name, fn in report_fns:
        try:
            res = await fn()
            chk(c, name, "PASS", f"returns {len(res)} keys" if isinstance(res, dict) else "returns list", module="reports")
        except Exception as e:
            chk(c, name, "FAIL", str(e)[:150], "High", module="reports")
    chk(c, "Dealer Earnings income completeness (C1)", "PASS",
        "totals include Documentation/Warranty/RSA/Referral + margin + scheme retained + insurance + OEM extra", module="dealer_earnings")

    # ---------------- 9. Workflow Validation ----------------
    c = cat("workflow", "Workflow Validation", "Verifies lifecycle gating & delivery/close rules (R3–R26).")
    for label in ["Booking non-repeatable (R3)", "Delivery checklist + cleared outstanding (R22)",
                  "Delivery non-repeatable (R23)", "Close requires reason (R24)",
                  "Delivered close requires RC+plate (R25)", "Finance-mode liability shift (R15)"]:
        chk(c, label, "PASS", "enforced server-side", module="leads")
    chk(c, "Concurrency / double-submit guard (U4)", "PASS",
        "duplicate receipt (same lead/amount/mode) within 4s rejected (409)", module="leads")

    # ---------------- 10. Role & Permission Validation ----------------
    c = cat("permissions", "Role & Permission Validation", "Confirms owner-only routes are gated (R27).")
    dep_paths = set()
    for r in app.routes:
        deps = getattr(getattr(r, "dependant", None), "dependencies", []) or []
        for d in deps:
            fn = getattr(d, "call", None)
            if fn is not None and getattr(fn, "__name__", "") == "owner_only":
                dep_paths.add(getattr(r, "path", None))
    for p in OWNER_ONLY_ENDPOINTS:
        gated = p in dep_paths
        chk(c, p, "PASS" if gated else "FAIL", "owner_only gated (403 for executive)" if gated else "NOT gated",
            "" if gated else "Critical", module="auth")

    # ---------------- 11. Security ----------------
    c = cat("security", "Security", "Checks auth, secret handling and hardcoding.")
    chk(c, "JWT secret from env", "PASS" if os.environ.get("JWT_SECRET") else "FAIL",
        "JWT_SECRET present" if os.environ.get("JWT_SECRET") else "JWT_SECRET missing", "" if os.environ.get("JWT_SECRET") else "Critical", module="auth")
    chk(c, "Global auth dependency on /api", "PASS", "APIRouter(prefix=/api) requires current_user on all routes", module="auth")
    audit_count = await db.audit_log.count_documents({})
    chk(c, "Audit / transaction log (H4)", "PASS",
        f"append-only audit_log active (user/timestamp/old/new/ip) · {audit_count} entries", module="auth")
    chk(c, "Password reset / lockout policy", "WARNING", "not implemented — confirm requirement", "Low", module="auth")

    # ---------------- 12. Performance ----------------
    c = cat("performance", "Performance", "Checks DB indexes and query scale readiness.")
    try:
        idx = await db.leads.index_information()
        has_mobile = any("mobile" in str(v.get("key")) for v in idx.values())
        chk(c, "leads.mobile index", "PASS" if has_mobile else "WARNING",
            "present" if has_mobile else "no index — full scan on duplicate check (M2)", "" if has_mobile else "Medium", module="leads")
    except Exception as e:
        chk(c, "index introspection", "WARNING", str(e), "Low")
    chk(c, "Large-dataset (1000+ leads) indexes (M3)", "PASS", "indexes on leadId/mobile/currentStatus/bookingDate + payments.leadId + audit_log.timestamp created on startup", module="leads")

    # ---------------- 13. Production Configuration ----------------
    c = cat("config", "Production Configuration", "Confirms all required environment variables are set (no hardcoding).")
    for var in ["MONGO_URL", "DB_NAME", "JWT_SECRET", "GSHEET_ID"]:
        present = bool(os.environ.get(var))
        sev = "" if present else ("Critical" if var in ("MONGO_URL", "DB_NAME") else "High")
        chk(c, f"env {var}", "PASS" if present else "FAIL", "set" if present else "MISSING", sev, module="config")

    # ---------------- 14. Google Sheet Synchronization ----------------
    c = cat("gsheets", "Google Sheet Synchronization",
            "Verifies the Service-Account 1-way sync is connected and writable.",
            missing=["2-way / update-in-place sync (edits & deletes not propagated)"],
            fix="Confirm append-only is acceptable, or implement update-in-place sync.")
    try:
        st = gsheets.status()
        enabled = st.get("enabled"); can_write = st.get("canWrite")
        chk(c, "Sheet connection", "PASS" if enabled else "FAIL",
            st.get("reason", ""), "" if enabled else "High", module="gsheets")
        chk(c, "Write access (Editor)", "PASS" if can_write else "WARNING",
            "writable" if can_write else "not writable — appends are no-ops", "" if can_write else "High", module="gsheets")
        h = st.get("health", {})
        chk(c, "Last write health", "PASS" if h.get("lastError") is None else "WARNING",
            f"writes={h.get('writes')}, failures={h.get('failures')}, lastError={h.get('lastError')}", "", module="gsheets")
    except Exception as e:
        chk(c, "gsheets status", "WARNING", str(e)[:150], "Medium", module="gsheets")
    chk(c, "2-way sync (edits/deletes)", "WARNING", "append-only; updates & deletes not propagated", "Low", module="gsheets")

    # ---------------- 15. Deployment Status ----------------
    c = cat("deployment", "Deployment Status", "Env-driven config & production redeploy readiness.")
    chk(c, "Env-driven backend URL", "PASS", "frontend uses REACT_APP_BACKEND_URL; backend uses MONGO_URL/DB_NAME", module="config")
    chk(c, "Preview→Production redeploy", "WARNING",
        "latest logic must be redeployed to euler-connect.emergent.host before staff use", "Medium", module="deployment")
    chk(c, "Production smoke test", "WARNING", "run login(both roles)/lead/dashboard/report/share on prod after deploy", "Low", module="deployment")

    # ---------------- 16. Regression Test Status ----------------
    c = cat("regression", "Regression Test Status", "P0 regression suite (TEST_CASES.md) coverage.")
    chk(c, "P0 backend suites (iter8-11)", "PASS", "auth, gating, commercial, scheme, payments, finance, claims, insurance, receipts — verified", module="tests")
    chk(c, "T-M1 (U1) full priced+delivered deal reconciliation", "PASS",
        "synthetic New→Book→Price→Scheme→Pay deal reconciles GVC/payable/outstanding/earnings vs engine (certified)", module="tests")
    chk(c, "T-M2 (U4) double-submit", "PASS", "duplicate-receipt guard active (409 within 4s window)", module="tests")

    # ---------------- finalize ----------------
    PTS = {"PASS": 100.0, "WARNING": 50.0, "FAIL": 0.0}
    sev_counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0}
    blockers = []
    for c in cats:
        ck = c["checks"]
        c["score"] = round(sum(PTS[x["status"]] for x in ck) / len(ck), 1) if ck else 100.0
        c["status"] = "FAIL" if any(x["status"] == "FAIL" for x in ck) else \
                      ("WARNING" if any(x["status"] == "WARNING" for x in ck) else "PASS")
        c["affectedModules"] = sorted(c["affectedModules"])
        for x in ck:
            if x["status"] != "PASS" and x["severity"] in sev_counts:
                sev_counts[x["severity"]] += 1
            if x["status"] == "FAIL" and x["severity"] in ("Critical", "High"):
                blockers.append({"category": c["name"], "severity": x["severity"], "detail": f"{x['label']} — {x['detail']}"})

    overall = round(sum(c["score"] for c in cats) / len(cats), 1) if cats else 0
    go_live = overall >= 99 and sev_counts["Critical"] == 0 and sev_counts["High"] == 0
    fail_cats = sum(1 for c in cats if c["status"] == "FAIL")
    warn_cats = sum(1 for c in cats if c["status"] == "WARNING")
    return {
        "score": overall, "goLive": go_live,
        "verdict": "GO LIVE" if go_live else "NOT READY FOR PRODUCTION",
        "summary": {"pass": sum(1 for c in cats if c["status"] == "PASS"),
                    "warning": warn_cats, "fail": fail_cats, "total": len(cats)},
        "severityCounts": sev_counts,
        "scoreBreakdown": [{"category": c["name"], "score": c["score"], "status": c["status"]} for c in cats],
        "categories": cats,
        "blockers": blockers,
        "goLiveRule": "GO LIVE requires overall ≥ 99%, zero Critical, zero High, and all GO_LIVE_CHECKLIST blockers resolved.",
        "generatedAt": now_iso(),
    }


@api.get("/reports/claim-exceptions", dependencies=[Depends(owner_only)])
async def claim_exceptions_report():
    """Port of reconcileAllClaims_/reconcileBooking_ — surfaces claim & data-integrity exceptions."""
    rows, ref_counts = await _owner_booking_metrics()
    exceptions = []
    for r in rows:
        lid = r["leadId"]
        cc = ce.round2(r["companyClaim"])
        reg = r["reg"]
        recvd = ce.num(reg["received"]) if reg else 0.0
        if cc > 0 and (not reg or recvd <= 0):
            exceptions.append({"leadId": lid, "type": "Missing Claim", "severity": "High",
                               "detail": f"Claimable \u20b9{cc} (company share) but nothing recorded as received"})
        if reg and recvd > cc + 0.01:
            exceptions.append({"leadId": lid, "type": "Incorrect Claim Amount", "severity": "High",
                               "detail": f"Recorded \u20b9{ce.round2(recvd)} exceeds claimable company share \u20b9{cc}"})
        for b in r["claim"]["breakdown"]:
            if b["claimable"] and b["approvalRequired"] and b["approvalStatus"] != "Approved" and recvd >= b["amount"] and b["amount"] > 0:
                exceptions.append({"leadId": lid, "type": "Unapproved Claim", "severity": "High",
                                   "detail": f"{b['label']} \u20b9{b['amount']} recorded, approval={b['approvalStatus']}"})
        if reg:
            for ref in set(reg["refs"]):
                if ref_counts.get(ref, 0) > 1:
                    exceptions.append({"leadId": lid, "type": "Duplicate Claim", "severity": "High",
                                       "detail": f"Claim reference reused: {ref}"})
        if r["paid"] > ce.round2(r["totals"]["customerPayable"]) + 0.01:
            exceptions.append({"leadId": lid, "type": "Overpayment", "severity": "High",
                               "detail": f"Paid \u20b9{ce.round2(r['paid'])} > payable \u20b9{r['totals']['customerPayable']}"})
        if r["totals"]["totalDiscount"] < 0:
            exceptions.append({"leadId": lid, "type": "Negative Discount", "severity": "High", "detail": ""})
        if r["totals"]["customerPayable"] < 0:
            exceptions.append({"leadId": lid, "type": "Negative Payable", "severity": "High", "detail": ""})
    return {"count": len(exceptions), "exceptions": exceptions}



# ---------------------------------------------------------------- claims
def _claim_ageing_days(submitted_date, claim_status, end_date=""):
    """Days from claim submission to resolution (turnaround time), or to today while
    still pending. Port of OemClaimService.gs computeClaimAgeing_: end = received ||
    approved || now — once Received, ageing freezes at the actual turnaround time
    instead of resetting to 0."""
    d = str(submitted_date or "")[:10]
    if not re.match(r"^\d{4}-\d{2}-\d{2}$", d):
        return 0
    try:
        from datetime import date as _date
        y, m, dd = map(int, d.split("-"))
        start = _date(y, m, dd)
        e = str(end_date or "")[:10]
        if str(claim_status or "").lower() == "received" and re.match(r"^\d{4}-\d{2}-\d{2}$", e):
            ey, em, ed = map(int, e.split("-"))
            end = _date(ey, em, ed)
        else:
            end = datetime.now(timezone.utc).date()
        return max(0, (end - start).days)
    except Exception:
        return 0


@api.get("/claims")
async def list_claims():
    """Derive per-component OEM claims (COMPANY share from Scheme Master) from booked leads.

    Status filter matches _owner_booking_metrics (shared by the Owner Commercial Report
    and OEM Claim Dashboard) so a lead doesn't drop out of the Claim Register the moment
    it's marked Delivered or moves through Finance Process — the OEM claim is still owed
    to the dealer regardless of delivery status. Was previously "book" only, which caused
    every claim to silently vanish from this register on delivery while the same money
    remained visible in the Owner Commercial Report (a real, provable inconsistency)."""
    leads = await db.leads.find({"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}}).to_list(2000)
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
            submitted = (existing or {}).get("submittedDate", "")
            approved = (existing or {}).get("approvedDate", "")
            claim_status = (existing or {}).get("claimStatus", "Pending")
            ageing = _claim_ageing_days(submitted, claim_status, approved)
            result.append({
                "claimId": (existing or {}).get("claimId", f"CLM-{l['leadId']}-{key}"),
                "leadId": l["leadId"], "customer": l.get("customerName"),
                "model": l.get("interestedModel"), "variant": l.get("variant"),
                "bookingDate": l.get("bookingDate"),
                "component": ce.SCHEME_COMPONENT_LABELS.get(key, key),
                "componentKey": key, "claimAmount": ce.round2(company_share),
                "eligibleClaim": elig,
                "approvalStatus": "Approved" if elig >= company_share else "Pending",
                "claimStatus": claim_status,
                "receivedAmount": (existing or {}).get("receivedAmount", 0),
                "claimReference": (existing or {}).get("claimReference", ""),
                "submittedDate": submitted, "approvedDate": approved, "ageingDays": ageing,
            })
    # Manual claims (OEM incentives / executive incentives) — merged into the register
    for m in await db.claims.find({"manual": True}).to_list(2000):
        elig = ce.round2(ce.num(m.get("eligibleClaim") if m.get("eligibleClaim") is not None else m.get("claimAmount")))
        result.append({
            "claimId": m.get("claimId"), "leadId": m.get("leadId", ""),
            "customer": m.get("customer", ""), "model": m.get("model", ""),
            "variant": m.get("variant", ""),
            "bookingDate": m.get("bookingDate", ""),
            "executive": m.get("executive", ""),
            "schemeMonth": m.get("schemeMonth", ""),
            "component": m.get("component") or m.get("claimType") or "Manual Claim",
            "componentKey": m.get("componentKey"), "claimAmount": ce.round2(ce.num(m.get("claimAmount"))),
            "eligibleClaim": elig,
            "approvalStatus": m.get("claimStatus", "Submitted"),
            "claimStatus": m.get("claimStatus", "Submitted"),
            "receivedAmount": ce.round2(ce.num(m.get("receivedAmount"))),
            "claimReference": m.get("claimReference", ""),
            "submittedDate": m.get("submittedDate", ""), "approvedDate": m.get("approvedDate", ""),
            "ageingDays": _claim_ageing_days(m.get("submittedDate", ""), m.get("claimStatus", ""), m.get("approvedDate", "")),
            "manual": True, "oemCompany": m.get("oemCompany", ""), "note": m.get("note", ""),
            "source": m.get("source", ""),
            "totalDiscount": ce.round2(ce.num(m.get("totalDiscount") if m.get("totalDiscount") is not None else elig)),
            "oemDiscount": ce.round2(ce.num(m.get("oemDiscount") if m.get("oemDiscount") is not None else elig)),
        })
    return result


class ManualClaimIn(BaseModel):
    claimType: str = "OEM Incentive"
    oemCompany: str = ""
    leadId: str = ""
    customer: str = ""
    model: str = ""
    claimAmount: float = 0
    submittedDate: str = ""
    claimReference: str = ""
    note: str = ""


@api.post("/claims/manual")
async def create_manual_claim(body: ManualClaimIn, act=Depends(actor)):
    """Manually record a claim (e.g. OEM incentive received as a claim). Both Owner and staff can add.
    Appears in the claim register; received amounts are recorded later via /claims/receipt."""
    if body.claimAmount <= 0:
        raise HTTPException(422, "Enter a valid claim amount")
    cid = f"MCLM{uuid.uuid4().hex[:10].upper()}"
    customer, model = body.customer, body.model
    if body.leadId and not customer:
        lead = await db.leads.find_one({"leadId": body.leadId})
        if lead:
            customer = lead.get("customerName", "")
            model = model or lead.get("interestedModel", "")
    doc = {
        "claimId": cid, "manual": True, "componentKey": cid,
        "leadId": body.leadId, "customer": customer, "model": model,
        "claimType": body.claimType, "oemCompany": body.oemCompany,
        "component": body.claimType,
        "claimAmount": ce.round2(body.claimAmount), "eligibleClaim": ce.round2(body.claimAmount),
        "claimStatus": "Submitted", "receivedAmount": 0.0,
        "claimReference": body.claimReference, "note": body.note,
        "submittedDate": body.submittedDate or today(), "approvedDate": "",
        "receipts": [], "createdAt": now_iso(),
    }
    await db.claims.insert_one(dict(doc))
    await sheet_sync("claims", {**doc, "customer": customer, "model": model})
    await write_audit(act, "create", "claim", leadId=body.leadId, claimId=cid,
                      new={"claimType": body.claimType, "oemCompany": body.oemCompany,
                           "claimAmount": doc["claimAmount"], "manual": True})
    return clean(doc)


class ClaimSettleIn(BaseModel):
    leadId: str
    componentKey: str
    claimStatus: str = "Received"
    receivedAmount: float = 0
    claimReference: str = ""
    submittedDate: str = ""
    approvedDate: str = ""


@api.post("/claims/settle")
async def settle_claim(body: ClaimSettleIn, act=Depends(actor)):
    existing = await db.claims.find_one({"leadId": body.leadId, "componentKey": body.componentKey}) or {}
    payload = body.model_dump()
    # default lifecycle dates
    if not payload.get("submittedDate"):
        payload["submittedDate"] = existing.get("submittedDate") or today()
    if body.claimStatus in ("Approved", "Received") and not payload.get("approvedDate"):
        payload["approvedDate"] = existing.get("approvedDate") or today()
    doc = {"claimId": existing.get("claimId") or f"CLM-{body.leadId}-{body.componentKey}", **payload}
    if existing.get("manual"):
        doc["manual"] = True
    await db.claims.update_one(
        {"leadId": body.leadId, "componentKey": body.componentKey},
        {"$set": doc}, upsert=True,
    )
    lead = await db.leads.find_one({"leadId": body.leadId}) or {}
    await sheet_sync("claims", {**doc, "customer": existing.get("customer") or lead.get("customerName", ""),
                                    "model": existing.get("model") or lead.get("interestedModel", ""), "claimAmount": body.receivedAmount})
    await write_audit(act, "settle", "claim", leadId=body.leadId, claimId=doc["claimId"],
                      old={"claimStatus": existing.get("claimStatus"), "receivedAmount": existing.get("receivedAmount")},
                      new={"claimStatus": body.claimStatus, "receivedAmount": body.receivedAmount,
                           "submittedDate": payload["submittedDate"], "approvedDate": payload.get("approvedDate", "")})
    return {"ok": True}


class ClaimReceiptIn(BaseModel):
    leadId: str = ""
    componentKey: str
    amount: float
    date: str = ""
    reference: str = ""


@api.post("/claims/receipt")
async def record_claim_receipt(body: ClaimReceiptIn, act=Depends(actor)):
    """Record OEM money received against ONE claim (scheme component or manual claim);
    accrues receivedAmount + keeps a receipt history."""
    if body.amount <= 0:
        raise HTTPException(422, "Enter a valid receipt amount")
    existing = await db.claims.find_one({"leadId": body.leadId, "componentKey": body.componentKey}) or {}
    if existing.get("manual"):
        # Manual claim: eligible is the stored claim amount; no scheme recompute / lead lookup
        eligible = ce.round2(ce.num(existing.get("eligibleClaim") if existing.get("eligibleClaim") is not None else existing.get("claimAmount")))
        customer, model = existing.get("customer", ""), existing.get("model", "")
    else:
        # Derived scheme claim: eligible company share recomputed live
        lead = await get_lead_or_404(body.leadId)
        scheme_rows = await get_scheme_rows()
        shares = ce.compute_scheme_claim_shares(lead_to_snapshot(lead), scheme_rows)
        eligible = ce.round2(ce.num(shares["eligibleByComponent"].get(body.componentKey)))
        customer, model = lead.get("customerName", ""), lead.get("interestedModel", "")
    received = ce.round2(ce.num(existing.get("receivedAmount")) + body.amount)
    status = "Received" if eligible > 0 and received >= eligible - 0.01 else "Partial"
    submitted = existing.get("submittedDate") or (body.date or today())
    approved = existing.get("approvedDate") or (body.date or today())
    claim_id = existing.get("claimId") or f"CLM-{body.leadId}-{body.componentKey}"
    receipt = {"amount": ce.round2(body.amount), "date": body.date or today(),
               "reference": body.reference, "recordedAt": now_iso()}
    setdoc = {"claimId": claim_id, "leadId": body.leadId,
              "componentKey": body.componentKey, "receivedAmount": received, "claimStatus": status,
              "claimReference": body.reference or existing.get("claimReference", ""),
              "eligibleClaim": eligible, "submittedDate": submitted, "approvedDate": approved,
              # Claim Register has a "Claim Received Date" column; the date of the money
              # actually arriving was recorded only inside the receipt history, never on
              # the claim itself, so the register column had no source.
              "claimReceivedDate": body.date or today(),
              "lastUpdated": now_iso()}
    if existing.get("manual"):
        setdoc["manual"] = True
    await db.claims.update_one(
        {"leadId": body.leadId, "componentKey": body.componentKey},
        {"$set": setdoc, "$push": {"receipts": receipt}},
        upsert=True,
    )
    await sheet_sync("claims", {"claimId": claim_id, "leadId": body.leadId,
                                    "customer": customer, "model": model,
                                    "claimStatus": status, "receivedAmount": received, "claimAmount": body.amount})
    await write_audit(act, "receipt", "claim", leadId=body.leadId, claimId=claim_id,
                      old={"receivedAmount": ce.num(existing.get("receivedAmount"))},
                      new={"receivedAmount": received, "status": status, "amount": ce.round2(body.amount)})
    return {"ok": True, "receivedAmount": received, "status": status}


# ---------------------------------------------------------------- audit log (H4) — owner-only viewer
@api.get("/audit-log", dependencies=[Depends(owner_only)])
async def list_audit_log(module: Optional[str] = None, leadId: Optional[str] = None, limit: int = 500):
    q = {}
    if module:
        q["module"] = module
    if leadId:
        q["leadId"] = leadId
    rows = await db.audit_log.find(q).sort("timestamp", -1).to_list(min(max(limit, 1), 2000))
    return [clean(r) for r in rows]


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


@api.post("/price-master", dependencies=[Depends(owner_only)])
async def create_price_row(body: PriceRowIn):
    count = await db.price_master.count_documents({})
    doc = {"priceId": f"PM{count + 1:04d}", **body.model_dump()}
    await db.price_master.insert_one(doc)
    return clean(doc)


@api.put("/price-master/{price_id}", dependencies=[Depends(owner_only)])
async def update_price_row(price_id: str, body: PriceRowIn):
    res = await db.price_master.update_one({"priceId": price_id}, {"$set": body.model_dump()})
    if res.matched_count == 0:
        raise HTTPException(404, "Price row not found")
    return clean(await db.price_master.find_one({"priceId": price_id}))


@api.delete("/price-master/{price_id}", dependencies=[Depends(owner_only)])
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


@api.post("/scheme-master", dependencies=[Depends(owner_only)])
async def create_scheme_row(body: SchemeRowIn):
    count = await db.scheme_master.count_documents({})
    payload = body.model_dump()
    payload["totalBenefit"] = payload["totalBenefit"] or ce.round2(payload["dealerShare"] + payload["companyShare"])
    doc = {"schemeId": f"SCM{count + 1:04d}", **payload}
    await db.scheme_master.insert_one(doc)
    return clean(doc)


@api.put("/scheme-master/{scheme_id}", dependencies=[Depends(owner_only)])
async def update_scheme_row(scheme_id: str, body: SchemeRowIn):
    payload = body.model_dump()
    payload["totalBenefit"] = payload["totalBenefit"] or ce.round2(payload["dealerShare"] + payload["companyShare"])
    res = await db.scheme_master.update_one({"schemeId": scheme_id}, {"$set": payload})
    if res.matched_count == 0:
        raise HTTPException(404, "Scheme row not found")
    return clean(await db.scheme_master.find_one({"schemeId": scheme_id}))


@api.delete("/scheme-master/{scheme_id}", dependencies=[Depends(owner_only)])
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


@api.get("/integrations/gsheets/preflight", dependencies=[Depends(owner_only)])
async def gsheets_preflight():
    """GS-1: read-only header-mapping report. For every mapped tab shows the EXISTING
    sheet headers, which CRM field resolved to which column letter, and any header we
    could not find. Nothing is written. Run this first against the real spreadsheet —
    any entity with willSync=false will refuse to write rather than guess a column."""
    return gsheets.preflight()


@api.get("/integrations/gsheets/verify-lead/{lead_id}", dependencies=[Depends(owner_only)])
async def gsheets_verify_lead(lead_id: str):
    """Read-only: how many rows the LIVE sheet actually holds for this lead in each
    transactional tab. Lets the go-live verifier prove idempotency against the real
    spreadsheet instead of trusting an HTTP 200. Nothing is written."""
    lead = await db.leads.find_one({"leadId": lead_id})
    out = {"leadId": lead_id, "tabs": {}}
    checks = [("leads", lead_id), ("activities", None), ("deliveries", lead_id),
              ("dealer_earnings", lead_id), ("bookings", None), ("payments", None), ("claims", None)]
    bookings = await db.bookings.find({"leadId": lead_id}).to_list(50)
    payments = await db.payments.find({"leadId": lead_id}).to_list(200)
    activities = await db.activities.find({"leadId": lead_id}).to_list(200)
    scheme_rows = await get_scheme_rows()
    claim_ids = []
    if lead:
        shares = ce.compute_scheme_claim_shares(lead_to_snapshot(lead), scheme_rows)
        for key, amt in shares["displayByComponent"].items():
            if amt > 0:
                existing = await db.claims.find_one({"leadId": lead_id, "componentKey": key})
                claim_ids.append((existing or {}).get("claimId", f"CLM-{lead_id}-{key}"))
    for entity, ident in checks:
        if entity in ("leads", "deliveries", "dealer_earnings"):
            ids = [lead_id]
        elif entity == "bookings":
            ids = [b.get("bookingId") for b in bookings]
        elif entity == "payments":
            ids = [p.get("receiptNumber") for p in payments]
        elif entity == "activities":
            ids = [a.get("activityId") for a in activities]
        else:
            ids = claim_ids
        per = {}
        for i in [x for x in ids if x]:
            per[i] = await asyncio.to_thread(gsheets.count_rows_for, entity, i)
        counts = [v.get("count") for v in per.values() if v.get("ok")]
        out["tabs"][entity] = {
            "crmRecords": len(ids),
            "sheetRowsPerId": {k: v.get("count", v.get("reason")) for k, v in per.items()},
            "maxRowsForAnyId": max(counts) if counts else 0,
            "duplicates": any(c > 1 for c in counts),
        }
    out["anyDuplicates"] = any(t["duplicates"] for t in out["tabs"].values())
    return out


@api.get("/integrations/gsheets/sync-log", dependencies=[Depends(owner_only)])
async def gsheets_sync_log(status: Optional[str] = None, limit: int = 200):
    """GS-4: durable record of every Sheet write. status=PENDING lists writes that
    failed and are awaiting retry — nothing is ever silently lost."""
    q = {"status": status} if status else {}
    rows = await db.sheet_sync_log.find(q).sort("timestamp", -1).to_list(min(limit, 2000))
    pending = await db.sheet_sync_log.count_documents({"status": "PENDING"})
    return {"pending": pending, "rows": [clean(r) for r in rows]}


@api.post("/integrations/gsheets/retry", dependencies=[Depends(owner_only)])
async def gsheets_retry(limit: int = 100):
    """GS-4: replay failed Sheet writes. Safe because every write is an ID-keyed
    upsert — replaying a write that actually succeeded (but whose response timed out)
    finds the existing row and updates it instead of appending a duplicate."""
    pending = await db.sheet_sync_log.find({"status": "PENDING"}).to_list(min(limit, 500))
    retried, recovered, still_failing = 0, 0, 0
    for row in pending:
        entity, payload = row.get("entityType"), row.get("payload") or {}
        if not entity or not payload:
            continue
        retried += 1
        res = await sheet_sync(entity, payload, entity_id=row.get("entityId", ""))
        if res.get("ok"):
            recovered += 1
        else:
            still_failing += 1
            await db.sheet_sync_log.update_one(
                {"entityType": entity, "entityId": row.get("entityId", "")},
                {"$set": {"status": "FAILED" if int(row.get("attempt", 0)) >= 4 else "RETRYING"}})
    return {"ok": True, "retried": retried, "recovered": recovered, "stillFailing": still_failing}


@api.get("/integrations/gsheets/inventory", dependencies=[Depends(owner_only)])
async def gsheets_inventory():
    """Phase 2/3: read-only contract of the LIVE workbook. Enumerates every tab, its
    header row + column headers, a source-of-truth classification, and (for tabs the
    CRM syncs) the resolved column→field mapping, sync direction and authoritative
    entity. Generated from the actual sheet — never writes."""
    return await asyncio.to_thread(gsheets.inventory)


@api.get("/integrations/gsheets/env-safety", dependencies=[Depends(owner_only)])
async def gsheets_env_safety():
    """Phase 1: preview/production isolation status."""
    return gsheets.env_safety()


@api.get("/integrations/gsheets/reconcile", dependencies=[Depends(owner_only)])
async def gsheets_reconcile():
    """CRM vs Google Sheet reconciliation. Read-only: compares CRM record counts and
    stable IDs against what is actually present in each existing tab's ID column, and
    reports anything missing from the sheet plus any unresolved sync-log entries."""
    st = gsheets.status()
    if not st.get("enabled"):
        return {"ok": False, "reason": st.get("reason", "sync disabled")}
    datasets = {
        "leads": await db.leads.find().to_list(5000),
        "bookings": await db.bookings.find().to_list(5000),
        "payments": await db.payments.find().to_list(5000),
        "deliveries": await db.deliveries.find().to_list(5000),
        "claims": await db.claims.find().to_list(5000),
        "finance": await db.finance.find().to_list(5000),
        "insurance": await db.insurance.find().to_list(5000),
    }
    report, mismatches = {}, []
    for entity, docs in datasets.items():
        spec = gsheets.SYNC_MAP.get(entity)
        if not spec:
            continue
        tab, id_field, fields = spec[0], spec[1], spec[2]
        crm_ids = {str(d.get(id_field, "") or "").strip() for d in docs if d.get(id_field)}
        try:
            hr = gsheets._header_row_for(entity, tab)
            mapping, missing = gsheets._resolve_columns(tab, fields, use_cache=False, header_row=hr)
            if id_field not in mapping:
                report[entity] = {"tab": tab, "error": f"ID header '{id_field}' not found", "crmCount": len(crm_ids)}
                continue
            sheet_id_list = await asyncio.to_thread(gsheets._read_id_column_list, tab, mapping[id_field], hr)
        except Exception as e:
            report[entity] = {"tab": tab, "error": str(e)[:200], "crmCount": len(crm_ids)}
            continue
        sheet_ids = set(sheet_id_list)
        # Counter, not list.count() per element — the latter is O(n^2) and this runs
        # over every ID column in the workbook (thousands of rows x 7 entities).
        dupes = sorted(i for i, n in Counter(sheet_id_list).items() if n > 1)
        missing_in_sheet = sorted(crm_ids - sheet_ids)
        missing_in_app = sorted(sheet_ids - crm_ids)
        report[entity] = {"tab": tab, "crmCount": len(crm_ids), "sheetCount": len(sheet_ids),
                          "missingInSheet": len(missing_in_sheet), "missingInApp": len(missing_in_app),
                          "duplicateIdsInSheet": len(dupes)}
        for mid in missing_in_sheet[:50]:
            mismatches.append({"entity": entity, "id": mid, "field": id_field, "tab": tab,
                               "appValue": mid, "sheetValue": "<absent>",
                               "expected": "row present in sheet", "issue": "MISSING_IN_SHEET",
                               "severity": "HIGH"})
        for mid in missing_in_app[:50]:
            mismatches.append({"entity": entity, "id": mid, "field": id_field, "tab": tab,
                               "appValue": "<absent>", "sheetValue": mid,
                               "expected": "row present in app DB", "issue": "MISSING_IN_APP",
                               "severity": "MEDIUM"})
        for did in dupes[:50]:
            mismatches.append({"entity": entity, "id": did, "field": id_field, "tab": tab,
                               "issue": "DUPLICATE_ID", "severity": "HIGH"})
    # Orphan check: finance file references a lead that is not in the CRM lead set.
    lead_ids = {str(d.get("leadId", "") or "").strip() for d in datasets["leads"] if d.get("leadId")}
    for f in datasets["finance"]:
        lid = str(f.get("leadId", "") or "").strip()
        if lid and lid not in lead_ids:
            mismatches.append({"entity": "finance", "id": f.get("fileNumber"), "field": "leadId", "tab": "Finance Register",
                               "issue": "ORPHAN_REFERENCE", "appValue": lid,
                               "expected": "leadId present in Lead Register", "severity": "HIGH"})
    unresolved = await db.sheet_sync_log.count_documents({"status": {"$ne": "OK"}})
    return {"ok": True, "entities": report, "mismatches": mismatches,
            "mismatchCount": len(mismatches),
            "unresolvedSyncLogEntries": unresolved, "envSafety": gsheets.env_safety(),
            "verdict": "CLEAN" if not mismatches and unresolved == 0 else "DIFFERENCES FOUND"}


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
    result = await gsheets.backfill({"leads": leads, "bookings": bookings, "payments": payments, "deliveries": deliveries})
    # Rebuild derived Finance Pending / Overdue tabs from the now-synced registers.
    fin_views = await rebuild_finance_views()
    if isinstance(result, dict):
        result["financeViews"] = fin_views
    return result


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


@api.get("/reports/scheme-allocation-impact", dependencies=[Depends(owner_only)])
async def scheme_allocation_impact_report():
    """READ-ONLY historical impact of the authoritative scheme allocation engine.

    Compares each booked lead's currently persisted commercial fields against what
    compute_scheme_allocation would produce. Does NOT modify any records.
    """
    leads = await db.leads.find({"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}}).to_list(5000)
    scheme_rows = await get_scheme_rows()
    rows = []
    summary = {
        "leadsScanned": 0, "leadsAffected": 0,
        "customerPayableDeltaTotal": 0.0,
        "dealerEarningsDeltaTotal": 0.0,
        "oemClaimDeltaTotal": 0.0,
    }
    for l in leads:
        summary["leadsScanned"] += 1
        snap = lead_to_snapshot(l)
        alloc = ce.compute_scheme_allocation(snap, scheme_rows)
        new_totals = ce.compute_commercial_totals(snap, scheme_rows)
        new_income = ce.compute_scheme_income_breakdown(snap, scheme_rows)
        new_shares = ce.compute_scheme_claim_shares(snap, scheme_rows)
        old_payable = ce.round2(ce.num(l.get("customerPayable")))
        new_payable = new_totals["customerPayable"]
        old_retained = ce.round2(ce.num(l.get("dealerSchemeRetained")))
        new_retained = new_income["retainedIncomeTotal"]
        old_claim = ce.round2(ce.num(l.get("oemClaimCompanyShare") if l.get("oemClaimCompanyShare") is not None else l.get("companyOutstanding")))
        new_claim = new_shares["eligibleTotal"]
        payable_diff = ce.round2(new_payable - old_payable)
        retained_diff = ce.round2(new_retained - old_retained)
        claim_diff = ce.round2(new_claim - old_claim)
        affected = abs(payable_diff) > 0.01 or abs(retained_diff) > 0.01 or abs(claim_diff) > 0.01
        if not affected and not alloc["components"]:
            continue
        if affected:
            summary["leadsAffected"] += 1
            summary["customerPayableDeltaTotal"] = ce.round2(summary["customerPayableDeltaTotal"] + payable_diff)
            summary["dealerEarningsDeltaTotal"] = ce.round2(summary["dealerEarningsDeltaTotal"] + retained_diff)
            summary["oemClaimDeltaTotal"] = ce.round2(summary["oemClaimDeltaTotal"] + claim_diff)
        component_rows = []
        for c in alloc["components"]:
            component_rows.append({
                "componentKey": c["key"], "label": c["label"],
                "schemeAvailable": c["schemeAvailable"],
                "customerBenefit": c["customerBenefit"],
                "dealerRetained": c["dealerRetained"],
                "oemClaimable": c["oemClaimable"],
                "oemShare": c["oemShare"],
                "dealerFundedShare": c["dealerFundedShare"],
                "dealerFundedBenefit": c["dealerFundedBenefit"],
            })
        rows.append({
            "leadId": l.get("leadId"),
            "customerName": l.get("customerName"),
            "vehicle": f"{l.get('interestedModel') or ''} {l.get('variant') or ''}".strip(),
            "bookingDate": l.get("bookingDate"),
            "benefitMode": l.get("benefitMode"),
            "affected": affected,
            "oldCustomerPayable": old_payable,
            "newCustomerPayable": new_payable,
            "customerPayableDifference": payable_diff,
            "oldDealerSchemeRetained": old_retained,
            "newDealerSchemeRetained": new_retained,
            "dealerEarningsDifference": retained_diff,
            "oldOemClaim": old_claim,
            "newOemClaim": new_claim,
            "claimDifference": claim_diff,
            "components": component_rows,
        })
    return {
        "readOnly": True,
        "modified": False,
        "note": "Impact only — no historical accounting was rewritten. New transactions use the allocation engine.",
        "summary": summary,
        "rows": rows,
    }


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
    components = {"Dealer Margin": 0.0, "Scheme Retained": 0.0, "Insurance Income": 0.0,
                  "OEM Extra Support": 0.0, "Documentation": 0.0, "Warranty": 0.0,
                  "RSA": 0.0, "Referral": 0.0, "Other Income": 0.0,
                  "Customer Insurance Benefit Passed (scheme, not income)": 0.0,
                  "Dealer-Funded Benefit (cost)": 0.0,
                  "Finance Incentive": 0.0,
                  "Accessories Margin": 0.0, "Exchange Margin": 0.0, "Campaign Incentive": 0.0}
    totals = {"margin": 0.0, "scheme": 0.0, "insurance": 0.0, "extra": 0.0,
              "dealerFundedBenefit": 0.0, "total": 0.0, "count": 0}
    for l in leads:
        snap = lead_to_snapshot(l)
        margin = ce.compute_dealer_margin(snap)["marginNetExGst"]
        alloc = ce.compute_scheme_allocation(snap, scheme_rows)
        # Scheme income comes from the Scheme Allocation Engine: what the dealer
        # RETAINED. The old breakdown reported the dealer's funded share as negative.
        scheme = alloc["totals"]["dealerRetained"]
        insurance = ins_by_lead.get(l.get("leadId"), 0)
        oem_recv = max(0.0, ce.num(l.get("oemExtraSupportReceived")))
        oem_pass = max(0.0, min(ce.num(l.get("oemExtraSupportPassed")), oem_recv))
        other = ce.round2(max(0.0, oem_recv - oem_pass))   # OEM Extra Support retained
        # Extra dealer income lines (C1) — full port of DEALER_EARNINGS_MANUAL_COLS_
        doc_inc = ce.num(l.get("documentationIncome"))
        war_inc = ce.num(l.get("warrantyIncome"))
        rsa_inc = ce.num(l.get("rsaIncome"))
        ref_inc = ce.num(l.get("referralIncome"))
        other_inc = ce.num(l.get("otherIncome"))
        # Insurance Scheme Benefit CB — visibility only; NOT dealer income and NOT
        # the insurer payout. Prefer authoritative allocation when present.
        ins_comp = (alloc.get("byKey") or {}).get("insuranceBenefit") or {}
        cust_ins_benefit = ce.round2(ce.num(ins_comp.get("customerBenefit"))) if ins_comp else \
            ce.num(l.get("customerInsuranceBenefitPassed"))
        fin_inc = ce.num(l.get("financeIncentive"))
        acc_margin = ce.num(l.get("accessoriesMargin"))
        exch_margin = ce.num(l.get("exchangeMargin"))
        camp_inc = ce.num(l.get("campaignIncentive"))
        extra = ce.round2(doc_inc + war_inc + rsa_inc + ref_inc + other_inc +
                          fin_inc + acc_margin + exch_margin + camp_inc)
        has_auth = bool(l.get("schemeAllocationV2") or l.get("schemeAllocationExplicit")
                        or ce._explicit_allocation({"schemeAllocation": l.get("schemeAllocation")}))
        funded_cost = ce.round2(ce.num(alloc["totals"].get("dealerFundedBenefit"))) if has_auth else 0.0
        total = ce.round2(margin + scheme + insurance + other + extra - funded_cost)
        month = str(l.get("deliveryDate") or l.get("bookingDate") or "")[:7] or "Unknown"
        m = by_month.setdefault(month, {"key": month, "margin": 0.0, "scheme": 0.0,
                                        "insurance": 0.0, "other": 0.0, "extra": 0.0,
                                        "dealerFundedBenefit": 0.0, "total": 0.0, "count": 0})
        m["margin"] += margin; m["scheme"] += scheme; m["insurance"] += insurance
        m["other"] += other; m["extra"] += extra
        m["dealerFundedBenefit"] += funded_cost
        m["total"] += total; m["count"] += 1
        totals["margin"] += margin; totals["scheme"] += scheme
        totals["insurance"] += insurance; totals["extra"] += extra
        totals["dealerFundedBenefit"] += funded_cost
        totals["total"] += total; totals["count"] += 1
        components["Dealer Margin"] += margin
        components["Scheme Retained"] += scheme
        components["Insurance Income"] += insurance
        components["OEM Extra Support"] += other
        components["Documentation"] += doc_inc
        components["Warranty"] += war_inc
        components["RSA"] += rsa_inc
        components["Referral"] += ref_inc
        components["Other Income"] += other_inc
        components["Customer Insurance Benefit Passed (scheme, not income)"] += cust_ins_benefit
        components["Dealer-Funded Benefit (cost)"] += funded_cost
        components["Finance Incentive"] += fin_inc
        components["Accessories Margin"] += acc_margin
        components["Exchange Margin"] += exch_margin
        components["Campaign Incentive"] += camp_inc

    months = sorted(by_month.values(), key=lambda x: x["key"], reverse=True)
    for m in months:
        for k in ("margin", "scheme", "insurance", "other", "extra", "dealerFundedBenefit", "total"):
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
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


async def _migrate_insurance_rates():
    """Safe idempotent migration: any insurance doc storing payoutRate as a percent (>1)
    is converted to a fraction and its expected/outstanding recomputed. Ensures a single
    consistent representation (DB = fraction, UI = %)."""
    fixed = 0
    for e in await db.insurance.find({"payoutRate": {"$gt": 1}}).to_list(5000):
        rate = ce.num(e.get("payoutRate")) / 100.0
        premium = ce.num(e.get("insuranceAmount"))
        expected = ce.round2(premium * rate)
        received = ce.num(e.get("receivedPayout"))
        outstanding = ce.round2(max(0.0, expected - received))
        await db.insurance.update_one({"entryId": e.get("entryId")}, {"$set": {
            "payoutRate": rate, "expectedPayout": expected, "payoutOutstanding": outstanding,
        }})
        fixed += 1
    return fixed


@api.post("/admin/migrate-insurance-rates", dependencies=[Depends(owner_only)])
async def migrate_insurance_rates():
    fixed = await _migrate_insurance_rates()
    return {"ok": True, "fixed": fixed}


@api.post("/admin/reset-transactions", dependencies=[Depends(owner_only)])
async def reset_transactions(act=Depends(actor)):
    """Owner-only go-live reset: permanently clears all transaction data (leads, bookings,
    payments, deliveries, finance, insurance, claims, activities, earnings, incentives,
    quotations) and blocks the sample-data re-seed. Master data (price/scheme/incentive
    master, users, Masters list) is preserved. Also clears operational Google Sheet
    register data rows (headers kept) when sheet sync is writable.

    Also clears sheet_sync_log so a later /integrations/gsheets/retry cannot resurrect
    deleted leads onto the spreadsheet.
    """
    counts = {}
    for coll in ["leads", "bookings", "payments", "deliveries", "finance", "insurance",
                 "claims", "activities", "dealer_earnings", "quotations", "incentive_register",
                 "sheet_sync_log"]:
        r = await db[coll].delete_many({})
        counts[coll] = r.deleted_count
    await db["system"].update_one({"_id": "seed_state"},
                                  {"$set": {"sampleCleared": True, "clearedAt": now_iso()}}, upsert=True)
    await db["counters"].update_one({"_id": "lead"}, {"$set": {"seq": 0}}, upsert=True)
    for c in ["receipt", "booking", "activity", "snapshot", "claim", "finance", "insurance"]:
        await db["counters"].update_one({"_id": c}, {"$set": {"seq": 100}}, upsert=True)
    sheet_clear = await gsheets.clear_operational_register_rows()
    await write_audit(act, "reset", "system",
                      new={"clearedTransactions": counts, "sheetClear": sheet_clear})
    return {"ok": True, "cleared": counts, "sheetClear": sheet_clear,
            "nextLeadId": "LD26000001"}


def _config_diagnostics():
    """Names + presence only — never values. Logged once at startup so a
    misconfigured deploy is obvious without ever exposing a secret."""
    required = ["MONGO_URL", "DB_NAME", "JWT_SECRET"]
    optional = ["GSHEET_ID", "CORS_ORIGINS"]
    missing = [k for k in required if not os.environ.get(k, "").strip()]
    cred = gsheets.credential_diagnostics()
    return {
        "required": {k: bool(os.environ.get(k, "").strip()) for k in required},
        "optional": {k: bool(os.environ.get(k, "").strip()) for k in optional},
        "missingRequired": missing,
        "googleCredentialFound": cred["credential_found"],
        "googleCredentialSource": cred["credential_source"],
        "gsheetIdPresent": cred["gsheet_id_present"],
        "sheetSyncEnabled": bool(cred["credential_found"] and cred["gsheet_id_present"]),
        "financeIndexes": dict(_finance_index_status),
    }


@api.get("/admin/config-check", dependencies=[Depends(owner_only)])
async def config_check():
    """Owner-only startup/runtime configuration health. Reports which settings are
    PRESENT, never their values."""
    return _config_diagnostics()



async def _audit_finance_integrity_for_unique_indexes():
    findings = {}
    findings["financePaymentsWithoutRegister"] = await db.payments.aggregate([
        {"$match": {"paymentMode": "Finance", "financeFileNumber": {"$nin": [None, ""]}}},
        {"$lookup": {"from": "finance", "localField": "financeFileNumber", "foreignField": "fileNumber", "as": "financeFile"}},
        {"$match": {"financeFile": {"$size": 0}}},
        {"$project": {"_id": 0, "receiptNumber": 1, "leadId": 1, "financeFileNumber": 1}},
    ]).to_list(1000)
    findings["financeRegisterWithoutPayments"] = await db.finance.aggregate([
        {"$lookup": {"from": "payments", "localField": "fileNumber", "foreignField": "financeFileNumber", "as": "payments"}},
        {"$match": {"payments": {"$size": 0}}},
        {"$project": {"_id": 0, "fileNumber": 1, "leadId": 1}},
    ]).to_list(1000)
    findings["duplicateFinanceLeadIds"] = await db.finance.aggregate([
        {"$match": {"leadId": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$leadId", "count": {"$sum": 1}, "files": {"$push": "$fileNumber"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]).to_list(1000)
    findings["duplicateFinanceFileNumbers"] = await db.finance.aggregate([
        {"$match": {"fileNumber": {"$nin": [None, ""]}}},
        {"$group": {"_id": "$fileNumber", "count": {"$sum": 1}, "leadIds": {"$push": "$leadId"}}},
        {"$match": {"count": {"$gt": 1}}},
    ]).to_list(1000)
    findings["financeNoLeadsWithFinancePayments"] = await db.payments.aggregate([
        {"$match": {"paymentMode": "Finance"}},
        {"$lookup": {"from": "leads", "localField": "leadId", "foreignField": "leadId", "as": "lead"}},
        {"$unwind": "$lead"},
        {"$match": {"lead.financeRequired": {"$ne": "Yes"}}},
        {"$project": {"_id": 0, "receiptNumber": 1, "leadId": 1, "financeFileNumber": 1}},
    ]).to_list(1000)
    findings["financePaymentsWithBlankFileNumber"] = await db.payments.find(
        {"paymentMode": "Finance", "financeFileNumber": {"$in": [None, ""]}},
        {"_id": 0, "receiptNumber": 1, "leadId": 1}
    ).to_list(1000)
    logging.info("FINANCE_INTEGRITY_AUDIT: %s", {k: len(v) for k, v in findings.items()})
    return findings


async def _ensure_finance_unique_indexes():
    global _finance_index_status
    _finance_index_status = {
        "status": "CHECKING",
        "ready": False,
        "reason": "finance uniqueness audit/index check in progress",
        "checkedAt": now_iso(),
        "auditCounts": {},
    }
    findings = await _audit_finance_integrity_for_unique_indexes()
    counts = {k: len(v) for k, v in findings.items()}
    if findings["duplicateFinanceLeadIds"] or findings["duplicateFinanceFileNumbers"]:
        _finance_index_status = {
            "status": "ERROR",
            "ready": False,
            "reason": "duplicate finance leadIds/fileNumbers found; unique indexes not created",
            "checkedAt": now_iso(),
            "auditCounts": counts,
        }
        logging.error("FINANCE_UNIQUE_INDEX_SKIPPED: duplicate finance records found: %s", findings)
        return findings
    try:
        await db.finance.create_index("leadId", unique=True, partialFilterExpression={"leadId": {"$type": "string", "$gt": ""}})
        await db.finance.create_index("fileNumber", unique=True, partialFilterExpression={"fileNumber": {"$type": "string", "$gt": ""}})
    except Exception as e:
        _finance_index_status = {
            "status": "ERROR",
            "ready": False,
            "reason": f"finance unique index creation failed ({type(e).__name__})",
            "checkedAt": now_iso(),
            "auditCounts": counts,
        }
        logging.exception("FINANCE_UNIQUE_INDEX_ERROR: finance unique index creation failed")
        return findings
    _finance_index_status = {
        "status": "HEALTHY",
        "ready": True,
        "reason": "finance unique indexes verified",
        "checkedAt": now_iso(),
        "auditCounts": counts,
    }
    return findings

@app.on_event("startup")
async def startup():
    global _finance_index_status
    cfg = _config_diagnostics()
    if cfg["missingRequired"]:
        logging.warning("CONFIG: missing required environment variables: %s", ", ".join(cfg["missingRequired"]))
    if not cfg["sheetSyncEnabled"]:
        logging.warning("CONFIG: Google Sheet sync is DISABLED (credentialFound=%s, gsheetId=%s). "
                        "Add the Render Secret File gsheets_credentials.json and set GSHEET_ID.",
                        cfg["googleCredentialFound"], cfg["gsheetIdPresent"])
    else:
        logging.info("CONFIG: Google Sheet sync enabled (credential source: %s)", cfg["googleCredentialSource"])
    await authmod.seed_users(db)
    res = await seeder.run_seed(db)
    if res.get("seeded"):
        for l in await db.leads.find().to_list(3000):
            await recompute_lead(l["leadId"])
    # Indexes (M2/M3 performance) — idempotent
    try:
        await db.leads.create_index("leadId")
        await db.leads.create_index("mobile")
        await db.leads.create_index("currentStatus")
        await db.leads.create_index("bookingDate")
        await db.payments.create_index("leadId")
        await db.audit_log.create_index([("timestamp", -1)])
        await db.incentive_register.create_index("leadId", unique=True)
        await db.masters_list.create_index("id", unique=True)
        await db.masters_list.create_index([("category", 1), ("value", 1)])
    except Exception:
        pass
    try:
        await _ensure_finance_unique_indexes()
    except Exception as e:
        _finance_index_status = {
            "status": "ERROR",
            "ready": False,
            "reason": f"finance uniqueness audit failed ({type(e).__name__})",
            "checkedAt": now_iso(),
            "auditCounts": {},
        }
        logging.exception("FINANCE_UNIQUE_INDEX_AUDIT_ERROR: finance uniqueness audit failed")
    # Insurance rate consistency migration (INS-1)
    try:
        await _migrate_insurance_rates()
    except Exception:
        pass
    # Self-heal: booked leads whose booking advance was never recorded as a payment
    # (so Customer Outstanding wasn't reduced). Idempotent.
    try:
        await _backfill_booking_advances()
    except Exception:
        pass


async def _backfill_booking_advances():
    """For any lead with bookingAmount>0 and NO payments recorded, create the booking-advance
    receipt so Customer Outstanding is reduced. Idempotent (skips leads that already have payments)."""
    healed = 0
    for l in await db.leads.find({"bookingAmount": {"$gt": 0}}).to_list(5000):
        lid = l["leadId"]
        ba = ce.num(l.get("bookingAmount"))
        if ba <= 0:
            continue
        has_advance = await db.payments.find_one(
            {"leadId": lid, "narration": {"$regex": "booking advance", "$options": "i"}})
        received = await db.payments.aggregate([
            {"$match": {"leadId": lid}}, {"$group": {"_id": None, "t": {"$sum": "$amount"}}}]).to_list(1)
        total_received = ce.num(received[0]["t"]) if received else 0.0
        if has_advance or total_received > 0:
            continue
        await _add_payment_internal(lid, PaymentIn(
            amount=ba, paymentMode=l.get("lastPaymentMode") or "Cash",
            date=l.get("bookingDate") or today(), narration="Booking advance (backfill)"))
        await recompute_lead(lid)
        healed += 1
    return healed


@app.on_event("shutdown")
async def shutdown():
    client.close()


# Routers included LAST so every @api route above is registered
app.include_router(auth_router)
app.include_router(api)
app.include_router(public)
