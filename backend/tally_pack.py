"""Tally pack checker — one lead, on demand, flags only.

Accounts uploads a ZIP (or single PDF) on tally_invoice (one GST invoice per
unit on a pack) and optionally tally_ledger (separate or combined). This
module reads invoice / ledger / receipt / journal pages and compares them to
the CRM billing summary and payment list. It never writes Tally and never
changes Price Structure or payments.
"""
from __future__ import annotations

import io
import re
import zipfile
from datetime import datetime, timezone

import commercial as ce
import lead_docs

MAX_PACK_FILES = 30
AMOUNT_TOL = 1.00
INVOICE_NO_RE = re.compile(r"\b(AF-[\w/-]+|INV[-/]\w+)\b", re.I)
INR_RE = re.compile(
    r"(?:₹|INR|ī|`)?\s*\(?-?\)?\s*([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{2})"
)


def _now():
    return datetime.now(timezone.utc).isoformat()


def parse_inr(raw) -> float:
    s = str(raw or "")
    s = s.replace(",", "").replace("₹", "").replace("ī", "").replace("INR", "")
    s = re.sub(r"[^\d.\-]", "", s)
    if not s or s in (".", "-", "-."):
        return 0.0
    try:
        return ce.round2(float(s))
    except ValueError:
        return 0.0


def amounts_in(text: str) -> list:
    return [parse_inr(m.group(1)) for m in INR_RE.finditer(text or "")]


def _norm_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def names_match(a: str, b: str) -> bool:
    ta = [t for t in _norm_name(a).split() if len(t) > 1 and t not in ("s", "o", "so", "w", "d")]
    tb = [t for t in _norm_name(b).split() if len(t) > 1 and t not in ("s", "o", "so", "w", "d")]
    if not ta or not tb:
        return False
    if ta[0] == tb[0] and (len(ta) == 1 or len(tb) == 1 or ta[1] == tb[1]):
        return True
    return len(set(ta[:3]) & set(tb[:3])) >= 2


def _norm_chassis(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or "")).upper()


def chassis_in(text: str) -> str:
    blob = re.sub(r"[\s\-]+", "", text or "")
    hit = re.search(r"(MD9[A-Z0-9]{14})", blob, re.I)
    return (hit.group(1) if hit else "").upper()


def classify_text(text: str, filename: str = "") -> str:
    t = (text or "").upper()
    fn = (filename or "").upper()
    if "LEDGER ACCOUNT" in t or "LEDGER" in fn:
        return "ledger"
    if "TAX INVOICE" in t or "EULER SALES" in t:
        return "invoice"
    if "JOURNAL" in t and "INSURANCE" in t:
        return "journal_insurance"
    if "JOURNAL" in t and "RTO" in t:
        return "journal_rto"
    if "RECEIPT" in t and "VOUCHER" in t:
        return "receipt"
    if fn.endswith(".PDF") and "RECEIPT" in fn:
        return "receipt"
    return "unknown"


def extract_pdf_text(data: bytes) -> str:
    if not data:
        return ""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)
    except Exception:
        return ""


def unpack(data: bytes, filename: str = "", content_type: str = "") -> list:
    """Return [{filename, text, kind}] from a ZIP or a single PDF."""
    name = (filename or "").lower()
    ctype = (content_type or "").lower()
    if not data:
        return []
    if name.endswith(".zip") or ctype.startswith("application/zip") or data[:2] == b"PK":
        return _unpack_zip(data)
    text = extract_pdf_text(data)
    return [{"filename": filename or "tally.pdf", "text": text,
             "kind": classify_text(text, filename)}]


def _unpack_zip(data: bytes) -> list:
    out = []
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise ValueError("That file is not a readable ZIP.") from exc
    names = [n for n in zf.namelist() if n and not n.endswith("/")]
    if len(names) > MAX_PACK_FILES:
        raise ValueError(f"ZIP has more than {MAX_PACK_FILES} files.")
    for raw_name in names:
        if ".." in raw_name.replace("\\", "/").split("/"):
            continue
        info = zf.getinfo(raw_name)
        if info.file_size > lead_docs.ZIP_MAX_BYTES:
            continue
        blob = zf.read(raw_name)
        base = raw_name.rsplit("/", 1)[-1]
        low = base.lower()
        if low.endswith(".pdf"):
            text = extract_pdf_text(blob)
        elif low.endswith(".txt"):
            text = blob.decode("utf-8", "ignore")
        else:
            text = ""
        out.append({"filename": base, "text": text, "kind": classify_text(text, base)})
    return out


