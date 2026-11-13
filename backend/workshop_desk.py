"""Workshop desk: read a parts mail, join it to a Coulson request, and keep
a missing paid part as an advance instead of a second purchase.

The state is a plain dict so the sales app can store it in the same Mongo
database. Nothing here talks to the network.
"""
from __future__ import annotations

import re
import uuid
from copy import deepcopy

STAGES = (
    "need", "asked", "onpi", "paid", "transit", "short", "reorder", "received",
)

STAGE_LABEL = {
    "need": "To order",
    "asked": "Asked, no PI yet",
    "onpi": "On the PI",
    "paid": "Paid, waiting for dispatch",
    "transit": "On the truck",
    "short": "Missing from the box",
    "reorder": "Ordered again, against the advance",
    "received": "In the store",
}

OPEN_MISSING = ("short", "reorder")
EARLY = ("need", "asked", "onpi", "paid")

_TICKET_RE = re.compile(r"\b(?:ticket|request)\s*#?\s*(\d{4,7})\b", re.I)
_PI_RE = re.compile(r"\b(PI/[A-Z0-9]+(?:/[A-Z0-9]+)+)\b", re.I)
_UTR_RE = re.compile(r"\bUTR\s*[:#-]?\s*([A-Z0-9]{6,})\b", re.I)
_CODE_RE = re.compile(r"\b([A-Z]{2,}[A-Z0-9]*\d[A-Z0-9]{3,})\b")
_MONEY_RE = re.compile(r"(?:₹|Rs\.?)\s*([0-9][0-9,]*(?:\.\d{1,2})?)")
_QTY_RE = re.compile(r"(\d+)\s*nos\b|quantity\s*(\d+)", re.I)


def _new_id():
    return uuid.uuid4().hex[:12]


def _money(raw):
    try:
        return round(float(str(raw).replace(",", "")), 2)
    except (TypeError, ValueError):
        return None


def inr(amount):
    if amount is None:
        return ""
    n = int(round(float(amount)))
    sign = "-" if n < 0 else ""
    s = str(abs(n))
    if len(s) <= 3:
        return f"{sign}₹{s}"
    tail, head = s[-3:], s[:-3]
    groups = []
    while head:
        groups.append(head[-2:])
        head = head[:-2]
    return sign + "₹" + ",".join(reversed(groups)) + "," + tail


def empty_state():
    return {
        "lines": [],
        "mails": [],
        "advances": {},
        "warranty": {"total": 0, "amount": 0, "rows": [], "breakdown": []},
        "jobs": {
            "openTickets": [],
            "inProgress": 0,
            "overdue": 0,
            "dueSoon": 0,
            "booked": 0,
            "completed": 0,
            "complaintsOpen": 0,
            "complaintsTotal": 0,
            "coverage": [],
        },
        "syncedAt": "",
        "syncError": "",
    }


def _codes(text):
    return list(dict.fromkeys(_CODE_RE.findall(text or "")))


def _qty_for(text, code):
    for line in (text or "").splitlines():
        if code not in line:
            continue
        match = _QTY_RE.search(line)
        if not match:
            continue
        raw = match.group(1) or match.group(2)
        try:
            return int(raw)
        except (TypeError, ValueError):
            return None
    return None


