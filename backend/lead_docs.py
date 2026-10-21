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

MAX_BYTES = 8 * 1024 * 1024
# Zip of Tally bills stays under Mongo's 16 MB BSON document limit.
ZIP_MAX_BYTES = 12 * 1024 * 1024
JPEG_MAGIC = b"\xff\xd8\xff"
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
PDF_MAGIC = b"%PDF"
WEBP_RIFF = b"RIFF"
WEBP_WEBP = b"WEBP"
COLLECTION = "lead_documents"
TALLY_KIND = "tally_invoice"
LEDGER_KIND = "tally_ledger"
TALLY_ZIP_KINDS = {TALLY_KIND, LEDGER_KIND}
ZIP_TYPES = {
    "application/zip",
    "application/x-zip-compressed",
    "application/x-zip",
}
ZIP_MAGIC = (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")

KINDS = {
    "kyc_aadhaar_front": {"group": "kyc", "label": "Aadhaar front", "unique": True},
    "kyc_aadhaar_back": {"group": "kyc", "label": "Aadhaar back", "unique": True},
    "kyc_pan": {"group": "kyc", "label": "PAN", "unique": True},
    "kyc_gst": {"group": "kyc", "label": "GST certificate", "unique": True},
    "delivery_insurance": {"group": "delivery", "label": "Insurance copy", "unique": True},
    "delivery_rto": {"group": "delivery", "label": "RTO / Registration", "unique": True},
    "tally_invoice": {"group": "tally", "label": "Tally GST invoice", "unique": True},
    "tally_ledger": {"group": "tally", "label": "Tally customer ledger", "unique": True},
    "refund_cheque": {"group": "refund", "label": "Refund cheque", "unique": False},
    "oem_extra_support": {
        "group": "oem_extra",
        "label": "OEM Extra Support email (ASM / RM)",
        "unique": True,
    },
    "deal_sheet": {
        "group": "deal",
        "label": "Deal sheet",
        "unique": True,
    },
}

KYC_INDIVIDUAL = ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan")
# B2B is a firm: PAN + GST are required. Aadhaar is optional (may still be attached).
KYC_B2B = ("kyc_pan", "kyc_gst")
KYC_B2B_OPTIONAL = ("kyc_aadhaar_front", "kyc_aadhaar_back")
EXTRA_SUPPORT_KIND = "oem_extra_support"
DEAL_SHEET_KIND = "deal_sheet"
# Vehicle paperwork is per unit on a same-order pack. KYC stays lead-level.
UNIT_SCOPED_KINDS = {
    "delivery_insurance",
    "delivery_rto",
    "deal_sheet",
    "tally_invoice",
    "tally_ledger",
    "oem_extra_support",
}

ALLOWED_TYPES = {
    "image/jpeg", "image/jpg", "image/pjpeg", "image/png", "image/webp",
    "image/heic", "image/heif", "application/pdf",
}
EXT_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".heic": "image/heic", ".heif": "image/heif",
    ".pdf": "application/pdf",
}
ZIP_EXT = ".zip"

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
        if role in ("owner", "sales_gm", "tl", "team_lead", "accounts"):
            return True
        return role == "executive" and own
    if group == "deal":
        if role in ("owner", "sales_gm", "tl", "team_lead", "accounts"):
            return True
        return role == "executive" and own
    if group == "oem_extra":
        if role in ("owner", "sales_gm", "tl", "team_lead", "accounts"):
            return True
        return role == "executive" and own
    if group == "delivery":
        return role in ("owner", "sales_gm", "tl", "team_lead", "accounts")
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
        if role in ("owner", "sales_gm", "tl", "team_lead"):
            return True
        return role == "executive" and own
    if group == "deal":
        if role in ("owner", "sales_gm", "tl", "team_lead"):
            return True
        return role == "executive" and own
    if group == "oem_extra":
        if role in ("owner", "sales_gm", "tl", "team_lead"):
            return True
        return role == "executive" and own
    if group == "delivery":
        return role in authmod.DEAL_DESK_ROLES
    if group == "tally":
        return role in ("owner", "accounts")
    if group == "refund":
        return role in authmod.MONEY_ROLES
    return False


def parse_unit_sno(kind: str, unit_sno) -> int | None:
    """KYC is always lead-level. Unit-scoped kinds keep a 1-based sno or None."""
    if kind not in UNIT_SCOPED_KINDS:
        return None
    if unit_sno in (None, "", 0, "0"):
        return None
    try:
        sno = int(unit_sno)
    except (TypeError, ValueError):
        raise HTTPException(422, "unitSno must be a unit number.")
    if sno < 1:
        raise HTTPException(422, "unitSno must be a unit number.")
    return sno


