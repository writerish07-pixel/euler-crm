"""Insurance agents (brokers) with per-agent payout slabs.

Before this, the payout rate was one hard-coded pair — 49% Storm/Turbo, 36.5%
everything else — with nowhere to record WHICH agent was paying it. A second
agent on a different slab could not be modelled at all.

Contract:
  * an agent carries a slab list keyed on model family, with a "*" catch-all
  * the rate resolves manual > agent slab > agent catch-all > legacy 49/36.5
  * the resolved rate is SNAPSHOT on the entry, so editing a slab later never
    restates money already booked into dealer earnings
  * the agent is chosen at delivery and flows into the entry automatically
  * the register behaves like the Finance Register: pending / overdue views,
    per-agent rollup, and an agent-wise payout receipt ledger
  * payout is due by the 10th of the month AFTER the policy month
  * seeding is amount-preserving: every pre-agent entry keeps its numbers
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter26agents")
os.environ.setdefault("JWT_SECRET", "iter26-insurance-agent-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

AGENT_1 = [
    {"modelFamily": "storm", "payoutRatePct": 49, "effectiveFrom": "", "effectiveTo": ""},
    {"modelFamily": "turbo", "payoutRatePct": 49, "effectiveFrom": "", "effectiveTo": ""},
    {"modelFamily": "*", "payoutRatePct": 36.5, "effectiveFrom": "", "effectiveTo": ""},
]
AGENT_2 = [
    {"modelFamily": "storm", "payoutRatePct": 52, "effectiveFrom": "", "effectiveTo": ""},
    {"modelFamily": "turbo", "payoutRatePct": 52, "effectiveFrom": "", "effectiveTo": ""},
    {"modelFamily": "*", "payoutRatePct": 42, "effectiveFrom": "", "effectiveTo": ""},
]


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def agents_by_name(c):
    return {a["agentName"]: a for a in (await c.get("/api/insurance-agents")).json()}


# =========================================================== slab resolution
@pytest.mark.parametrize("model,a1,a2", [
    ("Turbo Max", 0.49, 0.52),
    ("Storm", 0.49, 0.52),
    ("Hi-Load", 0.365, 0.42),
    ("HiCity", 0.365, 0.42),
    ("Neo HiRange", 0.365, 0.42),
])
def test_each_agent_resolves_its_own_slab(model, a1, a2):
    """The whole point: same vehicle, two agents, two different payouts."""
    one = ce.resolve_insurance_payout_rate({"agentId": "A1", "slabs": AGENT_1}, model)
    two = ce.resolve_insurance_payout_rate({"agentId": "A2", "slabs": AGENT_2}, model)
    assert one["rate"] == a1
    assert two["rate"] == a2


def test_rate_precedence_manual_beats_slab():
    r = ce.resolve_insurance_payout_rate({"slabs": AGENT_2}, "Turbo Max", manual_rate=15)
    assert r["rate"] == 0.15 and r["source"] == "manual"
    # a percent typed as 15 must not be read as 1500%
    assert ce.resolve_insurance_payout_rate({}, "Turbo Max", manual_rate=0.15)["rate"] == 0.15


def test_family_slab_beats_catch_all():
    r = ce.resolve_insurance_payout_rate({"slabs": AGENT_2}, "Turbo Max")
    assert r["source"] == "agent-slab" and r["slabFamily"] == "turbo"
    r = ce.resolve_insurance_payout_rate({"slabs": AGENT_2}, "Hi-Load")
    assert r["source"] == "agent-catch-all"


def test_no_agent_falls_back_to_the_legacy_rule():
    """Every entry created before agents existed must still resolve a rate."""
    assert ce.resolve_insurance_payout_rate(None, "Turbo Max")["rate"] == 0.49
    assert ce.resolve_insurance_payout_rate({}, "Hi-Load")["rate"] == 0.365
    assert ce.resolve_insurance_payout_rate({}, "Hi-Load")["source"] == "legacy-default"


def test_slab_effective_dates_are_honoured():
    dated = [{"modelFamily": "*", "payoutRatePct": 40, "effectiveFrom": "2026-09-01", "effectiveTo": ""}]
    agent = {"slabs": dated}
    assert ce.resolve_insurance_payout_rate(agent, "Hi-Load", on_date="2026-08-31")["rate"] == 0.365
    assert ce.resolve_insurance_payout_rate(agent, "Hi-Load", on_date="2026-09-01")["rate"] == 0.40


def test_legacy_rule_is_unchanged():
    """Guards the ERP audit R18 check and the parity suites."""
    assert ce.suggested_insurance_payout_rate("Turbo Max") == 0.49
    assert ce.suggested_insurance_payout_rate("Storm") == 0.49
    assert ce.suggested_insurance_payout_rate("Hi-Load") == 0.365


# ============================================================ settlement TAT
def test_payout_is_due_by_the_10th_of_the_next_month():
    assert ce.insurance_payout_due_by("2026-08-01") == "2026-09-10"
    assert ce.insurance_payout_due_by("2026-08-31") == "2026-09-10"
    assert ce.insurance_payout_due_by("2026-12-15") == "2027-01-10"


def test_undated_entry_is_never_flagged_overdue():
    assert ce.insurance_payout_due_by("") == ""
    assert ce.insurance_payout_due_by(None) == ""
    assert server._insurance_enrich(
        {"payoutOutstanding": 5000, "status": "Pending"})["overdue"] is False


def test_settled_entry_is_neither_pending_nor_overdue():
    e = server._insurance_enrich({"payoutOutstanding": 0, "status": "Received",
                                  "policyDate": "2020-01-01"})
    assert e["pending"] is False and e["overdue"] is False
    # customer-arranged insurance carries no dealer payout at all
    na = server._insurance_enrich({"payoutOutstanding": 0, "status": "N/A — customer arranged",
                                   "policyDate": "2020-01-01"})
    assert na["pending"] is False


# ================================================================ agent CRUD
@pytest.mark.asyncio
async def test_two_agents_are_seeded_with_the_stated_slabs(client):
    agents = await agents_by_name(client)
    assert "Agent 1" in agents and "Agent 2" in agents
    a1 = {s["modelFamily"]: s["payoutRatePct"] for s in agents["Agent 1"]["slabs"]}
    a2 = {s["modelFamily"]: s["payoutRatePct"] for s in agents["Agent 2"]["slabs"]}
    assert a1 == {"storm": 49.0, "turbo": 49.0, "*": 36.5}
    assert a2 == {"storm": 52.0, "turbo": 52.0, "*": 42.0}
    assert agents["Agent 1"]["isDefault"] is True
    assert agents["Agent 2"]["isDefault"] is False


@pytest.mark.asyncio
async def test_seeding_is_idempotent(client):
    before = len((await client.get("/api/insurance-agents")).json())
    await client.post("/api/admin/seed-insurance-agents", json={})
    await client.post("/api/admin/seed-insurance-agents", json={})
    assert len((await client.get("/api/insurance-agents")).json()) == before


@pytest.mark.asyncio
async def test_agent_can_be_renamed_and_reslabbed(client):
    """The seeded names are placeholders — renaming to the real agent is the
    first thing the owner will do, and it must not disturb the slabs."""
    agents = await agents_by_name(client)
    aid = agents["Agent 2"]["agentId"]
    r = await client.put(f"/api/insurance-agents/{aid}", json={
        "agentName": "Bharat Insurance Services", "agentCode": "BIS",
        "status": "Active", "isDefault": False, "slabs": AGENT_2})
    assert r.status_code == 200, r.text
    assert r.json()["agentName"] == "Bharat Insurance Services"
    assert {s["modelFamily"]: s["payoutRatePct"] for s in r.json()["slabs"]} == {
        "storm": 52.0, "turbo": 52.0, "*": 42.0}
    # Restore — the rest of the suite addresses this agent by its seeded name.
    back = await client.put(f"/api/insurance-agents/{aid}", json={
        "agentName": "Agent 2", "status": "Active", "isDefault": False, "slabs": AGENT_2})
    assert back.status_code == 200, back.text


@pytest.mark.asyncio
async def test_duplicate_agent_name_is_rejected(client):
    r = await client.post("/api/insurance-agents", json={"agentName": "Agent 1", "slabs": []})
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_only_one_agent_can_be_default(client):
    r = await client.post("/api/insurance-agents", json={
        "agentName": "ITER26 Third Agent", "isDefault": True, "slabs": AGENT_1})
    assert r.status_code == 200, r.text
    defaults = [a for a in (await client.get("/api/insurance-agents")).json() if a["isDefault"]]
    assert len(defaults) == 1 and defaults[0]["agentName"] == "ITER26 Third Agent"
    # restore Agent 1 as default for the rest of the suite
    agents = await agents_by_name(client)
    await client.put(f"/api/insurance-agents/{agents['Agent 1']['agentId']}", json={
        "agentName": "Agent 1", "isDefault": True, "slabs": AGENT_1})
    await client.delete(f"/api/insurance-agents/{agents['ITER26 Third Agent']['agentId']}")


@pytest.mark.asyncio
async def test_slab_percent_is_stored_as_percent_not_fraction(client):
    """Slabs hold 52 meaning 52%; entries hold 0.52. Mixing them silently halves payouts."""
    agents = await agents_by_name(client)
    for slab in agents["Agent 2"]["slabs"]:
        assert slab["payoutRatePct"] > 1


@pytest.mark.asyncio
async def test_agent_in_use_cannot_be_deleted(client):
    agents = await agents_by_name(client)
    aid = agents["Agent 1"]["agentId"]
    await server.db.insurance.insert_one({
        "entryId": "INS26DELGUARD", "leadId": "", "customerName": "ITER26 Guard",
        "insuranceAgentId": aid, "insuranceAmount": 1000, "expectedPayout": 365,
        "receivedPayout": 0, "payoutOutstanding": 365, "status": "Pending"})
    r = await client.delete(f"/api/insurance-agents/{aid}")
    assert r.status_code == 409
    assert "Inactive" in r.json()["detail"]
    await server.db.insurance.delete_one({"entryId": "INS26DELGUARD"})


# ================================================= entry uses the agent slab
async def make_entry(c, agent_id, model, premium, **extra):
    r = await c.post("/api/insurance", json={
        "customerName": f"ITER26 {model}", "model": model, "insuranceAmount": premium,
        "insuranceAgentId": agent_id, "insuranceCompany": "ICICI Lombard",
        "policyDate": "2026-08-10", **extra})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_entry_takes_the_selected_agents_rate(client):
    agents = await agents_by_name(client)
    one = await make_entry(client, agents["Agent 1"]["agentId"], "Hi-Load", 20000)
    two = await make_entry(client, agents["Agent 2"]["agentId"], "Hi-Load", 20000)
    assert one["payoutRate"] == 0.365 and one["expectedPayout"] == 7300
    assert two["payoutRate"] == 0.42 and two["expectedPayout"] == 8400
    assert two["insuranceAgentName"] == agents["Agent 2"]["agentName"]


@pytest.mark.asyncio
async def test_entry_snapshots_the_rate_source(client):
    agents = await agents_by_name(client)
    e = await make_entry(client, agents["Agent 2"]["agentId"], "Turbo Max", 30000)
    assert e["payoutRate"] == 0.52
    assert e["payoutRateSource"] == "agent-slab"
    assert e["payoutSlabFamily"] == "turbo"


@pytest.mark.asyncio
async def test_editing_a_slab_does_not_restate_an_existing_entry(client):
    """The safety property: booked earnings must never move under the owner's feet."""
    agents = await agents_by_name(client)
    aid = agents["Agent 2"]["agentId"]
    entry = await make_entry(client, aid, "Hi-Load", 10000)
    assert entry["expectedPayout"] == 4200

    bumped = [dict(s, payoutRatePct=90) for s in AGENT_2]
    r = await client.put(f"/api/insurance-agents/{aid}",
                         json={"agentName": agents["Agent 2"]["agentName"], "slabs": bumped})
    assert r.status_code == 200, r.text

    after = await server.db.insurance.find_one({"entryId": entry["entryId"]})
    assert after["payoutRate"] == 0.42
    assert after["expectedPayout"] == 4200

    # restore
    await client.put(f"/api/insurance-agents/{aid}",
                     json={"agentName": agents["Agent 2"]["agentName"], "slabs": AGENT_2})


