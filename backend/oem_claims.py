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
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


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


def normalise_line_item(item):
    """One claim line. Chassis and source invoice are the keys back to a lead.

    The per-line `documents[]` are customer photographs on an open S3 bucket. Only
    their count is kept: the CRM has no business re-hosting customer images, and the
    read-only OEM finance role must never be able to reach them.
    """
    if not isinstance(item, dict):
        return None
    return {
        "lineId": str(item.get("id") or ""),
        "claimType": str(item.get("claim_type") or "").strip(),
        "description": str(item.get("description") or "").strip(),
        "chassis": oem_sync._norm_chassis(item.get("chassis")),
        "sourceInvoiceNumber": str(item.get("source_invoice_number") or "").strip(),
        "model": str(item.get("model") or "").strip(),
        "variant": str(item.get("variant") or "").strip(),
        "status": str(item.get("status") or "").strip(),
        "baseAmount": round2(item.get("base_amount")),
        "totalAmount": round2(item.get("total_amount")),
        "rejectedBy": str(item.get("rejected_by") or "") or "",
        "remarks": str(item.get("remarks") or "") or "",
        "documentCount": len(item.get("documents") or []),
        "sourceInvoiceUrl": str(item.get("source_invoice_s3_link") or ""),
        "leadId": "", "leadCustomer": "", "matchedBy": "",
    }


def claim_doc_from_row(row):
    """The list row — everything except chassis, which only the journey call has."""
    created = parse_list_datetime(row.get("_created_at"))
    status = str(row.get("status") or "").strip()
    return {
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


def merge_detail(doc, detail):
    """Fold a journey response into a claim doc: line items and ladder position."""
    doc = dict(doc)
    if not isinstance(detail, dict):
        return doc
    header = detail.get("header") if isinstance(detail.get("header"), dict) else {}
    lines = [normalise_line_item(li) for li in (detail.get("line_items") or [])]
    doc["lineItems"] = [li for li in lines if li]
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
    doc["detailFetchedAt"] = now_iso()
    doc["detailStatusAtFetch"] = doc.get("status") or ""
    doc["detailAmountAtFetch"] = doc.get("approvedAmount") or 0.0
    return doc


def needs_detail(existing, row_doc):
    """Fetch the journey only when it can have changed. Chassis never moves.

    First sight always. After that, only when Euler advanced the status or approved a
    different amount — which keeps the steady state at a couple of calls per sync
    instead of one per claim.
    """
    if not existing or not existing.get("detailFetchedAt"):
        return True
    if not (existing.get("lineItems") or []):
        return True
    if str(existing.get("detailStatusAtFetch") or "") != str(row_doc.get("status") or ""):
        return True
    if abs(_num(existing.get("detailAmountAtFetch")) - _num(row_doc.get("approvedAmount"))) > 0.005:
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
                {"invoiceNumber": {"$nin": ["", None]}}],
    }):
        ch = oem_sync._norm_chassis(lead.get("chassisNumber"))
        if ch:
            by_chassis.setdefault(ch, lead)
        inv = str(lead.get("invoiceNumber") or "").strip().lower()
        if inv:
            by_invoice.setdefault(inv, lead)
    return {"chassis": by_chassis, "invoice": by_invoice}


async def _lead_for_chassis(db, chassis, index=None):
    ch = oem_sync._norm_chassis(chassis)
    if not ch:
        return None
    if index is not None:
        return index["chassis"].get(ch)
    async for lead in db.leads.find({"chassisNumber": {"$nin": ["", None]}}):
        if oem_sync._norm_chassis(lead.get("chassisNumber")) == ch:
            return lead
    return None


async def _lead_for_invoice(db, invoice, index=None):
    inv = str(invoice or "").strip()
    if not inv:
        return None
    if index is not None:
        return index["invoice"].get(inv.lower())
    return await db.leads.find_one({
        "invoiceNumber": {"$regex": f"^{re.escape(inv)}$", "$options": "i"},
    })