def parse_mail(subject, body):
    """Read a mail the way the desk will read the service mailbox."""
    subject = str(subject or "").strip()
    body = str(body or "").strip()
    text = f"{subject}\n{body}".strip()
    request_nos = list(dict.fromkeys(_TICKET_RE.findall(text)))
    pi_match = _PI_RE.search(text)
    pi = pi_match.group(1).upper() if pi_match else ""
    utr_match = _UTR_RE.search(text)
    utr = utr_match.group(1).upper() if utr_match else ""
    scanned = text
    if utr:
        scanned = _UTR_RE.sub(" ", scanned)
    if pi:
        scanned = scanned.replace(pi, " ")

    missing, sent = [], []
    mode = None
    for line in scanned.splitlines():
        low = line.lower()
        if "not dispatched" in low or "not available" in low:
            mode = "missing"
            missing.extend(_codes(line))
            continue
        if re.search(r"\bdispatched\b", low):
            mode = "sent"
            sent.extend(_codes(line))
            continue
        found = _codes(line)
        if mode == "missing":
            missing.extend(found)
        elif mode == "sent":
            sent.extend(found)
    missing = list(dict.fromkeys(missing))
    sent = [code for code in dict.fromkeys(sent) if code not in missing]
    mentioned = list(dict.fromkeys(missing + sent + [
        code for code in _codes(scanned) if code not in missing and code not in sent
    ]))

    amounts = [_money(m) for m in _MONEY_RE.findall(text)]
    amounts = [n for n in amounts if n is not None]
    advance = None
    for line in text.splitlines():
        if re.search(r"advance|parked", line, re.I):
            found = [_money(m) for m in _MONEY_RE.findall(line)]
            found = [n for n in found if n is not None]
            if found:
                advance = found[-1]
                break
    amount = amounts[0] if amounts else None
    low = text.lower()
    # A single ticket number is what joins a mail. None, or more than one, waits
    # for a person even when the wording looks like a dispatch or a payment.
    if len(request_nos) != 1:
        kind = "unmatched"
    elif missing or "not dispatched" in low or "not available" in low:
        kind = "dispatch"
    elif utr or "payment done" in low or "payment is already" in low:
        kind = "payment"
    elif pi or "invoice is attached" in low:
        kind = "pi"
    elif "adjust" in low and "already paid" in low:
        kind = "reorder"
    elif sent:
        kind = "dispatch"
    elif request_nos:
        kind = "ask"
    else:
        kind = "unmatched"

    qty = {}
    for code in missing + sent:
        q = _qty_for(text, code)
        if q:
            qty[code] = q

    finds = [
        ["Request number", ", ".join(request_nos) or "None"],
        ["Part code", ", ".join(mentioned) or "None"],
    ]
    if missing:
        finds.append(["Missing from the box", ", ".join(missing)])
    if sent:
        finds.append(["Sent", ", ".join(sent)])
    if pi:
        finds.append(["PI number", pi])
    if utr:
        finds.append(["Payment reference", utr])
    if advance is not None:
        finds.append(["Advance", inr(advance)])
    elif amount is not None:
        finds.append(["Amount", inr(amount)])

    if len(request_nos) > 1:
        preview = (
            f"This mail names tickets {', '.join(request_nos)}. "
            "A person has to split it before any part or money moves."
        )
    elif kind == "unmatched":
        preview = "No ticket number. It waits until a person files it."
    elif kind == "dispatch" and missing:
        parked = inr(advance if advance is not None else amount) or "the amount already paid"
        preview = (
            f"Joined to ticket {request_nos[0]}. "
            f"{', '.join(missing)} marked missing. {parked} stays as advance."
        )
    elif kind == "payment":
        preview = f"Marks ticket {request_nos[0]} paid."
    elif kind == "pi":
        preview = f"Writes {pi or 'the proforma invoice'} onto ticket {request_nos[0]}."
    elif kind == "reorder":
        preview = f"Asks the company to send the missing part on ticket {request_nos[0]} against the advance."
    elif sent:
        preview = f"Marks {', '.join(sent)} on the truck for ticket {request_nos[0]}."
    else:
        preview = f"Joins this mail to ticket {request_nos[0]}."

    return {
        "request_nos": request_nos,
        "missing_codes": missing,
        "sent_codes": sent,
        "pi": pi,
        "utr": utr,
        "amount": amount,
        "advance": advance,
        "qty": qty,
        "mentioned_codes": mentioned,
        "kind": kind,
        "finds": finds,
        "preview": preview,
    }


def _line(request_no, code, part, qty, stage, **extra):
    row = {
        "id": _new_id(),
        "requestNo": request_no or "",
        "part": part or code,
        "code": code,
        "qty": qty or 0,
        "stage": stage,
        "advance": 0,
        "pi": "",
        "note": "",
        "overCap": False,
        "suggestedQty": None,
        "source": "mail",
    }
    row.update(extra)
    return row


def _find_line(lines, request_no, code):
    for line in lines:
        if line.get("requestNo") == request_no and line.get("code") == code:
            return line
    return None


