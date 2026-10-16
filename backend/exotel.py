"""Akar Euler deal-verify calls via Exotel.

Booked leads are called in Hindi from the dealership ExoPhone. The customer
types the amount they paid and/or speaks it. We keep rescheduling until an
amount is stored, then flag a mismatch vs receipts on the file.

Never blocks Convert to Booking. Secrets live in Settings, never in git.
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from xml.sax.saxutils import escape as xml_escape

import httpx

logger = logging.getLogger("euler.exotel")

IST = timezone(timedelta(hours=5, minutes=30))
SETTINGS_ID = "exotel"
BRAND = "Akar Euler"
DEFAULT_SID = "shubhammotors1"
DEFAULT_SUBDOMAIN = "api.in.exotel.com"
SG_API_HOST = "api.exotel.com"
IN_API_HOST = "api.in.exotel.com"
DEFAULT_EXOPHONE = "01414937655"
DEFAULT_QUIET_START = 10
DEFAULT_QUIET_END = 19
MAX_ATTEMPTS_PER_DAY = 2
SLACK_RUPEES = 100
AUDIO_DIR = Path(__file__).parent / "static" / "exotel"
AUDIO_CLIPS = ("intro", "prompt", "speak", "thanks")

# Plain spoken Hindi for milk / vegetable sellers. Same words as the MP3s.
# Avoid English (booking, keypad, type) and formal words (rashi, bhugtan, pushti).
SPOKEN = {
    "intro": (
        "Namaste. Main Akar Euler se baat kar rahi hoon. "
        "Aapne hamari gaadi li hai. Hum poochna chahte hain — "
        "gaadi ke liye aapne kitne paise diye."
    ),
    "prompt": (
        "Jo paise aapne gaadi ke liye diye, wahi poora number phone ke button se dabaiye. "
        "Number dabane ke baad hash wala button daba den. "
        "Hash button par do chhoti linein bani hoti hain."
    ),
    "speak": "Agar number nahi daba sakte, to ab bolkar batayein. Aapne kitne paise diye.",
    "thanks": "Dhanyavaad. Akar Euler.",
}

# Devanagari used when rebuilding the MP3s (clearer TTS than roman Hindi).
SPOKEN_HI = {
    "intro": (
        "नमस्ते। मैं आकर यूलर से बात कर रही हूँ। "
        "आपने हमारी गाड़ी ली है। हम पूछना चाहते हैं — "
        "गाड़ी के लिए आपने कितने पैसे दिए।"
    ),
    "prompt": (
        "जो पैसे आपने गाड़ी के लिए दिए, वही पूरा नंबर फ़ोन के बटनों से दबाएं। "
        "नंबर दबाने के बाद, हैश वाला बटन दबा दें। "
        "हैश बटन पर दो छोटी लाइनें बनी होती हैं।"
    ),
    "speak": "अगर नंबर नहीं दबा सकते, तो अब बोलकर बताएं। आपने कितने पैसे दिए।",
    "thanks": "धन्यवाद। आकर यूलर।",
}

# Hindi number words used when a recording is transcribed or staff types words.
_HI_ONES = {
    "शून्य": 0, "zero": 0, "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पाँच": 5, "पांच": 5,
    "छह": 6, "सात": 7, "आठ": 8, "नौ": 9, "दस": 10, "ग्यारह": 11, "बारह": 12,
    "तेरह": 13, "चौदह": 14, "पंद्रह": 15, "सोलह": 16, "सत्रह": 17, "अठारह": 18,
    "उन्नीस": 19, "बीस": 20, "तीस": 30, "चालीस": 40, "पचास": 50, "साठ": 60,
    "सत्तर": 70, "अस्सी": 80, "नब्बे": 90,
}
_HI_SCALE = {
    "करोड़": 10000000, "crore": 10000000,
    "लाख": 100000, "lakh": 100000, "lac": 100000,
    "हजार": 1000, "हज़ार": 1000, "thousand": 1000,
}


def now_ist() -> datetime:
    return datetime.now(IST)


def today_ist() -> str:
    return now_ist().strftime("%Y-%m-%d")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def as_utc_iso(dt: datetime) -> str:
    """Store due-times in UTC so Mongo string compare matches now_iso()."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(timezone.utc).isoformat()


def digits10(phone) -> str:
    d = re.sub(r"\D", "", str(phone or ""))
    return d[-10:] if len(d) >= 10 else d


def _db():
    import server
    return server.db


def _is_booked(lead) -> bool:
    import server
    return bool(lead) and server._is_booked_lead(lead)


