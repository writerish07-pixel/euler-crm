"""Dealer Trade Advance (TA) — tranche register + finance auto-consume.

A TA draw credits the dealer from a financer (e.g. Shriram ₹1 Cr). Each
Finance-mode receipt on a lead for that financer consumes the oldest open
tranche (FIFO). WhatsApp daily / day-25 / low-balance alerts read this
collection; they never change customer payable by themselves.
"""
from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import commercial as ce

logger = logging.getLogger("euler.trade_advance")

COLLECTION = "trade_advances"
TENURE_DAYS = 30
DAY25_ALERT = 25
LOW_BALANCE_RS = 1_000_000.0  # ₹10 lakh per tranche
STATUS_OPEN = "Open"
STATUS_CLOSED = "Closed"


def _db():
    import server
    return server.db


def today_iso() -> str:
    import server
    return server.today()


def _parse_day(raw) -> Optional[date]:
    s = str(raw or "").strip()[:10]
    if len(s) != 10 or s[4] != "-" or s[7] != "-":
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def due_on(drawn_on: str) -> str:
    d = _parse_day(drawn_on) or date.today()
    return (d + timedelta(days=TENURE_DAYS)).isoformat()


def days_since_drawn(drawn_on: str, on: Optional[str] = None) -> int:
    start = _parse_day(drawn_on)
    end = _parse_day(on) or date.today()
    if not start:
        return 0
    return max(0, (end - start).days)


def balance_of(doc: dict) -> float:
    drawn = ce.round2(ce.num(doc.get("drawnAmount")))
    consumed = ce.round2(ce.num(doc.get("consumed")))
    repaid = ce.round2(ce.num(doc.get("repaid")))
    return ce.round2(max(0.0, drawn - consumed - repaid))


def public_row(doc: dict, on: Optional[str] = None) -> dict:
    if not doc:
        return {}
    bal = balance_of(doc)
    drawn_on = str(doc.get("drawnOn") or "")[:10]
    return {
        "trancheId": doc.get("trancheId"),
        "financer": doc.get("financer") or "",
        "drawnAmount": ce.round2(ce.num(doc.get("drawnAmount"))),
        "drawnOn": drawn_on,
        "dueOn": str(doc.get("dueOn") or due_on(drawn_on))[:10],
        "consumed": ce.round2(ce.num(doc.get("consumed"))),
        "repaid": ce.round2(ce.num(doc.get("repaid"))),
        "balance": bal,
        "status": doc.get("status") or STATUS_OPEN,
        "reference": doc.get("reference") or "",
        "daysSinceDrawn": days_since_drawn(drawn_on, on),
        "daysLeft": max(0, TENURE_DAYS - days_since_drawn(drawn_on, on)),
        "whatsappDay25SentOn": doc.get("whatsappDay25SentOn") or "",
        "whatsappLowBalanceSentOn": doc.get("whatsappLowBalanceSentOn") or "",
    }


async def list_tranches(*, status: Optional[str] = None, financer: Optional[str] = None) -> list:
    filt = {}
    if status:
        filt["status"] = status
    if financer:
        filt["financer"] = str(financer).strip()
    rows = await _db()[COLLECTION].find(filt).sort([("drawnOn", 1), ("createdAt", 1)]).to_list(500)
    on = today_iso()
    return [public_row(r, on) for r in rows]


async def list_open(financer: Optional[str] = None) -> list:
    rows = await list_tranches(status=STATUS_OPEN, financer=financer)
    return [r for r in rows if r.get("balance", 0) > 0.01]


