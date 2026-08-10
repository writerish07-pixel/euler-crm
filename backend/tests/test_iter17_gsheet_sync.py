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
        if ":" in a1 and a1.replace(":", "").isdigit():          # e.g. 1:1 or 1:5
            lo, hi = (int(x) for x in a1.split(":"))
            out = [list(r) for r in grid[lo - 1:hi]]
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
    """EXACT structure of the live Euler Master (2).xlsx workbook:
    real tab names, real header text, real column order — including the Lead
    Register whose real database header is on ROW 3 starting at column J, with
    rows 1-2 being the SEARCH/helper area the CRM must never write into."""
    return {
        "Lead Register": [
            # row 1 = search/helper header, row 2 = helper data, row 3 = REAL header
            ["SEARCH", "Lead ID", "Mobile", "Customer Name",
             "\u2192 Use CRM menu > Search Lead, or filter column below"],
            ["LD26000001", "2026-08-08", "First Real Lead", "9800000001", "Walk-in",
             "Turbo Max", "City (PV)", "", "New"],
            ["LD26000008", "2026-07-04", "Sher Singh", "7023644243", "Phone", "Hi-Load",
             "XR (PV)", "Payal", "New",
             "Lead ID", "Created Date", "Customer Name", "Mobile", "Alternate Mobile",
             "Village", "City", "Lead Source", "Interested Model", "Variant", "Executive",
             "Current Status", "Priority", "Budget", "Last Activity", "Next Follow-up Date",
             "Next Follow-up Time", "Booking Date", "Booking Amount", "Finance Required",
             "Exchange Required", "Delivery Status", "Delivery Date", "Outstanding Amount",
             "Remarks", "Last Updated", "Last Updated By", "Account Status", "Closed Date",
             "Close Reason", "Final Outstanding", "Closed By", "Close Timestamp",
             "Ex Showroom", "RTO", "Insurance Amount", "Accessories Amount",
             "Handling Charges", "TRC", "Fastag", "Extended Warranty", "Other Charges",
             "Gross Vehicle Cost", "Customer Payable", "Financer Name", "Finance File Number",
             "Last Payment Mode", "Total Received", "Consumer Discount", "Exchange Bonus",
             "Loyalty Bonus", "Referral Bonus", "DSA Bonus", "Additional Discount",
             "Total Discount", "OEM Scheme Amount", "Dealer Scheme Amount",
             "Customer Outstanding", "Company Outstanding", "Insurer Name", "Invoice Number",
             "Chassis Number", "Number Plate", "Insurance Status", "Registration Status",
             "Invoice Status", "RC Status", "PDI Status", "Dealer Earnings"],
        ],
        "Activity Log": [
            ["Activity ID", "Lead ID", "Date", "Time", "Activity Type", "Discussion",
             "Next Follow-up", "Reminder", "Executive", "Customer Name", "Mobile", "Model"],
        ],
        "Booking Register": [
            ["BookingID", "LeadID", "CustomerName", "Booking Date", "Vehicle Model", "Variant",
             "Booking Amount", "Finance Required", "Exchange Required", "CommercialSnapshotID",
             "Booking Status", "Created By", "Created Date", "Last Updated", "Amount Received",
             "Payment Mode", "Dealer Earnings"],
        ],
        "Payment Ledger": [
            ["Receipt Number", "Lead ID", "Customer Name", "Date", "Amount", "Payment Mode",
             "Narration", "Running Total", "Outstanding Balance", "Payment ID",
             "Financer Name", "Finance File Number"],
        ],
        "Delivery Tracker": [
            ["Lead ID", "Customer Name", "Insurance", "Registration", "Invoice", "Accessories",
             "RC", "Number Plate", "PDI", "Delivered", "Delivery Date", "Feedback",
             "Delivery ID", "Insurer Name", "Invoice Number", "Dealer Earnings", "Chassis Number"],
        ],
        "Finance Register": [
            ["File Number", "Lead ID", "Customer Name", "Financer", "Sanctioned Amount",
             "Received Against File", "File Outstanding", "Status", "Last Payment Date",
             "Last Updated"],
        ],
        "Insurance Register": [
            ["Entry ID", "Lead ID", "Customer Name", "Mobile", "Model", "Variant",
             "Insurance Company", "Policy Number", "Insurance Amount", "Payout Rate %",
             "Expected Payout", "Received Payout", "Payout Outstanding", "Status",
             "Policy Date", "Delivery Date", "Last Updated", "Remarks", "Insurance Executive"],
        ],
        "Scheme Claim Register": [
            ["Claim ID", "Source", "Booking ID", "Lead ID", "Customer", "Model", "Variant",
             "Booking Date", "Scheme Month", "Executive", "Component", "Component Key",
             "Consumer Discount", "Exchange Bonus", "Loyalty Bonus", "Referral Bonus",
             "DSA Discount", "Additional Discount", "Total Discount", "Dealer Discount",
             "OEM Discount", "DSA Approval", "Claim Required", "Eligible Claim", "Claim Amount",
             "Received Amount", "Claim Status", "Claim Reference Number", "Claim Submitted Date",
             "Claim Approved Date", "Claim Received Date", "Claim Ageing (Days)", "Claim Remarks"],
        ],
        "Dealer Earnings Register": [
            ["Lead ID", "Booking ID", "Customer Name", "Executive", "Team Leader", "Lead Source",
             "Vehicle Model", "Variant", "Colour", "Current Stage", "Booking Date",
             "Delivery Date", "Invoice Number", "Customer Payable", "OEM Eligible Scheme",
             "Customer Scheme Benefit Passed", "Dealer Scheme Retained", "Insurance Payout",
             "Customer Insurance Benefit Passed", "Dealer Insurance Income", "Finance Incentive",
             "Accessories Margin", "Exchange Margin", "Documentation Income", "Warranty Income",
             "RSA Income", "Referral Income", "Campaign Incentive", "Other Income",
             "TOTAL DEALER EARNINGS", "Claim Status", "Insurance Status", "Last Updated",
             "Created By", "Modified By", "Timestamp", "Remarks", "Consumer Retained",
             "Exchange Retained", "Loyalty Retained", "Referral Retained", "DSA Retained",
             "Scheme Retained Breakup", "Dealer Margin Gross (Incl GST)",
             "Dealer Margin GST (5%)", "Dealer Margin Net (Ex GST)", "",
             "OEM Extra Support Received", "OEM Extra Support Passed To Customer",
             "OEM Extra Support Retained"],
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
    """Data rows below the tab's header row (Lead Register's real header is row 3)."""
    return tabs[tab][3:] if tab == "Lead Register" else tabs[tab][1:]


def hdr(tabs, tab):
    return tabs[tab][2] if tab == "Lead Register" else tabs[tab][0]


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
    hdr = tabs["Lead Register"][2]
    assert row[hdr.index("Lead ID")] == "LD1"
    assert row[hdr.index("Customer Name")] == "Asha"
    assert row[hdr.index("Created Date")] == "2026-08-01"


@pytest.mark.asyncio
async def test_missing_id_header_refuses_to_write(sheet):
    """If the ID header is absent we must refuse, never guess a column."""
    tabs, values = sheet
    tabs["Lead Register"][2] = ["Created Date", "Customer Name", "Mobile"]
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
    hdr = tabs["Lead Register"][2]
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
        "activities": {"activityId": "AC1", "leadId": "LD1", "activityType": "Note"},
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
    """Real Lead Register columns: "Total Discount" is mapped but may hold a sheet
    formula; "Last Activity" and "Registration Status" are real columns the CRM does
    not own. None of them may be touched."""
    tabs, _ = sheet
    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha", "currentStatus": "New"})
    hdr = tabs["Lead Register"][2]
    row = tabs["Lead Register"][3]
    row[hdr.index("Total Discount")] = "=BF4+BG4+BH4"        # sheet formula, mapped column
    row[hdr.index("Last Activity")] = "called customer"       # staff input, unmapped
    row[hdr.index("Registration Status")] = "Pending RTO"     # dealership-owned, unmapped

    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha Devi",
                                 "currentStatus": "Delivered", "totalDiscount": 99999})
    row = tabs["Lead Register"][3]
    assert row[hdr.index("Total Discount")] == "=BF4+BG4+BH4", "formula in mapped column overwritten"
    assert row[hdr.index("Last Activity")] == "called customer", "unmapped staff column altered"
    assert row[hdr.index("Registration Status")] == "Pending RTO", "unmapped column altered"
    assert row[hdr.index("Customer Name")] == "Asha Devi", "normal cell should still update"
    assert row[hdr.index("Current Status")] == "Delivered"


