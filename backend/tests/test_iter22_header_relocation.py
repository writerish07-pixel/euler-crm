"""The sync survives a header that is not where the hint says it is.

A Google Sheets append with insertDataOption=INSERT_ROWS inserts rows wherever its
range anchors. The Lead Register's register starts at column J with a separate
SEARCH/helper block in A:I; anchored at A1 the API treated the helper block as the
table and inserted rows into it, pushing the real header from row 3 down to row 22.

With a hard-coded header row the sync then reads DATA as headers and silently
mis-maps every column. These lock both halves of the fix: the header is located by
content, and appends anchor on the register itself.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import gsheets  # noqa: E402
from gsheets import SYNC_MAP, _col_letter  # noqa: E402

from live_headers import LIVE_HEADERS  # noqa: E402

LEAD_HEADER = LIVE_HEADERS["Lead Register"][1][9:]     # real header, column J onward


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class ShiftedValues:
    """Lead Register in the state the live sheet was found in: SEARCH labels on row 1,
    19 lead rows at rows 2-20 (columns J+), blank row 21, real header on row 22."""

    def __init__(self, header_row=22, n_data=19):
        self.header_row = header_row
        self.appended = []
        grid = [["SEARCH", "Lead ID", "Mobile", "Customer Name"]]
        for i in range(n_data):
            grid.append([""] * 9 + [f"LD260000{i + 1:02d}", "2026-08-09", f"Customer {i + 1}"])
        while len(grid) < header_row - 1:
            grid.append([])                              # blank separator row(s)
        grid.append([""] * 9 + list(LEAD_HEADER))        # the real header
        self.grid = grid

    def get(self, spreadsheetId=None, range=None, valueRenderOption=None, **kw):
        a1 = range.split("!")[1]
        if ":" in a1 and a1.replace(":", "").isdigit():
            lo, hi = (int(x) for x in a1.split(":"))
            return _Exec({"values": [list(r) for r in self.grid[lo - 1:hi]]})
        return _Exec({"values": []})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        self.appended.append(range)
        return _Exec({"updates": {"updatedRange": f"'Lead Register'!A{len(self.grid) + 1}"}})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        return _Exec({})

    def clear(self, **kw):
        return _Exec({})

    def update(self, **kw):
        return _Exec({})


class Service:
    def __init__(self, values):
        self._values = values

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, **kw):
        return _Exec({"properties": {"title": "Euler Master"}})

    def batchUpdate(self, **kw):
        return _Exec({})


@pytest.fixture(autouse=True)
def clean_caches(monkeypatch):
    monkeypatch.setattr(gsheets, "_headerrow_cache", {})
    monkeypatch.setattr(gsheets, "_header_cache", {})
    monkeypatch.setattr(gsheets, "_idrow_cache", {})
    monkeypatch.setattr(gsheets, "_formula_cache", {})
    for k in list(os.environ):
        if k.startswith("GSHEET_HEADERROW_"):
            monkeypatch.delenv(k, raising=False)
    yield


def install(monkeypatch, values):
    monkeypatch.setattr(gsheets, "_service", Service(values))
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=True, canWrite=True))
    return values


def test_locate_header_row_finds_a_header_that_moved_to_row_22(monkeypatch):
    v = install(monkeypatch, ShiftedValues())
    found = gsheets.locate_header_row("Lead Register", SYNC_MAP["leads"][2], hint=3)
    assert found == 22, f"header not located; would have read row 3 (lead data) as headers, got {found}"


def test_header_row_for_overrides_a_stale_hint(monkeypatch):
    """SYNC_MAP still hints row 3; the sheet says 22. The sheet wins."""
    install(monkeypatch, ShiftedValues())
    assert SYNC_MAP["leads"][3] == 3
    assert gsheets._header_row_for("leads", "Lead Register") == 22


def test_columns_resolve_correctly_against_the_relocated_header(monkeypatch):
    install(monkeypatch, ShiftedValues())
    hr = gsheets._header_row_for("leads", "Lead Register")
    mapping, missing = gsheets._resolve_columns("Lead Register", SYNC_MAP["leads"][2],
                                                use_cache=False, header_row=hr)
    assert missing == [], f"unresolved fields against relocated header: {missing}"
    assert _col_letter(mapping["leadId"]) == "J"
    assert min(mapping.values()) >= 9, "a lead field mapped into the protected A:I area"


def test_unshifted_sheet_still_uses_its_normal_header_row(monkeypatch):
    """The fix must not disturb a well-formed tab: header on row 3, data below."""
    v = ShiftedValues(header_row=3, n_data=0)
    v.grid = [["SEARCH", "Lead ID", "Mobile"], [], [""] * 9 + list(LEAD_HEADER),
              [""] * 9 + ["LD26000001", "2026-08-09", "Real Customer"]]
    install(monkeypatch, v)
    assert gsheets._header_row_for("leads", "Lead Register") == 3


def test_a_row_of_lead_data_is_never_mistaken_for_the_header(monkeypatch):
    """Row 2 holds lead IDs, not header labels — it must score far below the header."""
    v = install(monkeypatch, ShiftedValues())
    assert gsheets.locate_header_row("Lead Register", SYNC_MAP["leads"][2], hint=3) != 2


@pytest.mark.asyncio
async def test_append_anchors_on_the_register_not_on_A1(monkeypatch):
    """A1 anchoring is what let INSERT_ROWS shift the header. The append must target
    the first mapped column at the header row instead."""
    v = install(monkeypatch, ShiftedValues())
    res = await gsheets.sync("leads", {"leadId": "LD26999999", "customerName": "New Lead"})
    assert res["ok"] is True, res
    assert res["operation"] == "appended"
    assert v.appended, "no append was issued"
    rng = v.appended[0]
    assert rng == "'Lead Register'!J22", f"append anchored at {rng} — must be the register's own header cell"
    assert "!A1" not in rng


@pytest.mark.asyncio
async def test_append_anchor_uses_each_tabs_own_first_column(monkeypatch):
    """Tabs whose table starts at column A must still anchor at A<header row>."""
    class Simple(ShiftedValues):
        def __init__(self):
            super().__init__()
            self.grid = [list(LIVE_HEADERS["Finance Register"][1])]

    v = install(monkeypatch, Simple())
    res = await gsheets.sync("finance", {"financeFileNumber": "FN26000999", "leadId": "LD1"})
    assert res["ok"] is True, res
    assert v.appended[0] == "'Finance Register'!A1"
