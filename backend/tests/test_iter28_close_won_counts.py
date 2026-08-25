"""Close Won is a completed retail and must keep counting for the executive.

Closing a lead overwrites currentStatus ("Delivered" -> "Close Won") and sets
accountStatus=Closed. The dashboards built their funnel from Active leads only,
so finishing the paperwork made the retail vanish from the executive's numbers —
penalising them for completing the file.

Contract:
  * Close Won counts as delivered on every dashboard
  * it lands in the Delivered funnel bucket, not in Lost and not nowhere
  * a lead closed without a Mark Delivered is still credited, dated by closedDate
  * Lost / Cancelled / Archived stay out of the funnel
  * workflow gating is UNCHANGED — only a real Mark Delivered counts there
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter28closewon")
os.environ.setdefault("JWT_SECRET", "iter28-close-won-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
EXEC = "Amit"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def bucket(funnel, name):
    return next(x["count"] for x in funnel if x["status"] == name)


async def delivered_lead(c, mobile, plate):
    r = await c.post("/api/leads", json={
        "customerName": f"ITER28 {mobile[-4:]}", "mobile": mobile,
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": EXEC})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await c.post(f"/api/leads/{lid}/payments",
                 json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    agents = (await c.get("/api/insurance-agents")).json()
    r = await c.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "insuranceAgentId": agents[0]["agentId"],
        "invoiceNumber": f"INV-{plate}", "chassisNumber": f"CH-{plate}",
        "numberPlate": plate, "delivered": "Yes"})
    assert r.status_code == 200, r.text
    return lid


# ================================================================== unit level
def test_close_won_is_a_retail():
    assert server._is_delivered_lead({"currentStatus": "Close Won"}) is True
    assert server._is_delivered_lead({"currentStatus": "Delivered"}) is True
    assert server._is_delivered_lead({"deliveryStatus": "Delivered"}) is True


def test_lost_and_open_leads_are_not_retails():
    assert server._is_delivered_lead({"currentStatus": "Lost"}) is False
    assert server._is_delivered_lead({"currentStatus": "Booked"}) is False
    assert server._is_delivered_lead({"currentStatus": "New"}) is False


def test_close_won_buckets_as_delivered():
    assert server._status_bucket({"currentStatus": "Close Won"}) == "Delivered"


def test_workflow_gating_stays_strict():
    """_is_delivered drives delivery locks and must NOT treat Close Won as delivered."""
    assert server._is_delivered({"currentStatus": "Close Won"}) is False
    assert server._is_delivered({"currentStatus": "Delivered"}) is True


def test_funnel_population_keeps_completed_drops_lost():
    rows = [
        {"leadId": "A", "accountStatus": "Active", "currentStatus": "Booked"},
        {"leadId": "B", "accountStatus": "Closed", "currentStatus": "Close Won"},
        {"leadId": "C", "accountStatus": "Closed", "currentStatus": "Lost"},
        {"leadId": "D", "accountStatus": "Cancelled", "currentStatus": "Cancelled"},
    ]
    ids = {l["leadId"] for l in server._funnel_population(rows)}
    assert ids == {"A", "B"}


def test_retail_date_falls_back_to_closed_date():
    assert server._retail_date({"deliveryDate": "2026-08-20"}) == "2026-08-20"
    assert server._retail_date({"closedDate": "2026-08-25"}) == "2026-08-25"
    # A delivered-then-closed lead is credited on its delivery date, not the close.
    assert server._retail_date(
        {"deliveryDate": "2026-08-20", "closedDate": "2026-08-25"}) == "2026-08-20"
    assert server._retail_date({}) == ""


# ============================================================== end to end
@pytest.mark.asyncio
async def test_closing_a_delivered_lead_keeps_it_in_the_count(client):
    """The reported bug: the retail disappeared the moment the file was completed."""
    lid = await delivered_lead(client, "9422280001", "RJ28-I28A")

    before = (await client.get("/api/executive/dashboard")).json()
    r = await client.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Delivered and settled", "rc": "Yes", "numberPlate": "RJ28-I28A"})
    assert r.status_code == 200, r.text
    after = (await client.get("/api/executive/dashboard")).json()

    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["currentStatus"] == "Close Won" and lead["accountStatus"] == "Closed"

    assert after["kpis"]["myDeliveriesMtd"] == before["kpis"]["myDeliveriesMtd"], \
        "closing the file must not remove the retail from the executive's MTD"
    assert bucket(after["funnel"], "Delivered") == bucket(before["funnel"], "Delivered"), \
        "a Close Won retail must stay in the Delivered bucket"


@pytest.mark.asyncio
async def test_close_won_appears_on_the_field_and_owner_boards_too(client):
    lid = await delivered_lead(client, "9422280002", "RJ28-I28B")
    await client.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Completed", "rc": "Yes", "numberPlate": "RJ28-I28B"})

    field = (await client.get("/api/field/dashboard")).json()
    assert bucket(field["funnel"], "Delivered") >= 1

    owner = (await client.get("/api/dashboard")).json()
    assert owner["kpis"]["monthlyDeliveries"] >= 1


@pytest.mark.asyncio
async def test_a_lost_lead_is_still_excluded_from_delivered(client):
    r = await client.post("/api/leads", json={
        "customerName": "ITER28 LOST", "mobile": "9422280003",
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": EXEC})
    lid = r.json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Lost", "accountStatus": "Closed"}})
    d = (await client.get("/api/executive/dashboard")).json()
    lead = await server.db.leads.find_one({"leadId": lid})
    assert server._is_delivered_lead(lead) is False
    assert lid not in [w.get("leadId") for w in d.get("worklist", [])]


@pytest.mark.asyncio
async def test_close_won_without_delivery_is_credited_by_closed_date(client):
    """A booking closed straight to Close Won has no deliveryDate — still a retail."""
    r = await client.post("/api/leads", json={
        "customerName": "ITER28 NODELIV", "mobile": "9422280004",
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": EXEC})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    before = (await client.get("/api/executive/dashboard")).json()["kpis"]["myDeliveriesMtd"]

    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Close Won", "accountStatus": "Closed",
        "closedDate": server.today(), "closeReason": "Retail booked out"}})

    lead = await server.db.leads.find_one({"leadId": lid})
    assert not lead.get("deliveryDate")
    assert server._is_delivered_lead(lead) is True
    assert server._retail_date(lead) == server.today()
    after = (await client.get("/api/executive/dashboard")).json()["kpis"]["myDeliveriesMtd"]
    assert after == before + 1
