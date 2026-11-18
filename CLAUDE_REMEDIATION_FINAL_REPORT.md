# Claude remediation report

Date: 18 Nov 2026 (Asia/Calcutta). Branch `cursor/claude-remediation-996c`. Not merged. Not deployed.

## Counts

- Claude findings: 24
- Fixed and verified by a regression test: 13 (CLD-01, 02, 03, 04, 05, 06, 07, 13, 18, 19, 21, 22, and the characterization for 16/23 is a lock, not a fix)
- Fixed in code, not covered by a new end-to-end test: CLD-09, 10, 11, 12, 14, 15, 24
- Already on main before this branch: the Created-list rebill and the different-customer rebill from PR 294. CLD-05 adds the blank-invoice case and the Sold archive.
- Requires a business decision, no code change: CLD-16, CLD-17, CLD-23
- Blocked on a repository admin: CLD-08 branch protection
- Not finished: CLD-20. Baseline full suite was 1560 passed, 63 failed, 28 errors. Live-HTTP collection errors are now skips. The other failures were not all cleared.

## Remaining severity

- CRITICAL: none left in the four P0 code paths (purge, share names, demo passwords, blank-invoice rebill). CLD-20 leaves a large unseen failure set, which is a process risk rather than one confirmed money bug.
- HIGH: CLD-08 branch protection is still open.
- MEDIUM: CLD-20 suite is not green. CLD-23 is an open business rule.
- LOW: CLD-16 and CLD-17 are open business rules. CLD-24 has no equality test yet.

## What was not done

Production data was not read. The plaintext-password and duplicate-census scripts were not run against production. Branch protection was not switched on. A deliberate red CI run was not pushed. The full backend suite was not re-run after the edits, so a new failure outside the regression files is possible.

## Protected behaviour

Booking price formulas, scheme month rules, and the Full Benefit default were not changed. Sales GM still cannot be given receipt rights. Refund stays on the money desk.
