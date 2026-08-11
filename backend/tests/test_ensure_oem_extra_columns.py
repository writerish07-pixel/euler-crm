"""Owner ensure-OEM-Extra-columns appends headers / creates the register tab."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET_OEM_COLS")

import gsheets  # noqa: E402


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class FakeValues:
    def __init__(self, tabs):
        self.tabs = tabs
        self.updates = []

    @staticmethod
    def _parse(rng):
        tab = rng.split("!")[0].strip("'")
        return tab, rng.split("!")[1]

    @staticmethod
    def _col_to_idx(letters):
        n = 0
        for ch in letters:
            n = n * 26 + (ord(ch) - 64)
        return n - 1

    def get(self, spreadsheetId=None, range=None, valueRenderOption=None):
        tab, a1 = self._parse(range)
        grid = self.tabs[tab]
        if ":" in a1 and a1.replace(":", "").isdigit():
            lo, hi = (int(x) for x in a1.split(":"))
            out = [list(r) for r in grid[lo - 1:hi]]
        else:
            # single cell or row range like A1 or BS1:BU1
            start = a1.split(":")[0]
            row_n = int("".join(c for c in start if c.isdigit()) or "1")
            out = [list(grid[row_n - 1])] if row_n - 1 < len(grid) else [[]]
        return _Exec({"values": out})

    def update(self, spreadsheetId=None, range=None, body=None, valueInputOption=None, **kw):
        tab, a1 = self._parse(range)
        start = a1.split(":")[0]
        col = self._col_to_idx("".join(c for c in start if c.isalpha()))
        row_n = int("".join(c for c in start if c.isdigit()) or "1")
        vals = body["values"][0]
        grid = self.tabs.setdefault(tab, [])
        while len(grid) < row_n:
            grid.append([])
        row = grid[row_n - 1]
        while len(row) < col + len(vals):
            row.append("")
        for i, v in enumerate(vals):
            row[col + i] = v
        self.updates.append((tab, range, vals))
        return _Exec({})


class FakeService:
    def __init__(self, values):
        self._values = values
        self.created = []

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, spreadsheetId=None, fields=None, **kw):
        sheets = [{"properties": {"title": t}} for t in self._values.tabs.keys()]
        return _Exec({"sheets": sheets})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        for req in body.get("requests") or []:
            add = req.get("addSheet")
            if add:
                title = add["properties"]["title"]
                self.created.append(title)
                self._values.tabs.setdefault(title, [])
        return _Exec({})


def test_ensure_appends_lead_register_headers_and_creates_oem_tab(monkeypatch):
    tabs = {
        "Lead Register": [["Lead ID", "Customer Name", "Additional Discount", "Dealer Earnings"]],
        "Dealer Earnings Register": [
            ["Lead ID", "Customer Name", "Dealer Margin Net (Ex GST)"]
        ],
        # OEM Extra Support Register intentionally missing
    }
    values = FakeValues(tabs)
    svc = FakeService(values)
    monkeypatch.setattr(gsheets, "_service", svc)
    monkeypatch.setattr(gsheets, "_status", {"enabled": True, "canWrite": True})
    monkeypatch.setattr(gsheets, "_write_blocked", lambda: None)
    for name in ("_header_cache", "_headerrow_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})

    res = gsheets._ensure_oem_extra_support_columns_sync()
    assert res["ok"] is True
    assert res["changed"] is True

    lead_hdr = tabs["Lead Register"][0]
    assert "OEM Extra Support Received" in lead_hdr
    assert "OEM Extra Support Passed To Customer" in lead_hdr
    assert "OEM Extra Support Retained" in lead_hdr

    earn_hdr = tabs["Dealer Earnings Register"][0]
    assert "OEM Extra Support Received" in earn_hdr

    assert "OEM Extra Support Register" in tabs
    assert tabs["OEM Extra Support Register"][0][0] == "Lead ID"
    assert "OEM Extra Support Retained" in tabs["OEM Extra Support Register"][0]


def test_ensure_is_idempotent_when_headers_exist(monkeypatch):
    trio = list(gsheets.OEM_EXTRA_CANONICAL_HEADERS)
    tabs = {
        "Lead Register": [["Lead ID", *trio]],
        "Dealer Earnings Register": [["Lead ID", *trio]],
        "OEM Extra Support Register": [list(gsheets.OEM_EXTRA_REGISTER_COLS)],
    }
    values = FakeValues(tabs)
    svc = FakeService(values)
    monkeypatch.setattr(gsheets, "_service", svc)
    monkeypatch.setattr(gsheets, "_status", {"enabled": True})
    monkeypatch.setattr(gsheets, "_write_blocked", lambda: None)
    for name in ("_header_cache", "_headerrow_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})

    res = gsheets._ensure_oem_extra_support_columns_sync()
    assert res["ok"] is True
    assert res["changed"] is False
    assert values.updates == []
    assert svc.created == []
