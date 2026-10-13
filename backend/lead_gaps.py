"""Exact missing docs / entries that block a live file from delivery.

Showroom Admin uses this on the Lead Register so they do not open every lead.
Closed, delivered, lost and cancelled files are skipped.
"""
from __future__ import annotations

import commercial as ce
import lead_docs

DOC_KINDS = (
    *lead_docs.KYC_INDIVIDUAL,
    *lead_docs.KYC_B2B,
    lead_docs.EXTRA_SUPPORT_KIND,
    lead_docs.DEAL_SHEET_KIND,
    "delivery_insurance",
    "delivery_rto",
)

_DONE = ("yes", "y", "done", "true", "1")


def _yes(value) -> bool:
    return str(value or "").strip().lower() in _DONE


def _flag(code: str, message: str) -> dict:
    return {"code": code, "message": message}


def is_closed_for_update(lead) -> bool:
    lead = lead or {}
    status = str(lead.get("currentStatus") or "").strip().lower()
    acct = str(lead.get("accountStatus") or "Active").strip().lower()
    if lead.get("dealCancelled"):
        return True
    # Showroom Admin register hides New — flags stay off those rows.
    if status == "new":
        return True
    if status in ("delivered", "close won", "closed", "lost"):
        return True
    if acct in ("cancelled", "closed", "archived", "inactive"):
        return True
    if str(lead.get("deliveryStatus") or "").strip().lower() == "delivered":
        return True
    return False


def _is_booked(lead) -> bool:
    cs = str((lead or {}).get("currentStatus") or "").lower()
    return ("book" in cs or "finance" in cs
            or bool(lead.get("bookingDate")) or ce.num(lead.get("bookingAmount")) > 0)


def _is_priced(lead) -> bool:
    if "priceStructureSaved" in (lead or {}):
        return bool(lead.get("priceStructureSaved"))
    return ce.num((lead or {}).get("exShowroom")) > 0


def flags_for_lead(lead, *, kinds=None) -> list:
    """Return ordered {code, message} gaps. Empty when the file is closed or complete."""
    lead = lead or {}
    if is_closed_for_update(lead):
        return []
    have = {str(k) for k in (kinds or set()) if k}
    flags = []

    if lead.get("assignmentPending"):
        flags.append(_flag("assignment", "Assignment not approved — executive cannot work this file"))

    if not str(lead.get("executive") or "").strip():
        flags.append(_flag("executive", "No executive assigned"))

    if not str(lead.get("interestedModel") or "").strip() and not str(lead.get("variant") or "").strip():
        flags.append(_flag("vehicle", "Model / variant not recorded"))

    missing_kyc = []
    for kind in lead_docs.required_kyc_kinds(lead.get("customerType")):
        if kind not in have:
            missing_kyc.append((lead_docs.KINDS.get(kind) or {}).get("label") or kind)
    if lead_docs.normalize_customer_type(lead.get("customerType")) == "B2B":
        if "kyc_gst" not in have and not str(lead.get("gstin") or "").strip():
            missing_kyc.append("GSTIN")
    if missing_kyc:
        flags.append(_flag("kyc", "KYC missing: " + ", ".join(missing_kyc)))

    if not (lead_docs.DEAL_SHEET_KIND in have):
        flags.append(_flag("deal_sheet", "Deal sheet not uploaded"))

    extra = lead.get("oemExtraSupportReceived")
    if extra is None and isinstance(lead.get("units"), list):
        extra = sum(ce.num((u or {}).get("oemExtraSupportReceived")) for u in lead["units"])
    if lead_docs.extra_support_required(extra) and lead_docs.EXTRA_SUPPORT_KIND not in have:
        flags.append(_flag("oem_extra", "OEM Extra Support proof missing"))

    if not _is_priced(lead):
        flags.append(_flag("price", "Price Structure not saved (ex-showroom is ₹0)"))

    booked = _is_booked(lead)
    entry_codes = {f["code"] for f in flags}
    if not booked and not (entry_codes & {"kyc", "deal_sheet", "oem_extra", "price", "vehicle", "executive"}):
        flags.append(_flag("booking", "Not booked yet"))

    if not booked:
        return flags

    os_amt = ce.round2(ce.num(lead.get("customerOutstanding")))
    if os_amt > 0.01:
        flags.append(_flag("outstanding", f"Customer outstanding ₹{os_amt:,.0f} — not cleared"))

    if not str(lead.get("chassisNumber") or "").strip():
        flags.append(_flag("chassis", "Chassis not recorded (OEM Sold)"))
    if not str(lead.get("invoiceNumber") or "").strip():
        flags.append(_flag("invoice_no", "Invoice number not recorded"))

    if not _yes(lead.get("insurance")):
        flags.append(_flag("insurance", "Insurance not marked Yes"))
    if not str(lead.get("insurerName") or "").strip():
        flags.append(_flag("insurer", "Insurer name not recorded"))
    if (ce.normalize_insurance_arranged_by(lead.get("insuranceArrangedBy")) != "self"
            and not str(lead.get("insuranceAgentId") or "").strip()):
        flags.append(_flag("ins_agent", "Insurance agent not selected"))
    if "delivery_insurance" not in have:
        flags.append(_flag("ins_copy", "Insurance copy not uploaded"))

    if not _yes(lead.get("registration")):
        flags.append(_flag("registration", "Registration not marked Yes"))
    if "delivery_rto" not in have:
        flags.append(_flag("rto_copy", "RTO / Registration copy not uploaded"))

    if not _yes(lead.get("invoice")):
        flags.append(_flag("invoice_step", "Invoice step not marked Yes"))
    if not _yes(lead.get("pdi")):
        flags.append(_flag("pdi", "PDI not marked Yes"))

    return flags


def summarize(flags) -> str:
    if not flags:
        return ""
    return flags[0]["message"]
