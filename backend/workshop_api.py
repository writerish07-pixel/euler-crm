"""Workshop Desk routes on the sales API. State lives in the same Mongo database."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

import coulson as coulson_client
import workshop_desk as desk
import workshop_gmail as gmail
_LIST = {"view_type": "table", "sort": '["id","DESC"]', "limit": "100"}


def thread_needs_fetch(message_id, thread_id, known_ids, seen):
    """A later reply in a thread already read still has to be fetched.

    Skip a message only when that exact Gmail id is already stored, or when
    this pull has already opened the thread.
    """
    if message_id and message_id in (known_ids or set()):
        return False
    if thread_id and thread_id in (seen or set()):
        return False
    return True


class MailIn(BaseModel):
    subject: str = ""
    body: str = ""
    direction: str = "Received from the company"


class FileIn(BaseModel):
    requestNo: str = ""


class ServiceLoginIn(BaseModel):
    username: str = ""
    password: str = ""


class GrantIn(BaseModel):
    areas: list = []
    password: str = ""


class GmailIn(BaseModel):
    clientId: str = ""
    clientSecret: str = ""


class GmailFinishIn(BaseModel):
    code: str = ""
    state: str = ""
    redirectUri: str = ""


def _now():
    return datetime.now(timezone.utc).isoformat()


def _mask(username, owner):
    username = str(username or "").strip()
    if owner:
        return username
    if len(username) <= 2:
        return ""
    return username[0] + ("•" * (len(username) - 2)) + username[-1]


async def load_state(db):
    doc = await db.workshop_desk.find_one({"_id": "desk"})
    if not doc:
        return desk.empty_state()
    doc.pop("_id", None)
    state = desk.empty_state()
    state.update({k: doc.get(k, state[k]) for k in state})
    state["lines"] = list(doc.get("lines") or [])
    state["mails"] = list(doc.get("mails") or [])
    state["advances"] = dict(doc.get("advances") or {})
    state["proofs"] = list(doc.get("proofs") or [])
    return state


async def save_state(db, state):
    await db.workshop_desk.replace_one({"_id": "desk"}, {**state, "_id": "desk"}, upsert=True)
    return state


async def _service_doc(db):
    return await db.system.find_one({"_id": "service_coulson"}) or {}


async def service_login_view(db, user):
    doc = await _service_doc(db)
    username = (doc.get("username") or os.environ.get("SERVICE_COULSON_USERNAME") or "").strip()
    password = doc.get("password") or os.environ.get("SERVICE_COULSON_PASSWORD") or ""
    owner = str((user or {}).get("role") or "") == "owner"
    return {
        "configured": bool(username and password),
        "username": _mask(username, owner),
    }


async def _service_secret(db):
    doc = await _service_doc(db)
    username = (doc.get("username") or os.environ.get("SERVICE_COULSON_USERNAME") or "").strip()
    password = doc.get("password") or os.environ.get("SERVICE_COULSON_PASSWORD") or ""
    return username, password


def _rows(payload):
    if not isinstance(payload, dict):
        return []
    data = payload.get("data")
    return data if isinstance(data, list) else []


def _one(payload):
    data = (payload or {}).get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return data[0] if data and isinstance(data[0], dict) else {}
    return data if isinstance(data, dict) else {}


def _pages(token, path, extra=None, pages=3):
    rows = []
    for offset in range(pages):
        params = dict(_LIST)
        params["offset"] = str(offset)
        if extra:
            params.update(extra)
        chunk = _rows(coulson_client.get_json(token, path, params, timeout=40))
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < 100:
            break
    return rows


def pull_service(username, password):
    """Sign in with the service login id and password, then read the portal."""
    token = coulson_client.login_service(username, password)
    stores = _rows(coulson_client.get_json(token, "store/allowed", dict(_LIST), timeout=30))
    if not stores:
        raise coulson_client.CoulsonError("This service login has no store.")
    store_id = str((stores[0] or {}).get("id") or "")
    store_rows = _rows(coulson_client.get_json(
        token, "intelligent-inventory/store-view", {"store_id": store_id}, timeout=40,
    ))
    stale_rows = _pages(token, "intelligent-inventory/stale-open-requests", {"store_id": store_id})
    claim_rows = _pages(token, "inbound-warranty-claim", pages=1)
    claim_analytics = _one(coulson_client.get_json(token, "inbound-warranty-claim/analytics", timeout=30))
    due_rows = _pages(token, "vehicle-scheduled-service", pages=2)
    complaint_rows = _pages(token, "complaint", pages=1)
    ticket_rows = _pages(token, "inbound-ticket/view", pages=1)
    snapshot = desk.snapshot_from_coulson(
        store_rows, stale_rows, claim_rows, claim_analytics, due_rows, complaint_rows, ticket_rows,
    )
    summary = _one(coulson_client.get_json(token, "inbound-ticket/analytics-summary", timeout=30))
    try:
        live_open = int(summary.get("in_progress_count") or 0)
    except (TypeError, ValueError):
        live_open = 0
    if live_open > snapshot["jobs"]["inProgress"]:
        snapshot["jobs"]["inProgress"] = live_open
    return snapshot


async def _create_staff_login(db, staff, password):
    """Owner gives a staff member their first login from the service desk."""
    import uuid
    import auth as authmod

    password = str(password or "").strip()
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="A new login needs a password of at least 6 characters.")
    email = str(staff.get("email") or "").strip().lower()
    login_id = email.split("@", 1)[0] if "@" in email else ""
    if not login_id:
        login_id = "".join(ch for ch in str(staff.get("name") or "").lower() if ch.isalnum())[:20]
    if not login_id:
        raise HTTPException(status_code=400, detail="This staff row needs a name or an email before a login can be created.")
    norm = authmod.norm_login_id(login_id)
    if await db.users.find_one({"loginIdNorm": norm}):
        raise HTTPException(status_code=409, detail="A login with that user ID already exists. Save the access without a new password.")
    if email and await db.users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="A login with that email already exists. Save the access without a new password.")
    role = str(staff.get("role") or "executive")
    if role not in authmod.ALLOWED_ROLES or role == "owner":
        role = "executive"
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "userId": user_id,
        "email": authmod._stored_email(email, login_id, user_id),
        "loginId": login_id,
        "loginIdNorm": norm,
        "passwordHash": authmod.hash_password(password),
        "passwordPlain": password,
        "name": staff.get("name") or "",
        "role": role,
        "createdAt": _now(),
    })
    return user_id


def register(api, db, current_user):
    async def access_for(user):
        grants = await db.workshop_access.find({}, {"_id": 0}).to_list(300)
        return desk.resolve_access(user, grants)

    async def workshop_user(user=Depends(current_user)):
        access = await access_for(user)
        if not access.get("owner") and not access.get("areas"):
            raise HTTPException(
                status_code=403,
                detail="Service is opened by the owner. Ask the owner to add you from the staff list.",
            )
        user = dict(user)
        user["serviceAccess"] = access
        return user

    def _owner(user):
        if not (user.get("serviceAccess") or {}).get("owner"):
            raise HTTPException(status_code=403, detail="Only the owner can do this on the service desk.")

    def _need(user, *areas):
        access = user.get("serviceAccess") or {}
        if access.get("owner"):
            return
        have = set(access.get("areas") or [])
        if not any(area in have for area in areas):
            raise HTTPException(status_code=403, detail="The owner has not opened this part of Service for you.")

    async def _gmail_doc():
        return await db.system.find_one({"_id": "workshop_gmail"}) or {}

    async def _gmail_secret():
        doc = await _gmail_doc()
        return {
            "clientId": (doc.get("clientId") or os.environ.get("GMAIL_CLIENT_ID") or "").strip(),
            "clientSecret": doc.get("clientSecret") or os.environ.get("GMAIL_CLIENT_SECRET") or "",
            "refreshToken": doc.get("refreshToken") or os.environ.get("GMAIL_REFRESH_TOKEN") or "",
            "email": doc.get("email") or "",
            "state": doc.get("state") or "",
        }

    def _gmail_public(secret, owner):
        client_id = secret.get("clientId") or ""
        shown = client_id if owner else ""
        if shown and len(shown) > 8:
            shown = shown[:4] + "…" + shown[-4:]
        return {
            "connected": bool(secret.get("refreshToken")),
            "email": secret.get("email") or "",
            "clientSaved": bool(secret.get("clientId") and secret.get("clientSecret")),
            "clientId": shown,
        }

    async def view(user):
        state = await load_state(db)
        access = user.get("serviceAccess") or {}
        secret = await _gmail_secret()
        return desk.public_view(
            state,
            await service_login_view(db, user),
            access,
            _gmail_public(secret, bool(access.get("owner"))),
            actor=user,
        )

    async def _token():
        secret = await _gmail_secret()
        if not secret["clientId"] or not secret["clientSecret"] or not secret["refreshToken"]:
            raise gmail.GmailError("Connect Gmail on the owner desk first.")
        return await asyncio.to_thread(
            gmail.access_token, secret["clientId"], secret["clientSecret"], secret["refreshToken"],
        )

    async def _post_mail(state, mail_id):
        mail = next((item for item in state["mails"] if item.get("id") == mail_id), None)
        if not mail:
            return state, "That payment is not on the desk."
        if mail.get("posted"):
            return state, ""
        if not mail.get("replyTo") or not mail.get("gmailThreadId"):
            return state, "This ticket has no company mail on the desk yet. Pull the mailbox, then post again."
        file_doc = await db.workshop_files.find_one({"_id": mail.get("fileId")}) or {}
        try:
            token = await _token()
            sent = await asyncio.to_thread(
                gmail.send_reply,
                token,
                to=mail.get("replyTo") or "",
                subject=mail.get("subject") or "",
                body=mail.get("body") or "",
                thread_id=mail.get("gmailThreadId") or "",
                in_reply_to=mail.get("rfcMessageId") or "",
                filename=file_doc.get("filename") or "payment-proof",
                data=bytes(file_doc.get("data") or b""),
                content_type=file_doc.get("contentType") or "application/octet-stream",
            )
        except gmail.GmailError as exc:
            return state, str(exc)
        return desk.mark_posted(state, mail_id, sent.get("id") or ""), ""

    @api.get("/workshop")
    async def workshop_get(user=Depends(workshop_user)):
        return await view(user)

    @api.post("/workshop/sample")
    async def workshop_sample(user=Depends(workshop_user)):
        _owner(user)
        current = await load_state(db)
        if desk.desk_has_work(current):
            raise HTTPException(
                status_code=409,
                detail="The desk already has workshop work. Load this morning only fills an empty desk.",
            )
        sample = desk.sample_state()
        sample["syncedAt"] = current.get("syncedAt") or ""
        await save_state(db, sample)
        return await view(user)

    @api.post("/workshop/mails")
    async def workshop_add_mail(body: MailIn, user=Depends(workshop_user)):
        _need(user, "mail")
        if not str(body.body or "").strip() and not str(body.subject or "").strip():
            raise HTTPException(status_code=400, detail="Paste the mail first.")
        state = await load_state(db)
        state, _mail_id = desk.add_mail(state, body.subject, body.body, body.direction)
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/mails/{mail_id}/read")
    async def workshop_read(mail_id: str, user=Depends(workshop_user)):
        _need(user, "mail")
        state = await load_state(db)
        try:
            state = desk.read_mail(state, mail_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That mail is not on the desk.")
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/mails/{mail_id}/file")
    async def workshop_file(mail_id: str, body: FileIn, user=Depends(workshop_user)):
        _need(user, "mail")
        state = await load_state(db)
        try:
            state = desk.file_mail(state, mail_id, body.requestNo)
        except KeyError:
            raise HTTPException(status_code=404, detail="That mail is not on the desk.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/lines/{line_id}/reorder")
    async def workshop_reorder(line_id: str, user=Depends(workshop_user)):
        _need(user, "buy")
        state = await load_state(db)
        try:
            state = desk.approve_reorder(state, line_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That part is not on the desk.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/lines/{line_id}/receive")
    async def workshop_receive(line_id: str, user=Depends(workshop_user)):
        _need(user, "buy")
        state = await load_state(db)
        try:
            state = desk.receive_line(state, line_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That part is not on the desk.")
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await save_state(db, state)
        return await view(user)

    @api.put("/workshop/service-login")
    async def workshop_save_login(body: ServiceLoginIn, user=Depends(workshop_user)):
        if str(user.get("role") or "") != "owner":
            raise HTTPException(status_code=403, detail="Only the owner can save the service login.")
        username = str(body.username or "").strip()
        if not username:
            raise HTTPException(status_code=400, detail="Enter the service Coulson login id.")
        existing = await _service_doc(db)
        password = body.password if body.password not in (None, "") else (existing.get("password") or "")
        if not password and not os.environ.get("SERVICE_COULSON_PASSWORD"):
            raise HTTPException(status_code=400, detail="Enter the service Coulson password.")
        await db.system.update_one(
            {"_id": "service_coulson"},
            {
                "$set": {"username": username, "password": password, "updatedAt": _now()},
                "$unset": {"sessionToken": "", "sessionExpiresAt": ""},
            },
            upsert=True,
        )
        return await view(user)

    @api.post("/workshop/sync")
    async def workshop_sync(user=Depends(workshop_user)):
        _owner(user)
        username, password = await _service_secret(db)
        if not username or not password:
            raise HTTPException(
                status_code=400,
                detail="Save the service Coulson login on Rules, then sync.",
            )
        try:
            snapshot = await asyncio.wait_for(
                asyncio.to_thread(pull_service, username, password),
                timeout=90,
            )
        except coulson_client.CoulsonError as exc:
            state = await load_state(db)
            state["syncError"] = str(exc)
            await save_state(db, state)
            raise HTTPException(status_code=400, detail=str(exc))
        except asyncio.TimeoutError:
            raise HTTPException(status_code=504, detail="Service Coulson took too long. Try the sync again.")
        state = desk.merge_snapshot(await load_state(db), snapshot)
        state["syncedAt"] = _now()
        state["syncError"] = ""
        await save_state(db, state)
        return await view(user)

    @api.get("/workshop/people")
    async def workshop_people(user=Depends(workshop_user)):
        _owner(user)
        staff = await db.staff.find({"status": {"$ne": "Inactive"}}).sort("name", 1).to_list(500)
        grants = {
            row.get("staffId"): row
            for row in await db.workshop_access.find().to_list(300)
        }
        users = await db.users.find({}, {"name": 1, "email": 1, "userId": 1}).to_list(300)
        return {
            "areas": [{"id": key, "label": label} for key, label in desk.SERVICE_AREAS],
            "people": [desk.people_row(row, grants.get(row.get("staffId")), users) for row in staff],
        }

    @api.put("/workshop/people/{staff_id}")
    async def workshop_grant(staff_id: str, body: GrantIn, user=Depends(workshop_user)):
        _owner(user)
        staff = await db.staff.find_one({"staffId": staff_id})
        if not staff:
            raise HTTPException(status_code=404, detail="That person is not on the staff list.")
        areas = desk.clean_areas(body.areas)
        if not areas:
            raise HTTPException(status_code=400, detail="Choose at least one part of Service.")
        users = await db.users.find({}, {"name": 1, "email": 1, "userId": 1}).to_list(300)
        row = desk.people_row(staff, None, users)
        user_id = row.get("userId") or ""
        if not user_id and str(body.password or "").strip():
            user_id = await _create_staff_login(db, staff, body.password)
        await db.workshop_access.replace_one(
            {"_id": staff_id},
            {
                "_id": staff_id,
                "staffId": staff_id,
                "name": staff.get("name") or "",
                "email": staff.get("email") or "",
                "role": staff.get("role") or "",
                "userId": user_id,
                "areas": areas,
                "updatedAt": _now(),
            },
            upsert=True,
        )
        return await workshop_people(user)

    @api.delete("/workshop/people/{staff_id}")
    async def workshop_revoke(staff_id: str, user=Depends(workshop_user)):
        _owner(user)
        await db.workshop_access.delete_one({"_id": staff_id})
        return await workshop_people(user)

    @api.put("/workshop/gmail")
    async def workshop_gmail_save(body: GmailIn, user=Depends(workshop_user)):
        _owner(user)
        client_id = str(body.clientId or "").strip()
        if not client_id:
            raise HTTPException(status_code=400, detail="Enter the Gmail client id.")
        existing = await _gmail_doc()
        secret = body.clientSecret if body.clientSecret not in (None, "") else (existing.get("clientSecret") or "")
        if not secret and not os.environ.get("GMAIL_CLIENT_SECRET"):
            raise HTTPException(status_code=400, detail="Enter the Gmail client secret.")
        await db.system.update_one(
            {"_id": "workshop_gmail"},
            {"$set": {"clientId": client_id, "clientSecret": secret, "updatedAt": _now()}},
            upsert=True,
        )
        return await view(user)

    @api.post("/workshop/gmail/start")
    async def workshop_gmail_start(body: GmailFinishIn, user=Depends(workshop_user)):
        _owner(user)
        secret = await _gmail_secret()
        if not secret["clientId"] or not secret["clientSecret"]:
            raise HTTPException(status_code=400, detail="Save the Gmail client on Rules first.")
        redirect = str(body.redirectUri or "").strip()
        if not redirect:
            raise HTTPException(status_code=400, detail="The browser did not say where to return.")
        state = os.urandom(16).hex()
        await db.system.update_one(
            {"_id": "workshop_gmail"},
            {"$set": {"state": state, "redirectUri": redirect}},
            upsert=True,
        )
        return {"url": gmail.auth_url(secret["clientId"], redirect, state)}

    @api.post("/workshop/gmail/finish")
    async def workshop_gmail_finish(body: GmailFinishIn, user=Depends(workshop_user)):
        _owner(user)
        secret = await _gmail_secret()
        if not body.code or not body.state or body.state != secret.get("state"):
            raise HTTPException(status_code=400, detail="This Gmail connection did not start on the service desk.")
        try:
            tokens = await asyncio.to_thread(
                gmail.exchange_code, secret["clientId"], secret["clientSecret"], body.code, body.redirectUri,
            )
            email = await asyncio.to_thread(gmail.profile_email, tokens["access_token"])
        except gmail.GmailError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await db.system.update_one(
            {"_id": "workshop_gmail"},
            {"$set": {"refreshToken": tokens["refresh_token"], "email": email, "connectedAt": _now(), "state": ""}},
        )
        return await view(user)

    @api.post("/workshop/gmail/pull")
    async def workshop_gmail_pull(user=Depends(workshop_user)):
        _need(user, "mail")
        try:
            token = await _token()
        except gmail.GmailError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        state = await load_state(db)
        mailbox = (await _gmail_secret()).get("email") or ""
        known = {mail.get("gmailId") for mail in state["mails"] if mail.get("gmailId")}
        seen = set()
        added = 0
        targets = desk.request_ids(state) or [""]
        for target in targets:
            has_pi = desk.request_has_pi(state, target)
            senders_known = desk.request_senders_known(state, target)
            query = (
                f'"{target}" newer_than:365d -from:github.com -from:notifications.github.com'
                if target else
                'newer_than:21d (ticket OR request) -from:github.com -from:notifications.github.com'
            )
            try:
                ids = await asyncio.to_thread(gmail.list_message_ids, token, query, 8 if target else 20)
            except gmail.GmailError:
                continue
            for message_id in ids:
                try:
                    head = await asyncio.to_thread(gmail.get_message, token, message_id, False)
                except gmail.GmailError:
                    continue
                thread_id = head.get("threadId") or ""
                if thread_id and thread_id in seen:
                    continue
                if message_id in known and has_pi and senders_known:
                    continue
                if thread_id:
                    seen.add(thread_id)
                try:
                    messages = await asyncio.to_thread(gmail.get_thread, token, thread_id) if thread_id else [head]
                except gmail.GmailError:
                    messages = [head]
                usable = []
                for message in messages:
                    if "github.com" in str(message.get("fromEmail") or message.get("replyTo") or "").lower():
                        continue
                    usable.append(message)
                touched = set()
                for message in usable:
                    body = "\n".join([
                        message.get("body") or "",
                        gmail.html_to_text(message.get("html") or ""),
                    ]).strip()
                    documents = [
                        {"name": doc.get("name") or "document", "kind": doc.get("kind") or "file", "text": doc.get("text") or ""}
                        for doc in (message.get("documents") or [])
                    ]
                    bits = [message.get("subject") or "", body]
                    for doc in documents:
                        bits.append(f"Attachment: {doc.get('name') or ''}")
                        bits.append(doc.get("text") or "")
                    request_no = desk.request_for_mail(target, "\n".join(bits))
                    if not request_no:
                        continue
                    existing = next((mail for mail in state["mails"] if mail.get("gmailId") == message.get("id")), None)
                    if existing:
                        mail = existing
                    else:
                        state, mail_id = desk.add_mail(
                            state, message.get("subject"), body or message.get("subject"),
                            meta={
                                "gmailId": message.get("id"),
                                "gmailThreadId": thread_id,
                                "replyTo": message.get("replyTo"),
                                "rfcMessageId": message.get("rfcMessageId"),
                            },
                        )
                        mail = next(item for item in state["mails"] if item.get("id") == mail_id)
                        added += 1
                    mail["body"] = body or mail.get("body") or ""
                    mail["documents"] = documents
                    mail["requestNo"] = request_no
                    mail["examined"] = True
                    if thread_id:
                        mail["gmailThreadId"] = thread_id
                    desk.remember_sender(mail, message, mailbox)
                    known.add(message.get("id"))
                    touched.add(request_no)
                for request_no in touched:
                    state = desk.apply_request_trail(state, request_no)
        for request_no in desk.request_ids(state):
            state = desk.apply_request_trail(state, request_no)
        state, dropped = desk.drop_unmatched_gmail(state)
        await save_state(db, state)
        payload = await view(user)
        payload["pulled"] = added
        payload["dropped"] = dropped
        return payload

    @api.post("/workshop/payments")
    async def workshop_payment(
        requestNo: str = Form(...),
        utr: str = Form(...),
        amount: str = Form(""),
        file: UploadFile = File(...),
        user=Depends(workshop_user),
    ):
        _need(user, "payments")
        if not (user.get("serviceAccess") or {}).get("owner") and not desk.sender_can_post_payment(user.get("name"), user.get("email")):
            raise HTTPException(
                status_code=403,
                detail="Only f.manager@akarfourwheel.com, Rishab Akar, or Euler Akar can post a payment proof.",
            )
        data = await file.read()
        if not data:
            raise HTTPException(status_code=400, detail="Attach the payment proof.")
        if len(data) > 8 * 1024 * 1024:
            raise HTTPException(status_code=413, detail="Payment proof must be under 8 MB.")
        content_type = str(file.content_type or "").split(";")[0].strip().lower()
        if content_type not in (
            "image/jpeg", "image/png", "image/webp", "application/pdf",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "text/plain", "text/csv",
        ):
            raise HTTPException(status_code=422, detail="Payment proof should be a photo, a PDF, a Word file, or a spreadsheet.")
        filename = os.path.basename(str(file.filename or "payment-proof")) or "payment-proof"
        read_text = gmail.attachment_text(filename, content_type, data)
        parsed = desk.parse_mail(filename, read_text)
        if not str(amount or "").strip() and parsed.get("amount") is not None:
            amount = str(parsed["amount"])
        if not re.sub(r"\s+", "", str(utr or "")) and parsed.get("utr"):
            utr = parsed["utr"]
        file_id = os.urandom(8).hex()
        state = await load_state(db)
        try:
            state, mail_id = desk.record_payment(state, requestNo, utr, amount, filename, file_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        await db.workshop_files.replace_one(
            {"_id": file_id},
            {
                "_id": file_id,
                "requestNo": str(requestNo).strip(),
                "filename": filename,
                "contentType": content_type,
                "data": data,
                "createdAt": _now(),
            },
            upsert=True,
        )
        state, post_error = await _post_mail(state, mail_id)
        await save_state(db, state)
        payload = await view(user)
        payload["posted"] = not post_error
        payload["postError"] = post_error
        return payload

    @api.post("/workshop/payments/{mail_id}/post")
    async def workshop_payment_post(mail_id: str, user=Depends(workshop_user)):
        _need(user, "payments")
        state = await load_state(db)
        state, post_error = await _post_mail(state, mail_id)
        await save_state(db, state)
        if post_error:
            raise HTTPException(status_code=400, detail=post_error)
        return await view(user)
