"""Read-only showroom price list for sales staff.

Price Master is an EDITING grid whose write endpoints are owner-gated, yet it was
in the sales sidebar — so a salesperson saw Add/Edit/Delete buttons that answered
403. They also had no on-road price and no view of the month's scheme; the three
charge columns had to be added up in front of the customer.

The price list gives them the number they actually quote, and nothing they should
not see:
  * on-road = the engine's Gross Vehicle Cost, plus TCS only where it is billed
  * scheme = the TOTAL available this month; the company/dealer split is withheld
  * no write path at all
"""
import os
import sys

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "iter31pricelist")
os.environ.setdefault("JWT_SECRET", "iter31-price-list-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import commercial as ce  # noqa: E402
import server  # noqa: E402


@pytest_asyncio.fixture
async def client():
    await server.startup()
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login",
                         json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
        yield c


@pytest_asyncio.fixture
async def staff(client):
    r = await client.post("/api/auth/login",
                          json={"email": "executive@euler.com", "password": "euler@123"})
    return {"Authorization": f"Bearer {r.json()['token']}"}


def all_rows(body):
    return [r for g in body["models"] for r in g["rows"]]


# ================================================================== contents
@pytest.mark.asyncio
async def test_every_active_vehicle_is_listed_and_grouped(client):
    body = (await client.get("/api/price-list")).json()
    assert body["totalRows"] > 0
    models = {g["model"] for g in body["models"]}
    assert {"Turbo Max", "Hi-Load", "Storm"} <= models
    for g in body["models"]:
        assert g["count"] == len(g["rows"])


@pytest.mark.asyncio
async def test_on_road_matches_the_commercial_engine(client):
    """The list must never quote a number the engine would not produce."""
    body = (await client.get("/api/price-list")).json()
    for r in all_rows(body)[:20]:
        totals = ce.compute_commercial_totals({
            "exShowroom": r["exShowroom"], "rto": r["rto"],
            "registrationRto": r["rto"], "insurance": r["insurance"],
            "otherCharges": r["otherCharges"],
            "tcsApplicable": "Yes" if r["tcsApplies"] else "No",
        })
        assert r["onRoad"] == ce.round2(totals["grossVehicleCost"] + totals["tcs"]), r


@pytest.mark.asyncio
async def test_rows_are_cheapest_first_within_a_model(client):
    body = (await client.get("/api/price-list")).json()
    for g in body["models"]:
        prices = [r["onRoad"] for r in g["rows"]]
        assert prices == sorted(prices)


@pytest.mark.asyncio
async def test_scheme_month_is_stated(client):
    """Scheme is monthly — quoting August's benefit in September is the risk."""
    body = (await client.get("/api/price-list")).json()
    assert body["schemeMonth"] == ce.scheme_month_from_date(server.today())
    assert body["asOf"] == server.today()


@pytest.mark.asyncio
async def test_scheme_shows_total_only_never_the_split(client):
    """Company vs dealer share is commercial information staff must not see."""
    body = (await client.get("/api/price-list")).json()
    for r in all_rows(body):
        assert "schemeAvailable" in r
        for banned in ("companyShare", "dealerShare", "oemShare",
                       "dealerFundedShare", "dealerRetained", "components"):
            assert banned not in r, f"{banned} leaked into the price list"


@pytest.mark.asyncio
async def test_a_turbo_row_carries_this_months_scheme(client):
    body = (await client.get("/api/price-list", params={"model": "Turbo Max"})).json()
    rows = all_rows(body)
    assert rows and all(r["schemeAvailable"] > 0 for r in rows), \
        "Turbo has an active Aug-2026 scheme"


# ======================================================================= TCS
@pytest.mark.asyncio
async def test_tcs_is_charged_only_where_the_engine_charges_it(client):
    body = (await client.get("/api/price-list")).json()
    for r in all_rows(body):
        base = ce.round2(r["exShowroom"] + r["rto"] + r["insurance"] + r["otherCharges"])
        if r["tcsApplies"]:
            assert base >= ce.TCS_THRESHOLD, "TCS on a row under the threshold"
            assert r["tcs"] == ce.round2(base * ce.TCS_RATE)
            assert r["onRoad"] == ce.round2(base + r["tcs"])
        else:
            assert r["tcs"] == 0
            assert r["onRoad"] == base


@pytest.mark.asyncio
async def test_a_row_over_the_threshold_with_the_flag_off_gets_no_tcs(client):
    """Seven live rows are like this. Quoting TCS the app will never bill is worse
    than omitting it — but the owner still needs to know."""
    body = (await client.get("/api/price-list")).json()
    review = body.get("tcsReview")
    assert review is not None, "owner should get the data-quality flag"
    for row in review:
        match = next(r for r in all_rows(body) if r["priceId"] == row["priceId"])
        assert match["tcs"] == 0
        assert match["onRoad"] >= ce.TCS_THRESHOLD


@pytest.mark.asyncio
async def test_the_tcs_review_flag_is_owner_only(staff, client):
    body = (await client.get("/api/price-list", headers=staff)).json()
    assert "tcsReview" not in body, "sales staff must not see the data-quality flag"


# =================================================================== access
@pytest.mark.asyncio
async def test_sales_staff_can_read_the_price_list(staff, client):
    r = await client.get("/api/price-list", headers=staff)
    assert r.status_code == 200
    assert r.json()["totalRows"] > 0


@pytest.mark.asyncio
async def test_price_list_has_no_write_path(staff, client):
    """It is a view. Prices are changed in Price Master, which is owner-only."""
    for verb in ("post", "put", "delete"):
        r = await getattr(client, verb)("/api/price-list", headers=staff)
        assert r.status_code in (403, 404, 405), f"{verb} /price-list should not exist"


@pytest.mark.asyncio
async def test_staff_still_cannot_change_a_price(staff, client):
    row = all_rows((await client.get("/api/price-list")).json())[0]
    r = await client.put(f"/api/price-master/{row['priceId']}",
                         json={"model": row["model"], "variant": row["variant"],
                               "exShowroom": 1},
                         headers=staff)
    assert r.status_code == 403


# =================================================================== filters
@pytest.mark.asyncio
async def test_model_filter(client):
    body = (await client.get("/api/price-list", params={"model": "Storm"})).json()
    assert {g["model"] for g in body["models"]} == {"Storm"}


@pytest.mark.asyncio
async def test_search_matches_model_and_variant(client):
    body = (await client.get("/api/price-list", params={"q": "maxx"})).json()
    rows = all_rows(body)
    assert rows and all("maxx" in r["variant"].lower() for r in rows)
    empty = (await client.get("/api/price-list", params={"q": "zzzznope"})).json()
    assert empty["totalRows"] == 0


@pytest.mark.asyncio
async def test_inactive_rows_are_hidden(client):
    row = all_rows((await client.get("/api/price-list")).json())[0]
    await server.db.price_master.update_one({"priceId": row["priceId"]},
                                            {"$set": {"status": "inactive"}})
    body = (await client.get("/api/price-list")).json()
    assert row["priceId"] not in {r["priceId"] for r in all_rows(body)}
    await server.db.price_master.update_one({"priceId": row["priceId"]},
                                            {"$set": {"status": "active"}})
