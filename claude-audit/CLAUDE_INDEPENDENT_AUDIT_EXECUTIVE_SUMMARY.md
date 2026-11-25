# Euler CRM — Independent Audit: Executive Summary (Claude)

**Status: RED.** Cursor reported AMBER with "0 critical defects". Claude independently reproduced three critical problems on the current `main`, and found that Cursor's 18 Nov reports omitted P0/P1 problems that Cursor itself had recorded on 27 Oct.

## The five questions

| Question | Answer |
|---|---|
| 1. Is Euler CRM functionally correct? | **Core sales money path: yes, where tested.** Lead → booking (Price Master values load automatically, for owner and executive) → partial payments → outstanding all persisted and reconciled. Over-payment and duplicate-receipt guards work. **But** reading the Lead Register can delete genuine leads (CLD-01), and OEM claim receipts can be double-counted (CLD-06). |
| 2. Has approved business logic been lost? | **Yes, twice.** Owner-confirmed duplicate cleanup became automatic deletion (22 Sep). "Sales GM does not post cash" was lost as a side effect on 27 Sep; the tests guarding it have been red since. |
| 3. Did Cursor's repairs introduce defects? | **Yes, one.** Its cancelled-invoice repair (merged) can clear a chassis that was genuinely rebilled. Cursor's own open PR #294 acknowledges part of this. Its test-alignment repair is correct. |
| 4. Do critical workflows work end to end? | **Partly verified.** Verified in-process: booking, pricing, payments, outstanding, role scoping. Not verifiable here: browser UI, live OEM/Coulson sync, Google Sheets, WhatsApp/Exotel live calls. |
| 5. Is it protected against future regressions? | **No.** CI runs 10 of 111 backend test files and no frontend tests; no check is required to merge; 63 tests fail and 28 error in the wider suite. |

## Top issues (all reproduced unless stated)

1. **CLD-01 CRITICAL — Leads are silently deleted.** Opening the Lead Register (or restarting the server) deletes an open lead if the same person (by mobile, or **by name when mobile is blank**) has another open lead for the same model — including returning customers months later — together with its call history and KYC scans. No audit record.
2. **CLD-02 CRITICAL — Customer names are public.** `/api/share/dashboard` needs no login and lists every customer's name, model and status.
3. **CLD-03 CRITICAL (production state unknown) — Default passwords.** Owner and six staff accounts (including the Accounts money desk) are created with the password `euler@123`, which is published in the repository.
4. **CLD-04 HIGH — Passwords stored in plain text** and shown to the owner.
5. **CLD-05 HIGH — Cursor's merged OEM repair can drop a rebilled chassis** from a delivered file.
6. **CLD-06 HIGH — OEM claim money can be recorded twice**, beyond the claim amount, and the app retries these posts automatically on network errors.
7. **CLD-07 HIGH — Call/WhatsApp webhooks accept forged requests** when no secret is set; anyone can stamp a "customer-confirmed amount" on any lead.
8. **CLD-13 HIGH — Sales GM can post cash receipts**, contrary to the approved role design.

## What is good

- Price Master auto-population at booking — the issue previously reported — is **resolved** on the backend.
- Payments persist correctly; totals equal the sum of receipt rows; outstanding is correct.
- Customer-passed scheme benefit is not counted as dealer income; company share is applied first; unused schemes are not claimed.
- Executives cannot open or list other executives' customers; dealer earnings are owner-only at endpoint level.
- Frontend: 193 unit tests pass and the production build is clean.

## Before the next production deploy

1. Remove the automatic lead purge (CLD-01).
2. Strip customer data from the public board (CLD-02).
3. Check production for accounts still using `euler@123`; stop seeding demo users in production (CLD-03).
4. Complete and merge PR #294 or revert Cursor's AUD-001 (CLD-05).

Then: fix CLD-04/06/07/13/19, make the full test suite green and **required** on `main`, and add the frontend tests to CI.

## How this was established

Full Git history (752 commits, 294 PRs), all Cursor documents, the full backend suite (1,648 tests), Cursor's critical suite (251), frontend tests (193), production build, and 21 independent probes run against the real application with an in-memory database. No code, configuration, branch or production data was changed; nothing was committed or pushed.
