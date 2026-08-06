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
