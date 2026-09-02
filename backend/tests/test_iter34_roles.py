"""Two role changes: an outside OEM finance desk, and a narrowed executive.

The OEM's finance manager is NOT dealership staff. That matters more than it
sounds: the /api router requires only a valid token, and 37 of its 43 GET
endpoints carry no role check of their own — so simply adding a role would have
handed an outside party the entire Lead Register, mobile numbers included.

The guard is therefore an ALLOWLIST enforced in current_user, which every /api
route depends on. It fails closed: a route added tomorrow is denied to that role
until someone deliberately opens it. These tests exist to keep it that way.

Separately, executives feed the funnel only — leads, booking + booking amount,
activities, quotations. The commercial half of the journey belongs to a TEAM
LEADER: pricing, scheme, collection, delivery, close and cancel. The TL exists
so that half never queues behind the owner, which is what happened when those
steps were owner-only — a handover could not complete until the owner logged in.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter34roles")
os.environ.setdefault("JWT_SECRET", "iter34-roles-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
BASE_MOBILE = 9534340000
OEM_EMAIL = "iter34.oem@euler.com"
OEM_PW = "oemDesk#2026"

_seq = {"n": 0}


def next_mobile():
    _seq["n"] += 1
    return str(BASE_MOBILE + _seq["n"])


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _token(email, password):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["token"]


@pytest_asyncio.fixture
async def oem(client):
    """A real OEM-finance login, created the way the owner would create it."""
    await server.db.users.delete_many({"email": OEM_EMAIL})
    r = await client.post("/api/auth/users", json={
        "email": OEM_EMAIL, "password": OEM_PW, "name": "ITER34 OEM Desk",
        "role": "oem_finance"})
    assert r.status_code == 200, r.text
    tok = await _token(OEM_EMAIL, OEM_PW)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


@pytest_asyncio.fixture
async def exec_client(client):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "executive@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def make_lead(c, name, executive="Amit"):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(), "interestedModel": TURBO[0],
        "variant": TURBO[1], "executive": executive})
    assert r.status_code == 200, r.text
    assert r.json().get("leadId"), r.text
    return r.json()["leadId"]


# ============================================== the outside role is fenced in
@pytest.mark.asyncio
async def test_the_role_exists_and_can_sign_in(oem):
    me = (await oem.get("/api/auth/me")).json()
    assert me["role"] == "oem_finance"


@pytest.mark.parametrize("path", [
    "/api/leads",
    "/api/dashboard",
    "/api/masters",
    "/api/payments",
    "/api/finance",
    "/api/insurance",
    "/api/claims",
    "/api/bookings",
    "/api/deliveries",
    "/api/activities",
    "/api/price-master",
    "/api/price-list",
    "/api/staff",
    "/api/audit-log",
    "/api/whatsapp/threads",
    "/api/reports/cancellations",
    "/api/reports/daily/manager",
    "/api/dealer-earnings",
    "/api/export",
])
@pytest.mark.asyncio
async def test_every_other_endpoint_is_denied(oem, path):
    """Not hidden in the UI — refused by the API."""
    r = await oem.get(path)
    assert r.status_code == 403, f"{path} returned {r.status_code}"


@pytest.mark.asyncio
async def test_a_specific_lead_and_its_360_are_denied(client, oem):
    lid = await make_lead(client, "ITER34 Private")
    assert (await oem.get(f"/api/leads/{lid}")).status_code == 403
    assert (await oem.get(f"/api/leads/{lid}/360")).status_code == 403


@pytest.mark.asyncio
async def test_the_role_cannot_write_anything(oem):
    assert (await oem.post("/api/leads", json={
        "customerName": "ITER34 Nope", "mobile": "9534349999"})).status_code == 403
    assert (await oem.post("/api/staff", json={"name": "x", "role": "owner"})).status_code == 403
    assert (await oem.post("/api/admin/reseed", json={})).status_code == 403


@pytest.mark.asyncio
async def test_the_allowlist_is_the_whole_permission(oem):
    """If this list grows, it should be a deliberate act with a test to match."""
    allowed = authmod.EXTERNAL_ROLE_PATHS["oem_finance"]
    assert set(allowed) == {
        "/api/auth/me", "/api/auth/change-password", "/api/reports/oem-finance"}


@pytest.mark.asyncio
async def test_a_new_endpoint_is_closed_by_default(client, oem):
    """The point of an allowlist, proved rather than asserted.

    A brand-new endpoint is registered here under the same guard every /api route
    carries. Nobody adds it to the allowlist — and the outside role is refused it
    while the owner is not. That is what "fails closed" has to mean: the next
    endpoint someone writes is denied without them having to remember anything.
    """
    from fastapi import Depends

    @server.app.get("/api/iter34-endpoint-added-later",
                    dependencies=[Depends(server.current_user)])
    async def _added_later():
        return {"sensitive": "dealer data"}

    assert (await oem.get("/api/iter34-endpoint-added-later")).status_code == 403
    assert (await client.get("/api/iter34-endpoint-added-later")).status_code == 200


# ============================================== what the OEM desk actually sees
async def _funded_delivered_lead(c, name, financer="HDFC BANK"):
    lid = await make_lead(c, name)
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": server.today(), "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await c.post(f"/api/leads/{lid}/payments", json={
        "amount": lead["customerOutstanding"], "paymentMode": "Finance",
        "financerName": financer})
    return lid


@pytest.mark.asyncio
async def test_the_report_lists_files_with_the_delay(client, oem):
    await _funded_delivered_lead(client, "ITER34 Financed")
    d = (await oem.get("/api/reports/oem-finance")).json()
    assert d["totals"]["files"] >= 1
    assert d["slaDays"] == server.FINANCE_RECEIPT_SLA_DAYS
    row = d["files"][0]
    for k in ("leadId", "customerName", "model", "financer", "fileNumber",
              "sanctioned", "received", "pending", "deliveryDate",
              "daysSinceDelivery", "status", "overdue"):
        assert k in row, k


@pytest.mark.asyncio
async def test_no_contact_detail_reaches_the_payload(client, oem):
    """The whole reason this is a separate report and not the Finance Register."""
    await _funded_delivered_lead(client, "ITER34 NoContact")
    body = (await oem.get("/api/reports/oem-finance")).text.lower()
    for banned in ("mobile", "altmobile", "village", "\"city\"", "whatsapp", "email"):
        assert banned not in body, f"{banned} leaked into the OEM report"


@pytest.mark.asyncio
async def test_no_dealer_commercial_reaches_the_payload(client, oem):
    """He sees the finance file. Not what the dealer makes on the deal."""
    await _funded_delivered_lead(client, "ITER34 NoMargin")
    body = (await oem.get("/api/reports/oem-finance")).text.lower()
    for banned in ("dealermargin", "dealertotalearnings", "schemeamount",
                   "customerpayable", "customeroutstanding", "expectedpayout",
                   "insuranceagent"):
        assert banned not in body, f"{banned} leaked into the OEM report"


@pytest.mark.asyncio
async def test_the_report_carries_received_files_too(client, oem):
    """Asked for explicitly: every file, not only what is still pending."""
    d = (await oem.get("/api/reports/oem-finance", params={"view": "received"})).json()
    assert all(r["pending"] <= 0.01 for r in d["files"])
    every = (await oem.get("/api/reports/oem-finance")).json()
    assert every["totals"]["files"] >= len(d["files"])


@pytest.mark.asyncio
async def test_views_and_filters_narrow_the_list(client, oem):
    await _funded_delivered_lead(client, "ITER34 Filter", financer="SHRIRAM")
    pend = (await oem.get("/api/reports/oem-finance", params={"view": "pending"})).json()
    assert all(r["pending"] > 0.01 for r in pend["files"])
    over = (await oem.get("/api/reports/oem-finance", params={"view": "overdue"})).json()
    assert all(r["overdue"] for r in over["files"])
    one = (await oem.get("/api/reports/oem-finance", params={"financer": "SHRIRAM"})).json()
    assert all(r["financer"] == "SHRIRAM" for r in one["files"])


@pytest.mark.asyncio
async def test_ageing_and_financer_totals_add_up(client, oem):
    d = (await oem.get("/api/reports/oem-finance")).json()
    assert sum(b["pending"] for b in d["ageing"]) == pytest.approx(d["totals"]["pending"], abs=1)
    assert sum(b["files"] for b in d["byFinancer"]) == d["totals"]["files"]


@pytest.mark.asyncio
async def test_the_owner_can_preview_the_same_report(client):
    """So you can see what the OEM sees before issuing the login."""
    assert (await client.get("/api/reports/oem-finance")).status_code == 200


@pytest.mark.asyncio
async def test_staff_roles_cannot_open_the_oem_report(exec_client):
    assert (await exec_client.get("/api/reports/oem-finance")).status_code == 403


# ============================================== the narrowed executive
@pytest.mark.asyncio
async def test_an_executive_still_feeds_leads_and_booking_amount(client, exec_client):
    """Enquiry goes to GM/Owner first. After Approve, the executive can still book."""
    r = await exec_client.post("/api/leads", json={
        "customerName": "ITER34 Exec lead", "mobile": next_mobile(),
        "interestedModel": TURBO[0], "variant": TURBO[1],
        "executive": "Executive", "budget": 185000})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("pending") is True
    rid = body["requestId"]
    names = {l["customerName"] for l in (await exec_client.get("/api/leads")).json()}
    assert "ITER34 Exec lead" not in names
    assert (await exec_client.post(f"/api/lead-requests/{rid}/approve")).status_code == 403
    ap = await client.post(f"/api/lead-requests/{rid}/approve")
    assert ap.status_code == 200, ap.text
    lid = ap.json()["leadId"]
    assert lid.startswith("LD26")
    assert (await exec_client.put(f"/api/leads/{lid}",
                                  json={"remarks": "called, interested"})).status_code == 200
    r = await exec_client.post(f"/api/leads/{lid}/convert-booking",
                               json={"bookingAmount": 10000, "executive": "Executive"})
    assert r.status_code == 200, r.text
    assert server.ce.num((await server.db.leads.find_one({"leadId": lid}))["bookingAmount"]) == 10000
    assert (await exec_client.post(f"/api/leads/{lid}/activities", json={
        "activityType": "Call", "discussion": "follow-up"})).status_code == 200


@pytest.mark.asyncio
async def test_the_booking_amount_still_posts_its_receipt(client, exec_client):
    """An executive taking a token must still be recorded as money received."""
    lid = await make_lead(client, "ITER34 Token", executive="Executive")
    await exec_client.post(f"/api/leads/{lid}/convert-booking",
                           json={"bookingAmount": 5000, "executive": "Executive"})
    pays = await server.db.payments.find({"leadId": lid}).to_list(10)
    assert sum(server.ce.num(p.get("amount")) for p in pays) == 5000


@pytest.mark.asyncio
async def test_an_executive_can_no_longer_price_or_scheme_a_deal(client, exec_client):
    lid = await make_lead(client, "ITER34 No pricing")
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    assert (await exec_client.put(f"/api/leads/{lid}/price-structure", json=ps)).status_code == 403
    assert (await exec_client.put(f"/api/leads/{lid}/scheme", json={})).status_code == 403
    assert (await exec_client.put(f"/api/leads/{lid}/scheme-allocation",
                                  json={})).status_code == 403
    assert (await exec_client.put(f"/api/leads/{lid}/extra-income", json={})).status_code == 403


@pytest.mark.asyncio
async def test_an_executive_can_no_longer_deliver_close_or_cancel(client, exec_client):
    lid = await make_lead(client, "ITER34 No exit")
    assert (await exec_client.put(f"/api/leads/{lid}/delivery",
                                  json={"delivered": "Yes"})).status_code == 403
    assert (await exec_client.post(f"/api/leads/{lid}/close",
                                   json={"closeReason": "done"})).status_code == 403
    assert (await exec_client.post(f"/api/leads/{lid}/cancel",
                                   json={"cancelReason": "Not reachable"})).status_code == 403
    assert (await exec_client.post(f"/api/leads/{lid}/revive")).status_code == 403


@pytest.mark.asyncio
async def test_an_executive_can_no_longer_move_money(client, exec_client):
    lid = await make_lead(client, "ITER34 No money")
    assert (await exec_client.post(f"/api/leads/{lid}/payments",
                                   json={"amount": 1000, "paymentMode": "Cash"})).status_code == 403
    assert (await exec_client.post(f"/api/leads/{lid}/refund",
                                   json={"amount": 100})).status_code == 403
    assert (await exec_client.post("/api/insurance", json={"leadId": lid})).status_code == 403
    assert (await exec_client.post("/api/claims/receipt", json={})).status_code == 403


@pytest.mark.asyncio
async def test_an_executive_keeps_read_access_to_what_they_must_quote(exec_client):
    """Losing the write must not blind them: they still face the customer."""
    for path in ("/api/leads", "/api/price-list", "/api/finance", "/api/executive/dashboard"):
        assert (await exec_client.get(path)).status_code == 200, path


@pytest.mark.asyncio
async def test_accounts_still_records_money(client):
    """The money desk had to keep working after executives were removed from it."""
    lid = await make_lead(client, "ITER34 Accounts money")
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": server.today(), "bookingAmount": 0})
    tok = await _token("accounts@euler.com", "euler@123")
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        r = await c.post(f"/api/leads/{lid}/payments",
                         json={"amount": 5000, "paymentMode": "Cash"})
    assert r.status_code == 200, r.text


def test_the_role_constants_say_what_changed():
    assert "oem_finance" in authmod.ALLOWED_ROLES
    assert "tl" in authmod.ALLOWED_ROLES
    assert "executive" in authmod.SALES_ROLES        # still feeds leads
    assert "executive" not in authmod.MONEY_ROLES    # no longer moves money
    assert authmod.MONEY_ROLES == ("owner", "tl", "accounts")
    # ...but an executive can still READ the finance register to answer a customer.
    assert "executive" in authmod.FINANCE_VIEW_ROLES


# ============================================== the Team Leader closes the deal
TL_EMAIL = "iter34.tl@euler.com"
TL_PW = "teamLead#2026"


@pytest_asyncio.fixture
async def tl(client):
    await server.db.users.delete_many({"email": TL_EMAIL})
    r = await client.post("/api/auth/users", json={
        "email": TL_EMAIL, "password": TL_PW, "name": "ITER34 TL", "role": "tl"})
    assert r.status_code == 200, r.text
    tok = await _token(TL_EMAIL, TL_PW)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        yield c


@pytest.mark.asyncio
async def test_an_executive_hands_over_and_a_tl_completes_it(client, exec_client, tl):
    """The whole point of the role, walked end to end across two people.

    The executive takes the enquiry and the booking; the TL prices it, collects
    and hands the vehicle over. If any step regressed to owner-only, a delivery
    would stall waiting for the owner to log in — which is exactly what the TL
    exists to prevent, and what this test catches.
    """
    lid = await make_lead(client, "ITER34 Handover", executive="Executive")
    assert (await exec_client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": server.today(), "bookingAmount": 10000,
        "executive": "Executive"})).status_code == 200

    # Executive stops here.
    ps = (await tl.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    assert (await exec_client.put(f"/api/leads/{lid}/price-structure",
                                  json=ps)).status_code == 403

    # TL takes it the rest of the way.
    assert (await tl.put(f"/api/leads/{lid}/price-structure", json=ps)).status_code == 200
    assert (await tl.put(f"/api/leads/{lid}/scheme",
                         json={"benefitMode": "No Benefit"})).status_code == 200
    lead = await server.db.leads.find_one({"leadId": lid})
    assert (await tl.post(f"/api/leads/{lid}/payments", json={
        "amount": lead["customerOutstanding"], "paymentMode": "Cash"})).status_code == 200

    agents = (await tl.get("/api/insurance-agents")).json()
    r = await tl.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "rc": "Yes", "insurerName": "ICICI Lombard",
        "insuranceAgentId": agents[0]["agentId"],
        "invoiceNumber": "INV-ITER34-TL", "chassisNumber": "CH-ITER34-TL",
        "numberPlate": "RJ34-TL01", "delivered": "Yes"})
    assert r.status_code == 200, r.text

    doc = await server.db.leads.find_one({"leadId": lid})
    assert server._is_delivered(doc) is True
    assert server.ce.num(doc["customerOutstanding"]) == 0


@pytest.mark.asyncio
async def test_a_tl_can_also_do_everything_an_executive_does(tl):
    """So a TL can cover for an executive who is out."""
    lid = await make_lead(tl, "ITER34 TL covers", executive="Amit")
    assert (await tl.put(f"/api/leads/{lid}", json={"remarks": "TL called"})).status_code == 200
    assert (await tl.post(f"/api/leads/{lid}/activities", json={
        "activityType": "Call", "discussion": "covered for Amit"})).status_code == 200
    assert (await tl.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingAmount": 5000, "executive": "Amit"})).status_code == 200


@pytest.mark.asyncio
async def test_a_tl_can_close_and_cancel(tl):
    lid = await make_lead(tl, "ITER34 TL cancels")
    assert (await tl.post(f"/api/leads/{lid}/cancel", json={
        "cancelReason": "Bought other brand"})).status_code == 200
    assert (await tl.post(f"/api/leads/{lid}/revive")).status_code == 200
    assert (await tl.post(f"/api/leads/{lid}/close", json={
        "closeReason": "Settled"})).status_code == 200


@pytest.mark.asyncio
async def test_a_tl_does_not_get_the_owner_only_commercials(tl):
    """Finishing deals is not the same as seeing what the dealership earns."""
    for path in ("/api/dealer-earnings", "/api/reports/owner-commercial",
                 "/api/reports/dealer-earnings", "/api/audit-log",
                 "/api/reports/oem-finance"):
        assert (await tl.get(path)).status_code == 403, path


@pytest.mark.asyncio
async def test_a_tl_cannot_change_masters_or_staff(tl):
    assert (await tl.post("/api/staff", json={"name": "x", "role": "owner"})).status_code == 403
    assert (await tl.post("/api/cancel-reasons", json={"reason": "x"})).status_code == 403
    assert (await tl.post("/api/admin/reseed", json={})).status_code == 403


@pytest.mark.asyncio
async def test_the_tl_sees_the_whole_showroom(tl, client):
    """Chosen deliberately over a TL-to-executive mapping: whoever is free closes
    the deal, which is how a single showroom actually runs."""
    lid = await make_lead(client, "ITER34 Someone elses", executive="Sanjay")
    assert (await tl.get(f"/api/leads/{lid}/360")).status_code == 200


def test_the_deal_desk_is_owner_tl_and_sales_gm():
    assert set(authmod.DEAL_DESK_ROLES) == {"owner", "tl", "sales_gm"}
    assert "tl" in authmod.SALES_ROLES        # covers for an executive
    assert "sales_gm" in authmod.SALES_ROLES
    assert "tl" in authmod.MONEY_ROLES        # collection precedes delivery
    assert "sales_gm" not in authmod.MONEY_ROLES  # GM chases files, does not post cash
    assert "executive" in authmod.SALES_ROLES
    assert "executive" not in authmod.MONEY_ROLES
    assert "executive" not in authmod.DEAL_DESK_ROLES
