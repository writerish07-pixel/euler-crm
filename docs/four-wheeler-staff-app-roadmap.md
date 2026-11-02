# Four-wheeler dealership: internal staff app roadmap

Date: 2 November 2026.
Builds on:
- [four-wheeler-dealership-sales-study.md](four-wheeler-dealership-sales-study.md): what the business does
- [four-wheeler-notification-roadmap.md](four-wheeler-notification-roadmap.md): who is told what, at every step
- [four-wheeler-automation-roadmap.md](four-wheeler-automation-roadmap.md): what the system does instead of people

Purpose: a plan to build one internal app used **only by dealership staff**. It covers what to decide first, the app's shape, technology, security, screens per role, build phases, team, testing, rollout and running costs.

Customers do not log in. They only receive messages (WhatsApp, SMS, email) and, where needed, one-time secure links (for example to upload a document or pick a delivery slot). Those links open a single page, not the app.

---

## Contents

1. [Decisions to make first](#1-decisions-to-make-first)
2. [Build, buy or customise](#2-build-buy-or-customise)
3. [Shape of the app](#3-shape-of-the-app)
4. [Technology](#4-technology)
5. [Security for a staff-only app](#5-security-for-a-staff-only-app)
6. [Core data model](#6-core-data-model)
7. [Screens by role](#7-screens-by-role)
8. [Common features every screen uses](#8-common-features-every-screen-uses)
9. [Build phases](#9-build-phases)
10. [Team](#10-team)
11. [How the work is run](#11-how-the-work-is-run)
12. [Testing](#12-testing)
13. [Data migration](#13-data-migration)
14. [Rollout and training](#14-rollout-and-training)
15. [After go-live](#15-after-go-live)
16. [Running costs to plan for](#16-running-costs-to-plan-for)
17. [Risks](#17-risks)
18. [Timeline at a glance](#18-timeline-at-a-glance)
19. [First 30 days checklist](#19-first-30-days-checklist)

---

## 1. Decisions to make first

Each has a recommended default. Change it if your situation differs.

| # | Decision | Options | Recommended default |
|---|---|---|---|
| D1 | Who builds it | In-house team · software agency · freelancers · customise an existing CRM | Agency or small in-house team building a custom app, with you (or your GM) as product owner. See §2 |
| D2 | Number of branches and users at launch | — | Design for many branches from day one, even if you start with one |
| D3 | Phones | Company phones · staff's own phones | Company Android phones for floor staff (consultants, delivery, yard, PDI); own phones allowed for managers with device registration |
| D4 | Platforms | Android · iPhone · desktop browser | Android app + desktop web app first; iPhone later if managers need it |
| D5 | Hosting | Cloud in India · own server | Cloud in an Indian region (keeps data in India; reliable backups) |
| D6 | OEM brand(s) | — | Matters for DMS file formats, scheme types and price list structure; list them before design |
| D7 | Accounting software | Tally · other | Tally (most common); confirm version |
| D8 | WhatsApp provider | Any Meta-approved Business API provider | Pick one in Phase 0; templates need Meta approval time |
| D9 | Telephony | Cloud calling provider · existing phones | Cloud calling in Phase 3 |
| D10 | Language | English · Hindi · regional | English first; labels ready for translation |
| D11 | Who owns the masters | — | One named person each for price list, schemes, tax rules; a second person approves changes |
| D12 | Budget and launch date | — | Fix a budget for Phase 0–1 first; later phases funded after the pilot proves value |

---

## 2. Build, buy or customise

| Option | Good | Bad | Fits when |
|---|---|---|---|
| **Custom build** | Fits your exact process, gates, notifications, approvals; you own the code and data | Takes months; needs a reliable team; you maintain it | You want the flow in the three documents exactly, and plan to grow branches |
| **Customise a general CRM** (Salesforce, Zoho, LeadSquared, HubSpot and similar) | Faster start for leads, tasks, calls; mature mobile apps | Per-user licence cost forever; car-specific parts (on-road price, allocation, chassis, gates, claims, registration) still need custom work; limits on deep changes | Small team, lead management is the main need |
| **Dealer software from a vendor** (dealer management products) | Car-specific features ready | Your process bends to theirs; integration and customisation limits; vendor lock-in | You prefer a standard product over a custom flow |
| **Low-code platforms** | Quick screens | Hard to keep fast, secure and correct as rules grow; money logic gets messy | Prototypes only |

**Recommendation:** custom build. The value is in your gates, calculations, notifications and approvals, which general CRMs do not provide out of the box. Before building, look at one or two dealer products for 2 weeks to borrow good ideas.

---

## 3. Shape of the app

One system, two front ends, one back end.

```
                 ┌──────────────────────────────────────────────┐
Staff phone ───► │  Mobile app (Android first)                  │  floor staff: consultants, TL,
(company/own)    │  tasks · leads · scan · camera · sign · push │  delivery, PDI, yard, security,
                 └──────────────────────────────────────────────┘  exchange, managers on the move
                 ┌──────────────────────────────────────────────┐
Staff desktop ─► │  Web app (browser)                           │  accounts, sales admin, finance,
                 │  tables · bulk work · reports · masters      │  insurance, registration, managers,
                 └──────────────────────────────────────────────┘  owner, admin
                                   │  secure API (HTTPS)
                                   ▼
                 ┌──────────────────────────────────────────────┐
                 │  Back end                                    │
                 │  API · rules · calculations · gates          │
                 │  event engine · task engine · approvals      │
                 │  notifications · documents · audit log       │
                 │  integration layer (WhatsApp, bank, Tally…)  │
                 └──────────────────────────────────────────────┘
                     │            │             │            │
                 Database    File storage   Job queue   Outside systems
                 (records)   (documents,    (messages,  (WhatsApp, bank,
                             photos)        timers,     Tally, insurers,
                                            imports)    lenders, OEM, Vahan)
```

**Which screens go where**

| Mobile app | Web app |
|---|---|
| My tasks and alerts | Everything on mobile, plus: |
| Leads, follow-ups, click-to-call | Masters (price list, schemes, taxes, users) |
| Walk-in entry | Accounts desk (receipts, matching, refunds, invoices) |
| Test-drive booking and gate scan | Allocation board |
| Quotation and sharing | Registration tracker |
| Discount request and one-tap approval | Claims and reconciliations |
| Booking form with signature | Reports and exports |
| Document capture (camera, scan) | Bulk imports (OEM invoices, leads) |
| Exchange inspection with photos | Incentive calculation |
| PDI and delivery checklists | Audit log |
| Yard scans, gate pass check | Settings (notifications, time limits, approval ladders) |
| Dashboards for managers | |

**Offline:** yard, PDI and delivery bays often have weak signal. Checklists and scans should save on the phone and sync when the connection returns. Money actions (receipts, approvals, invoice) need a live connection.

---

## 4. Technology

A common, well-supported stack so it is easy to hire for and maintain. Any equivalent stack is fine if the team knows it well.

| Layer | Recommended | Why |
|---|---|---|
| Mobile app | React Native (Expo) with TypeScript | One codebase for Android and later iPhone; shares code and skills with the web app |
| Web app | React with TypeScript | Same language as mobile |
| Back end | Node.js (NestJS) with TypeScript, or Python (FastAPI) | Mature, easy to hire |
| Database | PostgreSQL | Money, stock and bookings need strict relations, transactions and unique rules (for example one chassis, one allocation) |
| Job queue and timers | Redis-based queue | Messages, escalations, reminders, imports, reconciliations |
| File storage | S3-compatible object storage | Documents and photos, with encryption and access-controlled links |
| Push notifications | Firebase Cloud Messaging | Standard for Android (and iPhone) |
| Search | PostgreSQL full-text first; a search engine later if needed | Find by mobile, name, chassis, booking number |
| PDFs | Server-side PDF generation from templates | Quotations, invoices, forms |
| Hosting | A major cloud provider's India region | Data in India; managed database backups |
| Monitoring | Error tracking + uptime + logs | Know about problems before staff call |
| Source control and builds | Git with automatic tests and deployment | Safe, repeatable releases |

**Rules for the code**
- All money in whole paise (integers), never floating numbers.
- All rules (discount limits, time limits, tax rates) in masters/settings, not hard-coded.
- Every write goes through the API with role and branch checks. Hiding a menu is never the security.
- Every important change writes an event and an audit entry.
- Tests for every calculation and gate.

---

## 5. Security for a staff-only app

| Area | Measure |
|---|---|
| Who can log in | Only staff created by an admin. No self sign-up |
| Login | Mobile number + OTP, then a personal PIN or fingerprint on the phone; desktop login with OTP |
| Device control | Each phone registered to a user; new device needs admin approval; admin can log out or block a device remotely |
| Leaving staff | Disable user in one click: all sessions ended, tasks and leads reassigned |
| Roles and branches | Access decided by role and branch on the server for every request (read and write) |
| Personal data | PAN and Aadhaar masked on screen (last 4 digits); full view only for roles that need it, and logged |
| Screenshots | Blocked on sensitive screens on Android (KYC, payments) |
| Exports | Only for permitted roles; every export logged; files watermarked with user and time |
| Sessions | Auto-lock after inactivity; short session on desktop |
| Network | HTTPS only; optional restriction of desktop access to showroom networks for accounts/admin roles |
| Data storage | Encrypted database and file storage; daily backups; tested restore |
| Customer links | One-time, expiring, single-purpose links (upload a document, pick a slot); no login |
| Audit | Every login, view of sensitive data, edit, approval and export recorded |
| Privacy law | Consent for messages and call recording; retention limits; process for a customer's data request under the Digital Personal Data Protection Act, 2023 |
| App distribution | Not on the public Play Store listing. Android: managed Google Play private app or direct install through device management; iPhone (later): Apple Business Manager custom app **(check current Apple and Google options)** |
| Testing | Security test (penetration test) before go-live and yearly |

---

## 6. Core data model

Main records and how they link. This is the backbone; fields come from the sales study.

```
Branch ─┬─ User (role, branch, devices)
        │
Customer ─┬─ Lead ─┬─ Activity (call, visit, message, note)
          │        ├─ Test drive ── Demo car
          │        ├─ Quotation (versions) ── Discount approval
          │        └─ Exchange evaluation ── Old car
          │
          └─ Booking ─┬─ Booking change
                      ├─ Verification call
                      ├─ Loan file ── Lender
                      ├─ Insurance policy ── Insurer
                      ├─ Accessory order ── Accessory
                      ├─ Payment / receipt / refund
                      ├─ Allocation ── Vehicle (chassis) ── OEM invoice
                      ├─ Invoice ── Credit note
                      ├─ Registration ── HSRP, FASTag, RC
                      ├─ PDI ── Delivery ── Gate pass
                      ├─ Scheme application ── Scheme claim ── OEM credit note
                      ├─ Feedback, Complaint, Referral
                      └─ Cancellation

Masters: Model · Variant · Colour · Price list (versions, dates) · Tax rule · Road-tax rule ·
         Scheme · Accessory · Add-on plan · Lender · Insurer · Lead source · Reasons · Discount limits
Engine:  Event · Task · Approval · Notification · Document · Audit entry · Setting
```

Key rules in the database:
- One customer per mobile number (with links for family or company).
- One active allocation per chassis.
- Payments, invoices and bookings are never deleted, only cancelled with a reason.
- Price list and scheme versions are stored on each quotation and booking, so old deals keep their original numbers.

---

## 7. Screens by role

Each role sees its own home screen: **my tasks, my alerts, my numbers**. The full lists are in the notification roadmap §6.

| Role | Device | Main screens |
|---|---|---|
| Reception | Tablet / mobile | Walk-in entry, today's appointments, consultant availability |
| BDC | Desktop + headset | Lead queue, call screen with script, appointment booking, recycle queue |
| Sales consultant | Mobile | My tasks, my leads, lead detail (timeline), test drive, quotation builder, discount request, booking form with signature, document capture, my bookings with status, my incentive |
| Team leader | Mobile | Team tasks and overdue items, hot leads, approvals, team funnel |
| Sales manager | Mobile + desktop | Approvals, showroom dashboard, allocation approvals, cancellations, escalations |
| Sales head / owner | Mobile + desktop | All-branch dashboard, money summary, big approvals, critical alerts, plain-language report questions (later) |
| Exchange evaluator | Mobile | Evaluation checklist with photos, offer, document checklist |
| Finance desk | Desktop | Loan files board (by stage), lender status, DO, disbursement, payout |
| Insurance desk | Desktop | Quotes, policies, own-policy checks, commission matching |
| Accessories | Mobile + desktop | Upsell call list, orders, fitment jobs, stock |
| Sales admin | Desktop | Booking desk, allocation board, OEM entries, invoice queue (with gate status), rebilling |
| Stock yard | Mobile | Receive car (scan, photos), yard location, movements, ageing, stock audit by scan |
| Accounts | Desktop | Receipts and matching, balances, refunds, invoices, Tally sync status, claims, reconciliations |
| Registration | Desktop + mobile | Registration tracker by stage, documents pending, HSRP, RC handover |
| PDI | Mobile | PDI list, checklist with photos and chassis scan |
| Delivery | Mobile + desktop | Delivery calendar, delivery gate checklist, handover checklist, photos |
| Customer relations | Desktop | Verification calls, feedback queue, complaints |
| Security | Mobile | Gate pass scan, test-drive out/in scan |
| Marketing | Desktop | Source and campaign reports, review replies |
| HR | Desktop | Users, incentive rules and results |
| Admin | Desktop | Masters, users and devices, settings, notification rules, audit log |

---

## 8. Common features every screen uses

| Feature | Detail |
|---|---|
| Global search | By mobile, name, booking number, chassis, registration number |
| Record timeline | Every record shows its full history: events, messages, calls, approvals, documents |
| Inbox | Tasks, approvals and alerts in one place, sorted by time limit |
| Status chips and gate panel | Where a booking stands and what is blocking the next step, with the responsible team |
| Camera and scanner | Documents, photos, chassis plate, QR codes |
| Signature | On-screen signature or e-sign link |
| Share | Send PDF or message by WhatsApp from the app |
| Click-to-call | Calls logged against the record |
| Comments and mentions | Talk about a record inside the app instead of personal WhatsApp groups |
| Filters and saved views | For desktop tables |
| Export | Permitted roles only, logged |
| Notifications | Push, in-app, and WhatsApp/SMS for critical items |
| Offline save | For checklists and scans |

---

## 9. Build phases

The phases line up with the automation roadmap (§12 there).

### Phase 0: Discovery and design (4 weeks)

| Work | Output |
|---|---|
| Walk through every process with each department head, using the three documents | Confirmed process and notification lists, with your local differences |
| Collect real samples: price list, scheme circulars, booking form, invoice, Vahan papers, OEM files, Tally setup | Masters and document templates |
| Decide D1–D12 | Signed decisions |
| Data model and API outline | Technical design |
| Wireframes for main screens (consultant mobile, accounts desk, allocation board, manager approvals) | Clickable prototype |
| Test the prototype with 3–5 real staff | Changes before coding |
| Set up code repository, environments (development, testing, live), monitoring | Ready to build |
| Start WhatsApp provider onboarding and template approval | Templates ready by Phase 1 |

### Phase 1: Pilot app, core sales flow (10–12 weeks build + 4 weeks pilot)

Goal: one showroom runs every sale from enquiry to delivery in the app.

| Sprint (2 weeks) | Delivered |
|---|---|
| 1 | Login, users, roles, branches, devices; masters (models, price list, taxes, schemes, reasons); audit log |
| 2 | Customers and leads; manual and web-form lead capture; duplicate check; auto-assignment; activities; follow-up tasks; walk-in |
| 3 | Event, task and notification engine; escalations; inbox; push notifications |
| 4 | Test drives and demo cars; quotation engine (on-road price, offers, EMI); PDF and WhatsApp share; discount approvals |
| 5 | Booking form with signature; booking changes; verification task; exchange evaluation (basic); finance and insurance records (manual entry) |
| 6 | Stock (manual and file import); allocation board with chassis lock; payments recording and balance; cash block |
| 7 | Gates; invoice and Form 21 generation; registration tracker; accessories orders and fitment |
| 8 | PDI and delivery checklists; gate pass; feedback messages; cancellation with reversals; dashboards and daily summary |

Then:
- **Testing and fixes:** 2 weeks.
- **Pilot:** 4 weeks in one showroom (see §14).
- **Exit test for Phase 1:** every booking in the pilot showroom goes through the app; no paper booking forms; daily report comes from the app.

### Phase 2: Money and documents (12 weeks)

- Bank feed matching, virtual account or UPI per booking, automatic receipts.
- Tally integration.
- Document capture with OCR; name match checks; generated Form 20/34, 29/30, 60; e-sign.
- Scheme claims, proof packs, credit-note matching.
- Lender payout and insurer commission reconciliation.
- Incentive engine and live tracker.
- Complaint tickets; referral tracking; renewal and anniversary messages.
- QR gate pass, demo-car gate scans, scan-based stock audit; offline checklists.
- Roll out to remaining branches during this phase.

### Phase 3: Outside integrations (12 weeks)

- Cloud telephony.
- Lead portals, Google and Meta lead forms.
- PAN, GSTIN, licence, RC and challan checks.
- E-invoice.
- Insurer, lender, OEM DMS, Vahan and FASTag connections, as access allows.
- Refund payouts through the bank.
- iPhone app if needed.

### Phase 4: AI and optimisation (ongoing)

- Call summaries, WhatsApp assistant, verification and feedback bots, lead scoring, demand forecast, anomaly alerts, report questions in plain language.

---

## 10. Team

### For Phase 0–1

| Role | Count | Responsibility |
|---|---|---|
| Product owner (you or your GM) | 1 (part-time, about a day a week, more in Phase 0) | Decides priorities, approves designs, accepts each sprint |
| Process champions (one per department) | 5–8 (a few hours a week) | Explain real work, test screens, train others |
| Business analyst / project manager | 1 | Turns processes into clear requirements; runs sprints |
| UI/UX designer | 1 (heavy in Phase 0, light later) | Screens that are fast to use on a phone |
| Back-end developers | 2 | API, rules, calculations, engines, integrations |
| Front-end / mobile developers | 2 | Mobile and web apps |
| QA tester | 1 | Test cases, especially money and gates |
| DevOps (part-time) | 0.5 | Hosting, backups, monitoring, releases |

### After go-live

- 1–2 developers for fixes and improvements.
- 1 in-house **app admin** at the dealership: users, devices, masters, first-line support.

### If an agency builds it

- The code, database and cloud accounts must be in **your name**.
- Contract includes source code handover, documentation, and a support period with response times.
- Pay against delivered and accepted sprints, not dates.

---

## 11. How the work is run

- Two-week sprints. At the end of each, a demo to the product owner and champions on real-looking data.
- One shared list of features and bugs, ordered by the product owner.
- Every feature has an acceptance test written in plain words, for example "Invoice button stays disabled while balance > 0; panel shows 'Accounts: balance ₹12,000 pending'".
- Weekly 30-minute review with you: progress, decisions needed, risks.
- Changes to masters and rules are made in settings, not by asking developers.

---

## 12. Testing

| Type | What |
|---|---|
| Calculation tests | Every price, tax, TCS, road tax, EMI, balance, refund, margin and incentive rule, with real examples from your price list |
| Gate tests | Each gate blocks and releases correctly |
| Permission tests | Each role sees and changes only what it should, per branch, checked on the server |
| Notification tests | Each event sends the right tasks to the right people with the right time limits |
| End-to-end runs | Full journeys: cash deal, loan deal, exchange deal, corporate offer, booking change, cancellation after invoice, delivery with balance approval |
| Device tests | Low-end Android phones, weak network, offline save |
| Load test | Peak days (festival deliveries, month-end) |
| Security test | Independent penetration test before go-live |
| User acceptance | Champions run their real day in the testing copy before each release |

---

## 13. Data migration

| Data | Source | Approach |
|---|---|---|
| Masters (models, prices, schemes, taxes, lenders, insurers) | OEM price lists, circulars, your sheets | Entered and checked in Phase 0–1 |
| Users | HR list | Created by admin |
| Open leads | Sheets, current CRM, DMS | Import with duplicate check; assign owners; drop very old dead leads |
| Open bookings (not yet delivered) | Booking files, accounts | Import with receipts and allocation; each checked by the consultant and accounts |
| Stock | DMS / OEM invoices / yard list | Import, then physical scan to confirm |
| Past customers (delivered) | DMS, accounts | Import basic details for referrals, renewals and upgrades |
| Pending claims | Accounts | Import open claim lines |

Rule: anything imported is marked "migrated" and checked once by its owner. Start the new app on a clean cut-over date (for example the 1st of a month) for new leads and bookings.

---

## 14. Rollout and training

### Pilot (one showroom, 4 weeks)

1. Week 0: train champions first; they help train others.
2. Short role-based training (30–60 minutes each) on the real app with practice data.
3. One-page guide per role; short videos in the app.
4. Daily 15-minute check-in during the pilot: problems, fixes, wins.
5. A developer or analyst on site for the first week.
6. Keep paper as backup only in the first week; then stop it.

### Make the app the only way

- Receipts are issued only from the app.
- Incentives are calculated only from app data.
- Discounts count only if approved in the app.
- Deliveries happen only with an app gate pass.
- Daily meetings use the app dashboard, not printed sheets.

### Branch rollout

- After the pilot passes, roll out branch by branch (one every 1–2 weeks) with the same training pattern.

---

## 15. After go-live

| Area | Practice |
|---|---|
| Support | In-app "report a problem" with screenshot; app admin handles first-line; developers for bugs with agreed response times |
| Releases | Every 2 weeks; urgent fixes any time; release notes in the app |
| Monitoring | Errors, slow screens, failed messages, failed integrations, overdue task counts |
| Backups | Daily; restore tested every quarter |
| Masters | Updated by owners with approval; price and scheme changes on effective dates |
| Rule review | Every quarter: tax and transport rule changes, **(verify)** items in the documents, time limits, approval limits |
| Improvement | Monthly review of the success measures (automation roadmap §15) and staff suggestions |

---

## 16. Running costs to plan for

Ask vendors for current prices; these are the cost heads.

| Cost head | Notes |
|---|---|
| Build (Phase 0–4) | Team or agency cost per phase |
| Cloud hosting | Servers, database, storage, backups; grows with users and documents |
| WhatsApp Business API | Provider fee plus Meta per-conversation charges |
| SMS | OTPs and fallback messages |
| Telephony | Per-minute and recording storage (Phase 3) |
| Verification services | Per check (PAN, GSTIN, RC, licence) |
| E-sign | Per signature |
| E-invoice provider | Per invoice or yearly plan |
| Tally connector | If a paid connector is used |
| Push notifications | Usually free at this scale |
| Device management | Per company phone, if used |
| Company phones | Floor staff devices |
| Security test | Before launch and yearly |
| Support and maintenance | Usually a monthly retainer after launch |

---

## 17. Risks

| Risk | What to do |
|---|---|
| Scope grows before the pilot | Phase 1 list is fixed; new ideas go to the list for later phases |
| Staff keep using paper and personal WhatsApp | §14 "make the app the only way"; champions; dashboard-led meetings |
| Wrong calculations in money | Calculation tests from real deals; accounts sign-off before go-live |
| Agency leaves | Code, cloud and data in your name; documentation; source handover in contract |
| Outside integrations not available | Manual entry with proof uploads always works |
| Slow app on cheap phones | Test on low-end devices every sprint |
| Data leak | §5 security measures; least access; logs; penetration test |
| Too many notifications | Priority levels and digests; settings per role |
| Key person dependency (one admin knows everything) | Two trained admins; written procedures |

---

## 18. Timeline at a glance

| Month | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10 | 11 | 12 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Phase 0 Discovery and design | ■ | | | | | | | | | | | |
| Phase 1 Build | | ■ | ■ | ■ | | | | | | | | |
| Phase 1 Test + pilot | | | | ■ | ■ | | | | | | | |
| Phase 2 Money and documents | | | | | ■ | ■ | ■ | | | | | |
| Branch rollout | | | | | | ■ | ■ | ■ | | | | |
| Phase 3 Integrations | | | | | | | | ■ | ■ | ■ | | |
| Phase 4 AI | | | | | | | | | | ■ | ■ | ■ |

About 5 months to a working pilot and about a year to the full system, with a team like §10. A smaller team stretches this; a larger one rarely shortens Phase 0 or the pilot.

---

## 19. First 30 days checklist

- [ ] Name the product owner and one champion per department.
- [ ] Decide D1–D12 (§1), especially who builds it and the budget for Phase 0–1.
- [ ] Shortlist 2–3 agencies or hire the core team; ask for similar past work and references.
- [ ] Collect samples: price list, last 3 scheme circulars, booking form, quotation, invoice, receipts, Form 20/21/22/34, PDI sheet, delivery checklist, OEM stock and retail files, Tally ledger structure.
- [ ] Walk the three documents with department heads; mark what differs in your showroom.
- [ ] Fix discount limits per role, approval ladders and default time limits.
- [ ] Choose the WhatsApp provider; start Meta business verification and template approval.
- [ ] Choose the cloud provider (India region); create accounts in the dealership's name.
- [ ] Decide company phones for floor staff; plan device management.
- [ ] Approve wireframes for the consultant mobile app and the accounts desk.
- [ ] Agree the pilot showroom and pilot start date.