@pytest.mark.asyncio
async def test_owner_manual_rate_still_overrides_the_slab(client):
    agents = await agents_by_name(client)
    e = await make_entry(client, agents["Agent 2"]["agentId"], "Hi-Load", 10000, payoutRate=25)
    assert e["payoutRate"] == 0.25
    assert e["payoutRateSource"] == "manual"
    assert e["expectedPayout"] == 2500


# ================================================== agent chosen at delivery
TURBO = ("Turbo Max", "Maxx (PV)")       # family "turbo"  -> 49% / 52%
HILOAD = ("Hi-Load", "TR-NC (HiLoad)")   # family "hiload" -> catch-all 36.5% / 42%


async def delivered_lead(c, mobile, model_variant, agent_id, plate):
    model, variant = model_variant
    r = await c.post("/api/leads", json={
        "customerName": "ITER26 DELIV", "mobile": mobile, "interestedModel": model,
        "variant": variant, "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await c.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    await c.put(f"/api/leads/{lid}/price-structure", json=ps)
    await c.post(f"/api/leads/{lid}/convert-booking",
                 json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await c.post(f"/api/leads/{lid}/payments",
                 json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    r = await c.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "insuranceAgentId": agent_id,
        "invoiceNumber": f"INV-{plate}", "chassisNumber": f"CH-{plate}",
        "numberPlate": plate, "delivered": "Yes"})
    assert r.status_code == 200, r.text
    return lid


@pytest.mark.asyncio
async def test_agent_picked_at_delivery_lands_on_the_entry(client):
    agents = await agents_by_name(client)
    aid = agents["Agent 2"]["agentId"]
    lid = await delivered_lead(client, "9266260001", TURBO, aid, "RJ26-I26A2")
    entry = await server.db.insurance.find_one({"leadId": lid})
    assert entry["insuranceAgentId"] == aid
    assert entry["payoutRate"] == 0.52
    assert entry["expectedPayout"] == ce.round2(entry["insuranceAmount"] * 0.52)


@pytest.mark.asyncio
async def test_same_vehicle_two_agents_two_earnings(client):
    """End to end: the selected agent drives dealer earnings."""
    agents = await agents_by_name(client)
    l1 = await delivered_lead(client, "9266260002", TURBO,
                              agents["Agent 1"]["agentId"], "RJ26-I26E1")
    l2 = await delivered_lead(client, "9266260003", TURBO,
                              agents["Agent 2"]["agentId"], "RJ26-I26E2")
    a = await server.db.leads.find_one({"leadId": l1})
    b = await server.db.leads.find_one({"leadId": l2})
    ea = await server.db.insurance.find_one({"leadId": l1})
    eb = await server.db.insurance.find_one({"leadId": l2})
    assert ea["insuranceAmount"] == eb["insuranceAmount"]      # same vehicle, same premium
    assert ea["payoutRate"] == 0.49 and eb["payoutRate"] == 0.52
    assert b["dealerInsuranceIncome"] > a["dealerInsuranceIncome"]
    assert b["dealerInsuranceIncome"] - a["dealerInsuranceIncome"] == ce.round2(
        ea["insuranceAmount"] * 0.03)
    assert b["dealerTotalEarnings"] > a["dealerTotalEarnings"]


@pytest.mark.asyncio
async def test_unknown_agent_at_delivery_is_rejected(client):
    r = await client.put("/api/leads/LD_NOPE/delivery", json={"insuranceAgentId": "IA26NOPE"})
    assert r.status_code in (404, 422)


@pytest.mark.asyncio
async def test_blank_agent_on_redelivery_keeps_the_existing_agent(client):
    """Re-saving delivery paperwork must not wipe the agent off a booked payout."""
    agents = await agents_by_name(client)
    aid = agents["Agent 2"]["agentId"]
    lid = await delivered_lead(client, "9266260004", HILOAD, aid, "RJ26-I26KEEP")
    r = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "ICICI Lombard", "insuranceAgentId": "",
        "invoiceNumber": "INV-RJ26-I26KEEP", "chassisNumber": "CH-RJ26-I26KEEP",
        "numberPlate": "RJ26-I26KEEP", "delivered": "Yes"})
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"leadId": lid})
    assert lead["insuranceAgentId"] == aid
    entry = await server.db.insurance.find_one({"leadId": lid})
    assert entry["insuranceAgentId"] == aid and entry["payoutRate"] == 0.42


