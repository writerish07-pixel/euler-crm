"""Tally pack checker — Ganpat-style invoice / ledger / receipts, flags only."""
import io
import os
import sys
import zipfile

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "tally_pack_tests")
os.environ.setdefault("JWT_SECRET", "tally-pack-secret-32chars!!xxxx")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import tally_pack  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402

PW = "euler@123"

INVOICE = """
Tax Invoice
AKAR FOURWHEEL PVT LTD (EULER)
Buyer (Bill to)
TEST RAM JAT S/O PRABHATI LAL JAT
Invoice No.
AF-122-I26270213
MD9EVDAD26J217668 - Turbo EV 1000
Less : - A.D. (-)1,173.00
CGST 18,661.15
SGST 18,661.15
Total ī7,83,768.00	1 NOS
"""

LEDGER = """
TEST RAM JAT S/O PRABHATI LAL JAT
Ledger Account
9-Oct-26 Dr CENTRAL BANK OF INDIA 5032 5,000.00	CR/CBI/2627/712	RECEIPT - 5032
11-Oct-26 Cr EULER LOADING SALES 7,83,768.00	AF-122-I26270213	Euler Sales
Cr AKAR FOURWHEEL PVT LTD-TATA 18,032.00	2905033126	JOURNAL - INSURANCE
Cr AKAR FOURWHEEL PVT LTD-TATA 2,200.00	MD9EVDAD26J217668	JOURNAL - RTO
12-Oct-26 Dr CENTRAL BANK OF INDIA 5032 6,80,000.00	CR/CBI/2627/739	RECEIPT - 5032
8,04,000.00	8,04,000.00
"""

RECEIPT = """
RECEIPT - 5032 Voucher
No. : CR/CBI/2627/712
Account :
TEST RAM JAT S/O PRABHATI LAL JAT 5,000.00
UPI/RRN 687911271366
"""


def test_parse_ganpat_style_invoice():
    inv = tally_pack.parse_invoice(INVOICE)
    assert inv["total"] == 783768
    assert inv["additionalDiscount"] == 1173
    assert inv["cgst"] == 18661.15
    assert "AF-122" in inv["invoiceNumber"]
    assert "MD9EVDAD26J217668" in inv["chassis"]
    assert tally_pack.names_match(inv["customerName"], "TEST RAM JAT")


def test_parse_ledger_and_receipt():
    led = tally_pack.parse_ledger(LEDGER)
    assert led["sales"] == 783768
    assert led["insurance"] == 18032
    assert led["rto"] == 2200
    rec = tally_pack.parse_receipt(RECEIPT)
    assert rec["amount"] == 5000
    assert rec["voucherNo"].startswith("CR/")


def test_compare_flags_invoice_mismatch_and_missing_receipt():
    files = [
        {"filename": "bill.pdf", "kind": "invoice", "text": INVOICE},
        {"filename": "ledger.pdf", "kind": "ledger", "text": LEDGER},
        {"filename": "r5.pdf", "kind": "receipt", "text": RECEIPT},
    ]
    expected = {
        "tallyTotal": 783768,
        "discount": 1173,
        "rto": 2200,
        "insurance": 18032,
        "payable": 804000,
        "customerName": "TEST RAM JAT",
        "chassis": "MD9EVDAD26J217668",
        "payments": [5000, 50000],
    }
    flags = tally_pack.compare(expected, files, crm_docs=set())
    messages = [f["message"] for f in flags]
    assert not any("Invoice ₹" in m and "vs Tally" in m for m in messages)
    assert any("50,000" in m or "50000" in m.replace(",", "") for m in messages)


def test_run_check_ok_when_pack_and_docs_match():
    lead = {
        "customerName": "TEST RAM JAT",
        "chassisNumber": "MD9EVDAD26J217668",
        "customerType": "Individual",
        "additionalDiscount": 1173,
        "rto": 2200,
        "insuranceAmount": 18032,
        "customerPayable": 804000,
        "oemExtraSupportReceived": 0,
    }
    summary = {
        "totals": {"tallyBillTotal": 783768, "additionalDiscount": 1173, "customerPayable": 804000},
        "offTallyLines": [
            {"code": "rto", "amount": 2200},
            {"code": "insurance", "amount": 18032},
        ],
        "gstReference": {"cgst": 18661.15, "sgst": 18661.15},
    }
    files = [
        {"filename": "bill.pdf", "kind": "invoice", "text": INVOICE},
        {"filename": "ledger.pdf", "kind": "ledger", "text": LEDGER},
        {"filename": "r5.pdf", "kind": "receipt", "text": RECEIPT},
    ]
    kinds = {"kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "deal_sheet",
             "delivery_insurance", "delivery_rto", "tally_invoice"}
    out = tally_pack.run_check(
        lead=lead, files=files, payments=[{"amount": 5000}], summary=summary, kinds=kinds)
    assert out["ok"] is True
    assert out["errorCount"] == 0


