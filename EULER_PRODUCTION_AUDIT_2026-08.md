# EULER CRM — CTO AUDIT & AUG'26 SCHEME UPDATE
**Date:** 8 Aug 2026 · **Supersedes:** `EULER_PRODUCTION_AUDIT.md` (2026-06) and `COMPARISON_REPORT.md` for the items below — those docs are kept for history, not as current status.
**Scope:** (1) a security review of the repo, (2) a fresh line-by-line parity audit of the app (`backend/`, `frontend/`) against the Apps Script source of truth (`_incoming/final_fix_extracted/final fix/*.gs`), (3) fixes for every confirmed gap, (4) the Aug'26 "Freedom From Fuel" scheme + Manpower Incentive update.

---

## 1. Security — credential leak (fixed in repo, action needed from you)

`backend/gsheets_credentials.json` — the real Google service-account private key for `euler-crm-service@shubham-motors-ai-agent.iam.gserviceaccount.com` — was committed **in plaintext** to the repo (added in commit `0df7620`).

**Done:**
- Removed the file from the tracked working tree.
- Hardened `.gitignore` (`*credentials*.json`, `backend/gsheets_credentials.json`, `__pycache__/`) so this can't silently recur.
- Confirmed `backend/gsheets.py` already reads the key path from `GSHEET_CREDENTIALS_PATH` (an env var) — the code was fine, only the checked-in file was the problem.

**Still your action, not something I can do from here:**
1. **Rotate the key** in Google Cloud Console (IAM & Admin → Service Accounts → this account → Keys) — generate a new key, delete the old one (`private_key_id` starting `4dcdedf1...`). The version in git history and in this chat should be treated as compromised regardless of what else happens.
2. Decide if you want git **history** rewritten to purge the old commit (`0df7620`) entirely. I deliberately did not do this without asking — it requires a force-push and breaks any other clone/branch of this repo. Say the word and I'll do it carefully.
3. Store the new key file only as a deploy-time secret (e.g. platform env var / secret manager), never in the repo.

---

## 2. Architecture reality check

The repo is **not** a copy of the Apps Script system. It's a full rewrite by "emergent": **React + FastAPI + MongoDB**, with a one-way sync (`backend/gsheets.py`) that appends new Leads/Bookings/Payments/Deliveries/Claims to your live Google Sheet via the service account. The `.gs` files you shared are the reference the business logic (`backend/commercial.py`) was ported from — they don't run directly.

Per your confirmation, this session kept that architecture and drove it to closer parity with the `.gs` engine rather than rebuilding the Apps Script + GitHub Pages stack from scratch.

---

## 3. Parity audit findings & disposition

A full read-through of every `.gs` module against `backend/server.py` (2,338 lines), `backend/commercial.py` (637 lines) and the React frontend found **one critical money bug**, three high-severity gaps, and one unbuilt feature. All are now fixed except the two that need your input (noted below).

