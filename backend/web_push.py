"""Optional Web Push for the installed PWA.

Owner / Sales GM who allow notifications on a phone (Home Screen app) get a
system notification when an executive submits a lead. If the browser refuses,
or this is iOS Safari without a standalone install, send is skipped — the
Approvals page in the app is the real gate.
"""
from __future__ import annotations

import base64
import json
import logging
from datetime import datetime, timezone

log = logging.getLogger("euler.web_push")

LEAD_APPROVER_ROLES = ("owner", "sales_gm")


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


async def ensure_vapid(db):
    """Persist a VAPID keypair so every Railway replica can send to the same subscribers."""
    doc = await db["system"].find_one({"_id": "web_push"}) or {}
    if doc.get("publicKey") and doc.get("privatePem"):
        return doc
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    key = ec.generate_private_key(ec.SECP256R1())
    raw_pub = key.public_key().public_bytes(
        serialization.Encoding.X962,
        serialization.PublicFormat.UncompressedPoint,
    )
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    patch = {
        "publicKey": _b64url(raw_pub),
        "privatePem": pem,
        "subject": "mailto:owner@euler.com",
        "createdAt": now_iso(),
    }
    await db["system"].update_one({"_id": "web_push"}, {"$set": patch}, upsert=True)
    return {**doc, **patch}


def public_key_from_doc(doc):
    return str((doc or {}).get("publicKey") or "")


async def save_subscription(db, user, subscription: dict):
    endpoint = str((subscription or {}).get("endpoint") or "").strip()
    keys = (subscription or {}).get("keys") or {}
    if not endpoint or not keys.get("p256dh") or not keys.get("auth"):
        raise ValueError("incomplete push subscription")
    uid = user.get("userId")
    await db.push_subscriptions.update_one(
        {"userId": uid, "endpoint": endpoint},
        {"$set": {
            "userId": uid,
            "role": user.get("role") or "",
            "email": user.get("email") or "",
            "endpoint": endpoint,
            "keys": {"p256dh": keys.get("p256dh"), "auth": keys.get("auth")},
            "updatedAt": now_iso(),
        }},
        upsert=True,
    )
    return {"ok": True}


async def drop_subscription(db, user, endpoint: str):
    await db.push_subscriptions.delete_many({
        "userId": user.get("userId"),
        "endpoint": str(endpoint or "").strip(),
    })
    return {"ok": True}


def _send_one(private_pem, subject, sub, payload: dict):
    from pywebpush import webpush, WebPushException
    webpush(
        subscription_info={
            "endpoint": sub["endpoint"],
            "keys": sub.get("keys") or {},
        },
        data=json.dumps(payload),
        vapid_private_key=private_pem,
        vapid_claims={"sub": subject or "mailto:owner@euler.com"},
    )


async def notify_lead_approvers(db, *, title: str, body: str, url: str = "/approvals"):
    """Best-effort. Never raises into the lead-request path."""
    try:
        vapid = await ensure_vapid(db)
        pem = vapid.get("privatePem")
        if not pem:
            return 0
        sent = 0
        async for sub in db.push_subscriptions.find({"role": {"$in": list(LEAD_APPROVER_ROLES)}}):
            try:
                _send_one(pem, vapid.get("subject"), sub, {
                    "title": title, "body": body, "url": url,
                })
                sent += 1
            except Exception as e:
                msg = str(e)
                # Gone / unsubscribed — drop the row so we stop retrying.
                if "410" in msg or "404" in msg or "unsubscribed" in msg.lower():
                    await db.push_subscriptions.delete_one({"_id": sub["_id"]})
                else:
                    log.info("web push skipped: %s", msg[:200])
        return sent
    except Exception:
        log.exception("web push notify failed")
        return 0
