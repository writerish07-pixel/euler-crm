# EULER CRM — FINAL PHASE (DETAILED) · v2.2
**EV Dealership CRM · React (frontend) + FastAPI (backend) + MongoDB (data)**
A full-stack rewrite of the original **Google Sheets + Apps Script** system (~27,000 lines / ~50 `.gs` modules). Goal: eliminate spreadsheet performance limits while preserving **100% of the commercial, scheme, workflow, reporting and permission logic**. The original spreadsheet is the source of truth; the Apps Script was the business engine; this app reproduces both.

- **Preview (dev):** value of `REACT_APP_BACKEND_URL` in `/app/frontend/.env`
- **Production (live):** https://euler-connect.emergent.host
- **Roles / logins:** Owner `owner@euler.com` / `euler@123` · Executive `executive@euler.com` / `euler@123`
- **Companion docs:** `/app/EULER_PRODUCTION_AUDIT.md` (parity audit), `/app/memory/PRD.md` (product spec + changelog)

---

## TABLE OF CONTENTS
1. System architecture
2. Roles & permissions
3. The deal lifecycle (end-to-end)
4. Step-eligibility matrix (LeadPicker parity)
5. The Lead 360° drawer — tab by tab, field by field
6. Commercial engine — every formula
7. Scheme engine — share-split, availability, benefit modes
8. Dealer earnings — definitions + full Turbo Max PV example
9. Money-received (receipt) flows — claims / finance / insurance
10. Insurance payout logic
11. Reports & dashboards
12. Masters (catalogue) & Settings
13. Integrations (Auth, Google Sheets)
14. Complete API reference
15. Data model (collections & key fields)
16. Validation & business-rule catalogue
17. Production-readiness status & open items
18. Deployment & environments
19. Iteration changelog (8–12)

---

## 1. SYSTEM ARCHITECTURE
```
/app
├── backend/
│   ├── server.py        # FastAPI app: all routes, workflow guards, reports, sync
│   ├── commercial.py    # Pure calc engine: totals, margin, scheme split, claim, payout rate
│   ├── gsheets.py       # Google Sheets 1-way append via Service Account
│   ├── auth.py          # JWT auth, password hashing, role dependency (owner_only)
│   ├── seed.py          # Migration/seeding from the legacy Euler Master workbook
│   ├── requirements.txt
│   └── .env             # MONGO_URL, DB_NAME, JWT secret, Sheet config (env-only, no hardcoding)
├── frontend/
│   ├── src/
│   │   ├── pages/       # Dashboard, Leads, LeadDrawer, Bookings, Quotations, Activities,
│   │   │                #   Finance, Insurance, Claims, InsurancePayoutReport, EarningsReport,
│   │   │                #   OwnerCommercialReport, OemClaimDashboard, ClaimExceptions,
│   │   │                #   Settings, Share, Login, PriceMaster, SchemeMaster, IncentiveMaster
│   │   ├── components/  # Layout (sidebar/nav), ui.js (PageHeader, Table, Card, StatCard, Badge,
│   │   │                #   Button, Field, Input, Select, Drawer, Tabs)
│   │   ├── lib/         # api.js (axios get/post/put/del + export), format.js (inr, compactInr, fmtDate)
│   │   └── context/     # AuthContext.js
│   └── .env             # REACT_APP_BACKEND_URL (never edited by hand)
└── memory/, test_reports/, EULER_PRODUCTION_AUDIT.md, EULER_CRM_FINAL_PHASE.md
```
- **Routing rule:** every backend route is prefixed `/api` (Kubernetes ingress routes `/api/*` → :8001, everything else → :3000). Frontend always calls `REACT_APP_BACKEND_URL`.
- **Services** run under supervisor with hot reload.

---

