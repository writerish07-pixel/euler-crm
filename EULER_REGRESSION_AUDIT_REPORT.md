# Euler CRM — regression audit report

Audit date: 18 Nov 2026. Baseline before repairs: `adef670` (`origin/main`).

Method: pull-request metadata for all 292 GitHub pull requests, code read of the commercial engine, auth roles, and OEM cancel/rebill path, then an in-process pytest batch. Production MongoDB was not queried. The live website was not clicked.

## Findings

### AUD-001 — R2 HIGH — Confirmed defect — OEM cancel treated as a rebill

A pack unit whose invoice is CANCELLED stayed on the lead when `oem_sold` still contained that same invoice. `delink_cancelled_sold_invoices` subtracted every Sold chassis from the cancel set, so a stale Sold copy of the cancelled bill blocked the clear.

Intended behaviour, from the function's own comment and from pull requests 198, 259, and 266: clear a cancelled bill; keep a chassis only when Sold has a different, new invoice.

Evidence: `tests/test_oem_billing.py::test_invoice_list_cancel_drops_pack_unit_even_if_sold_still_lists_it` failed with `cleared == 0` before the repair. The rebill tests (`test_delink_and_stamp_keep_rebilled_chassis_on_the_lead`, `test_staff_delivered_rebill_replaces_cancelled_pack_chassis`) still require the new-invoice case to stay.

Affected: OEM Billing, lead chassis list, pack unit count. Not a customer-payable formula change.

Status: repaired in this branch. See the repair register.

### AUD-002 — Historical requirement conflict — stale catalog test, not a price change

`test_apply_catalog_renames_and_drops` still expected RTO and insurance of 0 on new OEM SKUs. Current `apply_catalog` fills `default_rto_insurance_for_model` on insert and refuses to overwrite a later manual amount. The later tests in `test_rto_insurance_deal_approval.py` require HiLoad ₹5,500 / ₹10,000 and Storm/Turbo ₹5,500 / ₹19,000, and those tests passed.

The price rule that stands is the later default. The assertion was updated to that rule. Price Master values were not changed.

### AUD-003 — R3 — External check — Cloudflare Workers Builds fail instantly

On recent pull requests the Workers check starts and finishes in the same second with zero annotations, while `.github/workflows/cloudflare-validate.yml` (wrangler dry-run) succeeds. This audit did not treat that as an application defect and did not change deploy config.

### AUD-004 — Stale document, not a current defect

`EULER_PRODUCTION_AUDIT.md` (June 2026) still lists missing dealer-income lines, missing dashboard KPIs, and no audit log. Later code has `documentationIncome` / warranty / RSA / referral fields, dashboard follow-up and finance outstanding KPIs, and `audit_log`. Those June items were not re-opened. The June file was not rewritten, so it does not describe `main` today.

### AUD-005 — Unable to verify in this session

- Live HTTP tests that require `REACT_APP_BACKEND_URL`: `test_auth_and_iter2.py`, `test_iter8_step_gating_and_scheme.py`, `test_iter9_scheme_avail_delivery_close_dupmobile.py`, `test_iter15_lead_partial_update.py`. Collection fails without that variable. No local API was started. Status: not tested.
- The other 101 test files outside the critical batch. Status: not tested this session.
- Production lead, payment, and chassis rows. Status: not tested. No production credentials were used.
- Browser walkthrough of lead, booking, payment, and OEM Billing screens. Status: not tested.

### AUD-006 — R4 — Open pull request, not a regression on main

Pull request 161 (Android and iOS) is open. Pull request 32 is closed. Neither is on `main`. No change was made to them.

## Counts from this audit only

| Class | Count | Ids |
|---|---|---|
| Confirmed defect repaired | 1 | AUD-001 |
| Historical test conflict corrected without a price change | 1 | AUD-002 |
| External check, not changed | 1 | AUD-003 |
| Stale audit document | 1 | AUD-004 |
| Not tested / blocked | the live-HTTP files, the rest of the suite, production data, the browser | AUD-005 |

No R1 financial-calculation defect was reproduced in the tests that ran. That is not a proof that every live deal is correct.

## Severity rollup used in the final report

- Critical (R1): 0 confirmed in the executed tests.
- High (R2): 1 confirmed (AUD-001), repaired on this branch.
- Medium (R3): 1 external (AUD-003), not repaired.
- Low (R4): 1 open Android pull request, not on main (AUD-006).