@pytest.mark.asyncio
async def test_search_helper_area_never_touched(sheet):
    """Lead Register rows 1-2 (cols A:I) are the SEARCH/helper area. CRM writes
    target the real table at row 3+ / column J+ and must leave A:I untouched."""
    tabs, _ = sheet
    before_r1 = list(tabs["Lead Register"][0])
    before_r2 = list(tabs["Lead Register"][1])
    await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "New Name",
                                 "currentStatus": "Booked"})
    await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "Newer Name"})
    assert tabs["Lead Register"][0] == before_r1, "search header row modified"
    assert tabs["Lead Register"][1] == before_r2, "search helper data row modified"
    # the helper row 2 also contains 'LD26000001' in col A — it must NOT be matched as
    # the target row; the real record goes below the row-3 header.
    hdr = tabs["Lead Register"][2]
    data = rows(tabs, "Lead Register")
    assert len(data) == 1
    assert data[0][hdr.index("Lead ID")] == "LD26000001"
    assert data[0][hdr.index("Customer Name")] == "Newer Name"


@pytest.mark.asyncio
async def test_partial_update_does_not_blank_other_fields(sheet):
    tabs, _ = sheet
    await gsheets.sync("leads", {"leadId": "LD1", "customerName": "Asha",
                                 "mobile": "9000000001", "executive": "Amit"})
    await gsheets.sync("leads", {"leadId": "LD1", "currentStatus": "Booked"})
    hdr = tabs["Lead Register"][2]
    row = tabs["Lead Register"][3]
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
    hdr = tabs["Dealer Earnings Register"][0]
    row = rows(tabs, "Dealer Earnings Register")[0]
    assert row[hdr.index("Dealer Margin Net (Ex GST)")] == 10884.35   # via alias
    assert row[hdr.index("Customer Insurance Benefit Passed")] == 500  # NOT Dealer Insurance Income
    assert row[hdr.index("TOTAL DEALER EARNINGS")] == 11384.35


