# Findings register

Baseline: `main` at `61b1ba8`, read 27 October 2026 (IST).
Severity: P0 critical, P1 high, P2 medium, P3 low.
Nothing in this file is marked fixed. No application code was changed for this audit.

| ID | Module | Finding in simple language | Evidence | Severity | Business impact | Recommended fix | Actual fix performed | Test performed | Result | Status |
|---|---|---|---|---|---|---|---|---|---|---|
| AUD-001 | Payments | On a multi-vehicle order, a refund is judged against vehicle 1’s price only. Money the customer still owes on the other vehicles can be sent back. | `backend/server.py` `_refund_position` still sets payable with `compute_commercial_totals(lead_to_snapshot(lead))`. Receipts were previously corrected to sum the pack. The 16 October audit reproduced a 2-unit case where ₹1,00,000 refunded while ₹4,84,500 was still owed. That scenario was not run again on 27 October. | P0 | The showroom can refund cash that is not actually excess. Outstanding then grows. | Use the same pack payable the receipt screen uses. Lock it with a test before and after. | None | Code read on 27 October. Prior reproduction was 16 October. Not re-executed today. | Code path unchanged | Verified issue |
| AUD-002 | Admin reset | The owner reset tool starts lead numbers again at LD26000001, but it does not clear KYC files or WhatsApp chats. A new customer can inherit the old customer’s documents. | `reset_transactions` deletes leads and payments, sets the lead counter to 0, and does not delete `lead_documents`, `whatsapp_threads`, or `whatsapp_messages`. It also says the next id is LD26000001. Scheme claim ids are built from the lead id, and the claim sheet is kept on purpose. | P0 | After a reset, the next customer can show the previous customer’s Aadhaar and chat. A new scheme claim can overwrite an old claim row in the sheet. | Never reuse lead ids. Archive or clear every collection keyed by lead id. Needs the owner’s approval because this is the go-live reset. | None | Code read on 27 October. Not executed. The reset was not called. | Code path unchanged | Verified issue. Waiting for approval |
| AUD-003 | Share board | Anyone with the share link, with no login, receives every customer’s name, model, variant, and status. | `@public.get("/share/dashboard")` builds `allLeads` with `customerName`. The list is capped at 5,000 leads. The June PRD said this board had no customer data. The current page shows names. Those two records disagree. | P0 | Customer names are public. Past 5,000 leads the counts are also silently short. | Confirm with the owner whether the company WhatsApp board is supposed to show names. If not, return counts only. | None | Code read on 27 October. The live URL was not called. | Code path unchanged | Verified issue. Waiting for approval |
| AUD-004 | Login | Staff passwords are stored in plain text, and demo accounts are created on every startup if they are missing. The owner screen can display those passwords. | `auth.py` `seed_users` inserts demo users with password `euler@123` when the row is absent, and stores `passwordPlain`. `_owner_user_row` returns that plain password to the owner user list. `password_matches` accepts the stored plain text. Tests assert the password is not in the login response. There is no login throttle in this file. | P1 | A database copy, a backup, or an owner session reveals every staff password. A missed demo account on a fresh database is a known password. | Seed demo users only outside production. Stop storing the plain password, and give the owner a reset instead of a view. This removes a feature the owner uses today, so it needs approval. | None | Code read on 27 October. Login was not attempted against production. | Code path unchanged | Verified issue. Waiting for approval |
| AUD-005 | Lead register | Typing a mobile number that starts with `+` can make the lead list fail. | Lead search still puts the raw text into a Mongo `$regex` on `customerName`, `mobile`, and `leadId` (`server.py` near the lead list query). `+` is a regex operator. The 16 October audit saw HTTP 500. Not re-run on 27 October. | P1 | Staff cannot find a customer while typing a normal phone number. | Escape the search text. Keep a test that `+9198…` returns 200. | None | Code read on 27 October. Not re-executed. | Code path unchanged | Verified issue |
| AUD-006 | Dates | The server’s “today” and “this month” use UTC. The dealership works on India time. From midnight to 5:30am IST, the server date is still the previous day. | `today()` and `this_month()` in `server.py` use `datetime.now(timezone.utc)`. WhatsApp and Exotel already have `today_ist()`. The public share board also labels the month from UTC. | P1 | On the morning of the 1st, a booking or a dashboard tile can land in the previous month, which changes scheme month and the day’s counts. | One India-date helper for business dates. Needs tests around midnight IST. Do not change stored historical dates blindly. | None | Code read on 27 October. No clock test was run. | Code path unchanged | Verified issue |
| AUD-007 | Tests and deploy | Backend tests do not run when a pull request is opened. The only GitHub workflow builds the frontend. | `.github/workflows/cloudflare-validate.yml` is the only workflow. The 16 October audit found backend failures that had still merged. Those failure counts were not re-measured on 27 October. | P1 | A money or permission bug can merge because nothing runs the Python tests. | Run the mongomock suite on pull requests. First record today’s pass and fail count so old failures are not mistaken for new ones. | None | Workflow file read. Full suite not run. | Not measured today | Verified issue |
| AUD-008 | Docs and legacy portal | The root README still tells staff to use the old Apps Script site. A June go-live checklist still says the app has two roles and scores itself 96/100. | `README.md` points at `assets/js/config.js`. `frontend/public/docs/GO_LIVE_CHECKLIST.md` is version 2.3, June 2026. `auth.py` now has nine roles. | P2 | A new person follows the wrong setup, or trusts a checklist that does not match the app. | After the audit, replace the README with the React app’s real start steps. Do not delete `assets/js` until nothing live still loads it. | None | Files read. No live GitHub Pages check. | Docs are stale | Verified issue |
| AUD-009 | Structure | Almost all business actions live in one 18,967-line file. Payable is calculated in more than one place, which is how AUD-001 survived. | `wc -l backend/server.py` on 27 October. | P3 | Fixes in one screen do not reach the other screen. A rewrite would risk working deals. | Do not split the file as a project of its own. When a bug is fixed, call the existing helper instead of copying the formula. | None | Line count only | Observation | Improvement recommended |
| AUD-010 | OEM chassis | A cancelled invoice that is later rebilled can drop the chassis, so the delivery screen says the vehicle is not billed. Real RTO and insurance can reduce the customer’s payable instead of the dealer’s discount. | Pull request 266, not on `main`. Tests on that branch passed on 27 October (mongomock). Production data for lead LD260000919 was not opened. | P1 | Until that pull request is merged and someone runs Sync from OEM, the chassis stays blank and a lower insurance premium can show a false excess. | Review and merge pull request 266, then Sync from OEM. This audit does not repeat that change. | None on this branch | 14 backend tests and 15 frontend tests on the other branch. Not production. | Passed on that branch | Confirmed working on an unmerged branch |

