"""BotSpace WhatsApp — additive, never blocks booking / delivery / payments.

Euler-only: inbound chats are attached only when the phone matches a CRM lead.
Tata (or any other) BotSpace contacts are ignored.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from datetime import datetime, date, timedelta, timezone
from typing import Optional

logger = logging.getLogger("euler.botspace")

IST = timezone(timedelta(hours=5, minutes=30))
SETTINGS_ID = "botspace"
BOTSPACE_BASE = "https://public-api.bot.space"

DEFAULT_TEMPLATES = {
    "followup": "lead_followup_3day",
    "booking": "booking_confirm",
    "delivery": "delivery_review",
    "finance": "finance_overdue_exec",
    # Internal daily reports (English, Utility category). Staff messages, so they
    # bypass customer quiet hours.
    "execMorning": "exec_day_ahead",
    "execEod": "exec_eod_scorecard",
    "managerEod": "manager_eod_volume",
    "ownerEod": "owner_eod_summary",
    # MARKETING category, unlike everything above it. Asks a lead with no model
    # recorded which vehicle they are interested in.
    "modelAsk": "lead_model_interest",
}

# How long before the same lead may be asked again. A marketing template resent
# every few days is what gets a number reported and a WABA quality rating cut.
MODEL_ASK_COOLOFF_DAYS = 45

# Slots the daily scheduler fires. Times are IST hours, overridable from settings.
REPORT_SLOTS = {"morning": 8, "eod": 20}

# Messages sent to our own people, not to customers. They carry no leadId, so
# they are kept out of the customer inbox — and they are the sends whose
# failures had nowhere to surface.
STAFF_KINDS = {"finance_exec", "exec_morning", "exec_eod", "manager_eod", "owner_eod"}

FOLLOWUP_STATUSES = {"new", "contacted", "follow-up", "follow up", "in progress"}
STOP_WORDS = {"stop", "unsubscribe", "रोकें", "रोक दो", "बंद"}
MAX_FINANCE_PINGS = 3
FINANCE_SLA_DAYS = 2


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> str:
    return now_ist().strftime("%Y-%m-%d")


def digits10(phone) -> str:
    d = re.sub(r"\D", "", str(phone or ""))
    if len(d) >= 10:
        return d[-10:]
    return d


def e164_in(phone) -> str:
    d = digits10(phone)
    return f"+91{d}" if len(d) == 10 else (str(phone or "").strip())


def parse_day(value) -> Optional[date]:
    raw = str(value or "")[:10]
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def days_since(created, today_s: Optional[str] = None) -> int:
    start = parse_day(created)
    end = parse_day(today_s or today_ist())
    if not start or not end:
        return -1
    return (end - start).days


def in_customer_hours(when: Optional[datetime] = None) -> bool:
    t = when or now_ist()
    return 9 <= t.hour < 20


def is_unbooked_active(lead: dict) -> bool:
    if (lead.get("accountStatus") or "Active").strip().lower() != "active":
        return False
    if lead.get("whatsappOptOut"):
        return False
    st = (lead.get("currentStatus") or "New").strip().lower()
    if st in {"lost", "cancelled", "archived", "close won", "closed"}:
        return False
    if "book" in st or "deliver" in st or "finance" in st:
        return False
    if lead.get("bookingDate") or lead.get("deliveryDate"):
        return False
    return st in FOLLOWUP_STATUSES or st == ""


def followup_anchor(lead: dict) -> str:
    """The date the 3/6/9 cycle counts from.

    Normally the lead's creation date. After a cancellation and revival it is the
    cancel date instead — otherwise a lead created ninety days ago would compute
    day 90 the moment it came back, fire once because 90 divides by 3, and then go
    silent for three days. The customer is starting over, so the clock does too.
    """
    return str(lead.get("followupAnchorDate") or lead.get("createdDate") or "")


def followup_due(lead: dict, today_s: Optional[str] = None) -> bool:
    """Day 3, 6, 9… from the follow-up anchor. Not nextFollowupDate."""
    if not is_unbooked_active(lead):
        return False
    today_s = today_s or today_ist()
    if str(lead.get("whatsappFollowupLastDate") or "")[:10] == today_s:
        return False
    n = days_since(followup_anchor(lead), today_s)
    return n >= 3 and n % 3 == 0


def inbound_is_stop(text: str) -> bool:
    t = (text or "").strip().lower()
    return t in STOP_WORDS or t.startswith("stop")


def session_open(last_inbound_at: Optional[str], now: Optional[datetime] = None) -> bool:
    if not last_inbound_at:
        return False
    try:
        ts = datetime.fromisoformat(str(last_inbound_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return (now or datetime.now(timezone.utc)) - ts <= timedelta(hours=24)


def _db():
    import server
    return server.db


def schedule(coro):
    """Fire-and-forget. Never raises into the caller (booking/delivery stay safe)."""
    async def _run():
        try:
            await coro
        except Exception:
            logger.exception("whatsapp background task failed")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        logger.warning("whatsapp: no running event loop; skipped")


async def get_config() -> dict:
    db = _db()
    doc = await db.settings.find_one({"_id": SETTINGS_ID}) or {}
    env_key = (os.environ.get("BOTSPACE_API_KEY") or "").strip()
    env_ch = (os.environ.get("BOTSPACE_CHANNEL_ID") or "").strip()
    api_key = env_key or (doc.get("apiKey") or "").strip()
    channel_id = env_ch or (doc.get("channelId") or "").strip()
    # Kill switch is env-only. A hidden Settings field used to persist enabled:false
    # whenever the form loaded before a key existed, which blocked every send while
    # the UI still said "Configured".
    enabled_env = os.environ.get("BOTSPACE_ENABLED")
    turned_on = True if enabled_env is None else enabled_env.strip().lower() not in {"0", "false", "no", "off"}
    configured = bool(api_key) and bool(channel_id)
    ready = turned_on and configured
    templates = {**DEFAULT_TEMPLATES, **(doc.get("templates") or {})}
    return {
        "apiKey": api_key,
        "channelId": channel_id,
        "reviewUrl": (os.environ.get("BOTSPACE_REVIEW_URL") or doc.get("reviewUrl") or "").strip(),
        "enabled": ready,
        "configured": configured,
        "hasKey": bool(api_key),
        "quietStart": int(doc.get("quietStart") or 9),
        "quietEnd": int(doc.get("quietEnd") or 20),
        "webhookSecret": (os.environ.get("BOTSPACE_WEBHOOK_SECRET") or doc.get("webhookSecret") or "").strip(),
        "cronToken": (os.environ.get("BOTSPACE_CRON_TOKEN") or doc.get("cronToken") or "").strip(),
        "executives": list(doc.get("executives") or []),
        "templates": templates,
        "apiKeyMasked": _mask(api_key),
    }


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "••••"
    return key[:12] + "…" + key[-4:]


def public_config(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if k != "apiKey"}
    out["webhookPath"] = "/api/integrations/botspace/webhook"
    out["templatesGuide"] = "docs/whatsapp-meta-templates.md"
    return out


async def save_config(body: dict) -> dict:
    db = _db()
    existing = await db.settings.find_one({"_id": SETTINGS_ID}) or {}
    updates = {}
    if "apiKey" in body:
        raw = str(body.get("apiKey") or "").strip()
        if raw and "…" not in raw and not raw.startswith("•"):
            updates["apiKey"] = raw
    for k in ("channelId", "reviewUrl", "webhookSecret", "cronToken"):
        if k in body:
            updates[k] = str(body.get(k) or "").strip()
    if "enabled" in body:
        # Never persist false from the Settings form (it had no visible toggle).
        # Explicit true heals a previous accidental disable.
        if body.get("enabled"):
            updates["enabled"] = True
    # Key + channel on file means WhatsApp should send.
    will_key = updates.get("apiKey") or existing.get("apiKey")
    will_ch = updates.get("channelId") if "channelId" in updates else existing.get("channelId")
    if will_key and will_ch:
        updates["enabled"] = True
    if "quietStart" in body:
        updates["quietStart"] = int(body.get("quietStart") or 9)
    if "quietEnd" in body:
        updates["quietEnd"] = int(body.get("quietEnd") or 20)
    if "executives" in body and isinstance(body.get("executives"), list):
        updates["executives"] = [
            {"name": str(x.get("name") or "").strip(), "mobile": digits10(x.get("mobile"))}
            for x in body["executives"] if str(x.get("name") or "").strip()
        ]
    if "templates" in body and isinstance(body.get("templates"), dict):
        updates["templates"] = {**DEFAULT_TEMPLATES, **{
            k: str(v).strip() for k, v in body["templates"].items() if k in DEFAULT_TEMPLATES and v
        }}
    if updates:
        updates["updatedAt"] = datetime.now(timezone.utc).isoformat()
        await db.settings.update_one({"_id": SETTINGS_ID}, {"$set": updates}, upsert=True)
    return public_config(await get_config())


async def find_euler_lead_by_phone(phone) -> Optional[dict]:
    """Only CRM leads. Unknown numbers (Tata etc.) return None."""
    d = digits10(phone)
    if len(d) != 10:
        return None
    db = _db()
    lead = await db.leads.find_one({"mobile": {"$regex": f"{d}$"}})
    if lead:
        return lead
    return await db.leads.find_one({"altMobile": {"$regex": f"{d}$"}})


def _payload_text(payload) -> str:
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload
    if not isinstance(payload, dict):
        return str(payload)
    inner = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
    for k in ("text", "title", "body", "button", "payload"):
        v = inner.get(k) if isinstance(inner, dict) else None
        if isinstance(v, str) and v.strip():
            return v.strip()
        if isinstance(v, dict) and v.get("text"):
            return str(v.get("text")).strip()
    return ""


async def _http(method: str, path: str, cfg: dict, json_body=None) -> dict:
    import httpx
    url = f"{BOTSPACE_BASE}{path}"
    params = {"apiKey": cfg["apiKey"]}
    headers = {"Content-Type": "application/json", "x-api-key": cfg["apiKey"]}
    async with httpx.AsyncClient(timeout=20.0) as client:
        r = await client.request(method, url, params=params, headers=headers, json=json_body)
    try:
        data = r.json()
    except Exception:
        data = {"raw": r.text[:500]}
    if r.status_code >= 400:
        raise RuntimeError(f"BotSpace {r.status_code}: {data}")
    return data if isinstance(data, dict) else {"data": data}


async def send_template(phone: str, template_id: str, variables: list, name: str = "") -> dict:
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured"}
    body = {
        "phone": e164_in(phone),
        "name": name or "Customer",
        "templateId": template_id,
        "variables": [str(v) for v in variables],
    }
    data = await _http("POST", f"/v1/{cfg['channelId']}/message/send-message", cfg, body)
    return {"ok": True, "data": data}


async def send_session_text(phone: str, text: str, name: str = "") -> dict:
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured"}
    body = {"phone": e164_in(phone), "name": name or "Customer", "text": text}
    data = await _http("POST", f"/v1/{cfg['channelId']}/message/send-session-message", cfg, body)
    return {"ok": True, "data": data}


async def _store_message(lead: dict, *, direction: str, kind: str, text: str,
                         phone: str, status: str, template_id: str = "",
                         provider_id: str = "", extra: Optional[dict] = None):
    db = _db()
    mid = f"WA{datetime.now(timezone.utc).strftime('%y%m%d%H%M%S')}{os.urandom(3).hex()}"
    doc = {
        "messageId": mid,
        "leadId": lead.get("leadId"),
        "customerName": lead.get("customerName"),
        "phone": digits10(phone or lead.get("mobile")),
        "direction": direction,
        "kind": kind,
        "text": text,
        "status": status,
        "templateId": template_id,
        "providerId": provider_id,
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "audience": "executive" if kind in STAFF_KINDS else "customer",
    }
    if extra:
        doc.update(extra)
    await db.whatsapp_messages.insert_one(doc)
    await _touch_thread(doc)
    if direction == "inbound":
        await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
            "whatsappLastInboundAt": doc["createdAt"], "lastUpdated": doc["createdAt"],
        }})
    return doc


async def _touch_thread(doc: dict):
    """Keep one thread row per lead, updated on every stored message.

    A stored thread rather than an aggregation over the message log: aggregation
    gets slower as the log grows, is not reliably supported by the test harness,
    and gives nowhere to keep read-state. Derived flags (unread / needsReply /
    sessionOpen) are computed at READ time so they cannot go stale.

    Staff messages (finance reminders, daily reports) are excluded — the inbox is
    customer conversations only.
    """
    lead_id = str(doc.get("leadId") or "").strip()
    if not lead_id or doc.get("audience") == "executive":
        return None
    db = _db()
    inbound = doc.get("direction") == "inbound"
    patch = {
        "leadId": lead_id,
        "customerName": doc.get("customerName") or "",
        "phone": doc.get("phone") or "",
        "lastMessageAt": doc["createdAt"],
        "lastMessageText": (doc.get("text") or "")[:280],
        "lastDirection": doc.get("direction"),
        "lastKind": doc.get("kind"),
    }
    patch["lastInboundAt" if inbound else "lastOutboundAt"] = doc["createdAt"]
    lead = await db.leads.find_one({"leadId": lead_id}) or {}
    patch["executive"] = lead.get("executive") or ""
    patch["model"] = lead.get("interestedModel") or ""
    patch["currentStatus"] = lead.get("currentStatus") or ""
    patch["optOut"] = bool(lead.get("whatsappOptOut"))
    await db.whatsapp_threads.update_one(
        {"leadId": lead_id},
        {"$set": patch,
         "$inc": {"inboundCount" if inbound else "outboundCount": 1},
         "$setOnInsert": {"lastReadAt": "", "createdAt": doc["createdAt"]}},
        upsert=True)
    return patch


async def backfill_threads() -> dict:
    """Rebuild every thread from the existing message log. Idempotent."""
    db = _db()
    await db.whatsapp_threads.delete_many({})
    rows = await db.whatsapp_messages.find().sort("createdAt", 1).to_list(20000)
    n = 0
    for doc in rows:
        if await _touch_thread(doc) is not None:
            n += 1
    return {"messages": len(rows), "threaded": n,
            "threads": await db.whatsapp_threads.count_documents({})}


async def _activity(lead: dict, discussion: str):
    try:
        import server
        act = {
            "activityId": await server.next_id("activity", "AC26"),
            "leadId": lead.get("leadId"),
            "date": today_ist(),
            "time": now_ist().strftime("%H:%M"),
            "activityType": "WhatsApp",
            "discussion": discussion,
            "executive": lead.get("executive"),
            "customerName": lead.get("customerName"),
            "mobile": lead.get("mobile"),
            "model": lead.get("interestedModel"),
        }
        await server.db.activities.insert_one(dict(act))
        await server.sheet_sync("activities", act)
    except Exception:
        logger.exception("whatsapp activity log failed for %s", lead.get("leadId"))


async def _enqueue_or_send(*, lead: dict, kind: str, phone: str, template_id: str,
                           variables: list, text: str, customer_hours: bool):
    if customer_hours and not in_customer_hours():
        db = _db()
        await db.whatsapp_outbox.insert_one({
            "leadId": lead.get("leadId"),
            "kind": kind,
            "phone": phone,
            "templateId": template_id,
            "variables": variables,
            "text": text,
            "name": lead.get("customerName") or "",
            "createdAt": datetime.now(timezone.utc).isoformat(),
            "status": "queued",
        })
        return {"ok": True, "queued": True}
    try:
        res = await send_template(phone, template_id, variables, name=lead.get("customerName") or "")
        status = "accepted" if res.get("ok") else "skipped"
        err = ""
        if not res.get("ok") and not res.get("skipped"):
            status = "failed"
            err = str(res)
        provider_id = ""
        data = res.get("data") or {}
        inner = data.get("data") if isinstance(data.get("data"), dict) else data
        if isinstance(inner, dict):
            provider_id = str(inner.get("id") or "")
        await _store_message(
            lead, direction="outbound", kind=kind, text=text, phone=phone,
            status=status, template_id=template_id, provider_id=provider_id,
            extra={"error": err} if err else None,
        )
        return res
    except Exception as e:
        logger.exception("whatsapp send failed %s %s", kind, lead.get("leadId"))
        await _store_message(
            lead, direction="outbound", kind=kind, text=text, phone=phone,
            status="failed", template_id=template_id, extra={"error": str(e)[:400]},
        )
        return {"ok": False, "error": str(e)[:400]}


def lead_is_booked(lead: dict) -> bool:
    cs = (lead.get("currentStatus") or "").strip().lower()
    if "book" in cs or cs == "delivered" or "finance" in cs:
        return True
    if str(lead.get("bookingDate") or "").strip():
        return True
    try:
        return float(lead.get("bookingAmount") or 0) > 0
    except (TypeError, ValueError):
        return False


async def notify_booking(lead_id: str, *, force: bool = False, immediate: bool = False):
    """Send booking_confirm template to a booked Euler lead.

    Auto Convert-to-Booking uses force=False, immediate=False (quiet hours + once-only).
    Manual / bulk uses immediate=True so the owner can send now.
    """
    db = _db()
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return {"ok": False, "reason": "lead-not-found"}
    if not lead_is_booked(lead):
        return {"ok": False, "reason": "not-booked"}
    if lead.get("whatsappOptOut"):
        return {"ok": False, "reason": "opted-out"}
    if lead.get("whatsappBookingSentAt") and not force:
        return {"ok": True, "skipped": True, "reason": "already-sent",
                "sentAt": lead.get("whatsappBookingSentAt")}
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured"}
    vars_ = [
        lead.get("customerName") or "ग्राहक",
        lead.get("interestedModel") or "vehicle",
        str(lead.get("bookingDate") or today_ist()),
        lead.get("executive") or "team",
    ]
    text = f"Booking confirm {lead.get('leadId')}"
    res = await _enqueue_or_send(
        lead=lead, kind="booking", phone=lead.get("mobile"),
        template_id=cfg["templates"]["booking"], variables=vars_, text=text,
        customer_hours=not immediate,
    )
    if res.get("ok"):
        await db.leads.update_one({"leadId": lead_id}, {"$set": {
            "whatsappBookingSentAt": datetime.now(timezone.utc).isoformat(),
        }})
        await _activity(lead, "WhatsApp booking confirmation sent")
    return {**res, "leadId": lead_id}


async def send_booking_confirms(*, force: bool = False, immediate: bool = True) -> dict:
    """Send booking-confirm WhatsApp to every booked Euler lead that has not had it yet."""
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured", "sent": 0}
    db = _db()
    q = {"$or": [
        {"currentStatus": {"$regex": "book|deliver|finance", "$options": "i"}},
        {"bookingDate": {"$exists": True, "$nin": [None, ""]}},
    ]}
    sent, skipped, failed = 0, 0, 0
    errors = []
    for lead in await db.leads.find(q).to_list(5000):
        if not lead_is_booked(lead):
            continue
        res = await notify_booking(lead["leadId"], force=force, immediate=immediate)
        if res.get("skipped"):
            skipped += 1
        elif res.get("ok"):
            sent += 1
        else:
            failed += 1
            if len(errors) < 20:
                errors.append({"leadId": lead.get("leadId"), "reason": res.get("reason") or res.get("error")})
    return {"ok": True, "sent": sent, "skipped": skipped, "failed": failed, "errors": errors}


def lead_is_delivered(lead: dict) -> bool:
    st = (lead.get("currentStatus") or "").strip().lower()
    ds = (lead.get("deliveryStatus") or "").strip().lower()
    return st == "delivered" or ds == "delivered"


async def notify_delivery(lead_id: str, *, force: bool = False, immediate: bool = False):
    """Send Google-review template to a delivered Euler lead.

    Auto Mark-Delivered uses force=False, immediate=False (quiet hours + once-only).
    Manual / bulk uses immediate=True so the owner can send now.
    """
    db = _db()
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return {"ok": False, "reason": "lead-not-found"}
    if not lead_is_delivered(lead):
        return {"ok": False, "reason": "not-delivered"}
    if lead.get("whatsappOptOut"):
        return {"ok": False, "reason": "opted-out"}
    if lead.get("whatsappDeliverySentAt") and not force:
        return {"ok": True, "skipped": True, "reason": "already-sent",
                "sentAt": lead.get("whatsappDeliverySentAt")}
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured"}
    vars_ = [
        lead.get("customerName") or "ग्राहक",
        lead.get("interestedModel") or "vehicle",
        str(lead.get("deliveryDate") or today_ist()),
    ]
    review = cfg.get("reviewUrl") or ""
    text = f"Delivered + Google review {lead.get('leadId')}"
    if review:
        text = f"{text} {review}"
    res = await _enqueue_or_send(
        lead=lead, kind="delivery", phone=lead.get("mobile"),
        template_id=cfg["templates"]["delivery"], variables=vars_,
        text=text, customer_hours=not immediate,
    )
    if res.get("ok"):
        await db.leads.update_one({"leadId": lead_id}, {"$set": {
            "whatsappDeliverySentAt": datetime.now(timezone.utc).isoformat(),
        }})
        await _activity(lead, "WhatsApp delivery + Google review sent")
    return {**res, "leadId": lead_id}


async def send_delivery_reviews(*, force: bool = False, immediate: bool = True) -> dict:
    """Send Google-review WhatsApp to every delivered Euler lead that has not had it yet."""
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured", "sent": 0}
    db = _db()
    q = {"$or": [
        {"currentStatus": {"$regex": "^delivered$", "$options": "i"}},
        {"deliveryStatus": {"$regex": "^delivered$", "$options": "i"}},
    ]}
    sent, skipped, failed = 0, 0, 0
    errors = []
    for lead in await db.leads.find(q).to_list(5000):
        if not lead_is_delivered(lead):
            continue
        res = await notify_delivery(lead["leadId"], force=force, immediate=immediate)
        if res.get("skipped"):
            skipped += 1
        elif res.get("ok"):
            sent += 1
        else:
            failed += 1
            if len(errors) < 20:
                errors.append({"leadId": lead.get("leadId"), "reason": res.get("reason") or res.get("error")})
    return {"ok": True, "sent": sent, "skipped": skipped, "failed": failed, "errors": errors}


async def run_unbooked_followups(today_s: Optional[str] = None) -> dict:
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "not-configured"}
    today_s = today_s or today_ist()
    db = _db()
    sent, skipped = 0, 0
    for lead in await db.leads.find({"accountStatus": {"$regex": "^active$", "$options": "i"}}).to_list(5000):
        if not followup_due(lead, today_s):
            skipped += 1
            continue
        vars_ = [
            lead.get("customerName") or "ग्राहक",
            lead.get("interestedModel") or "vehicle",
            lead.get("leadId") or "",
        ]
        res = await _enqueue_or_send(
            lead=lead, kind="followup", phone=lead.get("mobile"),
            template_id=cfg["templates"]["followup"], variables=vars_,
            text=f"3-day follow-up {lead.get('leadId')}",
            customer_hours=True,
        )
        if res.get("ok"):
            sent += 1
            await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
                "whatsappFollowupLastDate": today_s,
                "whatsappFollowupCount": int(lead.get("whatsappFollowupCount") or 0) + 1,
            }})
            await _activity(lead, "WhatsApp 3-day follow-up sent")
    return {"ok": True, "sent": sent, "considered": sent + skipped}


# ------------------------------------------------------- model-ask campaign
async def _crm_models() -> list:
    """Sellable models, from Price Master — the same list the lead form offers."""
    db = _db()
    return sorted([m for m in await db.price_master.distinct("model") if str(m or "").strip()])


def _norm_model_text(s: str) -> str:
    """Squash to bare letters+digits so 'Hi-Load', 'hi load' and 'HILOAD' all agree."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").lower())


