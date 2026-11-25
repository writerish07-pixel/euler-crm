# Business Logic Verification (Claude independent reconstruction)

Sources used: current code on `main` (`fbb0e21`), PR titles/commit messages across 752 commits, existing tests, Cursor's baseline (as a reference only), and Claude's in-process probes (real FastAPI app, in-memory MongoDB, no production data).

Verdict key: **VERIFIED** (executed by Claude and observed), **CODE** (read, consistent, not executed), **DEFECT** (see findings ID), **UNVERIFIED** (could not be established), **DECISION** (code and documents disagree; owner must decide).

## 1. Lead management

| Rule | Source | Verdict | Notes |
|---|---|---|---|
| Lead create mints a unique `LD26…` id atomically | `next_id` `$inc` | VERIFIED | 3 concurrent identical creates → 1 lead |
| Duplicate 10-digit mobile blocked unless "another vehicle" confirmed | PR #163/#171, `server.py` ~5142 | CODE | Not re-probed beyond concurrency |
| Different mobile = different customer even with same name | PR #286 | CODE | Contradicted by the background purge, which groups **by name when mobile is blank** |
| Executives see only their own leads | PR #79, `_require_lead_visible` | VERIFIED | 403 on another executive's lead; 14 list endpoints checked |
| `PUT /leads/{id}` is a partial update | PR #3 | CODE | Covered by `test_iter15_lead_partial_update.py` (live-HTTP; not runnable here) |
| Lead history (activities, documents) is preserved | implied | **DEFECT CLD-01** | `GET /api/leads` deletes "duplicate" open leads with history and KYC |
| Lead approval queue (exec leads held for GM/Owner) | PR #95 | CODE | `approve_lead_request` checks `_can_approve_leads` |
| Lead allocation / split for bulk uploads | PR #79, #96 | CODE | `sales_gm_only` dependency |
| Status transitions: cancel, revive, close won | PR #72–#74, #45–#46 | CODE | Covered by full suite (see test report) |

## 2. Booking

| Rule | Verdict | Evidence |
|---|---|---|
| Booking loads Price Master automatically | **VERIFIED** | Turbo Max Maxx (PV) and Hi-Load SR (FB120) booked without any manual price save; ex-showroom, RTO, insurance and payable populated |
| Executive booking (with KYC) populates Price Master | **VERIFIED** | Executive-posted bookings: Turbo ₹7,85,000, Hi-Load ₹4,21,156; executive booking without Aadhaar/PAN → 422. A back-dated Turbo booking (9 Aug, before the overlay) was parked as a "dealer discount" deal for approval — observation only |
| Booking refused when no Price Master row | **VERIFIED** | Unknown variant → HTTP 422 with clear message; lead stays "New" with zero amounts |
| Booked price locked against later Price Master edits | **VERIFIED** | Price Master +₹10,000 after booking → lead unchanged (₹7,85,000) |
| Booking advance becomes a receipt | VERIFIED | `totalReceived` = ₹1,000 immediately after booking with ₹1,000 advance |
| Turbo +₹15,000 dealer overlay from 1 Sep 2026 | **VERIFIED, with caveat CLD-11** | Lead ₹7,85,000 vs Price Master ₹7,70,000; overlay disappears once the row is Coulson-synced; boot job may apply it to open leads |
| VIN/chassis allocation unique across live leads | VERIFIED (single process) | Second lead with same chassis → 409 sequentially and concurrently; no DB unique index (CLD-12) |
| Booking cancellation / refunds | CODE | Phase-1 pack-refund defect is fixed (`_refund_position` uses `_receipt_payable`) |

**Previously reported issue — "Price Master values not automatically populated during booking":** on the backend, the underlying problem is **resolved** for the paths Claude could execute (`POST /leads` → `POST /leads/{id}/convert-booking`, both as owner and as an executive with KYC attached). The test that appears to show the opposite (`test_scheme_retained_and_step_locks.py::test_booking_autofill_does_not_lock_price_for_staff`) fails only because it does not attach the KYC now required and never checks the booking's status code. The frontend booking drawer (`BookEnquiryDrawer.js`) has 1 Jest suite passing; a browser walk-through was not possible (no running backend with production-like data), so the UI half is **UNVERIFIED in a browser**.

## 3. Price Master

| Rule | Verdict | Notes |
|---|---|---|
| Family defaults RTO ₹5,500; insurance ₹19,000 (Storm/Turbo), ₹10,000 (HiLoad/HiRange/HiCity) for new rows | CODE + tests pass | `default_rto_insurance_for_model`; observed in probe rows |
| Catalog apply does not overwrite a typed RTO/insurance | CODE + tests | PR #289 |
| Price change by owner only | CODE | `POST /price-master` `owner_only` |
| Variant mapping from OEM exact SKU, no guessing | CODE + tests | PR #288/#290/#292 tests pass in critical suite |

## 4. Quotation

`POST /quotations` (`sales_staff_only`) uses the same `compute_full_commercials`. Not separately probed. External quotation application integration: **none found** in the repository beyond the internal quotation endpoint and PDF deal sheet. UNVERIFIED.

## 5. Payments and outstanding

