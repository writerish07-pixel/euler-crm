# EULER CRM — FINAL PHASE (v2.2)
**EV Dealership CRM · React + FastAPI + MongoDB**
_A full-stack rewrite of the original Google Sheets + Apps Script system (~27k lines, 50 modules), preserving 100% of the commercial/scheme/workflow logic._

- **Preview (dev):** driven by `REACT_APP_BACKEND_URL` in `/app/frontend/.env`
- **Production (live):** https://euler-connect.emergent.host
- **Logins:** Owner `owner@euler.com` / `euler@123` · Executive `executive@euler.com` / `euler@123`
- **Source of truth for parity:** the original `final fix/*.gs` codebase + the spreadsheet.

---

## 1. WHAT THE APP DOES
A complete dealership CRM that runs the full deal lifecycle and all commercial settlement math that used to live in the spreadsheet:

**New Lead → Convert to Booking → Price Structure → Scheme Update → Add Payment → Finance / Claims / Insurance → Mark Delivered → Close Lead.**

Every step enforces the exact business rules of the source system, computes commercials live, and (optionally) appends to the original Google Sheet.

---

## 2. NAVIGATION MAP
**Overview**
- **Dashboard** — KPIs (today/monthly leads, bookings, deliveries; payments by mode; outstanding; model performance).

**Sales Pipeline**
- **Lead Register** — all leads; open a lead for the 360° drawer (Overview · Price Structure · Scheme · Payments · Delivery · Insurance · Activity) + Edit + workflow actions.
- **Bookings** · **Quotations** · **Activity Log**

**Money**
- **Payment Ledger** — customer receipts (with over-payment guard).
- **Finance Register** — financer files (committed vs disbursed) + **Record Financer Receipt**.
- **Insurance Payouts** — insurer entries (per-model payout rate) + **Record Payout**.
- **Payout Report** (Owner) — insurer payout report.

**Owner Reports** (owner-only)
- **Owner Commercial Report** · **OEM Claim Dashboard** · **Claim Exceptions**
- **Dealer Earnings / Earnings Report**

**Catalogue & Admin**
- **OEM Claims register** · **Scheme Master** · **Incentive Master** · **Price Master** · **Settings**

**Public**
- **/share** — company Share board (Active Bookings, Retail MTD, New, Today).

---

## 3. WORKFLOW & STEP-ELIGIBILITY (LeadPickerService parity)
A lead can never repeat a completed step (`lead_actions()` + `_require_action()` guards, mirrors `PICKER_STAGE` + `requireActiveLead_`):

| Step | Allowed when |
|---|---|
| Convert to Booking | Active **and** not already Booked/Delivered |
| Price Structure / Scheme / Payment / Activity | Active only |
| Mark Delivered | Active + Booked + not already Delivered + **full checklist** + **customer outstanding cleared** |
| Close Lead | Active; **reason required**; if Delivered → **RC + Number Plate required** |
| Finance receipt | allowed even after Close (until Archived) |

Other enforced rules: **duplicate 10-digit mobile blocked** on create; **payment can't exceed Customer Payable** (provisional allowed only at ₹0 payable / slim booking).

---

## 4. COMMERCIAL ENGINE (`backend/commercial.py`)
- **Gross Vehicle Cost** = ex-showroom + accessories + insurance + RTO + FASTag + handling + TRC + extended warranty + RSA/AMC + other charges.
- **TCS** 1% when applicable.
- **Customer Payable** = GVC + TCS − benefit actually passed to customer − exchange adjustment.
- **Dealer Margin** = 4% of ex-showroom, net of 5% GST (`marginNetExGst`).
- Constants verified identical to `Config.gs` COMMERCIAL.

### Scheme share-split (company-share-FIRST)
- Each scheme component has a **company share** and **dealer share** in Scheme Master (per model/variant/month).
- Model/variant aliasing ported (Turbo Max→turbo, Hi-Load→hiload, HiCity/Hirange XR/TR, Storm).
- **OEM Claimable = OEM company share** (capped company-first), never the raw offer sum.
- **Scheme availability:** the Scheme tab only shows components that exist in Scheme Master for that model/variant/month; unavailable ones are hidden and rejected server-side; max caps enforced.
- **Benefit modes:** Full / Partial (per-component breakup) / No Benefit determine how much of each offer reaches the customer.

### Insurance payout (InsuranceService parity)
- **Rate by model:** Storm/Turbo = **49%**, all others = **36.5%** (auto-suggested, manual override kept).
- **Expected Payout = Premium × Rate**; Outstanding = Expected − Received.

---

## 5. DEALER EARNINGS — worked example (Turbo Max · City PV, ex ₹6,40,000)
Scheme offered: Exchange 15k, DSA 10k, Referral 5k, Loyalty 5k → OEM company share ₹25,000 / dealer share ₹10,000. Insurance premium ₹22,000.
Constants: **Dealer Margin ₹23,220** (4% net GST) · **Insurance Income ₹10,780** (49%).

