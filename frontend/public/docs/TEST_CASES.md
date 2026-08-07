# TEST_CASES — Euler CRM Regression Suite

Each case: **ID · Area · Steps · Expected**. Priority P0 (blocker) / P1 / P2. Use Owner `owner@euler.com` unless noted. Numbers reference the certified engine values.
_Version 2.2 · 2026-06_

## A. AUTH & PERMISSIONS
- **T-A1 (P0)** Login owner/exec → both succeed, correct role in token.
- **T-A2 (P0)** Executive GET `/api/reports/dealer-earnings` → **403**; owner → **200**. Same for owner-commercial, oem-claim-dashboard, claim-exceptions, payout report.
- **T-A3 (P1)** Executive sidebar: no "Owner Reports"; Owner: present.

## B. LEAD & DUPLICATE
- **T-B1 (P0)** Create lead with a mobile already used → **409**.
- **T-B2 (P1)** Create lead unique mobile → 200, leadId issued.

## C. STEP-ELIGIBILITY
- **T-C1 (P0)** Convert-booking on already-Booked lead → **409**; `/360` actions.canBook=false, isBooked=true.
- **T-C2 (P0)** Convert-booking on New Active lead → 200; then canBook=false afterwards.
- **T-C3 (P0)** New lead `/360`: canBook=true, canDeliver=false.
- **T-C4 (P1)** Price/Scheme/Payment/Activity on a non-Active lead → **409**.

## D. COMMERCIAL MATH (Turbo Max City PV, ex 640000, ins 22000)
- **T-D1 (P0)** GVC = 662,000; Dealer Margin net = **23,220**.
- **T-D2 (P0)** No scheme applied → Customer Payable = 662,000.
- **T-D3 (P0)** TCS toggled Yes → TCS = 1% × GVC added to payable.

## E. SCHEME AVAILABILITY & VALIDATION
- **T-E1 (P0)** `/leads/{turbo}/scheme-rules`: consumerDiscount.allowed=false; exchange/dsa/referral/loyalty allowed with caps; additionalDiscount allowed.
- **T-E2 (P0)** PUT scheme consumerDiscount=5000 on Turbo → **422**.
- **T-E3 (P0)** PUT scheme exchangeBonus above cap → **422**.
- **T-E4 (P0)** `/leads/{hiload}/scheme-rules`: all 5 OEM components allowed.
- **T-E5 (P1)** Scheme tab hides unavailable components + shows "not available" note.

## F. SCHEME RETAINED & COMPANY SHARE (Turbo full scheme: Exch15k/DSA10k/Ref5k/Loy5k; company 25k / dealer 10k)
- **T-F1 (P0)** No Benefit → dealerSchemeRetained = **25,000**; companyOutstanding = 25,000; payable 662,000.
- **T-F2 (P0)** Partial (pass Exchange 15k only) → retained = **10,000**; payable 647,000.
- **T-F3 (P0)** Full Benefit → retained = **−10,000**; payable 627,000.
- **T-F4 (P1)** DSA auto-approved on booked deal (eligible includes DSA company share).

## G. PAYMENTS & CAP
- **T-G1 (P0)** Payment > (payable − received) → **422**; within balance → 200.
- **T-G2 (P1)** Provisional advance at payable=0 (slim booking) → 200.
- **T-G3 (P1)** Outstanding recalculates after each receipt.

## H. FINANCE
- **T-H1 (P0)** Finance-mode payment on lead reduces customer outstanding by that amount; creates finance file with committed = amount, disbursed = 0.
- **T-H2 (P0)** `/finance/{file}/receipt` → disbursed↑, outstanding↓, status Partial/Received; **customer outstanding unchanged**.
- **T-H3 (P1)** `/finance/NONEXISTENT/receipt` → **404**. Receipt history persisted in `receipts[]`.