## 2. ROLES & PERMISSIONS
| Capability | Owner | Executive |
|---|:--:|:--:|
| Leads, bookings, price, scheme, payments, delivery, close | ✅ | ✅ |
| Finance / Insurance / Claims registers + receipts | ✅ | ✅ |
| Dealer Earnings, Owner Commercial, OEM Claim Dashboard, Claim Exceptions, Payout Report | ✅ | ❌ (403 + hidden nav) |
| Settings / Masters | ✅ | limited |
Backend enforces owner-only routes via `Depends(owner_only)`; frontend hides owner-only nav and route-guards them.

---

## 3. THE DEAL LIFECYCLE (END-TO-END)
**New Lead → Convert to Booking → Price Structure → Scheme Update → Add Payment → Finance / Claims / Insurance → Mark Delivered → Close Lead.**

1. **New Lead** — capture customer, mobile (unique), interested model/variant, source, executive.
2. **Convert to Booking** — records booking + advance (works even before pricing = "slim/provisional booking").
3. **Price Structure** — set ex-showroom & all charges → Customer Payable computed.
4. **Scheme Update** — apply OEM/dealer offers (only components available for that model); choose benefit mode.
5. **Add Payment** — customer receipts; outstanding recalculated; over-payment blocked.
6. **Finance / Claims / Insurance** — arrange finance (shifts liability to financer), track OEM claim (company share), sell insurance (payout income).
7. **Mark Delivered** — only after full delivery checklist + cleared outstanding.
8. **Close Lead** — reason required; delivered deals also need RC + number plate.

---

## 4. STEP-ELIGIBILITY MATRIX (LeadPickerService `PICKER_STAGE` + `requireActiveLead_`)
`GET /api/leads/{id}/360` returns an `actions{}` object driving UI + enforced server-side (409/422).

| Action | Allowed when | Blocked with |
|---|---|---|
| `canBook` (Convert) | Active AND not Booked/Delivered | 409 |
| `canPrice` / `canScheme` / `canPayment` / activity | Active | 409 |
| `canDeliver` (Mark Delivered) | Active + Booked + not Delivered + checklist + outstanding cleared | 409 / 422 |
| `canClose` | Active (reason required; RC+plate if delivered) | 409 / 422 |
| `canFinanceReceipt` | not Archived (allowed post-close) | — |

Once a lead passes a one-time step (Booking, Delivery, Close) it cannot repeat it (badge "Booked ✓ / Delivered ✓"); editable data tabs (Price/Scheme/Payments) can be revised while Active.

---

## 5. THE LEAD 360° DRAWER — TAB BY TAB
Header: status badges (currentStatus, accountStatus), **Edit** button, live **Outstanding**. Footer: workflow actions (Convert / Close) gated by `actions`.

### 5.1 Overview
Read-only summary: Gross Vehicle Cost, TCS, Total Discount, Customer Payable, Customer Outstanding, Dealer Margin, **OEM Claimable (Company Share)**, **Dealer Scheme Retained**.

### 5.2 Price Structure (`PUT /leads/{id}/price-structure`, Active only)
Fields: ex-showroom, RTO, insurance, accessories, handling charges, TRC, FASTag, extended warranty, other charges, **Final Exchange Value**, **TCS Applicable (Yes/No)**. Live preview: GVC · TCS · Total Discount · Customer Payable.

### 5.3 Scheme (`PUT /leads/{id}/scheme`, Active only; rules from `GET /leads/{id}/scheme-rules`)
- Renders **only components available** for the model/variant/month (others hidden + "not available" note); each shows its **max cap**.
- Fields (when available): Consumer, Exchange, Loyalty, Referral, DSA, Additional Discount; **Benefit Mode** (Full / Partial / No Benefit); OEM Extra Support Received / Passed.
- **Partial Benefit** reveals a per-component "amount passed to customer" breakup (sent as `benefitPassedBreakup` JSON).
- Preview: OEM Eligible · Dealer Discount · **OEM Claimable (Co. Share)** · **Dealer Scheme Retained**.
- Server rejects (422) any component not in Scheme Master or above its cap.