def match_model_reply(text: str, models: list) -> Optional[str]:
    """Resolve a customer's WhatsApp reply to exactly one model, or to nothing.

    Deliberately returns None on ambiguity rather than picking a winner. A wrong
    model written into a lead is worse than an empty one: the executive stops
    asking, and the mistake is invisible until someone quotes the wrong vehicle.

    Handles a tapped quick-reply button, a menu number, the model name in any
    spacing or case, and a name embedded in a sentence.
    """
    raw = str(text or "").strip()
    if not raw or not models:
        return None
    flat = _norm_model_text(raw)
    if not flat:
        return None

    # 1. Exact name (button payloads and one-word replies land here).
    exact = [m for m in models if _norm_model_text(m) == flat]
    if len(exact) == 1:
        return exact[0]

    # 2. A bare menu number: "2", "2." or "option 2".
    num = re.fullmatch(r"(?:option\s*)?(\d{1,2})[.)]?", raw.strip().lower())
    if num:
        idx = int(num.group(1))
        if 1 <= idx <= len(models):
            return models[idx - 1]
        return None

    # 3. Name inside a sentence ("I want hi load", "hiload ka price?").
    hits = [m for m in models if _norm_model_text(m) and _norm_model_text(m) in flat]
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        # "hiload or hicity?" names two vehicles and decides nothing.
        return None

    # 4. Last resort: the reply is a prefix of exactly one model ("hi ra" -> HiRange).
    if len(flat) >= 4:
        starts = [m for m in models if _norm_model_text(m).startswith(flat)]
        if len(starts) == 1:
            return starts[0]
    return None