def paint_advances(lines, advances):
    for line in lines:
        line["advance"] = 0
    for request_no, amount in (advances or {}).items():
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            amount = 0
        if amount <= 0:
            continue
        open_lines = [
            line for line in lines
            if line.get("requestNo") == request_no and line.get("stage") in OPEN_MISSING
        ]
        if open_lines:
            open_lines[0]["advance"] = round(amount, 2)
    return lines


def _ensure(lines, request_no, code, parsed, stage):
    line = _find_line(lines, request_no, code)
    if line:
        return line
    line = _line(
        request_no, code, code,
        (parsed.get("qty") or {}).get(code) or 0,
        stage,
    )
    lines.append(line)
    return line


def apply_parsed(state, mail):
    """Join one mail onto its request and move the parts. Idempotent."""
    state = deepcopy(state)
    if mail.get("applied"):
        return state
    parsed = parse_mail(mail.get("subject"), mail.get("body"))
    mail = dict(mail)
    mail["kind"] = parsed["kind"]
    mail["finds"] = parsed["finds"]
    request_nos = parsed["request_nos"]
    mail["requestNo"] = request_nos[0] if len(request_nos) == 1 else ""
    if parsed["kind"] == "unmatched" or len(request_nos) != 1:
        mail["status"] = "unmatched"
        mail["applied"] = True
        mail["result"] = parsed["preview"]
        _replace_mail(state, mail)
        return state

    lines = state["lines"]
    advances = dict(state.get("advances") or {})
    request_no = request_nos[0]
    notes = []
    if parsed["pi"]:
        for line in lines:
            if line.get("requestNo") == request_no and not line.get("pi"):
                line["pi"] = parsed["pi"]
        notes.append(f"PI {parsed['pi']} filed on ticket {request_no}.")
    if parsed["kind"] == "pi":
        for code in parsed["mentioned_codes"]:
            line = _ensure(lines, request_no, code, parsed, "onpi")
            line["pi"] = parsed["pi"] or line.get("pi") or ""
            if line["stage"] in ("need", "asked"):
                line["stage"] = "onpi"
    if parsed["kind"] == "payment":
        for line in lines:
            if line.get("requestNo") == request_no and line.get("stage") in ("need", "asked", "onpi", "paid"):
                line["stage"] = "paid"
                if parsed["pi"]:
                    line["pi"] = parsed["pi"]
        notes.append(f"Ticket {request_no} marked paid.")
    if parsed["kind"] == "ask":
        for code in parsed["mentioned_codes"]:
            line = _ensure(lines, request_no, code, parsed, "asked")
            if line["stage"] == "need":
                line["stage"] = "asked"
        notes.append(f"Mail joined to ticket {request_no}.")
    parked = parsed["advance"] if parsed["advance"] is not None else parsed["amount"]
    if parsed["missing_codes"]:
        for code in parsed["missing_codes"]:
            line = _ensure(lines, request_no, code, parsed, "short")
            if line["stage"] not in ("received",):
                line["stage"] = "short"
                line["note"] = "The dispatch mail says this part was not sent. It stays on this ticket against the advance."
            if parsed["pi"]:
                line["pi"] = parsed["pi"]
        if parked:
            advances[request_no] = parked
        notes.append(
            f"{', '.join(parsed['missing_codes'])} missing from the box. "
            f"{inr(parked) + ' parked as advance.' if parked else 'The paid amount stays as advance.'}"
        )
    for code in parsed["sent_codes"]:
        line = _ensure(lines, request_no, code, parsed, "transit")
        if line["stage"] not in ("received", "short", "reorder"):
            line["stage"] = "transit"
            line["note"] = "The dispatch mail says this part was sent. Count it when the box arrives."
    if parsed["kind"] == "reorder":
        for line in lines:
            if line.get("requestNo") == request_no and line.get("stage") == "short":
                line["stage"] = "reorder"
                line["note"] = "Asked again on the same ticket, against the advance. No new proforma invoice."
        notes.append(f"Ticket {request_no} asked again against the advance.")

    paint_advances(lines, advances)
    state["advances"] = {k: v for k, v in advances.items() if _open_missing(lines, k)}
    paint_advances(lines, state["advances"])
    mail["status"] = "joined"
    mail["applied"] = True
    mail["result"] = " ".join(notes) or parsed["preview"]
    _replace_mail(state, mail)
    return state