# =========================================== register behaves like Finance
@pytest.mark.asyncio
async def test_pending_and_overdue_views(client):
    agents = await agents_by_name(client)
    aid = agents["Agent 1"]["agentId"]
    old = await make_entry(client, aid, "Hi-Load", 10000, policyDate="2020-01-15")
    fresh = await make_entry(client, aid, "Hi-Load", 10000, policyDate="2099-01-15")

    pending = {e["entryId"] for e in (await client.get("/api/insurance?view=pending")).json()}
    overdue = {e["entryId"] for e in (await client.get("/api/insurance?view=overdue")).json()}
    assert old["entryId"] in pending and fresh["entryId"] in pending
    assert old["entryId"] in overdue, "a 2020 policy is well past the 10th-of-next-month TAT"
    assert fresh["entryId"] not in overdue
    assert overdue <= pending, "overdue must be a subset of pending"


@pytest.mark.asyncio
async def test_entries_can_be_filtered_by_agent(client):
    agents = await agents_by_name(client)
    a2 = agents["Agent 2"]["agentId"]
    rows = (await client.get(f"/api/insurance?agent_id={a2}")).json()
    assert rows, "expected entries for agent 2"
    assert all(r["insuranceAgentId"] == a2 for r in rows)


@pytest.mark.asyncio
async def test_agent_rollup_totals_match_the_entries(client):
    rollup = {r["agentId"]: r for r in (await client.get("/api/insurance/agents-rollup")).json()}
    entries = (await client.get("/api/insurance")).json()
    for aid, row in rollup.items():
        mine = [e for e in entries if (e.get("insuranceAgentId") or "") == aid]
        assert row["entries"] == len(mine)
        assert row["expected"] == ce.round2(sum(ce.num(e["expectedPayout"]) for e in mine))
        assert row["received"] == ce.round2(sum(ce.num(e["receivedPayout"]) for e in mine))
        assert row["outstanding"] == ce.round2(
            sum(ce.num(e["payoutOutstanding"]) for e in mine))


