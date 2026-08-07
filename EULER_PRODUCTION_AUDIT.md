# EULER CRM — PRODUCTION READINESS AUDIT (Zero-Tolerance Parity)
**Scope:** Business-logic parity between the source system (Google Sheet = source of truth, Apps Script `final fix/*.gs` = business engine, public portal = UI) and the new React + FastAPI + MongoDB application.
**Method:** Requirement → Spreadsheet/Apps-Script → API → Portal → Report/Dashboard trace. Each item marked **VERIFIED** (proven by code trace and/or automated test), **DEFECT** (parity broken/missing), or **UNVERIFIED** (needs a dedicated test before go-live).
**Date:** 2026-06 · **Auditor role:** Solution Architect + ERP Auditor + Apps-Script Architect + QA Lead + Financial-Systems Auditor + Dealership Ops.

---

## 1. EXECUTIVE SUMMARY
The **core commercial + scheme + workflow engine is faithfully ported and test-proven** (charges, TCS, two-pool benefit model, dealer margin, company-share-first scheme split, step-gating, delivery/close validation, duplicate-mobile block, three owner reports). This is the hard 80% and it is correct.

However, the app is **NOT yet 100% identical** to the source. There are **3 CRITICAL and 5 HIGH** parity gaps — most notably (a) **Dealer Earnings omits several extra-income lines** the source captures, (b) **payments are not capped at customer payable**, and (c) the **"Record Receipt" dropdown flows are backend-only / not finished on the UI and untested**. A few areas remain **UNVERIFIED** and must be tested before go-live.

**Verdict: NO-GO for "100% identical, go live tomorrow"** until the CRITICAL + HIGH items below are closed and the UNVERIFIED items are tested. The system **is** safe for a **controlled pilot** (owner-supervised, no un-reconciled finance) because the money math itself is correct.

**Overall Production-Readiness Score: 78 / 100.**

---

## 2. VERIFIED — parity holds (proven)
| # | Requirement | Source | App | Evidence |
|---|---|---|---|---|
| V1 | Gross Vehicle Cost = ex-showroom + accessories + insurance + RTO + FASTag + handling + TRC + extended warranty + RSA/AMC + other charges | Config.gs COMMERCIAL | `commercial.CHARGE_KEYS` summed in `compute_commercial_totals` | Charge keys + `lead_to_snapshot` mapping traced |
| V2 | TCS 1% on gross when applicable (threshold) | Config TCS_RATE/THRESHOLD | `calculate_tcs` | Constants match |
| V3 | Two-pool benefit model (dealer pool vs OEM pool), Customer Payable, Total Discount | CommercialEngineService | `compute_commercial_totals` | Regression values match |
| V4 | Dealer margin 4% + 5% GST | CommercialEngineService | `compute_dealer_margin` | Constants match |
| V5 | Scheme share-split **company-share-first**, model/variant aliases, scheme-month, availability rules + max caps | SchemeMasterService | `scheme_share_split_for`, `get_scheme_offer_rules_for_vehicle`, `validate_scheme_offers` | iteration_9 tests 13/13 |
| V6 | OEM claimable = OEM **company** share (not raw offer) | July-2026 circular logic | `recompute_lead` companyOutstanding = eligible company share | curl-verified |
| V7 | Step-eligibility (PICKER_STAGE + requireActiveLead): booking / delivery / close / price / scheme / payment / activity | LeadPickerService | `lead_actions` + `_require_action` guards | iteration_8/9 |
| V8 | Delivery needs full checklist + cleared customer outstanding | DeliveryService | `_validate_delivery_ready` | iteration_9 (422) |
| V9 | Close needs reason; delivered-lead close needs RC + number plate | LeadService/DeliveryService | `close_lead` | iteration_9 (422) |
| V10 | Duplicate 10-digit mobile blocked on create | LeadService | `create_lead` | iteration_9 (409) |
| V11 | Slim / provisional booking: book before price, advance recorded even at payable ₹0 | BookingService/BusinessRules | `convert_booking` records advance via `_add_payment_internal` | code trace |
| V12 | Insurance expected payout = premium × rate | InsuranceService | `_insurance_derive` | code trace |
| V13 | Owner Commercial Report / OEM Claim Dashboard / Claim Exception Report | OemClaimService | `/reports/owner-commercial`, `/oem-claim-dashboard`, `/claim-exceptions` | iteration_10, owner 200 / exec 403 |
| V14 | Public Share board (Active Bookings, Retail MTD, New, Today) | portal share.html | `/share` + `/api/share/dashboard` | iteration_7 |
| V15 | Google Sheet 1-way append sync | SyncEngine | `gsheets.append` | handoff, live |

