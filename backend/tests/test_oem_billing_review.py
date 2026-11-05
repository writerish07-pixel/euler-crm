"""OEM Billing review: never match a different vehicle model; resolve reviews by choice.

Regression for a repeat buyer: Storm delivered (no chassis saved) + a new
Turbo Max booked on the same mobile. The billed Turbo Max must land on the
Turbo Max file — not go to review, and never be suggested to the Storm file.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from test_oem_billing import client, _no_live_coulson_sold, oem_sync, server  # noqa: E402,F401

MOBILE = "9024000001"
STORM_ROW = {
    "chassis": "MD9EMSDL26E000001", "mobile": MOBILE, "invoiceNumber": "AF-STORM-1",
    "customerName": "Repeat Buyer", "model": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh",
    "soldDate": "2026-10-02", "coulsonStatus": "SOLD",
}
TURBO_ROW = {
    "chassis": "MD9EVDAD26K000002", "mobile": MOBILE, "invoiceNumber": "AF-TURBO-2",
    "customerName": "Repeat Buyer", "model": "Turbo Max", "variant": "Maxx (PV)",
    "soldDate": "2026-11-03", "coulsonStatus": "SOLD",
}


def _storm_lead(**kw):
    return {
        "leadId": "LD-STORM", "customerName": "Repeat Buyer", "mobile": MOBILE,
        "accountStatus": "Active", "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": "2026-10-05", "interestedModel": "Storm",
        "variant": "Storm LR (PV) Reg C7 6.6kWh", **kw,
    }


def _turbo_lead(**kw):
    return {
        "leadId": "LD-TURBO", "customerName": "Repeat Buyer", "mobile": MOBILE,
        "accountStatus": "Active", "currentStatus": "Booked",
        "interestedModel": "Turbo Max", "variant": "Maxx (FB)", **kw,
    }


def _row(rows, chassis):
    return next(r for r in rows if r["chassis"] == chassis)


# ------------------------------------------------------------------ model rule
def test_model_conflict_rule():
    assert oem_sync.sold_model_conflicts(TURBO_ROW, _storm_lead())
    assert not oem_sync.sold_model_conflicts(TURBO_ROW, _turbo_lead())  # FB vs PV: same model
    # Unknown on either side is never a conflict.
    assert not oem_sync.sold_model_conflicts({**TURBO_ROW, "model": "", "variant": ""}, _storm_lead())
    assert not oem_sync.sold_model_conflicts(TURBO_ROW, _storm_lead(interestedModel="", variant=""))


def test_oem_hiload_plus_name_still_matches_crm_hi_load():
    """OEM "HiLoad +" / "XR" alone normalises to HiCity; the catalog maps it to Hi-Load."""
    row = {"chassis": "MD9HL1", "mobile": MOBILE, "model": "HiLoad +", "variant": "XR"}
    lead = {"interestedModel": "Hi-Load", "variant": "XR (PV)", "mobile": MOBILE}
    assert not oem_sync.sold_model_conflicts(row, lead)


def test_pack_with_mixed_models_accepts_either_family():
    pack = _turbo_lead(sameOrderMultiUnit=True, units=[
        {"sno": 1, "model": "Turbo Max", "variant": "Maxx (FB)"},
        {"sno": 2, "model": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh"},
    ])
    assert not oem_sync.sold_model_conflicts(STORM_ROW, pack)
    assert not oem_sync.sold_model_conflicts(TURBO_ROW, pack)


# ------------------------------------------------------------------ repeat buyer
def test_repeat_buyer_turbo_lands_on_turbo_file_not_review():
    rows = oem_sync.classify_oem_billing([TURBO_ROW], [_storm_lead(), _turbo_lead()])
    hit = _row(rows, TURBO_ROW["chassis"])
    assert hit["bucket"] == oem_sync.BUCKET_PENDING
    assert hit["leadId"] == "LD-TURBO"


def test_repeat_buyer_both_invoices_land_on_their_own_files():
    rows = oem_sync.classify_oem_billing([STORM_ROW, TURBO_ROW], [_storm_lead(), _turbo_lead()])
    assert _row(rows, STORM_ROW["chassis"])["leadId"] == "LD-STORM"
    assert _row(rows, TURBO_ROW["chassis"])["leadId"] == "LD-TURBO"


def test_delivery_tab_never_suggests_the_other_vehicle():
    """Lead drawer auto-fill: the Turbo file must not be handed the Storm chassis."""
    turbo = _turbo_lead()
    assert oem_sync.match_sold_row(turbo, [STORM_ROW]) is None
    assert oem_sync.match_sold_row(turbo, [STORM_ROW, TURBO_ROW])["chassis"] == TURBO_ROW["chassis"]
    assert oem_sync.match_sold_row(_storm_lead(), [STORM_ROW, TURBO_ROW])["chassis"] == STORM_ROW["chassis"]
    assert oem_sync.sold_rows_for_lead(turbo, [STORM_ROW]) == []


def test_name_fallback_also_respects_the_model():
    turbo = _turbo_lead(mobile="")
    assert oem_sync.match_sold_row(turbo, [STORM_ROW]) is None


# ------------------------------------------------------------------ review choices
def test_genuine_tie_goes_to_review_with_choices():
    a = _turbo_lead(leadId="LD-A")
    b = _turbo_lead(leadId="LD-B", currentStatus="Finance Process")
    rows = oem_sync.classify_oem_billing([TURBO_ROW], [a, b])
    hit = _row(rows, TURBO_ROW["chassis"])
    assert hit["bucket"] == oem_sync.BUCKET_REVIEW
    cands = {c["leadId"]: c for c in hit["candidateLeads"]}
    assert set(cands) == {"LD-A", "LD-B"}
    assert all(c["canLink"] and c["modelMatches"] for c in cands.values())
    # No chassis yet: "another unit" would only fill the empty slot, so Link it is.
    assert not any(c["canAddUnit"] for c in cands.values())
    assert sum(1 for c in hit["candidateLeads"] if c.get("recommended")) == 1


def test_candidate_flags_explain_why():
    storm = oem_sync.review_candidate(_storm_lead(), TURBO_ROW)
    assert not storm["canLink"] and "model" in storm["linkBlockedReason"].lower()
    assert not storm["canAddUnit"] and "Delivered" in storm["addUnitBlockedReason"]
    held = oem_sync.review_candidate(_turbo_lead(chassisNumber="MD9OTHER"), TURBO_ROW)
    assert not held["canLink"] and held["canAddUnit"]


def test_only_other_model_on_mobile_is_review_with_create_path():
    """Storm delivered with no chassis, Turbo billed, no Turbo file in CRM."""
    rows = oem_sync.classify_oem_billing([TURBO_ROW], [_storm_lead()])
    hit = _row(rows, TURBO_ROW["chassis"])
    assert hit["bucket"] == oem_sync.BUCKET_REVIEW
    (only,) = hit["candidateLeads"]
    assert only["leadId"] == "LD-STORM" and not only["canLink"] and not only["canAddUnit"]


# ------------------------------------------------------------------ resolve API
async def _seed(leads, sold):
    ids = [l["leadId"] for l in leads]
    await server.db.leads.delete_many({"$or": [{"leadId": {"$in": ids}}, {"mobile": MOBILE}]})
    await server.db.oem_sold.delete_many({"$or": [{"mobile": MOBILE},
                                                   {"chassis": {"$in": [s["chassis"] for s in sold]}}]})
    await server.db.oem_invoices.delete_many({})
    if leads:
        await server.db.leads.insert_many([dict(l) for l in leads])
    await server.db.oem_sold.insert_many([dict(s) for s in sold])


@pytest.mark.asyncio
async def test_resolve_link_puts_chassis_on_the_chosen_lead(client):
    await _seed([_turbo_lead(leadId="LD-A"), _turbo_lead(leadId="LD-B")], [TURBO_ROW])
    r = await client.post("/api/oem-billing/resolve",
                          json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-B", "action": "link"})
    assert r.status_code == 200, r.text
    b = await server.db.leads.find_one({"leadId": "LD-B"})
    assert TURBO_ROW["chassis"] in oem_sync.lead_chassis_list(b)
    assert b.get("invoiceNumber") == TURBO_ROW["invoiceNumber"]
    a = await server.db.leads.find_one({"leadId": "LD-A"})
    assert not oem_sync.lead_chassis_list(a)
    again = await client.post("/api/oem-billing/resolve",
                              json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-A", "action": "link"})
    assert again.status_code == 409


@pytest.mark.asyncio
async def test_resolve_refuses_a_lead_the_review_did_not_offer(client):
    await _seed([_turbo_lead(leadId="LD-A"), _turbo_lead(leadId="LD-B")], [TURBO_ROW])
    r = await client.post("/api/oem-billing/resolve",
                          json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-ELSEWHERE", "action": "link"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_resolve_refuses_to_add_a_unit_on_a_delivered_file(client):
    await _seed([_storm_lead()], [TURBO_ROW])
    r = await client.post("/api/oem-billing/resolve",
                          json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-STORM", "action": "add_unit"})
    assert r.status_code == 409
    assert "Delivered" in r.json()["detail"]
    link = await client.post("/api/oem-billing/resolve",
                             json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-STORM", "action": "link"})
    assert link.status_code == 409
    storm = await server.db.leads.find_one({"leadId": "LD-STORM"})
    assert not oem_sync.lead_chassis_list(storm)


@pytest.mark.asyncio
async def test_resolve_create_makes_a_separate_lead_for_a_repeat_purchase(client):
    await _seed([_storm_lead()], [TURBO_ROW])
    r = await client.post("/api/oem-billing/resolve",
                          json={"chassis": TURBO_ROW["chassis"], "action": "create"})
    assert r.status_code == 200, r.text
    new_id = r.json()["leadId"]
    assert new_id and new_id != "LD-STORM"
    new = await server.db.leads.find_one({"leadId": new_id})
    assert TURBO_ROW["chassis"] in oem_sync.lead_chassis_list(new)
    storm = await server.db.leads.find_one({"leadId": "LD-STORM"})
    assert not oem_sync.lead_chassis_list(storm)


@pytest.mark.asyncio
async def test_resolve_add_unit_on_an_open_file_with_its_own_vehicle(client):
    """Open Turbo file already holds its first chassis; a second Turbo is billed.
    The delivered Storm file (no chassis saved) keeps it a review, and the open
    Turbo file is offered "add as another unit"."""
    held = _turbo_lead(leadId="LD-A", chassisNumber="MD9EVDAD26K000009",
                       invoiceNumber="AF-TURBO-1")
    rows = oem_sync.classify_oem_billing([TURBO_ROW], [held, _storm_lead()])
    hit = _row(rows, TURBO_ROW["chassis"])
    assert hit["bucket"] == oem_sync.BUCKET_REVIEW
    cand = {c["leadId"]: c for c in hit["candidateLeads"]}
    assert cand["LD-A"]["canAddUnit"] and not cand["LD-A"]["canLink"]
    assert not cand["LD-STORM"]["canAddUnit"]

    await _seed([held, _storm_lead()], [TURBO_ROW])
    r = await client.post("/api/oem-billing/resolve", json={
        "chassis": TURBO_ROW["chassis"], "leadId": "LD-A", "action": "add_unit"})
    assert r.status_code == 200, r.text
    assert r.json()["vehicleCount"] == 2
    a = await server.db.leads.find_one({"leadId": "LD-A"})
    assert set(oem_sync.lead_chassis_list(a)) == {"MD9EVDAD26K000009", TURBO_ROW["chassis"]}
    assert a.get("sameOrderMultiUnit") is True


@pytest.mark.asyncio
async def test_resolve_is_deal_desk_only(client):
    import httpx
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "accounts@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        r = await c.post("/api/oem-billing/resolve",
                         headers={"Authorization": f"Bearer {r.json()['token']}"},
                         json={"chassis": TURBO_ROW["chassis"], "leadId": "LD-A", "action": "link"})
        assert r.status_code == 403
