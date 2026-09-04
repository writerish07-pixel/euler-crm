"""Owner User Accounts: optional email, visible password, staff change updates it."""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "user_account_password_v1")
os.environ.setdefault("JWT_SECRET", "user-account-password-secret-32")
os.environ.setdefault("OWNER_PASSWORD", "euler@123")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        assert r.status_code == 200, r.text
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


def _row(users, login_id):
    return next(u for u in users if u.get("loginId") == login_id)


@pytest.mark.asyncio
async def test_create_user_without_email_shows_password(client):
    r = await client.post("/api/auth/users", json={
        "name": "Harish Bhatnagar", "loginId": "harish.b", "password": "desk#441",
        "role": "executive",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["email"] == ""
    assert body["loginId"] == "harish.b"
    assert body["password"] == "desk#441"

    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "harish.b")
    assert row["email"] == ""
    assert row["password"] == "desk#441"

    login = await client.post("/api/auth/login", json={"email": "harish.b", "password": "desk#441"})
    assert login.status_code == 200, login.text
    assert login.json()["user"]["name"] == "Harish Bhatnagar"
    assert "password" not in login.json()["user"]
    assert "passwordPlain" not in login.json()["user"]


@pytest.mark.asyncio
async def test_blank_email_and_blank_user_id_rejected(client):
    r = await client.post("/api/auth/users", json={
        "name": "No Handle", "password": "desk#441", "role": "executive",
    })
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_staff_me_never_includes_password(client):
    await client.post("/api/auth/users", json={
        "name": "Devang", "loginId": "devang.p", "password": "firstPass1",
        "role": "executive",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "devang.p", "password": "firstPass1"})).json()["token"]
    me = await client.get("/api/auth/me", headers={"Authorization": f"Bearer {tok}"})
    assert me.status_code == 200
    assert "passwordPlain" not in me.json()
    assert me.json().get("password") in (None, "")


@pytest.mark.asyncio
async def test_staff_change_password_updates_owner_list(client):
    await client.post("/api/auth/users", json={
        "name": "Shelendra", "loginId": "s.mathur", "password": "oldPass1",
        "role": "tl",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "s.mathur", "password": "oldPass1"})).json()["token"]
    r = await client.post("/api/auth/change-password",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"currentPassword": "oldPass1", "newPassword": "newPass9"})
    assert r.status_code == 200, r.text

    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "s.mathur")
    assert row["password"] == "newPass9"
    assert row.get("passwordChangedAt")

    ok = await client.post("/api/auth/login", json={"email": "s.mathur", "password": "newPass9"})
    assert ok.status_code == 200
    bad = await client.post("/api/auth/login", json={"email": "s.mathur", "password": "oldPass1"})
    assert bad.status_code == 401


@pytest.mark.asyncio
async def test_seed_fills_password_plain_when_hash_still_default(client):
    """Existing demo rows that never stored plaintext get it backfilled if the hash is still euler@123."""
    import auth as authmod

    await server.db.users.update_one(
        {"email": "executive@euler.com"},
        {"$unset": {"passwordPlain": ""}},
    )
    await server.db.users.update_one(
        {"email": "executive@euler.com"},
        {"$set": {"passwordHash": authmod.hash_password("euler@123")}},
    )
    await authmod.seed_users(server.db)
    listed = (await client.get("/api/auth/users")).json()
    row = next(u for u in listed if u["email"] == "executive@euler.com")
    assert row["password"] == "euler@123"


@pytest.mark.asyncio
async def test_seed_does_not_overwrite_staff_password_after_change(client):
    import auth as authmod

    await client.post("/api/auth/users", json={
        "name": "Kept", "loginId": "kept.pw", "password": "oldPass1",
        "role": "executive",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "kept.pw", "password": "oldPass1"})).json()["token"]
    r = await client.post("/api/auth/change-password",
                          headers={"Authorization": f"Bearer {tok}"},
                          json={"currentPassword": "oldPass1", "newPassword": "keptPass9"})
    assert r.status_code == 200, r.text
    await authmod.seed_users(server.db)
    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "kept.pw")
    assert row["password"] == "keptPass9"
    ok = await client.post("/api/auth/login", json={"email": "kept.pw", "password": "keptPass9"})
    assert ok.status_code == 200


@pytest.mark.asyncio
async def test_staff_cannot_list_user_passwords(client):
    await client.post("/api/auth/users", json={
        "name": "Peek", "loginId": "peek.user", "password": "secret99",
        "role": "executive",
    })
    tok = (await client.post("/api/auth/login",
                             json={"email": "peek.user", "password": "secret99"})).json()["token"]
    r = await client.get("/api/auth/users", headers={"Authorization": f"Bearer {tok}"})
    assert r.status_code == 403


