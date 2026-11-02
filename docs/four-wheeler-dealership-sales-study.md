# Four-wheeler dealership: sales side study

Date: 2 November 2026.
Purpose: groundwork for a new CRM for a passenger-car (four-wheeler) dealership in India. It lists every sales-side department, role, process, step, document and hand-off. It walks through the purchase from both sides: what the customer does and what the dealership does.

**In scope:** everything from the first enquiry to the car leaving the showroom, plus the follow-up after delivery. That includes sales, finance, insurance, exchange, accessories, stock, accounts as it touches a sale, registration and delivery.
**Out of scope for now:** service workshop, spare parts and body shop.

Benchmarks: Indian franchised car dealers (Maruti Arena/NEXA, Hyundai, Tata, Mahindra, Toyota, Kia, Honda) and the large US dealer groups (AutoNation, Lithia, Penske, Hendrick), which have the most mature sales structure.

Tax rates, transport rules and OEM policies change. Items marked **(verify)** should be confirmed against the current notification, state transport rules or the OEM dealer manual before they become a CRM rule.

---

## Contents

1. [The macro picture](#1-the-macro-picture)
2. [Sales-side organisation](#2-sales-side-organisation)
3. [Every sales-side department and role](#3-every-sales-side-department-and-role)
4. [The purchase journey: customer side and dealer side](#4-the-purchase-journey-customer-side-and-dealer-side)
5. [Sub-processes in micro detail](#5-sub-processes-in-micro-detail)
6. [Special sales channels](#6-special-sales-channels)
7. [Stock and OEM side of sales](#7-stock-and-oem-side-of-sales)
8. [Accounts work that touches a sale](#8-accounts-work-that-touches-a-sale)
9. [Interlinks: who hands what to whom](#9-interlinks-who-hands-what-to-whom)
10. [Record lifecycles and statuses](#10-record-lifecycles-and-statuses)
11. [Approvals and controls](#11-approvals-and-controls)
12. [Documents register](#12-documents-register)
13. [KPIs and reports](#13-kpis-and-reports)
14. [What the CRM has to cover](#14-what-the-crm-has-to-cover)
15. [Glossary](#15-glossary)
16. [Sources](#16-sources)

---

## 1. The macro picture

### 1.1 Who is involved in one car sale

```
OEM (manufacturer)
  price list · scheme circulars · allocation · wholesale billing · DMS · targets
        │
        ▼
Dealership (sales side)
  Marketing → Lead team/BDC → Showroom sales → Finance & Insurance → Exchange
  → Sales admin / Stock → Accounts → Registration (RTO) → Accessories & PDI → Delivery
  → Customer relations (feedback, referrals)
        │
        ▼
Customer (individual, business, corporate employee, fleet, defence/CSD, government)

Outside parties: banks and NBFCs · insurers · RTO / Vahan · HSRP supply · FASTag issuer ·
inventory-funding bank · transporter · used-car buyers and scrapping facility ·
lead portals · GST and income-tax systems
```

### 1.2 Dealer formats on the sales side

| Format | Sales role |
|---|---|
| Main showroom (3S or 1S) | Full sales process, billing, delivery |
| City outlet / satellite showroom | Display, test drive, booking; billing and delivery through main dealer |
| Rural / true-rural outlet | Field-led selling, booking; billing through main dealer |
| Experience centre / mall kiosk / pop-up | Lead generation and booking |
| Online (OEM website, dealer website) | Online booking with a booking amount; dealer completes the sale |
| Used-car outlet (OEM certified programme) | Buys exchange cars, sells used cars |

### 1.3 Where the dealer earns on a car sale

| Income line | Notes |
|---|---|
| Vehicle margin | Selling price minus dealer purchase price (OEM wholesale invoice), after dealer discount |
| OEM schemes and incentives | Retail and wholesale targets, model support, consumer offers, exchange, corporate, loyalty, rural offers. Claimed back from OEM. |
| Finance payout | Commission from bank/NBFC per loan |
| Insurance commission | Through broker or corporate-agent tie-up |
| Extended warranty, RSA, service packages | Margin per product |
| Accessories | High margin; fitted before delivery |
| Coatings / protection products | Ceramic, anti-rust, underbody, interior protection |
| Exchange | Margin on reselling the old car plus OEM exchange bonus |
| FASTag, number plate, registration | Mostly pass-through; "handling" or "logistics" charges are banned or restricted by many states and OEMs **(verify)** |

For comparison, AutoNation's 2025 accounts show new cars at about 49% of revenue but only about 13% of gross profit, while finance and insurance were about 5% of revenue and about 30% of gross profit. The add-ons around the car matter as much as the car.

---

## 2. Sales-side organisation

Reporting lines vary. This is the full version; smaller dealers merge roles.

```
Dealer Principal / Owner
└── CEO / General Manager
    ├── Sales Head / General Sales Manager (GSM)
    │   ├── Showroom Sales Manager(s)  (one per showroom or per brand channel)
    │   │   ├── Team Leaders (TL)
    │   │   │   └── Sales Consultants / DSEs (Dealer Sales Executives)
    │   │   ├── Relationship Managers (premium channel)
    │   │   └── Showroom Host / Receptionist
    │   ├── Field / Rural Sales Manager
    │   │   └── Rural sales executives, outlet in-charges, sub-dealer coordinators
    │   ├── Corporate & Fleet Sales Manager
    │   │   └── Corporate executives, fleet/taxi executives, CSD/CPC desk, government desk
    │   ├── Digital / Online Sales Manager
    │   │   └── Digital lead executives
    │   ├── Pre-owned / Exchange Manager
    │   │   └── Evaluators, used-car sales, document executive
    │   ├── F&I Manager
    │   │   ├── Finance executives (bank and NBFC desks)
    │   │   └── Insurance executives
    │   ├── Accessories Manager
    │   │   └── Accessory sales, fitment coordinator
    │   ├── Sales Admin / Sales Coordinator
    │   │   └── Booking desk, allocation desk, OEM DMS operator, invoice preparation
    │   └── Delivery Manager
    │       ├── PDI team
    │       ├── Registration (RTO) executive
    │       └── Delivery coordinators
    ├── Lead Centre / BDC Manager
    │   └── Tele-callers (inbound, outbound, digital leads)
    ├── Marketing Manager
    │   └── Digital, events, activations
    ├── Customer Relations Manager (CRM)
    │   └── Feedback callers, complaint handling, verification calls
    ├── Accounts Manager (sales-related staff)
    │   ├── Cashier
    │   ├── Receivables (customer, financier, OEM, insurer)
    │   ├── OEM scheme-claims accountant
    │   └── Tax (GST, TCS), Tally
    ├── Stock Yard / Inventory In-charge
    │   └── Yard staff, drivers, security (gate register)
    └── HR & Admin
        └── Recruitment, training, attendance, incentives
```

---

## 3. Every sales-side department and role

### 3.1 Reception / showroom host

- Greets every walk-in; records name, phone, purpose, model interest, source in the walk-in register.
- Checks whether the customer already has an assigned consultant (repeat visit).
- Assigns a consultant by roster, territory or source.
- Offers refreshments, notes wait time.
- Hands over to the consultant with the walk-in slip.
- **Measures:** walk-ins recorded against gate count, time to greet, time to consultant.

### 3.2 Lead centre / BDC (business development centre)

- Receives digital leads (OEM website, dealer website, Google, Meta, lead portals, WhatsApp, missed calls).
- Calls within minutes; qualifies (model, city, timeline, budget, finance, exchange).
- Books a showroom visit, home visit or home test drive.
- Assigns to a consultant and confirms the appointment by message.
- Calls back no-shows, dormant leads, lost leads after a cooling period.
- **Measures:** speed to lead, contact rate, appointments set, show rate, leads converted.

### 3.3 Sales consultant (DSE)

Owns the customer from first contact to delivery.
- Prospecting: calls, referrals, society and office activations, existing customers.
- Needs analysis, product presentation and walk-around, competitor comparison.
- Test drive (showroom or home).
- Quotation, EMI calculation, scheme explanation.
- Negotiation within personal discount limit; raises approval for anything above.
- Hands over to finance, insurance, exchange and accessories.
- Booking: form, booking amount, documents.
- Follow-up during waiting: allocation update, payment reminders, document collection.
- Delivery: present the car, explain features, handover documents.
- Post-delivery: thank-you call, review request, referral request.
- Logs every activity and next follow-up date.
- **Measures:** enquiries handled, test drives, bookings, retails, conversion, discount per car, finance/insurance/accessories/exchange/extended-warranty penetration, cancellations, customer feedback score.

### 3.4 Team leader

- Morning huddle: yesterday's numbers, today's hot leads, follow-ups due.
- Checks follow-up compliance, overdue leads, lost-lead reasons.
- Joins hot-lead negotiations; approves discount within TL limit.
- Allots test-drive cars, handles escalations.
- Evening review of each consultant's day.

### 3.5 Showroom sales manager / sales head

- Monthly targets by model, variant, consultant; tracks daily.
- Discount authority above TL limit; scheme strategy for the month.
- Stock order plan with the OEM; ageing stock push.
- Approves deal sheets, cancellations, refunds, re-allocations.
- Lost-to-competition review; pricing intelligence.
- Owns SSI (sales satisfaction) score and OEM audits.

### 3.6 Field / rural sales

- Village, mandi, haat, fair and panchayat activations.
- Influencer network: existing owners, village heads, bank managers, mechanics, insurance agents.
- Rural-specific schemes (for farmers, panchayat members, teachers, etc.) **(verify per OEM)**.
- Document help (address proof, land records for loans).
- Outlet and sub-dealer management.

### 3.7 Corporate, fleet and institutional sales

- **Corporate:** tie-ups with companies for employee offers; corporate-scheme eligibility proof (employee ID, salary slip).
- **Leasing:** company-leased cars through leasing firms.
- **Fleet / taxi:** taxi operators and ride-hailing drivers; commercial registration; taxi variants.
- **CSD / CPC:** defence and police canteen sales (see §6.4).
- **Government:** tenders, GeM portal orders **(verify)**.

### 3.8 Digital / online sales

- OEM online bookings, website and portal leads, social media campaigns.
- Video calls and virtual walk-arounds, online quotation, online booking payment.
- Hands over to the showroom team for test drive and closure.

### 3.9 Pre-owned / exchange team

- Evaluates the customer's old car; gives a price; buys it.
- Handles document checks and ownership transfer.
- Coordinates the OEM exchange bonus proof.
- Sells or wholesales the bought car; arranges scrapping for end-of-life cars.

### 3.10 F&I (finance and insurance)

- **Finance:** finds out early whether the customer will pay cash or take a loan, checks eligibility, logs files with banks and NBFCs, gets sanction, collects down payment, gets the delivery order (DO), follows disbursement, claims the dealer payout.
- **Insurance:** quotes, issues the policy before registration, adds the financier's name, sells add-ons, reconciles insurer commission statements, hands renewal data on.
- **Other products:** extended warranty, roadside assistance, service packages, coatings, tyre/alloy protection.

### 3.11 Accessories

- Accessory catalogue and packs per model and variant.
- Pitches at quotation; records the order; sends fitment instructions; quality check; billing.

### 3.12 Sales admin / sales coordinator

- Booking entry in DMS and CRM; booking receipt.
- Allocation queue and chassis allocation.
- OEM order placement, transit tracking.
- Invoice preparation once everything is ready.
- OEM DMS retail entry (needed for warranty activation and scheme claims).
- Scheme claim documents (with Accounts).

### 3.13 Delivery team (PDI, registration, delivery)

- **PDI:** full inspection of the allocated car, accessories fitted, cleaning, photos.
- **Registration:** Vahan entry, road tax, number allotment, HSRP, RC.
- **FASTag:** issue and link to the car.
- **Delivery:** schedule, delivery bay, document kit, ceremony, gate pass.

### 3.14 Customer relations

- Deal verification call before invoice (price, discount, promises, payment).
- Feedback calls after delivery; OEM sales-satisfaction survey support.
- Complaint logging, assignment and closure.
- Google review requests; referral collection.

### 3.15 Accounts (sales-related)

- Receipts and refunds, invoices, credit notes.
- Reconciliation of customer payments, loan disbursements, insurer and financier payouts, OEM scheme credit notes.
- GST and TCS; Tally.
- Payment-cleared confirmation that releases the car for delivery.

### 3.16 Stock yard / inventory

- Receives cars from the OEM transporter; checks transit damage; records chassis and engine numbers.
- Yard placement, battery maintenance, periodic start-up, cleaning.
- Physical stock audit (also by the inventory-funding bank).
- Moves cars to PDI and delivery bay; gate register for every movement.
- Demo and test-drive car register.

### 3.17 Marketing

- Campaigns, lead portals, events (launches, exchange melas, loan melas, test-drive camps, society and corporate activations).
- Tracks cost per lead and cost per sale by source.
- OEM co-op marketing claims.

### 3.18 HR and admin (sales-related)

- Recruitment and OEM training and certification of consultants.
- Attendance, targets and incentive calculation.
- Security, key control, test-drive log.

---

## 4. The purchase journey: customer side and dealer side

Each stage shows what the **customer** does, what the **dealership** does, who owns it, and what gets recorded.

### Stage 1: Need and research

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Decides to buy (first car, upgrade, extra car, family change). Researches online: reviews, videos, price, mileage, safety rating, features, waiting period, resale. Asks friends. | Visible online (OEM site, Google profile, portals, social media). Quick replies. Up-to-date price and offers. Reviews managed. | Marketing, Digital | Campaign and source data |

### Stage 2: Enquiry

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Calls, fills a form, sends a WhatsApp message, books online, or walks in | Captures the lead (name, mobile, city, source, model), checks for duplicates, assigns a consultant, first call within minutes, sends brochure and price list | BDC, Reception | Lead with source and owner |

### Stage 3: Qualification and needs analysis

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Explains needs: family size, daily running, city or highway, fuel type (petrol, diesel, CNG, hybrid, EV), transmission, budget, must-have features, current car, timeline | Asks structured questions; recommends model, variant, fuel, colour; checks budget, finance and exchange; sets lead temperature (hot / warm / cold) and next follow-up | Consultant | Requirement profile, temperature, expected purchase date |

### Stage 4: Showroom or home visit and product presentation

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Visits the showroom or gets a home visit; sees the car, sits inside, compares variants | Walk-around (front, side, rear, boot, interior, engine), variant comparison, competitor comparison, total running cost, safety features, connected-car demo | Consultant | Visit logged |

### Stage 5: Test drive

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Drives on a set route, or at home | Checks driving licence, gets the test-drive form signed, logs the car out (km and fuel), explains features during the drive, takes feedback, logs the car back in | Consultant, Security | Test drive record, licence copy, feedback |

### Stage 6: Quotation and price discussion

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Asks for the on-road price, compares with other dealers, asks about offers, EMI, exchange | Prepares the quotation (see §5.6): ex-showroom, TCS if applicable, road tax and registration, insurance, FASTag, extended warranty, accessories, minus offers. Gives EMI options. | Consultant | Quotation (versioned) |

### Stage 7: Exchange evaluation (if trading in)

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Brings the old car with RC, insurance, loan papers | Evaluator inspects, checks documents and challans, offers a price, negotiates, agrees; OEM exchange bonus shown separately | Evaluator | Evaluation sheet, agreed price |

### Stage 8: Negotiation and approval

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Asks for more discount, free accessories, better exchange value, quicker delivery | Consultant offers within limit; above limit goes to TL, then Sales Manager, then GM; final offer frozen | Consultant, TL, Manager | Discount approval with approver and reason |

### Stage 9: Finance

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Chooses cash, dealer-arranged loan or own-bank loan; gives KYC and income documents | Checks eligibility, logs files with banks/NBFCs, gets sanction, confirms down payment, EMI and tenure; gets the delivery order | Finance executive | Loan file, sanction, DO |

### Stage 10: Booking

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Pays the booking amount (often ₹11,000–₹51,000, set by OEM/dealer), signs the booking form | Booking form with model, variant, fuel, transmission, colour (and second choice), price terms (price at invoice date normally applies), offers, accessories, exchange, finance, expected delivery, cancellation terms; booking receipt; entry in DMS and CRM | Consultant, Cashier, Sales admin | Booking, receipt, booking number |

### Stage 11: Verification

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Receives a call from the dealership | Customer relations confirms price, discount, free items, exchange value, delivery promise, and that no cash was paid off-record | Customer relations | Verification outcome |

### Stage 12: Waiting and allocation

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Waits; asks for updates; may change variant or colour | Matches a car from stock or orders from OEM; allocates a chassis; tells the customer the chassis and date; manages changes (variant, colour, name) | Sales admin, Stock | Allocation (chassis to booking), change log |

### Stage 13: Payment completion

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Pays the balance (bank transfer, card, UPI, cheque, demand draft); loan disbursed; hands over the old car | A receipt for every payment; total received matched to the deal; exchange value adjusted; balance tracked | Accounts | Payment ledger per booking |

### Stage 14: Insurance

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Chooses the dealer's policy or brings their own | Policy issued with chassis and engine numbers and financier name; starts before registration | Insurance executive | Policy |

### Stage 15: Invoice

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Checks name, address, model, colour, price, GSTIN (if a business buyer) | Tax invoice raised (GST, TCS where applicable, chassis and engine numbers, hypothecation); e-invoice if required; OEM DMS retail entry | Accounts, Sales admin | Invoice, OEM retail entry |

### Stage 16: Registration and FASTag

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Signs Form 20 (and Form 34 if on loan); chooses a fancy or BH number if wanted | Vahan entry, road tax and fees paid, registration number allotted, HSRP fitted, RC issued (printed or digital); FASTag issued and linked | Registration executive | Registration number, RC status, HSRP, FASTag |

### Stage 17: PDI and accessories

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| May attend the PDI | PDI checklist, accessory fitment, coating if bought, cleaning, number plates fitted, photos | PDI team, Accessories | PDI sheet |

### Stage 18: Delivery

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Comes for delivery (often with family, often on an auspicious date), checks the car, signs the delivery note | Checks payment cleared, documents ready; delivery bay and ceremony; hands over keys, invoice, insurance, RC or registration slip, warranty booklet, manual, accessories bill, loan papers; explains features and app; introduces service contact; photo; gate pass | Delivery coordinator, Consultant | Delivery note, gate pass, photos |

### Stage 19: After delivery

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Starts using the car; may have questions | Thank-you message; feedback calls (day 1–2, day 7, day 30); OEM survey support; Google review request; referral request; pending RC handover; loan file closure | Customer relations, Consultant | Feedback score, review, referrals |

### Stage 20: Repeat and referral

| Customer | Dealership | Owner | Record |
|---|---|---|---|
| Recommends friends; later upgrades or buys a second car | Referral reward; loyalty offer; birthday and purchase-anniversary messages; upgrade offer at the right time | Customer relations, Sales | New leads from the customer |

### Ways a deal can fall through

| Exit | What the dealer does |
|---|---|
| Lead lost or dropped | Records reason (price, competitor, finance, postponed, not reachable, bought elsewhere), competitor and model; manager review; re-engage later |
| Booking cancelled | Cancellation request and reason, approval, refund per booking terms, chassis released, OEM booking cancelled, incentive reversed |
| Loan rejected | Try another lender, higher down payment, co-applicant, or switch to cash |
| Car refused at PDI or delivery | Fix, swap chassis, or escalate to OEM |
| Complaint after delivery | Log, assign, resolve, confirm with customer |

---

## 5. Sub-processes in micro detail

### 5.1 Lead management

1. **Sources:** walk-in, phone call, missed call, OEM website, dealer website, lead portals, Google and Meta ads, WhatsApp, Instagram, referral, existing customer, corporate tie-up, event or activation, field visit, exchange mela, loan mela, online booking.
2. **Capture fields:** name, mobile (main key for duplicates), alternate number, email, city/pincode, source, sub-source, campaign, model, variant, fuel, transmission, colour, current car, exchange yes/no, payment mode (cash/loan), budget, expected purchase date, customer type (individual, business, corporate, fleet, CSD), assigned consultant, created by, date and time.
3. **Duplicate check:** same mobile already open → link to the existing lead and owner, not a new lead.
4. **Assignment:** round robin, territory, source team, language, or returning customer goes to previous consultant.
5. **First response:** minutes for digital leads; same day for others.
6. **Temperature:** hot (buying within 15 days), warm (within 30), cold (later or unclear).
7. **Follow-up:** next follow-up date mandatory; overdue escalates to TL, then manager.
8. **Activity log:** every call, message, visit, test drive, quotation, with outcome and notes.
9. **Pipeline:** New → Contacted → Qualified → Visited → Test drive done → Quoted → Negotiation → Booked; exits: Lost, Dropped, Not interested, Duplicate, Invalid.
10. **Lost analysis:** reason, competitor brand and model, price gap.
11. **Recycling:** dormant and lost leads re-contacted after a set period or put into campaigns.

### 5.2 Walk-in process (showroom standard)

1. Greet at the door within a set time.
2. Walk-in entry: name, mobile, purpose, model, source ("how did you hear about us").
3. Existing lead check by mobile.
4. Consultant assigned; introduces themselves; gives a business card.
5. Needs analysis.
6. Product presentation and walk-around.
7. Test drive offer.
8. Quotation.
9. Close attempt: booking today, or next appointment fixed.
10. Exit: thank-you message with quotation and brochure; follow-up date set.

### 5.3 Needs analysis checklist

- Who will drive; who decides (often family decision).
- Family size; seating need.
- Daily and monthly running; city or highway; parking space.
- Fuel preference and running cost; home charging possible (for EV).
- Manual or automatic.
- Must-have features (sunroof, safety, screen, cruise control, ADAS).
- Budget for on-road price and EMI.
- Current car: brand, model, year, km, loan status (for exchange).
- Purchase timeline and occasion (festival, birthday, new job).
- Cash or loan; income type (salaried, self-employed, business).
- Competitor models being considered.

### 5.4 Product presentation (walk-around)

Six-point walk-around used by many OEMs: front (design, lights, safety rating), driver side (doors, tyres, alloys), rear seat (space, comfort), rear (boot space, camera), passenger side, engine bay, then driver seat (dashboard, infotainment, connected car, controls). Support material: brochure, variant comparison sheet, competitor comparison, running cost sheet, accessory catalogue.

### 5.5 Test drive

- **Demo fleet:** each model and fuel type, registered and insured in the dealer's name; demo car register with km, fuel, condition, service.
- **Scheduling:** slot booking (showroom or home), route set in advance.
- **Before:** driving licence check and copy, test-drive form and indemnity signed, car checked out (km, fuel, damage).
- **During:** consultant rides along; explains features; safety rules.
- **After:** car checked in (km, fuel, damage); feedback recorded; next step (quotation or booking).
- **Controls:** no test drive without licence; gate log; demo car utilisation tracked; demo cars sold off after a set age or km.

### 5.6 On-road price and quotation

Typical lines (actual structure differs by OEM and state):

| Line | Notes |
|---|---|
| Ex-showroom price | From OEM price list, per model, variant, fuel, transmission, colour (some colours cost extra), effective date. Includes GST. Since 22 September 2025: small cars (petrol/CNG/LPG up to 1200 cc, diesel up to 1500 cc, and up to 4 m long) at 18%, other cars and SUVs at 40%, electric cars at 5%, no compensation cess **(verify current notification)** |
| TCS | 1% of the sale value where the car's value is above ₹10 lakh; moved from Section 206C(1F) of the 1961 Act to the Income-tax Act, 2025 from 1 April 2026 **(verify)**. Buyer can claim credit against income tax. |
| Road tax | State-set, often a percentage of price by price slab and fuel type; EVs exempt or reduced in many states **(verify per state)** |
| Registration fee, smart-card RC fee, HSRP charge | State-set |
| Insurance | First-year own damage plus 3-year third party for new private cars; add-ons listed separately |
| FASTag | Issue fee and minimum balance |
| Extended warranty | Optional, by plan and years |
| Roadside assistance / service package | Optional |
| Accessories | Pack or itemised |
| Coating / protection | Optional |
| **Less:** consumer offer, exchange bonus, scrappage bonus, corporate offer, loyalty bonus, rural offer, dealer discount | Each offer shown separately with who funds it |
| **On-road price** | Sum of the above |
| **EMI options** | Loan amount, tenure, rate, EMI, down payment |

Controls: quotation numbered and versioned; price list and scheme versions captured on the quotation; validity date; discount above role limit needs approval before the quotation is shared.

### 5.7 Offers and schemes

- OEM issues circulars monthly, sometimes mid-month changes.
- Each scheme has: name, valid from/to, models/variants/fuels, customer type, amount, funding (OEM / dealer / shared, with split), conditions, proofs needed, claim deadline, and whether it can combine with other offers.
- Types: consumer cash offer, exchange bonus, scrappage bonus, corporate offer, loyalty bonus (existing owner of the brand), rural offer, first-time buyer offer, finance offer (low rate, subvention), festive offer, year-end stock offer, free accessories, free extended warranty, additional dealer discount.
- At deal stage: eligible offers checked and applied, proofs collected.
- After retail: claim to OEM with proofs; tracked as claimed, settled, short-paid, rejected.

### 5.8 Negotiation and discount approval

- Each role has a discount limit (amount or percentage, per model).
- Discount includes cash discount and free items (accessories, insurance, extended warranty) valued at cost.
- Request shows: customer, model, quotation, competitor quote if any, requested amount, reason.
- Approver sees margin impact (vehicle margin, scheme income, F&I and accessories income).
- Approval logged with time and approver; the booking cannot exceed approved discount.
- Typical ladder: Consultant → TL → Sales Manager → Sales Head / GM → Owner.

### 5.9 Exchange (old car purchase)

1. Customer declares an old car.
2. Evaluation: physical inspection (exterior, interior, engine, underbody, tyres, accident signs, odometer), test drive, photos.
3. Document check: RC (name match, hypothecation), insurance (claim history), PUC, loan status, traffic challans, number of owners, service history.
4. Price: market reference (online valuation tools, recent trades), refurbishment estimate, margin.
5. Offer and negotiation; final price agreed.
6. Old-car handover: Form 29 (notice of transfer) and Form 30 (application for transfer) signed by the seller, RC original, keys (all), service book, insurance copy, loan closure NOC and Form 35 if it was financed, seller's KYC, delivery note, indemnity for any past liabilities.
7. Value adjusted against the new car, or paid to the seller by bank transfer.
8. OEM exchange bonus claimed (proof: old RC in customer's name for the required period **(verify OEM rule)**).
9. Ownership transferred to the dealer or the next buyer within the legal period.
10. Old car retailed, wholesaled, auctioned or scrapped. Scrapping at a Registered Vehicle Scrapping Facility gives a Certificate of Deposit that can earn a road-tax concession on the new car **(verify by state)**.

### 5.10 Finance (car loan)

1. Eligibility check: CIBIL score, income, existing EMIs, age, job or business stability.
2. Documents: KYC (Aadhaar, PAN), photos, address proof, income proof (salary slips, Form 16, ITR, bank statements; for business owners, business proof and GST returns), quotation or proforma invoice.
3. File logged with 2–3 lenders; lender's field verification of residence and office.
4. Sanction: amount, rate, tenure, EMI, processing fee, conditions.
5. Down payment collected by the dealer.
6. Loan agreement, e-mandate (NACH) for EMIs.
7. Delivery order (DO) from the lender to the dealer.
8. Invoice and insurance with hypothecation to the lender.
9. Disbursement to the dealer after invoice, insurance and (sometimes) RC copies are sent.
10. RC with hypothecation entry; copy to lender.
11. Dealer payout claimed from the lender and reconciled.
12. Own-bank loans (customer arranges): dealer still needs the DO and hypothecation details.

### 5.11 Insurance

1. Quote: insurer comparison, IDV (insured declared value), add-ons (zero depreciation, engine protection, return to invoice, roadside assistance, consumables, key replacement, tyre protection), owner-driver personal accident cover.
2. No-claim bonus transfer from the old car if the customer has a certificate.
3. Customer choice recorded (dealer policy or own policy; customers are free to buy elsewhere).
4. Policy issued with chassis and engine numbers and lender's name.
5. Policy copy goes into the Vahan file.
6. Insurer commission statement reconciled policy by policy.
7. Renewal date stored for next year's renewal.

### 5.12 Booking

- **Booking form fields:** customer details exactly as KYC, co-owner if any, address for registration, model, variant, fuel, transmission, colour (first and second choice), accessories, extended warranty, insurance choice, finance choice, exchange details, offers applied, discount approved, booking amount, expected delivery, price clause, cancellation and refund terms, consultant, signatures.
- **Receipt** for the booking amount.
- **OEM DMS booking entry** (affects allocation priority).
- **Booking changes:** variant change, colour change, fuel change, name change (before invoice only), transfer of booking to another person (OEM rule), booking moved to another branch. Each change logged with approval; price and offers re-checked.

### 5.13 Allocation and waiting

- **Booking queue:** ordered by booking date and payment status. Many dealers allot only after full payment or lender DO, especially for high-demand models.
- **Matching:** model, variant, fuel, transmission, colour; oldest stock first to cut interest cost.
- **Allocation:** chassis locked to the booking; no double allocation.
- **Not in stock:** order from OEM; track OEM allocation, wholesale invoice, dispatch, transit, arrival.
- **Customer updates:** waiting time, chassis allotted, arrival date, delivery date.
- **Re-allocation:** only with approval and a log (for example, to give a car to a customer who paid in full first).

### 5.14 Payments and receipts

- **Types:** booking amount, part payments, balance, loan disbursement, exchange adjustment, refunds.
- **Modes:** bank transfer (NEFT/RTGS/IMPS), UPI, card, cheque, demand draft, cash within legal limits.
- **Receipt fields:** date, amount, mode, reference (UTR, cheque number), bank, received by, booking linked.
- **Controls:** receipts only from the system; cash cannot exceed ₹2 lakh from one person for one transaction (Section 269ST of the 1961 Act; check the matching section of the 2025 Act) **(verify)**; cheques marked realised only after clearing; refunds only by bank transfer with approval.
- **Payment status per booking:** due, received, pending loan, short, cleared.

### 5.15 KYC and tax checks

- PAN (or Form 60) required for buying a motor vehicle other than a two-wheeler (Rule 114B) **(verify current rule under the 2025 Act)**.
- Name and address match across KYC, invoice, insurance, loan and Form 20.
- GSTIN for business buyers who want input credit (generally restricted for cars; check with tax advisor).
- TCS collected where applicable and shown on invoice.

### 5.16 Invoice

- **Pre-checks:** payment cleared or DO received, chassis allocated, KYC complete, insurance ready, offers and discount approved, verification call done.
- **Contents:** customer name and address, GSTIN if any, model, variant, colour, chassis and engine numbers, HSN, taxable value, GST, TCS, hypothecation, offers.
- **E-invoice** (IRN) if the dealer's turnover requires it.
- **OEM DMS retail entry** with customer details (warranty start, scheme claims, OEM survey).
- **Invoice cancellation:** credit note, approval, OEM rebilling; high-control event.

### 5.17 Registration

1. **Documents:** Form 20 (application), Form 21 (sale certificate, from dealer), Form 22 (roadworthiness, from manufacturer), invoice, insurance, address proof, PAN or Form 60, Form 34 if on loan, photos.
2. **Vahan entry** (dealer-point registration in most states); road tax and fees paid online.
3. **Number choice:** normal series, fancy or choice number (by auction or fee), or BH (Bharat) series for eligible transferable employees **(verify eligibility and tax rules)**.
4. **Temporary registration** if the permanent number is not issued before delivery, or if the car will be registered in another state **(verify)**.
5. **HSRP:** mandatory for new cars since April 2019; supplied through the dealer and fitted before delivery.
6. **RC:** smart card dispatched by post or collected; digital RC on DigiLocker and mParivahan.
7. **Tracking:** applied date, number allotted date, HSRP fitted date, RC received date, RC handed to customer date.

### 5.18 FASTag

- Mandatory for new four-wheelers; issued at delivery through a bank or the dealer.
- Linked to registration number and chassis; customer's KYC.

### 5.19 Accessories and protection products

1. Pitch at quotation; packs by variant.
2. Order recorded on the booking (free or paid).
3. Fitment job sent to the fitment team once the chassis is allocated.
4. Quality check at PDI.
5. Billing (separate invoice or on the vehicle invoice, by OEM practice).
6. Free accessories counted as discount at cost in the approval.

### 5.20 PDI (pre-delivery inspection)

- Chassis and engine numbers match the invoice and Form 22.
- Exterior: paint, panel gaps, dents, scratches, glass, lights, tyres (brand, date, pressure), spare wheel.
- Interior: seats, upholstery, dashboard, switches, infotainment, AC, power windows, mirrors, seat belts, airbags light.
- Mechanical and electrical: brakes, steering, battery, fluid levels, warning lights.
- Software and connected-car activation.
- Accessories and coating checked.
- Toolkit, jack, first-aid kit, manuals, all keys.
- Number plates fitted; FASTag stuck.
- Washed; photos taken.
- Signed by PDI technician and delivery coordinator; customer copy.

### 5.21 Delivery

1. **Scheduling:** date and time (auspicious dates and festivals cause peaks; plan bay capacity).
2. **Pre-checks (delivery gate):** payment cleared, invoice, insurance, registration done or temporary registration, HSRP, FASTag, PDI passed, accessories fitted.
3. **Delivery bay:** car covered or decorated.
4. **Handover kit:** invoice, insurance, RC or registration slip, Form 21/22 copies, warranty booklet, owner's manual, extended warranty certificate, roadside assistance card, accessories invoice, loan papers, keys (counted).
5. **Orientation:** controls, safety, infotainment and app, fuel type, warranty, first-service schedule, emergency number.
6. **Service handover:** service contact introduced and first-service reminder set (service itself is out of scope here).
7. **Ceremony:** key handover, photo, cake or gift, social media post with consent.
8. **Delivery note signed by customer;** gate pass issued; security logs the car out.
9. **CRM updated:** delivered, delivery date, photos.

### 5.22 After-delivery follow-up

- Same day: thank-you message with photo.
- Day 1–2: call to check satisfaction and any questions.
- Day 7: call; OEM survey reminder.
- Day 30: call; referral request.
- Google review request.
- RC handover if pending; loan file closed with lender.
- Customer added to birthday and anniversary messages, and to the referral and loyalty programme.

### 5.23 Cancellation and refund

1. Customer request in writing with reason.
2. Retention attempt (another variant, earlier delivery, better offer) recorded.
3. Approval by manager; deductions only as stated in booking terms.
4. Refund to the original payment source by bank transfer, with approval by Accounts.
5. Chassis released; OEM booking cancelled; invoice reversed by credit note if already invoiced; insurance cancelled; Vahan application withdrawn if started; loan cancelled with lender.
6. Consultant's incentive reversed if already counted.
7. Monthly cancellation report by reason and consultant.

### 5.24 Complaints (sales-related)

- Channels: phone, WhatsApp, email, OEM call centre, social media, walk-in.
- Categories: promise not kept (discount, accessories, date), delivery delay, documents and RC delay, billing error, refund delay, staff behaviour, car condition at delivery.
- Ticket: category, priority, owner, deadline, root cause, closure with customer confirmation; OEM escalation if unresolved.

### 5.25 Referral and loyalty

- Referral captured with the referring customer linked; reward on retail.
- Loyalty bonus for existing customers of the brand (OEM proof rules).
- Customer events and offers.

---

## 6. Special sales channels

### 6.1 Corporate sales

- Company tie-up with agreed offer; employee proof (ID card, salary slip).
- Sometimes salary-deduction or company-paid schemes.
- Separate corporate scheme claim to OEM.

### 6.2 Fleet and taxi

- Buyers: taxi operators, travel agencies, ride-hailing drivers, staff transport firms.
- Taxi variants (some OEMs sell separate taxi versions).
- **Commercial registration:** yellow number plate (black on yellow; EVs yellow text on green), permit (state, all-India tourist), fitness certificate, commercial insurance **(verify state rules)**.
- Bulk pricing and OEM fleet support; staggered deliveries.

### 6.3 Leasing and subscription

- Car bought by a leasing company for a corporate employee; invoice to the lessor; registration in the lessor's name.

### 6.4 CSD and CPC (defence and police canteens)

- Eligible defence or central police personnel apply through the canteen system; the canteen issues a supply order.
- Dealer delivers against the supply order at canteen price; payment comes from the canteen.
- Specific documents, eligibility checks and claim process **(verify current CSD/CPC rules and OEM process)**.

### 6.5 Government orders

- Tenders and GeM portal orders; government invoicing and payment timelines.

### 6.6 Online booking

- Customer books on the OEM or dealer website and pays the booking amount online.
- Dealer receives the booking in DMS, calls the customer, arranges test drive and closes the deal.
- Refund rules for online bookings follow OEM terms.

### 6.7 Rural sales

- Field executives, outlets, rural events.
- Rural offers with eligibility proof.
- Wider loan options (rural banks, NBFCs).

### 6.8 Home delivery and doorstep sales

- Home test drive, doorstep document collection, home delivery with the same checklist as showroom delivery.

---

## 7. Stock and OEM side of sales

### 7.1 Monthly planning with the OEM

- Retail and wholesale targets by model.
- Stock order by model, variant, fuel, colour, based on bookings, lead pipeline and ageing.
- OEM allocation can be lower than the order for high-demand models.

### 7.2 Wholesale and transit

- OEM bills each car to the dealer (wholesale invoice); payment through the inventory-funding bank or advance.
- Transporter delivers with e-way bill; transit insurance.
- Arrival check: chassis and engine numbers, transit damage (photos, damage claim to transporter or OEM), keys, toolkit, manuals.

### 7.3 Inventory funding (floor plan)

- A bank pays the OEM for each car; the dealer pays interest daily until the car is sold and the bank is repaid.
- The bank audits physical stock; selling a car without repaying the bank ("sold out of trust") is a serious breach.
- Ageing stock costs money, so oldest-first allocation and ageing reports matter.

### 7.4 Yard management

- Location of each car in the yard; battery maintenance; periodic start-up; cleaning; cover.
- Gate register for every movement (to PDI, to delivery bay, test drive, branch transfer).
- Physical stock count matched to the stock list.

### 7.5 Stock ageing and push

- Ageing buckets: 0–30, 31–60, 61–90, 90+ days.
- Older stock gets extra offers or OEM support; year-end stock (previous model year) needs clear disclosure to the customer.

### 7.6 Branch and dealer transfers

- Transfer between own branches (stock transfer note, e-way bill).
- Swap with another dealer of the same brand for a colour or variant (OEM-approved).

### 7.7 Demo cars

- Register of demo cars: model, registration, insurance, km, condition.
- Sold off after a set age or km, usually at a discount.

### 7.8 OEM reporting

- Daily enquiry, booking, retail and stock figures to OEM DMS.
- Retail entry with customer details for each invoice.
- Sales satisfaction survey (SSI) results from OEM.
- OEM process audits and mystery shopping.

---

## 8. Accounts work that touches a sale

| Area | What Accounts does |
|---|---|
| Receipts | Records every payment against the booking; daily cash and bank reconciliation |
| Refunds | Bank transfer only, with approval |
| Invoice | Raises the tax invoice, collects TCS, issues e-invoice; credit note for cancellations |
| Customer balance | Due, received, short, cleared; releases the car for delivery |
| Loan disbursements | Matches lender disbursements to invoices; follows pending disbursements |
| Lender payouts | Claims dealer commission per loan; reconciles |
| Insurance payouts | Reconciles insurer commission statements policy by policy |
| OEM scheme claims | Files claims with proofs; tracks claimed, settled, short-paid, rejected; books credit notes |
| OEM account | Reconciles wholesale invoices, payments, credit notes |
| Exchange | Pays old-car sellers; loan closure for old car; records used-car stock |
| Tax | GST returns, TCS returns and certificates, TDS, e-invoice and e-way bill |
| Books | Tally entries, month-end closing |
| Profit per car | Vehicle margin + scheme income + finance + insurance + accessories + extended warranty + exchange margin − discount − free items |
| Incentives | Calculates consultant incentive from retails, penetration, discount discipline, cancellations; HR and Sales Head approve |

---

## 9. Interlinks: who hands what to whom

### 9.1 Hand-off flow

```
Marketing ──leads──► Lead centre/BDC ──appointment──► Consultant
Reception ──walk-in──► Consultant
Consultant ──test drive request──► Demo car register / Security
Consultant ──quotation──► TL/Manager (discount approval)
Consultant ──old car──► Exchange evaluator ──agreed value──► Consultant, Accounts
Consultant ──loan need──► Finance executive ──DO──► Accounts
Consultant ──insurance need──► Insurance executive ──policy──► Accounts, Registration
Consultant ──booking──► Sales admin (DMS, allocation) ──chassis──► Stock yard
Consultant ──accessories order──► Accessories ──fitment──► PDI
Customer relations ──verification result──► Sales admin, Manager
Accounts ──payment cleared──► Sales admin (invoice) ──invoice──► Registration
Registration ──number, HSRP, RC──► Delivery team
Stock yard ──car──► PDI ──passed──► Delivery team
Delivery team ──delivered──► Customer relations (feedback) ──referrals──► Lead centre
Sales admin ──retail entry──► OEM ──scheme credit──► Accounts
Accounts ──retails, penetration, cancellations──► HR (incentives)
Lost leads ──► Lead centre (recycle) and Manager (lost analysis)
```

### 9.2 Department interlink matrix

● = daily dependency, ○ = periodic.

| From \ To | Lead centre | Consultant | Manager | Exchange | F&I | Accessories | Sales admin | Stock | Accounts | Registration | PDI/Delivery | Cust. relations | OEM |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **Marketing** | ● | ○ | ○ | | | | | | ○ | | | | ○ |
| **Lead centre** | – | ● | ○ | | | | | | | | | | |
| **Consultant** | ○ | – | ● | ● | ● | ● | ● | ○ | ● | ○ | ● | ● | |
| **Manager** | ○ | ● | – | ○ | ○ | | ● | ● | ● | | ○ | ○ | ● |
| **Exchange** | | ● | ○ | – | ○ | | | | ● | | | | ○ |
| **F&I** | | ● | ○ | | – | | ○ | | ● | ● | ○ | | |
| **Accessories** | | ● | | | | – | | | ● | | ● | | ○ |
| **Sales admin** | | ● | ● | | ○ | ● | – | ● | ● | ● | ● | ● | ● |
| **Stock** | | ○ | ● | | | | ● | – | ● | | ● | | ● |
| **Accounts** | | ● | ● | ● | ● | ● | ● | ● | – | ● | ● | | ● |
| **Registration** | | ● | | | ○ | | ○ | | ● | – | ● | ○ | |
| **PDI/Delivery** | | ● | ○ | | | ● | ● | ● | ○ | ○ | – | ● | |
| **Cust. relations** | ● | ● | ● | | | | | | | | ○ | – | ○ |
| **OEM** | ○ | | ● | ○ | ○ | ○ | ● | ● | ● | | | ○ | – |

### 9.3 Shared records

| Record | Created by | Used by |
|---|---|---|
| Customer | Lead centre, Reception, Consultant | Everyone |
| Lead | Lead centre, Consultant | Manager, Marketing |
| Activity / follow-up | Consultant, Lead centre | TL, Manager |
| Walk-in | Reception | Consultant, Manager |
| Test drive | Consultant | Security, Manager |
| Demo car | Stock / Admin | Consultant, Security |
| Quotation | Consultant | Manager, Accounts |
| Discount approval | Consultant (request), Manager (decision) | Accounts, Owner |
| Exchange evaluation | Evaluator | Consultant, Accounts, OEM claim |
| Loan file | Finance executive | Accounts, Registration |
| Insurance policy | Insurance executive | Registration, Accounts |
| Booking | Consultant, Sales admin | Everyone downstream |
| Booking change | Consultant | Manager, Sales admin |
| Verification call | Customer relations | Manager, Sales admin |
| Vehicle (chassis) | Stock (from OEM invoice) | Allocation, Invoice, Insurance, Registration, PDI, Delivery |
| Allocation | Sales admin | Stock, Consultant, Accounts |
| Payment / receipt | Accounts | Consultant, Delivery |
| Invoice | Accounts | Registration, Lender, Insurer, OEM |
| Scheme / offer | Accounts or Sales admin (from OEM circular) | Consultant, Manager, Accounts |
| Scheme claim | Accounts | Owner |
| Registration | Registration executive | Delivery, Customer, Lender |
| Accessory order | Consultant | Accessories, PDI, Accounts |
| PDI | PDI team | Delivery |
| Delivery | Delivery team | Consultant, Customer relations, Accounts |
| Feedback | Customer relations | Manager |
| Complaint | Customer relations | Concerned department |
| Cancellation | Consultant | Manager, Accounts, Stock, OEM |
| Referral | Customer relations, Consultant | Lead centre |
| Incentive | HR, Accounts | Consultant, Owner |

---

## 10. Record lifecycles and statuses

### 10.1 Lead

`New → Contacted → Qualified → Visited → Test drive done → Quoted → Negotiation → Booked`
Exits: `Lost` (with reason), `Dropped`, `Not interested`, `Duplicate`, `Invalid number`.
Temperature: `Hot / Warm / Cold`.

### 10.2 Booking

`Booked → Verified → Approved → Allocated → Payment complete → Invoiced → Registered → PDI done → Ready for delivery → Delivered`
Side states: `Change requested`, `On hold`, `Cancellation requested → Cancelled → Refunded`.

### 10.3 Vehicle (chassis)

`Ordered → OEM invoiced (wholesale) → In transit → Received → In stock → Allocated → Invoiced (retail) → In PDI → Delivered`
Side states: `Transit damage`, `Demo`, `Transferred`, `Blocked`.

### 10.4 Payment

`Pending → Received → Realised` (cheque) · `Bounced` · `Refund requested → Refunded`.

### 10.5 Loan

`Not needed / Enquired → Documents collected → Logged → Field verification → Sanctioned / Rejected → DO received → Disbursed → Payout claimed → Payout received`.

### 10.6 Insurance

`Quoted → Customer choice (dealer / own) → Issued → Commission reconciled`.

### 10.7 Exchange

`Declared → Evaluated → Offer made → Agreed / Rejected → Old car received → Documents received → Paid / Adjusted → Ownership transferred → Resold / Scrapped`.

### 10.8 Registration

`Documents pending → Applied on Vahan → Tax paid → Number allotted → HSRP fitted → RC received → RC handed over`.

### 10.9 Scheme claim

`Eligible → Proofs collected → Claimed → Settled / Short-paid / Rejected → Recovery or write-off`.

### 10.10 Discount approval

`Requested → Approved / Rejected / Counter-offered`, with approver and time.

---

## 11. Approvals and controls

### 11.1 Approval matrix (typical)

| Action | Who approves |
|---|---|
| Discount within consultant limit | None |
| Discount above consultant limit | TL → Sales Manager → GM / Owner by amount |
| Free accessories / insurance / extended warranty | Same ladder, valued at cost |
| Exchange price above evaluator limit | Exchange Manager |
| Booking change (variant, colour) | Sales Manager (price and offers re-checked) |
| Name change / booking transfer | Sales Manager, per OEM rule |
| Re-allocation of a chassis | Sales Manager |
| Delivery with balance pending | GM / Owner only |
| Cancellation and refund | Sales Manager + Accounts |
| Invoice cancellation / rebilling | GM + Accounts |
| Deal sheet after verification | Sales Manager |
| Edit after approval | Re-approval |

### 11.2 Leakage and fraud points

| Risk | Control |
|---|---|
| Discount beyond authority | Role limits, approval workflow, margin shown to approver |
| Side deals or cash not recorded | System receipts only, verification call, payment check before delivery |
| Promises not on record (free accessories, date) | Everything on the booking form; verification call |
| Double allocation of a chassis | Chassis lock and audit log |
| Delivery before payment | Delivery gate blocks until balance is zero or approved |
| Fake scheme claims | Proofs mandatory, customer verification, OEM audit |
| Exchange bonus without a real exchange | Old RC and transfer proof |
| Lead stealing between consultants | Duplicate check by mobile, ownership rules, audit log |
| Test-drive misuse | Licence check, gate log, km log |
| Lender or insurer payout not received | Reconciliation by lender and insurer |
| Stock sold without repaying the funding bank | Stock audit, sale-to-repayment link |
| Invoice manipulation | Credit-note approvals, rebilling log |
| Customer data misuse (Aadhaar, PAN, phone) | Role-based access, masking, consent and retention rules under the Digital Personal Data Protection Act, 2023 |
| Cash above legal limit | System block |
| Edits after approval | Edit lock, edit log, re-approval |

---

## 12. Documents register

### 12.1 From the customer

| Document | Use |
|---|---|
| Aadhaar / passport / voter ID | KYC, address |
| PAN or Form 60 | Required for car purchase; TCS |
| Address proof (if different) | Registration jurisdiction |
| Photographs | Loan, registration |
| Driving licence | Test drive |
| Income proof, bank statements, ITR | Loan |
| GSTIN | Business buyer invoice |
| Old car RC, insurance, PUC, loan NOC, Form 35, service book | Exchange |
| Corporate ID, salary slip | Corporate offer |
| Previous-car RC of the same brand | Loyalty offer |
| Scrapping Certificate of Deposit | Scrappage offer, road-tax concession |
| CSD/CPC supply order | Canteen sale |
| Signed Form 20, Form 34, Form 29/30 (exchange) | Registration, transfer |

### 12.2 Issued by the dealer

| Document | Stage |
|---|---|
| Brochure, price list, variant comparison | Enquiry |
| Test-drive form / indemnity | Test drive |
| Quotation / proforma invoice | Negotiation, loan |
| Exchange evaluation sheet, old-car purchase agreement, delivery note | Exchange |
| Booking form and receipt | Booking |
| Payment receipts | Every payment |
| Deal sheet (internal) | Approval |
| Tax invoice, e-invoice | Invoice |
| Form 21 | Registration |
| Form 22 (from manufacturer) | Registration |
| Insurance policy | Before registration |
| Temporary registration (if any) | Delivery |
| PDI checklist | Before delivery |
| Accessories invoice | Delivery |
| Extended warranty certificate, roadside assistance card | Delivery |
| Delivery note, gate pass | Delivery |
| TCS certificate | After quarter end |
| Credit note, refund voucher | Cancellation |

### 12.3 Dealer's own licences

- OEM dealer agreement.
- Trade certificate (Form 16 application, Form 17 certificate under the Central Motor Vehicles Rules) for holding and moving unregistered cars.
- GST registration; shop and establishment licence.
- Insurance distribution licence or tie-up (IRDAI corporate agent or broker arrangement).
- Lender DSA agreements.

---

## 13. KPIs and reports

### 13.1 KPIs

| KPI | Formula |
|---|---|
| Speed to lead | Lead created → first contact |
| Contact rate | Leads contacted ÷ leads received |
| Walk-in to test drive | Test drives ÷ walk-ins |
| Enquiry to test drive | Test drives ÷ enquiries |
| Test drive to booking | Bookings ÷ test drives |
| Enquiry to booking | Bookings ÷ enquiries |
| Booking to retail | Retails ÷ bookings (same cohort) |
| Cancellation rate | Cancellations ÷ bookings |
| Lost to competition | Lost with competitor reason ÷ all lost |
| Follow-up adherence | Follow-ups done on time ÷ due |
| Average discount per car | Total discount (incl. free items at cost) ÷ retails |
| Gross per car | (Margin + scheme income + F&I + accessories + extended warranty + exchange margin − discount) ÷ retails |
| Finance penetration | Dealer loans ÷ retails |
| Insurance penetration | Dealer policies ÷ retails |
| Accessories per car | Accessories revenue ÷ retails |
| Extended warranty penetration | Plans sold ÷ retails |
| Exchange penetration | Exchanges ÷ retails |
| Booking-to-delivery days | Average days |
| On-time delivery | Delivered by promised date ÷ deliveries |
| Registration turnaround | Invoice → number allotted; invoice → RC handed over |
| Stock days | Stock ÷ average daily retail |
| Stock ageing 90+ | Count and value |
| Demo car utilisation | Test drives per demo car per day |
| Scheme claim settlement | Settled ÷ claimed (amount) |
| Claim ageing | Days from claim to settlement |
| SSI / delivery NPS | OEM survey score |
| Google rating | Average and review count |
| Referral share | Retails from referrals ÷ retails |
| Cost per lead / per sale | Marketing spend ÷ leads or retails, by source |

### 13.2 Reports

- **Daily:** enquiries by source, walk-ins, test drives, bookings, retails, deliveries, cancellations, collections, stock position, overdue follow-ups.
- **Consultant:** funnel, follow-ups, discount, penetration, cancellations.
- **Monthly:** target vs achievement by model and consultant, funnel conversion, source effectiveness, lost analysis, penetration, scheme claims, stock ageing, gross per car, incentives.
- **Owner:** total gross by line, receivables (customer, lender, insurer, OEM), stock value and funding interest, discount trend.

---

## 14. What the CRM has to cover

Derived from the processes above. This is the module list for a sales-only four-wheeler CRM.

| # | Module | Covers |
|---|---|---|
| 1 | Masters | Models, variants, fuels, transmissions, colours, price list with effective dates, tax rules (GST, TCS, road tax by state), insurance add-ons, accessories, extended warranty plans, lenders, insurers, branches, sources, lost reasons |
| 2 | Users and roles | Consultant, TL, Sales Manager, Sales Head, GM, Owner, Lead centre, Reception, Exchange, Finance, Insurance, Accessories, Sales admin, Registration, Delivery, Customer relations, Accounts, Stock; discount limits per role |
| 3 | Leads | Capture from all sources, duplicate check, assignment, temperature, pipeline, follow-ups, activity log, lost reasons, recycling |
| 4 | Walk-in register | Reception entry linked to leads |
| 5 | Test drives and demo cars | Booking slots, licence capture, out/in log, feedback, demo car register |
| 6 | Quotations | On-road price builder, offers, EMI, versions, sharing by WhatsApp/PDF |
| 7 | Offers and schemes | Scheme master with funding split, eligibility, proofs, combinability |
| 8 | Discount approvals | Request, ladder, margin view, decision log |
| 9 | Exchange | Evaluation, offer, documents, payment, ownership transfer, resale/scrap, OEM bonus proof |
| 10 | Finance | Loan files, lender logins, sanction, DO, disbursement, payout |
| 11 | Insurance | Quotes, policies, add-ons, commission reconciliation, renewal date |
| 12 | Bookings | Booking form, receipt, changes, transfer, verification call, approval |
| 13 | Stock and allocation | OEM orders, transit, receipt, yard, ageing, allocation queue, chassis lock, transfers |
| 14 | Payments | Receipts, modes, realisation, balance per booking, refunds, cash limit check |
| 15 | Invoice | Pre-check gate, invoice data, TCS, credit notes, OEM retail entry |
| 16 | Registration and FASTag | Vahan steps, number choice, HSRP, RC tracking, FASTag |
| 17 | Accessories | Orders, fitment, billing |
| 18 | PDI | Checklist, photos, sign-off |
| 19 | Delivery | Scheduling, delivery gate, handover checklist, gate pass, photos |
| 20 | Customer relations | Verification calls, feedback calls, reviews, complaints, referrals, loyalty |
| 21 | Cancellations | Request, retention attempt, approval, refund, reversals |
| 22 | OEM scheme claims | Claim list, proofs, settlement tracking, short-paid and rejected |
| 23 | Incentives | Rules, calculation, approval |
| 24 | Communication | WhatsApp, SMS, email, calls, templates, reminders |
| 25 | Dashboards and reports | Role dashboards and the reports in §13 |
| 26 | Audit and security | Edit log, approval log, data masking, consent, backups |

---

## 15. Glossary

| Term | Meaning |
|---|---|
| BDC | Business development centre (lead-calling team) |
| BH series | Bharat series registration for eligible transferable employees |
| CSD / CPC | Canteen Stores Department (defence) / central police canteen |
| DMS | Dealer management system, usually supplied by the OEM |
| DO | Delivery order issued by the lender to the dealer |
| DSE | Dealer sales executive (sales consultant) |
| Ex-showroom | Price of the car including GST, before registration, insurance and extras |
| FASTag | Electronic toll tag |
| GSM | General sales manager |
| HSRP | High-security registration plate |
| IDV | Insured declared value |
| NCB | No-claim bonus |
| OEM | Manufacturer |
| On-road price | Total the customer pays to drive the car away |
| PDI | Pre-delivery inspection |
| RC | Registration certificate |
| Retail | Sale from dealer to customer |
| SSI | Sales satisfaction index (OEM survey) |
| TCS | Tax collected at source |
| Vahan | National vehicle registration system |
| Wholesale | Sale from OEM to dealer |

---

## 16. Sources

- [AutoAlert: The dealership org chart](https://www.autoalert.com/dealership-org-chart/)
- [Edmunds: Roles of the car dealership sales department staff](https://www.edmunds.com/car-buying/roles-of-the-car-dealership-sales-department-staff.html)
- [NADA dealership organisation chart (PDF)](https://nada.org/media/3247/download)
- [CBT News: Improving BDC processes](https://www.cbtnews.com/how-dealers-can-improve-their-bdc-processes/)
- [AutoNation FY2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/350698/000162828026007800/an-20251231.htm)
- [91Wheels: Pre-delivery inspection guide](https://www.91wheels.com/buyers-guide/the-ultimate-pre-delivery-inspection-guide-for-new-cars)
- [Motomotar: Car registration process in India 2026](https://motomotar.com/car-buying-guide/car-registration-process-india/)
- [Tamil Nadu STA: Form 20](https://tnsta.gov.in/about_us/form20.pdf)
- [Policybazaar: Form 17 trade certificate](https://www.policybazaar.com/rto/form-17/)
- [Outlook Business: new GST rates for car buyers](https://www.outlookbusiness.com/news/what-the-new-gst-rates-mean-for-buyers-entry-level-car-suv-prices-likely-to-go-down-due-to-lower-taxes)
- [ThePrint: vehicles under the new GST slabs](https://theprint.in/opinion/dashboard/what-vehicles-become-cheaper-with-new-gst-slabs/2737714)
- [TDSMAN: TCS on sale of motor vehicles](https://blog.tdsman.com/2026/02/section-206c1f-tcs-on-sale-of-motor-vehicles-and-luxury-goods/)
- [Business Today: claiming TCS on a car above ₹10 lakh](https://www.businesstoday.in/personal-finance/tax/story/bought-a-car-above-rs-10-lakh-you-can-claim-tcs-refund-on-your-purchase-heres-how-531117-2026-05-12)
- [MoRTH advisory on BH series implementation (PDF)](https://morth.gov.in/sites/default/files/comprehensive_compendium_circular/44-Advisory%20to%20TC%20and%20Principal%20Secretaries%20dt.%2018.03.2024%20reg%20BH%20Series%20implementation.pdf)
- [Factly: BH series explainer](https://factly.in/explainer-all-you-need-to-know-about-the-new-bharat-or-bh-series-for-vehicle-registration)
- [GrowthJockey: Dealer KPIs OEMs track](https://www.growthjockey.com/blogs/dealer-kpis-oems-track)

Role duties, process steps and controls draw on general Indian dealership practice as well as the sources above. Points marked **(verify)** change by state, OEM or over time.