async def create_tranche(*, financer: str, amount: float, drawn_on: Optional[str] = None,
                         reference: str = "", act: Optional[dict] = None) -> dict:
    financer = str(financer or "").strip()
    amount = ce.round2(max(0.0, ce.num(amount)))
    if not financer:
        raise ValueError("Financer is required for Trade Advance")
    if amount <= 0:
        raise ValueError("Trade Advance amount must be greater than zero")
    drawn = str(drawn_on or today_iso())[:10]
    if not _parse_day(drawn):
        raise ValueError("drawnOn must be YYYY-MM-DD")
    tranche_id = f"TA{uuid.uuid4().hex[:10].upper()}"
    doc = {
        "trancheId": tranche_id,
        "financer": financer,
        "drawnAmount": amount,
        "drawnOn": drawn,
        "dueOn": due_on(drawn),
        "consumed": 0.0,
        "repaid": 0.0,
        "status": STATUS_OPEN,
        "reference": str(reference or "").strip(),
        "adjustments": [],
        "whatsappDay25SentOn": "",
        "whatsappLowBalanceSentOn": "",
        "createdAt": datetime.now(timezone.utc).isoformat(),
        "createdBy": (act or {}).get("email") or "",
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
    }
    await _db()[COLLECTION].insert_one(doc)
    return public_row(doc)


async def _open_fifo(financer: str) -> list:
    """Oldest open tranches for this financer with remaining balance."""
    name = str(financer or "").strip().lower()
    if not name:
        return []
    rows = await _db()[COLLECTION].find({"status": STATUS_OPEN}).sort(
        [("drawnOn", 1), ("createdAt", 1)]).to_list(200)
    out = []
    for r in rows:
        if str(r.get("financer") or "").strip().lower() != name:
            continue
        if balance_of(r) <= 0.01:
            continue
        out.append(r)
    return out


async def consume_for_finance(*, financer: str, amount: float, lead_id: str = "",
                              receipt_number: str = "", finance_file_number: str = "",
                              customer_name: str = "") -> dict:
    """FIFO-consume open TA for this financer. Does not touch customer payable.

    Returns {adjusted, trancheId, remainingOnTranche, openBalanceForFinancer}.
    """
    want = ce.round2(max(0.0, ce.num(amount)))
    if want <= 0 or not str(financer or "").strip():
        return {"adjusted": 0.0, "trancheId": "", "splits": []}
    left = want
    splits = []
    for row in await _open_fifo(financer):
        if left <= 0.01:
            break
        bal = balance_of(row)
        take = ce.round2(min(bal, left))
        if take <= 0.01:
            continue
        new_consumed = ce.round2(ce.num(row.get("consumed")) + take)
        patch = {
            "consumed": new_consumed,
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
        }
        adj = {
            "at": datetime.now(timezone.utc).isoformat(),
            "amount": take,
            "leadId": lead_id,
            "receiptNumber": receipt_number,
            "financeFileNumber": finance_file_number,
            "customerName": customer_name,
        }
        await _db()[COLLECTION].update_one(
            {"trancheId": row["trancheId"]},
            {"$set": patch, "$push": {"adjustments": adj}},
        )
        # Auto-close when fully used (no repay needed).
        fresh = await _db()[COLLECTION].find_one({"trancheId": row["trancheId"]})
        if fresh and balance_of(fresh) <= 0.01:
            await _db()[COLLECTION].update_one(
                {"trancheId": row["trancheId"]},
                {"$set": {"status": STATUS_CLOSED, "closedAt": datetime.now(timezone.utc).isoformat(),
                          "closedReason": "consumed"}},
            )
        splits.append({"trancheId": row["trancheId"], "amount": take})
        left = ce.round2(left - take)
    adjusted = ce.round2(want - left)
    open_bal = ce.round2(sum(r["balance"] for r in await list_open(financer)))
    return {
        "adjusted": adjusted,
        "trancheId": (splits[0]["trancheId"] if splits else ""),
        "splits": splits,
        "openBalanceForFinancer": open_bal,
    }


