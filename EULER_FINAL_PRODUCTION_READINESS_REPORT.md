# Euler CRM — production readiness (this audit)

Date: 18 Nov 2026 (Asia/Calcutta).

**Status: AMBER.**

Critical money tests that were executed passed, and one confirmed chassis defect was repaired on the audit branch. That is not full-system verification. Production data was not read. The browser was not exercised. Most of the 111 test files were not run. AMBER is the honest status.

## What was checked

| Item | Result |
|---|---|
| Repositories | 1 — `writerish07-pixel/euler-crm` |
| `main` commits | 750, from 28 Jul 2026 through merge `adef670` (16 Nov 2026, 15:00 IST) |
| Pull requests | 292 metadata records. 290 merged, 1 open (#161), 1 closed (#32). All target `main`. |
| Remote branches | 261 (244 `cursor/`, 13 `claude/`, 1 `feature/`, 1 `codex/`, `main`) |
| In-process critical tests | 250 passed and 1 failed in one run. The failure was a stale RTO assertion. Re-run of that test after the assertion update: passed. |
| Production database | Not opened |
| Browser | Not used |
| Deploy | Not performed |

## Working, with test evidence from this session

- Deal lifecycle separation of customer payable, company outstanding, finance outstanding, and dealer earnings.
- Scheme allocation (company share first, explicit use).
- October and November 2026 scheme months.
- Cx Demand and typed RTO/insurance rules covered by the files in the critical plan.
- Payment delete and finance excess/dedupe tests that ran.
- OEM billing file, including cancel-versus-rebill after AUD-001.
- New catalog rows receive the family RTO/insurance default and do not clobber a later manual edit.

## Repaired on this branch, not yet on production

- AUD-001: a cancelled invoice that is still sitting in the Sold cache is cleared. A different invoice on the same chassis remains a rebill.

## Unresolved

- AUD-003 Cloudflare Workers instant failure. Not an application patch.
- Live HTTP iteration tests not run.
- Remainder of `backend/tests/` not run.
- No production reconciliation of live leads, payments, or chassis.
- Branch protection was not changed. The new workflow protects `main` only after an administrator requires the check.
- Pull request 161 remains open. It was not merged and not closed.

## Production safety

Starting checkout was `cursor/native-android-ios-996c` at `06fdfbea` with a clean tree. The audit branch was created from `origin/main`. No force-push, no history rewrite, no branch delete, no production write, no deploy.
