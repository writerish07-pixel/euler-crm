# Euler CRM — Production-Grade Pass: False-Finding Purge, Re-Audit and Hardening (Claude, 25 Nov 2026)

Branch `claude/fervent-curie-mpt5mm` on `origin/main` `a5a4ec7`. Nothing merged to `main`, nothing deployed. Production CRM and the OEM app (Coulson) were used **read-only**; the browser checks logged zero non-GET API calls. Credentials are not stored in the repository.

---

## 1. False findings retracted or corrected

| Earlier finding (source) | Verdict | Proof |
|---|---|---|
| "2 leads where totalReceived ≠ receipts" (live check, 25 Nov) | **RETRACTED** | Both are refunds: LD26000020 ₹8,53,000 − ₹18,000 refund = ₹8,35,000; LD26000050 ₹10,000 − ₹10,000 on a cancelled file. All 726 production leads reconcile. |
| "Dashboard conversion 107.4% is a defect" | **RETRACTED** | The tile is labelled "bookings ÷ MTD leads"; it exceeds 100% when earlier leads book this month. Accurate to its label. |
| "4 failed OEM reads are an outage" (`oemReadsFailed: 4`) | **RETRACTED as a defect** | They are wrong health-check calls whose data the CRM never uses: `model-variant/list` is a service-module route needing `vehicle_type`; `sap-vehicle-models/facets` is 403 for dealers; `invoices-with-schemes` needs a `settlement_type`; `dealer/vehicle-booking` has no list endpoint (Coulson SPA bundle only uses `/check?id=`, POST, PUT). Cosmetic. |
| "6 booked files with ex-showroom 0" | **RETRACTED as a regression** | All booked 30 Jun – 28 Jul 2026, before Price Master enforcement (PR #11, 9 Aug). Legacy data; flagged to the owner only. |
| "My full-suite baseline was distorted by a missing SEED_DEMO_USERS flag" (my own mid-pass correction) | **RETRACTED** | `tests/conftest.py` already sets it; GitHub's own `backend-full` run on `main` reports the identical 69 failed / 1,627 passed / 11 skipped / 17 errors. |
| "Price Master reprice is broken" (17 errors → 8 failures in `test_iter27`) | **FALSE — test drift** | The test reused a seed row renamed by PR #80 (31 Aug), booked on 9 Aug (inside the 1 Sep price lock, PR #89 `6c53868`), and edited an OEM-sourced row whose ex-showroom owners cannot change since PR #117/#118. With its own manual row booked 9 Sep, all 17 pass with assertions unchanged. |
| R-01 severity "HIGH (money)" | **CORRECTED → MEDIUM** | The code regression is real (CI red on #307), but all 15 active Turbo Price Master rows in production are Coulson-synced, so no production file was hit. |
| CLD-21 "Close Won claim drops from register" (18 Nov) | **RETRACTED** | Test fixture inserted a non-manual claim with no scheme; the register rebuild correctly omits it. |
| CLD-23 "legacy Full-Benefit auto-pass" (18 Nov) | **CLOSED — superseded** | Owner-approved PR #303 "Apply a scheme only after someone selects it". |
| CLD-06 "lost update under concurrency", CLD-12 "races", CLD-14 "truncation" (18 Nov) | **CORRECTED → theoretical** | Never reproduced in-process; Cursor's #295 added `$inc` writes and removed the caps anyway. |
| CLD-16 "dealer margin GST divided twice" (18 Nov) | **CORRECTED → business question, not a defect** | No evidence of the intended formula; locked by a characterization test, left for the owner. |
| CLD-07 BotSpace part (my 18 Nov recommendation) | **CORRECTED — my recommendation caused R-04** | Dropping unsigned BotSpace callbacks lost every customer reply in production; reversed in this pass (see R-04). |
| "PRD Iter 16–17: staff can open Insurance / add manual claims" broken | **RETRACTED — intentional newer behaviour** | `53aa5de` (PR #41, 12 Aug) moved insurance and manual claims to the money desk on purpose. |
| "PR #134 OEM-match pickers widened", "PR #1 entitlements always claimed" | **RETRACTED — intentional** | Superseded by PR #243/#251 and PR #20/#33/#303. |

## 2. Re-audit and sign-off

### Sources covered

- **All 307 PRs** (305 merged, #32 closed, #161 open native app) via merge commits plus the full message of all 433 commits they introduced; GitHub API for CI runs and the post-18-Nov PRs. **281** PRs changed tests (their approvals are executable); the 24 that did not were traced by hand (PR #1, #2, #11–#14, #134 carry logic).
- **263 branches**; `git cherry` shows no approved logic stranded on unmerged branches.
- **53 Markdown files** across history incl. `memory/PRD.md` (June iterations 1–21) and all audit/remediation docs.
- **Chat history:** `docs/EULER_CRM_CHAT_HISTORY_TILL_DATE.md` (PR #308, 582 turns). The local Cursor databases (`state.vscdb`, `cursorDiskKV`, transcripts) are on your computer and were **not reachable** from this cloud session (no folder shared); the redacted export was used. 117 "again / still / was working" turns were mapped to the PRs and tests that now guard them.

### Executable approved-logic ledger

The backend suite (≈1,720 tests across 121 modules) is the ledger: each merged PR's approved behaviour is encoded in the tests it added. On `main` it has **never been green in CI** (every `backend-full` run failed). This pass classified every failure:

| Group | Count on `main` | Cause | Resolution |
|---|---|---|---|
| Real code regressions / defects | 4 tests | R-01 (#307), booking-date gate, model-ask menu, WhatsApp R-04 | Code fixed (section 3) |
| Rule changes the test never followed | 9 tests + 17 errors | #295 D1 passwords; PR #95 approval flow; KYC at booking; PR #80/#89/#117 for reprice | Tests updated to the current rule, each with the PR/commit in a comment; no money assertion weakened |
| Google Sheets guard blocked fake-service tests | 36 | `5df8196` blocked all pytest writes; conftest no-oped `gsheets.sync` | `fake_sheets` marker: real sync logic against the in-memory fake, `gsheets._init` disabled so real credentials can never load |
| Unwritten tab without a header snapshot | 5 | Since `f3a95d8` only claims are written live | `oemUnpayableWriteOff` registered as pending; unrecorded and unwritten tab skipped with an asserted reason |
| Fixture collisions | 9 | Reused chassis (PR #28 uniqueness); seeded settings doc (#295 workaround) | Unique identifiers; workaround removed |
| Order-dependent (pass alone) | ~19 | All modules share one in-memory DB via `server` | `scripts/run_tests_isolated.py` (one process per module) now used by `backend-full` |
| Environment-specific | 2 | `test_python_runtime_pin` expects Python 3.12 (CI uses 3.12; the scratch venv is 3.13) | None needed |
| Live-HTTP modules | 11 skipped | Need a running API | Marked `live_http` (unchanged) |

### Sign-off

**Zero known approved-logic regressions remain in the code on this branch.** The final isolated run results are in section 4. Remaining items are owner actions or business decisions, not code regressions:

1. Inbound WhatsApp lost **18–25 Nov** (before this fix deploys) cannot be recovered by the CRM; the replies are in BotSpace's own inbox.
2. 4 production accounts still on the default password (`accounts`, `asm`, `rm`, `oemfinance`).
3. Required CI checks on `main` need a repository admin. Without them a red check can still be merged (as #307 was).
4. Business questions left open on purpose: dealer-margin GST (CLD-16), year in IDs (CLD-17), the definition of the Conversion tile.
5. The local Cursor chat databases were not inspected (not reachable); the PR #308 export was.

## 3. Fixes, OEM features and hardening

| # | Change | Files | Root cause / wiring | Verification |
|---|---|---|---|---|
| R-01 | Booked Turbo price no longer rises ₹15,000 on an RTO/insurance edit or Price Structure open | `backend/server.py` `_is_todays_synced_list` | PR #307 treated an unsynced row's raw base as "today's sync" | Critical-suite test green; new guard fails without the fix |
| R-02 | Convert to Booking disabled while the price loads or when Price Master has no row | `frontend/src/pages/BookEnquiryDrawer.js` (+test) | Gate from PR #12 lost in PR #215 (`2592d1e`) | 2 Jest tests; fail on old code |
| R-03 | Staff 360 view no longer returns OEM Extra retained (owner P&L) | `backend/server.py` `_staff_safe_commercials` | Redaction missed lead-level keys and `dealerRetained` alias | Recursive staff-payload test |
| R-04 | **WhatsApp customer replies and delivery statuses recorded again** | `backend/server.py` `botspace_webhook`; `frontend/src/pages/Settings.js` (+test) | #295 dropped unsigned callbacks and the app had **no field to set a BotSpace secret**. Production evidence: replies on every 3-day bulk send (8–18 each) until 18 Nov, **0** on 21 and 24 Nov; 861 outbound stuck at "accepted". Now processed when no secret is saved, enforced once one is; Settings has the field, a warning, and a copyable URL carrying the secret | `test_cld07_webhooks.py` (4), WhatsApp suite 23/23, 2 Jest tests |
| R-06 | Back-dated booking without discount no longer parked as "dealer discount" | `backend/server.py` `convert_booking` | Discount gate priced on `createdDate` (today) while the payable used the booking date | Step-lock test asserts 200 (was 409); approval suites green (discounted deals still parked) |
| R-07 | WhatsApp model-interest reply "3" maps to the model the customer saw | `backend/botspace.py` | Replies numbered against today's Price Master list; the OEM import added HiCity and shifted numbers | 2 new guards fail without fix; 48/48 |
| OEM-1 | **OEM "Sold, PDI pending" in CRM** (live: 142; 55 already delivered/closed) | `coulson.py`, `oem_sync.py`, `server.py` `GET /api/oem-pdi-pending`, `OemPdiPendingCard.js`, `OemBilling.js` | Same read the Coulson tile runs; stored without personal data; fail-soft | 3 backend + 2 Jest tests; live-data run 142/140/55/2 |
| H-1 | Tests can never call the live OEM | `tests/conftest.py` | New Coulson fetch would have gone to production from CI | 184 OEM tests green |
| H-2 | Sheets sync logic tested again, still no real writes | `tests/conftest.py` `fake_sheets`; 5 Sheets modules | Guard blocked the fake-service tests | 122 pass + 3 reasoned skips; `test_pytest_blocks_sheet_writes` green |
| H-3 | Order-independent backend CI | `backend/scripts/run_tests_isolated.py`, `.github/workflows/backend-full.yml` | Shared in-memory DB across modules | Isolated run (section 4) |
| H-4 | Rule-drift tests realigned (no money assertion weakened) | `test_iter27…`, `test_change_password`, `test_deal_format`, `test_scheme_retained…`, `test_iter22_reported_defects`, `test_iter20_column_contract`, `live_headers.py`, `test_whatsapp_botspace` | Each comment names the PR/commit | Each module green |
| H-5 | Regression guard | `.cursor/rules/regression-guard.mdc` | New invariants and test discipline | — |
| H-6 | Stale docstring | `server.py` `create_manual_claim` | — | — |

Frontend: **49 suites, 203 tests pass; `CI=true` build clean** (lint warnings fail the build). There is no TypeScript or Python type-checker configured in the repository; none was added.

### Live checks (final)

CRM production: Dashboard, Lead Register, OEM Billing, Payments, Claims, Dealer Earnings load in 5.3–7.6 s, 0 console errors, 0 failed API calls, 0 write calls. OEM app: login OK; pending tasks 2 in transit / 142 PDI pending / 0 details pending.

### Owner actions after merge and deploy

1. Settings → WhatsApp → **Webhook secret**: save a long random value, press Copy on the webhook URL, paste it into BotSpace (recommended; replies already work without it after deploy).
2. Settings → User Accounts: reset `accounts`, `asm`, `rm`, `oemfinance` (or delete unused ones).
3. GitHub → Settings → Branches → `main`: require `backend-full`, `critical-regression`, `frontend-tests`, `wrangler-dry-run`.

## 4. Final verification gate

| Check | `main` (`a5a4ec7`, GitHub CI) | This branch |
|---|---|---|
| Backend full suite | 69 failed, 1,627 passed, 11 skipped, **17 errors** | **1,737 tests: 0 failed, 0 errors, 14 skipped** (11 `live_http` + 3 reasoned), one process per module. Two modules that read repo-root files (`test_iter29_daily_reports`, `test_python_runtime_pin`) were re-run in the full checkout: 58/58. |
| Critical-regression job | Red since #307 | Green (`test_deal_pass_meet_cx` fixed) |
| Frontend unit tests | 197 | **203 passed (49 suites)** |
| Frontend build | `CI=false` | **`CI=true` clean** |
| Type checking | Not configured in the repo | Not configured (not added) |
| Live CRM (read-only) | — | 6 screens, 0 console errors, 0 failed API calls, 0 writes |
| Live OEM (read-only) | — | Login OK, pending tasks read |

**Production-ready verdict:** the code on this branch has no known approved-logic regressions and passes every automated check. Production itself is not yet on this code: it needs the branch merged and deployed, then the three owner actions above (WhatsApp secret, 4 default passwords, required checks). Until it deploys, production keeps R-01 (latent, no file affected) and **R-04 (customer WhatsApp replies are still being dropped)**.
