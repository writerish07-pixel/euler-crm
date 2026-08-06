"""JWT email+password auth with Owner / Executive roles (Bearer token)."""
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


def build_router(db):
    router = APIRouter(prefix="/api/auth")

    async def current_user(creds: HTTPAuthorizationCredentials = Depends(bearer)):
        if not creds:
            raise HTTPException(401, "Not authenticated")
        payload = decode_token(creds.credentials)
        user = await db.users.find_one({"userId": payload["sub"]})
        if not user:
            raise HTTPException(401, "User not found")
        user.pop("_id", None)
        user.pop("passwordHash", None)
        return user

    async def owner_only(user=Depends(current_user)):
        if user["role"] != "owner":
            raise HTTPException(403, "Owner access required")
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

    @router.get("/users")
    async def list_users(user=Depends(owner_only)):
        users = await db.users.find().to_list(200)
        return [{"userId": u["userId"], "email": u["email"], "name": u.get("name", ""), "role": u["role"]} for u in users]

    @router.post("/users")
    async def create_user(body: UserIn, user=Depends(owner_only)):
        email = body.email.strip().lower()
        if await db.users.find_one({"email": email}):
            raise HTTPException(400, "Email already exists")
        role = body.role if body.role in ("owner", "executive") else "executive"
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
    elif not verify_password(owner_pw, existing["passwordHash"]):
        await db.users.update_one({"email": owner_email}, {"$set": {"passwordHash": hash_password(owner_pw)}})
    # a demo executive
    exec_email = "executive@euler.com"
    if not await db.users.find_one({"email": exec_email}):
        await db.users.insert_one({
            "userId": str(uuid.uuid4()), "email": exec_email, "passwordHash": hash_password("euler@123"),
            "name": "Executive", "role": "executive", "createdAt": datetime.now(timezone.utc).isoformat(),
        })
