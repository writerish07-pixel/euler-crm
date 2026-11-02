# Four-wheeler dealership: automation roadmap

Date: 2 November 2026.
Builds on:
- [four-wheeler-dealership-sales-study.md](four-wheeler-dealership-sales-study.md): departments, processes, documents, controls (§ numbers below refer to it as "Study §")
- [four-wheeler-notification-roadmap.md](four-wheeler-notification-roadmap.md): events, notifications, gates (event codes like `C01` refer to it)

Purpose: list everything in the sales side that can be automated, how, and in what order, so the dealership needs fewer people for routine work and makes fewer mistakes. It also says what should stay with a person.

Integrations with outside systems (government portals, banks, insurers, OEM DMS, lead portals) depend on what each provider offers and on licences. Each one is marked **(check availability)**. The CRM must keep working by hand when an integration is down.

---

## Contents

1. [Principles](#1-principles)
2. [Levels of automation](#2-levels-of-automation)
3. [What stays with a person](#3-what-stays-with-a-person)
4. [The foundation: what has to exist first](#4-the-foundation-what-has-to-exist-first)
5. [Automation catalogue, process by process](#5-automation-catalogue-process-by-process)
6. [Error-proofing: checks the CRM runs on every entry](#6-error-proofing-checks-the-crm-runs-on-every-entry)
7. [Calculations the CRM does, so people never do them](#7-calculations-the-crm-does-so-people-never-do-them)
8. [Documents: generate, capture, read, check](#8-documents-generate-capture-read-check)
9. [Reconciliations that run themselves](#9-reconciliations-that-run-themselves)
10. [Outside integrations](#10-outside-integrations)
11. [Where AI helps, and its limits](#11-where-ai-helps-and-its-limits)
12. [Phased roadmap](#12-phased-roadmap)
13. [Impact and effort](#13-impact-and-effort)
14. [Labour saved by role](#14-labour-saved-by-role)
15. [Measuring success](#15-measuring-success)
16. [Risks and safeguards](#16-risks-and-safeguards)

---

## 1. Principles

1. **Enter once, use everywhere.** A customer's name, address, PAN, chassis number or price is typed once. Every form, invoice, policy, Vahan file and message pulls from that record. Most dealership errors come from retyping the same thing into five places.
2. **Pick, don't type.** Models, variants, colours, prices, offers, lenders, insurers and reasons come from masters as dropdowns. Free text only for notes.
3. **Verify at the source.** PAN, GSTIN, mobile number, bank payment, registration and RC are checked against the issuing system where an integration exists, not by eye.
4. **The system calculates.** On-road price, tax, TCS, discount value, balance due, refund, incentive and margin are never worked out by hand.
5. **Events drive work.** Every step in the notification roadmap creates tasks for the next teams automatically. Nobody has to remember to tell anyone.
6. **Gates instead of checking.** The invoice, delivery and refund buttons stay locked until everything they need is done (Notification roadmap §5).
7. **People handle exceptions.** Routine cases flow through. People see only what is stuck, unusual or needs judgement.
8. **Everything leaves a trail.** Every change, approval and message is logged with who and when.
9. **Works on a phone.** Consultants, delivery and yard staff do their part from a phone: photos, scans, signatures, gate scans.
10. **Fallback by hand.** If an outside system is down, staff can enter the data and upload proof; the CRM marks it "manually verified" for later checking.

---

## 2. Levels of automation

| Level | Meaning | Example |
|---|---|---|
| **L0 Manual** | Person does it outside the system | Calculating on-road price in a calculator |
| **L1 Recorded** | Person does it, system records it | Consultant logs a call |
| **L2 Assisted** | System prepares, person checks and clicks | Quotation built automatically; consultant shares it |
| **L3 Automatic with exceptions** | System does it; person handles only failures | Bank payment matched to booking; unmatched ones go to Accounts |
| **L4 Fully automatic** | No person involved | Booking confirmation message to customer |

The target is L3–L4 for routine steps and L2 where judgement or money release is involved.

---

## 3. What stays with a person

Automation supports these; it does not replace them.

| Stays human | Why | What the CRM does to help |
|---|---|---|
| Building a relationship, needs analysis, test drive, negotiation | Trust and persuasion sell cars | Guided question list, suggested variant, live price and margin, competitor comparison |
| Discount and free-item approval | Money and judgement | Shows margin impact and past deals; one-tap approve on phone |
| Exchange car inspection | Physical check | Guided checklist with photos; suggested price |
| Releasing a car with balance pending, invoice cancellation, refunds | High money risk | Approval with full context; cannot be bypassed |
| PDI physical inspection | Physical check | Checklist on phone, mandatory photos |
| Delivery ceremony | Customer experience | Checklist and document kit ready automatically |
| Handling an unhappy customer | Empathy | Full history in one screen |
| Verification calls with doubt | Fraud detection | Script, recording, auto-flag of mismatches |

---

## 4. The foundation: what has to exist first

Nothing in §5 works without these.

| # | Foundation | What it is | Why it matters |
|---|---|---|---|
| F1 | **Masters** | Models, variants, fuels, transmissions, colours; price list with effective dates; tax rules (GST rate per car class, TCS threshold, road tax per state/fuel/price slab, registration and HSRP fees); insurance add-ons; accessories with prices and fitment per variant; extended warranty and RSA plans; schemes with funding split and conditions; lenders; insurers; branches; lead sources; lost and cancellation reasons; discount limits per role | Every calculation and dropdown comes from here. One wrong master value spreads, so masters need versioning, effective dates and an approver |
| F2 | **One customer record** | One customer per mobile number (with family/company links), holding KYC, leads, bookings, payments, documents and messages | Stops duplicates and retyping |
| F3 | **Event engine** | Every step writes an event (the codes in the notification roadmap) | Triggers tasks, messages, gates and reports |
| F4 | **Task engine** | Tasks with owner, time limit, auto-close rule, escalation ladder, working-hours calendar | Turns the notification roadmap into daily work |
| F5 | **Rules and approval engine** | Configurable rules (discount limits, gates, time limits) and approval ladders | Owner can change rules without code |
| F6 | **Document vault** | Every document stored against the customer/booking, with type, status and expiry; masked display of ID numbers | Paperless file, nothing lost |
| F7 | **Message templates** | WhatsApp/SMS/email templates with merge fields, approved WhatsApp Business templates, opt-out handling | Customer messages without typing |
| F8 | **Integration layer** | One place for all outside connections, with retries, logs and manual fallback | Integrations can be added one by one |
| F9 | **Roles and permissions** | Role-based access per branch; field-level masking of PAN/Aadhaar | Security and privacy |
| F10 | **Audit log** | Every create, edit, approval, export | Control and trust |

---

## 5. Automation catalogue, process by process

Columns:
- **Manual today:** what people do by hand.
- **Automate:** what the CRM does instead.
- **How:** method or integration.
- **Errors removed / labour saved.**
- **Phase:** when to build it (see §12).

### 5.1 Lead capture and handling (Study §5.1, events A01–A11)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Copying leads from portals, website, ads, emails into a sheet | Leads flow in automatically with source and campaign | Website forms and webhook; Google and Meta lead-form integrations; lead portal APIs or email parsing **(check availability)**; WhatsApp Business API; missed-call number | No lost leads, no typing, correct source | 1 |
| Checking if the customer already exists | Duplicate check on mobile number; merge into existing record and alert the owner | Rule | No double ownership fights | 1 |
| Deciding who gets the lead | Auto-assignment by round robin, branch, pincode, model, language, workload; returning customers go to their previous consultant | Rules engine | Fair, instant distribution | 1 |
| First call delays | Instant alert to BDC/consultant; click-to-call from the CRM; timer with escalation | Telephony integration (cloud calling) | Faster first response; no forgotten leads | 1 |
| Logging calls by hand | Calls logged automatically with duration and recording | Telephony integration | Accurate activity history | 2 |
| Writing call notes | Call recording transcribed and summarised; next follow-up date suggested | Speech-to-text and AI summary (§11) | Saves typing; better notes | 4 |
| Remembering follow-ups | Next follow-up date mandatory; daily task list; overdue escalation | Task engine | No missed follow-ups | 1 |
| Sending brochure and price | Auto-message with brochure, price list and location on lead creation | Templates + WhatsApp | Instant, consistent | 1 |
| Judging which lead is hot | Lead score from source, activity, test drive, quotation, response speed, budget fit | Rules first; AI model later on past conversion data | Focus on the right leads | 2 rules / 4 AI |
| Reviving old leads | Dormant and lost leads put into drip campaigns and recycle queues automatically; re-assigned if consultant inactive | Rules + campaigns | Revenue from old leads with no manual effort | 2 |
| Lost reason analysis in spreadsheets | Lost reason mandatory from list; dashboards by source, model, competitor, consultant | Reports | Instant insight | 1 |

### 5.2 Walk-ins (Study §5.2, A02)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Paper walk-in register | Tablet or QR self check-in at the door; mobile number pulls existing record | Kiosk / QR form | No missed walk-ins; returning customer recognised | 1 |
| Calling a consultant to the floor | Auto-assign and push alert | Rules | Faster greeting | 1 |
| Counting walk-ins | Walk-in vs gate count reconciliation | Optional footfall counter | Shows unrecorded walk-ins | 3 |

### 5.3 Test drives and demo cars (Study §5.5, B01–B05)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Booking test drives by phone and memory | Slot booking with demo car calendar; customer can self-book online | Calendar | No double booking of a car | 1 |
| Photocopying driving licence | Phone scan; licence details read from image; verification where an integration exists | OCR; DL verification via Parivahan-linked provider **(check availability)** | No test drive without a valid licence | 2 / 3 |
| Paper test-drive form | Digital form with e-signature on phone | E-sign / on-screen signature | Paperless, stored | 1 |
| Gate log of km and fuel | QR on demo car scanned at gate; km and fuel photo | QR + photo | Misuse visible | 2 |
| Tracking demo car location and misuse | Location and km from GPS tracker or connected-car app | Telematics **(check availability)** | Route and speed checks | 3 |
| Feedback after drive | Auto-message with feedback link; quotation task created | Templates + task | Every drive followed up | 1 |
| Demo car service and sell-off timing | Alerts on km/age limits | Rules | Demo fleet kept fresh | 2 |

### 5.4 Quotation and on-road price (Study §5.6, B07)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Calculating on-road price by hand or spreadsheet | One-tap quotation from masters: ex-showroom, GST class, TCS, road tax, registration, HSRP, insurance, FASTag, EW, accessories, offers, discount | Calculation engine (§7) | No wrong tax or price; consistent across consultants | 1 |
| Checking which offers apply | Only eligible offers appear, based on model, date, customer type and proofs | Scheme engine | No wrong offer promised | 1 |
| EMI calculation | EMI table for several tenures and down payments | Calculator; lender rate cards | Accurate EMI | 1 |
| Insurance premium estimate | Live quotes from insurers | Insurer or broker platform API **(check availability)** | Real premium, not a guess | 3 |
| Typing and sending PDFs | Branded PDF with validity date sent by WhatsApp in one tap | Document generator + WhatsApp | Saves time; professional | 1 |
| Old quotations after a price change | Open quotations flagged when price list or scheme changes; consultant gets task to re-send | Event L01/L02 | No customer surprised by old prices | 2 |
| Comparing variants or competitors | Comparison sheet generated from master data | Generator | Faster, consistent pitch | 2 |

### 5.5 Offers and schemes (Study §5.7, L02–L03)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Reading circulars and remembering rules | Scheme master entered once by admin (with approver); applied automatically in quotes | Scheme engine | Same rule for everyone | 1 |
| Checking eligibility proofs | Required proofs listed per scheme; booking cannot be invoiced until proofs uploaded | Gate + document checklist | Fewer rejected claims | 1 |
| Telling team about new offers | Auto-broadcast on scheme creation | Event L02 | Everyone informed | 1 |
| Scheme expiry rush | Alerts 3 days before end with list of eligible open deals | Event L03 | No lost scheme income | 2 |
| Reading circular PDFs into the system | AI reads the circular and pre-fills the scheme form for admin to approve | Document AI (§11) | Faster setup, fewer typos | 4 |

### 5.6 Discount approval (Study §5.8, B08–B10)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Phoning managers for approval | Request in CRM routed by amount to the right level; approve on phone notification | Approval engine | Fast; no verbal approvals | 1 |
| Approver guessing the margin | Approver sees full deal margin (vehicle, schemes, finance, insurance, accessories, exchange) and past discounts on same model | Margin calculation | Better decisions | 1 |
| Free items not counted | Free items valued at cost and added to discount | Rule | True discount visible | 1 |
| Discount beyond approval slipping into invoice | Invoice amount locked to approved deal | Gate | No leakage | 1 |
| Auto-approval for small amounts | Within role limit: no approval needed; optionally auto-approve within guard rails (stock older than X days, month-end target gap) | Rules | Fewer approval requests | 2 |

### 5.7 Exchange (Study §5.9, B06, D08–D10)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Paper inspection sheet | Phone checklist with mandatory photos per section | Mobile form | Complete, evidence stored | 1 |
| Typing RC details | Registration number lookup fills owner, model, year, fuel, hypothecation, insurance validity | RC verification via Vahan-linked provider **(check availability)** | Correct data; spots loan or name mismatch | 3 |
| Checking challans manually | Pending challans fetched | e-Challan lookup provider **(check availability)** | No surprise fines after purchase | 3 |
| Guessing price | Suggested price from valuation tools and own past deals | Valuation API **(check availability)** + own data | Consistent pricing | 3 |
| Form 29/30, delivery note, indemnity by hand | Generated pre-filled from the record; e-signed | Document generator | No mistakes in transfer papers | 2 |
| Chasing old-car documents | Document checklist with reminders to consultant and customer | Task engine | Faster closure | 1 |
| OEM exchange bonus proof | Proof pack assembled automatically for the claim | Claim engine | Fewer rejections | 2 |

### 5.8 Finance (Study §5.10, D01–D05, F04)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Collecting documents by WhatsApp and photocopy | Customer upload link; checklist by income type; quality check (blurred, wrong document) | Upload portal + OCR | Complete files first time | 2 |
| Reading bank statements for income | Income analysis from statements or Account Aggregator consent | Bank statement analyser / Account Aggregator through a licensed provider **(check availability)** | Faster eligibility | 4 |
| Logging files on several lender portals | Push application to lender systems | Lender APIs / DSA platforms **(check availability)** | One entry instead of three | 3 |
| Chasing status by phone | Status updates pulled or entered once; customer informed automatically | Lender API or status entry + templates | Less calling | 2 / 3 |
| DO arrival not noticed | DO uploaded or received triggers Accounts and invoice gate | Event D05 | No delay | 1 |
| Disbursement matching | Bank credit matched to lender and booking automatically | Bank feed matching (§9) | No unmatched receipts | 2 |
| Payout tracking | Payout due computed per loan from lender rate card; overdue alerts | Rules + reconciliation | No lost commission | 2 |

### 5.9 Insurance (Study §5.11, D06–D07)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Typing car and customer details on insurer portal | Policy issued from CRM data | Insurer / broker API **(check availability)** | No wrong chassis or name on policy | 3 |
| Forgetting the lender's name | Lender auto-added if loan exists | Rule | Valid hypothecation | 1 (check) / 3 (API) |
| Own policy accepted without checking | Uploaded policy read; chassis, name, dates and lender checked | OCR + rules | No invalid policy at Vahan | 2 |
| Commission reconciliation | Insurer statement matched policy by policy | Reconciliation (§9) | Missing commissions found | 2 |
| Renewal list | Renewal date stored; reminder 45 days before | Rules + templates | Renewal retention | 2 |

### 5.10 Booking (Study §5.12, C01–C09)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Paper booking form | Digital booking form pre-filled from the quotation; customer e-signs | Form + e-sign | Same price as approved; nothing missing | 1 |
| Booking amount receipt by hand | Payment link or QR per booking; receipt auto-issued on payment | Payment gateway / UPI collection | No fake or missed receipts | 2 |
| Telling 10+ departments | All C01 notifications sent automatically | Event engine | No department forgotten | 1 |
| Entering booking in OEM DMS | Push to DMS, or export file for upload, or screen automation | DMS API / file / RPA **(check availability)** | No double typing | 3 |
| Booking changes | Change form with automatic re-pricing; approval; downstream tasks | Rules + events | Correct price after change | 1 |
| Verification call scheduling | Auto-task to CR; automated voice/WhatsApp confirmation of key terms for simple cases; human call only on mismatch or no answer | Voice bot or WhatsApp confirm (§11) | Fewer calls; fraud flagged | 1 task / 4 bot |

### 5.11 Stock and allocation (Study §5.13, §7, E01–E08)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Typing OEM wholesale invoices into stock | Stock created from OEM invoice file or DMS feed | File import / DMS API **(check availability)** | Correct chassis and engine numbers | 2 |
| Order planning by gut | Suggested OEM order from bookings waiting, pipeline (hot/warm leads by model), stock and ageing | Rules first, forecast later | Less ageing stock, fewer lost sales | 2 / 4 |
| Arrival check on paper | Phone checklist; scan of chassis plate/barcode; damage photos | Scan + photos | No wrong car received | 2 |
| Allocation by spreadsheet | Allocation suggestion: booking queue priority (date, payment status) × oldest matching stock (first in, first out) | Rules | Fair, oldest stock out first, no double allocation | 1 |
| Double allocation | Chassis lock | Rule | Impossible to allot twice | 1 |
| Ageing stock reports | Daily ageing buckets with alerts at 60/90 days; funding interest per car | Rules | Visible cost | 1 |
| Yard location | Yard slot recorded by QR scan | QR | Cars found quickly | 3 |
| Stock audit | Scan-based physical audit against system list | QR / barcode | Fast, accurate audit | 3 |

### 5.12 Payments (Study §5.14, F01–F05)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Customer pays to a common account; Accounts guesses whose money it is | One virtual account or UPI ID per booking; incoming money auto-matched | Bank virtual accounts / payment gateway **(check availability)** | No unidentified receipts | 2 |
| Typing receipts | Receipt created from bank credit; sent to customer | Bank feed + templates | No typing; instant receipt | 2 |
| Cheque status tracking | Cheque marked pending until cleared in bank feed | Bank feed | No delivery on a bounced cheque | 2 |
| Cash limit | Block cash receipt above legal limit per person per transaction **(verify current law)** | Rule | Legal compliance | 1 |
| Balance calculation | Live balance = deal price − all receipts − loan − exchange − approved credit | Calculation | No disputes at delivery | 1 |
| Payment reminders | Auto-reminders to customer at allocation and before delivery | Templates | Less chasing | 1 |

### 5.13 KYC and tax checks (Study §5.15)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Photocopying ID | Phone capture or DigiLocker consent fetch | DigiLocker / OCR **(check availability)** | Clean data, masked storage | 2 / 3 |
| Checking PAN by eye | PAN verified, name matched | PAN verification through an authorised provider **(check availability)** | Correct TCS reporting | 3 |
| Checking GSTIN | GSTIN verified; legal name and address filled | GST verification **(check availability)** | Correct business invoice | 3 |
| Name spelt differently across documents | Name match check across KYC, booking, loan, policy, invoice; mismatch flagged | Fuzzy match rule | No rejected Vahan or loan files | 1 |
| Form 60 when no PAN | Form 60 generated pre-filled | Generator | Compliance | 2 |

### 5.14 Invoice and OEM reporting (Study §5.16, F05–F09)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Checking everything before invoice | Invoice gate checks all items (Notification roadmap §5.2) | Gate | No incomplete invoices | 1 |
| Typing invoice in accounting software | Invoice generated from deal; GST and TCS computed; e-invoice number obtained | Calculation + e-invoice portal API through GST Suvidha Provider **(check availability)** | No tax errors | 2 / 3 |
| Posting to Tally | Invoice, receipts, credit notes pushed to Tally | Tally integration (XML/ODBC or connector) **(check availability)** | No double entry | 2 |
| OEM DMS retail entry | Pushed or exported | DMS API / file / RPA **(check availability)** | No typing; warranty starts correctly | 3 |
| Form 21 by hand | Generated | Generator | Correct chassis and engine numbers | 1 |
| Invoice cancellation | Approval flow; credit note; all downstream tasks created | Approval + events | Full trail | 1 |

### 5.15 Registration and FASTag (Study §5.17–5.18, G01–G07)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Collecting forms on paper | Form 20 and Form 34 generated pre-filled; customer e-signs or signs once | Generator + e-sign where accepted | Correct forms first time | 2 |
| Typing data into Vahan | Data pack ready to copy or upload; screen automation where permitted | Export / RPA **(check availability and legal acceptability)** | Less typing; fewer rejections | 3 |
| Road tax calculation | Calculated from state master | Calculation | Correct tax collected from customer | 1 |
| Tracking registration status | Status steps with dates; delays escalated | Task engine; Vahan status lookup **(check availability)** | Customers informed without calling | 1 / 3 |
| HSRP order and fitment | Order task created on number allotment; fitment photo | Events + photo | No car delivered without plates | 1 |
| FASTag | Issued from CRM data | Issuer bank API **(check availability)** | No typing | 3 |
| RC handover | RC received date, handover date; reminder | Task engine | No forgotten RCs | 1 |

### 5.16 Accessories and add-ons (Study §5.19, D11–D13)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Upsell depends on memory | Auto-task after booking with suggested pack for the variant; customer gets a catalogue link to choose | Event C01 + catalogue | More accessory revenue | 1 |
| Fitment order on paper | Fitment job created on allocation with chassis and items | Event E05 | Right items on right car | 1 |
| Stock check | Accessory stock checked on order; shortage alert | Inventory rule | No delivery delays | 2 |
| Billing | Billed automatically from the order | Generator | No missed billing | 1 |

### 5.17 PDI (Study §5.20, H02–H05)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Paper checklist | Phone checklist per model with mandatory photos | Mobile form | Complete, evidence stored | 1 |
| Chassis number check by eye | Scan of chassis plate compared with invoice and Form 22 | Scan/OCR | Wrong car never delivered | 2 |
| Scheduling | PDI task created from delivery date | Event H01 | No last-minute rush | 1 |
| Defect handling | Fail creates manager task and optional re-allocation | Event H05 | Quick resolution | 1 |

### 5.18 Delivery (Study §5.21, H01–H10)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Delivery slot by phone | Customer picks slot from available bay calendar | Calendar + link | No double booking | 2 |
| Checking readiness | Delivery gate shows ready/not ready with owner of each gap | Gate | No surprises on delivery day | 1 |
| Assembling the document kit | All documents generated and bundled; digital copy sent to customer | Generator | Nothing missing | 2 |
| Delivery note and gate pass on paper | E-signed delivery note; QR gate pass checked by security app | E-sign + QR | Car cannot leave without clearance | 2 |
| Delivery photos shared by staff phones | Photos captured in app; sent with consent; posted to social media queue | App + templates | Consistent experience | 2 |

### 5.19 After delivery (Study §5.22, I01–I11)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Feedback calls by staff | WhatsApp survey first; call only for no response or low score | Templates + rules; voice bot later | Fewer calls; every customer covered | 1 / 4 |
| Asking for Google reviews | Review link sent automatically after a good score | Rule | More reviews | 1 |
| Referral tracking | Referral link per customer; new lead auto-linked; reward triggered on retail | Link + rules | Referrals credited correctly | 2 |
| Birthday, anniversary, upgrade reminders | Automatic messages and BDC tasks | Scheduler | Repeat business | 2 |

### 5.20 Cancellation and refund (Study §5.23, J01–J04)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Calculating refund | Refund computed from booking terms and receipts | Calculation | Correct refund | 1 |
| Telling every department | J02 tasks sent to all | Event engine | Nothing left open (insurance, loan, Vahan) | 1 |
| Refund payment | Refund to original source via bank payout after approval | Bank payout API **(check availability)** | Faster, traceable | 3 |
| Reversing incentives | Automatic reversal | Rule | No disputes | 1 |

### 5.21 Complaints (Study §5.24, K01–K04)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Complaints in notebooks | Ticket from any channel (WhatsApp keyword, form, call); auto-routed by category | Ticketing + rules | None lost | 2 |
| Chasing resolution | Time limits and escalation | Task engine | Faster closure | 2 |
| Detecting complaints in messages | Negative WhatsApp messages or reviews flagged | AI sentiment (§11) | Early warning | 4 |

### 5.22 OEM scheme claims (Study §8, F08, I08–I09)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Building claim lists by hand | Claim lines generated per retail from applied schemes | Claim engine | No missed claims | 2 |
| Collecting proofs | Proof pack assembled from the document vault; missing proofs flagged before invoice | Gate + vault | Fewer rejections | 2 |
| Matching OEM credit notes | Credit notes matched to claim lines; short-paid and rejected flagged | Reconciliation (§9) | Lost money found | 2 |
| Claim deadline tracking | Alerts before deadline | Scheduler | No expired claims | 2 |

### 5.23 Incentives (Study §8.5, L06)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Monthly spreadsheet calculation | Incentive computed from rules: retails, model slabs, targets, penetration, discount discipline, cancellations | Rules engine | No disputes; same rule for all | 2 |
| Staff not knowing where they stand | Live incentive tracker for each consultant | Dashboard | Motivation | 2 |

### 5.24 Reports and MIS (Study §13, L04–L05)

| Manual today | Automate | How | Errors removed / labour saved | Phase |
|---|---|---|---|---|
| Daily reports compiled by staff | Live dashboards per role; daily summary on WhatsApp/email at a set time | Reports + scheduler | Hours saved daily; one version of truth | 1 |
| OEM daily reporting | Export in OEM format or push | File / API **(check availability)** | No retyping | 3 |
| Month-end reports | Generated automatically | Reports | Instant month close view | 2 |

---

## 6. Error-proofing: checks the CRM runs on every entry

| Field / step | Check |
|---|---|
| Mobile number | 10 digits, starts 6–9 (India); OTP verification on self-registration; duplicate check |
| Email | Format check |
| Name | Matches across KYC, booking, loan, insurance, invoice, Form 20 (fuzzy match; flags differences) |
| PAN | Format (5 letters, 4 digits, 1 letter); verification where integrated; name match |
| Aadhaar | Never store full number in open view; mask to last 4 digits; store only what law and consent allow |
| GSTIN | Format (15 characters, state code, PAN inside); verification where integrated |
| Pincode | 6 digits; maps to city, state, RTO |
| Chassis number (VIN) | 17 characters, no I, O or Q; must exist in stock; scan match at PDI |
| Engine number | Must match stock record |
| Registration number | State format; unique |
| Model / variant / colour | From master only; colour must exist for that variant |
| Price | From price list effective on that date; cannot be typed |
| Offers | Only eligible offers selectable; combination rules enforced |
| Discount | Within role limit or approved; cannot exceed approved amount |
| Payment amount | Sum cannot exceed deal price without an "excess" flag; refund only to source |
| Cash | Block above legal limit **(verify)** |
| Dates | Delivery date not before invoice; policy start not after registration; booking date not in future |
| Insurance | Chassis, name and lender on policy match the booking |
| Loan | Lender on DO matches lender on invoice and policy |
| Documents | Required documents per step present before the gate opens; expiry checked (licence, policy) |
| Approvals | Editing an approved deal re-opens approval |
| Deletion | No hard delete of bookings, payments or invoices; cancel with reason only |
| Back-dated entries | Allowed only with permission and reason; logged |

---

## 7. Calculations the CRM does, so people never do them

| Calculation | Inputs |
|---|---|
| On-road price | Price list, GST class, TCS rule, road tax master, fees, insurance, add-ons, accessories, offers, discount |
| GST split | Rate from the car's class (engine size, length, fuel) **(verify current rates)** |
| TCS | 1% where value above ₹10 lakh **(verify current law and base)** |
| Road tax | State, fuel, price slab, ownership type (individual / company), EV concessions |
| EMI | Loan amount, rate, tenure |
| Discount value | Cash discount + free items at cost |
| Deal margin | Vehicle margin + scheme income + finance payout + insurance commission + accessories + EW + exchange margin − discount − free items |
| Balance due | Deal price − receipts − loan − exchange − approved credit |
| Refund | Receipts − deductions per booking terms |
| Exchange settlement | Agreed value − old loan payoff − pending challans |
| Scheme claim amount | Per scheme rule and funding split |
| Lender payout due | Lender rate card × loan amount (slabs) |
| Insurance commission due | Insurer rate × premium (by product) |
| Incentive | Incentive rules |
| Stock interest | Funding rate × days in stock × car cost |
| Stock ageing | Today − received date |
| Time-limit breaches | Task created time vs working calendar |

---

## 8. Documents: generate, capture, read, check

### 8.1 Generated automatically (pre-filled from the record)

Quotation · proforma invoice · variant comparison · test-drive form · booking form · receipts · deal sheet · exchange purchase agreement · Form 29 / Form 30 · delivery note for old car · indemnity · Form 60 · tax invoice · Form 21 · Form 20 and Form 34 (pre-filled) · accessories invoice · PDI report · delivery note · gate pass · refund voucher · credit note · cancellation letter · TCS certificate data · claim proof pack · welcome kit.

### 8.2 Captured on phone

Photos and scans with automatic cropping and quality check: KYC, licence, old RC, insurance, PDI photos, delivery photos, chassis plate, transit damage, HSRP fitment.

### 8.3 Read automatically (OCR / document AI)

| Document | Fields read |
|---|---|
| PAN card | Name, PAN, date of birth |
| Aadhaar (masked) | Name, address, last 4 digits |
| Driving licence | Name, licence number, validity |
| RC (old car) | Owner, registration number, chassis, model, year, hypothecation |
| Insurance policy | Insurer, policy number, chassis, period, lender |
| Lender DO | Lender, customer, loan amount, model |
| Cheque | Bank, number, amount, date |
| OEM invoice | Chassis, engine, model, colour, price |
| Scheme circular | Scheme name, period, models, amounts, conditions (admin approves) |

Every read value is shown to a person for a quick check the first time; once accuracy is proven, only low-confidence reads go to a person.

### 8.4 Signed digitally

Booking form, test-drive form, delivery note, exchange papers, cancellation request. Aadhaar-based e-sign or on-screen signature, depending on the document and what the other party accepts **(check acceptability for RTO and lender forms)**.

---

## 9. Reconciliations that run themselves

| Reconciliation | Matches | Exceptions go to |
|---|---|---|
| Customer receipts | Bank credits ↔ bookings (by virtual account, UPI reference, amount) | ACC |
| Loan disbursements | Bank credits ↔ DO ↔ invoice | ACC, FIN |
| Lender payouts | Payout statements ↔ loans disbursed | FIN, ACC |
| Insurance commission | Insurer statement ↔ policies issued | INS, ACC |
| OEM scheme claims | OEM credit notes ↔ claim lines | ACC, SM |
| OEM account | OEM invoices and payments ↔ stock received | ACC |
| Stock | Physical scan ↔ system stock ↔ funding bank list | STK, ACC |
| Accessories | Fitted ↔ billed | ACC-S, ACC |
| Registration fees | Fees paid on Vahan ↔ fees collected from customer | RTO, ACC |
| Tally | CRM invoices and receipts ↔ Tally entries | ACC |

Each runs daily (or on file upload) and produces an exception list. Accounts works only the exceptions.

---

## 10. Outside integrations

Ordered by value. Availability, cost and licensing differ by provider; all marked **(check availability)**.

| # | Integration | Use | Value | Notes |
|---|---|---|---|---|
| 1 | WhatsApp Business API | Customer and staff messages, lead capture, document collection | Very high | Approved templates, opt-in, opt-out |
| 2 | Cloud telephony | Click-to-call, call logging, recording, missed-call leads | Very high | Consent for recording |
| 3 | Website and ad lead forms (Google, Meta) | Lead capture | Very high | Webhooks |
| 4 | Lead portals | Lead capture | High | API or email parsing |
| 5 | Bank feed / virtual accounts / payment gateway | Auto-matching payments, payment links, refunds | Very high | Through the dealer's bank |
| 6 | Tally | Accounting entries | High | Connector, XML import |
| 7 | E-invoice (IRP) | Invoice registration number | High where required | Through a GST Suvidha Provider |
| 8 | PAN / GSTIN verification | KYC and tax checks | High | Authorised providers |
| 9 | DigiLocker | Consent-based KYC documents | Medium | Partner onboarding needed |
| 10 | E-sign | Signing forms | Medium | Licensed e-sign providers |
| 11 | Insurer / broker platform | Quotes and policy issue | High | Through the dealer's insurance tie-up |
| 12 | Lender / DSA platforms | Loan application and status | Medium–high | Varies by lender |
| 13 | OEM DMS | Booking, stock, retail entry | High | Many OEMs give no API; file exchange or screen automation where the OEM permits |
| 14 | Vahan-linked lookups (RC, DL, challan) | Exchange checks, test-drive licence check | Medium | Through authorised providers |
| 15 | Vahan dealer registration | Registration filing | Medium | Government portal; automation only where permitted |
| 16 | FASTag issuer | FASTag issue | Low–medium | Bank partner |
| 17 | Used-car valuation | Exchange pricing | Medium | Data providers |
| 18 | Telematics / GPS | Demo car tracking | Low–medium | Tracker or connected-car app |
| 19 | Google Business Profile | Reviews | Medium | API for reading and replying |
| 20 | Account Aggregator | Income checks with consent | Medium | Through licensed entities |

---

## 11. Where AI helps, and its limits

| Use | What it does | Guard rails |
|---|---|---|
| Call summary | Transcribes calls; writes a short note, customer needs, objections, next step | Consultant can edit; recording consent |
| Lead scoring | Predicts likelihood to buy from past data | Starts after enough history (for example 6+ months); explains main reasons; never hides leads |
| Next best action | Suggests "send EMI options", "offer test drive at home", "manager call" | Suggestion only |
| WhatsApp assistant | Answers price, variant, availability, offer and document questions outside working hours; books test drives; hands over to a person | Uses only master data; never promises discounts; clear hand-over |
| Document reading | Reads KYC, RC, policy, DO, OEM invoice, scheme circulars | Person checks low-confidence fields; scheme setup always approved by admin |
| Verification bot | Calls or messages the customer to confirm price, discount, free items and payments | Any mismatch or doubt goes to a person |
| Feedback bot | Runs the day-1/7/30 surveys | Low scores go to a person immediately |
| Sentiment watch | Flags angry messages and bad reviews | Alert only |
| Demand forecast | Suggests OEM order mix from pipeline, bookings, season | Manager decides |
| Discount guidance | Shows typical approved discount for similar deals | Approver decides |
| Anomaly detection | Flags unusual patterns: one consultant's discounts much higher, many cancellations, same phone number on many deals, payments split to dodge cash limit | Investigation by a person |
| Report questions | Owner asks "how many Creta-class bookings this month by source?" in plain language | Read-only, respects permissions |

AI never: approves money, changes prices, issues invoices or refunds, or sends a message that promises something not in the system.

---

## 12. Phased roadmap

### Phase 0: Foundation (weeks 0–4)

| Deliverable | Outcome |
|---|---|
| Masters with versioning and approval (F1) | One source for prices, taxes, offers |
| Customer record and duplicate rules (F2) | No duplicates |
| Roles, branches, permissions, masking (F9) | Secure from day one |
| Event engine, task engine, approval engine (F3–F5) | Base for all automation |
| Audit log (F10) | Trail from day one |
| Document vault (F6) | Paperless start |
| Message templates (F7) | Customer messages ready |

### Phase 1: Core sales flow without manual hand-offs (months 1–3)

| Deliverable | Removes |
|---|---|
| Lead capture from website, ads, WhatsApp; auto-assignment; first-call timer; follow-up tasks; lost reasons | Copying leads, forgotten follow-ups |
| Walk-in check-in | Paper register |
| Test-drive booking, digital form, feedback | Paper forms, missed quotes |
| Quotation engine with taxes, offers, EMI; PDF on WhatsApp | Manual price calculation |
| Discount approvals on phone with margin view | Phone approvals, leakage |
| Digital booking form; all C01 notifications | Paper booking; forgotten departments |
| Allocation suggestion and chassis lock; ageing alerts | Double allocation; ageing |
| Balance calculation; payment reminders; cash block | Disputes, legal risk |
| All gates (allocation, invoice, registration, delivery, refund) | Incomplete invoices and deliveries |
| Invoice, Form 21 and receipt generation | Retyping |
| Registration, HSRP and RC tracker | Lost track of RC |
| Accessories upsell task and fitment job | Missed upsell |
| PDI and delivery checklists on phone | Paper checklists |
| Cancellation flow with all reversals | Open loose ends |
| WhatsApp feedback and review requests | Manual feedback calling |
| Role dashboards and daily summary | Manual daily reports |

### Phase 2: Money and documents (months 3–6)

| Deliverable | Removes |
|---|---|
| Virtual account / UPI per booking; bank feed auto-matching; auto receipts | Unidentified money, receipt typing |
| Tally integration | Double entry |
| Document capture with OCR; name match checks | Typing KYC; mismatched names |
| Own-policy check; lender name rules | Invalid policies |
| Generated Form 20/34, Form 29/30, Form 60, delivery kit; e-sign | Paperwork errors |
| Scheme claim engine; proof packs; credit-note matching | Missed and rejected claims |
| Lender payout and insurer commission reconciliation | Lost commission |
| Incentive engine with live tracker | Spreadsheet incentives |
| Complaint tickets | Lost complaints |
| Referral links; renewal and anniversary messages | Manual tracking |
| QR gate pass and demo car gate scans; scan-based stock check | Gate errors |
| Lead scoring (rules), drip campaigns for dormant leads | Manual revival |
| OEM invoice import into stock | Typing chassis numbers |

### Phase 3: Outside integrations (months 6–9)

| Deliverable | Removes |
|---|---|
| Cloud telephony with call logging and recording | Manual call logs |
| Lead portal integrations | Copy-paste |
| PAN, GSTIN, DL, RC, challan verification | Manual checks |
| E-invoice | Manual IRN generation |
| Insurer/broker policy issue | Typing on insurer portals |
| Lender/DSA platform push | Logging on several portals |
| OEM DMS exchange (API, file or screen automation where permitted) | Retyping in DMS |
| Vahan data pack / permitted automation; FASTag issue | Typing on Vahan |
| Payout API for refunds | Manual bank transfers |
| Valuation data for exchange | Price guessing |
| Demo car telematics, footfall counter | Blind spots |

### Phase 4: AI and optimisation (months 9–12 and beyond)

| Deliverable | Removes |
|---|---|
| Call transcription and summaries | Typing notes |
| WhatsApp assistant for after-hours questions and test-drive booking | Missed night-time leads |
| Verification and feedback bots | Most routine calls |
| AI lead scoring and next best action | Guesswork |
| Demand forecast for OEM orders | Over/under stocking |
| Anomaly detection | Hidden leakage |
| Scheme circular reading | Manual scheme setup |
| Plain-language owner reports | Waiting for reports |

---

## 13. Impact and effort

| Automation | Impact | Effort | Do |
|---|---|---|---|
| Lead capture + auto-assign + follow-up tasks | Very high | Low | First |
| Quotation engine | Very high | Medium | First |
| Event notifications and gates | Very high | Medium | First |
| Discount approvals with margin | High | Low | First |
| Allocation with chassis lock | High | Low | First |
| Checklists on phone (PDI, delivery, exchange) | High | Low | First |
| WhatsApp messages and feedback | High | Low | First |
| Bank auto-matching / virtual accounts | Very high | Medium | Second |
| Tally integration | High | Medium | Second |
| Scheme claims and reconciliation | Very high (money) | Medium | Second |
| OCR and generated forms | High | Medium | Second |
| Incentive engine | Medium | Medium | Second |
| Telephony | High | Medium | Third |
| PAN/GSTIN/RC verification | Medium | Low–medium | Third |
| Insurer and lender integrations | Medium–high | High | Third |
| OEM DMS and Vahan automation | High | High (depends on access) | Third |
| AI bots and scoring | Medium–high | Medium–high | Fourth |

---

## 14. Labour saved by role

Qualitative, from the steps removed above. Real figures should be measured (see §15).

| Role | Routine work removed | What they spend time on instead |
|---|---|---|
| Sales consultant | Price calculation, PDF making, logging calls, chasing documents, telling other departments, writing notes | More customers, more test drives |
| Team leader / manager | Compiling reports, chasing follow-ups by phone, verbal approvals | Coaching, closing hot deals |
| BDC | Copying leads, routine reminder calls | Qualifying and converting |
| Sales admin | Typing bookings, stock and retail entries; allocation spreadsheets; invoice preparation | Exceptions, OEM coordination |
| Accounts | Matching receipts, typing receipts and invoices, Tally entry, claim lists, commission matching | Exceptions, cash control, analysis |
| Finance / insurance desks | Retyping on portals, status calls | More files, better penetration |
| Registration | Filling forms, tracking by spreadsheet | Faster filing |
| Customer relations | Routine feedback and verification calls | Handling problems |
| PDI / delivery | Paper forms, hunting for documents | Quality and customer experience |
| HR | Incentive spreadsheets | Training and hiring |
| Owner | Waiting for reports, finding leakage | Decisions |

---

## 15. Measuring success

Measure before and after each phase.

| Measure | What it shows |
|---|---|
| Manual data entries per booking (fields typed) | Retyping removed |
| Time from lead to first contact | Lead automation |
| Follow-up adherence | Task engine |
| Time from booking to delivery | Hand-offs |
| Time from balance cleared to invoice; invoice to registration | Gates and tasks |
| Deliveries delayed by missing items | Gates |
| Unmatched receipts at day end | Bank automation |
| Tally mismatches | Integration |
| Name/data mismatch rejections (Vahan, lender, insurer) | Error-proofing |
| Scheme claims rejected or short-paid (amount) | Claim engine |
| Unreconciled lender and insurer payouts | Reconciliation |
| Discount above approval (should be zero) | Controls |
| Tasks overdue by department | Where hand-offs still break |
| Calls per delivery by customer relations | Bot effect |
| Staff hours on reports per week | Dashboards |
| Customer feedback score and Google rating | Experience |

---

## 16. Risks and safeguards

| Risk | Safeguard |
|---|---|
| Wrong master data spreads to every deal | Masters versioned, effective-dated, approved by a second person; change alerts |
| Outside system down | Manual entry with proof upload; "manually verified" flag; retry queue |
| Over-notification (people ignore alerts) | Priority levels, bundling, daily digests for info items, per-role settings |
| Staff bypass the system (side deals) | Gates, verification, receipts only from bank feed, anomaly detection |
| Data privacy (Aadhaar, PAN, phone, recordings) | Consent capture, masking, role-based access, retention limits, export logging, compliance with the Digital Personal Data Protection Act, 2023 |
| Vendor lock-in for integrations | Integration layer (F8) with replaceable connectors |
| AI mistakes | AI only suggests or drafts; people approve money and promises; confidence thresholds |
| Unauthorised screen automation on government or OEM portals | Use only where the portal owner permits; otherwise prepare data for staff to submit |
| Staff resistance | Phone-first design, fewer clicks than paper, live incentive tracker as a reason to use it |
| Tax and rule changes | Rules in masters, not code; owner alerted to update; **(verify)** items reviewed each quarter |
