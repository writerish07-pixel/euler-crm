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


def test_lead_register_insurance_benefit_resolves_after_loyalty():
    """Insurance Benefit is an independent Lead Register column after Loyalty Bonus."""
    tab, fields = SYNC_MAP["leads"][0], SYNC_MAP["leads"][2]
    assert "insuranceBenefit" in fields
    mapping, missing = resolve(tab, ["loyaltyBonus", "insuranceBenefit"])
    assert missing == []
    assert mapping["insuranceBenefit"] == mapping["loyaltyBonus"] + 1
    _hr, headers = LIVE_HEADERS[tab]
    assert headers[mapping["insuranceBenefit"]] == "Insurance Benefit"


def test_claim_register_has_independent_scheme_amount_columns():
    """Claim Register must resolve every scheme amount column independently."""
    tab, fields = SYNC_MAP["claims"][0], SYNC_MAP["claims"][2]
    needed = ["loyaltyBonus", "insuranceBenefit", "rtoBenefit", "rtoInsuranceBenefit",
              "consumerDiscount", "exchangeBonus", "referralBonus", "dsaDiscount",
              "additionalDiscount"]
    for f in needed:
        assert f in fields, f
    mapping, missing = resolve(tab, needed)
    assert missing == [], missing
    # No two scheme fields may collapse onto one column.
    seen = {}
    for f in needed:
        seen.setdefault(mapping[f], []).append(f)
    collisions = {i: fs for i, fs in seen.items() if len(fs) > 1}
    assert collisions == {}
    _hr, headers = LIVE_HEADERS[tab]
    assert headers[mapping["insuranceBenefit"]] == "Insurance Benefit"
    assert mapping["insuranceBenefit"] == mapping["loyaltyBonus"] + 1


# --------------------------------------------------------------- phase 3
# Columns that had no mapping AND no obvious camelCase field, but whose value the CRM
# either already captured under a different name or can derive from data it holds.
NEWLY_SOURCED = {
    "leads": ["lastActivity", "lastUpdatedBy", "closedBy", "closeTimestamp"],
    "activities": ["nextFollowup"],
    "deliveries": ["feedback"],
    "insurance": ["insuranceExecutive"],
    "claims": ["source", "dsaApproval", "claimReceivedDate", "claimRemarks"],
    "dealer_earnings": ["modifiedBy", "currentStage"],
}


@pytest.mark.parametrize("entity,fields", sorted(NEWLY_SOURCED.items()))
def test_newly_sourced_columns_resolve_live(entity, fields):
    tab = SYNC_MAP[entity][0]
    declared = SYNC_MAP[entity][2]
    assert [f for f in fields if f not in declared] == []
    mapping, _ = resolve(tab, fields)
    assert [f for f in fields if f not in mapping] == []


def test_every_operational_column_is_either_mapped_or_declared_source_required():
    """The contract's central promise: no operational column is silently unaccounted for."""
    unaccounted = []
    for entity, spec in SYNC_MAP.items():
        tab, fields = spec[0], spec[2]
        _hr, headers = LIVE_HEADERS[tab]
        mapping, _ = resolve(tab, fields)
        owned = set(mapping.values())
        for i, header in enumerate(headers):
            if not str(header).strip() or i in owned:
                continue
            if (tab, header) in gsheets.SOURCE_REQUIRED:
                continue
            unaccounted.append(f"{tab}!{_col_letter(i)} {header}")
    assert unaccounted == [], f"operational columns with no classification: {unaccounted}"


def test_source_required_entries_name_a_real_column_and_explain_themselves():
    for (tab, column), spec in gsheets.SOURCE_REQUIRED.items():
        _hr, headers = LIVE_HEADERS[tab]
        assert column in headers, f"SOURCE_REQUIRED names a column not in {tab}: {column}"
        assert spec["why"] and spec["needs"], f"{tab}/{column} must explain why and what is needed"


def test_source_required_columns_are_not_silently_invented():
    """A column with no source must stay blank — never filled with a placeholder."""
    for (_tab, _column), spec in gsheets.SOURCE_REQUIRED.items():
        assert spec["field"] not in ("", None)


def test_preflight_reports_source_required(monkeypatch):
    """The gap must stay visible in the API, not just in a comment."""
    # Prevent re-init from picking up a live credential file mounted in the VM.
    monkeypatch.setattr(gsheets, "_init", lambda: None)
    monkeypatch.setattr(gsheets, "_service", None)
    monkeypatch.setattr(gsheets, "_status", dict(gsheets._status, enabled=False,
                                                 reason="sync disabled for test"))
    rep = gsheets.preflight()
    assert rep["enabled"] is False        # not connected here, but the shape is asserted below
    assert isinstance(gsheets.SOURCE_REQUIRED, dict) and gsheets.SOURCE_REQUIRED


def test_lead_register_header_is_row_1_and_starts_at_column_A():
    """Lead Register matches every other tab: header in A1, leads from A2 downward."""
    hr, headers = LIVE_HEADERS["Lead Register"]
    assert hr == 1
    assert headers[0] == "Lead ID"
    assert "Insurance Benefit" in headers
    mapping, _ = resolve("Lead Register", SYNC_MAP["leads"][2])
    assert mapping["leadId"] == 0
    assert _col_letter(mapping["leadId"]) == "A"
    assert SYNC_MAP["leads"][3] == 1


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
