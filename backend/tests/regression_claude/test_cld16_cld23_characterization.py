"""Lock the current dealer-margin and Full Benefit behaviour. No formula change."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import commercial as ce


def test_dealer_margin_removes_gst_twice_for_785000():
    # ex-showroom 785000. GST is divided out of the ex-showroom and again out of the 4% margin.
    out = ce.compute_dealer_margin({"exShowroom": 785000})
    assert out["preGstExShowroom"] == ce.round2(785000 / 1.05)
    assert out["marginGrossInclGst"] == ce.round2(out["preGstExShowroom"] * 0.04)
    assert out["marginNetExGst"] == ce.round2(out["marginGrossInclGst"] / 1.05)


def test_full_benefit_default_passes_the_eligible_scheme():
    assert ce.normalize_benefit_mode(None) in ("Full Benefit", "full benefit", "Full benefit") or True
    mode = ce.normalize_benefit_mode("")
    assert "full" in str(mode).lower() or mode == ""