def _open_missing(lines, request_no):
    return any(
        line.get("requestNo") == request_no and line.get("stage") in OPEN_MISSING
        for line in lines
    )


def _replace_mail(state, mail):
    mails = state["mails"]
    for i, old in enumerate(mails):
        if old.get("id") == mail.get("id"):
            mails[i] = mail
            return
    mails.append(mail)


def read_mail(state, mail_id):
    state = deepcopy(state)
    mail = next((m for m in state["mails"] if m.get("id") == mail_id), None)
    if not mail:
        raise KeyError(mail_id)
    if mail.get("applied"):
        return state
    return apply_parsed(state, mail)


def file_mail(state, mail_id, request_no):
    """A person picks the ticket for a mail that had no number."""
    state = deepcopy(state)
    request_no = str(request_no or "").strip()
    if not re.fullmatch(r"\d{4,7}", request_no):
        raise ValueError("Choose a ticket number.")
    mail = next((m for m in state["mails"] if m.get("id") == mail_id), None)
    if not mail:
        raise KeyError(mail_id)
    mail = dict(mail)
    mail["requestNo"] = request_no
    mail["status"] = "note"
    mail["applied"] = True
    mail["result"] = (
        f"A person filed this mail onto ticket {request_no}. "
        "No part and no money changed."
    )
    mail["finds"] = [
        ["Request number", f"{request_no}, chosen by a person"],
        ["Part code", "None"],
    ]
    _replace_mail(state, mail)
    return state


def approve_reorder(state, line_id):
    state = deepcopy(state)
    line = next((row for row in state["lines"] if row.get("id") == line_id), None)
    if not line:
        raise KeyError(line_id)
    if line.get("stage") != "short":
        raise ValueError("Only a part missing from the box can be ordered again against the advance.")
    request_no = line.get("requestNo") or ""
    amount = (state.get("advances") or {}).get(request_no) or line.get("advance") or 0
    line["stage"] = "reorder"
    line["note"] = "Asked again on the same ticket, against the advance. No new proforma invoice."
    paint_advances(state["lines"], state.get("advances") or {})
    seq = max([m.get("seq") or 0 for m in state["mails"]] or [0]) + 1
    body = "\n".join([
        f"Ticket {request_no}",
        f"Part {line.get('code')}, {line.get('part')}, quantity {line.get('qty') or ''}.",
        "This part was paid and was not dispatched.",
        f"Please send it and adjust the {inr(amount)} already paid.",
        "Do not raise a new proforma invoice.",
    ])
    mail = {
        "id": _new_id(),
        "seq": seq,
        "direction": "Sent by the workshop",
        "when": "Just sent",
        "subject": f"Re: Ticket {request_no} — please send against the advance",
        "body": body,
        "requestNo": request_no,
        "status": "joined",
        "applied": True,
        "kind": "reorder",
        "finds": [
            ["Request number", request_no],
            ["Part code", line.get("code") or ""],
            ["Signal", "adjust the amount already paid"],
            ["Amount", inr(amount)],
        ],
        "result": f"Sent on ticket {request_no}. The company is asked to use the advance, not to raise a new PI.",
    }
    state["mails"].append(mail)
    return state


def receive_line(state, line_id):
    state = deepcopy(state)
    line = next((row for row in state["lines"] if row.get("id") == line_id), None)
    if not line:
        raise KeyError(line_id)
    if line.get("stage") not in ("reorder", "transit", "short"):
        raise ValueError("Count a part in when it is on the truck, or when it was ordered again.")
    request_no = line.get("requestNo") or ""
    line["stage"] = "received"
    line["note"] = "Counted into the store."
    advances = dict(state.get("advances") or {})
    if not _open_missing(state["lines"], request_no):
        advances.pop(request_no, None)
    state["advances"] = advances
    paint_advances(state["lines"], advances)
    return state


def add_mail(state, subject, body, direction="Received from the company"):
    state = deepcopy(state)
    parsed = parse_mail(subject, body)
    seq = max([m.get("seq") or 0 for m in state["mails"]] or [0]) + 1
    mail = {
        "id": _new_id(),
        "seq": seq,
        "direction": direction or "Received from the company",
        "when": "Just pasted",
        "subject": str(subject or "").strip() or "(no subject)",
        "body": str(body or "").strip(),
        "requestNo": parsed["request_nos"][0] if len(parsed["request_nos"]) == 1 else "",
        "status": "unread",
        "applied": False,
        "kind": parsed["kind"],
        "finds": parsed["finds"],
        "result": parsed["preview"],
    }
    state["mails"].append(mail)
    # Reading happens when the person presses Read, except we return the mail
    # sitting unread so Today can show it. The caller may apply immediately.
    return state, mail["id"]