def parse_unit_snos(kind: str, unit_sno=None, unit_snos=None) -> list[int]:
    """Sorted unique 1-based snos. Ledger may cover several units; invoice is one."""
    if kind not in UNIT_SCOPED_KINDS:
        return []
    raw = unit_snos
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif raw is None:
        raw = []
    else:
        raw = list(raw)
    out = []
    for x in raw:
        sno = parse_unit_sno(kind, x)
        if sno:
            out.append(sno)
    one = parse_unit_sno(kind, unit_sno)
    if one:
        out.append(one)
    return sorted(set(out))


def doc_unit_snos(doc) -> list[int]:
    """Units a Tally / delivery scan belongs to. Empty = lead-level (legacy pack)."""
    raw = (doc or {}).get("unitSnos")
    if isinstance(raw, str):
        raw = [p.strip() for p in raw.replace(";", ",").split(",") if p.strip()]
    snos = []
    for x in list(raw or []):
        try:
            n = int(x)
        except (TypeError, ValueError):
            continue
        if n >= 1:
            snos.append(n)
    if snos:
        return sorted(set(snos))
    one = parse_unit_sno((doc or {}).get("kind") or "", (doc or {}).get("unitSno"))
    return [one] if one else []


def doc_matches_unit(doc, unit_sno) -> bool:
    """True when this scan belongs to unit_sno. Unit 1 also matches legacy (no sno)."""
    try:
        sno = int((doc or {}).get("unitSno") or 0)
    except (TypeError, ValueError):
        sno = 0
    try:
        want = int(unit_sno or 0)
    except (TypeError, ValueError):
        want = 0
    if want <= 0:
        return sno <= 0
    if sno == want:
        return True
    return want == 1 and sno <= 0


def unique_doc_filter(kind: str, *, lead_id: str = "", request_id: str = "",
                      unit_sno=None) -> dict:
    q = {"kind": kind}
    if lead_id:
        q["leadId"] = lead_id
    if request_id:
        q["requestId"] = request_id
    if kind in UNIT_SCOPED_KINDS:
        if unit_sno:
            q["unitSno"] = unit_sno
        else:
            q["$or"] = [
                {"unitSno": {"$in": [None, 0, ""]}},
                {"unitSno": {"$exists": False}},
            ]
    return q


def public_row(doc) -> dict:
    if not doc:
        return doc
    row = {k: v for k, v in doc.items() if k not in ("_id", "data")}
    info = KINDS.get(row.get("kind") or "", {})
    row["label"] = info.get("label") or row.get("kind")
    row["group"] = info.get("group") or ""
    sno = parse_unit_sno(row.get("kind") or "", row.get("unitSno"))
    snos = doc_unit_snos(row)
    if len(snos) > 1:
        row["unitSnos"] = snos
        row["unitSno"] = snos[0]
    elif sno:
        row["unitSno"] = sno
        row.pop("unitSnos", None)
    elif "unitSno" in row and not row.get("unitSno"):
        row.pop("unitSno", None)
        row.pop("unitSnos", None)
    return row


def _is_zip_name(name: str) -> bool:
    return str(name or "").lower().endswith(ZIP_EXT)


def _looks_like_zip(raw: str, name: str) -> bool:
    return raw in ZIP_TYPES or _is_zip_name(name)


def _sniff_content_type(data: bytes) -> str:
    """Windows Camera / File often sends application/octet-stream with no extension."""
    if not data:
        return ""
    if data.startswith(JPEG_MAGIC):
        return "image/jpeg"
    if data.startswith(PNG_MAGIC):
        return "image/png"
    if data.startswith(PDF_MAGIC):
        return "application/pdf"
    if data.startswith(WEBP_RIFF) and data[8:12] == WEBP_WEBP:
        return "image/webp"
    if data.startswith(ZIP_MAGIC):
        return "application/zip"
    # iPhone / Android camera often sends HEIC as octet-stream named "image".
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12].lower()
        if brand in (b"heic", b"heix", b"heif", b"mif1", b"msf1"):
            return "image/heic"
    return ""


def _content_type(upload: UploadFile, *, kind: str = "", data: bytes = b"") -> str:
    raw = (upload.content_type or "").split(";")[0].strip().lower()
    name = (upload.filename or "").lower()
    if kind in TALLY_ZIP_KINDS and _looks_like_zip(raw, name):
        return "application/zip"
    if raw in ALLOWED_TYPES:
        return "image/jpeg" if raw in ("image/jpg", "image/pjpeg") else raw
    for ext, ctype in EXT_TYPES.items():
        if name.endswith(ext):
            return ctype
    sniffed = _sniff_content_type(data)
    if sniffed == "application/zip" and kind in TALLY_ZIP_KINDS:
        return sniffed
    if sniffed in ALLOWED_TYPES or sniffed in ("image/jpeg", "image/png", "image/webp", "application/pdf"):
        return sniffed
    if kind == TALLY_KIND:
        raise HTTPException(422, "Upload a photo, PDF or ZIP of the Tally GST invoice.")
    if kind == LEDGER_KIND:
        raise HTTPException(422, "Upload a photo, PDF or ZIP of the Tally customer ledger.")
    raise HTTPException(422, "Upload a photo or PDF (JPEG, PNG, WebP, HEIC, PDF).")