async def link_claim_lines(db, doc, index=None):
    """Tie each line to a lead: chassis first, source invoice as the fallback.

    Chassis is the stronger key — it is one-to-one with the physical vehicle, is
    already unique across live leads, and cannot be shared the way a fleet buyer's
    mobile can. A line that matches on chassis but disagrees on invoice is linked and
    FLAGGED rather than silently accepted: that disagreement is real information.
    """
    lines = doc.get("lineItems") or []
    lead_ids, conflicts = [], []
    for line in lines:
        lead = await _lead_for_chassis(db, line.get("chassis"), index)
        matched_by = "chassis" if lead else ""
        if not lead:
            lead = await _lead_for_invoice(db, line.get("sourceInvoiceNumber"), index)
            matched_by = "invoice" if lead else ""
        if not lead:
            line["leadId"] = line["leadCustomer"] = line["matchedBy"] = ""
            continue
        line["leadId"] = lead.get("leadId") or ""
        line["leadCustomer"] = lead.get("customerName") or ""
        line["matchedBy"] = matched_by
        want_inv = str(line.get("sourceInvoiceNumber") or "").strip().lower()
        got_inv = str(lead.get("invoiceNumber") or "").strip().lower()
        if matched_by == "chassis" and want_inv and got_inv and want_inv != got_inv:
            line["invoiceMismatch"] = True
            conflicts.append(
                f"{line.get('chassis')}: claim says invoice {line.get('sourceInvoiceNumber')}, "
                f"lead {line['leadId']} says {lead.get('invoiceNumber')}")
        else:
            line["invoiceMismatch"] = False
        if line["leadId"] not in lead_ids:
            lead_ids.append(line["leadId"])
    doc["lineItems"] = lines
    doc["leadIds"] = lead_ids
    doc["linkedLineCount"] = sum(1 for li in lines if li.get("leadId"))
    doc["unlinkedLineCount"] = sum(1 for li in lines if not li.get("leadId"))
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
    coll = db[CLAIMS_COLLECTION]
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
        merged = await link_claim_lines(db, merged, lead_index)
        merged["missingFromOem"] = False
        if merged.get("linkedLineCount"):
            linked += 1
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

    mirrored = await coll.count_documents({"missingFromOem": {"$ne": True}})
    incomplete = bool(expected is not None and mirrored < expected)
    stats = {
        "claimsMirrored": mirrored,
        "claimsExpected": expected,
        "claimsFetchMode": mode,
        "claimsIncomplete": incomplete,
        "claimsLinked": linked,
        "claimDetailCalls": detail_calls,
        "claimDetailFailures": detail_failures,
        "claimsMissingFromOem": stale,
        "claimsNeedsResubmission": needs_resubmission,
        "claimsSyncedAt": now_iso(),
        "claimsSyncOk": True,
    }
    await db["system"].update_one({"_id": "coulson"}, {"$set": stats}, upsert=True)
    return {"ok": True, "credentialSource": src, **stats}


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
    ("insuranceBenefit", ("insurance benefit", "free insurance", "insurance")),
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


def map_claim_type_to_component(claim_type, description=""):
    """Best-effort componentKey for a Coulson line. Empty when nothing matches."""
    hay = f"{description or ''} {claim_type or ''}".lower()
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
        for line in row.get("lineItems") or []:
            ch = oem_sync._norm_chassis(line.get("chassis"))
            if ch:
                by_chassis.setdefault(ch, []).append(row)
    for ch, rows in by_chassis.items():
        rows.sort(key=lambda r: str(r.get("createdAt") or ""))
    flagged = 0
    async for row in db[CLAIMS_COLLECTION].find({"status": "Rejected"}):
        created = str(row.get("createdAt") or "")
        successor = ""
        for line in row.get("lineItems") or []:
            ch = oem_sync._norm_chassis(line.get("chassis"))
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
        patch = {"resubmittedBy": successor, "needsResubmission": not successor}
        if not successor:
            flagged += 1
        await db[CLAIMS_COLLECTION].update_one({"_id": row["_id"]}, {"$set": patch})
    return flagged


