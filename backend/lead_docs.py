"""Lead document store — KYC, delivery scans, Tally GST invoice, refund cheques.

Railway's disk is ephemeral, so files live in MongoDB (BSON binary on the
`lead_documents` row). They are never written to Google Sheets. The OEM finance
allowlist must NOT gain these routes — Aadhaar / PAN / GST / cheques stay inside
the dealership.
"""
from __future__ import annotations

import io
import re
from datetime import datetime, timezone

from bson.binary import Binary
from fastapi import HTTPException, UploadFile
from fastapi.responses import StreamingResponse

import auth as authmod

MAX_BYTES = 5 * 1024 * 1024
COLLECTION = "lead_documents"

KINDS = {
    "kyc_aadhaar_front": {"group": "kyc", "label": "Aadhaar front", "unique": True},
    "kyc_aadhaar_back": {"group": "kyc", "label": "Aadhaar back", "unique": True},
    "kyc_pan": {"group": "kyc", "label": "PAN", "unique": True},
    "kyc_gst": {"group": "kyc", "label": "GST certificate", "unique": True},
    "delivery_insurance": {"group": "delivery", "label": "Insurance copy", "unique": True},
    "delivery_rto": {"group": "delivery", "label": "RTO / Registration", "unique": True},
    "tally_invoice": {"group": "tally", "label": "Tally GST invoice", "unique": True},
    "refund_cheque": {"group": "refund", "label": "Refund cheque", "unique": False},
    "oem_extra_support": {
        "group": "oem_extra",
        "label": "OEM Extra Support email (ASM / RM)",
        "unique": True,
    },
}

KYC_INDIVIDUAL = ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan")
# B2B is a firm: PAN + GST are required. Aadhaar is optional (may still be attached).
KYC_B2B = ("kyc_pan", "kyc_gst")
KYC_B2B_OPTIONAL = ("kyc_aadhaar_front", "kyc_aadhaar_back")

ALLOWED_TYPES = {
    "image/jpeg", "image/jpg", "image/png", "image/webp", "image/heic", "image/heif",
    "application/pdf",
}
EXT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".pdf": "application/pdf",
}

_META_PROJ = {"data": 0}


def normalize_customer_type(value) -> str:
    t = str(value or "Individual").strip().lower()
    if t in ("b2b", "business", "gst", "company", "firm"):
        return "B2B"
    return "Individual"


def required_kyc_kinds(customer_type) -> tuple:
    if normalize_customer_type(customer_type) == "B2B":
        return KYC_B2B
    return KYC_INDIVIDUAL


def _role(user) -> str:
    return str((user or {}).get("role") or "").strip().lower()


def can_read_kind(user, kind: str, *, own: bool = False) -> bool:
    info = KINDS.get(kind)
    if not info:
        return False
    role = _role(user)
    if role in authmod.FIELD_ROLES or role in authmod.EXTERNAL_ROLES:
        return False
    group = info["group"]
    if group == "kyc":
        if role in ("owner", "sales_gm", "tl", "accounts"):
            return True
        return role == "executive" and own
    if group == "oem_extra":
        if role in ("owner", "sales_gm", "tl", "accounts"):
            return True
        return role == "executive" and own
    if group == "delivery":
        return role in ("owner", "sales_gm", "tl", "accounts")
    if group == "tally":
        return role in ("owner", "sales_gm", "tl", "accounts")
    if group == "refund":
        return role in ("owner", "tl", "accounts")
    return False


def can_upload_kind(user, kind: str, *, own: bool = False) -> bool:
    info = KINDS.get(kind)
    if not info:
        return False
    role = _role(user)
    if role in authmod.FIELD_ROLES or role in authmod.EXTERNAL_ROLES:
        return False
    group = info["group"]
    if group == "kyc":
        if role in ("owner", "sales_gm", "tl"):
            return True
        return role == "executive" and own
    if group == "oem_extra":
        if role in ("owner", "sales_gm", "tl"):
            return True
        return role == "executive" and own
    if group == "delivery":
        return role in authmod.DEAL_DESK_ROLES
    if group == "tally":
        return role in ("owner", "accounts")
    if group == "refund":
        return role in authmod.MONEY_ROLES
    return False


def public_row(doc) -> dict:
    if not doc:
        return doc
    row = {k: v for k, v in doc.items() if k not in ("_id", "data")}
    info = KINDS.get(row.get("kind") or "", {})
    row["label"] = info.get("label") or row.get("kind")
    row["group"] = info.get("group") or ""
    return row