### 5.4 Payments (`POST /leads/{id}/payments`)
Fields: Amount, Mode (Cash/UPI/Bank/Finance…), Narration (+ financer name/file when Finance). Rules: amount > 0; **total received may not exceed Customer Payable** (422) unless payable is still ₹0 (provisional). A **Finance-mode** entry accrues the financer file's committed amount and shifts outstanding customer→financer.

### 5.5 Delivery (`PUT /leads/{id}/delivery`)
Checklist toggles: Insurance, Registration, Invoice, RC, PDI. Fields: Invoice Number, Chassis Number, Number Plate, Insurer Name, Delivery Date, **Mark Delivered?**. To mark delivered (422 otherwise): Insurance=Yes + Insurer, Registration=Yes, Invoice=Yes + Invoice Number, Chassis Number, PDI=Yes, **customer outstanding = 0**. Once delivered, paperwork stays editable but it can't be re-delivered.

### 5.6 Insurance (per-lead tab)
Premium pre-filled from Price Structure; enter Insurer, Policy Number, Executive, **Payout Rate %**, Received. Expected Payout = Premium × Rate. _(Auto-fill of 49%/36.5% currently on the standalone Insurance Payouts page; per-lead tab auto-fill is a pending item — see §17.)_

### 5.7 Activity (`POST /leads/{id}/activities`, Active only)
Log calls/visits/follow-ups with type, discussion, next follow-up date.

---

## 6. COMMERCIAL ENGINE — EVERY FORMULA (`commercial.py`)
Constants verified identical to `Config.gs` COMMERCIAL.

- **Charge components** (`CHARGE_KEYS`): exShowroom, accessories, insurance, registrationRto, fastag, handlingCharges, trc, extendedWarranty, rsaAmc, otherCharges.
- **Gross Vehicle Cost (GVC)** = Σ CHARGE_KEYS.
- **TCS** = 1% × GVC when `tcsApplicable = Yes` (else 0).
- **Total Discount (offer)** = Σ OEM offers + dealer offers (Consumer, Exchange, Loyalty, Referral, DSA, Additional).
- **Benefit actually passed** = per Benefit Mode (Full = all; Partial = per-component breakup; No = 0).
- **Customer Payable** = GVC + TCS − benefit passed − exchange adjustment (final exchange value).
- **Customer Outstanding** = max(0, Customer Payable − total received) (0 if payable is 0).
- **Dealer Margin (gross)** = 4% × exShowroom. **Margin net of GST** (`marginNetExGst`) = grossmargin ÷ 1.05 (5% GST removed).
- **deriveClaim** = per-component OEM/dealer classification; DSA is approval-required (auto-approved on a booked deal unless rejected).

---

## 7. SCHEME ENGINE (`SchemeMasterService` parity)
- **Scheme Master row** per model/variant/month: `companyShare`, `dealerShare`, `totalBenefit`, `component`, `componentKey`, effective window, status.
- **Model/variant aliasing:** Turbo/Turbo Max→`turbo`, Hi-Load/HiLoad→`hiload`, HiCity→`hicity`, Hirange/Neo HiRange/High Range→`hirange`, Storm/Strom→`storm`; variant XR/TR/GBT/non-GBT normalisation.
- **Company-share-FIRST split** (`scheme_share_split_for`): for each applied offer, fill the OEM **company** share first (capped), remainder up to the **dealer** share.
- **OEM Claimable = eligible company share** (not the raw offer). Additional Discount is always 100% dealer-funded.
- **Availability** (`get_scheme_offer_rules_for_vehicle`): a component shows only if a matching Active Scheme Master row exists for that model/variant/month, with a max cap; else hidden + rejected (422).
- **Benefit modes**: Full (pass everything), Partial (`benefitPassedBreakup` per component), No Benefit (pass nothing).
- **Scheme Retained (dealer income)** per component = (company share KEPT, i.e. not passed) − (dealer share GIVEN to customer).

---

