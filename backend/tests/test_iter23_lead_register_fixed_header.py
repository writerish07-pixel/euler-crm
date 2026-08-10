"""The Lead Register is a normal register: FIXED header at the top, data below.

Contract:
  * the header stays permanently at the top and never moves
  * existing leads sit below the header
  * a new lead is written after the last existing lead
  * updating an existing lead rewrites its own row — never adds one
  * re-syncing the same lead produces no duplicate
  * columns A:I are a SEARCH/helper area and are never touched
  * formulas, formatting and the frozen header are preserved

The headline test drives three consecutive inserts and asserts every point.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

_RANGE = range        # the Sheets API param is named `range`, shadowing the builtin

import gsheets  # noqa: E402
from gsheets import SYNC_MAP, _col_letter  # noqa: E402

from live_headers import LIVE_HEADERS  # noqa: E402

LEAD_HEADER = LIVE_HEADERS["Lead Register"][1][9:]      # real header, column J onward
HEADER_ROW = 3                                          # rows 1-2 are the helper block
FIRST_DATA_ROW = 4
HELPER_ROW1 = ["SEARCH", "Lead ID", "Mobile", "Customer Name", "→ Use CRM menu > Search Lead"]
HELPER_ROW2 = ["LD26000001", "2026-08-08", "Helper Row", "9800000001", "Walk-in"]


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class LeadSheet:
    """Lead Register in its correct shape: helper block rows 1-2 (cols A:I), the
    header on row 3 from column J, and lead rows from row 4 downward."""

    def __init__(self, n_existing=0):
        self.grid = [list(HELPER_ROW1), list(HELPER_ROW2),
                     [""] * 9 + list(LEAD_HEADER)]
        for i in range(n_existing):
            self.grid.append([""] * 9 + [f"LD260000{i + 1:02d}", "2026-08-01", f"Old {i + 1}"])
        self.appended = []

    # --- inspection helpers ---------------------------------------------
    def _cell(self, r0, c):
        row = self.grid[r0] if r0 < len(self.grid) else []
        return row[c] if c < len(row) else ""

    def header_row_number(self):
        for i, row in enumerate(self.grid, start=1):
            if len(row) > 9 and str(row[9]).strip() == "Lead ID":
                return i
        raise AssertionError("header row not found")

    def lead_rows(self):
        """(row number, leadId) for every row carrying a lead id in column J."""
        return [(i, str(self._cell(i - 1, 9)).strip())
                for i in range(1, len(self.grid) + 1)
                if str(self._cell(i - 1, 9)).strip().startswith("LD26")]

    def helper_block(self):
        return [list(r[:9]) for r in self.grid[:2]]

    # --- Sheets values() surface -----------------------------------------
    def get(self, spreadsheetId=None, range=None, valueRenderOption=None, **kw):
        a1 = range.split("!")[1]
        if ":" in a1 and a1.replace(":", "").isdigit():
            lo, hi = (int(x) for x in a1.split(":"))
            return _Exec({"values": [list(r) for r in self.grid[lo - 1:hi]]})
        if ":" in a1 and a1.replace(":", "").isalpha():
            letters = a1.split(":")[0]
            idx = 0
            for ch in letters:
                idx = idx * 26 + (ord(ch) - 64)
            idx -= 1
            return _Exec({"values": [[self._cell(r, idx)] for r in _RANGE(len(self.grid))]})
        # single-row span, e.g. J5:BZ5 (formula protection probe)
        start = a1.split(":")[0]
        row_n = int("".join(c for c in start if c.isdigit()))
        c0 = 0
        for ch in "".join(c for c in start if c.isalpha()):
            c0 = c0 * 26 + (ord(ch) - 64)
        c0 -= 1
        row = self.grid[row_n - 1] if row_n - 1 < len(self.grid) else []
        seg = [row[i] if i < len(row) else "" for i in _RANGE(c0, len(row))]
        if valueRenderOption != "FORMULA":
            seg = ["" if isinstance(v, str) and v.startswith("=") else v for v in seg]
        return _Exec({"values": [seg]})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        """Append after the last row of the table the range anchors on."""
        self.appended.append(range)
        self.grid.append(list(body["values"][0]))
        return _Exec({"updates": {"updatedRange": f"'Lead Register'!A{len(self.grid)}"}})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        for item in (body or {}).get("data", []):
            a1 = item["range"].split("!")[1]
            col_letters = "".join(c for c in a1 if c.isalpha())
            row_n = int("".join(c for c in a1 if c.isdigit()))
            c = 0
            for ch in col_letters:
                c = c * 26 + (ord(ch) - 64)
            c -= 1
            while len(self.grid) < row_n:
                self.grid.append([])
            row = self.grid[row_n - 1]
            while len(row) <= c:
                row.append("")
            row[c] = item["values"][0][0]
            self.grid[row_n - 1] = row
        return _Exec({})

    def clear(self, **kw):
        raise AssertionError("the Lead Register must never be cleared by a sync")

    def update(self, **kw):
        raise AssertionError("a fixed-header register writes via append/batchUpdate only")


class Service:
    def __init__(self, values):
        self._values = values

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, **kw):
        return _Exec({"properties": {"title": "Euler Master"}})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        assert not (body or {}).get("requests"), \
            f"no structural request may be issued on a fixed-header register: {body}"
        return _Exec({})


@pytest.fixture(autouse=True)
def clean_caches(monkeypatch):
    for name in ("_headerrow_cache", "_header_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})
    for k in list(os.environ):
        if k.startswith("GSHEET_HEADERROW_"):
            monkeypatch.delenv(k, raising=False)
    yield


def install(monkeypatch, sheet):
    monkeypatch.setattr(gsheets, "_service", Service(sheet))
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=True, canWrite=True))
    return sheet


# ----------------------------------------------------------- the headline test
@pytest.mark.asyncio
async def test_three_leads_append_downward_under_a_fixed_header(monkeypatch):
    sheet = install(monkeypatch, LeadSheet())
    assert sheet.header_row_number() == HEADER_ROW
    assert sheet.lead_rows() == [], "fixture should start with no leads"

    expected_rows = []
    for n in range(1, 4):
        lead_id = f"LD2690000{n}"
        res = await gsheets.sync("leads", {"leadId": lead_id, "customerName": f"Lead {n}"})
        assert res["ok"] is True, res
        assert res["operation"] == "appended"

        # the header never moves
        assert sheet.header_row_number() == HEADER_ROW, \
            f"header moved to row {sheet.header_row_number()} after insert {n}"

        expected_rows.append((FIRST_DATA_ROW + n - 1, lead_id))
        assert sheet.lead_rows() == expected_rows, \
            f"after insert {n} the register is {sheet.lead_rows()}, expected {expected_rows}"

    # first lead directly below the header, each subsequent one below the previous
    rows = sheet.lead_rows()
    assert rows[0][0] == HEADER_ROW + 1
    assert rows[1][0] == rows[0][0] + 1
    assert rows[2][0] == rows[1][0] + 1

    # nothing above the header, everything below it
    assert all(r > HEADER_ROW for r, _lid in rows)

    # order is oldest -> newest reading downward
    assert [lid for _r, lid in rows] == ["LD26900001", "LD26900002", "LD26900003"]


@pytest.mark.asyncio
async def test_new_lead_appends_below_the_last_existing_lead(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=3))
    last_row = sheet.lead_rows()[-1][0]
    res = await gsheets.sync("leads", {"leadId": "LD26910001", "customerName": "Newest"})
    assert res["operation"] == "appended"
    assert sheet.lead_rows()[-1] == (last_row + 1, "LD26910001")
    assert sheet.header_row_number() == HEADER_ROW


@pytest.mark.asyncio
async def test_updating_an_existing_lead_does_not_add_a_row(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=3))
    before = sheet.lead_rows()
    res = await gsheets.sync("leads", {"leadId": "LD26000002", "customerName": "Renamed"})
    assert res["operation"] == "updated"
    assert sheet.lead_rows() == before, "an update changed the row layout"
    assert sheet.appended == [], "an update must not append"
    hdr_idx = sheet.header_row_number() - 1
    name_col = sheet.grid[hdr_idx].index("Customer Name")
    row_n = dict((lid, r) for r, lid in before)["LD26000002"]
    assert sheet._cell(row_n - 1, name_col) == "Renamed"


@pytest.mark.asyncio
async def test_repeated_sync_creates_zero_duplicates(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=3))
    before = sheet.lead_rows()
    for _r, lid in before:
        for _ in range(3):
            res = await gsheets.sync("leads", {"leadId": lid, "customerName": "Resync"})
            assert res["operation"] == "updated", f"{lid} was re-appended: {res}"
    after = sheet.lead_rows()
    assert after == before
    ids = [lid for _r, lid in after]
    assert len(ids) == len(set(ids)), f"duplicate rows: {ids}"
    assert sheet.header_row_number() == HEADER_ROW


@pytest.mark.asyncio
async def test_header_row_never_changes_across_many_writes(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=2))
    for n in range(5):
        await gsheets.sync("leads", {"leadId": f"LD2692000{n}", "customerName": f"N{n}"})
        await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": f"Upd{n}"})
        assert sheet.header_row_number() == HEADER_ROW
    assert sheet.grid[HEADER_ROW - 1][9:9 + len(LEAD_HEADER)] == list(LEAD_HEADER), \
        "header labels were altered"


@pytest.mark.asyncio
async def test_A_to_I_helper_area_is_never_touched(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=2))
    before = sheet.helper_block()
    for n in range(3):
        await gsheets.sync("leads", {"leadId": f"LD2693000{n}", "customerName": f"H{n}"})
    await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Updated"})
    assert sheet.helper_block() == before, "the A:I search/helper area was modified"
    # and no lead field ever maps into A:I
    hr = gsheets._header_row_for("leads", "Lead Register")
    mapping, _ = gsheets._resolve_columns("Lead Register", SYNC_MAP["leads"][2],
                                          use_cache=False, header_row=hr)
    assert min(mapping.values()) >= 9
    assert _col_letter(mapping["leadId"]) == "J"


@pytest.mark.asyncio
async def test_helper_row_lead_id_is_not_mistaken_for_a_record(monkeypatch):
    """Helper row 2 carries 'LD26000001' in column A. The ID scan reads column J only,
    below the header — it must not match the helper cell and update the wrong row."""
    sheet = install(monkeypatch, LeadSheet())
    res = await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Real Record"})
    assert res["operation"] == "appended", "matched the A:I helper row instead of appending"
    assert sheet.lead_rows() == [(FIRST_DATA_ROW, "LD26000001")]
    assert sheet.helper_block()[1] == HELPER_ROW2


@pytest.mark.asyncio
async def test_formulas_in_mapped_columns_are_preserved_on_update(monkeypatch):
    sheet = install(monkeypatch, LeadSheet(n_existing=1))
    hdr = sheet.grid[HEADER_ROW - 1]
    td = hdr.index("Total Discount")
    row = sheet.grid[FIRST_DATA_ROW - 1]
    while len(row) <= td:
        row.append("")
    row[td] = "=BF4+BG4+BH4"
    await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Asha",
                                 "totalDiscount": 99999})
    assert sheet.grid[FIRST_DATA_ROW - 1][td] == "=BF4+BG4+BH4", "formula was overwritten"


@pytest.mark.asyncio
async def test_no_structural_request_is_ever_issued(monkeypatch):
    """No insertDimension / moveDimension: the register must not restructure itself.
    Service.batchUpdate asserts this; this test makes the intent explicit."""
    sheet = install(monkeypatch, LeadSheet(n_existing=1))
    await gsheets.sync("leads", {"leadId": "LD26940001", "customerName": "Structural"})
    await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Updated"})
    assert sheet.header_row_number() == HEADER_ROW
