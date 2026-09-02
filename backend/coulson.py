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
TIMEOUT = 25


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


def _request(url, method="GET", headers=None, body=None, follow_redirects=True):
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
    try:
        with opener(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
            status = getattr(resp, "status", 200)
    except urllib.error.HTTPError as e:
        raw = e.read() if e.fp else b""
        raise CoulsonError(_message_from_body(raw) or e.reason or str(e), status=e.code) from e
    except urllib.error.URLError as e:
        raise CoulsonError(f"Coulson unreachable: {e.reason}") from e
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
        with httpx.Client(timeout=TIMEOUT, follow_redirects=False) as client:
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


def fetch_inventory_by_status(token: str, vehicle_status: str, limit=200):
    """Paginated vehicle-inventory/transfer for one Coulson vehicle_status."""
    offset = 0
    rows = []
    total = None
    status = str(vehicle_status or "").strip() or "PRESENT"
    while True:
        payload = get_json(token, "vehicle-inventory/transfer", {
            "view_type": "table",
            "sort": json.dumps(["created_at", "DESC"]),
            "limit": str(limit),
            "offset": str(offset),
            "vehicle_status": status,
        })
        chunk = payload.get("data") or []
        if not isinstance(chunk, list):
            chunk = []
        rows.extend(chunk)
        extras = payload.get("extras") or {}
        total = extras.get("total_count", total)
        if not chunk or (total is not None and len(rows) >= int(total)) or len(chunk) < limit:
            break
        offset += limit
        if offset > 5000:
            break
    return rows


def fetch_present_inventory(token: str, limit=200):
    """Yard stock currently PRESENT at the logged-in dealer."""
    return fetch_inventory_by_status(token, "PRESENT", limit=limit)


# Billed vehicles leave PRESENT immediately. The dealer Sold tab is the same
# inventory API with vehicle_status=SOLD (Coulson SPA: Present / In Transit / Sold).
SOLD_INVENTORY_STATUSES = ("SOLD",)


def fetch_sold_inventory(token: str, limit=200):
    """Vehicles billed / sold at this dealer — no longer in the yard list."""
    rows = []
    seen = set()
    for status in SOLD_INVENTORY_STATUSES:
        try:
            chunk = fetch_inventory_by_status(token, status, limit=limit)
        except CoulsonError as e:
            log.info("Coulson %s inventory skipped: %s", status, e)
            continue
        for v in chunk or []:
            if not isinstance(v, dict):
                continue
            key = (
                str(v.get("chassis") or v.get("chassis_number") or "").strip().upper()
                or str(v.get("id") or v.get("vehicle_id") or "")
            )
            if not key or key in seen:
                continue
            seen.add(key)
            row = dict(v)
            row["_coulsonStatus"] = status
            rows.append(row)
    return rows


# ---------------------------------------------------------------- claim settlements
# Coulson calls a claim a DEBIT NOTE. Their "Claim Settlements List" is one row per
# debit note; the money detail — chassis, source invoice, claim type — lives only on
# that note's line items, which arrive from a second call.
CLAIM_LIST_PATH = "debit-note"
CLAIM_JOURNEY_PATH = "journey"

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
    """
    note_id = str(debit_note_id or "").strip()
    if not note_id:
        raise CoulsonError("A debit note id is required")
    attempts = (
        (CLAIM_JOURNEY_PATH, {"debit_note_id": note_id}),
        (CLAIM_JOURNEY_PATH, {"id": note_id}),
        (f"debit-note/{note_id}", None),
    )
    last = {}
    for path, params in attempts:
        try:
            payload = get_json(token, path, params)
        except CoulsonError:
            continue
        body = journey_body(payload)
        last = body
        if pick_line_items(body):
            return body
    return last

# The eleven buckets the Claim Settlements List tabs across, approval order first
# and terminal states last. Used to sweep per-status when one unfiltered pull comes
# back short of the true total.
CLAIM_STATUSES = (
    "RM Approval Pending",
    "Dealer Development Department Approval Pending",
    "Sales Department Approval Pending",
    "Finance Department Approval Pending",
    "Credit Note Generation Pending",
    "Sales Invoice Generation Pending",
    "Credit Note Generated",
    "Sales Invoice Generated",
    "Settled",
    "Rejected",
    "Cancelled",
)


def fetch_debit_notes(token: str, *, status: str = "", limit=100, max_rows=5000):
    """Page through the Claim Settlements List. Returns (rows, total_count).

    Same envelope as vehicle-inventory/transfer — {success, data[], extras.total_count}
    — so the paging is the same shape as the yard pull.

    `status` is best-effort. Their UI filters by status, but we never saw the parameter
    name, so an unknown one may simply be ignored and return the unfiltered page. The
    caller de-duplicates by id, which makes a wrong guess cost a wasted call rather than
    a wrong mirror.
    """
    offset = 0
    rows, total = [], None
    while True:
        params = {"limit": str(limit), "offset": str(offset)}
        if status:
            params["status"] = status
        payload = get_json(token, CLAIM_LIST_PATH, params)
        chunk = payload.get("data") or []
        if not isinstance(chunk, list):
            chunk = []
        rows.extend(r for r in chunk if isinstance(r, dict))
        got = (payload.get("extras") or {}).get("total_count")
        if got is not None:
            try:
                total = int(got)
            except (TypeError, ValueError):
                pass
        if not chunk or len(chunk) < limit:
            break
        if total is not None and len(rows) >= total:
            break
        offset += limit
        if offset >= max_rows:
            break
    return rows, total


def fetch_allowed_showrooms(token: str):
    payload = get_json(token, "allowed-showrooms")
    data = payload.get("data") or []
    return data if isinstance(data, list) else []


def fetch_claim_status_counts(token: str, showroom_id: str = ""):
    """The eleven tab numbers, already aggregated by Coulson — one call, no paging.

    Their own Claim Settlements List header is built from this, so it is the cheapest
    honest answer to "how many claims exist", and the yardstick a full sweep is checked
    against.
    """
    params = {}
    if str(showroom_id or "").strip():
        params["showroom_id"] = str(showroom_id).strip()
    payload = get_json(token, "status-counts", params or None)
    data = payload.get("data")
    return data if isinstance(data, (dict, list)) else {}


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