## 8. DEALER EARNINGS
**Total Dealer Earnings = Dealer Margin (net GST) + Scheme Retained + Insurance Income + OEM Extra Support kept ( + Documentation/Warranty/RSA/Referral income — PENDING, see §17).**
- `Scheme Retained = Σ (company_kept − dealer_given)`
- `OEM Extra Support kept = Received − Passed`
- OEM Claimable (company share) is the **cash** recovered from OEM and is already inside Scheme Retained — **never added twice**.

### Worked example — Turbo Max · City (PV), ex-showroom ₹6,40,000
Scheme offered: Exchange 15k, DSA 10k, Referral 5k, Loyalty 5k → **OEM company ₹25,000 / dealer ₹10,000**. Insurance premium ₹22,000 (Turbo rate 49%).
Constants: **Dealer Margin ₹23,220** · **Insurance Income ₹10,780**.

| # | Scenario | Margin | Scheme Retained | Insurance | OEM Extra kept | **TOTAL EARNINGS** | Customer Payable |
|---|---|---:|---:|---:|---:|---:|---:|
| 1 | Full Benefit (all passed) | 23,220 | −10,000 | 10,780 | 0 | **24,000** | 6,27,000 |
| 2 | Partial (pass Exchange only) | 23,220 | +10,000 | 10,780 | 0 | **44,000** | 6,47,000 |
| 3 | No Benefit | 23,220 | +25,000 | 10,780 | 0 | **59,000** | 6,62,000 |
| 4 | No Benefit + OEM extra ₹10k kept | 23,220 | +25,000 | 10,780 | 10,000 | **69,000** | 6,62,000 |
| 5 | Full Benefit + OEM extra ₹10k passed | 23,220 | −10,000 | 10,780 | 0 | **24,000** | 6,17,000 |

**Reading:** you earn most when benefit is NOT passed (₹59k) and least when fully passed (₹24k) — passing benefit is a customer-acquisition cost partly funded by the dealer's own ₹10k share. OEM extra support is pure profit only if kept (Case 4). OEM Claimable ₹25k is constant across modes (always claimed); what varies is how much you hand the customer.

---

## 9. MONEY-RECEIVED (RECEIPT) FLOWS
Dropdown-driven; each keeps a **receipt history** (`receipts[]`: amount, date, reference/UTR).

| Stream | Trigger | Endpoint | Effect |
|---|---|---|---|
| **OEM Claim** (per component) | Claims page → Record Claim Received | `POST /api/claims/receipt` | accrues Received; status Partial/Received; does not change customer payable |
| **Financer Receipt** | Finance page → Record Financer Receipt | `POST /api/finance/{file}/receipt` | Disbursed↑, file Outstanding↓; **customer outstanding unchanged** (already shifted when Finance entry was made) |
| **Insurer Payout** | Insurance page → Record Payout | `POST /api/insurance/{id}/receipt` | Received Payout↑, Outstanding↓; entries pick from **delivered leads** only |

**Finance liability shift:** a Finance-mode payment on a lead reduces the customer's outstanding by that amount and makes the **financer** liable (finance file committed amount). Actual disbursement is booked separately via the financer receipt.

---

## 10. INSURANCE PAYOUT LOGIC (`InsuranceService` parity)
- **Payout rate by model:** Storm/Turbo = **49%**; all other models = **36.5%** (auto-suggested, manual override kept).
- **Expected Payout = Premium × Rate**; **Outstanding = Expected − Received**; status Pending → Partial → Received.
- Expected payout is the dealer's **Insurance Income** in Dealer Earnings.
- Per-lead premium pre-fills from Price Structure.

---

