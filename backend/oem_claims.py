"""Coulson claim settlements ("debit notes") mirrored and tied back to CRM leads.

This is NOT the Scheme Claim Register in db.claims. That register is the dealer's own
per-lead, per-component statement of what Euler owes under Scheme Master. This module
mirrors Euler's own workflow record of the claims actually filed with them — keyed on
chassis and source invoice, moving through their seven-stage approval ladder.

The two are reconciled side by side and never merged. One Coulson debit note can carry
line items belonging to several leads, and its claim types ("Referral Commission") do
not share a vocabulary with the register's component keys, so folding one into the
other would corrupt the Owner Commercial Report, Dealer Earnings and the OEM Claim
Dashboard — all of which sum eligibleClaim - receivedAmount out of db.claims.

Read-only. Claims are raised in Coulson, never from here.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone

from pymongo.errors import DuplicateKeyError

import coulson as coulson_client
import oem_sync

log = logging.getLogger("oem_claims")

CLAIMS_COLLECTION = "oem_portal_claims"

# The dealership works in IST and every date in the CRM is an IST calendar date.
IST = timezone(timedelta(hours=5, minutes=30))

# Their seven-stage approval ladder, in order, as the journey timeline names them.
CLAIM_STAGES = (
    ("creation", "Creation"),
    ("rm_approval", "RM Approval"),
    ("dealer_development_department_approval", "Dealer Development Approval"),
    ("sales_department_approval", "Sales Department Approval"),
    ("finance_department_approval", "Finance Department Approval"),
    ("sales_invoice_generation", "Sales Invoice Generation"),
    ("bill_posted_in_sap", "Bill Posted in SAP"),
)
STAGE_LABELS = dict(CLAIM_STAGES)

# A claim in one of these has stopped moving — ageing it further is noise.
TERMINAL_STATUSES = ("Settled", "Rejected", "Cancelled")
# Euler has issued the settlement instrument; whether the money landed is a
# question for the money desk, not something this mirror can answer.
GENERATED_STATUSES = ("Credit Note Generated", "Sales Invoice Generated")


def now_ist():
    return datetime.now(IST)


def now_iso():
    return oem_sync.now_iso()


def _num(v):
    """Money / count from Coulson or Mongo. Strings like '2.0' / '5,000' are fine."""
    try:
        if v is None or v is False or v == "":
            return 0.0
        if isinstance(v, bool):
            return 1.0 if v else 0.0
        if isinstance(v, (int, float)):
            return float(v)
        if isinstance(v, str):
            s = v.strip().replace(",", "").replace("₹", "").replace("Rs", "")
            if not s:
                return 0.0
            return float(s)
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _as_int(v, default=0):
    """int() that does not throw on '2.0', '', lists, or None."""
    try:
        return int(_num(v))
    except (TypeError, ValueError):
        return default


def _as_id_list(value):
    """leadIds may be a list, a single string, or junk from an older sync."""
    if value is None or value is False or value == "":
        return []
    if isinstance(value, str):
        v = value.strip()
        return [v] if v else []
    if isinstance(value, dict):
        value = list(value.values())
    if isinstance(value, (list, tuple, set)):
        out = []
        for x in value:
            s = str(x or "").strip()
            if s and s not in out:
                out.append(s)
        return out
    s = str(value).strip()
    return [s] if s else []


def round2(v):
    return round(_num(v) + 0.0, 2)


# ---------------------------------------------------------------- dates
# Coulson hands the same instant back in two different formats and two different
# zones, and they are 5h30m apart:
#
#   list   "_created_at": "2 Sep 2026 13:34:38"     <- IST wall clock
#   detail  "created_at": "2026-09-02 08:04:38"     <- UTC
#
# Reading one with the other's rule shifts every ageing figure by a day near the
# date boundary, which is exactly the sort of wrong number nobody notices.
_LIST_FORMATS = ("%d %b %Y %H:%M:%S", "%d %B %Y %H:%M:%S", "%d %b %Y %H:%M", "%d %B %Y %H:%M")
_DETAIL_FORMATS = ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d")


def _try_formats(value, formats):
    s = str(value or "").strip()
    if not s:
        return None
    # "2 Sept 2026" appears in their UI; the API says "2 Sep 2026". Accept both.
    s = re.sub(r"\bSept\b", "Sep", s)
    s = s.replace("T", " ").replace("Z", "").strip()
    for fmt in formats:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def parse_list_datetime(value):
    """List rows carry local IST wall-clock time."""
    dt = _try_formats(value, _LIST_FORMATS)
    return dt.replace(tzinfo=IST) if dt else None


def parse_detail_datetime(value):
    """Journey header and timeline stamps are UTC; return them as IST."""
    dt = _try_formats(value, _DETAIL_FORMATS)
    if not dt:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(IST)


def iso_ist(dt):
    return dt.astimezone(IST).strftime("%Y-%m-%dT%H:%M:%S%z") if dt else ""


def date_ist(dt):
    return dt.astimezone(IST).strftime("%Y-%m-%d") if dt else ""


def days_since(dt, *, now=None):
    if not dt:
        return 0
    ref = now or now_ist()
    return max(0, (ref.astimezone(IST).date() - dt.astimezone(IST).date()).days)


# ---------------------------------------------------------------- shape
def is_terminal(status):
    return str(status or "").strip() in TERMINAL_STATUSES


def stage_progress(timeline, *, now=None):
    """Which rung the claim is on, and how long it has sat there.

    "Stage days" counts from the moment the PREVIOUS stage completed — that is the
    time the current desk has actually been holding it, which is the number worth
    chasing. Days since the claim was raised is a different figure and is kept apart.
    """
    out = {
        "stageKey": "", "stageLabel": "", "stageState": "",
        "stageSince": "", "stageDays": 0,
        "stagesCompleted": 0, "stagesTotal": len(CLAIM_STAGES),
        "lastActor": "", "lastRemarks": "",
    }
    if not isinstance(timeline, dict):
        return out
    last_done_at = None
    last_actor = ""
    last_remarks = ""
    completed = 0
    for key, label in CLAIM_STAGES:
        node = timeline.get(key)
        if not isinstance(node, dict):
            continue
        state = str(node.get("status") or "").strip().upper()
        when = parse_detail_datetime(node.get("date"))
        if state == "COMPLETED":
            completed += 1
            if when:
                last_done_at = when
            if node.get("performed_by"):
                last_actor = str(node.get("performed_by") or "")
            if node.get("remarks"):
                last_remarks = str(node.get("remarks") or "")
            continue
        out.update({
            "stageKey": key,
            "stageLabel": label,
            "stageState": state,
            "stageSince": iso_ist(last_done_at),
            "stageDays": days_since(last_done_at, now=now),
        })
        break
    out["stagesCompleted"] = completed
    out["lastActor"] = last_actor
    out["lastRemarks"] = last_remarks
    if not out["stageKey"] and completed:
        out["stageKey"] = CLAIM_STAGES[-1][0]
        out["stageLabel"] = STAGE_LABELS[CLAIM_STAGES[-1][0]]
        out["stageState"] = "COMPLETED"
    return out


_CHASSIS_FIELD_KEYS = (
    "chassis", "chassis_number", "chassisNumber", "chassis_no", "chassisNo",
    "vin", "vehicle_chassis", "vehicleChassis",
)
_VEHICLE_LIST_KEYS = (
    "vehicles", "linked_vehicles", "linkedVehicles", "vehicle_list",
    "linked_vehicle", "linkedVehicle",
)
_VEHICLE_ID_KEYS = (
    "linked_vehicle_ids", "linkedVehicleIds", "vehicle_ids", "vehicleIds",
    "vehicle_id", "vehicleId",
)


def _looks_like_uuid(value):
    return bool(re.fullmatch(
        r"[0-9A-F]{8}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{4}-[0-9A-F]{12}",
        str(value or "").strip(), re.I))


def _looks_like_chassis_token(value):
    """True for an Euler VIN / chassis, false for a Coulson vehicle UUID."""
    ch = oem_sync._norm_chassis(value)
    if not ch or _looks_like_uuid(ch) or "-" in ch:
        return False
    if ch.startswith("MD9") and len(ch) >= 13:
        return True
    return bool(11 <= len(ch) <= 20 and re.fullmatch(r"[A-Z0-9]+", ch))


def _iter_vehicle_blobs(item):
    """Vehicle dicts Coulson now hangs on Extra Support / debit-note lines."""
    if not isinstance(item, dict):
        return []
    blobs = []
    vehicle = item.get("vehicle")
    if isinstance(vehicle, dict):
        blobs.append(vehicle)
        inner = vehicle.get("vehicle")
        if isinstance(inner, dict):
            blobs.append(inner)
    for key in _VEHICLE_LIST_KEYS:
        val = item.get(key)
        if isinstance(val, list):
            for v in val:
                if isinstance(v, dict):
                    blobs.append(v)
                elif isinstance(v, str) and v.strip():
                    blobs.append({"chassis": v})
        elif isinstance(val, dict):
            blobs.append(val)
            nested = val.get("data") or val.get("items") or val.get("vehicles")
            if isinstance(nested, list):
                blobs.extend(x for x in nested if isinstance(x, dict))
    return blobs


def _chassis_from_blob(blob):
    if not isinstance(blob, dict):
        return ""
    for key in _CHASSIS_FIELD_KEYS:
        ch = oem_sync._norm_chassis(blob.get(key))
        if _looks_like_chassis_token(ch):
            return ch
    return ""


def _line_chassis_list(item):
    """Every chassis Coulson attached to this line.

    Oct 2026 Extra Support create requires at least one vehicle and posts
    `line_item_N_linked_vehicle_ids` (and sometimes `vehicle_id`). The journey
    returns those as `vehicles[]`, `linked_vehicle_ids`, or nested `vehicle`.
    Older Additional Support notes had none of these — empty list, manual match.
    """
    if not isinstance(item, dict):
        return []
    found = []

    def add(raw):
        ch = oem_sync._norm_chassis(raw)
        if _looks_like_chassis_token(ch) and ch not in found:
            found.append(ch)

    for key in _CHASSIS_FIELD_KEYS:
        add(item.get(key))
    for blob in _iter_vehicle_blobs(item):
        add(_chassis_from_blob(blob))
    for key in _VEHICLE_ID_KEYS:
        for raw in _as_id_list(item.get(key)):
            add(raw)
    hay = f"{item.get('description') or ''} {item.get('claim_type') or ''} {item.get('claimType') or ''}"
    for m in re.finditer(r"\bMD9[A-Z0-9]{10,}\b", hay, re.I):
        add(m.group(0))
    for ch in item.get("chassisList") or []:
        add(ch)
    return found


def _line_chassis(item):
    """Primary chassis from whatever key (or nested vehicle) Coulson used."""
    found = _line_chassis_list(item)
    return found[0] if found else ""


def line_chassis_list(line):
    """Normalised chassis on a stored line, including Extra Support multi-vehicle."""
    if not isinstance(line, dict):
        return []
    out = []
    primary = oem_sync._norm_chassis(line.get("chassis"))
    if _looks_like_chassis_token(primary):
        out.append(primary)
    for ch in line.get("chassisList") or []:
        n = oem_sync._norm_chassis(ch)
        if _looks_like_chassis_token(n) and n not in out:
            out.append(n)
    return out


def _line_invoice(item):
    if not isinstance(item, dict):
        return ""
    inv = (item.get("source_invoice_number") or item.get("sourceInvoiceNumber")
           or item.get("source_invoice") or item.get("invoice_number")
           or item.get("invoiceNumber") or "")
    inv = str(inv).strip()
    if inv:
        return inv
    hay = f"{item.get('description') or ''} {item.get('claim_type') or ''}"
    m = re.search(r"\bAF-\d+-I\d+\b", hay, re.I)
    return m.group(0) if m else ""


def _item_document_count(item):
    """How many files the desk uploaded on this Claim Item (Coulson's Docs column).

    The dealer SPA renders `line.documents.length` as "N Docs" and POSTs new files
    to `debit-note/line-item-documents`. Those land back on the journey as
    `documents[]` with `file_url`. Integer aliases (`document_count`) are accepted
    so a list payload that already summed them still counts. URLs are never kept.
    """
    if not isinstance(item, dict):
        return 0
    counts = []
    for key in ("document_count", "documents_count", "documentCount", "docs_count", "docsCount"):
        val = item.get(key)
        if isinstance(val, bool):
            continue
        if isinstance(val, (int, float)):
            counts.append(max(_as_int(val), 0))
        elif isinstance(val, str) and val.strip():
            n = _as_int(val)
            if n or val.strip().replace(",", "").replace(".", "", 1).isdigit():
                counts.append(max(n, 0))
    for key in ("documents", "supporting_documents", "supportingDocuments",
                "attachments", "files", "docs"):
        val = item.get(key)
        if isinstance(val, list):
            counts.append(len(val))
        elif isinstance(val, dict):
            nested = val.get("data") or val.get("files") or val.get("documents")
            if isinstance(nested, list):
                counts.append(len(nested))
            for ck in ("count", "total", "total_count"):
                n = val.get(ck)
                if isinstance(n, bool):
                    continue
                if n not in (None, ""):
                    counts.append(max(_as_int(n), 0))
    return max(counts) if counts else 0


def _first_text(*vals):
    for v in vals:
        s = str(v or "").strip()
        if s:
            return s
    return ""


def _oem_line_description(item, claim_type=""):
    """The prose Euler shows on Additional Support (claim type, customer, approver).

    Extra Support used to omit chassis; the customer name lived here. New notes
    carry a mandatory vehicle, but this prose is still what the desk reads.
    Prefer the OEM description blob when it already names the customer.
    """
    if not isinstance(item, dict):
        return ""
    raw = _first_text(
        item.get("description"), item.get("remarks"), item.get("particulars"),
        item.get("narration"), item.get("claim_description"), item.get("claimDescription"),
        item.get("line_description"), item.get("lineDescription"),
    )
    customer = _first_text(
        item.get("customer_name"), item.get("customerName"), item.get("customer"),
        item.get("retail_customer_name"), item.get("retailCustomerName"),
    )
    approved = _first_text(
        item.get("approved_by"), item.get("approvedBy"), item.get("approved_by_name"),
    )
    folded = raw.lower()
    if raw and ("customer name" in folded or not customer):
        return raw
    bits = []
    if claim_type:
        bits.append(f"Claim Type :- {claim_type}")
    if raw:
        bits.append(raw)
    if customer:
        bits.append(f"Customer Name:- {customer}")
    if approved:
        bits.append(f"Approved By :- {approved}")
    return " ".join(bits)


def normalise_line_item(item):
    """One claim line. Chassis and source invoice are the keys back to a lead.

    The per-line `documents[]` are the files the desk uploads under Docs / Add
    Documents in Coulson (often customer photographs on an open S3 bucket). Only
    their count is kept: the CRM has no business re-hosting those images, and the
    read-only OEM finance role must never be able to reach them.
    """
    if not isinstance(item, dict):
        return None
    claim_type = str(item.get("claim_type") or item.get("claimType")
                     or item.get("type") or "").strip()
    description = _oem_line_description(item, claim_type)
    customer_name = _first_text(
        item.get("customer_name"), item.get("customerName"), item.get("customer"),
        item.get("retail_customer_name"), item.get("retailCustomerName"),
    )
    approved_by = _first_text(
        item.get("approved_by"), item.get("approvedBy"), item.get("approved_by_name"),
    )
    chassis_list = _line_chassis_list(item)
    return {
        "lineId": str(item.get("id") or item.get("line_id") or item.get("lineId") or ""),
        "claimType": claim_type,
        "description": description,
        "customerName": customer_name,
        "approvedBy": approved_by,
        "chassis": chassis_list[0] if chassis_list else "",
        "chassisList": chassis_list,
        "sourceInvoiceNumber": _line_invoice(item),
        "model": str(item.get("model") or "").strip(),
        "variant": str(item.get("variant") or "").strip(),
        "status": str(item.get("status") or "").strip(),
        "baseAmount": round2(item.get("base_amount") or item.get("baseAmount")),
        "totalAmount": round2(item.get("total_amount") or item.get("totalAmount")),
        "rejectedBy": str(item.get("rejected_by") or item.get("rejectedBy") or "") or "",
        "remarks": str(item.get("remarks") or "") or "",
        "documentCount": _item_document_count(item),
        "sourceInvoiceUrl": str(item.get("source_invoice_s3_link")
                                or item.get("sourceInvoiceUrl") or ""),
        "leadId": str(item.get("leadId") or ""),
        "leadCustomer": str(item.get("leadCustomer") or ""),
        "leadIds": _as_id_list(item.get("leadIds")),
        "leadCustomers": [str(x) for x in _as_id_list(item.get("leadCustomers"))],
        "matchedBy": str(item.get("matchedBy") or ""),
        "componentKey": map_claim_type_to_component(claim_type, description),
    }


def _line_item_list(raw):
    """Coulson / older syncs have stored a dict, a string, or mixed junk here."""
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        items = list(raw.values()) if raw else []
    else:
        items = []
    return [li for li in items if isinstance(li, dict)]


def _ensure_line_ids(lines):
    """Stable ids so a debit note with eight Extra Support rows can be matched
    one item at a time even when Coulson omitted `id`. Drops non-dict junk so
    later `.get` / `int()` calls cannot crash the sync or Create."""
    kept = []
    for i, line in enumerate(_line_item_list(lines)):
        if not str(line.get("lineId") or "").strip():
            line["lineId"] = f"idx:{i}"
        if line_lead_ids(line):
            stamp_line_leads(line, list(zip(line_lead_ids(line), line_lead_customers(line))))
        kept.append(line)
    if isinstance(lines, list):
        lines[:] = kept
        return lines
    return kept


def coerce_line_items(doc):
    """Guarantee doc['lineItems'] is a list of dicts. Safe to call on any row."""
    if not isinstance(doc, dict):
        return []
    lines = _ensure_line_ids(_line_item_list(doc.get("lineItems")))
    doc["lineItems"] = lines
    return lines


def line_lead_ids(line):
    """Every CRM lead on this Euler line. Extra Support can name two customers
    on one 5000+5000 row; `leadId` alone only held the first."""
    if not isinstance(line, dict):
        return []
    ids = []
    for lid in _as_id_list(line.get("leadIds")):
        if lid and lid not in ids:
            ids.append(lid)
    primary = str(line.get("leadId") or "").strip()
    if primary and primary not in ids:
        ids.insert(0, primary)
    return ids


def line_lead_customers(line):
    ids = line_lead_ids(line)
    names = [str(x or "") for x in _as_id_list((line or {}).get("leadCustomers"))]
    by_id = {}
    if (line or {}).get("leadId") and (line or {}).get("leadCustomer"):
        by_id[str(line.get("leadId"))] = str(line.get("leadCustomer") or "")
    for i, lid in enumerate(ids):
        if i < len(names) and names[i]:
            by_id.setdefault(lid, names[i])
    return [by_id.get(lid, "") for lid in ids]


def stamp_line_leads(line, leads):
    """Write leadId + leadIds. leadId stays the first lead for older readers."""
    if not isinstance(line, dict):
        return line
    ids, names = [], []
    for item in leads or []:
        if isinstance(item, dict):
            lid = str(item.get("leadId") or "").strip()
            name = str(item.get("customer") or item.get("leadCustomer")
                       or item.get("customerName") or "")
        elif isinstance(item, (list, tuple)) and item:
            lid = str(item[0] or "").strip()
            name = str(item[1] if len(item) > 1 else "")
        else:
            lid, name = str(item or "").strip(), ""
        if lid and lid not in ids:
            ids.append(lid)
            names.append(name)
    line["leadIds"] = ids
    line["leadCustomers"] = names
    line["leadId"] = ids[0] if ids else ""
    line["leadCustomer"] = names[0] if names else ""
    if not ids:
        line["matchedBy"] = ""
    return line


def collect_claim_lead_ids(lines):
    out = []
    for li in lines or []:
        for lid in line_lead_ids(li):
            if lid not in out:
                out.append(lid)
    return out


def _add_line_lead(line, lead_id, customer=""):
    lead_id = str(lead_id or "").strip()
    if not lead_id:
        return line
    ids = line_lead_ids(line)
    names = line_lead_customers(line)
    if lead_id in ids:
        names[ids.index(lead_id)] = customer or names[ids.index(lead_id)]
    else:
        ids.append(lead_id)
        names.append(customer or "")
    stamp_line_leads(line, list(zip(ids, names)))
    return line


def _drop_line_lead(line, lead_id):
    lead_id = str(lead_id or "").strip()
    ids = line_lead_ids(line)
    names = line_lead_customers(line)
    if lead_id not in ids:
        return line
    i = ids.index(lead_id)
    ids.pop(i)
    if i < len(names):
        names.pop(i)
    stamp_line_leads(line, list(zip(ids, names)))
    if ids:
        line["matchedBy"] = "manual"
    return line


def _restore_manual_line_joins(new_lines, old_lines):
    """Keep desk-made Extra Support joins across a Coulson re-fetch."""
    by_id = {}
    for li in old_lines or []:
        if not isinstance(li, dict):
            continue
        key = str(li.get("lineId") or "").strip()
        if key:
            by_id[key] = li
    for line in new_lines or []:
        if not isinstance(line, dict):
            continue
        old = by_id.get(str(line.get("lineId") or "").strip())
        if not old or old.get("matchedBy") != "manual":
            continue
        ids = line_lead_ids(old)
        if not ids:
            continue
        stamp_line_leads(line, list(zip(ids, line_lead_customers(old))))
        line["matchedBy"] = "manual"
    return new_lines


def _normalise_lines(raw):
    out = []
    for item in raw or []:
        line = normalise_line_item(item)
        if line:
            out.append(line)
    return _ensure_line_ids(out)


def _lines_have_vehicle(lines):
    return any(
        isinstance(li, dict) and (
            li.get("chassis") or line_chassis_list(li) or li.get("sourceInvoiceNumber"))
        for li in (lines or []) if isinstance(li, dict))


def claim_lines(doc):
    return [li for li in (doc.get("lineItems") or []) if isinstance(li, dict)]


def documented_line_count(doc):
    return sum(1 for li in claim_lines(doc) if _as_int(li.get("documentCount")) > 0)


def claim_document_count(doc):
    return sum(_as_int(li.get("documentCount")) for li in claim_lines(doc))


def claim_has_document(doc):
    """True only when every claim item has its own Docs upload.

    One Coulson debit note often carries several lines on the same chassis /
    invoice (Insurance, RTO, Consumer Discount, …). Each line has its own
    Add Documents control. A file on the first item does not cover the others.
    """
    lines = claim_lines(doc)
    if not lines:
        return False
    return all(_as_int(li.get("documentCount")) > 0 for li in lines)


def stamp_document_flag(doc):
    doc = doc if isinstance(doc, dict) else {}
    lines = claim_lines(doc)
    for li in lines:
        li["documentCount"] = _as_int(li.get("documentCount"))
    doc["documentCount"] = claim_document_count(doc)
    doc["lineItemCount"] = len(lines)
    doc["documentedLineCount"] = documented_line_count(doc)
    doc["hasDocument"] = claim_has_document(doc)
    return doc


def claim_doc_from_row(row):
    """The list row. Chassis usually lives only on the journey, but some list
    payloads already include line items — keep them so a failed journey does not
    blank Chassis / Invoice on OEM Claim Settlements.
    """
    created = parse_list_datetime(row.get("_created_at"))
    status = str(row.get("status") or "").strip()
    doc = {
        "debitNoteId": str(row.get("id") or ""),
        "claimNumber": str(row.get("debit_note_number") or "").strip(),
        "status": status,
        "settlementType": str(row.get("settlement_type") or "").strip(),
        "claimedAmount": round2(row.get("total_claimed_amount")),
        "approvedAmount": round2(row.get("total_approved_amount")),
        "activeAmount": round2(row.get("current_active_amount")),
        "sapBillNumber": str(row.get("sap_bill_number") or "") or "",
        "salesInvoiceNumber": str(row.get("sales_invoice_number") or "") or "",
        "creditNoteNumber": str(row.get("credit_note_number") or "") or "",
        "claimDocumentUrl": str(row.get("debit_note_s3_link") or ""),
        "showroomName": str(row.get("showroom_name") or "").strip(),
        "cityName": str(row.get("city_name") or "").strip(),
        "createdAt": iso_ist(created),
        "createdDate": date_ist(created),
        "claimAgeingDays": 0 if is_terminal(status) else days_since(created),
        "terminal": is_terminal(status),
        "syncedAt": now_iso(),
    }
    lines = _normalise_lines(coulson_client.pick_line_items(row if isinstance(row, dict) else {}))
    if lines:
        doc["lineItems"] = lines
    return stamp_document_flag(doc)


def merge_detail(doc, detail):
    """Fold a journey response into a claim doc: line items and ladder position.

    An empty journey must NOT wipe line items we already have (from the list row
    or a previous fetch). That wipe is what left AF-122-CL2627127 with a blank
    Chassis / Invoice column after a successful list sync.
    """
    doc = dict(doc)
    if not isinstance(detail, dict):
        return doc
    detail = coulson_client.journey_body(detail)
    header = detail.get("header") if isinstance(detail.get("header"), dict) else {}
    lines = _normalise_lines(coulson_client.pick_line_items(detail))
    if lines:
        doc["lineItems"] = lines
        # Journey is where the SPA reads `documents[]` for the Docs column.
        doc["docsCheckedAt"] = now_iso()
    if isinstance(detail.get("timeline"), dict):
        doc.update(stage_progress(detail.get("timeline")))
    if header:
        # The header repeats the money in UTC-stamped form; the list row is the
        # display of record, so only fill gaps rather than overwrite.
        for field, key in (("sapBillNumber", "sap_bill_number"),
                           ("salesInvoiceNumber", "sales_invoice_number"),
                           ("creditNoteNumber", "credit_note_number")):
            if not doc.get(field) and header.get(key):
                doc[field] = str(header.get(key))
        doc["autogenerated"] = bool(header.get("autogenerated"))
        showroom = header.get("showroom") if isinstance(header.get("showroom"), dict) else {}
        if showroom.get("id"):
            doc["showroomId"] = str(showroom.get("id"))
    if lines or doc.get("lineItems"):
        doc["detailFetchedAt"] = now_iso()
        doc["detailStatusAtFetch"] = doc.get("status") or ""
        doc["detailAmountAtFetch"] = doc.get("approvedAmount") or 0.0
    if header and not doc.get("claimDocumentUrl"):
        pdf = str(header.get("debit_note_s3_link") or header.get("debitNoteS3Link") or "")
        if pdf:
            doc["claimDocumentUrl"] = pdf
    return stamp_document_flag(doc)


def needs_detail(existing, row_doc):
    """Fetch the journey when chassis, status, amount, or item Docs could have changed.

    First sight always. After that, when Euler advanced the status or approved a
    different amount. A stored row with no chassis / invoice is NOT done: that is
    the OEM Claim Settlements blank column, and we keep asking.

    Item Docs are uploaded after filing, with no status change. We re-fetch until
    the journey has been seen for documents (`docsCheckedAt`), and we keep asking
    open claims until every line item has its own file — one upload on a
    multi-item debit note does not cover the rest.
    """
    if not existing or not existing.get("detailFetchedAt"):
        return True
    if not _lines_have_vehicle(existing.get("lineItems")):
        return True
    if str(existing.get("detailStatusAtFetch") or "") != str(row_doc.get("status") or ""):
        return True
    if abs(_num(existing.get("detailAmountAtFetch")) - _num(row_doc.get("approvedAmount"))) > 0.005:
        return True
    if not claim_has_document(existing):
        if not existing.get("docsCheckedAt"):
            return True
        status = existing.get("status") or (
            row_doc.get("status") if isinstance(row_doc, dict) else "") or ""
        if not is_terminal(status):
            return True
    return False


# ---------------------------------------------------------------- fetching
def _status_counts_total(counts):
    """Sum whatever shape status-counts answers with. None when unreadable."""
    if isinstance(counts, dict):
        vals = [v for v in counts.values() if isinstance(v, (int, float))]
        if vals:
            return int(sum(vals))
        nested = [v for v in counts.values() if isinstance(v, dict)]
        total = 0
        found = False
        for n in nested:
            for v in n.values():
                if isinstance(v, (int, float)):
                    total += int(v)
                    found = True
        return total if found else None
    if isinstance(counts, list):
        total = 0
        found = False
        for entry in counts:
            if not isinstance(entry, dict):
                continue
            for key in ("count", "total", "value"):
                if isinstance(entry.get(key), (int, float)):
                    total += int(entry[key])
                    found = True
                    break
        return total if found else None
    return None


def expected_claim_total(token, showroom_id=""):
    """Coulson's own count of every claim, or None when it cannot be read."""
    try:
        counts = coulson_client.fetch_claim_status_counts(token, showroom_id)
    except coulson_client.CoulsonError as e:
        log.info("Coulson status-counts unavailable: %s", e)
        return None
    except Exception:
        log.exception("Coulson status-counts failed")
        return None
    return _status_counts_total(counts)


def fetch_all_claims(token, *, showroom_id=""):
    """Every claim, whatever Coulson's default filter does.

    Their dealer UI ships a status filter by default. If the API applies one too, a
    plain sweep would quietly mirror a single bucket and drop the rest — a mirror that
    is wrong while looking healthy. So: sweep, check the result against Coulson's own
    per-status totals, and fall back to walking the eleven buckets when it comes up
    short. Returns (rows, mode, expected) so the caller can record whether the mirror
    is actually complete rather than assume it.
    """
    by_id = {}

    def absorb(rows):
        for r in rows or []:
            rid = str(r.get("id") or "")
            if rid:
                by_id[rid] = r

    swept, total = coulson_client.fetch_debit_notes(token)
    absorb(swept)
    expected = expected_claim_total(token, showroom_id)
    if expected is None:
        expected = total
    if expected is not None and len(by_id) >= expected:
        return list(by_id.values()), "sweep", expected

    for status in coulson_client.CLAIM_STATUSES:
        try:
            chunk, _ = coulson_client.fetch_debit_notes(token, status=status)
        except coulson_client.CoulsonError as e:
            log.info("Coulson claim status %s skipped: %s", status, e)
            continue
        absorb(chunk)
        if expected is not None and len(by_id) >= expected:
            break
    return list(by_id.values()), "per-status", expected


async def access_token(db):
    """Same session-or-password resolution the yard sync uses. Never a second login."""
    return await oem_sync._access_token(db)


# ---------------------------------------------------------------- linking
async def build_lead_index(db):
    """One pass over delivered leads, indexed by normalised chassis and invoice.

    Chassis has to be normalised before it can be compared, so a per-line query
    would mean re-scanning the lead collection for every claim line. Built once per
    sync instead — a hundred-odd claims against a few thousand leads.
    """
    by_chassis, by_invoice = {}, {}
    async for lead in db.leads.find({
        "$or": [{"chassisNumber": {"$nin": ["", None]}},
                {"invoiceNumber": {"$nin": ["", None]}},
                {"units.chassisNumber": {"$nin": ["", None]}},
                {"units.invoiceNumber": {"$nin": ["", None]}}],
    }):
        for ch in oem_sync.lead_chassis_list(lead):
            by_chassis.setdefault(ch, lead)
        for inv in oem_sync.lead_invoice_list(lead):
            if inv:
                by_invoice.setdefault(inv.lower(), lead)
    return {"chassis": by_chassis, "invoice": by_invoice}


async def _lead_for_chassis(db, chassis, index=None):
    ch = oem_sync._norm_chassis(chassis)
    if not ch:
        return None
    if index is not None:
        return index["chassis"].get(ch)
    async for lead in db.leads.find({
        "$or": [{"chassisNumber": {"$nin": ["", None]}},
                {"units.chassisNumber": {"$nin": ["", None]}}],
    }):
        if ch in set(oem_sync.lead_chassis_list(lead)):
            return lead
    return None


async def _lead_for_invoice(db, invoice, index=None):
    inv = str(invoice or "").strip()
    if not inv:
        return None
    if index is not None:
        return index["invoice"].get(inv.lower())
    hit = await db.leads.find_one({
        "invoiceNumber": {"$regex": f"^{re.escape(inv)}$", "$options": "i"},
    })
    if hit:
        return hit
    async for lead in db.leads.find({"units.invoiceNumber": {"$nin": ["", None]}}):
        if inv.lower() in {x.lower() for x in oem_sync.lead_invoice_list(lead)}:
            return lead
    return None


async def link_claim_lines(db, doc, index=None):
    """Tie each line to a lead: chassis first, source invoice as the fallback.

    Chassis is the stronger key — it is one-to-one with the physical vehicle, is
    already unique across live leads, and cannot be shared the way a fleet buyer's
    mobile can. A line that matches on chassis but disagrees on invoice is linked and
    FLAGGED rather than silently accepted: that disagreement is real information.

    Extra Support now requires a vehicle in the OEM app, so those lines auto-match
    the same way as scheme claims. One Extra Support line can name several chassis
    (`linked_vehicle_ids`); each matching lead is stamped. Old notes with no
    chassis still keep a desk-made manual join.

    Cancelled notes are left as stored. Chassis relink must not glue a cancelled
    debit note back onto the lead after the desk moved to the replacement.
    """
    if str(doc.get("status") or "") == "Cancelled":
        return doc
    lines = coerce_line_items(doc)
    lead_ids, conflicts = [], []
    for line in lines:
        held = line_lead_ids(line)
        held_names = line_lead_customers(line)
        auto_pairs = []
        auto_leads = []
        matched_by = ""
        for ch in line_chassis_list(line):
            lead = await _lead_for_chassis(db, ch, index)
            if not lead:
                continue
            auto_id = str(lead.get("leadId") or "").strip()
            if not auto_id or auto_id in {p[0] for p in auto_pairs}:
                continue
            auto_pairs.append((auto_id, str(lead.get("customerName") or "")))
            auto_leads.append((ch, lead))
            matched_by = "chassis"
        if not auto_pairs:
            lead = await _lead_for_invoice(db, line.get("sourceInvoiceNumber"), index)
            if lead:
                auto_id = str(lead.get("leadId") or "").strip()
                if auto_id:
                    auto_pairs.append((auto_id, str(lead.get("customerName") or "")))
                    auto_leads.append(("", lead))
                    matched_by = "invoice"
        if not auto_pairs:
            if line.get("matchedBy") == "manual" and held:
                # Desk-made Extra Support joins on old chassis-less notes.
                # Relink must not wipe them — including a second lead on a
                # 5000+5000 line.
                stamp_line_leads(line, list(zip(held, held_names)))
                line["matchedBy"] = "manual"
                for lid in held:
                    if lid not in lead_ids:
                        lead_ids.append(lid)
                continue
            stamp_line_leads(line, [])
            continue
        pairs = list(auto_pairs)
        if line.get("matchedBy") == "manual" and held:
            for lid, name in zip(held, held_names):
                if lid not in {p[0] for p in pairs}:
                    pairs.append((lid, name))
        stamp_line_leads(line, pairs)
        line["matchedBy"] = matched_by
        want_inv = str(line.get("sourceInvoiceNumber") or "").strip()
        mismatch = False
        for ch, lead in auto_leads:
            if matched_by != "chassis" or not ch:
                continue
            auto_id = str(lead.get("leadId") or "").strip()
            got_inv = oem_sync.invoice_for_chassis(lead, ch)
            if want_inv and got_inv and (
                    oem_sync._norm_invoice(want_inv) != oem_sync._norm_invoice(got_inv)):
                mismatch = True
                line["invoiceMismatch"] = True
                line["invoiceCancelled"] = True
                line["cancelledInvoiceNumber"] = want_inv
                line["newInvoiceNumber"] = got_inv
                conflicts.append({
                    "detail": (
                        f"{ch}: invoice {want_inv} cancelled; "
                        f"new invoice {got_inv} on {auto_id}"
                    ),
                    "chassis": ch,
                    "leadId": auto_id,
                    "cancelledInvoice": want_inv,
                    "newInvoice": got_inv,
                    "invoiceCancelled": True,
                })
                break
        if not mismatch:
            line["invoiceMismatch"] = False
            line["invoiceCancelled"] = False
        for lid in line_lead_ids(line):
            if lid not in lead_ids:
                lead_ids.append(lid)
    doc["lineItems"] = lines
    doc["leadIds"] = lead_ids
    doc["linkedLineCount"] = sum(1 for li in lines if line_lead_ids(li))
    doc["unlinkedLineCount"] = sum(1 for li in lines if not line_lead_ids(li))
    doc["invoiceConflicts"] = conflicts
    return doc


# ---------------------------------------------------------------- sync
async def sync_claims(db, *, detail_budget=250, token=None):
    """Mirror the Claim Settlements List into db.oem_portal_claims.

    Upsert only — a claim is a money record and this collection is a ledger, the same
    rule the Scheme Claim Register follows. A claim that vanishes from Coulson is
    marked, never deleted.
    """
    src = ""
    if token is None:
        token, src = await access_token(db)
    if not token:
        return {"ok": False, "reason": "not_configured"}

    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    # coulson.py speaks blocking urllib. The first sync walks every claim — well over a
    # hundred sequential requests — and doing that on the event loop would freeze the
    # API long enough for a Railway healthcheck to kill the deploy and start again.
    rows, mode, expected = await asyncio.to_thread(
        fetch_all_claims, token, showroom_id=doc.get("showroomId") or "")

    lead_index = await build_lead_index(db)
    seen_ids = []
    detail_calls = 0
    detail_failures = 0
    linked = 0
    with_vehicle = 0
    coll = db[CLAIMS_COLLECTION]
    held_by_id = {}
    async for held in coll.find({}, {"debitNoteId": 1, "lineItems": 1, "detailFetchedAt": 1,
                                     "detailStatusAtFetch": 1, "detailAmountAtFetch": 1,
                                     "docsCheckedAt": 1, "status": 1, "terminal": 1}):
        held_by_id[held.get("debitNoteId")] = held

    def _need_chassis_first(row):
        rid = str(row.get("id") or "")
        return 0 if needs_detail(held_by_id.get(rid) or {}, claim_doc_from_row(row)) else 1

    rows = sorted(rows, key=_need_chassis_first)
    for row in rows:
        row_doc = claim_doc_from_row(row)
        note_id = row_doc["debitNoteId"]
        if not note_id:
            continue
        seen_ids.append(note_id)
        existing = await coll.find_one({"debitNoteId": note_id}) or {}
        merged = {**existing, **row_doc}
        if needs_detail(existing, row_doc) and detail_calls < detail_budget:
            try:
                detail = await asyncio.to_thread(
                    coulson_client.fetch_claim_journey, token, note_id)
                detail_calls += 1
                merged = merge_detail(merged, detail)
            except coulson_client.CoulsonError as e:
                detail_failures += 1
                log.info("Coulson journey %s skipped: %s", note_id, e)
            except Exception:
                detail_failures += 1
                log.exception("Coulson journey %s failed", note_id)
        merged.setdefault("lineItems", existing.get("lineItems") or [])
        _restore_manual_line_joins(
            merged.get("lineItems") or [], existing.get("lineItems") or [])
        merged = await link_claim_lines(db, merged, lead_index)
        merged["missingFromOem"] = False
        if merged.get("linkedLineCount"):
            linked += 1
        if _lines_have_vehicle(merged.get("lineItems")):
            with_vehicle += 1
        merged = stamp_document_flag(merged)
        await coll.update_one({"debitNoteId": note_id}, {"$set": merged}, upsert=True)

    # Anything we hold that Coulson no longer lists: keep the row, flag it.
    stale = 0
    async for held in coll.find({"missingFromOem": {"$ne": True}}, {"debitNoteId": 1}):
        if held.get("debitNoteId") not in seen_ids:
            await coll.update_one({"_id": held["_id"]},
                                  {"$set": {"missingFromOem": True, "syncedAt": now_iso()}})
            stale += 1

    # Rejections only matter once we know whether anyone refiled them.
    needs_resubmission = await annotate_resubmissions(db)
    register_docs = await apply_oem_filing_to_register(db)

    mirrored = await coll.count_documents({"missingFromOem": {"$ne": True}})
    incomplete = bool(expected is not None and mirrored < expected)
    stats = {
        "claimsMirrored": mirrored,
        "claimsExpected": expected,
        "claimsFetchMode": mode,
        "claimsIncomplete": incomplete,
        "claimsLinked": linked,
        "claimsWithVehicle": with_vehicle,
        "claimDetailCalls": detail_calls,
        "claimDetailFailures": detail_failures,
        "claimsMissingFromOem": stale,
        "claimsNeedsResubmission": needs_resubmission,
        "claimsRegisterPatched": len(register_docs),
        "claimsSyncedAt": now_iso(),
        "claimsSyncOk": True,
    }
    await db["system"].update_one({"_id": "coulson"}, {"$set": stats}, upsert=True)
    return {"ok": True, "credentialSource": src, "registerPatches": register_docs, **stats}


# ---------------------------------------------------------------- register cross-check
# Coulson describes a claim line in prose ("Referral Commission for invoice AF-122-…")
# and types it only as "Scheme Claim". The Scheme Claim Register speaks component keys.
# Nothing in either system maps one to the other, so this table does — on the words that
# actually appear in their descriptions, most specific first.
#
# A miss is NOT read as "never claimed". It resolves to `lead_filed_unmapped`, which asks
# for a human eye instead of sending the money desk chasing a claim that already exists.
COMPONENT_PHRASES = (
    ("rtoInsuranceBenefit", ("free rto + free insurance", "rto + insurance", "rto and insurance")),
    ("insuranceBenefit", ("insurance benefits up to", "insurance benefits", "insurance benefit",
                          "free insurance", "insurance")),
    ("rtoBenefit", ("rto benefit", "free rto", "rto")),
    ("referralBonus", ("referral commission", "referral bonus", "referral")),
    ("loyaltyBonus", ("loyalty bonus", "loyalty")),
    ("exchangeBonus", ("exchange bonus", "exchange benefit", "exchange")),
    ("consumerDiscount", ("consumer scheme", "consumer discount", "consumer offer", "consumer")),
    ("dsaDiscount", ("dsa commission", "dsa payout", "dsa")),
    ("oemExtraSupport", ("extra support", "special support", "additional support")),
    ("additionalDiscount", ("additional discount", "special discount")),
)

# Euler has agreed the money (or paid it). Anything else open is still in the ladder.
ACCEPTED_STATUSES = GENERATED_STATUSES + ("Settled",)

# Coulson's Create Claim chips. The value is what lands on line_item.claim_type.
# These are checked BEFORE description prose: an Additional Support line often
# still says "Insurance Benefits Up to…" in the description, and the word
# "insurance" used to steal the match — OEM Extra Support then read Not claimed
# while OEM Claim Settlements said In scheme register (AF-122-CL2627077).
#
# "Additional Discount Claim" is dealer-funded Additional, which is not an OEM
# claim. Staff pick that chip for Extra Support (AF-122-CL2627161 Kapoor). Treat
# it as Extra Support so Match lists the CRM file.
CLAIM_TYPE_KEYS = (
    ("oemExtraSupport", (
        "additional support", "additional discount claim", "dealer incentive",
        "support scheme (btl)", "support scheme", "oem extra support", "oem extra",
    )),
)

# "Additiniol" / "addtiniol" support documents — same Extra Support prose.
_SUPPORT_PROSE = re.compile(r"\b(?:add\w+|extra|special)\s+support\b")


def _fold_claim_text(value):
    return re.sub(r"[_-]+", " ", str(value or "").lower()).strip()


def map_claim_type_to_component(claim_type, description=""):
    """Best-effort componentKey for a Coulson line. Empty when nothing matches.

    Claim type wins over description. Scheme Claim lines still fall through to
    COMPONENT_PHRASES on the prose ("Referral Commission for invoice …").
    """
    type_folded = _fold_claim_text(claim_type)
    for key, phrases in CLAIM_TYPE_KEYS:
        if any(p in type_folded for p in phrases):
            return key
    hay = f"{_fold_claim_text(description)} {type_folded}".strip()
    if _SUPPORT_PROSE.search(hay):
        return "oemExtraSupport"
    for key, phrases in COMPONENT_PHRASES:
        if any(p in hay for p in phrases):
            return key
    return ""


async def annotate_resubmissions(db):
    """A rejected claim is only a problem if nobody filed it again.

    Euler does not reopen a rejected debit note — a resubmission is a NEW note for the
    same chassis. So a rejection with a later claim on that chassis has been handled,
    and one without is money that quietly stopped being chased. Only the second is an
    alert.
    """
    by_chassis = {}
    async for row in db[CLAIMS_COLLECTION].find({}):
        for line in _line_item_list(row.get("lineItems")):
            for ch in line_chassis_list(line):
                by_chassis.setdefault(ch, []).append(row)
    for ch, rows in by_chassis.items():
        rows.sort(key=lambda r: str(r.get("createdAt") or ""))
    flagged = 0
    async for row in db[CLAIMS_COLLECTION].find({"status": "Rejected"}):
        created = str(row.get("createdAt") or "")
        successor = ""
        for line in _line_item_list(row.get("lineItems")):
            for ch in line_chassis_list(line):
                for other in by_chassis.get(ch) or []:
                    if other.get("debitNoteId") == row.get("debitNoteId"):
                        continue
                    if str(other.get("createdAt") or "") <= created:
                        continue
                    if str(other.get("status") or "") == "Cancelled":
                        continue
                    successor = other.get("claimNumber") or ""
                    break
                if successor:
                    break
            if successor:
                break
        patch = {"resubmittedBy": successor, "needsResubmission": not successor}
        if not successor:
            flagged += 1
        await db[CLAIMS_COLLECTION].update_one({"_id": row["_id"]}, {"$set": patch})
    return flagged


def _empty_match_entry():
    return {
        "byComponent": {}, "unmapped": [], "claimNumbers": [],
        "filedTotal": 0.0, "acceptedTotal": 0.0,
        "rejectedOpen": [], "hasAnyClaim": False,
    }


def _absorb_line(entry, row, line):
    """Fold one Euler line into a match entry (by lead, chassis or invoice)."""
    if not isinstance(line, dict):
        return entry
    status = str(row.get("status") or "")
    entry["hasAnyClaim"] = True
    amount = round2(line.get("totalAmount"))
    if status != "Cancelled":
        entry["filedTotal"] = round2(entry["filedTotal"] + amount)
    if status in ACCEPTED_STATUSES:
        entry["acceptedTotal"] = round2(entry["acceptedTotal"] + amount)
    if row.get("claimNumber") and row["claimNumber"] not in entry["claimNumbers"]:
        entry["claimNumbers"].append(row["claimNumber"])
    hit = {
        "claimNumber": row.get("claimNumber") or "",
        "lineId": str(line.get("lineId") or ""),
        "oemStatus": status,
        "amount": amount,
        "stageLabel": row.get("stageLabel") or "",
        "stageDays": _as_int(row.get("stageDays")),
        "createdAt": row.get("createdAt") or "",
        "needsResubmission": bool(row.get("needsResubmission")),
        "resubmittedBy": row.get("resubmittedBy") or "",
        "description": line.get("description") or "",
        "hasDocument": _as_int(line.get("documentCount")) > 0,
        "documentCount": _as_int(line.get("documentCount")),
        "claimDocumentUrl": str(row.get("claimDocumentUrl") or ""),
    }
    if status == "Rejected" and row.get("needsResubmission"):
        entry["rejectedOpen"].append(hit)
    key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
    if key:
        entry["byComponent"].setdefault(key, []).append(hit)
    else:
        entry["unmapped"].append(hit)
    return entry


async def relink_stored_claims(db):
    """Stamp leadId onto stored Euler lines now that leads have chassis / invoice.

    Claim sync often runs before Sold/delivery writes those ids onto the lead, so
    every register row then reads as Not claimed even though Euler already holds
    the debit note. Relinking is local — no Coulson call.
    """
    lead_index = await build_lead_index(db)
    patched = 0
    async for row in db[CLAIMS_COLLECTION].find({}):
        before = _as_id_list(row.get("leadIds"))
        updated = await link_claim_lines(db, row, lead_index)
        if _as_id_list(updated.get("leadIds")) == before:
            continue
        await db[CLAIMS_COLLECTION].update_one(
            {"_id": row["_id"]} if row.get("_id") else {"debitNoteId": row.get("debitNoteId")},
            {"$set": {
                "lineItems": updated.get("lineItems") or [],
                "leadIds": updated.get("leadIds") or [],
                "linkedLineCount": updated.get("linkedLineCount") or 0,
                "unlinkedLineCount": updated.get("unlinkedLineCount") or 0,
                "invoiceConflicts": updated.get("invoiceConflicts") or [],
            }})
        patched += 1
    return patched


async def register_match_index(db, *, relink=True):
    """What Euler holds, keyed the way the register asks: lead, then chassis, then invoice.

    A line with no leadId still belongs to a vehicle. Indexing it by chassis / invoice
    is what stops Divine Public School (and every other row) reading as Not claimed
    when the debit note is sitting in oem_portal_claims unlinked.

    relink=False is the GET /claims path — restamping every debit note on page
    load is what made the register miss the 25s browser timeout and render empty.
    """
    if relink:
        await relink_stored_claims(db)
    by_lead, by_chassis, by_invoice, by_number, by_line = {}, {}, {}, {}, {}
    async for row in db[CLAIMS_COLLECTION].find({}):
        row.pop("_id", None)
        stamp_document_flag(row)
        coerce_line_items(row)
        num = str(row.get("claimNumber") or "").strip().upper()
        if num:
            by_number[num] = {
                "claimNumber": row.get("claimNumber") or "",
                "oemStatus": str(row.get("status") or ""),
                "amount": round2(row.get("claimedAmount")),
                "stageLabel": row.get("stageLabel") or "",
                "stageDays": _as_int(row.get("stageDays")),
                "createdAt": row.get("createdAt") or "",
                "needsResubmission": bool(row.get("needsResubmission")),
                "resubmittedBy": row.get("resubmittedBy") or "",
                "description": "",
                "hasDocument": bool(row.get("hasDocument")),
                "documentCount": _as_int(row.get("documentCount")),
                "lineItemCount": _as_int(row.get("lineItemCount")),
                "documentedLineCount": _as_int(row.get("documentedLineCount")),
                "claimDocumentUrl": str(row.get("claimDocumentUrl") or ""),
            }
        for line in coerce_line_items(row):
            for lead_id in line_lead_ids(line):
                _absorb_line(by_lead.setdefault(lead_id, _empty_match_entry()), row, line)
            for ch in line_chassis_list(line):
                _absorb_line(by_chassis.setdefault(ch, _empty_match_entry()), row, line)
            inv = str(line.get("sourceInvoiceNumber") or "").strip().lower()
            if not inv:
                desc = f"{line.get('description') or ''} {line.get('claimType') or ''}"
                m = re.search(r"\bAF-\d+-I\d+\b", desc, re.I)
                inv = (m.group(0) if m else "").lower()
            if inv:
                _absorb_line(by_invoice.setdefault(inv, _empty_match_entry()), row, line)
            lid = str(line.get("lineId") or "").strip()
            if num and lid:
                hit = {
                    "claimNumber": row.get("claimNumber") or "",
                    "lineId": lid,
                    "oemStatus": str(row.get("status") or ""),
                    "amount": round2(line.get("totalAmount")),
                    "stageLabel": row.get("stageLabel") or "",
                    "stageDays": _as_int(row.get("stageDays")),
                    "createdAt": row.get("createdAt") or "",
                    "needsResubmission": bool(row.get("needsResubmission")),
                    "resubmittedBy": row.get("resubmittedBy") or "",
                    "description": line.get("description") or "",
                    "hasDocument": _as_int(line.get("documentCount")) > 0,
                    "documentCount": _as_int(line.get("documentCount")),
                    "claimDocumentUrl": str(row.get("claimDocumentUrl") or ""),
                }
                by_line[f"{num}:{lid}"] = hit
    return {"byLead": by_lead, "byChassis": by_chassis, "byInvoice": by_invoice,
            "byNumber": by_number, "byLine": by_line}


def _index_packs(index):
    """Accept the packed index and the older by-lead-id shape the unit tests use."""
    if isinstance(index, dict) and "byLead" in index and "byChassis" in index:
        packs = dict(index)
        packs.setdefault("byNumber", {})
        packs.setdefault("byLine", {})
        return packs
    return {"byLead": index or {}, "byChassis": {}, "byInvoice": {}, "byNumber": {},
            "byLine": {}}


# OEM Extra Support is a staff-typed side ledger in this app. In Coulson it is
# filed as Additional Support / Dealer Incentive / Support Scheme (BTL), or as
# prose that names extra/additional support. A Scheme Claim for Insurance /
# Loyalty on the same vehicle is NOT that filing — treating it as one made Extra
# Support look claimed in Euler when the dealer never raised it.


def _state_from_hits(hits):
    live = [h for h in hits if h.get("oemStatus") not in ("Rejected", "Cancelled")]
    rejected = [h for h in hits if h.get("oemStatus") == "Rejected"]
    cancelled = [h for h in hits if h.get("oemStatus") == "Cancelled"]
    pick = live[0] if live else (rejected[0] if rejected else hits[0])
    if live:
        state = "accepted" if pick.get("oemStatus") in ACCEPTED_STATUSES else "filed"
    elif rejected:
        state = "resubmitted" if rejected[0].get("resubmittedBy") else "rejected"
    elif cancelled:
        state = "cancelled"
    else:
        state = "not_filed"
    detail = ""
    if state == "rejected":
        detail = "Euler rejected this and no replacement claim has been filed."
    elif state == "resubmitted":
        detail = f"Rejected, refiled as {rejected[0]['resubmittedBy']}."
    elif state == "cancelled":
        detail = "OEM claim was cancelled. Relink the replacement debit note."
    elif state == "filed" and pick.get("stageLabel"):
        detail = f"{pick.get('stageDays') or 0}d at {pick['stageLabel']}."
    return {
        "state": state,
        "claimNumbers": [h.get("claimNumber") for h in hits if h.get("claimNumber")],
        "oemStatus": pick.get("oemStatus") or "",
        "filedAmount": round2(sum(_num(h.get("amount")) for h in hits)),
        "stageLabel": pick.get("stageLabel") or "",
        "stageDays": _as_int(pick.get("stageDays")),
        "createdAt": str(pick.get("createdAt") or "")[:10],
        "hasDocument": bool(hits) and all(h.get("hasDocument") for h in hits),
        "documentCount": max((_as_int(h.get("documentCount")) for h in hits), default=0),
        "claimDocumentUrl": next((h.get("claimDocumentUrl") for h in hits if h.get("claimDocumentUrl")), "") or "",
        "detail": detail,
    }


def match_state(index, lead_id, component_key, chassis="", invoice="",
                manual_claim_number="", manual_line_id=""):
    """How this register row stands against Euler. Never guesses "unclaimed".

    Join order: a desk-made manual link (claim number + optional line id), then
    lead id, chassis, then invoice. Chassis/invoice are how the desk actually
    ties a scheme-drawer row to a Coulson debit note; lead id alone misses every
    claim that was mirrored before those ids landed on the lead.

    filed / accepted  — Euler has it, and has agreed it where `accepted`
    rejected          — refused and nobody filed it again: act
    cancelled         — the matched OEM note was cancelled; relink the replacement
    resubmitted       — refused, but a newer claim exists: informational
    unmapped          — the lead has claims, none of them reads as this component:
                        needs a human, NOT a gap
    not_filed         — nothing at all was filed for this vehicle: a genuine gap
    """
    packs = _index_packs(index)
    manual = str(manual_claim_number or "").strip()
    line_key = str(manual_line_id or "").strip()
    ch = oem_sync._norm_chassis(chassis)
    if manual:
        hit = None
        if line_key:
            hit = packs.get("byLine", {}).get(f"{manual.upper()}:{line_key}")
        if not hit:
            hit = packs.get("byNumber", {}).get(manual.upper())
        if hit:
            got = _state_from_hits([hit])
            got["manual"] = True
            got["lineId"] = hit.get("lineId") or line_key
            got["detail"] = ((got.get("detail") + " ") if got.get("detail") else "") + (
                "Manually matched to this OEM claim.")
            return got
        return {"state": "not_filed", "claimNumbers": [manual], "oemStatus": "",
                "filedAmount": 0.0, "hasDocument": False, "documentCount": 0,
                "manual": True, "lineId": line_key,
                "detail": "Manual OEM claim number is not in the last Euler sync. Sync again."}
    entry = None
    # Pack Extra Support is per chassis. Lead-first would glue every Extra
    # Support debit note on the file onto every unit of the pack.
    extra_chassis = component_key == "oemExtraSupport" and bool(ch)
    if extra_chassis:
        entry = packs["byChassis"].get(ch)
    else:
        entry = packs["byLead"].get(lead_id)
        if not entry and ch:
            entry = packs["byChassis"].get(ch)
    if not entry:
        inv = str(invoice or "").strip().lower()
        if inv:
            entry = packs["byInvoice"].get(inv)
    if not entry:
        return {"state": "not_filed", "claimNumbers": [], "oemStatus": "",
                "filedAmount": 0.0, "hasDocument": False, "documentCount": 0,
                "detail": "No claim filed with Euler for this lead."}
    hits = entry["byComponent"].get(component_key) or []
    if not hits:
        if entry["unmapped"]:
            um = entry["unmapped"]
            return {
                "state": "unmapped",
                "claimNumbers": [h["claimNumber"] for h in um],
                "oemStatus": "", "filedAmount": round2(entry["filedTotal"]),
                "hasDocument": any(h.get("hasDocument") for h in um),
                "documentCount": max((_as_int(h.get("documentCount")) for h in um), default=0),
                "detail": "This lead has claims in Euler, but none of them names this "
                          "component. Check before treating it as unclaimed.",
            }
        extra = " No Additional Support / Extra Support claim was filed in the OEM app." \
            if component_key == "oemExtraSupport" else ""
        return {"state": "not_filed", "claimNumbers": [], "oemStatus": "",
                "filedAmount": 0.0, "hasDocument": False, "documentCount": 0,
                "detail": "Euler holds a claim for this vehicle, but it maps to a "
                          "different component than this register row." + extra}
    return _state_from_hits(hits)


_LOCK_REGISTER_STATUSES = ("Received", "Partial", "Dropped")
_STATUS_RANK = {"Pending": 0, "Submitted": 1, "Approved": 2}


def _oem_note_is_dead(status) -> bool:
    return str(status or "").strip() in ("Cancelled", "Rejected")


def _lead_blocks_claim_relink(lead) -> bool:
    """A cancelled booking stays dead. OEM-cancel on a live file can be relinked."""
    if not lead:
        return False
    if lead.get("dealCancelled"):
        return True
    return str(lead.get("accountStatus") or "").strip().lower() == "cancelled"


def register_status_from_oem(oem_status, current=""):
    """Map Euler's ladder onto the register's Pending/Submitted/Approved/Received.

    Received / Partial / Dropped stay put — those are money-desk or write-off
    states this overlay must never invent. Cancelled stays put while the matched
    OEM note is still cancelled (or missing). A live replacement note reopens
    the row so a cancel-and-refile can be relinked. Open Euler claims become
    Submitted; generated / settled notes become Approved. Rejected Euler notes
    become Rejected. Cancelled Euler notes become Cancelled.
    receivedAmount is never touched.
    """
    cur = str(current or "").strip() or "Pending"
    if cur in _LOCK_REGISTER_STATUSES:
        return cur
    oem = str(oem_status or "").strip()
    if cur == "Cancelled" and (not oem or oem == "Cancelled"):
        return "Cancelled"
    if cur == "Cancelled":
        cur = "Pending"
    if oem == "Rejected":
        return "Rejected"
    if oem == "Cancelled":
        return "Cancelled"
    if oem in ACCEPTED_STATUSES:
        target = "Approved"
    elif oem:
        target = "Submitted"
    else:
        return cur
    if _STATUS_RANK.get(cur, 0) > _STATUS_RANK.get(target, 0):
        return cur
    return target


def overlay_register_from_oem(row, match):
    """Copy Euler filing onto a register row. Returns (row, patch).

    Patch never contains eligibleClaim / claimAmount / receivedAmount.
    """
    row = dict(row)
    match = match or {}
    state = match.get("state") or ""
    patch = {
        "oemMatchState": state,
        "oemStatus": match.get("oemStatus") or "",
        "oemStageLabel": match.get("stageLabel") or "",
    }
    row["oemMatchState"] = patch["oemMatchState"]
    row["oemStatus"] = patch["oemStatus"]
    row["oemStageLabel"] = patch["oemStageLabel"]
    if state in ("filed", "accepted", "rejected", "resubmitted", "unmapped", "cancelled"):
        nums = [n for n in (match.get("claimNumbers") or []) if n]
        if nums:
            patch["claimReference"] = nums[0]
            row["claimReference"] = nums[0]
        new_status = register_status_from_oem(
            match.get("oemStatus") or "", row.get("claimStatus") or "Pending")
        if new_status != (row.get("claimStatus") or ""):
            patch["claimStatus"] = new_status
            row["claimStatus"] = new_status
        created = str(match.get("createdAt") or "")[:10]
        if re.match(r"^\d{4}-\d{2}-\d{2}$", created):
            if not str(row.get("submittedDate") or "").strip():
                patch["submittedDate"] = created
                row["submittedDate"] = created
            if row.get("claimStatus") == "Approved" and not str(row.get("approvedDate") or "").strip():
                patch["approvedDate"] = created
                row["approvedDate"] = created
    elif state == "not_filed":
        if match.get("manual"):
            nums = [n for n in (match.get("claimNumbers") or []) if n]
            if nums:
                patch["claimReference"] = nums[0]
                row["claimReference"] = nums[0]
            return row, patch
        # A previous vehicle-wide Extra Support match may have stamped another
        # component's claim number / Submitted. Drop that once we know Euler
        # never filed THIS component.
        if str(row.get("claimReference") or ""):
            patch["claimReference"] = ""
            row["claimReference"] = ""
        cur = str(row.get("claimStatus") or "").strip() or "Pending"
        if cur not in _LOCK_REGISTER_STATUSES and cur in ("Submitted", "Approved", "Rejected"):
            patch["claimStatus"] = "Pending"
            row["claimStatus"] = "Pending"
    return row, patch


async def apply_oem_filing_to_register(db, index=None, *, lead_ids=None, relink=None):
    """Stamp Euler claim number / status / dates onto matching register rows.

    Money is untouched. Called after claim sync and Match — not on GET /claims.
    Match passes the attached lead ids with relink=False so a five-unit pack
    save does not rescan every Euler debit note (that missed the 25s timeout
    and surfaced as "Could not save match").
    """
    if index is None:
        index = await register_match_index(
            db, relink=True if relink is None else bool(relink))
    query = {"manual": {"$ne": True}}
    lids = [str(x).strip() for x in (lead_ids or []) if str(x).strip()]
    if lids:
        query["leadId"] = {"$in": lids}
    claims = [c async for c in db.claims.find(query)]
    lead_ids = list({c.get("leadId") for c in claims if c.get("leadId")})
    leads = {}
    if lead_ids:
        async for lead in db.leads.find(
            {"leadId": {"$in": lead_ids}},
            {"leadId": 1, "chassisNumber": 1, "invoiceNumber": 1, "units": 1, "_id": 0},
        ):
            leads[lead.get("leadId")] = lead
    patched = []
    for c in claims:
        lead = leads.get(c.get("leadId")) or {}
        chassis = c.get("chassisNumber") or ""
        if not chassis and c.get("unitSno"):
            try:
                want_unit = int(c.get("unitSno"))
            except (TypeError, ValueError):
                want_unit = None
            for u in (lead.get("units") or []):
                if not isinstance(u, dict):
                    continue
                try:
                    got_unit = int(u.get("unitSno") or 0)
                except (TypeError, ValueError):
                    got_unit = 0
                if want_unit is not None and got_unit == want_unit:
                    chassis = u.get("chassisNumber") or ""
                    break
        if not chassis:
            chassis = lead.get("chassisNumber") or ""
        invoice = c.get("invoiceNumber") or lead.get("invoiceNumber") or ""
        match = match_state(
            index, c.get("leadId") or "", c.get("componentKey") or "",
            chassis=chassis, invoice=invoice,
            manual_claim_number=c.get("manualOemClaimNumber") or "",
            manual_line_id=c.get("manualOemLineId") or "")
        row = {
            "claimStatus": c.get("claimStatus") or "Pending",
            "claimReference": c.get("claimReference") or "",
            "submittedDate": c.get("submittedDate") or "",
            "approvedDate": c.get("approvedDate") or "",
        }
        _, patch = overlay_register_from_oem(row, match)
        if chassis and c.get("chassisNumber") != chassis:
            patch["chassisNumber"] = chassis
        if invoice and c.get("invoiceNumber") != invoice:
            patch["invoiceNumber"] = invoice
        persist = {k: v for k, v in patch.items() if c.get(k) != v}
        if not persist:
            continue
        await db.claims.update_one({"_id": c["_id"]}, {"$set": persist})
        c.update(persist)
        c.pop("_id", None)
        patched.append(c)
    return patched


async def oem_only_lines(db, register_pairs):
    """Euler's side of the cross-check: claim lines that still have no CRM match.

    A line already stamped with a lead — chassis, invoice, or Match — is done
    work. Listing it again as "not in the register" kept matched Referral /
    Extra Support notes in the unmatched queue.
    """
    out = []
    manual = await load_manual_oem_links(db)
    async for row in db[CLAIMS_COLLECTION].find({}):
        if str(row.get("status") or "") == "Cancelled":
            continue
        num = str(row.get("claimNumber") or "").strip().upper()
        if num and manual.get(num):
            continue
        for line in _line_item_list(row.get("lineItems")):
            leads = line_lead_ids(line)
            if leads:
                continue
            key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
            out.append({
                "claimNumber": row.get("claimNumber") or "",
                "oemStatus": row.get("status") or "",
                "stageLabel": row.get("stageLabel") or "",
                "stageDays": _as_int(row.get("stageDays")),
                "createdDate": row.get("createdDate") or "",
                "leadId": "",
                "lineId": str(line.get("lineId") or ""),
                "customer": line.get("leadCustomer") or "",
                "chassis": line.get("chassis") or "",
                "sourceInvoiceNumber": line.get("sourceInvoiceNumber") or "",
                "description": line.get("description") or "",
                "claimType": line.get("claimType") or "",
                "mappedComponent": key,
                "amount": round2(line.get("totalAmount")),
                "hasVehicle": bool(line_chassis_list(line) or line.get("sourceInvoiceNumber")),
                "reason": "unknown_lead",
            })
    out.sort(key=lambda r: -r["amount"])
    return out


# ---------------------------------------------------------------- reporting
async def register_pairs(db):
    """(leadId, componentKey) the Scheme Claim Register actually holds.

    Manual / executive-incentive rows are skipped — they are not filed as scheme
    lines in Coulson, so comparing them here would paint every Euler claim as a gap.
    """
    pairs = set()
    async for c in db.claims.find(
            {"manual": {"$ne": True}, "claimStatus": {"$ne": "Dropped"}},
            {"leadId": 1, "componentKey": 1, "_id": 0}):
        lid, key = c.get("leadId") or "", c.get("componentKey") or ""
        if lid and key:
            pairs.add((lid, key))
    return pairs


def claim_register_match(row, pairs, manual_links=None):
    """How this Euler debit note stands against the Scheme Claim Register.

    The reverse of `match_state`: that function colours a register row by whether
    Euler filed it; this colours an Euler claim by whether the register raised it.
    A miss here is money Euler is processing that the books do not know they are owed.
    A desk-made manual link always wins — that is how unmapped wording is joined.
    """
    num = str(row.get("claimNumber") or "").strip().upper()
    links = (manual_links or {}).get(num) or []
    line_ids_linked = {str(x.get("lineId") or "") for x in links if x.get("lineId")}
    whole_manual = bool(links) and not line_ids_linked
    lines = _line_item_list(row.get("lineItems"))
    if whole_manual:
        keys = [x.get("componentKey") for x in links if x.get("componentKey")]
        return {"state": "in_register",
                "detail": "Manually matched to the Scheme Claim Register.",
                "mappedComponents": keys, "manual": True,
                "needsResubmission": bool(row.get("needsResubmission")),
                "resubmittedBy": row.get("resubmittedBy") or ""}
    if not lines:
        if links:
            keys = [x.get("componentKey") for x in links if x.get("componentKey")]
            return {"state": "in_register",
                    "detail": "Manually matched to the Scheme Claim Register.",
                    "mappedComponents": keys, "manual": True,
                    "needsResubmission": bool(row.get("needsResubmission")),
                    "resubmittedBy": row.get("resubmittedBy") or ""}
        return {"state": "unknown_lead", "detail": "No line items on this claim.",
                "mappedComponents": []}
    states, keys = [], []
    for line in lines:
        leads = line_lead_ids(line)
        key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
        lid = str(line.get("lineId") or "")
        if key:
            keys.append(key)
        if lid and lid in line_ids_linked:
            states.append("in_register")
        elif leads:
            # Chassis / invoice / Match already joined a CRM lead. That is
            # matched work — not a "not in scheme register" chase item.
            states.append("in_register")
        else:
            states.append("unknown_lead")
    if "in_register" in states and any(s != "in_register" for s in states):
        pick = "partial"
    else:
        order = ("unknown_lead", "missing_register", "unmapped", "in_register")
        pick = min(states, key=lambda s: order.index(s) if s in order else 99)
    detail = {
        "unknown_lead": "No chassis or invoice on this claim matched a lead.",
        "missing_register": "Euler filed this, but the Scheme Claim Register has no row.",
        "unmapped": "This lead is in the register, but the claim wording did not map to a component.",
        "in_register": "Matched to a lead or the Scheme Claim Register.",
        "partial": "Some items on this OEM claim are matched; others still need a lead.",
    }.get(pick, "")
    if row.get("status") == "Rejected" and row.get("needsResubmission"):
        detail = (detail + " " if detail else "") + "Rejected — nothing refiled on this chassis."
    elif row.get("resubmittedBy"):
        detail = (detail + " " if detail else "") + f"Rejected, refiled as {row['resubmittedBy']}."
    return {"state": pick, "detail": detail.strip(),
            "mappedComponents": keys,
            "manual": bool(links),
            "needsResubmission": bool(row.get("needsResubmission")),
            "resubmittedBy": row.get("resubmittedBy") or ""}


async def load_manual_oem_links(db):
    """claimNumber.upper() -> [{leadId, componentKey, claimId, lineId}]."""
    by_oem = {}
    async for c in db.claims.find(
            {"manualOemClaimNumber": {"$nin": ["", None]}},
            {"leadId": 1, "componentKey": 1, "claimId": 1, "manualOemClaimNumber": 1,
             "manualOemLineId": 1, "_id": 0}):
        num = str(c.get("manualOemClaimNumber") or "").strip().upper()
        lid, key = c.get("leadId") or "", c.get("componentKey") or ""
        if num and key:
            by_oem.setdefault(num, []).append({
                "leadId": lid, "componentKey": key, "claimId": c.get("claimId") or "",
                "lineId": str(c.get("manualOemLineId") or ""),
            })
    return by_oem


async def attach_register_match(db, rows):
    pairs = await register_pairs(db)
    manual = await load_manual_oem_links(db)
    for row in rows:
        coerce_line_items(row)
        stamp_document_flag(row)
        row["registerMatch"] = claim_register_match(row, pairs, manual)
    return rows


def _claim_matches_query(row, *, q="", chassis="", invoice=""):
    lines = _line_item_list(row.get("lineItems"))
    if chassis:
        ch = oem_sync._norm_chassis(chassis)
        if not any(ch in line_chassis_list(li) for li in lines):
            return False
    if invoice:
        inv = str(invoice or "").strip().lower()
        if not any(str(li.get("sourceInvoiceNumber") or "").strip().lower() == inv
                   for li in lines):
            return False
    if q:
        needle = str(q).strip().lower()
        blob = " ".join([
            str(row.get("claimNumber") or ""),
            str(row.get("status") or ""),
            " ".join(_as_id_list(row.get("leadIds"))),
            " ".join(" ".join(line_chassis_list(li)) for li in lines),
            " ".join(str(li.get("sourceInvoiceNumber") or "") for li in lines),
            " ".join(str(li.get("leadCustomer") or "") for li in lines),
            " ".join(str(li.get("description") or "") for li in lines),
        ]).lower()
        if needle not in blob:
            return False
    return True


def oem_claim_is_unmatched(row):
    """True while any line still needs a lead / register match."""
    state = ((row or {}).get("registerMatch") or {}).get("state") or ""
    return state != "in_register"


async def list_claims(db, *, status="", lead_id="", unlinked=False,
                      q="", chassis="", invoice="", missing_doc=False,
                      missing_vehicle=False, exclude_missing_vehicle=False,
                      unmatched_only=False):
    filt = {}
    if status:
        filt["status"] = status
    if lead_id:
        filt["leadIds"] = lead_id
    rows = [r async for r in db[CLAIMS_COLLECTION].find(filt)]
    if unlinked:
        rows = [r for r in rows if not (r.get("linkedLineCount") or 0)]
    if missing_doc:
        rows = [r for r in rows if not stamp_document_flag(r).get("hasDocument")]
    if missing_vehicle:
        rows = [r for r in rows if not _lines_have_vehicle(r.get("lineItems"))]
    elif exclude_missing_vehicle:
        rows = [r for r in rows if _lines_have_vehicle(r.get("lineItems"))]
    if q or chassis or invoice:
        rows = [r for r in rows if _claim_matches_query(
            r, q=q, chassis=chassis, invoice=invoice)]
    rows.sort(key=lambda r: (r.get("terminal") and 1 or 0, -_as_int(r.get("stageDays")),
                             str(r.get("createdAt") or "")))
    for r in rows:
        r.pop("_id", None)
    await attach_register_match(db, rows)
    if unmatched_only:
        rows = [r for r in rows if oem_claim_is_unmatched(r)]
    return rows


async def claims_for_lead(db, lead_id):
    """Every claim carrying a line for this lead, with that lead's lines only."""
    out = []
    async for row in db[CLAIMS_COLLECTION].find({"leadIds": lead_id}):
        row.pop("_id", None)
        mine = [li for li in _line_item_list(row.get("lineItems")) if lead_id in line_lead_ids(li)]
        out.append({
            **{k: v for k, v in row.items() if k != "lineItems"},
            "lineItems": mine,
            "leadClaimedAmount": round2(sum(_num(li.get("totalAmount")) for li in mine)),
        })
    out.sort(key=lambda r: str(r.get("createdAt") or ""), reverse=True)
    return out


async def lead_claim_crosscheck(db, lead_id, lead=None):
    """OEM claims AND scheme-register rows for one lead, joined on chassis / invoice.

    The scheme drawer creates the register rows; this is what the drawer reads so a
    salesperson can see, on the same lead, whether Euler actually filed them.
    """
    lead = lead or {}
    await relink_stored_claims(db)
    oem = await claims_for_lead(db, lead_id)
    await attach_register_match(db, oem)
    index = await register_match_index(db, relink=False)
    units = [u for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    stored = [c async for c in db.claims.find({"leadId": lead_id, "manual": {"$ne": True}})]
    has_unit_extra = any(
        str(c.get("componentKey") or "") == "oemExtraSupport" and int(c.get("unitSno") or 0) > 0
        for c in stored)
    register = []
    for c in stored:
        key = c.get("componentKey") or ""
        if not key or str(c.get("claimStatus") or "") == "Dropped":
            continue
        sno = int(c.get("unitSno") or 0)
        if key == "oemExtraSupport" and not sno and has_unit_extra:
            continue
        unit = units[sno - 1] if sno and 0 < sno <= len(units) else {}
        if key == "oemExtraSupport":
            chassis = str(c.get("chassisNumber") or unit.get("chassisNumber") or "").strip()
            invoice = str(c.get("invoiceNumber") or unit.get("invoiceNumber") or "").strip()
        else:
            chassis = str(c.get("chassisNumber") or unit.get("chassisNumber")
                          or lead.get("chassisNumber") or "").strip()
            invoice = str(c.get("invoiceNumber") or unit.get("invoiceNumber")
                          or lead.get("invoiceNumber") or "").strip()
        register.append({
            "claimId": c.get("claimId") or f"CLM-{lead_id}-{key}",
            "componentKey": key,
            "component": c.get("component") or key,
            "unitSno": sno or None,
            "eligibleClaim": round2(c.get("eligibleClaim") if c.get("eligibleClaim") is not None
                                    else c.get("claimAmount")),
            "claimStatus": c.get("claimStatus") or "",
            "receivedAmount": round2(c.get("receivedAmount")),
            "submittedDate": c.get("submittedDate") or "",
            "approvedDate": c.get("approvedDate") or "",
            "claimReceivedDate": c.get("claimReceivedDate") or "",
            "oemMatch": match_state(
                index, lead_id, key,
                chassis=chassis,
                invoice=invoice,
                manual_claim_number=c.get("manualOemClaimNumber") or "",
                manual_line_id=c.get("manualOemLineId") or ""),
        })
    return {
        "claims": oem,
        "schemeRegister": register,
        "chassisNumber": lead.get("chassisNumber") or "",
        "invoiceNumber": lead.get("invoiceNumber") or "",
        "leadId": lead_id,
    }


async def claims_summary(db):
    """Bucket counts and money, plus the two lists worth acting on.

    `stuck` is what the chase list is for; `rejected` is money the dealer's own
    register may still be carrying as receivable when Euler has already refused it.
    """
    buckets = {}
    totals = {"claimed": 0.0, "approved": 0.0, "openClaimed": 0.0}
    stuck, rejected, conflicts = [], [], []
    total = 0
    with_vehicle = 0
    missing_doc = 0
    async for row in db[CLAIMS_COLLECTION].find({}):
        row.pop("_id", None)
        total += 1
        stamp_document_flag(row)
        if not row.get("hasDocument") and str(row.get("status") or "") != "Cancelled":
            missing_doc += 1
        if _lines_have_vehicle(row.get("lineItems")):
            with_vehicle += 1
        status = str(row.get("status") or "Unknown")
        b = buckets.setdefault(status, {"status": status, "count": 0, "claimed": 0.0, "approved": 0.0})
        b["count"] += 1
        b["claimed"] = round2(b["claimed"] + _num(row.get("claimedAmount")))
        b["approved"] = round2(b["approved"] + _num(row.get("approvedAmount")))
        totals["claimed"] = round2(totals["claimed"] + _num(row.get("claimedAmount")))
        totals["approved"] = round2(totals["approved"] + _num(row.get("approvedAmount")))
        if not row.get("terminal"):
            totals["openClaimed"] = round2(totals["openClaimed"] + _num(row.get("claimedAmount")))
            stuck.append({
                "claimNumber": row.get("claimNumber"), "status": status,
                "stageLabel": row.get("stageLabel") or status,
                "stageDays": _as_int(row.get("stageDays")),
                "claimAgeingDays": _as_int(row.get("claimAgeingDays")),
                "claimedAmount": round2(row.get("claimedAmount")),
                "leadIds": row.get("leadIds") or [],
            })
        if status == "Rejected":
            rejected.append({
                "claimNumber": row.get("claimNumber"),
                "claimedAmount": round2(row.get("claimedAmount")),
                "leadIds": row.get("leadIds") or [],
                "needsResubmission": bool(row.get("needsResubmission")),
                "resubmittedBy": row.get("resubmittedBy") or "",
                "lineItems": [{"description": li.get("description"), "leadId": li.get("leadId"),
                               "chassis": li.get("chassis") or "",
                               "sourceInvoiceNumber": li.get("sourceInvoiceNumber") or "",
                               "totalAmount": round2(li.get("totalAmount")),
                               "rejectedBy": li.get("rejectedBy") or ""}
                              for li in _line_item_list(row.get("lineItems"))],
            })
        for msg in row.get("invoiceConflicts") or []:
            if isinstance(msg, dict):
                conflicts.append({
                    "claimNumber": row.get("claimNumber"),
                    "detail": msg.get("detail") or "",
                    "leadId": msg.get("leadId") or "",
                    "chassis": msg.get("chassis") or "",
                    "cancelledInvoice": msg.get("cancelledInvoice") or "",
                    "newInvoice": msg.get("newInvoice") or "",
                    "invoiceCancelled": bool(msg.get("invoiceCancelled")),
                })
            else:
                conflicts.append({"claimNumber": row.get("claimNumber"), "detail": msg})
    stuck.sort(key=lambda r: -r["stageDays"])
    ordered = [buckets[s] for s in coulson_client.CLAIM_STATUSES if s in buckets]
    ordered += [b for s, b in buckets.items() if s not in coulson_client.CLAIM_STATUSES]
    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    return {
        "total": total,
        "buckets": ordered,
        "totals": totals,
        "stuck": stuck[:50],
        "rejected": rejected,
        "invoiceConflicts": conflicts,
        "mirror": {
            "expected": doc.get("claimsExpected"),
            "mirrored": doc.get("claimsMirrored"),
            "incomplete": bool(doc.get("claimsIncomplete")),
            "fetchMode": doc.get("claimsFetchMode") or "",
            "syncedAt": doc.get("claimsSyncedAt") or "",
            "detailFailures": doc.get("claimDetailFailures") or 0,
            "withVehicle": with_vehicle,
            "missingVehicle": max(0, total - with_vehicle),
            "missingDocument": missing_doc,
        },
    }


async def find_oem_claim(db, claim_number):
    number = str(claim_number or "").strip()
    if not number:
        return None
    row = await db[CLAIMS_COLLECTION].find_one({"claimNumber": number})
    if row:
        return row
    return await db[CLAIMS_COLLECTION].find_one(
        {"claimNumber": {"$regex": f"^{re.escape(number)}$", "$options": "i"}})


_OEM_CUSTOMER_RE = re.compile(
    r"customer\s*name\s*[:-]\s*(.+?)(?=\s+approved\s*by|\s*$)", re.I | re.S)


def oem_entry_name(line, oem=None):
    """The name Euler printed on the debit-note line — not a CRM lead."""
    for raw in ((line or {}).get("customerName"), (line or {}).get("leadCustomer")):
        name = str(raw or "").strip()
        if name:
            return name
    desc = str((line or {}).get("description") or "")
    m = _OEM_CUSTOMER_RE.search(desc)
    if m:
        return re.sub(r"\s+", " ", m.group(1)).strip(" -:.")
    desc = re.sub(r"\s+", " ", desc).strip()
    if desc:
        return desc[:120]
    return str((oem or {}).get("claimNumber") or "OEM claim")


def _oem_create_claim_id(claim_number, line_id, component_key):
    safe_num = re.sub(r"[^A-Za-z0-9-]+", "", str(claim_number or "")) or "OEM"
    safe_line = re.sub(r"[^A-Za-z0-9:-]+", "", str(line_id or "0")) or "0"
    safe_key = re.sub(r"[^A-Za-z0-9]+", "", str(component_key or "oemClaim")) or "oemClaim"
    return f"CLM-OEM-{safe_num}-{safe_line}-{safe_key}"


def _pick_oem_line(oem, line_id=""):
    lines = coerce_line_items(oem if isinstance(oem, dict) else {})
    want_line = str(line_id or "").strip()
    if want_line:
        targets = [li for li in lines if str(li.get("lineId") or "") == want_line]
        if not targets:
            raise ValueError("That claim item is not on this OEM claim.")
        return targets[0], lines
    if len(lines) == 1:
        return lines[0], lines
    if not lines:
        raise ValueError("This OEM claim has no line items. Sync from Euler first.")
    raise ValueError(f"This OEM claim has {len(lines)} items. Create each item separately.")


async def resolve_oem_create_target(db, *, claim_number, line_id="", lead_id="",
                                    component_key=""):
    """Pick the OEM line + existing CRM lead + component. Never inserts a lead."""
    oem = await find_oem_claim(db, claim_number)
    if not oem:
        raise ValueError("That OEM claim is not in the last Euler sync. Sync from Euler first.")
    if str(oem.get("status") or "") == "Cancelled":
        raise ValueError("That OEM claim is cancelled.")
    lines = coerce_line_items(oem)
    want_line = str(line_id or "").strip()
    if want_line:
        targets = [li for li in lines if str(li.get("lineId") or "") == want_line]
        if not targets:
            raise ValueError("That claim item is not on this OEM claim.")
        line = targets[0]
    elif len(lines) == 1:
        line = lines[0]
    elif not lines:
        raise ValueError("This OEM claim has no line items. Sync from Euler first.")
    else:
        raise ValueError(
            f"This OEM claim has {len(lines)} items. Create each item separately.")
    want_lead = str(lead_id or line.get("leadId") or "").strip()
    lead = await db.leads.find_one({"leadId": want_lead}) if want_lead else None
    if not lead:
        for ch in line_chassis_list(line):
            lead = await _lead_for_chassis(db, ch)
            if lead:
                break
    if not lead:
        lead = await _lead_for_invoice(db, line.get("sourceInvoiceNumber"))
    if not lead:
        raise ValueError("Pick an existing lead. This will not create a new lead.")
    key = str(component_key or "").strip() or map_claim_type_to_component(
        line.get("claimType"), line.get("description"))
    if not key:
        raise ValueError("Pick a scheme component. The OEM wording did not map.")
    return {
        "oem": oem,
        "line": line,
        "lead": lead,
        "componentKey": key,
        "claimNumber": str(oem.get("claimNumber") or "").strip(),
        "lineId": str(line.get("lineId") or ""),
    }


def extra_support_from_lead(lead, unit_sno=None):
    """Lead / pack-unit Extra Support amount and vehicle ids. Never Coulson money."""
    import commercial as ce
    sno = 0
    try:
        sno = int(unit_sno or 0)
    except (TypeError, ValueError):
        sno = 0
    pack = [u for u in ((lead or {}).get("units") or []) if isinstance(u, dict)]
    if sno and len(pack) > 1:
        # This vehicle only — never the lead roll-up (that glued a pack total
        # onto a sibling that was not selected for this claim).
        unit = pack[sno - 1] if 0 < sno <= len(pack) else {}
        return (
            round2(ce.num((unit or {}).get("oemExtraSupportReceived"))),
            str((unit or {}).get("chassisNumber") or "").strip(),
            str((unit or {}).get("invoiceNumber") or "").strip(),
            sno,
        )
    units = ce.extra_support_unit_rows(lead or {})
    if sno and units:
        unit = next((u for u in units if int(u.get("unitSno") or 0) == sno), {}) or {}
        return (
            round2(unit.get("oemExtraSupportReceived")),
            str(unit.get("chassisNumber") or "").strip(),
            str(unit.get("invoiceNumber") or "").strip(),
            sno,
        )
    return (
        round2(ce.num((lead or {}).get("oemExtraSupportReceived"))),
        str((lead or {}).get("chassisNumber") or "").strip(),
        str((lead or {}).get("invoiceNumber") or "").strip(),
        sno,
    )


def extra_support_unit_amounts(lead):
    import commercial as ce
    return [round2(u.get("oemExtraSupportReceived"))
            for u in ce.extra_support_unit_rows(lead or {})]


def _register_unit_filter(unit_sno=None):
    sno = 0
    try:
        sno = int(unit_sno or 0)
    except (TypeError, ValueError):
        sno = 0
    if sno:
        return {"unitSno": sno}
    return {"$or": [{"unitSno": {"$in": [None, 0]}}, {"unitSno": {"$exists": False}}]}


async def ensure_register_row(db, lead, component_key, *, claim_amount=0.0,
                              eligible_claim=0.0, unit_sno=None):
    """Insert a Scheme Claim Register row for an existing lead. Money is scheme/lead only.

    Keeps `_id` so Match can stamp the OEM claim number on the same document.
    """
    import commercial as ce
    lead_id = str((lead or {}).get("leadId") or "").strip()
    key = str(component_key or "").strip()
    if not lead_id or not key:
        raise ValueError("Lead and scheme component are required.")
    sno = 0
    try:
        sno = int(unit_sno or 0)
    except (TypeError, ValueError):
        sno = 0
    filt = {"leadId": lead_id, "componentKey": key, "manual": {"$ne": True}}
    filt.update(_register_unit_filter(sno))
    rec = await db.claims.find_one(filt)
    if rec:
        return rec, False
    amt, chassis, invoice, sno = extra_support_from_lead(lead, sno)
    if key != ce.OEM_EXTRA_SUPPORT_KEY:
        amt = round2(claim_amount)
        chassis = str(lead.get("chassisNumber") or "").strip()
        invoice = str(lead.get("invoiceNumber") or "").strip()
    elif round2(claim_amount) > 0 and amt <= 0:
        amt = round2(claim_amount)
    elig = round2(eligible_claim if eligible_claim else amt)
    suffix = f"-u{sno}" if sno else ""
    doc = {
        "claimId": f"CLM-{lead_id}-{key}{suffix}",
        "leadId": lead_id,
        "customer": lead.get("customerName") or "",
        "model": lead.get("interestedModel") or "",
        "variant": lead.get("variant") or "",
        "bookingDate": lead.get("bookingDate") or "",
        "executive": lead.get("executive") or "",
        "component": ce.SCHEME_COMPONENT_LABELS.get(key, key),
        "componentKey": key,
        "eligibleClaim": elig,
        "claimAmount": amt,
        "receivedAmount": 0.0,
        "claimStatus": "Pending",
        "claimReference": "",
        "source": ("OEM Extra Support" if key == ce.OEM_EXTRA_SUPPORT_KEY
                   else "Created from OEM claim"),
        "manual": False,
        "chassisNumber": chassis,
        "invoiceNumber": invoice,
        "schemeMonth": ce.scheme_month_from_date(
            lead.get("schemeAsOf") or lead.get("bookingDate") or ""),
        "submittedDate": "",
        "approvedDate": "",
    }
    if sno:
        doc["unitSno"] = sno
    try:
        result = await db.claims.insert_one(dict(doc))
    except DuplicateKeyError:
        rec = await db.claims.find_one({"claimId": doc["claimId"]}) or await db.claims.find_one(filt)
        if rec:
            return rec, False
        raise
    doc["_id"] = result.inserted_id
    return doc, True


async def adopt_or_ensure_register_row(db, *, lead_id, lead, component_key,
                                       unit_sno=None, claim_number="", line_id=""):
    """Attach a Create-from-OEM empty row, or insert Extra Support from the CRM lead.

    Match used to 422 when Extra Support lived only on the lead (no db.claims row)
    or when Create had inserted a lead-less register row. Save match must still
    link the debit note.
    """
    import commercial as ce
    lead_id = str(lead_id or "").strip()
    key = match_register_component_key(component_key)
    claim_number = str(claim_number or "").strip()
    line_id = str(line_id or "").strip()
    amt, chassis, invoice, sno = extra_support_from_lead(lead, unit_sno)

    def _attach_empty(rec):
        patch = {
            "leadId": lead_id,
            "customer": (lead or {}).get("customerName") or rec.get("customer") or "",
            "model": (lead or {}).get("interestedModel") or rec.get("model") or "",
            "variant": (lead or {}).get("variant") or rec.get("variant") or "",
            "bookingDate": (lead or {}).get("bookingDate") or rec.get("bookingDate") or "",
            "executive": (lead or {}).get("executive") or "",
            "chassisNumber": chassis or rec.get("chassisNumber") or "",
            "invoiceNumber": invoice or rec.get("invoiceNumber") or "",
            "oemUnmatched": False,
            "componentKey": key,
            "component": ce.SCHEME_COMPONENT_LABELS.get(key, rec.get("component") or key),
        }
        if sno:
            patch["unitSno"] = sno
        if amt > 0:
            patch["eligibleClaim"] = amt
            patch["claimAmount"] = amt
            if key == ce.OEM_EXTRA_SUPPORT_KEY:
                patch["source"] = "OEM Extra Support"
        return patch

    if claim_number:
        empty_filt = {
            "leadId": {"$in": ["", None]},
            "manualOemClaimNumber": claim_number,
            "manual": {"$ne": True},
        }
        if line_id:
            empty_filt["manualOemLineId"] = line_id
        rec = await db.claims.find_one({**empty_filt, "componentKey": key})
        if not rec and key == ce.OEM_EXTRA_SUPPORT_KEY:
            # Create stored Additional Discount / generic OEM chip; Match is Extra Support.
            rec = await db.claims.find_one(empty_filt)
        if rec:
            patch = _attach_empty(rec)
            await db.claims.update_one({"_id": rec["_id"]}, {"$set": patch})
            rec.update(patch)
            return rec
    if sno and key == ce.OEM_EXTRA_SUPPORT_KEY:
        leftover = await db.claims.find_one({
            "leadId": lead_id,
            "componentKey": key,
            "manual": {"$ne": True},
            "$or": [{"unitSno": {"$in": [None, 0]}}, {"unitSno": {"$exists": False}}],
        })
        if leftover:
            prev = str(leftover.get("manualOemClaimNumber") or "").strip()
            unit_amts = extra_support_unit_amounts(lead)
            leftover_amt = round2(leftover.get("claimAmount") if leftover.get("claimAmount") is not None
                                  else leftover.get("eligibleClaim"))
            pack_total = round2(sum(unit_amts))
            # Kapoor-style: leftover ₹8,000 is both units. Do not turn it into Unit 2.
            is_pack_total = len(unit_amts) > 1 and leftover_amt >= pack_total - 0.01
            if is_pack_total:
                leftover = None
            elif not prev or (claim_number and prev.upper() == claim_number.upper()):
                patch = {"unitSno": sno}
                if chassis:
                    patch["chassisNumber"] = chassis
                if invoice:
                    patch["invoiceNumber"] = invoice
                if amt > 0:
                    patch["eligibleClaim"] = amt
                    patch["claimAmount"] = amt
                await db.claims.update_one({"_id": leftover["_id"]}, {"$set": patch})
                leftover.update(patch)
                return leftover
    rec, _created = await ensure_register_row(
        db, lead, key, claim_amount=amt, eligible_claim=amt, unit_sno=sno)
    return rec


async def create_named_register_from_oem(db, *, claim_number, line_id="",
                                         component_key=""):
    """Insert a Scheme Claim Register row named from the OEM line.

    Does not invent a lead and does not attach one. Coulson claimed/approved
    amounts stay off db.claims. The OEM claim number is stored so the two
    registers stay joined without a CRM lead.
    """
    import commercial as ce
    oem = await find_oem_claim(db, claim_number)
    if not oem:
        raise ValueError("That OEM claim is not in the last Euler sync. Sync from Euler first.")
    if str(oem.get("status") or "") == "Cancelled":
        raise ValueError("That OEM claim is cancelled.")
    line, _ = _pick_oem_line(oem, line_id)
    key = str(component_key or "").strip() or map_claim_type_to_component(
        line.get("claimType"), line.get("description")) or "oemClaim"
    number = str(oem.get("claimNumber") or "").strip()
    lid = str(line.get("lineId") or "")
    claim_id = _oem_create_claim_id(number, lid, key)
    rec = await db.claims.find_one({"claimId": claim_id})
    if not rec:
        rec = await db.claims.find_one({
            "source": "Created from OEM claim",
            "manualOemClaimNumber": number,
            "manualOemLineId": lid,
            "leadId": {"$in": ["", None]},
        })
    patch = {
        "manualOemClaimNumber": number,
        "manualOemLineId": lid,
        "claimReference": number,
    }
    if rec:
        await db.claims.update_one({"_id": rec["_id"]}, {"$set": patch})
        rec.update(patch)
        rec.pop("_id", None)
        oem.pop("_id", None)
        return {"created": False, "register": rec, "oemClaim": stamp_document_flag(oem)}
    name = oem_entry_name(line, oem)
    label = (str(line.get("claimType") or "OEM Claim") if key == "oemClaim"
             else ce.SCHEME_COMPONENT_LABELS.get(key, key))
    as_of = str(oem.get("createdDate") or "")[:10]
    doc = {
        "claimId": claim_id,
        "leadId": "",
        "customer": name,
        "model": line.get("model") or "",
        "variant": line.get("variant") or "",
        "bookingDate": as_of,
        "executive": "",
        "component": label,
        "componentKey": key,
        "eligibleClaim": 0.0,
        "claimAmount": 0.0,
        "receivedAmount": 0.0,
        "claimStatus": "Pending",
        "claimReference": number,
        "source": "Created from OEM claim",
        "manual": False,
        "oemUnmatched": True,
        "chassisNumber": line.get("chassis") or "",
        "invoiceNumber": line.get("sourceInvoiceNumber") or "",
        "schemeMonth": ce.scheme_month_from_date(as_of),
        "submittedDate": "",
        "approvedDate": "",
        "manualOemClaimNumber": number,
        "manualOemLineId": lid,
        "manualOemMatchedAt": now_iso(),
    }
    await db.claims.insert_one(dict(doc))
    oem.pop("_id", None)
    return {"created": True, "register": doc, "oemClaim": stamp_document_flag(oem)}


async def create_register_from_oem(db, *, claim_number, line_id="", lead_id="",
                                   component_key="", claim_amount=0.0,
                                   eligible_claim=0.0):
    """Create a register entry named from the OEM line. Does not attach a lead.

    `lead_id` / Coulson amounts are ignored — Create is not a lead match.
    """
    return await create_named_register_from_oem(
        db, claim_number=claim_number, line_id=line_id, component_key=component_key)


async def _detach_lead_from_oem_claim(db, *, number, lead_id, line_id=""):
    """Remove a CRM lead from a mirrored OEM debit-note line."""
    number = str(number or "").strip()
    lead_id = str(lead_id or "").strip()
    if not number or not lead_id:
        return None
    oem = await find_oem_claim(db, number)
    if not oem:
        return None
    want_line = str(line_id or "").strip()
    lines = coerce_line_items(oem)
    changed = False
    for li in lines:
        if lead_id not in line_lead_ids(li):
            continue
        if want_line and str(li.get("lineId") or "") != want_line:
            continue
        _drop_line_lead(li, lead_id)
        if not line_lead_ids(li) and li.get("matchedBy") == "manual":
            li.pop("matchedBy", None)
        changed = True
    if not changed:
        return oem
    lead_ids = collect_claim_lead_ids(lines)
    patch = {
        "lineItems": lines,
        "leadIds": lead_ids,
        "linkedLineCount": sum(1 for li in lines if line_lead_ids(li)),
        "unlinkedLineCount": sum(1 for li in lines if not line_lead_ids(li)),
    }
    await db[CLAIMS_COLLECTION].update_one(
        {"_id": oem["_id"]} if oem.get("_id") else {"claimNumber": number},
        {"$set": patch})
    oem.update(patch)
    return oem


def match_register_component_key(component_key):
    """Euler 'Additional Discount Claim' is Extra Support in this app."""
    key = str(component_key or "").strip()
    if key == "additionalDiscount":
        return "oemExtraSupport"
    return key


def _unmatched_extra_unit_rows(rows):
    unit_rows = [c for c in (rows or []) if int(c.get("unitSno") or 0) > 0]
    unmatched = [c for c in unit_rows
                 if not str(c.get("manualOemClaimNumber") or "").strip()]
    return unit_rows, unmatched


async def find_register_row(db, *, lead_id, component_key, unit_sno=None):
    """Scheme Claim Register row for this lead + component (+ pack unit)."""
    component_key = match_register_component_key(component_key)
    filt = {"leadId": lead_id, "componentKey": component_key, "manual": {"$ne": True}}
    rows = [c async for c in db.claims.find(filt)]
    if not rows:
        return None
    want = 0
    try:
        want = int(unit_sno or 0)
    except (TypeError, ValueError):
        want = 0
    if want:
        hit = next((c for c in rows if int(c.get("unitSno") or 0) == want), None)
        if hit:
            return hit
        # Do not reuse another unit's row — that glued one Extra Support
        # debit note onto every vehicle on the pack.
        return None
    unit_rows, unmatched = _unmatched_extra_unit_rows(rows)
    if unit_rows:
        # Never attach to the leftover pack-total row once per-unit rows exist.
        if len(unmatched) == 1:
            return unmatched[0]
        if len(unit_rows) == 1:
            return unit_rows[0]
        raise ValueError("This lead has Extra Support on more than one unit. Pick the unit.")
    no_unit = [c for c in rows if not int(c.get("unitSno") or 0)]
    if len(rows) == 1:
        return rows[0]
    if len(no_unit) == 1:
        return no_unit[0]
    raise ValueError("This lead has Extra Support on more than one unit. Pick the unit.")


async def link_register_to_oem(db, *, lead_id, component_key, claim_number, line_id="",
                               unit_sno=None):
    """Desk-made join. Never copies Coulson amounts into db.claims.

    A debit note can carry several Extra Support items. Matching without a line
    id is only allowed when exactly one unmatched item is a candidate — otherwise
    the desk must pick the line so two customers on one claim id are not glued
    to the same lead.

    One Extra Support line can itself cover two leads (5000+5000=10000). Matching
    a second lead ADDS it to that line; it does not replace the first.

    Relink (cancel in OEM, refile under the right head) replaces a previous
    manualOemClaimNumber: the old debit note loses this lead, and a Cancelled
    register row reopens from the new live note.

    A same-order pack can have two Extra Support rows (one per unit). unit_sno
    picks which vehicle's claim this debit note settles.
    """
    lead_id = str(lead_id or "").strip()
    component_key = match_register_component_key(component_key)
    want_line = str(line_id or "").strip()
    oem = await find_oem_claim(db, claim_number)
    if not oem:
        raise ValueError("That OEM claim is not in the last Euler sync. Sync from Euler first.")
    if _oem_note_is_dead(oem.get("status")):
        raise ValueError("That OEM claim is cancelled. Relink to the new live claim.")
    lead_row = await db.leads.find_one({"leadId": lead_id}) or {}
    if not str(lead_row.get("leadId") or "").strip():
        raise ValueError("Pick an existing lead.")
    if _lead_blocks_claim_relink(lead_row):
        raise ValueError("This booking is cancelled. The claim cannot be relinked.")
    rec = await find_register_row(
        db, lead_id=lead_id, component_key=component_key, unit_sno=unit_sno)
    if not rec:
        rec = await adopt_or_ensure_register_row(
            db, lead_id=lead_id, lead=lead_row, component_key=component_key,
            unit_sno=unit_sno, claim_number=str(oem.get("claimNumber") or ""),
            line_id=want_line)
    if not rec:
        raise ValueError("Scheme Claim Register has no row for that lead and component.")
    number = str(oem.get("claimNumber") or "").strip()
    prev_number = str(rec.get("manualOemClaimNumber") or "").strip()
    prev_line = str(rec.get("manualOemLineId") or "").strip()
    if prev_number and prev_number.upper() != number.upper():
        await _detach_lead_from_oem_claim(
            db, number=prev_number, lead_id=lead_id, line_id=prev_line)
    lines = coerce_line_items(oem)
    customer = lead_row.get("customerName") or ""

    def _line_key(li):
        return map_claim_type_to_component(li.get("claimType"), li.get("description"))

    if want_line:
        targets = [li for li in lines if str(li.get("lineId") or "") == want_line]
        if not targets:
            raise ValueError("That claim item is not on this OEM claim.")
    else:
        same = [li for li in lines if not component_key or _line_key(li) == component_key]
        pool = same or lines
        unmatched = [li for li in pool if not li.get("leadId")]
        if len(unmatched) == 1:
            targets = unmatched
        elif len(pool) == 1:
            targets = pool
        elif len(lines) == 1:
            targets = lines
        else:
            raise ValueError(
                f"This OEM claim has {len(pool) or len(lines)} items. "
                "Match each item separately.")

    target_ids = {str(li.get("lineId") or "") for li in targets}
    for li in lines:
        if str(li.get("lineId") or "") in target_ids:
            continue
        if lead_id not in line_lead_ids(li):
            continue
        if li.get("matchedBy") != "manual":
            continue
        if prev_line and str(li.get("lineId") or "") != prev_line:
            continue
        _drop_line_lead(li, lead_id)
    for li in targets:
        _add_line_lead(li, lead_id, customer)
        li["matchedBy"] = "manual"
    chosen_id = str(targets[0].get("lineId") or "")
    relinked = bool(prev_number) and prev_number.upper() != number.upper()
    patch = {
        "manualOemClaimNumber": number,
        "manualOemLineId": chosen_id,
        "manualOemMatchedAt": now_iso(),
        "claimReference": number,
    }
    if (str(rec.get("claimStatus") or "") == "Cancelled"
            and round2(rec.get("receivedAmount") or 0) <= 0):
        patch["claimStatus"] = "Pending"
        patch["submittedDate"] = ""
        patch["approvedDate"] = ""
        relinked = True
    await db.claims.update_one({"_id": rec["_id"]}, {"$set": patch})
    lead_ids = collect_claim_lead_ids(lines)
    oem_patch = {
        "lineItems": lines,
        "leadIds": lead_ids,
        "linkedLineCount": sum(1 for li in lines if line_lead_ids(li)),
        "unlinkedLineCount": sum(1 for li in lines if not line_lead_ids(li)),
    }
    await db[CLAIMS_COLLECTION].update_one(
        {"_id": oem["_id"]} if oem.get("_id") else {"claimNumber": number},
        {"$set": oem_patch})
    rec.update(patch)
    rec.pop("_id", None)
    oem.update(oem_patch)
    oem.pop("_id", None)
    return {
        "register": rec,
        "oemClaim": stamp_document_flag(oem),
        "relinked": relinked,
        "previousClaimNumber": prev_number if relinked else "",
    }


async def clear_register_oem_link(db, *, lead_id, component_key, unit_sno=None):
    rec = await find_register_row(
        db, lead_id=lead_id, component_key=component_key, unit_sno=unit_sno)
    if not rec:
        raise ValueError("Scheme Claim Register has no row for that lead and component.")
    number = str(rec.get("manualOemClaimNumber") or "").strip()
    line_id = str(rec.get("manualOemLineId") or "").strip()
    await db.claims.update_one(
        {"_id": rec["_id"]},
        {"$unset": {"manualOemClaimNumber": "", "manualOemLineId": "",
                    "manualOemMatchedAt": ""}})
    if number:
        await _detach_lead_from_oem_claim(
            db, number=number, lead_id=lead_id, line_id=line_id)
    rec.pop("manualOemClaimNumber", None)
    rec.pop("manualOemLineId", None)
    rec.pop("manualOemMatchedAt", None)
    rec.pop("_id", None)
    return rec


def _oem_amount_for_lead(oem, lead_id):
    lead_id = str(lead_id or "").strip()
    lines = coerce_line_items(oem or {})
    mine = [li for li in lines if lead_id in line_lead_ids(li)]
    if mine:
        return round2(sum(_num(li.get("totalAmount")) for li in mine))
    return round2((oem or {}).get("claimedAmount"))


async def rehome_pack_level_extra_support(db, lead_id, lead=None):
    """Move a leftover pack-total Extra Support row onto one unit, then drop it.

    Matching without a unit sno glued the first ₹4,000 OEM note onto the pack
    ₹8,000 row (Kapoor LD26000893). Unit 2 then could not take its own debit
    note, and the drawer listed ₹8,000 as filed twice.
    """
    import commercial as ce
    lead_id = str(lead_id or "").strip()
    if not lead_id:
        return 0
    lead = lead or await db.leads.find_one({"leadId": lead_id}) or {}
    unit_amts = extra_support_unit_amounts(lead)
    if len(unit_amts) < 2:
        return 0
    extra_key = ce.OEM_EXTRA_SUPPORT_KEY
    pack_rows = [c async for c in db.claims.find({
        "leadId": lead_id, "componentKey": extra_key, "manual": {"$ne": True},
        "$or": [{"unitSno": {"$in": [None, 0]}}, {"unitSno": {"$exists": False}}],
    })]
    if not pack_rows:
        return 0
    unit_rows = [c async for c in db.claims.find({
        "leadId": lead_id, "componentKey": extra_key, "manual": {"$ne": True},
        "unitSno": {"$gt": 0},
    })]
    moved = 0
    for pack in pack_rows:
        oem_no = str(pack.get("manualOemClaimNumber") or pack.get("claimReference") or "").strip()
        already = [u for u in unit_rows
                   if oem_no and str(u.get("manualOemClaimNumber") or "").strip().upper() == oem_no.upper()]
        unmatched = [u for u in unit_rows
                     if not str(u.get("manualOemClaimNumber") or "").strip()]
        target = already[0] if already else None
        if not target and oem_no:
            oem = await find_oem_claim(db, oem_no)
            oem_amt = _oem_amount_for_lead(oem, lead_id) if oem else 0
            by_amt = [u for u in unmatched
                      if oem_amt > 0 and abs(round2(u.get("claimAmount") or u.get("eligibleClaim")) - oem_amt) < 1]
            pack_ch = oem_sync._norm_chassis(pack.get("chassisNumber"))
            by_ch = [u for u in unmatched
                     if pack_ch and oem_sync._norm_chassis(u.get("chassisNumber")) == pack_ch]
            target = (by_ch[0] if by_ch else None) or (by_amt[0] if by_amt else None) or (
                unmatched[0] if unmatched else None)
        if target and oem_no and not already:
            patch = {
                "manualOemClaimNumber": pack.get("manualOemClaimNumber") or oem_no,
                "manualOemLineId": pack.get("manualOemLineId") or "",
                "claimReference": pack.get("claimReference") or oem_no,
                "oemMatchState": pack.get("oemMatchState") or "",
                "oemStatus": pack.get("oemStatus") or "",
                "oemStageLabel": pack.get("oemStageLabel") or "",
                "submittedDate": target.get("submittedDate") or pack.get("submittedDate") or "",
                "approvedDate": target.get("approvedDate") or pack.get("approvedDate") or "",
            }
            if ce.num(pack.get("receivedAmount")) > 0 and ce.num(target.get("receivedAmount")) <= 0:
                patch["receivedAmount"] = pack.get("receivedAmount")
                patch["claimStatus"] = pack.get("claimStatus") or target.get("claimStatus")
            elif pack.get("claimStatus") and str(target.get("claimStatus") or "") in ("", "Pending"):
                patch["claimStatus"] = pack.get("claimStatus")
            await db.claims.update_one({"_id": target["_id"]}, {"$set": patch})
            target.update(patch)
            moved += 1
        await db.claims.delete_one({"_id": pack["_id"]})
        moved += 1
    return moved


async def unlink_additional_discount_extra_support(db, lead_id=""):
    """Additional Discount is dealer-funded. Extra Support OEM notes must not sit on it."""
    filt = {"componentKey": "additionalDiscount", "manual": {"$ne": True}}
    if lead_id:
        filt["leadId"] = lead_id
    n = 0
    async for row in db.claims.find(filt):
        number = str(row.get("manualOemClaimNumber") or row.get("claimReference") or "").strip()
        if not number:
            continue
        oem = await find_oem_claim(db, number)
        if not oem:
            continue
        extra = any(
            map_claim_type_to_component(li.get("claimType"), li.get("description")) == "oemExtraSupport"
            for li in coerce_line_items(oem))
        if not extra:
            continue
        patch = {
            "claimReference": "",
            "oemMatchState": "not_filed",
            "oemStatus": "",
            "oemStageLabel": "",
        }
        unset = {"manualOemClaimNumber": "", "manualOemLineId": "", "manualOemMatchedAt": ""}
        if str(row.get("claimStatus") or "") == "Submitted" and round2(row.get("receivedAmount")) <= 0:
            patch["claimStatus"] = "Pending"
            patch["submittedDate"] = ""
        await db.claims.update_one({"_id": row["_id"]}, {"$set": patch, "$unset": unset})
        lid = str(row.get("leadId") or "").strip()
        keep = await db.claims.find_one({
            "leadId": lid, "componentKey": "oemExtraSupport", "manual": {"$ne": True},
            "manualOemClaimNumber": number,
        }) if lid else None
        if lid and not keep:
            await _detach_lead_from_oem_claim(
                db, number=number, lead_id=lid,
                line_id=str(row.get("manualOemLineId") or ""))
        n += 1
    return n


async def repair_pack_extra_support_leads(db, lead_id=""):
    """Heal every same-order pack that still carries a glued Extra Support total."""
    import commercial as ce
    filt = {"units.oemExtraSupportReceived": {"$gt": 0}}
    if lead_id:
        filt["leadId"] = lead_id
    n = 0
    async for lead in db.leads.find(filt, {"leadId": 1, "units": 1, "oemExtraSupportReceived": 1}):
        if len(ce.extra_support_unit_rows(lead)) < 2:
            continue
        n += await rehome_pack_level_extra_support(db, lead.get("leadId"), lead)
    n += await unlink_additional_discount_extra_support(db, lead_id)
    return n
