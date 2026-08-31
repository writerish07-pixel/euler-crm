"""Coulson (Euler OEM portal) HTTP client.

Login is Basic auth against euler-auth: base64(username:password:coulson),
then Bearer JWT on coulson.eulerlogistics.com. Credentials come from env
(COULSON_USERNAME / COULSON_PASSWORD) or owner Settings (Mongo). Never log
the password.
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


def _request(url, method="GET", headers=None, body=None):
    hdrs = {"Accept": "application/json", "User-Agent": "EulerCRM/coulson-sync"}
    if headers:
        hdrs.update(headers)
    data = body if body is None or isinstance(body, (bytes, bytearray)) else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
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
    if not username or not password:
        raise CoulsonError("Coulson username and password are required")
    token_src = f"{username}:{password}:{_env('COULSON_APP_NAME', APP_NAME)}"
    basic = base64.b64encode(token_src.encode("utf-8")).decode("ascii")
    status, payload = _request(
        f"{auth_url()}/login",
        method="POST",
        headers={"Authorization": f"Basic {basic}"},
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
