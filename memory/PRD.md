# Euler CRM — Full-Stack Migration PRD

## Original problem statement
User's "Euler company CRM" was built on **Google Sheets + Apps Script (~27,000 lines, 50 .gs modules)** with a static GitHub Pages portal (vanilla JS calling the Apps Script Web App). Root cause of slowness = Apps Script + spreadsheet reads. User wants it rebuilt as a **true full-stack app** with a real database, migrating all existing data, without disrupting their live spreadsheet (read-only source).

## User choices (2026-06)
- No login (single shared view)
- Everything at once (all modules)
- Migrate all existing data from Euler Master.xlsx
- Clean modern SaaS dashboard (light), data-dense tables

## Architecture
- **Backend:** FastAPI + Motor (MongoDB async). Faithful Python port of the commercial engine in `commercial.py` (Gross Vehicle Cost, TCS 1%/₹10L threshold, discount pools OEM vs Dealer, benefit modes, Customer Payable, dealer margin 4% + 5% GST, claim derivation). `seed.py` migrates `data/euler_raw.json` (exported from the xlsx) into clean camelCase MongoDB collections.
- **Frontend:** React (CRA) + Tailwind + lucide-react + recharts + sonner. Sidebar + topbar layout, side-drawers for lead detail & forms. Fonts: Cabinet Grotesk / IBM Plex Sans / JetBrains Mono. INR lakh/crore formatting.
- Collections: leads, price_master, scheme_master, incentive_master, bookings, payments, deliveries, finance, insurance, dealer_earnings, activities, claims, quotations, counters.

## Implemented (2026-06)
- Dashboard KPIs + payments-by-mode chart + model performance + outstanding split
- Lead Register (list/filter/search), New Lead, Lead 360 drawer with tabs:
  Overview (commercial breakup), Price Structure (live compute), Scheme Update, Payments (add receipt + ledger), Delivery (checklist + mark delivered), Activity log
- Workflow: Convert to Booking (creates booking + advance payment + activity), Close Lead
- Registers: Bookings, Quotations (with live compute + price-master autofill), Activity Log, Payment Ledger, Finance Register (auto-created on Finance-mode payments), Insurance Payouts, Delivery Tracker, OEM Claims (derived per-component + settle), Scheme Master, Incentive Master, Dealer Earnings (owner), Price Master

## Data migrated
10 leads, 69 price rows, 33 scheme rows, 4 incentives, 3 bookings, 3 payments, 3 dealer-earnings.

## Backlog / Next
- P1: Efficiency suggestions doc for user (indexing, endpoint slimming) — user asked for advice
- P1: Auth + roles (owner vs executive) to truly gate Dealer Earnings
- P2: Editable Price Master / Scheme Master (currently read-only)
- P2: Insurance payout entry form, incentive register computation
- P2: Export / share board (read-only company view), CSV export