| Scenario | Margin | Scheme Retained | Insurance | OEM Extra kept | **Total Earnings** | Customer Payable |
|---|---:|---:|---:|---:|---:|---:|
| Full Benefit (all passed) | 23,220 | −10,000 | 10,780 | 0 | **24,000** | 6,27,000 |
| Partial (Exchange only) | 23,220 | +10,000 | 10,780 | 0 | **44,000** | 6,47,000 |
| No Benefit | 23,220 | +25,000 | 10,780 | 0 | **59,000** | 6,62,000 |
| No Benefit + OEM extra ₹10k kept | 23,220 | +25,000 | 10,780 | 10,000 | **69,000** | 6,62,000 |
| Full Benefit + OEM extra ₹10k passed | 23,220 | −10,000 | 10,780 | 0 | **24,000** | 6,17,000 |

**Rules:** `Scheme Retained = (OEM company share kept) − (dealer share given)`; `OEM Extra kept = Received − Passed`. OEM Claimable (₹25k) is the cash recovered from OEM and is already inside Scheme Retained (not double-counted).

---

## 6. MONEY-RECEIVED (RECEIPT) FLOWS
Dropdown-driven "Record Receipt" on each money stream; each keeps a full **receipt history** (amount/date/UTR):

- **OEM Claim** (per component) → `POST /api/claims/receipt` — accrues Received, status Partial/Received.
- **Financer Receipt** → `POST /api/finance/{file}/receipt` — a Finance-mode entry on a lead shifts outstanding **customer→financer**; the disbursement is recorded here and does **not** change customer outstanding.
- **Insurer Payout** → `POST /api/insurance/{id}/receipt` — insurer entries pick from **delivered leads** only.

---

## 7. REPORTS (ports of OemClaimService / ExtraIncomeService)
- **Owner Commercial Report** — discount cost ownership (dealer vs OEM), claim position, scheme ROI, executive discount usage.
- **OEM Claim Dashboard** — claim status/value summary, monthly / scheme-wise / executive-wise, all at company-share values.
- **Claim Exception Report** — Missing / Incorrect / Unapproved / Duplicate claim, Overpayment, Negatives.
- **Dealer Earnings / Earnings Report** — margin + scheme retained + insurance + OEM extra support (per month & component).
- **Insurer Payout Report**, **Excel Export**, public **Share board**.

---

## 8. INTEGRATIONS
- **Auth:** JWT, roles Owner / Executive (owner-only routes gated front + back).
- **Google Sheets:** 1-way append sync via Service Account ("Sheet Synced" badge).

---

## 9. KEY API ENDPOINTS
`POST /api/auth/login` · `GET/POST /api/leads`, `PUT /api/leads/{id}` · `POST /api/leads/{id}/convert-booking` · `PUT /api/leads/{id}/price-structure|scheme|delivery` · `GET /api/leads/{id}/scheme-rules` · `POST /api/leads/{id}/payments|close|activities` · `GET /api/leads/{id}/360` (+ `actions`) · `GET/POST /api/finance`, `POST /api/finance/{file}/receipt` · `GET /api/claims`, `POST /api/claims/receipt|settle` · `GET/POST /api/insurance`, `POST /api/insurance/{id}/receipt` · `GET /api/reports/owner-commercial|oem-claim-dashboard|claim-exceptions|dealer-earnings` · `GET /api/dashboard` · `GET /api/share/dashboard`.

---

## 10. DATA MODEL (collections)
`leads · bookings · payments · finance · claims · insurance · scheme_master · price_master · incentive_master · activities · deliveries · users · counters`.

---

## 11. PRODUCTION-READINESS STATUS (see `EULER_PRODUCTION_AUDIT.md`)
**Overall 84/100.** Core commercial/scheme/workflow engine is verified-correct and test-proven (iterations 8–12).

**Resolved:** payment cap, all 3 receipt flows, insurance delivered-lead dropdown, model-based payout rate.

**Open before full "100% identical" go-live:**
- **C1** Dealer Earnings missing income lines (Documentation / Warranty / RSA / Referral) — no capture field yet.
- **H1** Dashboard KPI parity (conversion %, MTD revenue, follow-ups, finance outstanding).
- **H3** Claim lifecycle dates (submitted/approved) + ageing.
- **H4** Audit / transaction log (who/what/when).
- **H5** RSA/AMC charge input field.
- Per-lead Insurance tab: add the same 49%/36.5% auto-fill as the standalone page.
- Regression: full priced+scheme+delivered deal reconciliation; concurrency double-submit.

**Verdict:** **GO for a supervised pilot** (money math verified); **NO-GO for "100% identical"** until C1 + H1/H3/H4/H5 close and regression passes.

---

## 12. DEPLOYMENT NOTES
- Preview and Production are separate. Changes made in preview require a **redeploy** to reach `euler-connect.emergent.host`.
- Env-driven config only (`REACT_APP_BACKEND_URL`, `MONGO_URL`, `DB_NAME`); no hardcoded secrets.
- Google Sheet sync needs the Service Account JSON present (currently active with Editor rights).

_Last updated: 2026-06 · v2.2 Full-stack._
