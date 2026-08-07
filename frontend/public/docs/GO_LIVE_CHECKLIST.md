# GO_LIVE_CHECKLIST — Euler CRM

Every item must be **PASS** before switching real dealership staff to production. Status: ✅ done · ⚠ open · ⬜ verify-before-launch.
_Version 2.2 · 2026-06 · Overall readiness 84/100_

## 1. BUSINESS LOGIC PARITY
- ✅ Commercial totals (GVC, TCS, payable, outstanding) match source
- ✅ Dealer margin (4% net 5% GST)
- ✅ Scheme company-share-first split + model/variant aliases
- ✅ Scheme availability + caps per model/variant/month
- ✅ Benefit modes (Full/Partial/No) + per-component breakup
- ✅ Insurance payout rate (49% / 36.5%) + expected payout
- ✅ Finance liability shift customer→financer
- ✅ OEM claim = company share; per-component receipts + history
- ⚠ **C1** Dealer Earnings extra-income lines (Documentation/Warranty/RSA/Referral) — build before relying on earnings totals
- ⚠ **H5** RSA/AMC charge input field

## 2. WORKFLOW & VALIDATION
- ✅ Step-eligibility gating (no repeating Booking/Delivery/Close)
- ✅ Duplicate mobile block
- ✅ Payment over-cap guard (≤ Customer Payable)
- ✅ Delivery checklist + cleared outstanding
- ✅ Close reason (+ RC/plate for delivered)
- ⚠ **M1/U4** Concurrency: guard rapid double-submit (idempotency) — verify

## 3. REPORTS & DASHBOARD
- ✅ Owner Commercial, OEM Claim Dashboard, Claim Exceptions
- ✅ Dealer Earnings / Payout report / Share board
- ⚠ **H1** Dashboard KPIs: conversion %, MTD revenue, follow-ups, finance outstanding
- ⚠ **H3** Claim submitted/approved dates + ageing

## 4. PERMISSIONS & SECURITY
- ✅ Owner vs Executive enforced (front + back, 403 on owner routes)
- ✅ JWT auth; env-only secrets; no hardcoded keys
- ⚠ **H4** Audit/transaction log (who/what/when) for finance-sensitive edits — **required for a money system**
- ⬜ Password reset / lockout policy (confirm requirement)
- ⬜ Confirm role granularity needs (Reception/Sales/TL/GM/Accounts) or keep Owner/Executive

## 5. DATA INTEGRITY
- ✅ Baseline preserved (10 real leads); no accidental reseed
- ✅ All money rounded via one helper; ISO/UTC datetimes
- ⬜ **U1** Full priced+scheme+delivered deal reconciled end-to-end vs hand calc
- ⬜ DB indexes on leadId/mobile/currentStatus/bookingDate (scale)
- ⬜ Backup/restore plan for MongoDB confirmed

## 6. INTEGRATIONS
- ✅ Google Sheet 1-way append active (Service Account, Editor)
- ⬜ Confirm whether 2-way / update-in-place sync is required (currently append-only)
- ⬜ Service Account JSON present in production env

## 7. UI / UX
- ✅ Registers, drawer tabs, receipt modals, reports render
- ⬜ Per-lead Insurance tab: add 49%/36.5% auto-fill (parity with standalone page)
- ⬜ Mobile/tablet usability for showroom floor (optional PWA)

## 8. DEPLOYMENT
- ✅ Env-driven config (REACT_APP_BACKEND_URL, MONGO_URL, DB_NAME)
- ⬜ **Redeploy preview → production** so latest logic reaches euler-connect.emergent.host
- ⬜ Smoke test on production: login (both roles), open a lead, dashboard, one report, /share
- ⬜ Production data check: correct baseline / migrated data present
- ⬜ Rollback point noted before switch-over

## 9. FINAL GO/NO-GO
- **NO-GO for "100% identical"** until §1 C1/H5, §3 H1/H3, §4 H4 close and §5 U1 + §2 U4 pass.
- **Conditional GO for supervised pilot:** money math verified; owner supervises finance/claim reconciliation; do not rely on Dealer Earnings totals until C1 lands.

**Sign-off:** Owner ____ · Accounts ____ · IT ____ · Date ____
