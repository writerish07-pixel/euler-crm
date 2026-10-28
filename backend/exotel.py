"""Akar Euler calls via Exotel.

Booked leads get a Hindi amount check from the dealership ExoPhone. Automatic
calling stops when the customer picks up, or after three calls with no answer.
A stored amount still flags a mismatch vs receipts on the file.

After the Google-review WhatsApp for a delivered file has actually been sent,
one separate call plays a short Hindi line and hangs up. It does not ask for
an amount, and it does not count toward the three booking calls.

Never blocks Convert to Booking or Mark Delivered. Secrets live in Settings.
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
# Lifetime automatic booking calls. Picking up stops earlier. Staff Call now
# can still dial after this, without scheduling another automatic call.
MAX_VERIFY_ATTEMPTS = 3
SLACK_RUPEES = 100
AUDIO_DIR = Path(__file__).parent / "static" / "exotel"
# First-upload verify clips. The build script skips these so they are not replaced.
AUDIO_CLIPS = ("intro", "prompt", "speak", "thanks")
REVIEW_CLIP = "review"

# Same words as the first-upload MP3s (do not regenerate those clips).
SPOKEN = {
    "intro": (
        "Namaste. Akar Euler se baat ho rahi hai. "
        "Aapki booking ke baare mein ek chhoti si pushti hai."
    ),
    "prompt": (
        "Aapne showroom mein jitna bhugtan kiya hai, woh rashi keypad par type karke hash dabaiye. "
        "Type nahi kar sakte to rashi bolkar bata dijiye."
    ),
    "speak": "Kripya ab rashi bol kar bataiye.",
    "thanks": "Dhanyavaad. Akar Euler.",
    "review": (
        "Namaskar, main Akar Euler se bol raha hoon. "
        "Humne aapko WhatsApp par Google review dene ke liye ek link bheja hai. "
        "Kripya us link par jaakar humein apna review dein. Dhanyavaad!"
    ),
}

# Devanagari used only if the original clips are rebuilt.
SPOKEN_HI = {
    "intro": (
        "नमस्ते। आकर यूलर से बात हो रही है। "
        "आपकी बुकिंग के बारे में एक छोटी सी पुष्टि है।"
    ),
    "prompt": (
        "आपने शोरूम में जितना भुगतान किया है, वो राशि कीपैड पर टाइप करके हैश दबाइये। "
        "टाइप नहीं कर सकते तो राशि बोलकर बता दीजिये।"
    ),
    "speak": "कृपया अब राशि बोल कर बताइये।",
    "thanks": "धन्यवाद। आकर यूलर।",
    "review": (
        "नमस्कार, मैं आकर Euler से बोल रहा हूँ। "
        "हमने आपको व्हाट्सऐप पर गूगल रिव्यू देने के लिए एक लिंक भेजा है। "
        "कृपया उस लिंक पर जाकर हमें अपना रिव्यू दें। धन्यवाद!"
    ),
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


def next_calling_morning(when: Optional[datetime] = None, cfg: Optional[dict] = None) -> datetime:
    """10:15 IST on the next calling morning. Same-day three-hour gaps are not used."""
    t = when or now_ist()
    start = int((cfg or {}).get("quietStart") or DEFAULT_QUIET_START)
    if t.hour < start or (t.hour == start and t.minute < 15):
        return t.replace(hour=start, minute=15, second=0, microsecond=0)
    return (t + timedelta(days=1)).replace(hour=start, minute=15, second=0, microsecond=0)


def _verify_followup_at(placed_attempts: int, cfg: Optional[dict]) -> str:
    """When the next automatic booking call should ring.

    After call 1 with no answer: about three hours later, or the next morning
    if that falls outside the window. After call 2: the next calling morning
    only. After call 3: stop.
    """
    if placed_attempts >= MAX_VERIFY_ATTEMPTS:
        return ""
    if placed_attempts >= 2:
        return as_utc_iso(next_calling_morning(now_ist(), cfg))
    return as_utc_iso(next_slot(now_ist(), cfg))


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
    if safe not in set(AUDIO_CLIPS) | {REVIEW_CLIP}:
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


def exoml_review(cfg: dict) -> str:
    """Google-review line, then hang up. No keypad and no amount recording."""
    line = _play_or_say(cfg, REVIEW_CLIP, SPOKEN[REVIEW_CLIP])
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        "<Response>"
        f"{line}"
        "<Hangup/>"
        "</Response>"
    )


def _url_with(url: str, **params) -> str:
    extra = "&".join(f"{key}={value}" for key, value in params.items() if value)
    if not extra:
        return url
    return url + ("&" if "?" in url else "?") + extra


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


async def _place_call_http(cfg: dict, customer: str, lead_id: str, *, purpose: str = "verify") -> dict:
    """Connect-to-flow only. Do not send Record/To — those belong to connect-two-numbers.

    Booking verify uses the App Bazaar flow when one is saved. The review call
    uses the CRM voice URL so the customer hears the review line and not the
    amount prompt.
    """
    urls = webhook_urls(cfg)
    sid = cfg["accountSid"]
    if purpose == "review":
        flow = _url_with(urls["voice"], purpose="review")
        status_cb = _url_with(urls["status"], purpose="review")
        custom = f"review:{lead_id}"
        time_limit = "60"
    else:
        flow = connect_flow_url(cfg)
        status_cb = urls["status"]
        custom = lead_id
        time_limit = "120"
    data = {
        "From": india_dial(customer),
        "CallerId": cfg["exoPhone"],
        "Url": flow,
        "StatusCallback": status_cb,
        "CustomField": custom,
        "CallType": "trans",
        "TimeLimit": time_limit,
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
    # A new booking starts its own three-call cycle. The historical sweep does not.
    await _apply(lead_id, {
        "dealVerifyStatus": "pending",
        "dealVerifyPaused": False,
        "dealVerifyNextAt": due,
        "dealVerifyLastStatus": "queued",
        "dealVerifyAttempts": 0,
        "dealVerifyAttemptsToday": 0,
        "dealVerifyAttemptsDate": "",
        "dealVerifyAutoStop": False,
    })
    return {"ok": True, "nextAt": due}


async def enqueue_unverified_booked(limit: int = 400) -> dict:
    """Queue every booked file that has not yet given an amount.

    Convert-to-booking queues new files. The scheduler / cron also call this
    so the booked register is auto-called without staff tapping Call now.
    Does not place the calls.
    """
    q = {
        "dealCancelled": {"$ne": True},
        "dealVerifyPaused": {"$ne": True},
        "dealVerifyAutoStop": {"$ne": True},
        "dealVerifyStatus": {"$nin": [
            "pending", "calling", "failed", "queued", "listening", "answered",
            "paused", "picked-up", "exhausted",
        ]},
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
        if lead.get("dealVerifyAutoStop"):
            continue
        if int(lead.get("dealVerifyAttempts") or 0) >= MAX_VERIFY_ATTEMPTS:
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
    already = int(lead.get("dealVerifyAttempts") or 0)
    status_now = str(lead.get("dealVerifyStatus") or "")
    stopped = bool(lead.get("dealVerifyAutoStop")) or status_now in ("picked-up", "exhausted", "listening")
    if not force:
        if status_now in ("picked-up", "listening"):
            return {"ok": True, "skipped": "picked-up"}
        if status_now == "exhausted" or already >= MAX_VERIFY_ATTEMPTS or lead.get("dealVerifyAutoStop"):
            await _apply(lead_id, {
                "dealVerifyStatus": "exhausted",
                "dealVerifyNextAt": "",
                "dealVerifyAutoStop": True,
            })
            return {"ok": False, "reason": "attempt-cap"}
        if not in_quiet_hours(now_ist(), cfg):
            due = as_utc_iso(next_slot(now_ist(), cfg))
            await _apply(lead_id, {"dealVerifyNextAt": due, "dealVerifyStatus": "pending"})
            return {"ok": False, "reason": "quiet-hours", "nextAt": due}
    today = today_ist()
    today_n = _attempts_today(lead) + 1
    total_n = already + 1
    result = await _place_call_http(cfg, mobile, lead_id)
    # Staff Call now after pickup or after the three calls must not restart the loop.
    if force and (stopped or already >= MAX_VERIFY_ATTEMPTS):
        due = ""
        auto_stop = True
    else:
        due = _verify_followup_at(total_n, cfg)
        auto_stop = False
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
        "dealVerifyAutoStop": auto_stop,
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
        "dealVerifyAutoStop": True,
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
    """Customer picked up and spoke, but no amount was parsed. Keep the tape and stop auto-dial."""
    if not recording_url:
        return {"ok": False, "reason": "no-recording"}
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if parse_amount(lead.get("dealVerifyAmount")):
        if recording_url:
            await _apply(lead_id, {"dealVerifyRecordingUrl": recording_url})
        return {"ok": True, "skipped": "already-answered"}
    lead = await _apply(lead_id, {
        "dealVerifyStatus": "listening",
        "dealVerifyRecordingUrl": recording_url,
        "dealVerifyCallSid": call_sid or lead.get("dealVerifyCallSid") or "",
        "dealVerifyLastAt": now_iso(),
        "dealVerifyLastStatus": "recorded",
        "dealVerifyNextAt": "",
        "dealVerifyAutoStop": True,
    })
    return {"ok": True, "leadId": lead_id, **snapshot(lead)}


def _lead_id_from_token(val: str) -> str:
    raw = str(val or "").strip()
    if raw.startswith("review:"):
        raw = raw.split(":", 1)[1].strip()
    return raw if raw.startswith("LD") else ""


def call_purpose(form: dict) -> str:
    if str(form.get("purpose") or "").strip().lower() == "review":
        return "review"
    for key in ("CustomField", "customField", "custom_field"):
        if str(form.get(key) or "").strip().startswith("review:"):
            return "review"
    return "verify"


def _pick_lead_id(form: dict, custom: str = "") -> str:
    for key in ("CustomField", "customField", "custom_field", "leadId", "LeadId"):
        found = _lead_id_from_token(str(form.get(key) or ""))
        if found:
            return found
    return _lead_id_from_token(custom)


async def _lead_for_call(form: dict) -> Optional[dict]:
    db = _db()
    sid = str(form.get("CallSid") or form.get("Sid") or form.get("callSid") or "").strip()
    lid = _pick_lead_id(form)
    if lid:
        return await db.leads.find_one({"leadId": lid})
    if sid and call_purpose(form) == "review":
        found = await db.leads.find_one({"reviewCallSid": sid})
        if found:
            return found
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


_MISSED_STATUSES = {"failed", "busy", "no-answer", "no_answer", "canceled", "cancelled"}


async def _handle_review_status(form: dict, lead: dict) -> dict:
    """A review call never schedules another try and never touches deal-verify."""
    status = str(form.get("Status") or form.get("DialCallStatus") or "").lower()
    sid = str(form.get("CallSid") or form.get("Sid") or "")
    updates = {
        "reviewCallLastStatus": status,
        "reviewCallLastAt": now_iso(),
        "reviewCallSid": sid or lead.get("reviewCallSid") or "",
        "reviewCallNextAt": "",
        "reviewCallAttempts": max(1, int(lead.get("reviewCallAttempts") or 0)),
    }
    if status in ("completed", "answered"):
        updates["reviewCallStatus"] = "done"
    elif status in _MISSED_STATUSES:
        updates["reviewCallStatus"] = "missed"
    else:
        updates["reviewCallStatus"] = "calling"
    await _apply(lead["leadId"], updates)
    return {"ok": True, "leadId": lead["leadId"], "purpose": "review", "status": status}


async def handle_status(form: dict) -> dict:
    lead = await _lead_for_call(form)
    if not lead:
        return {"ok": True, "ignored": True}
    if call_purpose(form) == "review":
        return await _handle_review_status(form, lead)
    if parse_amount(lead.get("dealVerifyAmount")):
        return {"ok": True, "skipped": "already-answered"}
    status = str(form.get("Status") or form.get("DialCallStatus") or "").lower()
    rec = str(form.get("RecordingUrl") or "")
    sid = str(form.get("CallSid") or form.get("Sid") or "")
    cfg = await get_config()
    attempts = int(lead.get("dealVerifyAttempts") or 0)
    base = {
        "dealVerifyLastStatus": status or lead.get("dealVerifyLastStatus") or "",
        "dealVerifyLastAt": now_iso(),
        "dealVerifyCallSid": sid or lead.get("dealVerifyCallSid") or "",
    }
    if rec and not lead.get("dealVerifyRecordingUrl"):
        base["dealVerifyRecordingUrl"] = rec
    # Pickup stops the automatic caller even when no amount was stored.
    if status in ("completed", "answered") or (rec and status not in _MISSED_STATUSES and status not in ("in-progress", "ringing", "queued")):
        updates = {
            **base,
            "dealVerifyStatus": "listening" if (rec or lead.get("dealVerifyRecordingUrl")) else "picked-up",
            "dealVerifyNextAt": "",
            "dealVerifyAutoStop": True,
        }
        await _apply(lead["leadId"], updates)
        return {"ok": True, "leadId": lead["leadId"], "status": status, "stopped": True}
    if status in ("in-progress", "ringing", "queued"):
        await _apply(lead["leadId"], {**base, "dealVerifyStatus": "calling"})
        return {"ok": True, "leadId": lead["leadId"], "status": status}
    if lead.get("dealVerifyAutoStop"):
        kept = "exhausted" if attempts >= MAX_VERIFY_ATTEMPTS else (
            "listening" if lead.get("dealVerifyRecordingUrl") else "picked-up"
        )
        if str(lead.get("dealVerifyStatus") or "") == "calling":
            next_status = kept
        else:
            next_status = str(lead.get("dealVerifyStatus") or kept)
        await _apply(lead["leadId"], {
            **base,
            "dealVerifyStatus": next_status,
            "dealVerifyNextAt": "",
            "dealVerifyAutoStop": True,
        })
        return {"ok": True, "leadId": lead["leadId"], "status": status, "stopped": True}
    if status in _MISSED_STATUSES:
        due = _verify_followup_at(attempts, cfg)
        updates = {**base, "dealVerifyNextAt": due}
        if due:
            updates["dealVerifyStatus"] = "pending"
            updates["dealVerifyAutoStop"] = False
        else:
            updates["dealVerifyStatus"] = "exhausted"
            updates["dealVerifyAutoStop"] = True
        await _apply(lead["leadId"], updates)
        return {"ok": True, "leadId": lead["leadId"], "status": status}
    await _apply(lead["leadId"], base)
    return {"ok": True, "leadId": lead["leadId"], "status": status}


async def pause_lead(lead_id: str, paused: bool = True) -> dict:
    current = await _db().leads.find_one({"leadId": lead_id}) or {}
    cfg = await get_config()
    blocked = (
        current.get("dealVerifyAutoStop")
        or int(current.get("dealVerifyAttempts") or 0) >= MAX_VERIFY_ATTEMPTS
        or parse_amount(current.get("dealVerifyAmount"))
    )
    if paused:
        updates = {
            "dealVerifyPaused": True,
            "dealVerifyStatus": "paused",
            "dealVerifyNextAt": "",
        }
    elif blocked:
        updates = {"dealVerifyPaused": False, "dealVerifyNextAt": ""}
    else:
        updates = {
            "dealVerifyPaused": False,
            "dealVerifyStatus": "pending",
            "dealVerifyNextAt": as_utc_iso(next_slot(now_ist(), cfg)),
        }
    lead = await _apply(lead_id, updates)
    return snapshot(lead or {})


async def run_due_calls(limit: int = 25, *, force: bool = False) -> dict:
    cfg = await get_config()
    if not cfg.get("enabled"):
        return {"ok": False, "reason": "exotel-not-configured", "placed": 0}
    if not force and not in_quiet_hours(now_ist(), cfg):
        return {"ok": True, "reason": "quiet-hours", "placed": 0}
    now = now_iso()
    q = {
        "dealCancelled": {"$ne": True},
        "dealVerifyPaused": {"$ne": True},
        "dealVerifyAutoStop": {"$ne": True},
        "$or": [
            {"dealVerifyAmount": {"$exists": False}},
            {"dealVerifyAmount": 0},
            {"dealVerifyAmount": None},
            {"dealVerifyAmount": ""},
        ],
        # Only files already marked for verify. Pickup, a saved tape, and a
        # finished three-call cycle stay out of this list.
        "dealVerifyStatus": {"$in": ["pending", "calling", "failed", "queued"]},
        "$and": [
            {"$or": [
                {"dealVerifyNextAt": {"$lte": now}},
                {"dealVerifyNextAt": {"$exists": False}},
                {"dealVerifyNextAt": ""},
            ]},
            {"$or": [
                {"dealVerifyAttempts": {"$lt": MAX_VERIFY_ATTEMPTS}},
                {"dealVerifyAttempts": {"$exists": False}},
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
        elif res.get("skipped") or res.get("reason") in (
            "quiet-hours", "attempt-cap", "paused", "already-answered", "picked-up",
        ):
            skipped += 1
        else:
            failed += 1
            reasons.append(res.get("reason") or "failed")
    return {"ok": True, "placed": placed, "skipped": skipped, "failed": failed, "reasons": reasons[:8]}


async def enqueue_review_call(lead_id: str) -> dict:
    """Queue the one Google-review call. Only after the WhatsApp link was sent."""
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if not lead:
        return {"ok": False, "reason": "missing-lead"}
    if len(digits10(lead.get("mobile"))) != 10:
        return {"ok": False, "reason": "no-mobile"}
    status = str(lead.get("reviewCallStatus") or "")
    if status in ("pending", "calling", "done", "missed") or int(lead.get("reviewCallAttempts") or 0) >= 1:
        return {"ok": True, "skipped": "already-queued"}
    cfg = await get_config()
    if not in_quiet_hours(now_ist(), cfg):
        due = as_utc_iso(next_calling_morning(now_ist(), cfg))
        await _apply(lead_id, {
            "reviewCallStatus": "pending",
            "reviewCallNextAt": due,
            "reviewCallAttempts": int(lead.get("reviewCallAttempts") or 0),
        })
        return {"ok": True, "queued": True, "nextAt": due}
    return await place_review_call(lead_id)


async def place_review_call(lead_id: str) -> dict:
    """Dial the review clip once. A missed call is not tried again."""
    cfg = await get_config()
    lead = await _db().leads.find_one({"leadId": lead_id}) or {}
    if not lead:
        return {"ok": False, "reason": "missing-lead"}
    if int(lead.get("reviewCallAttempts") or 0) >= 1 or str(lead.get("reviewCallStatus") or "") in (
        "calling", "done", "missed",
    ):
        return {"ok": True, "skipped": "already-called"}
    mobile = digits10(lead.get("mobile"))
    if len(mobile) != 10:
        return {"ok": False, "reason": "no-mobile"}
    if not cfg.get("enabled"):
        due = as_utc_iso(next_calling_morning(now_ist(), cfg))
        await _apply(lead_id, {"reviewCallStatus": "pending", "reviewCallNextAt": due})
        return {"ok": False, "reason": "exotel-not-configured", "nextAt": due}
    if not in_quiet_hours(now_ist(), cfg):
        due = as_utc_iso(next_calling_morning(now_ist(), cfg))
        await _apply(lead_id, {"reviewCallStatus": "pending", "reviewCallNextAt": due})
        return {"ok": False, "reason": "quiet-hours", "nextAt": due}
    result = await _place_call_http(cfg, mobile, lead_id, purpose="review")
    if result.get("ok"):
        await _apply(lead_id, {
            "reviewCallStatus": "calling",
            "reviewCallSid": result.get("callSid") or "",
            "reviewCallAttempts": 1,
            "reviewCallLastAt": now_iso(),
            "reviewCallLastStatus": result.get("status") or "queued",
            "reviewCallNextAt": "",
        })
    else:
        # The phone did not ring. Retry a few times for a blip, then stop.
        tries = int(lead.get("reviewCallApiTries") or 0) + 1
        reason = (result.get("reason") or "failed")[:180]
        if tries >= 6:
            await _apply(lead_id, {
                "reviewCallStatus": "missed",
                "reviewCallApiTries": tries,
                "reviewCallLastAt": now_iso(),
                "reviewCallLastStatus": reason,
                "reviewCallNextAt": "",
            })
        else:
            await _apply(lead_id, {
                "reviewCallStatus": "pending",
                "reviewCallApiTries": tries,
                "reviewCallLastAt": now_iso(),
                "reviewCallLastStatus": reason,
                "reviewCallNextAt": as_utc_iso(now_ist() + timedelta(minutes=15)),
            })
    return {**result, "leadId": lead_id, "purpose": "review"}


async def run_due_review_calls(limit: int = 25) -> dict:
    cfg = await get_config()
    if not cfg.get("enabled"):
        return {"ok": False, "reason": "exotel-not-configured", "placed": 0}
    if not in_quiet_hours(now_ist(), cfg):
        return {"ok": True, "reason": "quiet-hours", "placed": 0}
    now = now_iso()
    q = {
        "reviewCallStatus": "pending",
        "$and": [
            {"$or": [
                {"reviewCallAttempts": {"$lt": 1}},
                {"reviewCallAttempts": {"$exists": False}},
            ]},
            {"$or": [
                {"reviewCallNextAt": {"$lte": now}},
                {"reviewCallNextAt": ""},
                {"reviewCallNextAt": {"$exists": False}},
            ]},
        ],
    }
    rows = await _db().leads.find(q).sort("reviewCallNextAt", 1).to_list(max(limit * 4, 40))
    placed = skipped = failed = 0
    for lead in rows:
        if placed + skipped + failed >= limit:
            break
        res = await place_review_call(lead["leadId"])
        if res.get("ok") and not res.get("skipped"):
            placed += 1
        elif res.get("skipped") or res.get("reason") in ("quiet-hours", "exotel-not-configured"):
            skipped += 1
        else:
            failed += 1
    return {"ok": True, "placed": placed, "skipped": skipped, "failed": failed}


async def run_auto_calls(limit: int = 25, *, force: bool = False, enqueue_limit: int = 400) -> dict:
    """Queue every unverified booked file, then place due verify and review calls."""
    queued = await enqueue_unverified_booked(limit=enqueue_limit)
    placed = await run_due_calls(limit=limit, force=force)
    reviews = await run_due_review_calls(limit=limit)
    return {**placed, "queued": queued.get("queued", 0), "reviewPlaced": reviews.get("placed", 0)}


async def list_queue(filter: str = "mismatch", limit: int = 300) -> list:
    q = {"dealCancelled": {"$ne": True}}
    if filter == "mismatch":
        q["dealVerifyMismatch"] = True
    elif filter == "listening":
        q["dealVerifyStatus"] = {"$in": ["listening", "picked-up"]}
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
            if cfg.get("enabled"):
                await run_auto_calls(limit=25)
        except Exception:
            logger.exception("exotel scheduler tick failed")
        await asyncio.sleep(5 * 60)
