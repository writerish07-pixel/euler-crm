# Test Execution, Coverage and Gaps (Claude)

## 1. Environment used

- Isolated Python 3.13 virtualenv in the session scratchpad (outside the repository), installed from `backend/requirements.txt` plus `pytest pytest-asyncio mongomock mongomock-motor` — the same packages Cursor's CI job installs. Production runs Python 3.12; Claude used 3.13 (the requirements file states 3.13 support).
- MongoDB: in-memory `mongomock` patched in by each test module (no database server). `GSHEET_ID` / credentials unset; the repository's `conftest.py` also blocks Sheet writes.
- Frontend: repository copied to the scratchpad, `yarn install --frozen-lockfile` there (the repository's `node_modules` was not created).
- No repository file, package file or lock file was modified. Nothing reached production.

## 2. Results

| Run | Command (summary) | Result |
|---|---|---|
| Cursor's 10-file critical suite, one process | `pytest` on the 10 files in `critical-regression.yml` | **251 passed, 0 failed** (150 s) |
| **Full backend suite** (111 files) | `pytest tests/ --continue-on-collection-errors` | **1,648 tests: 1,557 passed, 63 failed, 28 errors** (17 min 36 s) |
| Failing files re-run one by one | 21 files in isolation | 13 failures disappear (order-dependent); 50 failures + 28 errors persist |
| Frontend unit tests | `CI=true yarn test --watchAll=false` | **46 suites, 193 tests, all passed** |
| Frontend production build | `CI=false yarn build` | Success, no warnings |
| Claude independent probes | 21 in-process probes (outside repo) | Observations quoted in the findings report |
| GitHub Actions | "Critical regression" runs #3–#7, "Cloudflare Workers validate" | All green; "Workers Builds" (Cloudflare app) **failed** on PR #293 and #294 |

Not run: browser end-to-end (no backend with realistic data and no approved credentials), live-HTTP iteration tests (need a running API), any live Coulson/Exotel/BotSpace/Gmail/Sheets call, load tests, dependency vulnerability scan (would need network installs of audit tools beyond the brief), static type checking (none configured).

## 3. Classification of the 91 non-passing results

| Category | Count | Files | Meaning |
|---|---|---|---|
| Live-HTTP files, collection error | 11 errors | `test_auth_and_iter2`, `test_euler_crm`, `test_iter3/4/7/8/9/11/13_14/15/16_*` | Need `REACT_APP_BACKEND_URL` + running API. Cursor listed 4 such files; there are 11. |
| Order-dependent (pass alone) | 13 failures | `test_scheme_allocation_engine` (6), `test_turbo_sept_exshowroom_uplift` (2), `test_iter29_daily_reports` (2), `test_tcs_and_sold_chassis` (1), `test_executive_field_dashboards` (1), `test_oem_portal_claims` (1) | Modules share the imported `server` and DB state; results depend on run order. A full-suite CI job would be flaky until fixed. |
| Google Sheets tests broken by the later write guard | 36 failures | `test_iter17_gsheet_sync` (13), `test_iter19_env_safety_and_finance_views` (12), `test_iter20_column_contract` (5), `test_iter23_lead_register_fixed_header` (4), `test_iter22_header_relocation` (2) | The pytest write-block (`conftest.py`, "TEST WRITE BLOCKED") pre-empts what these tests assert. **Sheet sync currently has no working tests.** |
| Seed/catalog drift | 17 errors + 2 failures | `test_iter27_price_master_reprice` (17: "seed is missing the Hi-Load/TR-NC (HiLoad) Price Master row"), `test_iter33_model_ask` (2: model list now includes Neo HiRange etc.) | **Price Master reprice has no working tests.** |
| **Business-rule regression** | 2 failures | `test_sales_gm_dashboard`, `test_oem_portal_claims` | Sales GM can post receipts → CLD-13 |
| **Dependency drift** | 2 failures | `test_doc_compress` | pypdf 7 removed an argument → CLD-19 |
| External service not mocked | 3 failures | `test_iter22_reported_defects` | "Coulson session not configured" |
| Stale test (new KYC rule) | 1 failure | `test_scheme_retained_and_step_locks::test_booking_autofill_does_not_lock_price_for_staff` | Executive booking now needs KYC; the test does not check the booking status code (weak assertion). Claude re-verified the behaviour with KYC: price populates. |
| Date-dependent | 1 failure | `test_same_order_multi_unit::test_pack_units_own_oem_extra_scheme` | November 2026 Storm scheme (₹35,000) now applies to the test's Storm unit |
| Unexplained (needs investigation) | 3 failures | `test_iter32_lead_cancel` (claim missing after Close Won → CLD-21), `test_delivery_billing_summary` (expected −4,000 adjustment, got 0), `test_deal_format` (`KeyError: 'leadId'` on an executive create) | Root cause not established by Claude |

## 4. Coverage gaps (what no test protects today)

| Area | Gap |
|---|---|
| Lead de-duplication | The background purge (CLD-01) is skipped when `ENVIRONMENT=test`; the only test calls the internal function and asserts it **deletes**. No test asserts that distinct leads survive. |
| Boot maintenance | Turbo uplift and retry-dup purge skipped in test env; no "restart twice, nothing changes" test. |
| Claim receipts | No duplicate / over-receipt / concurrency test (CLD-06). |
| Webhooks | No test that unsigned Exotel/BotSpace requests are refused (CLD-07). |
| Public endpoints | No test that `/api/share/dashboard` contains no personal data (CLD-02). |
| Authentication | No test that production does not seed demo users or store plaintext (CLD-03/04). |
| Role redaction | No recursive test for owner-only keys in staff payloads (CLD-09). |
| OEM rebill via Invoice List | Missing on `main`; added in open PR #294 (CLD-05). Blank-invoice Sold row case missing everywhere. |
| Concurrency | No test runs against real MongoDB with more than one worker. |
| Google Sheets sync, Price Master reprice | Tests exist but no longer run successfully (section 3). |
| Frontend | 193 tests pass but are in no CI workflow; no end-to-end (Playwright/Cypress) tests exist. |
| Weak assertions | Several tests assert only HTTP 200 or a field without checking the preceding call's status (example in section 3). |

## 5. Regression-prevention verdict

A future PR **can** silently break critical functionality today:

1. Only 10 of 111 backend files run in CI; 1,397 other backend tests are never executed.
2. Frontend tests are not executed in CI.
3. No branch protection / required checks (Cursor confirms it did not set any; PR #293 merged with a failing check).
4. The existing suite is not green (78 persistent non-passes: 50 failures + 28 errors), so it cannot simply be made required without first repairing or explicitly quarantining tests with written reasons.
5. Test dependencies in CI are unpinned (`pip install pytest pytest-asyncio mongomock mongomock-motor`) and runtime dependencies use `>=`, so CI results can change without a code change (as CLD-19 shows).

## 6. Recommended test work (in order)

1. Fix the 13 order-dependent tests (isolate DB and module state per file), then run the full backend suite in CI.
2. For each persistent failure, either fix the code (CLD-13, CLD-19) or update the test with a written business justification reviewed by the owner — do not bulk-update assertions.
3. Add the gap tests in section 4, starting with CLD-01, CLD-02, CLD-06, CLD-07.
4. Add `yarn test` to CI; build with `CI=true`.
5. Make backend-full, frontend-test and build **required** on `main`.
6. Add one Playwright smoke path (login → lead → booking → payment → outstanding) against a disposable API and database.