def parse_invoice(text: str) -> dict:
    ad = 0.0
    m = re.search(
        r"(?:A\.D\.|Less\s*:\s*-?\s*A\.D\.)[^\d]{0,16}([0-9]{1,3}(?:,[0-9]{2,3})+(?:\.[0-9]{1,2})?|[0-9]+\.[0-9]{2})",
        text or "", re.I)
    if m:
        ad = parse_inr(m.group(1))
    cgst = _first_after(text, r"CGST")
    sgst = _first_after(text, r"SGST")
    total = 0.0
    for m in re.finditer(r"Total[^\n]{0,60}", text or "", re.I):
        chunk = m.group(0)
        found = amounts_in(chunk)
        if not found:
            continue
        if "NOS" in chunk.upper() or "₹" in chunk or "ī" in chunk or "INR" in chunk.upper():
            total = max(found)
            break
        total = max(total, max(found))
    if not total:
        found = amounts_in(text or "")
        total = max(found) if found else 0.0
    inv = ""
    im = INVOICE_NO_RE.search(text or "")
    if im:
        inv = im.group(1)
    return {
        "invoiceNumber": inv,
        "additionalDiscount": ad,
        "cgst": cgst,
        "sgst": sgst,
        "total": total,
        "chassis": chassis_in(text or ""),
        "customerName": _buyer_name(text or ""),
    }


def parse_receipt(text: str) -> dict:
    found = amounts_in(text or "")
    amt = max(found) if found else 0.0
    vch = ""
    m = re.search(r"\b(CR/[A-Z0-9/-]+)\b", text or "", re.I)
    if m:
        vch = m.group(1)
    return {"amount": amt, "voucherNo": vch, "text": text or ""}


def parse_ledger(text: str) -> dict:
    sales = 0.0
    insurance = 0.0
    rto = 0.0
    receipts = []
    for line in (text or "").splitlines():
        u = line.upper()
        amts = amounts_in(line)
        if not amts:
            continue
        amt = amts[-1]
        if "SALES" in u or "EULER SALES" in u:
            sales = max(sales, amt)
        elif "INSURANCE" in u:
            insurance = max(insurance, amt)
        elif re.search(r"\bRTO\b", u):
            rto = max(rto, amt)
        elif "RECEIPT" in u or "CENTRAL BANK" in u or "CBI" in u:
            receipts.append(amt)
    return {"sales": sales, "insurance": insurance, "rto": rto, "receipts": receipts}


def parse_journal(text: str) -> float:
    found = amounts_in(text or "")
    return max(found) if found else 0.0


def _first_after(text: str, label: str) -> float:
    m = re.search(label + r"[^\n]{0,40}", text or "", re.I)
    if not m:
        return 0.0
    found = amounts_in(m.group(0))
    return found[0] if found else 0.0


def _buyer_name(text: str) -> str:
    m = re.search(
        r"(?:Buyer \(Bill to\)|Consignee \(Ship to\)|Ledger Account)\s*\n\s*([A-Z][A-Za-z .'/]+)",
        text or "", re.I)
    if m:
        return m.group(1).strip()
    return ""


def _flag(code, message, severity="error") -> dict:
    return {"code": code, "message": message, "severity": severity}


def _off(summary, code) -> float:
    for ln in (summary or {}).get("offTallyLines") or []:
        if (ln.get("code") or "") == code:
            return ce.round2(ce.num(ln.get("amount")))
    return 0.0


def _payment_snos(pay) -> set:
    snos = set()
    for x in list((pay or {}).get("unitSnos") or []):
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n >= 1:
            snos.add(n)
    try:
        one = int((pay or {}).get("unitSno") or 0)
    except (TypeError, ValueError):
        one = 0
    if one >= 1:
        snos.add(one)
    return snos


def payments_for_snos(payments, snos) -> list:
    want = {int(n) for n in (snos or []) if int(n) >= 1}
    out = []
    for p in payments or []:
        if str(p.get("entryType") or "").lower() == "refund":
            continue
        amt = ce.round2(ce.num(p.get("amount")))
        if amt <= 0.01:
            continue
        have = _payment_snos(p)
        if not want or not have or have & want:
            out.append(amt)
    return out