| Rule | Verdict | Evidence |
|---|---|---|
| Multiple / partial payments persist | **VERIFIED** | Booking advance + ₹20,000 cash + ₹30,000 UPI → 3 rows, `totalReceived` ₹51,000 = Σ rows |
| Outstanding = payable − received | **VERIFIED** | ₹8,09,500 − ₹51,000 = ₹7,58,500 |
| Over-payment refused unless confirmed as excess | **VERIFIED** | Concurrent 60%+60% → 200 and 422 |
| Duplicate receipt within 4 s refused | **VERIFIED** | 3 parallel identical → 200, 409, 409; 1 row saved |
| Non-cash receipt needs a reference/UTR | CODE | `_payment_ref_required` |
| Frontend never auto-retries customer receipts | CODE | `CREATE_ONCE_LEAD_ACTIONS` |
| Owner can delete a receipt; totals rebuilt | Tests pass (`test_owner_payment_delete.py`) | |
| Financer receipt does not change customer outstanding; dedupe window | CODE | `record_financer_receipt` |
| **OEM claim receipts** protected the same way | **DEFECT CLD-06** | Duplicate and over-eligible receipts accepted; auto-retried by frontend |
| Who may post customer receipts | **DEFECT CLD-13** | Code allows Sales GM; two existing tests and the baseline say 403; side effect of `070836e` (27 Sep) |

Previously reported payment-saving and persistence failures: **not reproduced**. In every probe the API response, the `payments` rows and the lead totals agreed.

## 6. Schemes and incentives

| Rule | Verdict |
|---|---|
| Scheme month = billed date, else explicit date, else booking date, else today (IST) | CODE (`compute_scheme_allocation` uses `schemeAsOf` then `bookingDate`; per-unit `soldDate` in server) |
| No carry-forward of last month's scheme | CODE + Oct/Nov tests pass |
| Eligibility ≠ assignment (explicit allocation) | CODE + `test_scheme_allocation_engine.py` passes |
| Legacy default passes eligible scheme automatically | **Observed** | A November Storm unit's payable included ₹35,000 of scheme before anyone allocated it; an explicit empty allocation removed it (date-dependent failure in `test_same_order_multi_unit.py`). Payable therefore changes when the desk first saves the scheme — owner to confirm intended default |
| Company share applied first to the passed amount | CODE: `oem_passed = min(oemShare, customerBenefit)` |
| Unused component: no OEM claim, no retained income | CODE: `used=False` zeroes `oemClaimable` and `dealerRetained` (PR #33) |
| Effective dates honoured | CODE: `effectiveFrom/To` checked in `get_scheme_shares_for_lead` |
| Executive incentive slabs | Full-suite tests (see test report) |

## 7. Dealer earnings engine — customer vs dealer separation

Formula on `main` (`recompute_lead`):

`dealerTotalEarnings = marginNetExGst + schemeRetained + OEMExtraRetained (unless unpayable) + extraIncome (documentation, warranty, RSA, referral, other, finance incentive, accessories margin, exchange margin, campaign) + insurancePayout + extraFromCustomer − dealerFundedBenefit − OEM unpayable scheme`

| Check | Verdict |
|---|---|
| Benefit passed to customer is **not** counted as dealer-retained | **CODE-VERIFIED**: `dealerRetained = oemShare − min(oemShare, customerBenefit)` per component |
| OEM claim receivable never enters earnings | CODE (comment and formula) |
| Insurance payout is a separate ledger from insurance benefit | CODE |
| Additional (dealer) discount is a dealer cost | CODE — deducted only when the lead has `schemeAllocationV2`/explicit allocation; legacy leads are not charged. Probe could not set Additional through `PUT /price-structure` (it is set on the deal desk), so the end-to-end deduction is **UNVERIFIED** |
| Dealer margin 4% + GST | **DECISION CLD-16** (GST removed twice) |
| Report total equals lead total | CODE — same terms; computed twice independently |
| Executives cannot see earnings | Endpoint 403 VERIFIED; payload leak **CLD-09** |

## 8. OEM billing, inventory, VIN

| Rule | Verdict |
|---|---|
| One chassis = one billed SKU; no sibling relabel | Tests pass |
| Cancelled invoice removed; rebill kept | **DEFECT CLD-05** on `main` (rebill on Invoice List ignored; blank-invoice Sold rows cleared) |
| Staff-delivered files flagged, not un-delivered, when Sold drops a chassis | CODE + tests |
| Inventory ledgers hidden from executive/TL | CODE (`INVENTORY_LEDGER_HIDDEN_ROLES`) |

## 9. Other modules present

Insurance (agents, slabs, MIS upload), finance files, exchange, accessories (charge lines), claims register and OEM settlements, Tally billing summary and pack checker, WhatsApp (BotSpace), Exotel calls, Google Sheets one-way sync, workshop/service desk with Gmail, KYC documents with compression, staff/users/roles, dashboards (owner, GM, executive, field, accounts), audit log, edit log, settings. These are exercised by the full backend suite (results in `CLAUDE_TEST_COVERAGE_AND_GAPS.md`); Claude did not reconstruct each module rule by rule. Warranty and RSA exist only as charge lines and dealer-income fields, not as separate modules.

## 10. Combined-module effects found

- **Lead register (read) × duplicate prevention** → deletion of genuine leads (CLD-01).
- **OEM sync × cancel repair** → rebilled chassis cleared (CLD-05).
- **Frontend retry policy × claim receipt endpoint** → double-counted OEM receivables (CLD-06).
- **Admin reset × KYC storage** → new customer sees old documents (CLD-10).
- **Boot maintenance × Price Master sync flag** → payable changes on restart (CLD-11).
