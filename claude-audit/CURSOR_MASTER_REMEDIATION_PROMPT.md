# CURSOR MASTER IMPLEMENTATION PROMPT — EULER CRM REMEDIATION OF CLAUDE'S INDEPENDENT AUDIT FINDINGS

You are Cursor, acting as the implementation engineer for Euler CRM (`writerish07-pixel/euler-crm`). Read this entire prompt before changing anything. It contains 24 tracked findings (CLD-01 … CLD-24), owner decisions, execution phases, tests and acceptance criteria. Work autonomously within the safeguards below.

---

## OWNER DECISIONS (the owner may edit this block before sending; follow exactly what is written here)

| ID | Question | Decision |
|---|---|---|
| D1 (CLD-04) | Stop storing/showing staff passwords in plaintext; replace "view password" in User Accounts with "reset password (shown once)". | **APPROVED** |
| D2 (CLD-13) | Sales GM must NOT post customer or Finance-mode receipts (restore the original rule). Executives, Team Leader, Showroom Admin, Owner, Accounts keep their current receipt rights. | **APPROVED** |
| D3 (CLD-03) | Demo accounts are created only when `SEED_DEMO_USERS=1`. Existing accounts are never deleted. | **APPROVED** |
| D4 (CLD-02) | The public share board shows counts and model totals only — no customer names, no per-lead rows. | **APPROVED** |
| D5 (CLD-10) | Go-live reset also clears lead-keyed KYC documents, WhatsApp threads/messages/outbox and lead requests (it already resets lead IDs to LD26000001). | **APPROVED** |
| D6 (CLD-23) | Legacy "Full Benefit" default that auto-passes eligible scheme to the customer before the desk allocates it. | **NO CHANGE — document only** |
| D7 (CLD-16) | Dealer margin formula (GST divided out twice). | **NO CHANGE — document only** |
| D8 (CLD-17) | Year fixed in ID prefixes (LD26 / RC26). | **NO CHANGE — document only** |

If a decision says NO CHANGE, do not modify that behaviour; record the finding as REQUIRES BUSINESS DECISION in the remediation register.

---

## SECTION A — PROJECT CONTEXT

1. You (Cursor) previously audited Euler CRM and merged PR #293 (`19667af`, merge `fbb0e21`, 18 Nov 2026). It added eight `EULER_*.md` documents, `.github/workflows/critical-regression.yml`, a cancel/rebill change in `backend/oem_sync.py` (your AUD-001) and a test alignment (your AUD-002). You then opened PR #294 (branch `cursor/crm-enterprise-audit-996c`, commits `36cf78f`, `5e9b03a`) to complete AUD-001; it is open and its Codex review reports unresolved findings.
2. Claude then performed an independent forensic audit. Its reports are in `claude-audit/` (if that folder is not in your checkout, the findings below are complete on their own):
   `CLAUDE_INDEPENDENT_AUDIT_EXECUTIVE_SUMMARY.md`, `CLAUDE_FINAL_INDEPENDENT_AUDIT_REPORT.md`, `CLAUDE_ADDITIONAL_REGRESSION_FINDINGS.md`, `CLAUDE_CURSOR_AUDIT_VERIFICATION.md`, `CLAUDE_INDEPENDENT_GIT_FORENSIC_REPORT.md`, `CLAUDE_BUSINESS_LOGIC_VERIFICATION.md`, `CLAUDE_DATABASE_AND_INTEGRATION_AUDIT.md`, `CLAUDE_TEST_COVERAGE_AND_GAPS.md`.
3. Claude's overall status is **RED**. Your 18 Nov reports concluded AMBER with "0 critical". That conclusion was reached partly by not carrying forward open P0/P1 findings from your own 27 Oct audit (`docs/audit/FINDINGS.md`: AUD-002, AUD-003, AUD-004, H4, M1, M7, M10). Do not rely on your previous conclusions or repairs; verify against code.
4. Stack: FastAPI + Motor/MongoDB in `backend/` (`server.py` ≈ 20,300 lines, `commercial.py`, `auth.py`, `oem_sync.py`, `exotel.py`, `botspace.py`, `doc_compress.py`, `lead_docs.py`, `gsheets.py`); React (CRA) in `frontend/`; tests in `backend/tests/` (pytest + `mongomock_motor`) and `frontend/src/**/*.test.js` (Jest).
5. Goal of this phase: correct the verified findings below while preserving all approved Euler CRM behaviour (Section L list). This is remediation, not feature development.

---

## SECTION C — STRICT PRESERVATION RULES (apply throughout)

You may implement every correction below without asking per-item approval, but you must:
- Preserve approved business logic; do not change any money formula unless the finding below explicitly instructs it.
- Make the smallest correct change; no refactors, renames or file splits; no new features beyond what a finding requires.
- Keep existing API routes, request/response field names and Mongo field names. Additive fields are allowed only where a finding says so.
- Never delete or rewrite existing production records. No data migrations that rewrite leads, payments, claims or prices. Index creation must not drop or modify documents.
- Do not touch production data, production configuration, Railway/Render/Cloudflare settings, Coulson, Exotel, BotSpace, Gmail or Google Sheets accounts.
- Do not run tests that write to the live Google Sheet (keep `backend/tests/conftest.py` guards).
- Do not deploy. Do not merge to `main`. Open a pull request for review.
- If evidence does not establish the correct business rule, stop on that finding, document the conflict, mark it REQUIRES BUSINESS DECISION, and continue with the others.
- Do not weaken, skip, delete or bulk-rewrite existing tests to get green. Any test change needs a one-line business justification in the remediation register.
- Never print or commit secrets, passwords, Coulson sessions or sheet credentials.

---

## SECTION D — PRE-IMPLEMENTATION INVESTIGATION (do this first, record results in the register)

