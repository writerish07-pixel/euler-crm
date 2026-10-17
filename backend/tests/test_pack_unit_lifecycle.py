"""Each pack unit is a full single-unit file. KYC is shared. Payments can club."""
import io
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "pack_unit_lifecycle_test")
os.environ.setdefault("JWT_SECRET", "pack-unit-lifecycle-secret-32ch")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")
os.environ["ENVIRONMENT"] = "test"

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import commercial as ce  # noqa: E402
import httpx  # noqa: E402
import oem_sync  # noqa: E402
import server  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"doc-bytes" * 16
PW = "euler@123"


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _png(name="scan.png"):
    return (name, io.BytesIO(PNG), "image/png")


async def upload(c, url, kind, unit_sno=None, name="scan.png"):
    data = {"kind": kind}
    if unit_sno:
        data["unitSno"] = str(unit_sno)
    return await c.post(url, files={"file": _png(name)}, data=data)


async def _seed_pack(client, mobile="9813399001"):
    await server.db.leads.delete_many({"mobile": mobile})
    await server.db.payments.delete_many({})
    await server.db.price_master.delete_many({"priceId": {"$in": ["PM-LIFE-A", "PM-LIFE-B"]}})
    await server.db.price_master.insert_one({
        "priceId": "PM-LIFE-A", "model": "Turbo Max", "variant": "Life A",
        "exShowroom": 400000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    await server.db.price_master.insert_one({
        "priceId": "PM-LIFE-B", "model": "Storm", "variant": "Life B",
        "exShowroom": 500000, "rto": 0, "insurance": 0, "handlingCharges": 0,
        "status": "active",
    })
    r = await client.post("/api/leads", json={
        "customerName": f"Fleet Life {mobile[-4:]}",
        "mobile": mobile,
        "interestedModel": "Turbo Max",
        "variant": "Life A",
        "executive": "Amit",
        "leadSource": "Walk-in",
        "sameOrderMultiUnit": True,
        "units": [
            {"model": "Turbo Max", "variant": "Life A"},
            {"model": "Storm", "variant": "Life B"},
        ],
    })
    assert r.status_code == 200, r.text
    lid = r.json()["leadId"]
    for sno in (1, 2):
        p = await client.put(f"/api/leads/{lid}/price-structure", json={
            "exShowroom": 400000 if sno == 1 else 500000, "unitSno": sno,
        })
        assert p.status_code == 200, p.text
        s = await client.put(f"/api/leads/{lid}/scheme", json={
            "benefitMode": "Partial Benefit",
            "benefitPassedBreakup": "{}",
            "schemeComponentsUsed": "{}",
            "unitSno": sno,
        })
        assert s.status_code == 200, s.text
    booked = await client.post(f"/api/leads/{lid}/convert-booking", json={
        "bookingDate": "2026-10-01", "bookingAmount": 0,
        "paymentMode": "Cash", "financeRequired": "No", "exchangeRequired": "No",
    })
    assert booked.status_code == 200, booked.text
    lead = await server.db.leads.find_one({"leadId": lid})
    return lid, lead


def test_unit_scoped_docs_do_not_overwrite_siblings():
    assert "delivery_insurance" in server.lead_docs.UNIT_SCOPED_KINDS
    q1 = server.lead_docs.unique_doc_filter(
        "delivery_insurance", lead_id="LD1", unit_sno=1)
    q2 = server.lead_docs.unique_doc_filter(
        "delivery_insurance", lead_id="LD1", unit_sno=2)
    assert q1["unitSno"] == 1
    assert q2["unitSno"] == 2
    kyc = server.lead_docs.unique_doc_filter("kyc_pan", lead_id="LD1", unit_sno=2)
    assert "unitSno" not in kyc
    assert server.lead_docs.doc_matches_unit({"kind": "delivery_rto"}, 1) is True
    assert server.lead_docs.doc_matches_unit({"kind": "delivery_rto", "unitSno": 2}, 1) is False
    assert server.lead_docs.doc_matches_unit({"kind": "delivery_rto", "unitSno": 2}, 2) is True


def test_partial_pack_is_not_whole_file_delivered():
    lead = {
        "sameOrderMultiUnit": True,
        "currentStatus": "Booked",
        "deliveryStatus": "",
        "units": [
            {"sno": 1, "deliveryStatus": "Delivered", "delivered": "Yes"},
            {"sno": 2, "model": "Storm"},
        ],
    }
    assert server._is_delivered(lead) is False
    assert server._unit_is_delivered(lead, lead["units"][0], 0) is True
    assert server._unit_is_delivered(lead, lead["units"][1], 1) is False
    inherited = {
        "sameOrderMultiUnit": True,
        "currentStatus": "Delivered",
        "deliveryStatus": "Delivered",
        "units": [
            {"sno": 1, "chassisNumber": "MD9A"},
            {"sno": 2, "chassisNumber": "MD9B", "model": "Storm"},
        ],
    }
    assert server._unit_is_delivered(inherited, inherited["units"][0], 0) is True
    assert server._unit_is_delivered(inherited, inherited["units"][1], 1) is False
    assert server._is_delivered(inherited) is False


def test_desk_lock_blocks_append_when_all_chassis_filled():
    lead = {
        "accountStatus": "Active",
        "currentStatus": "Delivered",
        "deliveryStatus": "Delivered",
        "insuranceStatus": "Yes",
        "registrationStatus": "Yes",
        "chassisNumber": "MD9A",
        "units": [
            {"sno": 1, "chassisNumber": "MD9A", "insurance": "Yes", "registration": "Yes",
             "deliveryStatus": "Delivered"},
            {"sno": 2, "chassisNumber": "MD9B", "insurance": "Yes", "registration": "Yes",
             "deliveryStatus": "Delivered"},
        ],
        "sameOrderMultiUnit": True,
    }
    assert server._can_append_sold_unit(lead) is False
    lead["units"][1]["chassisNumber"] = ""
    assert server._can_append_sold_unit(lead) is True


def test_club_fills_outstanding_in_unit_order():
    lead = {
        "sameOrderMultiUnit": True,
        "units": [
            {"sno": 1, "customerPayable": 100000},
            {"sno": 2, "customerPayable": 100000},
            {"sno": 3, "customerPayable": 100000},
        ],
    }
    splits, mode = server._allocate_payment_splits(
        lead, 150000, [1, 2], "club", None,
        {1: 100000, 2: 100000, 3: 100000},
        {1: 0, 2: 0, 3: 0})
    assert mode == "club"
    by = {s["unitSno"]: s["amount"] for s in splits}
    assert by[1] == 100000
    assert by[2] == 50000
    sep, mode = server._allocate_payment_splits(
        lead, 40000, [3], "separate", None,
        {1: 100000, 2: 100000, 3: 100000},
        {1: 0, 2: 0, 3: 0})
    assert mode == "separate"
    assert sep == [{"unitSno": 3, "amount": 40000}]


@pytest.mark.asyncio
async def test_pack_insurance_rto_are_per_unit(client):
    lid, _lead = await _seed_pack(client, "9813399111")
    u1 = await upload(client, f"/api/leads/{lid}/documents", "delivery_insurance", 1, "ins1.png")
    u2 = await upload(client, f"/api/leads/{lid}/documents", "delivery_insurance", 2, "ins2.png")
    rto1 = await upload(client, f"/api/leads/{lid}/documents", "delivery_rto", 1, "rto1.png")
    rto2 = await upload(client, f"/api/leads/{lid}/documents", "delivery_rto", 2, "rto2.png")
    assert u1.status_code == 200 and u2.status_code == 200, u2.text
    assert rto1.status_code == 200 and rto2.status_code == 200
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    ins = [d for d in docs if d["kind"] == "delivery_insurance"]
    assert {d.get("unitSno") for d in ins} == {1, 2}
    assert {d["filename"] for d in ins} == {"ins1.png", "ins2.png"}
    again = await upload(client, f"/api/leads/{lid}/documents", "delivery_insurance", 2, "ins2b.png")
    assert again.status_code == 200
    docs = (await client.get(f"/api/leads/{lid}/documents")).json()
    ins = [d for d in docs if d["kind"] == "delivery_insurance"]
    by = {d.get("unitSno"): d["filename"] for d in ins}
    assert by[1] == "ins1.png"
    assert by[2] == "ins2b.png"


@pytest.mark.asyncio
async def test_club_and_separate_payments_hit_selected_units(client):
    lid, lead = await _seed_pack(client, "9813399222")
    pay1 = ce.num((lead.get("units") or [{}])[0].get("customerPayable"))
    pay2 = ce.num((lead.get("units") or [{}])[1].get("customerPayable"))
    assert pay1 > 0 and pay2 > 0
    club = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": pay1 + 10000, "paymentMode": "NEFT",
        "paymentReference": "UTRCLUB1", "date": "2026-10-02",
        "unitSnos": [1, 2], "allocation": "club",
    })
    assert club.status_code == 200, club.text
    body = club.json()
    assert body.get("allocation") == "club"
    assert body.get("unitSnos") == [1, 2]
    splits = {s["unitSno"]: s["amount"] for s in body.get("unitSplits") or []}
    assert splits[1] == pay1
    assert splits[2] == 10000
    live = await server.db.leads.find_one({"leadId": lid})
    u1 = (live.get("units") or [{}])[0]
    u2 = (live.get("units") or [{}])[1]
    assert ce.num(u1.get("customerOutstanding")) <= 0.01
    assert ce.num(u2.get("totalReceived")) == 10000
    rest = ce.round2(ce.num(u2.get("customerOutstanding")))
    sep = await client.post(f"/api/leads/{lid}/payments", json={
        "amount": rest, "paymentMode": "UPI",
        "paymentReference": "UTRSEP2", "date": "2026-10-03",
        "unitSnos": [2], "allocation": "separate",
    })
    assert sep.status_code == 200, sep.text
    after = await server.db.leads.find_one({"leadId": lid})
    assert ce.num(after.get("customerOutstanding")) <= 0.01
    assert ce.num((after.get("units") or [{}])[1].get("customerOutstanding")) <= 0.01