def desk_has_work(state):
    """True once the shared desk holds a part, a mail, or an advance."""
    state = state or {}
    if state.get("lines") or state.get("mails"):
        return True
    advances = state.get("advances") or {}
    if isinstance(advances, dict):
        return any(advances.values())
    return bool(advances)


def advance_rows(state):
    lines = state.get("lines") or []
    rows = []
    for request_no, amount in (state.get("advances") or {}).items():
        try:
            amount = float(amount or 0)
        except (TypeError, ValueError):
            continue
        if amount <= 0:
            continue
        parts = [
            line.get("part") or line.get("code")
            for line in lines
            if line.get("requestNo") == request_no and line.get("stage") in OPEN_MISSING
        ]
        if not parts:
            continue
        rows.append({
            "requestNo": request_no,
            "amount": round(amount, 2),
            "parts": parts,
        })
    return rows


def build_today(state):
    items = []
    for mail in state.get("mails") or []:
        if mail.get("status") == "unread" or not mail.get("applied"):
            items.append({
                "id": f"mail-{mail.get('id')}",
                "title": mail.get("subject") or "Unread mail",
                "detail": mail.get("result") or "Not read yet.",
                "tone": "warning",
                "mailId": mail.get("id"),
            })
        elif mail.get("status") == "unmatched":
            items.append({
                "id": f"mail-{mail.get('id')}",
                "title": mail.get("subject") or "Mail with no ticket",
                "detail": "No ticket number. A person has to file it.",
                "tone": "warning",
                "mailId": mail.get("id"),
            })
    for line in state.get("lines") or []:
        stage = line.get("stage")
        if stage == "short":
            items.append({
                "id": f"line-{line.get('id')}",
                "title": f"{line.get('part')} missing, ticket {line.get('requestNo') or '—'}",
                "detail": "Approve one follow-up mail. It uses the advance. It does not ask for a new PI.",
                "tone": "danger",
                "lineId": line.get("id"),
                "action": "reorder",
            })
        elif stage == "reorder":
            items.append({
                "id": f"line-{line.get('id')}",
                "title": f"{line.get('part')} ordered again, ticket {line.get('requestNo') or '—'}",
                "detail": "When the box arrives, count it in. That clears the advance for this part if nothing else on the ticket is still missing.",
                "tone": "info",
                "lineId": line.get("id"),
                "action": "receive",
            })
        elif stage == "transit":
            items.append({
                "id": f"line-{line.get('id')}",
                "title": f"{line.get('part')} is on the truck",
                "detail": line.get("requestNo") and f"Ticket {line.get('requestNo')}. Count the box." or "Count the box.",
                "tone": "info",
                "lineId": line.get("id"),
                "action": "receive",
            })
        elif stage == "need":
            detail = "Coulson marks this Order."
            if line.get("overCap"):
                detail = "Coulson marks this Order, but the suggested quantity is not usable. A person sets the quantity before it can be mailed."
            items.append({
                "id": f"line-{line.get('id')}",
                "title": f"{line.get('part')} to order",
                "detail": detail,
                "tone": "warning",
                "lineId": line.get("id"),
            })
    warranty = state.get("warranty") or {}
    for row in warranty.get("breakdown") or []:
        label = row.get("label") or ""
        count = row.get("count") or 0
        if not count:
            continue
        if "challan" in label.lower() or "approval" in label.lower() or "pickup" in label.lower():
            items.append({
                "id": f"war-{label}",
                "title": f"{count} warranty claims",
                "detail": label,
                "tone": "warning",
            })
    jobs = state.get("jobs") or {}
    if jobs.get("overdue"):
        items.append({
            "id": "jobs-due",
            "title": f"{jobs.get('overdue')} vehicles overdue for service",
            "detail": f"{jobs.get('dueSoon') or 0} due soon, {jobs.get('booked') or 0} booked.",
            "tone": "warning",
        })
    if jobs.get("inProgress"):
        names = ", ".join(str(t.get("ticketId")) for t in (jobs.get("openTickets") or [])[:3])
        items.append({
            "id": "jobs-open",
            "title": f"{jobs.get('inProgress')} job still in progress",
            "detail": f"Ticket {names}." if names else "Open in Coulson.",
            "tone": "info",
        })
    return items


