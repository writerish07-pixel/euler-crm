"""One-page customer deal sheet PDF — print, sign, upload.

Customer-facing only: vehicle, list price, scheme passed to the customer,
amount payable, declaration, signature boxes. Extra margin / support required
stay off the page.
"""
from __future__ import annotations

from datetime import datetime, timezone

import commercial as ce

A4_W = 595.0
A4_H = 842.0
MARGIN = 48.0


def indian_rs(n):
    n = int(round(ce.num(n)))
    sign = "-" if n < 0 else ""
    digits = str(abs(n))
    if len(digits) <= 3:
        body = digits
    else:
        last = digits[-3:]
        rest = digits[:-3]
        chunks = []
        while rest:
            chunks.append(rest[-2:])
            rest = rest[:-2]
        body = ",".join(list(reversed(chunks)) + [last])
    return f"Rs {sign}{body}"


def _pdf_text(s):
    s = str(s or "").replace("₹", "Rs ").replace("—", "-").replace("–", "-")
    out = []
    for ch in s:
        o = ord(ch)
        if ch in "\\()":
            out.append("\\" + ch)
        elif o == 10 or o == 13:
            out.append(" ")
        elif 32 <= o <= 126:
            out.append(ch)
        else:
            out.append("?")
    return "".join(out)


class _Page:
    def __init__(self):
        self.ops = []

    def text(self, x, y_from_top, s, size=10, bold=False):
        y = A4_H - y_from_top
        font = "F2" if bold else "F1"
        self.ops.append(
            f"BT /{font} {size:.1f} Tf 1 0 0 1 {x:.2f} {y:.2f} Tm ({_pdf_text(s)}) Tj ET"
        )

    def line(self, x1, y1_from_top, x2, y2_from_top, width=0.6):
        y1 = A4_H - y1_from_top
        y2 = A4_H - y2_from_top
        self.ops.append(
            f"{width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S"
        )

    def rect(self, x, y_from_top, w, h, width=0.8):
        y = A4_H - y_from_top - h
        self.ops.append(f"{width:.2f} w {x:.2f} {y:.2f} {w:.2f} {h:.2f} re S")

    def stream(self):
        return "\n".join(self.ops).encode("latin-1", "replace")


def _pdf_bytes(page: _Page) -> bytes:
    content = page.stream()
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R /F2 6 0 R >> >> >>"
        ),
        b"<< /Length %d >>\nstream\n" % len(content) + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out.extend(f"{i} 0 obj\n".encode("ascii"))
        out.extend(obj)
        out.extend(b"\nendobj\n")
    xref = len(out)
    out.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode("ascii"))
    out.extend(
        (
            f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref}\n%%EOF\n"
        ).encode("ascii")
    )
    return bytes(out)


def _fmt_date(raw):
    s = str(raw or "").strip()[:10]
    if len(s) == 10 and s[4] == "-":
        try:
            d = datetime.strptime(s, "%Y-%m-%d")
            return d.strftime("%d %b %Y")
        except ValueError:
            return s
    return datetime.now(timezone.utc).strftime("%d %b %Y")


def _right(page, y, label, value, bold=False, size=10):
    page.text(MARGIN, y, label, size=size)
    page.text(A4_W - MARGIN - 120, y, value, size=size, bold=bold)


def build_deal_sheet_pdf(sheet: dict) -> bytes:
    """Render a customer deal sheet. `sheet` is the public payload from assemble()."""
    s = sheet or {}
    page = _Page()
    y = 52
    page.text(MARGIN, y, "EULER MOTORS", size=16, bold=True)
    page.text(A4_W - MARGIN - 160, y + 2, "Deal Sheet", size=14, bold=True)
    y += 18
    page.text(MARGIN, y, "Print, get the customer to sign, then upload this sheet.", size=9)
    y += 16
    page.line(MARGIN, y, A4_W - MARGIN, y, 1.2)
    y += 18

    page.text(MARGIN, y, f"Date: {_fmt_date(s.get('date'))}", size=10)
    ref = s.get("ref") or ""
    if ref:
        page.text(320, y, f"Ref: {ref}", size=10)
    y += 22

    page.text(MARGIN, y, "CUSTOMER", size=11, bold=True)
    y += 16
    page.text(MARGIN, y, f"Name: {s.get('customerName') or '—'}", size=10, bold=True)
    y += 14
    page.text(MARGIN, y, f"Mobile: {s.get('mobile') or '—'}", size=10)
    city = s.get("city") or ""
    if city:
        page.text(320, y, f"City: {city}", size=10)
    y += 14
    ctype = s.get("customerType") or "Individual"
    page.text(MARGIN, y, f"Type: {ctype}", size=10)
    if ctype == "B2B" and s.get("gstin"):
        page.text(320, y, f"GSTIN: {s.get('gstin')}", size=10)
    y += 20

    page.text(MARGIN, y, "VEHICLE", size=11, bold=True)
    y += 16
    units = s.get("units") or []
    if not units:
        units = [{"label": s.get("vehicle") or "—"}]
    for u in units:
        page.text(MARGIN, y, u.get("label") or "—", size=10)
        y += 13
        if y > 520:
            break
    y += 8

    page.text(MARGIN, y, "PRICE", size=11, bold=True)
    y += 16
    rows = s.get("lines") or []
    for row in rows:
        _right(page, y, row.get("label") or "", indian_rs(row.get("amount")),
               bold=bool(row.get("strong")), size=10 if not row.get("strong") else 11)
        y += 14
    y += 6
    page.line(MARGIN, y, A4_W - MARGIN, y, 1.0)
    y += 18
    page.text(MARGIN, y, "Amount payable (Cx Demand)", size=12, bold=True)
    page.text(A4_W - MARGIN - 120, y, indian_rs(s.get("cxDemand")), size=12, bold=True)
    y += 22

    page.text(MARGIN, y, "DECLARATION", size=11, bold=True)
    y += 16
    for line in (
        "I/we have understood the above price and agree to purchase the vehicle(s) on these terms.",
        "OEM scheme amounts listed as passed are included in the amount payable.",
        "This sheet is not a tax invoice. Booking is subject to KYC and dealership confirmation.",
    ):
        page.text(MARGIN, y, line, size=9)
        y += 13
    y += 10

    box_h = 70
    box_w = (A4_W - 2 * MARGIN - 16) / 2
    page.rect(MARGIN, y, box_w, box_h)
    page.text(MARGIN + 8, y + 14, "Customer signature", size=9, bold=True)
    page.text(MARGIN + 8, y + 32, "Name: ___________________________", size=9)
    page.text(MARGIN + 8, y + 48, "Date: ______________", size=9)
    page.rect(MARGIN + box_w + 16, y, box_w, box_h)
    page.text(MARGIN + box_w + 24, y + 14, "Executive", size=9, bold=True)
    exec_name = s.get("executive") or ""
    page.text(MARGIN + box_w + 24, y + 32,
              f"Name: {exec_name}" if exec_name else "Name: ___________________________", size=9)
    page.text(MARGIN + box_w + 24, y + 48, "Date: ______________", size=9)
    y += box_h + 18
    page.text(MARGIN, y, "Euler Motors dealership copy — attach the signed sheet in Euler CRM.", size=8)
    return _pdf_bytes(page)


