"""Match an insurance agent's MIS spreadsheet to Insurance Payout entries.

The agent file keys each vehicle by **chassis**. We dedupe on that VIN, fetch the
Insurance Payout / lead details, show expected vs MIS difference, and the owner
ticks rows to accept the agent's figure as received — even when it is short or over.
"""
from __future__ import annotations

import re
from datetime import date, datetime

import commercial as ce

MIS_COLUMNS = (
    ("Chassis", "chassisNumber"),
    ("Policy Number", "policyNumber"),
    ("Customer Name", "customerName"),
    ("Mobile", "mobile"),
    ("Lead ID", "leadId"),
    ("Entry ID", "entryId"),
    ("Premium", "insuranceAmount"),
    ("Distribution Fee", "misAmount"),
    ("Insurer", "insuranceCompany"),
    ("UTR / Reference", "reference"),
    ("Policy Date", "policyDate"),
)

# Extra header spellings agents actually put on MIS files.
_FIELD_ALIASES = {
    "chassisNumber": (
        "chassis", "chassis number", "chassis no", "chassis no.", "chassis #",
        "chasis", "chasis number", "vin", "vin no", "vehicle chassis",
    ),
    "policyNumber": (
        "policy number", "policy no", "policy no.", "policy #", "policyno",
        "policy", "policy_no",
    ),
    "customerName": (
        "insured name", "customer name", "customer", "insured", "proposer",
        "name",
    ),
    "mobile": ("mobile", "phone", "mobile no", "mobile number", "contact"),
    "leadId": ("lead id", "leadid", "lead"),
    "entryId": ("entry id", "entryid", "entry"),
    "insuranceAmount": (
        "gross", "gross premium", "premium", "premium amount", "insurance amount",
        "od premium", "net",
    ),
    "misAmount": (
        "distribut fee", "distribution fee", "distributor fee", "distrib fee",
        "payout amount", "payout", "commission", "agent payout", "mis amount",
        "net payout", "payout rs", "brokerage", "amount", "received",
    ),
    "insuranceCompany": (
        "insurance comp", "insurance company", "insurer", "company",
    ),
    "reference": ("utr", "utr / reference", "reference", "utr no", "txn id"),
    "policyDate": (
        "valid from", "valid f", "policy date", "risk date", "date",
    ),
}


def _norm_chassis(s):
    return re.sub(r"\s+", "", str(s or "")).strip().upper()


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
            elif field == "chassisNumber":
                rec[field] = _norm_chassis(cell)
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
    m = re.match(r"^(\d{1,2})[-/](\d{1,2})[-/](\d{2,4})$", s)
    if m:
        d, mo, y = m.groups()
        yi = int(y)
        if yi < 100:
            yi += 2000
        try:
            return date(yi, int(mo), int(d)).isoformat()
        except ValueError:
            return s
    m = re.match(r"^(\d{1,2})[-/\s]([A-Za-z]{3,9})[-/\s](\d{2,4})$", s)
    if m:
        d, mon, y = m.groups()
        yi = int(y)
        if yi < 100:
            yi += 2000
        months = ("jan", "feb", "mar", "apr", "may", "jun",
                  "jul", "aug", "sep", "oct", "nov", "dec")
        try:
            mo = months.index(mon[:3].lower()) + 1
            return date(yi, mo, int(d)).isoformat()
        except ValueError:
            return s
    return s


def enrich_entries_with_chassis(entries, leads):
    """Copy the lead's chassis onto each payout so the agent MIS can join on VIN."""
    by_id = {}
    for lead in leads or []:
        lid = str(lead.get("leadId") or "").strip()
        if lid:
            by_id[lid] = _norm_chassis(lead.get("chassisNumber"))
    out = []
    for e in entries or []:
        e = dict(e)
        e["chassisNumber"] = (
            _norm_chassis(e.get("chassisNumber"))
            or by_id.get(str(e.get("leadId") or "").strip())
            or ""
        )
        out.append(e)
    return out


def unique_by_chassis(rows):
    """One MIS row per chassis. Blank-chassis rows keep other keys (policy / mobile)."""
    seen = set()
    out, dupes = [], []
    for row in rows or []:
        ch = _norm_chassis(row.get("chassisNumber"))
        if not ch:
            out.append(row)
            continue
        row = {**row, "chassisNumber": ch}
        if ch in seen:
            dupes.append({**_mis_public(row), "reason": "duplicate_chassis"})
            continue
        seen.add(ch)
        out.append(row)
    return out, dupes