1. `git status`, current branch, `git rev-parse HEAD`; confirm `origin/main` SHA (Claude audited `fbb0e21`). Record any newer commits on `main` since `fbb0e21` and read their diffs.
2. Confirm there are no uncommitted changes; if there are, stop and record them — do not discard.
3. Create a working branch from current `origin/main`: `cursor/claude-remediation-996c`. Tag nothing; the recovery point is the recorded SHA.
4. Record environment: Python version, `pip freeze` for the test venv, Node version.
5. Run the baseline and save outputs to `docs/remediation/baseline/`:
   - Full backend suite: `cd backend && python -m pytest tests/ -q --continue-on-collection-errors -W ignore --junitxml=../docs/remediation/baseline/backend.xml` with `ENVIRONMENT=test`, `MONGO_URL=mongodb://localhost:27017`, `DB_NAME=euler_baseline`, `JWT_SECRET=<32+ char test value>`, `OWNER_PASSWORD=euler@123`, and no `GSHEET_*` variables. Claude's baseline: 1,648 tests, 1,557 passed, 63 failed, 28 errors.
   - Critical suite (10 files in `critical-regression.yml`): Claude got 251 passed.
   - Frontend: `cd frontend && CI=true yarn test --watchAll=false` (Claude: 46 suites, 193 passed) and `CI=false yarn build`.
6. For each finding, locate the current function by name (line numbers below are approximate as of `fbb0e21`), confirm the defect still exists, and reproduce it with a failing test before changing code. If already fixed, record ALREADY RESOLVED AND VERIFIED with evidence and do not change code.

---

## SECTION E — EXECUTION ORDER (dependencies first)

- **Phase 0 — Safety net.** Create `backend/tests/regression_claude/` with one test module per finding (`test_cld01_*.py` …). Write each reproduction test first and confirm it fails on the baseline (or record why it cannot).
- **Phase 1 — P0 data loss and exposure:** CLD-01 → CLD-02 → CLD-03 → CLD-05.
- **Phase 2 — P1 security and money integrity:** CLD-04 (same module as CLD-03) → CLD-07 → CLD-06 (backend, then frontend retry policy) → CLD-13.
- **Phase 3 — P2 correctness and integrity:** CLD-09 → CLD-10 → CLD-19 → CLD-11 → CLD-21 (investigate first) → CLD-12 → CLD-14.
- **Phase 4 — Regression protection:** CLD-20 (repair suite), then CLD-08 (CI enforcement). CI must come last so it can be green.
- **Phase 5 — P3:** CLD-15, CLD-18, CLD-22, CLD-24; document CLD-16, CLD-17, CLD-23.

After each phase run: the new regression tests, the 10-file critical suite, the full backend suite, and frontend tests if frontend changed. Compare with baseline; any newly failing test is a regression you introduced — fix it before continuing.

---

## SECTION B — FINDINGS AND REPAIR INSTRUCTIONS

Legend — Category: A bug · B regression of approved behaviour · C incomplete implementation · D data integrity · E financial/business logic · F API/integration · G security/permission · H performance · I missing tests · J architecture · K business-rule conflict.

### CLD-01 — CRITICAL — P0 — Categories A, B, D — Lead Register read and server boot silently delete genuine leads

- **Problem:** `GET /api/leads` (`list_leads`, `server.py` ~4783) calls `_ensure_retry_dups_repaired` (~8949) at most every 15 s; `_run_boot_maintenance` (~19913) calls `_repair_retry_duplicate_leads` (~9059) on every start (skipped only when `ENVIRONMENT=test`). It groups open, unbooked, payment-less leads by `_person_group_key` (last 10 mobile digits, **or normalised customer name when mobile is blank**), then per model keeps the lowest leadId and calls `_purge_retry_duplicate_lead` (~9018), which deletes the lead and its `payments, bookings, deliveries, finance, insurance, claims, activities, dealer_earnings, incentive_register, billing_summaries, whatsapp_messages, whatsapp_outbox, lead_documents`. It also force-merges different models created the same day into one pack (`_merge_retry_siblings_into_pack`). No `audit_log` entry is written.
- **Evidence (Claude reproduced):** two different customers "Ramesh Kumar", blank mobile, Hi-Load, created 2 Aug and 10 Nov, each with 1 activity and 1 KYC doc → one `GET /api/leads` deleted the 10 Nov lead, its activity and document; audit rows 0. Same customer (`9822200011` / `+91 98222 00011`), Storm EV, New, 2 Aug and 10 Nov → newer lead deleted.
- **Root cause / history:** `f12168b` (22 Sep) added an owner-only `POST /leads/repair-retry-duplicates`; `f1e648e` (22 Sep) removed that endpoint and made the purge automatic; `11bc1d1` attached it to the register load. The original cause (create-lead retries) is already prevented by `isCreateOncePath` in `frontend/src/lib/api.js` and idempotent create (3 concurrent identical creates → 1 lead).
- **Required correction:**
  1. Remove the call to `_ensure_retry_dups_repaired()` from `list_leads`, and remove `_repair_retry_duplicate_leads()` from `_run_boot_maintenance`. Keep the helper functions.
  2. Restore an owner-only endpoint `POST /api/leads/repair-retry-duplicates` (`owner_only`) with a `dryRun` query parameter defaulting to `true` that returns the candidate clusters without writing.
  3. Tighten `_repair_retry_duplicate_leads` candidate selection: never group by name alone (skip leads with no usable 10-digit mobile); require same mobile, same model, same variant and `createdDate`/creation timestamp within 10 minutes of the keeper; skip any lead with activities, documents, WhatsApp messages, payments, bookings, finance, insurance or claims. Do not perform the same-day multi-model pack merge automatically; include such clusters in the dry-run output only.
  4. Before any deletion (only when `dryRun=false`), copy the full lead document and its related documents into a new collection `leads_purged_archive` with `purgedAt`, `purgedBy`, `keptLeadId`, and write `write_audit(act, "purge-duplicate", "lead", leadId=...)`.
  5. Remove any frontend call that relied on the automatic heal only if it exists; do not add new UI beyond optionally re-adding the owner button that existed before `f1e648e`.
- **Dependencies:** `list_leads` query/filters, `_ensure_pending_deals_parked`, register performance, `tests/test_same_order_multi_unit.py` (calls `_repair_retry_duplicate_leads` directly and expects deletion of true retry triples — keep that scenario passing with the tightened rules by making its fixture leads same mobile/model/variant within minutes).
- **Regression risks:** genuine retry triples are no longer auto-cleaned (acceptable; the owner endpoint remains); register load time changes (should improve).
- **Tests to add (`regression_claude/test_cld01_lead_purge.py`):** (a) same name, blank mobile, same model, months apart, with activity + document → `GET /api/leads` twice and call `_run_boot_maintenance` (temporarily set `ENVIRONMENT` to non-test inside the test via monkeypatch) → both leads, activities and documents remain; (b) same mobile in two formats, months apart → both remain; (c) true retry triple (same mobile/model/variant, 30 s apart, no history) → dry run lists it and writes nothing; `dryRun=false` as owner deletes extras, archives them in `leads_purged_archive`, writes audit rows; (d) non-owner → 403.
- **E2E verification:** create leads through the API, load the register as executive and owner, restart the app (call startup), verify lead counts, `activities`, `lead_documents` counts unchanged.
- **Acceptance:** no code path reachable from a GET request or from boot deletes leads; tests (a)–(d) pass; full suite has no new failures.