---

## 3. DEFECTS

### CRITICAL (must fix before go-live)
- **C1 — Dealer Earnings is INCOMPLETE.** Source `ExtraIncomeService.gs` dealer-earnings register captures **Documentation Income, Warranty Income, RSA Income, Referral Income** (plus OEM extra support, insurance income, scheme retained). The app's `/reports/dealer-earnings` computes only **Margin + Scheme Retained + Insurance + OEM Extra Support**. There is **no field/UI to capture Documentation / Warranty / RSA / Referral income**, so **Total Dealer Earnings will be understated**. → Add these income inputs (per booked lead) + include them in the report.
  Files: `backend/server.py::dealer_earnings_report`, new income fields on lead + a capture UI.
- **C2 — Payments are NOT capped at Customer Payable.** Source `BusinessRulesService.validatePaymentAmount_` rejects `paid > payable` unless explicitly provisional. App `_add_payment_internal` records any amount. Over-payment is only *reported* later (Exception Report), not *prevented*. Real risk of ledger corruption on day one. → Enforce cap in `add_payment` (allow provisional only when payable is still ₹0 / slim booking).
  File: `backend/server.py::_add_payment_internal` / `add_payment`.
- **C3 — "Record Receipt" dropdown flows are UNFINISHED.** Per the requested design (dropdown of leads/files/entries with outstanding → enter amount → update against that lead/financer/insurer, with receipt history), the **backend endpoints exist** (`/claims/receipt`, `/finance/{file}/receipt`, `/insurance/{id}/receipt`) but the **front-end UI is not built and nothing is tested**. Finance semantics were also reworked (Finance-mode entry shifts outstanding customer→financer; disbursement recorded separately) and need end-to-end testing. → Build the 3 UIs + test.
  Files: `frontend/src/pages/Claims.js`, `Finance.js`, `Insurance.js`; backend endpoints already added.

### HIGH
- **H1 — Dashboard KPI parity is PARTIAL.** Source `DashboardService.gs` computes today-followups, pending-followups, monthly **new** bookings (distinct from active), monthly deliveries, **conversion %**, **MTD revenue**, payments-by-mode, and a **Finance Total Outstanding** KPI. App `/dashboard` has today leads/bookings/deliveries, monthly leads/bookings, payments-by-mode, customer & company outstanding, model performance — but is **missing follow-up KPIs, conversion %, MTD revenue and the Finance-outstanding KPI**. → Add missing KPIs.
- **H2 — Insurance Lead is free-text, not a delivered-lead dropdown.** Data-integrity + user requirement. `Insurance.js` `EntryDrawer` uses a text `leadId`. → Replace with a dropdown of delivered leads (auto-fill customer/model/mobile). *(frontend pending)*
- **H3 — Claim register lacks lifecycle dates + ageing.** Source register has Claim Submitted / Approved / Received dates; the Owner report's **Average Claim Ageing** depends on them. App stores only status/received/reference. → Capture submitted/approved dates so ageing is real (currently ageing = 0).
- **H4 — No audit / transaction log.** Source `TransactionLogService` / `logAudit_` records who/what/when on every mutation. App has none → no traceability on finance-sensitive edits (a Big-4 blocker for a money system). → Add an append-only audit log with user + before/after.
- **H5 — RSA/AMC charge cannot be entered.** `lead_to_snapshot` hardcodes `rsaAmc: 0`; no price-structure field feeds it, even though the engine sums it. If the dealership charges RSA/AMC, payable is understated. → Add the input field.