def _content_type(upload: UploadFile) -> str:
    raw = (upload.content_type or "").split(";")[0].strip().lower()
    name = (upload.filename or "").lower()
    if raw in ALLOWED_TYPES:
        return "image/jpeg" if raw == "image/jpg" else raw
    for ext, ctype in EXT_TYPES.items():
        if name.endswith(ext):
            return ctype
    raise HTTPException(422, "Upload a photo or PDF (JPEG, PNG, WebP, HEIC, PDF).")


async def read_upload(upload: UploadFile) -> tuple[bytes, str, str]:
    ctype = _content_type(upload)
    data = await upload.read()
    if not data:
        raise HTTPException(422, "The file is empty.")
    if len(data) > MAX_BYTES:
        raise HTTPException(422, "File is over 5 MB. Compress the photo or send a smaller PDF.")
    filename = (upload.filename or "document").strip() or "document"
    filename = re.sub(r"[^\w.\-]+", "_", filename)[:120]
    return data, ctype, filename


def _own_request(req, user) -> bool:
    if not req or not user:
        return False
    uid = user.get("userId") or ""
    email = (user.get("email") or "").strip().lower()
    return (uid and req.get("submittedByUserId") == uid) or (
        email and str(req.get("submittedBy") or "").strip().lower() == email)


async def missing_kyc(db, *, request_id: str = "", lead_id: str = "",
                      customer_type: str = "Individual", gstin: str = "") -> list:
    q = {"requestId": request_id} if request_id else {"leadId": lead_id}
    if not (request_id or lead_id):
        return list(required_kyc_kinds(customer_type))
    rows = await db[COLLECTION].find(q, _META_PROJ).to_list(50)
    have = {r.get("kind") for r in rows}
    missing = [k for k in required_kyc_kinds(customer_type) if k not in have]
    if normalize_customer_type(customer_type) == "B2B" and not str(gstin or "").strip():
        missing.append("gstin")
    return missing


async def has_oem_extra_proof(db, *, request_id: str = "", lead_id: str = "") -> bool:
    """True when the ASM/RM confirmation email is on the request or the live lead."""
    clauses = []
    if request_id:
        clauses.append({"requestId": request_id, "kind": "oem_extra_support"})
    if lead_id:
        clauses.append({"leadId": lead_id, "kind": "oem_extra_support"})
    if not clauses:
        return False
    q = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    return await db[COLLECTION].find_one(q, _META_PROJ) is not None


async def list_docs(db, user, *, lead_id: str = "", request_id: str = "",
                    own: bool = False) -> list:
    if lead_id:
        q = {"leadId": lead_id}
    elif request_id:
        q = {"requestId": request_id}
    else:
        return []
    rows = await db[COLLECTION].find(q, _META_PROJ).sort("uploadedAt", 1).to_list(200)
    return [public_row(r) for r in rows if can_read_kind(user, r.get("kind") or "", own=own)]


async def get_meta(db, document_id: str):
    return await db[COLLECTION].find_one({"documentId": document_id}, _META_PROJ)


async def save_doc(db, *, next_id, user, kind: str, data: bytes, content_type: str,
                   filename: str, lead_id: str = "", request_id: str = "") -> dict:
    if kind not in KINDS:
        raise HTTPException(422, f"Unknown document kind '{kind}'.")
    info = KINDS[kind]
    if info["unique"]:
        q = {"kind": kind}
        if lead_id:
            q["leadId"] = lead_id
        if request_id:
            q["requestId"] = request_id
        await db[COLLECTION].delete_many(q)
    doc = {
        "documentId": await next_id("lead_document", "DC26"),
        "leadId": lead_id or "",
        "requestId": request_id or "",
        "kind": kind,
        "filename": filename,
        "contentType": content_type,
        "size": len(data),
        "uploadedBy": (user or {}).get("email") or "",
        "uploadedByName": (user or {}).get("name") or "",
        "uploadedAt": datetime.now(timezone.utc).isoformat(),
        "refundReceiptNumber": "",
        "data": Binary(data),
    }
    await db[COLLECTION].insert_one(dict(doc))
    return public_row(doc)


CREATE_DOC_KINDS = (
    *KYC_INDIVIDUAL, *KYC_B2B, *KYC_B2B_OPTIONAL, "oem_extra_support",
)


