# Merge Request — Euler CRM (Google Sheets / Apps Script)

**Branch (suggested):** `release/crm-stabilization-jul16`  
**Target:** `main` / production Apps Script project  
**Window covered:** 13–16 Jul 2026 (last 3–4 days)  
**Source folder:** `C:\Users\hp\Desktop\final fix`  
**Date:** 16 Jul 2026

---

## Summary

Stabilization and go-live hardening of the dealership CRM: booking/payment integrity, scheme master matching with dropdown-only offers, finance overdue tracking, dashboard payment breakdowns, safer dialog HTML, deferred CRM refresh to avoid timeouts, and a scheme-only **Scheme Update** dialog.

---

## What’s included

### Booking & payments
- Booking conversion requires a **non-zero booking amount** and payment mode (advance required).
- Commercial offers removed from **Convert to Booking**; scheme/discount editing moved to **Scheme Update**.
- Duplicate booking / multi-payment logging guarded on convert.
- Payment mode column on booking-related views; finance flag kept in sync across tabs.
- Payment register / outstanding refresh paths tightened so Lead Register, Outstanding, and Dashboard stay aligned after create/update.

### Scheme Master & Scheme Update
- New / expanded **`SchemeMasterService.gs`**: month matching, model aliases (Hi-Load ↔ HiLoad, Neo HiRange ↔ Hirange, Turbo Max ↔ Turbo, Storm), variant rules, company vs dealer share for month-end claim.
- Scheme Update is **scheme-only** (customer details removed — already shown in lead picker summary).
- All scheme amount fields are **dropdowns** from Scheme Master choices (no free typing / over-discount).
- Fields without a matching scheme for model/variant/month stay at ₹0 and cannot accept invalid amounts.
- On lead pick, rules load via `getSchemeRulesForLeadDialog` (Lead Register model first) with dialog fallbacks.
- Month-end claim path: company share vs dealer share from Scheme Master for claim calculation.

### Finance
- Finance file number auto-generation; finance payment pending tracking.
- After **Mark Delivered** + finance: financer payment expected within **2 days**; overdue cases surface on dashboard.
- Finance-received updates for pending files.

### Dashboard & refresh
- Dashboard payment totals split by type (e.g. cash, UPI, finance).
- Outstanding split after scheme update: customer outstanding vs company/dealer share where applicable.
- **Refresh Dashboard / CRM** refreshes the full workbook sync path.
- Heavy dashboard/claim rebuild deferred after saves (`scheduleDeferredCrmSync_`, client `kickDeferredCrmRefresh`) to reduce false “timeout” / server timeout alerts while data is already written.

### Delivery
- Mark Delivery shows full column context and updates related tabs without manual sheet hunting.

### Dialogs / UX reliability
- Fixed **Malformed HTML** on Convert to Booking and related dialogs (`createDialogOutput_`, void-element XML safety, safer `htmlSafeJs_` that does not break `<=` in client JS).
- Lead picker “Loading leads…” stuck state fixed (over-escaped `<=` in picker JS).
- New Lead false client timeout after successful create softened; save returns after write, sync deferred.
- Customer detail edits on update path restricted to **owner** (where still applicable); Scheme Update no longer edits customer fields.

### Fresh start & masters
- Fresh Start deletes **leads and related operational data only** — Price Master / Masters preserved for test cycles.
- Price Master / pricing engine wiring kept for commercial snapshot and outstanding.

---

## Files changed (vs earlier `google-sheets-crm-dms/src` baseline)

| File | Change |
|------|--------|
| `SchemeMasterService.gs` | **New** — scheme matching, choices, claim shares, dialog APIs |
| `FinanceService.gs` | **New** — finance file / overdue / pending flows |
| `Dialogs.gs` | Scheme-only update UI, HTML safety, timeouts |
| `LeadService.gs` | Scheme save path, deferred refresh |
| `LeadPickerService.gs` | Picker reliability |
| `BookingService.gs` | Booking amount/mode, offer removal from convert |
| `PaymentService.gs` | Payment integrity / modes |
| `CommercialEngineService.gs` | Light commercial snapshot for dialogs |
| `Config.gs` | Public APIs (`getSchemeRulesForDialog`, etc.) |
| `Utils.gs` | Deferred sync helpers, dialog HTML helpers |
| `DashboardService.gs` | Payment-type totals, overdue finance |
| `DeliveryService.gs` | Mark delivery completeness |
| `DataStore.gs` / `SyncEngine.gs` | Sync / index refresh behaviour |
| `PricingService.gs` / `MasterService.gs` / `MasterDataService.gs` | Master alignment |
| `BusinessRulesService.gs` / `RelationshipEngineService.gs` | Rule/relationship updates |
| `Code.gs` / `Setup.gs` / `FreshStartService.gs` | Menu, setup, safe wipe |
| `PriceMasterImport.gs` / `ValidationService.gs` / `CommercialCertificationService.gs` | Jul 15 hardening |

**Deploy:** copy all `.gs` files from `final fix` into Apps Script → Save → reload spreadsheet.

---

## Test plan

- [ ] **New Lead** — creates successfully; Dashboard / Outstanding update (or after Refresh CRM); no false hard failure if create succeeded.
- [ ] **Convert to Booking** — amount > 0 + payment mode required; opens without Malformed HTML; single payment row; no commercial offer block on convert.
- [ ] **Scheme Update** — pick booked lead → lead summary shows customer; **no** Customer Details form; scheme dropdowns show Scheme Master amounts for model (e.g. Turbo Max → Turbo); save updates outstanding / shares.
- [ ] **Scheme guardrails** — model with no scheme component: only ₹0 / Additional Discount as designed; cannot type arbitrary amounts.
- [ ] **Add Payment** — modes reflected; dashboard cash / UPI / finance totals correct.
- [ ] **Finance** — file number auto; after delivery, overdue (>2 days) appears on dashboard when unpaid.
- [ ] **Mark Delivered** — fields populated; Delivery / related tabs update.
- [ ] **Fresh Start** — leads/payments/bookings cleared; Price Master + Masters intact.
- [ ] **Refresh CRM / Dashboard** — full sheet catch-up after batch operations.
- [ ] **Lead picker** — lists active leads (not stuck on “Loading leads…”).

---

## Out of scope / follow-ups

- GitHub/GitLab remote PR not opened (local folder is not a git repo; `gh` not installed on this machine).
- Paste this MR description when opening a remote PR after `git init` / push, or attach `MR.md` to the release notes for Apps Script deploy.

---

## Suggested commit / PR title

`fix(crm): Jul 13–16 stabilization — scheme dropdowns, finance overdue, dialog HTML, deferred sync`