def _mask(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 10:
        return "••••"
    return key[:6] + "…" + key[-4:]


def public_api_origin() -> str:
    origin = (os.environ.get("PUBLIC_API_URL") or "").strip().rstrip("/")
    if origin.endswith("/api"):
        origin = origin[:-4]
    if not origin.startswith("http") or "onrender.com" in origin:
        origin = "https://euler-crm-production.up.railway.app"
    return origin


def webhook_urls(cfg: dict) -> dict:
    origin = public_api_origin()
    token = (cfg.get("webhookSecret") or "").strip()
    q = f"?token={token}" if token else ""
    base = f"{origin}/api/integrations/exotel"
    return {
        "voice": f"{base}/voice{q}",
        "gather": f"{base}/gather{q}",
        "gatherConfig": f"{base}/gather-config{q}",
        "recorded": f"{base}/recorded{q}",
        "status": f"{base}/status{q}",
        "audio": f"{base}/audio",
        "cron": f"{base}/cron",
    }


async def get_config() -> dict:
    db = _db()
    doc = await db.settings.find_one({"_id": SETTINGS_ID}) or {}
    api_key = (os.environ.get("EXOTEL_API_KEY") or doc.get("apiKey") or "").strip()
    api_token = (os.environ.get("EXOTEL_API_TOKEN") or doc.get("apiToken") or "").strip()
    sid = (os.environ.get("EXOTEL_SID") or doc.get("accountSid") or DEFAULT_SID).strip()
    subdomain = (os.environ.get("EXOTEL_SUBDOMAIN") or doc.get("subdomain") or DEFAULT_SUBDOMAIN).strip()
    exo = re.sub(r"\D", "", os.environ.get("EXOTEL_EXOPHONE") or doc.get("exoPhone") or DEFAULT_EXOPHONE)
    enabled_env = os.environ.get("EXOTEL_ENABLED")
    turned_on = True if enabled_env is None else enabled_env.strip().lower() not in {"0", "false", "no", "off"}
    if "enabled" in doc and not doc.get("enabled"):
        turned_on = False
    configured = bool(api_key) and bool(api_token) and bool(sid) and bool(exo)
    quiet_start = int(doc.get("quietStart") or DEFAULT_QUIET_START)
    quiet_end = int(doc.get("quietEnd") or DEFAULT_QUIET_END)
    return {
        "apiKey": api_key,
        "apiToken": api_token,
        "accountSid": sid,
        "subdomain": subdomain or DEFAULT_SUBDOMAIN,
        "exoPhone": exo,
        "enabled": turned_on and configured,
        "configured": configured,
        "hasKey": bool(api_key),
        "hasToken": bool(api_token),
        "apiKeyMasked": _mask(api_key),
        "apiTokenMasked": _mask(api_token),
        "quietStart": quiet_start,
        "quietEnd": quiet_end,
        "webhookSecret": (os.environ.get("EXOTEL_WEBHOOK_SECRET") or doc.get("webhookSecret") or "").strip(),
        "cronToken": (os.environ.get("EXOTEL_CRON_TOKEN") or doc.get("cronToken") or "").strip(),
        "flowAppId": (os.environ.get("EXOTEL_FLOW_APP_ID") or doc.get("flowAppId") or "").strip(),
        "brand": BRAND,
    }


def public_config(cfg: dict) -> dict:
    out = {k: v for k, v in cfg.items() if k not in ("apiKey", "apiToken")}
    urls = webhook_urls(cfg)
    out["voiceUrl"] = urls["voice"]
    out["gatherUrl"] = urls["gather"]
    out["gatherConfigUrl"] = urls["gatherConfig"]
    out["recordedUrl"] = urls["recorded"]
    out["statusUrl"] = urls["status"]
    out["cronUrl"] = urls["cron"]
    out["audioUrl"] = urls["audio"]
    out["introAudioUrl"] = urls["audio"] + "/intro.mp3"
    out["promptAudioUrl"] = urls["audio"] + "/prompt.mp3"
    out["speakAudioUrl"] = urls["audio"] + "/speak.mp3"
    out["thanksAudioUrl"] = urls["audio"] + "/thanks.mp3"
    out["connectUrl"] = connect_flow_url(cfg)
    return out


async def save_config(body: dict) -> dict:
    db = _db()
    existing = await db.settings.find_one({"_id": SETTINGS_ID}) or {}
    updates = {}
    for secret_key in ("apiKey", "apiToken", "webhookSecret", "cronToken"):
        if secret_key not in body:
            continue
        raw = str(body.get(secret_key) or "").strip()
        if raw and "…" not in raw and not raw.startswith("•"):
            updates[secret_key] = raw
    if "accountSid" in body:
        updates["accountSid"] = str(body.get("accountSid") or DEFAULT_SID).strip() or DEFAULT_SID
    if "subdomain" in body:
        updates["subdomain"] = str(body.get("subdomain") or DEFAULT_SUBDOMAIN).strip() or DEFAULT_SUBDOMAIN
    if "exoPhone" in body:
        updates["exoPhone"] = re.sub(r"\D", "", str(body.get("exoPhone") or "")) or DEFAULT_EXOPHONE
    if "flowAppId" in body:
        updates["flowAppId"] = re.sub(r"\D", "", str(body.get("flowAppId") or ""))
    if "enabled" in body:
        updates["enabled"] = bool(body.get("enabled"))
    if "quietStart" in body:
        updates["quietStart"] = max(0, min(23, int(body.get("quietStart") or DEFAULT_QUIET_START)))
    if "quietEnd" in body:
        updates["quietEnd"] = max(1, min(24, int(body.get("quietEnd") or DEFAULT_QUIET_END)))
    will_key = updates.get("apiKey") or existing.get("apiKey")
    will_tok = updates.get("apiToken") or existing.get("apiToken")
    if will_key and will_tok and updates.get("enabled") is not False:
        updates["enabled"] = True
    if not (updates.get("webhookSecret") or existing.get("webhookSecret")):
        updates["webhookSecret"] = secrets.token_urlsafe(18)
    if updates:
        updates["updatedAt"] = now_iso()
        await db.settings.update_one({"_id": SETTINGS_ID}, {"$set": updates}, upsert=True)
    return public_config(await get_config())


def in_quiet_hours(when: Optional[datetime] = None, cfg: Optional[dict] = None) -> bool:
    """True when we are allowed to ring the customer (default 10:00–19:00 IST)."""
    t = when or now_ist()
    start = int((cfg or {}).get("quietStart") or DEFAULT_QUIET_START)
    end = int((cfg or {}).get("quietEnd") or DEFAULT_QUIET_END)
    return start <= t.hour < end


def next_slot(when: Optional[datetime] = None, cfg: Optional[dict] = None) -> datetime:
    t = when or now_ist()
    start = int((cfg or {}).get("quietStart") or DEFAULT_QUIET_START)
    end = int((cfg or {}).get("quietEnd") or DEFAULT_QUIET_END)
    if t.hour < start:
        return t.replace(hour=start, minute=15, second=0, microsecond=0)
    later = t + timedelta(hours=3)
    if later.hour < end and later.date() == t.date():
        return later
    nxt = (t + timedelta(days=1)).replace(hour=start, minute=15, second=0, microsecond=0)
    return nxt


def parse_amount(raw) -> Optional[float]:
    """DTMF digits, '486933#', '4.87 lakh', or Hindi लाख/हजार phrasing."""
    if raw is None:
        return None
    if isinstance(raw, bool):
        return None
    if isinstance(raw, (int, float)):
        val = float(raw)
        return val if val > 0 else None
    text = str(raw).strip()
    if not text:
        return None
    plain = text.replace(",", "").replace("₹", "").replace("#", "").strip()
    if re.fullmatch(r"\d+(?:\.\d+)?", plain):
        val = float(plain)
        return val if val > 0 else None
    digits = re.sub(r"[^\d]", "", text)
    # Bare keypad / hash amount (ignore a trailing # already stripped).
    if re.fullmatch(r"\d{3,9}", digits) and not re.search(r"[a-zA-Z\u0900-\u097F]", text):
        val = float(digits)
        return val if val > 0 else None
    lower = text.lower().replace("₹", " ").replace(",", " ")
    # 4.87 lakh / 4.87 लाख
    m = re.search(r"(\d+(?:\.\d+)?)\s*(lakh|lac|लाख)", lower)
    if m:
        return round(float(m.group(1)) * 100000, 0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(hazar|thousand|हजार|हज़ार)", lower)
    if m:
        return round(float(m.group(1)) * 1000, 0)
    m = re.search(r"(\d+(?:\.\d+)?)\s*(crore|करोड़)", lower)
    if m:
        return round(float(m.group(1)) * 10000000, 0)
    total = 0.0
    last = 0.0
    used_words = False
    for tok in re.findall(r"[0-9]+(?:\.[0-9]+)?|[a-zA-Z]+|[\u0900-\u097F]+", lower):
        if tok in _HI_SCALE:
            used_words = True
            total += (last or 1) * _HI_SCALE[tok]
            last = 0.0
            continue
        if tok in _HI_ONES:
            used_words = True
            last += _HI_ONES[tok]
            continue
        if re.fullmatch(r"\d+(?:\.\d+)?", tok):
            last += float(tok)
    if used_words:
        total += last
        return total if total > 0 else None
    if digits:
        val = float(digits)
        return val if val > 0 else None
    return None


def amounts_match(stated, received) -> bool:
    s = float(stated or 0)
    r = float(received or 0)
    if s <= 0 and r <= 0:
        return True
    gap = abs(s - r)
    if gap <= SLACK_RUPEES:
        return True
    # Spoken round thousands ("चार लाख सत्तासी हजार") vs exact payable.
    if gap <= 1000 and (s % 1000 == 0 or r % 1000 == 0):
        return True
    basis = max(s, r, 1)
    return gap / basis <= 0.02


def mismatch_kind(stated, received) -> str:
    s = float(stated or 0)
    r = float(received or 0)
    if amounts_match(s, r):
        return ""
    return "over" if s > r else "under"


def schedule(coro):
    async def _run():
        try:
            await coro
        except Exception:
            logger.exception("exotel background task failed")

    try:
        asyncio.get_running_loop().create_task(_run())
    except RuntimeError:
        logger.warning("exotel: no running event loop; skipped")


def gather_config_json(cfg: dict) -> dict:
    """JSON Gather applet Primary URL — plays Hindi prompt, hash to finish."""
    audio = webhook_urls(cfg)["audio"]
    return {
        "gather_prompt": {"audio_url": f"{audio}/prompt.mp3"},
        "max_input_digits": 8,
        "finish_on_key": "#",
        "input_timeout": 12,
        "repeat_menu": 1,
        "repeat_gather_prompt": {"audio_url": f"{audio}/prompt.mp3"},
    }


def connect_flow_url(cfg: dict) -> str:
    """Exotel Connect-to-flow Url. App Bazaar app_id is required for live calls."""
    app_id = re.sub(r"\D", "", str((cfg or {}).get("flowAppId") or ""))
    sid = str((cfg or {}).get("accountSid") or DEFAULT_SID).strip() or DEFAULT_SID
    if app_id:
        return f"http://my.exotel.com/{sid}/exoml/start_voice/{app_id}"
    return webhook_urls(cfg or {})["voice"]


def india_dial(phone: str) -> str:
    d = digits10(phone)
    if len(d) == 10:
        return "0" + d
    exo = re.sub(r"\D", "", phone or "")
    return exo


def _form(form) -> dict:
    if not form:
        return {}
    if hasattr(form, "items"):
        return {str(k): (v[0] if isinstance(v, (list, tuple)) else v) for k, v in form.items()}
    return dict(form)


def audio_path(name: str) -> Optional[Path]:
    safe = re.sub(r"[^a-z]", "", str(name or "").lower())
    if safe not in AUDIO_CLIPS:
        return None
    path = AUDIO_DIR / f"{safe}.mp3"
    return path if path.is_file() else None


def _play_or_say(cfg: dict, clip: str, spoken: str) -> str:
    urls = webhook_urls(cfg)
    if audio_path(clip):
        return f'<Play>{xml_escape(urls["audio"] + "/" + clip + ".mp3")}</Play>'
    return f"<Say voice=\"female\">{xml_escape(spoken)}</Say>"


def exoml_start(cfg: dict) -> str:
    urls = webhook_urls(cfg)
    intro = _play_or_say(cfg, "intro", SPOKEN["intro"])
    prompt = _play_or_say(cfg, "prompt", SPOKEN["prompt"])
    speak = _play_or_say(cfg, "speak", SPOKEN["speak"])
    # Intro + prompt sit inside Gather so keypad during the greeting still counts.
    # Record here is a fallback if Exotel continues this document on timeout;
    # the gather webhook also returns Record when no digits arrive.
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f'<Gather timeout="12" finishOnKey="#" numDigits="8" method="POST" action="{xml_escape(urls["gather"])}">'
        f"{intro}"
        f"{prompt}"
        "</Gather>"
        f"{speak}"
        f'<Record maxLength="25" timeout="5" playBeep="true" method="POST" action="{xml_escape(urls["recorded"])}"/>'
        "</Response>"
    )


def exoml_after_digits(cfg: dict) -> str:
    thanks = _play_or_say(cfg, "thanks", SPOKEN["thanks"])
    return '<?xml version="1.0" encoding="UTF-8"?><Response>' + thanks + "<Hangup/></Response>"


def exoml_record_then_thanks(cfg: dict) -> str:
    """Spoken-amount path after Gather timeout / empty keypad. Thanks play on /recorded."""
    speak = _play_or_say(cfg, "speak", SPOKEN["speak"])
    urls = webhook_urls(cfg)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{speak}"
        f'<Record maxLength="25" timeout="5" playBeep="true" method="POST" action="{xml_escape(urls["recorded"])}"/>'
        "</Response>"
    )


