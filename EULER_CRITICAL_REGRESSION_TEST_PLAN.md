# Euler CRM — critical regression test plan

## Suite

Workflow: `.github/workflows/critical-regression.yml`.

It runs on push to `main` and `cursor/**`, and on pull requests. It does not deploy. It does not replace `cloudflare-validate.yml`.

In-process pytest (mongomock). These files:

1. `tests/test_iter21_golive_lifecycle.py` — lead, book, price, scheme, pay, finance, deliver, claim, earnings, close. The four money ledgers stay separate.
2. `tests/test_scheme_allocation_engine.py` — eligibility versus assignment, company-share-first.
3. `tests/test_oct_2026_schemes.py` — October circular and no September leak.
4. `tests/test_nov_2026_schemes.py` — November circular by billed date.
5. `tests/test_deal_pass_meet_cx.py` — Cx Demand versus payable.
6. `tests/test_rto_insurance_deal_approval.py` — family RTO/insurance defaults and typed amounts.
7. `tests/test_owner_payment_delete.py` — receipt delete.
8. `tests/test_excess_refund_and_finance_dedupe.py` — excess refund and finance double-post.
9. `tests/test_oem_billing.py` — Sold match, cancel versus rebill, variant not guessed.
10. `tests/test_coulson_oem_inventory.py` — catalog apply, rebill keeps the new invoice.

A test passes only when the asserted amount, status, or chassis list matches. HTTP 200 alone is not the check inside these files.

## This audit's execution

Command (backend directory), before the catalog assertion edit:

`python3 -m pytest` on the ten files above.

Result: 250 passed, 1 failed (`test_apply_catalog_renames_and_drops`, RTO 5500 versus expected 0).

After AUD-001 (already included in that run) the cancel/rebill tests were green, including `test_invoice_list_cancel_drops_pack_unit_even_if_sold_still_lists_it`.

After AUD-002, `test_apply_catalog_renames_and_drops` was re-run alone: 1 passed.

The ten files were not re-run as one process after AUD-002. The only edit after the 250-pass run was that assertion.

## Deliberately outside this workflow

Live HTTP tests (`test_auth_and_iter2.py`, iteration 8, iteration 9, iteration 15) need a running API and `REACT_APP_BACKEND_URL`. They are not part of CI until a disposable API is provided. They were not executed.

The other test files under `backend/tests/` (111 files total in the tree) are still valuable. They are not all in the critical job, so a green critical job does not mean the whole tree was run.

## Branch protection

This audit did not change GitHub branch protection. An administrator can require the "Critical regression" check on `main`. Until that is set, a red run is visible but not a hard block.
