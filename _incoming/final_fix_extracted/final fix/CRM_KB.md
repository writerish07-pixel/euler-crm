# Euler CRM — Knowledge Base (final fix folder)

**Location:** `C:\Users\hp\Desktop\final fix`  
**Version:** `v2.2-quotation-finance-fix` (Config.gs `PATCH_VERSION`)  
**Stack:** Google Sheets + Apps Script (50 `.gs` files, no HTML files — dialogs built in `Dialogs.gs` / `BookingService.gs` / `QuotationService.gs`)

---

## Architecture

| Layer | Files | Role |
|-------|-------|------|
| Entry / Menu | `Code.gs` | `onOpen`, CRM menu, triggers, Go-Live Quick Fix |
| Config | `Config.gs` | Sheet names, column defs, PUBLIC_API, MENU_HANDLERS |
| UI Dialogs | `Dialogs.gs`, `LeadPickerService.gs` | Lead picker, Scheme Update, payments, delivery |
| Booking | `BookingService.gs` | Convert to Booking (Price Master locked ex-showroom) |
| Quotation | `QuotationService.gs` | Deal Quotation + Quotation Log |
| Pricing | `PricingService.gs` | **Only** reader for PRICE MASTER |
| Scheme | `SchemeMasterService.gs` | Monthly scheme matrix, dropdown rules, claim shares |
| Commercial | `CommercialEngineService.gs` | Snapshots, totals, outstanding |
| Finance | `FinanceService.gs` | Finance Register, Pending, Overdue, financer receipts |
| Payments | `PaymentService.gs` | Payment Ledger (customer payments only) |
| Dashboard | `DashboardService.gs` | KPIs, payment-by-mode, outstanding split |
| Sync | `SyncEngine.gs`, `DataStore.gs` | Full refresh, CRM store index |
| Setup | `Setup.gs`, `FreshStartService.gs` | Sheet creation, fresh start (leads only) |
| Fixes | `FixesService.gs` | `setValueSafe_`, auto-refresh trigger, post-save refresh |
| Navigation | `NavigationService.gs`, `Customer360Service.gs`, `GlobalSearchService.gs` | v2.2 UX |

---

## Key sheets

| Sheet | Purpose |
|-------|---------|
| Lead Register | Master lead data |
| Booking Register | Booking rows |
| Payment Ledger | **Customer** payments (Cash/UPI/Finance DO) |
| Finance Register | **Financer** files (sanctioned vs received) |
| Finance Pending | Open finance files view |
| Finance Overdue | Delivered + finance unpaid > 2 days |
| PRICE MASTER | Vehicle pricing (import via Admin) |
| Scheme Master | Monthly OEM scheme ₹ shares |
| Quotation Log | Saved deal quotations |
| Commercial Snapshot | Booking commercial truth |

---

## Dashboard finance vs Finance Register

- **Dashboard → Finance (B29):** Sum of Payment Ledger rows where Payment Mode = `Finance` (customer DO amount this month).
- **Finance Register:** One row per finance **file** (File Number, Sanctioned, Received, Outstanding).
- Finance Register rows are created when **Add Payment** runs with Finance mode (`upsertFinanceFilePayment_`).
- If register is empty but dashboard shows finance: run **CRM → Admin → Rebuild Finance Register** or **Refresh All Sheets** (auto-sync when register empty).

---

## Scheme Update (current)

- Dialog: scheme amounts only (no customer fields — shown in lead picker summary).
- Manual number entry with Scheme Master max caps when matched.
- APIs: `getSchemeRulesForLeadDialog`, `getSchemeRulesForDialog`, `updateLeadFromDialog`.

---

## Price Master / dialogs

- Booking & Quotation call `getCommercialBreakup_` → `PricingService.getActivePrice_`.
- Ex Showroom is **locked** from Price Master; other charges editable.
- Turbo Max variants: `Maxx (PV)`, `Maxx (HD)`, `Maxx (FB)`, `Maxx (DV200)` in `PriceMasterImport.gs`.
- If "No response from server": reload sheet, run **Admin → Go-Live Quick Fix**, approve CRM authorization.

---

## Deploy

1. Copy all `.gs` from `final fix` into Apps Script (one file per script).
2. Save → reload spreadsheet.
3. Owner: **CRM → Admin → Go-Live Quick Fix**.
4. **CRM → Refresh All Sheets**.

---

## Recent fixes (17 Jul 2026)

1. **CRITICAL — Price Master row read:** `getPricingRows_()` used `numRows` as end row instead of `lastRow`, skipping the last PRICE MASTER rows (Turbo Max / Maxx variants). Fixed in `PricingService.gs`.
2. Booking + Quotation price APIs restored from working `src-fixed` build (`formatPriceForClient_`, `getPriceForBookingContext`, `getBookingLeadContext`).
3. Finance Register read/sync fixes (see prior session).
4. Quotation Log sheet ensured on open.
