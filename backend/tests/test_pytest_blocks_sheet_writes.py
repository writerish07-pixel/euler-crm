"""Guard: pytest must never write to the live Google Sheet."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gsheets  # noqa: E402


def test_pytest_blocks_sheet_writes_even_with_production_gsheet_id(monkeypatch):
    monkeypatch.setenv("GSHEET_ID", "fake-production-sheet-id")
    monkeypatch.setenv("PRODUCTION_GSHEET_ID", "fake-production-sheet-id")
    monkeypatch.delenv("GSHEET_ALLOW_TEST_WRITES", raising=False)
    # PYTEST_CURRENT_TEST is set automatically by pytest while this runs.
    safety = gsheets.env_safety()
    assert safety["writeBlocked"] is True
    assert "TEST WRITE BLOCKED" in (safety["blockReason"] or "")


def test_explicit_opt_in_allows_test_sheet_writes(monkeypatch):
    monkeypatch.setenv("GSHEET_ID", "disposable-test-sheet")
    monkeypatch.setenv("GSHEET_ALLOW_TEST_WRITES", "1")
    monkeypatch.delenv("PRODUCTION_GSHEET_ID", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "test")
    safety = gsheets.env_safety()
    # Opt-in clears the pytest block; preview-vs-prod block does not apply without prod id match.
    assert safety["writeBlocked"] is False