async def has_create_docs(db, lead_id: str) -> bool:
    if not lead_id:
        return False
    return await db[COLLECTION].find_one({
        "leadId": lead_id,
        "kind": {"$in": list(CREATE_DOC_KINDS)},
    }, _META_PROJ) is not None


async def copy_create_docs(db, *, next_id, from_lead_id: str, to_lead_id: str = "",
                           to_request_id: str = "", user=None, kinds=None) -> int:
    """Clone KYC + OEM Extra Support from one live lead onto another vehicle.

    Delivery, Tally and refund scans stay on the source file. Each copy is a
    new documentId so deleting one unit does not drop the sibling's papers.
    Pass to_request_id to park the copies on a pending approval request.
    """
    if not from_lead_id:
        return 0
    if to_lead_id and from_lead_id == to_lead_id:
        return 0
    if not to_lead_id and not to_request_id:
        return 0
    allow = set(kinds) if kinds else set(CREATE_DOC_KINDS)
    copied = 0
    seen = set()
    async for src in db[COLLECTION].find({"leadId": from_lead_id}):
        kind = src.get("kind") or ""
        if kind not in CREATE_DOC_KINDS or kind not in allow or kind in seen:
            continue
        seen.add(kind)
        raw = src.get("data") or b""
        if isinstance(raw, Binary):
            raw = bytes(raw)
        if not raw:
            continue
        if KINDS.get(kind, {}).get("unique"):
            q = {"kind": kind}
            if to_lead_id:
                q["leadId"] = to_lead_id
            if to_request_id:
                q["requestId"] = to_request_id
            await db[COLLECTION].delete_many(q)
        doc = {
            "documentId": await next_id("lead_document", "DC26"),
            "leadId": to_lead_id or "",
            "requestId": to_request_id or "",
            "kind": kind,
            "filename": src.get("filename") or "document",
            "contentType": src.get("contentType") or "application/octet-stream",
            "size": len(raw),
            "uploadedBy": (user or {}).get("email") or src.get("uploadedBy") or "",
            "uploadedByName": (user or {}).get("name") or src.get("uploadedByName") or "",
            "uploadedAt": datetime.now(timezone.utc).isoformat(),
            "refundReceiptNumber": "",
            "copiedFromLeadId": from_lead_id,
            "copiedFromDocumentId": src.get("documentId") or "",
            "data": Binary(raw),
        }
        await db[COLLECTION].insert_one(dict(doc))
        copied += 1
    return copied


async def attach_request_docs_to_lead(db, request_id: str, lead_id: str):
    await db[COLLECTION].update_many(
        {"requestId": request_id}, {"$set": {"leadId": lead_id}})


async def bind_refund_cheque(db, document_id: str, lead_id: str, receipt_number: str):
    await db[COLLECTION].update_one(
        {"documentId": document_id, "leadId": lead_id, "kind": "refund_cheque"},
        {"$set": {"refundReceiptNumber": receipt_number}},
    )


async def file_response(db, document_id: str, user, *, own: bool = False):
    doc = await db[COLLECTION].find_one({"documentId": document_id})
    if not doc:
        raise HTTPException(404, "Document not found")
    kind = doc.get("kind") or ""
    if not can_read_kind(user, kind, own=own):
        raise HTTPException(403, "You cannot open this document.")
    raw = doc.get("data") or b""
    if isinstance(raw, Binary):
        raw = bytes(raw)
    filename = doc.get("filename") or "document"
    ctype = doc.get("contentType") or "application/octet-stream"
    return StreamingResponse(
        io.BytesIO(raw),
        media_type=ctype,
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


async def delete_doc(db, document_id: str, user, *, own: bool = False) -> dict:
    doc = await db[COLLECTION].find_one({"documentId": document_id}, _META_PROJ)
    if not doc:
        raise HTTPException(404, "Document not found")
    kind = doc.get("kind") or ""
    if not can_upload_kind(user, kind, own=own):
        raise HTTPException(403, "You cannot replace this document.")
    await db[COLLECTION].delete_one({"documentId": document_id})
    return {"ok": True, "documentId": document_id}


def require_kind(kind: str) -> str:
    k = (kind or "").strip()
    if k not in KINDS:
        raise HTTPException(422, f"Unknown document kind '{kind}'.")
    return k
