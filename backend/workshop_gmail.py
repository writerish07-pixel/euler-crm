"""Gmail for the service desk. Read the mailbox and reply on a request's thread.

Tokens and client secrets stay with the caller. This module only talks to Google.
"""
from __future__ import annotations

import base64
import re
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlencode

import httpx

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
GMAIL = "https://gmail.googleapis.com/gmail/v1/users/me"
SCOPE = "https://www.googleapis.com/auth/gmail.modify"


class GmailError(Exception):
    pass


def auth_url(client_id, redirect_uri, state):
    query = urlencode({
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": SCOPE,
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
    })
    return f"{AUTH_URL}?{query}"


def _post_token(data):
    try:
        response = httpx.post(TOKEN_URL, data=data, timeout=30)
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail refused the connection. Check the client and connect again.")
    body = response.json() if response.content else {}
    token = str((body or {}).get("access_token") or "")
    if not token:
        raise GmailError("Gmail did not return a token.")
    return body


def exchange_code(client_id, client_secret, code, redirect_uri):
    body = _post_token({
        "client_id": client_id,
        "client_secret": client_secret,
        "code": code,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    })
    refresh = str(body.get("refresh_token") or "")
    if not refresh:
        raise GmailError("Gmail did not return a refresh token. Connect again and allow offline access.")
    return {"refresh_token": refresh, "access_token": body.get("access_token") or ""}


def access_token(client_id, client_secret, refresh_token):
    body = _post_token({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    })
    return body["access_token"]


def _headers(token):
    return {"Authorization": f"Bearer {token}"}


def profile_email(token):
    try:
        response = httpx.get(f"{GMAIL}/profile", headers=_headers(token), timeout=30)
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail did not open the mailbox.")
    return str((response.json() or {}).get("emailAddress") or "")


def list_message_ids(token, query="newer_than:21d", limit=30):
    try:
        response = httpx.get(
            f"{GMAIL}/messages",
            headers=_headers(token),
            params={"q": query, "maxResults": str(limit)},
            timeout=40,
        )
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail did not list the mailbox.")
    rows = (response.json() or {}).get("messages") or []
    return [str(row.get("id")) for row in rows if row.get("id")]


def _decode(data):
    if not data:
        return ""
    pad = "=" * (-len(data) % 4)
    try:
        return base64.urlsafe_b64decode(data + pad).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _plain_parts(payload):
    if not isinstance(payload, dict):
        return
    mime = str(payload.get("mimeType") or "")
    data = ((payload.get("body") or {}).get("data")) or ""
    if data and mime.startswith("text/plain"):
        yield _decode(data)
    for part in payload.get("parts") or []:
        yield from _plain_parts(part)


def _header(headers, name):
    for row in headers or []:
        if str(row.get("name") or "").lower() == name.lower():
            return str(row.get("value") or "")
    return ""


def get_message(token, message_id):
    try:
        response = httpx.get(
            f"{GMAIL}/messages/{message_id}",
            headers=_headers(token),
            params={"format": "full"},
            timeout=40,
        )
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail did not open that message.")
    body = response.json() or {}
    payload = body.get("payload") or {}
    headers = payload.get("headers") or []
    text = "\n".join(part for part in _plain_parts(payload) if part).strip()
    if not text:
        text = _decode((payload.get("body") or {}).get("data") or "")
    return {
        "id": str(body.get("id") or message_id),
        "threadId": str(body.get("threadId") or ""),
        "subject": _header(headers, "Subject"),
        "body": text,
        "replyTo": _address(_header(headers, "From")),
        "rfcMessageId": _header(headers, "Message-ID") or _header(headers, "Message-Id"),
    }


def _address(value):
    match = re.search(r"<([^>]+)>", value or "")
    if match:
        return match.group(1).strip()
    return str(value or "").strip()


def build_raw(to, subject, body, *, in_reply_to="", filename="", data=b"", content_type="application/octet-stream"):
    message = MIMEMultipart()
    message["To"] = to
    message["Subject"] = subject
    if in_reply_to:
        message["In-Reply-To"] = in_reply_to
        message["References"] = in_reply_to
    message.attach(MIMEText(body or "", "plain", "utf-8"))
    if data:
        main, _, sub = (content_type or "application/octet-stream").partition("/")
        part = MIMEBase(main or "application", sub or "octet-stream")
        part.set_payload(data)
        encoders.encode_base64(part)
        safe = re.sub(r"[^A-Za-z0-9._-]+", "_", filename or "payment-proof")
        part.add_header("Content-Disposition", f'attachment; filename="{safe}"')
        message.attach(part)
    return base64.urlsafe_b64encode(message.as_bytes()).decode()


def send_reply(token, *, to, subject, body, thread_id, in_reply_to="", filename="", data=b"", content_type="application/octet-stream"):
    if not to or not thread_id:
        raise GmailError("This ticket has no company mail to reply on yet.")
    raw = build_raw(
        to, subject, body, in_reply_to=in_reply_to,
        filename=filename, data=data, content_type=content_type,
    )
    try:
        response = httpx.post(
            f"{GMAIL}/messages/send",
            headers={**_headers(token), "Content-Type": "application/json"},
            json={"raw": raw, "threadId": thread_id},
            timeout=40,
        )
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail did not accept the reply.")
    sent = response.json() or {}
    return {"id": str(sent.get("id") or ""), "threadId": str(sent.get("threadId") or thread_id)}
