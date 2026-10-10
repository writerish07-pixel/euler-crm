"""Printable customer deal sheet PDF — sign, then upload."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "deal_sheet_pdf_v1")
os.environ.setdefault("JWT_SECRET", "deal-sheet-pdf-secret-32ch!!")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ.setdefault("ENVIRONMENT", "test")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import deal_sheet_pdf as dsp  # noqa: E402
import httpx  # noqa: E402
import server  # noqa: E402


def test_pdf_lists_payable_and_hides_owner_pnl():
    payload, pdf = dsp.assemble_deal_sheet(
        customer={"customerName": "Ramesh Kumar", "mobile": "9876543210",
                  "city": "Jaipur", "customerType": "Individual",
                  "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
                  "budget": 790000, "executive": "Amit"},
        deal={
            "model": "Turbo Max", "variant": "Maxx (FB)",
            "exShowroom": 800000, "rto": 5500, "insurance": 19000,
            "priceTotal": 824500, "transport": 0, "tcs": 0,
            "netToCx": 824500, "cxDemand": 790000,
            "additionalDiscount": 34500, "schemePassed": 0,
            "extraMargin": 0, "supportRequired": 34500,
        },
        ref="LD26009999", date="2026-10-09", executive="Amit",
    )
    assert pdf.startswith(b"%PDF-1.4")
    assert b"%%EOF" in pdf
    text = pdf.decode("latin-1")
    assert "Ramesh Kumar" in text
    assert "Turbo Max" in text
    assert "Amount payable" in text
    assert "Customer signature" in text
    assert "Extra margin" not in text
    assert "Support required" not in text
    assert payload["cxDemand"] == 790000
    assert dsp.filename_for(payload).startswith("deal-sheet-Ramesh-Kumar")


def test_pack_lists_each_unit():
    _, pdf = dsp.assemble_deal_sheet(
        customer={"customerName": "Kapoor Freight", "budget": 1580000},
        deal={
            "pack": True, "unitCount": 2,
            "model": "Turbo Max", "variant": "Maxx (FB)",
            "exShowroom": 1600000, "rto": 11000, "insurance": 38000,
            "priceTotal": 1649000, "cxDemand": 1580000, "netToCx": 1649000,
            "units": [
                {"model": "Turbo Max", "variant": "Maxx (FB)"},
                {"model": "Turbo Max", "variant": "Maxx (FB)"},
            ],
        },
        date="2026-10-09",
    )
    text = pdf.decode("latin-1")
    assert "Unit 1" in text and "Unit 2" in text


def test_passed_scheme_shows_as_customer_discount():
    _, pdf = dsp.assemble_deal_sheet(
        customer={"customerName": "Sita", "interestedModel": "Storm", "budget": 1350000},
        deal={
            "model": "Storm", "variant": "Storm LR",
            "exShowroom": 1410000, "rto": 5500, "insurance": 19000,
            "priceTotal": 1434500, "cxDemand": 1350000, "netToCx": 1434500,
            "schemePassed": 25000,
            "schemePassOn": {"consumerDiscount": True},
            "schemeOffers": [{"key": "consumerDiscount", "label": "Consumer Scheme",
                              "schemeAvailable": 25000}],
        },
    )
    text = pdf.decode("latin-1")
    assert "Consumer Scheme" in text
    assert "OEM scheme passed" in text


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


@pytest.mark.asyncio
async def test_preview_pdf_requires_name_vehicle_and_demand(client):
    missing = await client.post("/api/commercial/deal-sheet.pdf", json={
        "customerName": "", "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "budget": 790000,
    })
    assert missing.status_code == 422
    no_cx = await client.post("/api/commercial/deal-sheet.pdf", json={
        "customerName": "Ramesh", "interestedModel": "Turbo Max", "variant": "Maxx (FB)",
        "budget": 0,
    })
    assert no_cx.status_code == 422


@pytest.mark.asyncio
async def test_preview_and_lead_pdf_download(client):
    await server.db.price_master.delete_many({"priceId": "PM-SHEET-A"})
    await server.db.price_master.insert_one({
        "priceId": "PM-SHEET-A", "model": "Turbo Max", "variant": "Sheet A",
        "exShowroom": 800000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    prev = await client.post("/api/commercial/deal-sheet.pdf", json={
        "customerName": "Sheet Cust", "mobile": "9813311222",
        "interestedModel": "Turbo Max", "variant": "Sheet A",
        "budget": 790000, "executive": "Amit", "createdDate": "2026-10-09",
    })
    assert prev.status_code == 200, prev.text
    assert prev.headers["content-type"].startswith("application/pdf")
    assert prev.content.startswith(b"%PDF")
    assert b"Sheet Cust" in prev.content

    created = await client.post("/api/leads", json={
        "customerName": "Sheet Cust", "mobile": "9813311222",
        "interestedModel": "Turbo Max", "variant": "Sheet A",
        "executive": "Amit", "budget": 790000, "createdDate": "2026-10-09",
    })
    assert created.status_code == 200, created.text
    lid = created.json()["leadId"]
    got = await client.get(f"/api/leads/{lid}/deal-sheet.pdf")
    assert got.status_code == 200, got.text
    assert got.content.startswith(b"%PDF")
    assert lid.encode() in got.content or b"Sheet Cust" in got.content
