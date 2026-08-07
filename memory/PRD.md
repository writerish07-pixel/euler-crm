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