def _exotel_fail_reason(body, status_code) -> str:
    if isinstance(body, dict):
        ex = body.get("RestException") if isinstance(body.get("RestException"), dict) else {}
        msg = ex.get("Message") or ex.get("message") or body.get("Message") or body.get("raw")
        if msg:
            return str(msg).strip()[:220]
    return f"Exotel HTTP {status_code}"


def _api_hosts(cfg: dict) -> list:
    primary = (cfg.get("subdomain") or DEFAULT_SUBDOMAIN).strip() or DEFAULT_SUBDOMAIN
    alt = IN_API_HOST if IN_API_HOST not in primary else SG_API_HOST
    hosts = [primary]
    if alt not in hosts:
        hosts.append(alt)
    return hosts


async def _place_call_http(cfg: dict, customer: str, lead_id: str) -> dict:
    """Connect-to-flow only. Do not send Record/To — those belong to connect-two-numbers."""
    urls = webhook_urls(cfg)
    sid = cfg["accountSid"]
    data = {
        "From": india_dial(customer),
        "CallerId": cfg["exoPhone"],
        "Url": connect_flow_url(cfg),
        "StatusCallback": urls["status"],
        "CustomField": lead_id,
        "CallType": "trans",
        "TimeLimit": "120",
        "TimeOut": "25",
    }
    auth = (cfg["apiKey"], cfg["apiToken"])
    last = {"ok": False, "statusCode": 0, "callSid": "", "status": "", "body": {}, "reason": "exotel-no-response"}
    async with httpx.AsyncClient(timeout=20.0) as client:
        for host in _api_hosts(cfg):
            url = f"https://{host}/v1/Accounts/{sid}/Calls/connect.json"
            r = await client.post(url, data=data, auth=auth)
            body = {}
            try:
                body = r.json()
            except Exception:
                body = {"raw": (r.text or "")[:400]}
            call = body.get("Call") if isinstance(body, dict) else None
            if not isinstance(call, dict):
                call = body if isinstance(body, dict) else {}
            ok = r.status_code < 400 and bool(call.get("Sid") or call.get("CallSid"))
            last = {
                "ok": ok,
                "statusCode": r.status_code,
                "callSid": call.get("Sid") or call.get("CallSid") or "",
                "status": call.get("Status") or "",
                "body": body,
                "reason": "" if ok else _exotel_fail_reason(body, r.status_code),
                "host": host,
            }
            if ok or r.status_code not in (401, 403, 404):
                break
    return last


