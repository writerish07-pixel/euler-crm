"""Read-only duplicate counts. Prints counts and sample ids. Does not write."""
import asyncio
import os

from motor.motor_asyncio import AsyncIOMotorClient


CHECKS = (
    ("leads", "leadId"),
    ("payments", "receiptNumber"),
)


async def dupes(db, coll, field):
    rows = await db[coll].aggregate([
        {"$match": {field: {"$type": "string", "$gt": ""}}},
        {"$group": {"_id": f"${field}", "n": {"$sum": 1}}},
        {"$match": {"n": {"$gt": 1}}},
        {"$limit": 5},
    ]).to_list(5)
    return rows


async def main():
    client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    db = client[os.environ["DB_NAME"]]
    for coll, field in CHECKS:
        rows = await dupes(db, coll, field)
        sample = [r.get("_id") for r in rows]
        print(f"{coll}.{field} duplicate_samples {len(sample)} {sample}")
    print("chassis invoice plate and claim keys are not indexed unique in this phase")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