@pytest.mark.asyncio
async def test_deliver_unit_one_leaves_unit_two_editable(client):
    lid, lead = await _seed_pack(client, "9813399333")
    pay = ce.num(lead.get("customerPayable"))
    await client.post(f"/api/leads/{lid}/payments", json={
        "amount": pay, "paymentMode": "Cash", "date": "2026-10-02",
        "unitSnos": [1, 2], "allocation": "club",
    })
    agent = await server.db.insurance_agents.find_one({"status": "Active"}) or {}
    if not agent:
        await server.db.insurance_agents.insert_one({
            "agentId": "IA-LIFE", "agentName": "Life Agent", "status": "Active",
        })
        agent = {"agentId": "IA-LIFE"}
    d1 = await client.put(f"/api/leads/{lid}/delivery", json={
        "insurance": "Yes", "registration": "Yes", "invoice": "Yes", "pdi": "Yes",
        "insurerName": "UIIC", "insuranceAgentId": agent["agentId"],
        "delivered": "Yes", "deliveryDate": "2026-10-04", "unitSno": 1,
        "units": [
            {"sno": 1, "model": "Turbo Max", "variant": "Life A",
             "chassisNumber": "MD9LIFE0001", "deliveryDate": "2026-10-04"},
            {"sno": 2, "model": "Storm", "variant": "Life B",
             "chassisNumber": "MD9LIFE0002"},
        ],
    })
    assert d1.status_code == 200, d1.text
    live = await server.db.leads.find_one({"leadId": lid})
    assert (live.get("currentStatus") or "").lower() != "delivered"
    assert server._is_delivered(live) is False
    units = live.get("units") or []
    assert server._unit_is_delivered(live, units[0], 0) is True
    assert server._unit_is_delivered(live, units[1], 1) is False
    email = "life.tl@euler.com"
    await server.db.users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "desk#441", "name": "Life TL", "role": "tl"})
    assert created.status_code == 200, created.text
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as tl:
        login = await tl.post("/api/auth/login", json={"email": email, "password": "desk#441"})
        assert login.status_code == 200, login.text
        tl.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
        blocked = await tl.put(f"/api/leads/{lid}/scheme", json={
            "benefitMode": "Partial Benefit",
            "benefitPassedBreakup": "{}",
            "schemeComponentsUsed": "{}",
            "unitSno": 1,
        })
        assert blocked.status_code in (403, 409), blocked.text
        open_u2 = await tl.put(f"/api/leads/{lid}/delivery", json={
            "insurance": "Yes", "registration": "Yes", "invoice": "", "pdi": "",
            "insurerName": "UIIC", "unitSno": 2, "delivered": "",
            "units": [
                {"sno": 1, "model": "Turbo Max", "variant": "Life A",
                 "chassisNumber": "MD9LIFE0001", "deliveryDate": "2026-10-04"},
                {"sno": 2, "model": "Storm", "variant": "Life B",
                 "chassisNumber": "MD9LIFE0002"},
            ],
        })
        assert open_u2.status_code == 200, open_u2.text


