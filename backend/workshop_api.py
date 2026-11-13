"""Workshop Desk routes on the sales API. State lives in the same Mongo database."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import coulson as coulson_client
import workshop_desk as desk

WORKSHOP_ROLES = {"owner", "sales_gm", "tl"}
_LIST = {"view_type": "table", "sort": '["id","DESC"]', "limit": "100"}


class MailIn(BaseModel):
    subject: str = ""
    body: str = ""
    direction: str = "Received from the company"


class FileIn(BaseModel):
    requestNo: str = ""


class ServiceLoginIn(BaseModel):
    username: str = ""
    password: str = ""


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


def register(api, db, current_user):
    async def workshop_user(user=Depends(current_user)):
        role = str((user or {}).get("role") or "").strip().lower()
        if role not in WORKSHOP_ROLES:
            raise HTTPException(status_code=403, detail="Workshop Desk is for the owner, sales GM, and showroom admin.")
        return user

    async def view(user):
        state = await load_state(db)
        return desk.public_view(state, await service_login_view(db, user))

    @api.get("/workshop")
    async def workshop_get(user=Depends(workshop_user)):
        return await view(user)

    @api.post("/workshop/sample")
    async def workshop_sample(user=Depends(workshop_user)):
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
        if not str(body.body or "").strip() and not str(body.subject or "").strip():
            raise HTTPException(status_code=400, detail="Paste the mail first.")
        state = await load_state(db)
        state, _mail_id = desk.add_mail(state, body.subject, body.body, body.direction)
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/mails/{mail_id}/read")
    async def workshop_read(mail_id: str, user=Depends(workshop_user)):
        state = await load_state(db)
        try:
            state = desk.read_mail(state, mail_id)
        except KeyError:
            raise HTTPException(status_code=404, detail="That mail is not on the desk.")
        await save_state(db, state)
        return await view(user)

    @api.post("/workshop/mails/{mail_id}/file")
    async def workshop_file(mail_id: str, body: FileIn, user=Depends(workshop_user)):
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
            raise HTTPException(status_code=400, detail="Enter the service Coulson username.")
        existing = await _service_doc(db)
        password = body.password if body.password not in (None, "") else (existing.get("password") or "")
        if not password and not os.environ.get("SERVICE_COULSON_PASSWORD"):
            raise HTTPException(status_code=400, detail="Enter the service Coulson password.")
        await db.system.update_one(
            {"_id": "service_coulson"},
            {"$set": {"username": username, "password": password, "updatedAt": _now()}},
            upsert=True,
        )
        return await view(user)

    @api.post("/workshop/sync")
    async def workshop_sync(user=Depends(workshop_user)):
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
