# Euler CRM — git history and pull-request audit

Audit date: 18 Nov 2026 (Asia/Calcutta).

## Repository

- One repository: `writerish07-pixel/euler-crm`.
- Remote: `origin` on GitHub.
- No git tags.
- Production line: `main`.
- First commit on `main`: `4c8b2e6` 28 Jul 2026 11:30 IST — "Euler Motors CRM portal — ready for GitHub Pages".
- Head of `main` at the start of this audit: `adef670eb4e4b5890c8147d6204156226df9b84e` 16 Nov 2026 15:00 IST — "Merge pull request #292".
- Commit count on `main`: 750 (`git rev-list --count origin/main`).

## Working tree at the start of this session

- Branch checked out: `cursor/native-android-ios-996c`.
- Commit: `06fdfbeac64fc5fa83cef91c4826203e65fe9864` (15 Sep 2026) "Point Android zip download at the raw GitHub file URL."
- Uncommitted changes: none.
- This audit branch `cursor/crm-enterprise-audit-996c` was created from `origin/main`. The Android branch was not modified and was not deleted.

## Branches

`git branch -r` count: 261.

| Prefix | Count |
|---|---|
| cursor/ | 244 |
| claude/ | 13 |
| feature/ | 1 |
| codex/ | 1 |
| main | 1 |

Each `cursor/` name is a historical feature or fix branch. They were not each diffed against `main` in this pass. Merged work is on `main` through the pull requests below. Unmerged work that is not in a pull request was not reconstructed line by line. That limit is explicit.

## Pull requests

Source: `gh pr list --state all --limit 400` on 18 Nov 2026. 292 records. Author login on every record: `writerish07-pixel`. Base branch on every record: `main`.