## Iteration 2 (2026-06) — Auth, Masters CRUD, Share, Export, Sheets sync
- **Auth:** JWT email+password, roles Owner/Executive (backend/auth.py). Seeds owner@euler.com/euler@123 + demo executive@euler.com/euler@123 on startup. Bearer token in localStorage. All /api/* protected; /api/dealer-earnings owner-only; /api/auth/users owner-only (last-owner delete guarded). Frontend: Login, AuthContext, Protected routes, role-filtered sidebar, user menu + logout.
- **Editable Masters:** Price Master & Scheme Master full CRUD via drawers.
- **Company Share Board:** public /share (no login), backend /api/share/dashboard public — active bookings, monthly retail, by-model bars; no customer/staff data.
- **Excel Export:** GET /api/export → single .xlsx, sheet per module. Topbar Export button.
- **Google Sheets one-way sync (backend/gsheets.py):** appends new Lead/Booking/Payment/Delivery/Claim to the Euler Master sheet via Service Account. GSHEET_ID=173a0LK-L7sgEBmkxwpZI3ovkxDNCdwf7DTyH8AZyn7w set. **NOT YET ACTIVE** — user must place Service Account JSON at /app/backend/gsheets_credentials.json and share the sheet with the SA email. Graceful no-op until then. Status: /api/integrations/gsheets + Settings page.
- Tested: backend 23/23, frontend 15/15 pass.

## Next
- P1: Activate Google Sheets sync when user supplies the Service Account JSON.
- P2: Insurance payout entry form; incentive computation; split server.py into routers.

## Iteration 3 (2026-06) — Insurance Entry, Lead Import, Google Sheet activation
- **Insurance Entry:** full CRUD (backend /api/insurance POST/PUT/DELETE). Expected payout = premium * rate (rate entered as % e.g. 15 -> 0.15, or fraction). Outstanding + status auto. Frontend Insurance page with add/edit/delete drawer + live preview.
- **Lead Import:** upload .xlsx/.csv -> /api/leads/import/preview (maps by header, skips no-name rows) then /api/leads/import/commit (creates LD26 leads, status New). Frontend Import drawer with dropzone, preview table, CSV template download.
- **Google Sheet sync ACTIVATED (credential installed):** service account key saved at /app/backend/gsheets_credentials.json (euler-crm-service@shubham-motors-ai-agent.iam.gserviceaccount.com). Verified it can READ the Euler Master sheet. WRITE currently 403 because the sheet is shared as VIEWER — appends are gracefully swallowed (never break creation). status() now probes read/write and reports canRead/canWrite. **ACTION PENDING: owner must change the sheet share for the service account email from Viewer to EDITOR; then enabled=true and appends flow automatically.**
- Tested: backend 13/13 pytest, frontend 6/6 — all pass. Baseline reseeded clean (10 leads, 69 price rows, 0 insurance).

## Iteration 4 (2026-06) — Insurance-from-Lead & Import column mapping
- **Insurance-from-Lead:** new "Insurance" tab in the Lead 360 drawer; premium pre-fills from the lead's price structure; staff add an insurance entry tied to the lead (GET /api/insurance?lead_id=, POST /api/insurance with leadId). LeadDrawer.js InsuranceTab.
- **Import column mapping:** Lead Import is now two-step (upload -> map). Backend import_preview/import_commit accept an optional `mapping` multipart Form field (JSON {field: header}); _suggest_mapping auto-matches by name; works with any header names. Fixed bug: mapping must be Form(None) not a query param.
- Tested: backend 17/17 pytest (test_iter4_mapping_and_lead_insurance.py), frontend 2/2 core flows. Baseline reseeded clean.
- Google Sheet sync still READ-ONLY: owner has NOT yet added the service account email as Editor (verified canWrite=false). Appends remain graceful no-ops.

## Iteration 5 (2026-06) — Backfill, Insurer Payout Report, Google Sheet LIVE
- **Google Sheet sync ACTIVATED & LIVE:** owner granted the service account Editor. Fixed the write-probe bug (empty batchUpdate returns 400 "must specify at least one request" = write OK, not a permission failure). status() now correctly reports enabled=true, canWrite=true. Verified end-to-end: creating a lead appends a row to the live Euler Master sheet.
- **Backfill (owner):** POST /api/integrations/gsheets/backfill pushes all leads/bookings/payments/deliveries to the sheet, idempotent (dedupes on column-A key so no duplicates). Settings "Backfill" button. Verified: skips existing, appends only missing.
- **Insurer Payout Report (owner-only):** /insurance-report + GET /api/reports/insurance-payout — expected vs received payouts by month & by insurer, totals, bar chart. Executive blocked (403 + nav hidden + route redirect).
- Tested: frontend 6/6 (iteration_5), backend verified via curl. Baseline clean (10 leads, 0 insurance).

## Iteration 6 (2026-06) — Dealer Earnings Report, Sync Health Badge, Full Backfill
- **Dealer Earnings Report (owner-only):** /earnings-report + GET /api/reports/dealer-earnings — monthly margin/scheme/insurance/other breakdown, KPI cards, stacked bar chart, By-Month table. Total derived from component fields (migrated totalDealerEarnings was 0). Executive blocked.
- **Sync Health Badge:** top-bar badge (SyncBadge) polls /api/integrations/gsheets every 60s → green 'Sheet Synced' (enabled+writable), amber 'Sync Off', red 'Sync Error' (with tooltip of lastError). gsheets.py tracks _health {lastWriteOk, lastWriteAt, lastError, writes, failures} updated on every append.
- **Full Backfill run:** executed POST /api/integrations/gsheets/backfill — all existing leads(10)/bookings(3)/payments(3) already present, 0 duplicates added; sheet is 100% in sync.
- Bug fixed by testing agent: Layout.js was missing `useEffect` import (crashed authenticated layout) — now fixed. Tested frontend 4/4 pass.

## Iteration 7 (2026-06) — Company board restyled to original
- Rebuilt public /share (Share.js) to EXACTLY match the original portal's company board using the original assets/css/share.css verbatim: dark navy (#07111f) gradient + grid bg, Syne + Instrument Sans fonts, cyan/lime/warm accents, gradient brand "Euler Motors / Bookings & Retail", live pill, glass KPI cards (Active Bookings, Retail MTD, New Bookings, Today), Active Bookings + Retail lists (date/name/model/badge), model chips, refresh footer.
- Expanded GET /api/share/dashboard to also return todayBookings, recentBookings[], recentRetail[] (name/model/variant/date). Still public, no auth.

## Iteration 8-9 (2026-06) — Faithful re-port of original Apps Script logic (scheme + workflow)
Source of truth: user's original `final fix` .gs codebase (27k lines). Read & mirrored: Config.gs (COMMERCIAL constants/component policy — confirmed already-matching), LeadPickerService (PICKER_STAGE), CommercialEngineService, SchemeMasterService (share split + scheme rules), BusinessRulesService, PaymentService, DeliveryService, BookingService, LeadService, and grepped Claim/OemClaim/Insurance/ExtraIncome/Finance services.

### Step-eligibility gating (LeadPickerService PICKER_STAGE + requireActiveLead_)
- Backend `lead_actions()` + `_require_action()` in server.py enforce: Booking excludes booked/delivered; Price/Scheme/Payment/Activity require Active; Delivery excludes already-delivered; Close requires Active (RC+plate captured here for delivered leads). Finance receipt allowed until Archived.
- `GET /leads/{id}/360` returns `actions{}`; convert-booking/scheme/price/payment/delivery/close/activity all guard server-side (409/422).
- Frontend LeadDrawer hides Convert-to-Booking once booked ("Booked ✓" badge), hides/disables Close appropriately, StepLock notices + disabled saves on non-Active tabs, delivered toggle locked once delivered.

### Scheme share-split engine (commercial.py) — company-share-FIRST
- Ported schemeShareSplitFor_, getSchemeSharesForLead_, model/variant matchers & aliases (Turbo Max→turbo, Hi-Load→hiload, HiCity/Hirange XR/TR), scheme_month_from_date, buildSchemeAmountChoices, getSchemeOfferRulesForVehicle_, validateSchemeOffersForVehicle_.
- OEM claimable = OEM **company share** (capped company-first), NOT raw offer sum. `recompute_lead` now sets companyOutstanding=eligible company share, dealerSchemeRetained (=company-unpassed − dealer-passed), oemExtraSupportRetained.
- `GET /leads/{id}/scheme-rules`: Scheme tab shows ONLY components available in Scheme Master for that model/variant/month; unavailable are hidden (+note) and rejected 422 server-side; caps enforced. Partial-Benefit per-component breakup (benefitPassedBreakup JSON).
- `/claims` register uses per-component company share; dealer-earnings report computed LIVE = margin + scheme retained + insurance income + OEM extra support retained.

### Other original rules mirrored
- Delivery mark-delivered requires full checklist (Insurance+Insurer, Registration, Invoice+Invoice#, Chassis, PDI) AND cleared customer outstanding (isDeliveryEligible_) → 422 otherwise.
- Close requires a Close Reason; closing a DELIVERED lead also requires RC=Done + Number Plate (validateCloseLeadRcFields_).
- Lead create blocks duplicate 10-digit mobile (409).
- Tested: iteration_8 + iteration_9 (13/13 backend pytest PASS + full frontend Playwright). Baseline intact (10 leads; LD26000005 remains Booked from iter8).

### Not ported (Apps-Script infra, N/A to React+FastAPI stack)
Locking, Dialogs UI, SyncEngine internals, SelfHealing/Backup/CrashReport/HealthCheck/PerformanceMonitor/VersionManagement/TransactionLog, DataStore/SheetLayout — these are Google-Sheets runtime concerns replaced by MongoDB + FastAPI.

## Iteration 10 (2026-06) — Owner reports parity (OemClaimService.gs ports)
Added the 3 report/register builders that existed in the .gs codebase but were missing from the app (all owner-only, computed LIVE from booked leads + claim register):
- **Owner Commercial Report** `GET /api/reports/owner-commercial` (port of buildOwnerCommercialReport_): Discount Cost Ownership (dealer vs OEM company share, total discount, OEM receivable, scheme income retained), Claim Position (pending/received value, scheme ROI %), Averages, Executive Discount Usage. Page: /owner-commercial (OwnerCommercialReport.js).
- **OEM Claim Dashboard** `GET /api/reports/oem-claim-dashboard` (port of buildOemClaimDashboard_): Claim Status Summary, Value Summary (company vs dealer share, OEM liability), Monthly / Scheme-wise / Executive-wise claim summaries — all at COMPANY-SHARE values. Page: /oem-claim-dashboard (OemClaimDashboard.js).
- **Claim Exception Report** `GET /api/reports/claim-exceptions` (port of reconcileAllClaims_/reconcileBooking_): Missing Claim, Incorrect Claim Amount, Unapproved Claim, Duplicate Claim, Overpayment, Negative Discount/Payable. Page: /claim-exceptions (ClaimExceptions.js).
- New sidebar section "Owner Reports" (owner-only). Verified: owner 200 / executive 403 on all three; Owner Commercial page renders. Existing registers already present: Lead/Booking/Payment/Finance/Insurance/Delivery/Claim/Dealer-Earnings/Insurance-Payout.

## Iteration 11 (2026-06) — Receipt capture, payment cap + Production Audit
- **Record Receipt flows (dropdown-driven, per user design):**
  - OEM claim receipts PER COMPONENT: POST /api/claims/receipt (accrues receivedAmount + receipts[] history, status Partial/Received). Claims page "Record Claim Received" modal.
  - Financer receipts: POST /api/finance/{file}/receipt (Disbursed/Outstanding update, receipts[] history). A Finance-mode payment on a lead now ACCRUES the file's committed amount (sanctionedAmount) and shifts customer→financer outstanding; the financer disbursement is recorded separately and does NOT change customer outstanding. Finance page "Record Financer Receipt" modal.
  - Insurer payouts: POST /api/insurance/{id}/receipt (receivedPayout accrues, receipts[] history). Insurance EntryDrawer Lead field is now a DELIVERED-LEAD dropdown (ins-lead-select). Insurance page "Record Payout" modal.
- **Over-payment guard:** _add_payment_internal returns 422 if a receipt exceeds Customer Payable (provisional allowed only when payable is 0 / slim booking). Port of BusinessRulesService.validatePaymentAmount_.
- Tested: iteration_10.json (labelled iter 11) — 8/8 pytest PASS + frontend testids verified, baseline preserved.
- **Production Readiness Audit** written to /app/EULER_PRODUCTION_AUDIT.md (zero-tolerance parity vs original .gs). Overall 84/100. RESOLVED: C2 payment cap, C3 receipts, H2 insurance dropdown. OPEN before full go-live: C1 Dealer-Earnings missing income lines (Documentation/Warranty/RSA/Referral), H1 dashboard KPI parity (followups, conversion %, MTD revenue, finance-outstanding), H3 claim lifecycle dates+ageing, H4 audit/transaction log, H5 RSA/AMC charge input. UNVERIFIED regression: U1 full priced+delivered deal reconciliation, U3 dashboard values, U4 concurrency.

## Iteration 12 (2026-06) — Insurance payout rate auto-fill (per model)
- Ported InsuranceService.getSuggestedInsurancePayoutRate_: Storm/Turbo -> 49%, all other models -> 36.5% (commercial.suggested_insurance_payout_rate).
- Backend _insurance_derive now falls back to the model-based rate when no manual Payout Rate % is entered. Expected Payout = premium x rate.
- Frontend Insurance EntryDrawer auto-fills Payout Rate % from the model/delivered-lead selection, with manual override preserved (rateTouched flag).
- Verified: Turbo Max 20000 -> 0.49 -> 9800; Hi-Load 20000 -> 0.365 -> 7300.
- Insurance receipts: "Record Payout" accrues receivedPayout + receipts[] history; Payout Outstanding = Expected - Received; status Partial/Received.

## Iteration 13 (2026-06) — ERP Production Audit Engine (Zero-Tolerance Certification)
- **Wired the ERP Production Audit page** (was built but unreachable): import + owner-only route `/erp-audit` in App.js + sidebar link (Owner Reports) in Layout.js.
- **Rebuilt `GET /api/reports/production-audit`** into a 16-category automated certification engine that introspects the live system at runtime:
  1 API Health (verifies 35 critical endpoints registered via app.routes), 2 MongoDB Integrity (14 collections reachable + orphan-payment + insurance-rate integrity), 3 Business Logic Parity (runs certified TEST_CASES values: GVC 662k, margin 23,220, TCS 1% above ₹10L, rates 49/36.5), 4 Spreadsheet Parity (FIELD_MAPPING fields), 5 Apps Script Parity (11 ported commercial fns present), 6 Formula Migration (scheme company-first split + caps), 7 Dashboard Parity (introspects live /dashboard KPIs), 8 Report Parity (runs all 5 owner report builders), 9 Workflow Validation, 10 Role & Permission (introspects owner_only deps on routes), 11 Security, 12 Performance (indexes), 13 Production Config (env vars), 14 Google Sheet Sync (gsheets.status), 15 Deployment, 16 Regression.
- Each category returns status/score%, per-check detail+severity, affectedModules, missingItems, suggestedFix. Response adds severityCounts, scoreBreakdown, blockers (Critical+High), goLiveRule. GO LIVE only when overall≥99% + zero Critical + zero High.
- Frontend page rewritten to render verdict, severity grid, per-category score bars, blockers, and expandable category cards.
- **First certified run: overall 86.1% · NOT READY FOR PRODUCTION.** Severity: 0 Critical, 3 High, 9 Medium, 4 Low. Owner 200 / Executive 403 verified.
- **High blockers:** C1 dealer-income lines (Documentation/Warranty/RSA/Referral) missing (surfaces in Spreadsheet + Report parity); H4 no audit/transaction log for finance-sensitive mutations.
- **Audit revealed H1 doc is partly STALE:** /dashboard already returns `conversion` % and `revenue` (MTD) KPIs; only finance-outstanding + follow-up KPIs remain (downgraded to Medium).
- **Latent HIGH defect noted (not auto-fixed, awaiting approval):** Insurance.js line ~139 posts payoutRate as a percent (e.g. 49) while backend `_insurance_derive` treats it as a fraction → 10× expected payout. Baseline unaffected only because no UI-created insurance entries exist. DB integrity check (payoutRate>1) currently PASS on empty data but will FAIL the moment an entry is created via UI.
- Status: engine built + verified (curl + screenshot). Parity-gap FIXES are HELD pending user approval per the user's "present findings first, wait for approval" directive.

## Iteration 14 (2026-06) — Full parity backlog CLOSED (user approved "Zero Tolerance" implementation)
User approved implementing every remaining gap in priority order. All done, backend 32/32 pytest + full frontend PASS (test_reports/iteration_11.json). ERP Production Audit now 96.4% · 0 Critical · 0 High · 0 blockers.
- **INS-1 (insurance rate consistency):** single representation — DB=fraction, UI=%, backend `_insurance_derive` coerces any input >1 (/100). Startup migration `_migrate_insurance_rates` + owner endpoint POST /admin/migrate-insurance-rates fix any payoutRate>1 docs (idempotent). Insurance now synced to Google Sheet (Insurance Register tab, rate written as %).
- **C1 (Dealer Earnings):** new lead fields documentationIncome/warrantyIncome/rsaIncome/referralIncome via PUT /leads/{id}/extra-income (Active-gated, audited). recompute_lead stores extraDealerIncomeTotal + dealerTotalEarnings. /reports/dealer-earnings adds 4 components + monthly `extra` + totals.extra. UI: ExtraIncomeCard in Lead drawer Scheme tab; EarningsReport shows components + Extra bar/column.
- **H4 (Audit trail):** append-only `audit_log` collection + `write_audit()`/`actor()` (user/role/ip/timestamp/action/module/old/new + refs). Wired into payment, finance receipt, claim receipt/settle, insurance create/update/delete/receipt, scheme, price-structure, extra-income, close. Owner-only GET /audit-log (?module=&leadId=). New page /audit-log (Audit Trail) + nav.
- **H1 (Dashboard):** kpis.financeOutstanding, followupDue, followupOverdue added (conversion % + revenue already existed). UI: 2 follow-up MiniStats + Finance Outstanding row.
- **H3 (Claim lifecycle):** submittedDate/approvedDate persisted on settle/receipt; list_claims returns ageingDays (`_claim_ageing_days`). UI: Submitted/Approved/Ageing columns + SettleModal date inputs.
- **H5 (RSA/AMC):** rsaAmc added to PriceStructureIn + SnapshotComputeIn; lead_to_snapshot reads lead.rsaAmc; flows into GVC/payable. UI: price-rsaAmc input.
- **U4 (double-submit):** identical receipt (same lead/amount/mode) within 4s → 409 (recordedAt on payment doc).
- **U1 (reconciliation):** synthetic New→Book→Price→Scheme→Pay deal reconciled vs engine (certified by testing agent) → audit T-M1 = PASS.
- **Perf:** startup indexes on leads.leadId/mobile/currentStatus/bookingDate + payments.leadId + audit_log.timestamp.
- Docs updated: ERP_PARITY_SPEC, FIELD_MAPPING, FORMULA_MIGRATION, GO_LIVE_CHECKLIST (96/100), TEST_CASES.
- **Remaining to reach ≥99% GO-LIVE (operational only, not code):** production redeploy + production smoke test; optional password-reset/lockout policy; confirm append-only Google Sheet sync is acceptable. Verdict stays "NOT READY FOR PRODUCTION" until the user redeploys + smoke-tests on production.

## Iteration 15 (2026-06) — Insurance payout hidden from staff (Executive)
User: staff must not see the dealer payout %/expected; owner manages the rate.
- Lead drawer Insurance tab now Owner-only (hidden for Executive) — `useAuth().isOwner` gate in LeadDrawer.js (tab list + render).
- Standalone "Insurance Payouts" page + sidebar link now Owner-only (App.js route P(...,true), Layout.js ownerOnly).
- Insurance API locked Owner-only: GET/POST/PUT/DELETE /api/insurance + POST /api/insurance/{id}/receipt → 403 for Executive (verified), 200 for Owner. Prevents API-level payout leakage.
- Preview change — user must REDEPLOY to push to production (euler-connect.emergent.host).

## Iteration 16 (2026-06) — Insurance page: staff record received, payout stays owner-only
User wants staff to use the Insurance Payouts page to enter amounts received against leads, WITHOUT seeing the dealer payout rate/expected (owner's cut).
- Restored /insurance page + sidebar for all roles (removed owner-only from App.js route + Layout.js nav).
- Backend server-side split (`_strip_payout_for_staff`): GET /insurance, POST /insurance, POST /insurance/{id}/receipt now open to staff but STRIP payoutRate/expectedPayout/payoutOutstanding for non-owner. PUT + DELETE remain owner-only.
- Staff-created entries: backend forces payoutRate=0 then auto-derives from model (49%/36.5%) — staff never set/see the rate; owner sees full economics.
- Frontend Insurance.js role-aware (useAuth): staff columns = Customer/Insurer/Premium/Received/Status; hidden Rate%/Expected/Outstanding + edit/delete + expected in subtitle; EntryDrawer hides rate field + summary card; PayoutReceiptModal hides outstanding, lists all entries, button "Record Received".
- Lead-drawer Insurance tab stays Owner-only (unchanged).
- Verified: curl (staff stripped, owner full, staff can create+receipt) + screenshot (staff UI). Preview only — REDEPLOY to push to production.

## Iteration 17 (2026-06) — Manual OEM-incentive claim entry
User: manually record claims (e.g. OEM incentive received as a claim); both Owner and staff can add; receive against it later.
- Backend: POST /api/claims/manual (ManualClaimIn: claimType/oemCompany/leadId/customer/model/claimAmount/submittedDate/claimReference/note). Stored in db.claims with manual=True, claimId=MCLM…, componentKey=claimId, eligibleClaim=claimAmount, status Submitted. Audited + gsheet append.
- list_claims now merges manual claims alongside derived scheme claims (Manual flag).
- record_claim_receipt made manual-aware: if claim doc is manual, uses stored eligibleClaim (no lead/scheme recompute); leadId optional (""). Partial→Received computed vs claimAmount. settle_claim preserves manual flag + MCLM claimId.
- Frontend Claims.js: "Add Manual Claim" button + ManualClaimModal (testids manual-claim-type/oem/lead/customer/amount/date/ref, save-manual-claim-btn); "Manual" badge in register; lead picker autofills customer/model; register shows manual + derived together.
- Verified: curl (create→register→partial 5000→full 15000 Received) + screenshot (staff add via UI, Manual badge, ₹12,000). Baseline cleaned (all manual test claims removed).
- Preview only — REDEPLOY to production.