def snapshot(lead: dict) -> dict:
    return {
        "dealVerifyStatus": lead.get("dealVerifyStatus") or "",
        "dealVerifyAmount": lead.get("dealVerifyAmount") or 0,
        "dealVerifySource": lead.get("dealVerifySource") or "",
        "dealVerifyRecordingUrl": lead.get("dealVerifyRecordingUrl") or "",
        "dealVerifyCallSid": lead.get("dealVerifyCallSid") or "",
        "dealVerifyAttempts": int(lead.get("dealVerifyAttempts") or 0),
        "dealVerifyAttemptsToday": int(lead.get("dealVerifyAttemptsToday") or 0),
        "dealVerifyAttemptsDate": lead.get("dealVerifyAttemptsDate") or "",
        "dealVerifyNextAt": lead.get("dealVerifyNextAt") or "",
        "dealVerifyLastAt": lead.get("dealVerifyLastAt") or "",
        "dealVerifyLastStatus": lead.get("dealVerifyLastStatus") or "",
        "dealVerifyTranscript": lead.get("dealVerifyTranscript") or "",
        "dealVerifyMismatch": bool(lead.get("dealVerifyMismatch")),
        "dealVerifyMismatchKind": lead.get("dealVerifyMismatchKind") or "",
        "dealVerifyPaused": bool(lead.get("dealVerifyPaused")),
        "totalReceived": lead.get("totalReceived") or 0,
        "customerPayable": lead.get("customerPayable") or lead.get("cxDemand") or 0,
    }


