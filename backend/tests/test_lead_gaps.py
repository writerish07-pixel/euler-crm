"""Showroom Admin delivery-gap flags — exact missing docs / entries."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "lead_gaps_unit")
os.environ.setdefault("JWT_SECRET", "lead-gaps-secret-32chars!!xxxx")

import lead_gaps  # noqa: E402


def test_new_and_delivered_are_not_flagged():
    assert lead_gaps.flags_for_lead({"currentStatus": "New", "executive": ""}) == []
    assert lead_gaps.flags_for_lead({"currentStatus": "Delivered", "executive": ""}) == []
    assert lead_gaps.flags_for_lead({"currentStatus": "Contacted", "dealCancelled": True}) == []


def test_open_lead_lists_each_missing_item():
    flags = lead_gaps.flags_for_lead({
        "currentStatus": "Contacted",
        "accountStatus": "Active",
        "customerType": "Individual",
        "interestedModel": "",
        "executive": "",
        "exShowroom": 0,
    }, kinds=set())
    codes = [f["code"] for f in flags]
    assert "executive" in codes
    assert "vehicle" in codes
    assert "kyc" in codes
    assert "deal_sheet" in codes
    assert "price" in codes
    assert any("Aadhaar" in f["message"] for f in flags)
    assert any("Deal sheet" in f["message"] for f in flags)
    assert "booking" not in codes


def test_ready_to_book_when_docs_and_price_are_in():
    flags = lead_gaps.flags_for_lead({
        "currentStatus": "Contacted",
        "executive": "Amit",
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "exShowroom": 785000,
        "priceStructureSaved": True,
        "customerType": "Individual",
    }, kinds={"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"})
    assert [f["code"] for f in flags] == ["booking"]
    assert flags[0]["message"] == "Not booked yet"


def test_booked_file_flags_outstanding_chassis_and_delivery_steps():
    flags = lead_gaps.flags_for_lead({
        "currentStatus": "Booked",
        "bookingDate": "2026-10-01",
        "executive": "Amit",
        "interestedModel": "Turbo Max",
        "exShowroom": 785000,
        "priceStructureSaved": True,
        "customerOutstanding": 5000,
        "customerType": "Individual",
        "oemExtraSupportReceived": 7000,
    }, kinds={"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet"})
    messages = [f["message"] for f in flags]
    assert any("OEM Extra Support proof" in m for m in messages)
    assert any("outstanding" in m.lower() for m in messages)
    assert any("Chassis" in m for m in messages)
    assert any("Insurance not marked" in m for m in messages)
    assert any("Insurance copy" in m for m in messages)
    assert any("RTO / Registration copy" in m for m in messages)
    assert any("PDI" in m for m in messages)
