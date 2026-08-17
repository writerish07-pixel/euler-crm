"""Owner can change Price Master rates for any model (dashboard editor uses the same API)."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "owner_dashboard_price_edit")
os.environ.setdefault("JWT_SECRET", "owner-price-edit-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


async def _login(client, email, password="euler@123"):
    r = await client.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    client.headers["Authorization"] = f"Bearer {r.json()['token']}"


@pytest_asyncio.fixture
async def client(monkeypatch):
    isolated = server.client["owner_dashboard_price_edit_isolated"]
    await isolated.price_master.delete_many({})
    await isolated.price_master.insert_many([
        {"priceId": "PM-STORM", "model": "Storm EV", "variant": "Storm (PV)",
         "bodyType": "PV", "exShowroom": 640000, "rto": 8000, "insurance": 12000,
         "accessories": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
         "extendedWarranty": 0, "otherCharges": 0, "gstPercent": 5,
         "tcsApplicable": "No", "priceVersion": "v1", "status": "active", "remarks": ""},
        {"priceId": "PM-TURBO", "model": "Turbo Max", "variant": "Maxx (PV)",
         "bodyType": "PV", "exShowroom": 770000, "rto": 9000, "insurance": 15000,
         "accessories": 0, "handlingCharges": 0, "trc": 0, "fastag": 0,
         "extendedWarranty": 0, "otherCharges": 0, "gstPercent": 5,
         "tcsApplicable": "No", "priceVersion": "v1", "status": "active", "remarks": ""},
    ])
    monkeypatch.setattr(server, "db", isolated)
    await server.authmod.seed_users(server.client[os.environ["DB_NAME"]])
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        await _login(c, "owner@euler.com")
        yield c


def _payload(row, **over):
    body = {
        "model": row["model"], "variant": row["variant"], "bodyType": row.get("bodyType") or "",
        "exShowroom": row.get("exShowroom") or 0, "rto": row.get("rto") or 0,
        "insurance": row.get("insurance") or 0, "accessories": row.get("accessories") or 0,
        "handlingCharges": row.get("handlingCharges") or 0, "trc": row.get("trc") or 0,
        "fastag": row.get("fastag") or 0, "extendedWarranty": row.get("extendedWarranty") or 0,
        "otherCharges": row.get("otherCharges") or 0, "gstPercent": row.get("gstPercent") or 0,
        "tcsApplicable": row.get("tcsApplicable") or "No",
        "priceVersion": row.get("priceVersion") or "", "status": row.get("status") or "active",
        "remarks": row.get("remarks") or "",
    }
    body.update(over)
    return body


@pytest.mark.asyncio
async def test_owner_can_change_price_of_any_model(client):
    listing = (await client.get("/api/price-master")).json()
    assert {r["model"] for r in listing} >= {"Storm EV", "Turbo Max"}

    storm = next(r for r in listing if r["priceId"] == "PM-STORM")
    turbo = next(r for r in listing if r["priceId"] == "PM-TURBO")

    r1 = await client.put("/api/price-master/PM-STORM", json=_payload(storm, exShowroom=655000, rto=8500))
    assert r1.status_code == 200, r1.text
    assert r1.json()["exShowroom"] == 655000
    assert r1.json()["rto"] == 8500

    r2 = await client.put("/api/price-master/PM-TURBO", json=_payload(turbo, exShowroom=790000, insurance=16000))
    assert r2.status_code == 200, r2.text
    assert r2.json()["exShowroom"] == 790000
    assert r2.json()["insurance"] == 16000

    # The other model's price is unchanged.
    again = {r["priceId"]: r for r in (await client.get("/api/price-master")).json()}
    assert again["PM-STORM"]["exShowroom"] == 655000
    assert again["PM-TURBO"]["exShowroom"] == 790000
    assert again["PM-TURBO"]["rto"] == 9000


@pytest.mark.asyncio
async def test_executive_cannot_change_model_price(client):
    await _login(client, "executive@euler.com")
    r = await client.put("/api/price-master/PM-STORM", json={
        "model": "Storm EV", "variant": "Storm (PV)", "exShowroom": 1,
    })
    assert r.status_code == 403
