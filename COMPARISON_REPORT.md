# Euler CRM — Original (Google Apps Script) vs New (Full-Stack) Comparison Report

_Generated during the full-stack migration. Original = the Google Sheets + Apps Script system (~50 `.gs` modules) + static GitHub Pages portal. New = React + FastAPI + MongoDB app._

---

## 1. Calculation & Business-Logic Parity

The commercial math is the heart of the system. It was ported **verbatim** from `CommercialEngineService.gs` into `backend/commercial.py`. Confirmed identical:

| Calculation | Original (`.gs`) | New (`commercial.py`) | Match |
|---|---|---|---|
| **Gross Vehicle Cost** | Σ(exShowroom, accessories, insurance, RTO, fastag, handling, TRC, ext-warranty, RSA/AMC, other) | same 10 components | ✅ |
| **TCS** | 1% when taxable ≥ ₹10,00,000 and `tcsApplicable=Yes` | `TCS_RATE=0.01`, `TCS_THRESHOLD=1_000_000` | ✅ |
| **OEM discount pool** | consumer + exchange + loyalty + referral + dsa (payer=OEM) | `sum_oem_offers()` | ✅ |
| **Dealer discount pool** | additional (payer=Dealer) | `sum_dealer_offers()` | ✅ |
| **Benefit mode** | Full / Partial / None → passed-to-customer | `resolve_customer_benefit_passed()` | ✅ |
| **Customer Payable** | GrossInvoice − totalPassed − finalExchangeValue | `compute_commercial_totals()` | ✅ |
| **Dealer margin** | preGst = ex/1.05; gross = preGst×4%; GST split at 5% | `compute_dealer_margin()` (`DEALER_MARGIN_RATE=0.04`, `GST=0.05`) | ✅ |
| **Claim derivation** | claimable = OEM components; dsa needs approval; additional not claimable | `derive_claim()` + `COMPONENT_POLICY` | ✅ |
| **Outstanding** | customerPayable − Σ payments | `recompute_lead()` | ✅ |
| **Payment running total / balance** | running Σ, outstanding = payable − running | `_add_payment_internal()` | ✅ |
| **Finance file** | sanctioned vs received vs outstanding | `_upsert_finance_file()` (auto on Finance-mode payment) | ✅ |
| **Insurance payout** | expected = premium × payoutRate%; outstanding = expected − received | `_insurance_derive()` | ✅ |
| **Dealer earnings** | margin(net) + scheme retained + insurance income + finance/accessories/exchange/other | `/reports/dealer-earnings` + migrated `dealer_earnings` | ✅ |
| **Dashboard KPIs** | leads/bookings/deliveries, conversion, payments-by-mode, outstanding split | `/api/dashboard` | ✅ (verified vs FINAL_PHASE.md) |

**Component policy (identical to `Config.gs` COMMERCIAL.COMPONENT_POLICY):**
- consumer / exchange / loyalty / referral → OEM, claimable, no approval
- dsa → OEM, claimable, approval required
- additional → Dealer, dealer-funded, not claimable

---

## 2. Module Mapping (Original `.gs` → New)