async def _apply(lead_id: str, updates: dict):
    updates = dict(updates)
    updates["lastUpdated"] = now_iso()
    await _db().leads.update_one({"leadId": lead_id}, {"$set": updates})
    return await _db().leads.find_one({"leadId": lead_id})


async def enqueue_after_booking(lead_id: str) -> dict:
    """Mark the file for verify. Does not place the call inline (booking stays fast)."""
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if not _is_booked(lead):
        return {"ok": False, "reason": "not-booked"}
    if parse_amount(lead.get("dealVerifyAmount")):
        return {"ok": True, "skipped": "already-answered"}
    if lead.get("dealCancelled"):
        return {"ok": False, "reason": "cancelled"}
    if not digits10(lead.get("mobile")):
        return {"ok": False, "reason": "no-mobile"}
    cfg = await get_config()
    nxt = now_ist() + timedelta(minutes=8)
    if not in_quiet_hours(nxt, cfg):
        nxt = next_slot(now_ist(), cfg)
    due = as_utc_iso(nxt)
    await _apply(lead_id, {
        "dealVerifyStatus": "pending",
        "dealVerifyPaused": False,
        "dealVerifyNextAt": due,
        "dealVerifyLastStatus": "queued",
    })
    return {"ok": True, "nextAt": due}


