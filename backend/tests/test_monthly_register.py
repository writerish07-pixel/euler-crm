"""Monthly register, OEM volume extras, export gate, OEM finance seed login."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "monthlyregister")
os.environ.setdefault("JWT_SECRET", "monthly-register-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import period as periodmod  # noqa: E402
import server  # noqa: E402

TURBO = ("Turbo Max", "Maxx (PV)")
OEM_EMAIL = "monthly.oem@euler.com"
OEM_PW = "oemDesk#2026"


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
    await server.db.users.delete_many({"email": OEM_EMAIL})
    r = await client.post("/api/auth/users", json={
        "email": OEM_EMAIL, "password": OEM_PW, "name": "Monthly OEM Desk",
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


_seq = {"n": 0}


def next_mobile():
    _seq["n"] += 1
    return str(9544300000 + _seq["n"])


async def make_lead(c, name, *, created="2026-03-10", executive="Amit"):
    r = await c.post("/api/leads", json={
        "customerName": name, "mobile": next_mobile(),
        "interestedModel": TURBO[0], "variant": TURBO[1], "executive": executive,
        "createdDate": created})
    assert r.status_code == 200, r.text
    return r.json()["leadId"]


@pytest.mark.asyncio
async def test_seeded_oem_finance_login_exists(client):
    row = await server.db.users.find_one({"email": "oemfinance@euler.com"})
    assert row is not None
    assert row["role"] == "oem_finance"
    tok = await _token("oemfinance@euler.com", "euler@123")
    assert tok


@pytest.mark.asyncio
async def test_oem_finance_user_does_not_need_staff_name(client):
    await server.db.users.delete_many({"email": "outside.oem@euler.com"})
    r = await client.post("/api/auth/users", json={
        "email": "outside.oem@euler.com", "password": "oemOut#2026",
        "role": "oem_finance", "loginId": "oemdesk"})
    assert r.status_code == 200, r.text
    assert r.json()["name"] == "oemdesk"
    assert r.json()["role"] == "oem_finance"


@pytest.mark.asyncio
async def test_monthly_register_counts_leads_bookings_by_month(client):
    ym = periodmod.utc_month()
    other = "2025-01-15"
    await make_lead(client, "Monthly Now", created=f"{ym}-05")
    await make_lead(client, "Monthly Old", created=other)

    all_rows = (await client.get("/api/leads")).json()
    now_rows = (await client.get("/api/leads", params={"month": ym})).json()
    year_rows = (await client.get("/api/leads", params={"year": "2025"})).json()
    assert any(r["customerName"] == "Monthly Now" for r in now_rows)
    assert not any(r["customerName"] == "Monthly Old" for r in now_rows)
    assert any(r["customerName"] == "Monthly Old" for r in year_rows)
    assert any(r["customerName"] == "Monthly Now" for r in all_rows)

    d = (await client.get("/api/reports/monthly", params={"month": ym})).json()
    assert d["period"]["kind"] == "month"
    assert d["selected"]["leads"]["count"] >= 1
    assert d["mtd"]["leads"]["count"] >= 1
    assert d["ytd"]["leads"]["count"] >= 1
    assert d["focusYear"] == ym[:4]
    assert len(d["byMonth"]) == 12
    assert d["byMonth"][0]["month"] == f"{ym[:4]}-01"


@pytest.mark.asyncio
async def test_executive_cannot_export_or_open_monthly(exec_client):
    assert (await exec_client.get("/api/export")).status_code == 403
    assert (await exec_client.get("/api/reports/monthly")).status_code == 403


@pytest.mark.asyncio
async def test_accounts_can_open_monthly_not_export(client):
    tok = await _token("accounts@euler.com", "euler@123")
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        c.headers.update({"Authorization": f"Bearer {tok}"})
        assert (await c.get("/api/reports/monthly")).status_code == 200
        assert (await c.get("/api/export")).status_code == 403


@pytest.mark.asyncio
async def test_oem_monthly_is_allowlisted_and_has_no_contacts(client, oem):
    r = await oem.get("/api/reports/oem-monthly")
    assert r.status_code == 200, r.text
    d = r.json()
    body = r.text.lower()
    assert "mobile" not in body
    assert "village" not in body
    assert "customeroutstanding" not in body
    assert "dealermargin" not in body
    assert "extraincome" not in body
    assert "earnings" not in d["selected"]
    assert "scheme" not in d["selected"]
    assert "payments" not in d["selected"]
    assert "leads" in d["selected"]
    assert "bookings" in d["selected"]
    assert "deliveries" in d["selected"]
    assert "finance" in d["selected"]
    assert (await oem.get("/api/reports/monthly")).status_code == 403
    assert (await oem.get("/api/leads")).status_code == 403


@pytest.mark.asyncio
async def test_oem_finance_month_filter_does_not_leak(client, oem):
    r = await oem.get("/api/reports/oem-finance", params={"month": periodmod.utc_month()})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["period"]["kind"] == "month"
    for row in d["files"]:
        assert "mobile" not in row
