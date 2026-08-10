"""The four defects found in the deployed application, each locked by a test.

A. Scheme screen understated the scheme — Turbo Aug'26 showed only Loyalty 10,000 and
   never surfaced the Insurance Benefit entitlement.
B. OEM Claim Dashboard scheme-wise showed Loyalty 10,000 while every other total on
   the same page correctly said 20,000.
C. Earnings Report insurance column was always 0.
D. Insurance Payouts screen was empty — nothing ever created a payout entry.

C and D are the same defect: the report sums expectedPayout from db.insurance, and
nothing was writing to it.

Business rules used, none invented: the August circular EM/08-2026/001 gives Turbo
Loyalty 0/10,000/10,000 and Insurance Benefits 10,000/10,000/20,000; the payout rate
comes from the existing suggested_insurance_payout_rate (49% Storm/Turbo, 36.5% other).
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter22defects")
os.environ.setdefault("JWT_SECRET", "iter22-test-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

MODEL, VARIANT = "Turbo Max", "Maxx (PV)"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def turbo_lead(c, mobile, deliver=False):
    r = await c.post("/api/leads", json={
        "customerName": "ITER22 TURBO", "mobile": mobile, "interestedModel": MODEL,
        "variant": VARIANT, "executive": "Amit", "leadSource": "Walk-in"})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    await c.put(f"/api/leads/{lid}/scheme",
                json={"loyaltyBonus": 10000, "benefitMode": "Full Benefit"})
    if deliver:
        lead = (await c.get(f"/api/leads/{lid}")).json()
        await c.post(f"/api/leads/{lid}/payments",
                     json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
        await c.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
            "insurerName": "ICICI Lombard", "invoiceNumber": "INV-22",
            "chassisNumber": "CH-22", "numberPlate": "RJ14-22", "delivered": "Yes"})
    return lid


# ------------------------------------------------------------------ defect A
@pytest.mark.asyncio
async def test_scheme_screen_surfaces_the_insurance_entitlement(client):
    """Turbo's Insurance Benefit is an entitlement, not a staff-typed offer, so it had
    no input and was invisible. It must still be reported as part of the scheme."""
    lid = await turbo_lead(client, "9777700001")
    rules = (await client.get(f"/api/leads/{lid}/scheme-rules")).json()

    assert rules["rules"]["loyaltyBonus"]["allowed"] is True
    assert rules["rules"]["loyaltyBonus"]["maxAmount"] == 10000

    ents = {e["key"]: e for e in rules["entitlements"]}
    assert "insuranceBenefit" in ents, "Insurance Benefit missing from the scheme screen"
    ins = ents["insuranceBenefit"]
    assert ins["companyShare"] == 10000       # per the August circular
    assert ins["dealerShare"] == 10000
    assert ins["totalBenefit"] == 20000
    assert ins["automatic"] is True
    assert rules["entitlementCompanyTotal"] == 10000


@pytest.mark.asyncio
async def test_entitlement_is_not_merged_into_loyalty(client):
    lid = await turbo_lead(client, "9777700002")
    rules = (await client.get(f"/api/leads/{lid}/scheme-rules")).json()
    keys = [e["key"] for e in rules["entitlements"]]
    assert "loyaltyBonus" not in keys, "loyalty must stay a staff-entered offer, not an entitlement"
    assert rules["rules"]["loyaltyBonus"]["maxAmount"] == 10000


# ------------------------------------------------------------------ defect B
@pytest.mark.asyncio
async def test_claim_dashboard_scheme_wise_includes_every_claimed_component(client):
    """Scheme-wise walked claim["breakdown"] (staff offers only), so entitlement
    components never appeared — the section said 10,000 while the page said 20,000."""
    lid = await turbo_lead(client, "9777700003")

    claims = [c for c in (await client.get("/api/claims")).json() if c["leadId"] == lid]
    assert sorted(c["componentKey"] for c in claims) == ["insuranceBenefit", "loyaltyBonus"]
    assert ce.round2(sum(ce.num(c["eligibleClaim"]) for c in claims)) == 20000

    dash = (await client.get("/api/reports/oem-claim-dashboard")).json()
    scheme_wise = {s["scheme"]: s["value"] for s in dash["schemeWise"]}
    assert "Insurance Benefit" in scheme_wise, \
        f"Insurance Benefit missing from scheme-wise: {list(scheme_wise)}"
    assert "Loyalty" in scheme_wise

    # Scheme-wise must reconcile with the headline claim value, not undercount it.
    assert ce.round2(sum(s["value"] for s in dash["schemeWise"])) == \
        ce.round2(dash["valueSummary"]["eligibleClaim"])


@pytest.mark.asyncio
async def test_one_vehicle_is_not_counted_as_two_bookings(client):
    """A lead with two claim components must count once in monthly/executive rollups,
    even though scheme-wise legitimately lists it under both components."""
    await server.db.leads.delete_many({})
    await server.db.claims.delete_many({})
    await turbo_lead(client, "9777700004")

    dash = (await client.get("/api/reports/oem-claim-dashboard")).json()
    assert dash["bookings"] == 1
    month = [m for m in dash["monthly"] if m["month"] == "2026-08"]
    assert month and month[0]["bookings"] == 1, f"one vehicle counted as {month} bookings"
    assert month[0]["claim"] == 20000

    execs = dash["executiveWise"]
    assert len(execs) == 1 and execs[0]["bookings"] == 1 and execs[0]["claim"] == 20000

    # Scheme-wise lists the same vehicle once per component — that is correct.
    scheme_wise = {s["scheme"]: (s["count"], s["value"]) for s in dash["schemeWise"]}
    assert scheme_wise["Loyalty"] == (1, 10000)
    assert scheme_wise["Insurance Benefit"] == (1, 10000)


# ------------------------------------------------------------- defects C + D
@pytest.mark.asyncio
async def test_insurance_payout_entry_is_created_at_delivery(client):
    """Nothing created these, so the Insurance Payouts screen was permanently empty."""
    lid = await turbo_lead(client, "9777700005", deliver=True)
    entries = [e for e in (await client.get("/api/insurance")).json() if e["leadId"] == lid]
    assert len(entries) == 1, f"expected exactly one payout entry, got {len(entries)}"
    e = entries[0]
    lead = await server.db.leads.find_one({"leadId": lid})
    premium = ce.num(lead["insuranceAmount"])
    assert e["insuranceAmount"] == premium
    assert e["insuranceCompany"] == "ICICI Lombard"
    # 49% for Turbo, straight from the existing rate function — not a new rule.
    assert e["payoutRate"] == ce.suggested_insurance_payout_rate(MODEL, VARIANT)
    assert e["expectedPayout"] == ce.round2(premium * e["payoutRate"])
    assert e["receivedPayout"] == 0
    assert e["payoutOutstanding"] == e["expectedPayout"]
    assert e["status"] == "Pending"


@pytest.mark.asyncio
async def test_delivery_twice_does_not_duplicate_the_payout_entry(client):
    lid = await turbo_lead(client, "9777700006", deliver=True)
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "invoiceNumber": "INV-22",
        "chassisNumber": "CH-22", "numberPlate": "RJ14-22", "delivered": "Yes"})
    assert await server.db.insurance.count_documents({"leadId": lid}) == 1


@pytest.mark.asyncio
async def test_no_payout_entry_when_no_premium_was_charged(client):
    """Blank is meaningful: no premium means no payout is due. Nothing is invented."""
    r = await client.post("/api/leads", json={
        "customerName": "ITER22 NO PREMIUM", "mobile": "9777700007",
        "interestedModel": MODEL, "variant": VARIANT, "executive": "Amit"})
    lid = r.json()["leadId"]
    await client.put(f"/api/leads/{lid}/price-structure",
                     json={"exShowroom": 770000, "rto": 15000, "insuranceAmount": 0})
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = (await client.get(f"/api/leads/{lid}")).json()
    await client.post(f"/api/leads/{lid}/payments",
                      json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "invoiceNumber": "INV-0", "chassisNumber": "CH-0",
        "numberPlate": "RJ14-0", "delivered": "Yes"})
    assert await server.db.insurance.count_documents({"leadId": lid}) == 0


@pytest.mark.asyncio
async def test_earnings_report_insurance_column_is_populated(client):
    """The report sums expectedPayout; it read 0 only because no entries existed."""
    lid = await turbo_lead(client, "9777700008", deliver=True)
    entry = await server.db.insurance.find_one({"leadId": lid})
    report = (await client.get("/api/reports/dealer-earnings")).json()
    assert report["totals"]["insurance"] >= entry["expectedPayout"] > 0


@pytest.mark.asyncio
async def test_insurance_payout_does_not_touch_customer_accounting(client):
    """Dealer insurance income must never move what the customer owes."""
    lid = await turbo_lead(client, "9777700009", deliver=True)
    before = await server.db.leads.find_one({"leadId": lid})
    entry = await server.db.insurance.find_one({"leadId": lid})
    r = await client.put(f"/api/insurance/{entry['entryId']}", json={
        "leadId": lid, "customerName": before["customerName"],
        "model": MODEL, "variant": VARIANT, "insuranceCompany": "ICICI Lombard",
        "insuranceAmount": entry["insuranceAmount"], "receivedPayout": 5000})
    assert r.status_code == 200, r.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before["customerPayable"]
    assert after["customerOutstanding"] == before["customerOutstanding"]
    assert after["companyOutstanding"] == before["companyOutstanding"]


# ------------------------------------------------------------- claim receipts
@pytest.mark.asyncio
async def test_receiving_one_claim_component_leaves_the_other_outstanding(client):
    lid = await turbo_lead(client, "9777700010")
    r = await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    assert r.status_code == 200, r.text

    claims = {c["componentKey"]: c for c in (await client.get("/api/claims")).json()
              if c["leadId"] == lid}
    assert claims["loyaltyBonus"]["receivedAmount"] == 10000
    assert claims["loyaltyBonus"]["claimStatus"] == "Received"
    assert claims["insuranceBenefit"]["receivedAmount"] == 0
    assert claims["insuranceBenefit"]["claimStatus"] == "Pending"

    total = ce.round2(sum(ce.num(c["eligibleClaim"]) for c in claims.values()))
    received = ce.round2(sum(ce.num(c["receivedAmount"]) for c in claims.values()))
    assert (total, received, ce.round2(total - received)) == (20000, 10000, 10000)


@pytest.mark.asyncio
async def test_claim_receipt_does_not_change_customer_accounting(client):
    lid = await turbo_lead(client, "9777700011")
    before = await server.db.leads.find_one({"leadId": lid})
    await client.post("/api/claims/receipt", json={
        "leadId": lid, "componentKey": "loyaltyBonus", "amount": 10000, "date": "2026-08-20"})
    after = await server.db.leads.find_one({"leadId": lid})
    assert after["customerPayable"] == before["customerPayable"]
    assert after["customerOutstanding"] == before["customerOutstanding"]
