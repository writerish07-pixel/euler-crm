"""GS-1..GS-5 Google Sheet integration tests.

Runs against a fake in-memory Sheets API that mimics the real
spreadsheets().values() surface, so the whole sync path (header resolution,
ID upsert, formula protection, retry) is exercised without touching Google.

The fake sheet deliberately uses headers in a DIFFERENT ORDER from the CRM
field list, with human-style names ("Lead ID", "Customer Name"), plus an extra
dealership-owned column and a formula column — proving the CRM adapts to the
existing sheet rather than the other way round.
"""
import os
import sys

import pytest

_RANGE = range

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import gsheets  # noqa: E402


class FakeValues:
    def __init__(self, tabs):
        self.tabs = tabs
        self.calls = {"append": 0, "batchUpdate": 0}
        self.fail_next = 0

    # --- helpers -------------------------------------------------------
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

    # --- API surface ---------------------------------------------------
    def get(self, spreadsheetId=None, range=None, valueRenderOption=None):
        tab, a1 = self._parse(range)
        grid = self.tabs.get(tab)
        if grid is None:
            raise RuntimeError(f"Unable to parse range: {range} (no such tab)")
        if a1 == "1:1":
            out = [list(grid[0])] if grid else []
        elif ":" in a1 and a1.replace(":", "").isalpha():           # e.g. A:A
            letters = a1.split(":")[0]
            i = self._col_to_idx(letters)
            out = [[r[i]] if i < len(r) else [] for r in grid]
        else:                                                        # e.g. B3:F3
            start, end = a1.split(":")
            s_col = self._col_to_idx("".join(c for c in start if c.isalpha()))
            e_col = self._col_to_idx("".join(c for c in end if c.isalpha()))
            row_n = int("".join(c for c in start if c.isdigit()))
            row = grid[row_n - 1] if row_n - 1 < len(grid) else []
            seg = [row[i] if i < len(row) else "" for i in _RANGE(s_col, e_col + 1)]
            if valueRenderOption != "FORMULA":
                seg = ["" if isinstance(v, str) and v.startswith("=") else v for v in seg]
            out = [seg]
        return _Exec({"values": out})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        tab, _ = self._parse(range)
        self.calls["append"] += 1
        for row in body["values"]:
            grid = self.tabs[tab]
            width = max(len(grid[0]), len(row))
            self.tabs[tab].append(list(row) + [""] * (width - len(row)))
        return _Exec({})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        if self.fail_next > 0:
            self.fail_next -= 1
            raise RuntimeError("Simulated Google API 503")
        self.calls["batchUpdate"] += 1
        for item in body["data"]:
            tab, a1 = self._parse(item["range"])
            col = self._col_to_idx("".join(c for c in a1 if c.isalpha()))
            row_n = int("".join(c for c in a1 if c.isdigit()))
            grid = self.tabs[tab]
            while len(grid) < row_n:
                grid.append([""] * len(grid[0]))
            row = grid[row_n - 1]
            while len(row) <= col:
                row.append("")
            row[col] = item["values"][0][0]
        return _Exec({})

    def clear(self, **kw):
        return _Exec({})

    def update(self, **kw):
        return _Exec({})


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class FakeService:
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