def _max_bytes(ctype: str, kind: str) -> int:
    if kind in TALLY_ZIP_KINDS and ctype == "application/zip":
        return ZIP_MAX_BYTES
    return MAX_BYTES


async def read_upload(upload: UploadFile, *, kind: str = "") -> tuple[bytes, str, str]:
    data = await upload.read()
    if not data:
        raise HTTPException(422, "The file is empty.")
    ctype = _content_type(upload, kind=kind, data=data)
    limit = _max_bytes(ctype, kind)
    if len(data) > limit:
        if ctype == "application/zip":
            raise HTTPException(422, "ZIP is over 12 MB. Send a smaller archive.")
        raise HTTPException(422, "File is over 8 MB. Compress the photo or send a smaller PDF.")
    if ctype == "application/zip" and not data.startswith(ZIP_MAGIC):
        raise HTTPException(422, "That file is not a ZIP. Export the Tally bills as a .zip.")
    filename = (upload.filename or "document").strip() or "document"
    if filename in ("document", "blob", "image", "untitled"):
        ext = { "image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
                "application/pdf": ".pdf", "application/zip": ".zip" }.get(ctype)
        if ext and not filename.lower().endswith(ext):
            filename = f"oem-proof{ext}" if kind == EXTRA_SUPPORT_KIND else f"document{ext}"
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
    clauses = []
    if request_id:
        clauses.append({"requestId": request_id})
    if lead_id:
        clauses.append({"leadId": lead_id})
    if not clauses:
        return list(required_kyc_kinds(customer_type))
    q = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    rows = await db[COLLECTION].find(q, _META_PROJ).to_list(50)
    have = {r.get("kind") for r in rows}
    missing = [k for k in required_kyc_kinds(customer_type) if k not in have]
    if normalize_customer_type(customer_type) == "B2B" and not str(gstin or "").strip():
        # GST certificate on file is the GSTIN proof. The 15-digit number is
        # optional once kyc_gst is attached (OEM-created B2B files never had a
        # GSTIN capture step).
        if "kyc_gst" not in have:
            missing.append("gstin")
    return missing


def extra_support_required(amount) -> bool:
    try:
        return float(amount or 0) > 0.01
    except (TypeError, ValueError):
        return False


async def has_extra_support_proof(db, *, request_id: str = "", lead_id: str = "") -> bool:
    clauses = []
    if request_id:
        clauses.append({"requestId": request_id, "kind": EXTRA_SUPPORT_KIND})
    if lead_id:
        clauses.append({"leadId": lead_id, "kind": EXTRA_SUPPORT_KIND})
    if not clauses:
        return False
    q = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    return await db[COLLECTION].find_one(q, _META_PROJ) is not None


async def missing_related_docs(db, *, lead=None, request_id: str = "",
                               extra_received=None, require_kyc: bool = True) -> list:
    """KYC (and extra-support proof when Received > 0) still outstanding."""
    lead = lead or {}
    lead_id = lead.get("leadId") or ""
    missing = []
    if require_kyc:
        missing.extend(await missing_kyc(
            db, request_id=request_id, lead_id=lead_id,
            customer_type=lead.get("customerType") or "Individual",
            gstin=lead.get("gstin") or ""))
    extra = extra_received if extra_received is not None else lead.get("oemExtraSupportReceived")
    if extra_support_required(extra):
        if not await has_extra_support_proof(db, request_id=request_id, lead_id=lead_id):
            missing.append(EXTRA_SUPPORT_KIND)
    return missing


async def has_deal_sheet(db, *, request_id: str = "", lead_id: str = "") -> bool:
    have_req, have_lead = await deal_sheet_present(
        db, request_ids=[request_id] if request_id else [],
        lead_ids=[lead_id] if lead_id else [])
    return bool((request_id and request_id in have_req) or (lead_id and lead_id in have_lead))


