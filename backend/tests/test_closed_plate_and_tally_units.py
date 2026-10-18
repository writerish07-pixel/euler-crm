"""Showroom Admin plate edits after Close Won; per-unit Tally invoices + ledger groups."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "closed_plate_tally_units")
os.environ.setdefault("JWT_SECRET", "closed-plate-tally-secret-32xxxx")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import auth as authmod  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

PW = "euler@123"
PNG = b"\x89PNG\r\n\x1a\n" + b"doc-bytes" * 16


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.deliveries.delete_many({})
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    await server.db.payments.delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _login(email, password=PW):
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


async def _user(client, email, role, password="desk#441", name=None):
    await server.db.users.delete_many({"email": email})
    r = await client.post("/api/auth/users", json={
        "email": email, "password": password, "name": name or role, "role": role})
    assert r.status_code == 200, r.text
    return password


def _closed_pack(lid="LD-PLATE-CLOSED"):
    return {
        "leadId": lid, "customerName": "Closed Plate", "mobile": "9813301999",
        "accountStatus": "Closed", "currentStatus": "Close Won",
        "deliveryStatus": "Delivered", "interestedModel": "Turbo Max",
        "sameOrderMultiUnit": True, "vehicleCount": 2,
        "chassisNumber": "MD9CLPL01AAAAAA1", "invoiceNumber": "INV-CL-1",
        "numberPlate": "RJ14OLD001",
        "units": [
            {"sno": 1, "model": "Turbo Max", "chassisNumber": "MD9CLPL01AAAAAA1",
             "invoiceNumber": "INV-CL-1", "numberPlate": "RJ14OLD001"},
            {"sno": 2, "model": "Turbo Max", "chassisNumber": "MD9CLPL02AAAAAA2",
             "invoiceNumber": "INV-CL-2", "numberPlate": "RJ14OLD002"},
        ],
    }


@pytest.mark.asyncio
async def test_showroom_admin_patches_plate_on_closed_pack(client):
    lid = "LD-PLATE-CLOSED"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one(_closed_pack(lid))
    await server.db.deliveries.insert_one({
        "leadId": lid, "numberPlate": "RJ14OLD001",
        "units": [{"sno": 1, "numberPlate": "RJ14OLD001"},
                  {"sno": 2, "numberPlate": "RJ14OLD002"}],
    })
    pw = await _user(client, "admin.plate@euler.com", "tl", name="Showroom Admin")
    async for admin in _login("admin.plate@euler.com", pw):
        denied = await client.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Done", "delivered": "Yes", "numberPlate": "RJ14NEW001"})
        assert denied.status_code == 409, denied.text
        r = await admin.patch(f"/api/leads/{lid}/number-plate", json={
            "units": [
                {"sno": 1, "numberPlate": "RJ14NEW001"},
                {"sno": 2, "numberPlate": "RJ14NEW002"},
            ]
        })
        assert r.status_code == 200, r.text
        lead = await server.db.leads.find_one({"leadId": lid})
        assert lead.get("numberPlate") == "RJ14NEW001"
        assert [u.get("numberPlate") for u in lead.get("units") or []] == ["RJ14NEW001", "RJ14NEW002"]
        assert lead.get("chassisNumber") == "MD9CLPL01AAAAAA1"
        deliv = await server.db.deliveries.find_one({"leadId": lid})
        assert deliv.get("numberPlate") == "RJ14NEW001"


@pytest.mark.asyncio
async def test_team_lead_and_exec_cannot_patch_closed_plate(client):
    lid = "LD-PLATE-ROLES"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one(_closed_pack(lid))
    await _user(client, "tl.plate@euler.com", "team_lead", name="Team Leader")
    await _user(client, "exec.plate@euler.com", "executive", name="Executive")
    async for tl in _login("tl.plate@euler.com", "desk#441"):
        r = await tl.patch(f"/api/leads/{lid}/number-plate", json={"numberPlate": "RJ14NOPE01"})
        assert r.status_code == 403, r.text
    async for ex in _login("exec.plate@euler.com", "desk#441"):
        r = await ex.patch(f"/api/leads/{lid}/number-plate", json={"numberPlate": "RJ14NOPE01"})
        assert r.status_code == 403, r.text


@pytest.mark.asyncio
async def test_cancelled_lead_rejects_plate_patch(client):
    lid = "LD-PLATE-CANCEL"
    rec = _closed_pack(lid)
    rec["dealCancelled"] = True
    rec["currentStatus"] = "Lost"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one(rec)
    r = await client.patch(f"/api/leads/{lid}/number-plate", json={"numberPlate": "RJ14CANC01"})
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_duplicate_plate_on_closed_patch_is_409(client):
    await server.db.leads.delete_many({"leadId": {"$in": ["LD-PLATE-A", "LD-PLATE-B"]}})
    a = _closed_pack("LD-PLATE-A")
    b = _closed_pack("LD-PLATE-B")
    b["mobile"] = "9813302000"
    b["chassisNumber"] = "MD9CLPL03AAAAAA3"
    b["invoiceNumber"] = "INV-CL-B1"
    b["numberPlate"] = "RJ14KEEP01"
    b["units"] = [
        {"sno": 1, "chassisNumber": "MD9CLPL03AAAAAA3", "invoiceNumber": "INV-CL-B1",
         "numberPlate": "RJ14KEEP01"},
        {"sno": 2, "chassisNumber": "MD9CLPL04AAAAAA4", "invoiceNumber": "INV-CL-B2",
         "numberPlate": "RJ14KEEP02"},
    ]
    await server.db.leads.insert_one(a)
    await server.db.leads.insert_one(b)
    r = await client.patch("/api/leads/LD-PLATE-B/number-plate", json={
        "units": [
            {"sno": 1, "numberPlate": "RJ14OLD001"},
            {"sno": 2, "numberPlate": "RJ14KEEP02"},
        ]
    })
    assert r.status_code == 409, r.text


@pytest.mark.asyncio
async def test_pack_tally_invoice_requires_unit_and_stores_per_unit(client):
    lid = "LD-TALLY-PACK"
    await server.db.leads.delete_many({"leadId": lid})
    await server.db.leads.insert_one({
        "leadId": lid, "customerName": "Pack Tally", "mobile": "9813302111",
        "accountStatus": "Active", "currentStatus": "Delivered",
        "deliveryStatus": "Delivered", "sameOrderMultiUnit": True, "vehicleCount": 2,
        "units": [
            {"sno": 1, "model": "Turbo Max", "chassisNumber": "MD9TALLY01AAAAA1",
             "exShowroom": 800000, "customerPayable": 800000},
            {"sno": 2, "model": "Turbo Max", "chassisNumber": "MD9TALLY02AAAAA2",
             "exShowroom": 800000, "customerPayable": 800000},
        ],
    })
    miss = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("one.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "tally_invoice"})
    assert miss.status_code == 422, miss.text
    u1 = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("u1.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "tally_invoice", "unitSno": "1"})
    assert u1.status_code == 200, u1.text
    assert u1.json().get("unitSno") == 1
    u2 = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("u2.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "tally_invoice", "unitSno": "2"})
    assert u2.status_code == 200, u2.text
    club = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("led.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "tally_ledger", "unitSnos": "1,2"})
    assert club.status_code == 200, club.text
    assert club.json().get("unitSnos") == [1, 2]
    sep = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("led1.png", io.BytesIO(PNG), "image/png")},
        data={"kind": "tally_ledger", "unitSno": "1"})
    assert sep.status_code == 200, sep.text
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    ledgers = [d for d in docs if d["kind"] == "tally_ledger"]
    assert len(ledgers) == 1
    assert ledgers[0].get("unitSno") == 1
    invoices = [d for d in docs if d["kind"] == "tally_invoice"]
    assert sorted(d.get("unitSno") for d in invoices) == [1, 2]


def test_pack_billing_disclaimer_says_one_invoice_per_unit():
    lead = {
        "leadId": "LD-PACK-BILL-TALLY",
        "customerName": "Messenger",
        "sameOrderMultiUnit": True,
        "customerPayable": 1000,
    }
    overlays = [
        {"sno": 1, "interestedModel": "Turbo Max", "exShowroom": 800000,
         "rto": 0, "insuranceAmount": 0, "additionalDiscount": 0,
         "chassisNumber": "CH1", "invoiceNumber": "INV1", "customerPayable": 800000},
        {"sno": 2, "interestedModel": "Turbo Max", "exShowroom": 800000,
         "rto": 0, "insuranceAmount": 0, "additionalDiscount": 0,
         "chassisNumber": "CH2", "invoiceNumber": "INV2", "customerPayable": 800000},
    ]
    s = ce.build_delivery_billing_summary(lead, pack_units=overlays)
    assert s.get("pack") is True
    assert "one tally gst invoice per unit" in (s.get("disclaimer") or "").lower()
    assert s["units"][0].get("tallyInvoiceLines")
    assert s["units"][1].get("tallyInvoiceLines")
