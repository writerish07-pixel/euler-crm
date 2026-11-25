# Verification of Cursor's Audit (Claude independent second opinion)

Baseline examined: `origin/main` `fbb0e21` (PR #293 merged 18 Nov 2026 08:21 UTC) plus open PR #294 on the same branch.

## 1. Documents located

| Document | Exists | Complete? | Notes |
|---|---|---|---|
| EULER_MASTER_FUNCTIONAL_BASELINE.md | Yes (112 lines) | Partial — states itself that `server.py` (20,280 lines) was "not re-read line by line" | Omits leads de-duplication, share board, auth storage, reset, boot jobs |
| EULER_SYSTEM_ARCHITECTURE.md | Yes (68 lines) | Partial | No mention of public routes, webhooks, boot maintenance jobs, or indexes |
| EULER_GIT_HISTORY_AND_PR_AUDIT.md | Yes (368 lines) | Metadata only — "Full diffs were not read for all 292" | Accurate counts at the time; 19 unmerged branches not analysed |
| EULER_REGRESSION_AUDIT_REPORT.md | Yes (63 lines) | Narrow — 6 items | Omits all open P0/P1 items from Cursor's own 27 Oct audit |
| EULER_AUDIT_REPAIR_REGISTER.md | Yes (45 lines) | Two repairs | AUD-001 incomplete (see CLD-05); AUD-002 correct |
| EULER_CRITICAL_REGRESSION_TEST_PLAN.md | Yes (46 lines) | Plan for 10 files | Accurate about its own limits |
| EULER_DEVELOPMENT_CHANGE_CONTROL.md | Yes (47 lines) | Policy only | Not enforced (no branch protection) |
| EULER_FINAL_PRODUCTION_READINESS_REPORT.md | Yes (47 lines) | Summary | Status AMBER; "Critical 0" unsupported |
| docs/audit/FINDINGS.md, 01-baseline-and-plan.md, 00-progress.md (Cursor phase 1, 27 Oct, PR #267) | Yes | Phase-1 register | Contains P0/P1 items that vanish from the 18 Nov set |
| AUDIT_REPORT_2026-10-16.md, EULER_PRODUCTION_AUDIT*.md, COMPARISON_REPORT.md | Yes | Earlier audits | Historical |

Note: Cursor reused the IDs AUD-001…AUD-006 on 18 Nov for different issues than the AUD-001…AUD-010 of 27 Oct, which makes the two registers impossible to reconcile by ID.

## 2. Verification matrix — major conclusions

| # | Cursor conclusion | Source | Claude verdict | Evidence |
|---|---|---|---|---|
| 1 | Critical suite (10 files): 250 pass + 1 stale assertion; after AUD-002 all pass | Test plan | **Independently verified** | Claude re-ran the 10 files in one process: **251 passed** (Cursor admitted it never did this after the edit). GitHub "Critical regression" runs #3–#7 green. |
| 2 | AUD-001 repaired: cancelled invoice cleared, rebill stays | Repair register, readiness report | **Incorrect / incomplete** | Ignores Invoice List Created rows and clears Sold rows with blank invoice (CLD-05). Cursor's own open PR #294 says the merged code "was treating that as a full cancel and clearing the lead". |
| 3 | AUD-002: catalog test expected 0 RTO, rule is family default | Repair register | **Independently verified** | `e06f5b0` (15 Sep) introduced `default_rto_insurance_for_model` in `apply_catalog`; `test_rto_insurance_deal_approval.py` requires the defaults. The test had been red on `main` for two months. |
| 4 | "Critical (R1): 0 confirmed" | Regression report | **Unsupported / incorrect** | CLD-01 (data deletion), CLD-02 (public PII), CLD-03 (default credentials) reproduced. Cursor itself graded CLD-02 (share board) **P0**, CLD-10 (reset) **P0** and CLD-03/04 (passwords) **P1** on 27 Oct. |
| 5 | Customer payable, outstanding, company outstanding, finance outstanding and dealer earnings are separate | Baseline | **Partially verified** | `compute_commercial_totals`/`compute_scheme_allocation` read; customer-benefit reduces payable; `dealerRetained = oemShare − passed`; E2E probe consistent. Dealer-funded cost is deducted only when an "authoritative allocation" flag exists (by design, unverified business intent). |
| 6 | Booking must load Price Master; empty commercial booking refused | Baseline | **Independently verified** | Probe: Turbo/Hi-Load booking populated ex-showroom, RTO, insurance without manual save; unknown variant → 422. |
| 7 | Receipt above payable rejected; identical receipt in 4 s → 409 | Baseline | **Independently verified** (customer receipts only) | Probes: 200/422 and 200/409/409. Claim receipts have no such guard (CLD-06). |
| 8 | Duplicate 10-digit mobile on create is blocked | Baseline | **Partially verified** | Concurrent identical create → one lead. But duplicates that exist are **deleted** by a background purge (CLD-01), which the baseline does not mention. |
| 9 | Roles table (Sales GM "no cash posting") | Baseline | **Incorrect** — code contradicts it | `add_payment` allows `SALES_ROLES` (incl. `sales_gm`); two existing tests asserting 403 have failed since 27 Sep (CLD-13). |
| 10 | Dealer earnings and owner commercial reports are owner-only | Baseline | **Partially verified** | Endpoints 403 for executive (probe). Executive lead payload still carries `dealerRetained` / `oemShare` in `schemeAllocationSummary` (CLD-09). |
| 11 | `oem_finance` denied everywhere except allow-list | Architecture | **Verified in code** | `auth.current_user` chokepoint read. Not penetration-tested. |
| 12 | Scheme months: no carry-forward, billed-date month | Baseline | **Independently verified** | `get_scheme_shares_for_lead` read; Oct/Nov tests pass in Claude run. |
| 13 | 750 commits, 292 PRs (290 merged, 1 open, 1 closed) | Git audit | **Verified at that time; now stale** | `main` has 752 commits; PR #293 merged, PR #294 open. |
| 14 | Unmerged branches "not reconstructed" | Git audit | **Gap closed by Claude** | 8 branches carry commits not on `main` (patch-equivalence checked). Only money-relevant one (`133dd28`, Cx Demand) has an equivalent on `main`. No approved logic found lost. |
| 15 | June audit items (extra income lines, KPIs, audit log) superseded | AUD-004 | **Verified** | Fields and `audit_log` exist on `main`. |
| 16 | New workflow protects `main` once required | Test plan / readiness | **Accurate but not in force** | No evidence of required checks; #293 merged with a failing check. Frontend tests not in any workflow (CLD-08). |
| 17 | Live HTTP tests need a running API: 4 files | AUD-005 | **Partially incorrect** | **11** files reference `REACT_APP_BACKEND_URL`; 11 collection errors in the full run. |
| 19 | "The other 101 files are still valuable" (implied healthy) | Test plan | **Incorrect** | Full run: 63 failed + 28 errors outside the critical job (CLD-20). |
| 18 | Status AMBER | Readiness | **Disagree — RED** | See final report. |

## 3. Cursor phase-1 (27 Oct) findings that disappeared from the 18 Nov reports

| Phase-1 ID | Finding | Phase-1 grade | Status on `main` today (Claude) | In 18 Nov reports? |
|---|---|---|---|---|
| AUD-001 | Pack refund judged on vehicle 1 | P0 | **Fixed** (`_refund_position` uses `_receipt_payable`, PR #270/#271) | No (fix not credited) |
| AUD-002 | Reset reuses IDs, keeps KYC/WhatsApp | **P0** | **Open** (CLD-10) | **No** |
| AUD-003 | Public share board shows customer names | **P0** | **Open, reproduced** (CLD-02) | **No** |
| AUD-004 | Plaintext passwords; demo accounts with `euler@123` | P1 | **Open, reproduced** (CLD-03, CLD-04) | **No** |
| AUD-005 | `+` in search → HTTP 500 | P1 | Fixed (`re.escape` in `_lead_search_or`) | No |
| AUD-006 | UTC "today" | P1 | Fixed (`today()` uses IST) | No |
| AUD-007 | No backend tests in CI | P1 | Partly addressed (10 files) | Partly |
| H4 | Webhooks accept posts without secret | open | **Open, reproduced** (CLD-07) | **No** |
| M1 | Sales GM can post payment | open | **Open** (CLD-13) | **No** — baseline asserts the opposite |
| M7 | CORS `*` | open | Open (CLD-15) | No |
| M10 | `leadId` not unique | open | Open (CLD-12) | No |

This is the most important reliability observation: the final report's "no critical defect" status was reached by **not carrying forward** Cursor's own unresolved P0 findings, not by fixing or disproving them.

## 4. Verification of Cursor's code repairs (file and function level)

| File / function | Change | Solves original? | Side effects |
|---|---|---|---|
| `backend/oem_sync.py` `_row_invoice` (new) | Normalised invoice reader | n/a | None found |
| `backend/oem_sync.py` `cancelled_chassis_without_live_rebill` (new) | Rebill = Sold row with different invoice | Yes for the test case | **Regression**: ignores `oem_invoices`; clears blank-invoice Sold rows (CLD-05) |
| `backend/oem_sync.py` `delink_cancelled_sold_invoices` | Deletes stale Sold rows `{chassis, invoiceNumber}` | Yes | Deletes production `oem_sold` rows on next sync; delete key uses normalised values (in practice the chassis-level delete also catches them — Claude probe). No audit trail of deleted Sold rows. Shared function also used by the delivery/flag path. |
| `backend/tests/test_oem_billing.py` | +1 helper test | — | Adequate for its case only |
| `backend/tests/test_coulson_oem_inventory.py` | Assertion 0 → 5500/10000/19000 | Aligns with later rule | **Not a weakening** — verified against `e06f5b0` and `test_rto_insurance_deal_approval.py` |
| `.github/workflows/critical-regression.yml` (new) | Runs 10 files on push/PR | Partly | No dependency pinning for pytest/mongomock (unpinned installs can change results over time) |

No new dependency, API contract change or security change was introduced by Cursor's diff. The only functional change is in OEM cancel/rebill handling, and it is incomplete.

## 5. Things Cursor overlooked (beyond its own phase-1 list)

- CLD-01: destructive lead purge on `GET /api/leads` and boot.
- CLD-06: claim receipts double-count; frontend retries them.
- CLD-09: owner P&L keys in executive lead payload.
- CLD-11: boot jobs changing money; test-env skips.
- Frontend Jest suites (193 tests) not run by Cursor and not in CI.
- The full backend suite (Claude ran it — see test coverage report).
