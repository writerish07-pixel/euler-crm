"""Confirming a model / variant must not block Mark Delivered.

A customer who has already paid keeps that price. Owner, Sales GM, Showroom
Admin and Team Leader all save delivery through the same request, so a balance
invented by the confirm shows up on every desk.
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "delivery_confirmed_variant")
os.environ.setdefault("JWT_SECRET", "delivery-confirmed-secret")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _lead(lid):
    return await server.db.leads.find_one({"leadId": lid})


async def _book(c, mobile, *, pay_full):
    created = await c.post("/api/leads", json={
        "customerName": f"Confirmed {mobile[-4:]}",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Maxx (PV)",
        "executive": "Amit",
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    booked = await c.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-09-15", "bookingAmount": 0,
    })
    assert booked.status_code == 200, booked.text
    row = await _lead(lid)
    owed = ce.num(row.get("customerOutstanding"))
    assert owed > 1000, row.get("customerPayable")
    if pay_full:
        paid = await c.post(f"/api/leads/{lid}/payments", json={
            "amount": owed, "paymentMode": "Cash",
        })
        assert paid.status_code == 200, paid.text
        row = await _lead(lid)
        assert ce.num(row.get("customerOutstanding")) <= 0.01
    return lid


async def _priced_other(c, row):
    variants = (await c.get("/api/price-master/variants", params={"model": "Turbo Max"})).json()
    current = ce.num(row.get("exShowroom"))
    for variant in variants:
        name = variant.get("variant")
        if not name or name == row.get("variant"):
            continue
        if abs(ce.num(variant.get("exShowroom")) - current) < 1:
            continue
        return name
    raise AssertionError("Turbo Max needs a second variant at a different ex-showroom")


async def _deliver(c, lid):
    agents = (await c.get("/api/insurance-agents")).json()
    assert agents, "seed insurance agents"
    return await c.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "rc": "Yes", "insurerName": "ICICI Lombard",
        "insuranceAgentId": agents[0]["agentId"],
        "delivered": "Yes", "deliveryDate": "2026-11-02",
    })


async def _login(role, email):
    await server.db.users.update_one(
        {"email": email},
        {"$set": {
            "email": email, "name": role, "role": role, "userId": f"uid-{role}-deliv",
            "passwordHash": server.authmod.hash_password("deliver-pass-1"),
        }},
        upsert=True,
    )
    c = httpx.AsyncClient(transport=httpx.ASGITransport(app=server.app), base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": "deliver-pass-1"})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = "Bearer " + r.json()["token"]
    return c


@pytest.mark.asyncio
async def test_confirming_a_paid_lead_keeps_the_price_and_delivers(client):
    lid = await _book(client, "9811200101", pay_full=True)
    before = await _lead(lid)
    other = await _priced_other(client, before)
    confirmed = await client.put(f"/api/leads/{lid}/confirm-variant", json={
        "model": "Turbo Max", "variant": other,
    })
    assert confirmed.status_code == 200, confirmed.text
    after = await _lead(lid)
    assert after["variant"] == other
    assert after.get("oemSkuConfirmed") is True
    assert ce.num(after.get("exShowroom")) == ce.num(before.get("exShowroom"))
    assert ce.num(after.get("customerOutstanding")) <= 0.01
    saved = await _deliver(client, lid)
    assert saved.status_code == 200, saved.text
    delivered = await _lead(lid)
    assert server._is_delivered(delivered) is True
    assert ce.num(delivered.get("customerOutstanding")) <= 0.01


@pytest.mark.asyncio
async def test_vehicle_edit_on_a_paid_lead_does_not_open_a_balance(client):
    lid = await _book(client, "9811200102", pay_full=True)
    before = await _lead(lid)
    other = await _priced_other(client, before)
    edited = await client.put(f"/api/leads/{lid}/vehicle", json={
        "model": "Turbo Max", "variant": other,
    })
    assert edited.status_code == 200, edited.text
    after = await _lead(lid)
    assert after["variant"] == other
    assert ce.num(after.get("exShowroom")) == ce.num(before.get("exShowroom"))
    assert ce.num(after.get("customerOutstanding")) <= 0.01
    saved = await _deliver(client, lid)
    assert saved.status_code == 200, saved.text


@pytest.mark.asyncio
async def test_unpaid_confirm_still_reprices_and_delivery_stays_blocked(client):
    lid = await _book(client, "9811200103", pay_full=False)
    before = await _lead(lid)
    other = await _priced_other(client, before)
    confirmed = await client.put(f"/api/leads/{lid}/confirm-variant", json={
        "model": "Turbo Max", "variant": other,
    })
    assert confirmed.status_code == 200, confirmed.text
    after = await _lead(lid)
    assert after["variant"] == other
    assert ce.num(after.get("exShowroom")) != ce.num(before.get("exShowroom"))
    assert ce.num(after.get("customerOutstanding")) > 0.01
    saved = await _deliver(client, lid)
    assert saved.status_code == 422
    assert "outstanding" in saved.text.lower()
    assert server._is_delivered(await _lead(lid)) is False


@pytest.mark.asyncio
async def test_each_deal_desk_can_deliver_a_confirmed_paid_lead(client):
    for role, mobile in (
            ("tl", "9811200111"),
            ("sales_gm", "9811200112"),
            ("team_lead", "9811200113"),
    ):
        lid = await _book(client, mobile, pay_full=True)
        before = await _lead(lid)
        other = await _priced_other(client, before)
        confirmed = await client.put(f"/api/leads/{lid}/confirm-variant", json={
            "model": "Turbo Max", "variant": other,
        })
        assert confirmed.status_code == 200, confirmed.text
        if role == "team_lead":
            # A team leader only delivers files on their own team.
            await server.db.leads.update_one(
                {"leadId": lid}, {"$set": {"executive": "team_lead"}})
        who = await _login(role, f"{role}.mark@euler.com")
        try:
            saved = await _deliver(who, lid)
            assert saved.status_code == 200, (role, saved.text)
        finally:
            await who.aclose()
        assert server._is_delivered(await _lead(lid)) is True


@pytest.mark.asyncio
async def test_showroom_admin_delivers_a_lead_already_repriced_by_confirm(client):
    lid = await _book(client, "9811200114", pay_full=True)
    before = await _lead(lid)
    other = await _priced_other(client, before)
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "variant": other,
        "originalModel": before.get("interestedModel"),
        "originalVariant": before.get("variant"),
        "oemSkuConfirmed": True,
        "exShowroom": ce.round2(ce.num(before.get("exShowroom")) + 20000),
        "useDealPrice": False,
    }})
    await server.recompute_lead(lid)
    assert ce.num((await _lead(lid)).get("customerOutstanding")) > 1000
    who = await _login("tl", "tl.already@euler.com")
    try:
        saved = await _deliver(who, lid)
        assert saved.status_code == 200, saved.text
    finally:
        await who.aclose()
    done = await _lead(lid)
    assert server._is_delivered(done) is True
    assert ce.num(done.get("customerOutstanding")) <= 0.01


@pytest.mark.asyncio
async def test_already_repriced_confirmed_lead_delivers_from_every_desk(client):
    """A file confirmed before this fix still has the catalog balance on it."""
    lid = await _book(client, "9811200104", pay_full=True)
    before = await _lead(lid)
    other = await _priced_other(client, before)
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "variant": other,
        "originalModel": before.get("interestedModel"),
        "originalVariant": before.get("variant"),
        "oemSkuConfirmed": True,
        "exShowroom": ce.round2(ce.num(before.get("exShowroom")) + 20000),
        "useDealPrice": False,
    }})
    await server.recompute_lead(lid)
    damaged = await _lead(lid)
    assert ce.num(damaged.get("customerOutstanding")) > 1000

    desks = {
        "owner": ("/api/dashboard", "/api/accounts/dashboard", "/api/executive/dashboard",
                  "/api/sales-gm/dashboard", "/api/field/dashboard"),
        "tl": ("/api/dashboard", "/api/executive/dashboard", "/api/accounts/dashboard"),
        "sales_gm": ("/api/dashboard", "/api/sales-gm/dashboard", "/api/accounts/dashboard"),
        "team_lead": ("/api/dashboard", "/api/executive/dashboard"),
        "accounts": ("/api/accounts/dashboard", "/api/dashboard"),
    }
    opened = await client.get(f"/api/leads/{lid}/360")
    assert opened.status_code == 200, opened.text
    assert ce.num(opened.json()["lead"].get("customerOutstanding")) <= 0.01

    for role, paths in desks.items():
        who = client if role == "owner" else await _login(role, f"{role}.deliver@euler.com")
        try:
            for path in paths:
                board = await who.get(path)
                assert board.status_code == 200, (role, path, board.status_code, board.text[:240])
            if role == "accounts":
                refused = await _deliver(who, lid)
                assert refused.status_code == 403
            elif role == "owner":
                saved = await _deliver(who, lid)
                assert saved.status_code == 200, saved.text
        finally:
            if who is not client:
                await who.aclose()
    done = await _lead(lid)
    assert server._is_delivered(done) is True
    assert ce.num(done.get("customerOutstanding")) <= 0.01
