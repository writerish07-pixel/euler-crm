# Euler CRM — Regression Restoration, Live Test and OEM Gap Report (Claude, 25 Nov 2026)

Branch: `claude/fervent-curie-mpt5mm`, based on `origin/main` `a5a4ec7` (PR #308). No pull request was opened; nothing was merged to `main` or deployed. Production was used **read-only**: no lead, payment, claim, setting or OEM record was created, changed or deleted (the browser test logged zero non-GET API calls). Credentials were used only in memory and in a private scratch token file deleted after the run; they are not in this repository.

---

## 1. PR, branch and chat-history audit ledger

### Sources inspected

| Source | Coverage |
|---|---|
| Pull requests | All 307 numbers: 305 merged, #32 closed unmerged, #161 open (native Android/iOS). Built from merge commits plus the full message of all 433 commits they brought in (the notes Cursor generates PR bodies from); GitHub API for the 14 PRs merged after 18 Nov and for CI runs. |
| Tests as executable PR approvals | 281 of 305 merged PRs changed tests. The 24 without tests were traced by hand (PR #1, #2, #11–#14, #134 carry logic; the rest are build, deploy or docs). |
| Branches | 263 remote branches; unmerged unique work checked with `git cherry` on 18 Nov (no approved logic stranded). |
| READMEs and docs | 53 Markdown files across all history, including `memory/PRD.md` (June iterations 1–21), `docs/remediation/*`, Cursor's and Claude's audit files. |
| Cursor chat history | `docs/EULER_CRM_CHAT_HISTORY_TILL_DATE.md` (PR #308, 582 human turns). The local Cursor databases on your computer were not reachable from this cloud session; PR #308's redacted export was used instead. 117 turns report something broken "again / still / was working". |

### Verified intact (sample of the approved rules checked against current code)

| Approved rule | Source | Evidence |
|---|---|---|
| Booking loads Price Master; no row → 422 | PR #11, #13 | In-process probe (owner and executive with KYC) |
| Booked price locked against later Price Master edits | PR #89, #306 | Probe |
| Receipts persist; `totalReceived` = Σ receipts; outstanding = payable − received | PR #4, #55 | Probe; **production: all 726 leads reconcile** (two apparent gaps are refunds) |
| Over-payment 422, duplicate receipt 409 | PR #55, U4 | Probe |
| Delivery needs cleared outstanding; close needs reason, RC and plate | PRD Iter 8-9 | Probe; new in-process test |
| Executive sees only own leads; owner-only earnings | PR #79, #41 | Probe (14 endpoints) |
| Insurance and manual claims are money-desk only | PR #41 (`53aa5de`) supersedes PRD Iter 16-17 | Code + probe (deliberate change, not a regression) |
| OEM-match pickers widened | PR #243/#251 supersede PR #134 | Code (deliberate) |
| Entitlement claims only when used | PR #20/#33/#303 supersede PR #1 | Code (deliberate) |
| Cursor's #295 remediation (CLD-01…07, 09, 10, 12, 13, 24) | Claude audit | Re-run of Claude's 21 independent probes; production share board returns no names |
| Chat T561 / PR #299: RTO/insurance change moves extra discount, not the customer price | Chat + PR | **Was broken by #307 — restored (R-01)** |

### Regressions found

| ID | Severity | Approved logic and source | What broke, where, culprit | Blast radius | Fix |
|---|---|---|---|---|---|
| R-01 | HIGH (money) | PR #299, #306, chat T561, `.cursor/rules/regression-guard.mdc` ("a real booked figure … not today's sync stays") | `server.py` `_is_todays_synced_list` (added by **PR #307**, `bc8d363`/`470f59e`) did not check `oemSyncedAt`. On an unsynced Turbo row it treated the saved raw base as stale and replaced it with base + ₹15,000 on any RTO/insurance save or Price Structure open. **"Critical regression" CI failed on `main` for #307 and it was merged anyway.** | `set_price_structure`, `price_preview`, pack unit and single-vehicle files, customer payable, Additional (Dealer), dealer earnings | Return False for unsynced rows. Production impact today: none found — all 15 active Turbo Price Master rows are Coulson-synced. |
| R-02 | MEDIUM | PR #12: Confirm Booking disabled while the price loads or when Price Master has no row | `frontend/src/pages/BookEnquiryDrawer.js` (introduced by **PR #215**, `2592d1e`, 15 Oct, when `BookingModal` was replaced) only disabled on `busy`. KYC uploaded, then the API refused. | Convert to Booking for every role | `priceBlocked` gate on the button and in `submit()` |
| R-03 | MEDIUM (privacy) | Hide dealer margin from staff (28 Jul onward, PR #41, CLD-09) | `server.py` `_staff_safe_commercials` left `oemExtraSupportRetained` and `oemExtraSupport.dealerRetained` in the 360 view for staff | `GET /leads/{id}/360` for executive, TL, GM | Also strip `OWNER_PNL_LEAD_KEYS` and `dealerRetained` |
| R-04 | HIGH (live, not fixed in code — needs your decision) | WhatsApp inbox and delivery statuses (PR #57, #61, #64, chat T110) | Cursor's #295 (my CLD-07 recommendation) ignores BotSpace webhooks when no secret is set. **Production has no BotSpace webhook secret**: the newest inbound WhatsApp message on all 200 threads is 18 Nov 06:01 UTC; outbound continues to today. Customer replies have not been recorded for 7 days. | WhatsApp inbox, needs-reply, opt-out, daily-report delivery status | See section 4, action 2 |
| R-05 | LOW (docs) | PR #41 | `create_manual_claim` docstring still said staff can add | — | Docstring corrected |

### Test-suite drift found (not product defects)

`test_change_password` expects the owner list to return passwords (removed on purpose by #295); `test_whatsapp_botspace` (6) — #295 seeded a settings document that collides with older helpers in the same file; `test_iter27_price_master_reprice` (17 errors, seed rows renamed); Google Sheets tests (36) broken by the pytest write guard; 13+ order-dependent failures that pass alone. These were already listed as CLD-20 and remain open.

---

## 2. Live login test results

### CRM (production, owner, read-only)

| Check | Result |
|---|---|
| Deployed version | #295 or later (public share board returns 766 rows, 0 names) |
| Browser: login → Dashboard, Lead Register, OEM Billing, Payments, Claims, Dealer Earnings | All load (5.6–7.2 s), 0 console errors, 0 failed API calls, 0 non-GET calls |
| Data volume | 726 leads, 647 payment rows, 115 claims, 144 finance files, 93 Price Master rows, 12 users |
| Duplicate lead IDs / receipt numbers | 0 / 0 |
| Lead totals vs receipt rows | 726/726 reconcile (net of refunds) |
| Claims received above eligible | 0 |
| Booked/delivered files with ex-showroom 0 | 6 — all booked 30 Jun – 28 Jul 2026, before Price Master enforcement (PR #11, 9 Aug); legacy data, not a current defect |
| **Accounts still on the default password** | **4: `accounts` (money desk), `asm`, `rm`, `oemfinance`** |
| Exotel webhook secret | Configured |
| **BotSpace webhook secret** | **Not configured → inbound WhatsApp not recorded since 18 Nov (R-04)** |
| Coulson connection in CRM | Healthy: synced today 06:51, 263 sold, 193 claims mirrored; `oemReadsFailed: 4` (explained below) |
| Dashboard | "Conversion 107.4%" = MTD bookings ÷ MTD leads; exceeds 100% when older leads book this month (label-accurate but misleading) |

### OEM app (Coulson, dealer login, read-only)

- Login succeeded with the same host and SHA-256 scheme the CRM uses (PR #305).
- The 4 failing CRM health reads are wrong calls, not outages: `model-variant/list` (service module, needs `vehicle_type`), `sap-vehicle-models/facets` (403 for dealers), `invoices-with-schemes` (needs a `settlement_type` value), `dealer/vehicle-booking` (no list endpoint exists; the SPA only uses `/check?id=`, POST and PUT). Their data is not used by the CRM. Left unchanged; noted for cleanup.
- OEM API map from the dealer web app: **480 paths in 153 modules**; 123 sales/money paths probed with GET.

---

## 3. OEM feature gap and additions

### CRM vs OEM matrix (dealer login)

| OEM capability | Readable by dealer | In CRM | Assessment |
|---|---|---|---|
| Price list (sap-vehicle-models), order catalog, schemes, scheme packages | Yes | Yes | Working in both |
| Present / In-transit / Sold / Booked-Pilot-Demo stock, Invoice List incl. cancelled | Yes | Yes | Working in both |
| Debit-note claims and journeys | Yes | Yes | Working in both (193 mirrored) |
| **Sold, PDI pending** (`pending-tasks` → SOLD + `is_pdi_done=false`) | Yes: **142 vehicles** | No | **Added** |
| Vehicle orders / proforma invoices (`dealer/vehicle-order/pi`) | Yes | No ("Need to order" is CRM-side only) | Worth adding next (read-only order/PI status) |
| E-POD inbound trips and issues (`vehicle-pods/list`, `truck-trips`, `issue-summary`) | Yes | No | Worth adding (in-transit visibility) |
| Discount / subsidy records (`dealer/discount-subsidy`) | Yes | No | Candidate for claims reconciliation |
| Claim analytics KPIs (`claim-analytics/*`) | Yes | Partly (CRM has its own register) | Low value (duplicate) |
| Post-sale feedback calls (`post-vehicle-sales-feedback`) | Yes | No | Optional |
| Dealer P&L (`dealer-pnl/*`, needs month / showroom ids) | Partly | CRM has its own earnings | Compare later; needs owner input on definitions |
| Customer KYC amendments | Yes | No | Optional |
| Failed invoices (`vehicle-inventory/failed-invoices`) | Yes: 4,052 | No | **Not worth adding** — all OEM-internal stock-transfer errors, 0 on CRM leads |
| Vehicle booking (reserve a yard vehicle) | Write-only | No | Would write to the OEM; needs your authorisation |
| Service, warranty, workshop, field-failure, battery modules (~350 paths) | Mostly | Workshop desk only | Out of sales scope |

### Added: OEM "Sold, PDI pending" in the CRM

Why: the OEM shows 142 sold vehicles whose PDI is not done; 140 are on CRM files and **55 of those are already Delivered (31) or Close Won (24)** — vehicles with customers while the OEM still shows the pre-delivery inspection open.

| Layer | Change |
|---|---|
| OEM client | `backend/coulson.py` `fetch_pdi_pending_sold()` — the exact query the Coulson dealer page runs for its tile (`vehicle-inventory/transfer`, `vehicle_status=SOLD`, `is_pdi_done=false`), paged, GET only |
| Sync | `backend/oem_sync.py` `replace_pdi_pending()` + step in `sync_from_coulson()` — stores chassis, invoice, sold date, OEM model/variant/product, OEM delivery date into `oem_pdi_pending`; **never** the OEM row's customer name, phone or insurance data. Replaced only on a complete pull; a failed pull keeps the last list; failure never fails the sync. `pdiPendingCount` added to the sync result. |
| API | `GET /api/oem-pdi-pending` (OEM claim desk roles, same as OEM Billing) — joins to CRM files by chassis including pack units; counts total / on lead / delivered / not in CRM; delivered-first ordering. Read-only. |
| UI | `frontend/src/components/OemPdiPendingCard.js` on the OEM Billing page: counts, expandable list, lead opens in the drawer. |
| Tests | `backend/tests/test_oem_pdi_pending.py` (3), `frontend/src/components/OemPdiPendingCard.test.js` (2), `conftest.py` stub so no test can reach the live OEM. |
| Live verification | Real OEM pull through the new code into an in-memory DB with the 726 production leads: **142 stored, 140 on lead, 55 delivered, 2 not in CRM**, no personal fields stored. It reaches production on the next deploy and the next OEM sync. |

---

## 4. Completion and verification matrix

| Item | Files changed | Verification | Status |
|---|---|---|---|
| R-01 Turbo +₹15,000 on RTO edit (PR #307) | `backend/server.py` | `test_deal_pass_meet_cx` (critical suite) green; new `test_rto_edit_never_moves_saved_ex_on_unsynced_turbo_row` fails without fix, passes with; all 13 #307 tests pass | FIXED AND VERIFIED |
| R-02 Booking gate (PR #12) | `BookEnquiryDrawer.js`, `.test.js` | 2 new Jest tests; fail on old code, pass on new | FIXED AND VERIFIED |
| R-03 360 view P&L leak | `backend/server.py` | `test_staff_payloads_never_carry_owner_pnl_keys`; 11 dependent files green | FIXED AND VERIFIED |
| R-04 BotSpace inbound stopped | — | Production evidence (7 days, 0 inbound) | REQUIRES YOUR ACTION |
| R-05 Docstring | `backend/server.py` | — | FIXED |
| Unprotected approved rules (delivery/close/partial update; reset; earnings) | `backend/tests/regression_claude/test_approved_invariants.py`, `test_cld10_cld24_reset_and_earnings.py` | Pass; CLD-10 mutation-checked | ADDED |
| OEM PDI pending feature | `coulson.py`, `oem_sync.py`, `server.py`, `OemPdiPendingCard.js`, `OemBilling.js`, tests, `conftest.py` | 3 backend + 2 frontend tests; 184 existing OEM tests green; live-data run | ADDED AND VERIFIED (not deployed) |
| Regression guard | `.cursor/rules/regression-guard.mdc` | Sourced invariants + guarding test names + "never merge on red CI" | UPDATED |
| Full backend suite | — | Baseline `main` (#307): 69 failed / 1,627 passed / 11 skipped / 17 errors. Final: see commit message / section 5 | see below |
| Frontend | — | 48 suites, 201 tests passed; `CI=true` build clean | VERIFIED |

### Actions only you can take

1. **Require the CI checks on `main`** (Settings → Branches → `main`: require `critical-regression`, `backend-full`, `frontend-tests`, `wrangler-dry-run`, branches up to date). This alone would have stopped #307.
2. **Restore inbound WhatsApp:** choose a long random secret, save it in CRM Settings → WhatsApp (BotSpace) → Webhook secret, and change the webhook URL in BotSpace to `https://euler-crm-production.up.railway.app/api/integrations/botspace/webhook?secret=<same secret>`. Replies since 18 Nov are still in BotSpace's own inbox. (Alternative if you prefer: accept unsigned BotSpace calls again — I did not do this because it reopens fake-message injection.)
3. **Change the 4 default passwords** (`accounts`, `asm`, `rm`, `oemfinance`) in Settings → User Accounts → Reset password, or delete unused accounts.
4. Fix the 6 legacy June/July bookings with no ex-showroom, if they are still live deals.
5. Review and merge `claude/fervent-curie-mpt5mm` (open a PR when you want it reviewed); then deploy.

## 5. Final full-suite result

Superseded by `CLAUDE_PRODUCTION_GRADE_REPORT.md` section 4 (full suite 1,737 tests: 0 failed, 0 errors). R-04 was fixed in code in that later pass.