def model_ask_due(lead: dict, today_s: Optional[str] = None) -> bool:
    """Active lead, no model recorded, opted in, and not asked recently."""
    if not is_unbooked_active(lead):
        return False
    if str(lead.get("interestedModel") or "").strip():
        return False
    if not digits10(lead.get("mobile")):
        return False
    last = str(lead.get("modelAskSentAt") or "")[:10]
    if last:
        n = days_since(last, today_s or today_ist())
        if n < MODEL_ASK_COOLOFF_DAYS:
            return False
    return True


async def run_model_ask_campaign(*, dry_run: bool = True, limit: int = 500,
                                 today_s: Optional[str] = None) -> dict:
    """Ask leads with no recorded model which vehicle they want.

    Dry run by default. This is the one MARKETING-category send in the app, so
    the owner sees exactly who would receive it before anything leaves.
    """
    cfg = await get_config()
    if not cfg["enabled"] and not dry_run:
        return {"ok": False, "skipped": True, "reason": "whatsapp-not-configured", "sent": 0}
    today_s = today_s or today_ist()
    db = _db()
    models = await _crm_models()
    if not models:
        return {"ok": False, "reason": "no models in Price Master", "sent": 0, "targets": []}
    menu = " / ".join(f"{i + 1} {m}" for i, m in enumerate(models))

    targets, sent, queued, failed = [], 0, 0, 0
    for lead in await db.leads.find(
            {"accountStatus": {"$regex": "^active$", "$options": "i"}}).to_list(5000):
        if not model_ask_due(lead, today_s):
            continue
        targets.append({"leadId": lead.get("leadId"), "customerName": lead.get("customerName"),
                        "mobile": digits10(lead.get("mobile")),
                        "executive": lead.get("executive") or "",
                        "createdDate": lead.get("createdDate") or ""})
        if dry_run or len(targets) > limit:
            continue
        res = await _enqueue_or_send(
            lead=lead, kind="model_ask", phone=lead.get("mobile"),
            template_id=cfg["templates"].get("modelAsk", DEFAULT_TEMPLATES["modelAsk"]),
            variables=[lead.get("customerName") or "ग्राहक", menu],
            text=f"Model interest ask {lead.get('leadId')}",
            customer_hours=True,
        )
        if res.get("queued"):
            queued += 1
        elif res.get("ok"):
            sent += 1
        else:
            failed += 1
        if res.get("ok"):
            await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
                "modelAskSentAt": datetime.now(timezone.utc).isoformat(),
            }})
            await _activity(lead, "WhatsApp model-interest ask sent")

    return {"ok": True, "dryRun": dry_run, "day": today_s, "models": models, "menu": menu,
            "eligible": len(targets), "sent": sent, "queued": queued, "failed": failed,
            "targets": targets[:limit]}


