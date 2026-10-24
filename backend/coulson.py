"""Coulson (Euler OEM portal) HTTP client.

Login is Basic auth against euler-auth: base64(username:password:coulson),
then Bearer JWT on coulson.eulerlogistics.com. Credentials come from owner Settings (Mongo), with optional env fallback
(COULSON_USERNAME / COULSON_PASSWORD). Never log the password.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Optional

import httpx
import jwt

log = logging.getLogger("coulson")

DEFAULT_AUTH_URL = "https://euler-auth.eulerlogistics.com/api/v1"
DEFAULT_API_URL = "https://coulson.eulerlogistics.com/api/v1"
APP_NAME = "coulson"
# Login / session ping must stay short so Settings Save cannot freeze the desk.
LOGIN_TIMEOUT = 25
# Yard, Sold, Vehicle Invoices and claims page Coulson slowly. 25s cut the
# Sold pull mid-page after today's billed list grew, then OEM Billing kept
# yesterday's chassis.
DATA_TIMEOUT = 90
TIMEOUT = LOGIN_TIMEOUT
INVENTORY_PAGE = 200
INVENTORY_MAX_ROWS = 20000


class CoulsonError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def _env(name, default=""):
    return (os.environ.get(name) or default).strip()


def auth_url():
    return _env("COULSON_AUTH_URL", DEFAULT_AUTH_URL).rstrip("/")


def api_url():
    return _env("COULSON_API_URL", DEFAULT_API_URL).rstrip("/")


def clean_credential(v) -> str:
    """Strip surrounding whitespace from a typed credential.

    The username was already trimmed on the way in; the password was not. A
    password pasted from a note or a password manager routinely carries a
    trailing space or newline, and Coulson then answers "Username/password is
    not valid" — indistinguishable from actually getting it wrong. No portal
    permits a password whose first or last character is a space, so trimming
    can only help.
    """
    return str(v or "").strip()


def app_name() -> str:
    return _env("COULSON_APP_NAME", APP_NAME)


def basic_auth_value(username: str, password: str, app: str = "") -> str:
    """Same encoding as Coulson's browser login: btoa(`${user}:${pass}:coulson`)."""
    app = app or app_name()
    raw = f"{username}:{password}:{app}"
    try:
        blob = raw.encode("latin-1")
    except UnicodeEncodeError:
        blob = raw.encode("utf-8")
    return base64.b64encode(blob).decode("ascii")


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Do not follow redirects on an authenticated call.

    urllib turns a redirected POST into a GET and drops the Authorization
    header on a cross-host hop. The login would then arrive with no credentials
    at all and come back "Username/password is not valid" — a wrong-password
    message for something that is not a password problem. Surfacing the 3xx
    says what actually happened.
    """
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise CoulsonError(
            f"Coulson redirected to {newurl} ({code}). The configured URL is not the "
            f"final one — an authenticated POST loses its credentials across a redirect.",
            status=code)


# Login only. The data calls keep urllib's default behaviour: if Coulson
# legitimately redirects a GET, breaking that would trade one failure for
# another, and only the LOGIN misreports a dropped credential as a bad password.
_no_redirect_opener = urllib.request.build_opener(_NoRedirect)


def _request(url, method="GET", headers=None, body=None, follow_redirects=True,
             timeout=None):
    hdrs = {"Accept": "application/json"}
    if headers:
        hdrs.update(headers)
    if body is None and str(method).upper() == "POST":
        data = b""
    elif body is None or isinstance(body, (bytes, bytearray)):
        data = body
    else:
        data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    opener = urllib.request.urlopen if follow_redirects else _no_redirect_opener.open
    seconds = DATA_TIMEOUT if timeout is None else timeout
    try:
        with opener(req, timeout=seconds) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        raise CoulsonError(_message_from_body(raw) or e.reason or str(e), status=e.code) from e
    except urllib.error.URLError as e:
        raise CoulsonError(f"Coulson unreachable: {e.reason}") from e
    except TimeoutError as e:
        raise CoulsonError(f"Coulson timed out after {seconds}s") from e
    try:
        parsed = json.loads(raw.decode() or "{}")
    except json.JSONDecodeError:
        raise CoulsonError(f"Non-JSON response from Coulson ({status})")
    return status, parsed


def _message_from_body(raw):
    try:
        return (json.loads(raw.decode() or "{}") or {}).get("message") or ""
    except Exception:
        return ""


# Same headers the Coulson SPA sends (plus Origin/Referer the browser adds).
# Euler's CloudFront CORS list includes both coulson.eulerlogistics.com and
# euler-crm.onrender.com; Origin must look like a dealer login, not a bot.
PORTAL_ORIGIN = "https://coulson.eulerlogistics.com"
LOGIN_HEADERS = {
    "Accept": "*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": PORTAL_ORIGIN,
    "Referer": f"{PORTAL_ORIGIN}/",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Access-Control-Allow-Origin": "*",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site",
}


def login_headers(username: str, password: str) -> dict:
    """Headers for POST /login — no Content-Type, no body. Matches the SPA fetch."""
    return {
        **LOGIN_HEADERS,
        "Authorization": f"Basic {basic_auth_value(username, password)}",
    }


def login(username: str, password: str) -> str:
    """Log in the same way coulson.eulerlogistics.com does.

    The SPA is: POST euler-auth .../login with Authorization Basic
    btoa(`${user}:${pass}:coulson`) and an empty body. urllib was sending
    Content-Length 0 as a form POST, which Euler treats as a missing
    credential and answers "Username/password is not valid".
    """
    username, password = clean_credential(username), clean_credential(password)
    if not username or not password:
        raise CoulsonError("Coulson username and password are required")
    url = f"{auth_url()}/login"
    headers = login_headers(username, password)
    try:
        with httpx.Client(timeout=LOGIN_TIMEOUT, follow_redirects=False) as client:
            # No content=/json=/data= — a body-less POST, like `new Request(..., {method:"POST"})`.
            resp = client.post(url, headers=headers)
    except httpx.RequestError as e:
        raise CoulsonError(f"Coulson unreachable: {e}") from e
    if 300 <= resp.status_code < 400:
        loc = resp.headers.get("location") or ""
        raise CoulsonError(
            f"Coulson redirected to {loc} ({resp.status_code}). The configured URL is not the "
            f"final one — an authenticated POST loses its credentials across a redirect.",
            status=resp.status_code,
        )
    try:
        payload = resp.json() if resp.content else {}
    except Exception:
        raise CoulsonError(f"Non-JSON response from Coulson ({resp.status_code})")
    if not isinstance(payload, dict):
        payload = {}
    if not payload.get("success"):
        raise CoulsonError(
            payload.get("message") or resp.reason_phrase or "Coulson login failed",
            status=resp.status_code,
        )
    token = ((payload.get("data") or {}) or {}).get("token") or ""
    if not token:
        raise CoulsonError("Coulson login returned no token", status=resp.status_code)
    return token


def clean_session_token(v: str) -> str:
    """Strip paste artefacts from a coulson_auth value copied out of the dealer site."""
    s = str(v or "").strip()
    if len(s) >= 2 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    if s.lower().startswith("bearer "):
        s = s[7:].strip()
    return s


def session_username(claims: dict) -> str:
    if not isinstance(claims, dict):
        return ""
    return str(claims.get("username") or claims.get("email") or claims.get("sub") or "").strip()


def session_expires_iso(claims: dict) -> str:
    if not isinstance(claims, dict) or claims.get("exp") is None:
        return ""
    try:
        exp = int(claims["exp"])
    except (TypeError, ValueError):
        return ""
    return datetime.fromtimestamp(exp, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_session_token(token: str) -> dict:
    """Read a Coulson JWT without verifying Euler's signature (we do not have their key).

    The dealer site stores this in localStorage as coulson_auth after a browser login.
    We still check shape, expiry, and application=coulson before sending it to their API.
    """
    token = clean_session_token(token)
    if not token or token.count(".") != 2:
        raise CoulsonError(
            "That is not a Coulson session. Sign in at coulson.eulerlogistics.com, then copy "
            "localStorage key coulson_auth and paste it here."
        )
    try:
        claims = jwt.decode(
            token,
            options={"verify_signature": False, "verify_aud": False, "verify_exp": False},
        )
    except Exception:
        raise CoulsonError(
            "That session could not be read. Sign in at coulson.eulerlogistics.com and copy "
            "coulson_auth again."
        )
    if not isinstance(claims, dict):
        raise CoulsonError("That session could not be read.")
    app = str(claims.get("application") or "")
    if app and app != APP_NAME:
        raise CoulsonError(f"That session is for '{app}', not Coulson.")
    exp = claims.get("exp")
    if exp is not None:
        try:
            exp_i = int(exp)
        except (TypeError, ValueError):
            exp_i = 0
        if exp_i <= time.time():
            raise CoulsonError(
                "That Coulson session has expired. Sign in at coulson.eulerlogistics.com again "
                "and paste a new session."
            )
    return claims


def verify_session_token(token: str) -> dict:
    """Confirm the pasted session is a live Coulson JWT.

    This hits the inventory API with Bearer auth — not euler-auth /login — so it cannot
    lock the dealer password. Euler already issued this token to the owner's browser.
    """
    token = clean_session_token(token)
    claims = parse_session_token(token)
    try:
        fetch_sap_models(token)
    except CoulsonError as e:
        raise CoulsonError(
            "Coulson did not accept that session. Sign in at coulson.eulerlogistics.com and "
            "copy coulson_auth again.",
            status=e.status,
        ) from e
    return claims


def _bearer(token):
    return {"Authorization": f"Bearer {token}"}


def get_json(token: str, path: str, params: Optional[dict] = None):
    url = f"{api_url()}/{path.lstrip('/')}"
    if params:
        url += "?" + urllib.parse.urlencode(params, doseq=True)
    status, payload = _request(url, headers=_bearer(token))
    if not payload.get("success", True) and status >= 400:
        raise CoulsonError(payload.get("message") or "Coulson request failed", status=status)
    return payload


def fetch_sap_models(token: str):
    payload = get_json(token, "sap-vehicle-models")
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


def _row_page_key(row):
    if not isinstance(row, dict):
        return ""
    return (
        str(row.get("id") or "").strip()
        or _vehicle_key(row)
        or str(row.get("debit_note_number") or row.get("invoice_number") or "")
    )


def _page_rows(token: str, path: str, params: Optional[dict] = None, *,
               limit=INVENTORY_PAGE, max_rows=INVENTORY_MAX_ROWS, meta=None):
    """Walk `{success, data[], extras.total_count}`. Keep earlier pages if a later page fails.

    Live Coulson SPA (debit-note, dealer-inventory) sends offset as a 0-based
    *page index*. Yard / Sold still use row-skip. Probe offset=1: a mostly-new
    page means page-index; a 1-row slide means row-skip.
    """
    rows, seen = [], set()
    total = None
    last_error = None
    base = dict(params or {})

    def pull(off):
        payload = get_json(token, path, {**base, "limit": str(limit), "offset": str(off)})
        chunk = payload.get("data") or []
        if not isinstance(chunk, list):
            chunk = []
        extras = payload.get("extras") or {}
        got = extras.get("total_count")
        parsed = None
        if got is not None:
            try:
                parsed = int(got)
            except (TypeError, ValueError):
                parsed = None
        return chunk, parsed

    def take(chunk):
        added = 0
        for row in chunk:
            if not row:
                continue
            key = _row_page_key(row) or f"idx:{len(rows)}"
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
            added += 1
        return added

    try:
        first, total = pull(0)
    except CoulsonError as e:
        last_error = e
        log.warning("Coulson %s offset=%s failed: %s", path, 0, e)
        if meta is not None:
            meta["total"] = total
            meta["complete"] = False
        raise last_error
    take(first)
    if not first or len(first) < limit or (total is not None and len(rows) >= total):
        if meta is not None:
            meta["total"] = total
            meta["complete"] = True
        return rows

    page_index = False
    try:
        probe, tot2 = pull(1)
        if tot2 is not None:
            total = tot2
        probe_new = take(probe)
        page_index = bool(probe) and probe_new > (len(probe) / 2)
    except CoulsonError as e:
        last_error = e
        log.warning("Coulson %s offset=%s failed: %s", path, 1, e)
        if meta is not None:
            meta["total"] = total
            meta["complete"] = False
        return rows

    nxt = 2 if page_index else limit
    step = 1 if page_index else limit
    while len(rows) < max_rows:
        if total is not None and len(rows) >= total:
            break
        try:
            chunk, tot2 = pull(nxt)
        except CoulsonError as e:
            last_error = e
            log.warning("Coulson %s offset=%s failed: %s", path, nxt, e)
            break
        if tot2 is not None:
            total = tot2
        added = take(chunk)
        if not chunk or len(chunk) < limit or added == 0:
            break
        nxt += step
    if meta is not None:
        meta["total"] = total
        meta["complete"] = last_error is None
    return rows


def fetch_inventory_by_status(token: str, vehicle_status: str, limit=INVENTORY_PAGE,
                              sort=None, meta=None):
    """Paginated vehicle-inventory/transfer for one Coulson vehicle_status."""
    status = str(vehicle_status or "").strip() or "PRESENT"
    return _page_rows(token, "vehicle-inventory/transfer", {
        "view_type": "table",
        "sort": sort or json.dumps(["created_at", "DESC"]),
        "vehicle_status": status,
    }, limit=limit, meta=meta)


def fetch_present_inventory(token: str, limit=INVENTORY_PAGE):
    """Yard stock currently PRESENT at the logged-in dealer."""
    return fetch_inventory_by_status(token, "PRESENT", limit=limit)


# Billed vehicles leave PRESENT immediately. The dealer Sold tab is
# vehicle-inventory/transfer?vehicle_status=SOLD. Chassis billed today also
# land on Vehicle Invoices (SPA `#/dealer-inventory-list` → ⋮ → Invoice List)
# before Sold catches up. Oct 2026 Coulson app: that list is
# GET /api/v1/dealer/invoice/vehicle — Created and Cancelled rows together.
#
# Oct 2026 Coulson SPA (dealer login) vs Euler:
#   CONNECTED — sap-vehicle-models (Price Master), PRESENT (Yard),
#     IN_TRANSIT, SOLD + Invoice List Created, debit-note claims (line
#     items + header Linked Vehicles chassis).
#   THIS SYNC — Invoice List CANCELLED (drop those chassis from leads),
#     BOOKED / PILOT / DEMO as held (not sellable yard).
#   NOT YET — Create Quotation, Quotation List, Stock Transfer, Vehicle
#     E-POD, Vehicle Orders, KYC amendments, Inbound/Prime tickets,
#     Euler Assured, AMC/EW offers, Warranty Parts, Analytics,
#     Announcements, Complaint Management, Downloads.
SOLD_INVENTORY_STATUSES = ("SOLD",)
TRANSIT_INVENTORY_STATUSES = ("IN_TRANSIT",)
# Vehicle Inventory left filter (Oct 2026 SPA `cDt`): Present, In Transit,
# Sold, Booked, Pilot Vehicle, Demo Vehicle. Unknown ids can echo Present
# and then skip the real Pilot/Demo pull — only send the SPA ids.
HELD_INVENTORY_STATUSES = (
    "BOOKED",
    "PILOT_VEHICLE",
    "DEMO_VEHICLE",
)
INVOICE_LIST_PATH = "dealer/invoice/vehicle"
VEHICLE_INVOICE_PATHS = (
    INVOICE_LIST_PATH,
    "vehicle-inventory/vehicle-invoice",
    "vehicle-invoices",
    "vehicle-invoice",
    "dealer-inventory-list",
    "dealer-inventory",
    "vehicle-inventory/invoices",
    "invoices",
)
_INVOICE_SORTS = (
    json.dumps(["invoice_creation_ts", "DESC"]),
    json.dumps(["date", "DESC"]),
    json.dumps(["invoice_date", "DESC"]),
    json.dumps(["created_at", "DESC"]),
)
_CANCELLED_INVOICE = {"CANCELLED", "CANCELED", "DELETED"}
_LIVE_INVOICE = {"CREATED", "ACTIVE", "POSTED", "CONFIRMED", ""}


def _vehicle_key(v):
    if not isinstance(v, dict):
        return ""
    return (
        str(v.get("chassis") or v.get("chassis_number") or v.get("chassisNumber")
            or v.get("vin") or "").strip().upper()
        or str(v.get("id") or v.get("vehicle_id") or "")
    )


def _invoice_created_at(row):
    """UTC timestamp from Invoice List. None when the row has no creation time."""
    raw = str(
        (row or {}).get("invoice_creation_ts")
        or (row or {}).get("invoiceCreationTs")
        or ""
    ).strip()
    if not raw:
        return None
    text = raw.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _created_invoice_is_newer(incoming, existing) -> bool:
    """True when the incoming Created row should replace invoice fields.

    Invoice List is newest-first. A later page is an older bill for the same
    chassis (rebill). That older row must not wipe the latest invoice number.
    Rows with no timestamp still fill blanks and otherwise overwrite, which
    is how the Sold tab used to land on an invoice-only chassis.
    """
    a = _invoice_created_at(incoming)
    b = _invoice_created_at(existing)
    if isinstance(a, datetime) and isinstance(b, datetime):
        return a >= b
    if isinstance(a, datetime) and b is None:
        return True
    if isinstance(b, datetime) and a is None:
        return False
    return True


def _merge_vehicle_rows(rows, chunk, status=""):
    by_key = {}
    for i, v in enumerate(rows):
        k = _vehicle_key(v)
        if k:
            by_key[k] = i
    for v in chunk or []:
        if not isinstance(v, dict):
            continue
        key = _vehicle_key(v)
        if not key:
            continue
        row = dict(v)
        if status:
            row["_coulsonStatus"] = row.get("_coulsonStatus") or status
        if key in by_key:
            dst = rows[by_key[key]]
            _copy_model_fields(dst, row)
            if row.get("updated_load_body"):
                dst["updated_load_body"] = row["updated_load_body"]
            overwrite = status == "INVOICED" and _created_invoice_is_newer(row, dst)
            for k in (
                "invoice_number", "invoiceNumber", "customer_name", "customer_phone",
                "customer_mobile", "registration_number", "invoice_creation_ts", "date",
                "motor_number", "motorNumber", "motor_no", "engine_number", "engineNumber",
                "battery_number", "batteryNumber", "battery_serial_number",
                "sap_invoice_date", "sap_invoice_number", "delivery_date",
                "total_amount", "amount_paid", "amount_due", "payment_status", "status",
            ):
                if row.get(k) not in (None, "") and (
                        overwrite or dst.get(k) in (None, "")):
                    dst[k] = row[k]
            if status == "INVOICED":
                dst["_coulsonStatus"] = "INVOICED"
            continue
        by_key[key] = len(rows)
        rows.append(row)
    return rows


def fetch_transit_inventory(token: str, limit=INVENTORY_PAGE):
    """Vehicles on the way to the dealer — Coulson In Transit tab."""
    rows = []
    for status in TRANSIT_INVENTORY_STATUSES:
        try:
            chunk = fetch_inventory_by_status(token, status, limit=limit)
        except CoulsonError as e:
            log.info("Coulson %s inventory skipped: %s", status, e)
            continue
        _merge_vehicle_rows(rows, chunk, status)
    return rows


def _held_status_label(status: str) -> str:
    s = str(status or "").strip().upper().replace("-", "_").replace(" ", "_")
    if "BOOK" in s:
        return "BOOKED"
    if "PILOT" in s:
        return "PILOT"
    if "DEMO" in s:
        return "DEMO"
    return s or "HELD"


def fetch_held_inventory(token: str, limit=INVENTORY_PAGE):
    """Booked / Pilot / Demo — on the lot, not sellable Present yard.

    Vehicle Inventory left filter (`cDt`): Present, In Transit, Sold,
    Booked, Pilot Vehicle (`PILOT_VEHICLE`), Demo Vehicle (`DEMO_VEHICLE`).
    Euler yard is Present only; these sit on a Held tab so matching does
    not treat them as available stock.
    """
    rows = []
    seen_labels = set()
    for status in HELD_INVENTORY_STATUSES:
        label = _held_status_label(status)
        if label in seen_labels:
            continue
        try:
            chunk = fetch_inventory_by_status(token, status, limit=limit)
        except CoulsonError as e:
            log.info("Coulson %s inventory skipped: %s", status, e)
            continue
        if not chunk:
            continue
        seen_labels.add(label)
        _merge_vehicle_rows(rows, chunk, label)
    return rows


def _invoice_status(row) -> str:
    return str(
        (row or {}).get("status")
        or (row or {}).get("invoice_status")
        or (row or {}).get("invoiceStatus")
        or ""
    ).strip().upper()


def _is_cancelled_invoice(row) -> bool:
    return _invoice_status(row) in _CANCELLED_INVOICE


def _live_invoices(rows):
    """Keep Created invoices. Cancelled stay in a side list for delink."""
    return [r for r in (rows or []) if not _is_cancelled_invoice(r)]


def _cancelled_invoices(rows):
    return [r for r in (rows or []) if _is_cancelled_invoice(r)]


def cancelled_chassis_set(rows):
    """Chassis whose Vehicle Invoice List row is Cancelled — even if Sold still shows them."""
    out = set()
    for r in rows or []:
        ch = _vehicle_key(r)
        if ch:
            out.add(ch)
    return out


def _invoice_row_key(v):
    """Invoice list can have Created + Cancelled rows for different chassis of one customer."""
    if not isinstance(v, dict):
        return ""
    return (
        str(v.get("invoice_number") or v.get("invoiceNumber") or "").strip().upper()
        or _vehicle_key(v)
        or str(v.get("id") or "")
    )


def _page_dealer_invoices(token: str, *, limit=INVENTORY_PAGE, max_rows=None):
    """Page GET dealer/invoice/vehicle the way the Coulson SPA does.

    Their Vehicle Invoices table sends offset as the 0-based *page index*
    (page 0, 1, 2…) with limit = page size, sorted by invoice_creation_ts
    DESC. Older inventory endpoints used row-skip offsets; if page 1 looks
    like a 1-row slide of page 0 we switch to row skip so we still drain
    the full 234-row month.

    Returns (rows, complete). complete is False when max_rows stopped us
    before extras.total_count, so callers must not wipe older cancelled
    invoices.
    """
    def pull(offset):
        payload = get_json(token, INVOICE_LIST_PATH, {
            "limit": str(limit),
            "offset": str(offset),
            "sort": json.dumps(["invoice_creation_ts", "DESC"]),
        })
        chunk = payload.get("data") or []
        if not isinstance(chunk, list):
            chunk = []
        extras = payload.get("extras") or {}
        total = None
        got = extras.get("total_count")
        if got is not None:
            try:
                total = int(got)
            except (TypeError, ValueError):
                total = None
        return chunk, total

    rows, seen = [], set()

    def take(chunk):
        added = 0
        for v in chunk:
            if not isinstance(v, dict):
                continue
            key = _invoice_row_key(v)
            if not key or key in seen:
                continue
            seen.add(key)
            rows.append(v)
            added += 1
        return added

    cap = INVENTORY_MAX_ROWS
    if max_rows is not None:
        try:
            cap = max(1, min(int(max_rows), INVENTORY_MAX_ROWS))
        except (TypeError, ValueError):
            cap = INVENTORY_MAX_ROWS

    def finished(complete_chunk=False):
        if total is not None and len(rows) >= total:
            return True, True
        if len(rows) >= cap:
            return True, bool(total is not None and len(rows) >= total)
        if complete_chunk:
            return True, True
        return False, False

    first, total = pull(0)
    take(first)
    stop, complete = finished(complete_chunk=bool(not first or len(first) < limit))
    if stop:
        return rows, complete

    probe, _ = pull(1)
    probe_new = take(probe)
    stop, complete = finished()
    if stop:
        return rows, complete
    # Page-index returns a mostly-new page. Row-skip offset=1 returns the
    # same window shifted by one row (one new chassis, the rest duplicates).
    page_index = bool(probe) and probe_new > (len(probe) / 2)
    if page_index:
        page = 2
        while True:
            stop, complete = finished()
            if stop:
                return rows, complete
            chunk, _ = pull(page)
            if not chunk:
                return rows, True
            added = take(chunk)
            if len(chunk) < limit or added == 0:
                return rows, True
            page += 1

    # Probe was a 1-row shift — API is row-skip. Re-pull from offset=limit.
    rows, seen = [], set()
    take(first)
    offset = limit
    while True:
        stop, complete = finished()
        if stop:
            return rows, complete
        chunk, _ = pull(offset)
        if not chunk:
            return rows, True
        added = take(chunk)
        if len(chunk) < limit or added == 0:
            return rows, True
        offset += limit


def fetch_raw_vehicle_invoices(token: str, limit=INVENTORY_PAGE, max_rows=None):
    """Every Vehicle Invoice List row — Created and Cancelled.

    Coulson Vehicle Inventory → ⋮ menu → Invoice List. Status filter is
    Created / Cancelled. Unfiltered list is ~all dealer invoices.

    Returns (rows, ok). ok is False when every path 404'd / failed, or when
    max_rows stopped a DESC page early, so callers must not wipe older
    cancelled invoices.
    """
    last_error = None
    try:
        return _page_dealer_invoices(token, limit=limit, max_rows=max_rows)
    except CoulsonError as e:
        last_error = e
        if e.status not in (404, 405, 400):
            log.info("Coulson %s failed: %s", INVOICE_LIST_PATH, e)
            return [], False

    for path in VEHICLE_INVOICE_PATHS:
        if path == INVOICE_LIST_PATH:
            continue
        for sort in _INVOICE_SORTS:
            try:
                chunk = _page_rows(token, path, {"sort": sort}, limit=limit)
            except CoulsonError as e:
                last_error = e
                if e.status in (404, 405, 400):
                    break
                log.info("Coulson vehicle invoices %s failed: %s", path, e)
                break
            if chunk:
                return chunk, True
    if last_error and last_error.status not in (404, 405, 400):
        log.info("Coulson vehicle invoices empty: %s", last_error)
    return [], False


def fetch_vehicle_invoices(token: str, limit=INVENTORY_PAGE, max_rows=None):
    """Live (Created) invoices only — billed today even when Sold is yesterday.

    The returned list is one row per chassis (latest Created invoice wins).
    `.invoices` keeps every Created row, including an older bill on a chassis
    that was rebilled, so persistence is not limited to the chassis merge.
    """
    chunk, ok = fetch_raw_vehicle_invoices(token, limit=limit, max_rows=max_rows)
    live_rows = [r for r in _live_invoices(chunk) if isinstance(r, dict)]
    live = _SoldPull(_merge_vehicle_rows([], live_rows, "INVOICED"))
    live.cancelled = tuple(_cancelled_invoices(chunk))
    live.invoice_list_ok = ok
    live.invoices = tuple(dict(r) for r in live_rows)
    return live


class _SoldPull(list):
    """List of Sold/invoice rows plus whether Invoice List + Sold fully paged."""
    complete = True
    cancelled = ()
    invoice_list_ok = False
    invoices = ()


_MODEL_COPY_KEYS = (
    "model", "variant", "sap_vehicle_model_id", "sap_product_name",
    "model_registered_name", "updated_load_body", "load_body_assembly",
    "octopus_model", "octopus_variant", "load_body",
)


def fetch_vehicle_by_chassis(token: str, chassis: str):
    """One vehicle-inventory/transfer row for a chassis, any status.

    Vehicle Invoices (`dealer/invoice/vehicle`) do not send model/variant.
    The Sold / Present transfer row still has them after billing.
    """
    ch = str(chassis or "").strip()
    if not ch:
        return None
    want = ch.replace(" ", "").upper()
    attempts = (
        {"view_type": "table", "chassis": ch, "limit": "5", "offset": "0"},
        {"view_type": "table", "vehicle_status": "SOLD", "chassis": ch,
         "limit": "5", "offset": "0"},
        {"view_type": "table", "vehicle_status": "PRESENT", "chassis": ch,
         "limit": "5", "offset": "0"},
    )
    for params in attempts:
        try:
            payload = get_json(token, "vehicle-inventory/transfer", params)
        except CoulsonError:
            continue
        data = payload.get("data") or []
        if not isinstance(data, list):
            continue
        for row in data:
            if not isinstance(row, dict):
                continue
            got = str(row.get("chassis") or row.get("chassis_number")
                      or row.get("chassisNumber") or "").replace(" ", "").upper()
            if got == want:
                return row
    return None


def _copy_model_fields(dst, src):
    if not isinstance(dst, dict) or not isinstance(src, dict):
        return
    for key in _MODEL_COPY_KEYS:
        if src.get(key) not in (None, "") and dst.get(key) in (None, ""):
            dst[key] = src.get(key)
    for nested_key in ("vehicle", "sap_vehicle_model", "sapVehicleModel"):
        nested = src.get(nested_key)
        if isinstance(nested, dict):
            _copy_model_fields(dst, nested)


def fill_missing_sold_models(token: str, rows, *, limit=40):
    """Copy model/variant onto Vehicle Invoice rows that arrived without them."""
    filled = 0
    for row in rows or []:
        if filled >= limit:
            break
        if not isinstance(row, dict):
            continue
        if row.get("model") or row.get("sap_vehicle_model_id") or row.get("sap_product_name"):
            continue
        extra = fetch_vehicle_by_chassis(
            token, row.get("chassis") or row.get("chassis_number") or "")
        if not extra:
            continue
        _copy_model_fields(row, extra)
        filled += 1
    return filled


def fetch_sold_inventory(token: str, limit=INVENTORY_PAGE, *,
                         fill_models=True, invoice_max_rows=None):
    """Billed vehicles — Invoice List first, then Sold tab, minus Cancelled.

    Vehicle Inventory → ⋮ → Invoice List (`GET dealer/invoice/vehicle`) is
    the dealer-visible billed source (Created rows). The Sold tab often
    lags that list and still shows a chassis after its tax invoice is
    Cancelled. Invoice dates/customer win; Sold only fills model and the
    dealer inbound (`sap_invoice_date`) used for the received ledger.

    A failed Invoice List pull must not wipe older oem_sold rows.

    invoice_max_rows caps the DESC invoice list (newest first) so an
    interactive OEM Billing tap does not page years of invoices past the
    HTTP timeout. fill_models=False skips the per-chassis model lookup.
    """
    rows = _SoldPull()
    errors = []
    sold_complete = True
    cancelled = []
    invoice_list_ok = False
    created_invoices = []
    try:
        invoices = fetch_vehicle_invoices(token, limit=limit, max_rows=invoice_max_rows)
        cancelled = list(getattr(invoices, "cancelled", ()) or ())
        invoice_list_ok = bool(getattr(invoices, "invoice_list_ok", False))
        # Raw Created rows, captured before the chassis merge inside
        # fetch_vehicle_invoices. Copying `invoices` itself drops every
        # extra bill when one chassis was invoiced twice.
        created_invoices = [
            dict(r) for r in (getattr(invoices, "invoices", ()) or ())
            if isinstance(r, dict)
        ]
        _merge_vehicle_rows(rows, invoices, "INVOICED")
    except CoulsonError as e:
        log.info("Coulson vehicle invoices skipped: %s", e)
        errors.append(e)
    for status in SOLD_INVENTORY_STATUSES:
        meta = {}
        try:
            chunk = fetch_inventory_by_status(token, status, limit=limit, meta=meta)
        except CoulsonError as e:
            log.info("Coulson %s inventory skipped: %s", status, e)
            errors.append(e)
            sold_complete = False
            continue
        _merge_vehicle_rows(rows, chunk, status)
        if meta.get("complete") is False:
            sold_complete = False
    drop = cancelled_chassis_set(cancelled)
    if drop:
        kept = [r for r in rows if _vehicle_key(r) not in drop]
        rows.clear()
        rows.extend(kept)
    if fill_models:
        try:
            fill_missing_sold_models(token, rows)
        except CoulsonError as e:
            log.info("Coulson chassis model fill skipped: %s", e)
        except Exception:
            log.exception("Coulson chassis model fill failed")
    if not rows and errors:
        raise errors[0]
    # Wipe oem_sold only when Invoice List fully paged. Sold-tab-only
    # completeness used to drop today's Created invoices after a 404/timeout.
    rows.complete = bool(sold_complete and invoice_list_ok)
    rows.cancelled = tuple(cancelled)
    rows.invoice_list_ok = invoice_list_ok
    rows.invoices = tuple(_enrich_invoice_rows(created_invoices, rows))
    return rows


def _enrich_invoice_rows(invoices, merged):
    """Copy model / dealer inbound date from the Sold+Invoice merge onto each list row."""
    by_key = {}
    for row in merged or []:
        key = _vehicle_key(row)
        if key:
            by_key[key] = row
    out = []
    for inv in invoices or []:
        if not isinstance(inv, dict):
            continue
        row = dict(inv)
        hit = by_key.get(_vehicle_key(row))
        if hit:
            _copy_model_fields(row, hit)
            for k in ("sap_invoice_date", "sap_invoice_number", "delivery_date",
                      "model", "variant"):
                if hit.get(k) not in (None, "") and row.get(k) in (None, ""):
                    row[k] = hit[k]
        out.append(row)
    return out


# ---------------------------------------------------------------- claim settlements
# Coulson calls a claim a DEBIT NOTE. Their "Claim Settlements List" is one row per
# debit note; the money detail — chassis, source invoice, claim type — lives only on
# that note's line items, which arrive from a second call.
CLAIM_LIST_PATH = "debit-note"
# The dealer SPA (getDebitNoteDetails) calls this — not a bare `journey` path.
# Hitting /api/v1/journey left every OEM Claim Settlements row with empty line
# items, so Chassis / Invoice stayed "Not pulled" after a successful list sync.
# Claim Item Docs (`line_items[].documents[]`, shown as "N Docs") also live only
# on this journey. Uploads go to POST debit-note/line-item-documents and reappear
# here after the SPA invalidates debitNoteDetails.
CLAIM_JOURNEY_PATH = "debit-note/journey"

# Line-item lists hide under several names depending on which envelope we got.
_LINE_ITEM_KEYS = (
    "line_items", "lineItems", "items", "debit_note_items", "debitNoteItems",
    "claim_items", "claimItems", "debit_note_line_items",
)


def pick_line_items(blob):
    """First non-empty list of dicts that looks like debit-note lines."""
    if not isinstance(blob, dict):
        return []
    for key in _LINE_ITEM_KEYS:
        val = blob.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    header = blob.get("header") if isinstance(blob.get("header"), dict) else {}
    for key in _LINE_ITEM_KEYS:
        val = header.get(key)
        if isinstance(val, list) and val and isinstance(val[0], dict):
            return val
    return []


def journey_has_vehicle_lines(blob):
    """True when at least one line carries a chassis or a source invoice."""
    for item in pick_line_items(blob):
        if (item.get("chassis") or item.get("chassis_number") or item.get("chassisNumber")
                or item.get("chassis_no") or item.get("chassisNo")
                or item.get("vehicles") or item.get("linked_vehicles")
                or item.get("linked_vehicle_ids") or item.get("linkedVehicleIds")
                or item.get("vehicle_ids") or item.get("vehicleIds")
                or item.get("vehicle_id") or item.get("vehicleId")
                or item.get("source_invoice_number") or item.get("sourceInvoiceNumber")
                or item.get("source_invoice") or item.get("invoice_number")):
            return True
        desc = f"{item.get('description') or ''} {item.get('claim_type') or ''}"
        if "MD9" in desc.upper() or "AF-" in desc.upper():
            return True
    return False


def journey_body(payload):
    """Unwrap Coulson's journey envelope to `{header, line_items, timeline}`.

    Live captures used `{success, data: {header, line_items, timeline}}`. Production
    has also answered with a double `data`, with `data` as the line-item list, and
    with the lines hanging off `debit_note`. Returning `{}` for any of those left
    every OEM Claim Settlements row with a blank Chassis / Invoice column.
    """
    if not isinstance(payload, dict):
        return {}
    candidates = [payload]
    data = payload.get("data")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return {
            "line_items": data,
            "header": payload.get("header") if isinstance(payload.get("header"), dict) else {},
            "timeline": payload.get("timeline") if isinstance(payload.get("timeline"), dict) else {},
        }
    if isinstance(data, dict):
        candidates.append(data)
        nested = data.get("data")
        if isinstance(nested, dict):
            candidates.append(nested)
        elif isinstance(nested, list) and nested and isinstance(nested[0], dict):
            return {
                "line_items": nested,
                "header": data.get("header") if isinstance(data.get("header"), dict) else {},
                "timeline": data.get("timeline") if isinstance(data.get("timeline"), dict) else {},
            }
        for key in ("debit_note", "debitNote", "claim", "journey"):
            inner = data.get(key)
            if isinstance(inner, dict):
                candidates.append(inner)
    for blob in candidates:
        lines = pick_line_items(blob)
        if not lines:
            continue
        out = dict(blob)
        out["line_items"] = lines
        if not isinstance(out.get("timeline"), dict):
            for other in candidates:
                if isinstance(other.get("timeline"), dict):
                    out["timeline"] = other["timeline"]
                    break
        if not isinstance(out.get("header"), dict):
            for other in candidates:
                if isinstance(other.get("header"), dict):
                    out["header"] = other["header"]
                    break
        return out
    if isinstance(data, dict):
        return data
    return payload


def fetch_claim_journey(token: str, debit_note_id: str):
    """One claim in full: {header, line_items[], timeline{}}.

    Chassis and source invoice exist ONLY on the line items. The list row has
    neither, so a claim cannot be tied to a lead without this call (or without
    line items already on the list row).

    The live portal asks `GET debit-note/journey?debit_note_id=<uuid>` and unwraps
    `{success, data: {header, line_items, timeline}}`. Older guesses (`journey`,
    `debit-note/<id>`) stay as fallbacks so a renamed route does not blank the
    column again.
    """
    note_id = str(debit_note_id or "").strip()
    if not note_id:
        raise CoulsonError("A debit note id is required")
    attempts = (
        (CLAIM_JOURNEY_PATH, {"debit_note_id": note_id}),
        ("journey", {"debit_note_id": note_id}),
        ("journey", {"id": note_id}),
        (f"debit-note/{note_id}", None),
    )
    last = {}
    last_keys = []
    for path, params in attempts:
        try:
            payload = get_json(token, path, params)
        except CoulsonError:
            continue
        body = journey_body(payload)
        last = body
        last_keys = list(body)[:12] if isinstance(body, dict) else []
        if pick_line_items(body):
            return body
    if last_keys:
        log.info("Coulson journey %s returned no line items (keys=%s)", note_id, last_keys)
    return last

# Status values the Claim Settlements List tabs across, approval order first
# and terminal states last. Used to sweep per-status when one unfiltered pull
# comes back short of the true total.
#
# Oct 2026 Coulson SPA `Jgo` filter: Dealer Development is only a *label*;
# the posted value is **Expansion Team Approval Pending**. Bill Posted in SAP
# is on the filter. Sales Invoice Generation Pending dropped from the filter;
# keep it so older notes still get swept.
CLAIM_STATUSES = (
    "RM Approval Pending",
    "Dealer Development Department Approval Pending",
    "Expansion Team Approval Pending",
    "Sales Department Approval Pending",
    "Finance Department Approval Pending",
    "Credit Note Generation Pending",
    "Sales Invoice Generation Pending",
    "Bill Posted in SAP",
    "Credit Note Generated",
    "Sales Invoice Generated",
    "Settled",
    "Rejected",
    "Cancelled",
)


def fetch_debit_notes(token: str, *, status: str = "", limit=100, max_rows=INVENTORY_MAX_ROWS):
    """Page through the Claim Settlements List. Returns (rows, total_count).

    Same envelope as vehicle-inventory/transfer — {success, data[], extras.total_count}
    — so the paging is the same shape as the yard pull.

    `status` is best-effort. Their UI filters by status, but we never saw the parameter
    name, so an unknown one may simply be ignored and return the unfiltered page. The
    caller de-duplicates by id, which makes a wrong guess cost a wasted call rather than
    a wrong mirror.
    """
    params = {"status": status} if status else {}
    meta = {}
    rows = _page_rows(token, CLAIM_LIST_PATH, params, limit=limit, max_rows=max_rows, meta=meta)
    return rows, meta.get("total")


def fetch_allowed_showrooms(token: str):
    payload = get_json(token, "allowed-showrooms")
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


CLAIM_STATUS_COUNT_PATHS = (
    "claim-analytics/status-counts",
    "status-counts",
)


def fetch_claim_status_counts(token: str, showroom_id: str = ""):
    """Tab numbers, already aggregated by Coulson — one call, no paging.

    Oct 2026 SPA reads `claim-analytics/status-counts`. Older `status-counts`
    stays as fallback so a renamed route does not make the sweep think the
    unfiltered list was complete.
    """
    params = {}
    if str(showroom_id or "").strip():
        params["showroom_id"] = str(showroom_id).strip()
    last = None
    for path in CLAIM_STATUS_COUNT_PATHS:
        try:
            payload = get_json(token, path, params or None)
        except CoulsonError as e:
            last = e
            if e.status in (404, 405, 400):
                continue
            raise
        data = payload.get("data")
        if isinstance(data, (dict, list)) and data:
            return data
    if last and last.status not in (404, 405, 400):
        raise last
    return {}


def diagnose(username: str, password: str) -> dict:
    """Attempt one login and report exactly what was sent and what came back.

    "Username/password is not valid" is what Coulson says for a wrong password,
    a wrong app segment, and a request that arrived without credentials at all.
    Those need completely different fixes, and nothing in the app distinguished
    them. This does — without ever revealing the password: only its length and
    whether it had surrounding whitespace, which is what tells a paste artefact
    apart from a genuinely wrong secret.

    ONE attempt, never a retry loop: repeated failures on a real portal lock the
    account out.
    """
    raw_user, raw_pw = str(username or ""), str(password or "")
    user, pw = clean_credential(raw_user), clean_credential(raw_pw)
    out = {
        "authUrl": f"{auth_url()}/login",
        "apiUrl": api_url(),
        "appSegment": app_name(),
        "encoding": "base64(username:password:appSegment)",
        "usernameSent": user,
        "usernameHadWhitespace": raw_user != user,
        "passwordLength": len(pw),
        "passwordHadWhitespace": raw_pw != pw,
        "ok": False,
        "status": None,
        "coulsonSaid": "",
        "hint": "",
    }
    if not user or not pw:
        out["hint"] = "Type both the username and the password, then try again."
        return out
    try:
        login(user, pw)
        out["ok"] = True
        out["hint"] = "Euler accepted this login."
        return out
    except CoulsonError as e:
        out["status"] = e.status
        out["coulsonSaid"] = str(e)
        out["hint"] = _diagnose_hint(out)
        return out


def _diagnose_hint(d: dict) -> str:
    said = str(d.get("coulsonSaid") or "").lower()
    if "redirected" in said:
        return ("The auth URL is not the final one. Set COULSON_AUTH_URL to the address "
                "the redirect points at — credentials are dropped across a redirect.")
    if "unreachable" in said or d.get("status") is None:
        return ("The server could not reach Euler at all. This is a network or DNS "
                "problem, not a password problem.")
    if d.get("passwordHadWhitespace"):
        return ("The password had a space or newline around it, which has now been "
                "trimmed. If it still fails, the secret itself is wrong.")
    # Euler returns HTTP 203 (not 401) with success:false for a bad login.
    if d.get("status") in (203, 401, 403) or "not valid" in said:
        return (f"Euler refused this password from our server. The username reached it as "
                f"'{d.get('usernameSent')}' with a {d.get('passwordLength')}-character "
                f"password. If the same Username and Password work in a private window on "
                f"coulson.eulerlogistics.com, Euler is blocking the login unless it comes from "
                f"their own site — a Railway variable will not change that. Sign in on Coulson, "
                f"then paste the session (localStorage key coulson_auth) in Settings.")
    if d.get("status") == 404:
        return ("That login path does not exist on Euler's side. Check COULSON_AUTH_URL.")
    return "Euler refused the login. The message above is theirs, verbatim."
