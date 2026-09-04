"""Match an insurance agent's MIS spreadsheet to Insurance Payout entries.

The agent sends a payout MIS (policy / customer / amount). We map it onto the
register, show expected vs MIS difference, and the owner ticks rows to accept
the agent's figure as received — even when it is short or over expected.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import commercial as ce

MIS_COLUMNS = (
    ("Policy Number", "policyNumber"),
    ("Customer Name", "customerName"),
    ("Mobile", "mobile"),
    ("Lead ID", "leadId"),
    ("Entry ID", "entryId"),
    ("Premium", "insuranceAmount"),
    ("Payout Amount", "misAmount"),
    ("Insurer", "insuranceCompany"),
    ("UTR / Reference", "reference"),
    ("Policy Date", "policyDate"),
)

# Extra header spellings agents actually put on MIS files.
_FIELD_ALIASES = {
    "policyNumber": (
        "policy number", "policy no", "policy no.", "policy #", "policyno",
        "policy", "policy_no",
    ),
    "customerName": (
        "customer name", "customer", "insured", "insured name", "proposer",
        "name",
    ),
    "mobile": ("mobile", "phone", "mobile no", "mobile number", "contact"),
    "leadId": ("lead id", "leadid", "lead"),
    "entryId": ("entry id", "entryid", "entry"),
    "insuranceAmount": (
        "premium", "premium amount", "idv premium", "insurance amount",
        "od premium",
    ),
    "misAmount": (
        "payout amount", "payout", "commission", "agent payout", "mis amount",
        "net payout", "payout rs", "amount", "received", "brokerage",
    ),
    "insuranceCompany": ("insurer", "insurance company", "company"),
    "reference": ("utr", "utr / reference", "reference", "utr no", "txn id"),
    "policyDate": ("policy date", "date", "risk date"),
}


def _alnum(s):
    return "".join(ch for ch in str(s or "").upper() if ch.isalnum())


def _digits(s):
    d = re.sub(r"\D", "", str(s or ""))
    return d[-10:] if len(d) >= 10 else d


def _name(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum())


def parse_money(v):
    if v in (None, ""):
        return 0.0
    if isinstance(v, (int, float)):
        return ce.round2(float(v))
    s = str(v).strip().replace(",", "").replace("₹", "").replace("Rs.", "").replace("Rs", "")
    s = s.replace("INR", "").strip()
    if not s:
        return 0.0
    try:
        return ce.round2(float(s))
    except (TypeError, ValueError):
        return 0.0


def suggest_mapping(headers):
    lower = {str(h).strip().lower(): str(h).strip() for h in headers if h not in (None, "")}
    mapping = {}
    used = set()
    for _label, field in MIS_COLUMNS:
        hit = ""
        for alias in _FIELD_ALIASES.get(field, ()):
            if alias in lower and lower[alias] not in used:
                hit = lower[alias]
                break
        if not hit and field.lower() in lower and lower[field.lower()] not in used:
            hit = lower[field.lower()]
        mapping[field] = hit
        if hit:
            used.add(hit)
    return mapping


def parse_rows(raw_rows, mapping):
    """Turn spreadsheet rows into dicts keyed by MIS field. First row is headers."""
    if not raw_rows:
        return [], []
    headers = [str(h).strip() if h is not None else "" for h in raw_rows[0]]
    idx = {h: i for i, h in enumerate(headers) if h}
    out = []
    for n, row in enumerate(raw_rows[1:], start=2):
        rec = {"_row": n}
        empty = True
        for field, header in (mapping or {}).items():
            if not header:
                rec[field] = "" if field != "misAmount" and field != "insuranceAmount" else 0.0
                continue
            i = idx.get(header)
            cell = row[i] if i is not None and i < len(row) else None
            if cell not in (None, ""):
                empty = False
            if field in ("misAmount", "insuranceAmount"):
                rec[field] = parse_money(cell)
            elif field == "mobile":
                rec[field] = _digits(cell)
            elif field == "policyDate":
                rec[field] = _as_iso_date(cell)
            else:
                rec[field] = str(cell).strip() if cell not in (None, "None") else ""
        if not empty:
            out.append(rec)
    return headers, out


def _as_iso_date(value):
    if value in (None, ""):
        return ""
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    s = str(value).strip()
    m = re.match(r"^(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return s
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{4})$", s)
    if m:
        d, mo, y = m.groups()
        try:
            return date(int(y), int(mo), int(d)).isoformat()
        except ValueError:
            return s
    return s


def _entry_indexes(entries):
    by_entry, by_lead, by_policy, by_mobile, by_name_prem = {}, {}, {}, {}, {}
    for e in entries:
        if str(e.get("status") or "").startswith("N/A"):
            continue
        eid = str(e.get("entryId") or "")
        if eid:
            by_entry[eid.upper()] = e
        lid = str(e.get("leadId") or "").strip()
        if lid:
            by_lead.setdefault(lid.upper(), []).append(e)
        pol = _alnum(e.get("policyNumber"))
        if pol:
            by_policy.setdefault(pol, []).append(e)
        mob = _digits(e.get("mobile"))
        if len(mob) == 10:
            by_mobile.setdefault(mob, []).append(e)
        nm = _name(e.get("customerName"))
        if nm:
            by_name_prem.setdefault(nm, []).append(e)
    return by_entry, by_lead, by_policy, by_mobile, by_name_prem


def _pick(hits, reason_ok, reason_amb):
    if len(hits) == 1:
        return hits[0], reason_ok
    if len(hits) > 1:
        return None, reason_amb
    return None, ""


def match_row(row, indexes):
    """Return (entry, matchKey) or (None, reason)."""
    by_entry, by_lead, by_policy, by_mobile, by_name_prem = indexes
    eid = str(row.get("entryId") or "").strip()
    if eid:
        hit = by_entry.get(eid.upper())
        if hit:
            return hit, "entryId"
        return None, "entry_id_not_found"
    lid = str(row.get("leadId") or "").strip()
    if lid:
        hits = by_lead.get(lid.upper()) or []
        picked, why = _pick(hits, "leadId", "ambiguous_lead")
        if picked or why:
            return picked, why
    pol = _alnum(row.get("policyNumber"))
    if pol:
        hits = by_policy.get(pol) or []
        picked, why = _pick(hits, "policyNumber", "ambiguous_policy")
        if picked or why:
            return picked, why
    mob = _digits(row.get("mobile"))
    if len(mob) == 10:
        hits = by_mobile.get(mob) or []
        picked, why = _pick(hits, "mobile", "ambiguous_mobile")
        if picked or why:
            return picked, why
    nm = _name(row.get("customerName"))
    prem = parse_money(row.get("insuranceAmount"))
    if nm:
        hits = by_name_prem.get(nm) or []
        if prem > 0:
            hits = [e for e in hits if abs(ce.num(e.get("insuranceAmount")) - prem) < 1]
        picked, why = _pick(hits, "customer", "ambiguous_customer")
        if picked or why:
            return picked, why
    return None, "unmatched"


def match_file(mis_rows, entries):
    indexes = _entry_indexes(entries)
    used = set()
    matched, unmatched_mis = [], []
    for row in mis_rows:
        amount = parse_money(row.get("misAmount"))
        if amount <= 0:
            unmatched_mis.append({**_mis_public(row), "reason": "no_payout_amount"})
            continue
        entry, key = match_row(row, indexes)
        if not entry:
            unmatched_mis.append({**_mis_public(row), "reason": key or "unmatched"})
            continue
        eid = entry.get("entryId")
        if eid in used:
            unmatched_mis.append({**_mis_public(row), "reason": "duplicate_match",
                                  "entryId": eid})
            continue
        used.add(eid)
        expected = ce.round2(ce.num(entry.get("expectedPayout")))
        already = ce.round2(ce.num(entry.get("receivedPayout")))
        matched.append({
            **_mis_public(row),
            "entryId": eid,
            "leadId": entry.get("leadId") or "",
            "registerCustomer": entry.get("customerName") or "",
            "registerPolicy": entry.get("policyNumber") or "",
            "insuranceAgentName": entry.get("insuranceAgentName") or "",
            "expectedPayout": expected,
            "alreadyReceived": already,
            "misAmount": amount,
            "difference": ce.round2(amount - expected),
            "matchKey": key,
            "misApproved": bool(entry.get("misApproved")),
            "status": entry.get("status") or "",
        })
    unmatched_entries = []
    for e in entries:
        if str(e.get("status") or "").startswith("N/A"):
            continue
        if e.get("entryId") in used:
            continue
        if str(e.get("status") or "") == "Received" or e.get("misApproved"):
            continue
        unmatched_entries.append({
            "entryId": e.get("entryId"),
            "leadId": e.get("leadId") or "",
            "customerName": e.get("customerName") or "",
            "policyNumber": e.get("policyNumber") or "",
            "mobile": e.get("mobile") or "",
            "expectedPayout": ce.round2(ce.num(e.get("expectedPayout"))),
            "receivedPayout": ce.round2(ce.num(e.get("receivedPayout"))),
            "status": e.get("status") or "",
        })
    return {
        "matched": matched,
        "unmatchedMis": unmatched_mis,
        "unmatchedEntries": unmatched_entries,
        "totals": {
            "misRows": len(mis_rows),
            "matched": len(matched),
            "unmatchedMis": len(unmatched_mis),
            "unmatchedEntries": len(unmatched_entries),
            "misAmount": ce.round2(sum(r["misAmount"] for r in matched)),
            "expected": ce.round2(sum(r["expectedPayout"] for r in matched)),
            "difference": ce.round2(sum(r["difference"] for r in matched)),
        },
    }


def _mis_public(row):
    return {
        "row": row.get("_row"),
        "policyNumber": row.get("policyNumber") or "",
        "customerName": row.get("customerName") or "",
        "mobile": row.get("mobile") or "",
        "leadId": row.get("leadId") or "",
        "entryId": row.get("entryId") or "",
        "insuranceAmount": parse_money(row.get("insuranceAmount")),
        "misAmount": parse_money(row.get("misAmount")),
        "insuranceCompany": row.get("insuranceCompany") or "",
        "reference": row.get("reference") or "",
        "policyDate": row.get("policyDate") or "",
    }
