"""Lead cancellation — the LOST exit, and the executive scorecard that survives it.

The app had exactly one way out of the funnel: POST /leads/{id}/close, which
hardcodes currentStatus="Close Won". A customer who walked away had to be closed
as a WIN or left open forever, so nobody could see who was losing deals or why.

The design tension this suite pins down: a cancelled lead is supposed to go back
into the funnel as a fresh lead AND still count against the executive who lost
it. Those two are only compatible if cancellation is a permanent STAMP
(cancelCount + cancelHistory) rather than a status — a status-based count would
read zero the instant the lead flipped back to New.

Also covered: money already received makes a cancellation owner-only, a delivered
vehicle cannot be cancelled at all (that is a buyback), and the 3/6/9-day
WhatsApp cycle genuinely restarts instead of resuming mid-stride.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter32cancel")
os.environ.setdefault("JWT_SECRET", "iter32-cancel-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
# Own mobile range — every test module shares one mongomock database, so a
# collision with another suite's numbers shows up as a duplicate-mobile 409.
BASE_MOBILE = 9532320000


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest_asyncio.fixture
async def exec_client(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "executive@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


_seq = {"n": 0}


def next_mobile():
    _seq["n"] += 1
    return str(BASE_MOBILE + _seq["n"])


async def make_lead(c, name, executive="Amit", model=TURBO[0]):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(), "interestedModel": model,
        "variant": TURBO[1], "executive": executive})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


async def cancel(c, lead_id, reason="Not reachable", **kw):
    return await c.post(f"/api/leads/{lead_id}/cancel",
                        json={"cancelReason": reason, **kw})


async def lead_doc(lead_id):
    return await server.db.leads.find_one({"leadId": lead_id})


# ==================================================== the reason master
@pytest.mark.asyncio
async def test_default_reasons_are_seeded_with_a_revival_policy(client):
    rows = (await client.get("/api/cancel-reasons")).json()
    by_reason = {r["reason"]: r for r in rows}
    assert "Bought other brand" in by_reason
    # A customer who bought a Tata must never re-enter the 3-day cycle.
    assert by_reason["Bought other brand"]["revive"] == "never"
    assert by_reason["Postponed purchase"]["revive"] == "days"
    assert by_reason["Postponed purchase"]["reviveAfterDays"] == 30
    assert by_reason["Not reachable"]["revive"] == "now"


@pytest.mark.asyncio
async def test_reason_crud_is_owner_only(exec_client):
    r = await exec_client.post("/api/cancel-reasons", json={"reason": "ITER32 Sneaky"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_reason_can_be_added_and_edited(client):
    r = await client.post("/api/cancel-reasons",
                          json={"reason": "ITER32 Competitor finance", "revive": "days",
                                "reviveAfterDays": 45})
    assert r.status_code == 200, r.text
    rid = r.json()["reasonId"]
    assert r.json()["reviveAfterDays"] == 45

    r2 = await client.put(f"/api/cancel-reasons/{rid}",
                          json={"reason": "ITER32 Competitor finance", "revive": "never"})
    assert r2.status_code == 200
    # Switching off revival must also clear the stale day count.
    assert r2.json()["revive"] == "never" and r2.json()["reviveAfterDays"] == 0
    await client.delete(f"/api/cancel-reasons/{rid}")


@pytest.mark.asyncio
async def test_duplicate_reason_is_rejected(client):
    r = await client.post("/api/cancel-reasons", json={"reason": "not reachable"})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_days_mode_without_a_number_gets_a_sane_default(client):
    r = await client.post("/api/cancel-reasons",
                          json={"reason": "ITER32 Waiting for subsidy", "revive": "days"})
    assert r.json()["reviveAfterDays"] == 30
    await client.delete(f"/api/cancel-reasons/{r.json()['reasonId']}")


@pytest.mark.asyncio
async def test_a_reason_in_use_cannot_be_deleted(client):
    r = await client.post("/api/cancel-reasons",
                          json={"reason": "ITER32 Used reason", "revive": "now"})
    rid = r.json()["reasonId"]
    lid = await make_lead(client, "ITER32 Uses reason")
    await cancel(client, lid, "ITER32 Used reason")

    d = await client.delete(f"/api/cancel-reasons/{rid}")
    assert d.status_code == 409
    # Deleting it would erase why those leads were lost.
    assert "Inactive" in d.json()["detail"]


# ==================================================== cancelling
@pytest.mark.asyncio
async def test_cancel_requires_a_reason(client):
    lid = await make_lead(client, "ITER32 No reason")
    r = await client.post(f"/api/leads/{lid}/cancel", json={"cancelReason": ""})
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_unknown_reason_is_rejected(client):
    lid = await make_lead(client, "ITER32 Bad reason")
    r = await cancel(client, lid, "Because I said so")
    assert r.status_code == 422
    assert "Cancel Reasons" in r.json()["detail"]


@pytest.mark.asyncio
async def test_other_demands_remarks(client):
    lid = await make_lead(client, "ITER32 Other blank")
    r = await cancel(client, lid, "Other")
    assert r.status_code == 422

    r2 = await cancel(client, lid, "Other", cancelRemarks="Moving out of state")
    assert r2.status_code == 200


@pytest.mark.asyncio
async def test_cancel_stamps_history_and_count(client):
    lid = await make_lead(client, "ITER32 Stamped", executive="Sanjay")
    r = await cancel(client, lid, "Price too high", cancelRemarks="wants 20k off",
                     cancelDate="2026-08-20")
    assert r.status_code == 200, r.text

    doc = await lead_doc(lid)
    assert doc["cancelCount"] == 1
    assert doc["lastCancelReason"] == "Price too high"
    assert doc["lastCancelDate"] == "2026-08-20"
    h = doc["cancelHistory"][0]
    assert h["reason"] == "Price too high"
    assert h["remarks"] == "wants 20k off"
    assert h["stage"] == "Enquiry"
    # Attribution is captured at cancel time so a later reassignment cannot move it.
    assert h["executive"] == "Sanjay"
    assert h["cancelledBy"] == "owner@euler.com"


@pytest.mark.asyncio
async def test_cancelling_twice_counts_twice(client):
    lid = await make_lead(client, "ITER32 Twice")
    await cancel(client, lid, "Not reachable")           # revives immediately
    await cancel(client, lid, "Not reachable")
    doc = await lead_doc(lid)
    assert doc["cancelCount"] == 2
    assert len(doc["cancelHistory"]) == 2


# ==================================================== revival policy
@pytest.mark.asyncio
async def test_revive_now_puts_the_lead_straight_back_in_the_funnel(client):
    lid = await make_lead(client, "ITER32 Straight back")
    r = await cancel(client, lid, "Not reachable", cancelDate="2026-08-20")
    assert r.json()["revivedNow"] is True

    doc = await lead_doc(lid)
    assert doc["accountStatus"] == "Active"
    assert doc["currentStatus"] == "New"
    # The clock restarts from the cancel date, not the original creation date.
    assert doc["followupAnchorDate"] == "2026-08-20"
    assert doc["whatsappFollowupCount"] == 0
    assert doc["whatsappFollowupLastDate"] == ""


@pytest.mark.asyncio
async def test_revive_days_parks_the_lead_with_a_return_date(client):
    lid = await make_lead(client, "ITER32 Parked")
    r = await cancel(client, lid, "Postponed purchase", cancelDate="2026-08-01")
    assert r.json()["revivedNow"] is False
    assert r.json()["reviveOn"] == "2026-08-31"       # 30 days on

    doc = await lead_doc(lid)
    assert doc["accountStatus"] == "Cancelled"
    assert doc["currentStatus"] == "Lost"
    assert doc["reviveOn"] == "2026-08-31"
    # The executive sees the return date in their normal follow-up list too.
    assert doc["nextFollowupDate"] == "2026-08-31"


@pytest.mark.asyncio
async def test_revive_never_leaves_the_lead_closed(client):
    lid = await make_lead(client, "ITER32 Gone for good")
    r = await cancel(client, lid, "Bought other brand")
    assert r.json()["revivedNow"] is False
    assert r.json()["reviveOn"] == ""

    doc = await lead_doc(lid)
    assert doc["accountStatus"] == "Cancelled"
    assert doc["reviveOn"] == ""


@pytest.mark.asyncio
async def test_stop_beats_the_revival_policy(client):
    """A customer who opted out is not walked back into the messaging cycle."""
    lid = await make_lead(client, "ITER32 Opted out")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"whatsappOptOut": True}})

    r = await cancel(client, lid, "Not reachable")     # would normally revive now
    assert r.json()["revivedNow"] is False
    assert r.json()["optOutBlockedRevival"] is True
    assert (await lead_doc(lid))["accountStatus"] == "Cancelled"


@pytest.mark.asyncio
async def test_scheduled_revival_brings_parked_leads_back_on_the_day(client):
    lid = await make_lead(client, "ITER32 Cool-off over")
    await cancel(client, lid, "Postponed purchase", cancelDate="2026-01-01")
    assert (await lead_doc(lid))["accountStatus"] == "Cancelled"

    # A day before the cool-off ends, nothing happens.
    res = await server.run_scheduled_revivals("2026-01-30")
    assert lid not in res["revived"]

    res = await server.run_scheduled_revivals("2026-01-31")
    assert lid in res["revived"]
    doc = await lead_doc(lid)
    assert doc["accountStatus"] == "Active" and doc["currentStatus"] == "New"
    assert doc["followupAnchorDate"] == "2026-01-31"
    assert doc["reviveOn"] == ""


@pytest.mark.asyncio
async def test_manual_revive_beats_the_cool_off(client):
    lid = await make_lead(client, "ITER32 Manual revive")
    await cancel(client, lid, "Bought other brand")

    r = await client.post(f"/api/leads/{lid}/revive")
    assert r.status_code == 200
    assert r.json()["accountStatus"] == "Active"
    assert r.json()["currentStatus"] == "New"


@pytest.mark.asyncio
async def test_reviving_an_active_lead_is_rejected(client):
    lid = await make_lead(client, "ITER32 Already active")
    r = await client.post(f"/api/leads/{lid}/revive")
    assert r.status_code == 409


# ==================================================== the money guard
@pytest.mark.asyncio
async def test_executive_cannot_cancel_a_lead_that_has_taken_money(client, exec_client):
    lid = await make_lead(client, "ITER32 Funded", executive="Executive")
    r = await client.post(f"/api/leads/{lid}/convert-booking",
                          json={"bookingAmount": 25000, "executive": "Executive"})
    assert r.status_code == 200, r.text

    blocked = await cancel(exec_client, lid, "Finance rejected")
    assert blocked.status_code == 403
    assert "only the owner" in blocked.json()["detail"]


@pytest.mark.asyncio
async def test_owner_can_cancel_a_funded_lead_and_the_money_is_recorded(client):
    lid = await make_lead(client, "ITER32 Owner cancels funded")
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingAmount": 25000, "executive": "Amit"})

    r = await cancel(client, lid, "Finance rejected")
    assert r.status_code == 200, r.text
    assert r.json()["moneyAtRisk"]["customerMoney"] == 25000

    doc = await lead_doc(lid)
    h = doc["cancelHistory"][-1]
    assert h["customerMoney"] == 25000
    # Where in the funnel it died — a booked cancellation is not an enquiry that fizzled.
    assert h["stage"] == "Booked"
    # Cancelling reverses nothing: the receipt still stands and is refunded separately.
    assert server.ce.num(doc.get("bookingAmount")) == 25000


@pytest.mark.asyncio
async def test_an_unfunded_lead_can_be_cancelled_by_an_executive(client, exec_client):
    lid = await make_lead(client, "ITER32 Exec cancels", executive="Executive")
    r = await cancel(exec_client, lid, "Not reachable")
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_a_delivered_vehicle_cannot_be_cancelled(client):
    lid = await make_lead(client, "ITER32 Delivered")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "deliveryDate": server.today()}})
    r = await cancel(client, lid, "Not reachable")
    assert r.status_code == 409
    assert "buyback" in r.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_action_flags_are_exposed_on_the_lead(client):
    lid = await make_lead(client, "ITER32 Action flags")
    acts = (await client.get(f"/api/leads/{lid}/360")).json()["actions"]
    assert acts["canCancel"] is True
    assert acts["cancelNeedsOwner"] is False

    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingAmount": 10000, "executive": "Amit"})
    acts = (await client.get(f"/api/leads/{lid}/360")).json()["actions"]
    assert acts["canCancel"] is True and acts["cancelNeedsOwner"] is True


# ==================================================== the count survives revival
@pytest.mark.asyncio
async def test_cancel_count_survives_the_lead_going_back_to_new(client):
    """The whole point. A status-based count would read zero here."""
    lid = await make_lead(client, "ITER32 Survivor", executive="Prasun")
    await cancel(client, lid, "Not reachable")

    doc = await lead_doc(lid)
    assert doc["currentStatus"] == "New"          # back at the top of the funnel
    assert doc["accountStatus"] == "Active"
    assert doc["cancelCount"] == 1                # and still counted against Prasun
    assert doc["cancelHistory"][0]["executive"] == "Prasun"


@pytest.mark.asyncio
async def test_cancel_stamp_cannot_be_edited_away_through_the_lead_form(client):
    lid = await make_lead(client, "ITER32 Tamper")
    await cancel(client, lid, "Not reachable")
    r = await client.put(f"/api/leads/{lid}", json={"cancelCount": 0})
    assert r.status_code in (403, 409, 422)
    assert (await lead_doc(lid))["cancelCount"] == 1


# ==================================================== reporting
@pytest.mark.asyncio
async def test_executive_rollup_carries_cancellations(client):
    lid = await make_lead(client, "ITER32 Rollup", executive="Amit")
    await cancel(client, lid, "Not reachable")

    d = (await client.get("/api/reports/daily/owner")).json()
    amit = next(e for e in d["executives"] if e["name"] == "Amit")
    assert amit["cancelledToday"] >= 1
    assert amit["cancelledMtd"] >= 1
    assert amit["cancelledTotal"] >= 1
    assert d["cancelledToday"] >= 1


@pytest.mark.asyncio
async def test_managers_see_cancellations_but_still_no_money(client):
    r = await client.get("/api/reports/daily/manager")
    d = r.json()
    assert "cancelledToday" in d           # volume: managers get it
    assert "revenueMtd" not in d           # money: they do not
    assert all("cancelledMtd" in e for e in d["executives"])


@pytest.mark.asyncio
async def test_cancellations_report_groups_three_ways(client):
    a = await make_lead(client, "ITER32 Report A", executive="Lokesh")
    b = await make_lead(client, "ITER32 Report B", executive="Lokesh")
    await cancel(client, a, "Price too high")
    await client.post(f"/api/leads/{b}/convert-booking",
                      json={"bookingAmount": 5000, "executive": "Lokesh"})
    await cancel(client, b, "Finance rejected")

    d = (await client.get("/api/reports/cancellations")).json()
    lok = next(x for x in d["byExecutive"] if x["executive"] == "Lokesh")
    assert lok["count"] >= 2

    reasons = {x["reason"] for x in d["byReason"]}
    assert {"Price too high", "Finance rejected"} <= reasons

    stages = {x["stage"]: x for x in d["byStage"]}
    assert "Enquiry" in stages and "Booked" in stages
    # The booked cancellation carried money; the enquiry one did not.
    assert stages["Booked"]["money"] >= 5000
    assert d["withMoney"] >= 1


@pytest.mark.asyncio
async def test_report_separates_revived_from_parked(client):
    a = await make_lead(client, "ITER32 Revived one")
    b = await make_lead(client, "ITER32 Parked one")
    await cancel(client, a, "Not reachable")           # straight back
    await cancel(client, b, "Bought other brand")      # parked for good

    d = (await client.get("/api/reports/cancellations")).json()
    assert d["revived"] >= 1 and d["parked"] >= 1
    assert d["revived"] + d["parked"] == d["total"]


@pytest.mark.asyncio
async def test_report_can_be_filtered(client):
    lid = await make_lead(client, "ITER32 Filtered", executive="Dharmendra")
    await cancel(client, lid, "Vehicle not available")

    d = (await client.get("/api/reports/cancellations",
                          params={"executive": "Dharmendra"})).json()
    assert d["total"] >= 1
    assert all(e["executive"] == "Dharmendra" for e in d["events"])

    d2 = (await client.get("/api/reports/cancellations",
                           params={"reason": "Vehicle not available"})).json()
    assert all(e["reason"] == "Vehicle not available" for e in d2["events"])


@pytest.mark.asyncio
async def test_an_executive_only_sees_their_own_cancellations(client, exec_client):
    mine = await make_lead(client, "ITER32 Mine", executive="Executive")
    theirs = await make_lead(client, "ITER32 Theirs", executive="Harish Bhatnagar")
    await cancel(client, mine, "Not reachable")
    await cancel(client, theirs, "Not reachable")

    d = (await exec_client.get("/api/reports/cancellations")).json()
    ids = {e["leadId"] for e in d["events"]}
    assert mine in ids
    assert theirs not in ids


# ==================================================== follow-up restart
def test_followup_anchor_prefers_the_cancel_date():
    lead = {"createdDate": "2026-01-01", "followupAnchorDate": "2026-06-01"}
    assert wa.followup_anchor(lead) == "2026-06-01"
    assert wa.followup_anchor({"createdDate": "2026-01-01"}) == "2026-01-01"


def test_the_three_day_cycle_restarts_from_the_anchor():
    """Without the anchor an old lead computes day 90, fires once because 90
    divides by 3, then falls silent for three days."""
    base = {"accountStatus": "Active", "currentStatus": "New", "createdDate": "2026-01-01"}
    old = {**base, "followupAnchorDate": "2026-04-01"}

    assert wa.followup_due(old, "2026-04-01") is False   # day 0
    assert wa.followup_due(old, "2026-04-02") is False   # day 1
    assert wa.followup_due(old, "2026-04-04") is True    # day 3
    assert wa.followup_due(old, "2026-04-07") is True    # day 6


def test_a_parked_lead_gets_no_followups():
    parked = {"accountStatus": "Cancelled", "currentStatus": "Lost",
              "followupAnchorDate": "2026-04-01"}
    assert wa.followup_due(parked, "2026-04-04") is False


# ==================================================== sheet contract
def test_lead_register_maps_the_cancel_columns():
    import gsheets
    fields = gsheets.SYNC_MAP["leads"][2]
    for f in ("cancelCount", "lastCancelDate", "lastCancelReason", "lastCancelStage", "reviveOn"):
        assert f in fields, f
        assert f in gsheets.HEADER_ALIASES, f"{f} needs a header alias or it never resolves"


def test_the_column_helper_is_append_only():
    import gsheets
    assert gsheets.LEAD_CANCEL_HEADERS == ["Cancel Count", "Last Cancel Date",
                                           "Last Cancel Reason", "Last Cancel Stage", "Revive On"]
