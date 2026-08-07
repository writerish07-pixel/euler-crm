# ERP_PARITY_SPEC — Euler CRM Business Specification (The Contract)
**Purpose:** the authoritative statement of *what the system must do*, independent of implementation. If the app and this spec disagree, one of them is a defect. Source of truth = original spreadsheet + Apps Script (`final fix/*.gs`).
_Version 2.2 · 2026-06_

---

## 1. SCOPE & ACTORS
- **Actors/roles:** Owner (full access incl. earnings, reports, settings), Executive (operational; no earnings/owner reports/settings).
- **Domain:** single Tata/Euler EV dealership; leads → bookings → delivery; commercial settlement with OEM; finance, insurance, claims.

## 2. CORE ENTITIES
Lead, Booking, Payment, Finance File, Insurance Entry, OEM Claim, Delivery, Activity, Price Master, Scheme Master, Incentive Master, User.

## 3. LIFECYCLE (MANDATORY SEQUENCE)
New Lead → Convert to Booking → Price Structure → Scheme Update → Add Payment → Finance/Claims/Insurance → Mark Delivered → Close Lead.
- A one-time step (Booking, Delivery, Close) must not be repeatable.
- Data steps (Price/Scheme/Payment) editable while the account is Active.

## 4. BUSINESS RULES (NORMATIVE — "MUST")
**Leads**
- R1 Mobile must be a unique 10-digit number; duplicates rejected.
- R2 Lead must have customer name; model/variant from Price Master.

**Booking**
- R3 Booking allowed only when Active and not already Booked/Delivered.
- R4 Booking may be created before pricing (slim/provisional booking); advance recorded as a receipt.

**Price Structure**
- R5 Editable only while Active.
- R6 Customer Payable recomputes immediately on any charge/discount change.

**Scheme**
- R7 Editable only while Active.
- R8 Only scheme components present in Scheme Master for the lead's model/variant/effective-month may be entered; others must be 0/hidden.
- R9 Each component amount must not exceed its Scheme Master total (cap).
- R10 OEM claimable = OEM **company share** (company-share-first cap), never the raw offer amount.
- R11 Benefit modes: Full (pass all), Partial (per-component passed amounts), No Benefit (pass nothing).
- R12 DSA is approval-required to be claimable; on a booked deal treated approved unless rejected.

**Payments**
- R13 Amount > 0.
- R14 Total received must not exceed Customer Payable; provisional receipts allowed only while payable = 0.
- R15 A Finance-mode entry shifts outstanding from customer to financer (customer no longer liable for that amount); financer becomes liable via a finance file.

**Finance**
- R16 A finance file accrues a **committed** amount (from Finance-mode entries) and a separate **disbursed** amount (from financer receipts). File outstanding = committed − disbursed.
- R17 Recording a financer receipt must not change customer outstanding.

**Insurance**
- R18 Insurer payout rate: Storm/Turbo = 49% of premium, all other models = 36.5% (suggested default; manual override allowed).
- R19 Expected Payout = Premium × Rate; Outstanding = Expected − Received; entries reference delivered leads.

**Claims (OEM)**
- R20 Claims are per scheme component at company-share value.
- R21 Receipts accrue received amount with a full history; status Pending→Partial→Received.

**Delivery**
- R22 Mark Delivered requires: Insurance=Yes + Insurer, Registration=Yes, Invoice=Yes + Invoice No., Chassis No., PDI=Yes, and **customer outstanding = 0**.
- R23 A delivered lead cannot be re-delivered; paperwork remains editable.

**Close**
- R24 Close requires a reason.
- R25 Closing a delivered lead additionally requires RC = Done + Number Plate.
- R26 Finance receipts allowed even after close (until Archived).

**Reports & permissions**
- R27 Dealer Earnings, Owner Commercial, OEM Claim Dashboard, Claim Exceptions, Payout Report are Owner-only.
- R28 Public Share board shows Active Bookings, Retail MTD, New, Today.

## 5. COMMERCIAL DEFINITIONS (NORMATIVE)
- Gross Vehicle Cost = ex-showroom + accessories + insurance + RTO + FASTag + handling + TRC + extended warranty + RSA/AMC + other charges.
- TCS = 1% × GVC when applicable.
- Customer Payable = GVC + TCS − benefit passed − exchange adjustment.
- Dealer Margin (net) = (4% × ex-showroom) ÷ 1.05.
- Scheme Retained = Σ over components of (company share kept − dealer share given).
- OEM Extra Support kept = received − passed.
- **Total Dealer Earnings** = Dealer Margin + Scheme Retained + Insurance Income + OEM Extra Support kept + Documentation + Warranty + RSA + Referral income.

## 6. NON-FUNCTIONAL
- All monetary values rounded to 2 decimals via one helper; datetimes ISO/UTC.
- Config from environment only; no hardcoded secrets.
- Every finance-sensitive mutation is auditable (who/what/when/old/new/IP) — **implemented** via append-only `audit_log` + owner-only `/audit-log` viewer.

## 7. ACCEPTANCE
The system is spec-compliant only when every rule R1–R28 and every definition in §5 is implemented and proven by the regression suite (`TEST_CASES.md`) and the go-live checklist (`GO_LIVE_CHECKLIST.md`).