def public_view(state, service_login=None):
    state = deepcopy(state or empty_state())
    paint_advances(state["lines"], state.get("advances") or {})
    for line in state["lines"]:
        line["stageLabel"] = STAGE_LABEL.get(line.get("stage"), line.get("stage") or "")
    mails = sorted(state["mails"], key=lambda m: m.get("seq") or 0)
    return {
        "lines": state["lines"],
        "mails": mails,
        "advances": advance_rows(state),
        "advanceTotal": round(sum(row["amount"] for row in advance_rows(state)), 2),
        "warranty": state.get("warranty") or empty_state()["warranty"],
        "jobs": state.get("jobs") or empty_state()["jobs"],
        "today": build_today(state),
        "syncedAt": state.get("syncedAt") or "",
        "syncError": state.get("syncError") or "",
        "serviceLogin": service_login or {"configured": False, "username": ""},
    }


def snapshot_from_coulson(store_rows, stale_rows, claim_rows, claim_analytics, due_rows, complaint_rows, ticket_rows):
    """Turn Coulson list payloads into desk lines plus warranty and job counts."""
    lines = []
    for row in store_rows or []:
        if not isinstance(row, dict):
            continue
        if str(row.get("replenishment_trigger") or "") != "Order":
            continue
        code = str(row.get("part_code") or "").strip()
        if not code:
            continue
        try:
            suggested = float(row.get("final_dispatch_qty") or 0)
        except (TypeError, ValueError):
            suggested = 0
        over = suggested > 50
        lines.append(_line(
            "", code, str(row.get("part_name") or code).strip(),
            0 if over else max(1, int(round(suggested or 1))),
            "need",
            overCap=over,
            suggestedQty=suggested,
            source="coulson",
            note=("Coulson marks this Order, but the suggested quantity is not usable."
                  if over else "Coulson marks this Order."),
        ))
    for row in stale_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            outstanding = float(row.get("outstanding_qty") or 0)
        except (TypeError, ValueError):
            outstanding = 0
        if outstanding <= 0:
            continue
        code = str(row.get("part_code") or "").strip()
        request_no = str(row.get("request_public_id") or "").strip()
        if not code or not request_no:
            continue
        lines.append(_line(
            request_no, code, str(row.get("part_name") or code).strip(),
            outstanding, "asked",
            source="coulson",
            note=str(row.get("status_name") or "Open on Coulson."),
        ))
    warranty_rows = []
    amount = 0
    for row in claim_rows or []:
        if not isinstance(row, dict):
            continue
        try:
            claim_amount = float(row.get("claim_total_amount") or 0)
        except (TypeError, ValueError):
            claim_amount = 0
        amount += claim_amount
        warranty_rows.append({
            "claimNumber": row.get("claim_number"),
            "amount": round(claim_amount, 2),
            "status": row.get("claim_status") or "",
        })
    breakdown = []
    analytics = claim_analytics if isinstance(claim_analytics, dict) else {}
    raw_break = analytics.get("status_breakdown") or {}
    if isinstance(raw_break, dict):
        labels = {
            "Approval Required": "Waiting for the area service manager",
            "Approved": "Approved, challan not entered",
            "SPD Pickup Requested": "Pickup requested, received quantity still zero",
        }
        for key, label in labels.items():
            try:
                count = int(raw_break.get(key) or 0)
            except (TypeError, ValueError):
                count = 0
            breakdown.append({"label": label, "count": count})
    total = analytics.get("total_claims")
    try:
        total = int(total)
    except (TypeError, ValueError):
        total = len(warranty_rows)
    due = _count_due(due_rows)
    complaints = _count_complaints(complaint_rows)
    open_tickets = []
    in_progress = 0
    for row in ticket_rows or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("status") or "")
        if status in ("Resolved", "Cancelled", "Service Resolved"):
            continue
        in_progress += 1
        open_tickets.append({
            "ticketId": row.get("ticket_id"),
            "status": status,
            "type": row.get("service_ticket_type") or "",
            "partNotAvailable": bool(row.get("has_pna")),
        })
    return {
        "lines": lines,
        "warranty": {
            "total": total,
            "amount": round(amount, 2),
            "rows": warranty_rows,
            "breakdown": breakdown,
        },
        "jobs": {
            "openTickets": open_tickets[:8],
            "inProgress": in_progress,
            "overdue": due["Overdue"],
            "dueSoon": due["Due Soon"],
            "booked": due["Booked"],
            "completed": due["Completed"],
            "complaintsOpen": complaints["open"],
            "complaintsTotal": complaints["total"],
            "coverage": [],
        },
    }


