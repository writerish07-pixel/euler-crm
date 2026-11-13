"""Gmail for the service desk. Read the mailbox and reply on a request's thread.

Tokens and client secrets stay with the caller. This module only talks to Google.
"""
from __future__ import annotations

import base64
import os
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


def _walk(payload):
    if not isinstance(payload, dict):
        return
    yield payload
    for part in payload.get("parts") or []:
        yield from _walk(part)


def html_to_text(html):
    raw = str(html or "")
    raw = re.sub(r"(?is)<(script|style)\b.*?>.*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>", "\n", raw)
    raw = re.sub(r"(?i)</(p|div|tr|h\d|li)>", "\n", raw)
    raw = re.sub(r"(?i)</td>", " ", raw)
    raw = re.sub(r"(?s)<[^>]+>", " ", raw)
    raw = raw.replace("&nbsp;", " ").replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    raw = re.sub(r"[ \t]+\n", "\n", raw)
    raw = re.sub(r"\n{3,}", "\n\n", raw)
    return raw.strip()


def pdf_text(data):
    if not data:
        return ""
    try:
        import io
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages).strip()
    except Exception:
        return ""


def image_text(data):
    """Read a screenshot when the tesseract program is installed."""
    if not data:
        return ""
    import shutil
    import subprocess
    import tempfile
    if not shutil.which("tesseract"):
        return ""
    path = ""
    try:
        import io
        from PIL import Image
        image = Image.open(io.BytesIO(data))
        handle = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        path = handle.name
        handle.close()
        image.save(path, format="PNG")
        done = subprocess.run(
            ["tesseract", path, "stdout"],
            capture_output=True, timeout=25, check=False,
        )
        return (done.stdout or b"").decode("utf-8", errors="replace").strip()
    except Exception:
        return ""
    finally:
        if path:
            try:
                os.remove(path)
            except OSError:
                pass


def attachment_text(filename, mime, data):
    mime = str(mime or "").lower()
    name = str(filename or "")
    if mime == "application/pdf" or name.lower().endswith(".pdf"):
        return pdf_text(data)
    if mime.startswith("text/") or name.lower().endswith((".txt", ".csv", ".htm", ".html")):
        if mime == "text/html" or name.lower().endswith((".htm", ".html")):
            try:
                return html_to_text(data.decode("utf-8", errors="replace"))
            except Exception:
                return ""
        try:
            return data.decode("utf-8", errors="replace").strip()
        except Exception:
            return ""
    if mime.startswith("image/") or name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".gif")):
        return image_text(data)
    return ""


def _plain_parts(payload):
    for part in _walk(payload):
        mime = str(part.get("mimeType") or "")
        data = ((part.get("body") or {}).get("data")) or ""
        if data and mime.startswith("text/plain"):
            yield _decode(data)


def _header(headers, name):
    for row in headers or []:
        if str(row.get("name") or "").lower() == name.lower():
            return str(row.get("value") or "")
    return ""


def _attachment_bytes(token, message_id, part):
    body = part.get("body") or {}
    encoded = body.get("data") or ""
    if encoded:
        pad = "=" * (-len(encoded) % 4)
        try:
            return base64.urlsafe_b64decode(encoded + pad)
        except Exception:
            return b""
    attachment_id = str(body.get("attachmentId") or "")
    if not token or not attachment_id:
        return b""
    try:
        response = httpx.get(
            f"{GMAIL}/messages/{message_id}/attachments/{attachment_id}",
            headers=_headers(token),
            timeout=40,
        )
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        return b""
    raw = str((response.json() or {}).get("data") or "")
    pad = "=" * (-len(raw) % 4)
    try:
        return base64.urlsafe_b64decode(raw + pad)
    except Exception:
        return b""


def _message_view(token, body, *, read_files=False):
    payload = body.get("payload") or {}
    headers = payload.get("headers") or []
    message_id = str(body.get("id") or "")
    plain = "\n".join(part for part in _plain_parts(payload) if part).strip()
    html = []
    documents = []
    for part in _walk(payload):
        mime = str(part.get("mimeType") or "").lower()
        filename = str(part.get("filename") or "")
        encoded = ((part.get("body") or {}).get("data")) or ""
        if mime == "text/html" and encoded and not filename:
            html.append(_decode(encoded))
            continue
        if not read_files:
            continue
        if not filename and not mime.startswith("image/") and mime != "application/pdf":
            continue
        if filename and mime.startswith("text/") and not filename.lower().endswith((".pdf", ".png", ".jpg", ".jpeg", ".webp", ".htm", ".html")):
            continue
        data = _attachment_bytes(token, message_id, part)
        if not data or len(data) > 8 * 1024 * 1024:
            continue
        text = attachment_text(filename or mime, mime, data)
        documents.append({
            "name": filename or mime,
            "kind": "pdf" if "pdf" in mime or filename.lower().endswith(".pdf") else (
                "image" if mime.startswith("image/") else "file"
            ),
            "text": (text or "")[:20000],
        })
    if not plain:
        plain = html_to_text("\n".join(html))
    from_name, from_email = _name_and_address(_header(headers, "From"))
    sent_at = str(body.get("internalDate") or "").strip()
    return {
        "id": message_id,
        "threadId": str(body.get("threadId") or ""),
        "subject": _header(headers, "Subject"),
        "body": plain,
        "html": "\n".join(html),
        "documents": documents,
        "fromName": from_name,
        "fromEmail": from_email,
        "toPeople": _people(_header(headers, "To")),
        "sentAt": sent_at if sent_at.isdigit() else "",
        "replyTo": from_email,
        "rfcMessageId": _header(headers, "Message-ID") or _header(headers, "Message-Id"),
    }


def get_message(token, message_id, read_files=True):
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
    return _message_view(token, response.json() or {}, read_files=read_files)


def get_thread(token, thread_id):
    try:
        response = httpx.get(
            f"{GMAIL}/threads/{thread_id}",
            headers=_headers(token),
            params={"format": "full"},
            timeout=40,
        )
    except httpx.HTTPError as exc:
        raise GmailError("Could not reach Gmail.") from exc
    if response.status_code >= 400:
        raise GmailError("Gmail did not open that mail trail.")
    rows = (response.json() or {}).get("messages") or []
    return [_message_view(token, row, read_files=True) for row in rows[:20]]


def _name_and_address(value):
    raw = str(value or "").strip()
    match = re.search(r"^(.*)<([^>]+)>", raw)
    if match:
        name = match.group(1).strip().strip('"').strip()
        return name, match.group(2).strip().lower()
    if "@" in raw:
        return "", raw.strip().lower()
    return raw, ""


def _people(value):
    people = []
    seen = set()
    pattern = re.compile(
        r'(?:"([^"]+)"|([^<",]+))?\s*<([^>]+)>|([A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,})',
        re.I,
    )
    for match in pattern.finditer(str(value or "")):
        name = (match.group(1) or match.group(2) or "").strip().strip('"')
        email = (match.group(3) or match.group(4) or "").strip().lower()
        if not email or email in seen:
            continue
        seen.add(email)
        people.append({"name": name, "email": email})
    return people


def _address(value):
    _name, email = _name_and_address(value)
    return email or str(value or "").strip()


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