async def apply_model_reply(lead: dict, text: str) -> dict:
    """Write a model onto a lead from what the customer said — or refuse to.

    Three rules, and all three exist to stop this from corrupting the register:
      - only fills a model that is currently EMPTY, never overwrites one an
        executive entered;
      - only on an unambiguous match;
      - stamps modelSource so a customer-stated model is always distinguishable
        from a staff-entered one.
    Anything else is left for a human, which is what the inbox is for.
    """
    if str(lead.get("interestedModel") or "").strip():
        return {"updated": False, "reason": "model-already-set"}
    models = await _crm_models()
    picked = match_model_reply(text, models)
    if not picked:
        return {"updated": False, "reason": "no-confident-match", "models": models}
    db = _db()
    await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
        "interestedModel": picked,
        "modelSource": "whatsapp-reply",
        "modelCapturedAt": datetime.now(timezone.utc).isoformat(),
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }})
    await _activity(lead, f"Model captured from WhatsApp reply: {picked}")
    try:
        import server
        updated = await db.leads.find_one({"leadId": lead["leadId"]})
        await server.sheet_sync("leads", server.clean(updated))
    except Exception:
        logger.exception("MODEL_REPLY_SHEET_SYNC_FAILED %s", lead.get("leadId"))
    return {"updated": True, "model": picked}