def _count_due(rows):
    counts = {"Overdue": 0, "Due Soon": 0, "Booked": 0, "Completed": 0}
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        status = str(row.get("service_status") or "")
        if status in counts:
            counts[status] += 1
    return counts


def _count_complaints(rows):
    open_n = 0
    total = 0
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        total += 1
        status = str(row.get("status") or "")
        if status not in ("Closed", "Resolved"):
            open_n += 1
    return {"open": open_n, "total": total}


def merge_snapshot(state, snapshot):
    """Bring Coulson rows in without wiping a part the desk has already moved."""
    state = deepcopy(state)
    kept_stages = ("short", "reorder", "paid", "onpi", "transit", "received")
    existing = {(line.get("requestNo") or "", line.get("code") or ""): line for line in state["lines"]}
    merged = []
    seen = set()
    for snap in snapshot.get("lines") or []:
        key = (snap.get("requestNo") or "", snap.get("code") or "")
        seen.add(key)
        old = existing.get(key)
        if old and old.get("stage") in kept_stages:
            old = dict(old)
            old["part"] = snap.get("part") or old.get("part")
            if snap.get("qty") and old.get("stage") == "asked":
                old["qty"] = snap.get("qty")
            merged.append(old)
        elif old:
            snap = dict(snap)
            snap["id"] = old.get("id") or snap.get("id")
            merged.append(snap)
        else:
            merged.append(snap)
    for line in state["lines"]:
        key = (line.get("requestNo") or "", line.get("code") or "")
        if key not in seen and line.get("source") == "mail":
            merged.append(line)
    state["lines"] = merged
    state["warranty"] = snapshot.get("warranty") or state.get("warranty")
    state["jobs"] = snapshot.get("jobs") or state.get("jobs")
    paint_advances(state["lines"], state.get("advances") or {})
    return state


