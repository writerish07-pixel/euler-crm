"""Global pytest guards — never touch the live Google Sheet from tests.

Cloud Agent / CI often inherit production GSHEET_ID + service-account credentials.
Tests mock Mongo (mongomock) but historically still called sheet_sync against the
real Euler Master workbook, which refilled Lead Register with ITER24 / Step Lock
rows after every go-live reset.
"""
import os

import pytest


@pytest.fixture(autouse=True)
def _block_live_google_sheet_writes(monkeypatch):
    # Force test environment flags even when the host exported production GSHEET_ID.
    monkeypatch.setenv("ENVIRONMENT", "test")
    # Keep whatever GSHEET_ID the host has — env_safety + mocks below stop writes.
    monkeypatch.delenv("GSHEET_ALLOW_TEST_WRITES", raising=False)

    async def _no_sync(entity, doc, *, entity_id=""):
        return {"ok": True, "skipped": True, "operation": "skipped",
                "reason": "pytest-autouse-mock", "entity": entity}

    async def _no_clear():
        return {"ok": True, "tabs": [], "clearedRanges": [], "reason": "pytest-autouse-mock"}

    async def _no_delete_lead_traces(lead_id):
        return {"ok": True, "operation": "skipped", "reason": "pytest-autouse-mock",
                "leadId": lead_id, "rowsDeleted": 0, "tabs": []}

    async def _no_delete_entity_row(entity, id_value):
        return {"ok": True, "operation": "skipped", "reason": "pytest-autouse-mock",
                "entity": entity, "entityId": id_value, "rowsDeleted": 0}

    # Import inside fixture so each test module's server/gsheets binding is patched.
    try:
        import server
        monkeypatch.setattr(server, "sheet_sync", _no_sync, raising=False)
    except Exception:
        pass
    try:
        import gsheets
        monkeypatch.setattr(gsheets, "sync", _no_sync, raising=False)
        monkeypatch.setattr(gsheets, "clear_operational_register_rows", _no_clear, raising=False)
        monkeypatch.setattr(gsheets, "delete_lead_traces", _no_delete_lead_traces, raising=False)
        monkeypatch.setattr(gsheets, "delete_entity_row", _no_delete_entity_row, raising=False)
    except Exception:
        pass
    yield