async def enqueue_unverified_booked(limit: int = 300) -> dict:
    """Queue existing booked files that were never marked for verify.

    Convert-to-booking queues new files. This covers the booked register that
    already existed when Exotel was switched on. Does not place the calls.
    """
    q = {
        "dealCancelled": {"$ne": True},
        "dealVerifyPaused": {"$ne": True},
        "dealVerifyStatus": {"$nin": ["pending", "calling", "failed", "queued", "listening", "answered", "paused"]},
        "$or": [
            {"dealVerifyAmount": {"$exists": False}},
            {"dealVerifyAmount": 0},
            {"dealVerifyAmount": None},
            {"dealVerifyAmount": ""},
        ],
    }
    rows = await _db().leads.find(q).sort("bookingDate", -1).to_list(800)
    due = as_utc_iso(now_ist())
    queued = 0
    for lead in rows:
        if queued >= limit:
            break
        if not _is_booked(lead):
            continue
        if parse_amount(lead.get("dealVerifyAmount")):
            continue
        if len(digits10(lead.get("mobile"))) != 10:
            continue
        await _apply(lead["leadId"], {
            "dealVerifyStatus": "pending",
            "dealVerifyPaused": False,
            "dealVerifyNextAt": due,
            "dealVerifyLastStatus": "queued",
        })
        queued += 1
    return {"ok": True, "queued": queued}


def _attempts_today(lead: dict) -> int:
    if str(lead.get("dealVerifyAttemptsDate") or "") != today_ist():
        return 0
    return int(lead.get("dealVerifyAttemptsToday") or 0)


async def place_verify_call(lead_id: str, *, force: bool = False) -> dict:
    cfg = await get_config()
    if not cfg.get("enabled"):
        return {"ok": False, "reason": "exotel-not-configured"}
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if not lead:
        return {"ok": False, "reason": "missing-lead"}
    if lead.get("dealCancelled"):
        return {"ok": False, "reason": "cancelled"}
    if parse_amount(lead.get("dealVerifyAmount")):
        return {"ok": True, "skipped": "already-answered"}
    if lead.get("dealVerifyPaused") and not force:
        return {"ok": False, "reason": "paused"}
    if not _is_booked(lead):
        return {"ok": False, "reason": "not-booked"}
    mobile = digits10(lead.get("mobile"))
    if len(mobile) != 10:
        return {"ok": False, "reason": "no-mobile"}
    if not force:
        if not in_quiet_hours(now_ist(), cfg):
            due = as_utc_iso(next_slot(now_ist(), cfg))
            await _apply(lead_id, {"dealVerifyNextAt": due, "dealVerifyStatus": "pending"})
            return {"ok": False, "reason": "quiet-hours", "nextAt": due}
        if _attempts_today(lead) >= MAX_ATTEMPTS_PER_DAY:
            due = as_utc_iso(next_slot(now_ist() + timedelta(hours=12), cfg))
            await _apply(lead_id, {"dealVerifyNextAt": due})
            return {"ok": False, "reason": "day-cap", "nextAt": due}
    today = today_ist()
    today_n = _attempts_today(lead) + 1
    total_n = int(lead.get("dealVerifyAttempts") or 0) + 1
    result = await _place_call_http(cfg, mobile, lead_id)
    due = as_utc_iso(next_slot(now_ist(), cfg))
    await _apply(lead_id, {
        "dealVerifyStatus": "calling" if result.get("ok") else "failed",
        "dealVerifyCallSid": result.get("callSid") or lead.get("dealVerifyCallSid") or "",
        "dealVerifyAttempts": total_n,
        "dealVerifyAttemptsToday": today_n,
        "dealVerifyAttemptsDate": today,
        "dealVerifyLastAt": now_iso(),
        "dealVerifyLastStatus": result.get("status") or (
            "queued" if result.get("ok") else (result.get("reason") or "failed")
        ),
        "dealVerifyNextAt": due,
    })
    await _db().deal_verify_calls.insert_one({
        "leadId": lead_id,
        "callSid": result.get("callSid") or "",
        "ok": bool(result.get("ok")),
        "statusCode": result.get("statusCode"),
        "reason": result.get("reason") or "",
        "host": result.get("host") or "",
        "createdAt": now_iso(),
        "customer": mobile,
    })
    if not result.get("ok"):
        logger.warning("EXOTEL_CALL_FAILED lead=%s status=%s reason=%s body=%s",
                       lead_id, result.get("statusCode"), result.get("reason"),
                       str(result.get("body"))[:300])
    return {**result, "leadId": lead_id, "attemptsToday": today_n}


async def record_amount(lead_id: str, amount, *, source: str, recording_url: str = "",
                        call_sid: str = "", transcript: str = "") -> dict:
    amt = parse_amount(amount)
    if not amt:
        return {"ok": False, "reason": "no-amount"}
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    received = float(lead.get("totalReceived") or 0)
    kind = mismatch_kind(amt, received)
    updates = {
        "dealVerifyStatus": "answered",
        "dealVerifyAmount": amt,
        "dealVerifySource": source,
        "dealVerifyMismatch": bool(kind),
        "dealVerifyMismatchKind": kind,
        "dealVerifyNextAt": "",
        "dealVerifyPaused": False,
        "dealVerifyLastAt": now_iso(),
        "dealVerifyLastStatus": "answered",
    }
    if recording_url:
        updates["dealVerifyRecordingUrl"] = recording_url
    if call_sid:
        updates["dealVerifyCallSid"] = call_sid
    if transcript:
        updates["dealVerifyTranscript"] = transcript[:500]
    lead = await _apply(lead_id, updates)
    return {"ok": True, "leadId": lead_id, **snapshot(lead)}