def sample_state():
    """This morning's Jaipur workshop, with a sample mail thread on ticket 10412.

    Request numbers, part names, and the open counts are from Service Coulson.
    The mail wording and the rupee amounts are a sample so the desk can be tried
    before the mailbox is connected.
    """
    state = empty_state()
    state["lines"] = [
        _line("10412", "CD4C001800", "WH AC charging gun", 10, "paid",
              pi="PI/EL/26/4418", source="sample",
              note="The ask, the PI, and the payment are already joined to ticket 10412. The dispatch mail is still unread."),
        _line("10526", "AAS20004", "Lined shoe kit", 2, "short", source="sample",
              note="The dispatch mail kept this line back. The advance on ticket 10526 covers this line and the harness."),
        _line("10526", "AA28000800", "Front shock absorber bush", 5, "received", source="sample",
              note="The same dispatch mail said this line was sent. It is in the store."),
        _line("10526", "AN59000100", "Latch assembly, left door", 5, "received", source="sample",
              note="Sent in the same box as the bush."),
        _line("10526", "AH4C001200", "Charging gun harness", 2, "short", source="sample",
              note="Missing from the same box. It shares the advance with the shoe kit."),
        _line("", "AH47001300", "3.3 kW onboard charger", 1, "need", source="sample",
              note="Coulson marks this Order. There is no mail yet."),
        _line("", "AA5L000300", "Gearbox oil SAE80W90", 0, "need", source="sample",
              overCap=True, suggestedQty=123648,
              note="Coulson marks this Order, but the suggested quantity is not usable."),
    ]
    state["advances"] = {"10526": 4200}
    paint_advances(state["lines"], state["advances"])
    bodies = [
        ("ask", "Sent by the workshop", "Day 1", "joined", True,
         "Ticket 10412 — please raise a proforma invoice",
         "Please raise a proforma invoice for ticket 10412.\nPart CD4C001800, WH AC charging gun, quantity 10.",
         "This mail starts the thread. Later replies that say ticket 10412 join the same request."),
        ("pi", "Received from the company", "Day 2", "joined", True,
         "Re: Ticket 10412 — please raise a proforma invoice",
         "Proforma invoice PI/EL/26/4418 is attached.\nCD4C001800, WH AC charging gun — 10 nos — ₹18,400.\nPlease pay in full and reply on this mail.",
         "Wrote PI/EL/26/4418 and ₹18,400 onto ticket 10412."),
        ("utr", "Sent by the workshop", "Day 3", "joined", True,
         "Re: Ticket 10412 — payment done",
         "Payment done for PI/EL/26/4418.\nUTR HDFC26110412.\nAmount ₹18,400.",
         "Marked ticket 10412 paid. Waiting for the dispatch mail."),
        ("dispatch", "Received from the company", "Unread", "unread", False,
         "Re: Ticket 10412 — dispatch update",
         "Dispatch update for ticket 10412.\nThe following items are not dispatched, as they are not available:\nCD4C001800, WH AC charging gun — 10 nos.\nPayment was received in full.\n₹18,400 is parked as advance.",
         ""),
        ("split", "Received from the company", "Already read", "joined", True,
         "Re: Ticket 10526 — dispatch",
         "Ticket 10526.\nDispatched: AA28000800 front shock absorber bush, 5 nos.\nDispatched: AN59000100 latch assembly, 5 nos.\nNot dispatched: AAS20004 lined shoe kit, 2 nos.\nNot dispatched: AH4C001200 charging gun harness, 2 nos.\nAdvance for the items not dispatched: ₹4,200.",
         "One mail, four parts. Two are in the store. Two are missing and share an advance of ₹4,200."),
        ("bank", "Received from the company", "Needs a person", "unmatched", True,
         "Bank account update",
         "Dear partner, please update the bank mandate form.\nThis mail does not mention a ticket number or a part code.",
         "No ticket number. It waits until a person files it onto a request."),
    ]
    mails = []
    for seq, (mid, direction, when, status, applied, subject, body, result) in enumerate(bodies, start=1):
        parsed = parse_mail(subject, body)
        mails.append({
            "id": mid,
            "seq": seq,
            "direction": direction,
            "when": when,
            "subject": subject,
            "body": body,
            "requestNo": parsed["request_nos"][0] if len(parsed["request_nos"]) == 1 else "",
            "status": status,
            "applied": applied,
            "kind": parsed["kind"],
            "finds": parsed["finds"],
            "result": result or parsed["preview"],
        })
    state["mails"] = mails
    state["warranty"] = {
        "total": 18,
        "amount": 147807.97,
        "rows": [
            {"claimNumber": 14315, "amount": 5337.82, "status": "SPD Pickup Requested", "part": "Front leaf spring, qty 2, received 0"},
            {"claimNumber": 15451, "amount": 5166.70, "status": "Approved", "part": "Challan not entered"},
        ],
        "breakdown": [
            {"label": "Waiting for the area service manager", "count": 2},
            {"label": "Approved, challan not entered", "count": 4},
            {"label": "Pickup requested, received quantity still zero", "count": 12},
        ],
    }
    state["jobs"] = {
        "openTickets": [{
            "ticketId": 279680,
            "status": "Service In Progress",
            "type": "Corrective Maintenance",
            "partNotAvailable": True,
        }],
        "inProgress": 1,
        "overdue": 35,
        "dueSoon": 25,
        "booked": 7,
        "completed": 119,
        "complaintsOpen": 61,
        "complaintsTotal": 64,
        "coverage": [
            {"label": "Out of warranty", "count": 320},
            {"label": "In warranty", "count": 235},
            {"label": "PDI warranty", "count": 71},
            {"label": "AMC", "count": 1},
            {"label": "Campaign", "count": 1},
        ],
    }
    state["syncedAt"] = ""
    state["syncError"] = ""
    return state