@pytest.mark.asyncio
async def test_receipt_ledger_is_agent_wise(client):
    agents = await agents_by_name(client)
    aid = agents["Agent 2"]["agentId"]
    entry = await make_entry(client, aid, "Hi-Load", 10000)      # expected 4200
    r = await client.post(f"/api/insurance/{entry['entryId']}/receipt",
                          json={"amount": 1200, "date": "2026-09-05", "reference": "UTR-A2-1"})
    assert r.status_code == 200, r.text

    ledger = (await client.get(f"/api/insurance/receipts?agent_id={aid}")).json()
    mine = [x for x in ledger if x["entryId"] == entry["entryId"]]
    assert len(mine) == 1
    assert mine[0]["amount"] == 1200
    assert mine[0]["insuranceAgentId"] == aid
    assert mine[0]["reference"] == "UTR-A2-1"
    assert all(x["insuranceAgentId"] == aid for x in ledger)


@pytest.mark.asyncio
async def test_receipt_reduces_outstanding_and_settles(client):
    agents = await agents_by_name(client)
    entry = await make_entry(client, agents["Agent 2"]["agentId"], "Hi-Load", 10000)
    await client.post(f"/api/insurance/{entry['entryId']}/receipt",
                      json={"amount": 200, "date": "2026-09-06"})
    mid = await server.db.insurance.find_one({"entryId": entry["entryId"]})
    assert mid["status"] == "Partial" and mid["payoutOutstanding"] == 4000
    await client.post(f"/api/insurance/{entry['entryId']}/receipt",
                      json={"amount": 4000, "date": "2026-09-07"})
    done = await server.db.insurance.find_one({"entryId": entry["entryId"]})
    assert done["status"] == "Received" and done["payoutOutstanding"] == 0