def expected_from_summary(summary, lead, payments, *, snos=None) -> dict:
    t = (summary or {}).get("totals") or {}
    unit_rows = list((summary or {}).get("units") or [])
    want = [int(n) for n in (snos or []) if int(n) >= 1]
    if want and unit_rows:
        rows = [u for u in unit_rows if int(u.get("sno") or 0) in set(want)]
        tally = ce.round2(sum(ce.num(u.get("tallyBillTotal")) for u in rows))
        discount = ce.round2(sum(ce.num(u.get("additionalDiscount")) for u in rows))
        rto = ce.round2(sum(_off(u, "rto") for u in rows))
        insurance = ce.round2(sum(_off(u, "insurance") for u in rows))
        payable = ce.round2(sum(ce.num(u.get("customerPayable") or u.get("customerCollectTotal"))
                                for u in rows))
        first = rows[0] if rows else {}
        chassis = first.get("chassisNumber") or "" if len(rows) == 1 else ""
        invoice_number = first.get("invoiceNumber") or "" if len(rows) == 1 else ""
        cgst = ce.round2(sum(ce.num(u.get("cgst")) for u in rows))
        sgst = ce.round2(sum(ce.num(u.get("sgst")) for u in rows))
        return {
            "tallyTotal": tally,
            "discount": discount,
            "cgst": cgst,
            "sgst": sgst,
            "rto": rto,
            "insurance": insurance,
            "payable": payable,
            "customerName": (lead.get("customerName") or ""),
            "chassis": chassis,
            "invoiceNumber": invoice_number,
            "payments": payments_for_snos(payments, want),
            "unitSnos": want,
            "label": ("Unit " + str(want[0])) if len(want) == 1 else (
                "Units " + "+".join(str(n) for n in want)),
        }
    return {
        "tallyTotal": ce.round2(ce.num(t.get("tallyBillTotal"))),
        "discount": ce.round2(ce.num(t.get("additionalDiscount") or t.get("customerBenefitPassed")
                                     or lead.get("additionalDiscount"))),
        "cgst": ce.round2(ce.num(((summary or {}).get("gstReference") or {}).get("cgst"))),
        "sgst": ce.round2(ce.num(((summary or {}).get("gstReference") or {}).get("sgst"))),
        "rto": _off(summary, "rto") or ce.round2(ce.num(lead.get("rto"))),
        "insurance": _off(summary, "insurance") or ce.round2(ce.num(lead.get("insuranceAmount"))),
        "payable": ce.round2(ce.num(t.get("customerPayable") or lead.get("customerPayable"))),
        "customerName": (lead.get("customerName") or ""),
        "chassis": lead.get("chassisNumber") or "",
        "invoiceNumber": lead.get("invoiceNumber") or "",
        "payments": payments_for_snos(payments, want),
        "unitSnos": want,
        "label": "",
    }


def close(a, b) -> bool:
    return abs(ce.round2(ce.num(a)) - ce.round2(ce.num(b))) <= AMOUNT_TOL


def _prefix(expected: dict, message: str) -> str:
    label = (expected or {}).get("label") or ""
    return f"{label}: {message}" if label else message


def _file_snos(f) -> list:
    raw = (f or {}).get("unitSnos") or []
    snos = []
    for x in list(raw):
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n >= 1:
            snos.append(n)
    if snos:
        return sorted(set(snos))
    try:
        one = int((f or {}).get("unitSno") or 0)
    except (TypeError, ValueError):
        one = 0
    return [one] if one >= 1 else []


def _file_covers(f, sno: int) -> bool:
    have = _file_snos(f)
    if not have:
        return False
    return int(sno) in have


