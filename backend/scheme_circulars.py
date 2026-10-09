"""OEM scheme circular pictures keyed by calendar month (YYYY-MM).

The Scheme screen loads the circular for the unit's billed date (scheme as-of).
Last month does not carry forward — a month with no file shows no picture.
"""
from __future__ import annotations

CIRCULARS = {
    "2026-10": {
        "month": "2026-10",
        "ref": "EM/10-2026/003",
        "title": "October 2026 Retail Consumer Scheme",
        "dated": "2026-10-08",
        "imageUrl": "/scheme-circulars/2026-10.png",
        "pdfUrl": "/scheme-circulars/2026-10.pdf",
    },
}


def _ym(raw):
    s = str(raw or "").strip()
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    return ""


def for_date(raw):
    """Circular metadata for a billed / scheme as-of date. None if that month has no file."""
    ym = _ym(raw)
    hit = CIRCULARS.get(ym)
    return dict(hit) if hit else None


def all_circulars():
    return [dict(v) for _, v in sorted(CIRCULARS.items())]