| State | Count |
|---|---|
| MERGED | 290 |
| OPEN | 1 (#161 Android and iOS; the website on main is unchanged by it) |
| CLOSED | 1 (#32 SPA refresh note) |

Pull requests by month of merge, or by creation month when the pull request was not merged:

| Month | Pull requests |
|---|---|
| 2026-08 | 84 |
| 2026-09 | 102 |
| 2026-10 | 83 |
| 2026-11 | 23 |

Full diffs were not read for all 292. Titles and the code they name were used to reconstruct the baseline. Files read in detail for the defect work: `backend/oem_sync.py` cancel/rebill, `backend/commercial.py` RTO defaults, `backend/auth.py` roles, the critical test modules, `frontend/src/App.js` routes, and the June audit file.

## What the history shows, in order

1. Jul–early Aug 2026: portal, then FastAPI port of the Apps Script commercial engine.
2. Aug 2026: partial lead update (data-loss fix), Price Master required at booking, scheme allocation engine, Google Sheet sync, dealer earnings lines, audit log, roles starting to split.
3. Sep 2026: Coulson inventory, staff roles (GM, TL, executive scope), September schemes, claims matched by chassis, insurance MIS, same-mobile and same-order packs.
4. Oct 2026: October scheme by billed date, OEM Billing tab, Tally, per-unit pack commercials, Exotel, showroom admin.
5. Nov 2026: exact per-chassis billed body, typed RTO/insurance kept, November scheme, confirmed variant stays off the queues. This audit then found the cancel-versus-rebill invoice bug on that head.

Later merged pull requests supersede the June 2026 production-audit document where they conflict. Examples: dealer extra-income fields, dashboard KPIs, and the audit log exist in current code.

## Inaccessible history

- Diffs of remote branches that were never opened as pull requests were not downloaded one by one.
- GitHub review comment threads were not re-read for all 292 pull requests.
- No second Euler CRM repository was found from this remote.

## Appendix — every pull request returned by the API

| Number | State | Date | Title |
|---|---|---|---|
| 1 | MERGED | 2026-08-08 | Port Apps Script parity fixes: entitlements, dealer earnings, claim ageing, finance SLA |
| 2 | MERGED | 2026-08-08 | Add editable Master Lists (Executives/Financers/etc.) synced to Google Sheet |
| 3 | MERGED | 2026-08-08 | Fix critical data-loss bug: PUT /leads/{id} now a true partial update |
| 4 | MERGED | 2026-08-08 | Fix 5 Phase 2 production defects: claim register, negative payments, … |
| 5 | MERGED | 2026-08-09 | Fix GS-1..GS-5: header-mapped, idempotent Google Sheet sync |
| 6 | MERGED | 2026-08-09 | Map Google Sheet sync to the real Euler Master workbook structure |
| 7 | MERGED | 2026-08-09 | Fix Sheets read-quota exhaustion and sync derived claims to the Sheet |
| 8 | MERGED | 2026-08-09 | Find the Render Secret File credential instead of only the env var |
| 9 | MERGED | 2026-08-09 | Wire the frontend to the production API and add config diagnostics |
| 10 | MERGED | 2026-08-09 | Fix Render frontend build: pin rootDir, add SPA rewrite and root fallback |
| 11 | MERGED | 2026-08-09 | Load Price Master at booking; refuse commercially empty bookings |
| 12 | MERGED | 2026-08-09 | Gate booking on the backend price preview |
| 13 | MERGED | 2026-08-09 | Strict production booking mode: revalidate Price Master on every booking |
| 14 | MERGED | 2026-08-09 | Sync the Lead Register on every recompute, not only on create |
| 15 | MERGED | 2026-08-09 | Finance: resolve finance file before receipts, enforce unique finance indexes, and show file in UI |
| 16 | MERGED | 2026-08-09 | Improve Google Sheets error diagnostics with precise error classification |
| 17 | MERGED | 2026-08-09 | Claude/codebase audit gs sync x0dz7v |
| 18 | MERGED | 2026-08-09 | Claude/codebase audit gs sync x0dz7v |
| 19 | MERGED | 2026-08-10 | Claude/codebase audit gs sync x0dz7v |
| 20 | MERGED | 2026-08-10 | fix: scheme eligibility ≠ assignment (Use Scheme Yes/No) |
| 21 | MERGED | 2026-08-10 | Add the Scheme Allocation Engine as the single commercial source of t… |
| 22 | MERGED | 2026-08-10 | fix: Cloudflare Workers Builds — add Wrangler SPA config |
| 23 | MERGED | 2026-08-10 | fix: Render startup crash — KeyError shareSplitAvailable in recompute_lead |
| 24 | MERGED | 2026-08-10 | fix: Insurance Benefit persistence + dealer-funded benefit in Dealer Earnings |
| 25 | MERGED | 2026-08-10 | feat: Lead Register A1 layout + Insurance Benefit / Claim columns |
| 26 | MERGED | 2026-08-10 | fix: go-live reset clears incentives + Google Sheet registers |
| 27 | MERGED | 2026-08-10 | feat: date input on every lead lifecycle step |
| 28 | MERGED | 2026-08-10 | fix: lock Ex-Showroom; unique invoice / chassis / number plate |
| 29 | MERGED | 2026-08-11 | fix: scheme retained = company kept; staff step locks; owner cascade |
| 30 | MERGED | 2026-08-11 | fix: Incentive sheet sync, paid → OEM claim, lock delivered/closed leads |
| 31 | MERGED | 2026-08-11 | fix: stop test leads refilling Google Sheet; fresh start from LD26000001 |
| 32 | CLOSED | 2026-08-11 | Fix: document why /leads refresh 404s on Render (SPA rewrite) |
| 33 | MERGED | 2026-08-11 | fix: unused schemes stop claiming; insurance Self vs Dealer |
| 34 | MERGED | 2026-08-11 | Owner lead delete also clears Google Sheet traces |
| 35 | MERGED | 2026-08-11 | Wire OEM Extra Support through claim, earnings, and Google Sheets |
| 36 | MERGED | 2026-08-11 | Dealer Earnings includes OEM Extra; total column last on sheet |
| 37 | MERGED | 2026-08-11 | Scheme Claim Register never archives — claims stay forever |
| 38 | MERGED | 2026-08-12 | Delivery Billing Summary for Tally cross-check |
| 39 | MERGED | 2026-08-12 | Change password for owner and executive |
| 40 | MERGED | 2026-08-12 | Accounts dashboard and money-desk role |
| 41 | MERGED | 2026-08-12 | Executive dashboard + shared ASM/RM field board |
| 42 | MERGED | 2026-08-12 | Fix ASM lead privacy and scoreboard Book % after delivery |
| 43 | MERGED | 2026-08-12 | Fix mobile layout: responsive shell and dense screens |
| 44 | MERGED | 2026-08-14 | Point Render frontend at Railway API |
| 45 | MERGED | 2026-08-14 | Owner edit until closed + Close Won status badge |
| 46 | MERGED | 2026-08-14 | Close Won on Lead Register and Google Sheet |
| 47 | MERGED | 2026-08-14 | Tally full-amount summary + booking advance default 0 |
| 48 | MERGED | 2026-08-14 | Refresh Tally summary after Additional (Dealer) / scheme edits |
| 49 | MERGED | 2026-08-14 | Fix Railway Google Sheet sync via GSHEET_CREDENTIALS_JSON |
| 50 | MERGED | 2026-08-14 | Fix Delivered leads stuck on “Fetching lead…” |
| 51 | MERGED | 2026-08-15 | ASM/RM read-only Finance Register |
| 52 | MERGED | 2026-08-15 | Parked: Insurance Benefit “upto” rule (wait for company confirm) |
| 53 | MERGED | 2026-08-15 | Parked: BotSpace WhatsApp follow-up (implement later) |
| 54 | MERGED | 2026-08-17 | Bulk lead upload: template with live dropdowns + validated import |
| 55 | MERGED | 2026-08-17 | Refundable excess payments; stop double-posting financer receipts |
| 56 | MERGED | 2026-08-17 | Owner dashboard: change price of any model |
| 57 | MERGED | 2026-08-18 | WhatsApp via BotSpace (Euler leads only) |
| 58 | MERGED | 2026-08-18 | Fix failed frontend build so WhatsApp Settings and lead tab appear |
| 59 | MERGED | 2026-08-18 | Send Google review WhatsApp to already-delivered leads |
| 60 | MERGED | 2026-08-18 | Owner can delete a payment receipt |
| 61 | MERGED | 2026-08-19 | Fix BotSpace webhook URL to live Railway API |
| 62 | MERGED | 2026-08-19 | Send booking confirmation WhatsApp to already-booked leads |
| 63 | MERGED | 2026-08-19 | Fix frontend deploy (LeadDrawer JSX + CI ESLint) |
| 64 | MERGED | 2026-08-19 | Fix WhatsApp “not configured” when Settings already has key + channel |
| 65 | MERGED | 2026-08-24 | Claude/codebase audit gs sync x0dz7v |
| 66 | MERGED | 2026-08-24 | Insurance agents with per-agent payout slabs |
| 67 | MERGED | 2026-08-24 | Show the insurance agent on the Lead Register; require it at delivery |
| 68 | MERGED | 2026-08-25 | Claude/codebase audit gs sync x0dz7v |
| 69 | MERGED | 2026-08-26 | Add the staff master and daily WhatsApp reports |
| 70 | MERGED | 2026-08-26 | Claude/codebase audit gs sync x0dz7v |
| 71 | MERGED | 2026-08-27 | Claude/codebase audit gs sync x0dz7v |
| 72 | MERGED | 2026-08-27 | Add lead cancellation, revival, and the model-interest campaign |
| 73 | MERGED | 2026-08-27 | Fix cancelled leads: dead outstanding, no refund path, double-counted money |
| 74 | MERGED | 2026-08-28 | Fix re-book money, Close Won OEM lists, and finance WhatsApp |
| 75 | MERGED | 2026-08-29 | Make a failed daily report say why it failed |
| 76 | MERGED | 2026-08-29 | Deliver EOD reports: session-window fallback and Utility-shaped templates |
| 77 | MERGED | 2026-08-31 | Add a read-only OEM finance role, fenced off from everything else |
| 78 | MERGED | 2026-08-31 | Add a Team Leader role to finish the deals executives start |
| 79 | MERGED | 2026-08-31 | Scope executives to their own leads, add login IDs and lead allocation |
| 80 | MERGED | 2026-08-31 | Pull Euler OEM inventory and ex-showroom from Coulson |
| 81 | MERGED | 2026-08-31 | Unblock Railway startup: apply OEM catalog after the server listens |
| 82 | MERGED | 2026-08-31 | Stop the login screen from rejecting the real owner password |
| 83 | MERGED | 2026-08-31 | Verify Coulson login on save so Sync uses a working OEM password |
| 84 | MERGED | 2026-08-31 | Stop sending the hidden Coulson username hint to Euler |
| 85 | MERGED | 2026-09-01 | Fix Coulson login refusing credentials that are correct |
| 86 | MERGED | 2026-09-01 | Log into Coulson from Euler CRM the same way the dealer portal does |
| 87 | MERGED | 2026-09-01 | Hit Coulson login once from the server, not from the browser tab |
| 88 | MERGED | 2026-09-01 | Paste Coulson session so OEM sync works without Euler login |
| 89 | MERGED | 2026-09-02 | Staff names, yard inventory on dashboards, chassis pick, Sept price lock |
| 90 | MERGED | 2026-09-02 | Fix Scheme Master not switching month when the date changes |
| 91 | MERGED | 2026-09-02 | Fix frontend deploy: close Executive Dashboard JSX |
| 92 | MERGED | 2026-09-02 | Optional email and owner-visible staff passwords |
| 93 | MERGED | 2026-09-02 | Live yard chassis pick for deliveries from 1 Sep |
| 94 | MERGED | 2026-09-02 | Sales GM dashboard and showroom sales role |
| 95 | MERGED | 2026-09-02 | Hold executive leads until GM or Owner approve |
| 96 | MERGED | 2026-09-02 | Hide company tools from executives; owner-set exec incentive; own finance files |
| 97 | MERGED | 2026-09-02 | Per-executive incentive targets and steps |
| 98 | MERGED | 2026-09-02 | Exec stops at booking; Turbo +₹15k; Coulson sold chassis; TCS after discount |
| 99 | MERGED | 2026-09-02 | Fix GSheet backfill for TCS/RSA fields and waiting headers |
| 100 | MERGED | 2026-09-02 | Listen before sheet backfills so Railway deploys stay up |
| 101 | MERGED | 2026-09-02 | Fix staff password change so owner User Accounts shows the new password |
| 102 | MERGED | 2026-09-02 | Catch up missed morning and EOD WhatsApp so staff actually receive them |
| 103 | MERGED | 2026-09-02 | Show Sheet Synced when Google Sheet is connected, not Sync Error |
| 104 | MERGED | 2026-09-02 | Give Sales GM executive incentive targets and this-month board |
| 105 | MERGED | 2026-09-02 | Sync Coulson Sold chassis and invoice onto all matching leads |
| 106 | MERGED | 2026-09-02 | Fill OEM mobile from unique Sold names so chassis can sync |
| 107 | MERGED | 2026-09-02 | Mirror Euler's claim settlements and tie them to leads by chassis |
| 108 | MERGED | 2026-09-02 | Connect Euler's claim settlements to the CRM and cross-check both registers |
| 109 | MERGED | 2026-09-02 | Join scheme claim register to OEM settlements by chassis and invoice |
| 110 | MERGED | 2026-09-02 | Fix scheme register Not claimed and blank OEM chassis/invoice |
| 111 | MERGED | 2026-09-02 | Hit debit-note/journey so OEM claims get chassis and invoice |
| 112 | MERGED | 2026-09-02 | Match Additional Support claims to OEM Extra Support |
| 113 | MERGED | 2026-09-02 | Stamp Scheme Claim status from Euler; Extra Support files from the vehicle |
| 114 | MERGED | 2026-09-03 | Monthly registers, OEM Finance extras, KYC documents, and lead search |
| 115 | MERGED | 2026-09-03 | KYC, delivery scans, Tally invoice, cancelled refunds, and header search |
| 116 | MERGED | 2026-09-04 | Show MTD and YTD on every dealership dashboard |
| 117 | MERGED | 2026-09-04 | Price List is OEM prices only; schemes stay monthly on the lead |
| 118 | MERGED | 2026-09-04 | Sync OEM list prices into Price List and Price Master |
| 119 | MERGED | 2026-09-04 | Upload agent MIS on Insurance Payouts and approve received amounts |
| 120 | MERGED | 2026-09-04 | File Extra Support only when the OEM app actually has it |
| 121 | MERGED | 2026-09-04 | Match insurance MIS on chassis and fetch payout details |
| 122 | MERGED | 2026-09-04 | OEM claim document Yes/No and manual register matching |
| 123 | MERGED | 2026-09-04 | Count Claim Item Docs (Add Documents) for OEM Yes/No |
| 124 | MERGED | 2026-09-04 | Each claim item needs its own Docs upload |
| 125 | MERGED | 2026-09-04 | Fix staff login after credentials are created |
| 126 | MERGED | 2026-09-04 | Multi-match OEM Extra Support lines and show Euler descriptions |
| 127 | MERGED | 2026-09-04 | Fix home-screen login on phones |
| 128 | MERGED | 2026-09-04 | MIS is mapping only; drop Extra Support; unpayable OEM write-off |
| 129 | MERGED | 2026-09-05 | Replace mapped insurance expected payout with MIS amount |
| 130 | MERGED | 2026-09-05 | Fix Replace with MIS amount errors and put it in dealer earnings |
| 131 | MERGED | 2026-09-05 | Fix staff login on Android phones |
| 132 | MERGED | 2026-09-06 | Sept 2026 schemes + scheme-free deal format |
| 133 | MERGED | 2026-09-06 | Create Scheme Claim Register rows from unmatched OEM claims |
| 134 | MERGED | 2026-09-06 | Restore filtered lead and component lists on OEM match |
| 135 | MERGED | 2026-09-06 | Fix empty Lead dropdown on OEM claim match |
| 136 | MERGED | 2026-09-06 | Create copies the OEM claim name — no lead match |
| 137 | MERGED | 2026-09-06 | Fix OEM sync and Create crashes on dirty Euler data |
| 138 | MERGED | 2026-09-07 | Fix OPPO and vivo phones stuck on Loading then blank |
| 139 | MERGED | 2026-09-07 | Land the OPPO/vivo locale fix that never reached production |
| 140 | MERGED | 2026-09-07 | Fix dashboard crash: outstanding.customer on OPPO/vivo |
| 141 | MERGED | 2026-09-07 | Make Clear cache fetch a fresh Euler page on OPPO/vivo |
| 142 | MERGED | 2026-09-07 | Fix TL bulk lead import and split uploads by executive % |
| 143 | MERGED | 2026-09-07 | Fix TL Import drawer crash (split state missing) |
| 144 | MERGED | 2026-09-07 | Skip bulk-upload leads that are already in the app |
| 145 | MERGED | 2026-09-07 | Stop import Network Error after leads already saved |
| 146 | MERGED | 2026-09-07 | Apply saved split to unassigned leads (pending approval) |
| 147 | MERGED | 2026-09-07 | Register Proceed, tap-to-call, month filter, stable scroll |
| 148 | MERGED | 2026-09-07 | Owner and GM Approve only — exec asks from the register |
| 149 | MERGED | 2026-09-07 | Add model and variant to the executive send-for-approval drawer |
| 150 | MERGED | 2026-09-08 | Production copy, errors, and Sheet wiring polish |
| 151 | MERGED | 2026-09-08 | Lead Allocation: status filter and reallocate selected leads |
| 152 | MERGED | 2026-09-08 | Bulk actions: no Sheet wait, no retry, chunked reallocate |
| 153 | MERGED | 2026-09-09 | Add OEM Extra Support on executive approval |
| 154 | MERGED | 2026-09-10 | Write only Scheme Claim Register to Google Sheets |
| 155 | MERGED | 2026-09-10 | Fix Railway crash: pin Python 3.12 and upgrade pymongo |
| 156 | MERGED | 2026-09-10 | No executive lead edit; TL creates under any executive with KYC |
| 157 | MERGED | 2026-09-10 | Restore insurance expected on Dealer Earnings until MIS overwrites |
| 158 | MERGED | 2026-09-13 | OEM report math, rebuild/refresh, yard transit, deal-amount WhatsApp |
| 159 | MERGED | 2026-09-15 | Price Master RTO/insurance + auto Additional (Dealer) + Owner-only when deal differs |
| 160 | MERGED | 2026-09-15 | Pin Railway to Python 3.12 and stop Sheets HTTP segfaults |
| 161 | OPEN | 2026-09-15 | Add Android and iOS apps; keep the live website |
| 162 | MERGED | 2026-09-16 | Payment UTR per receipt and OEM Extra Support proof |
| 163 | MERGED | 2026-09-16 | Same mobile, many vehicles — confirm before a second file |
| 164 | MERGED | 2026-09-17 | Hide owner commercials from staff; fix phone layout |
| 165 | MERGED | 2026-09-18 | OEM scheme on exec lead create, B2B Aadhaar optional, owner per-field edit, TL team pipeline |
| 166 | MERGED | 2026-09-22 | TL lead-create parity: OEM extra + visible multi-unit |
| 167 | MERGED | 2026-09-22 | Stop blocking delivery on chassis; auto-fill from OEM Sold |
| 168 | MERGED | 2026-09-22 | Add OEM Billing tab: Sold vs CRM and auto-create missing leads |
| 169 | MERGED | 2026-09-22 | Copy KYC onto extra units and auto-add OEM fleet chassis |
| 170 | MERGED | 2026-09-22 | Copy OEM Extra Support email onto an additional unit |
| 171 | MERGED | 2026-09-22 | Same-order multi-unit pack on one lead id |
| 172 | MERGED | 2026-09-22 | Stop Create Lead from minting three ids for one tap |
| 173 | MERGED | 2026-09-22 | Heal live New triples and give each pack unit its own price and scheme |
| 174 | MERGED | 2026-09-22 | Per-unit price and scheme, and heal the live New triples |
| 175 | MERGED | 2026-09-22 | Show each pack unit’s Price and Scheme, and fix pack payable |
| 176 | MERGED | 2026-09-22 | Fix frontend compile so pack Units tab can deploy |
| 177 | MERGED | 2026-09-22 | Per-unit Scheme (OEM Extra) and number plate on pack orders |
| 178 | MERGED | 2026-09-22 | Pack billing: ₹48,000 OEM extra and ₹11,500 dealer-funded on each unit |
| 179 | MERGED | 2026-09-23 | Meet Cx Demand: Extra Passed follows the deal; outstanding from GVC |
| 180 | MERGED | 2026-09-23 | Payable stays on Cx Demand; extra vs GVC goes to dealer margin |
| 181 | MERGED | 2026-09-24 | OEM sync matches only; relink Created-from-OEM stubs to booked leads |
| 182 | MERGED | 2026-09-24 | Relink OEM stubs onto Close Won / August files with the same mobile |
| 183 | MERGED | 2026-09-24 | Connect same-mobile duplicates and delete the empty file |
| 184 | MERGED | 2026-09-28 | Hide scheme from executives; they book and collect |
| 185 | MERGED | 2026-09-28 | Require deal sheet on approval and export the open register |
| 186 | MERGED | 2026-09-29 | Keep Customer Payable in sync when Cx Demand is edited |
| 187 | MERGED | 2026-10-05 | Hide dropped, unused, and matched claims from live queues |
| 188 | MERGED | 2026-10-05 | Auto-approve exec/TL deals when there is no discount |
| 189 | MERGED | 2026-10-08 | Connect OEM Sold to existing mobiles; open bookings; approval uploads |
| 190 | MERGED | 2026-10-09 | B2B booking: GST certificate counts as GSTIN |
| 191 | MERGED | 2026-10-09 | Post pack booking advance and per-unit billed dates |
| 192 | MERGED | 2026-10-09 | Scope insurance MIS match to the file’s month |
| 193 | MERGED | 2026-10-09 | October 2026 scheme + circular by billed date |
| 194 | MERGED | 2026-10-10 | Print a customer deal sheet PDF to sign and upload |
| 195 | MERGED | 2026-10-10 | Showroom Admin, team-scoped TL, and executive Finance receipts |
| 196 | MERGED | 2026-10-10 | Adopt Coulson billed body when Sold fetch stamps the chassis |
| 197 | MERGED | 2026-10-11 | Relink a lead after the OEM claim is cancelled and refiled |
| 198 | MERGED | 2026-10-11 | OEM Billing: auto-attach by mobile, mark Delivered, delink cancelled invoices |
| 199 | MERGED | 2026-10-11 | Fix Scheme Claim Register empty load |
| 200 | MERGED | 2026-10-12 | Tally billing summary invoices the vehicle only |
| 201 | MERGED | 2026-10-12 | OEM Extra Passed is not a customer discount |
| 202 | MERGED | 2026-10-12 | Tally bill: vehicle without GST, then discount, then GST |
| 203 | MERGED | 2026-10-12 | Confirm-only AI Agents desk (papers, PDF RTO/Ins, OEM, Coulson, follow-up, Tally-prep) |
| 204 | MERGED | 2026-10-12 | Fix AI Agents 25s timeout and stuck Loading |
| 205 | MERGED | 2026-10-13 | Remove AI Agents desk (rollback) |
| 206 | MERGED | 2026-10-13 | Tally invoice ZIP upload + Showroom Admin register hides New |
| 207 | MERGED | 2026-10-13 | Showroom Admin: flag leads that cannot be delivered yet |
| 208 | MERGED | 2026-10-13 | Tally pack checker — flag invoice, ledger, and receipt gaps on one lead |
| 209 | MERGED | 2026-10-13 | Show all leads on Showroom Admin, including New |
| 210 | MERGED | 2026-10-14 | Walk-in enquiries create live; KYC and deal approval at booking |
| 211 | MERGED | 2026-10-14 | Pack Extra Support: two OEM claims per lead, hide matched, flag cancelled rebills |
| 212 | MERGED | 2026-10-14 | Let Team Leader see team leads when names differ |
| 213 | MERGED | 2026-10-14 | Show TL-created team leads on the dashboard; stop deleted users coming back |
| 214 | MERGED | 2026-10-15 | Add Edit Log Register for GM, Showroom Admin, TL, and Executive |
| 215 | MERGED | 2026-10-15 | Slim walk-in create, complete at Book, Team Leader nav matches Executive |
| 216 | MERGED | 2026-10-15 | Hide OEM scheme on Team Leader Convert to Booking |
| 217 | MERGED | 2026-10-16 | Akar Euler Hindi Exotel calls to verify amount paid |
| 218 | MERGED | 2026-10-16 | Queue existing booked leads for Exotel verify calls |
| 219 | MERGED | 2026-10-16 | Fix Exotel verify calls failing on Call now |
| 220 | MERGED | 2026-10-16 | Drop StatusCallbackEvents from Exotel verify calls |
| 221 | MERGED | 2026-10-16 | Fix Convert to Booking docs staying on No file |
| 222 | MERGED | 2026-10-16 | Keep unapproved discounted deals off the staff register |
| 223 | MERGED | 2026-10-16 | Clearer Exotel Hindi greeting for field customers |
| 224 | MERGED | 2026-10-16 | Restore the original Exotel verify audio |
| 225 | MERGED | 2026-10-16 | Let staff recreate a lead after reject or Lost |
| 226 | MERGED | 2026-10-16 | Auto-call every booked lead for amount verify |
| 227 | MERGED | 2026-10-16 | Pick any month on the executive / TL scoreboard |
| 228 | MERGED | 2026-10-16 | Stop boot work from emptying the live CRM |
| 229 | MERGED | 2026-10-16 | Unblock dashboards stuck on Loading |
| 230 | MERGED | 2026-10-16 | Stop 25s dashboard timeouts after staff monthly register |
| 231 | MERGED | 2026-10-16 | Stop Coulson Save session from freezing the live desk |
| 232 | MERGED | 2026-10-16 | Stop OEM Billing from timing out to empty zeros |
| 233 | MERGED | 2026-10-16 | Show print and upload deal sheet on executive Request a lead |
| 234 | MERGED | 2026-10-16 | Park unbooked enquiries on Follow-up Lead Register |
| 235 | MERGED | 2026-10-16 | Sync Coulson Vehicle Invoices so chassis billed today show in OEM Billing |
| 236 | MERGED | 2026-10-16 | Fix OEM Extra Support proof upload |
| 237 | MERGED | 2026-10-16 | Pull today's OEM invoices from Coulson's updated Vehicle Invoices API |
| 238 | MERGED | 2026-10-16 | Auto-match OEM Extra Support by the chassis now required in Coulson |
| 239 | MERGED | 2026-10-16 | Confirm Booking after GM approval instead of asking for papers again |
| 240 | MERGED | 2026-10-16 | Show model on OEM Billing rows billed from Vehicle Invoices |
| 241 | MERGED | 2026-10-16 | Add full code audit report (Markdown + PDF) |
| 242 | MERGED | 2026-10-16 | OEM Billing Create lead lands on Lead Register as Delivered |
| 243 | MERGED | 2026-10-16 | OEM Extra Support Match dropdown lists CRM files |
| 244 | MERGED | 2026-10-16 | Pack RTO/insurance cuts shrink dealer Additional, not payable |
| 245 | MERGED | 2026-10-16 | Show billed DV on pack units and OEM Billing |
| 246 | MERGED | 2026-10-16 | Keep pack Unit 1 on its own price; no Additional cap |
| 247 | MERGED | 2026-10-16 | Keep available vs billed body and per-unit delivery dates |
| 248 | MERGED | 2026-10-16 | Pack Extra Support units, billed-date scheme, and per-unit Cx Demand |
| 249 | MERGED | 2026-10-16 | Per-unit Cx Demand, Additional, and delivery dates on same-order packs |
| 250 | MERGED | 2026-10-16 | Owner can edit Additional (Dealer) when Cx Demand is locked |
| 251 | MERGED | 2026-10-16 | Match OEM Extra Support to selected pack units |
| 252 | MERGED | 2026-10-17 | Give each pack unit its own delivery, docs, and payments |
| 253 | MERGED | 2026-10-18 | Keep OEM billed files unlocked until desk Marks Delivered |
| 254 | MERGED | 2026-10-18 | Match each pack Extra Support OEM claim to one unit |
| 255 | MERGED | 2026-10-18 | Closed-lead plate edits and per-unit Tally invoices |
| 256 | MERGED | 2026-10-18 | Restore Accounts Dashboard so receipts and Tally can be uploaded |
| 257 | MERGED | 2026-10-19 | Hide deal-verify mismatch from executives |
| 258 | MERGED | 2026-10-19 | Open uploaded deal sheets and replace cancelled OEM chassis |
| 259 | MERGED | 2026-10-19 | Drop cancelled OEM invoices and map the rest of Coulson |
| 260 | MERGED | 2026-10-21 | Yard motor/battery numbers and executive KYC that owner can approve |
| 261 | MERGED | 2026-10-21 | Need to order is executive-scoped — no more everyone seeing every deal |
| 262 | MERGED | 2026-10-23 | Fix OEM billing sync and tab Refresh buttons |
| 263 | MERGED | 2026-10-23 | Restore B2C/B2B and KYC docs on create lead |
| 264 | MERGED | 2026-10-24 | Fix OEM invoice dates so 14 Oct matches Coulson |
| 265 | MERGED | 2026-10-24 | OEM Invoice List sync plus inventory Sold and Received tabs |
| 266 | MERGED | 2026-10-26 | Keep rebilled chassis and cut dealer discount for real RTO and insurance |
| 267 | MERGED | 2026-10-28 | Record the CRM audit baseline without changing behaviour |
| 268 | MERGED | 2026-10-28 | Stop booking calls after pickup or three misses, and call once for a Google review |
| 269 | MERGED | 2026-10-28 | One Claims page, with the three old screens one click away |
| 270 | MERGED | 2026-11-02 | Make search, saves and forms easier to use |
| 271 | MERGED | 2026-11-02 | Fix refund, lead access, variant change, India dates, documents and sheet bugs |
| 272 | MERGED | 2026-11-12 | Move the vehicle copy to a new variant even when Price Master has no row for it |
| 273 | MERGED | 2026-11-05 | Compress uploaded documents before storing them in MongoDB |
| 274 | MERGED | 2026-11-05 | OEM Billing: never match a different vehicle model; resolve reviews by choice |
| 275 | MERGED | 2026-11-05 | OEM Billing: replace a wrong-model chassis, manual link to any open lead |
| 276 | MERGED | 2026-11-05 | Lead: live built→billed body banner; Model + Variant dropdown editor |
| 277 | MERGED | 2026-11-12 | Join claim chassis and show when Euler is asking |
| 278 | MERGED | 2026-11-12 | Import new OEM models, prices, and schemes |
| 279 | MERGED | 2026-11-13 | Add the Workshop Desk to the sales app |
| 280 | MERGED | 2026-11-13 | Connect Service Coulson with a pasted session |
| 281 | MERGED | 2026-11-13 | Restore Service Coulson login id and password |
| 282 | MERGED | 2026-11-13 | Pull only Gmail that names one request number |
| 283 | MERGED | 2026-11-13 | Read the request mail trail and group parts by request |
| 284 | MERGED | 2026-11-13 | Match each request to its Gmail invoice and who is holding it |
| 285 | MERGED | 2026-11-13 | Scroll the service desk and read payment proofs |
| 286 | MERGED | 2026-11-14 | Separate same-name customers when OEM mobiles differ |
| 287 | MERGED | 2026-11-16 | Fill model price from OEM billing and allow B2B on the lead |
| 288 | MERGED | 2026-11-16 | Write each chassis the exact body Coulson billed |
| 289 | MERGED | 2026-11-16 | Keep typed RTO, insurance, and GSTIN when a model price is filled |
| 290 | MERGED | 2026-11-16 | Replace a sibling DV label with the body that chassis was billed as |
| 291 | MERGED | 2026-11-16 | Load November 2026 retail consumer scheme |
| 292 | MERGED | 2026-11-16 | Hide a confirmed variant question everywhere |
