# Euler CRM — master functional baseline

Audit date: 18 Nov 2026 (Asia/Calcutta). Baseline commit: `adef670eb4e4b5890c8147d6204156226df9b84e` (`origin/main`, merge of pull request 292).

This document reconstructs approved behaviour from the current `main` code, pull-request titles, and the tests that still pass. It is not a claim that every screen was clicked on production. A June 2026 parity note in `EULER_PRODUCTION_AUDIT.md` is historical. Later pull requests closed several items it still lists as open.

Coverage limit: business rules below were read in `backend/commercial.py`, `backend/auth.py`, `backend/oem_sync.py`, `backend/scheme_circulars.py`, and the test modules named in `EULER_CRITICAL_REGRESSION_TEST_PLAN.md`. `backend/server.py` is about 20,000 lines. It was not re-read line by line in this audit.

## Commercial engine

Purpose: one calculation for what the customer pays, what the OEM owes the dealer, and what the dealer keeps.

Approved rules, from `commercial.py` and `tests/test_iter21_golive_lifecycle.py`:

- Gross vehicle cost sums ex-showroom, accessories, insurance, RTO, FASTag, handling, TRC, extended warranty, RSA/AMC, and other charges (`CHARGE_KEYS`).
- TCS is 1 percent. The threshold constant is ₹10,00,000 (`TCS_RATE`, `TCS_THRESHOLD`).
- Dealer margin rate is 4 percent plus 5 percent GST on that margin.
- Customer payable, customer outstanding, company outstanding (OEM claim), finance outstanding, and dealer earnings are separate amounts. Dealer earnings do not reduce what the customer owes.
- Scheme Master is eligibility. A component is used only when the deal assigns it. Use Scheme = No opts out. Company share is applied before dealer share. Customer benefit reduces payable. Dealer-retained is the company share kept. Dealer-funded benefit is the dealer share given. Additional (Dealer) is not an OEM discount.
- Insurance payout (premium times rate) is a separate ledger from the scheme. Suggested rates in the June port were Storm/Turbo 49 percent and other models 36.5 percent. Later MIS upload can replace the expected payout with the MIS amount (pull requests 119, 129, 130).
- Family RTO and insurance defaults, used when a new Price Master row is created: RTO ₹5,500 for Storm, Turbo, HiLoad, HiRange, and HiCity. Insurance ₹19,000 for Storm and Turbo, ₹10,000 for the three-wheelers (`default_rto_insurance_for_model`). A later manual RTO or insurance on an existing row is not overwritten by catalog apply.

Verification: `test_iter21_golive_lifecycle.py`, `test_scheme_allocation_engine.py`, `test_rto_insurance_deal_approval.py`, and `test_deal_pass_meet_cx.py` passed in this audit.

## Scheme months

Purpose: the circular for the month the vehicle was billed, not last month carried forward.

- September, October, and November 2026 circulars are upserted on boot (`sept_2026_schemes.py`, `oct_2026_schemes.py`, `nov_2026_schemes.py`).
- The scheme date is the unit sold/billed date, then an explicit date, then the booking date.
- October and November: HiLoad and HiCity get insurance up to ₹10,000 and loyalty ₹10,000. Storm gets consumer ₹25,000 and loyalty ₹10,000. Turbo is not on those circulars. Loyalty is noted as existing-customer only, max 5 percent of retails.
- November reference is EM/11-2026/001, 1–30 Nov 2026. October is EM/10-2026/003.
- A confirmed owner answer on a chassis is not a scheme rule. It is recorded under OEM variant confirmation below.

Verification: `test_oct_2026_schemes.py` and `test_nov_2026_schemes.py` passed.

## Leads, booking, and price

Purpose: one customer file from enquiry through booking, price, scheme, payment, delivery, and close.

Approved behaviour reconstructed from pull requests 3, 11–13, 78–79, 95, 163, 171–175, 188, 210, 239, 286–289 and the current guards:

- `PUT /leads/{id}` is a partial update (pull request 3). A full-document replace was a data-loss defect and was rejected.
- Booking must load Price Master. An empty commercial booking is refused (pull requests 11–13).
- Duplicate 10-digit mobile on create is blocked, except where a later rule allows another vehicle: same mobile with a different chassis is a second file or a pack unit after confirmation (pull requests 163, 171). A different 10-digit mobile is a different customer even when the name matches (pull request 286).
- Same-order packs keep one lead id and per-unit price, scheme, Cx Demand, documents, payments, and delivery dates (pull requests 171–178, 248–252).
- Executives book and collect. Scheme and price decisions sit with Owner, Sales GM, Showroom Admin, and Team Leader (`DEAL_DESK_ROLES`). Deals with no discount can auto-approve (pull request 188). Discounted deals stay off the staff register until approved (pull request 222).
- Typed RTO, insurance, and GSTIN are kept when OEM billing fills a missing ex-showroom (pull request 289). A saved zero is a saved zero.
- Pack header totals (customer payable, Cx Demand, budget, gross vehicle cost) are order totals and are not copied onto unit 1 as that unit's price.