async def _executive_whatsapp(name: str, cfg: dict) -> str:
    """Staff master is the source of executive mobiles; BotSpace list is fallback."""
    key = (name or "").strip().lower()
    if not key:
        return ""
    import server
    for r in await server.db.staff.find().to_list(500):
        if str(r.get("status") or "Active").lower() != "active":
            continue
        if str(r.get("name") or "").strip().lower() != key:
            continue
        m = digits10(r.get("mobile"))
        if m:
            return m
    exec_map = {str(x.get("name") or "").strip().lower(): x.get("mobile")
                for x in (cfg.get("executives") or [])}
    return digits10(exec_map.get(key) or "")


async def run_finance_reminders(today_s: Optional[str] = None) -> dict:
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "not-configured"}
    today_s = today_s or today_ist()
    db = _db()
    import server
    pending = [f for f in await db.finance.find().to_list(2000)
               if float(f.get("fileOutstanding") or 0) > 0.01 and (f.get("status") or "") != "Received"]
    overdue = await server._enrich_finance_with_delivery(pending)
    sent, skipped_cancelled, skipped_no_mobile = 0, 0, []
    for f in overdue:
        if not f.get("overdue"):
            continue
        lead = await db.leads.find_one({"leadId": f.get("leadId")}) or {}
        if not lead:
            continue
        if lead.get("dealCancelled") or str(lead.get("accountStatus") or "").lower() == "cancelled":
            skipped_cancelled += 1
            continue
        count = int(lead.get("whatsappFinancePingCount") or 0)
        if count >= MAX_FINANCE_PINGS:
            continue
        if str(lead.get("whatsappFinanceLastDate") or "")[:10] == today_s:
            continue
        exec_name = (lead.get("executive") or "").strip()
        mobile = await _executive_whatsapp(exec_name, cfg)
        if not mobile:
            if exec_name and exec_name not in skipped_no_mobile:
                skipped_no_mobile.append(exec_name)
            continue
        vars_ = [
            lead.get("customerName") or "",
            f.get("financer") or lead.get("financerName") or "",
            f.get("fileNumber") or lead.get("financeFileNumber") or "",
            str(int(float(f.get("fileOutstanding") or 0))),
            str(f.get("deliveryDate") or lead.get("deliveryDate") or ""),
        ]
        staff = {"leadId": lead.get("leadId"), "customerName": exec_name or "Executive",
                 "mobile": mobile, "executive": exec_name, "interestedModel": lead.get("interestedModel")}
        res = await _enqueue_or_send(
            lead=staff, kind="finance_exec", phone=mobile,
            template_id=cfg["templates"]["finance"], variables=vars_,
            text=f"Finance overdue {f.get('fileNumber')}",
            customer_hours=False,
        )
        if res.get("ok"):
            sent += 1
            await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
                "whatsappFinancePingCount": count + 1,
                "whatsappFinanceLastDate": today_s,
            }})
    return {"ok": True, "sent": sent, "skippedCancelled": skipped_cancelled,
            "skippedNoMobile": skipped_no_mobile}


async def flush_outbox() -> dict:
    if not in_customer_hours():
        return {"ok": True, "flushed": 0, "reason": "quiet-hours"}
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True}
    db = _db()
    flushed = 0
    for item in await db.whatsapp_outbox.find({"status": "queued"}).to_list(200):
        lead = await db.leads.find_one({"leadId": item.get("leadId")}) or {
            "leadId": item.get("leadId"), "customerName": item.get("name"), "mobile": item.get("phone"),
        }
        try:
            res = await send_template(item.get("phone"), item.get("templateId"),
                                      item.get("variables") or [], name=item.get("name") or "")
            status = "accepted" if res.get("ok") else "failed"
            await _store_message(
                lead, direction="outbound", kind=item.get("kind") or "queued",
                text=item.get("text") or "", phone=item.get("phone"),
                status=status, template_id=item.get("templateId") or "",
            )
            await db.whatsapp_outbox.update_one({"_id": item["_id"]}, {"$set": {"status": "sent"}})
            flushed += 1
        except Exception as e:
            await db.whatsapp_outbox.update_one({"_id": item["_id"]}, {"$set": {
                "status": "failed", "error": str(e)[:400],
            }})
    return {"ok": True, "flushed": flushed}


