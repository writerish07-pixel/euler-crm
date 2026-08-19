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
}

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


def followup_due(lead: dict, today_s: Optional[str] = None) -> bool:
    """Day 3, 6, 9… from createdDate. Not nextFollowupDate."""
    if not is_unbooked_active(lead):
        return False
    today_s = today_s or today_ist()
    if str(lead.get("whatsappFollowupLastDate") or "")[:10] == today_s:
        return False
    n = days_since(lead.get("createdDate"), today_s)
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
    enabled_env = os.environ.get("BOTSPACE_ENABLED")
    enabled = True if enabled_env is None else enabled_env.strip().lower() not in {"0", "false", "no", "off"}
    if "enabled" in doc:
        enabled = bool(doc.get("enabled"))
    templates = {**DEFAULT_TEMPLATES, **(doc.get("templates") or {})}
    return {
        "apiKey": api_key,
        "channelId": channel_id,
        "reviewUrl": (os.environ.get("BOTSPACE_REVIEW_URL") or doc.get("reviewUrl") or "").strip(),
        "enabled": enabled and bool(api_key) and bool(channel_id),
        "configured": bool(api_key) and bool(channel_id),
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
        updates["enabled"] = bool(body.get("enabled"))
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
        "audience": "executive" if kind == "finance_exec" else "customer",
    }
    if extra:
        doc.update(extra)
    await db.whatsapp_messages.insert_one(doc)
    if direction == "inbound":
        await db.leads.update_one({"leadId": lead["leadId"]}, {"$set": {
            "whatsappLastInboundAt": doc["createdAt"], "lastUpdated": doc["createdAt"],
        }})
    return doc


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
    exec_map = {str(x.get("name") or "").strip().lower(): x.get("mobile") for x in cfg["executives"]}
    sent = 0
    for f in overdue:
        if not f.get("overdue"):
            continue
        lead = await db.leads.find_one({"leadId": f.get("leadId")}) or {}
        if not lead:
            continue
        count = int(lead.get("whatsappFinancePingCount") or 0)
        if count >= MAX_FINANCE_PINGS:
            continue
        if str(lead.get("whatsappFinanceLastDate") or "")[:10] == today_s:
            continue
        exec_name = (lead.get("executive") or "").strip()
        mobile = exec_map.get(exec_name.lower())
        if not mobile:
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
    return {"ok": True, "sent": sent}


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
    lead = await find_euler_lead_by_phone(phone)
    if not lead:
        return {"ok": True, "ignored": True, "reason": "not-euler-lead"}

    if event in {"delivery-update", "delivery-event"} or body.get("status") in {"SENT", "READ", "DELIVERED", "FAILED"}:
        pid = str(body.get("id") or "")
        status = str(body.get("status") or "").lower() or "updated"
        db = _db()
        if pid:
            await db.whatsapp_messages.update_one(
                {"providerId": pid},
                {"$set": {"status": status, "deliveryAt": datetime.now(timezone.utc).isoformat(),
                          "failedReason": body.get("failedReason") or ""}},
            )
        return {"ok": True, "leadId": lead.get("leadId"), "event": "delivery"}

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
    return {"ok": True, "leadId": lead.get("leadId")}


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
    """Best-effort morning job. Railway cron hitting /cron is the reliable path."""
    await asyncio.sleep(15)
    while True:
        try:
            now = now_ist()
            if now.hour == 9:
                marker = await _db().settings.find_one({"_id": "botspace_job"}) or {}
                if marker.get("lastRun") != today_ist():
                    await run_daily_jobs()
        except Exception:
            logger.exception("whatsapp scheduler tick failed")
        await asyncio.sleep(15 * 60)
