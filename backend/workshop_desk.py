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

_TICKET_RE = re.compile(
    r"\b(?:ticket|request)(?:\s+(?:id|no\.?|number))?\s*[:#-]?\s*(\d{4,7})\b",
    re.I,
)
_PI_RE = re.compile(
    r"\b(PI/[A-Z0-9]+(?:/[A-Z0-9]+)+)\b"
    r"|\b(PI-\d{4,8})\b"
    r"|\b(PQIN\d{6,})\b"
    r"|\bInvoice[- ]([A-Z]{2,}\d{5,})\b"
    r"|\bPI\s*(?:No\.?|Number|#|:|-)\s*([A-Z0-9][A-Z0-9./-]{2,24})\b"
    r"|\bProforma(?:\s+Invoice)?\s*(?:No\.?|Number|#|:|-)\s*([A-Z0-9][A-Z0-9./-]{2,24})\b",
    re.I,
)
_DROP_LINE = re.compile(
    r"not dispatched|not available|not supplied|not sent|short dispatch|dropped|balance qty|pending qty",
    re.I,
)
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
        "proofs": [],
    }


SERVICE_AREAS = (
    ("today", "Today"),
    ("mail", "Mail"),
    ("buy", "Buy parts"),
    ("warranty", "Warranty"),
    ("jobs", "Jobs"),
    ("money", "Money"),
    ("payments", "Payment proof"),
)
OWNER_AREAS = ("users", "gmail")
_AREA_KEYS = {key for key, _label in SERVICE_AREAS}

# What a staff role is offered. The owner can untick any of these before saving.
PRESETS = {
    "executive": ["today", "buy", "jobs"],
    "team_lead": ["today", "mail", "buy", "warranty", "jobs"],
    "tl": ["today", "mail", "buy", "warranty", "jobs", "money", "payments"],
    "accounts": ["today", "money", "payments"],
    "asm": ["today", "jobs", "warranty"],
    "rm": ["today", "jobs", "warranty"],
    "sales_gm": ["today", "mail", "buy", "warranty", "jobs", "money", "payments"],
}


def preset_for_role(role):
    return list(PRESETS.get(str(role or "").strip().lower(), ["today"]))


def clean_areas(areas):
    cleaned = []
    for area in areas or []:
        key = str(area or "").strip()
        if key in _AREA_KEYS and key not in cleaned:
            cleaned.append(key)
    return cleaned


def resolve_access(user, grants):
    """Owner sees the whole service desk. Everyone else sees only a saved grant."""
    role = str((user or {}).get("role") or "").strip().lower()
    name = str((user or {}).get("name") or "").strip()
    if role == "owner":
        return {
            "owner": True,
            "areas": [key for key, _label in SERVICE_AREAS] + list(OWNER_AREAS),
            "staffId": "",
            "name": name or "Owner",
        }
    uid = str((user or {}).get("userId") or "")
    email = str((user or {}).get("email") or "").strip().lower()
    name_key = name.lower()
    hit = None
    for grant in grants or []:
        if uid and str(grant.get("userId") or "") == uid:
            hit = grant
            break
        if email and str(grant.get("email") or "").strip().lower() == email:
            hit = grant
            break
        if name_key and str(grant.get("name") or "").strip().lower() == name_key:
            hit = grant
            break
    if not hit:
        return {"owner": False, "areas": [], "staffId": "", "name": ""}
    return {
        "owner": False,
        "areas": clean_areas(hit.get("areas")),
        "staffId": str(hit.get("staffId") or ""),
        "name": str(hit.get("name") or ""),
    }