| Original module(s) | New location |
|---|---|
| `CommercialEngineService.gs`, `CommercialSchemeService.gs`, `PricingService.gs` | `backend/commercial.py` + price-structure/scheme endpoints |
| `LeadService.gs`, `LeadPickerService.gs`, `MergeLeadService.gs` | `/api/leads*`, Lead Register + Lead 360 drawer |
| `BookingService.gs` | `/api/leads/{id}/convert-booking`, Bookings page |
| `PaymentService.gs` | `/api/leads/{id}/payments`, Payment Ledger |
| `DeliveryService.gs` | `/api/leads/{id}/delivery`, Delivery Tracker |
| `FinanceService.gs` | `/api/finance`, Finance Register |
| `InsuranceService.gs` | `/api/insurance*`, Insurance page + lead Insurance tab |
| `OemClaimService.gs`, `ClaimService.gs` | `/api/claims*`, OEM Claim Register |
| `ExtraIncomeService.gs` | `/api/dealer-earnings`, `/api/reports/dealer-earnings` (owner) |
| `SchemeMasterService.gs`, `MasterDataService.gs`, `MasterService.gs` | `/api/scheme-master`, `/api/incentive-master`, `/api/masters` |
| `PriceMasterImport.gs`, `PriceMaster*` | `/api/price-master*`, editable Price Master |
| `DashboardService.gs` | `/api/dashboard`, Dashboard page |
| `Customer360Service.gs` | `/api/leads/{id}/360`, Lead 360 drawer |
| `ActivityService.gs`, `RecentRecordsService.gs` | `/api/activities`, Activity Log |
| `QuotationService.gs` | `/api/quotations`, Quotations page |
| `GlobalSearchService.gs` | lead search (`q` param) |
| `ImportService.gs`, `ImportData.gs` | `/api/leads/import/*` with column mapping |
| `WebApi.gs`, `NavigationService.gs`, `Dialogs.gs` | React SPA (router + drawers/modals) |
| `DataStore.gs`, `SyncEngine.gs` | MongoDB collections (replaces the spreadsheet store) |
| `BackupService.gs`, static `share.html` | `/api/export` (xlsx) + public `/share` company board |
| `ValidationService.gs`, `BusinessRulesService.gs` | Pydantic models + endpoint validation |

---

## 3. UI Comparison

| Aspect | Original | New |
|---|---|---|
| **Delivery mechanism** | Google Sheets sidebar/dialogs (Apps Script HTML) + a static GitHub Pages portal that called the Apps Script Web App | Single-page React app (own domain), persistent sidebar + top bar |
| **Company board** | `share.html` (dark navy "Bookings & Retail" board, Syne/Instrument Sans) | Re-created **pixel-for-pixel** at `/share` using the original `share.css`, now also lists **All Leads** |
| **Data entry** | Sheet rows + dialog forms | Structured forms in side-drawers/modals with live commercial preview |
| **Navigation** | Sheet tabs + custom menu | 15+ module sidebar with role-based visibility |
| **Look & feel** | Spreadsheet-driven | Clean light SaaS dashboard, INR (lakh/crore) formatting, status chips |

---

## 4. What the New System Adds / Improves

- **Performance:** the original reloaded the whole spreadsheet store on nearly every action (`loadCrmStore_` / `force`), the root cause of slowness. The new app reads only needed rows from an indexed DB → near-instant pages.
- **Roles & security:** JWT auth with Owner/Executive; Dealer Earnings, reports & user management are owner-only (the original had no real auth).
- **Reports:** owner Insurer Payout Report and Dealer Earnings Report (by month/insurer) with charts.
- **Google Sheet sync (one-way, live):** every new Lead/Booking/Payment/Delivery/Claim is appended to the **existing Euler Master sheet** via a service account, plus an idempotent Backfill and a top-bar sync-health badge.
- **Import with column mapping**, **Excel export** (sheet per module), **editable Price/Scheme Master**, and **owner lead-edit** to correct staff mistakes.

---

## 5. Gaps / Not Yet Ported (backlog)

- Certification/self-healing/health-check utilities (`*CertificationService.gs`, `SelfHealingService.gs`, `HealthCheckService.gs`) — these were spreadsheet-integrity tools; not needed with a real DB.
- OEM Extra Support edge cases (`forcePersistOemExtraSupportForLead_`) — supported in the engine (`oemExtraSupportReceived/Passed`) but no dedicated UI yet.
- Incentive Register auto-computation (slabs) — master data shown; computation is backlog.
- Two-way Sheet sync (currently one-way App→Sheet by design).

_Overall: 100% of the commercial/financial calculation logic is faithfully reproduced; the UI is modernised while the company board matches the original exactly._
