"""MTD hero + YTD subtitle on every dealership dashboard."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "dashboard_period_kpis_tests")
os.environ.setdefault("JWT_SECRET", "dashboard-period-kpis-secret-32ch")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import period as periodmod  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _token(email, password="euler@123"):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return r.json()["token"]


def _ytd_only_day():
    """A date in this calendar year that is not this month, so YTD > MTD."""
    ym = periodmod.utc_month()
    year = ym[:4]
    other = "06" if ym[5:7] != "06" else "07"
    return f"{year}-{other}-10"


async def _seed_period_rows():
    ym = periodmod.utc_month()
    ytd_only = _ytd_only_day()
    mtd_day = f"{ym}-05"
    await server.db.leads.delete_many({})
    await server.db.payments.delete_many({})
    await server.db.leads.insert_many([
        {
            "leadId": "LD-MTD-1", "customerName": "Mtd Lead", "executive": "Executive",
            "currentStatus": "Booked", "accountStatus": "Active",
            "createdDate": mtd_day, "bookingDate": mtd_day,
            "deliveryDate": mtd_day, "deliveryStatus": "Delivered",
            "customerOutstanding": 0,
        },
        {
            "leadId": "LD-YTD-1", "customerName": "Ytd Only", "executive": "Executive",
            "currentStatus": "New", "accountStatus": "Active",
            "createdDate": ytd_only, "customerOutstanding": 0,
        },
        {
            "leadId": "LD-OLD-1", "customerName": "Last Year", "executive": "Sanjay",
            "currentStatus": "New", "accountStatus": "Active",
            "createdDate": "2025-03-01", "customerOutstanding": 0,
        },
    ])
    await server.db.payments.insert_many([
        {"paymentId": "P-MTD", "leadId": "LD-MTD-1", "amount": 4000, "date": mtd_day, "paymentMode": "Cash"},
        {"paymentId": "P-YTD", "leadId": "LD-YTD-1", "amount": 2500, "date": ytd_only, "paymentMode": "UPI"},
        {"paymentId": "P-OLD", "leadId": "LD-OLD-1", "amount": 9000, "date": "2025-03-02", "paymentMode": "Cash"},
    ])
    return mtd_day, ytd_only


@pytest.mark.asyncio
async def test_owner_dashboard_mtd_ytd_and_collected(client):
    await _seed_period_rows()
    d = (await client.get("/api/dashboard")).json()
    k = d["kpis"]
    period = d["period"]
    assert period["mtd"]["leads"] >= 1
    assert period["ytd"]["leads"] > period["mtd"]["leads"]
    assert k["monthlyLeads"] == period["mtd"]["leads"]
    assert k["leadsYtd"] == period["ytd"]["leads"]
    assert k["collectedMtd"] == period["mtd"]["collected"]
    assert k["collectedYtd"] == period["ytd"]["collected"]
    assert k["revenue"] == k["collectedMtd"]
    assert k["collectedYtd"] >= k["collectedMtd"] + 2500 - 0.01
    assert "Last Year" not in str(period)
    # Last-year receipt must not sit in YTD collected
    assert k["collectedYtd"] < 9000


@pytest.mark.asyncio
async def test_accounts_dashboard_collected_and_deliveries_period(client):
    await _seed_period_rows()
    tok = await _token("accounts@euler.com")
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        d = (await c.get("/api/accounts/dashboard")).json()
    k = d["kpis"]
    assert k["deliveriesMtd"] >= 1
    assert k["deliveriesYtd"] >= k["deliveriesMtd"]
    assert k["collectedMtd"] >= 4000
    assert k["collectedYtd"] >= k["collectedMtd"] + 2500 - 0.01
    assert d["period"]["mtd"]["collected"] == k["collectedMtd"]


@pytest.mark.asyncio
async def test_executive_dashboard_own_period_no_collected(client):
    await _seed_period_rows()
    tok = await _token("executive@euler.com")
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        d = (await c.get("/api/executive/dashboard")).json()
    k = d["kpis"]
    assert k["myLeadsMtd"] >= 1
    assert k["myLeadsYtd"] > k["myLeadsMtd"]
    assert "collected" not in d["period"]["mtd"]
    assert "collectedMtd" not in k


@pytest.mark.asyncio
async def test_field_and_gm_share_period_without_collected(client):
    await _seed_period_rows()
    for email, path in (
        ("asm@euler.com", "/api/field/dashboard"),
        ("salesgm@euler.com", "/api/sales-gm/dashboard"),
    ):
        tok = await _token(email)
        transport = httpx.ASGITransport(app=server.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
            c.headers.update({"Authorization": f"Bearer {tok}"})
            d = (await c.get(path)).json()
        k = d["kpis"]
        assert k["leadsYtd"] > k["leadsMtd"]
        assert k["cancellationsYtd"] >= k["cancellationsMtd"]
        assert "collected" not in d["period"]["mtd"]
        assert "collected" not in k