def people_row(staff, grant, users):
    email = str((staff or {}).get("email") or "").strip().lower()
    name = str((staff or {}).get("name") or "").strip()
    login = None
    for person in users or []:
        if email and str(person.get("email") or "").strip().lower() == email:
            login = person
            break
        if name and str(person.get("name") or "").strip().lower() == name.lower():
            login = person
            break
    role = str((staff or {}).get("role") or "executive")
    return {
        "staffId": (staff or {}).get("staffId") or "",
        "name": name,
        "role": role,
        "email": (staff or {}).get("email") or "",
        "preset": preset_for_role(role),
        "areas": clean_areas((grant or {}).get("areas")),
        "hasLogin": bool(login),
        "userId": (login or {}).get("userId") or "",
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


def find_pi(text):
    """A proforma invoice number, or a clear sign the invoice is in the mail."""
    raw = str(text or "")
    found = []
    for match in _PI_RE.finditer(raw):
        if match.group(1):
            found.append(match.group(1).upper())
            continue
        token = next(group for group in match.groups() if group)
        token = re.sub(r"\.(PDF|PNG|JPE?G|WEBP)$", "", token, flags=re.I).upper()
        lead = match.group(0).upper()
        if lead.startswith("PI") and not token.startswith("PI"):
            joiner = "-" if lead.startswith("PI-") else " "
            token = f"PI{joiner}{token}"
        found.append(token)
    if found:
        return next((item for item in found if "/" in item), found[0])
    for line in raw.splitlines():
        if not line.lower().startswith("attachment:"):
            continue
        name = line.split(":", 1)[1].strip()
        if re.search(r"payment|receipt|utr", name, re.I):
            continue
        if re.search(r"proforma|invoice|pqin\d|(^|[^A-Za-z])pi([^A-Za-z]|$)", name, re.I):
            numbered = re.search(r"((?:PI[-/]|PQIN)\d{4,}|PI[/A-Z0-9-]{3,})", name, re.I)
            return numbered.group(1).upper() if numbered else "PI attached"
    if re.search(r"\binvoice is attached\b", raw, re.I) and not re.search(
        r"please raise|waiting for|awaiting|yet to (receive|get)|not (yet )?attached",
        raw,
        re.I,
    ):
        return "PI attached"
    return ""


_JOB_LABEL = {
    "dispatch": "Dispatches the parts",
    "payment": "Pays the order",
    "pi": "Raises the PI",
    "short": "Reports what was left out",
    "ask_dispatch": "Chases dispatch",
    "ask_pi": "Chases the PI",
    "ask": "Writes on the request",
}
_DOING_JOBS = ("dispatch", "payment", "pi", "short")


def describe_sender(subject, body):
    """What this one mail shows its sender doing."""
    text = f"{subject or ''}\n{body or ''}"
    low = text.lower()
    jobs = []
    if re.search(r"not dispatched|not available|not supplied|not sent|short dispatch|dropped", low):
        jobs.append("short")
    if re.search(r"(?<!not )\b(dispatched|shipment completed|shipped)\b", low):
        jobs.append("dispatch")
    if _UTR_RE.search(text) or re.search(
        r"payment done|payment of order|order confirmation|amount to be paid|payment proof",
        low,
    ):
        jobs.append("payment")
    # A payment mail names the PI it is paying. That does not make the sender
    # the person who raises invoices.
    if "payment" not in jobs and (find_pi(text) or re.search(r"invoice is attached", low)):
        jobs.append("pi")
    if re.search(r"kindly raise a pi|please raise|raise a (?:proforma|pi)\b", low):
        jobs.append("ask_pi")
    if re.search(r"request for dispatch|pending spare|pending part|kindly dispatch", low):
        jobs.append("ask_dispatch")
    if not jobs and _TICKET_RE.search(text):
        jobs.append("ask")
    order = ("short", "dispatch", "payment", "pi", "ask_dispatch", "ask_pi", "ask")
    headline = next((job for job in order if job in jobs), "")
    return {"jobs": jobs, "job": headline}


def dropped_part_names(text, part_names):
    """Part names written in a 'not dispatched' section of a mail or a document."""
    wanted = []
    for name in part_names or []:
        cleaned = re.sub(r"\s+", " ", str(name or "").strip().lower())
        if len(cleaned) >= 4:
            wanted.append(cleaned)
    hits = []
    mode = None
    for line in str(text or "").splitlines():
        if _DROP_LINE.search(line):
            mode = "drop"
        elif re.search(r"\bdispatched\b", line, re.I):
            mode = "sent"
        if mode != "drop":
            continue
        flat = re.sub(r"\s+", " ", line.lower())
        for name in wanted:
            if name in flat and name not in hits:
                hits.append(name)
    return hits


def parse_mail(subject, body):
    """Read a mail the way the desk will read the service mailbox."""
    subject = str(subject or "").strip()
    body = str(body or "").strip()
    text = f"{subject}\n{body}".strip()
    request_nos = list(dict.fromkeys(_TICKET_RE.findall(text)))
    pi = find_pi(text)
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


def mail_reading(mail):
    """Body plus the text read from a PDF, a screenshot, or another file."""
    chunks = [str((mail or {}).get("body") or "")]
    for doc in (mail or {}).get("documents") or []:
        chunks.append(f"Attachment: {doc.get('name') or 'document'}")
        chunks.append(str(doc.get("text") or ""))
    return "\n".join(chunk for chunk in chunks if chunk).strip()


def _apply_to_request(state, request_no, parsed, source_text):
    """Move the parts on one request from a parsed trail. Mutates state."""
    lines = state["lines"]
    advances = dict(state.get("advances") or {})
    notes = []
    if parsed["pi"]:
        for line in lines:
            if line.get("requestNo") != request_no:
                continue
            if not line.get("pi"):
                line["pi"] = parsed["pi"]
            if line.get("stage") in ("need", "asked"):
                line["stage"] = "onpi"
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
    named = dropped_part_names(source_text, [
        line.get("part") for line in lines if line.get("requestNo") == request_no
    ])
    for line in lines:
        cleaned = re.sub(r"\s+", " ", str(line.get("part") or "").strip().lower())
        if line.get("requestNo") == request_no and cleaned in named:
            if line.get("stage") not in ("received", "reorder"):
                line["stage"] = "short"
                line["note"] = "The dispatch left this part out. It was on this request and was not sent."
            if parsed["pi"] and not line.get("pi"):
                line["pi"] = parsed["pi"]
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
    if named:
        notes.append("Parts named as not dispatched are on the dropped list.")
    paint_advances(lines, advances)
    state["advances"] = {k: v for k, v in advances.items() if _open_missing(lines, k)}
    paint_advances(lines, state["advances"])
    return notes


def apply_parsed(state, mail):
    """Join one mail onto its request and move the parts. Idempotent."""
    state = deepcopy(state)
    if mail.get("applied"):
        return state
    reading = mail_reading(mail)
    parsed = parse_mail(mail.get("subject"), reading)
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

    request_no = request_nos[0]
    notes = _apply_to_request(state, request_no, parsed, f"{mail.get('subject')}\n{reading}")
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


def record_payment(state, request_no, utr, amount, filename, file_id):
    """File a payment on one ticket and prepare the reply for that ticket's mail."""
    state = deepcopy(state)
    request_no = str(request_no or "").strip()
    utr = re.sub(r"\s+", "", str(utr or "")).upper()
    if not re.fullmatch(r"\d{4,7}", request_no):
        raise ValueError("Choose a ticket number.")
    if not re.fullmatch(r"[A-Z0-9]{6,}", utr):
        raise ValueError("Enter the payment reference from the bank.")
    lines = [line for line in state["lines"] if line.get("requestNo") == request_no]
    if not lines:
        raise ValueError("That ticket is not on the desk yet.")
    try:
        amount = round(float(amount), 2) if amount not in (None, "") else None
    except (TypeError, ValueError):
        amount = None
    for line in lines:
        if line.get("stage") in EARLY:
            line["stage"] = "paid"
        line["note"] = f"Payment proof {filename} filed here. UTR {utr}."
    thread = None
    for mail in reversed(state["mails"]):
        if mail.get("requestNo") == request_no and mail.get("gmailThreadId"):
            thread = mail
            break
    subject = f"Ticket {request_no} — payment done"
    if thread and thread.get("subject"):
        prior = str(thread["subject"]).strip()
        subject = prior if prior.lower().startswith("re:") else f"Re: {prior}"
    body_lines = [f"Payment done for ticket {request_no}.", f"UTR {utr}."]
    if amount:
        body_lines.append(f"Amount {inr(amount)}.")
    body_lines.append(f"Payment proof {filename} is attached.")
    seq = max([m.get("seq") or 0 for m in state["mails"]] or [0]) + 1
    mail_id = _new_id()
    mail = {
        "id": mail_id,
        "seq": seq,
        "direction": "Sent by the workshop",
        "when": "Just filed",
        "subject": subject,
        "body": "\n".join(body_lines),
        "requestNo": request_no,
        "status": "joined",
        "applied": True,
        "kind": "payment",
        "finds": [["Request number", request_no], ["Payment reference", utr]],
        "result": f"Payment proof filed on ticket {request_no}.",
        "posted": False,
        "fileId": file_id,
        "gmailThreadId": (thread or {}).get("gmailThreadId") or "",
        "replyTo": (thread or {}).get("replyTo") or "",
        "rfcMessageId": (thread or {}).get("rfcMessageId") or "",
    }
    state["mails"].append(mail)
    state.setdefault("proofs", []).append({
        "id": file_id,
        "requestNo": request_no,
        "utr": utr,
        "amount": amount,
        "filename": filename,
        "mailId": mail_id,
        "posted": False,
    })
    return state, mail_id


def mark_posted(state, mail_id, gmail_id=""):
    state = deepcopy(state)
    for mail in state["mails"]:
        if mail.get("id") == mail_id:
            mail["posted"] = True
            if gmail_id:
                mail["gmailId"] = gmail_id
            mail["result"] = f"Posted onto the mail for ticket {mail.get('requestNo')}."
    for proof in state.get("proofs") or []:
        if proof.get("mailId") == mail_id:
            proof["posted"] = True
    return state


def request_ids(state):
    """Request numbers on the desk. Ones still missing a PI come first."""
    missing, ready = [], []
    seen = set()
    by_request = {}
    for line in (state or {}).get("lines") or []:
        number = str(line.get("requestNo") or "").strip()
        if not re.fullmatch(r"\d{4,7}", number):
            continue
        by_request.setdefault(number, []).append(line)
    for number, rows in by_request.items():
        if number in seen:
            continue
        seen.add(number)
        if any(row.get("pi") for row in rows):
            ready.append(number)
        else:
            missing.append(number)
    return missing + ready


def request_has_pi(state, request_no):
    request_no = str(request_no or "").strip()
    if not request_no:
        return False
    return any(
        str(line.get("requestNo") or "") == request_no and line.get("pi")
        for line in (state or {}).get("lines") or []
    )


def text_has_request(text, request_no):
    return bool(re.search(rf"\b{re.escape(str(request_no or ''))}\b", str(text or "")))


def _same_address(left, right):
    return bool(left) and str(left).strip().lower() == str(right or "").strip().lower()


def _mail_people(mail):
    """Addresses on one saved mail, the sender first."""
    people = []
    email = str(mail.get("fromEmail") or mail.get("replyTo") or "").strip().lower()
    if email:
        people.append({"name": str(mail.get("fromName") or "").strip(), "email": email, "sent": True})
    for person in mail.get("toPeople") or []:
        addr = str((person or {}).get("email") or "").strip().lower()
        if not addr:
            continue
        people.append({
            "name": str((person or {}).get("name") or "").strip(),
            "email": addr,
            "sent": False,
        })
    return people


def remember_sender(mail, message, mailbox=""):
    """Keep who sent this mail, who it was sent to, and what the sender did."""
    email = str((message or {}).get("fromEmail") or (message or {}).get("replyTo") or "").strip().lower()
    name = str((message or {}).get("fromName") or "").strip()
    mail["fromEmail"] = email
    mail["fromName"] = name
    mail["toPeople"] = [
        {"name": str(person.get("name") or "").strip(), "email": str(person.get("email") or "").strip().lower()}
        for person in ((message or {}).get("toPeople") or [])
        if str((person or {}).get("email") or "").strip()
    ]
    sent_at = str((message or {}).get("sentAt") or "").strip()
    if sent_at.isdigit():
        mail["sentAt"] = int(sent_at)
        mail["when"] = _mail_when(int(sent_at))
    action = describe_sender(mail.get("subject"), mail_reading(mail) or mail.get("body"))
    mail["jobs"] = action["jobs"]
    mail["senderJob"] = action["job"]
    if mailbox and _same_address(email, mailbox):
        mail["direction"] = "Sent by the workshop"
        external = [person for person in mail["toPeople"] if not _same_address(person.get("email"), mailbox)]
        if external:
            mail["replyTo"] = external[0]["email"]
    elif email:
        mail["direction"] = "Received"
        mail["replyTo"] = email
    return mail


def _mail_when(sent_at):
    from datetime import datetime, timedelta, timezone
    moment = datetime.fromtimestamp(int(sent_at) / 1000, tz=timezone.utc) + timedelta(hours=5, minutes=30)
    return f"{moment.day} {moment.strftime('%b %Y')}"


def _jobs_of(mail):
    saved = mail.get("jobs")
    if isinstance(saved, list) and saved:
        return saved
    return describe_sender(mail.get("subject"), mail_reading(mail) or mail.get("body"))["jobs"]


def sender_book(state, mailbox=""):
    """What each address does, learned from the mail that address sent."""
    book = {}
    for mail in (state or {}).get("mails") or []:
        email = str(mail.get("fromEmail") or mail.get("replyTo") or "").strip().lower()
        if not email or "github.com" in email:
            continue
        row = book.setdefault(email, {
            "email": email,
            "name": "",
            "counts": {},
            "own": _same_address(email, mailbox),
        })
        name = str(mail.get("fromName") or "").strip()
        if name:
            row["name"] = name
        for job in _jobs_of(mail):
            row["counts"][job] = row["counts"].get(job, 0) + 1
    rows = []
    for row in book.values():
        counts = row["counts"]
        doing = [(job, counts.get(job, 0)) for job in _DOING_JOBS if counts.get(job, 0)]
        doing.sort(key=lambda item: (-item[1], _DOING_JOBS.index(item[0])))
        if row["own"]:
            does = "This mailbox"
        elif doing:
            lead = doing[0][1]
            chosen = [job for job, count in doing if count == lead]
            does = " and ".join(_JOB_LABEL[job][0].lower() + _JOB_LABEL[job][1:] for job in chosen)
            does = does[0].upper() + does[1:]
        else:
            chase = next((job for job in ("ask_dispatch", "ask_pi", "ask") if counts.get(job)), "")
            does = _JOB_LABEL.get(chase, "Writes on the request")
        rows.append({
            "email": row["email"],
            "name": row["name"] or row["email"],
            "does": does,
            "own": row["own"],
            "counts": counts,
        })
    rows.sort(key=lambda item: (item["own"], item["name"].lower()))
    return rows


def request_stage(parts):
    """The same stage the parts list shows for one request."""
    parts = list(parts or [])
    if not parts or not any(part.get("requestNo") for part in parts):
        return "need"
    if any(part.get("stage") in ("short", "reorder") for part in parts):
        return "short"
    if all(part.get("stage") == "received" for part in parts):
        return "received"
    if any(part.get("stage") == "transit" for part in parts):
        return "transit"
    if any(part.get("stage") == "paid" for part in parts):
        return "paid"
    if any(part.get("pi") or part.get("stage") == "onpi" for part in parts):
        return "onpi"
    return "asked"


def _request_mails(state, request_no):
    rows = []
    for mail in (state or {}).get("mails") or []:
        if str(mail.get("requestNo") or "") == request_no:
            rows.append(mail)
            continue
        if request_no and request_no in (parse_mail(mail.get("subject"), mail_reading(mail)).get("request_nos") or []):
            rows.append(mail)
    rows.sort(key=lambda mail: (int(mail.get("sentAt") or 0), int(mail.get("seq") or 0)))
    return rows


def _display_name(person, book_by_email):
    email = str((person or {}).get("email") or "").strip().lower()
    known = book_by_email.get(email) or {}
    return (person or {}).get("name") or known.get("name") or email


def request_holds(state, mailbox=""):
    """Who an open request is waiting on, from the people on its mail."""
    book = sender_book(state, mailbox)
    by_email = {row["email"]: row for row in book}
    grouped = {}
    for line in (state or {}).get("lines") or []:
        number = str(line.get("requestNo") or "").strip()
        if not re.fullmatch(r"\d{4,7}", number):
            continue
        grouped.setdefault(number, []).append(line)
    holds = []
    needed_for = {
        "asked": ("pi", "for the PI"),
        "onpi": ("payment", "to pay"),
        "paid": ("dispatch", "to dispatch"),
        "reorder": ("dispatch", "to send the dropped part"),
        "short": ("dispatch", "to send the dropped part"),
    }
    for request_no, parts in grouped.items():
        stage = request_stage(parts)
        mails = _request_mails(state, request_no)
        if stage == "transit":
            sender = _last_actor(mails, "dispatch", mailbox)
            if not sender:
                continue
            name = _display_name(sender, by_email)
            holds.append({
                "requestNo": request_no,
                "stage": stage,
                "waiting": False,
                "email": sender.get("email") or "",
                "name": name,
                "label": f"Sent by {name}",
            })
            continue
        if stage not in needed_for:
            continue
        job, phrase = needed_for[stage]
        person = _person_holding(mails, job, by_email, mailbox)
        if not person:
            continue
        name = _display_name(person, by_email)
        known = by_email.get(person.get("email") or "") or {}
        does = known.get("does") or ""
        why = f"Waiting on {name} {phrase}."
        if does and not known.get("own"):
            why = f"{why} {does}."
        holds.append({
            "requestNo": request_no,
            "stage": stage,
            "waiting": True,
            "email": person.get("email") or "",
            "name": name,
            "label": f"Waiting on {name}",
            "why": why,
        })
    return holds


def _last_actor(mails, job, mailbox):
    found = None
    for mail in mails:
        email = str(mail.get("fromEmail") or mail.get("replyTo") or "").strip().lower()
        if not email or _same_address(email, mailbox):
            continue
        if job in _jobs_of(mail):
            found = {"name": str(mail.get("fromName") or "").strip(), "email": email}
    return found


def _person_holding(mails, job, book_by_email, mailbox):
    """The address the open step is sitting with.

    A chase mail names that person in To. Otherwise it is the address that
    usually does this job. The workshop mailbox itself is never the delay.
    """
    chase = {"pi": "ask_pi", "dispatch": "ask_dispatch"}.get(job)
    asked = []
    did = set()
    for mail in mails:
        email = str(mail.get("fromEmail") or mail.get("replyTo") or "").strip().lower()
        jobs = _jobs_of(mail)
        if email and not _same_address(email, mailbox) and job in jobs:
            did.add(email)
        if chase and chase in jobs:
            for person in _mail_people(mail):
                if person.get("sent") or _same_address(person.get("email"), mailbox):
                    continue
                asked.append(person)
    for person in reversed(asked):
        if person.get("email") not in did:
            return person
    best = None
    best_count = 0
    for row in book_by_email.values():
        count = (row.get("counts") or {}).get(job) or 0
        if row.get("own") or not count or row["email"] in did:
            continue
        on_request = any(
            person.get("email") == row["email"]
            for mail in mails
            for person in _mail_people(mail)
        )
        if asked and not on_request:
            continue
        if count > best_count:
            best = row
            best_count = count
    if best:
        return {"name": best.get("name") or "", "email": best["email"]}
    for mail in reversed(mails):
        email = str(mail.get("fromEmail") or mail.get("replyTo") or "").strip().lower()
        if email and not _same_address(email, mailbox) and email not in did:
            return {"name": str(mail.get("fromName") or "").strip(), "email": email}
    return None


def delay_groups(holds):
    """One Today line per person who is holding requests up."""
    grouped = {}
    for hold in holds or []:
        if not hold.get("waiting"):
            continue
        key = hold.get("email") or hold.get("name") or ""
        if not key:
            continue
        bucket = grouped.setdefault(key, {"name": hold.get("name") or key, "requests": [], "why": hold.get("why") or ""})
        bucket["requests"].append(hold.get("requestNo"))
    items = []
    for key, bucket in grouped.items():
        count = len(bucket["requests"])
        noun = "request" if count == 1 else "requests"
        items.append({
            "id": f"delay-{key}",
            "title": f"{count} {noun} waiting on {bucket['name']}",
            "detail": f"{', '.join(bucket['requests'])}. {bucket['why']}",
            "tone": "warning",
        })
    items.sort(key=lambda item: item["title"])
    return items


def request_mail(subject, body, sender=""):
    """A mailbox message belongs on the desk only when it names one request.

    Bank alerts, GitHub notices, and other inbox mail do not. The sender is
    ignored except to drop GitHub, which can mention a pull request number.
    """
    sender = str(sender or "").lower()
    if "github.com" in sender:
        return ""
    return request_for_mail("", f"{subject or ''}\n{body or ''}")


def request_for_mail(target, text):
    """The one request a mail belongs to.

    A search for 11880 may claim a payment mail that only carries that number.
    A mail that names two request numbers stays unmatched, so it is not filed
    onto either request and the other request can still read its own mail.
    """
    nos = list(dict.fromkeys(_TICKET_RE.findall(str(text or ""))))
    if len(nos) > 1:
        return ""
    if len(nos) == 1:
        return nos[0]
    target = str(target or "").strip()
    if target and text_has_request(text, target):
        return target
    return ""


def apply_request_trail(state, request_no):
    """Read every saved mail and document for one request and update its parts.

    A PI in a later reply, a PDF, or a screenshot moves the request off
    'Asked, no PI yet'. Parts the dispatch left out become the dropped list.
    """
    state = deepcopy(state)
    request_no = str(request_no or "").strip()
    if not request_no:
        return state
    chunks = []
    for mail in state.get("mails") or []:
        reading = mail_reading(mail)
        parsed_one = parse_mail(mail.get("subject"), reading)
        nos = parsed_one["request_nos"]
        if len(nos) > 1:
            continue
        if mail.get("requestNo") == request_no or nos == [request_no]:
            chunks.append(f"{mail.get('subject') or ''}\n{reading}")
    text = "\n".join(chunks).strip()
    if not text:
        return state
    parsed = parse_mail(f"Ticket {request_no}", text)
    if parsed["request_nos"] and set(parsed["request_nos"]) != {request_no}:
        return state
    _apply_to_request(state, request_no, parsed, text)
    return state


def drop_unmatched_gmail(state):
    """Remove mail the mailbox pull saved when it does not name one request.

    A mail a person pasted has no gmail id and stays, even with no request.
    """
    state = deepcopy(state)
    kept = []
    dropped = 0
    for mail in state.get("mails") or []:
        if mail.get("gmailId") and not mail.get("requestNo") and not request_mail(mail.get("subject"), mail.get("body")):
            dropped += 1
            continue
        kept.append(mail)
    state["mails"] = kept
    return state, dropped


def add_mail(state, subject, body, direction="Received from the company", meta=None):
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
        "posted": False,
    }
    for key in ("gmailId", "gmailThreadId", "replyTo", "rfcMessageId"):
        if (meta or {}).get(key):
            mail[key] = meta[key]
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


