"""Count users that still store passwordPlain. Dry-run unless --apply.

Does not print passwords. Do not run --apply against production from this change.
"""
import argparse
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="unset passwordPlain")
    args = parser.parse_args()
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    query = {"passwordPlain": {"$exists": True, "$nin": ["", None]}}
    count = await db.users.count_documents(query)
    print(f"passwordPlain_rows {count}")
    if args.apply and count:
        result = await db.users.update_many(query, {"$unset": {"passwordPlain": ""}})
        print(f"unset {result.modified_count}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