async def register_match_index(db):
    """Per lead, what Euler actually holds — indexed the way the register asks for it."""
    index = {}
    async for row in db[CLAIMS_COLLECTION].find({}):
        status = str(row.get("status") or "")
        for line in row.get("lineItems") or []:
            lead_id = line.get("leadId")
            if not lead_id:
                continue
            entry = index.setdefault(lead_id, {
                "byComponent": {}, "unmapped": [], "claimNumbers": [],
                "filedTotal": 0.0, "acceptedTotal": 0.0,
                "rejectedOpen": [], "hasAnyClaim": False,
            })
            entry["hasAnyClaim"] = True
            amount = round2(line.get("totalAmount"))
            if str(row.get("status")) != "Cancelled":
                entry["filedTotal"] = round2(entry["filedTotal"] + amount)
            if status in ACCEPTED_STATUSES:
                entry["acceptedTotal"] = round2(entry["acceptedTotal"] + amount)
            if row.get("claimNumber") and row["claimNumber"] not in entry["claimNumbers"]:
                entry["claimNumbers"].append(row["claimNumber"])
            hit = {
                "claimNumber": row.get("claimNumber") or "",
                "oemStatus": status,
                "amount": amount,
                "stageLabel": row.get("stageLabel") or "",
                "stageDays": int(row.get("stageDays") or 0),
                "createdAt": row.get("createdAt") or "",
                "needsResubmission": bool(row.get("needsResubmission")),
                "resubmittedBy": row.get("resubmittedBy") or "",
                "description": line.get("description") or "",
            }
            if status == "Rejected" and row.get("needsResubmission"):
                entry["rejectedOpen"].append(hit)
            key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
            if key:
                entry["byComponent"].setdefault(key, []).append(hit)
            else:
                entry["unmapped"].append(hit)
    return index


def match_state(index, lead_id, component_key):
    """How this register row stands against Euler. Never guesses "unclaimed".

    filed / accepted  — Euler has it, and has agreed it where `accepted`
    rejected          — refused and nobody filed it again: act
    resubmitted       — refused, but a newer claim exists: informational
    unmapped          — the lead has claims, none of them reads as this component:
                        needs a human, NOT a gap
    not_filed         — nothing at all was filed for this lead: a genuine gap
    """
    entry = (index or {}).get(lead_id)
    if not entry:
        return {"state": "not_filed", "claimNumbers": [], "oemStatus": "",
                "filedAmount": 0.0, "detail": "No claim filed with Euler for this lead."}
    hits = entry["byComponent"].get(component_key) or []
    if not hits:
        if entry["unmapped"]:
            return {
                "state": "unmapped",
                "claimNumbers": [h["claimNumber"] for h in entry["unmapped"]],
                "oemStatus": "", "filedAmount": round2(entry["filedTotal"]),
                "detail": "This lead has claims in Euler, but none of them names this "
                          "component. Check before treating it as unclaimed.",
            }
        return {"state": "not_filed", "claimNumbers": entry["claimNumbers"], "oemStatus": "",
                "filedAmount": round2(entry["filedTotal"]),
                "detail": "Euler holds claims for this lead, but not this component."}
    live = [h for h in hits if h["oemStatus"] not in ("Rejected", "Cancelled")]
    rejected = [h for h in hits if h["oemStatus"] == "Rejected"]
    pick = live[0] if live else (rejected[0] if rejected else hits[0])
    if live:
        state = "accepted" if pick["oemStatus"] in ACCEPTED_STATUSES else "filed"
    elif rejected:
        state = "resubmitted" if rejected[0]["resubmittedBy"] else "rejected"
    else:
        state = "not_filed"
    detail = ""
    if state == "rejected":
        detail = "Euler rejected this and no replacement claim has been filed."
    elif state == "resubmitted":
        detail = f"Rejected, refiled as {rejected[0]['resubmittedBy']}."
    elif state == "filed" and pick["stageLabel"]:
        detail = f"{pick['stageDays']}d at {pick['stageLabel']}."
    return {
        "state": state,
        "claimNumbers": [h["claimNumber"] for h in hits if h["claimNumber"]],
        "oemStatus": pick["oemStatus"],
        "filedAmount": round2(sum(h["amount"] for h in hits)),
        "stageLabel": pick["stageLabel"], "stageDays": pick["stageDays"],
        "detail": detail,
    }


