"""Text written to the Google Sheet mirror is never run as a formula."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gsheets  # noqa: E402


def test_formula_like_text_is_kept_as_text():
    formula = '=HYPERLINK("http://x","y")'
    assert gsheets._sheet_value(formula) == "'" + formula
    assert gsheets._sheet_value("@import") == "'@import"
    assert gsheets._sheet_value("+91 98765 43210") == "'+91 98765 43210"
    assert gsheets._sheet_value("-cash adjusted") == "'-cash adjusted"


def test_ordinary_values_are_unchanged():
    assert gsheets._sheet_value("Ramesh Gupta") == "Ramesh Gupta"
    assert gsheets._sheet_value("-5000") == "-5000"
    assert gsheets._sheet_value(-5000) == -5000
    assert gsheets._sheet_value(150000.5) == 150000.5
    assert gsheets._sheet_value("") == ""
    assert gsheets._sheet_value(None) == ""
    assert gsheets._sheet_value(True) == "Yes"
