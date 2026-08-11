"""Owner ensure-OEM-Extra-columns places trio before Dealer Earnings (total last)."""
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
        self.batch = []

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, spreadsheetId=None, fields=None, **kw):
        if fields and "sheetId" in str(fields):
            sheets = []
            for i, title in enumerate(self._values.tabs.keys()):
                sheets.append({"properties": {"sheetId": 1000 + i, "title": title}})
            return _Exec({"sheets": sheets})
        sheets = [{"properties": {"title": t}} for t in self._values.tabs.keys()]
        return _Exec({"sheets": sheets})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        title_by_gid = {1000 + i: t for i, t in enumerate(self._values.tabs.keys())}
        for req in body.get("requests") or []:
            self.batch.append(req)
            if req.get("addSheet"):
                title = req["addSheet"]["properties"]["title"]
                self.created.append(title)
                self._values.tabs.setdefault(title, [])
            elif req.get("insertDimension"):
                rng = req["insertDimension"]["range"]
                tab = title_by_gid.get(rng["sheetId"])
                if not tab:
                    continue
                start, end = rng["startIndex"], rng["endIndex"]
                n = end - start
                grid = self._values.tabs[tab]
                for row in grid:
                    for _ in range(n):
                        row.insert(start, "")
            elif req.get("moveDimension"):
                src = req["moveDimension"]["source"]
                dest = req["moveDimension"]["destinationIndex"]
                tab = title_by_gid.get(src["sheetId"])
                if not tab:
                    continue
                si, ei = src["startIndex"], src["endIndex"]
                grid = self._values.tabs[tab]
                for row in grid:
                    block = row[si:ei]
                    del row[si:ei]
                    # destinationIndex is based on coords BEFORE removal when moving right
                    d = dest
                    if dest > si:
                        d = dest - (ei - si)
                    for i, cell in enumerate(block):
                        row.insert(d + i, cell)
        return _Exec({})


def test_ensure_inserts_oem_before_dealer_earnings(monkeypatch):
    tabs = {
        "Lead Register": [
            ["Lead ID", "Customer Name", "Additional Discount", "Dealer Earnings"],
            ["LD1", "A", "0", "100"],
        ],
        "Dealer Earnings Register": [
            ["Lead ID", "TOTAL DEALER EARNINGS", "Claim Status"],
            ["LD1", "100", ""],
        ],
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
    # OEM Extra trio then Dealer Earnings last among them
    assert lead_hdr.index("OEM Extra Support Received") < lead_hdr.index("Dealer Earnings")
    assert lead_hdr.index("OEM Extra Support Retained") < lead_hdr.index("Dealer Earnings")
    assert lead_hdr.index("OEM Extra Support Retained") == lead_hdr.index("Dealer Earnings") - 1

    assert "OEM Extra Support Register" in tabs


def test_ensure_moves_dealer_earnings_after_existing_oem_cols(monkeypatch):
    """Live bug: Dealer Earnings was left of OEM Extra — move it to the right."""
    tabs = {
        "Lead Register": [[
            "Lead ID", "Dealer Earnings",
            "OEM Extra Support Received", "OEM Extra Support Passed To Customer",
            "OEM Extra Support Retained",
        ]],
        "Dealer Earnings Register": [[
            "Lead ID", "TOTAL DEALER EARNINGS",
            "OEM Extra Support Received", "OEM Extra Support Passed To Customer",
            "OEM Extra Support Retained",
        ]],
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
    lead_hdr = tabs["Lead Register"][0]
    assert lead_hdr[-1] == "Dealer Earnings"
    assert lead_hdr[-4:-1] == list(gsheets.OEM_EXTRA_CANONICAL_HEADERS)

    earn_hdr = tabs["Dealer Earnings Register"][0]
    assert earn_hdr.index("TOTAL DEALER EARNINGS") > earn_hdr.index("OEM Extra Support Retained")


def test_ensure_idempotent_when_order_correct(monkeypatch):
    trio = list(gsheets.OEM_EXTRA_CANONICAL_HEADERS)
    tabs = {
        "Lead Register": [["Lead ID", *trio, "Dealer Earnings"]],
        "Dealer Earnings Register": [["Lead ID", *trio, "TOTAL DEALER EARNINGS"]],
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
    assert not any("moveDimension" in r or "insertDimension" in r for r in svc.batch)
