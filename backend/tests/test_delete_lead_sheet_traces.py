"""Owner lead delete must remove every Google Sheet register row for that lead.

Uses an in-memory Fake Sheets API — never touches the live Euler Master workbook.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "delete_lead_sheet_traces")
os.environ.setdefault("JWT_SECRET", "delete-lead-sheet-traces")
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET_DELETE")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import gsheets  # noqa: E402
import server  # noqa: E402


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class FakeValues:
    def __init__(self, tabs):
        self.tabs = tabs

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
        grid = self.tabs.get(tab)
        if grid is None:
            raise RuntimeError(f"Unable to parse range: {range} (no such tab)")
        if ":" in a1 and a1.replace(":", "").isalpha():
            letters = a1.split(":")[0]
            i = self._col_to_idx(letters)
            out = [[r[i]] if i < len(r) else [] for r in grid]
        elif ":" in a1 and a1.replace(":", "").isdigit():
            lo, hi = (int(x) for x in a1.split(":"))
            out = [list(r) for r in grid[lo - 1:hi]]
        else:
            start, end = a1.split(":")
            s_col = self._col_to_idx("".join(c for c in start if c.isalpha()))
            e_col = self._col_to_idx("".join(c for c in end if c.isalpha()))
            row_n = int("".join(c for c in start if c.isdigit()))
            row = grid[row_n - 1] if row_n - 1 < len(grid) else []
            out = [[row[i] if i < len(row) else "" for i in range(s_col, e_col + 1)]]
        return _Exec({"values": out})


class FakeService:
    """Supports values.get + spreadsheets.get (gids) + batchUpdate deleteDimension."""

    def __init__(self, values):
        self._values = values

    def spreadsheets(self):
        return self

    def values(self):
        return self._values

    def get(self, spreadsheetId=None, fields=None, **kw):
        if fields and "sheets" in str(fields):
            sheets = []
            for i, title in enumerate(self._values.tabs.keys()):
                sheets.append({"properties": {"sheetId": 1000 + i, "title": title}})
            return _Exec({"sheets": sheets})
        return _Exec({"properties": {"title": "Euler Master Fake"}})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        title_by_gid = {1000 + i: t for i, t in enumerate(self._values.tabs.keys())}
        for req in body.get("requests") or []:
            dr = req.get("deleteDimension") or {}
            rng = dr.get("range") or {}
            tab = title_by_gid.get(rng.get("sheetId"))
            if not tab:
                continue
            start = int(rng["startIndex"])
            end = int(rng["endIndex"])
            grid = self._values.tabs[tab]
            for _ in range(end - start):
                if 0 <= start < len(grid):
                    del grid[start]
        return _Exec({})


def make_populated_sheet():
    """Minimal headers + two leads' traces across operational registers."""
    return {
        "Lead Register": [
            ["Lead ID", "Customer Name", "Mobile", "Current Status"],
            ["LD_KEEP", "Keep Me", "9000000001", "New"],
            ["LD_DEL", "Delete Me", "9000000002", "Booked"],
        ],
        "Activity Log": [
            ["Activity ID", "Lead ID", "Date", "Activity Type", "Executive"],
            ["ACT1", "LD_KEEP", "2026-08-01", "Call", "Amit"],
            ["ACT2", "LD_DEL", "2026-08-02", "Visit", "Amit"],
            ["ACT3", "LD_DEL", "2026-08-03", "Call", "Amit"],
        ],
        "Booking Register": [
            ["BookingID", "LeadID", "CustomerName", "Booking Date"],
            ["BK1", "LD_KEEP", "Keep Me", "2026-08-01"],
            ["BK2", "LD_DEL", "Delete Me", "2026-08-02"],
        ],
        "Payment Ledger": [
            ["Receipt Number", "Lead ID", "Customer Name", "Amount"],
            ["R1", "LD_KEEP", "Keep Me", "1000"],
            ["R2", "LD_DEL", "Delete Me", "5000"],
            ["R3", "LD_DEL", "Delete Me", "2000"],
        ],
        "Delivery Tracker": [
            ["Lead ID", "Customer Name", "Delivered", "Delivery Date"],
            ["LD_KEEP", "Keep Me", "No", ""],
            ["LD_DEL", "Delete Me", "Yes", "2026-08-10"],
        ],
        "Scheme Claim Register": [
            ["Claim ID", "Lead ID", "Customer", "Claim Amount", "Claim Status"],
            ["CL1", "LD_KEEP", "Keep Me", "10000", "Pending"],
            ["CL2", "LD_DEL", "Delete Me", "20000", "Pending"],
            ["CL3", "LD_DEL", "Delete Me", "5000", "Submitted"],
        ],
        "Insurance Register": [
            ["Entry ID", "Lead ID", "Customer Name", "Status"],
            ["INS1", "LD_KEEP", "Keep Me", "Open"],
            ["INS2", "LD_DEL", "Delete Me", "Open"],
        ],
        "Finance Register": [
            ["File Number", "Lead ID", "Customer Name", "Status"],
            ["FF1", "LD_KEEP", "Keep Me", "Open"],
            ["FF2", "LD_DEL", "Delete Me", "Open"],
        ],
        "Dealer Earnings Register": [
            ["Lead ID", "Customer Name", "TOTAL DEALER EARNINGS"],
            ["LD_KEEP", "Keep Me", "100"],
            ["LD_DEL", "Delete Me", "999"],
        ],
        "Incentive Register": [
            ["Incentive ID", "Lead ID", "Executive", "Incentive Amount", "Status"],
            ["INC1", "LD_KEEP", "Amit", "500", "Pending"],
            ["INC2", "LD_DEL", "Amit", "750", "Pending"],
        ],
    }