def make_sheet():
    """Existing sheet: headers in a different order than the CRM field list,
    human names, an extra dealership column, and a formula column."""
    return {
        "Lead Register": [
            # Note the order: NOT the CRM field order. "Days Open" is a formula the
            # dealership owns; "Remarks (Manual)" is staff-entered and unmapped.
            ["Created Date", "Lead ID", "Customer Name", "Mobile", "Lead Source",
             "Interested Model", "Variant", "Executive", "Current Status",
             "Days Open", "Remarks (Manual)"],
        ],
        "Booking Register": [
            ["Booking ID", "Lead ID", "Customer Name", "Booking Date", "Model",
             "Variant", "Booking Amount", "Payment Mode", "Booking Status"],
        ],
        "Payment Ledger": [
            ["Receipt Number", "Payment Id", "Lead ID", "Customer Name", "Date", "Amount",
             "Payment Mode", "Narration", "Running Total", "Outstanding Balance"],
        ],
        "Scheme Claim Register": [
            ["Claim ID", "Lead ID", "Customer", "Model", "Component",
             "Claim Amount", "Claim Status", "Received Amount", "Claim Reference"],
        ],
        "Delivery Tracker": [
            ["Lead ID", "Customer Name", "Delivery Date", "Delivered",
             "Invoice Number", "Chassis Number", "Number Plate"],
        ],
        "Dealer Earnings": [
            ["Lead ID", "Customer Name", "Model", "Dealer Margin", "Dealer Scheme Retained",
             "Dealer Insurance Income", "Finance Incentive", "Accessories Margin",
             "Exchange Margin", "Documentation Income", "Warranty Income", "RSA Income",
             "Referral Income", "Campaign Incentive", "Other Income",
             "Oem Extra Support Retained", "Extra Dealer Income", "Dealer Total Earnings"],
        ],
        "Finance Register": [
            ["Finance File Number", "Lead ID", "Customer Name", "Financer Name",
             "Committed Amount", "Disbursed Amount", "Finance Outstanding", "Status"],
        ],
        "Exchange Register": [
            ["Lead ID", "Customer Name", "Exchange Required", "Final Exchange Value",
             "Exchange Bonus", "Exchange Margin"],
        ],
    }


@pytest.fixture
def sheet(monkeypatch):
    tabs = make_sheet()
    values = FakeValues(tabs)
    monkeypatch.setattr(gsheets, "_service", FakeService(values))
    monkeypatch.setattr(gsheets, "_status", {"enabled": True, "reason": "connected", "email": "x@y.iam"})
    gsheets.invalidate_header_cache()
    return tabs, values


def rows(tabs, tab):
    return tabs[tab][1:]


# ---------------------------------------------------------------- GS-1
@pytest.mark.asyncio
async def test_header_based_mapping_not_positional(sheet):
    """Lead ID is column B in this sheet, not column A. A positional writer would
    corrupt every row; the header-mapped writer must place values correctly."""
    tabs, _ = sheet
    res = await gsheets.sync("leads", {
        "leadId": "LD1", "createdDate": "2026-08-01", "customerName": "Asha",
        "mobile": "9000000001", "leadSource": "Walk-in", "interestedModel": "HiCity",
        "variant": "XR", "executive": "Amit", "currentStatus": "New"})
    assert res["ok"] and res["operation"] == "appended"
    row = rows(tabs, "Lead Register")[0]
    hdr = tabs["Lead Register"][0]
    assert row[hdr.index("Lead ID")] == "LD1"
    assert row[hdr.index("Customer Name")] == "Asha"
    assert row[hdr.index("Created Date")] == "2026-08-01"


@pytest.mark.asyncio
async def test_missing_id_header_refuses_to_write(sheet):
    """If the ID header is absent we must refuse, never guess a column."""
    tabs, values = sheet
    tabs["Lead Register"][0] = ["Created Date", "Customer Name", "Mobile"]
    gsheets.invalidate_header_cache()
    res = await gsheets.sync("leads", {"leadId": "LD9", "customerName": "X"})
    assert res["ok"] is False
    assert res["operation"] == "refused"
    assert "leadId" in res["error"]
    assert values.calls["append"] == 0
    assert len(rows(tabs, "Lead Register")) == 0


# ---------------------------------------------------------------- GS-2 / GS-3
@pytest.mark.asyncio
async def test_lead_update_updates_same_row(sheet):
    tabs, _ = sheet
    base = {"leadId": "LD1", "createdDate": "2026-08-01", "customerName": "Asha",
            "mobile": "9000000001", "currentStatus": "New"}
    await gsheets.sync("leads", base)
    r2 = await gsheets.sync("leads", {**base, "customerName": "Asha Devi", "currentStatus": "Booked"})
    r3 = await gsheets.sync("leads", {**base, "customerName": "Asha Devi", "currentStatus": "Delivered"})
    assert r2["operation"] == "updated" and r3["operation"] == "updated"
    assert len(rows(tabs, "Lead Register")) == 1, "must never append a second row"
    hdr = tabs["Lead Register"][0]
    assert rows(tabs, "Lead Register")[0][hdr.index("Current Status")] == "Delivered"
    assert rows(tabs, "Lead Register")[0][hdr.index("Customer Name")] == "Asha Devi"


