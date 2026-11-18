# Euler CRM — audit repair register

Branch: `cursor/crm-enterprise-audit-996c`, cut from `origin/main` at `adef670eb4e4b5890c8147d6204156226df9b84e`.

No production database was written. No deploy was triggered. No pull request was merged or closed by this audit.

## AUD-001 — Cancelled invoice still listed in Sold

| | |
|---|---|
| Severity | R2 |
| Module | OEM billing / lead chassis |
| Original behaviour | A CANCELLED invoice is removed from the lead. A chassis on Sold under a different invoice is a rebill and stays. |
| Incorrect behaviour | Any Sold row for the chassis suppressed the cancel, including a Sold row that still carried the cancelled invoice number. `test_invoice_list_cancel_drops_pack_unit_even_if_sold_still_lists_it` returned `cleared == 0`. |
| Historical reference | Pull requests 198, 259, 266. Test name and docstring in `tests/test_oem_billing.py`. |
| Root cause | `cancelled_only = cancelled_chassis_set - sold_chassis_set` ignored invoice identity. |
| Correction | `cancelled_chassis_without_live_rebill` keeps a chassis only when Sold has an invoice that is not the cancelled one. Stale Sold rows of the cancelled invoice are deleted. |
| Files | `backend/oem_sync.py`, `backend/tests/test_oem_billing.py` |
| Dependencies | Rebill path, staff-delivered missing-sold flag, pack unit drop. |
| Tests executed | The new helper test; the previously failing pack-cancel test; `test_staff_delivered_rebill_replaces_cancelled_pack_chassis`; `test_oem_sold_cancel_delinks_auto_delivered_then_restamps`; `test_staff_delivered_missing_sold_is_flagged_not_cleared`; `test_delink_and_stamp_keep_rebilled_chassis_on_the_lead`; `test_replace_cancelled_keeps_rebilled_chassis_on_sold`. |
| Result | 7 passed. Follow-up: a Created invoice list row is also a rebill when Sold still shows the cancelled bill. That chassis stays, and the Sold row is moved to the Created invoice. |
| Status | Repaired on this branch. Not deployed. |

## AUD-002 — Catalog test still expected blank RTO

| | |
|---|---|
| Severity | Test drift, not a price change |
| Module | Price Master catalog apply |
| Original later rule | New catalog rows receive family RTO/insurance. Existing manual amounts are not overwritten. |
| Incorrect test | `test_apply_catalog_renames_and_drops` expected 0. Actual Hi-Load SR (FB120) RTO was 5500. |
| Correction | Assertion updated to ₹5,500 / ₹10,000 for that Hi-Load row and ₹5,500 / ₹19,000 for Turbo City (Tipper). No catalog amount was edited. |
| Files | `backend/tests/test_coulson_oem_inventory.py` |
| Tests executed | `test_apply_catalog_renames_and_drops` after the edit. |
| Result | 1 passed. |
| Status | Test aligned. Business numbers unchanged. |

## Not repaired

| Id | Why left |
|---|---|
| AUD-003 | Cloudflare Workers instant failure is outside this repo's workflow. Wrangler dry-run remains the inspectable check. |
| AUD-004 | June audit file left as a historical record. |
| AUD-005 | No evidence of a wrong business result. Not tested is not a licence to change the rule. |
| AUD-006 | Open Android pull request. Out of scope. Not closed. |