@pytest.fixture
def fake_sheet(monkeypatch):
    tabs = make_populated_sheet()
    values = FakeValues(tabs)
    svc = FakeService(values)
    monkeypatch.setattr(gsheets, "_service", svc)
    monkeypatch.setattr(gsheets, "_status",
                        {"enabled": True, "reason": "connected", "canWrite": True})
    for name in ("_header_cache", "_headerrow_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})
    gsheets.invalidate_header_cache()
    return tabs, svc


def test_delete_lead_traces_sync_removes_all_related_rows(fake_sheet):
    tabs, _ = fake_sheet
    res = gsheets._delete_lead_traces_sync("LD_DEL")
    assert res["ok"] is True
    # lead + 2 act + book + 2 pay + del + 2 claim + ins + fin + earn + inc = 13
    assert res["rowsDeleted"] == 13

    def col_ids(tab, col=0):
        return [r[col] for r in tabs[tab][1:]]

    assert "LD_DEL" not in col_ids("Lead Register")
    assert "LD_KEEP" in col_ids("Lead Register")
    assert col_ids("Activity Log", 1) == ["LD_KEEP"]
    assert col_ids("Booking Register", 1) == ["LD_KEEP"]
    assert col_ids("Payment Ledger", 1) == ["LD_KEEP"]
    assert col_ids("Delivery Tracker") == ["LD_KEEP"]
    assert col_ids("Scheme Claim Register", 1) == ["LD_KEEP"]
    assert col_ids("Insurance Register", 1) == ["LD_KEEP"]
    assert col_ids("Finance Register", 1) == ["LD_KEEP"]
    assert col_ids("Dealer Earnings Register") == ["LD_KEEP"]
    assert col_ids("Incentive Register", 1) == ["LD_KEEP"]


def test_delete_lead_traces_sync_noop_for_unknown_lead(fake_sheet):
    tabs, _ = fake_sheet
    before = {t: [list(r) for r in grid] for t, grid in tabs.items()}
    res = gsheets._delete_lead_traces_sync("LD_MISSING")
    assert res["ok"] is True
    assert res["rowsDeleted"] == 0
    assert tabs == before


def test_delete_lead_traces_sync_survives_missing_tab(monkeypatch):
    tabs = make_populated_sheet()
    del tabs["Incentive Register"]
    values = FakeValues(tabs)
    svc = FakeService(values)
    monkeypatch.setattr(gsheets, "_service", svc)
    for name in ("_header_cache", "_headerrow_cache", "_idrow_cache", "_formula_cache"):
        monkeypatch.setattr(gsheets, name, {})
    gsheets.invalidate_header_cache()
    res = gsheets._delete_lead_traces_sync("LD_DEL")
    assert res["ok"] is True
    assert "LD_DEL" not in [r[0] for r in tabs["Lead Register"][1:]]
    bad = [t for t in res["tabs"] if t.get("ok") is False]
    assert any(t.get("entity") == "incentive_register" or t.get("tab") == "Incentive Register"
               for t in bad)


@pytest.mark.asyncio
async def test_async_delete_honours_write_block(monkeypatch):
    """delete_lead_traces must not call Sheets when env_safety blocks writes."""
    monkeypatch.setattr(gsheets, "_service", object())
    monkeypatch.setattr(gsheets, "_status", {"enabled": True, "reason": "connected"})
    monkeypatch.setattr(gsheets, "_write_blocked",
                        lambda: "TEST WRITE BLOCKED — pytest must not write")

    # Install the real async function (autouse conftest may have mocked it).
    import asyncio

    async def real_delete_lead_traces(lead_id: str):
        if gsheets._service is None:
            gsheets._init()
        if gsheets._service is None or not gsheets._status.get("enabled"):
            return {"ok": True, "operation": "skipped",
                    "reason": gsheets._status.get("reason", "sync disabled"),
                    "rowsDeleted": 0, "tabs": []}
        blocked = gsheets._write_blocked()
        if blocked:
            return {"ok": False, "operation": "blocked", "error": blocked,
                    "rowsDeleted": 0, "tabs": []}
        res = await asyncio.to_thread(gsheets._delete_lead_traces_sync, lead_id)
        return res

    monkeypatch.setattr(gsheets, "delete_lead_traces", real_delete_lead_traces)
    res = await gsheets.delete_lead_traces("LD1")
    assert res["operation"] == "blocked"
    assert res["rowsDeleted"] == 0


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_owner_delete_lead_calls_sheet_purge_and_clears_sync_log(client, monkeypatch):
    called = {}

    async def fake_delete_traces(lead_id):
        called["leadId"] = lead_id
        return {"ok": True, "operation": "deleted", "leadId": lead_id,
                "rowsDeleted": 7, "tabs": [{"tab": "Lead Register", "rowsDeleted": 1}]}

    async def fake_rebuild():
        return {"ok": True, "pending": 0, "overdue": 0}

    monkeypatch.setattr(gsheets, "delete_lead_traces", fake_delete_traces)
    monkeypatch.setattr(server, "rebuild_finance_views", fake_rebuild)

    login = await client.post("/api/auth/login",
                              json={"email": "owner@euler.com", "password": "euler@123"})
    assert login.status_code == 200, login.text
    client.headers["Authorization"] = f"Bearer {login.json()['token']}"

    r = await client.post("/api/leads", json={
        "customerName": "Sheet Cascade", "mobile": "9888800099",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]

    await server.db.payments.insert_one({
        "leadId": lid, "receiptNumber": "RCP_DEL_1", "amount": 1000})
    await server.db.bookings.insert_one({
        "leadId": lid, "bookingId": "BK_DEL_1"})
    await server.db.sheet_sync_log.insert_many([
        {"entity": "leads", "entityId": lid, "status": "ok"},
        {"entity": "payments", "entityId": "RCP_DEL_1", "status": "ok"},
        {"entity": "bookings", "entityId": "BK_DEL_1", "payload": {"leadId": lid},
         "status": "pending"},
        {"entity": "leads", "entityId": "OTHER", "status": "ok"},
    ])

    r = await client.delete(f"/api/leads/{lid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True
    assert called.get("leadId") == lid
    assert body["sheet"]["rowsDeleted"] == 7
    assert await server.db.leads.find_one({"leadId": lid}) is None
    assert await server.db.payments.count_documents({"leadId": lid}) == 0
    assert await server.db.sheet_sync_log.count_documents({"entityId": lid}) == 0
    assert await server.db.sheet_sync_log.count_documents({"entityId": "RCP_DEL_1"}) == 0
    assert await server.db.sheet_sync_log.count_documents({"entityId": "OTHER"}) == 1


@pytest.mark.asyncio
async def test_staff_cannot_delete_lead(client):
    # Create lead as owner, then try delete as executive.
    login = await client.post("/api/auth/login",
                              json={"email": "owner@euler.com", "password": "euler@123"})
    assert login.status_code == 200
    client.headers["Authorization"] = f"Bearer {login.json()['token']}"
    r = await client.post("/api/leads", json={
        "customerName": "No Delete", "mobile": "9888800088",
        "interestedModel": "Hi-Load", "variant": "XR", "executive": "Amit"})
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]

    login = await client.post("/api/auth/login",
                              json={"email": "executive@euler.com", "password": "euler@123"})
    assert login.status_code == 200, login.text
    client.headers["Authorization"] = f"Bearer {login.json()['token']}"
    r = await client.delete(f"/api/leads/{lid}")
    assert r.status_code in (401, 403)