def compare(expected: dict, files: list, *, crm_docs: set, require_invoice: bool = True,
            require_ledger: bool = True) -> list:
    flags = []
    by = {}
    for f in files or []:
        by.setdefault(f.get("kind") or "unknown", []).append(f)

    invoices = [parse_invoice(f.get("text") or "") for f in by.get("invoice") or []]
    ledgers = [parse_ledger(f.get("text") or "") for f in by.get("ledger") or []]
    receipts = [parse_receipt(f.get("text") or "") for f in by.get("receipt") or []]
    ins_j = [parse_journal(f.get("text") or "") for f in by.get("journal_insurance") or []]
    rto_j = [parse_journal(f.get("text") or "") for f in by.get("journal_rto") or []]

    if require_invoice and not files:
        flags.append(_flag("pack", "Tally pack ZIP not uploaded"))
    elif require_invoice and not invoices:
        flags.append(_flag("invoice_missing", _prefix(expected, "Tax invoice PDF not found in the ZIP")))
    if require_ledger and files and not ledgers:
        flags.append(_flag("ledger_missing", _prefix(expected, "Customer ledger PDF not found"), "warn"))

    inv = invoices[0] if invoices else {}
    if inv and expected.get("tallyTotal") and not close(inv.get("total"), expected["tallyTotal"]):
        flags.append(_flag(
            "invoice_total",
            _prefix(expected, f"Invoice ₹{inv.get('total'):,.2f} vs Tally GST invoice ₹{expected['tallyTotal']:,.2f}"),
        ))
    if inv and expected.get("discount") and inv.get("additionalDiscount") and not close(
            inv.get("additionalDiscount"), expected["discount"]):
        flags.append(_flag(
            "invoice_ad",
            _prefix(expected, f"A.D. on invoice ₹{inv.get('additionalDiscount'):,.2f} vs deal discount ₹{expected['discount']:,.2f}"),
        ))
    if inv and expected.get("customerName") and inv.get("customerName"):
        if not names_match(inv["customerName"], expected["customerName"]):
            flags.append(_flag(
                "invoice_name",
                _prefix(expected, f"Invoice buyer '{inv['customerName']}' does not match {expected['customerName']}"),
            ))
    want_ch = _norm_chassis(expected.get("chassis") or "")
    got_ch = _norm_chassis(inv.get("chassis") or "")
    if want_ch and got_ch and want_ch != got_ch and not want_ch.endswith(got_ch[-6:]):
        flags.append(_flag("invoice_chassis", _prefix(expected, f"Invoice chassis {got_ch} vs file {want_ch}")))

    led = ledgers[0] if ledgers else {}
    if led and expected.get("tallyTotal") and led.get("sales") and not close(led["sales"], expected["tallyTotal"]):
        flags.append(_flag(
            "ledger_sales",
            _prefix(expected, f"Ledger Euler Sales ₹{led['sales']:,.2f} vs Tally invoice ₹{expected['tallyTotal']:,.2f}"),
        ))
    ins_amt = max(ins_j) if ins_j else led.get("insurance") or 0.0
    if expected.get("insurance") and ins_amt and not close(ins_amt, expected["insurance"]):
        flags.append(_flag(
            "journal_ins",
            _prefix(expected, f"Insurance journal ₹{ins_amt:,.2f} vs file ₹{expected['insurance']:,.2f}"),
        ))
    elif require_ledger and expected.get("insurance") and expected["insurance"] > 0.01 and not ins_amt:
        flags.append(_flag("journal_ins_missing", _prefix(expected, "JOURNAL - INSURANCE not found in the pack")))
    rto_amt = max(rto_j) if rto_j else led.get("rto") or 0.0
    if expected.get("rto") and rto_amt and not close(rto_amt, expected["rto"]):
        flags.append(_flag(
            "journal_rto",
            _prefix(expected, f"RTO journal ₹{rto_amt:,.2f} vs file ₹{expected['rto']:,.2f}"),
        ))
    elif require_ledger and expected.get("rto") and expected["rto"] > 0.01 and not rto_amt:
        flags.append(_flag("journal_rto_missing", _prefix(expected, "JOURNAL - RTO not found in the pack")))

    receipt_amts = [r["amount"] for r in receipts if r.get("amount")]
    if led.get("receipts"):
        receipt_amts.extend(led["receipts"])
    leftover = list(receipt_amts)
    for pay in expected.get("payments") or []:
        hit = next((i for i, a in enumerate(leftover) if close(a, pay)), None)
        if hit is None:
            flags.append(_flag("receipt_missing", _prefix(expected, f"Payment ₹{pay:,.2f} has no matching receipt in the ZIP")))
        else:
            leftover.pop(hit)

    if "kyc_aadhaar_front" not in crm_docs and "kyc_pan" not in crm_docs:
        # Full KYC list is produced by lead_docs; this is a pack-side reminder.
        pass
    return flags


def _match_invoice_to_unit(f, unit) -> bool:
    if _file_covers(f, int(unit.get("sno") or 0)):
        return True
    if _file_snos(f):
        return False
    want = _norm_chassis(unit.get("chassisNumber") or "")
    parsed = parse_invoice(f.get("text") or "")
    got = _norm_chassis(chassis_in(f.get("text") or "") or parsed.get("chassis") or "")
    if want and got and (want == got or want.endswith(got[-6:])):
        return True
    return False


