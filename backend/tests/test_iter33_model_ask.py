"""Model-interest marketing ask, and reading the reply back into the lead.

Leads arrive from walk-ins and referrals with no vehicle recorded, so the
register carries rows nobody can quote against. This asks the customer directly
and writes the answer back.

The parsing is deliberately timid. A wrong model written onto a lead is worse
than an empty one: the executive stops asking, and the mistake stays invisible
until somebody quotes the wrong vehicle to the customer. So it fills only an
EMPTY model, only on an unambiguous match, and stamps where the value came from.

This is also the app's only Marketing-category template — every other send is
Utility — so the runner is dry-run by default and needs an explicit confirm.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter33modelask")
os.environ.setdefault("JWT_SECRET", "iter33-model-ask-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

MODELS = ["Hi-Load", "Neo HiRange", "Storm", "Turbo Max"]
BASE_MOBILE = 9533330000


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


async def make_lead(c, name, model="", mobile=None, variant=""):
    body = {"customerName": name, "mobile": mobile or next_mobile(), "executive": "Amit"}
    if model:
        body["interestedModel"] = model
    if variant:
        body["variant"] = variant
    r = await c.post("/api/leads", json=body)
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


# ==================================================== matching a reply
@pytest.mark.parametrize("reply,expected", [
    ("Storm", "Storm"),
    ("storm", "Storm"),
    ("STORM", "Storm"),
    # Spacing and punctuation vary wildly in real replies.
    ("hi load", "Hi-Load"),
    ("hiload", "Hi-Load"),
    ("Hi-Load", "Hi-Load"),
    ("HI  LOAD", "Hi-Load"),
    ("turbo max", "Turbo Max"),
    ("turbomax", "Turbo Max"),
])
def test_a_model_name_is_matched_however_it_is_written(reply, expected):
    assert wa.match_model_reply(reply, MODELS) == expected


@pytest.mark.parametrize("reply,expected", [
    ("1", "Hi-Load"),
    ("2", "Neo HiRange"),
    ("3", "Storm"),
    ("4", "Turbo Max"),
    ("3.", "Storm"),
    ("option 3", "Storm"),
])
def test_a_menu_number_is_matched(reply, expected):
    assert wa.match_model_reply(reply, MODELS) == expected


def test_a_number_outside_the_menu_matches_nothing():
    assert wa.match_model_reply("9", MODELS) is None
    assert wa.match_model_reply("0", MODELS) is None


@pytest.mark.parametrize("reply,expected", [
    ("mujhe storm chahiye", "Storm"),
    ("I want the hi load one", "Hi-Load"),
    ("turbo max ka price kya hai", "Turbo Max"),
])
def test_a_model_named_inside_a_sentence_is_matched(reply, expected):
    assert wa.match_model_reply(reply, MODELS) == expected


def test_two_models_in_one_reply_decide_nothing():
    """'storm or turbo max?' is a question, not an answer."""
    assert wa.match_model_reply("storm ya turbo max?", MODELS) is None
    assert wa.match_model_reply("Hi-Load or Storm", MODELS) is None


def test_an_unambiguous_prefix_is_matched():
    assert wa.match_model_reply("neohi", MODELS) == "Neo HiRange"


@pytest.mark.parametrize("reply", ["", "   ", "hi", "ok", "kitna", "👍", "?"])
def test_noise_matches_nothing(reply):
    assert wa.match_model_reply(reply, MODELS) is None


def test_no_models_configured_matches_nothing():
    assert wa.match_model_reply("Storm", []) is None


# ==================================================== who is eligible
@pytest.mark.asyncio
async def test_only_leads_without_a_model_are_targeted(client):
    blank = await make_lead(client, "ITER33 Blank")
    known = await make_lead(client, "ITER33 Known", model="Storm")

    res = await wa.run_model_ask_campaign(dry_run=True)
    ids = {t["leadId"] for t in res["targets"]}
    assert blank in ids
    assert known not in ids


@pytest.mark.asyncio
async def test_an_opted_out_lead_is_never_targeted(client):
    lid = await make_lead(client, "ITER33 Opted out")
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"whatsappOptOut": True}})
    res = await wa.run_model_ask_campaign(dry_run=True)
    assert lid not in {t["leadId"] for t in res["targets"]}


@pytest.mark.asyncio
async def test_a_booked_lead_is_never_targeted(client):
    """A booking needs a Price Master match, so a booked lead always HAS a model.

    The model is blanked here afterwards to force the awkward case a legacy or
    part-migrated row can present: booked, but with no model recorded. Marketing
    a "which vehicle interests you?" message to somebody who has already paid a
    booking amount is the single worst thing this campaign could do.
    """
    lid = await make_lead(client, "ITER33 Booked", model="Turbo Max", variant="Maxx (PV)")
    r = await client.post(f"/api/leads/{lid}/convert-booking",
                          json={"bookingAmount": 5000, "executive": "Amit"})
    assert r.status_code == 200, r.text
    await server.db.leads.update_one({"leadId": lid}, {"$set": {"interestedModel": ""}})

    lead = await server.db.leads.find_one({"leadId": lid})
    assert wa.model_ask_due(lead) is False
    res = await wa.run_model_ask_campaign(dry_run=True)
    assert lid not in {t["leadId"] for t in res["targets"]}


@pytest.mark.asyncio
async def test_a_cancelled_lead_parked_out_of_the_funnel_is_not_targeted(client):
    lid = await make_lead(client, "ITER33 Parked")
    r = await client.post(f"/api/leads/{lid}/cancel",
                          json={"cancelReason": "Bought other brand"})
    assert r.status_code == 200, r.text
    res = await wa.run_model_ask_campaign(dry_run=True)
    assert lid not in {t["leadId"] for t in res["targets"]}


@pytest.mark.asyncio
async def test_the_same_lead_is_not_asked_again_inside_the_cool_off(client):
    lid = await make_lead(client, "ITER33 Recently asked")
    await server.db.leads.update_one({"leadId": lid},
                                     {"$set": {"modelAskSentAt": "2026-08-01"}})
    lead = await server.db.leads.find_one({"leadId": lid})

    assert wa.model_ask_due(lead, "2026-08-20") is False   # 19 days later
    assert wa.model_ask_due(lead, "2026-09-20") is True    # past the 45-day cool-off


# ==================================================== running the campaign
@pytest.mark.asyncio
async def test_the_preview_sends_nothing(client):
    await make_lead(client, "ITER33 Preview target")
    before = await server.db.whatsapp_messages.count_documents({"kind": "model_ask"})

    r = await client.get("/api/integrations/botspace/model-ask/preview")
    assert r.status_code == 200
    body = r.json()
    assert body["dryRun"] is True
    assert body["eligible"] >= 1
    assert body["sent"] == 0
    assert await server.db.whatsapp_messages.count_documents({"kind": "model_ask"}) == before


@pytest.mark.asyncio
async def test_the_runner_refuses_to_send_without_an_explicit_confirm(client):
    r = await client.post("/api/integrations/botspace/model-ask")
    assert r.status_code == 200
    assert r.json()["dryRun"] is True
    assert "confirm=true" in r.json()["hint"]


@pytest.mark.asyncio
async def test_the_campaign_is_owner_only(exec_client):
    assert (await exec_client.get(
        "/api/integrations/botspace/model-ask/preview")).status_code == 403
    assert (await exec_client.post(
        "/api/integrations/botspace/model-ask", params={"confirm": "true"})).status_code == 403


@pytest.mark.asyncio
async def test_the_preview_carries_the_numbered_menu(client):
    await make_lead(client, "ITER33 Menu")
    body = (await client.get("/api/integrations/botspace/model-ask/preview")).json()
    assert body["models"] == MODELS
    # The body text the customer sees, and the numbering the reply parser expects.
    assert body["menu"] == "1 Hi-Load / 2 Neo HiRange / 3 Storm / 4 Turbo Max"


# ==================================================== writing the answer back
@pytest.mark.asyncio
async def test_a_confident_reply_fills_an_empty_model(client):
    lid = await make_lead(client, "ITER33 Answers")
    lead = await server.db.leads.find_one({"leadId": lid})

    res = await wa.apply_model_reply(lead, "3")
    assert res == {"updated": True, "model": "Storm"}

    doc = await server.db.leads.find_one({"leadId": lid})
    assert doc["interestedModel"] == "Storm"
    # Always distinguishable from a model an executive typed.
    assert doc["modelSource"] == "whatsapp-reply"
    assert doc["modelCapturedAt"]


@pytest.mark.asyncio
async def test_a_reply_never_overwrites_a_model_an_executive_entered(client):
    lid = await make_lead(client, "ITER33 Already set", model="Turbo Max")
    lead = await server.db.leads.find_one({"leadId": lid})

    res = await wa.apply_model_reply(lead, "Storm")
    assert res["updated"] is False
    assert res["reason"] == "model-already-set"
    assert (await server.db.leads.find_one({"leadId": lid}))["interestedModel"] == "Turbo Max"


@pytest.mark.asyncio
async def test_an_ambiguous_reply_writes_nothing_and_says_so(client):
    lid = await make_lead(client, "ITER33 Ambiguous")
    lead = await server.db.leads.find_one({"leadId": lid})

    res = await wa.apply_model_reply(lead, "storm or hi load?")
    assert res["updated"] is False
    assert res["reason"] == "no-confident-match"
    doc = await server.db.leads.find_one({"leadId": lid})
    assert not doc.get("interestedModel")
    assert not doc.get("modelSource")


@pytest.mark.asyncio
async def test_capturing_a_model_leaves_a_trail_on_the_timeline(client):
    lid = await make_lead(client, "ITER33 Timeline")
    lead = await server.db.leads.find_one({"leadId": lid})
    await wa.apply_model_reply(lead, "Storm")

    acts = await server.db.activities.find({"leadId": lid}).to_list(20)
    assert any("Storm" in (a.get("discussion") or "") for a in acts)


# ==================================================== end to end via the webhook
@pytest.mark.asyncio
async def test_an_inbound_whatsapp_reply_updates_the_lead(client):
    mobile = next_mobile()
    lid = await make_lead(client, "ITER33 Webhook", mobile=mobile)

    res = await wa.handle_webhook({
        "phone": {"phone": mobile, "countryCode": "91"},
        "direction": "incoming",
        "payload": {"type": "text", "text": "hi load"},
    })
    assert res["leadId"] == lid
    assert res["model"] == {"updated": True, "model": "Hi-Load"}
    assert (await server.db.leads.find_one({"leadId": lid}))["interestedModel"] == "Hi-Load"


@pytest.mark.asyncio
async def test_a_stop_reply_opts_out_and_writes_no_model(client):
    mobile = next_mobile()
    lid = await make_lead(client, "ITER33 Stop", mobile=mobile)

    res = await wa.handle_webhook({
        "phone": {"phone": mobile, "countryCode": "91"},
        "direction": "incoming",
        "payload": {"type": "text", "text": "STOP"},
    })
    assert res["optOut"] is True
    doc = await server.db.leads.find_one({"leadId": lid})
    assert doc["whatsappOptOut"] is True
    assert not doc.get("interestedModel")


@pytest.mark.asyncio
async def test_an_unknown_number_is_ignored_entirely(client):
    res = await wa.handle_webhook({
        "phone": {"phone": "9111100011", "countryCode": "91"},
        "direction": "incoming",
        "payload": {"type": "text", "text": "Storm"},
    })
    assert res["ignored"] is True
    assert res["reason"] == "not-euler-lead"


@pytest.mark.asyncio
async def test_a_reply_on_a_lead_that_already_has_a_model_is_stored_but_changes_nothing(client):
    mobile = next_mobile()
    lid = await make_lead(client, "ITER33 Has model", model="Storm", mobile=mobile)

    res = await wa.handle_webhook({
        "phone": {"phone": mobile, "countryCode": "91"},
        "direction": "incoming",
        "payload": {"type": "text", "text": "turbo max"},
    })
    assert res["model"]["updated"] is False
    assert (await server.db.leads.find_one({"leadId": lid}))["interestedModel"] == "Storm"
    # The message itself is still captured — the executive needs to read it.
    msgs = await server.db.whatsapp_messages.find(
        {"leadId": lid, "direction": "inbound"}).to_list(10)
    assert any("turbo max" in (m.get("text") or "") for m in msgs)


# ==================================================== template registration
def test_the_model_ask_template_is_registered():
    assert wa.DEFAULT_TEMPLATES["modelAsk"] == "lead_model_interest"
    assert wa.MODEL_ASK_COOLOFF_DAYS >= 30
