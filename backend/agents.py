"""Confirm-only AI desk for Euler CRM.

Seven scanners. They upsert open suggestions. They never write Scheme, Ex-Showroom,
OEM Extra, or Tally. Confirm is a separate call with a role gate per agent.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone

import commercial as ce
import lead_docs
import oem_claims
import oem_sync
import pdf_extract

log = logging.getLogger("euler.agents")

COLLECTION = "agent_suggestions"
SCAN_META = "agent_scan"

AGENT_DOCUMENT = "document"
AGENT_PDF = "pdf_rto_insurance"
AGENT_PDF_CHASSIS = "pdf_chassis"
AGENT_OEM_MATCH = "oem_match"
AGENT_OEM_SETTLEMENT = "oem_settlement"
AGENT_COULSON = "coulson_watch"
AGENT_FOLLOWUP = "followup"
AGENT_TALLY = "tally_prep"

AGENTS = (
    AGENT_DOCUMENT, AGENT_PDF, AGENT_PDF_CHASSIS, AGENT_OEM_MATCH,
    AGENT_OEM_SETTLEMENT, AGENT_COULSON, AGENT_FOLLOWUP, AGENT_TALLY,
)

AGENT_LABELS = {
    AGENT_DOCUMENT: "Document",
    AGENT_PDF: "Insurance / RTO PDF",
    AGENT_PDF_CHASSIS: "PDF chassis",
    AGENT_OEM_MATCH: "OEM match",
    AGENT_OEM_SETTLEMENT: "OEM settlement",
    AGENT_COULSON: "Coulson session",
    AGENT_FOLLOWUP: "Follow-up",
    AGENT_TALLY: "Tally-prep",
}

# Owner / GM / Showroom Admin / team TL / Accounts — not executives, not OEM finance.
AGENT_DESK_ROLES = ("owner", "sales_gm", "tl", "team_lead", "accounts")
# Price Structure is already saved → only owner or Showroom Admin may rewrite RTO/Ins.
PDF_CONFIRM_ROLES = ("owner", "tl")
FOLLOWUP_CONFIRM_ROLES = ("owner", "sales_gm", "tl", "team_lead")
OEM_MATCH_CONFIRM_ROLES = ("owner", "sales_gm", "tl", "team_lead")

OPEN_FOLLOWUP_STATUSES = {
    "new", "contacted", "follow-up", "followup", "hot", "in progress", "inprogress",
}
DEAD_STATUSES = {
    "lost", "cancelled", "close won", "closed",
}
BOOKED_STATUSES = {"booked", "finance process", "finance"}

DELIVERY_DOC_KINDS = ("delivery_insurance", "delivery_rto")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def today():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def tomorrow():
    return (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")


def _role(user) -> str:
    return str((user or {}).get("role") or "").strip().lower()


def can_view_desk(user) -> bool:
    return _role(user) in AGENT_DESK_ROLES


def fingerprint(agent: str, subject: str, key: str = "") -> str:
    raw = f"{agent}|{subject}|{key}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:24]


def _public(row) -> dict:
    if not row:
        return {}
    out = dict(row)
    out.pop("_id", None)
    return out


def can_confirm(user, suggestion) -> bool:
    """Role gate. Confirm still cannot rewrite Scheme."""
    if not suggestion or suggestion.get("status") != "open":
        return False
    role = _role(user)
    if role not in AGENT_DESK_ROLES:
        return False
    agent = suggestion.get("agent")
    payload = suggestion.get("payload") or {}
    if agent == AGENT_PDF:
        return role in PDF_CONFIRM_ROLES and bool(payload.get("field") in ("rto", "insuranceAmount"))
    if agent == AGENT_OEM_MATCH:
        return role in OEM_MATCH_CONFIRM_ROLES and bool(payload.get("proposedLeadId")) and bool(payload.get("chassis"))
    if agent == AGENT_COULSON:
        return role == "owner" and payload.get("action") in ("renew_sync", "sync")
    if agent == AGENT_FOLLOWUP:
        return role in FOLLOWUP_CONFIRM_ROLES
    if agent in (AGENT_DOCUMENT, AGENT_OEM_SETTLEMENT, AGENT_TALLY, AGENT_PDF_CHASSIS):
        return True
    return False


def confirm_kind(suggestion) -> str:
    """What Confirm actually does — shown on the desk so staff are not surprised."""
    agent = (suggestion or {}).get("agent")
    payload = (suggestion or {}).get("payload") or {}
    if agent == AGENT_PDF:
        return "write_price_structure"
    if agent == AGENT_OEM_MATCH and payload.get("proposedLeadId"):
        return "connect_oem_sold"
    if agent == AGENT_COULSON:
        return "coulson_sync"
    if agent == AGENT_FOLLOWUP:
        return "schedule_followup"
    return "acknowledge"


async def list_suggestions(db, *, status="open", agent=""):
    q = {}
    if status and status != "all":
        q["status"] = status
    if agent and agent in AGENTS:
        q["agent"] = agent
    rows = [r async for r in db[COLLECTION].find(q).sort("createdAt", -1)]
    return [_public(r) for r in rows]


async def get_suggestion(db, suggestion_id: str):
    row = await db[COLLECTION].find_one({"suggestionId": suggestion_id})
    return _public(row) if row else None


async def _upsert(db, row: dict):
    fp = row["fingerprint"]
    existing = await db[COLLECTION].find_one({"fingerprint": fp, "status": "open"})
    now = now_iso()
    if existing:
        patch = {
            "title": row.get("title"),
            "detail": row.get("detail"),
            "payload": row.get("payload") or {},
            "leadId": row.get("leadId") or "",
            "severity": row.get("severity") or "Medium",
            "href": row.get("href") or "",
            "updatedAt": now,
        }
        await db[COLLECTION].update_one({"suggestionId": existing["suggestionId"]}, {"$set": patch})
        return existing["suggestionId"], "updated"
    recent = await db[COLLECTION].find_one(
        {"fingerprint": fp, "status": {"$in": ["dismissed", "confirmed"]}},
        sort=[("resolvedAt", -1)],
    )
    if recent:
        resolved = str(recent.get("resolvedAt") or "")
        if resolved[:10] >= (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%d"):
            if (recent.get("payload") or {}) == (row.get("payload") or {}):
                return recent.get("suggestionId") or "", "skipped"
    sid = f"AG{hashlib.sha1((fp + now).encode()).hexdigest()[:10].upper()}"
    doc = {
        "suggestionId": sid,
        "agent": row["agent"],
        "fingerprint": fp,
        "status": "open",
        "title": row.get("title") or "",
        "detail": row.get("detail") or "",
        "payload": row.get("payload") or {},
        "leadId": row.get("leadId") or "",
        "severity": row.get("severity") or "Medium",
        "href": row.get("href") or "",
        "createdAt": now,
        "updatedAt": now,
        "resolvedAt": "",
        "resolvedBy": "",
        "result": {},
    }
    await db[COLLECTION].insert_one(doc)
    return sid, "created"


async def _close_stale(db, keep_fps, complete_agents):
    """Drop open cards only for agents that scanned their full population this run."""
    if not complete_agents:
        return 0
    open_rows = [r async for r in db[COLLECTION].find({"status": "open"})]
    closed = 0
    now = now_iso()
    for row in open_rows:
        if row.get("agent") not in complete_agents:
            continue
        if row.get("fingerprint") in keep_fps:
            continue
        await db[COLLECTION].update_one(
            {"suggestionId": row["suggestionId"]},
            {"$set": {
                "status": "resolved",
                "resolvedAt": now,
                "updatedAt": now,
                "result": {"reason": "no_longer_true"},
            }},
        )
        closed += 1
    return closed


def _dead_lead(lead) -> bool:
    acct = str((lead or {}).get("accountStatus") or "Active").strip().lower()
    if acct in ("cancelled", "inactive", "archived"):
        return True
    if (lead or {}).get("dealCancelled"):
        return True
    st = str((lead or {}).get("currentStatus") or "").strip().lower()
    return st in DEAD_STATUSES or st == "lost"


def _is_delivered(lead) -> bool:
    return (
        str((lead or {}).get("deliveryStatus") or "").lower() == "delivered"
        or str((lead or {}).get("currentStatus") or "").lower() == "delivered"
    )


def _is_booked(lead) -> bool:
    st = str((lead or {}).get("currentStatus") or "").lower()
    return st in BOOKED_STATUSES or "book" in st or bool((lead or {}).get("bookingDate"))


# --- scanners -----------------------------------------------------------------


_DOC_META = {"leadId": 1, "kind": 1, "_id": 0}
_LIVE_LEAD_PROJ = {
    "leadId": 1, "customerName": 1, "customerType": 1, "gstin": 1,
    "currentStatus": 1, "accountStatus": 1, "dealCancelled": 1,
    "deliveryStatus": 1, "bookingDate": 1, "bookingAmount": 1,
    "oemExtraSupportReceived": 1, "executive": 1, "interestedModel": 1,
    "nextFollowupDate": 1, "nextFollowup": 1, "_id": 0,
}
_DOC_KINDS_SCAN = (
    *lead_docs.KYC_INDIVIDUAL, *lead_docs.KYC_B2B, lead_docs.EXTRA_SUPPORT_KIND,
    *DELIVERY_DOC_KINDS,
)
PDF_SCAN_CAP = 40


async def scan_documents(db) -> list:
    """One leads pass + one docs pass. Never N queries per lead (that 25s-timeouted)."""
    live = []
    async for lead in db.leads.find({}, _LIVE_LEAD_PROJ):
        if _dead_lead(lead) or _is_delivered(lead):
            continue
        if lead.get("leadId"):
            live.append(lead)
    if not live:
        return [], True
    ids = [l["leadId"] for l in live]
    have = {}
    async for d in db[lead_docs.COLLECTION].find(
            {"leadId": {"$in": ids}, "kind": {"$in": list(_DOC_KINDS_SCAN)}}, _DOC_META):
        have.setdefault(d.get("leadId"), set()).add(d.get("kind"))
    out = []
    for lead in live:
        lid = lead["leadId"]
        kinds_have = have.get(lid) or set()
        missing = [
            k for k in lead_docs.required_kyc_kinds(lead.get("customerType") or "Individual")
            if k not in kinds_have]
        if (lead_docs.normalize_customer_type(lead.get("customerType")) == "B2B"
                and not str(lead.get("gstin") or "").strip()
                and "kyc_gst" not in kinds_have
                and "gstin" not in missing):
            missing.append("gstin")
        if lead_docs.extra_support_required(lead.get("oemExtraSupportReceived")):
            if lead_docs.EXTRA_SUPPORT_KIND not in kinds_have:
                missing.append(lead_docs.EXTRA_SUPPORT_KIND)
        if missing:
            labels = lead_docs.missing_doc_labels(missing)
            out.append({
                "agent": AGENT_DOCUMENT,
                "fingerprint": fingerprint(AGENT_DOCUMENT, lid, "kyc"),
                "leadId": lid,
                "severity": "High",
                "href": "/leads",
                "title": f"{lid} missing {labels}",
                "detail": f"{lead.get('customerName') or ''} · attach before Book / Deliver",
                "payload": {"kinds": missing, "stage": "kyc"},
            })
        if _is_booked(lead):
            need = [k for k in DELIVERY_DOC_KINDS if k not in kinds_have]
            if need:
                labels = lead_docs.missing_doc_labels(need)
                out.append({
                    "agent": AGENT_DOCUMENT,
                    "fingerprint": fingerprint(AGENT_DOCUMENT, lid, "delivery"),
                    "leadId": lid,
                    "severity": "Medium",
                    "href": "/deliveries",
                    "title": f"{lid} missing {labels}",
                    "detail": f"{lead.get('customerName') or ''} · booked, papers not on file",
                    "payload": {"kinds": need, "stage": "delivery"},
                })
    return out, True


def _doc_bytes(doc) -> bytes:
    raw = (doc or {}).get("data") or b""
    try:
        return bytes(raw)
    except Exception:
        return b""


async def scan_pdf_rto_insurance(db) -> tuple:
    """Compare insurance / RTO PDF amounts to Price Structure. Never Scheme.

    Metadata first (no binaries). Fetch at most PDF_SCAN_CAP files, one at a time.
    """
    out = []
    metas = [d async for d in db[lead_docs.COLLECTION].find(
        {"kind": {"$in": list(DELIVERY_DOC_KINDS)}},
        {"data": 0},
    ).sort("uploadedAt", -1)]
    complete = len(metas) <= PDF_SCAN_CAP
    metas = metas[:PDF_SCAN_CAP]
    by_lead = {}
    for d in metas:
        lid = d.get("leadId") or ""
        if lid:
            by_lead.setdefault(lid, []).append(d)
    if not by_lead:
        return out, True
    leads = {
        l["leadId"]: l
        async for l in db.leads.find({"leadId": {"$in": list(by_lead)}})
        if l.get("leadId")
    }
    for lid, files in by_lead.items():
        lead = leads.get(lid) or {}
        if _dead_lead(lead):
            continue
        current_rto = ce._rto_amount(lead)
        current_ins = ce._insurance_premium_amount(lead)
        lead_ch = oem_sync._norm_chassis(lead.get("chassisNumber"))
        scheme_ins = ce.round2(ce.num(lead.get("insuranceBenefit")))
        scheme_rto = ce.round2(ce.num(lead.get("rtoBenefit") or lead.get("rtoInsuranceBenefit")))
        for meta in files:
            kind = meta.get("kind")
            ctype = str(meta.get("contentType") or "")
            if ctype.startswith("image/"):
                text = ""
            else:
                full = await db[lead_docs.COLLECTION].find_one(
                    {"documentId": meta.get("documentId")},
                    {"data": 1, "contentType": 1, "kind": 1})
                text = pdf_extract.pdf_text(_doc_bytes(full), ctype)
            if len((text or "").strip()) < 8:
                out.append({
                    "agent": AGENT_PDF,
                    "fingerprint": fingerprint(AGENT_PDF, lid, f"{kind}-unreadable"),
                    "leadId": lid,
                    "severity": "Info",
                    "href": "/leads",
                    "title": f"{lid} {lead_docs.KINDS.get(kind, {}).get('label') or kind} could not be read",
                    "detail": "Scanned image or empty PDF — type RTO / Insurance from the paper. Scheme is not changed.",
                    "payload": {"field": "", "unreadable": True, "kind": kind},
                })
                continue
            if kind == "delivery_insurance":
                parsed = pdf_extract.extract_insurance(text)
                prem = parsed.get("premium") or 0
                if prem and pdf_extract.amounts_differ(prem, current_ins):
                    out.append({
                        "agent": AGENT_PDF,
                        "fingerprint": fingerprint(AGENT_PDF, lid, "insuranceAmount"),
                        "leadId": lid,
                        "severity": "High",
                        "href": "/leads",
                        "title": f"{lid} insurance PDF ₹{prem:.0f} vs Price Structure ₹{current_ins:.0f}",
                        "detail": (
                            f"Confirm writes Price Structure insuranceAmount only. "
                            f"Scheme insuranceBenefit (₹{scheme_ins:.0f}) is not touched."
                        ),
                        "payload": {
                            "field": "insuranceAmount",
                            "fromAmount": current_ins,
                            "toAmount": prem,
                            "policyNumber": parsed.get("policyNumber") or "",
                            "kind": kind,
                        },
                    })
                ch = oem_sync._norm_chassis(parsed.get("chassis"))
                if ch and lead_ch and ch != lead_ch:
                    out.append({
                        "agent": AGENT_PDF_CHASSIS,
                        "fingerprint": fingerprint(AGENT_PDF_CHASSIS, lid, ch),
                        "leadId": lid,
                        "severity": "High",
                        "href": "/leads",
                        "title": f"{lid} insurance PDF chassis {ch} ≠ {lead_ch}",
                        "detail": "Do not stamp the wrong unit. Open the lead and match by eye.",
                        "payload": {"pdfChassis": ch, "leadChassis": lead_ch, "kind": kind},
                    })
            elif kind == "delivery_rto":
                parsed = pdf_extract.extract_rto(text)
                fee = parsed.get("rto") or 0
                if fee and pdf_extract.amounts_differ(fee, current_rto):
                    out.append({
                        "agent": AGENT_PDF,
                        "fingerprint": fingerprint(AGENT_PDF, lid, "rto"),
                        "leadId": lid,
                        "severity": "High",
                        "href": "/leads",
                        "title": f"{lid} RTO PDF ₹{fee:.0f} vs Price Structure ₹{current_rto:.0f}",
                        "detail": (
                            f"Confirm writes Price Structure rto only. "
                            f"Scheme rtoBenefit (₹{scheme_rto:.0f}) is not touched."
                        ),
                        "payload": {
                            "field": "rto",
                            "fromAmount": current_rto,
                            "toAmount": fee,
                            "registrationNumber": parsed.get("registrationNumber") or "",
                            "kind": kind,
                        },
                    })
                ch = oem_sync._norm_chassis(parsed.get("chassis"))
                if ch and lead_ch and ch != lead_ch:
                    out.append({
                        "agent": AGENT_PDF_CHASSIS,
                        "fingerprint": fingerprint(AGENT_PDF_CHASSIS, lid, ch),
                        "leadId": lid,
                        "severity": "High",
                        "href": "/leads",
                        "title": f"{lid} RTO PDF chassis {ch} ≠ {lead_ch}",
                        "detail": "Do not stamp the wrong unit. Open the lead and match by eye.",
                        "payload": {"pdfChassis": ch, "leadChassis": lead_ch, "kind": kind},
                    })
    return out, complete


async def scan_oem_match(db) -> tuple:
    sold = [r async for r in db.oem_sold.find({})]
    leads = [l async for l in db.leads.find({})]
    if not sold:
        return [], True
    classified = oem_sync.classify_oem_billing(sold, leads)
    live = [l for l in leads if not _dead_lead(l)]
    out = []
    for row in classified:
        if row.get("bucket") != oem_sync.BUCKET_UNMATCHED:
            continue
        chassis = row.get("chassis") or ""
        candidates = []
        for lead in live:
            score = oem_sync.sold_match_score(row, lead)
            if score <= 0:
                name_key = oem_sync._norm_person_name(row.get("customerName"))
                if oem_sync._name_key_usable(name_key) and name_key == oem_sync._norm_person_name(
                        lead.get("customerName")):
                    score = 0.5
                else:
                    continue
            candidates.append({
                "leadId": lead.get("leadId"),
                "customerName": lead.get("customerName") or "",
                "score": score,
            })
        candidates.sort(key=lambda c: -c["score"])
        top = candidates[0] if len(candidates) == 1 else (
            candidates[0] if candidates and candidates[0]["score"] >= 1
            and (len(candidates) == 1 or candidates[0]["score"] > candidates[1]["score"])
            else None
        )
        proposed = (top or {}).get("leadId") or ""
        out.append({
            "agent": AGENT_OEM_MATCH,
            "fingerprint": fingerprint(AGENT_OEM_MATCH, chassis),
            "leadId": proposed,
            "severity": "High" if proposed else "Medium",
            "href": "/oem-billing",
            "title": (
                f"OEM sold {chassis} → {proposed}"
                if proposed else f"OEM sold {chassis} unmatched"
            ),
            "detail": (
                f"{row.get('customerName') or ''} · {row.get('mobile') or ''} · "
                f"{row.get('model') or ''} {row.get('variant') or ''}"
            ).strip(" ·"),
            "payload": {
                "chassis": chassis,
                "invoiceNumber": row.get("invoiceNumber") or "",
                "proposedLeadId": proposed,
                "candidates": candidates[:5],
            },
        })
    return out, True


async def scan_oem_settlement(db) -> tuple:
    rows = await oem_claims.list_claims(db, unmatched_only=True)
    out = []
    pool = rows or []
    for row in pool[:60]:
        num = str(row.get("claimNumber") or row.get("oemClaimNumber") or "").strip()
        if not num:
            continue
        out.append({
            "agent": AGENT_OEM_SETTLEMENT,
            "fingerprint": fingerprint(AGENT_OEM_SETTLEMENT, num),
            "leadId": (row.get("leadIds") or [""])[0] if row.get("leadIds") else "",
            "severity": "Medium",
            "href": "/oem-claims",
            "title": f"OEM claim {num} unmatched",
            "detail": "Open OEM Claim Settlements and match by eye. Confirm only acknowledges.",
            "payload": {
                "claimNumber": num,
                "status": row.get("status") or "",
                "acknowledgeOnly": True,
            },
        })
    return out, len(pool) <= 60


async def scan_coulson(db) -> tuple:
    doc = await db["system"].find_one({"_id": "coulson"}) or {}
    if not doc:
        return [], True
    expired = oem_sync.session_expired(doc)
    has_session = bool(oem_sync.session_from_doc(doc))
    user, pw, _src = await oem_sync.resolve_credentials(db)
    configured = oem_sync.credentials_configured(user, pw)
    if has_session and not expired:
        exp = str(doc.get("sessionExpiresAt") or "")
        if exp:
            try:
                when = datetime.fromisoformat(exp.replace("Z", "+00:00"))
            except ValueError:
                when = None
            if when:
                hours = (when - datetime.now(timezone.utc)).total_seconds() / 3600
                if hours > 12:
                    return [], True
                return [{
                    "agent": AGENT_COULSON,
                    "fingerprint": fingerprint(AGENT_COULSON, "expiring"),
                    "leadId": "",
                    "severity": "Medium",
                    "href": "/settings",
                    "title": "Coulson session expires within 12 hours",
                    "detail": (
                        "Confirm retries saved username/password then Sync. "
                        "If Euler refuses this server, paste coulson_auth in Settings."
                    ),
                    "payload": {"action": "renew_sync", "sessionExpiresAt": exp},
                }], True
        return [], True
    if expired or (configured and not has_session):
        return [{
            "agent": AGENT_COULSON,
            "fingerprint": fingerprint(AGENT_COULSON, "expired"),
            "leadId": "",
            "severity": "High",
            "href": "/settings",
            "title": "Coulson session expired — renew or paste",
            "detail": (
                "Confirm tries saved login + Sync. "
                "This app cannot F12 coulson.eulerlogistics.com. "
                "If renew fails, paste localStorage coulson_auth."
            ),
            "payload": {"action": "renew_sync", "sessionExpired": True},
        }], True
    return [], True


_FOLLOWUP_STATUSES = ("New", "Contacted", "Follow-up", "Hot", "In Progress", "")


async def scan_followup(db) -> tuple:
    out = []
    today_s = today()
    async for lead in db.leads.find(
            {"accountStatus": {"$nin": ["Cancelled", "Inactive", "Archived"]},
             "dealCancelled": {"$ne": True},
             "currentStatus": {"$in": list(_FOLLOWUP_STATUSES) + ["New"]}},
            _LIVE_LEAD_PROJ):
        if len(out) >= 80:
            break
        if _dead_lead(lead) or _is_delivered(lead) or _is_booked(lead):
            continue
        st = str(lead.get("currentStatus") or "New").strip().lower()
        if st not in OPEN_FOLLOWUP_STATUSES and st:
            # New is in the set; empty counts as New.
            if st not in ("",):
                continue
        lid = lead.get("leadId") or ""
        due = str(lead.get("nextFollowupDate") or lead.get("nextFollowup") or "")[:10]
        overdue = (not due) or due < today_s
        if not overdue:
            continue
        out.append({
            "agent": AGENT_FOLLOWUP,
            "fingerprint": fingerprint(AGENT_FOLLOWUP, lid),
            "leadId": lid,
            "severity": "Medium" if due else "Info",
            "href": "/leads",
            "title": f"{lid} follow-up {'overdue' if due else 'not set'}",
            "detail": (
                f"{lead.get('customerName') or ''} · {lead.get('executive') or ''} · "
                f"{lead.get('interestedModel') or ''} · next was {due or '—'}"
            ),
            "payload": {
                "nextFollowupDate": due,
                "draftNote": (
                    f"Call {lead.get('customerName') or 'customer'} about "
                    f"{lead.get('interestedModel') or 'the vehicle'} "
                    f"(lead {lid}). Next follow-up was {due or 'not set'}."
                ),
            },
        })
    return out, True


async def scan_tally_prep(db) -> tuple:
    out = []
    async for lead in db.leads.find({
            "$or": [
                {"deliveryStatus": "Delivered"},
                {"currentStatus": "Delivered"},
            ]}).sort("deliveryDate", -1):
        if len(out) >= 40:
            return out, False
        if not _is_delivered(lead):
            continue
        if _dead_lead(lead) and str(lead.get("currentStatus") or "").lower() != "delivered":
            continue
        lid = lead.get("leadId") or ""
        stored = lead.get("deliveryBillingSummary") or {}
        try:
            summary = ce.build_delivery_billing_summary(lead)
        except Exception:
            log.exception("tally-prep summary failed for %s", lid)
            continue
        lines = []
        for ln in (summary.get("tallyInvoiceLines") or []):
            lines.append({
                "section": "A",
                "code": ln.get("code"),
                "label": ln.get("label") or ln.get("code"),
                "amount": ln.get("amount"),
            })
        for ln in (summary.get("offTallyLines") or []):
            lines.append({
                "section": "B",
                "code": ln.get("code"),
                "label": ln.get("label") or ln.get("code"),
                "amount": ln.get("amount"),
            })
        totals = summary.get("totals") or {}
        lines.append({
            "section": "C",
            "code": "customerCollect",
            "label": "Customer collect",
            "amount": totals.get("customerCollectTotal"),
        })
        out.append({
            "agent": AGENT_TALLY,
            "fingerprint": fingerprint(AGENT_TALLY, lid),
            "leadId": lid,
            "severity": "Info",
            "href": "/accounts",
            "title": f"{lid} Tally type-in list",
            "detail": (
                f"Vehicle without GST → discount → GST, then RTO/Insurance. "
                f"Collect {ce.round2(ce.num(totals.get('customerCollectTotal')))}. "
                "Confirm acknowledges. This does not post to Tally."
            ),
            "payload": {
                "lines": lines,
                "tallyBillTotal": totals.get("tallyBillTotal"),
                "offTallyTotal": totals.get("offTallyTotal"),
                "customerCollectTotal": totals.get("customerCollectTotal"),
                "acknowledgeOnly": True,
                "hadStoredSummary": bool(stored),
            },
        })
    return out, True


SCANNER_AGENTS = {
    "scan_documents": {AGENT_DOCUMENT},
    "scan_pdf_rto_insurance": {AGENT_PDF, AGENT_PDF_CHASSIS},
    "scan_oem_match": {AGENT_OEM_MATCH},
    "scan_oem_settlement": {AGENT_OEM_SETTLEMENT},
    "scan_coulson": {AGENT_COULSON},
    "scan_followup": {AGENT_FOLLOWUP},
    "scan_tally_prep": {AGENT_TALLY},
}

SCANNERS = (
    scan_documents,
    scan_pdf_rto_insurance,
    scan_oem_match,
    scan_oem_settlement,
    scan_coulson,
    scan_followup,
    scan_tally_prep,
)


async def run_scan(db) -> dict:
    created = updated = skipped = 0
    keep = set()
    counts = {a: 0 for a in AGENTS}
    complete_agents = set()
    for fn in SCANNERS:
        try:
            got = await fn(db)
        except Exception:
            log.exception("agent scan %s failed", fn.__name__)
            continue
        if isinstance(got, tuple):
            rows, complete = got[0], bool(got[1])
        else:
            rows, complete = got, False
        if complete:
            complete_agents |= SCANNER_AGENTS.get(fn.__name__, set())
        for row in rows or []:
            keep.add(row["fingerprint"])
            counts[row["agent"]] = counts.get(row["agent"], 0) + 1
            _sid, action = await _upsert(db, row)
            if action == "created":
                created += 1
            elif action == "updated":
                updated += 1
            else:
                skipped += 1
    closed = await _close_stale(db, keep, complete_agents)
    open_n = await db[COLLECTION].count_documents({"status": "open"})
    meta = {
        "_id": SCAN_META,
        "lastScanAt": now_iso(),
        "open": open_n,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "closedStale": closed,
        "emitted": counts,
    }
    await db["system"].update_one({"_id": SCAN_META}, {"$set": meta}, upsert=True)
    return {k: v for k, v in meta.items() if k != "_id"}


async def dismiss(db, suggestion_id: str, user) -> dict:
    row = await get_suggestion(db, suggestion_id)
    if not row:
        return {}
    now = now_iso()
    await db[COLLECTION].update_one(
        {"suggestionId": suggestion_id},
        {"$set": {
            "status": "dismissed",
            "resolvedAt": now,
            "resolvedBy": (user or {}).get("email") or "",
            "updatedAt": now,
        }},
    )
    return await get_suggestion(db, suggestion_id)


async def mark_confirmed(db, suggestion_id: str, user, result: dict) -> dict:
    now = now_iso()
    await db[COLLECTION].update_one(
        {"suggestionId": suggestion_id},
        {"$set": {
            "status": "confirmed",
            "resolvedAt": now,
            "resolvedBy": (user or {}).get("email") or "",
            "updatedAt": now,
            "result": result or {},
        }},
    )
    return await get_suggestion(db, suggestion_id)


def price_payload_from_lead(lead, *, rto=None, insurance_amount=None) -> dict:
    """Copy the saved Price Structure and overwrite only RTO and/or insuranceAmount."""
    lead = lead or {}
    return {
        "exShowroom": ce.num(lead.get("exShowroom")),
        "rto": ce.num(lead.get("rto") if rto is None else rto),
        "insuranceAmount": ce.num(
            lead.get("insuranceAmount") if insurance_amount is None else insurance_amount),
        "insuranceArrangedBy": ce.normalize_insurance_arranged_by(
            lead.get("insuranceArrangedBy")),
        "accessoriesAmount": ce.num(lead.get("accessoriesAmount")),
        "handlingCharges": ce.num(lead.get("handlingCharges")),
        "trc": ce.num(lead.get("trc")),
        "fastag": ce.num(lead.get("fastag")),
        "extendedWarranty": ce.num(lead.get("extendedWarranty")),
        "rsaAmc": ce.num(lead.get("rsaAmc")),
        "otherCharges": ce.num(lead.get("otherCharges")),
        "tcsApplicable": lead.get("tcsApplicable") or "No",
        "finalExchangeValue": ce.num(lead.get("finalExchangeValue")),
    }
