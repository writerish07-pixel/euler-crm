"""Preview/Production isolation + derived Finance report tabs.

Covers the Phase-1 write-guard (`env_safety`), the derived-tab writer
(`overwrite_report_tab`) used to rebuild Finance Pending / Finance Overdue, the
read-only workbook `inventory()`, and the duplicate-preserving ID reader that
backs duplicate/orphan detection in reconciliation.

The guard exists because preview and production share one service account: a
preview deploy pointing at the production GSHEET_ID must never WRITE to it.
Reads stay allowed so preview still renders real data.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import gsheets  # noqa: E402

PROD_ID = "PROD_SHEET_ID"
TEST_ID = "PREVIEW_SHEET_ID"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for k in ("ENVIRONMENT", "PRODUCTION_GSHEET_ID"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("GSHEET_ID", PROD_ID)
    yield


def set_env(monkeypatch, environment, gsheet_id, prod_id=PROD_ID):
    monkeypatch.setenv("ENVIRONMENT", environment)
    monkeypatch.setenv("GSHEET_ID", gsheet_id)
    monkeypatch.setenv("PRODUCTION_GSHEET_ID", prod_id)


# ------------------------------------------------------------------ env_safety
@pytest.mark.parametrize("environment", ["preview", "dev", "development", "test", "staging"])
def test_preview_pointing_at_production_sheet_is_write_blocked(monkeypatch, environment):
    """THE defect this guards: a preview deploy writing into the live workbook."""
    set_env(monkeypatch, environment, PROD_ID)
    s = gsheets.env_safety()
    assert s["writeBlocked"] is True
    assert s["isPreview"] is True
    assert s["pointingAtProduction"] is True
    assert "PREVIEW WRITE BLOCKED" in s["blockReason"]


def test_preview_with_its_own_sheet_is_allowed(monkeypatch):
    set_env(monkeypatch, "preview", TEST_ID)
    s = gsheets.env_safety()
    assert s["writeBlocked"] is False
    assert s["blockReason"] is None
    assert s["pointingAtProduction"] is False


def test_production_pointing_at_production_sheet_is_allowed(monkeypatch):
    set_env(monkeypatch, "production", PROD_ID)
    s = gsheets.env_safety()
    assert s["writeBlocked"] is False
    assert s["pointingAtProduction"] is True


def test_production_pointing_at_the_wrong_sheet_is_blocked(monkeypatch):
    """Symmetric guard: production must not silently write into a scratch sheet."""
    set_env(monkeypatch, "production", TEST_ID)
    s = gsheets.env_safety()
    assert s["writeBlocked"] is True
    assert "PRODUCTION WRITE BLOCKED" in s["blockReason"]


def test_unset_environment_does_not_block(monkeypatch):
    """Absent configuration must not brick an existing working deploy."""
    monkeypatch.setenv("GSHEET_ID", PROD_ID)
    s = gsheets.env_safety()
    assert s["writeBlocked"] is False
    assert s["environment"] == "unset"


def test_env_safety_never_leaks_credentials(monkeypatch):
    set_env(monkeypatch, "preview", PROD_ID)
    blob = str(gsheets.env_safety())
    assert "private_key" not in blob and "BEGIN" not in blob


# ------------------------------------------------- write paths honour the guard
class RecordingValues:
    """Minimal Sheets values() surface that records every mutating call."""

    def __init__(self):
        self.cleared, self.updated, self.appended, self.batch = [], [], [], []

    def get(self, spreadsheetId=None, range=None, **kw):
        return _Exec({"values": []})

    def clear(self, spreadsheetId=None, range=None, body=None, **kw):
        self.cleared.append(range)
        return _Exec({})

    def update(self, spreadsheetId=None, range=None, body=None, **kw):
        self.updated.append((range, body["values"]))
        return _Exec({})

    def append(self, spreadsheetId=None, range=None, body=None, **kw):
        self.appended.append(range)
        return _Exec({})

    def batchUpdate(self, spreadsheetId=None, body=None, **kw):
        self.batch.append(body)
        return _Exec({})


class _Exec:
    def __init__(self, res):
        self._res = res

    def execute(self):
        return self._res


class RecordingService:
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


@pytest.fixture
def recording(monkeypatch):
    vals = RecordingValues()
    monkeypatch.setattr(gsheets, "_service", RecordingService(vals))
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=True, canWrite=True))
    return vals


@pytest.mark.asyncio
async def test_sync_is_blocked_and_writes_nothing_in_preview(monkeypatch, recording):
    set_env(monkeypatch, "preview", PROD_ID)
    res = await gsheets.sync("leads", {"leadId": "LD26000001", "customerName": "X"})
    assert res["ok"] is False
    assert res["operation"] == "blocked"
    assert recording.appended == [] and recording.batch == [] and recording.updated == []


@pytest.mark.asyncio
async def test_overwrite_report_tab_is_blocked_in_preview(monkeypatch, recording):
    set_env(monkeypatch, "preview", PROD_ID)
    ok = await gsheets.overwrite_report_tab("Finance Pending", [["x"]])
    assert ok is False
    assert recording.cleared == [] and recording.updated == []


@pytest.mark.asyncio
async def test_sync_masters_is_blocked_in_preview(monkeypatch, recording):
    set_env(monkeypatch, "preview", PROD_ID)
    assert await gsheets.sync_masters([["a"]]) is False


@pytest.mark.asyncio
async def test_backfill_is_blocked_in_preview(monkeypatch, recording):
    set_env(monkeypatch, "preview", PROD_ID)
    res = await gsheets.backfill({"leads": [{"leadId": "LD1"}]})
    assert res["ok"] is False
    assert res["canWrite"] is False
    assert recording.appended == [] and recording.batch == []


@pytest.mark.asyncio
async def test_writes_go_through_when_environment_is_production(monkeypatch, recording):
    """The guard must not block a correctly-configured production deploy."""
    set_env(monkeypatch, "production", PROD_ID)
    ok = await gsheets.overwrite_report_tab("Finance Pending", [["title"], ["refreshed"], ["hdr"]])
    assert ok is True
    assert recording.cleared and recording.updated


def test_status_reports_env_block_without_claiming_a_google_failure(monkeypatch, recording):
    set_env(monkeypatch, "preview", PROD_ID)
    st = gsheets.status()
    assert st["canWrite"] is False
    assert st["errorCode"] == "env_write_blocked"
    assert st["envSafety"]["writeBlocked"] is True
    # Must NOT tell the user to re-share the sheet — the credential is fine.
    assert "share the sheet" not in st["reason"].lower()


# ------------------------------------------------------ derived-tab full mirror
@pytest.mark.asyncio
async def test_overwrite_report_tab_clears_before_writing(monkeypatch, recording):
    """Derived tabs are projections: stale rows must disappear, not accumulate."""
    set_env(monkeypatch, "production", PROD_ID)
    rows = [["Finance Pending — open files"], ["Refreshed: now"], ["File Number", "Lead ID"],
            ["FIN-1", "LD26000001"]]
    assert await gsheets.overwrite_report_tab("Finance Pending", rows) is True
    assert len(recording.cleared) == 1
    assert "Finance Pending" in recording.cleared[0]
    rng, values = recording.updated[0]
    assert rng == "'Finance Pending'!A1"
    assert values == rows


def test_finance_report_tab_names_match_the_live_workbook():
    """These tabs exist in Euler Master and are rewritten wholesale — the names
    must match exactly or the write lands on a new//wrong tab."""
    assert gsheets.FINANCE_PENDING_TAB == "Finance Pending"
    assert gsheets.FINANCE_OVERDUE_TAB == "Finance Overdue"


# ------------------------------------------------- duplicate-preserving ID read
def test_read_id_column_list_preserves_duplicates_and_skips_header(monkeypatch):
    class V:
        def get(self, spreadsheetId=None, range=None, **kw):
            return _Exec({"values": [["Booking ID"], ["BK1"], ["BK2"], ["BK1"], [""], ["BK3"]]})

    monkeypatch.setattr(gsheets, "_service", RecordingService(V()))
    lst = gsheets._read_id_column_list("Booking Register", 0, header_row=1)
    assert lst == ["BK1", "BK2", "BK1", "BK3"]          # duplicate retained
    assert gsheets._read_id_column("Booking Register", 0, header_row=1) == {"BK1", "BK2", "BK3"}


def test_read_id_column_list_respects_a_row_3_header(monkeypatch):
    """Lead Register's real header is on row 3 — rows 1-2 are the search/helper area."""
    class V:
        def get(self, spreadsheetId=None, range=None, **kw):
            return _Exec({"values": [["SEARCH"], ["LD_HELPER"], ["Lead ID"], ["LD26000001"]]})

    monkeypatch.setattr(gsheets, "_service", RecordingService(V()))
    assert gsheets._read_id_column_list("Lead Register", 0, header_row=3) == ["LD26000001"]
