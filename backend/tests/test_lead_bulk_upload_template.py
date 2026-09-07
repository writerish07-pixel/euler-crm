"""Bulk lead upload — template dropdowns, row validation, and Owner/GM split.

The template's dropdown values and the upload's validation must come from the same
live masters, so a downloaded template can never offer a value the upload rejects.
Unknown Lead Source / Model / Status values are reported and skipped. A blank or
unknown Executive is not skipped — Owner/GM percentages assign those rows on commit.
"""
import io
import json
import os
import sys
from collections import Counter

import pytest
import pytest_asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("MONGO_URL", "mongodb://localhost:27017")
os.environ.setdefault("DB_NAME", "lead_bulk_upload")
os.environ.setdefault("JWT_SECRET", "bulk-upload-secret")

import motor.motor_asyncio  # noqa: E402
from mongomock_motor import AsyncMongoMockClient  # noqa: E402

motor.motor_asyncio.AsyncIOMotorClient = AsyncMongoMockClient

import httpx  # noqa: E402
import openpyxl  # noqa: E402
import server  # noqa: E402

HEADERS = [label for label, _ in server.IMPORT_COLUMNS]


def _csv(rows):
    body = ",".join(HEADERS) + "\n"
    for r in rows:
        body += ",".join("" if v is None else str(v) for v in r) + "\n"
    return body.encode()


def _row(name, mobile, **over):
    """A row in IMPORT_COLUMNS order with valid defaults."""
    values = {
        "Customer Name": name, "Mobile": mobile, "Alternate Mobile": "",
        "Village": "Bassi", "City": "Jaipur", "Lead Date": "2026-08-10",
        "Next Follow-up": "", "Lead Source": "Walk-in",
        "Interested Model": "Turbo Max", "Variant": "Maxx (PV)", "Executive": "Amit",
        "Current Status": "New", "Priority": "Normal", "Budget": 750000,
        "Remarks": "", "Finance Required": "No", "Exchange Required": "No",
    }
    values.update(over)
    return [values[label] for label in HEADERS]


