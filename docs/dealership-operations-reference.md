# Automobile dealership operations: complete reference

Date: 30 October 2026.
Purpose: one place that lists how a full-scale automobile dealership works. It covers every department, role, process and document, and how they connect. It walks through the purchase step by step from both sides: what the customer does and what the dealership does. The last part maps this against the Euler CRM so gaps are visible.

Scope:

- **Global benchmark:** the large US dealer groups (AutoNation, Lithia, Penske, Hendrick). They have the most mature departmental structure.
- **India practice:** passenger-vehicle dealers (Maruti Arena/NEXA, Tata, Mahindra, Hyundai) and commercial / EV three-wheeler dealers (the Euler model). Indian statutory steps are covered: GST, Vahan, Forms 20/21/22/34, HSRP, insurance and PM E-DRIVE.

Rules, rates and scheme windows change. Anything marked **(verify)** should be confirmed against the current state transport notice, the OEM dealer manual or the scheme portal before it drives a CRM rule.

---

## Contents

1. [Dealership models and the macro picture](#1-dealership-models-and-the-macro-picture)
2. [Where the money comes from](#2-where-the-money-comes-from)
3. [Organisation chart](#3-organisation-chart)
4. [Every department: roles, functions, KPIs, systems](#4-every-department-roles-functions-kpis-systems)
5. [The customer journey: customer side and dealer side, step by step](#5-the-customer-journey-customer-side-and-dealer-side-step-by-step)
6. [Sub-processes in micro detail](#6-sub-processes-in-micro-detail)
7. [After the sale: ownership lifecycle](#7-after-the-sale-ownership-lifecycle)
8. [Back office and OEM-facing processes](#8-back-office-and-oem-facing-processes)
9. [Interlinks: who hands what to whom](#9-interlinks-who-hands-what-to-whom)
10. [Documents and forms register](#10-documents-and-forms-register)
11. [KPI dictionary](#11-kpi-dictionary)
12. [Controls, leakage and fraud points](#12-controls-leakage-and-fraud-points)
13. [EV commercial three-wheeler specifics](#13-ev-commercial-three-wheeler-specifics)
14. [Gap map against the Euler CRM](#14-gap-map-against-the-euler-crm)
15. [Glossary](#15-glossary)
16. [Sources](#16-sources)

---

## 1. Dealership models and the macro picture

### 1.1 Formats

| Format | What it does | Typical in |
|---|---|---|
| **3S** | Sales + Service + Spares under one roof | Most Indian franchised dealers, all US franchise stores |
| **2S** | Sales + Spares, or Service + Spares | Smaller towns |
| **1S** | Sales only (showroom / outlet) | City satellite outlets, rural outlets |
| **Sub-dealer / ASC** | Sells or services under a main dealer's trade certificate and billing | Indian rural network, three-wheelers, two-wheelers |
| **Workshop-only (dealer workshop / authorised service centre)** | Service, warranty and parts only | All OEMs |
| **Body and paint shop** | Accident repair, insurance claims | Larger dealers |
| **Pre-owned outlet** | Used-car buy, refurbish, sell (True Value, Mahindra First Choice, Hyundai Promise) | Large dealers |
| **Experience centre / digital store** | Display and test drive; billing through the parent dealership | Premium and EV brands |
| **Dealer group** | Many franchises and brands under one management (AutoNation: 323 franchises from 245 stores at end of 2025) | US, Indian metros |

### 1.2 The macro value chain

```
OEM (manufacturer)
  │  product plan, wholesale price, schemes, allocation, warranty policy, DMS
  ▼
Dealer principal / owner
  │  capital, trade certificate, OEM dealer agreement, bank (inventory funding)
  ▼
Dealership
  ├── Variable operations (front end): New sales · Used sales · F&I · Accessories · Fleet/Institutional
  ├── Fixed operations (back end): Service · Parts · Body shop · Warranty
  ├── Support: Marketing · BDC/CRM · Accounts · HR · IT · Admin/Security · Compliance
  ▼
Customer  ──► ownership lifecycle (service, warranty, insurance renewal, upgrade/exchange) ──► back to Sales
External parties around the dealer:
  Banks/NBFCs · Insurers · RTO/Vahan · HSRP vendor · Logistics/transporter · OEM finance arm ·
  Government scheme portal (PM E-DRIVE, state EV subsidy) · Tally/auditor · GST portal
```

The point to hold on to: **the sale is the start of the relationship, not the end.** In mature groups, service, parts and F&I earn most of the gross profit (see §2). The CRM has to carry the customer from enquiry to the next purchase.

---

## 2. Where the money comes from

### 2.1 AutoNation FY2025 (largest US franchised group), from its 10-K

| Line | Share of revenue | Share of gross profit |
|---|---|---|
| New vehicles | 48.9% | about 13% |
| Used vehicles | 28.3% | about 9% |
| Parts and service | 17.5% | about 48% |
| Finance and insurance (net) | 5.3% | about 30% |

New cars bring the customer in. Fixed operations and F&I make the profit.

### 2.2 Indian dealer income lines

| Income line | Where it comes from |
|---|---|
| Vehicle margin | Difference between dealer purchase price (OEM invoice) and selling price, after dealer discount |
| OEM schemes / incentives | Volume targets, retail targets, model-specific support, consumer offers funded by OEM, exchange bonus, corporate/loyalty bonus. Claimed back from OEM. |
| Finance payout | Commission from bank/NBFC per loan disbursed (a percentage of loan amount, sometimes slab-based) |
| Insurance commission | Through the dealer's broker/corporate-agent tie-up with insurers; renewal commission later |
| Extended warranty / AMC / RSA | Margin on add-on products |
| Accessories | High-margin; fitted before delivery |
| Exchange / used vehicle | Trade-in margin plus OEM exchange bonus |
| Registration and handling | RTO fee is pass-through; "handling" or "logistics" charges are restricted by many OEMs and state rules **(verify)** |
| Service labour | Paid service, running repairs |
| Spares and lubricants | Counter and workshop sales |
| Warranty labour and parts | Reimbursed by OEM |
| Body shop | Insurance-claim repairs |
| Fleet / institutional | Bulk orders, often thin margin plus OEM fleet support |

---

## 3. Organisation chart

Reporting lines vary by store. This is the full-scale version; smaller dealers merge roles.

```
Dealer Principal / Owner
└── General Manager / CEO (dealership)
    ├── General Sales Manager (GSM) / Sales Head
    │   ├── New Vehicle Sales Manager
    │   │   ├── Team Leaders (TL)
    │   │   │   └── Sales Consultants / Executives (DSE)
    │   │   └── Showroom Host / Receptionist
    │   ├── Field / Rural Sales Manager (ASM, RM)
    │   │   └── Field executives, sub-dealer coordinators
    │   ├── Fleet / Institutional / Corporate Sales Manager
    │   ├── Used Car (Pre-owned) Manager
    │   │   └── Evaluators, refurbishment coordinator, used-car sales
    │   ├── F&I Manager (sometimes reports to GM)
    │   │   ├── Finance executives (bank/NBFC desks, DSA coordination)
    │   │   └── Insurance executive
    │   ├── Accessories Manager
    │   ├── Delivery Manager / Delivery Coordinator
    │   │   └── PDI team, delivery bay staff, registration (RTO) executive
    │   └── Internet / Digital Sales Manager
    ├── Fixed Operations Director / Works Manager
    │   ├── Service Manager
    │   │   ├── Service Advisors (SA)
    │   │   ├── Workshop Controller / Floor In-charge
    │   │   ├── Technicians (mechanical, electrical, EV high-voltage certified), Foreman
    │   │   ├── Washing / detailing team
    │   │   ├── Road-test driver, pick-up & drop (PUDO) drivers
    │   │   └── Warranty Administrator
    │   ├── Body Shop Manager
    │   │   └── Estimators, insurance surveyor liaison, denter, painter
    │   └── Parts Manager
    │       └── Parts counter, warehouse/storekeeper, parts sales (retail, wholesale, workshop)
    ├── Business Development Centre (BDC) / CRM Manager
    │   ├── Sales BDC (lead calling, appointments)
    │   └── Service BDC (service reminders, bookings, feedback calls)
    ├── Marketing Manager
    │   └── Digital, events/activations, local promotions
    ├── Customer Relations Manager (CRM)
    │   └── Feedback callers, complaint handling
    ├── Finance Controller / Accounts Manager
    │   ├── Cashier, receivables, payables
    │   ├── OEM claims (scheme claims, warranty claims) accountant
    │   ├── Insurance / finance payout reconciliation
    │   └── GST / TDS / TCS compliance, Tally
    ├── HR & Admin
    │   └── Recruitment, training, payroll, incentives, security, housekeeping
    ├── IT / DMS administrator
    └── Stock yard / Inventory in-charge
        └── Yard staff, drivers, gate security (in/out register)
```

---

## 4. Every department: roles, functions, KPIs, systems

### 4.1 Front desk / reception

- Greets walk-ins within a set time, records a walk-in in the register or DMS.
- Asks the purpose: new purchase, service, parts, accounts, complaint.
- Assigns a sales consultant by roster ("up system" in US stores) or by source/territory.
- Gives the customer a refreshment and a wait time.
- **KPI:** walk-ins recorded vs gate count, time to first greet.

### 4.2 Sales department (new vehicles)

| Role | Main duties |
|---|---|
| Sales Head / GSM | Monthly targets by model, scheme strategy, discount authority, stock order, staffing, daily review |
| Sales Manager / Team Leader | Daily huddle, follow-up audit, discount approval within limit, joint calls on hot leads, test drive control |
| Sales Consultant (DSE) | Greet, needs analysis, product presentation, walk-around, test drive, quotation, negotiation, booking, follow-up, finance/insurance hand-off, delivery, post-sale follow-up |
| Showroom Host | Walk-in register, customer comfort, hand-over to consultant |
| Delivery Coordinator | Schedules deliveries, checks payment and documents, PDI done, delivery bay ready |
| Field / Rural / ASM / RM | Village or market activations, sub-dealer management, fleet owners, haats/mandis, influencer network (mechanics, drivers' unions, existing customers) |
| Fleet / Institutional | Tenders, logistics companies, e-commerce fleets, government, corporate leasing |

**Functions:** prospecting · lead handling · showroom process · test drive · quotation · negotiation · booking · order/allocation · stock matching · payment collection coordination · finance coordination · exchange coordination · delivery · post-delivery follow-up · referrals.

**KPIs:** enquiries, enquiry-to-test-drive %, test-drive-to-booking %, booking-to-retail %, lost-to-competition %, average discount per unit, gross per unit, finance penetration, insurance penetration, accessories per car, exchange penetration, extended-warranty penetration, SSI / delivery NPS, follow-up adherence, booking cancellation %.

**Systems:** OEM DMS, CRM, lead aggregator portals, WhatsApp, call telephony, price list / scheme circulars.

### 4.3 Used car / pre-owned department

- **Evaluation:** physical inspection (checklist of 100–200 points), document check (RC, insurance, loan NOC, challans, accident history), market price lookup, offer price.
- **Purchase:** negotiation, payment to seller (or adjusted against new car), loan foreclosure with the seller's bank, Form 29 and Form 30 signed by the seller (transfer of ownership), delivery note and indemnity.
- **Refurbishment:** service, body/paint, detailing, certification.
- **Sale:** listing, test drive, finance, ownership transfer at RTO, warranty on certified cars.
- **Disposal:** cars not fit for retail go to auction or to a wholesale broker.
- **KPIs:** exchange penetration, evaluation-to-purchase %, days in stock, refurbishment cost per car, gross per used car, stock turns.

### 4.4 F&I (finance and insurance)

**Finance:**
- Finds out early whether the customer will pay cash or take a loan.
- Collects KYC (Aadhaar, PAN, address proof), income proof (salary slips, ITR, bank statements; for commercial buyers, business proof, GST, contracts, existing vehicle RCs).
- Sends to several banks/NBFCs, gets sanction, negotiates rate, tenure, down payment, processing fee.
- Collects the down payment (margin money), gets the loan agreement signed, arranges the delivery order (DO) from the financier.
- Makes sure hypothecation is marked on the invoice, Form 20 and the insurance policy.
- Follows up disbursement and matches it to the invoice.
- Collects the dealer payout from the financier.
- For commercial / EV three-wheelers: NBFCs specialising in drivers, battery-financing or battery-subscription partners, OEM captive finance, co-lending, guarantor requirement **(verify per financier)**.

**Insurance:**
- Quotes the own-damage (OD) premium and the mandatory third-party (TP) premium. New private cars need 3-year TP and two-wheelers 5-year TP; commercial vehicles are normally annual **(verify)**.
- Add-ons: zero depreciation, engine/battery protect, return to invoice, roadside assistance, consumables, key replacement, personal accident cover for owner-driver.
- Issues the policy before registration (the policy number goes on Form 20), with the financier's name for hypothecation.
- Tracks renewals, endorsements, claim support (works with the body shop).
- Reconciles the insurer's commission statement (MIS) with policies issued.

**Other F&I products:** extended warranty, AMC / service package, RSA, battery warranty extension (EV), anti-rust / coating, tyre and alloy protection, GAP cover (US).

**KPIs:** finance penetration, insurance penetration, payout per unit, products per deal, rate of loan rejection, disbursement TAT, insurance renewal retention.

### 4.5 Accessories

- Accessory catalogue and price (OEM genuine and local).
- Pitch at quotation stage, packs per variant.
- Order to the fitment team, fitment before PDI, quality check, billing.
- **KPIs:** accessories revenue per car, penetration, fitment errors.

### 4.6 Delivery, PDI and registration

- **PDI (pre-delivery inspection):** exterior and interior check, fluid levels, battery state (12 V and, for EVs, traction battery state of charge), tyre pressure, all electrics, software version, VIN/chassis and motor/engine number match with invoice, accessories fitted, cleaning, photos.
- **Registration:** Form 20 (application), Form 21 (sale certificate), Form 22 (roadworthiness from manufacturer), insurance, invoice, KYC, address proof, Form 34 if hypothecated, fees and road tax paid online on Vahan. Temporary registration if needed. HSRP order and fitment. RC print or digital RC.
- **Delivery bay:** decoration, ceremony, photo, product demo, document kit.
- **KPIs:** on-time delivery %, PDI defects found, delivery complaints, days from booking to delivery, registration TAT.

### 4.7 Service department

| Role | Main duties |
|---|---|
| Service Manager / Works Manager | Throughput, profitability, staffing, quality, OEM audits |
| Service Advisor | Appointment, reception, vehicle walk-around with customer, job card, estimate, approvals for extra work, updates, billing explanation, delivery |
| Workshop Controller | Assigns jobs to bays and technicians, tracks progress board |
| Technician | Diagnosis, repair, records labour time; EV high-voltage work only by certified technicians |
| Foreman / QC | Final inspection, road test |
| Warranty Administrator | Files warranty claims with OEM, keeps failed parts, handles rejections |
| PUDO driver | Pick-up and drop |
| Washing | Wash and vacuum before delivery |

**Job types:** free service (OEM-paid schedule), paid service, running repair, warranty repair, recall / service campaign, accident repair (body shop), PDI, accessories fitment, software update, roadside breakdown.

**KPIs:** vehicles reported per day, labour revenue per job, parts per job, technician efficiency and productivity, bay utilisation, repeat repair %, first-time-right %, service retention (cars returning for service), CSI, warranty claim rejection %, service absorption (fixed-ops gross ÷ dealership overheads).

### 4.8 Parts department

- Ordering from OEM (stock order, emergency order, VOR — vehicle off road order).
- Receiving, GRN, binning, stock count.
- Issue to workshop against job card, counter sales, wholesale to retailers and independent garages.
- Warranty parts return to OEM.
- Obsolete and slow-moving stock management.
- **KPIs:** fill rate, inventory turns, days of stock, non-moving stock %, counter sales, parts gross margin, lost sales.

### 4.9 Body shop

- Accident vehicle intake, insurer intimation, surveyor visit, estimate, approval, repair, re-inspection, release with customer liability (deductibles, depreciation) and insurer liability split. Cashless or reimbursement.
- **KPIs:** turnaround time, claims per month, average repair order value, insurer rejection rate.

### 4.10 BDC / call centre / CRM team

- **Sales BDC:** calls every new lead within minutes, qualifies, books a showroom visit or test drive, chases lost and old leads, calls web and social leads.
- **Service BDC:** service due reminders, appointment booking, no-show follow-up, insurance renewal calls.
- **Feedback:** post-delivery calls (day 1, day 7, day 30), post-service calls (within 3 days), complaint logging and closure.
- **KPIs:** speed-to-lead, contact rate, appointment set %, show rate, feedback coverage, complaint closure time.

### 4.11 Marketing

- Digital campaigns (Google, Meta, OEM portals), lead aggregators, local press, outdoor.
- Events: launches, rural activations, exchange melas, loan melas, test-drive camps, fleet owner meets.
- Co-op funding claims from OEM for approved activities.
- **KPIs:** cost per lead, cost per sale, lead-to-sale by source, event ROI.

### 4.12 Accounts and finance

- Receipts: cash, UPI, card, cheque, NEFT/RTGS, loan disbursement, subsidy (from scheme), exchange adjustment. Receipt voucher per payment.
- Vehicle invoice (tax invoice with GST, chassis and engine/motor number, hypothecation).
- Payables: OEM (vehicle purchase, usually through inventory funding / trade advance), vendors, staff.
- Inventory funding (floor plan): interest on each vehicle until sold; ageing.
- OEM claims: schemes, warranty, co-op marketing, subsidy reimbursement. Tracking claim submitted vs settled vs rejected, and credit notes.
- Reconciliation: bank, finance payouts, insurance payouts, OEM statement of account.
- Tax: GST returns (GSTR-1, GSTR-3B), TDS, TCS where it applies (for example on vehicles above ₹10 lakh under the Income Tax Act **(verify current rule)**), e-invoice, e-way bill for vehicle transport.
- Books in Tally or the DMS finance module; month-end closing; audit.
- **KPIs:** debtors days, unreconciled receipts, claim ageing, inventory interest cost, gross margin by line.

### 4.13 HR and admin

- Recruitment, OEM-mandated training and certification, attendance, payroll.
- **Incentive schemes:** per unit, per target slab, per finance/insurance/accessories, deductions for cancellations or excess discount.
- Security, gate register (vehicle in/out), test-drive vehicle log, key control, housekeeping.

### 4.14 IT / DMS

- OEM DMS (dealer management system), CRM, telephony, website, Tally integration, user rights, backups.

### 4.15 Inventory / stock yard

- Receive vehicles from OEM transporter: check against e-way bill / OEM invoice, transit damage check, record chassis.
- Yard placement, battery charging cycles (EVs), periodic start-up, cleanliness, physical stock audit (also by bank for floor plan).
- Allocation of specific chassis to bookings, transfers between branches.
- **KPIs:** stock days, ageing buckets (0–30, 31–60, 61–90, 90+), transit damage, stock audit variance.

---

## 5. The customer journey: customer side and dealer side, step by step

Each stage shows what the **customer** does, what the **dealership** does, who owns it, and the record it produces.

### Stage 0: Need arises

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Realises a need (new business, replace old vehicle, family need, fuel cost, subsidy news) | Builds awareness: ads, OEM campaigns, field activations, existing customers, mechanics and drivers as referrers | Marketing, Field sales | Brand awareness |

### Stage 1: Research

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Searches online, watches videos, asks peers and drivers, compares brands, checks price, range (EV), payload, EMI, resale | Website and listings up to date, WhatsApp catalogue, quick reply to enquiries, review management on Google | Marketing, Digital | Online leads |

### Stage 2: First contact / enquiry

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Calls, fills a form, sends a WhatsApp message, walks in, or meets a field executive | Captures the lead with source, name, phone, location, model interest, use case, timeline, budget, payment mode, exchange; de-duplicates; assigns to an executive; first call within minutes; sends brochure and price | BDC / Reception / Executive | Lead (enquiry) record, source tag |

### Stage 3: Qualification and needs analysis

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Explains use: daily km, load, route, charging access, parking, family size, budget, income | Asks questions, classifies hot / warm / cold, suggests model and variant, works out EMI, checks finance eligibility and exchange | Sales Consultant | Lead temperature, expected purchase date, next follow-up date |

### Stage 4: Showroom visit and product presentation

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Visits, sees the vehicle, sits in, asks questions | Greet, walk-around (front, side, rear, cabin, engine/battery, features), competitor comparison, total cost of ownership (fuel vs electricity, maintenance), demo of app/telematics | Consultant | Visit logged |

### Stage 5: Test drive

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Takes a drive on a set route (or a home test drive), for commercial vehicles often a loaded or route trial | Checks licence copy, gets the test-drive form and indemnity signed, logs the vehicle, km and fuel/charge out and in, consultant explains during drive, takes feedback | Consultant, Security (gate log) | Test-drive record, licence copy |

### Stage 6: Quotation and negotiation

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Asks for the on-road price, compares other dealers, negotiates discount, accessories, exchange value | Prepares the quotation: ex-showroom, GST, RTO (road tax, registration, HSRP, smart card), insurance, extended warranty, accessories, handling (if allowed), minus schemes (consumer, exchange, corporate, loyalty, subsidy), minus dealer discount = on-road price; EMI options. Discount above the consultant's limit goes to TL, then Sales Manager / GM for approval. | Consultant, TL, Sales Manager | Quotation (versioned), discount approval |

### Stage 7: Exchange evaluation (if there is a trade-in)

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Brings the old vehicle and its RC, insurance, loan papers | Evaluator inspects, checks documents and challans, gives an offer, negotiates, agrees an amount; exchange bonus from OEM shown separately | Used-car evaluator | Evaluation sheet, agreed price |

### Stage 8: Finance decision

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Chooses cash, dealer-arranged loan or own bank loan; hands over KYC and income documents | Logs in the file with financiers, gets sanction, confirms down payment, EMI, tenure; collects the financier's delivery order | Finance executive | Loan file, sanction letter, DO |

### Stage 9: Booking

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Pays the booking amount, signs the booking form (order form) with model, variant, colour, price terms, cancellation terms, expected delivery | Issues the booking receipt, enters the booking in DMS / OEM system, explains the waiting period, schedules follow-ups | Consultant, Cashier | Booking form, receipt, booking ID |

### Stage 10: Verification and approval (internal)

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Gets a confirmation call | Manager or CRM team calls to confirm the price, discount, promises (accessories, delivery date) and that there is no unrecorded side deal. Deal sheet approved by TL / Admin / GM. | CRM, Sales Manager | Verified and approved deal sheet |

### Stage 11: Allocation and stock

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Waits; asks for updates | Matches a chassis from stock or orders from OEM; allocates the chassis to the booking; if not in stock, OEM order and transit tracking; informs the customer of the chassis and date | Sales admin, Inventory | Chassis allocated to booking |

### Stage 12: Payment completion

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Pays the balance (cash/UPI/RTGS) or the financier disburses; hands over the old vehicle if exchange | Receipts for each payment, matches total received to on-road price, tracks shortfall; exchange value adjusted; subsidy (if applicable) reduces customer payable and becomes a receivable from the scheme | Accounts, Cashier | Payment ledger per customer, zero balance or approved credit |

### Stage 13: Insurance

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Chooses the dealer's insurer or brings their own policy | Issues the policy with chassis and motor/engine number and financier name; policy start date before registration | Insurance executive | Policy document |

### Stage 14: Invoicing

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Checks name, address, model, colour, price | Raises the tax invoice (GST, chassis and engine/motor number, HSN, hypothecation), e-invoice IRN if applicable; updates OEM DMS (retail / sale report); for subsidy schemes, generates the e-voucher | Accounts, Sales admin | Tax invoice, OEM retail entry |

### Stage 15: Registration

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Signs Form 20 and Form 34 (if loan), gives address proof; chooses a fancy number if wanted | Uploads documents and pays road tax and fee on Vahan (dealer-point registration in many states), gets the temporary or permanent number, orders HSRP, gets RC | RTO executive | Registration number, RC, HSRP order |

### Stage 16: PDI and accessories

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| May attend the PDI (recommended) | Full PDI checklist, accessory fitment, cleaning, HSRP fitment, photos, charge to full (EV) | PDI team, Service | PDI sheet signed |

### Stage 17: Delivery

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Comes for delivery (often with family; auspicious dates matter in India), checks the vehicle, signs the delivery note | Delivery checklist: all payments clear, invoice, insurance, RC/temporary registration, Form 21/22 copies, warranty booklet, owner's manual, service schedule, charger and cables (EV), keys (count), toolkit, accessories list; product orientation (controls, charging, app, service schedule, roadside number); introduces the service advisor; photo and ceremony; gate pass | Delivery coordinator, Consultant | Delivery note, gate pass, photos, retail recorded |

### Stage 18: Post-delivery

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Starts using the vehicle; may have small questions or issues | Thank-you message; feedback calls on day 1/2, 7 and 30; OEM survey (SSI); request for Google review; referral ask; first free service reminder; RC and HSRP handover if pending; loan file closure with financier | CRM / BDC, Consultant | Feedback score, review, referral leads |

### Stage 19: Ownership

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Services the vehicle, renews insurance, claims warranty, maybe has an accident | Service reminders, job cards, warranty claims, renewal calls, body shop, upgrade offer at the right time | Service, Insurance, BDC | Service history, renewal, lifetime value |

### Stage 20: Replacement / repurchase

| Customer | Dealership | Owner | Output |
|---|---|---|---|
| Thinks about the next vehicle or a second vehicle for the fleet | Exchange offer, loyalty bonus, fleet upgrade proposal | Sales, Used car | New lead (loop closes) |

### Exit paths at any stage

| Exit | Dealer action |
|---|---|
| **Lost / dropped lead** | Record reason (price, competitor, finance rejected, postponed, not reachable), competitor and model; manager review; re-engage campaign later |
| **Booking cancellation** | Cancellation form, reason, manager approval, refund per policy (less deductions if stated), chassis released back to stock, OEM booking cancelled, incentive reversal |
| **Finance rejection** | Try another financier, raise down payment, add a co-applicant/guarantor, or convert to cash |
| **Delivery refusal / defect at PDI** | Replace the chassis, rectify, or escalate to OEM |
| **Post-sale complaint** | Log, assign, resolve, close with customer confirmation; OEM escalation if needed |

---

## 6. Sub-processes in micro detail

### 6.1 Lead management

1. **Sources:** walk-in, phone, website, OEM portal, aggregator portals, social media, WhatsApp, field activity, referral, existing customer, fleet tender, event, mechanic/driver influencer, exchange mela.
2. **Capture fields:** name, mobile (primary key, de-dupe), alternate number, location/pincode, source, sub-source, campaign, model, variant, use case (passenger/cargo, own use/hire), current vehicle, exchange yes/no, payment mode, budget, expected purchase date, assigned executive, created by, created at.
3. **Assignment rules:** round robin, territory, source-specific team, language.
4. **First response SLA:** minutes for digital leads; same day for others.
5. **Temperature:** hot (buy within 7–15 days), warm (within 30), cold (later or unclear).
6. **Follow-up cadence:** next-action date is mandatory; overdue follow-ups escalate to TL.
7. **Activity log:** every call, visit, WhatsApp, test drive, quotation, with outcome.
8. **Stage pipeline:** New → Contacted → Qualified → Visit / Test drive → Quoted → Negotiation → Booked → Allocated → Invoiced → Delivered; side exits Lost / Dropped / Cancelled.
9. **Lost analysis:** reason codes, competitor, price gap; monthly lost report.
10. **Recycling:** dormant leads re-assigned or put into campaigns.

### 6.2 Pricing and quotation

- **Inputs:** price list (ex-showroom per model/variant/colour, effective dates), GST rate per vehicle class, road tax by state and vehicle class (EVs often exempt or reduced **(verify by state)**), registration fees, HSRP charge, insurance premium, accessories, extended warranty, scheme master (consumer offer, exchange bonus, corporate, loyalty, rural, finance subvention, government subsidy, state subsidy), dealer discount limits by role.
- **Logic:** on-road price = ex-showroom + RTO + insurance + accessories + EW/AMC + other allowed charges − schemes − discount.
- **Controls:** a quotation is versioned; any discount above the role limit needs approval; scheme eligibility checked (dates, model, customer type); the final booked price is frozen against the quotation.

### 6.3 Scheme / offer handling

- OEM issues scheme circulars monthly (sometimes mid-month changes).
- Each scheme has: name, period, models, amount, who funds it (OEM / dealer / shared split), eligibility (exchange proof, corporate ID, previous-customer proof), claim documents, claim deadline.
- At the deal: applied scheme recorded with its funding split.
- After retail: claim to OEM with proofs; track settled / short-paid / rejected; rejected amounts become a dealer loss or recovery from staff if the paperwork was the cause.

### 6.4 Exchange (trade-in)

1. Customer declares an old vehicle.
2. Evaluator inspects and checks RC, insurance, hypothecation, challans, number of owners.
3. Price offered (market reference, refurbishment estimate, margin).
4. Agreement: price, date of handover, documents.
5. On handover: Form 29, Form 30 signed by seller, delivery note, keys, RC original, NOC from seller's financier if loan, indemnity.
6. Value adjusted against the new vehicle (or paid out).
7. OEM exchange bonus claimed with the old vehicle's RC proof.
8. Ownership transferred to the dealer or the next buyer; refurbish; resell or scrap (Registered Vehicle Scrapping Facility gives a Certificate of Deposit that can earn a road-tax concession **(verify)**).

### 6.5 Finance (loan) workflow

1. Eligibility screen: CIBIL, income, existing EMIs, age, residence stability, for commercial buyers the earning plan (route, contract, fleet tie-up).
2. Documents: KYC, photos, bank statements, income proof, address proof, guarantor documents, quotation.
3. Login to 2–3 financiers; field investigation (residence and business verification).
4. Sanction: amount, rate, tenure, EMI, processing fee, insurance requirement.
5. Down payment collected by the dealer.
6. Agreement signed, NACH/e-mandate for EMIs, post-dated cheques if required.
7. Delivery order (DO) issued by the financier to the dealer.
8. Invoice with hypothecation; insurance with financier as loss payee.
9. Disbursement to the dealer's account after invoice/RC/insurance copies are sent.
10. RC with hypothecation entry sent to the financier (some keep a copy).
11. Dealer payout claimed and reconciled.

### 6.6 Insurance workflow

1. Quote (insurer comparison, IDV, add-ons, NCB transfer from the old vehicle if applicable).
2. Customer choice recorded (dealer insurer or own).
3. Policy issued with chassis/motor numbers and financier.
4. Policy copy for Vahan.
5. Commission MIS from insurer reconciled monthly.
6. Renewal reminder 30–45 days before expiry each year.
7. Claims support through the body shop.

### 6.7 Payment collection

- Booking amount, part payments, balance, loan disbursement, exchange adjustment, subsidy receivable.
- Every receipt has: date, mode, reference (UTR/cheque/UPI), amount, received by, against lead/booking.
- Cash limits and reporting (cash above legal limits not accepted **(verify current limit under the Income Tax Act, Section 269ST)**).
- Daily cash/bank reconciliation by Accounts; cashier day close.
- Refunds through bank only, with approval.

### 6.8 Allocation and stock matching

- Booking queue ordered by booking date and payment status (many dealers allot only after full payment or finance DO).
- Match model/variant/colour; choose oldest stock first (FIFO) to cut floor-plan interest.
- Lock the chassis to the booking; prevent double allocation.
- Re-allocation only with approval and a log.

### 6.9 Invoicing and OEM reporting

- Invoice only after payment is complete or DO received, chassis allocated, KYC complete, insurance ready.
- Invoice data: customer name exactly as KYC, address, GSTIN (if business buyer, for input credit), HSN, taxable value, GST, chassis, engine/motor number, battery number (EV), colour, hypothecation.
- OEM DMS: "retail" or "sold" entry with customer details (needed for warranty activation and scheme claims).
- Cancellation of an invoice needs a credit note and OEM re-billing; this is a high-control event.

### 6.10 Registration (India)

1. Collect Form 20 signed, Form 21 (dealer issues), Form 22 (manufacturer roadworthiness), insurance, invoice, KYC, address proof, Form 34 if financed, Form 60 if no PAN.
2. Enter on Vahan; pay road tax and registration fee online.
3. Temporary registration (valid 30 days in most states **(verify)**) or permanent registration at dealer point.
4. Fancy / choice number auction if asked.
5. Registration number allotted; HSRP ordered with the vendor; fitment at dealer or customer location.
6. RC printed and dispatched (or digital RC through DigiLocker / mParivahan).
7. For commercial vehicles: fitness certificate, goods-carriage classification, permit (battery-operated vehicles have been exempted from permit requirements by MoRTH **(verify for the vehicle type and state)**), yellow-on-green plate for commercial EVs.

### 6.11 PDI checklist (summary)

- Documents: chassis and motor/engine number match invoice and Form 22.
- Exterior: paint, panel gaps, dents, scratches, glass, lights, tyres (make, date, pressure), spare.
- Interior: seats, upholstery, dashboard, switches, horn, wipers, mirrors, AC (cars), seat belts.
- Mechanical / electrical: brakes, steering, suspension noise, 12 V battery, fluids.
- EV: traction battery SoC and health, charger and cable, charging test, motor and controller fault codes, telematics/app linking, software version, battery serial number recorded.
- Accessories fitted and working.
- Toolkit, jack, first-aid kit, manuals, keys.
- Wash and final look.
- Signed by PDI technician and delivery coordinator; customer copy.

### 6.12 Delivery ceremony and orientation

- Vehicle covered or decorated in the delivery bay.
- Document folder: invoice, insurance, RC or temporary registration, warranty card, owner's manual, service booklet, accessory bill, loan papers, roadside assistance card, charger warranty (EV).
- Orientation: controls, safety, charging/fuelling, range tips, service schedule, warranty terms, app, emergency number.
- Introduction to the service advisor; first service booking.
- Photo, social media post (with consent), gift.
- Gate pass issued; security logs vehicle out.

### 6.13 Cancellation and refund

- Customer request in writing; reason captured.
- Manager approval; deductions as stated on the booking form.
- Refund to the original payment source by bank transfer.
- Chassis released, OEM booking reversed, any invoice reversed with credit note, insurance cancelled, Vahan application withdrawn if started.
- Staff incentive reversed; cancellation report reviewed monthly.

### 6.14 Complaint handling

- Channels: phone, WhatsApp, email, OEM call centre, social media, walk-in.
- Ticket: category (sales promise, delivery delay, document, vehicle defect, service, billing, staff behaviour), severity, owner, SLA.
- Root cause and closure with customer confirmation; OEM escalation ladder for unresolved cases.

---

## 7. After the sale: ownership lifecycle

### 7.1 Service journey (customer and dealer)

1. **Reminder:** service due by date or km (SMS/WhatsApp/call from service BDC).
2. **Appointment:** slot booked, pick-up requested or not.
3. **Arrival:** greeted, security logs the vehicle in.
4. **Reception:** service advisor walk-around with customer (dents, belongings, fuel/charge level, odometer), records customer complaints ("voice of customer").
5. **Job card:** jobs, estimate, promised time, customer signature.
6. **Workshop:** controller assigns bay and technician; diagnosis; additional work found → customer approval by call/WhatsApp with revised estimate.
7. **Parts:** issued against the job card; out-of-stock parts → VOR order.
8. **Quality check and road test.**
9. **Wash.**
10. **Billing:** labour, parts, consumables, taxes; warranty/free service portions billed to OEM.
11. **Delivery:** advisor explains work done, old parts shown, payment, gate pass.
12. **Follow-up call** within 3 days; OEM CSI survey.
13. **Next service due** set.

### 7.2 Warranty

- Standard vehicle warranty and battery/motor warranty (EV) per OEM terms; extended warranty if bought.
- **Claim:** failure diagnosed, warranty eligibility checked (registration date, km, service history, no misuse), part replaced, claim filed in OEM portal with photos, part kept for return, claim settled as a credit note.
- **Goodwill:** OEM or dealer pays outside warranty for customer retention.
- **Recalls / campaigns:** OEM list of chassis, dealer contacts owners, fixes, reports.

### 7.3 Insurance renewal and claims

- Renewal calls each year; NCB retained.
- Accident: customer informs insurer and dealer, tow-in, surveyor, estimate, approval, repair, customer pays deductible/depreciation, insurer pays the rest.

### 7.4 Roadside assistance

- 24×7 number; towing, jump-start, flat tyre, low charge (EV mobile charging), key lockout.

### 7.5 Loyalty, referral and upgrade

- Loyalty bonus on the next purchase, referral rewards, customer events, birthday and purchase-anniversary messages, fleet upgrade proposals.

---

## 8. Back office and OEM-facing processes

### 8.1 Dealer–OEM relationship

| Process | What happens |
|---|---|
| Dealer agreement and standards | Facility standards (CI/CVI), staffing norms, training, audits |
| Business plan and targets | Annual and monthly volume targets by model; retail and wholesale targets |
| Order and allocation | Dealer places stock orders; OEM allocates based on targets, payments and production; hot models are rationed |
| Wholesale (billing to dealer) | OEM invoices the dealer for each vehicle; payment by trade advance or through inventory funding bank |
| Transit | OEM-appointed transporter, e-way bill, transit insurance; damage claims |
| Retail reporting | Each sale reported to OEM DMS (customer data for warranty and schemes) |
| Schemes and claims | Monthly circulars, claim submission, settlement through credit notes, deductions for non-compliance |
| Warranty claims | Portal submission, part return, settlement |
| Parts ordering | Stock and emergency orders |
| Audits | Process audit, stock audit, claim audit, mystery shopping, SSI/CSI scores linked to incentives |
| Training | Product launches, sales process, technician certification (EV high voltage) |
| Marketing co-op | Approved activities partly funded by OEM |
| Rebilling / chassis swap | When an invoice must change (wrong customer, wrong chassis), OEM and dealer reverse and re-bill; needs strict tracking |

### 8.2 Inventory funding (floor plan)

- A bank funds each vehicle as it is billed by the OEM; the dealer pays interest daily until the vehicle is sold and repaid.
- The bank audits physical stock; sold-not-repaid ("SOT" — sold out of trust) is a serious breach.
- Ageing stock costs money, so FIFO allocation matters.

### 8.3 Government scheme claims (EV)

- PM E-DRIVE: the dealer authenticates the buyer through Aadhaar (face authentication in the PM E-DRIVE app), generates an e-voucher showing vehicle, subsidy and final price, the buyer signs it, the dealer uploads it and the OEM claims the subsidy. The subsidy is deducted from the invoice, so it becomes a receivable until the OEM/scheme passes it back. Category windows and amounts change; e-3W (L5) status has conflicting reports, so **verify on pmedrive.heavyindustries.gov.in**.
- State EV policies: purchase incentive, road-tax and registration-fee waivers, scrapping incentives **(verify by state)**.

### 8.4 Accounting cycle

| Frequency | Activities |
|---|---|
| Daily | Cash book, bank entries, receipts matched to customers, day-end cash count, sales report |
| Weekly | Debtors follow-up, finance disbursement chase, claim submission |
| Monthly | GST returns, TDS, payroll and incentives, insurance and finance payout reconciliation, OEM statement reconciliation, stock audit, scheme claim filing, P&L by department, Tally pack |
| Quarterly / yearly | TDS returns, statutory audit, income tax, OEM annual review |

### 8.5 Incentive calculation (staff)

- Inputs: retails per executive, model mix, target achievement slab, finance/insurance/accessories/EW penetration, discount given vs allowed, cancellations, customer feedback score.
- Output: monthly incentive sheet approved by Sales Head and Accounts; disputes logged.

### 8.6 MIS and reporting

- **Daily:** enquiries, test drives, bookings, retails, deliveries, collections, stock, cancellations.
- **Monthly:** target vs achievement by model and executive, funnel conversion, source effectiveness, lost analysis, finance/insurance penetration, scheme claims status, stock ageing, gross margin, department P&L.
- **Owner view:** total gross by line, receivables (customer, financier, OEM, insurer, subsidy), cash position, inventory interest.

---

## 9. Interlinks: who hands what to whom

### 9.1 Hand-off map

```
Marketing ──leads──► BDC ──qualified appointment──► Sales consultant
Sales ──needs, budget──► F&I (finance file, insurance quote)
Sales ──trade-in vehicle──► Used car (evaluation) ──agreed value──► Sales / Accounts
Sales ──booking──► Sales admin / Inventory (allocation) ──chassis──► Accounts (invoice)
Sales ──deal sheet──► Manager approval ──► CRM verification call
F&I ──DO, policy──► Accounts (invoice with hypothecation) ──► RTO executive (Vahan)
Accounts ──payment clear──► Delivery coordinator
Inventory ──chassis──► Service/PDI ──accessories fitment──► Delivery bay
RTO executive ──registration no.──► HSRP vendor ──plates──► PDI/Delivery
Delivery ──customer handover──► CRM/BDC (feedback) ──► Service BDC (first service)
Accounts ──retail data──► OEM (DMS retail, scheme & subsidy claims) ──credit notes──► Accounts
Service ──warranty jobs──► Warranty admin ──claims──► OEM ──credit──► Accounts
Service ──parts demand──► Parts ──orders──► OEM
Body shop ──claims──► Insurer ──payment──► Accounts
Insurance desk ──policy──► Insurer MIS ──commission──► Accounts
F&I ──disbursement──► Accounts ──payout claim──► Financier
HR ──incentive rules──► Accounts (payroll) ◄── Sales results, cancellations, discounts
Service history, insurance expiry, loan end ──► Sales (upgrade / exchange lead)
```

### 9.2 Department interlink matrix

Rows hand to columns. ● = strong daily dependency, ○ = periodic.

| From \ To | Sales | F&I | Used | Inventory | Accounts | RTO/Delivery | Service | Parts | BDC/CRM | OEM |
|---|---|---|---|---|---|---|---|---|---|---|
| **Marketing** | ● | | | | ○ | | ○ | | ● | ○ |
| **BDC/CRM** | ● | | | | | | ● | | – | ○ |
| **Sales** | – | ● | ● | ● | ● | ● | ○ | | ● | ● |
| **F&I** | ● | – | | | ● | ● | ○ | | ○ | |
| **Used car** | ● | ○ | – | | ● | ○ | ● | ○ | | ○ |
| **Inventory** | ● | | | – | ● | ● | ● | | | ● |
| **Accounts** | ● | ● | ● | ● | – | ● | ● | ● | | ● |
| **RTO/Delivery** | ● | ○ | | ○ | ● | – | ● | | ● | ○ |
| **Service** | ○ | ○ | ● | ○ | ● | ● | – | ● | ● | ● |
| **Parts** | | | ○ | | ● | | ● | – | | ● |
| **OEM** | ● | | ○ | ● | ● | ○ | ● | ● | ○ | – |

### 9.3 Shared data objects (the backbone)

| Object | Created by | Used by |
|---|---|---|
| Customer | BDC / Sales | Every department, for life |
| Lead / Enquiry | BDC / Sales | Sales, Marketing (ROI), Management |
| Activity / follow-up | Sales, BDC | TL, Manager, CRM |
| Test drive | Sales | Security, Management |
| Quotation | Sales | Manager (approval), Accounts (price check) |
| Exchange evaluation | Used car | Sales, Accounts, OEM (bonus claim) |
| Finance file | F&I | Accounts, RTO, Financier |
| Insurance policy | F&I | RTO, Accounts, Service (claims, renewal) |
| Booking / deal sheet | Sales | Approvals, Inventory, Accounts, OEM |
| Payment / receipt | Accounts | Sales (status), Delivery gate, Owner |
| Vehicle / chassis | Inventory (from OEM invoice) | Allocation, Invoice, Insurance, RTO, PDI, Service, Warranty, Claims |
| Invoice | Accounts | OEM, RTO, Financier, Insurer, Tax |
| Scheme / claim | Accounts (from OEM circular) | Sales (pricing), Accounts (receivable), Owner (margin) |
| Registration | RTO executive | Delivery, Customer, Financier |
| Delivery | Delivery coordinator | Sales (retail count), CRM (feedback), Service |
| Job card | Service | Parts, Warranty, Accounts, CRM |
| Complaint ticket | CRM | Concerned department, OEM |
| Incentive | HR / Accounts | Staff, Owner |

---

## 10. Documents and forms register

### 10.1 From the customer

| Document | Why |
|---|---|
| Aadhaar | KYC, address, PM E-DRIVE authentication |
| PAN (or Form 60) | KYC, high-value transaction reporting, TCS |
| Address proof (if different) | Registration jurisdiction |
| Photographs | Loan, registration |
| Driving licence | Test drive, commercial vehicle eligibility |
| Income proof / bank statements / ITR | Loan |
| GSTIN | Business buyer invoice |
| Old vehicle RC, insurance, NOC | Exchange |
| Corporate ID / previous-customer proof | Scheme eligibility |
| Signed Form 20, Form 34 | Registration, hypothecation |

### 10.2 Issued or prepared by the dealer

| Document | Stage |
|---|---|
| Quotation / proforma invoice | Negotiation, loan |
| Booking form and receipt | Booking |
| Deal sheet (internal) | Approval |
| Payment receipts | Each payment |
| Exchange evaluation sheet, purchase agreement, Form 29/30 | Exchange |
| Tax invoice (and e-invoice IRN where required) | Invoicing |
| Form 21 (sale certificate) | Registration |
| Form 22 (roadworthiness, from manufacturer) | Registration |
| Temporary registration certificate | Delivery |
| Insurance policy and cover note | Before registration |
| PDI checklist | Before delivery |
| Delivery note / delivery checklist | Delivery |
| Gate pass | Delivery, service |
| Warranty card / activation | Delivery |
| E-voucher (PM E-DRIVE) | Invoicing (EV) |
| Credit note | Cancellation, rebilling |
| Refund voucher | Cancellation |
| Job card, estimate, service invoice | Service |

### 10.3 Dealer's own licences and statutory items

- OEM dealer agreement.
- Trade certificate (Form 16 application, Form 17 certificate under CMVR) for holding and moving unregistered vehicles.
- GST registration, shop and establishment licence, fire NOC, pollution consent (workshop), insurance agency / broker tie-up licence (IRDAI), DSA agreements with financiers.

---

## 11. KPI dictionary

| KPI | Formula | Owner |
|---|---|---|
| Speed to lead | Time from lead created to first contact | BDC |
| Contact rate | Leads contacted ÷ leads received | BDC |
| Enquiry to test drive | Test drives ÷ enquiries | Sales |
| Test drive to booking | Bookings ÷ test drives | Sales |
| Enquiry to booking (conversion) | Bookings ÷ enquiries | Sales |
| Booking to retail | Retails ÷ bookings (same cohort) | Sales |
| Cancellation rate | Cancelled bookings ÷ bookings | Sales |
| Lost to competition | Lost with competitor reason ÷ lost | Sales |
| Average discount per unit | Total dealer discount ÷ units | Sales Head |
| Gross per unit (GPU) | (Vehicle margin + schemes earned + F&I + accessories) ÷ units | Owner |
| Finance penetration | Dealer-arranged loans ÷ retails | F&I |
| Insurance penetration | Dealer policies ÷ retails | F&I |
| Accessories per unit | Accessories revenue ÷ retails | Accessories |
| Exchange penetration | Exchange deals ÷ retails | Used car |
| EW / AMC penetration | Products sold ÷ retails | F&I |
| On-time delivery | Delivered on promised date ÷ deliveries | Delivery |
| Booking-to-delivery days | Average days | Delivery |
| SSI / delivery NPS | OEM survey score | Sales |
| Stock days | Stock ÷ average daily retail | Inventory |
| Stock ageing 90+ | Units older than 90 days | Inventory |
| Scheme claim settlement % | Settled ÷ claimed | Accounts |
| Claim ageing | Days from claim to settlement | Accounts |
| Debtors days | Receivables ÷ daily sales | Accounts |
| Service retention | Vehicles returning for service ÷ eligible | Service |
| Technician efficiency | Billed hours ÷ worked hours | Service |
| CSI | OEM service survey | Service |
| Repeat repair | Comebacks ÷ jobs | Service |
| Parts fill rate | Lines supplied from stock ÷ lines requested | Parts |
| Service absorption | Fixed-ops gross ÷ total overheads | GM |
| Cost per lead / per sale | Marketing spend ÷ leads or sales | Marketing |
| Insurance renewal retention | Renewed ÷ due | Insurance |

---

## 12. Controls, leakage and fraud points

| Risk | Where it happens | Control |
|---|---|---|
| Unauthorised discount | Negotiation | Role-based limits, approval workflow, verification call to customer |
| Side deals / cash not recorded | Booking, delivery | Receipts only through the system, customer verification call, payment-before-gate-pass |
| Double allocation of a chassis | Allocation | Chassis lock, audit log |
| Delivery before full payment | Delivery | Gate pass blocked until balance = 0 or approved credit |
| Fake scheme claims | Scheme | Proof documents, OEM audit, customer verification |
| Exchange bonus without real exchange | Exchange | Old RC transfer proof |
| Subsidy fraud | EV scheme | Aadhaar face authentication, e-voucher, physical vehicle and buyer photo |
| Insurance commission leakage | Insurance | Insurer MIS reconciled policy by policy |
| Finance payout not received | F&I | Disbursement and payout reconciliation by financier |
| Wrong invoice / rebilling abuse | Invoicing | Credit note approval, OEM rebill log, chassis history |
| Lead stealing between executives | Lead management | De-dupe by mobile, ownership rules, audit log |
| Test-drive vehicle misuse | Test drive | Gate log, km log, licence copy |
| Stock theft / sold out of trust | Inventory | Gate pass, periodic physical audit, bank audit |
| Data privacy (Aadhaar, PAN, phone) | Everywhere | Role-based access, masking, consent, retention limits under the DPDP Act 2023 |
| Cash limit breach | Payments | System block above the legal cash limit **(verify)** |
| Edit after approval | Deal sheet | Lock after approval, edit log, re-approval |

---

## 13. EV commercial three-wheeler specifics

These change the generic flow above for a dealer like Euler.

| Area | What is different |
|---|---|
| Customer | Owner-drivers, small fleet owners, logistics and e-commerce aggregators, FMCG distributors. The decision is about earnings per day, not lifestyle. |
| Needs analysis | Daily km, payload, route type, charging location (home, depot, public), working hours, current vehicle (diesel/CNG auto, other EV), earning contract. |
| Selling points | Running cost per km vs diesel/CNG, range, payload, battery warranty, uptime, resale, financing EMI vs daily savings. |
| Test drive | Often loaded trial or a day trial on the customer's route. |
| Finance | Specialised NBFCs; credit-thin customers; higher down payment or guarantor; sometimes battery leasing or OEM-backed financing **(verify per program)**. |
| Insurance | Commercial policy, goods-carrying vehicle; annual. |
| Subsidy | PM E-DRIVE e-voucher with Aadhaar face authentication (category status to be verified); state subsidies; road-tax waivers in many states. |
| Registration | Commercial (goods) registration, fitness certificate, EV plate (yellow text on green for commercial), permit exemption for battery-operated vehicles **(verify)**. |
| PDI | Traction battery SoC and health, charger test, telematics activation, battery and motor serial capture. |
| Delivery | Charging training, app onboarding, driver training, uptime support numbers. |
| After-sale | Uptime is income for the customer: fast breakdown response, battery health monitoring, spare battery or replacement vehicle policies, telematics alerts. |
| Repeat sales | Fleet expansion; referrals among driver communities are strong. |
| Field sales | Market/mandi activations, fleet meets, aggregator tie-ups, sub-dealer network. |

---

## 14. Gap map against the Euler CRM

Method: page list in `frontend/src/pages/` and keyword search over `backend/*.py` and the pages on 30 October 2026. "Not found" means no matching code was found by keyword search. It does not prove the feature is absent under another name.

| Process (this document) | In the CRM today | Notes |
|---|---|---|
| Lead capture, import, assignment | `Leads`, `NewLeadDrawer`, `LeadImport`, `Activities` | Present |
| WhatsApp and calls | `WhatsAppInbox`, `LeadWhatsApp`, `backend/botspace.py`, `backend/exotel.py` | Present |
| Lost / dropped leads | Status values Lost, Dropped | Present; check reason codes and competitor capture |
| Test drive | Not found (`test drive` has no matches) | **Gap:** no test-drive record, licence capture or vehicle log |
| Quotation | `Quotations`, `PriceList`, `PriceMaster` | Present |
| Scheme master and funding split | `SchemeMaster`, `backend/commercial.py` | Present |
| Discount approval | `Approvals` | Present |
| Booking | `Bookings`, `BookEnquiryDrawer` | Present |
| Deal verification call | `DealVerify`, Exotel prompts | Present |
| Exchange evaluation | Only an exchange bonus / exchange margin in commercial code | **Gap:** no evaluation sheet, old-vehicle documents, Form 29/30 tracking |
| Finance | `Finance` | Present; check financier DO, disbursement and payout tracking |
| Insurance | `Insurance`, `InsuranceAgents`, `InsuranceMisUpload`, `InsurancePayoutReport` | Present, including MIS reconciliation |
| Allocation | `Allocation`, `Inventory` | Present |
| Payments | `Payments`, `AccountsDashboard` | Present |
| OEM billing / rebilling | `OemBilling`, `backend/oem_sync.py`, `backend/coulson.py` | Present |
| PM E-DRIVE e-voucher / subsidy receivable | Not found | **Gap** if the scheme applies to the models sold (verify scheme status) |
| Registration (Vahan, temporary reg., RC) | Not found (`vahan` has no matches) | **Gap:** no registration number, RC status or TAT tracking |
| HSRP | Not found | **Gap** |
| PDI | `pdi` matches exist in 9 files | Partial; check whether there is a full checklist with battery/motor serials |
| Accessories | Matches in 8 files | Partial; check fitment workflow |
| Delivery | `Deliveries`, `LeadDrawer` delivery tests | Present |
| Post-delivery feedback / Google review | Review call added (commit `05450b2`) | Present; check day-7 and day-30 calls |
| Cancellation / refund | `Cancellations` | Present |
| OEM scheme claims | `Claims`, `ClaimsDesk`, `ClaimReconciliation`, `ClaimExceptions`, `OemClaims`, `OemClaimDashboard`, `OemExtraSupport` | Present and detailed |
| Incentives | `IncentiveMaster`, `ExecutiveIncentive` | Present |
| Dealer earnings / owner P&L | `DealerEarnings`, `EarningsReport`, `OwnerCommercialReport` | Present |
| Tally | `backend/tally_pack.py` | Present |
| Audit and edit logs | `AuditLog`, `EditLog` | Present |
| Role dashboards | Executive, Sales GM, Field, Accounts | Present |
| Complaint tickets | Not found as a module | **Gap** |
| Service / workshop (job card, appointments, reminders) | Not found (`job card` has no matches) | **Gap:** the whole fixed-operations side is outside the CRM |
| Warranty claims (service side) | Not found | **Gap** (only sales-scheme claims exist) |
| Parts / spares | 5 keyword hits, no parts module | **Gap** |
| Insurance renewal reminders | Not confirmed | Check |
| Stock ageing / floor-plan interest | `Inventory` (not checked for ageing) | Check |
| Referral tracking | Not checked | Check |

The sales-to-delivery-to-claims chain is well covered. The suggested order for closing gaps, by impact on money and on customer experience:

1. Registration and HSRP tracking (customers chase it; financiers need the RC).
2. Test-drive records (conversion data and vehicle control).
3. Exchange evaluation (money moves; OEM bonus needs proof).
4. Subsidy e-voucher and receivable, if a scheme applies.
5. Complaint tickets.
6. Service and warranty, if the dealership runs a workshop. This is a separate module, not a field on a lead.

---

## 15. Glossary

| Term | Meaning |
|---|---|
| 3S / 2S / 1S | Sales, Service, Spares formats |
| AMC | Annual maintenance contract |
| ASM / RM | Area sales manager / regional manager |
| BDC | Business development centre (call team) |
| CSI / SSI | Customer satisfaction index (service) / sales satisfaction index |
| DMS | Dealer management system (usually OEM-provided) |
| DO | Delivery order from a financier |
| DSE | Dealer sales executive |
| EW | Extended warranty |
| F&I | Finance and insurance |
| FIFO | First in, first out (oldest stock sold first) |
| Fixed ops | Service, parts, body shop |
| GPU | Gross profit per unit |
| HSRP | High-security registration plate |
| IDV | Insured declared value |
| L5 | Category of three-wheelers with higher speed and power (e-autos, cargo) |
| NCB | No-claim bonus |
| PDI | Pre-delivery inspection |
| PUDO | Pick-up and drop |
| RC | Registration certificate |
| Retail | Sale to the end customer (as against wholesale from OEM to dealer) |
| RSA | Roadside assistance |
| SA | Service advisor |
| SOT | Sold out of trust (sold but floor-plan loan not repaid) |
| TP / OD | Third-party / own-damage insurance |
| Vahan | National vehicle registration system |
| Variable ops | New, used, F&I, accessories |
| VOR | Vehicle off road (urgent parts order) |
| Wholesale | OEM billing to dealer |

---

## 16. Sources

- [AutoAlert: The dealership org chart](https://www.autoalert.com/dealership-org-chart/)
- [Edmunds: Roles of the car dealership sales department staff](https://www.edmunds.com/car-buying/roles-of-the-car-dealership-sales-department-staff.html)
- [NADA dealership organisation chart (PDF)](https://nada.org/media/3247/download)
- [Hendrick Automotive career paths](https://www.hendrickcars.com/hendrick-careers/career-paths.htm)
- [CBT News: Improving BDC processes](https://www.cbtnews.com/how-dealers-can-improve-their-bdc-processes/)
- [Digital Dealer: BDC for fixed operations](https://www.digitaldealer.com/dealership-utilize-bdc-fixed-operations/)
- [AutoNation FY2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/350698/000162828026007800/an-20251231.htm)
- [AutoNation FY2025 annual report](https://www.sec.gov/Archives/edgar/data/350698/000162828026018709/a2025ars.pdf)
- [91Wheels: Pre-delivery inspection guide](https://www.91wheels.com/buyers-guide/the-ultimate-pre-delivery-inspection-guide-for-new-cars)
- [Motomotar: Car registration process in India 2026](https://motomotar.com/car-buying-guide/car-registration-process-india/)
- [Tamil Nadu STA: Form 20](https://tnsta.gov.in/about_us/form20.pdf)
- [Odisha Transport: trade certificate notification](https://odishatransport.gov.in/Application/uploadDocuments/Notification/Rules_1620118749.pdf)
- [Policybazaar: Form 17 trade certificate](https://www.policybazaar.com/rto/form-17/)
- [FADA president's message on trade certificate amendments](https://fada.in/president-message.php?id=23)
- [PM E-DRIVE official portal](https://pmedrive.heavyindustries.gov.in)
- [ClearTax: PM E-DRIVE scheme](https://cleartax.in/s/pm-e-drive-scheme)
- [Business Standard: faster subsidy disbursal under PM E-DRIVE](https://business-standard.com/industry/auto/govt-aims-to-fasten-subsidy-claim-disbursals-for-evs-under-pm-e-drive-125042700505_1.html)
- [Mahindra Last Mile Mobility: PM E-DRIVE](https://mahindralastmilemobility.com/blogs/pm-e-drive-scheme)
- [GrowthJockey: Dealer KPIs OEMs track](https://www.growthjockey.com/blogs/dealer-kpis-oems-track)
- [ICICI Direct: Maruti Suzuki Q4 FY26 note](https://www.icicidirect.com/mailcontent/idirect_marutisuzuki_q4fy26.pdf)
- [Autocar Pro: Maruti December 2025 retail and inventory](https://www.autocarpro.in/news/maruti-suzuki-logs-286000-december-retail-sales-as-inventory-drops-to-three-days-130379?amp=1)

Parts of this document (role duties, sub-process steps, controls) come from general industry practice rather than one cited source. The Indian statutory points marked **(verify)** change by state and over time.