### MEDIUM
- **M1 — Concurrency / idempotency.** Source used `LockService`. App has no locking; a double-click on Convert-to-Booking or Add-Payment could double-insert (duplicate advance). → Add idempotency keys / disable-on-submit + a unique guard.
- **M2 — No pagination / DB indexes** on list endpoints (fine at 10 leads; degrades at 1,000+). → Add indexes on `leadId`, `mobile`, `currentStatus`, `bookingDate`.
- **M3 — Role granularity.** Only Owner vs Executive. Source referenced finer roles (Reception/Sales/TL/GM/Accounts). Confirm dealership requirement; if needed, extend RBAC.
- **M4 — Google Sheet sync is append-only.** Edits / status changes / deletes are NOT propagated to the sheet. If the sheet is still a live artefact, it will drift. → Confirm whether 2-way / update-in-place is required.
- **M5 — `server.py` is monolithic (~1.6k lines).** Maintainability only, not correctness. → Split into routers.

### LOW
- **L1** No SMS/WhatsApp/email notifications. **L2** No document uploads (RC, invoice, KYC, policy). **L3** No PWA / mobile-optimised layout. **L4** Reports recomputed per request (no cache) — fine at current scale.

---

## 4. UNVERIFIED — must be tested before go-live
- **U1** Full end-to-end money reconciliation on a **priced, scheme-applied, delivered** lead (baseline booked leads currently carry ₹0 scheme, so claim/earnings paths ran but produced ₹0 — they are structurally correct but not value-proven on live-like data). Create a synthetic full deal and reconcile customer payable, outstanding, OEM claim, dealer earnings against a hand calculation.
- **U2** The three new receipt endpoints (`/claims/receipt`, `/finance/*/receipt`, `/insurance/*/receipt`) — behaviour, partial receipts, status transitions, and the finance customer→financer outstanding shift.
- **U3** Dashboard KPI values against a seeded month of activity (see H1).
- **U4** Concurrency (rapid double submit) — see M1.

---

## 5. NOT APPLICABLE (Apps-Script runtime infra intentionally not ported)
LockService, SyncEngine internals, SelfHealing/Backup/CrashReport/HealthCheck/PerformanceMonitor/VersionManagement, DataStore/SheetLayout, Dialogs UI. These are Google-Sheets execution concerns replaced by MongoDB + FastAPI and are out of scope for business-logic parity.

---

## 6. PRODUCTION-READINESS SCORECARD
| Dimension | Score | Note |
|---|---|---|
| Commercial / Scheme math | 96 | Verified; minus RSA/AMC input (H5) |
| Workflow & validations | 92 | Step-gating, delivery, close, dup-mobile proven |
| Finance & payments | 62 | C2 (no cap), C3 (receipts unfinished) |
| Dealer earnings / commercials | 60 | C1 (missing income lines) |
| Reports & dashboards | 80 | Reports done; dashboard partial (H1) |
| Data integrity / audit | 65 | No audit log (H4), no locking (M1) |
| Security / permissions | 75 | JWT + owner/exec proven; coarse roles (M3) |
| Performance / scalability | 80 | Fine now; indexes/pagination later (M2) |
| Maintainability | 78 | Monolith (M5) |
| **Overall** | **78** | NO-GO for "identical"; GO for supervised pilot |

---

## 7. GO / NO-GO
**NO-GO** for the stated bar ("100% identical, staff live tomorrow, single missing rule = critical failure") until **C1, C2, C3, H1, H2, H3, H4, H5** are resolved and **U1–U4** are tested.
**Conditional GO** for a **supervised pilot** (owner present, finance/claim receipts reconciled manually, no reliance on Dealer Earnings totals) — the customer-facing money math (payable, discounts, outstanding, scheme company share) is verified-correct.

**Recommended fix order:** C2 → C3 → C1 → H5 → H3 → H1 → H2 → H4 → then U1–U4 regression, then re-score.