async def record_listening(lead_id: str, *, recording_url: str, call_sid: str = "") -> dict:
    """Customer spoke but we do not yet have digits — keep the tape, retry later."""
    if not recording_url:
        return {"ok": False, "reason": "no-recording"}
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if parse_amount(lead.get("dealVerifyAmount")):
        if recording_url:
            await _apply(lead_id, {"dealVerifyRecordingUrl": recording_url})
        return {"ok": True, "skipped": "already-answered"}
    due = as_utc_iso(next_slot(now_ist() + timedelta(hours=6), await get_config()))
    lead = await _apply(lead_id, {
        "dealVerifyStatus": "listening",
        "dealVerifyRecordingUrl": recording_url,
        "dealVerifyCallSid": call_sid or lead.get("dealVerifyCallSid") or "",
        "dealVerifyLastAt": now_iso(),
        "dealVerifyLastStatus": "recorded",
        "dealVerifyNextAt": due,
    })
    return {"ok": True, "leadId": lead_id, **snapshot(lead)}


def _pick_lead_id(form: dict, custom: str = "") -> str:
    for key in ("CustomField", "customField", "custom_field", "leadId", "LeadId"):
        val = str(form.get(key) or "").strip()
        if val.startswith("LD"):
            return val
    extra = str(custom or "").strip()
    if extra.startswith("LD"):
        return extra
    return ""


async def _lead_for_call(form: dict) -> Optional[dict]:
    db = _db()
    sid = str(form.get("CallSid") or form.get("Sid") or form.get("callSid") or "").strip()
    lid = _pick_lead_id(form)
    if lid:
        return await db.leads.find_one({"leadId": lid})
    if sid:
        return await db.leads.find_one({"dealVerifyCallSid": sid})
    return None


async def handle_gather(form: dict) -> dict:
    lead = await _lead_for_call(form)
    if not lead:
        return {"ok": False, "reason": "unknown-call"}
    digits = form.get("Digits") or form.get("digits") or ""
    amt = parse_amount(digits)
    rec = str(form.get("RecordingUrl") or form.get("recording_url") or "")
    sid = str(form.get("CallSid") or form.get("Sid") or "")
    if amt:
        return await record_amount(lead["leadId"], amt, source="typed",
                                   recording_url=rec, call_sid=sid, transcript=str(digits))
    return {"ok": False, "reason": "no-digits", "leadId": lead["leadId"]}


async def handle_recorded(form: dict) -> dict:
    lead = await _lead_for_call(form)
    if not lead:
        return {"ok": False, "reason": "unknown-call"}
    rec = str(form.get("RecordingUrl") or form.get("recording_url") or "")
    sid = str(form.get("CallSid") or form.get("Sid") or "")
    digits = form.get("Digits") or form.get("digits") or ""
    spoken = form.get("TranscriptionText") or form.get("transcription") or ""
    amt = parse_amount(digits) or parse_amount(spoken)
    if amt:
        src = "typed" if parse_amount(digits) else "spoken"
        return await record_amount(lead["leadId"], amt, source=src,
                                   recording_url=rec, call_sid=sid, transcript=str(spoken or digits))
    return await record_listening(lead["leadId"], recording_url=rec, call_sid=sid)


async def handle_status(form: dict) -> dict:
    lead = await _lead_for_call(form)
    if not lead:
        return {"ok": True, "ignored": True}
    if parse_amount(lead.get("dealVerifyAmount")):
        return {"ok": True, "skipped": "already-answered"}
    status = str(form.get("Status") or form.get("DialCallStatus") or "").lower()
    rec = str(form.get("RecordingUrl") or "")
    sid = str(form.get("CallSid") or form.get("Sid") or "")
    cfg = await get_config()
    due = as_utc_iso(next_slot(now_ist(), cfg))
    updates = {
        "dealVerifyLastStatus": status or lead.get("dealVerifyLastStatus") or "",
        "dealVerifyLastAt": now_iso(),
        "dealVerifyCallSid": sid or lead.get("dealVerifyCallSid") or "",
        "dealVerifyNextAt": due,
    }
    if rec and not lead.get("dealVerifyRecordingUrl"):
        updates["dealVerifyRecordingUrl"] = rec
        if str(lead.get("dealVerifyStatus") or "") not in ("answered",):
            updates["dealVerifyStatus"] = "listening"
    elif status in ("completed", "in-progress"):
        if str(lead.get("dealVerifyStatus") or "") == "calling":
            updates["dealVerifyStatus"] = "pending"
    elif status in ("failed", "busy", "no-answer", "no_answer"):
        updates["dealVerifyStatus"] = "pending"
    await _apply(lead["leadId"], updates)
    return {"ok": True, "leadId": lead["leadId"], "status": status}