async def release_for_receipt(receipt_number: str) -> float:
    """Undo TA consume when a Finance receipt is deleted. Returns amount released."""
    rn = str(receipt_number or "").strip()
    if not rn:
        return 0.0
    released = 0.0
    rows = await _db()[COLLECTION].find({"adjustments.receiptNumber": rn}).to_list(50)
    for row in rows:
        keep = []
        give_back = 0.0
        for adj in (row.get("adjustments") or []):
            if str(adj.get("receiptNumber") or "") == rn:
                give_back = ce.round2(give_back + ce.num(adj.get("amount")))
            else:
                keep.append(adj)
        if give_back <= 0:
            continue
        new_consumed = ce.round2(max(0.0, ce.num(row.get("consumed")) - give_back))
        patch = {
            "consumed": new_consumed,
            "adjustments": keep,
            "lastUpdated": datetime.now(timezone.utc).isoformat(),
            "status": STATUS_OPEN,
        }
        patch.pop("closedAt", None)
        await _db()[COLLECTION].update_one(
            {"trancheId": row["trancheId"]},
            {"$set": patch, "$unset": {"closedAt": "", "closedReason": ""}},
        )
        released = ce.round2(released + give_back)
    return released


async def repay_tranche(tranche_id: str, amount: float, *, act: Optional[dict] = None) -> dict:
    """Dealer pays leftover TA back to the financer (clear for new draw)."""
    row = await _db()[COLLECTION].find_one({"trancheId": tranche_id})
    if not row:
        raise ValueError("Trade Advance tranche not found")
    pay = ce.round2(max(0.0, ce.num(amount)))
    bal = balance_of(row)
    if pay <= 0:
        raise ValueError("Repay amount must be greater than zero")
    if pay > bal + 0.01:
        raise ValueError(f"Repay ₹{pay} exceeds balance ₹{bal}")
    new_repaid = ce.round2(ce.num(row.get("repaid")) + pay)
    patch = {
        "repaid": new_repaid,
        "lastUpdated": datetime.now(timezone.utc).isoformat(),
        "lastRepaidBy": (act or {}).get("email") or "",
    }
    await _db()[COLLECTION].update_one({"trancheId": tranche_id}, {"$set": patch})
    fresh = await _db()[COLLECTION].find_one({"trancheId": tranche_id})
    if fresh and balance_of(fresh) <= 0.01:
        await _db()[COLLECTION].update_one(
            {"trancheId": tranche_id},
            {"$set": {"status": STATUS_CLOSED, "closedAt": datetime.now(timezone.utc).isoformat(),
                      "closedReason": "repaid"}},
        )
        fresh = await _db()[COLLECTION].find_one({"trancheId": tranche_id})
    return public_row(fresh)


def format_open_summary(rows: list) -> str:
    """Single-line summary for WhatsApp template variables (no newlines)."""
    parts = []
    for r in rows or []:
        parts.append(
            f"{r.get('financer') or '—'} drawn {r.get('drawnOn')} due {r.get('dueOn')} "
            f"drawn Rs {ce.round2(r.get('drawnAmount')):,.0f} "
            f"consumed Rs {ce.round2(r.get('consumed')):,.0f} "
            f"bal Rs {ce.round2(r.get('balance')):,.0f} "
            f"days left {r.get('daysLeft')}"
        )
    return " | ".join(parts) if parts else "No open Trade Advance"


async def mark_whatsapp(tranche_id: str, field: str, day: str):
    if field not in ("whatsappDay25SentOn", "whatsappLowBalanceSentOn"):
        return
    await _db()[COLLECTION].update_one(
        {"trancheId": tranche_id},
        {"$set": {field: day, "lastUpdated": datetime.now(timezone.utc).isoformat()}},
    )


async def ensure_indexes():
    try:
        await _db()[COLLECTION].create_index("trancheId", unique=True)
        await _db()[COLLECTION].create_index([("status", 1), ("financer", 1), ("drawnOn", 1)])
        await _db()[COLLECTION].create_index("adjustments.receiptNumber")
    except Exception:
        logger.exception("trade_advance index ensure failed")
