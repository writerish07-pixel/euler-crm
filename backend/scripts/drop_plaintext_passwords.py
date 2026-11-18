"""Count users that still store passwordPlain. Dry-run unless --apply.

A row that has only passwordPlain is hashed first, then the plaintext is removed.
A row that already has a hash only loses the plaintext. Passwords are never printed.
Do not run --apply against production from this change.
"""
import argparse
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient

import auth as authmod


def _has_hash(row):
    return bool(str((row or {}).get("passwordHash") or "").strip())


def _has_plain(row):
    return bool(str((row or {}).get("passwordPlain") or "").strip())


async def drop_plaintext(db, apply=False):
    rows = await db.users.find({}, {"userId": 1, "passwordHash": 1, "passwordPlain": 1}).to_list(None)
    with_hash = [r for r in rows if _has_plain(r) and _has_hash(r)]
    plain_only = [r for r in rows if _has_plain(r) and not _has_hash(r)]
    summary = {
        "passwordPlain_with_hash": len(with_hash),
        "passwordPlain_only": len(plain_only),
        "unset": 0,
        "hashed_then_unset": 0,
    }
    if not apply:
        return summary
    if with_hash:
        result = await db.users.update_many(
            {"userId": {"$in": [r["userId"] for r in with_hash]}},
            {"$unset": {"passwordPlain": ""}},
        )
        summary["unset"] = result.modified_count
    for row in plain_only:
        await db.users.update_one(
            {"userId": row["userId"]},
            {"$set": {"passwordHash": authmod.hash_password(str(row.get("passwordPlain") or ""))},
             "$unset": {"passwordPlain": ""}},
        )
        summary["hashed_then_unset"] += 1
    return summary


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="hash plaintext-only rows, then unset passwordPlain")
    args = parser.parse_args()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    summary = await drop_plaintext(db, apply=args.apply)
    print(
        "passwordPlain_with_hash {passwordPlain_with_hash} "
        "passwordPlain_only {passwordPlain_only}".format(**summary)
    )
    if args.apply:
        print("unset {unset} hashed_then_unset {hashed_then_unset}".format(**summary))
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