@pytest.mark.asyncio
async def test_login_by_unique_staff_name(client):
    """Staff often type the Staff & Reports name, not the User ID."""
    r = await client.post("/api/auth/users", json={
        "name": "Priya Sharma", "loginId": "priya.s", "password": "desk#441",
        "role": "executive",
    })
    assert r.status_code == 200, r.text
    ok = await client.post("/api/auth/login", json={"email": "Priya Sharma", "password": "desk#441"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["user"]["loginId"] == "priya.s"
    folded = await client.post("/api/auth/login", json={"email": "priya sharma", "password": "desk#441"})
    assert folded.status_code == 200, folded.text


@pytest.mark.asyncio
async def test_ambiguous_name_does_not_log_anyone_in(client):
    await client.post("/api/auth/users", json={
        "name": "Amit", "loginId": "amit.one", "password": "desk#441", "role": "executive",
    })
    await client.post("/api/auth/users", json={
        "name": "Amit", "loginId": "amit.two", "password": "desk#442", "role": "tl",
    })
    r = await client.post("/api/auth/login", json={"email": "Amit", "password": "desk#441"})
    assert r.status_code == 401
    one = await client.post("/api/auth/login", json={"email": "amit.one", "password": "desk#441"})
    assert one.status_code == 200, one.text


@pytest.mark.asyncio
async def test_login_with_login_id_when_norm_field_is_missing(client):
    """Accounts created before loginIdNorm existed still have a User ID."""
    r = await client.post("/api/auth/users", json={
        "name": "Legacy Id", "loginId": "legacy.id", "password": "desk#441",
        "role": "executive",
    })
    assert r.status_code == 200, r.text
    uid = r.json()["userId"]
    await server.db.users.update_one({"userId": uid}, {"$unset": {"loginIdNorm": ""}})
    ok = await client.post("/api/auth/login", json={"email": "legacy.id", "password": "desk#441"})
    assert ok.status_code == 200, ok.text
    repaired = await server.db.users.find_one({"userId": uid})
    assert repaired.get("loginIdNorm") == "legacy.id"


@pytest.mark.asyncio
async def test_login_succeeds_from_plaintext_when_hash_is_missing(client):
    """A missing passwordHash used to KeyError and toast 'Something went wrong'."""
    r = await client.post("/api/auth/users", json={
        "name": "No Hash", "loginId": "no.hash", "password": "desk#441",
        "role": "executive",
    })
    uid = r.json()["userId"]
    await server.db.users.update_one({"userId": uid}, {"$unset": {"passwordHash": ""}})
    ok = await client.post("/api/auth/login", json={"email": "no.hash", "password": "desk#441"})
    assert ok.status_code == 200, ok.text
    repaired = await server.db.users.find_one({"userId": uid})
    assert repaired.get("passwordHash")
    import auth as authmod
    assert authmod.verify_password("desk#441", repaired["passwordHash"])


@pytest.mark.asyncio
async def test_missing_hash_and_plaintext_is_401_not_500(client):
    r = await client.post("/api/auth/users", json={
        "name": "Empty Creds", "loginId": "empty.pw", "password": "desk#441",
        "role": "executive",
    })
    uid = r.json()["userId"]
    await server.db.users.update_one(
        {"userId": uid},
        {"$unset": {"passwordHash": "", "passwordPlain": ""}},
    )
    bad = await client.post("/api/auth/login", json={"email": "empty.pw", "password": "desk#441"})
    assert bad.status_code == 401, bad.text
    assert "Invalid user ID or password" in bad.text


@pytest.mark.asyncio
async def test_login_strips_password_whitespace(client):
    await client.post("/api/auth/users", json={
        "name": "Paste Spaces", "loginId": "paste.pw", "password": "desk#441",
        "role": "executive",
    })
    ok = await client.post("/api/auth/login", json={"email": "paste.pw", "password": "  desk#441  "})
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_long_password_does_not_500(client):
    """bcrypt 4.1+ raises past 72 bytes — that used to surface as a blank toast."""
    pw = "long-pass#" + ("x" * 80)
    r = await client.post("/api/auth/users", json={
        "name": "Long Pass", "loginId": "long.pw", "password": pw, "role": "executive",
    })
    assert r.status_code == 200, r.text
    ok = await client.post("/api/auth/login", json={"email": "long.pw", "password": pw})
    assert ok.status_code == 200, ok.text
    assert ok.status_code != 500


@pytest.mark.asyncio
async def test_owner_can_reset_staff_password_then_they_sign_in(client):
    r = await client.post("/api/auth/users", json={
        "name": "Reset Me", "loginId": "reset.me", "password": "oldPass1",
        "role": "executive",
    })
    uid = r.json()["userId"]
    put = await client.put(f"/api/auth/users/{uid}/password", json={"password": "newPass9"})
    assert put.status_code == 200, put.text
    listed = (await client.get("/api/auth/users")).json()
    row = _row(listed, "reset.me")
    assert row["password"] == "newPass9"
    ok = await client.post("/api/auth/login", json={"email": "reset.me", "password": "newPass9"})
    assert ok.status_code == 200, ok.text
    stale = await client.post("/api/auth/login", json={"email": "reset.me", "password": "oldPass1"})
    assert stale.status_code == 401


@pytest.mark.asyncio
async def test_seed_backfills_missing_login_id_norm(client):
    import auth as authmod

    r = await client.post("/api/auth/users", json={
        "name": "Needs Norm", "loginId": "needs.norm", "password": "desk#441",
        "role": "executive",
    })
    uid = r.json()["userId"]
    await server.db.users.update_one({"userId": uid}, {"$unset": {"loginIdNorm": ""}})
    await authmod.seed_users(server.db)
    row = await server.db.users.find_one({"userId": uid})
    assert row.get("loginIdNorm") == "needs.norm"