def test_compare_pack_requires_each_unit_invoice_and_flags_combined_ledger():
    summary = {
        "pack": True,
        "units": [
            {"sno": 1, "tallyBillTotal": 783768, "additionalDiscount": 1173,
             "chassisNumber": "MD9EVDAD26J217668", "offTallyLines": [],
             "customerPayable": 783768},
            {"sno": 2, "tallyBillTotal": 783768, "additionalDiscount": 1173,
             "chassisNumber": "MD9EVDAD26J217669", "offTallyLines": [],
             "customerPayable": 783768},
        ],
        "totals": {"tallyBillTotal": 1567536, "customerPayable": 1567536},
    }
    lead = {"customerName": "TEST RAM JAT", "customerType": "Individual"}
    missing = tally_pack.compare_pack(summary, lead, [], [
        {"filename": "u1.txt", "kind": "invoice", "text": INVOICE,
         "unitSno": 1, "unitSnos": [1]},
    ])
    assert any(f["code"] == "invoice_missing" and "Unit 2" in f["message"] for f in missing)
    flags = tally_pack.compare_pack(summary, lead, [], [
        {"filename": "u1.txt", "kind": "invoice", "text": INVOICE,
         "unitSno": 1, "unitSnos": [1]},
        {"filename": "u2.txt", "kind": "invoice", "text": INVOICE,
         "unitSno": 2, "unitSnos": [2]},
        {"filename": "led.txt", "kind": "ledger", "text": LEDGER,
         "unitSnos": [1, 2]},
    ])
    assert not any(f["code"] == "invoice_missing" for f in flags)
    assert any(f["code"] == "ledger_sales" for f in flags)


def test_compare_pack_legacy_zip_warns_to_split_invoices():
    summary = {
        "pack": True,
        "units": [
            {"sno": 1, "tallyBillTotal": 400000, "offTallyLines": []},
            {"sno": 2, "tallyBillTotal": 383768, "offTallyLines": []},
        ],
        "totals": {"tallyBillTotal": 783768},
    }
    flags = tally_pack.compare_pack(summary, {"customerName": "TEST RAM JAT"}, [], [
        {"filename": "bill.txt", "kind": "invoice", "text": INVOICE},
        {"filename": "ledger.txt", "kind": "ledger", "text": LEDGER},
    ])
    assert any(f["code"] == "invoice_per_unit" for f in flags)


def test_unpack_zip_reads_txt_pages():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("invoice.pdf", b"%PDF-not-valid")
        zf.writestr("ledger.txt", LEDGER)
    files = tally_pack.unpack(buf.getvalue(), "pack.zip", "application/zip")
    kinds = {f["kind"] for f in files}
    assert "ledger" in kinds


@pytest_asyncio.fixture
async def client():
    await server.startup()
    await server.db.leads.delete_many({})
    await server.db.payments.delete_many({})
    await server.db[server.lead_docs.COLLECTION].delete_many({})
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": PW})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _zip_pack():
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("bill.txt", INVOICE)
        zf.writestr("ledger.txt", LEDGER)
        zf.writestr("receipt.txt", RECEIPT)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_tally_pack_check_endpoint_flags_then_matches(client):
    r = await client.post("/api/leads", json={
        "customerName": "TEST RAM JAT", "mobile": "9811100999",
        "interestedModel": "Turbo Max", "variant": "Maxx (PV)", "executive": "Amit"})
    lid = r.json()["leadId"]
    await server.db.leads.update_one({"leadId": lid}, {"$set": {
        "exShowroom": 785000, "additionalDiscount": 1173, "rto": 2200,
        "insuranceAmount": 18032, "customerPayable": 804000,
        "chassisNumber": "MD9EVDAD26J217668",
    }})
    empty = await client.post(f"/api/leads/{lid}/tally-pack/check")
    assert empty.status_code == 200, empty.text
    assert empty.json()["ok"] is False
    assert any(f["code"] == "pack" for f in empty.json()["flags"])

    up = await client.post(
        f"/api/leads/{lid}/documents",
        files={"file": ("pack.zip", io.BytesIO(_zip_pack()), "application/zip")},
        data={"kind": "tally_invoice"})
    assert up.status_code == 200, up.text
    checked = await client.get(f"/api/leads/{lid}/tally-pack")
    assert checked.status_code == 200, checked.text
    assert checked.json().get("found", {}).get("ledgerCount") >= 1