## Carried from 16 October and not re-checked on 27 October

These were reported then. They are not marked open or closed today. Phase 4 has to re-read the current functions and, where it still matters, reproduce them.

| Old id | Topic | Why it is not closed or reopened yet |
|---|---|---|
| H2 | An executive may open or change another executive’s lead on some routes | Routes moved. Not re-tested |
| H3 | Changing model or variant can leave the unit on the old price | Not re-tested |
| H4 | WhatsApp and call webhooks accept posts when no secret is set | Not re-tested |
| H6 | Long lists cut off at a fixed number before filters | Not re-counted |
| M1 | Sales GM may be able to post a customer payment | Not re-tested. The role comment still says they do not post cash |
| M2–M6 | Sheet formula injection, sheet row cache, duplicate receipt retry, refund race, lead 360 writing on open | Not re-tested |
| M7 | CORS allows every origin | Not re-tested |
| M8 | Sample customer data in seed files | Files were not re-opened this session |
| M10 | `leadId` is not a unique index | Startup indexes were read. `leadId` is indexed and is not unique. The collision story was not reproduced |

## Confirmed working, only for the checks named

| ID | What | Evidence | Status |
|---|---|---|---|
| AUD-011 | Invoice List is the billed source, and a chassis with only a cancelled invoice leaves Sold | Pull request 265 is merged at `61b1ba8`. Its tests were not re-run on 27 October | Confirmed working as merged code. Live sync not run |
| AUD-012 | Outside OEM finance users are blocked from the lead register by a central allow-list | `auth.py` `EXTERNAL_ROLES` | Confirmed in code. Not penetration-tested |

## Explicitly not tested

- Live Coulson login, sync, pagination, and rate limits.
- Production MongoDB size, slow queries, and backups.
- Two staff saving the same lead at once, except where an older test already covers a 4-second duplicate receipt.
- Click-through of every page on a phone.
- Dependency vulnerability scan.
- Performance timings. No before/after numbers exist for this audit.
