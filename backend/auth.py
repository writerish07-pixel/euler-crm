"""JWT email+password auth — Owner / TL / Executive / Accounts / ASM / RM / OEM (Bearer)."""
import os
import uuid
from datetime import datetime, timezone, timedelta

import bcrypt
import jwt
from fastapi import APIRouter, HTTPException, Depends, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr

JWT_ALGORITHM = "HS256"
bearer = HTTPBearer(auto_error=False)

# Dealership staff + company field managers + money desk + the OEM's finance desk
ALLOWED_ROLES = ("owner", "tl", "executive", "accounts", "asm", "rm", "oem_finance")
# Executives feed the funnel: leads, booking + booking amount, activities,
# quotations. A TEAM LEADER then finishes the deal — pricing, scheme, collection
# and delivery — so a handover never waits for the owner to log in. A TL can do
# everything an executive can, and so covers for one.
SALES_ROLES = ("owner", "tl", "executive")
LEAD_INTAKE_ROLES = ("owner", "tl", "executive")
MONEY_ROLES = ("owner", "tl", "accounts")
# Closing the deal: price, scheme, extra income, delivery, close, cancel, revive.
# The commercial decisions an executive does not make.
DEAL_DESK_ROLES = ("owner", "tl")
FIELD_ROLES = ("asm", "rm")
# Money desk can write; ASM/RM may view Finance Register (disbursed vs remaining).
FINANCE_VIEW_ROLES = (*MONEY_ROLES, "executive", *FIELD_ROLES)

# Roles belonging to people OUTSIDE the dealership. 37 of 43 GET endpoints carry
# no role check of their own — the /api router only requires a valid token — so an
# outside role would otherwise read the entire Lead Register, mobile numbers
# included. These roles are therefore denied EVERY authenticated route except the
# handful named below, which means a route added later is closed to them by
# default instead of silently exposed.
EXTERNAL_ROLES = ("oem_finance",)
EXTERNAL_ROLE_PATHS = {
    "oem_finance": (
        "/api/auth/me",
        "/api/auth/change-password",
        "/api/reports/oem-finance",
    ),
}


def _secret():
    return os.environ["JWT_SECRET"]


def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False


def create_token(user):
    payload = {
        "sub": user["userId"], "email": user["email"], "role": user["role"],
        "name": user.get("name", ""), "exp": datetime.now(timezone.utc) + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, _secret(), algorithm=JWT_ALGORITHM)


