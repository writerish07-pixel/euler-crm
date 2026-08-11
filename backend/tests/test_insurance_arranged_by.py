"""Insurance arranged by Self vs Dealer — payable + payout earnings."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "insurance_arranged_by")
os.environ.setdefault("JWT_SECRET", "insurance-arranged-by-secret")

import commercial as ce  # noqa: E402


def test_normalize_insurance_arranged_by():
    assert ce.normalize_insurance_arranged_by(None) == "dealer"
    assert ce.normalize_insurance_arranged_by("dealer") == "dealer"
    assert ce.normalize_insurance_arranged_by("Self") == "self"
    assert ce.normalize_insurance_arranged_by("customer") == "self"


def test_self_insurance_excluded_from_customer_payable():
    dealer = ce.compute_commercial_totals({
        "exShowroom": 400000, "insurance": 10000, "insuranceArrangedBy": "dealer",
        "tcsApplicable": "No", "benefitMode": "No Benefit",
    })
    self_arr = ce.compute_commercial_totals({
        "exShowroom": 400000, "insurance": 10000, "insuranceArrangedBy": "self",
        "tcsApplicable": "No", "benefitMode": "No Benefit",
    })
    assert dealer["grossVehicleCost"] == 410000
    assert dealer["customerPayable"] == 410000
    assert self_arr["grossVehicleCost"] == 400000
    assert self_arr["customerPayable"] == 400000
    assert dealer["customerPayable"] - self_arr["customerPayable"] == 10000


def test_insurance_charge_helper():
    assert ce.insurance_charge_for_payable({"insurance": 5000}) == 5000
    assert ce.insurance_charge_for_payable(
        {"insurance": 5000, "insuranceArrangedBy": "self"}) == 0