async def oem_only_lines(db, register_pairs):
    """Euler's side of the cross-check: claim lines the register has no row for.

    `register_pairs` is the set of (leadId, componentKey) the register actually renders.
    A line whose lead is unknown, or whose component the register never raised, is money
    Euler is processing that this app does not know it is owed.
    """
    out = []
    async for row in db[CLAIMS_COLLECTION].find({}):
        if str(row.get("status") or "") == "Cancelled":
            continue
        for line in row.get("lineItems") or []:
            lead_id = line.get("leadId") or ""
            key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
            if lead_id and key and (lead_id, key) in register_pairs:
                continue
            if lead_id and not key and any(p[0] == lead_id for p in register_pairs):
                # The lead is in the register; the phrase just did not map. That is the
                # `unmapped` amber on the register side, not a missing row here.
                continue
            out.append({
                "claimNumber": row.get("claimNumber") or "",
                "oemStatus": row.get("status") or "",
                "stageLabel": row.get("stageLabel") or "",
                "stageDays": int(row.get("stageDays") or 0),
                "createdDate": row.get("createdDate") or "",
                "leadId": lead_id,
                "customer": line.get("leadCustomer") or "",
                "chassis": line.get("chassis") or "",
                "sourceInvoiceNumber": line.get("sourceInvoiceNumber") or "",
                "description": line.get("description") or "",
                "claimType": line.get("claimType") or "",
                "mappedComponent": key,
                "amount": round2(line.get("totalAmount")),
                "reason": "unknown_lead" if not lead_id else (
                    "unmapped_component" if not key else "missing_register_row"),
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
    async for c in db.claims.find({"manual": {"$ne": True}},
                                  {"leadId": 1, "componentKey": 1, "_id": 0}):
        lid, key = c.get("leadId") or "", c.get("componentKey") or ""
        if lid and key:
            pairs.add((lid, key))
    return pairs


def claim_register_match(row, pairs):
    """How this Euler debit note stands against the Scheme Claim Register.

    The reverse of `match_state`: that function colours a register row by whether
    Euler filed it; this colours an Euler claim by whether the register raised it.
    A miss here is money Euler is processing that the books do not know they are owed.
    """
    lines = row.get("lineItems") or []
    if not lines:
        return {"state": "unknown_lead", "detail": "No line items on this claim.",
                "mappedComponents": []}
    states, keys = [], []
    for line in lines:
        lead_id = line.get("leadId") or ""
        key = map_claim_type_to_component(line.get("claimType"), line.get("description"))
        if key:
            keys.append(key)
        if not lead_id:
            states.append("unknown_lead")
        elif not key:
            states.append("unmapped")
        elif (lead_id, key) in pairs:
            states.append("in_register")
        else:
            states.append("missing_register")
    order = ("unknown_lead", "missing_register", "unmapped", "in_register")
    pick = min(states, key=lambda s: order.index(s) if s in order else 99)
    detail = {
        "unknown_lead": "No chassis or invoice on this claim matched a lead.",
        "missing_register": "Euler filed this, but the Scheme Claim Register has no row.",
        "unmapped": "This lead is in the register, but the claim wording did not map to a component.",
        "in_register": "Connected to the Scheme Claim Register by chassis / invoice.",
    }.get(pick, "")
    if row.get("status") == "Rejected" and row.get("needsResubmission"):
        detail = (detail + " " if detail else "") + "Rejected — nothing refiled on this chassis."
    elif row.get("resubmittedBy"):
        detail = (detail + " " if detail else "") + f"Rejected, refiled as {row['resubmittedBy']}."
    return {"state": pick, "detail": detail.strip(),
            "mappedComponents": keys,
            "needsResubmission": bool(row.get("needsResubmission")),
            "resubmittedBy": row.get("resubmittedBy") or ""}


async def attach_register_match(db, rows):
    pairs = await register_pairs(db)
    for row in rows:
        row["registerMatch"] = claim_register_match(row, pairs)
    return rows


def _claim_matches_query(row, *, q="", chassis="", invoice=""):
    if chassis:
        ch = oem_sync._norm_chassis(chassis)
        if not any(oem_sync._norm_chassis(li.get("chassis")) == ch
                   for li in (row.get("lineItems") or [])):
            return False
    if invoice:
        inv = str(invoice or "").strip().lower()
        if not any(str(li.get("sourceInvoiceNumber") or "").strip().lower() == inv
                   for li in (row.get("lineItems") or [])):
            return False
    if q:
        needle = str(q).strip().lower()
        blob = " ".join([
            str(row.get("claimNumber") or ""),
            str(row.get("status") or ""),
            " ".join(str(x) for x in (row.get("leadIds") or [])),
            " ".join(str(li.get("chassis") or "") for li in (row.get("lineItems") or [])),
            " ".join(str(li.get("sourceInvoiceNumber") or "") for li in (row.get("lineItems") or [])),
            " ".join(str(li.get("leadCustomer") or "") for li in (row.get("lineItems") or [])),
            " ".join(str(li.get("description") or "") for li in (row.get("lineItems") or [])),
        ]).lower()
        if needle not in blob:
            return False
    return True


async def list_claims(db, *, status="", lead_id="", unlinked=False,
                      q="", chassis="", invoice=""):
    filt = {}
    if status:
        filt["status"] = status
    if lead_id:
        filt["leadIds"] = lead_id
    rows = [r async for r in db[CLAIMS_COLLECTION].find(filt)]
    if unlinked:
        rows = [r for r in rows if not (r.get("linkedLineCount") or 0)]
    if q or chassis or invoice:
        rows = [r for r in rows if _claim_matches_query(
            r, q=q, chassis=chassis, invoice=invoice)]
    rows.sort(key=lambda r: (r.get("terminal") and 1 or 0, -int(r.get("stageDays") or 0),
                             str(r.get("createdAt") or "")))
    for r in rows:
        r.pop("_id", None)
    await attach_register_match(db, rows)
    return rows


async def claims_for_lead(db, lead_id):
    """Every claim carrying a line for this lead, with that lead's lines only."""
    out = []
    async for row in db[CLAIMS_COLLECTION].find({"leadIds": lead_id}):
        row.pop("_id", None)
        mine = [li for li in (row.get("lineItems") or []) if li.get("leadId") == lead_id]
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
    oem = await claims_for_lead(db, lead_id)
    await attach_register_match(db, oem)
    index = await register_match_index(db)
    register = []
    async for c in db.claims.find({"leadId": lead_id, "manual": {"$ne": True}}):
        key = c.get("componentKey") or ""
        if not key:
            continue
        register.append({
            "claimId": c.get("claimId") or f"CLM-{lead_id}-{key}",
            "componentKey": key,
            "component": c.get("component") or key,
            "eligibleClaim": round2(c.get("eligibleClaim") if c.get("eligibleClaim") is not None
                                    else c.get("claimAmount")),
            "claimStatus": c.get("claimStatus") or "",
            "oemMatch": match_state(index, lead_id, key),
        })
    lead = lead or {}
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
    async for row in db[CLAIMS_COLLECTION].find({}):
        row.pop("_id", None)
        total += 1
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
                "stageDays": int(row.get("stageDays") or 0),
                "claimAgeingDays": int(row.get("claimAgeingDays") or 0),
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
                              for li in (row.get("lineItems") or [])],
            })
        for msg in row.get("invoiceConflicts") or []:
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
        },
    }
