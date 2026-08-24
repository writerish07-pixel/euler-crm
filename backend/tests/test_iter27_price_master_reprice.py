"""A Price Master revision reaches every live lead on that vehicle.

Next month's price rise must not leave booked-but-undelivered leads quoting the
old ex-showroom. When an owner saves a new price, every Active, NOT-delivered
lead on that model/variant is repriced from the master and recomputed.

Deliberate exclusions:
  * delivered leads          — the invoice is already raised
  * non-Active accounts      — closed/cancelled leads are frozen
  * unpriced leads           — nothing to refresh yet
  * settled leads            — money received AND outstanding cleared. Repricing
                               them would re-open an outstanding and BLOCK Mark
                               Delivered on a customer who owes nothing.

Scheme is not realigned: entitlements follow the Scheme Master and the booking
month, and must not move because the vehicle price moved.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter27reprice")
os.environ.setdefault("JWT_SECRET", "iter27-reprice-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Hi-Load", "TR-NC (HiLoad)"
BASE_EX = 500000.0
RISE = 25000.0
# The seed already holds a row for this vehicle. Reuse it rather than inserting a
# second one — two Active rows for one model/variant make _price_master_row
# ambiguous, which is a different bug from the one under test.
PRICE_ID = None


@pytest_asyncio.fixture
async def client():
    global PRICE_ID
    await server.startup()
    row = await server.db.price_master.find_one({"model": MODEL, "variant": VARIANT})
    assert row, f"seed is missing the {MODEL}/{VARIANT} Price Master row"
    PRICE_ID = row["priceId"]
    await server.db.price_master.update_one(
        {"priceId": PRICE_ID},
        {"$set": {"exShowroom": BASE_EX, "rto": 10000, "insurance": 10000,
                  "accessories": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
                  "extendedWarranty": 0, "otherCharges": 0,
                  "tcsApplicable": "No", "status": "Active"}})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c
    # Leave the master at the base price so each test starts from a known rate.
    await server.db.price_master.update_one({"priceId": PRICE_ID},
                                            {"$set": {"exShowroom": BASE_EX}})


def body(**over):
    base = {"model": MODEL, "variant": VARIANT, "exShowroom": BASE_EX, "rto": 10000,
            "insurance": 10000, "accessories": 0, "handlingCharges": 0, "trc": 0,
            "fastag": 0, "extendedWarranty": 0, "otherCharges": 0, "tcsApplicable": "No"}
    base.update(over)
    return base


async def make_lead(c, mobile, *, priced=True, booked=False, pay=0.0):
    r = await c.post("/api/leads", json={
        "customerName": f"ITER27 {mobile[-4:]}", "mobile": mobile,
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    if priced:
        ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
        await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    if booked:
        await c.post(f"/api/leads/{lid}/convert-booking",
                     json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    if pay:
        await c.post(f"/api/leads/{lid}/payments", json={"amount": pay, "paymentMode": "Cash"})
    return lid


async def lead(lid):
    return await server.db.leads.find_one({"leadId": lid})


async def raise_price(c, to=BASE_EX + RISE):
    return (await c.put(f"/api/price-master/{PRICE_ID}", json=body(exShowroom=to))).json()


# ============================================================ the headline case
@pytest.mark.asyncio
async def test_booked_undelivered_lead_gets_the_new_price(client):
    lid = await make_lead(client, "9355510001", booked=True, pay=20000)
    before = await lead(lid)
    assert before["exShowroom"] == BASE_EX

    res = await raise_price(client)
    assert res["reprice"]["repricedCount"] >= 1

    after = await lead(lid)
    assert after["exShowroom"] == BASE_EX + RISE
    assert after["customerPayable"] == ce.round2(before["customerPayable"] + RISE)
    # Money already received is untouched; the rise lands on what is still owed.
    assert after["totalReceived"] == before["totalReceived"]
    assert after["customerOutstanding"] == ce.round2(before["customerOutstanding"] + RISE)


@pytest.mark.asyncio
async def test_report_shows_before_and_after_per_lead(client):
    lid = await make_lead(client, "9355510002", booked=True, pay=20000)
    res = await raise_price(client)
    row = next(r for r in res["reprice"]["repriced"] if r["leadId"] == lid)
    assert row["exShowroomBefore"] == BASE_EX
    assert row["exShowroomAfter"] == BASE_EX + RISE
    assert row["delta"] == RISE
    assert res["reprice"]["changedFields"] == ["exShowroom"]


@pytest.mark.asyncio
async def test_price_drop_also_propagates(client):
    lid = await make_lead(client, "9355510003", booked=True, pay=20000)
    before = await lead(lid)
    await raise_price(client, to=BASE_EX - 15000)
    after = await lead(lid)
    assert after["exShowroom"] == BASE_EX - 15000
    assert after["customerPayable"] == ce.round2(before["customerPayable"] - 15000)


# ================================================================== exclusions
@pytest.mark.asyncio
async def test_settled_lead_keeps_the_price_it_paid(client):
    """The guard that stops a price rise blocking a delivery on a paid-up customer."""
    lid = await make_lead(client, "9355510004", booked=True)
    owed = (await lead(lid))["customerOutstanding"]
    await client.post(f"/api/leads/{lid}/payments", json={"amount": owed, "paymentMode": "Cash"})
    settled = await lead(lid)
    assert settled["customerOutstanding"] == 0

    res = await raise_price(client)
    after = await lead(lid)
    assert after["exShowroom"] == BASE_EX, "a fully paid lead must not be repriced"
    assert after["customerPayable"] == settled["customerPayable"]
    assert after["customerOutstanding"] == 0, "delivery must not become blocked"
    reason = next(s for s in res["reprice"]["skipped"] if s["leadId"] == lid)["reason"]
    assert "paid in full" in reason


@pytest.mark.asyncio
async def test_delivered_lead_is_never_repriced(client):
    lid = await make_lead(client, "9355510005", booked=True)
    owed = (await lead(lid))["customerOutstanding"]
    await client.post(f"/api/leads/{lid}/payments", json={"amount": owed, "paymentMode": "Cash"})
    agents = (await client.get("/api/insurance-agents")).json()
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "insuranceAgentId": agents[0]["agentId"],
        "invoiceNumber": "INV-I27DEL", "chassisNumber": "CH-I27DEL",
        "numberPlate": "RJ27-I27DEL", "delivered": "Yes"})
    assert r.status_code == 200, r.text
    billed = await lead(lid)

    res = await raise_price(client)
    after = await lead(lid)
    assert after["exShowroom"] == billed["exShowroom"], "an invoiced lead must never move"
    assert after["customerPayable"] == billed["customerPayable"]
    assert all(x["leadId"] != lid for x in res["reprice"]["repriced"])


@pytest.mark.asyncio
async def test_closed_lead_is_not_repriced(client):
    lid = await make_lead(client, "9355510006", booked=True, pay=20000)
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"accountStatus": "Closed"}})
    before = await lead(lid)
    res = await raise_price(client)
    after = await lead(lid)
    assert after["exShowroom"] == before["exShowroom"]
    assert any(s["leadId"] == lid and "account" in s["reason"] for s in res["reprice"]["skipped"])


@pytest.mark.asyncio
async def test_unpriced_lead_is_not_repriced(client):
    lid = await make_lead(client, "9355510007", priced=False)
    res = await raise_price(client)
    assert any(s["leadId"] == lid and "no price structure" in s["reason"]
               for s in res["reprice"]["skipped"])


@pytest.mark.asyncio
async def test_a_different_vehicle_is_untouched(client):
    r = await client.post("/api/leads", json={
        "customerName": "ITER27 OTHER", "mobile": "9355510008",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    before = await lead(lid)
    res = await raise_price(client)
    after = await lead(lid)
    assert after["exShowroom"] == before["exShowroom"]
    assert all(x["leadId"] != lid for x in res["reprice"]["repriced"])


# ============================================================== scope + safety
@pytest.mark.asyncio
async def test_priced_but_unbooked_lead_is_repriced(client):
    """An open quote must not keep offering a withdrawn price."""
    lid = await make_lead(client, "9355510009", booked=False)
    await raise_price(client)
    assert (await lead(lid))["exShowroom"] == BASE_EX + RISE


@pytest.mark.asyncio
async def test_saving_the_same_price_reprices_nothing(client):
    await make_lead(client, "9355510010", booked=True, pay=20000)
    res = (await client.put(f"/api/price-master/{PRICE_ID}", json=body())).json()
    assert res["reprice"]["repricedCount"] == 0
    assert res["reprice"]["changedFields"] == []


@pytest.mark.asyncio
async def test_repricing_is_idempotent(client):
    lid = await make_lead(client, "9355510011", booked=True, pay=20000)
    await raise_price(client)
    once = await lead(lid)
    again = await raise_price(client)
    twice = await lead(lid)
    assert twice["customerPayable"] == once["customerPayable"]
    assert again["reprice"]["repricedCount"] == 0, "a no-op save must not re-report leads"


@pytest.mark.asyncio
async def test_status_only_edit_does_not_reprice(client):
    lid = await make_lead(client, "9355510012", booked=True, pay=20000)
    before = await lead(lid)
    res = (await client.put(f"/api/price-master/{PRICE_ID}",
                            json=body(bodyType="Flat Bed"))).json()
    assert res["reprice"]["repricedCount"] == 0
    assert (await lead(lid))["customerPayable"] == before["customerPayable"]


@pytest.mark.asyncio
async def test_scheme_entitlements_do_not_move_with_price(client):
    """Scheme follows the Scheme Master and the booking month, not the price."""
    lid = await make_lead(client, "9355510013", booked=True, pay=20000)
    before = await lead(lid)
    await raise_price(client)
    after = await lead(lid)
    for f in ("oemSchemeAmount", "dealerSchemeAmount", "schemeCustomerBenefit",
              "dealerSchemeRetained"):
        assert ce.num(after.get(f)) == ce.num(before.get(f)), f"{f} moved with the price"


@pytest.mark.asyncio
async def test_reprice_is_owner_only(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    tok = r.json()["token"]
    res = await client.put(f"/api/price-master/{PRICE_ID}", json=body(exShowroom=999999),
                           headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 403
    row = await server.db.price_master.find_one({"priceId": PRICE_ID})
    assert ce.num(row["exShowroom"]) != 999999


@pytest.mark.asyncio
async def test_every_repriced_lead_is_audited(client):
    lid = await make_lead(client, "9355510014", booked=True, pay=20000)
    await raise_price(client)
    entry = await server.db.audit_log.find_one({"leadId": lid, "action": "reprice"})
    assert entry, "a money-moving reprice must leave an audit trail"
    assert ce.num(entry["oldValue"]["exShowroom"]) == BASE_EX
    assert ce.num(entry["newValue"]["exShowroom"]) == BASE_EX + RISE


# ==================================================================== preview
@pytest.mark.asyncio
async def test_preview_reports_impact_without_writing(client):
    lid = await make_lead(client, "9355510015", booked=True, pay=20000)
    before = await lead(lid)
    pv = (await client.get(f"/api/price-master/{PRICE_ID}/reprice-preview",
                           params={"exShowroom": BASE_EX + RISE})).json()
    assert pv["proposedExShowroom"] == BASE_EX + RISE
    assert pv["wouldRepriceCount"] >= 1
    assert any(x["leadId"] == lid and x["estimatedDelta"] == RISE for x in pv["wouldReprice"])
    after = await lead(lid)
    assert after["exShowroom"] == before["exShowroom"], "preview must not write"
    assert after["customerPayable"] == before["customerPayable"]


@pytest.mark.asyncio
async def test_preview_lists_the_leads_it_would_skip(client):
    lid = await make_lead(client, "9355510016", booked=True)
    owed = (await lead(lid))["customerOutstanding"]
    await client.post(f"/api/leads/{lid}/payments", json={"amount": owed, "paymentMode": "Cash"})
    pv = (await client.get(f"/api/price-master/{PRICE_ID}/reprice-preview",
                           params={"exShowroom": BASE_EX + RISE})).json()
    assert any(x["leadId"] == lid and "paid in full" in x["reason"] for x in pv["wouldSkip"])