def attach_lead_hint(unmatched, leads):
    """When chassis misses a payout entry, still fetch the lead so the desk sees who it is."""
    by_ch = {}
    for lead in leads or []:
        ch = _norm_chassis(lead.get("chassisNumber"))
        if ch:
            by_ch.setdefault(ch, lead)
    for r in unmatched or []:
        if r.get("reason") not in ("chassis_not_found", "no_payout_amount", "duplicate_chassis"):
            continue
        lead = by_ch.get(_norm_chassis(r.get("chassisNumber")))
        if not lead:
            continue
        r["leadId"] = lead.get("leadId") or r.get("leadId") or ""
        r["registerCustomer"] = lead.get("customerName") or ""
        r["registerChassis"] = _norm_chassis(lead.get("chassisNumber"))
        if r.get("reason") == "chassis_not_found":
            r["reason"] = "no_payout_entry"
    return unmatched


def _entry_indexes(entries):
    by_entry, by_lead, by_chassis, by_policy, by_mobile, by_name_prem = (
        {}, {}, {}, {}, {}, {})
    for e in entries:
        if str(e.get("status") or "").startswith("N/A"):
            continue
        eid = str(e.get("entryId") or "")
        if eid:
            by_entry[eid.upper()] = e
        lid = str(e.get("leadId") or "").strip()
        if lid:
            by_lead.setdefault(lid.upper(), []).append(e)
        ch = _norm_chassis(e.get("chassisNumber"))
        if ch:
            by_chassis.setdefault(ch, []).append(e)
        pol = _alnum(e.get("policyNumber"))
        if pol:
            by_policy.setdefault(pol, []).append(e)
        mob = _digits(e.get("mobile"))
        if len(mob) == 10:
            by_mobile.setdefault(mob, []).append(e)
        nm = _name(e.get("customerName"))
        if nm:
            by_name_prem.setdefault(nm, []).append(e)
    return by_entry, by_lead, by_chassis, by_policy, by_mobile, by_name_prem


def _pick(hits, reason_ok, reason_amb):
    if len(hits) == 1:
        return hits[0], reason_ok
    if len(hits) > 1:
        return None, reason_amb
    return None, ""


def match_row(row, indexes):
    """Return (entry, matchKey) or (None, reason). Chassis wins — it is unique on the vehicle."""
    by_entry, by_lead, by_chassis, by_policy, by_mobile, by_name_prem = indexes
    eid = str(row.get("entryId") or "").strip()
    if eid:
        hit = by_entry.get(eid.upper())
        if hit:
            return hit, "entryId"
        return None, "entry_id_not_found"
    ch = _norm_chassis(row.get("chassisNumber"))
    if ch:
        hits = by_chassis.get(ch) or []
        picked, why = _pick(hits, "chassis", "ambiguous_chassis")
        if picked or why:
            return picked, why
        return None, "chassis_not_found"
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
    rows, chassis_dupes = unique_by_chassis(mis_rows)
    indexes = _entry_indexes(entries)
    used = set()
    matched, unmatched_mis = [], []
    unmatched_mis.extend(chassis_dupes)
    for row in rows:
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
            "leadId": entry.get("leadId") or row.get("leadId") or "",
            "registerCustomer": entry.get("customerName") or "",
            "registerPolicy": entry.get("policyNumber") or "",
            "registerChassis": entry.get("chassisNumber") or "",
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
        # Already-received cash does not need the agent to chase it. Mapped-but-unpaid
        # and never-mapped rows that are missing from this file do.
        if str(e.get("status") or "") == "Received" and ce.num(e.get("receivedPayout")) > 0.01:
            continue
        unmatched_entries.append({
            "entryId": e.get("entryId"),
            "leadId": e.get("leadId") or "",
            "customerName": e.get("customerName") or "",
            "policyNumber": e.get("policyNumber") or "",
            "chassisNumber": e.get("chassisNumber") or "",
            "mobile": e.get("mobile") or "",
            "expectedPayout": ce.round2(ce.num(e.get("expectedPayout"))),
            "receivedPayout": ce.round2(ce.num(e.get("receivedPayout"))),
            "status": e.get("status") or "",
            "misApproved": bool(e.get("misApproved")),
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
        "chassisNumber": _norm_chassis(row.get("chassisNumber")),
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
