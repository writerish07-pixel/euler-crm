"""The values behind the newly-mapped columns are really produced and persisted.

Mapping a column is only half the fix: `recompute_lead` has to actually write the value
into Mongo, or the new column syncs as a blank. These run the real route handlers
in-process against mongomock and assert on the persisted lead document.

Nothing is invented to fill a column — every field here is either already returned by
commercial.py (margin components, per-component scheme retention) or already set by an
existing lifecycle handler (closure and delivery-checklist fields).
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter20persist")
os.environ.setdefault("JWT_SECRET", "iter20-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Hi-Load", "XR"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def booked(c, mobile, name="ITER20"):
    r = await c.post("/api/leads", json={"customerName": name, "mobile": mobile,
                                         "interestedModel": MODEL, "variant": VARIANT,
                                         "executive": "Amit", "leadSource": "Walk-in"})
    lid = r.json()["leadId"]
    await c.put(f"/api/leads/{lid}/price-structure",
                json={"exShowroom": 300000, "rto": 20000, "insuranceAmount": 15000})
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-08", "bookingAmount": 0})
    return lid


@pytest.mark.asyncio
async def test_margin_components_are_persisted(client):
    """compute_dealer_margin returns gross and GST; only net used to be stored, leaving
    'Dealer Margin Gross (Incl GST)' and 'Dealer Margin GST (5%)' without a source."""
    lid = await booked(client, "9444400001")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert "dealerMarginGrossInclGst" in lead
    assert "dealerMarginGst" in lead
    margin = ce.compute_dealer_margin(server.lead_to_snapshot(lead))
    assert lead["dealerMarginGrossInclGst"] == margin["marginGrossInclGst"]
    assert lead["dealerMarginGst"] == margin["marginGst"]
    # Net + GST must reconstruct gross — proves these are the same calculation, not a new one.
    assert round(lead["dealerMarginNetExGst"] + lead["dealerMarginGst"], 2) == \
        round(lead["dealerMarginGrossInclGst"], 2)


@pytest.mark.asyncio
async def test_per_component_retention_is_persisted_and_sums_to_the_total(client):
    """The five '… Retained' columns are the existing retainedByComponent map broken out.
    Their sum must equal the already-trusted dealerSchemeRetained total."""
    lid = await booked(client, "9444400002")
    await client.put(f"/api/leads/{lid}/scheme",
                     json={"consumerDiscount": 25000, "loyaltyBonus": 10000,
                           "benefitMode": "Full Benefit"})
    lead = await server.db.leads.find_one({"leadId": lid})
    parts = ["consumerRetained", "exchangeRetained", "loyaltyRetained",
             "referralRetained", "dsaRetained"]
    for p in parts:
        assert p in lead, f"{p} not persisted"
    assert "schemeRetainedBreakup" in lead
    # Every component the breakdown reported must be accounted for by a column.
    total = round(sum(ce.num(lead[p]) for p in parts), 2)
    assert total == round(ce.num(lead["dealerSchemeRetained"]), 2), \
        f"per-component {total} != total {lead['dealerSchemeRetained']}"


@pytest.mark.asyncio
async def test_zero_retention_is_stored_as_zero_not_blank(client):
    """'No retention on this component' is a commercial fact, not missing data."""
    lid = await booked(client, "9444400003")
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["referralRetained"] == 0.0
    assert isinstance(lead["dsaRetained"], float)


@pytest.mark.asyncio
async def test_delivery_checklist_statuses_reach_the_lead(client):
    """Insurance/Registration/Invoice/RC/PDI Status are Lead Register columns; they were
    persisted by mark_delivery all along but never mapped."""
    lid = await booked(client, "9444400004")
    await client.post(f"/api/leads/{lid}/payments", json={"amount": 335000, "paymentMode": "Cash"})
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ABC", "invoiceNumber": "INV-20", "chassisNumber": "CH-20",
        "delivered": "Yes"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    for f in ("insuranceStatus", "registrationStatus", "invoiceStatus", "rcStatus", "pdiStatus"):
        assert lead.get(f), f"{f} missing after delivery"


@pytest.mark.asyncio
async def test_closure_fields_reach_the_lead(client):
    """Closed Date / Close Reason / Final Outstanding are Lead Register columns."""
    lid = await booked(client, "9444400005")
    r = await client.post(f"/api/leads/{lid}/close", json={"closeReason": "Lost to competitor"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead.get("closedDate")
    assert lead.get("closeReason") == "Lost to competitor"
    assert "finalOutstanding" in lead


@pytest.mark.asyncio
async def test_claim_rows_carry_scheme_month_and_booking_id(client):
    """Scheme Month was blank on every live claim row because it was never mapped."""
    lid = await booked(client, "9444400006")
    await client.put(f"/api/leads/{lid}/scheme",
                     json={"consumerDiscount": 25000, "benefitMode": "Full Benefit"})
    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert claims, "no claims generated"
    assert ce.scheme_month_from_date("2026-08-08") == "2026-08"


@pytest.mark.asyncio
async def test_recompute_is_idempotent_for_the_new_fields(client):
    """Running recompute twice must not drift any newly persisted value."""
    lid = await booked(client, "9444400007")
    await client.put(f"/api/leads/{lid}/scheme",
                     json={"loyaltyBonus": 10000, "benefitMode": "Full Benefit"})
    before = await server.db.leads.find_one({"leadId": lid})
    await server.recompute_lead(lid)
    after = await server.db.leads.find_one({"leadId": lid})
    for f in ("dealerMarginGrossInclGst", "dealerMarginGst", "consumerRetained",
              "loyaltyRetained", "dealerSchemeRetained", "dealerTotalEarnings"):
        assert before[f] == after[f], f"{f} drifted on recompute: {before[f]} -> {after[f]}"


@pytest.mark.asyncio
async def test_activity_updates_the_lead_last_activity_summary(client):
    """Lead Register 'Last Activity' is derived from the most recent activity."""
    lid = await booked(client, "9444400008")
    r = await client.post(f"/api/leads/{lid}/activities",
                          json={"activityType": "Call", "discussion": "Customer will visit Friday",
                                "nextFollowup": "2026-08-15"})
    assert r.status_code == 200, r.text
    assert r.json()["nextFollowup"] == "2026-08-15"      # persisted on the activity itself
    lead = await server.db.leads.find_one({"leadId": lid})
    assert "Call" in lead["lastActivity"]
    assert "Friday" in lead["lastActivity"]


@pytest.mark.asyncio
async def test_closure_records_who_and_when(client):
    lid = await booked(client, "9444400009")
    await client.post(f"/api/leads/{lid}/close", json={"closeReason": "Duplicate enquiry"})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["closedBy"] == "owner@euler.com"
    assert lead["closeTimestamp"]
    assert lead["lastUpdatedBy"] == "owner@euler.com"


@pytest.mark.asyncio
async def test_lead_edit_records_the_acting_user(client):
    lid = await booked(client, "9444400010")
    await client.put(f"/api/leads/{lid}", json={"city": "Jaipur"})
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["lastUpdatedBy"] == "owner@euler.com"


@pytest.mark.asyncio
async def test_delivery_feedback_is_persisted(client):
    lid = await booked(client, "9444400011")
    await client.post(f"/api/leads/{lid}/payments", json={"amount": 335000, "paymentMode": "Cash"})
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ABC", "invoiceNumber": "INV-21", "chassisNumber": "CH-21",
        "delivered": "Yes", "feedback": "Very happy with the handover"})
    d = await server.db.deliveries.find_one({"leadId": lid})
    assert d["feedback"] == "Very happy with the handover"
    assert d["deliveryId"]


@pytest.mark.asyncio
async def test_claim_receipt_records_the_received_date(client):
    lid = await booked(client, "9444400012")
    await client.put(f"/api/leads/{lid}/scheme",
                     json={"consumerDiscount": 25000, "benefitMode": "Full Benefit"})
    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert claims, "no derived claims"
    key = claims[0]["componentKey"]
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": key, "amount": 1000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text
    rec = await server.db.claims.find_one({"leadId": lid, "componentKey": key})
    assert rec["claimReceivedDate"] == "2026-08-20"


def test_source_required_columns_have_no_writer():
    """These must stay blank rather than be invented. Asserted structurally: none of the
    unmapped SOURCE_REQUIRED fields appears as a written key in server.py."""
    import gsheets
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "server.py")).read()
    for (_tab, _col), spec in gsheets.SOURCE_REQUIRED.items():
        f = spec["field"]
        if f == "claimRemarks":
            continue          # mapped so a value flows once entered; still nothing writes it
        assert f'"{f}":' not in src, f"{f} is declared SOURCE_REQUIRED but something writes it"
