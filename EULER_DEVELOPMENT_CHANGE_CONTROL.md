# Euler CRM — development change control

This policy applies to every later change on this repository. A feature is not done when only the new screen works.

## Before changing code

1. Name the module (lead, booking, price, scheme, payment, outstanding, OEM chassis, claims, earnings, role).
2. Read the matching section of `EULER_MASTER_FUNCTIONAL_BASELINE.md`.
3. Find the tests that already lock that rule.
4. If two pull requests disagree, the later merged rule on `main` stands unless a still-later fix reversed it. If that cannot be shown, do not change the calculation.

## During the change

- Change the smallest set of lines that fixes the confirmed behaviour.
- Do not rename Mongo fields.
- Do not replace a partial lead update with a full-document write.
- Do not copy one chassis body's variant onto another chassis.
- Do not let last month's scheme apply when this month has no row, and do not let this month's scheme apply to a unit billed last month.
- Do not overwrite a typed RTO, insurance, GSTIN, or saved zero when filling a missing ex-showroom.
- Do not print or commit passwords, Coulson sessions, or sheet credentials.
- Do not run tests that write the live Google Sheet.

## Before merge

Run `.github/workflows/critical-regression.yml` locally when the change touches money, scheme, booking, payments, or OEM chassis:

```bash
cd backend
python3 -m pytest \
  tests/test_iter21_golive_lifecycle.py \
  tests/test_scheme_allocation_engine.py \
  tests/test_oct_2026_schemes.py \
  tests/test_nov_2026_schemes.py \
  tests/test_deal_pass_meet_cx.py \
  tests/test_rto_insurance_deal_approval.py \
  tests/test_owner_payment_delete.py \
  tests/test_excess_refund_and_finance_dedupe.py \
  tests/test_oem_billing.py \
  tests/test_coulson_oem_inventory.py \
  -q --tb=line
```

Review the diff for unrelated files. A Cloudflare Workers check that fails in the same second with no annotations is the known external miss. A failure inside the critical pytest job is a real failure.

## Before deploy

Confirm the commit on `main`, that the critical job passed, and that no migration was added that rewrites existing leads. This audit does not authorize a production deploy by itself.