| ID | Finding | Fix |
|---|---|---|
| **C-NEW-1 (CRITICAL)** | The "Free RTO + Free Insurance" scheme entitlement (₹20,000/booking on HiCity & Hirange) was an **automatic, entitlement-based** claim in the `.gs` engine (`schemeShareSplitFor_`'s `forceInclude` branch) — not something staff type in. The Python port never implemented this at all: `rtoInsuranceBenefit` didn't exist anywhere in `commercial.py`. **Every HiCity/Hirange claim in the app was silently short by ₹20,000.** | Ported the exact entitlement logic into `scheme_share_split_for()` in `commercial.py`, and extended it to the new Aug'26 split components (`rtoBenefit`, `insuranceBenefit`). Verified against real scheme data: a HiCity Aug booking with zero manually-entered offers now correctly shows ₹20,000 auto-claimed; July bookings still resolve the old combined `rtoInsuranceBenefit` unchanged (no regression). |
| **H-NEW-1 (HIGH)** | Dealer Earnings only captured 4 of the source's 10 income lines (Documentation/Warranty/RSA/Referral). Finance Incentive, Accessories Margin, Exchange Margin, Campaign Incentive, Other Income, and Customer Insurance Benefit Passed had no input field, no API, no report line — Dealer Earnings was structurally understated. | Added all 6 missing fields to `ExtraIncomeIn`, `recompute_lead()`, `/reports/dealer-earnings`, and the Lead Drawer's Extra Income card. |
| **H-NEW-2 (HIGH)** | Per-claim ageing reset to 0 the moment a claim was marked Received (source freezes it at actual turnaround time). The Owner Commercial Report was also missing the aggregate "Average Claim Ageing" KPI entirely. | `_claim_ageing_days()` now takes an end date and freezes ageing at `approvedDate` once Received, matching `computeClaimAgeing_`. Added `avgClaimAgeingDays` to `/reports/owner-commercial` and the Owner Commercial Report page. |
| **H-NEW-3 (HIGH)** | Finance "Overdue" had collapsed into "any pending balance" — the source's real definition (>2 days since delivery, an SLA breach) was gone, so every pending finance file looked equally urgent. | Ported `enrichFinanceFilesWithDelivery_`'s day-since-delivery SLA logic. `/finance?view=overdue` and the dashboard now use the real 2-day SLA breach, with new `financeOverdueCount`/`financeOverdueAmount` KPIs surfaced on the Dashboard. |
| **M-NEW-1 (MEDIUM)** | Incentive Register (executive payout tracking, auto-created on delivery) was entirely unbuilt — `Incentive Master` data existed but nothing computed payouts from it. | Implemented `_upsert_incentive_register_on_delivery()` (fires on Mark Delivered), `GET /incentive-register`, owner-only `PUT /incentive-register/{id}/pay`, and a register table + "Mark Paid" action on the Incentive Master page. Category mapping updated for Aug'26 (HiCity and Hirange now their own categories, not lumped into "3WC" as the old circular had it). |
| **M-NEW-2 (MEDIUM)** | The app's own in-app `/reports/production-audit` self-test asserted "PASS" on C1/H3 in a way that overclaimed completeness (partial fixes reported as done). | Updated the check messages to accurately describe what's covered now that the underlying gaps are actually closed. |

**Already correct, re-verified, no change needed:** payment-cap-at-payable (C2), Record Receipt flows (C3), dashboard KPI set (H1 — conversion%, MTD revenue, follow-ups all present), Insurance lead dropdown (H2), RSA/AMC charge input (H5), audit log (H4), duplicate-mobile block, DB indexes, double-submit guard. The June audit doc's punch list was stale on all of these.

**Still open (not fixed this pass, low money-risk):** Google Sheet sync stays one-way/append-only (edits/deletes don't propagate) — confirm if that's acceptable or if you need two-way sync. Finer role granularity (Reception/Sales/TL/GM/Accounts beyond Owner/Executive) — confirm if needed.

---

## 4. Aug'26 "Freedom From Fuel" scheme — applied

Extracted from `Aug26_Consumer_Scheme.pdf` (circular EM/08-2026/001, 8 Aug – 31 Aug 2026) and added to `backend/data/euler_raw.json`'s Scheme Master / Incentive Master (the seed source for the app's DB):

| Model | Consumer Scheme | Loyalty | RTO Benefit | Insurance Benefit |
|---|---|---|---|---|
| HiLoad (Non-GBT) | ₹5,000 dealer | ₹10,000 company | — | ₹10,000 company |
| HiCity (XR) | ₹25,000 company | ₹10,000 company | ₹10,000 company | ₹10,000 company |
| Hirange (XR/TR) | ₹25,000 company | ₹10,000 company | ₹10,000 company | ₹10,000 company |
| Storm | — | ₹10,000 company | — | ₹30,000 company |
| Turbo | — | ₹10,000 company | — | ₹10,000 dealer + ₹10,000 company |

**Manpower Incentive Power Drive** (₹/retail, min 2 retails/TSM, max ₹25,000/TSM/month): 3WC ₹2,000 · Hi-City (SR&TR) ₹2,000 · HiRange ₹2,000 · Storm ₹5,000 · Turbo ₹3,500.

**Per your confirmation:** Exchange Benefit, DSA Bonus and Referral Bonus are **zeroed for August** (the circular is silent on them; explicit ₹0 rows were added rather than deleted, so staff entering an amount for these in August gets a clear "not in Scheme Master" validation error instead of silently succeeding).

July's rows are untouched — historical July bookings keep resolving against July's rates.

**Not yet done — needs your input:** I did not push this to your live Google Sheet. `GSHEET_ID`/`GSHEET_CREDENTIALS_PATH` aren't configured in this environment, and writing to a spreadsheet your team may be actively using isn't something to do without confirming the real Sheet ID and exact rows with you first. Once you give the go-ahead and the Sheet ID, I can either write it directly via the service account or hand you the rows to paste in.

---

## 5. What changed (files)

- `backend/commercial.py` — RTO/Insurance entitlement engine, Incentive Register rate lookup, new component labels.
- `backend/server.py` — claim ageing fix, dealer earnings fields, finance SLA overdue, Incentive Register endpoints, self-test message accuracy, DB index.
- `backend/data/euler_raw.json` — Aug'26 Scheme Master (39 new rows) + Incentive Master (5 new rows).
- `frontend/src/pages/{Dashboard,IncentiveMaster,LeadDrawer,OwnerCommercialReport}.js` — surfaced all of the above in the UI.
- `.gitignore`, removed `backend/gsheets_credentials.json` — security fix.

All changes are committed to `claude/codebase-audit-gs-sync-x0dz7v` and pushed.

---

## 6. Recommended next steps

1. Rotate the GCP service-account key (your action — see §1).
2. Tell me the live Google Sheet ID if you want the Aug'26 scheme (and future data) actually written there.
3. Decide on git history purge for the leaked key (§1.2).
4. Confirm Google Sheet sync direction (one-way is current; two-way is a real project if needed).
5. When you're ready to test, run the backend against a real Mongo instance and re-seed (`POST /admin/reseed`) to pick up the new scheme data, then verify a HiCity test booking shows the ₹20,000 RTO+Insurance claim automatically.