async def pause_lead(lead_id: str, paused: bool = True) -> dict:
    lead = await _apply(lead_id, {
        "dealVerifyPaused": bool(paused),
        "dealVerifyStatus": "paused" if paused else "pending",
        "dealVerifyNextAt": "" if paused else as_utc_iso(next_slot(now_ist(), await get_config())),
    })
    return snapshot(lead or {})


async def run_due_calls(limit: int = 25, *, force: bool = False) -> dict:
    cfg = await get_config()
    if not cfg.get("enabled"):
        return {"ok": False, "reason": "exotel-not-configured", "placed": 0}
    if not force and not in_quiet_hours(now_ist(), cfg):
        return {"ok": True, "reason": "quiet-hours", "placed": 0}
    now = now_iso()
    today = today_ist()
    q = {
        "dealCancelled": {"$ne": True},
        "dealVerifyPaused": {"$ne": True},
        "$or": [
            {"dealVerifyAmount": {"$exists": False}},
            {"dealVerifyAmount": 0},
            {"dealVerifyAmount": None},
            {"dealVerifyAmount": ""},
        ],
        # Only files the CRM queued (after booking / Call now). Do not ring every
        # historical booked lead the first time Exotel is switched on.
        "dealVerifyStatus": {"$in": ["pending", "calling", "failed", "queued", "listening"]},
        "$and": [
            {"$or": [
                {"dealVerifyNextAt": {"$lte": now}},
                {"dealVerifyNextAt": {"$exists": False}},
                {"dealVerifyNextAt": ""},
            ]},
            {"$or": [
                {"dealVerifyAttemptsDate": {"$ne": today}},
                {"dealVerifyAttemptsToday": {"$lt": MAX_ATTEMPTS_PER_DAY}},
                {"dealVerifyAttemptsToday": {"$exists": False}},
            ]},
        ],
    }
    rows = await _db().leads.find(q).sort("dealVerifyNextAt", 1).to_list(200)
    placed = skipped = failed = 0
    reasons = []
    for lead in rows:
        if placed + failed + skipped >= limit:
            break
        if not _is_booked(lead):
            skipped += 1
            continue
        res = await place_verify_call(lead["leadId"], force=force)
        if res.get("ok") and not res.get("skipped"):
            placed += 1
        elif res.get("skipped") or res.get("reason") in ("quiet-hours", "day-cap", "paused", "already-answered"):
            skipped += 1
        else:
            failed += 1
            reasons.append(res.get("reason") or "failed")
    return {"ok": True, "placed": placed, "skipped": skipped, "failed": failed, "reasons": reasons[:8]}


async def list_queue(filter: str = "mismatch", limit: int = 300) -> list:
    q = {"dealCancelled": {"$ne": True}}
    if filter == "mismatch":
        q["dealVerifyMismatch"] = True
    elif filter == "listening":
        q["dealVerifyStatus"] = "listening"
        q["dealVerifyRecordingUrl"] = {"$ne": ""}
    elif filter == "pending":
        q["dealVerifyStatus"] = {"$in": ["pending", "calling", "failed", "queued"]}
        q["$or"] = [{"dealVerifyAmount": {"$exists": False}}, {"dealVerifyAmount": 0}, {"dealVerifyAmount": ""}]
    elif filter == "answered":
        q["dealVerifyStatus"] = "answered"
    rows = await _db().leads.find(q, {
        "_id": 0,
        "leadId": 1, "customerName": 1, "mobile": 1, "executive": 1,
        "currentStatus": 1, "bookingDate": 1,
        "totalReceived": 1, "customerPayable": 1, "cxDemand": 1, "budget": 1,
        "dealVerifyStatus": 1, "dealVerifyAmount": 1, "dealVerifySource": 1,
        "dealVerifyRecordingUrl": 1, "dealVerifyMismatch": 1, "dealVerifyMismatchKind": 1,
        "dealVerifyAttempts": 1, "dealVerifyLastAt": 1, "dealVerifyNextAt": 1,
        "dealVerifyPaused": 1, "dealVerifyTranscript": 1,
    }).sort("dealVerifyLastAt", -1).to_list(limit)
    out = []
    for r in rows:
        if filter != "answered" and not _is_booked(r):
            continue
        out.append(r)
        if len(out) >= limit:
            break
    return out


async def scheduler_loop():
    await asyncio.sleep(20)
    while True:
        try:
            cfg = await get_config()
            if cfg.get("enabled") and in_quiet_hours(now_ist(), cfg):
                await run_due_calls(limit=15)
        except Exception:
            logger.exception("exotel scheduler tick failed")
        await asyncio.sleep(15 * 60)