## 11. REPORTS & DASHBOARDS
- **Dashboard** — today/monthly leads, bookings, deliveries; payments by mode; customer & company outstanding; model performance. _(Missing vs source: conversion %, MTD revenue, follow-up KPIs, finance-outstanding — see §17.)_
- **Owner Commercial Report** (`/reports/owner-commercial`) — discount cost ownership (dealer vs OEM), claim position (pending/received, scheme ROI %), averages, executive discount usage.
- **OEM Claim Dashboard** (`/reports/oem-claim-dashboard`) — claim status summary, value summary (company vs dealer share, OEM liability), monthly / scheme-wise / executive-wise, all at company-share values.
- **Claim Exception Report** (`/reports/claim-exceptions`) — Missing / Incorrect / Unapproved / Duplicate claim, Overpayment, Negative discount/payable.
- **Dealer Earnings / Earnings Report** (`/reports/dealer-earnings`) — margin + scheme retained + insurance + OEM extra support, by month & component.
- **Insurer Payout Report**, **Excel Export**, public **Share board** (`/share`: Active Bookings, Retail MTD, New, Today).

---

## 12. MASTERS & SETTINGS
- **Price Master** — model/variant → ex-showroom + charges (feeds Price Structure).
- **Scheme Master** — model/variant/month → company/dealer share per component (drives scheme availability + split).
- **Incentive Master** — executive incentive definitions.
- **Settings / masters lists** — executives, payment modes, benefit modes, sources, statuses.

---

## 13. INTEGRATIONS
- **Auth** — JWT; roles Owner/Executive; `owner_only` dependency; test creds in `/app/memory/test_credentials.md`.
- **Google Sheets** — 1-way **append** sync via Service Account (UI "Sheet Synced" badge). Edits/deletes not propagated (append-only).

---

## 14. COMPLETE API REFERENCE (prefix `/api`)
**Auth:** `POST /auth/login`
**Leads:** `GET /leads` · `POST /leads` (dup-mobile 409) · `PUT /leads/{id}` · `GET /leads/{id}/360` (+actions) · `POST /leads/{id}/convert-booking` · `PUT /leads/{id}/price-structure` · `GET /leads/{id}/scheme-rules` · `PUT /leads/{id}/scheme` · `POST /leads/{id}/payments` · `PUT /leads/{id}/delivery` · `POST /leads/{id}/close` · `POST /leads/{id}/activities`
**Finance:** `GET /finance?view=all|pending|overdue` · `POST /finance/{file}/receipt`
**Claims:** `GET /claims` · `POST /claims/settle` · `POST /claims/receipt`
**Insurance:** `GET /insurance` · `POST /insurance` · `PUT /insurance/{id}` · `DELETE /insurance/{id}` · `POST /insurance/{id}/receipt`
**Reports (owner):** `GET /reports/owner-commercial` · `/reports/oem-claim-dashboard` · `/reports/claim-exceptions` · `/reports/dealer-earnings` · payout report
**Other:** `GET /dashboard` · `GET /share/dashboard` · `GET /masters` · price/scheme/incentive master CRUD · export.

---

## 15. DATA MODEL (collections & key fields)
- **leads** — leadId, customerName, mobile, interestedModel, variant, source, executive, currentStatus, accountStatus, bookingDate, bookingAmount, ex-showroom + all charges, scheme offers, benefitMode, benefitPassedBreakup, oemExtraSupportReceived/Passed, derived: grossVehicleCost, customerPayable, totalDiscount, totalReceived, customerOutstanding, companyOutstanding (=eligible company share), oemClaimCompanyShare, schemeCompanyTotal, dealerSchemeRetained, oemExtraSupportRetained, dealerMarginNetExGst, deliveryStatus, closedDate, closeReason, rcStatus, numberPlate.
- **payments** — leadId, amount, paymentMode, narration, financerName, financeFileNumber, date.
- **finance** — fileNumber, leadId, customerName, financer, sanctionedAmount (committed), receivedAgainstFile, fileOutstanding, status, receipts[], lastPaymentDate.
- **claims** — claimId, leadId, componentKey, receivedAmount, eligibleClaim, claimStatus, claimReference, receipts[].
- **insurance** — entryId, leadId, customerName, model, insuranceCompany, policyNumber, insuranceAmount (premium), payoutRate, expectedPayout, receivedPayout, payoutOutstanding, status, receipts[].
- **scheme_master / price_master / incentive_master · activities · deliveries · bookings · users · counters.**

