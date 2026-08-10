"""The Lead Register grows UPWARD against a footer header.

Contract (explicit, not inferred):
  * the operational table lives in columns J onward
  * columns A:I are a SEARCH/helper area — never cleared, never the table anchor
  * the header sits at the BOTTOM of the data as a footer boundary
  * every new lead is inserted immediately ABOVE the header
  * after each insert the header moves down by exactly one row, and the newest lead
    occupies the row directly above it
  * nothing is ever written below the header
  * existing rows, their formulas and their formatting are preserved

The headline test drives three consecutive inserts and asserts all of it.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import gsheets  # noqa: E402
from gsheets import SYNC_MAP, _col_letter  # noqa: E402

from live_headers import LIVE_HEADERS  # noqa: E402

LEAD_HEADER = LIVE_HEADERS["Lead Register"][1][9:]      # real header, column J onward
GID = 854596174
HELPER_ROW1 = ["SEARCH", "Lead ID", "Mobile", "Customer Name", "→ Use CRM menu > Search Lead"]


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class FooterSheet:
    """Lead Register shaped like the live one: helper labels on row 1, lead rows in
    columns J+, a blank separator, then the header as a footer."""

    def __init__(self, n_existing=2, header_row=5):
        self.grid = [list(HELPER_ROW1)]
        for i in range(n_existing):
            self.grid.append([""] * 9 + [f"LD260000{i + 1:02d}", "2026-08-01", f"Old {i + 1}"])
        while len(self.grid) < header_row - 1:
            self.grid.append([])
        self.grid.append([""] * 9 + list(LEAD_HEADER))
        self.inserts = []

    # --- helpers -------------------------------------------------------
    def _cell(self, r, c):
        row = self.grid[r] if r < len(self.grid) else []
        return row[c] if c < len(row) else ""

    def header_row_number(self):
        for i, row in enumerate(self.grid, start=1):
            if len(row) > 9 and str(row[9]).strip() == "Lead ID":
                return i
        raise AssertionError("header row not found")

    def lead_rows(self):
        """(row number, leadId) for every data row carrying a lead id."""
        out = []
        for i, row in enumerate(self.grid, start=1):
            v = str(self._cell(i - 1, 9)).strip()
            if v.startswith("LD26"):
                out.append((i, v))
        return out

    # --- Sheets values() surface ---------------------------------------
    def get(self, spreadsheetId=None, range=None, valueRenderOption=None, **kw):
        a1 = range.split("!")[1]
        if ":" in a1 and a1.replace(":", "").isdigit():
            lo, hi = (int(x) for x in a1.split(":"))
            return _Exec({"values": [list(r) for r in self.grid[lo - 1:hi]]})
        if ":" in a1 and a1.replace(":", "").isalpha():
            col = a1.split(":")[0]
            idx = 0
            for ch in col:
                idx = idx * 26 + (ord(ch) - 64)
            idx -= 1
            return _Exec({"values": [[self._cell(r, idx)] for r in range_len(self.grid)]})
        return _Exec({"values": []})

    def update(self, spreadsheetId=None, range=None, body=None, **kw):
        a1 = range.split("!")[1]
        start = a1.split(":")[0]
        col_letters = "".join(ch for ch in start if ch.isalpha())
        row_n = int("".join(ch for ch in start if ch.isdigit()))
        c0 = 0
        for ch in col_letters:
            c0 = c0 * 26 + (ord(ch) - 64)
        c0 -= 1
        while len(self.grid) < row_n:
            self.grid.append([])
        row = self.grid[row_n - 1]
        vals = body["values"][0]
        while len(row) < c0 + len(vals):
            row.append("")
        for i, v in enumerate(vals):
            row[c0 + i] = v
        self.grid[row_n - 1] = row
        return _Exec({})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        raise AssertionError("append must NOT be used on an upward-growing register")

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        return _Exec({})

    def clear(self, **kw):
        raise AssertionError("the Lead Register must never be cleared by a sync")


def range_len(grid):
    return list(range(len(grid)))


class Service:
    def __init__(self, values):
        self._values = values

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, **kw):
        return _Exec({"sheets": [{"properties": {"sheetId": GID, "title": "Lead Register"}}],
                      "properties": {"title": "Euler Master"}})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        """Only insertDimension is expected — perform the row insert on the fake grid."""
        for req in (body or {}).get("requests", []):
            ins = req.get("insertDimension")
            assert ins, f"unexpected structural request: {req}"
            rng = ins["range"]
            assert rng["dimension"] == "ROWS"
            assert ins.get("inheritFromBefore") is True, "must inherit formatting from the row above"
            at = rng["startIndex"]
            self._values.inserts.append(at)
            self._values.grid.insert(at, [])
        return _Exec({})


@pytest.fixture(autouse=True)
def clean_caches(monkeypatch):
    for name in ("_headerrow_cache", "_header_cache", "_idrow_cache", "_formula_cache",
                 "_sheetid_cache"):
        monkeypatch.setattr(gsheets, name, {})
    for k in list(os.environ):
        if k.startswith("GSHEET_HEADERROW_"):
            monkeypatch.delenv(k, raising=False)
    yield


def install(monkeypatch, sheet):
    monkeypatch.setattr(gsheets, "_service", Service(sheet))
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=True, canWrite=True))
    return sheet


# ------------------------------------------------------------ the headline test
@pytest.mark.asyncio
async def test_three_consecutive_inserts_grow_upward_against_the_footer_header(monkeypatch):
    sheet = install(monkeypatch, FooterSheet(n_existing=2, header_row=5))
    header_before = sheet.header_row_number()
    assert header_before == 5
    existing_before = sheet.lead_rows()
    assert [lid for _r, lid in existing_before] == ["LD26000001", "LD26000002"]

    inserted = []
    for n in range(1, 4):
        lead_id = f"LD2690000{n}"
        expected_header = header_before + n - 1
        res = await gsheets.sync("leads", {"leadId": lead_id, "customerName": f"New {n}"})
        assert res["ok"] is True, res
        assert res["operation"] == "inserted-above-header"

        # the record landed on the row the header just vacated ...
        assert res["row"] == expected_header, \
            f"insert {n} landed on row {res['row']}, expected {expected_header}"
        # ... and the header moved down by exactly one
        assert sheet.header_row_number() == expected_header + 1, \
            f"header moved to {sheet.header_row_number()}, expected {expected_header + 1}"
        assert res["headerRow"] == sheet.header_row_number()

        # the newest lead is directly above the header
        hdr = sheet.header_row_number()
        assert str(sheet._cell(hdr - 2, 9)).strip() == lead_id, \
            f"newest lead is not immediately above the header after insert {n}"
        inserted.append(lead_id)

    # exactly three rows were inserted, each at the header's index
    assert len(sheet.inserts) == 3

    # NOTHING below the header
    hdr = sheet.header_row_number()
    below = [(r, v) for r, v in sheet.lead_rows() if r > hdr]
    assert below == [], f"data written below the footer header: {below}"

    # reading UP from the header: newest -> oldest
    rows = sheet.lead_rows()
    upward = [lid for _r, lid in reversed(rows)]
    assert upward[:3] == list(reversed(inserted)), \
        f"rows above the header are not newest-to-oldest reading upward: {upward}"

    # historical rows kept their original row numbers and values
    assert [(r, lid) for r, lid in rows if lid.startswith("LD260000")] == existing_before


@pytest.mark.asyncio
async def test_insert_never_touches_the_A_to_I_helper_area(monkeypatch):
    sheet = install(monkeypatch, FooterSheet(n_existing=2, header_row=5))
    await gsheets.sync("leads", {"leadId": "LD26900010", "customerName": "Helper Guard"})
    assert sheet.grid[0][:5] == HELPER_ROW1, "row 1 helper labels were modified"
    hdr = sheet.header_row_number()
    for r in range(1, hdr + 1):
        for c in range(9):
            assert sheet._cell(r - 1, c) in ("", *HELPER_ROW1), \
                f"sync wrote into the A:I helper area at row {r} col {_col_letter(c)}"


@pytest.mark.asyncio
async def test_header_labels_survive_every_insert(monkeypatch):
    sheet = install(monkeypatch, FooterSheet(n_existing=1, header_row=4))
    for n in range(3):
        await gsheets.sync("leads", {"leadId": f"LD2691000{n}", "customerName": f"H{n}"})
    hdr = sheet.header_row_number()
    assert sheet.grid[hdr - 1][9:9 + len(LEAD_HEADER)] == list(LEAD_HEADER), \
        "header labels were altered or partially overwritten"


@pytest.mark.asyncio
async def test_columns_still_resolve_after_the_header_moves(monkeypatch):
    """The whole point of the footer contract: the header moves on every insert, so a
    cached/hard-coded row number must never be used to map columns."""
    sheet = install(monkeypatch, FooterSheet(n_existing=1, header_row=4))
    await gsheets.sync("leads", {"leadId": "LD26920001", "customerName": "A"})
    hr = gsheets._header_row_for("leads", "Lead Register")
    assert hr == sheet.header_row_number()
    mapping, missing = gsheets._resolve_columns("Lead Register", SYNC_MAP["leads"][2],
                                                use_cache=False, header_row=hr)
    assert missing == []
    assert _col_letter(mapping["leadId"]) == "J"


@pytest.mark.asyncio
async def test_existing_lead_is_updated_in_place_not_inserted(monkeypatch):
    """Only NEW ids grow the register; an existing id updates its own row."""
    sheet = install(monkeypatch, FooterSheet(n_existing=2, header_row=5))
    hdr_before = sheet.header_row_number()
    res = await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Renamed"})
    assert res["operation"] == "updated"
    assert sheet.header_row_number() == hdr_before, "an update must not move the header"
    assert sheet.inserts == [], "an update must not insert a row"


@pytest.mark.asyncio
async def test_other_registers_still_append_below_their_header(monkeypatch):
    """Only the Lead Register grows upward. Booking Register keeps normal append."""
    assert gsheets.UPWARD_GROWING_REGISTERS == {"leads"}

    class Normal(FooterSheet):
        def __init__(self):
            super().__init__()
            self.grid = [list(LIVE_HEADERS["Booking Register"][1])]
            self.appended = []

        def append(self, spreadsheetId=None, range=None, body=None, **kw):
            self.appended.append(range)
            self.grid.append(body["values"][0])
            return _Exec({"updates": {"updatedRange": f"'Booking Register'!A{len(self.grid)}"}})

    sheet = install(monkeypatch, Normal())
    res = await gsheets.sync("bookings", {"bookingId": "BK26999999", "leadId": "LD1"})
    assert res["ok"] is True and res["operation"] == "appended"
    assert sheet.appended, "booking register should still use append"


@pytest.mark.asyncio
async def test_resyncing_every_existing_lead_creates_no_duplicates(monkeypatch):
    """Regression for the data-window bug this contract exposed: the ID scan used to
    start at header_row+1. On a footer-header register every record lives ABOVE the
    header, so the scan found nothing, every lead looked new, and each sync inserted a
    duplicate. Re-syncing must be a pure no-op on row count and header position."""
    sheet = install(monkeypatch, FooterSheet(n_existing=3, header_row=6))
    before_rows = sheet.lead_rows()
    before_header = sheet.header_row_number()

    for _r, lid in before_rows:                       # re-sync every existing lead twice
        for _ in range(2):
            res = await gsheets.sync("leads", {"leadId": lid, "customerName": "Resync"})
            assert res["operation"] == "updated", f"{lid} was re-inserted: {res}"

    assert sheet.lead_rows() == before_rows, "re-sync changed the row layout"
    assert sheet.header_row_number() == before_header, "re-sync moved the header"
    assert sheet.inserts == [], "re-sync inserted rows"
    ids = [lid for _r, lid in sheet.lead_rows()]
    assert len(ids) == len(set(ids)), f"duplicate lead rows: {ids}"