@pytest_asyncio.fixture
async def client(monkeypatch):
    """Run against a dedicated mongomock database.

    Every test module shares one `server` import (and therefore one DB_NAME), so
    wiping leads / price_master here would corrupt other modules' fixtures. Auth
    keeps using the original database because the auth router captured it at
    import time; seed_users is idempotent and never deletes.
    """
    isolated = server.client["lead_bulk_upload_isolated"]
    for name in ("leads", "price_master", "masters_list", "counters", "activities",
                 "lead_split", "staff", "sheet_sync_log", "lead_requests", "lead_documents"):
        await isolated[name].delete_many({})
    await isolated.price_master.insert_many([
        {"priceId": "PM1", "model": "Turbo Max", "variant": "Maxx (PV)", "exShowroom": 770000, "status": "Active"},
        {"priceId": "PM2", "model": "Turbo Max", "variant": "Maxx (DV2000)", "exShowroom": 780000, "status": "Active"},
        {"priceId": "PM3", "model": "Storm EV", "variant": "Storm (PV)", "exShowroom": 640000, "status": "Active"},
    ])
    monkeypatch.setattr(server, "db", isolated)
    await server.authmod.seed_users(server.client[os.environ["DB_NAME"]])
    transport = httpx.ASGITransport(app=server.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        r = await c.post("/api/auth/login", json={"email": "owner@euler.com", "password": "euler@123"})
        c.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield c


# ------------------------------------------------------------------ template
@pytest.mark.asyncio
async def test_template_has_dropdowns_from_live_masters(client):
    r = await client.get("/api/leads/import/template")
    assert r.status_code == 200, r.text
    assert "spreadsheetml" in r.headers["content-type"]

    wb = openpyxl.load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Leads", "Lists", "How to use"]

    leads, lists = wb["Leads"], wb["Lists"]
    assert [c.value for c in leads[1]] == HEADERS

    # Every list column the user must not free-type carries a validation range.
    validated = set()
    for dv in leads.data_validations.dataValidation:
        assert dv.type == "list"
        assert dv.formula1.startswith("=Lists!")
        # Without showErrorMessage the list is only a hint and Excel accepts a
        # typed value; showDropDown must stay falsey or the arrow is hidden.
        assert dv.showErrorMessage is True and dv.errorStyle == "stop"
        assert not dv.showDropDown
        validated.update(str(sqref) for sqref in dv.sqref.ranges)
    assert len(validated) == 8, validated

    # Dropdown values come from Price Master / Settings, not a hardcoded list.
    by_title = {}
    for col in lists.iter_cols(min_row=1, max_row=lists.max_row):
        title = col[0].value
        if title:
            by_title[title] = [c.value for c in col[1:] if c.value]
    assert by_title["Interested Model"] == ["Storm EV", "Turbo Max"]
    assert "Maxx (DV2000)" in by_title["Variant"]
    assert "Amit" in by_title["Executive"]
    assert by_title["Current Status"] == server.IMPORT_STATUSES
    assert by_title["Yes / No"] == ["Yes", "No"]
    # Valid model+variant pairs are listed because validation cannot be dependent.
    assert ("Turbo Max", "Maxx (PV)") in list(zip(by_title["Valid Model"],
                                                  by_title["Valid Variant for that Model"]))


@pytest.mark.asyncio
async def test_downloaded_template_uploads_without_column_mapping(client):
    """Round trip: the file we hand out must import as-is, with no mapping step."""
    tpl = await client.get("/api/leads/import/template")
    wb = openpyxl.load_workbook(io.BytesIO(tpl.content))
    ws = wb["Leads"]
    assert ws.max_row == 1, "template must ship empty so a sample row is never imported"

    lists = {c[0].value: [x.value for x in c[1:] if x.value]
             for c in wb["Lists"].iter_cols(min_row=1, max_row=wb["Lists"].max_row) if c[0].value}
    picked = {
        "Lead Source": lists["Lead Source"][0],
        "Executive": lists["Executive"][0],
        "Interested Model": "Turbo Max",
        "Variant": "Maxx (PV)",
        "Priority": lists["Priority"][0],
        "Current Status": lists["Current Status"][0],
        "Finance Required": "Yes",
        "Exchange Required": "No",
    }
    row = {"Customer Name": "Round Trip", "Mobile": "9800000099", "City": "Jaipur",
           "Lead Date": "2026-08-12", **picked}
    ws.append([row.get(label, "") for label in HEADERS])
    buf = io.BytesIO()
    wb.save(buf)

    r = await client.post("/api/leads/import/commit", files={
        "file": ("filled.xlsx", buf.getvalue(),
                 "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")})
    assert r.status_code == 200, r.text
    assert (r.json()["created"], r.json()["skipped"]) == (1, 0), r.json()
    lead = await server.db.leads.find_one({"customerName": "Round Trip"})
    assert lead["leadSource"] == picked["Lead Source"]
    assert lead["executive"] == picked["Executive"]
    assert lead["financeRequired"] == "Yes"
    assert lead["createdDate"] == "2026-08-12"


@pytest.mark.asyncio
async def test_template_needs_sales_role(client):
    r = await client.post("/api/auth/login", json={"email": "asm@euler.com", "password": "euler@123"})
    asm = {"Authorization": f"Bearer {r.json()['token']}"}
    assert (await client.get("/api/leads/import/template", headers=asm)).status_code == 403


# ------------------------------------------------------------------ validation
async def _preview(client, rows):
    r = await client.post("/api/leads/import/preview",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


@pytest.mark.asyncio
async def test_clean_template_rows_import(client):
    rows = [_row("Ramesh Kumar", "9800000001"), _row("Sita Devi", "9800000002", **{
        "Interested Model": "Storm EV", "Variant": "Storm (PV)", "Lead Source": "Referral",
        "Current Status": "Follow-up", "Next Follow-up": "2026-08-20"})]
    body = await _preview(client, rows)
    assert (body["rowCount"], body["validCount"], body["errorCount"]) == (2, 2, 0)

    r = await client.post("/api/leads/import/commit",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 2 and r.json()["skipped"] == 0

    lead = await server.db.leads.find_one({"customerName": "Sita Devi"})
    assert lead["leadSource"] == "Referral"
    assert lead["interestedModel"] == "Storm EV" and lead["variant"] == "Storm (PV)"
    assert lead["currentStatus"] == "Follow-up"
    assert lead["nextFollowupDate"] == "2026-08-20"
    assert lead["createdDate"] == "2026-08-10"
    assert lead["accountStatus"] == "Active"


@pytest.mark.asyncio
async def test_values_outside_masters_are_skipped_not_imported(client):
    rows = [
        _row("Bad Source", "9800000011", **{"Lead Source": "Instagram DM"}),
        _row("Bad Exec", "9800000012", **{"Executive": "Someone Else"}),
        _row("Bad Model", "9800000013", **{"Interested Model": "Turbo Maxx", "Variant": ""}),
        _row("Wrong Variant", "9800000014", **{"Interested Model": "Turbo Max", "Variant": "Storm (PV)"}),
        _row("Booked Status", "9800000015", **{"Current Status": "Delivered"}),
        _row("Good Row", "9800000016"),
    ]
    body = await _preview(client, rows)
    assert body["validCount"] == 2 and body["errorCount"] == 4
    problems = {e["customerName"]: " ".join(e["errors"]) for e in body["errors"]}
    assert "Lead Source" in problems["Bad Source"]
    assert "Bad Exec" not in problems, "unknown Executive is blanked and split, not skipped"
    assert "Price Master" in problems["Bad Model"]
    assert "does not belong to Turbo Max" in problems["Wrong Variant"]
    assert "Current Status" in problems["Booked Status"]

    r = await client.post("/api/leads/import/commit",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.json()["created"] == 2 and r.json()["skipped"] == 4
    names = {d["customerName"] for d in await server.db.leads.find().to_list(10)}
    assert names == {"Bad Exec", "Good Row"}
    bad = await server.db.leads.find_one({"customerName": "Bad Exec"})
    assert not str(bad.get("executive") or "").strip()


@pytest.mark.asyncio
async def test_case_and_spacing_differences_are_accepted(client):
    rows = [_row("Loose Case", "9800000021", **{
        "Lead Source": "walk-in", "Executive": "  amit ", "Interested Model": "turbo max",
        "Variant": "maxx (pv)", "Finance Required": "yes", "Priority": "high"})]
    body = await _preview(client, rows)
    assert body["errorCount"] == 0, body["errors"]
    row = body["sample"][0]
    assert (row["leadSource"], row["executive"]) == ("Walk-in", "Amit")
    assert (row["interestedModel"], row["variant"]) == ("Turbo Max", "Maxx (PV)")
    assert (row["financeRequired"], row["priority"]) == ("Yes", "High")


@pytest.mark.asyncio
async def test_blank_optional_cells_use_new_lead_defaults(client):
    rows = [_row("Minimal Row", "9800000031", **{
        "Lead Date": "", "Lead Source": "", "Executive": "", "Interested Model": "",
        "Variant": "", "Current Status": "", "Priority": "", "Budget": "",
        "Finance Required": "", "Exchange Required": ""})]
    body = await _preview(client, rows)
    assert body["errorCount"] == 0, body["errors"]
    row = body["sample"][0]
    assert row["leadSource"] == "Walk-in"
    assert row["currentStatus"] == "New" and row["priority"] == "Normal"
    assert row["financeRequired"] == "No" and row["exchangeRequired"] == "No"
    assert row["createdDate"] == server.today()
    # The old import wrote leadSource="Import", which is not a Settings value.
    assert row["leadSource"] in server.seeder.MASTERS["leadSources"]


@pytest.mark.asyncio
async def test_duplicate_mobiles_blocked_in_file_and_against_crm(client):
    await client.post("/api/leads/import/commit",
                      files={"file": ("a.csv", _csv([_row("First In", "9800000041")]), "text/csv")})
    rows = [_row("Same File A", "9800000042"), _row("Same File B", "9800000042"),
            _row("Already There", "9800000041"), _row("No Mobile", "")]
    body = await _preview(client, rows)
    assert (body["validCount"], body["alreadyCount"], body["errorCount"]) == (1, 1, 2)
    problems = {e["customerName"]: " ".join(e["errors"]) for e in body["errors"]}
    assert "Already There" not in problems
    assert "Duplicate mobile" in problems["Same File B"]
    assert "Mobile is required" in problems["No Mobile"]
    already = {e["customerName"]: e["leadId"] for e in body["alreadyInApp"]}
    assert "Already There" in already
    first = await server.db.leads.find_one({"customerName": "First In"})
    assert already["Already There"] == first["leadId"]

    r = await client.post("/api/leads/import/commit",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 1
    assert r.json()["alreadyExisted"] == 1
    assert r.json()["skipped"] == 2
    assert await server.db.leads.count_documents({"mobile": "9800000041"}) == 1


@pytest.mark.asyncio
async def test_dates_accept_indian_format_and_reject_junk(client):
    rows = [_row("DMY Date", "9800000051", **{"Lead Date": "10-08-2026"}),
            _row("Junk Date", "9800000052", **{"Lead Date": "next monday"})]
    body = await _preview(client, rows)
    assert body["validCount"] == 1
    assert body["sample"][0]["createdDate"] == "2026-08-10"
    assert "is not a date" in " ".join(body["errors"][0]["errors"])


# ------------------------------------------------------------------ split + TL
def test_distribute_by_share_largest_remainder_interleaved():
    names = server.distribute_by_share(10, [
        {"executive": "Amit", "pct": 70}, {"executive": "Rahul", "pct": 30}])
    assert names.count("Amit") == 7 and names.count("Rahul") == 3
    assert names[0] == "Amit" and names[1] == "Rahul"
    assert server.distribute_by_share(0, [{"executive": "Amit", "pct": 100}]) == []
    assert server.distribute_by_share(3, []) == ["", "", ""]


def test_executive_suggestions_are_case_and_token_aware():
    names = ["Amit", "Rahul", "Harish Bhatnagar"]
    assert server._executive_suggestions("amit", names) == ["Amit"]
    assert server._executive_suggestions("AMIT", names) == ["Amit"]
    assert server._executive_suggestions("Amit Kumar", names) == ["Amit"]
    assert server._executive_suggestions("harish", names) == ["Harish Bhatnagar"]
    assert server._executive_suggestions("Someone Else", names) == []


async def _login(email, password):
    transport = httpx.ASGITransport(app=server.app)
    c = httpx.AsyncClient(transport=transport, base_url="http://test")
    r = await c.post("/api/auth/login", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    c.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return c


async def _ensure_staff(*names):
    await server.db.staff.delete_many({})
    for i, name in enumerate(names, start=1):
        await server.db.staff.insert_one({
            "staffId": f"ST{i}", "name": name, "role": "executive", "status": "Active",
        })


@pytest.mark.asyncio
async def test_tl_can_download_template_and_import(client):
    """The TL bulk-upload path is what the floor uses; Owner rarely hits it."""
    email = "tl.bulk@euler.com"
    auth_db = server.client[os.environ["DB_NAME"]]
    await auth_db.users.delete_many({"email": email})
    created = await client.post("/api/auth/users", json={
        "email": email, "password": "tlPass#1", "name": "Bulk TL",
        "role": "tl", "loginId": "tl.bulk"})
    assert created.status_code == 200, created.text
    tl = await _login(email, "tlPass#1")
    try:
        tpl = await tl.get("/api/leads/import/template")
        assert tpl.status_code == 200, tpl.text
        assert "spreadsheetml" in tpl.headers["content-type"]
        wb = openpyxl.load_workbook(io.BytesIO(tpl.content))
        guide = "\n".join(str(c[0].value or "") for c in wb["How to use"].iter_rows(max_col=1))
        assert "optional" in guide.lower()

        rows = [_row("TL Import", "9830000001", **{"Executive": ""})]
        preview = await tl.post("/api/leads/import/preview",
                                files={"file": ("leads.csv", _csv(rows), "text/csv")})
        assert preview.status_code == 200, preview.text
        assert preview.json()["validCount"] == 1

        commit = await tl.post("/api/leads/import/commit",
                               files={"file": ("leads.csv", _csv(rows), "text/csv")})
        assert commit.status_code == 200, commit.text
        assert commit.json()["created"] == 1
        lead = await server.db.leads.find_one({"customerName": "TL Import"})
        assert lead is not None
    finally:
        await tl.aclose()


@pytest.mark.asyncio
async def test_tl_cannot_edit_lead_split_owner_and_gm_can(client):
    await _ensure_staff("Amit", "Rahul")
    email = "tl.bulk@euler.com"
    auth_db = server.client[os.environ["DB_NAME"]]
    await auth_db.users.delete_many({"email": email})
    await client.post("/api/auth/users", json={
        "email": email, "password": "tlPass#1", "name": "Bulk TL",
        "role": "tl", "loginId": "tl.bulk"})
    body = {"shares": [{"executive": "Amit", "pct": 70}, {"executive": "Rahul", "pct": 30}]}
    tl = await _login(email, "tlPass#1")
    gm = await _login("salesgm@euler.com", "euler@123")
    try:
        assert (await tl.get("/api/leads/split")).status_code == 200
        assert (await tl.put("/api/leads/split", json=body)).status_code == 403
        owner = await client.put("/api/leads/split", json=body)
        assert owner.status_code == 200, owner.text
        assert owner.json()["totalPct"] == 100
        gm_save = await gm.put("/api/leads/split", json={
            "shares": [{"executive": "Amit", "pct": 40}, {"executive": "Rahul", "pct": 60}]})
        assert gm_save.status_code == 200, gm_save.text
        assert gm_save.json()["totalPct"] == 100
        bad = await client.put("/api/leads/split", json={
            "shares": [{"executive": "Amit", "pct": 40}]})
        assert bad.status_code == 422
    finally:
        await tl.aclose()
        await gm.aclose()


@pytest.mark.asyncio
async def test_bulk_import_assigns_blank_executives_by_saved_split(client):
    await _ensure_staff("Amit", "Rahul")
    saved = await client.put("/api/leads/split", json={
        "shares": [{"executive": "Amit", "pct": 70}, {"executive": "Rahul", "pct": 30}]})
    assert saved.status_code == 200, saved.text

    rows = [_row(f"Split {i}", f"98400000{i:02d}", **{"Executive": ""}) for i in range(10)]
    rows.append(_row("Keep Named", "9840000099", **{"Executive": "Amit"}))
    r = await client.post("/api/leads/import/commit",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 11
    assigned = r.json()["splitAssigned"]
    assert len(assigned) == 10
    split_leads = await server.db.leads.find({"customerName": {"$regex": "^Split "}}).to_list(20)
    counts = Counter(d["executive"] for d in split_leads)
    assert counts["Amit"] == 7 and counts["Rahul"] == 3
    keep = await server.db.leads.find_one({"customerName": "Keep Named"})
    assert keep["executive"] == "Amit"
    assert keep["leadId"] not in assigned

    auth_db = server.client[os.environ["DB_NAME"]]
    await auth_db.users.delete_many({"email": "amit.split@euler.com"})
    created = await client.post("/api/auth/users", json={
        "email": "amit.split@euler.com", "password": "execPass#1",
        "name": "Amit", "role": "executive", "loginId": "amit.split"})
    assert created.status_code == 200, created.text
    exec_c = await _login("amit.split@euler.com", "execPass#1")
    try:
        split = await exec_c.get("/api/leads/split")
        assert split.status_code == 200, split.text
        assert split.json()["myShare"] == 70
        dash = await exec_c.get("/api/executive/dashboard")
        assert dash.status_code == 200, dash.text
        assert dash.json()["leadSplit"]["pct"] == 70
        mine = await exec_c.get("/api/leads")
        assert mine.status_code == 200
        names = {d["customerName"] for d in mine.json()}
        assert "Keep Named" in names
        assert any(n.startswith("Split ") for n in names)
        for d in mine.json():
            assert d["executive"] == "Amit"
    finally:
        await exec_c.aclose()


@pytest.mark.asyncio
async def test_import_prompts_case_mismatch_and_transfers_on_commit(client):
    await _ensure_staff("Amit", "Rahul")
    rows = [
        _row("Case Amit", "9850000001", **{"Executive": "AMIT"}),
        _row("Token Amit", "9850000002", **{"Executive": "Amit Kumar"}),
    ]
    body = await _preview(client, rows)
    keys = {p["key"]: p for p in body["executivePrompts"]}
    assert keys["amit"]["suggested"] == "Amit"
    assert keys["amit kumar"]["suggested"] == "Amit"

    r = await client.post(
        "/api/leads/import/commit",
        data={"executiveMap": json.dumps({"amit": "Amit", "amit kumar": "Amit"})},
        files={"file": ("leads.csv", _csv(rows), "text/csv")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["matchedExecutives"] == 2
    assert (await server.db.leads.find_one({"customerName": "Case Amit"}))["executive"] == "Amit"
    assert (await server.db.leads.find_one({"customerName": "Token Amit"}))["executive"] == "Amit"


@pytest.mark.asyncio
async def test_declining_a_case_match_uses_the_lead_split(client):
    await _ensure_staff("Amit", "Rahul")
    saved = await client.put("/api/leads/split", json={
        "shares": [{"executive": "Amit", "pct": 0}, {"executive": "Rahul", "pct": 100}]})
    assert saved.status_code == 200, saved.text
    rows = [_row("Skip Match", "9850000011", **{"Executive": "amit"})]
    r = await client.post(
        "/api/leads/import/commit",
        data={"executiveMap": json.dumps({"amit": ""})},
        files={"file": ("leads.csv", _csv(rows), "text/csv")},
    )
    assert r.status_code == 200, r.text
    lead = await server.db.leads.find_one({"customerName": "Skip Match"})
    assert lead["executive"] == "Rahul"
    assert lead.get("importedSplit") is True


@pytest.mark.asyncio
async def test_existing_wrong_case_executives_can_be_transferred(client):
    await _ensure_staff("Amit", "Rahul")
    await client.post("/api/leads/import/commit", files={
        "file": ("a.csv", _csv([_row("Old Case", "9850000021", **{"Executive": "Amit"})]),
                 "text/csv")})
    await server.db.leads.update_one({"customerName": "Old Case"}, {"$set": {"executive": "AMIT"}})
    summary = await client.get("/api/leads/allocation/summary")
    assert summary.status_code == 200, summary.text
    matches = summary.json()["executiveMatches"]
    assert any(m["key"] == "amit" and m["suggested"] == "Amit" for m in matches)
    r = await client.post("/api/leads/match-executive",
                          json={"key": "amit", "executive": "Amit"})
    assert r.status_code == 200, r.text
    assert r.json()["movedCount"] == 1
    assert (await server.db.leads.find_one({"customerName": "Old Case"}))["executive"] == "Amit"


@pytest.mark.asyncio
async def test_next_ids_reserves_a_contiguous_block(client):
    ids = await server.next_ids("lead", "LD26", 3)
    assert ids == ["LD26000001", "LD26000002", "LD26000003"]
    assert await server.next_id("lead", "LD26") == "LD26000004"
    assert await server.next_ids("lead", "LD26", 0) == []


@pytest.mark.asyncio
async def test_import_commit_inserts_once_and_does_not_await_google(client, monkeypatch):
    """A 168-row import used to await Google once per lead and blow the 25s
    browser timeout. Leads already written stayed in the app, the toast said
    Network Error, and a retry could race the first request. Commit must insert
    the batch, queue sheet rows, and return without calling sheet_sync."""
    scheduled = []
    monkeypatch.setattr(server, "_schedule_sheet_syncs", lambda docs: scheduled.append(len(docs)))

    awaited = {"n": 0}

    async def boom(*_a, **_k):
        awaited["n"] += 1
        raise AssertionError("Google sync must run after the HTTP response")

    monkeypatch.setattr(server, "sheet_sync", boom)

    rows = [_row("One", "9860000001"), _row("Two", "9860000002"), _row("Three", "9860000003")]
    r = await client.post("/api/leads/import/commit",
                          files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r.status_code == 200, r.text
    assert r.json()["created"] == 3
    assert awaited["n"] == 0
    assert scheduled == [3]
    assert r.json()["leadIds"] == ["LD26000001", "LD26000002", "LD26000003"]
    pending = await server.db.sheet_sync_log.find().to_list(10)
    assert len(pending) == 3
    assert all(p.get("status") == "PENDING" for p in pending)

    r2 = await client.post("/api/leads/import/commit",
                           files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert r2.status_code == 200, r2.text
    assert r2.json()["created"] == 0
    assert r2.json()["alreadyExisted"] == 3
    assert await server.db.leads.count_documents({}) == 3


PNG = b"\x89PNG\r\n\x1a\n" + b"kyc-scan" * 8


async def _attach_kyc(client, request_id):
    for kind in ("kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"):
        r = await client.post(
            f"/api/lead-requests/{request_id}/documents",
            files={"file": ("scan.png", io.BytesIO(PNG), "image/png")},
            data={"kind": kind},
        )
        assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_apply_split_names_unassigned_leads_pending_approval(client):
    """Already-imported blanks get executive names on the register, but the
    executive cannot work them until Deal format + KYC and GM / Owner Approve."""
    await _ensure_staff("Amit", "Rahul")
    saved = await client.put("/api/leads/split", json={
        "shares": [{"executive": "Amit", "pct": 70}, {"executive": "Rahul", "pct": 30}]})
    assert saved.status_code == 200, saved.text

    rows = [_row(f"Orphan {i}", f"98700000{i:02d}", **{"Executive": ""}) for i in range(10)]
    imported = await client.post("/api/leads/import/commit",
                                 files={"file": ("leads.csv", _csv(rows), "text/csv")})
    assert imported.status_code == 200, imported.text
    # No split was applied at import because... wait, split IS saved so import
    # already assigns. Wipe executives to simulate the 400 already-uploaded blanks.
    await server.db.leads.update_many({}, {"$set": {"executive": "", "assignmentPending": False},
                                           "$unset": {"importedSplit": ""}})
    assert await server.db.leads.count_documents({"executive": ""}) == 10

    r = await client.post("/api/leads/split/apply-unassigned")
    assert r.status_code == 200, r.text
    assert r.json()["assigned"] == 10
    assert r.json()["requests"] == 10
    assert r.json()["byExecutive"]["Amit"] == 7
    assert r.json()["byExecutive"]["Rahul"] == 3

    leads = {d["customerName"]: d for d in await server.db.leads.find().to_list(20)}
    assert all(d.get("executive") for d in leads.values())
    assert all(d.get("assignmentPending") is True for d in leads.values())

    listed = (await client.get("/api/leads")).json()
    named = {d["customerName"]: d["executive"] for d in listed}
    assert len(named) == 10
    assert all(named.values())

    auth_db = server.client[os.environ["DB_NAME"]]
    await auth_db.users.delete_many({"email": "amit.apply@euler.com"})
    created = await client.post("/api/auth/users", json={
        "email": "amit.apply@euler.com", "password": "execPass#1",
        "name": "Amit", "role": "executive", "loginId": "amit.apply"})
    assert created.status_code == 200, created.text
    exec_c = await _login("amit.apply@euler.com", "execPass#1")
    try:
        mine = (await exec_c.get("/api/leads")).json()
        assert mine == []
        waiting = (await exec_c.get("/api/lead-requests", params={"status": "pending"})).json()
        assert len(waiting) == 7
        assert all(w.get("existingLeadId") for w in waiting)
        rid = waiting[0]["requestId"]
        lid = waiting[0]["existingLeadId"]
        assert (await exec_c.get(f"/api/leads/{lid}")).status_code == 403

        fmt = await exec_c.put(f"/api/lead-requests/{rid}", json={"budget": 185000})
        assert fmt.status_code == 200, fmt.text
        await _attach_kyc(exec_c, rid)

        ap = await client.post(f"/api/lead-requests/{rid}/approve")
        assert ap.status_code == 200, ap.text
        assert ap.json()["leadId"] == lid
        assert ap.json().get("existing") is True
        live = await server.db.leads.find_one({"leadId": lid})
        assert live.get("assignmentPending") is False
        assert live["executive"] == "Amit"
        assert (await exec_c.get(f"/api/leads/{lid}")).status_code == 200
        ids = {d["leadId"] for d in (await exec_c.get("/api/leads")).json()}
        assert lid in ids
    finally:
        await exec_c.aclose()


@pytest.mark.asyncio
async def test_reject_split_assignment_returns_lead_to_unassigned(client):
    await _ensure_staff("Amit", "Rahul")
    await client.put("/api/leads/split", json={
        "shares": [{"executive": "Amit", "pct": 100}]})
    await client.post("/api/leads/import/commit", files={
        "file": ("a.csv", _csv([_row("Send Back", "9871000001", **{"Executive": ""})]), "text/csv")})
    await server.db.leads.update_many({}, {"$set": {"executive": "", "assignmentPending": False}})
    r = await client.post("/api/leads/split/apply-unassigned")
    assert r.status_code == 200, r.text
    req = await server.db.lead_requests.find_one({"existingLeadId": r.json()["leadIds"][0]})
    rej = await client.post(f"/api/lead-requests/{req['requestId']}/reject",
                            json={"reason": "wrong book"})
    assert rej.status_code == 200, rej.text
    lead = await server.db.leads.find_one({"customerName": "Send Back"})
    assert not str(lead.get("executive") or "").strip()
    assert lead.get("assignmentPending") is False


@pytest.mark.asyncio
async def test_apply_split_requires_a_hundred_percent_plan(client):
    await _ensure_staff("Amit")
    await server.db.lead_split.replace_one({"_id": "plan"}, {
        "_id": "plan", "shares": [{"executive": "Amit", "pct": 40}],
    }, upsert=True)
    r = await client.post("/api/leads/split/apply-unassigned")
    assert r.status_code == 422
