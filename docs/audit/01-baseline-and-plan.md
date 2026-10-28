# Baseline and audit plan

Date: 27 October 2026 (IST).
Code inspected: `main` at `61b1ba8`.
Open work not in this baseline: pull request 266 (`cursor/oem-rebill-chassis-rto-996c`) keeps a rebilled chassis and makes real RTO and insurance reduce Additional (Dealer) instead of customer payable. It is not merged.

## 1. Architecture

One dealership CRM. Staff use a phone or a desktop browser. There is no separate native app in this repository’s main path (a native-shell branch exists and is not this baseline).

```
Staff browser
  React (Create React App) in frontend/
  Cloudflare Worker in frontend/worker.js serves the built site
        |
        | HTTPS, JWT in the Authorization header
        v
FastAPI in backend/server.py  (~18,967 lines, about 234 route handlers)
  commercial.py     price, scheme, payable, margin
  oem_sync.py       Coulson sold / invoice / chassis stamp
  coulson.py        Coulson HTTP client
  oem_claims.py     OEM claim match
  auth.py           login, roles, JWT
  gsheets.py        one-way Google Sheet mirror
  botspace.py       WhatsApp
  exotel.py         phone calls and deal-verify prompts
  insurance_mis.py  insurer statement upload
  tally_pack.py     Tally ZIP check
        |
        v
MongoDB (Motor). No SQL migrations. Indexes are created on startup.
Google Sheets and Coulson are external. They are not the system of record.
```

The old portal is still in the repo: `index.html` and `assets/js`. `README.md` still tells staff to set an Apps Script URL. The `.gs` source is not in this repo. Treat that portal as legacy until a search proves a live deploy still points at it. It was not deleted in this phase.

### Roles (from `backend/auth.py`)

| Role stored | Who they are |
|---|---|
| owner | Owner. Earnings, price master, user passwords, reset |
| tl | Showroom Admin. Whole showroom, money desk, delivery |
| team_lead | Working team leader. Own team. Not the money desk |
| sales_gm | Sales GM. Whole showroom deals. Not meant to post cash |
| executive | Sales executive. Own leads |
| accounts | Accounts. Payments, insurance, not the sales funnel |
| asm, rm | Field managers. View, not the money desk |
| oem_finance | Outside OEM finance reader. A short allow-list of report routes only |

Hiding a menu item is not the security control. `auth.py` states that many GET routes have no role check of their own. An outside OEM finance user is denied by a central allow-list. A logged-in staff role is not.

### Staff screens

71 page files under `frontend/src/pages/`. Routes are in `frontend/src/App.js`. The daily path is the lead register and the lead drawer (price, scheme, payment, delivery). Around that sit bookings, approvals, allocation, payments, finance, insurance, deliveries, OEM billing, claims, scheme master, dashboards, and owner reports.

### Persistence

Mongo collections are created by use, not by a migration folder. Startup creates indexes for leads, payments, audit log, OEM chassis, and several registers (`backend/server.py` near the startup handler). `leads.leadId` is indexed but not unique. There is no foreign-key layer. A lead id is a string copied onto payments, documents, and claims.

Backup and restore are not described by a tested script in this repo. The June go-live checklist still has backup as unchecked.

## 2. What was checked on 27 October

| Check | Result |
|---|---|
| Read `main` layout, routes, roles, startup indexes, and the public share and refund functions | Done. Evidence is in FINDINGS.md |
| Compared the 16 October critical findings with the current functions | Four critical items are still in the code. See AUD-001 to AUD-004 |
| Full backend pytest on this commit | Not run |
| Frontend production build and ESLint on this commit | Not run |
| Live MongoDB, live Coulson, live Google Sheet | Not used. No production data was read or changed |
| 14 backend tests and 15 frontend tests on the unmerged pull request 266 branch | Passed earlier the same day. They do not cover this audit’s findings |

The 16 October audit reported 1,277 backend tests passed, 59 failed, and 17 errors, and 130 frontend tests passed. That run is 11 days old. It is not repeated here, so those fail counts are not treated as today’s result.

## 3. Module status after phase 1

| Module | Status |
|---|---|
| Login and roles | Inventoried. Plaintext password storage confirmed in code. Full permission matrix not re-tested |
| Lead register and drawer | Inventoried. Search crash path still present in code. Drawer behaviour not click-tested |
| Price, scheme, payable | Engine located in `commercial.py`. Not re-certified against the scheme circular this phase |
| Payments and refunds | Refund cap still uses a single-vehicle price. See AUD-001 |
| Delivery and OEM chassis | Invoice List is the billed source on `main` (pull request 265). Rebill stamp is pull request 266, not merged |
| OEM Coulson sync | Code path mapped. Live sync not run |
| WhatsApp and Exotel | Not re-tested. 16 October webhook findings not re-checked |
| Google Sheets | Not re-tested |
| Public share board | Code still returns every customer name without login. See AUD-003 |
| Dashboards and owner earnings | Screens exist. Totals not re-measured |
| Legacy `assets/js` | Present. Not proven unused at runtime outside this repo |

## 4. Phases

| Phase | Work | Gate |
|---|---|---|
| 1 | This baseline | Done. Waiting for approval before code changes |
| 2 | Requirements matrix from PRD, go-live docs, tests, and later decisions | No production change |
| 3 | Static review of auth, money, and OEM paths | No production change |
| 4 | Reproduce P0/P1 with tests. Fix only reproduced defects whose rule is already decided | Pause on share-board names, password storage, and the reset tool |
| 5 | Page-by-page UX notes and a short public-source benchmark | No new features yet |
| 6 | Remediation plan with owner decisions called out | |
| 7 | Small fixes, retest | |
| 8 | Low-risk UX: labels, empty states, fewer duplicate clicks | No removal of owner controls |
| 9 | Regression of touched flows | |
| 10 | Release checklist. Honest gaps stay listed | |

Final documents named in the audit brief (traceability matrix, UX audit, OEM report, security report, performance report, benchmark, test report, changelog, staff guide, release checklist) are written as those phases finish. They are not stubbed here.

## 5. First remediation tasks, after approval

1. AUD-001. Add a test that a two-vehicle order cannot refund money the customer still owes. Point the refund at the same payable the receipt screen uses.
2. AUD-005. Escape lead-search text so a `+` in a mobile number does not return HTTP 500. Debounce is a separate UX change.
3. Leave AUD-002, AUD-003, and AUD-004 for an owner decision. They are real, and changing them changes a public page, stored passwords, or a reset tool.
4. Do not split `server.py`, delete `assets/js`, or redesign screens in the first fix pass.