def _today_visible(item, areas):
    if item.get("mailId"):
        return "mail" in areas
    if item.get("lineId"):
        return "buy" in areas
    item_id = str(item.get("id") or "")
    if item_id.startswith("war"):
        return "warranty" in areas
    if item_id.startswith("jobs"):
        return "jobs" in areas
    return "today" in areas


def request_senders_known(state, request_no):
    """True once every pulled mail for this request records who sent it."""
    rows = [
        mail for mail in (state or {}).get("mails") or []
        if str(mail.get("requestNo") or "") == str(request_no or "") and mail.get("gmailId")
    ]
    return bool(rows) and all(mail.get("fromEmail") for mail in rows)


def public_view(state, service_login=None, access=None, gmail=None, mailbox=""):
    state = deepcopy(state or empty_state())
    paint_advances(state["lines"], state.get("advances") or {})
    for line in state["lines"]:
        line["stageLabel"] = STAGE_LABEL.get(line.get("stage"), line.get("stage") or "")
    mails = sorted(state["mails"], key=lambda m: m.get("seq") or 0)
    mailbox = mailbox or (gmail or {}).get("email") or ""
    holds = request_holds(state, mailbox)
    view = {
        "lines": state["lines"],
        "mails": mails,
        "advances": advance_rows(state),
        "advanceTotal": round(sum(row["amount"] for row in advance_rows(state)), 2),
        "warranty": state.get("warranty") or empty_state()["warranty"],
        "jobs": state.get("jobs") or empty_state()["jobs"],
        "today": build_today(state),
        "proofs": list(state.get("proofs") or []),
        "syncedAt": state.get("syncedAt") or "",
        "syncError": state.get("syncError") or "",
        "serviceLogin": service_login or {"configured": False, "username": ""},
        "access": access or {"owner": False, "areas": []},
        "gmail": gmail or {"connected": False, "email": ""},
        "senders": sender_book(state, mailbox),
        "holds": holds,
    }
    view["today"] = delay_groups(holds) + view["today"]
    if not access or access.get("owner"):
        return view
    areas = set(access.get("areas") or [])
    if "mail" not in areas:
        view["mails"] = []
    if "buy" not in areas and "payments" not in areas:
        view["lines"] = []
        view["holds"] = []
    if "mail" not in areas:
        view["senders"] = []
    if "money" not in areas and "payments" not in areas:
        view["advances"] = []
        view["advanceTotal"] = 0
    if "payments" not in areas:
        view["proofs"] = []
    if "warranty" not in areas:
        view["warranty"] = empty_state()["warranty"]
    if "jobs" not in areas:
        view["jobs"] = empty_state()["jobs"]
    if "today" not in areas:
        view["today"] = []
    else:
        view["today"] = [item for item in view["today"] if _today_visible(item, areas)]
    view["serviceLogin"] = {
        "configured": bool((view.get("serviceLogin") or {}).get("configured")),
        "username": "",
    }
    return view


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