---

## 16. VALIDATION & BUSINESS-RULE CATALOGUE
- Duplicate 10-digit mobile blocked on lead create (409).
- Payment cannot exceed Customer Payable (422); provisional allowed only at ₹0 payable.
- Scheme component not in Scheme Master, or above cap → 422.
- Booking only once; Delivery only after checklist + cleared outstanding; Close requires reason (+RC/plate if delivered).
- Step actions enforced by `actions` object (409).
- Owner-only reports (403 for executive).
- All money math rounded via a single `round2` helper; datetimes stored ISO/UTC.

---

## 17. PRODUCTION-READINESS STATUS (see `EULER_PRODUCTION_AUDIT.md`)
**Overall 84/100.** Core commercial/scheme/workflow engine verified-correct (iterations 8–12; automated tests pass).

**Resolved:** payment over-cap guard; OEM/finance/insurance receipt flows + history; insurance delivered-lead dropdown; model-based insurance payout rate (standalone page); scheme availability + caps; step-gating; delivery/close validation; dup-mobile.

**Open before "100% identical" go-live:**
- **C1** Dealer Earnings missing income lines: Documentation, Warranty, RSA, Referral (no capture field yet) → totals understated.
- **H1** Dashboard KPI parity: conversion %, MTD revenue, follow-up KPIs, Finance total outstanding.
- **H3** Claim lifecycle dates (submitted/approved) + ageing.
- **H4** Audit / transaction log (who/what/when) for finance-sensitive edits.
- **H5** RSA/AMC charge input field (engine sums it, no UI input).
- **Per-lead Insurance tab** needs the same 49%/36.5% auto-fill as the standalone page.
- **Regression:** full priced+scheme+delivered deal end-to-end reconciliation; concurrency (double-submit) idempotency.

**Verdict:** **GO for a supervised pilot** (money math verified); **NO-GO for "100% identical"** until C1 + H1/H3/H4/H5 close and regression passes.

**Not ported (Apps-Script runtime infra, N/A to this stack):** LockService, SyncEngine internals, SelfHealing/Backup/CrashReport/HealthCheck/PerformanceMonitor/VersionManagement, DataStore/SheetLayout, Dialogs UI — replaced by MongoDB + FastAPI.

---

## 18. DEPLOYMENT & ENVIRONMENTS
- **Preview** (where changes are made) and **Production** (`euler-connect.emergent.host`) are separate. New changes require a **redeploy** to reach production.
- Env-only config: `REACT_APP_BACKEND_URL` (frontend), `MONGO_URL` + `DB_NAME` (backend); no hardcoded URLs/secrets.
- Google Sheet sync requires the Service Account JSON (active, Editor rights).
- Do not reseed the DB unless resetting data (baseline = 10 real leads).

---

## 19. ITERATION CHANGELOG
- **Iter 8** — Step-eligibility gating (PICKER_STAGE + requireActiveLead) backend + UI; `actions{}` on /360.
- **Iter 9** — Scheme company-share-first split, model/variant aliases, scheme availability + caps, Partial per-component breakup; delivery checklist + outstanding gate; close reason + RC/plate; duplicate-mobile block. (13/13 tests.)
- **Iter 10** — Owner Commercial Report, OEM Claim Dashboard, Claim Exception Report (owner-only) + "Owner Reports" nav.
- **Iter 11** — Receipt flows (OEM claim / financer / insurer) with history; payment over-cap guard; insurance delivered-lead dropdown. (8/8 tests.)
- **Iter 12** — Insurance payout rate auto-fill by model (49% / 36.5%) on the standalone page + backend fallback; Production Readiness Audit written.

_Last updated: 2026-06 · v2.2 Full-stack._