@pytest.mark.asyncio
async def test_repeated_sync_is_idempotent_all_entities(sheet):
    tabs, _ = sheet
    payloads = {
        "leads": {"leadId": "LD1", "customerName": "A"},
        "bookings": {"bookingId": "BK1", "leadId": "LD1", "bookingAmount": 50000},
        "payments": {"receiptNumber": "RC1", "paymentId": "PY1", "leadId": "LD1", "amount": 50000},
        "claims": {"claimId": "CLM1", "leadId": "LD1", "claimAmount": 25000},
        "deliveries": {"leadId": "LD1", "delivered": "Yes"},
        "finance": {"financeFileNumber": "FF1", "leadId": "LD1", "committedAmount": 100},
        "exchange": {"leadId": "LD1", "exchangeRequired": "Yes"},
        "dealer_earnings": {"leadId": "LD1", "dealerTotalEarnings": 1234},
    }
    for _ in range(3):
        for entity, doc in payloads.items():
            r = await gsheets.sync(entity, doc)
            assert r["ok"], f"{entity}: {r}"
    for entity in payloads:
        tab = gsheets.SYNC_MAP[entity][0]
        assert len(rows(tabs, tab)) == 1, f"{entity} duplicated in {tab}"


@pytest.mark.asyncio
async def test_claim_lifecycle_updates_one_row(sheet):
    """Claim created -> settled -> receipt recorded = ONE row, not three."""
    tabs, _ = sheet
    cid = "CLM-LD1-consumerDiscount"
    await gsheets.sync("claims", {"claimId": cid, "leadId": "LD1", "claimAmount": 25000,
                                  "claimStatus": "Pending", "receivedAmount": 0})
    await gsheets.sync("claims", {"claimId": cid, "leadId": "LD1", "claimAmount": 25000,
                                  "claimStatus": "Submitted", "receivedAmount": 0})
    await gsheets.sync("claims", {"claimId": cid, "leadId": "LD1", "claimAmount": 25000,
                                  "claimStatus": "Received", "receivedAmount": 25000})
    r = rows(tabs, "Scheme Claim Register")
    assert len(r) == 1
    hdr = tabs["Scheme Claim Register"][0]
    assert r[0][hdr.index("Claim Status")] == "Received"
    assert r[0][hdr.index("Received Amount")] == 25000


@pytest.mark.asyncio
async def test_delivery_repeat_does_not_duplicate(sheet):
    tabs, _ = sheet
    for _ in range(4):
        await gsheets.sync("deliveries", {"leadId": "LD7", "customerName": "R",
                                          "delivered": "Yes", "invoiceNumber": "INV1"})
    assert len(rows(tabs, "Delivery Tracker")) == 1


# ---------------------------------------------------------------- formula protection
@pytest.mark.asyncio
async def test_formula_and_unmapped_columns_preserved(sheet):
    """A formula in a mapped column is never overwritten, and columns the CRM
    does not own (staff remarks) are never touched."""
    tabs, _ = sheet
    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha", "currentStatus": "New"})
    hdr = tabs["Lead Register"][0]
    row = tabs["Lead Register"][1]
    row[hdr.index("Days Open")] = "=TODAY()-A2"           # dealership formula
    row[hdr.index("Remarks (Manual)")] = "call back Tue"   # staff input, unmapped
    # Also put a formula INSIDE a mapped column to prove it is skipped.
    row[hdr.index("Current Status")] = "=UPPER(\"booked\")"

    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha Devi",
                                 "currentStatus": "Delivered"})
    row = tabs["Lead Register"][1]
    assert row[hdr.index("Days Open")] == "=TODAY()-A2", "unmapped formula column altered"
    assert row[hdr.index("Remarks (Manual)")] == "call back Tue", "manual staff column altered"
    assert row[hdr.index("Current Status")] == "=UPPER(\"booked\")", "formula in mapped column overwritten"
    assert row[hdr.index("Customer Name")] == "Asha Devi", "normal cell should still update"


