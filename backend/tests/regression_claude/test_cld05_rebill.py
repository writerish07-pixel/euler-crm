"""CLD-05: a Sold row with a blank invoice is not a live rebill and is not deleted."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "cld05_rebill")
os.environ.setdefault("JWT_SECRET", "cld05-rebill-secret-32-characters")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import oem_sync  # noqa: E402
import server  # noqa: E402


@pytest.mark.asyncio
async def test_blank_invoice_sold_row_is_not_cleared():
    chassis = "MD9X1CLD05"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.oem_cancelled_invoices.delete_many({"chassis": chassis})
    await server.db.oem_sold_removed.delete_many({"chassis": chassis})
    await server.db.leads.delete_many({"leadId": "LD26CLD05"})
    await server.db.oem_sold.insert_one({"chassis": chassis, "invoiceNumber": "", "mobile": "9811111111"})
    await server.db.oem_cancelled_invoices.insert_one({"chassis": chassis, "invoiceNumber": "INV-A"})
    await server.db.leads.insert_one({
        "leadId": "LD26CLD05", "customerName": "Keep", "mobile": "9811111111",
        "chassisNumber": chassis, "invoiceNumber": "INV-A",
        "currentStatus": "Booked", "accountStatus": "Active",
    })
    stats = await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert chassis in stats["ambiguousBlankInvoice"]
    sold = await server.db.oem_sold.find_one({"chassis": chassis})
    assert sold
    lead = await server.db.leads.find_one({"leadId": "LD26CLD05"})
    assert lead["chassisNumber"] == chassis


@pytest.mark.asyncio
async def test_bare_cancel_still_clears_and_archives():
    chassis = "MD9BARECLD05"
    await server.db.oem_sold.delete_many({"chassis": chassis})
    await server.db.oem_cancelled_invoices.delete_many({"chassis": chassis})
    await server.db.oem_invoices.delete_many({"chassis": chassis})
    await server.db.oem_sold.insert_one({"chassis": chassis, "invoiceNumber": "INV-GONE"})
    await server.db.oem_cancelled_invoices.insert_one({"chassis": chassis, "invoiceNumber": "INV-GONE"})
    await server.db.leads.delete_many({"leadId": "LD26CLD05B"})
    await server.db.leads.insert_one({
        "leadId": "LD26CLD05B", "mobile": "9822222222", "customerName": "Gone",
        "chassisNumber": chassis, "invoiceNumber": "INV-GONE",
        "currentStatus": "Booked", "accountStatus": "Active",
    })
    await oem_sync.delink_cancelled_sold_invoices(server.db)
    assert await server.db.oem_sold.find_one({"chassis": chassis}) is None
    archived = await server.db.oem_sold_removed.find_one({"chassis": chassis})
    assert archived
    assert archived.get("reason")
    lead = await server.db.leads.find_one({"leadId": "LD26CLD05B"})
    assert not lead.get("chassisNumber")