@pytest.mark.asyncio
async def test_oem_create_on_delivered_file_mints_new_lead_with_kyc(client):
    mobile = "9813399444"
    lid, _lead = await _seed_pack(client, mobile)
    live = await server.db.leads.find_one({"leadId": lid})
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "currentStatus": "Delivered", "deliveryStatus": "Delivered",
        "insuranceStatus": "Yes", "registrationStatus": "Yes",
        "chassisNumber": "MD9OLD0001",
        "units": [
            {**(live.get("units") or [{}])[0], "chassisNumber": "MD9OLD0001",
             "insurance": "Yes", "registration": "Yes", "deliveryStatus": "Delivered"},
            {**(live.get("units") or [{}, {}])[1], "chassisNumber": "MD9OLD0002",
             "insurance": "Yes", "registration": "Yes", "deliveryStatus": "Delivered"},
        ],
    }})
    kyc = await upload(client, f"/api/leads/{lid}/documents", "kyc_pan", name="pan.png")
    assert kyc.status_code == 200, kyc.text
    await upload(client, f"/api/leads/{lid}/documents", "kyc_aadhaar_front")
    await upload(client, f"/api/leads/{lid}/documents", "kyc_aadhaar_back")
    fresh = await server.db.leads.find_one({"leadId": lid})
    assert server._can_append_sold_unit(fresh) is False
    await server.db.oem_sold.delete_many({})
    name = str(fresh.get("customerName") or f"Fleet Life {mobile[-4:]}")
    await server.db.oem_sold.insert_one({
        "chassis": "MD9NEW0999", "mobile": mobile, "invoiceNumber": "CINV-NEW",
        "customerName": name, "model": "Turbo Max", "variant": "Life A",
        "soldDate": "2026-11-02", "coulsonStatus": "SOLD",
    })
    created = await client.post("/api/oem-billing/create", json={"chassis": "MD9NEW0999"})
    assert created.status_code == 200, created.text
    body = created.json()
    assert body.get("created") is True
    assert body.get("leadId") != lid
    new_id = body["leadId"]
    docs = (await client.get(f"/api/leads/{new_id}/documents")).json()
    kinds = {d["kind"] for d in docs}
    assert "kyc_pan" in kinds
    assert await server.db.leads.count_documents({"mobile": mobile}) == 2
