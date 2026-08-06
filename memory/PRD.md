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
