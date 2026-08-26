"""One inbox for every WhatsApp conversation, instead of opening each lead.

Messages lived in a flat log with no thread record and no read-state, so there
was no way to see which customer had replied without opening every lead in turn.
`whatsapp_threads` keeps one row per lead, updated on every stored message.

Derived at READ time so they cannot go stale:
    sessionOpen  customer wrote within 24h  (the reply window)
    unread       lastInboundAt > lastReadAt
    needsReply   the last message was theirs

Staff messages — finance reminders and the daily reports — are deliberately NOT
threaded. The inbox is customer conversations only.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter30inbox")
os.environ.setdefault("JWT_SECRET", "iter30-inbox-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import botspace as wa  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.whatsapp_threads.delete_many({})
    await server.db.whatsapp_messages.delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def make_lead(c, mobile, name, executive="Amit"):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": mobile, "interestedModel": TURBO[0],
        "variant": TURBO[1], "executive": executive})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


async def msg(lead_id, direction, text, kind="text", status="received", audience=None):
    lead = await server.db.leads.find_one({"leadId": lead_id})
    extra = {"audience": audience} if audience else None
    return await wa._store_message(lead, direction=direction, kind=kind, text=text,
                                   phone=lead["mobile"], status=status, extra=extra)


async def threads(c, **params):
    return (await c.get("/api/whatsapp/threads", params=params)).json()


# ============================================================ thread building
@pytest.mark.asyncio
async def test_a_message_creates_one_thread_per_lead(client):
    lid = await make_lead(client, "9700010001", "ITER30 Asha")
    await msg(lid, "outbound", "Booking confirmed", kind="booking", status="accepted")
    await msg(lid, "inbound", "Thanks, when is delivery?")

    d = await threads(client)
    assert d["total"] == 1
    t = d["threads"][0]
    assert t["leadId"] == lid
    assert t["customerName"] == "ITER30 Asha"
    assert t["inboundCount"] == 1 and t["outboundCount"] == 1
    assert t["lastMessageText"] == "Thanks, when is delivery?"
    assert t["lastDirection"] == "inbound"


@pytest.mark.asyncio
async def test_thread_carries_lead_context(client):
    lid = await make_lead(client, "9700010002", "ITER30 Bharat", executive="Sanjay")
    await msg(lid, "inbound", "Price?")
    t = (await threads(client))["threads"][0]
    assert t["executive"] == "Sanjay"
    assert t["model"] == TURBO[0]
    assert t["phone"] == "9700010002"


@pytest.mark.asyncio
async def test_many_messages_do_not_create_many_threads(client):
    lid = await make_lead(client, "9700010003", "ITER30 Chetan")
    for i in range(6):
        await msg(lid, "inbound" if i % 2 else "outbound", f"m{i}")
    d = await threads(client)
    assert d["total"] == 1
    assert d["threads"][0]["inboundCount"] + d["threads"][0]["outboundCount"] == 6


@pytest.mark.asyncio
async def test_staff_messages_are_not_threaded(client):
    """Finance reminders and daily reports go to staff — not customer conversations."""
    lid = await make_lead(client, "9700010004", "ITER30 Divya")
    await msg(lid, "outbound", "Finance overdue FN26000123", kind="finance_exec",
              status="accepted")
    assert (await threads(client))["total"] == 0


@pytest.mark.asyncio
async def test_threads_are_newest_first(client):
    a = await make_lead(client, "9700010005", "ITER30 Older")
    b = await make_lead(client, "9700010006", "ITER30 Newer")
    await msg(a, "inbound", "first")
    await msg(b, "inbound", "second")
    ids = [t["leadId"] for t in (await threads(client))["threads"]]
    assert ids[0] == b


# ================================================================== filters
@pytest.mark.asyncio
async def test_needs_reply_is_where_the_customer_spoke_last(client):
    waiting = await make_lead(client, "9700010007", "ITER30 Waiting")
    handled = await make_lead(client, "9700010008", "ITER30 Handled")
    await msg(waiting, "inbound", "Are you there?")
    await msg(handled, "inbound", "Question")
    await msg(handled, "outbound", "Answered", kind="staff_reply", status="accepted")

    ids = {t["leadId"] for t in (await threads(client, filter="needs-reply"))["threads"]}
    assert waiting in ids and handled not in ids


@pytest.mark.asyncio
async def test_unread_clears_when_marked_read(client):
    lid = await make_lead(client, "9700010009", "ITER30 Unread")
    await msg(lid, "inbound", "Hello")
    assert (await threads(client, filter="unread"))["total"] == 1

    r = await client.post(f"/api/whatsapp/threads/{lid}/read")
    assert r.status_code == 200
    assert (await threads(client, filter="unread"))["total"] == 0

    # A new inbound makes it unread again.
    await msg(lid, "inbound", "Still waiting")
    assert (await threads(client, filter="unread"))["total"] == 1


@pytest.mark.asyncio
async def test_active_means_the_24h_window_is_open(client):
    fresh = await make_lead(client, "9700010010", "ITER30 Fresh")
    stale = await make_lead(client, "9700010011", "ITER30 Stale")
    await msg(fresh, "inbound", "just now")
    await msg(stale, "inbound", "ages ago")
    await server.db.whatsapp_threads.update_one(
        {"leadId": stale}, {"$set": {"lastInboundAt": "2020-01-01T00:00:00+00:00"}})

    ids = {t["leadId"] for t in (await threads(client, filter="active"))["threads"]}
    assert fresh in ids and stale not in ids


@pytest.mark.asyncio
async def test_search_matches_name_phone_and_lead_id(client):
    lid = await make_lead(client, "9700010012", "ITER30 Findme")
    await msg(lid, "inbound", "hi")
    for needle in ("findme", "9700010012", lid.lower()):
        assert (await threads(client, q=needle))["total"] == 1
    assert (await threads(client, q="nobodyhere"))["total"] == 0


@pytest.mark.asyncio
async def test_mark_read_on_a_lead_with_no_chat_is_404(client):
    r = await client.post("/api/whatsapp/threads/LD_NOPE/read")
    assert r.status_code == 404


# ================================================================== summary
@pytest.mark.asyncio
async def test_summary_counts_match_the_filters(client):
    a = await make_lead(client, "9700010013", "ITER30 SumA")
    b = await make_lead(client, "9700010014", "ITER30 SumB")
    await msg(a, "inbound", "one")
    await msg(b, "outbound", "sent", kind="booking", status="accepted")

    s = (await client.get("/api/whatsapp/summary")).json()
    assert s["threads"] == 2
    assert s["unread"] == (await threads(client, filter="unread"))["total"]
    assert s["needsReply"] == (await threads(client, filter="needs-reply"))["total"]
    assert s["activeChats"] == (await threads(client, filter="active"))["total"]


# ================================================================= sent box
@pytest.mark.asyncio
async def test_sent_box_lists_outbound_across_leads(client):
    a = await make_lead(client, "9700010015", "ITER30 SentA")
    b = await make_lead(client, "9700010016", "ITER30 SentB")
    await msg(a, "outbound", "Booking confirmed", kind="booking", status="accepted")
    await msg(b, "outbound", "Review please", kind="delivery", status="failed")
    await msg(a, "inbound", "ok")

    rows = (await client.get("/api/whatsapp/messages")).json()
    assert {r["leadId"] for r in rows} == {a, b}
    assert all(r["direction"] == "outbound" for r in rows), "inbound must not appear"


@pytest.mark.asyncio
async def test_sent_box_filters_by_kind_and_status(client):
    lid = await make_lead(client, "9700010017", "ITER30 Filter")
    await msg(lid, "outbound", "Booking", kind="booking", status="accepted")
    await msg(lid, "outbound", "Review", kind="delivery", status="failed")

    only_failed = (await client.get("/api/whatsapp/messages",
                                    params={"status": "failed"})).json()
    assert len(only_failed) == 1 and only_failed[0]["kind"] == "delivery"

    only_booking = (await client.get("/api/whatsapp/messages",
                                     params={"kind": "booking"})).json()
    assert len(only_booking) == 1 and only_booking[0]["status"] == "accepted"


# ============================================================ executive scope
@pytest.mark.asyncio
async def test_executive_sees_only_their_own_conversations(client):
    mine = await make_lead(client, "9700010018", "ITER30 Mine", executive="Executive")
    other = await make_lead(client, "9700010019", "ITER30 Other", executive="Sanjay")
    await msg(mine, "inbound", "mine")
    await msg(other, "inbound", "not mine")

    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    tok = r.json()["token"]
    hdr = {"Authorization": f"Bearer {tok}"}

    d = (await client.get("/api/whatsapp/threads", headers=hdr)).json()
    ids = {t["leadId"] for t in d["threads"]}
    assert other not in ids, "an executive must not see another executive's chats"

    sent = (await client.get("/api/whatsapp/messages", headers=hdr)).json()
    assert all(m["leadId"] != other for m in sent)


# =============================================================== backfill
@pytest.mark.asyncio
async def test_backfill_rebuilds_threads_from_the_message_log(client):
    lid = await make_lead(client, "9700010020", "ITER30 Backfill")
    await msg(lid, "outbound", "one", kind="booking", status="accepted")
    await msg(lid, "inbound", "two")
    await server.db.whatsapp_threads.delete_many({})
    assert (await threads(client))["total"] == 0

    r = await client.post("/api/admin/backfill-whatsapp-threads", json={})
    assert r.status_code == 200, r.text
    d = await threads(client)
    assert d["total"] == 1
    t = d["threads"][0]
    assert t["inboundCount"] == 1 and t["outboundCount"] == 1


@pytest.mark.asyncio
async def test_backfill_is_idempotent(client):
    lid = await make_lead(client, "9700010021", "ITER30 Twice")
    await msg(lid, "inbound", "one")
    await client.post("/api/admin/backfill-whatsapp-threads", json={})
    first = (await threads(client))["threads"][0]
    await client.post("/api/admin/backfill-whatsapp-threads", json={})
    second = (await threads(client))["threads"][0]
    assert second["inboundCount"] == first["inboundCount"] == 1


@pytest.mark.asyncio
async def test_backfill_is_owner_only(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    tok = r.json()["token"]
    res = await client.post("/api/admin/backfill-whatsapp-threads", json={},
                            headers={"Authorization": f"Bearer {tok}"})
    assert res.status_code == 403
