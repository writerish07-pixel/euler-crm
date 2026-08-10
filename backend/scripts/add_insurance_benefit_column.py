#!/usr/bin/env python3
"""Idempotently add Lead Register header 'Insurance Benefit' after 'Loyalty Bonus'.

Safety rules (production Euler Master):
  * Find headers by TEXT, never by fixed column numbers.
  * Only touch Lead Register header row (default 3).
  * Insert one column after Loyalty Bonus if Insurance Benefit is missing.
  * Never clear(), never reorder rows, never touch A:I helper area contents
    beyond the structural column insert that Sheets applies to the whole grid.
  * Refuse to run if Loyalty Bonus header is not found.
  * No-op if Insurance Benefit already exists.

Credentials (any one path):
  * env GSHEET_CREDENTIALS_JSON = full service-account JSON string
  * env GSHEET_CREDENTIALS_PATH / /etc/secrets/gsheets_credentials.json
  * env GSHEET_ID = spreadsheet id
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from google.oauth2 import service_account  # noqa: E402
from googleapiclient.discovery import build  # noqa: E402

import gsheets  # noqa: E402

TAB = os.environ.get("GSHEET_TAB_LEADS", "").strip() or "Lead Register"
ANCHOR_HEADER = "Loyalty Bonus"
NEW_HEADER = "Insurance Benefit"
SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]


def _creds_path():
    raw = os.environ.get("GSHEET_CREDENTIALS_JSON", "").strip()
    if raw:
        data = json.loads(raw)
        fd, path = tempfile.mkstemp(prefix="gsheet-", suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump(data, f)
        return path, "env:GSHEET_CREDENTIALS_JSON"
    path, label = gsheets.resolve_credentials_path()
    return path, label


def _service():
    path, label = _creds_path()
    sheet_id = os.environ.get("GSHEET_ID", "").strip()
    if not path:
        raise SystemExit("No Google credentials found (GSHEET_CREDENTIALS_JSON or gsheets_credentials.json).")
    if not sheet_id:
        raise SystemExit("GSHEET_ID is missing.")
    creds = service_account.Credentials.from_service_account_file(path, scopes=SCOPES)
    return build("sheets", "v4", credentials=creds, cache_discovery=False), sheet_id, label


def _sheet_meta(svc, sheet_id):
    meta = svc.spreadsheets().get(
        spreadsheetId=sheet_id,
        fields="sheets(properties(sheetId,title,gridProperties))",
    ).execute()
    for sh in meta.get("sheets", []):
        props = sh.get("properties") or {}
        if props.get("title") == TAB:
            return props["sheetId"], props.get("gridProperties") or {}
    raise SystemExit(f"Tab not found: {TAB!r}")


def _read_header_row(svc, sheet_id, header_row):
    resp = svc.spreadsheets().values().get(
        spreadsheetId=sheet_id,
        range=f"'{TAB}'!{header_row}:{header_row}",
        majorDimension="ROWS",
    ).execute()
    values = (resp.get("values") or [[]])[0]
    return [str(c or "").strip() for c in values]


def main():
    dry = "--dry-run" in sys.argv
    svc, sheet_id, cred_src = _service()
    sheet_gid, grid = _sheet_meta(svc, sheet_id)
    header_row = int(os.environ.get("GSHEET_HEADERROW_LEADS", "").strip() or "3")
    headers = _read_header_row(svc, sheet_id, header_row)

    def find(name):
        target = gsheets._norm(name)
        for i, h in enumerate(headers):
            if gsheets._norm(h) == target:
                return i
        return None

    existing = find(NEW_HEADER)
    if existing is not None:
        letter = gsheets._col_letter(existing)
        print(json.dumps({
            "ok": True, "action": "already_present",
            "tab": TAB, "headerRow": header_row,
            "column": letter, "header": NEW_HEADER,
            "credentialSource": cred_src,
        }, indent=2))
        return 0

    anchor = find(ANCHOR_HEADER)
    if anchor is None:
        raise SystemExit(
            f"Anchor header {ANCHOR_HEADER!r} not found on {TAB} row {header_row}. "
            "Refusing to guess a column.")

    insert_at = anchor + 1  # 0-based index; Sheets API uses 0-based startIndex
    letter = gsheets._col_letter(insert_at)
    print(json.dumps({
        "ok": True,
        "action": "planned_insert" if dry else "inserting",
        "tab": TAB,
        "headerRow": header_row,
        "after": ANCHOR_HEADER,
        "afterColumn": gsheets._col_letter(anchor),
        "newColumn": letter,
        "header": NEW_HEADER,
        "columnCount": grid.get("columnCount"),
        "credentialSource": cred_src,
        "dryRun": dry,
    }, indent=2))
    if dry:
        return 0

    svc.spreadsheets().batchUpdate(
        spreadsheetId=sheet_id,
        body={"requests": [{
            "insertDimension": {
                "range": {
                    "sheetId": sheet_gid,
                    "dimension": "COLUMNS",
                    "startIndex": insert_at,
                    "endIndex": insert_at + 1,
                },
                "inheritFromBefore": True,
            }
        }]},
    ).execute()

    # Write ONLY the new header cell — do not touch data rows or other headers.
    svc.spreadsheets().values().update(
        spreadsheetId=sheet_id,
        range=f"'{TAB}'!{letter}{header_row}",
        valueInputOption="RAW",
        body={"values": [[NEW_HEADER]]},
    ).execute()

    # Verify
    headers2 = _read_header_row(svc, sheet_id, header_row)
    idx = None
    target = gsheets._norm(NEW_HEADER)
    for i, h in enumerate(headers2):
        if gsheets._norm(h) == target:
            idx = i
            break
    if idx is None:
        raise SystemExit("Insert appeared to run but Insurance Benefit header was not found afterward.")
    # Confirm Loyalty still immediately precedes it when possible
    if idx > 0 and gsheets._norm(headers2[idx - 1]) != gsheets._norm(ANCHOR_HEADER):
        print("WARNING: Insurance Benefit is present but not immediately after Loyalty Bonus.",
              file=sys.stderr)

    print(json.dumps({
        "ok": True, "action": "inserted",
        "tab": TAB, "headerRow": header_row,
        "column": gsheets._col_letter(idx), "header": NEW_HEADER,
        "previousHeader": headers2[idx - 1] if idx else None,
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