@pytest.mark.asyncio
async def test_over_receipt_is_rejected(client):
    agents = await agents_by_name(client)
    entry = await make_entry(client, agents["Agent 2"]["agentId"], "Hi-Load", 10000)
    r = await client.post(f"/api/insurance/{entry['entryId']}/receipt",
                          json={"amount": 9999, "date": "2026-09-08"})
    assert r.status_code == 422
    assert "more than this entry still expects" in r.json()["detail"]


@pytest.mark.asyncio
async def test_double_click_receipt_is_rejected(client):
    """A double submit used to book the insurer payout twice."""
    agents = await agents_by_name(client)
    entry = await make_entry(client, agents["Agent 2"]["agentId"], "Hi-Load", 10000)
    body = {"amount": 1000, "date": "2026-09-09", "reference": "UTR-DUP"}
    first = await client.post(f"/api/insurance/{entry['entryId']}/receipt", json=body)
    assert first.status_code == 200, first.text
    second = await client.post(f"/api/insurance/{entry['entryId']}/receipt", json=body)
    assert second.status_code == 409
    doc = await server.db.insurance.find_one({"entryId": entry["entryId"]})
    assert doc["receivedPayout"] == 1000
    assert len(doc["receipts"]) == 1


@pytest.mark.asyncio
async def test_payout_report_breaks_down_by_agent(client):
    rep = (await client.get("/api/reports/insurance-payout")).json()
    assert "byAgent" in rep
    names = {r["key"] for r in rep["byAgent"]}
    assert names, "expected at least one agent bucket"
    assert ce.round2(sum(r["expected"] for r in rep["byAgent"])) == rep["totals"]["expected"]


