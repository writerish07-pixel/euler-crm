# Open business questions

These are recorded. The code was not changed.

## CLD-16 dealer margin

`compute_dealer_margin` removes GST twice. For an ex-showroom of ₹7,85,000:

- pre-GST = 7,85,000 / 1.05
- gross margin = that figure × 4%
- net margin = gross / 1.05

A characterization test locks this output. Confirm whether the second division is the intended net margin.

## CLD-17 year in ids

New leads are `LD26…` and receipts are `RC26…`. Identifiers created in 2027 will still read 26 until the prefix is changed.

## CLD-23 Full Benefit default

A lead with no explicit scheme allocation uses benefit mode Full Benefit. That passes the eligible scheme to the customer before anyone allocates it on the desk. An explicit empty allocation removes it. November Storm is the example Claude recorded (₹35,000 of scheme inside the payable before allocation).

## Turbo overlay and the sync flag

`_turbo_selling_ex` adds ₹15,000 only when the Price Master row has no `oemSyncedAt`. Two Turbo rows can differ by ₹15,000 based only on whether OEM sync has stamped the row. The formula was not changed.
