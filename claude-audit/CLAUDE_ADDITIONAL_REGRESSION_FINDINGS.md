# Euler CRM — Additional Regression and Defect Findings (Claude independent audit)

Audit date: 18 Nov 2026. Code baseline: `origin/main` = `fbb0e21` (merge of PR #293, Cursor's audit).
Method: source reading, full Git history (repository unshallowed: 752 commits on `main`), execution of the existing test suites in an isolated scratch virtualenv, and an independent probe suite run in-process against the real FastAPI app with an in-memory MongoDB (`mongomock`). No production system, database, credential, Google Sheet, Coulson, Exotel or BotSpace account was touched. No repository file outside `claude-audit/` was changed.

Evidence key:
- **REPRODUCED** — the behaviour was executed and observed by a Claude probe (probe file kept outside the repo; outputs quoted below).
- **CODE-VERIFIED** — read in current source; not executed.
- **THEORETICAL** — a risk that follows from the design but could not be demonstrated in this environment.

Severity follows the brief (CRITICAL / HIGH / MEDIUM / LOW). "Production impact" statements are conditional wherever production data or configuration could not be inspected.

---

## Summary table

| ID | Sev | Module | Title | Class | Evidence |
|---|---|---|---|---|---|
| CLD-01 | CRITICAL | Leads | `GET /api/leads` and every boot silently **delete** open leads, their activity history, KYC documents and WhatsApp history | Additional regression missed by Cursor; historical logic discrepancy | REPRODUCED |
| CLD-02 | CRITICAL | Security / Share board | Unauthenticated `/api/share/dashboard` returns every customer's name, model and status | Security vulnerability (pre-existing; flagged by Cursor on 27 Oct, dropped on 18 Nov) | REPRODUCED |
| CLD-03 | CRITICAL | Security / Auth | Six demo accounts (incl. `accounts` money role and `salesgm` approver) and the owner are auto-created with the published password `euler@123` | Security vulnerability | REPRODUCED (fresh DB); production state unknown |
| CLD-04 | HIGH | Security / Auth | Staff passwords stored in plaintext (`passwordPlain`), returned by `GET /api/auth/users`, accepted by plaintext compare | Security vulnerability | REPRODUCED |
| CLD-05 | HIGH | OEM billing | Cursor's AUD-001 repair, merged to `main`, clears genuinely rebilled chassis in two situations; Cursor's own open PR #294 admits one of them | New issue introduced by Cursor; Cursor repair failure | REPRODUCED (pure function) + Cursor PR #294 |
| CLD-06 | HIGH | Claims / Money | `POST /api/claims/receipt` has no duplicate guard, no cap at the eligible amount, and the frontend auto-retries it | Additional defect missed by Cursor | REPRODUCED |
| CLD-07 | HIGH | Integrations / Security | Exotel and BotSpace webhooks are fail-open when no secret is configured; a forged call can stamp a "customer-confirmed" amount on any lead | Security vulnerability | REPRODUCED |
| CLD-08 | HIGH | Regression control | No enforced regression gate: 10 of 111 backend test files in CI, 0 of 46 frontend suites, no branch protection, merges proceed with red checks | Missing test coverage; architectural weakness | CODE-VERIFIED + GitHub check data |
| CLD-09 | MEDIUM | Roles / P&L | Executives receive owner-only P&L keys (`dealerRetained`, `oemShare`, `dealerFundedBenefit`) inside `schemeAllocationSummary` | Security (information exposure) | REPRODUCED (keys present) |
| CLD-10 | MEDIUM | Admin reset | Go-live reset restarts lead IDs at `LD26000001` but keeps KYC documents and WhatsApp threads keyed by those IDs | Pre-existing defect (Cursor phase-1 AUD-002, dropped) | CODE-VERIFIED |
| CLD-11 | MEDIUM | Pricing / Boot | Boot-time jobs rewrite money fields on every restart; two are skipped under test so never tested; Turbo +₹15,000 overlay depends on a sync flag | Architectural weakness; missing coverage | REPRODUCED (₹15,000 delta) + CODE-VERIFIED |
| CLD-12 | MEDIUM | Data integrity | No database-level uniqueness for `leadId`, `receiptNumber`, claim rows, chassis/invoice/plate; all de-duplication is read-then-write; claim/finance receipt totals use read-modify-`$set` | Architectural weakness | CODE-VERIFIED; races THEORETICAL (not reproduced in-process) |
| CLD-13 | HIGH | Roles / Money | Sales GM gained customer-receipt (cash) posting as a side effect on 27 Sep; two existing tests that forbid it have been red since | Historical logic discrepancy; unintended regression | CODE-VERIFIED + 2 failing tests |
| CLD-14 | MEDIUM | Performance | Unbounded full-collection scans with silent hard caps (`to_list(5000)`, `8000`) on reports, dashboards and the public board | Performance risk; silent truncation | CODE-VERIFIED; THEORETICAL at current volume |
| CLD-15 | LOW | Security | CORS `allow_origins=["*"]`; 7-day JWTs in `localStorage` with no revocation; webhook/cron tokens accepted in query string | Security hardening | CODE-VERIFIED |
| CLD-16 | LOW | Commercial | Dealer-margin formula divides out GST twice; needs business confirmation | Unverified functionality | CODE-VERIFIED |
| CLD-17 | LOW | IDs | Year hard-coded in ID prefixes (`LD26`, `RC26`); January 2027 IDs will still read "26" | Pre-existing defect | CODE-VERIFIED |
| CLD-18 | LOW | Code quality | Contradictory comment in `compute_scheme_allocation` about which allocation source wins | Documentation defect | CODE-VERIFIED |
| CLD-19 | MEDIUM | Documents | Unpinned `pypdf>=4.0.0`: with pypdf 7.x every PDF compression silently fails and the full-size file is stored | Pre-existing defect (dependency drift) | REPRODUCED (failing test + code) |
| CLD-20 | MEDIUM | Tests | 91 tests fail or error outside CI (13 order-dependent, 78 persistent); whole modules (Sheets sync, Price Master reprice) no longer verify anything | Missing test coverage | REPRODUCED |
| CLD-21 | MEDIUM | Claims | Close Won lead's pending claim missing from `GET /api/claims` (`test_iter32_lead_cancel`, PR #37 "claims stay forever") | Unverified — plausible regression | Failing test; root cause not established |

---

## CLD-01 — CRITICAL — Read endpoint and boot silently delete genuine leads

1. **ID:** CLD-01
2. **Severity:** CRITICAL (data loss)
3. **Module:** Lead management / duplicate prevention
4. **Files / functions:** `backend/server.py` — `list_leads` (`@api.get("/leads")`, ~line 4783) calls `_ensure_retry_dups_repaired` (~8949) → `_repair_retry_duplicate_leads` (~9059) → `_purge_retry_duplicate_lead` (~9018) and `_merge_retry_siblings_into_pack` (~9038). Also run by `_run_boot_maintenance` on every start.
5. **Evidence (REPRODUCED):**
   - Two different walk-in customers, both named "Ramesh Kumar", blank mobile, model Hi-Load, created 2 Aug and 10 Nov, each with one call activity and one KYC document. A single `GET /api/leads` as owner left only `LD26PRB001`. The 10 Nov lead, its activity and its KYC document were deleted. **Audit-log rows for the deleted lead: 0.**
   - A re-enquiry: same customer (`9822200011` vs `+91 98222 00011`), Storm EV, 2 Aug and 10 Nov, both "New". `GET /api/leads` deleted the November lead.
   - Grouping key (`_person_group_key`): last 10 digits of mobile, **or the normalised customer name when the mobile is blank**. Within a person, any 2+ open, unbooked, payment-less leads of the same model are collapsed: the lowest ID is kept and the rest are deleted from `leads`, `activities`, `lead_documents`, `whatsapp_messages`, `whatsapp_outbox`, `insurance`, `finance`, `claims` and more. Different models created on the same day are force-merged into one pack.
   - The purge runs at most every 15 s, triggered by **any** user loading the Lead Register, and on every deploy/restart.
6. **Expected behaviour:** A read endpoint never deletes data. Duplicate cleanup, if needed, is an explicit, owner-confirmed, audited action limited to provable retry artefacts (same create request, seconds apart).
7. **Actual behaviour:** Silent, unaudited deletion of any open lead that resembles another open lead of the same person and model, regardless of how far apart they were created. The **newer** lead is the one destroyed, so the most recent follow-up history is lost.
8. **Root cause:** A one-off repair for the September "triple New lead" retry bug was turned into a permanent background job with a broad similarity heuristic (no time window, name fallback, no request fingerprint).
9. **Historical reference:** `f12168b` (22 Sep 2026, "Repair retry-duplicate New files…") added the repair. `f1e648e` (22 Sep, "Remove the duplicate-fix button and heal New triples in the background") removed the owner-triggered button and the test that called the HTTP endpoint, and made it automatic. `11bc1d1` (22 Sep) attached it to the Lead Register load. The root cause (create retries) was separately fixed in the frontend (`isCreateOncePath` in `frontend/src/lib/api.js`) and by idempotent create (Claude probe: 3 concurrent identical creates → 1 lead), so the background purge is no longer needed for its original purpose.
10. **Business impact:** Loss of genuine enquiries, follow-up history and KYC scans, with no trace. Particularly likely for: walk-ins with no mobile captured; returning customers; bulk imports; OEM-created leads. Executives may see a lead vanish between page loads. Not covered by Cursor's audit at all.
11. **Recommended correction:** Remove the purge from `GET /api/leads` and from boot. If still needed, restore an owner-only, preview-then-confirm endpoint that (a) never groups by name alone, (b) requires creation within a short window (e.g. ≤ 2 minutes) and identical payload, (c) soft-deletes (archives) instead of deleting, (d) writes `audit_log`. Before any change, query production for leads whose IDs have gaps or `RETRY_DUP_LEADS_REPAIRED` log lines to estimate past loss.
12. **Verification test:** Create two open same-name/no-mobile leads and two same-mobile leads a month apart with activities and documents; call `GET /api/leads` and restart the app; assert all four leads, their activities and documents still exist.

---

## CLD-02 — CRITICAL — Public endpoint publishes every customer's name

1. **ID:** CLD-02 · 2. **Severity:** CRITICAL (personal data exposure) · 3. **Module:** Share board
4. **File / function:** `backend/server.py` `share_dashboard` (`@public.get("/share/dashboard")`, ~line 19396); frontend `frontend/src/pages/Share.js`.
5. **Evidence (REPRODUCED):** An HTTP client with **no Authorization header** received status 200 with `allLeads` containing every lead (14 in the probe DB) with `name`, `model`, `variant`, `status`, plus `recentBookings` / `recentRetail` names.
6. **Expected:** `memory/test_credentials.md` and the June PRD describe the share board as "no customer or staff data".
7. **Actual:** Full customer name list, all statuses, available to anyone with the URL. It also loads up to 5,000 leads per anonymous request (see CLD-14).
8. **Root cause:** Rows added in auto-commits `0052549` / `b06aac0` (6 Aug 2026) without an auth check.
9. **Historical reference:** Cursor's own 27 Oct audit (`docs/audit/FINDINGS.md`, AUD-003) graded this **P0** and recommended removal. It is **absent** from Cursor's 18 Nov regression report, repair register and readiness report, which state "Critical (R1): 0".
10. **Impact:** Disclosure of customer identity and purchase intent; DPDP Act exposure; enumerable by competitors.
11. **Correction:** Remove `allLeads` and names from the public payload (counts only), or require a signed share token; add rate limiting.
12. **Verification test:** Anonymous `GET /api/share/dashboard` must contain no `customerName`-derived values; authenticated owner view unchanged.

---

## CLD-03 — CRITICAL — Published default credentials re-created on every start

1. **ID:** CLD-03 · 2. **Severity:** CRITICAL if any default account is live in production; production state **not verified** · 3. **Module:** Authentication
4. **File / function:** `backend/auth.py` `seed_users` (~line 710); `memory/test_credentials.md` (committed).
5. **Evidence (REPRODUCED on a fresh DB):** after `seed_users`, logins `owner`, `accounts`, `salesgm`, `executive`, `asm`, `rm`, `oemfinance` with password `euler@123` each returned HTTP 200. The owner uses `OWNER_PASSWORD` if set, otherwise `euler@123`. Each demo account is re-inserted on every start **if missing**, unless a deletion marker exists. `_ensure_password_plain_if_still_default` explicitly anticipates accounts still on the default.
6. **Expected:** No default passwords in production; no auto-created privileged accounts.
7. **Actual:** `accounts` (in `MONEY_ROLES`: post receipts, refunds) and `salesgm` (lead approval, deal desk) are created with a password published in the repository.
8. **Root cause:** Demo seeding retained from the prototype.
9. **Historical reference:** Present since the FastAPI port (Aug 2026); demo list extended with role PRs #40, #41, #77, #94. Cursor phase-1 AUD-004 (graded P1), dropped from the 18 Nov reports.
10. **Impact:** Anyone who knows the repo (or guesses `euler@123`) may post or delete money records, approve leads and read the whole register.
11. **Correction:** Seed demo users only when `ENVIRONMENT` is a dev/test value; refuse to start in production if `OWNER_PASSWORD` is unset; force password change on first login; immediately audit production `users` for accounts whose hash still verifies `euler@123` (can be done read-only with `verify_password`).
12. **Verification test:** Start with `ENVIRONMENT=production` and an empty users collection; assert no demo accounts are created and login with `euler@123` fails.

---

## CLD-04 — HIGH — Plaintext passwords stored and displayed

1. **ID:** CLD-04 · 2. **Severity:** HIGH · 3. **Module:** Authentication / User accounts
4. **Files / functions:** `backend/auth.py` — `password_matches` (accepts plaintext equality), `login` (writes `passwordPlain` back), `_owner_user_row` (returns `password`), user create/password-set handlers (~lines 478, 520, 562); `backend/workshop_api.py` ~203.
5. **Evidence (REPRODUCED):** `GET /api/auth/users` as owner returned a non-empty `password` for all seven seeded accounts; the `users` document contains `passwordPlain`.
6. **Expected:** Only salted hashes stored; passwords never retrievable.
7. **Actual:** A single database read, backup leak, or owner-session compromise exposes every staff password (often reused elsewhere).
8. **Root cause:** Feature "owner-visible staff passwords" (PR #92, `cursor/staff-user-password-996c`, 2 Sep 2026) and PR #101.
9. **Historical reference:** Cursor phase-1 AUD-004; dropped on 18 Nov.
10. **Impact:** Credential disclosure; non-repudiation of money actions is lost (the owner can log in as any staff member).
11. **Correction:** Replace with owner-initiated **reset** (new temporary password shown once). Remove `passwordPlain` from storage after migrating, and remove the plaintext branch from `password_matches`.
12. **Verification test:** After create/reset, `users` contains no plaintext; `GET /api/auth/users` has no password field; login with plaintext-only doc fails.

---

## CLD-05 — HIGH — Cursor's AUD-001 repair, as merged, can clear a rebilled chassis

1. **ID:** CLD-05 · 2. **Severity:** HIGH · 3. **Module:** OEM billing / lead chassis
4. **File / function:** `backend/oem_sync.py` `cancelled_chassis_without_live_rebill` and `delink_cancelled_sold_invoices` (as merged in `19667af`, PR #293).
5. **Evidence:**
   - **(a) Created-list rebill ignored.** The merged function decides "rebill" from `oem_sold` only and ignores `oem_invoices` (the Invoice List, which the code elsewhere treats as the billed source — PR #265, `created_invoice_chassis`). Cursor's own follow-up PR #294 (open, unmerged, opened 08:23 UTC, two minutes after #293 merged) states: *"Delink was treating that as a full cancel and clearing the lead before the new bill could be applied."* Codex's automated review of #294 reports unresolved findings.
   - **(b) Behaviour change for Sold rows without an invoice number (REPRODUCED).** Sold row `{chassis: MD9X1, invoiceNumber: ""}` with a cancel row `{MD9X1, INV-A}`: pre-repair rule cleared `[]`; merged rule clears `["MD9X1"]`. #294 keeps the same `if not ch or not inv: return` condition, so this case remains.
6. **Expected (baseline rule, PRs #198/#259/#266):** a chassis that has a live rebill stays on the lead; only cancelled-only chassis leave.
7. **Actual:** After a Coulson cancel-and-rebill, a lead (including a delivered pack unit) can lose its chassis/invoice until a later sync re-stamps it; for (b) the `oem_sold` row is also deleted.
8. **Root cause:** Repair validated only against the single failing test; the second live source (Invoice List) and blank-invoice Sold rows were not considered.
9. **Historical reference:** `19667af` (Cursor, 18 Nov); `36cf78f`, `5e9b03a` (PR #294, open).
10. **Impact:** Delivery desk shows "not billed", Tally/claim matching by chassis fails, scheme month by billed date can shift. Cursor's readiness report states the rebill path is safe after AUD-001 — that statement is **incorrect** for `main` as it stands.
11. **Correction:** Review and complete #294 (resolve Codex findings), add the blank-invoice case, then merge before the next production deploy, or revert AUD-001 until then.
12. **Verification test:** Cancel A + Invoice List Created B + Sold still showing A → lead keeps chassis with invoice B. Cancel A + Sold row for chassis with blank invoice → lead keeps chassis.

---

## CLD-06 — HIGH — OEM claim receipts can be double-counted

1. **ID:** CLD-06 · 2. **Severity:** HIGH (financial) · 3. **Module:** Claims / receivables
4. **Files / functions:** `backend/server.py` `record_claim_receipt` (`@api.post("/claims/receipt")`, ~17587); `frontend/src/lib/api.js` `isCreateOncePath` / `withFallback`.
5. **Evidence (REPRODUCED):** Manual claim with eligible ₹10,000. Posting ₹10,000 twice (what one network retry sends) and then ₹5,000 returned `200, 200, 200`; stored `receivedAmount = 25,000`, status `Received`, three receipts in history. Frontend: only `/leads`, `/leads/{id}/payments|refund|convert-booking` are create-once; `/claims/receipt` and `/finance/{file}/receipt` are retried on network error / 502 / 503 / 504, up to twice per base URL across two base URLs.
6. **Expected:** Same protections as customer receipts (dup window → 409; amount capped at what is still due unless explicitly marked excess).
7. **Actual:** No idempotency, no cap; `receivedAmount` computed as `existing + amount` then `$set` (lost update under true concurrency — THEORETICAL; not reproduced in-process).
8. **Root cause:** Guard added to customer and financer receipts (PR #55, U4) but never to claim receipts.
9. **Historical reference:** Not mentioned by Cursor. Finance receipt has `FINANCE_RECEIPT_DEDUPE_SECONDS`; claim receipt has nothing.
10. **Impact:** OEM receivable shown as received when it is not; "Received" status closes the chase; dealer earnings / company outstanding reports overstated.
11. **Correction:** Add dup guard + over-receipt check; use `$inc`; add `/claims/receipt` and `/finance/*/receipt` to `CREATE_ONCE_LEAD_ACTIONS`; unique key on `(leadId, componentKey, unitSno)`.
12. **Verification test:** Two identical posts within 5 s → second 409; post beyond eligible → 422; concurrent posts → `receivedAmount == sum(receipts)`.

---

## CLD-07 — HIGH — Fail-open webhooks allow forged deal-verification answers

1. **ID:** CLD-07 · 2. **Severity:** HIGH (fraud-control bypass; conditional on secret not configured — production setting **not verified**) · 3. **Module:** Exotel / BotSpace integrations
4. **Files / functions:** `backend/server.py` `_exotel_token_ok` (returns early when `webhookSecret` empty), `exotel_gather` / `exotel_recorded` / `exotel_status`; `botspace_webhook` (secret optional); `backend/exotel.py` `handle_gather` → `record_amount`.
5. **Evidence (REPRODUCED):** Anonymous `POST /api/integrations/exotel/gather` with `CustomField=<leadId>&Digits=123456` returned 200 and set `dealVerifyAmount = 123456`, `dealVerifyStatus = "answered"`, `dealVerifyMismatch = true` on the lead. Lead IDs are sequential (`LD26000001…`).
6. **Expected:** Webhooks reject unsigned requests; the "customer stated amount" control can only be set by the telephony provider.
7. **Actual:** Anyone can mark any lead as verified-matching or as a mismatch, and stop auto-dial (`dealVerifyAutoStop`).
8. **Root cause:** Optional-secret design; secrets passed as query parameters.
9. **Historical reference:** Cursor phase-1 carried item H4 ("not re-tested"); absent from 18 Nov reports.
10. **Impact:** Undermines the amount-verification control introduced to detect staff collecting a different amount than recorded (PRs #217–226).
11. **Correction:** Refuse webhook traffic when no secret is configured; compare with `hmac.compare_digest`; prefer header or provider signature over query string.
12. **Verification test:** With secret unset, forged gather → 401/503 and lead unchanged.

---

## CLD-08 — HIGH — Regression protection is advisory, partial and unenforced

1. **ID:** CLD-08 · 2. **Severity:** HIGH · 3. **Module:** CI / change control
4. **Files:** `.github/workflows/critical-regression.yml`, `.github/workflows/cloudflare-validate.yml`, `EULER_DEVELOPMENT_CHANGE_CONTROL.md`.
5. **Evidence:**
   - Critical job runs 10 of 111 backend test files. The full suite (see `CLAUDE_TEST_COVERAGE_AND_GAPS.md`) contains failing tests that no CI runs.
   - Frontend: 46 Jest suites / 193 tests pass locally, but **no workflow runs them**; the build uses `CI=false`, so lint errors cannot fail it.
   - Branch protection: Cursor states it did not configure it; PR #293 was merged while the "Workers Builds" check was failing, showing that failing checks do not block merges (at least that one).
   - `test_apply_catalog_renames_and_drops` was failing on `main` from `e06f5b0` (15 Sep 2026) until Cursor's AUD-002 (18 Nov) — **two months red, unnoticed**.
   - Destructive code paths (`_repair_retry_duplicate_leads` at boot, Turbo uplift at boot) are explicitly skipped when `ENVIRONMENT=test`, so they can never be caught by CI.
6. **Expected (brief §13):** a future PR cannot silently break critical functionality.
7. **Actual:** It can. Nothing outside the 10 files is executed; nothing is required.
8. **Root cause:** CI was introduced on the audit day and scoped narrowly; no required-check policy.
9. **Historical reference:** Cursor phase-1 AUD-007 (P1).
10. **Impact:** Recurrence of the class of defects in this report.
11. **Correction:** Run the full backend suite (after fixing/quarantining with justification the currently failing tests), run frontend Jest, set `CI=true` for build lint, and make all three required checks on `main` with "require branches up to date".
12. **Verification test:** Open a PR that breaks a non-critical-suite test; confirm merge is blocked.

---

## CLD-09 — MEDIUM — Owner-only P&L keys reach executives

1. **ID:** CLD-09 · 3. **Module:** Roles / Dealer earnings privacy
4. **File / function:** `backend/server.py` `_staff_safe_lead` / `_lead_for_viewer` (~3091 / 3179); `recompute_lead` writes `schemeAllocationSummary` with `components` and `totals` that include `dealerRetained`, `oemShare`, `oemClaimable`, `dealerFundedBenefit`.
5. **Evidence (REPRODUCED):** executive `GET /api/leads/{own lead}` returned `schemeAllocationSummary.totals.dealerRetained`, `.oemShare`, `.dealerFundedBenefit`. `_staff_safe_lead` strips only top-level keys listed in `OWNER_PNL_LEAD_KEYS`; `schemeAllocationSummary` is not filtered (the separate `_staff_safe_nested_shares` is applied to commercial-preview, scheme-rule and deal-preview responses — `_staff_safe_commercials`, `_staff_safe_scheme_rules` — but never to the lead document itself). In the probe the scheme amounts were zero; on a lead with an active scheme they carry real values.
6. **Expected:** "Hide dealer margin from staff" (PR history from 28 Jul onward; Cursor baseline: dealer earnings owner-only).
7. **Actual:** Executives can read the company share and the dealer-retained amount per component through the API (the UI may not render them).
8–9. **Root cause / history:** Summary object introduced with the allocation engine (PR #21); redaction list not extended.
10. **Impact:** Staff learn dealer retention per deal, which the business deliberately hides.
11. **Correction:** Apply `_staff_safe_nested_shares` to `schemeAllocationSummary` (and any `units[*]` copies) inside `_staff_safe_lead`.
12. **Test:** Recursive key scan of every executive/TL response for `OWNER_PNL_*` keys.

---

## CLD-10 — MEDIUM — Go-live reset lets new customers inherit old documents

1. **ID:** CLD-10 · 3. **Module:** Admin reset · 4. `backend/server.py` `reset_transactions` (~19659).
5. **Evidence (CODE-VERIFIED):** deletes `leads, bookings, payments, … sheet_sync_log`, resets the lead counter to 0 ("nextLeadId": "LD26000001"), but does **not** delete `lead_documents` (KYC), `whatsapp_threads`, `whatsapp_messages`, `lead_requests`, `deal_requests`. New `LD26000001` therefore links to the previous `LD26000001`'s KYC scans and chat history.
6–7. Expected: a clean start; actual: cross-customer document exposure. Owner-only and rare.
9. Cursor phase-1 AUD-002 (graded **P0**); dropped on 18 Nov.
11. Delete all lead-keyed collections, or never reset the counter.
12. Test: upload doc to LD26000001, reset, create lead, assert no documents.

---

## CLD-11 — MEDIUM — Boot jobs change money; Turbo overlay is state-dependent

1. **ID:** CLD-11 · 3. **Module:** Pricing / startup · 4. `backend/server.py` `_run_boot_maintenance` (~19913), `_apply_turbo_sept_uplift_to_open_leads` (~20230), `_turbo_selling_ex` (~7581).
5. **Evidence:** REPRODUCED: Turbo Max Maxx (PV) Price Master row ₹7,70,000; booking populated ₹7,85,000 (+₹15,000 overlay). CODE-VERIFIED: the overlay is skipped once a row has `oemSyncedAt`, so two Turbo variants can differ by ₹15,000 depending only on whether Coulson has synced that row. On every restart, any open Turbo lead whose saved ex-showroom equals the unsynced base is silently lifted by ₹15,000 and recomputed (no audit row). Twelve other repair/backfill jobs run at boot; `turbo_sept_uplift` and `_repair_retry_duplicate_leads` are skipped in test env.
6–7. Expected: price changes are explicit, dated and audited; actual: restarts can change customer payable.
10. Impact: payable can change between a quote and the next deploy; a manually set price equal to the OEM base is overwritten.
11. Move one-time migrations to explicit, versioned, audited scripts with a "done" marker; make the Turbo rule a dated Price Master field rather than code.
12. Test: start app twice; assert no lead money field changes on the second start.

---

## CLD-12 — MEDIUM — Uniqueness depends on read-then-write

1. **ID:** CLD-12 · 3. **Module:** Database integrity · 4. `server.py` index creation (~20070–20101).
5. **Evidence:** `leads.leadId`, `payments.receiptNumber`, `claims (leadId, componentKey[, unitSno])`, lead `chassisNumber/invoiceNumber/numberPlate` have **no unique index**. Duplicate-receipt, over-payment and chassis-uniqueness checks are `find` then `insert/update`. In-process probes did **not** reproduce a race (concurrent identical receipts → 200/409/409; concurrent over-payment → 200/422; concurrent same-chassis delivery → 200/409; concurrent identical lead create → one lead). Production worker count is not in the repository (Railway config is external).
7. Actual: protection holds within one event loop when awaits happen to serialise; it does not hold across multiple workers/replicas.
11. Add unique (partial) indexes after a read-only duplicate census in production; use `$inc` for running totals.
12. Test: real MongoDB + 2 uvicorn workers + parallel requests.

---

## CLD-13 — HIGH — Sales GM can post cash receipts (unintended since 27 Sep)

1. **ID:** CLD-13 · 2. **Severity:** HIGH (segregation of duties on money) · 3. **Module:** Roles / payments
4. **File / function:** `backend/server.py` `add_payment` (~11031) — allows `SALES_ROLES + MONEY_ROLES`; `backend/auth.py` `SALES_ROLES` includes `sales_gm`.
5. **Evidence:** Two existing tests assert Sales GM gets 403 on `POST /leads/{id}/payments`: `tests/test_sales_gm_dashboard.py:134` (fails: **200**, receipt `RC26000101` saved) and `tests/test_oem_portal_claims.py:1961` (fails: 404 instead of 403, i.e. the role check let Sales GM through). Both fail in isolation too.
6. **Expected:** PR #94 ("Sales GM dashboard and showroom sales role") and Cursor's baseline: Sales GM approves and chases, "no cash posting". Money desk = owner, Showroom Admin (`tl`), accounts.
7. **Actual:** Sales GM (and, since `b1d67f7`, all sales roles) can post customer and Finance-mode receipts.
8. **Root cause:** `070836e` (27 Sep, "Hide scheme from executives and let them collect after booking") replaced `money_desk_only` with `sales_staff_only` to let executives collect; Sales GM is in `SALES_ROLES`, so it gained cash posting as a side effect. `f4a91a2` (27 Sep) and `b1d67f7` (10 Oct) kept and widened it.
9. **History:** The guarding tests went red on 27 Sep and stayed red for 7 weeks because no CI ran them. Cursor phase-1 M1 "not re-tested"; Cursor's 18 Nov baseline asserts the opposite of the code.
10. **Impact:** Segregation of duties between approval (GM) and cash collection is lost.
11. **Correction:** Owner to confirm the intended rule; if the tests are right, exclude `sales_gm` from receipt posting explicitly.
12. **Test:** the two existing tests, once added to the required CI job.

---

## CLD-14 — MEDIUM — Full scans with silent truncation

Examples (CODE-VERIFIED): `share_dashboard` `leads.find().to_list(5000)` per anonymous request; `list_dealer_earnings` `dealer_earnings.to_list(5000)`, `insurance.to_list(8000)`, `claims.to_list(8000)`; `list_deliveries` `to_list(5000)`; `list_payments` `to_list(2000)` before period filter; `get_scheme_rows` `to_list(1000)`; `_repair_retry_duplicate_leads` up to 15,000 leads every 15 s. Past those counts totals become silently wrong; no pagination. No load measurement was possible — risk is THEORETICAL at today's volume (the code comments themselves cite 15k-row scans timing out the register).

---

## CLD-19 — MEDIUM — PDF compression silently disabled by dependency drift

`backend/doc_compress.py` `compress_pdf` calls `writer.compress_identical_objects(remove_identicals=True, …)`. pypdf 7.0 removed that argument; `requirements.txt` allows `pypdf>=4.0.0`, so a fresh install resolves 7.x (7.1.0 here). The exception is caught and the original is stored ("pdf compression failed; keeping original"). `tests/test_doc_compress.py` fails 2/9 (DeprecationError; size not reduced). The production pypdf version is unknown. Impact: PR #273's purpose (smaller documents in MongoDB) is defeated, and large scans approach the 16 MB document limit. Fix: pin `pypdf<7` or switch to `remove_duplicates`; pin all runtime dependencies.

## CLD-20 — MEDIUM — Large parts of the test suite are broken and unseen

Full run (1,648 tests): 1,557 passed, 63 failed, 28 errors. Classification in `CLAUDE_TEST_COVERAGE_AND_GAPS.md`. Key point: the Google Sheets sync tests (36 failures) and the Price Master reprice tests (17 errors: "seed is missing the Hi-Load/TR-NC (HiLoad) Price Master row" after catalog renames) no longer exercise the code they were written for, so those modules currently have **no working regression tests**.

## CLD-21 — MEDIUM (unverified) — Claim register after Close Won

`tests/test_iter32_lead_cancel.py:880` expects a pending claim on a Close Won lead to stay in `GET /api/claims` (PR #37: "Scheme Claim Register never archives — claims stay forever"); it fails in isolation. Claude did not establish whether the cause is a product change or test data (the claim row is inserted with `manual: False`). Needs investigation before any claim-register change.

## CLD-15 to CLD-18 — LOW

- **CLD-15:** `CORSMiddleware(allow_origins=["*"])`; JWT 7-day expiry, stored in `localStorage`, not revocable on role change except via user deletion; webhook/cron tokens accepted in query string (logged by proxies). Hardening.
- **CLD-16:** `commercial.compute_dealer_margin`: `pre_gst = ex/1.05; gross = pre_gst×4%; net = gross/1.05`. GST is removed twice. May be intentional (margin invoiced GST-inclusive) — owner/accountant to confirm against the OEM dealer agreement. Not changed by Cursor; not covered by a test that states the business source.
- **CLD-17:** `next_id("receipt","RC26")`, lead prefix `LD26`. Fixed year in ID text from 2027.
- **CLD-18:** `compute_scheme_allocation` comment says "Breakup wins on key conflict" two lines above code and a comment where flat decisions win. Code behaviour is consistent with PUT `/scheme-allocation` being authoritative; fix the comment.

---

## Positive results (independently verified, not findings)

- Price Master auto-populates booking for Turbo Max and Hi-Load without a manual price save; unknown variant is refused with 422 and the lead stays "New". Booked price does not move when Price Master later changes (price lock).
- Payments: two partial receipts persisted; `totalReceived` equals the sum of payment rows; `customerOutstanding = customerPayable − received`; over-payment refused with 422 unless `allowExcess`; identical receipt within 4 s refused with 409.
- Executive scoping: another executive's lead is 403; not visible on 14 list endpoints tested; `dealer-earnings` and `owner-commercial` 403 for executives.
- ID counters are atomic (`find_one_and_update $inc`).
- The September Cx Demand rule on the unmerged branch `cursor/deal-pass-meet-cx-996c` (`133dd28`) **is present on `main`** through a later commit (`server.py` ~1576) — not lost.

---

## Addendum (added when building the Cursor remediation prompt)

Items already described in the companion reports, now given tracking IDs:

| ID | Sev | Module | Title | Source / evidence |
|---|---|---|---|---|
| CLD-22 | LOW | Documentation | Root `README.md` still instructs staff to use the GitHub-Pages / Apps Script portal | Git forensic report §6; README re-read 18 Nov (CODE-VERIFIED) |
| CLD-23 | MEDIUM | Schemes | Legacy "Full Benefit" default auto-passes eligible scheme before the desk allocates it (₹35,000 on a Nov Storm unit); payable changes when the scheme is first saved — owner decision | Business logic report §6; `test_same_order_multi_unit` investigation (REPRODUCED) |
| CLD-24 | LOW | Architecture | Parallel implementations: `scheme_share_split_for` vs `compute_scheme_allocation`; dealer earnings computed twice | Git forensic report §6 (CODE-VERIFIED) |

Also added to CLD-20: two unexplained failing tests (`test_delivery_billing_summary` ~372, `test_deal_format` ~170) to investigate.