@pytest.mark.asyncio
async def test_finance_maps_to_real_headers(sheet):
    """Finance Register headers differ substantially from CRM field names
    (File Number / Financer / Sanctioned Amount / Received Against File /
    File Outstanding) — all must resolve through explicit aliases."""
    tabs, _ = sheet
    await gsheets.sync("finance", {"financeFileNumber": "FF1", "leadId": "LD1",
                                   "financerName": "HDFC", "committedAmount": 200000,
                                   "disbursedAmount": 50000, "financeOutstanding": 150000,
                                   "status": "Partial"})
    fh = tabs["Finance Register"][0]
    row = rows(tabs, "Finance Register")[0]
    assert row[fh.index("File Number")] == "FF1"
    assert row[fh.index("Financer")] == "HDFC"
    assert row[fh.index("Sanctioned Amount")] == 200000
    assert row[fh.index("Received Against File")] == 50000
    assert row[fh.index("File Outstanding")] == 150000


@pytest.mark.asyncio
async def test_exchange_is_intentionally_unmapped_no_tab_created(sheet):
    """The workbook has no Exchange Register. We must NOT create one — exchange is
    declared intentionally unmapped and carried by Lead/Dealer Earnings registers."""
    tabs, _ = sheet
    assert "exchange" in gsheets.INTENTIONALLY_UNMAPPED
    assert "exchange" not in gsheets.SYNC_MAP
    res = await gsheets.sync("exchange", {"leadId": "LD1"})
    assert res["ok"] is False and res["operation"] == "error"
    assert "Exchange Register" not in tabs


# ---------------------------------------------------------------- preflight
@pytest.mark.asyncio
async def test_preflight_reports_mapping_and_gaps(sheet):
    tabs, _ = sheet
    tabs["Booking Register"][0] = ["BookingID", "LeadID"]   # deliberately narrow
    gsheets.invalidate_header_cache()
    rep = gsheets.preflight()
    assert rep["enabled"] is True
    assert rep["tabs"]["leads"]["willSync"] is True
    assert rep["tabs"]["leads"]["resolved"]["leadId"] == "J"
    assert rep["tabs"]["leads"]["headerRow"] == 3
    bk = rep["tabs"]["bookings"]
    assert bk["willSync"] is True
    assert "bookingAmount" in bk["missingHeaders"]
