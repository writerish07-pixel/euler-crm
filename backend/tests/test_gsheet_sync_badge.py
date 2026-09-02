"""Top-bar Sync Error must not fire when the Euler Master sheet is connected.

A missing derived tab (Finance Pending) or a pending header used to set
lastWriteOk=false. Settings still said Live; the header screamed Sync Error.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gsheets  # noqa: E402


def _reset():
    gsheets._health.update({
        "lastWriteOk": None, "lastWriteAt": None, "lastError": None,
        "lastErrorClass": None, "hardFailure": False, "writes": 0, "failures": 0,
    })


def test_missing_finance_pending_tab_is_sheet_shape_not_a_hard_failure():
    assert gsheets.classify_write_error(
        "Unable to parse range: 'Finance Pending'!A1:Z10000"
    ) == "sheet_shape"


def test_missing_header_is_sheet_shape():
    assert gsheets.classify_write_error(
        "required ID header for 'leadId' not found in tab 'Lead Register'"
    ) == "sheet_shape"


def test_quota_and_permission_are_hard():
    assert gsheets.classify_write_error("Google returned 429 -- quota exceeded") == "quota"
    assert gsheets.classify_write_error("403 permission denied") == "permission"


def test_shape_miss_does_not_turn_the_badge_red():
    _reset()
    gsheets._mark_health(True)
    gsheets._mark_health(False, "Unable to parse range: 'Finance Overdue'!A1")
    assert gsheets._health["hardFailure"] is False
    assert gsheets._health["lastWriteOk"] is True
    assert gsheets._health["lastErrorClass"] == "sheet_shape"


def test_quota_does_turn_the_badge_red():
    _reset()
    gsheets._mark_health(True)
    gsheets._mark_health(False, "HttpError 429: Quota exceeded")
    assert gsheets._health["hardFailure"] is True
    assert gsheets._health["lastWriteOk"] is False
