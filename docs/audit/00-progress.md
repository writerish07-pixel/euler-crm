# Audit progress

Updated 27 October 2026 (IST).

## Completed

- Phase 1 baseline on `origin/main` at `61b1ba8` (merge of pull request 265).
- Repository inventory: frontend pages, backend modules, roles, routes, indexes, tests, and deploy workflow.
- Re-read of the 16 October 2026 audit against current `main` for the four critical items and two high items that could be confirmed by reading the current functions.
- Findings register opened. No application code changed in this phase.

## Not done

- The app was not started against the live MongoDB database or the live Coulson OEM API.
- The full backend pytest suite was not re-run on this commit.
- The frontend production build and ESLint were not re-run on this commit.
- Phases 2–10 are not started. No bug fix from this audit has been applied.

## Checks that did run, on a different branch

On 26–27 October 2026, before this audit branch, these checks passed on `cursor/oem-rebill-chassis-rto-996c` (main plus the unmerged chassis/RTO commit, pull request 266). They used mongomock. They are not a full-suite baseline for `main`.

- 14 backend tests: rebilled chassis stays billed, a taken number plate does not block chassis, real RTO and insurance cut Additional (Dealer) and leave payable unchanged, Showroom Admin can edit RTO and insurance, the existing pack RTO test still passes.
- Frontend: `format.test.js` and `LeadDrawer.delivery.test.js` — 15 tests passed.

## Next action, after approval

1. Reproduce finding AUD-001 (pack refund uses unit 1’s price) with a new automated test, then fix it.
2. Reproduce finding AUD-005 (lead search crashes on `+` in a phone number) and escape the search text.
3. Do not change the public share board, password storage, or the go-live reset until the owner decides. Those change what staff and the public can see.

## How to resume

Read this file, then `FINDINGS.md`. Do not restart discovery. The safe rollback point for this phase is `origin/main` at `61b1ba8`. This branch only adds `docs/audit/`.
