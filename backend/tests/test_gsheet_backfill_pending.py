"""Backfill must add waiting Lead Register columns the app now writes.

TCS / RSA / Insurance Arranged By / Final Exchange Value / Scheme As Of /
Deal Cancelled persist on the lead but were never in SYNC_MAP, and the live
Euler Master header row still does not have them. Sync skips missing headers,
so Backfill looked like it succeeded while those cells stayed blank — or the
per-row write quota timed out. These tests lock both fixes: append-only header
ensure (also run by Backfill) and batched upserts that land the new fields.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET_BACKFILL")

import gsheets  # noqa: E402
from live_headers import LIVE_HEADERS, PENDING_SHEET_COLUMNS  # noqa: E402


NEW_LEAD_FIELDS = [
    "rsaAmc", "tcs", "tcsBase", "tcsApplicable",
    "insuranceArrangedBy", "finalExchangeValue", "schemeAsOf", "dealCancelled",
]


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class FakeValues:
    def __init__(self, tabs):
        self.tabs = tabs
        self.calls = {"append": 0, "batchUpdate": 0, "get": 0, "update": 0}

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
        self.calls["get"] += 1
        tab, a1 = self._parse(range)
        grid = self.tabs[tab]
        start, end = (a1.split(":") + [a1])[:2]
        s_let = "".join(c for c in start if c.isalpha())
        e_let = "".join(c for c in end if c.isalpha())
        s_dig = "".join(c for c in start if c.isdigit())
        e_dig = "".join(c for c in end if c.isdigit())
        if not s_let and s_dig:
            lo, hi = int(s_dig), int(e_dig or s_dig)
            return _Exec({"values": [list(r) for r in grid[lo - 1:hi]]})
        s_col = self._col_to_idx(s_let) if s_let else 0
        e_col = self._col_to_idx(e_let) if e_let else s_col
        if not s_dig and not e_dig:
            out = [[r[s_col]] if s_col < len(r) else [] for r in grid]
            return _Exec({"values": out})
        start_row = int(s_dig or "1")
        end_row = int(e_dig) if e_dig else len(grid)
        out = []
        for row in grid[start_row - 1:end_row]:
            out.append([row[i] if i < len(row) else "" for i in range(s_col, e_col + 1)])
        return _Exec({"values": out})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        self.calls["append"] += 1
        tab, _ = self._parse(range)
        for row in body["values"]:
            grid = self.tabs[tab]
            width = max(len(grid[0]) if grid else 0, len(row))
            self.tabs[tab].append(list(row) + [""] * (width - len(row)))
        return _Exec({})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        self.calls["batchUpdate"] += 1
        for item in body["data"]:
            tab, a1 = self._parse(item["range"])
            col = self._col_to_idx("".join(c for c in a1 if c.isalpha()))
            row_n = int("".join(c for c in a1 if c.isdigit()))
            grid = self.tabs[tab]
            while len(grid) < row_n:
                grid.append([""] * (len(grid[0]) if grid else col + 1))
            row = grid[row_n - 1]
            while len(row) <= col:
                row.append("")
            row[col] = item["values"][0][0]
        return _Exec({})

    def update(self, spreadsheetId=None, range=None, body=None, valueInputOption=None, **kw):
        self.calls["update"] += 1
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
        return _Exec({})

    def clear(self, **kw):
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
            sheets = [{"properties": {"sheetId": 1000 + i, "title": t}}
                      for i, t in enumerate(self._values.tabs.keys())]
            return _Exec({"sheets": sheets})
        return _Exec({
            "properties": {"title": "Euler Master"},
            "sheets": [{"properties": {"title": t}} for t in self._values.tabs.keys()],
        })

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
                for row in self._values.tabs[tab]:
                    for _ in range(n):
                        row.insert(start, "")
            elif req.get("moveDimension"):
                src = req["moveDimension"]["source"]
                dest = req["moveDimension"]["destinationIndex"]
                tab = title_by_gid.get(src["sheetId"])
                if not tab:
                    continue
                si, ei = src["startIndex"], src["endIndex"]
                for row in self._values.tabs[tab]:
                    block = row[si:ei]
                    del row[si:ei]
                    d = dest - (ei - si) if dest > si else dest
                    for i, cell in enumerate(block):
                        row.insert(d + i, cell)
        return _Exec({})


def live_tabs():
    return {name: [list(headers)] for name, (_hr, headers) in LIVE_HEADERS.items()}


@pytest.fixture
def sheet(monkeypatch):
    tabs = live_tabs()
    values = FakeValues(tabs)
    svc = FakeService(values)
    monkeypatch.setattr(gsheets, "_service", svc)
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=True, canWrite=True))
    monkeypatch.setenv("GSHEET_ID", "FAKE_SHEET_BACKFILL")
    # Autouse conftest blocks live sheet writes; this fake never reaches Google.
    monkeypatch.setenv("GSHEET_ALLOW_TEST_WRITES", "1")
    for k in ("ENVIRONMENT", "PRODUCTION_GSHEET_ID"):
        monkeypatch.delenv(k, raising=False)
    for name in ("_header_cache", "_headerrow_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})
    return tabs, values


def test_sync_map_declares_the_new_lead_fields():
    fields = gsheets.SYNC_MAP["leads"][2]
    for f in NEW_LEAD_FIELDS:
        assert f in fields, f
        assert f in PENDING_SHEET_COLUMNS["leads"], f
    assert gsheets.LEAD_COMMERCIAL_HEADERS == [
        "RSA / AMC", "TCS", "TCS Applicable", "TCS Base",
        "Insurance Arranged By", "Final Exchange Value", "Scheme As Of",
        "Deal Cancelled",
    ]


def test_commercial_button_appends_headers_and_is_idempotent(sheet):
    tabs, values = sheet
    before = list(tabs["Lead Register"][0])
    res = gsheets._ensure_lead_commercial_columns_sync()
    assert res["ok"] is True and res["changed"] is True, res
    assert res["tabs"][0]["added"] == gsheets.LEAD_COMMERCIAL_HEADERS
    hdr = tabs["Lead Register"][0]
    assert hdr[:len(before)] == before, "existing headers were reordered or renamed"
    for h in gsheets.LEAD_COMMERCIAL_HEADERS:
        assert h in hdr
    writes = values.calls["update"]
    again = gsheets._ensure_lead_commercial_columns_sync()
    assert again["changed"] is False
    assert values.calls["update"] == writes


def test_appended_headers_resolve_the_new_sync_fields(sheet):
    tabs, _ = sheet
    gsheets._ensure_lead_commercial_columns_sync()
    hdr = tabs["Lead Register"][0]
    by_norm = {gsheets._norm(h): i for i, h in enumerate(hdr) if str(h).strip()}
    for f in NEW_LEAD_FIELDS:
        idx = by_norm.get(gsheets._norm(f))
        if idx is None:
            for alias in gsheets.HEADER_ALIASES.get(f, []):
                idx = by_norm.get(gsheets._norm(alias))
                if idx is not None:
                    break
        assert idx is not None, f"{f} still does not resolve after the repair"


@pytest.mark.asyncio
async def test_backfill_adds_waiting_headers_then_writes_tcs(sheet):
    tabs, values = sheet
    lead = {
        "leadId": "LD-TCS-1", "customerName": "Ravi",
        "rsaAmc": 2500, "tcs": 11000, "tcsBase": 1100000, "tcsApplicable": "Yes",
        "insuranceArrangedBy": "self", "finalExchangeValue": 40000,
        "schemeAsOf": "2026-09-01", "dealCancelled": False,
    }
    res = await gsheets.backfill({"leads": [lead]})
    assert res["ok"] is True, res
    assert res["failed"] == 0, res
    assert res["result"]["leads"]["appended"] == 1
    hdr = tabs["Lead Register"][0]
    for h in gsheets.LEAD_COMMERCIAL_HEADERS:
        assert h in hdr, h
    row = tabs["Lead Register"][1]
    assert row[hdr.index("Lead ID")] == "LD-TCS-1"
    assert row[hdr.index("TCS")] == 11000
    assert row[hdr.index("TCS Base")] == 1100000
    assert row[hdr.index("TCS Applicable")] == "Yes"
    assert row[hdr.index("RSA / AMC")] == 2500
    assert row[hdr.index("Insurance Arranged By")] == "self"
    assert row[hdr.index("Final Exchange Value")] == 40000
    assert row[hdr.index("Scheme As Of")] == "2026-09-01"
    assert row[hdr.index("Deal Cancelled")] == "No"
    # Batch path: one append for the new row, not one write per field.
    assert values.calls["append"] == 1
    # Second backfill updates in place, never duplicates.
    lead["tcs"] = 12000
    lead["dealCancelled"] = True
    again = await gsheets.backfill({"leads": [lead]})
    assert again["result"]["leads"]["updated"] == 1
    assert again["result"]["leads"]["appended"] == 0
    assert len(tabs["Lead Register"]) == 2
    row = tabs["Lead Register"][1]
    assert row[hdr.index("TCS")] == 12000
    assert row[hdr.index("Deal Cancelled")] == "Yes"


@pytest.mark.asyncio
async def test_backfill_batches_existing_rows_instead_of_one_call_each(sheet):
    tabs, values = sheet
    gsheets._ensure_lead_commercial_columns_sync()
    gsheets.invalidate_header_cache()
    docs = [{"leadId": f"LD{i}", "customerName": f"C{i}", "tcs": i * 100}
            for i in range(1, 6)]
    await gsheets.backfill({"leads": docs})
    appends_after_create = values.calls["append"]
    # Five existing rows: one (or few) batchUpdate, not five.
    values.calls["batchUpdate"] = 0
    await gsheets.backfill({"leads": docs})
    assert values.calls["append"] == appends_after_create
    assert values.calls["batchUpdate"] == 1
    assert len(tabs["Lead Register"]) == 6


@pytest.mark.asyncio
async def test_backfill_still_honours_the_write_guard(monkeypatch, sheet):
    monkeypatch.delenv("GSHEET_ALLOW_TEST_WRITES", raising=False)
    res = await gsheets.backfill({"leads": [{"leadId": "LD1"}]})
    assert res["ok"] is False
    assert res.get("canWrite") is False
    assert "TEST WRITE BLOCKED" in (res.get("reason") or "")


@pytest.mark.asyncio
async def test_commercial_ensure_honours_the_write_guard(monkeypatch, sheet):
    monkeypatch.delenv("GSHEET_ALLOW_TEST_WRITES", raising=False)
    res = await gsheets.ensure_lead_commercial_columns()
    assert res["ok"] is False and res.get("writeBlocked") is True


def test_sync_map_declares_scheme_claim_oem_fields():
    fields = gsheets.SYNC_MAP["claims"][2]
    for f in ("chassisNumber", "invoiceNumber", "oemMatchState", "oemStatus", "oemStageLabel"):
        assert f in fields, f
        assert f in PENDING_SHEET_COLUMNS["claims"], f
    assert gsheets.CLAIM_OEM_HEADERS == [
        "Chassis Number", "Invoice Number", "In Euler", "Euler Status", "Euler Stage",
    ]


def test_scheme_claim_oem_button_appends_headers_and_is_idempotent(sheet):
    tabs, values = sheet
    before = list(tabs["Scheme Claim Register"][0])
    res = gsheets._ensure_scheme_claim_oem_columns_sync()
    assert res["ok"] is True and res["changed"] is True, res
    assert res["tabs"][0]["added"] == gsheets.CLAIM_OEM_HEADERS
    hdr = tabs["Scheme Claim Register"][0]
    assert hdr[:len(before)] == before, "existing headers were reordered or renamed"
    for h in gsheets.CLAIM_OEM_HEADERS:
        assert h in hdr
    writes = values.calls["update"]
    again = gsheets._ensure_scheme_claim_oem_columns_sync()
    assert again["changed"] is False
    assert values.calls["update"] == writes


def test_appended_scheme_claim_headers_resolve_oem_fields(sheet):
    tabs, _ = sheet
    gsheets._ensure_scheme_claim_oem_columns_sync()
    hdr = tabs["Scheme Claim Register"][0]
    by_norm = {gsheets._norm(h): i for i, h in enumerate(hdr) if str(h).strip()}
    for f in ("chassisNumber", "invoiceNumber", "oemMatchState", "oemStatus", "oemStageLabel"):
        idx = by_norm.get(gsheets._norm(f))
        if idx is None:
            for alias in gsheets.HEADER_ALIASES.get(f, []):
                idx = by_norm.get(gsheets._norm(alias))
                if idx is not None:
                    break
        assert idx is not None, f"{f} still does not resolve after the repair"


@pytest.mark.asyncio
async def test_backfill_adds_scheme_claim_oem_headers_then_writes_filing(sheet):
    tabs, values = sheet
    claim = {
        "claimId": "CLM-LD1-oemExtraSupport", "leadId": "LD1",
        "customer": "Sita Ram Sharma", "component": "OEM Extra Support",
        "componentKey": "oemExtraSupport", "eligibleClaim": 7000,
        "claimAmount": 7000, "receivedAmount": 0, "claimStatus": "Submitted",
        "claimReference": "AF-122-CL2627077", "chassisNumber": "MD9EMVDL26G217730",
        "invoiceNumber": "AF-122-I26270117", "oemMatchState": "filed",
        "oemStatus": "Dealer Development Department Approval Pending",
        "oemStageLabel": "Dealer Development",
    }
    res = await gsheets.backfill({"claims": [claim]})
    assert res["ok"] is True, res
    assert res["failed"] == 0, res
    hdr = tabs["Scheme Claim Register"][0]
    for h in gsheets.CLAIM_OEM_HEADERS:
        assert h in hdr, h
    row = tabs["Scheme Claim Register"][1]
    assert row[hdr.index("Claim ID")] == "CLM-LD1-oemExtraSupport"
    assert row[hdr.index("Chassis Number")] == "MD9EMVDL26G217730"
    assert row[hdr.index("Invoice Number")] == "AF-122-I26270117"
    assert row[hdr.index("In Euler")] == "filed"
    assert row[hdr.index("Euler Status")] == "Dealer Development Department Approval Pending"
    assert row[hdr.index("Euler Stage")] == "Dealer Development"
    assert row[hdr.index("Claim Status")] == "Submitted"
    assert row[hdr.index("Claim Reference Number")] == "AF-122-CL2627077"
    assert row[hdr.index("Eligible Claim")] == 7000
    assert row[hdr.index("Received Amount")] == 0
