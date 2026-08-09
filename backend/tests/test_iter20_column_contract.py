"""The Google Sheets column contract, locked against the LIVE workbook headers.

`live_headers.py` holds the real header rows of the nine operational registers, pulled
read-only from Euler Master. These tests assert that every field in SYNC_MAP resolves to
a real column, that no two fields collide onto one column, and that the 50 columns which
previously had a computed Mongo value but no mapping are now mapped.

If someone renames a header in the workbook, or adds a SYNC_MAP field that does not
exist there, these fail — which is the point: the CRM adapts to the sheet, never the
other way round.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("GSHEET_ID", "FAKE_SHEET")

import gsheets  # noqa: E402
from gsheets import HEADER_ALIASES, SYNC_MAP, _col_letter, _norm  # noqa: E402

from live_headers import LIVE_HEADERS  # noqa: E402

# Columns that had a computed Mongo value but no Sheet mapping before this change.
NEWLY_MAPPED = {
    "leads": ["closedDate", "closeReason", "finalOutstanding", "insuranceStatus",
              "registrationStatus", "invoiceStatus", "rcStatus", "pdiStatus"],
    "bookings": ["createdBy", "lastUpdated", "dealerTotalEarnings"],
    "deliveries": ["deliveryId", "dealerTotalEarnings"],
    "finance": ["lastPaymentDate", "lastUpdated"],
    "insurance": ["policyDate", "deliveryDate", "lastUpdated", "remarks"],
    "claims": ["bookingId", "schemeMonth", "executive", "consumerDiscount", "exchangeBonus",
               "loyaltyBonus", "referralBonus", "dsaDiscount", "additionalDiscount",
               "totalDiscount", "dealerDiscount", "oemDiscount", "claimRequired", "ageingDays"],
    "dealer_earnings": ["dealerMarginGrossInclGst", "dealerMarginGst", "consumerRetained",
                        "exchangeRetained", "loyaltyRetained", "referralRetained", "dsaRetained",
                        "schemeRetainedBreakup", "oemExtraSupportReceived", "oemExtraSupportPassed",
                        "leadSource", "claimStatus", "insuranceStatus", "lastUpdated",
                        "createdBy", "timestamp", "remarks"],
}


def resolve(tab, fields):
    """Same resolution the sync uses: exact normalised header, then explicit aliases."""
    _hr, headers = LIVE_HEADERS[tab]
    by_norm = {}
    for i, h in enumerate(headers):
        n = _norm(h)
        if n and n not in by_norm:
            by_norm[n] = i
    mapping, missing = {}, []
    for f in fields:
        idx = by_norm.get(_norm(f))
        if idx is None:
            for alias in HEADER_ALIASES.get(f, []):
                idx = by_norm.get(_norm(alias))
                if idx is not None:
                    break
        if idx is None:
            missing.append(f)
        else:
            mapping[f] = idx
    return mapping, missing


@pytest.mark.parametrize("entity", sorted(SYNC_MAP))
def test_every_sync_field_resolves_to_a_real_column(entity):
    tab, _id_field, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][1], SYNC_MAP[entity][2]
    _mapping, missing = resolve(tab, fields)
    assert missing == [], f"{tab}: no live column for {missing}"


@pytest.mark.parametrize("entity", sorted(SYNC_MAP))
def test_no_two_fields_share_a_column(entity):
    """Guards the class of bug that once collapsed 'Customer Insurance Benefit Passed'
    onto 'Dealer Insurance Income' — two different columns, two different meanings."""
    tab, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][2]
    mapping, _ = resolve(tab, fields)
    seen = {}
    for f, idx in mapping.items():
        seen.setdefault(idx, []).append(f)
    collisions = {_col_letter(i): fs for i, fs in seen.items() if len(fs) > 1}
    assert collisions == {}, f"{tab}: fields collide on one column: {collisions}"


@pytest.mark.parametrize("entity", sorted(SYNC_MAP))
def test_stable_id_field_resolves(entity):
    tab, id_field, fields = SYNC_MAP[entity][0], SYNC_MAP[entity][1], SYNC_MAP[entity][2]
    mapping, _ = resolve(tab, fields)
    assert id_field in mapping, f"{tab}: stable ID '{id_field}' has no column — upsert impossible"


@pytest.mark.parametrize("entity,fields", sorted(NEWLY_MAPPED.items()))
def test_newly_mapped_columns_are_in_the_contract(entity, fields):
    declared = SYNC_MAP[entity][2]
    missing = [f for f in fields if f not in declared]
    assert missing == [], f"{entity}: newly-mapped fields absent from SYNC_MAP: {missing}"


@pytest.mark.parametrize("entity,fields", sorted(NEWLY_MAPPED.items()))
def test_newly_mapped_columns_resolve_live(entity, fields):
    tab = SYNC_MAP[entity][0]
    mapping, _ = resolve(tab, fields)
    unresolved = [f for f in fields if f not in mapping]
    assert unresolved == [], f"{tab}: newly-mapped fields do not resolve: {unresolved}"


def test_fifty_columns_were_added():
    """The audit found exactly 50 operational columns with an existing Mongo source."""
    assert sum(len(v) for v in NEWLY_MAPPED.values()) == 50


def test_lead_register_header_is_row_3_and_starts_at_column_J():
    """Rows 1-2 and columns A:I are the staff search/helper area — never written."""
    hr, headers = LIVE_HEADERS["Lead Register"]
    assert hr == 3
    assert headers[9] == "Lead ID"
    mapping, _ = resolve("Lead Register", SYNC_MAP["leads"][2])
    assert min(mapping.values()) >= 9, "a lead field resolved into the protected A:I area"
    assert _col_letter(mapping["leadId"]) == "J"


def test_helper_area_is_masked_in_the_fixture():
    """The A:I area holds live customer rows; the fixture must not carry them."""
    _hr, headers = LIVE_HEADERS["Lead Register"]
    assert all("masked" in h for h in headers[:9])


def test_insurance_benefit_columns_stay_distinct():
    mapping, _ = resolve("Dealer Earnings Register", SYNC_MAP["dealer_earnings"][2])
    assert mapping["customerInsuranceBenefitPassed"] != mapping["dealerInsuranceIncome"]


def test_oem_extra_support_columns_stay_distinct():
    """Received / Passed To Customer / Retained are three separate columns."""
    mapping, _ = resolve("Dealer Earnings Register", SYNC_MAP["dealer_earnings"][2])
    idxs = {mapping["oemExtraSupportReceived"], mapping["oemExtraSupportPassed"],
            mapping["oemExtraSupportRetained"]}
    assert len(idxs) == 3


def test_exchange_has_no_destination_and_says_so():
    assert "exchange" in gsheets.INTENTIONALLY_UNMAPPED
    assert "exchange" not in SYNC_MAP