async def deal_sheet_present(db, *, request_ids=(), lead_ids=()) -> tuple[set, set]:
    """Return (requestIds, leadIds) that already have a deal sheet."""
    have_req, have_lead = set(), set()
    reqs = [str(x).strip() for x in (request_ids or []) if str(x or "").strip()]
    lids = [str(x).strip() for x in (lead_ids or []) if str(x or "").strip()]
    clauses = []
    if reqs:
        clauses.append({"requestId": {"$in": reqs}, "kind": DEAL_SHEET_KIND})
    if lids:
        clauses.append({"leadId": {"$in": lids}, "kind": DEAL_SHEET_KIND})
    if not clauses:
        return have_req, have_lead
    q = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    for d in await db[COLLECTION].find(q, {"requestId": 1, "leadId": 1}).to_list(
            max(len(reqs) + len(lids) + 20, 50)):
        if d.get("requestId"):
            have_req.add(d["requestId"])
        if d.get("leadId"):
            have_lead.add(d["leadId"])
    return have_req, have_lead


def missing_doc_labels(kinds) -> str:
    labels = []
    for k in kinds or []:
        if k == "gstin":
            labels.append("GSTIN")
        else:
            labels.append((KINDS.get(k) or {}).get("label") or k)
    return ", ".join(labels)


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
                    own: bool = False, extra_request_ids=None) -> list:
    clauses = []
    if lead_id:
        clauses.append({"leadId": lead_id})
    if request_id:
        clauses.append({"requestId": request_id})
    for rid in extra_request_ids or []:
        rid = str(rid or "").strip()
        if rid:
            clauses.append({"requestId": rid})
    if not clauses:
        return []
    q = {"$or": clauses} if len(clauses) > 1 else clauses[0]
    rows = await db[COLLECTION].find(q, _META_PROJ).sort("uploadedAt", 1).to_list(400)
    seen, out = set(), []
    for r in rows:
        if not can_read_kind(user, r.get("kind") or "", own=own):
            continue
        did = str(r.get("documentId") or "")
        if did and did in seen:
            continue
        if did:
            seen.add(did)
        out.append(public_row(r))
    return out


async def get_meta(db, document_id: str):
    return await db[COLLECTION].find_one({"documentId": document_id}, _META_PROJ)


async def _delete_overlapping_ledgers(db, *, lead_id: str, snos: list[int]):
    """One ledger covers a unit — combined or separate. Replacing overlaps."""
    if not lead_id:
        return
    want = set(snos or [])
    ids = []
    async for doc in db[COLLECTION].find(
            {"leadId": lead_id, "kind": LEDGER_KIND},
            {"documentId": 1, "unitSno": 1, "unitSnos": 1}):
        have = set(doc_unit_snos(doc))
        if not want:
            if not have:
                ids.append(doc.get("documentId"))
            continue
        if not have or have & want:
            ids.append(doc.get("documentId"))
    ids = [i for i in ids if i]
    if ids:
        await db[COLLECTION].delete_many({"documentId": {"$in": ids}})


async def _delete_unique_docs(db, kind, *, lead_id="", request_id="", unit_sno=None):
    """Drop the previous file for this slot on the request or the live lead."""
    clauses = []
    if lead_id:
        clauses.append(unique_doc_filter(kind, lead_id=lead_id, unit_sno=unit_sno))
    if request_id:
        clauses.append(unique_doc_filter(kind, request_id=request_id, unit_sno=unit_sno))
    if not clauses:
        return
    await db[COLLECTION].delete_many({"$or": clauses} if len(clauses) > 1 else clauses[0])


async def save_doc(db, *, next_id, user, kind: str, data: bytes, content_type: str,
                   filename: str, lead_id: str = "", request_id: str = "",
                   unit_sno=None, unit_snos=None) -> dict:
    if kind not in KINDS:
        raise HTTPException(422, f"Unknown document kind '{kind}'.")
    info = KINDS[kind]
    snos = parse_unit_snos(kind, unit_sno, unit_snos)
    sno = snos[0] if len(snos) == 1 else parse_unit_sno(kind, unit_sno)
    if kind == LEDGER_KIND:
        await _delete_overlapping_ledgers(db, lead_id=lead_id, snos=snos)
        if not snos and info["unique"]:
            await _delete_unique_docs(
                db, kind, lead_id=lead_id, request_id=request_id, unit_sno=None)
    elif info["unique"]:
        await _delete_unique_docs(
            db, kind, lead_id=lead_id, request_id=request_id, unit_sno=sno)
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
    if len(snos) > 1:
        doc["unitSno"] = snos[0]
        doc["unitSnos"] = snos
    elif sno:
        doc["unitSno"] = sno
    await db[COLLECTION].insert_one(dict(doc))
    return public_row(doc)


# Deal sheet is per-enquiry paper — never sibling-copied onto another unit.
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
            await db[COLLECTION].delete_many(unique_doc_filter(
                kind, lead_id=to_lead_id, request_id=to_request_id, unit_sno=None))
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