Verification of the full create-to-close path: `test_iter21_golive_lifecycle.py` passed in-process. The older live-HTTP iteration 8 and 9 tests were not run (no server). Status for those two files: not tested this audit.

## OEM billing, chassis, and variant

Purpose: write the body Coulson billed on that chassis. Do not guess from a sibling.

- One chassis, one billed SKU. `updatedLoadBody` is the billed body. A sibling DV does not relabel an FB or PV invoice (pull requests 288, 290).
- If the invoice does not name exactly one catalog variant, the file is queued for the owner. Nothing is guessed.
- Once the owner or Showroom Admin confirms a variant, that chassis leaves the dashboard queue, the lead card, and the OEM Billing "Confirm variant" line. The next sync does not ask again (pull request 292).
- A cancelled invoice is removed from the lead even when the Sold cache still holds that same invoice. A chassis that is on Sold under a different invoice is a rebill and stays (pull requests 198, 259, 266, and repair AUD-001 in this audit).
- Staff-completed Delivered or Close Won files are not auto-un-delivered when a chassis merely disappears from Sold. They are flagged `oemInvoiceMissing` unless a replacement for the same customer is already on Sold.
- Unnamed invoices and a different model family are not written. The owner confirms them.

Verification: OEM billing and Coulson inventory tests in the critical run, including the previously failing cancel test after AUD-001. Passed.

## Payments and outstanding

- A receipt above customer payable is rejected, except a provisional receipt while payable is still zero.
- Identical receipt (same lead, amount, mode) inside 4 seconds returns 409.
- Owner can delete a payment (pull request 60). Each receipt can carry a UTR (pull request 162).
- Excess receipts are refundable. Financer receipts are not posted twice (pull request 55).
- Finance-mode payment moves outstanding from customer to financer. The financer's later disbursement does not change customer outstanding again.

Verification: `test_owner_payment_delete.py` and `test_excess_refund_and_finance_dedupe.py` passed. Production payment rows were not read.

## Roles

From `backend/auth.py` `ALLOWED_ROLES`:

| Role value | Who |
|---|---|
| owner | Full desk, dealer earnings, price master, user passwords |
| sales_gm | Showroom sales, approvals, no cash posting |
| tl | Showroom Admin (whole showroom), deal desk |
| team_lead | Team-scoped leader, executive navigation plus deal steps |
| executive | Own leads, book and collect, no scheme edit |
| accounts | Money desk, receipts, Tally |
| asm, rm | Field dashboards, read-only finance register |
| oem_finance | External. Denied every route except the OEM finance allow-list |

Dealer earnings and owner commercial reports are owner-only.

Verification: role constants read. `test_iter34_roles.py` and `test_role_smoke.py` were not in the critical run. Status: rules read, those two files not executed this audit.

## Other modules present

These exist on `main` and were identified from routes and pull-request titles. They were not each re-executed in this audit.

- Inventory and yard: chassis from 1 Sep 2026, motor and battery numbers, need-to-order scoped to the executive (pull requests 80, 93, 260, 261).
- Claims: scheme claim register is permanent, OEM debit notes match by chassis and invoice, extra support is its own claim (pull requests 35–37, 107–113, 120).
- Insurance MIS upload replaces mapped expected payout (pull requests 119–130).
- WhatsApp via BotSpace, Exotel amount-verify calls, Google review call (pull requests 57, 217–226, 268).
- Google Sheets sync is one-way and claims-aware. Tests must not write the live sheet (`test_pytest_blocks_sheet_writes.py` exists; not run in this critical batch).
- Workshop / service desk and Gmail request matching (pull requests 279–285).
- Documents: KYC, deal sheet PDF, compressed uploads (pull requests 194, 273).
- Tally billing summary invoices the vehicle, then discount, then GST (pull requests 200–202, 208).

## Explicit non-goals already decided

- AI Agents desk was added (203) and removed (205). It is not approved current behaviour.
- Native Android/iOS pull request 161 is still open. The live product on `main` is the web app.
- Last month's scheme does not carry forward.
