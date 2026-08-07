# GO_LIVE_CHECKLIST — Euler CRM

Every item must be **PASS** before switching real dealership staff to production. Status: ✅ done · ⚠ open · ⬜ verify-before-launch.
_Version 2.3 · 2026-06 · Overall readiness 96/100 (ERP Production Audit engine · 0 Critical · 0 High)_

## 1. BUSINESS LOGIC PARITY
- ✅ Commercial totals (GVC, TCS, payable, outstanding) match source
- ✅ Dealer margin (4% net 5% GST)
- ✅ Scheme company-share-first split + model/variant aliases
- ✅ Scheme availability + caps per model/variant/month
- ✅ Benefit modes (Full/Partial/No) + per-component breakup
- ✅ Insurance payout rate (49% / 36.5%) + expected payout; single representation (DB fraction / UI %) with startup migration
- ✅ Finance liability shift customer→financer
- ✅ OEM claim = company share; per-component receipts + history
- ✅ **C1** Dealer Earnings extra-income lines (Documentation/Warranty/RSA/Referral) — DB + UI + report + total
- ✅ **H5** RSA/AMC charge input (Price Structure → GVC/payable)

## 2. WORKFLOW & VALIDATION
- ✅ Step-eligibility gating (no repeating Booking/Delivery/Close)
- ✅ Duplicate mobile block
- ✅ Payment over-cap guard (≤ Customer Payable)
- ✅ Delivery checklist + cleared outstanding
- ✅ Close reason (+ RC/plate for delivered)
- ✅ **U4** Concurrency: rapid identical receipt (same lead/amount/mode <4s) rejected (409)

## 3. REPORTS & DASHBOARD
- ✅ Owner Commercial, OEM Claim Dashboard, Claim Exceptions
- ✅ Dealer Earnings / Payout report / Share board
- ✅ **H1** Dashboard KPIs: conversion %, MTD revenue, finance outstanding, follow-up due/overdue
- ✅ **H3** Claim submitted/approved dates + ageing

## 4. PERMISSIONS & SECURITY
- ✅ Owner vs Executive enforced (front + back, 403 on owner routes)
- ✅ JWT auth; env-only secrets; no hardcoded keys
- ✅ **H4** Audit/transaction log (who/what/when/old/new/IP) on every finance-sensitive mutation — `audit_log` + owner-only /audit-log viewer
- ⬜ Password reset / lockout policy (optional — confirm requirement)
- ⬜ Confirm role granularity needs (Reception/Sales/TL/GM/Accounts) or keep Owner/Executive

## 5. DATA INTEGRITY
- ✅ Baseline preserved (10 real leads); no accidental reseed
- ✅ All money rounded via one helper; ISO/UTC datetimes
- ✅ **U1** Full priced+scheme deal reconciled end-to-end vs engine (certified in regression suite)
- ✅ DB indexes on leadId/mobile/currentStatus/bookingDate + payments.leadId + audit_log.timestamp (startup)
- ⬜ Backup/restore plan for MongoDB confirmed

## 6. INTEGRATIONS
- ✅ Google Sheet 1-way append active (Service Account, Editor) — incl. Insurance Register
- ⬜ Confirm whether 2-way / update-in-place sync is required (currently append-only by design — never overwrites formulas/helper columns)
- ⬜ Service Account JSON present in production env

## 7. UI / UX
- ✅ Registers, drawer tabs, receipt modals, reports render
- ✅ Per-lead Insurance tab: 49%/36.5% auto-fill (parity with standalone page)
- ⬜ Mobile/tablet usability for showroom floor (optional PWA)

## 8. DEPLOYMENT
- ✅ Env-driven config (REACT_APP_BACKEND_URL, MONGO_URL, DB_NAME)
- ⬜ **Redeploy preview → production** so latest logic reaches euler-connect.emergent.host
- ⬜ Smoke test on production: login (both roles), open a lead, dashboard, one report, /share
- ⬜ Production data check: correct baseline / migrated data present
- ⬜ Rollback point noted before switch-over

## 9. FINAL GO/NO-GO
- **All code parity gaps CLOSED** (C1/H1/H3/H4/H5/INS-1/U4/U1). ERP Production Audit: 96/100, 0 Critical, 0 High, 0 blockers.
- **Remaining before "GO LIVE" (≥99%):** operational only — production redeploy + production smoke test (§8), optional password-reset policy (§4), confirm append-only sync is acceptable (§6).
- **Recommended:** proceed to supervised production pilot; complete §8 redeploy + smoke test to reach the ≥99% GO-LIVE threshold.

**Sign-off:** Owner ____ · Accounts ____ · IT ____ · Date ____