## I. INSURANCE
- **T-I1 (P0)** New entry model Turbo Max, no rate → rate 0.49, Expected = premium×0.49 (20000→9800).
- **T-I2 (P0)** Model Hi-Load → rate 0.365 (20000→7300).
- **T-I3 (P1)** `/insurance/{id}/receipt` accrues receivedPayout, outstanding↓, status Partial/Received, history saved.
- **T-I4 (P1)** Entry Lead dropdown lists only delivered leads.

## J. OEM CLAIM
- **T-J1 (P0)** `/claims` lists claimable components at company share; outstanding = eligible − received.
- **T-J2 (P0)** `/claims/receipt` accrues received, status Partial/Received, history saved.

## K. DELIVERY & CLOSE
- **T-K1 (P0)** Mark Delivered with missing checklist → **422** listing missing items.
- **T-K2 (P0)** Mark Delivered with customer outstanding > 0 → **422** (must clear).
- **T-K3 (P0)** Full checklist + outstanding 0 → delivered; cannot re-deliver.
- **T-K4 (P0)** Close with empty reason → **422**.
- **T-K5 (P0)** Close a delivered lead without RC/plate → **422**; with RC=Done + plate → 200.

## L. REPORTS & DASHBOARD
- **T-L1 (P0)** Owner Commercial, OEM Claim Dashboard, Claim Exceptions → 200, correct structure.
- **T-L2 (P1)** Dealer Earnings = margin + scheme retained + insurance + OEM extra support (per month).
- **T-L3 (P1)** Claim Exceptions flags overpayment/missing/duplicate correctly.
- **T-L4 (P2)** Dashboard KPIs render; Share board shows Active/Retail/New/Today.

## M. DATA INTEGRITY / REGRESSION
- **T-M1 (P0)** Full deal: New→Book→Price→Scheme→Pay→Insurance→Deliver→Close reconciles end-to-end vs hand calc (**U1**).
- **T-M2 (P1)** Rapid double-submit of booking/payment does not double-insert (**U4 — currently unguarded**).
- **T-M3 (P2)** 1000-lead load: list + dashboard respond acceptably (needs indexes — M2).

## PENDING (previously would fail — now IMPLEMENTED ✅)
- ✅ Documentation/Warranty/RSA/Referral income in Dealer Earnings (C1) — PUT /leads/{id}/extra-income + report components + dealerTotalEarnings.
- ✅ Dashboard conversion %, MTD revenue, finance-outstanding, follow-up due/overdue KPIs (H1).
- ✅ Claim submitted/approved dates + ageing (H3). Audit log who/what/when/old/new/IP (H4). RSA/AMC input (H5). Per-lead insurance 49%/36.5% auto-fill.
- ✅ U4 double-submit guard (identical receipt <4s → 409). U1 end-to-end reconciliation certified.

## NEW REGRESSION CASES (iter 13-14)
- **T-N1 (P0)** POST /insurance payoutRate=49, premium=20000 → stored 0.49, expectedPayout=9800 (no 49×). 36.5 → 0.365/7300.
- **T-N2 (P0)** PUT /leads/{id}/extra-income {1500,800,600,1000} → extraDealerIncomeTotal=3900; /reports/dealer-earnings totals.extra=3900 with 4 named components.
- **T-N3 (P0)** Every finance-sensitive mutation writes an audit_log entry; GET /api/audit-log owner 200 / executive 403; ?module= filter works.
- **T-N4 (P1)** /dashboard kpis include conversion, revenue, financeOutstanding, followupDue, followupOverdue.
- **T-N5 (P1)** /claims returns submittedDate/approvedDate/ageingDays; settle persists dates.
- **T-N6 (P1)** PUT /price-structure rsaAmc increases GVC + customerPayable.
- **T-N7 (P0)** Identical payment (same lead/amount/mode) within 4s → 409.
- **T-N8 (P0)** GET /reports/production-audit owner 200 / executive 403; 16 categories, 0 Critical, 0 High, blockers=[].

**Baseline discipline:** after any create/mutation in tests, revert (delete created docs, reset scheme/extra-income to zero, recompute) to keep the 10-lead baseline. `audit_log` is append-only — leave entries.
