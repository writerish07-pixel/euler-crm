"""MTD hero + YTD subtitle on every dealership dashboard."""
import os
import sys
import time

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


@pytest.mark.asyncio
async def test_owner_dashboard_stays_fast_with_many_leads(client):
    """`l in booked` compared whole lead dicts and timed the live desk out."""
    fat = {
        "schemeAllocationSummary": {"components": [{"k": i, "v": i} for i in range(12)]},
        "units": [{"sno": 1, "model": "Storm", **{f"f{j}": j for j in range(15)}}],
    }
    leads, payments, finance = [], [], []
    for i in range(280):
        lid = f"LD-LOAD-{i:04d}"
        booked = i % 2 == 0
        leads.append({
            "leadId": lid, "customerName": f"Cust {i}", "executive": "Amit",
            "currentStatus": "Booked" if booked else "New",
            "accountStatus": "Active",
            "createdDate": "2026-10-01",
            "bookingDate": "2026-10-02" if booked else "",
            "interestedModel": "Storm",
            "customerOutstanding": 50,
            "companyOutstanding": 0,
            **fat,
        })
        payments.append({
            "paymentId": f"PAY{i}", "leadId": lid, "amount": 10,
            "date": "2026-10-03", "paymentMode": "Cash",
        })
        if i < 90:
            finance.append({
                "financeFileNumber": f"FF{i}", "leadId": lid,
                "fileOutstanding": 1000, "status": "Pending",
            })
    await server.db.leads.delete_many({})
    await server.db.payments.delete_many({})
    await server.db.finance.delete_many({})
    await server.db.leads.insert_many(leads)
    await server.db.payments.insert_many(payments)
    await server.db.finance.insert_many(finance)
    t0 = time.monotonic()
    r = await client.get("/api/dashboard")
    elapsed = time.monotonic() - t0
    assert r.status_code == 200, r.text
    assert elapsed < 6, f"owner dashboard hung ({elapsed:.2f}s)"
    d = r.json()
    assert d["kpis"]["totalLeads"] == 280
    storm = next(m for m in d["modelPerformance"] if m["model"] == "Storm")
    assert storm["revenue"] == 2800
    assert storm["bookings"] == 140


@pytest.mark.asyncio
async def test_monthly_and_gm_dashboards_stay_fast_with_many_leads(client):
    fat = {
        "units": [{"sno": 1, "model": "Storm", **{f"f{j}": j for j in range(12)}}],
        "schemeAllocationSummary": {"components": [{"k": i, "v": i} for i in range(20)]},
        "kycDocuments": [{"name": f"doc{i}", "b64": "x" * 80} for i in range(8)],
    }
    await server.db.leads.delete_many({})
    await server.db.leads.insert_many([
        {
            "leadId": f"LD-M{i:04d}", "customerName": f"Cust {i}", "executive": "Amit",
            "currentStatus": "Booked" if i % 2 == 0 else "New",
            "accountStatus": "Active", "createdDate": "2026-10-01",
            "bookingDate": "2026-10-02" if i % 2 == 0 else "",
            "interestedModel": "Storm", "cancelHistory": [
                {"date": "2026-09-01", "reason": "Price", "executive": "Amit"},
            ],
            "dealerTotalEarnings": 1200 if i % 2 == 0 else 0,
            **fat,
        }
        for i in range(220)
    ])
    t0 = time.monotonic()
    monthly = await client.get("/api/reports/monthly", params={"month": "2026-10"})
    monthly_s = time.monotonic() - t0
    assert monthly.status_code == 200, monthly.text
    assert monthly_s < 6, f"monthly register hung ({monthly_s:.2f}s)"
    t_sb = time.monotonic()
    scoreboard = await client.get("/api/reports/scoreboard", params={"month": "2026-10"})
    sb_s = time.monotonic() - t_sb
    assert scoreboard.status_code == 200, scoreboard.text
    assert sb_s < 2, f"scoreboard hung ({sb_s:.2f}s)"
    assert "selected" not in scoreboard.json()
    tok = await _token("salesgm@euler.com")
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        t1 = time.monotonic()
        gm = await c.get("/api/sales-gm/dashboard")
        gm_s = time.monotonic() - t1
    assert gm.status_code == 200, gm.text
    assert gm_s < 6, f"sales GM dashboard hung ({gm_s:.2f}s)"


def test_lead_earnings_total_uses_stored_not_recompute():
    assert server._lead_earnings_total({"dealerTotalEarnings": 2500}) == 2500
    assert server._lead_earnings_total({
        "dealerMarginNetExGst": 1000,
        "dealerSchemeRetained": 200,
        "oemExtraSupportReceived": 50,
        "dealerInsuranceIncome": 10,
        "extraDealerIncomeTotal": 5,
        "dealerFundedBenefit": 15,
    }) == 1250
