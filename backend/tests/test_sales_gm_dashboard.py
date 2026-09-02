"""Sales GM: showroom-wide pipeline, deal desk, no money posting."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "sales_gm_dashboard_tests")
os.environ.setdefault("JWT_SECRET", "sales-gm-dashboard-secret-32ch!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import server  # noqa: E402

GM_EMAIL = "salesgm@euler.com"
GM_PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _token(email, password=GM_PW):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["token"]


@pytest.mark.asyncio
async def test_sales_gm_dashboard_showroom_wide(client):
    await server.db.leads.delete_many({})
    await server.db.leads.insert_one({
        "leadId": "LD-GM-1", "customerName": "GM Cust", "executive": "Amit",
        "leadSource": "Walk-in", "interestedModel": "Storm",
        "currentStatus": "Booked", "accountStatus": "Active",
        "createdDate": server.this_month() + "-01",
        "bookingDate": server.this_month() + "-02",
        "customerOutstanding": 12000,
        "nextFollowupDate": "2020-01-01",
    })
    tok = await _token(GM_EMAIL)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        r = await c.get("/api/sales-gm/dashboard")
    assert r.status_code == 200, r.text
    body = r.json()
    assert "kpis" in body
    assert "executiveScoreboard" in body
    assert "worklist" in body
    assert "executiveIncentive" in body
    assert "executives" in body["executiveIncentive"]
    assert body["kpis"]["bookingsMtd"] >= 1
    assert body["kpis"]["customerOutstanding"] >= 12000


@pytest.mark.asyncio
async def test_executive_and_accounts_cannot_open_gm_dashboard(client):
    for email in ("executive@euler.com", "accounts@euler.com", "asm@euler.com"):
        tok = await _token(email)
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.headers.update({"Authorization": f"Bearer {tok}"})
            r = await c.get("/api/sales-gm/dashboard")
        assert r.status_code == 403, (email, r.text)


@pytest.mark.asyncio
async def test_gm_sees_all_leads_and_commercials(client):
    r = await client.post("/api/leads", json={
        "customerName": "GM Other Exec", "mobile": "9888800001",
        "interestedModel": "Storm", "variant": "Storm LR (PV) Reg C7 6.6kWh",
        "executive": "Sanjay", "leadSource": "Walk-in",
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    tok = await _token(GM_EMAIL)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        listing = await c.get("/api/leads")
        assert listing.status_code == 200
        assert any(x["leadId"] == lid for x in listing.json())
        d360 = await c.get(f"/api/leads/{lid}/360")
        assert d360.status_code == 200, d360.text
        assert d360.json().get("fieldView") is not True
        assert "commercials" in d360.json()


@pytest.mark.asyncio
async def test_gm_is_deal_desk_not_money_desk(client):
    created = await client.post("/api/leads", json={
        "customerName": "GM Desk", "mobile": "9888800002",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)",
        "executive": "Amit", "leadSource": "Walk-in",
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    ps = (await client.get(f"/api/leads/{lid}/price-preview")).json()["priceStructure"]
    tok = await _token(GM_EMAIL)
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        price = await c.put(f"/api/leads/{lid}/price-structure", json=ps)
        assert price.status_code == 200, price.text
        pay = await c.post(f"/api/leads/{lid}/payments", json={
            "amount": 1000, "paymentMode": "Cash",
        })
        assert pay.status_code == 403, pay.text
        fin = await c.get("/api/finance")
        assert fin.status_code == 200, fin.text
        earn = await c.get("/api/dealer-earnings")
        assert earn.status_code == 403, earn.text
        master = await c.get("/api/incentive-master")
        assert master.status_code == 403, master.text
        board = await c.get("/api/executive-incentive/board")
        assert board.status_code == 200, board.text
        assert "executives" in board.json()


def test_sales_gm_is_on_the_role_constants():
    assert "sales_gm" in authmod.ALLOWED_ROLES
    assert "sales_gm" in authmod.SALES_ROLES
    assert "sales_gm" in authmod.DEAL_DESK_ROLES
    assert "sales_gm" in authmod.FINANCE_VIEW_ROLES
    assert "sales_gm" not in authmod.MONEY_ROLES
    assert "GM" in server.STAFF_ROLES
