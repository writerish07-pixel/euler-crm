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
import urllib.error
import urllib.parse
import urllib.request
from typing import Optional

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


def login(username: str, password: str) -> str:
    username, password = clean_credential(username), clean_credential(password)
    if not username or not password:
        raise CoulsonError("Coulson username and password are required")
    basic = basic_auth_value(username, password)
    status, payload = _request(
        f"{auth_url()}/login",
        method="POST",
        headers={"Authorization": f"Basic {basic}"},
        follow_redirects=False,
    )
    if not payload.get("success"):
        raise CoulsonError(payload.get("message") or "Coulson login failed", status=status)
    token = ((payload.get("data") or {}) or {}).get("token") or ""
    if not token:
        raise CoulsonError("Coulson login returned no token", status=status)
    return token


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


def fetch_present_inventory(token: str, limit=200):
    """Yard stock currently PRESENT at the logged-in dealer."""
    offset = 0
    rows = []
    total = None
    while True:
        payload = get_json(token, "vehicle-inventory/transfer", {
            "view_type": "table",
            "sort": json.dumps(["created_at", "DESC"]),
            "limit": str(limit),
            "offset": str(offset),
            "vehicle_status": "PRESENT",
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
    if d.get("status") in (401, 403):
        return (f"Euler rejected the credentials as sent. The username reached it as "
                f"'{d.get('usernameSent')}' with a {d.get('passwordLength')}-character "
                f"password, encoded as {d.get('encoding')} with app segment "
                f"'{d.get('appSegment')}'. If that username and password work in the "
                f"browser at coulson.eulerlogistics.com, the app segment is the thing "
                f"that differs — set COULSON_APP_NAME to whatever their login page uses.")
    if d.get("status") == 404:
        return ("That login path does not exist on Euler's side. Check COULSON_AUTH_URL.")
    return "Euler refused the login. The message above is theirs, verbatim."