def _vehicle_label(model, variant, sno=None):
    name = " ".join(x for x in (str(model or "").strip(), str(variant or "").strip()) if x) or "—"
    if sno:
        return f"Unit {sno}  {name}"
    return name


def _passed_offer_lines(deal):
    offers = deal.get("schemeOffers") or []
    flags = deal.get("schemePassOn") or {}
    breakup = deal.get("schemePassedBreakup") or {}
    lines = []
    for o in offers:
        key = o.get("key")
        yes = bool(flags.get(key))
        amt = ce.num(breakup.get(key) if key in breakup else (o.get("schemeAvailable") if yes else 0))
        if not yes and amt <= 0:
            continue
        label = o.get("label") or key or "OEM scheme"
        unit = o.get("unit")
        if unit:
            label = f"Unit {unit} {label}"
        lines.append({"label": f"OEM scheme passed — {label}", "amount": -abs(amt)})
    if not lines and ce.num(deal.get("schemePassed")) > 0:
        lines.append({"label": "OEM scheme passed", "amount": -abs(ce.num(deal.get("schemePassed")))})
    return lines


def assemble_deal_sheet(*, customer=None, deal=None, ref="", date="", executive=""):
    """Public payload + PDF bytes. Strips owner P&L."""
    customer = customer or {}
    deal = deal or {}
    units = []
    if deal.get("pack") and isinstance(deal.get("units"), list) and deal.get("units"):
        for i, u in enumerate(deal.get("units") or [], start=1):
            units.append({"label": _vehicle_label(u.get("model"), u.get("variant"), i)})
    else:
        units.append({"label": _vehicle_label(
            deal.get("model") or customer.get("interestedModel"),
            deal.get("variant") or customer.get("variant"),
        )})
    lines = [
        {"label": "Ex-showroom", "amount": deal.get("exShowroom")},
        {"label": "RTO", "amount": deal.get("rto")},
        {"label": "Insurance", "amount": deal.get("insurance")},
        {"label": "My total (Ex + RTO + Insurance)", "amount": deal.get("priceTotal"), "strong": True},
        {"label": "Transport", "amount": deal.get("transport") if deal.get("transport") is not None
         else deal.get("handlingCharges")},
    ]
    if ce.num(deal.get("otherCharges")) > 0:
        lines.append({"label": "Other charges", "amount": deal.get("otherCharges")})
    lines.append({"label": "TCS (1% after discount)", "amount": deal.get("tcs")})
    lines.append({"label": "Net to customer", "amount": deal.get("netToCx"), "strong": True})
    lines.extend(_passed_offer_lines(deal))
    extra = ce.num(deal.get("additionalDiscount"))
    if extra > 0:
        lines.append({"label": "Additional (Dealer) discount", "amount": -extra})
    payload = {
        "customerName": customer.get("customerName") or "",
        "mobile": customer.get("mobile") or "",
        "city": customer.get("city") or "",
        "customerType": customer.get("customerType") or "Individual",
        "gstin": customer.get("gstin") or "",
        "vehicle": _vehicle_label(
            deal.get("model") or customer.get("interestedModel"),
            deal.get("variant") or customer.get("variant"),
        ),
        "units": units,
        "lines": lines,
        "cxDemand": ce.round2(ce.num(deal.get("cxDemand") or customer.get("budget"))),
        "ref": ref or "",
        "date": date or customer.get("createdDate") or deal.get("asOf") or "",
        "executive": executive or customer.get("executive") or "",
    }
    return payload, build_deal_sheet_pdf(payload)


def filename_for(payload):
    name = "".join(ch if ch.isalnum() else "-" for ch in str((payload or {}).get("customerName") or "customer"))
    name = name.strip("-")[:24] or "customer"
    day = str((payload or {}).get("date") or "")[:10] or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"deal-sheet-{name}-{day}.pdf"
