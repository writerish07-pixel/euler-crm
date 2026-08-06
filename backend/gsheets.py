"""One-way sync: append new records to the existing Euler Master Google Sheet.

Uses a Google Service Account. Activates automatically once a credentials JSON
is present at GSHEET_CREDENTIALS_PATH and the sheet is shared with the service
account email as Editor. If not configured, every call is a safe no-op.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Worksheet/tab name in the Euler Master sheet -> header order for appended rows.
SYNC_MAP = {
    "leads": ("Lead Register", ["leadId", "createdDate", "customerName", "mobile", "leadSource",
                                "interestedModel", "variant", "executive", "currentStatus"]),
    "bookings": ("Booking Register", ["bookingId", "leadId", "customerName", "bookingDate", "model",
                                      "variant", "bookingAmount", "paymentMode", "bookingStatus"]),
    "payments": ("Payment Ledger", ["receiptNumber", "leadId", "customerName", "date", "amount",
                                    "paymentMode", "narration", "runningTotal", "outstandingBalance"]),
    "deliveries": ("Delivery Tracker", ["leadId", "customerName", "deliveryDate", "delivered",
                                        "invoiceNumber", "chassisNumber", "numberPlate"]),
    "claims": ("Scheme Claim Register", ["claimId", "leadId", "customer", "model", "component",
                                         "claimAmount", "claimStatus", "receivedAmount", "claimReference"]),
}

_service = None
_status = {"enabled": False, "reason": "not configured", "email": None}


def _init():
    global _service, _status
    path = os.environ.get("GSHEET_CREDENTIALS_PATH", "")
    sheet_id = os.environ.get("GSHEET_ID", "")
    if not path or not Path(path).exists():
        _status = {"enabled": False, "reason": "credentials JSON not found — add the service account key to enable sync", "email": None}
        _service = None
        return
    if not sheet_id:
        _status = {"enabled": False, "reason": "GSHEET_ID missing", "email": None}
        return
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        import json
        info = json.loads(Path(path).read_text())
        creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
        _service = build("sheets", "v4", credentials=creds, cache_discovery=False)
        _status = {"enabled": True, "reason": "connected", "email": info.get("client_email")}
    except Exception as e:
        _service = None
        _status = {"enabled": False, "reason": f"init failed: {e}", "email": None}


def status():
    global _status
    if _service is None:
        _init()
    if _service is None:
        return {**_status, "spreadsheetId": os.environ.get("GSHEET_ID", "")}
    # probe write permission with a harmless empty batchUpdate (needs Editor)
    sheet_id = os.environ.get("GSHEET_ID", "")
    try:
        _service.spreadsheets().get(spreadsheetId=sheet_id, fields="properties.title").execute()
        _status["canRead"] = True
    except Exception as e:
        _status.update({"enabled": False, "canRead": False, "canWrite": False,
                        "reason": "cannot access sheet — share it with the service account email"})
        return {**_status, "spreadsheetId": sheet_id}
    try:
        _service.spreadsheets().batchUpdate(spreadsheetId=sheet_id, body={"requests": []}).execute()
        _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
    except Exception as e:
        # 400 "Must specify at least one request" means the write PASSED permission
        # (only failed body validation) => we DO have Editor access. 403 = no access.
        code = getattr(getattr(e, "resp", None), "status", None)
        msg = str(e)
        if str(code) == "400" or "at least one request" in msg:
            _status.update({"enabled": True, "canWrite": True, "reason": "connected (read + write)"})
        else:
            _status.update({"enabled": False, "canWrite": False,
                            "reason": "read-only — share the sheet with the service account email as EDITOR to enable syncing"})
    return {**_status, "spreadsheetId": sheet_id}


def _append_sync(tab, values):
    sheet_id = os.environ.get("GSHEET_ID", "")
    _service.spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": [values]},
    ).execute()


async def append(entity: str, doc: dict):
    """Append one record to the mapped worksheet. No-op if sync disabled."""
    global _service
    if _service is None:
        _init()
    if _service is None or not _status.get("enabled"):
        return False
    mapping = SYNC_MAP.get(entity)
    if not mapping:
        return False
    tab, fields = mapping
    row = [doc.get(f, "") for f in fields]
    try:
        await asyncio.to_thread(_append_sync, tab, row)
        return True
    except Exception as e:
        _status["lastError"] = str(e)
        return False


def _read_column_a(tab):
    sheet_id = os.environ.get("GSHEET_ID", "")
    res = _service.spreadsheets().values().get(spreadsheetId=sheet_id, range=f"'{tab}'!A:A").execute()
    return {str(r[0]).strip() for r in res.get("values", []) if r}


def _append_many(tab, rows):
    sheet_id = os.environ.get("GSHEET_ID", "")
    _service.spreadsheets().values().append(
        spreadsheetId=sheet_id, range=f"'{tab}'!A1",
        valueInputOption="USER_ENTERED", insertDataOption="INSERT_ROWS",
        body={"values": rows},
    ).execute()


def _backfill_sync(datasets):
    """datasets = {entity: [docs]}. Idempotent: skips records whose key already
    exists in the sheet's column A. Returns per-entity {appended, skipped}."""
    result = {}
    for entity, docs in datasets.items():
        mapping = SYNC_MAP.get(entity)
        if not mapping:
            continue
        tab, fields = mapping
        key_field = fields[0]
        existing = _read_column_a(tab)
        rows, skipped = [], 0
        for d in docs:
            key = str(d.get(key_field, "")).strip()
            if key and key in existing:
                skipped += 1
                continue
            rows.append([d.get(f, "") for f in fields])
        if rows:
            _append_many(tab, rows)
        result[entity] = {"appended": len(rows), "skipped": skipped}
    return result


async def backfill(datasets):
    global _service
    if _service is None:
        _init()
    st = status()
    if not st.get("enabled") or not st.get("canWrite"):
        return {"ok": False, "reason": st.get("reason", "sync not enabled"), "canWrite": st.get("canWrite", False)}
    try:
        result = await asyncio.to_thread(_backfill_sync, datasets)
        return {"ok": True, "result": result}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# initialise on import
_init()