@pytest.mark.asyncio
async def test_partial_update_does_not_blank_other_fields(sheet):
    tabs, _ = sheet
    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha",
                                 "mobile": "9000000001", "executive": "Amit"})
    await gsheets.sync("leads", {"leadId": "LD1", "currentStatus": "Booked"})
    hdr = tabs["Lead Register"][0]
    row = tabs["Lead Register"][1]
    assert row[hdr.index("Mobile")] == "9000000001"
    assert row[hdr.index("Executive")] == "Amit"
    assert row[hdr.index("Current Status")] == "Booked"


# ---------------------------------------------------------------- GS-4
@pytest.mark.asyncio
async def test_api_failure_reported_not_swallowed(sheet):
    tabs, values = sheet
    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha"})
    values.fail_next = 1
    res = await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Changed"})
    assert res["ok"] is False
    assert res["operation"] == "error"
    assert "503" in res["error"]


@pytest.mark.asyncio
async def test_retry_after_timeout_updates_never_duplicates(sheet):
    """The write succeeded but the caller saw a failure; replaying must find the
    existing row by ID and update it, not append a second row."""
    tabs, _ = sheet
    doc = {"leadId": "LD1", "customerName": "Asha", "currentStatus": "New"}
    await gsheets.sync("leads", doc)
    for _ in range(3):                       # simulate replays of the same write
        r = await gsheets.sync("leads", doc)
        assert r["operation"] == "updated"
    assert len(rows(tabs, "Lead Register")) == 1


# ---------------------------------------------------------------- GS-5
@pytest.mark.asyncio
async def test_dealer_earnings_maps_to_existing_headers(sheet):
    tabs, _ = sheet
    await gsheets.sync("dealer_earnings", {
        "leadId": "LD1", "customerName": "Asha", "model": "HiCity",
        "dealerMarginNetExGst": 10884.35, "dealerSchemeRetained": 0,
        "customerInsuranceBenefitPassed": 500, "dealerTotalEarnings": 11384.35})
    hdr = tabs["Dealer Earnings"][0]
    row = rows(tabs, "Dealer Earnings")[0]
    assert row[hdr.index("Dealer Margin")] == 10884.35        # via alias
    assert row[hdr.index("Dealer Insurance Income")] == 500   # via alias
    assert row[hdr.index("Dealer Total Earnings")] == 11384.35


@pytest.mark.asyncio
async def test_finance_and_exchange_sync(sheet):
    tabs, _ = sheet
    await gsheets.sync("finance", {"financeFileNumber": "FF1", "leadId": "LD1",
                                   "committedAmount": 200000, "financeOutstanding": 200000,
                                   "status": "Pending"})
    await gsheets.sync("exchange", {"leadId": "LD1", "exchangeRequired": "Yes",
                                    "finalExchangeValue": 30000})
    fh = tabs["Finance Register"][0]
    assert rows(tabs, "Finance Register")[0][fh.index("Committed Amount")] == 200000
    eh = tabs["Exchange Register"][0]
    assert rows(tabs, "Exchange Register")[0][eh.index("Final Exchange Value")] == 30000


# ---------------------------------------------------------------- preflight
@pytest.mark.asyncio
async def test_preflight_reports_mapping_and_gaps(sheet):
    tabs, _ = sheet
    tabs["Booking Register"][0] = ["Booking ID", "Lead ID"]   # deliberately narrow
    gsheets.invalidate_header_cache()
    rep = gsheets.preflight()
    assert rep["enabled"] is True
    assert rep["tabs"]["leads"]["willSync"] is True
    assert rep["tabs"]["leads"]["resolved"]["leadId"] == "B"
    bk = rep["tabs"]["bookings"]
    assert bk["willSync"] is True
    assert "bookingAmount" in bk["missingHeaders"]