def decode_token(token):
    try:
        return jwt.decode(token, _secret(), algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


class LoginIn(BaseModel):
    email: str
    password: str


class UserIn(BaseModel):
    email: str
    password: str
    name: str = ""
    role: str = "executive"


class ChangePasswordIn(BaseModel):
    currentPassword: str
    newPassword: str


def build_router(db):
    router = APIRouter(prefix="/api/auth")

    async def current_user(request: Request,
                           creds: HTTPAuthorizationCredentials = Depends(bearer)):
        if not creds:
            raise HTTPException(401, "Not authenticated")
        payload = decode_token(creds.credentials)
        user = await db.users.find_one({"userId": payload["sub"]})
        if not user:
            raise HTTPException(401, "User not found")
        user.pop("_id", None)
        user.pop("passwordHash", None)
        # One chokepoint for outside roles. The /api router depends on
        # current_user for every route, so denying here denies everywhere —
        # including the 37 GET endpoints that have no role check of their own.
        # Allowlisted, so it fails closed: a new route is denied until someone
        # deliberately opens it.
        role = str(user.get("role") or "").strip().lower()
        if role in EXTERNAL_ROLES:
            path = (request.url.path or "").rstrip("/") or "/"
            if path not in EXTERNAL_ROLE_PATHS.get(role, ()):
                raise HTTPException(
                    403, "This account can only open the OEM finance report.")
        return user

    async def owner_only(user=Depends(current_user)):
        if user["role"] != "owner":
            raise HTTPException(403, "Owner access required")
        return user

    async def sales_staff_only(user=Depends(current_user)):
        """Owner + Executive — feeding the funnel.

        Leads, booking (with the booking amount), activities, bulk import and
        quotations. Pricing, scheme, delivery, close/cancel and money movements
        are NOT here — they are owner or money-desk decisions.
        """
        if user.get("role") not in SALES_ROLES:
            raise HTTPException(
                403,
                "Only Owner / Executive can add or update leads and bookings.",
            )
        return user

    async def deal_desk_only(user=Depends(current_user)):
        """Owner + Team Leader — the commercial steps that close a deal.

        Executives hand over here: pricing, scheme, extra income, delivery,
        close and cancel. A TL exists so those never queue behind the owner.
        """
        if user.get("role") not in DEAL_DESK_ROLES:
            raise HTTPException(
                403,
                "Only the Owner or a Team Leader can price, scheme, deliver, "
                "close or cancel a lead.",
            )
        return user

    async def money_desk_only(user=Depends(current_user)):
        """Owner / TL / Accounts — record payments, finance, claims, insurance."""
        if user.get("role") not in MONEY_ROLES:
            raise HTTPException(
                403,
                "Only the Owner, a Team Leader or Accounts can record money movements.",
            )
        return user

    async def finance_viewer_only(user=Depends(current_user)):
        """Money desk + ASM/RM — read Finance Register (committed / disbursed / outstanding)."""
        if user.get("role") not in FINANCE_VIEW_ROLES:
            raise HTTPException(403, "Finance Register is for money desk and ASM / RM.")
        return user

    async def field_viewer_only(user=Depends(current_user)):
        """ASM / RM (shared field board) + Owner shortcut."""
        if user.get("role") not in (*FIELD_ROLES, "owner"):
            raise HTTPException(403, "Field dashboard is for ASM / RM (and Owner).")
        return user

    @router.post("/login")
    async def login(body: LoginIn):
        email = body.email.strip().lower()
        user = await db.users.find_one({"email": email})
        if not user or not verify_password(body.password, user["passwordHash"]):
            raise HTTPException(401, "Invalid email or password")
        token = create_token(user)
        return {"token": token, "user": {"email": user["email"], "name": user.get("name", ""), "role": user["role"], "userId": user["userId"]}}

    @router.get("/me")
    async def me(user=Depends(current_user)):
        return user

    @router.post("/change-password")
    async def change_password(body: ChangePasswordIn, user=Depends(current_user)):
        """Any logged-in user can change their own password."""
        new_pw = (body.newPassword or "").strip()
        if len(new_pw) < 6:
            raise HTTPException(422, "New password must be at least 6 characters")
        if body.currentPassword == new_pw:
            raise HTTPException(422, "New password must be different from the current password")
        row = await db.users.find_one({"userId": user["userId"]})
        if not row or not verify_password(body.currentPassword, row["passwordHash"]):
            raise HTTPException(401, "Current password is incorrect")
        await db.users.update_one(
            {"userId": user["userId"]},
            {"$set": {
                "passwordHash": hash_password(new_pw),
                "passwordChangedAt": datetime.now(timezone.utc).isoformat(),
            }},
        )
        return {"ok": True, "message": "Password updated"}

    @router.get("/users")
    async def list_users(user=Depends(owner_only)):
        users = await db.users.find().to_list(200)
        return [{"userId": u["userId"], "email": u["email"], "name": u.get("name", ""), "role": u["role"]} for u in users]

    @router.post("/users")
    async def create_user(body: UserIn, user=Depends(owner_only)):
        email = body.email.strip().lower()
        if await db.users.find_one({"email": email}):
            raise HTTPException(400, "Email already exists")
        role = body.role if body.role in ALLOWED_ROLES else "executive"
        doc = {"userId": str(uuid.uuid4()), "email": email, "passwordHash": hash_password(body.password),
               "name": body.name, "role": role, "createdAt": datetime.now(timezone.utc).isoformat()}
        await db.users.insert_one(doc)
        return {"userId": doc["userId"], "email": email, "name": body.name, "role": role}

    @router.delete("/users/{user_id}")
    async def delete_user(user_id: str, user=Depends(owner_only)):
        if user_id == user["userId"]:
            raise HTTPException(400, "Cannot delete yourself")
        target = await db.users.find_one({"userId": user_id})
        if target and target.get("role") == "owner":
            owners = await db.users.count_documents({"role": "owner"})
            if owners <= 1:
                raise HTTPException(400, "Cannot delete the last owner")
        await db.users.delete_one({"userId": user_id})
        return {"ok": True}

    router.current_user = current_user
    router.owner_only = owner_only
    router.sales_staff_only = sales_staff_only
    router.deal_desk_only = deal_desk_only
    router.money_desk_only = money_desk_only
    router.finance_viewer_only = finance_viewer_only
    router.field_viewer_only = field_viewer_only
    return router


async def seed_users(db):
    await db.users.create_index("email", unique=True)
    owner_email = os.environ.get("OWNER_EMAIL", "owner@euler.com").strip().lower()
    owner_pw = os.environ.get("OWNER_PASSWORD", "euler@123")
    existing = await db.users.find_one({"email": owner_email})
    if not existing:
        await db.users.insert_one({
            "userId": str(uuid.uuid4()), "email": owner_email, "passwordHash": hash_password(owner_pw),
            "name": "Owner", "role": "owner", "createdAt": datetime.now(timezone.utc).isoformat(),
        })
    # Never reset an existing owner's password on startup — that would undo
    # Settings → Change password after every deploy/restart.
    demos = [
        ("executive@euler.com", "Executive", "executive"),
        ("accounts@euler.com", "Accounts", "accounts"),
        ("asm@euler.com", "ASM", "asm"),
        ("rm@euler.com", "RM", "rm"),
    ]
    for email, name, role in demos:
        if not await db.users.find_one({"email": email}):
            await db.users.insert_one({
                "userId": str(uuid.uuid4()), "email": email,
                "passwordHash": hash_password("euler@123"),
                "name": name, "role": role,
                "createdAt": datetime.now(timezone.utc).isoformat(),
            })