### CLD-02 — CRITICAL — P0 — Category G — Public endpoint exposes all customer names

- **Problem:** `@public.get("/share/dashboard")` (`share_dashboard`, `server.py` ~19396) needs no authentication and returns `allLeads` (every lead's `name`, `model`, `variant`, `status`), plus names in `recentBookings` and `recentRetail`. It loads up to 5,000 leads per anonymous request.
- **Evidence:** Claude's anonymous request (no Authorization header) returned 200 with all 14 probe customers' names. Introduced in auto-commits `0052549`/`b06aac0` (6 Aug). Your 27 Oct audit graded it P0 (AUD-003).
- **Required correction (D4):** keep the route and the existing count fields (`activeBookings`, `newThisMonth`, `retailThisMonth`, `todayBookings`, `totalLeads`, `byModel`, `month`, `lastUpdated`). Return `recentBookings`, `recentRetail`, `allLeads` as lists **without** `name` (keep `date`, `model`, `variant`, `status` so `frontend/src/pages/Share.js` still renders), or as empty lists if the page renders correctly with them empty — verify `Share.js` and its rendering and choose the option that keeps the page working. Replace the full-document fetch with a projection of only the fields used (`bookingDate`, `deliveryDate`, `createdDate`, `currentStatus`, `interestedModel`, `variant`, plus fields used by `_is_booked_lead`/`_is_open_booking_lead`/`_is_delivered_lead`).
- **Dependencies:** `frontend/src/pages/Share.js`, any `share.html` legacy page (do not modify the legacy portal), the definition of booked/delivered helpers.
- **Tests:** `test_cld02_share_board.py`: anonymous GET returns 200, counts equal the owner dashboard's counts for the same data, and the JSON text contains none of the seeded customer names. Frontend: update/add a `Share` Jest test that renders with name-less rows.
- **Acceptance:** no customer name, mobile or leadId in the anonymous response; counts unchanged versus baseline for the same seed.

### CLD-03 — CRITICAL — P0 — Category G — Published default credentials re-created on every start

- **Problem:** `auth.py` `seed_users` (~710) creates the owner with `OWNER_PASSWORD` or `euler@123`, and on every start inserts missing demo users `executive`, `accounts` (money role), `asm`, `rm`, `salesgm`, `oemfinance` with password `euler@123` (published in `memory/test_credentials.md`). Claude reproduced: all seven log in with `euler@123` on a fresh DB.
- **Required correction (D3):**
  1. Create demo users only when `SEED_DEMO_USERS` is `1`/`true`. Never delete or modify existing users.
  2. If no owner exists and `OWNER_PASSWORD` is unset, and the environment is not test/dev (`_is_test_env()` false and `SEED_DEMO_USERS` not set), log a CRITICAL config error and do not create an owner with the default password (do not crash the server).
  3. Add an additive boolean `usingDefaultPassword` to each row of owner-only `GET /api/auth/users` (true when `verify_password("euler@123", passwordHash)`), and log at startup the **count** (not names, not passwords) of accounts still using the default.
  4. Update test fixtures that rely on demo users by setting `SEED_DEMO_USERS=1` in `conftest.py` or the affected modules (justify in register). Update `memory/test_credentials.md` to say demo users are test-only.
- **Dependencies:** login, `_ensure_password_plain_if_still_default`, `_is_deleted_account`, every test that logs in as `executive@euler.com`, `salesgm@euler.com`, etc.
- **Tests:** `test_cld03_seed.py`: with `SEED_DEMO_USERS` unset and empty users → no demo users created and `accounts`/`euler@123` login → 401; with it set → created; existing users untouched in both cases; `usingDefaultPassword` true for a default-hash user.
- **Acceptance:** no privileged account is auto-created with a known password outside explicit demo/test mode. **Production follow-up (owner, read-only):** list accounts with `usingDefaultPassword=true` and change their passwords.

### CLD-04 — HIGH — P1 — Category G — Plaintext passwords stored, displayed and accepted

- **Problem:** `auth.py` stores `passwordPlain` (user create ~520, password set ~562, change-password ~478, login repair ~435, seed, `workshop_api.py` ~203); `_owner_user_row` returns it as `password`; `password_matches` accepts plaintext equality. Claude reproduced: `GET /api/auth/users` returned passwords for all seeded users. Origin PR #92, #101.
- **Required correction (D1):**
  1. Stop writing `passwordPlain` everywhere (auth.py, workshop_api.py). Keep `passwordHash`.
  2. Login: if `passwordHash` is missing but a legacy `passwordPlain` exists and matches, set `passwordHash` from the typed password, then `$unset` `passwordPlain` for that user (lazy migration). Remove the plaintext comparison for users that have a valid hash.
  3. `_owner_user_row`: stop returning `password`; return `passwordSet: bool` instead. Existing `PUT /api/auth/users/{user_id}/password` remains the owner reset path; its response may return the new password once (it was typed by the owner).
  4. Frontend Settings → User Accounts (`frontend/src/pages/Settings.js` and related components): replace the password column with a "Reset password" action using the existing endpoint. No other UI changes.
  5. Do not bulk-unset `passwordPlain` in production via a migration; the lazy unset on login plus a documented owner-run script `backend/scripts/drop_plaintext_passwords.py` (dry-run by default, prints counts only) is sufficient. Do not run the script against production.
- **Dependencies:** CLD-03 (same module), login by loginId/name, workshop login, change-password, all auth tests (`test_change_password.py`, `test_user_account_password.py`, `test_staff_*`).
- **Tests:** `test_cld04_passwords.py`: create/reset/change → no `passwordPlain` in DB; users list has no `password`; legacy doc with only `passwordPlain` logs in once, then has a hash and no plaintext; wrong password still 401.
- **Acceptance:** no plaintext password stored after any write path or returned by any API.

### CLD-05 — HIGH — P0 (blocks deploy) — Categories C, A — Your AUD-001 repair on `main` clears genuinely rebilled chassis

- **Problem:** `oem_sync.py` `cancelled_chassis_without_live_rebill` and `delink_cancelled_sold_invoices` (as merged in `19667af`) decide "rebill" from `oem_sold` only and ignore `oem_invoices` Created rows (the billed source since PR #265, see `created_invoice_chassis`). Also, a Sold row whose `invoiceNumber` is blank is no longer treated as live: Claude reproduced `sold=[{chassis:MD9X1, invoiceNumber:""}]`, `cancelled=[{MD9X1, INV-A}]` → pre-repair cleared `[]`, merged code clears `["MD9X1"]` and deletes the Sold row. PR #294 fixes the Invoice List case but keeps `if not ch or not inv: return`, so the blank-invoice case remains; Codex review on #294 reports unresolved findings.
- **Required correction:**
  1. Start from PR #294's changes (cherry-pick `36cf78f` and `5e9b03a` onto your remediation branch, or reimplement equivalently). Read and resolve every Codex finding on PR #294; record each in the register.
  2. In `cancelled_chassis_without_live_rebill`, treat a Sold row for a cancelled chassis whose invoice is blank as **ambiguous**: do not clear the chassis on that basis (keep pre-repair behaviour) and do not delete that Sold row; record it in the returned stats (e.g. `ambiguousBlankInvoice`) and log it.
  3. Before `delete_many` on `oem_sold`, append each deleted row to a new collection `oem_sold_removed` (`removedAt`, `reason`) so removals are traceable.
  4. Close PR #294 as superseded only after its content is on the remediation branch (do not merge it to `main` yourself).
- **Dependencies:** `apply_sold_vehicle_ids_to_leads`, `replace_cancelled_invoices`, `sold_rows_replacing_gone`, staff-delivered flag (`oemInvoiceMissing`), pack unit drop, delivery desk, Tally summary, claim matching by chassis, scheme month by billed date.
- **Tests:** keep all tests from #293 and #294; add `test_cld05_rebill.py`: (a) cancel A + Invoice List Created B + Sold still A → lead keeps chassis, invoice becomes B; (b) cancel A + Sold row with blank invoice → lead keeps chassis, Sold row not deleted; (c) cancel A only (no other bill anywhere) → chassis cleared (your original AUD-001 case still passes); (d) different-customer Created bill → old lead loses chassis and is not stamped with the new invoice; (e) removed Sold rows appear in `oem_sold_removed`.
- **Acceptance:** all five pass; `tests/test_oem_billing.py` and `tests/test_coulson_oem_inventory.py` fully pass.

### CLD-06 — HIGH — P1 — Categories A, D, E — OEM claim receipts can be double-counted

- **Problem:** `record_claim_receipt` (`@api.post("/claims/receipt")`, `server.py` ~17587) has no duplicate guard and no cap; it computes `received = existing.receivedAmount + amount` and `$set`s it (lost update under concurrency) while `$push`ing to `receipts`. Frontend `frontend/src/lib/api.js` auto-retries it (and `/finance/{file}/receipt`) on network error/502/503/504 up to twice per base URL because they are not in `CREATE_ONCE_LEAD_ACTIONS`. Claude reproduced: eligible ₹10,000; posts ₹10,000, ₹10,000, ₹5,000 → all 200, `receivedAmount` ₹25,000, status "Received".
- **Required correction:**
  1. Duplicate guard: if the latest receipt on the same claim has the same amount, same date and same reference within `FINANCE_RECEIPT_DEDUPE_SECONDS` (10 s, reuse the constant), return 409 with a message like the finance receipt's.
  2. Over-receipt: if `eligible > 0` and `existing.receivedAmount + amount > eligible + 0.01`, return 422 explaining the remaining amount, unless the request includes an explicit `allowExcess: true` (additive optional field on `ClaimReceiptIn`, default false). Do not block manual claims whose eligible is 0 (keep current behaviour there).
  3. Use `$inc` for `receivedAmount` together with `$push` in one `update_one`; compute `claimStatus` from the post-update document (`find_one_and_update` with `return_document=True`) and then `$set` status.
  4. Apply the same `$inc` pattern to `record_financer_receipt` (`receivedAgainstFile`, ~11537) keeping its existing dedupe and cap.
  5. Frontend: add `/claims/receipt` and `^/finance/[^/]+/receipt$` to the never-retry set in `api.js` (extend `isCreateOncePath`), with Jest tests in `api.test.js`.
- **Dependencies:** claim register, `companyOutstanding`, dealer earnings write-offs (`unpayable_write_off_from_claims`), OEM claim dashboard, Google Sheet claims sync (mocked), `drop_extra_support` (blocks after cash recorded).
- **Tests:** `test_cld06_claim_receipt.py`: duplicate → 409 and one receipt; over-eligible → 422; `allowExcess` → 200; four concurrent different receipts → `receivedAmount == sum(receipts)`; financer receipt concurrency → `receivedAgainstFile == sum(receipts)`; existing claim and finance tests pass.
- **Acceptance:** a retried or doubled claim receipt cannot inflate `receivedAmount`; frontend never auto-retries money posts.

### CLD-07 — HIGH — P1 — Categories G, F — Fail-open Exotel and BotSpace webhooks

- **Problem:** `_exotel_token_ok` (`server.py` ~19208) returns without checking when `webhookSecret` is empty; `/integrations/exotel/voice|gather|recorded|status` then process any request. `botspace_webhook` (~19137) checks the secret only if configured. Claude reproduced an anonymous `POST /api/integrations/exotel/gather` with `CustomField=<leadId>&Digits=123456` setting `dealVerifyAmount=123456`, `dealVerifyStatus="answered"`, `dealVerifyMismatch=true`. Your 27 Oct audit item H4.
- **Required correction:** in `_exotel_token_ok`, when no secret is configured, allow only requests that cannot change lead data: `voice` and `gather-config` may still return ExoML, but `gather`, `recorded` and `status` must not write (return the same ExoML/JSON the handler returns for unknown calls, log a warning `EXOTEL_WEBHOOK_SECRET_MISSING`). Compare secrets with `hmac.compare_digest`. Accept the token from header `x-exotel-token` as well as the query string (keep query for compatibility). For BotSpace: when no secret is configured, keep returning 200 (BotSpace must not retry) but do not write delivery statuses or inbound messages; log a warning. Surface "webhook secret not configured" in the existing Exotel/BotSpace settings/status responses as an additive boolean.
- **Dependencies:** deal-verify page, Exotel scheduler `run_auto_calls`, Google-review call flow, WhatsApp inbox, daily-report delivery statuses.
- **Tests:** `test_cld07_webhooks.py`: no secret → forged gather/recorded/status leave the lead unchanged; correct secret (header and query) → amount recorded; wrong secret → 401; BotSpace without secret → 200 and no DB write; existing `test_exotel_deal_verify.py` and `test_whatsapp_botspace.py` pass (configure a secret in their fixtures if needed, with justification).
- **Acceptance:** no unauthenticated request can change lead or message data.

### CLD-13 — HIGH — P1 — Categories B, G (decision D2) — Sales GM can post cash receipts

- **Problem:** `add_payment` (`@api.post("/leads/{lead_id}/payments")`, ~11031) allows `(*authmod.SALES_ROLES, *authmod.MONEY_ROLES)`; `SALES_ROLES` includes `sales_gm`. Two existing tests that require 403 have failed since 27 Sep: `tests/test_sales_gm_dashboard.py` (~line 134, gets 200 and saves `RC26…`) and `tests/test_oem_portal_claims.py::test_sales_gm_and_tl_can_match_and_sync_oem_claims` (~1961, gets 404 meaning the role check passed).
- **Root cause:** `070836e` (27 Sep) replaced `money_desk_only` with `sales_staff_only` so executives could collect; Sales GM gained cash posting as a side effect; `f4a91a2` and `b1d67f7` (10 Oct, Finance mode) kept it.
- **Required correction:** in `add_payment`, deny `sales_gm` for both customer and Finance-mode receipts with 403 ("Sales GM approves deals; receipts are posted by sales staff or the money desk."). Do the role check **before** loading the lead so the response is 403 even for unknown lead ids (the OEM-portal test posts to `/api/leads/x/payments`). Check `/leads/{id}/refund` and `convert-booking` advance receipts for the same side effect and align only if the same 27 Sep change introduced it (record evidence). Do not change rights for owner, tl, team_lead, executive, accounts.
- **Tests:** the two existing tests must pass unchanged; add `test_cld13_sales_gm_receipt.py` covering customer and Finance mode, and confirm executive (own lead) and accounts still get 200.
- **Acceptance:** both existing tests green without modification.

### CLD-08 — HIGH — P1 (implemented in Phase 4) — Categories I, J — Regression protection is advisory and partial

- **Problem:** `.github/workflows/critical-regression.yml` runs 10 of 111 backend files; no workflow runs the 46 frontend Jest suites; `cloudflare-validate.yml` builds with `CI=false`; no required checks (PR #293 merged while "Workers Builds" failed); `test_apply_catalog_renames_and_drops` was red on `main` from `e06f5b0` (15 Sep) to 18 Nov unnoticed; CI test tools are unpinned.
- **Required correction (after CLD-20 makes the suite green):**
  1. Add workflow `backend-full.yml`: full `pytest tests/` with pinned `pytest`, `pytest-asyncio`, `mongomock`, `mongomock-motor` versions (pin to the versions you used for the green run) and `--junitxml` artifact; exclude only the live-HTTP files by an explicit, commented list (or a `live_http` marker), never by `-k` pattern.
  2. Keep `critical-regression.yml` and add `tests/regression_claude/` to it.
  3. Add `frontend-tests.yml`: `yarn install --frozen-lockfile` and `CI=true yarn test --watchAll=false`.
  4. Create `docs/remediation/BRANCH_PROTECTION.md` stating exactly which checks the owner must mark as required on `main` (backend-full, critical-regression, frontend-tests, wrangler-dry-run) and "require branches to be up to date". You cannot set branch protection yourself; record this as BLOCKED (needs repository admin) in the register.
  5. Do not change `CI=false` in the build until the build passes with `CI=true`; if it does, switch it and record the result.
- **Acceptance:** all workflows green on the remediation PR; a deliberately broken assertion in a scratch commit (not merged) turns `backend-full` red — record the run URL.

### CLD-09 — MEDIUM — P2 — Category G — Owner-only P&L keys reach executives

- **Problem:** `_staff_safe_lead` (`server.py` ~3091) removes only top-level `OWNER_PNL_LEAD_KEYS`; `schemeAllocationSummary` (written by `recompute_lead` ~1690 with `components` and `totals` containing `dealerRetained`, `oemShare`, `oemClaimable`, `dealerFundedBenefit`, `dealerFundedShare`) is returned unfiltered by `_lead_for_viewer` to executives/TLs. Claude reproduced the keys in an executive `GET /api/leads/{id}`.
- **Required correction:** in `_staff_safe_lead`, if `schemeAllocationSummary` is present, replace it with `_staff_safe_nested_shares(...)` (already used for previews); apply the same to each element of `units` if units carry `schemeAllocationSummary` or any `OWNER_PNL_LEAD_KEYS`. Do not change the owner response.
- **Dependencies:** `frontend/src/pages/LeadDrawer.js` and pack unit views that may read `schemeAllocationSummary.components[].customerBenefit` for staff — confirm that staff-visible fields (`customerBenefit`, `schemeAvailable`, `label`, `used`) remain.
- **Tests:** `test_cld09_staff_redaction.py`: on a lead with an active scheme (use the Nov 2026 Storm rows), recursively scan executive and team_lead responses of `GET /leads/{id}`, `GET /leads`, `GET /leads/{id}/360`, `/bookings`, `/deliveries`, `/dashboard` for any key in `OWNER_PNL_LEAD_KEYS ∪ OWNER_PNL_COMMERCIAL_KEYS ∪ OWNER_PNL_SHARE_KEYS`; none present; owner still sees them. Frontend LeadDrawer tests still pass.
- **Acceptance:** zero owner-only keys in any staff payload.

### CLD-10 — MEDIUM — P2 — Categories A, G (decision D5) — Go-live reset lets new customers inherit old KYC and chats

- **Problem:** `reset_transactions` (`@api.post("/admin/reset-transactions")`, ~19659) deletes `leads, bookings, payments, deliveries, finance, insurance, claims, activities, dealer_earnings, quotations, incentive_register, billing_summaries, sheet_sync_log` and resets the lead counter to 0, but not `lead_documents`, `whatsapp_threads`, `whatsapp_messages`, `whatsapp_outbox`, `lead_requests`. New `LD26000001` therefore links to the previous holder's documents and chats. Your 27 Oct AUD-002 (P0).
- **Required correction:** add those five collections to the deletion list; include their counts in the response and audit entry. Do not change anything else in the reset.
- **Tests:** `test_cld10_reset.py`: upload a KYC doc and a WhatsApp message on LD26000001, reset, create a new lead (gets LD26000001), assert no documents/messages/requests for it; `tests/test_fresh_start_reset.py` passes.
- **Acceptance:** after reset no lead-keyed record survives.

### CLD-19 — MEDIUM — P2 — Categories A, J — PDF compression silently disabled by pypdf 7

- **Problem:** `doc_compress.py` `compress_pdf` calls `writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)`; pypdf 7.0 removed `remove_identicals` (now `remove_duplicates`). `requirements.txt` allows `pypdf>=4.0.0`; a fresh install gets 7.x; the exception is caught and the original PDF is stored. `tests/test_doc_compress.py` fails 2/9.
- **Required correction:** call `compress_identical_objects` compatibly: try `remove_duplicates=True, remove_orphans=True`, fall back to `remove_identicals=True, remove_orphans=True` on `TypeError` (supports both major versions). Pin `pypdf>=4.0.0,<8` in `backend/requirements.txt` (keeping the lower bound). Do not change image compression.
- **Tests:** existing `test_doc_compress.py` passes with the installed pypdf 7.x; add a test that a compressible sample PDF shrinks.
- **Acceptance:** no "pdf compression failed" log for a valid PDF.

### CLD-11 — MEDIUM — P2 — Categories J, E — Boot jobs change money; Turbo overlay depends on a sync flag

- **Problem:** `_run_boot_maintenance` runs 13 heal/backfill jobs on every start. `_apply_turbo_sept_uplift_to_open_leads` (~20230) raises open Turbo leads whose saved ex-showroom equals the unsynced Price Master base by ₹15,000 and recomputes them, with no audit row; it is skipped when `ENVIRONMENT=test`, so it is untested. `_turbo_selling_ex` (~7581) adds the overlay only when the row has no `oemSyncedAt`, so two Turbo rows can differ by ₹15,000 depending only on sync state. Claude observed Price Master ₹7,70,000 vs booking ₹7,85,000 (overlay active, intended), and a back-dated (9 Aug) executive Turbo booking parked as a "dealer discount" deal.
- **Required correction (no formula change):**
  1. Make `_apply_turbo_sept_uplift_to_open_leads` idempotent and audited: record a marker in `db.system` (`{_id: "turbo_sept_uplift"}`) after the first successful run and skip on later boots; write `write_audit` for each lifted lead with old/new ex-showroom. Make it testable by allowing a test to call it directly (do not run it automatically in the test env).
  2. For every other boot job that writes lead money fields, add an audit entry when it changes a document (no behaviour change).
  3. Do not change `_turbo_selling_ex` (pricing rule). Document the sync-flag dependency in `docs/remediation/OPEN_BUSINESS_QUESTIONS.md` for the owner.
- **Tests:** `test_cld11_boot.py`: call startup twice on seeded data → second boot changes no lead money field; the uplift writes audit rows and runs once.
- **Acceptance:** repeated restarts do not change any customer payable.

### CLD-21 — MEDIUM — P2 — Investigate first — Claim missing from register after Close Won

- **Problem:** `tests/test_iter32_lead_cancel.py` (~line 880) expects a pending claim on a Close Won lead to remain in `GET /api/claims` (PR #37: "Scheme Claim Register never archives — claims stay forever"); it fails in isolation. Claude did not establish the cause; the inserted claim has `manual: False`.
- **Required action:** find the commit where this test started failing (`git bisect` on the test, in a scratch worktree) and the code path that filters it out (`list_claims` and the claim register builder). If a code change removed Close Won claims from the register without a stated business reason → restore inclusion (category B). If the test fixture is invalid for current rules (e.g. derived claims are rebuilt from scheme allocation and the fixture has no scheme) → fix the fixture with a justification. Record the evidence either way.
- **Acceptance:** test passes for a documented reason; a Close Won lead with a real derived claim stays in the register (add `test_cld21_claims_after_close.py`).

### CLD-12 — MEDIUM — P2 — Category D — Uniqueness relies on read-then-write

- **Problem:** no unique index on `leads.leadId`, `payments.receiptNumber`, `claims (leadId, componentKey, unitSno)`, or live lead `chassisNumber/invoiceNumber/numberPlate` (index block `server.py` ~20070). Dedupe and uniqueness checks are `find` then write. Claude could not reproduce a race in-process (single event loop); risk applies with multiple workers/replicas (production worker count is not in the repo).
- **Required correction (no data changes):**
  1. Add `backend/scripts/duplicate_census.py` (read-only): counts duplicates for each key above and prints counts and sample ids only. Do not run it against production.
  2. In startup, for `leads.leadId` and `payments.receiptNumber` only: check for duplicates with an aggregation; if none, create a unique index; if any exist, skip index creation and log `UNIQUE_INDEX_SKIPPED <collection> <count>` (never delete or modify documents). Expose the result in the existing finance-index status style (additive).
  3. Do not add unique indexes for chassis/invoice/plate or claims in this phase (live/cancelled rules make partial filters business-sensitive); document as recommended next step.
- **Tests:** `test_cld12_indexes.py`: clean DB → unique index exists and a duplicate insert raises; DB with a pre-existing duplicate → startup succeeds, no document removed, index skipped and logged.
- **Acceptance:** no startup failure on duplicate data; uniqueness enforced at DB level where data allows.

### CLD-14 — MEDIUM — P2 — Category H — Full scans with silent truncation

- **Problem:** money totals are computed from capped `to_list` scans: `list_dealer_earnings` (~18268: `dealer_earnings` 5000, `insurance` 8000, `claims` 8000), `list_payments` (~10990: 2000 before period filter), `list_deliveries` (5000), `share_dashboard` (5000; fixed by CLD-02 projection), `get_scheme_rows` (1000). Past the cap, totals are silently wrong. No load measurement exists.
- **Required correction (no API contract change):** in these functions, replace caps that feed totals with `to_list(None)` plus field projections, or Mongo aggregation for sums, keeping response shapes identical. Where a cap must stay for memory reasons, log `RESULT_CAP_REACHED <endpoint> <cap>` when `len(result) == cap`. Do not add pagination UI.
- **Tests:** `test_cld14_caps.py`: monkeypatch a small cap or seed > cap rows (e.g. 2,100 payments for `/payments` filtered by period) → totals equal the true sum.
- **Acceptance:** report totals are correct regardless of collection size up to tested volume.

### CLD-20 — MEDIUM — P2 (Phase 4) — Category I — Large parts of the test suite fail and are unseen

- **Baseline (Claude, isolated venv, Python 3.13):** 1,648 tests; 63 failed, 28 errors. Classification:
  - 11 collection errors — live-HTTP files needing `REACT_APP_BACKEND_URL`: `test_auth_and_iter2, test_euler_crm, test_iter3_insurance_import, test_iter4_mapping_and_lead_insurance, test_iter7_lead_edit_and_share, test_iter8_step_gating_and_scheme, test_iter9_scheme_avail_delivery_close_dupmobile, test_iter11_receipts_flows, test_iter13_14_parity, test_iter15_lead_partial_update, test_iter16_phase2_production_fixes` → add a `live_http` marker and skip them cleanly with a reason when the variable is unset (do not delete).
  - 13 order-dependent failures (pass alone): `test_scheme_allocation_engine` (6), `test_turbo_sept_exshowroom_uplift` (2), `test_iter29_daily_reports` (2), `test_tcs_and_sold_chassis` (1), `test_executive_field_dashboards` (1), `test_oem_portal_claims` (1) → fix shared state (each module must use its own isolated DB and restore patched module globals; consider an autouse fixture that resets `server.db` and module-level caches/timestamps such as `_retry_dup_last_clean_at`).
  - 36 Google Sheets failures broken by the later pytest write guard: `test_iter17_gsheet_sync` (13), `test_iter19_env_safety_and_finance_views` (12), `test_iter20_column_contract` (5), `test_iter23_lead_register_fixed_header` (4), `test_iter22_header_relocation` (2) → make them run against an in-memory fake Sheets client injected for these modules (marker `real_sheet_sync` exists) so they verify sync logic again, without any real Google call; update expected guard messages only where the guard text legitimately changed (justify).
  - 17 errors `test_iter27_price_master_reprice` ("seed is missing the Hi-Load/TR-NC (HiLoad) Price Master row") and 2 failures `test_iter33_model_ask` (model list now includes catalog additions) → update fixtures to insert the rows they need / derive expected lists from the catalog; do not change catalog data.
  - 2 `test_doc_compress` → fixed by CLD-19. 2 Sales GM receipt tests → fixed by CLD-13.
  - 3 `test_iter22_reported_defects` ("Coulson session not configured") → mock the Coulson client in those tests; no network.
  - 1 `test_scheme_retained_and_step_locks::test_booking_autofill_does_not_lock_price_for_staff` → stale: executive booking now requires KYC. Attach `kyc_aadhaar_front`, `kyc_aadhaar_back`, `kyc_pan` before booking (see `tests/test_exec_journey_docs.py::attach_docs`) and assert the booking status code (Claude verified the behaviour with KYC: price populates).
  - 1 `test_same_order_multi_unit::test_pack_units_own_oem_extra_scheme` → date-dependent (Nov 2026 Storm scheme now applies). Freeze the scheme date in the test (explicit `bookingDate`/`schemeAsOf` in a month without Storm rows, or delete scheme rows inside the test's isolated DB). Do not change scheme logic (see CLD-23).
  - 3 unexplained: `test_iter32_lead_cancel` (CLD-21), `test_delivery_billing_summary` (~line 372: expected −4,000 adjustment, got 0), `test_deal_format` (~line 170: `KeyError: 'leadId'` after an executive `POST /leads` with budget). Investigate each like CLD-21: find the breaking commit, decide code vs fixture with evidence, record it. If code is wrong and the fix is a calculation change not supported by evidence, mark REQUIRES BUSINESS DECISION.
- **Acceptance:** full backend suite: 0 failures, 0 errors; live-HTTP files skipped with reason; every test change justified in the register.

### CLD-15 — LOW — P3 — Category G — CORS, token handling hardening

- **Problem:** `CORSMiddleware(allow_origins=["*"])` (~19509) although `CORS_ORIGINS` is already listed as an optional config variable (~19698) but unused; webhook/cron tokens accepted only via query string in places; JWT 7-day expiry in `localStorage`.
- **Required correction:** if `CORS_ORIGINS` (comma-separated) is set, use it; if unset keep `["*"]` and log a warning (no production break). Accept cron/webhook tokens via header as well as query (already partly). Compare tokens with `hmac.compare_digest`. Do not change JWT lifetime or storage (document as recommendation).
- **Tests:** CORS origin honoured when set; header token accepted.

### CLD-16 — LOW — Decision D7 — Dealer margin formula

`commercial.compute_dealer_margin`: `pre_gst = ex/1.05; gross = pre_gst×0.04; net = gross/1.05`. GST removed twice; may be intentional. **No code change.** Add the question to `docs/remediation/OPEN_BUSINESS_QUESTIONS.md` with a worked example (ex-showroom ₹7,85,000) and add a characterization test locking current output so any future change is deliberate.

### CLD-17 — LOW — Decision D8 — Year in ID prefixes

`next_id(..., "RC26")`, lead prefix `LD26`. **No code change.** Document in open questions (IDs created in 2027 will still read 26).

### CLD-18 — LOW — P3 — Contradictory comment

`commercial.compute_scheme_allocation`: comment "Breakup wins on key conflict" contradicts code and the next comment (flat `schemeAllocation` decisions win). Correct the first comment only.

### CLD-22 — LOW — P3 — Stale root README and legacy portal

Root `README.md` still instructs staff to use the GitHub-Pages/Apps Script portal (`assets/js/config.js`, Apps Script `/exec`). The live product is `frontend/` + `backend/`. Update `README.md` to describe the current stack, with one line noting the legacy portal files are historical. Do not delete legacy files.

### CLD-23 — MEDIUM — Decision D6 — Legacy default auto-passes eligible scheme

For leads without explicit allocation, `benefitMode` default "Full Benefit" passes the full eligible scheme to the customer (`_component_customer_benefit`); Claude observed a November Storm unit's payable include ₹35,000 of scheme before anyone allocated it, and an explicit empty allocation removing it. **No code change.** Document in open questions with the example; add a characterization test pinning current behaviour.

### CLD-24 — LOW — P3 — Category J — Parallel implementations

`commercial.scheme_share_split_for` (always claims entitlement components) remains alongside the authoritative `compute_scheme_allocation` (claims only used components; PR #33); it is used only by a diagnostics endpoint (`server.py` ~16469). Dealer earnings are computed twice (`recompute_lead` ~1682 and `list_dealer_earnings` ~18268). **No refactor.** Add a docstring warning on `scheme_share_split_for` ("diagnostics only; money must use compute_scheme_allocation") and a test asserting `dealerTotalEarnings` on a lead equals `totalDealerEarnings` in `/dealer-earnings` for the same lead (owner, with scheme, insurance payout and extra income).

---

## SECTION L — EXISTING FUNCTIONALITY THAT WORKS AND MUST BE PROTECTED

Claude verified these; your changes must keep them passing (add tests in `regression_claude/test_protected_flows.py` where not already covered):
1. Booking auto-loads Price Master (owner booking and executive booking with KYC): Turbo Max Maxx (PV) ex-showroom ₹7,85,000 (₹7,70,000 + ₹15,000 overlay), RTO ₹5,500, insurance ₹19,000, payable ₹8,09,500; Hi-Load SR (FB120) ₹4,21,156 / ₹5,500 / ₹10,000, payable ₹4,36,656. Unknown variant → 422 and lead stays "New". Executive booking without KYC → 422.
2. Booked price does not change when Price Master is edited later.
3. Payments: advance + partial receipts persist; `totalReceived` = Σ payment rows; `customerOutstanding = customerPayable − totalReceived`; over-payment → 422 unless `allowExcess`; identical receipt within 4 s → 409; frontend never auto-retries `/leads/{id}/payments|refund|convert-booking` and `POST /leads`.
4. Concurrent identical `POST /leads` → one lead. Same chassis on a second live lead → 409.
5. Executive scoping: another executive's lead → 403; not present in `/leads, /bookings, /deliveries, /activities, /quotations, /finance, /dashboard, /inventory`; `/dealer-earnings` and `/reports/owner-commercial` → 403 for executives.
6. Scheme engine: month by billed/booking date, no carry-forward, eligibility ≠ assignment, company share first, unused component → no claim and no retained income, customer benefit not counted as dealer retained.
7. `oem_finance` role blocked from every route except its allow-list.
8. Cursor's 10-file critical suite (251 tests) and all 193 frontend tests.
9. Atomic ID counters (`next_id`).

---

## SECTION F — REGRESSION PROTECTION (mandatory)

- Every finding with a code change gets a test in `backend/tests/regression_claude/` (or a frontend test) that fails on the baseline commit and passes after the fix. Record the baseline failure output in the register.
- For money changes (CLD-06, CLD-13), also assert: payment/claim persistence, receipt history, outstanding, booking balance, the owner dashboard values and `/dealer-earnings` for the affected lead.
- Add `tests/regression_claude/` to `critical-regression.yml` and run the full suite in CI (CLD-08).

## SECTION G — END-TO-END VERIFICATION (after all phases, in-process, never production)

Run and record DB-level results for:
1. Lead create → executive KYC upload → booking → Price Master values → two partial payments → outstanding → owner dashboard and `/payments` agree.
2. Lead register load (owner, executive) and app restart → no lead/activity/document count changes (CLD-01).
3. OEM: cancel A + Created B + Sold A → lead keeps chassis with B; delivery and Tally summary show B (CLD-05).
4. Claim receipt duplicate/over-eligible blocked; claim register and dealer earnings consistent (CLD-06).
5. Anonymous share board: counts only (CLD-02). Forged Exotel gather without secret: no change (CLD-07).
6. Executive payloads contain no owner P&L keys (CLD-09). Sales GM receipt → 403 (CLD-13).
7. Reset → new LD26000001 has no documents/chats (CLD-10).
An HTTP 200 or a toast is not verification; read the Mongo documents.

## SECTION H — DOCUMENTATION TO CREATE

1. `CLAUDE_FINDINGS_REMEDIATION_REGISTER.md` (repo root): one row per CLD-01…CLD-24 with: original ID, original severity, reproduced (Y/N + test name), already resolved (Y/N), code modified (Y/N), files modified, actual correction, tests executed, results (counts), remaining risks, final status.
2. `CLAUDE_REMEDIATION_FINAL_REPORT.md` (repo root): summary, baseline vs final test counts (backend full, critical, regression_claude, frontend), and the totals listed in Section I.
3. `docs/remediation/OPEN_BUSINESS_QUESTIONS.md`: CLD-16, CLD-17, CLD-23, the Turbo sync-flag dependency (CLD-11), any finding you could not resolve from evidence.
4. `docs/remediation/BRANCH_PROTECTION.md` (CLD-08).
5. `docs/remediation/PRODUCTION_FOLLOW_UP.md`: read-only checks for the owner — accounts with `usingDefaultPassword` (CLD-03); whether Exotel/BotSpace `webhookSecret` is set (CLD-07); claims where `receivedAmount > eligibleClaim` (CLD-06); `duplicate_census.py` output (CLD-12); application logs containing `RETRY_DUP_LEADS_REPAIRED` to estimate leads already deleted (CLD-01); installed pypdf version (CLD-19).
Do not edit Claude's reports or your earlier `EULER_*.md` files, except to add a one-line pointer at the top of `EULER_FINAL_PRODUCTION_READINESS_REPORT.md` to the new remediation report.

## SECTION I — FINAL ACCEPTANCE

Give every finding exactly one status: FIXED AND VERIFIED · ALREADY RESOLVED AND VERIFIED · FIXED BUT NOT FULLY VERIFIED · NOT REPRODUCED · BLOCKED · REQUIRES BUSINESS DECISION · NOT FIXED. Provide evidence (test names, counts, DB assertions).

Report: total Claude findings (24); confirmed; already resolved; repaired; tests added; tests passed / failed / blocked (backend full, critical, regression_claude, frontend); remaining CRITICAL / HIGH / MEDIUM / LOW. Expected non-code outcomes: CLD-08 branch protection BLOCKED (admin action); CLD-16, CLD-17, CLD-23 REQUIRES BUSINESS DECISION. Do not report 100% if anything confirmed remains open.

Finish by opening one pull request from `cursor/claude-remediation-996c` to `main` titled "Remediate Claude independent audit findings (CLD-01…CLD-24)", with the register summary in the description. **Do not merge it and do not deploy.**