# ============================================== migration is amount-preserving
@pytest.mark.asyncio
async def test_pre_agent_entry_is_stamped_without_changing_its_money(client):
    await server.db.insurance.insert_one({
        "entryId": "INS26LEGACY1", "leadId": "", "customerName": "ITER26 Legacy",
        "model": "Hi-Load", "insuranceAmount": 20000, "payoutRate": 0.365,
        "expectedPayout": 7300, "receivedPayout": 1000, "payoutOutstanding": 6300,
        "status": "Partial"})
    res = await client.post("/api/admin/seed-insurance-agents", json={})
    assert res.status_code == 200, res.text

    doc = await server.db.insurance.find_one({"entryId": "INS26LEGACY1"})
    agents = await agents_by_name(client)
    assert doc["insuranceAgentId"] == agents["Agent 1"]["agentId"]
    assert doc["payoutRate"] == 0.365
    assert doc["expectedPayout"] == 7300
    assert doc["receivedPayout"] == 1000
    assert doc["payoutOutstanding"] == 6300
    assert doc["status"] == "Partial"


@pytest.mark.asyncio
async def test_self_arranged_insurance_still_earns_no_payout(client):
    """Agent selection must not resurrect a payout the customer's own policy never earns."""
    agents = await agents_by_name(client)
    r = await client.post("/api/leads", json={
        "customerName": "ITER26 SELF", "mobile": "9266260009",
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": "Amit"})
    lid = r.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    ps["insuranceArrangedBy"] = "self"
    await client.put(f"/api/leads/{lid}/price-structure", json=ps)
    await client.post(f"/api/leads/{lid}/convert-booking",
                      json={"bookingDate": "2026-08-09", "bookingAmount": 0})
    lead = await server.db.leads.find_one({"leadId": lid})
    await client.post(f"/api/leads/{lid}/payments",
                      json={"amount": lead["customerOutstanding"], "paymentMode": "Cash"})
    await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes", "rc": "Yes",
        "insurerName": "Own", "insuranceAgentId": agents["Agent 2"]["agentId"],
        "invoiceNumber": "INV-I26SELF", "chassisNumber": "CH-I26SELF",
        "numberPlate": "RJ26-I26SELF", "delivered": "Yes"})
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("dealerInsuranceIncome")) == 0