# ---------------------------------------------------------------- daily reports
def _inr(n) -> str:
    """Indian grouping, no decimals. Template variables must be single-line."""
    try:
        v = int(round(float(n or 0)))
    except (TypeError, ValueError):
        return "0"
    sign, v = ("-" if v < 0 else ""), abs(v)
    sv = str(v)
    if len(sv) <= 3:
        return sign + sv
    head, tail = sv[:-3], sv[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return sign + ",".join(parts) + "," + tail


def _one_line(v) -> str:
    """Meta rejects a template variable containing a newline, tab, or 4+ spaces."""
    return re.sub(r"\s+", " ", str(v if v is not None else "")).strip() or "-"


def _top_line(rows) -> str:
    """Top executives as ONE single-line string, e.g. 'Amit (2), Sanjay (1)'."""
    named = [f"{r['name']} ({r.get('bookingsToday', 0)})" for r in (rows or [])[:3]]
    return _one_line(", ".join(named)) if named else "-"


def _target_line(done, target, pct) -> str:
    if not target:
        return _one_line(f"{done}")
    return _one_line(f"{done} of {int(target)} ({pct if pct is not None else 0}%)")


async def _staff_by_phone(phone) -> Optional[dict]:
    d = digits10(phone)
    if len(d) != 10:
        return None
    return await _db().staff.find_one({"mobile": {"$regex": f"{d}$"}})


async def _record_report_delivery_failure(provider_id: str, reason: str):
    """Stamp a post-accept delivery failure onto today's report run.

    Meta accepts a report send, returns 200, and only later refuses to deliver it
    (the marketing frequency cap does exactly this). Without writing that back,
    the run marker keeps claiming the report was sent.
    """
    db = _db()
    msg = await db.whatsapp_messages.find_one({"providerId": provider_id})
    if not msg or msg.get("audience") != "executive":
        return
    kind = msg.get("kind") or ""
    slot = "morning" if kind.endswith("_morning") else "eod"
    marker_id = f"report_{slot}_{str(msg.get('createdAt') or '')[:10]}"
    marker = await db.settings.find_one({"_id": marker_id})
    if not marker:
        return
    recipients, changed = marker.get("recipients") or [], False
    for r in recipients:
        if r.get("kind") == kind and digits10(r.get("mobile")) == digits10(msg.get("phone")):
            r["ok"] = False
            r["error"] = reason[:400]
            r["deliveryFailed"] = True
            changed = True
    if changed:
        await db.settings.update_one({"_id": marker_id}, {"$set": {
            "recipients": recipients,
            "sent": sum(1 for r in recipients if r.get("ok")),
            "failed": sum(1 for r in recipients if not r.get("ok")),
        }})


async def _send_report(staff: dict, kind: str, variables: list, text: str,
                       body_text: str = "") -> dict:
    """Staff report send. customer_hours=False — an EOD report at 20:00 is not
    a customer marketing message and must not be deferred to the outbox.

    Prefers a free-form session message when the recipient's 24-hour window is
    open. That is not merely cheaper: a session message is not a template, so it
    carries no Meta category and is not subject to the marketing frequency cap
    that silently drops report templates ("not delivered to maintain healthy
    ecosystem engagement"). Staff who reply to any message keep the window open.
    """
    who = {"leadId": "", "customerName": staff.get("name") or "Team",
           "mobile": staff.get("mobile"), "executive": staff.get("name")}
    cfg = await get_config()
    phone = staff.get("mobile")

    if body_text and session_open(staff.get("whatsappLastInboundAt")):
        try:
            res = await send_session_text(phone, body_text, name=staff.get("name") or "")
            if res.get("ok"):
                await _store_message(
                    who, direction="outbound", kind=kind, text=body_text, phone=phone,
                    status="accepted", extra={"audience": "executive", "viaSession": True,
                                              "providerId": ""})
                return {**res, "session": True}
            # Session send refused (window actually closed) — fall through to the
            # template rather than dropping the report.
        except Exception:
            logger.exception("session report send failed %s %s", kind, staff.get("name"))

    return await _enqueue_or_send(
        lead=who, kind=kind, phone=phone,
        template_id=cfg["templates"].get(kind_to_template(kind), kind),
        variables=variables, text=body_text or text, customer_hours=False)


def kind_to_template(kind: str) -> str:
    return {"exec_morning": "execMorning", "exec_eod": "execEod",
            "manager_eod": "managerEod", "owner_eod": "ownerEod"}.get(kind, kind)


async def run_daily_reports(slot: str, today_s: Optional[str] = None) -> dict:
    """Send the reports for one slot. Idempotent per day+slot: a re-run (cron
    retry, second worker) will not message anyone twice."""
    cfg = await get_config()
    if not cfg["enabled"]:
        return {"ok": False, "skipped": True, "reason": "not-configured", "sent": 0}
    import server
    today_s = today_s or today_ist()
    db = _db()
    marker_id = f"report_{slot}_{today_s}"
    if await db.settings.find_one({"_id": marker_id}):
        return {"ok": True, "slot": slot, "sent": 0, "alreadySent": True}

    data = await server._daily_report_data()
    sent, failed, recipients = 0, 0, []

    async def deliver(staff, kind, variables, text, body_text=""):
        nonlocal sent, failed
        res = await _send_report(staff, kind, variables, text, body_text)
        # The provider's own words. Without this a failed report is a bare "not
        # sent" — and the report messages carry no leadId, so they never appear
        # in the Sent box either. There was nowhere at all to read the reason.
        recipients.append({
            "name": staff.get("name"), "kind": kind, "ok": bool(res.get("ok")),
            "mobile": digits10(staff.get("mobile")),
            "templateId": cfg["templates"].get(kind_to_template(kind), kind),
            "variableCount": len(variables),
            "viaSession": bool(res.get("ok") and res.get("session")),
            "error": "" if res.get("ok") else str(res.get("error") or res.get("reason") or "")[:400],
        })
        if res.get("ok"):
            sent += 1
        else:
            failed += 1

    if slot == "morning":
        for st in await server._staff_for_report("exec_morning"):
            e = next((x for x in data["executives"]
                      if x["name"].strip().lower() == str(st.get("name") or "").strip().lower()), None)
            if not e:
                continue
            await deliver(st, "exec_morning", [
                _one_line(e["name"]),
                _one_line(e["pendingBookings"]),
                _inr(e["pendingCollection"]),
                _one_line(e["followupsDue"]),
                _one_line(e["followupsOverdue"]),
            ], f"Day ahead {today_s} for {e['name']}", "\n".join([
                f"Good morning {e['name']}.", "",
                f"Pending deliveries: {e['pendingBookings']}",
                f"To collect: Rs {_inr(e['pendingCollection'])}",
                f"Follow-ups due today: {e['followupsDue']}",
                f"Overdue follow-ups: {e['followupsOverdue']}", "",
                "Open the app for the customer list.",
            ]))
    elif slot == "eod":
        for st in await server._staff_for_report("exec_eod"):
            e = next((x for x in data["executives"]
                      if x["name"].strip().lower() == str(st.get("name") or "").strip().lower()), None)
            if not e:
                continue
            await deliver(st, "exec_eod", [
                _one_line(e["name"]),
                _one_line(e["bookingsToday"]),
                _one_line(e["bookingsMtd"]),
                _target_line(e["deliveriesMtd"], e["monthlyTarget"], e.get("attainmentPct")),
                _one_line(e["followupsOverdue"]),
            ], f"EOD {today_s} for {e['name']}", "\n".join([
                f"Day close for {e['name']}.", "",
                f"Bookings today: {e['bookingsToday']}",
                f"Bookings this month: {e['bookingsMtd']}",
                f"Deliveries this month: "
                f"{_target_line(e['deliveriesMtd'], e['monthlyTarget'], e.get('attainmentPct'))}",
                f"Overdue follow-ups: {e['followupsOverdue']}", "",
                "Open the app for the full list.",
            ]))

        for st in await server._staff_for_report("manager_eod"):
            await deliver(st, "manager_eod", [
                _one_line(today_s),
                _one_line(data["bookingsToday"]), _one_line(data["bookingsMtd"]),
                _one_line(data["deliveriesToday"]), _one_line(data["deliveriesMtd"]),
                _top_line(data["topExecutives"]),
            ], f"Manager EOD {today_s}", "\n".join([
                f"Euler team EOD - {today_s}", "",
                f"Bookings today: {data['bookingsToday']} | Month: {data['bookingsMtd']}",
                f"Deliveries today: {data['deliveriesToday']}",
                f"Deliveries this month: {data['deliveriesMtd']}",
                f"Top today: {_top_line(data['topExecutives'])}", "",
                "Open the app for the executive-wise list.",
            ]))

        for st in await server._staff_for_report("owner_eod"):
            await deliver(st, "owner_eod", [
                _one_line(today_s),
                _one_line(data["bookingsToday"]), _one_line(data["bookingsMtd"]),
                _one_line(data["deliveriesToday"]),
                _target_line(data["deliveriesMtd"], data["targetUnits"], data.get("attainmentPct")),
                _inr(data["revenueMtd"]),
                _inr(data["customerOutstanding"]),
                _one_line(f'{_inr(data["financePendingAmount"])} ({data["financePendingFiles"]} files)'),
                _top_line(data["topExecutives"]),
            ], f"Owner EOD {today_s}", "\n".join([
                f"Euler CRM - EOD {today_s}", "",
                f"Bookings today: {data['bookingsToday']} | Month: {data['bookingsMtd']}",
                f"Deliveries today: {data['deliveriesToday']}",
                f"Deliveries this month: "
                f"{_target_line(data['deliveriesMtd'], data['targetUnits'], data.get('attainmentPct'))}",
                "",
                f"Revenue this month: Rs {_inr(data['revenueMtd'])}",
                f"Customer outstanding: Rs {_inr(data['customerOutstanding'])}",
                f"Finance pending: Rs {_inr(data['financePendingAmount'])} "
                f"({data['financePendingFiles']} files)",
                f"Top today: {_top_line(data['topExecutives'])}", "",
                "Open the app for the full breakdown.",
            ]))
    else:
        return {"ok": False, "reason": f"unknown slot '{slot}'", "sent": 0}

    await db.settings.update_one({"_id": marker_id}, {"$set": {
        "slot": slot, "day": today_s, "sentAt": datetime.now(timezone.utc).isoformat(),
        "sent": sent, "failed": failed, "recipients": recipients,
    }}, upsert=True)
    return {"ok": True, "slot": slot, "day": today_s, "sent": sent,
            "failed": failed, "recipients": recipients}


# Provider wording that means "this template is not usable", which is by far the
# most common reason a report slot fails while another slot on the same numbers
# and the same code path succeeds.
_TEMPLATE_ERROR_HINTS = (
    "template", "not found", "not approved", "does not exist", "rejected",
    "pending", "disabled", "paused", "132001", "132000", "132012",
)


def diagnose_report_failure(error: str) -> str:
    """Turn a provider error into the thing the owner has to go and do."""
    e = str(error or "").lower()
    if not e:
        return ""
    # Meta ACCEPTS the send, then refuses to deliver it. This is the per-user
    # marketing frequency cap, and it only applies to MARKETING-category
    # templates — so seeing it means Meta has categorised this report as
    # Marketing, whatever category was requested when it was submitted.
    if "healthy ecosystem" in e or "131049" in e or "not delivered to maintain" in e:
        return ("Meta accepted this then blocked delivery under its marketing frequency "
                "cap, which applies ONLY to Marketing-category templates — so this report "
                "is categorised Marketing on Meta, not Utility. Fix it in WhatsApp Manager: "
                "open the template, check Category, and request Utility (or delete and "
                "re-create it as Utility). Until then, have the recipient reply once to any "
                "message — the app then sends their report as a plain session message, which "
                "carries no category and is not capped.")
    if "132000" in e or "number of parameters" in e or "mismatch" in e:
        return ("The template on Meta expects a different number of variables than the app "
                "sends. Compare it against docs/whatsapp-meta-templates.md.")
    if any(h in e for h in _TEMPLATE_ERROR_HINTS):
        return ("This template is not approved and active on Meta under this exact name. "
                "Check its status in the WhatsApp Manager — a rejected or still-pending "
                "template cannot be sent, and the name must match character for character.")
    if "24" in e and "window" in e:
        return "Outside the 24-hour session window — this send needs an approved template."
    if "phone" in e or "recipient" in e:
        return "The recipient's WhatsApp number was not accepted. Check it on Staff & Reports."
    if "auth" in e or "401" in e or "403" in e:
        return "BotSpace rejected the credentials. Re-check the API key and Channel ID."
    return ""


async def report_status(days: int = 7) -> dict:
    """What actually happened on the last report runs, and why anything failed.

    Reports are staff messages with no leadId, so they are excluded from the
    WhatsApp inbox and the Sent box by design — which left no way to see a
    failure. This is that way.
    """
    db = _db()
    cfg = await get_config()
    import server
    out = {"configured": cfg["enabled"], "slots": {}, "templates": {}, "generatedAt":
           datetime.now(timezone.utc).isoformat()}
    for kind, key in (("exec_morning", "execMorning"), ("exec_eod", "execEod"),
                      ("manager_eod", "managerEod"), ("owner_eod", "ownerEod")):
        out["templates"][kind] = {
            "templateId": cfg["templates"].get(key, DEFAULT_TEMPLATES[key]),
            "recipients": len(await server._staff_for_report(kind)),
        }

    for slot in ("morning", "eod"):
        runs = []
        for row in await db.settings.find(
                {"_id": {"$regex": f"^report_{slot}_"}}).to_list(400):
            runs.append({
                "day": row.get("day") or str(row.get("_id", ""))[-10:],
                "sentAt": row.get("sentAt"), "sent": row.get("sent", 0),
                "failed": row.get("failed", 0),
                "recipients": row.get("recipients") or [],
            })
        runs.sort(key=lambda r: str(r.get("day") or ""), reverse=True)
        runs = runs[:days]
        last = runs[0] if runs else None
        failures = []
        if last:
            for r in last["recipients"]:
                if r.get("ok"):
                    continue
                failures.append({**r, "hint": diagnose_report_failure(r.get("error"))})
        out["slots"][slot] = {
            "lastRun": last, "failures": failures, "history": runs,
            "everRan": bool(runs),
        }
    return out


async def run_daily_jobs(today_s: Optional[str] = None) -> dict:
    today_s = today_s or today_ist()
    db = _db()
    marker = await db.settings.find_one({"_id": "botspace_job"}) or {}
    follow = await run_unbooked_followups(today_s)
    finance = await run_finance_reminders(today_s)
    outbox = await flush_outbox()
    await db.settings.update_one(
        {"_id": "botspace_job"},
        {"$set": {"lastRun": today_s, "lastAt": datetime.now(timezone.utc).isoformat(),
                  "follow": follow, "finance": finance, "outbox": outbox}},
        upsert=True,
    )
    return {"ok": True, "day": today_s, "follow": follow, "finance": finance, "outbox": outbox,
            "alreadyRan": marker.get("lastRun") == today_s}


async def handle_webhook(body: dict) -> dict:
    """Ignore non-Euler phones. Always 200 to BotSpace so Tata traffic is not retried."""
    if not isinstance(body, dict):
        return {"ok": True, "ignored": True, "reason": "not-object"}
    event = str(body.get("event") or "")
    phone_obj = body.get("phone") or {}
    if isinstance(phone_obj, dict):
        phone = phone_obj.get("phone") or phone_obj.get("number") or ""
        cc = str(phone_obj.get("countryCode") or "")
        if cc and not str(phone).startswith(cc):
            phone = f"{cc}{phone}"
    else:
        phone = str(phone_obj or body.get("mobile") or "")
    # Delivery status FIRST, before the lead lookup. A daily report goes to a
    # staff number, which is not a lead — so its delivery failure used to be
    # dropped here as "not-euler-lead" and the reason never reached the app.
    # Meta reports a post-accept block (e.g. the marketing frequency cap) only
    # on this callback, so dropping it hid the single most useful signal.
    is_status = (event in {"delivery-update", "delivery-event"}
                 or body.get("status") in {"SENT", "READ", "DELIVERED", "FAILED"})
    if is_status:
        pid = str(body.get("id") or "")
        status = str(body.get("status") or "").lower() or "updated"
        reason = str(body.get("failedReason") or body.get("reason") or "")
        db = _db()
        matched = 0
        if pid:
            res = await db.whatsapp_messages.update_one(
                {"providerId": pid},
                {"$set": {"status": status, "deliveryAt": datetime.now(timezone.utc).isoformat(),
                          "failedReason": reason}},
            )
            matched = res.matched_count
            if status == "failed" and reason:
                await _record_report_delivery_failure(pid, reason)
        lead = await find_euler_lead_by_phone(phone)
        return {"ok": True, "event": "delivery", "status": status,
                "leadId": (lead or {}).get("leadId", ""), "matched": matched}

    lead = await find_euler_lead_by_phone(phone)
    if not lead:
        # Not a customer — but it may be one of our own staff replying, which
        # opens their 24-hour session and lets the next report go as plain text
        # instead of a template.
        staff = await _staff_by_phone(phone)
        if staff:
            await _db().staff.update_one(
                {"staffId": staff["staffId"]},
                {"$set": {"whatsappLastInboundAt": datetime.now(timezone.utc).isoformat()}})
            return {"ok": True, "staff": staff.get("name"), "sessionOpened": True}
        return {"ok": True, "ignored": True, "reason": "not-euler-lead"}

    payload = body.get("payload") or {}
    text = _payload_text(payload) or _payload_text(body)
    direction = str(body.get("direction") or "incoming").lower()
    if direction.startswith("out"):
        return {"ok": True, "leadId": lead.get("leadId"), "ignored": True, "reason": "outbound-echo"}

    if inbound_is_stop(text):
        await _db().leads.update_one({"leadId": lead["leadId"]}, {"$set": {"whatsappOptOut": True}})
        await _store_message(lead, direction="inbound", kind="stop", text=text or "STOP",
                             phone=phone, status="received",
                             provider_id=str(body.get("id") or ""))
        await _activity(lead, "WhatsApp STOP — follow-ups cancelled")
        return {"ok": True, "leadId": lead.get("leadId"), "optOut": True}

    await _store_message(
        lead, direction="inbound", kind=str((payload or {}).get("type") or "text"),
        text=text or "(message)", phone=phone, status="received",
        provider_id=str(body.get("id") or ""),
    )
    await _activity(lead, f"WhatsApp reply: {(text or '')[:120]}")

    # If this lead has no model yet, the reply may be answering the model-ask.
    # Never blocks or fails the webhook — BotSpace only needs the 200.
    model_res = {"updated": False, "reason": "skipped"}
    try:
        model_res = await apply_model_reply(lead, text)
        if model_res.get("updated"):
            # The customer just messaged us, so the 24-hour session is open and a
            # plain confirmation needs no template.
            await send_session_text(
                phone,
                f"Thank you! We have noted your interest in {model_res['model']}. "
                f"Our team will call you shortly with the price and offers.",
                name=lead.get("customerName") or "",
            )
    except Exception:
        logger.exception("MODEL_REPLY_FAILED %s", lead.get("leadId"))

    return {"ok": True, "leadId": lead.get("leadId"), "model": model_res}


async def list_thread(lead_id: str) -> dict:
    db = _db()
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        return {"messages": [], "sessionOpen": False}
    rows = [ {k: v for k, v in r.items() if k != "_id"}
             for r in await db.whatsapp_messages.find({"leadId": lead_id}).sort("createdAt", 1).to_list(500)]
    last_in = next((r["createdAt"] for r in reversed(rows) if r.get("direction") == "inbound"),
                   lead.get("whatsappLastInboundAt"))
    delivered = lead_is_delivered(lead)
    booked = lead_is_booked(lead)
    opted = bool(lead.get("whatsappOptOut"))
    return {
        "leadId": lead_id,
        "optOut": opted,
        "sessionOpen": session_open(last_in),
        "lastInboundAt": last_in,
        "messages": rows,
        "configured": (await get_config())["configured"],
        "booked": booked,
        "bookingConfirmSentAt": lead.get("whatsappBookingSentAt") or "",
        "canSendBooking": booked and not opted,
        "delivered": delivered,
        "deliveryReviewSentAt": lead.get("whatsappDeliverySentAt") or "",
        "canSendReview": delivered and not opted,
    }


async def staff_reply(lead_id: str, text: str, actor_name: str = "") -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Message text required")
    db = _db()
    lead = await db.leads.find_one({"leadId": lead_id})
    if not lead:
        raise ValueError("Lead not found")
    thread = await list_thread(lead_id)
    if not thread["sessionOpen"]:
        raise ValueError("24-hour reply window is closed. Send an approved template from BotSpace, or wait for the customer to write.")
    res = await send_session_text(lead.get("mobile"), text, name=lead.get("customerName") or "")
    if not res.get("ok"):
        raise RuntimeError(res.get("reason") or res.get("error") or "Send failed")
    inner = (res.get("data") or {}).get("data") if isinstance(res.get("data"), dict) else res.get("data")
    provider_id = str((inner or {}).get("id") or "")
    await _store_message(
        lead, direction="outbound", kind="staff_reply", text=text,
        phone=lead.get("mobile"), status="accepted", provider_id=provider_id,
        extra={"sentBy": actor_name},
    )
    await _activity(lead, f"WhatsApp reply by {actor_name or 'staff'}: {text[:120]}")
    return {"ok": True}


async def summary_for_lead(lead_id: str) -> dict:
    db = _db()
    n = await db.whatsapp_messages.count_documents({"leadId": lead_id})
    last = await db.whatsapp_messages.find_one({"leadId": lead_id}, sort=[("createdAt", -1)])
    lead = await db.leads.find_one({"leadId": lead_id}) or {}
    return {
        "count": n,
        "lastAt": (last or {}).get("createdAt"),
        "optOut": bool(lead.get("whatsappOptOut")),
        "sessionOpen": session_open(lead.get("whatsappLastInboundAt")),
    }


async def scheduler_loop():
    """Best-effort in-process ticker.

    This only fires if the process happens to be awake in the right hour, so it
    is a fallback, NOT the mechanism: an idle or restarting host silently skips a
    day. External cron hitting /api/integrations/botspace/cron?slot=... is the
    reliable path. Both are safe to run together — every job is idempotent per
    day (and per day+slot for reports).
    """
    await asyncio.sleep(15)
    while True:
        try:
            now = now_ist()
            if now.hour == 9:
                marker = await _db().settings.find_one({"_id": "botspace_job"}) or {}
                if marker.get("lastRun") != today_ist():
                    await run_daily_jobs()
            for slot, hour in REPORT_SLOTS.items():
                if now.hour == hour:
                    await run_daily_reports(slot)
        except Exception:
            logger.exception("whatsapp scheduler tick failed")
        await asyncio.sleep(15 * 60)