def compare_pack(summary, lead, payments, files) -> list:
    """Per-unit GST invoices; ledger groups may club selected units or stay separate."""
    units = list((summary or {}).get("units") or [])
    if not units:
        return compare(expected_from_summary(summary, lead, payments), files, crm_docs=set())
    flags = []
    if not files:
        flags.append(_flag("pack", "Tally pack ZIP not uploaded"))
        return flags
    unit_scoped = any(_file_snos(f) for f in files)
    if not unit_scoped:
        expected = expected_from_summary(summary, lead, payments)
        flags.extend(compare(expected, files, crm_docs=set()))
        flags.append(_flag(
            "invoice_per_unit",
            "Re-upload one GST invoice per unit. Ledger can be combined (select units) or separate.",
            "warn",
        ))
        return flags

    all_snos = [int(u.get("sno") or i + 1) for i, u in enumerate(units)]
    for u in units:
        sno = int(u.get("sno") or 0)
        ufiles = [f for f in files if f.get("kind") == "invoice" and _match_invoice_to_unit(f, u)]
        expected = expected_from_summary(summary, lead, payments, snos=[sno])
        if not ufiles:
            flags.append(_flag("invoice_missing", f"Unit {sno}: Tax invoice not uploaded"))
            continue
        flags.extend(compare(expected, ufiles, crm_docs=set(), require_invoice=True, require_ledger=False))

    ledger_files = [f for f in files if f.get("kind") == "ledger"]
    groups = {}
    for f in ledger_files:
        key = tuple(_file_snos(f) or all_snos)
        groups.setdefault(key, []).append(f)
    covered = set()
    for key, gfiles in groups.items():
        covered.update(key)
        extra = [f for f in files if f.get("kind") in ("receipt", "journal_insurance", "journal_rto")
                 and (not _file_snos(f) or set(_file_snos(f)) & set(key))]
        expected = expected_from_summary(summary, lead, payments, snos=list(key))
        flags.extend(compare(expected, gfiles + extra, crm_docs=set(),
                             require_invoice=False, require_ledger=True))
    missing = [n for n in all_snos if n not in covered]
    if missing and not ledger_files:
        flags.append(_flag(
            "ledger_missing",
            "Customer ledger not uploaded. Combine selected units or post one ledger per unit.",
            "warn",
        ))
    elif missing:
        flags.append(_flag(
            "ledger_missing",
            "No Tally ledger for unit" + ("s " if len(missing) > 1 else " ")
            + ", ".join(str(n) for n in missing),
            "warn",
        ))
    return flags


def crm_doc_flags(lead, kinds: set) -> list:
    flags = []
    missing = []
    for kind in lead_docs.required_kyc_kinds(lead.get("customerType")):
        if kind not in kinds:
            missing.append((lead_docs.KINDS.get(kind) or {}).get("label") or kind)
    if missing:
        flags.append(_flag("kyc", "KYC missing: " + ", ".join(missing)))
    if lead_docs.DEAL_SHEET_KIND not in kinds:
        flags.append(_flag("deal_sheet", "Deal sheet not uploaded", "warn"))
    extra = lead.get("oemExtraSupportReceived")
    if lead_docs.extra_support_required(extra) and lead_docs.EXTRA_SUPPORT_KIND not in kinds:
        flags.append(_flag("oem_extra", "OEM Extra Support proof missing"))
    if "delivery_insurance" not in kinds:
        flags.append(_flag("ins_copy", "Insurance copy not uploaded", "warn"))
    if "delivery_rto" not in kinds:
        flags.append(_flag("rto_copy", "RTO / Registration copy not uploaded", "warn"))
    return flags


def run_check(*, lead, files, payments, summary, kinds) -> dict:
    expected = expected_from_summary(summary, lead, payments)
    flags = crm_doc_flags(lead, kinds)
    if (summary or {}).get("pack") and (summary or {}).get("units"):
        flags.extend(compare_pack(summary, lead, payments, files))
    else:
        flags.extend(compare(expected, files, crm_docs=kinds))
    found = {
        "files": [{"filename": f.get("filename"), "kind": f.get("kind")} for f in files or []],
        "invoiceCount": sum(1 for f in files or [] if f.get("kind") == "invoice"),
        "ledgerCount": sum(1 for f in files or [] if f.get("kind") == "ledger"),
        "receiptCount": sum(1 for f in files or [] if f.get("kind") == "receipt"),
    }
    errors = [f for f in flags if f.get("severity") != "warn"]
    return {
        "checkedAt": _now(),
        "ok": not errors,
        "flagCount": len(flags),
        "errorCount": len(errors),
        "flags": flags,
        "found": found,
        "expected": {
            "tallyTotal": expected.get("tallyTotal"),
            "payable": expected.get("payable"),
            "payments": expected.get("payments"),
        },
    }
