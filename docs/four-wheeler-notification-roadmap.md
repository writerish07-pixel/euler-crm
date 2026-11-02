# Four-wheeler dealership: notification and interlink roadmap

Date: 2 November 2026.
Companion to [four-wheeler-dealership-sales-study.md](four-wheeler-dealership-sales-study.md).

Purpose: for every step from the customer's first enquiry to delivery and after, list:

- **what event happens** and who causes it
- **which departments are notified**
- **what each of them must do**
- **how fast** (suggested time limit)
- **who is told if it is not done** (escalation)
- **what the customer receives**

This is where departments connect. One step by one person sets off work in several other departments.

---

## Contents

1. [How to read this](#1-how-to-read-this)
2. [Departments and short codes](#2-departments-and-short-codes)
3. [The journey at a glance](#3-the-journey-at-a-glance)
4. [Event roadmap, stage by stage](#4-event-roadmap-stage-by-stage)
   - [A. Enquiry and lead](#a-enquiry-and-lead)
   - [B. Test drive, quotation, negotiation](#b-test-drive-quotation-negotiation)
   - [C. Booking](#c-booking)
   - [D. Finance, insurance, exchange, accessories during waiting](#d-finance-insurance-exchange-accessories-during-waiting)
   - [E. Stock and allocation](#e-stock-and-allocation)
   - [F. Payment and invoice](#f-payment-and-invoice)
   - [G. Registration and FASTag](#g-registration-and-fastag)
   - [H. PDI and delivery](#h-pdi-and-delivery)
   - [I. After delivery](#i-after-delivery)
   - [J. Cancellation and refund](#j-cancellation-and-refund)
   - [K. Complaints](#k-complaints)
   - [L. Master data and periodic events](#l-master-data-and-periodic-events)
5. [Gates: steps that cannot happen until others are done](#5-gates-steps-that-cannot-happen-until-others-are-done)
6. [Department inbox view](#6-department-inbox-view)
7. [Event × department matrix](#7-event--department-matrix)
8. [Customer messages](#8-customer-messages)
9. [Escalation ladder and time limits](#9-escalation-ladder-and-time-limits)
10. [Rules for building the notification engine](#10-rules-for-building-the-notification-engine)

---

## 1. How to read this

Each event has an ID (for example `C01`) so it can be used as a code in the CRM.

Every notification is one of three kinds:

| Kind | Meaning | In the CRM |
|---|---|---|
| **Action** | The department must do something. It becomes a task with a time limit and closes only when the work is recorded. | Task + alert |
| **Approval** | Someone must approve or reject. Work stops until they decide. | Approval request |
| **Info** | For awareness only. No task. | Feed / daily summary |

Time limits are **suggested starting values**. Each dealership should set its own in the CRM settings.

---

## 2. Departments and short codes

| Code | Department / role |
|---|---|
| **REC** | Reception / showroom host |
| **BDC** | Lead centre (tele-calling) |
| **SC** | Sales consultant (owner of the customer) |
| **TL** | Team leader |
| **SM** | Showroom sales manager |
| **SH** | Sales head / GM |
| **OWN** | Owner / dealer principal |
| **EXC** | Exchange / pre-owned team |
| **FIN** | Finance (loan) desk |
| **INS** | Insurance desk |
| **ACC-S** | Accessories team |
| **ADM** | Sales admin / sales coordinator (DMS, booking desk, allocation, invoice preparation) |
| **STK** | Stock yard / inventory |
| **ACC** | Accounts (cashier, receivables, claims) |
| **RTO** | Registration executive |
| **PDI** | PDI and fitment team |
| **DEL** | Delivery coordinator |
| **CR** | Customer relations (verification, feedback, complaints) |
| **MKT** | Marketing |
| **HR** | HR / incentives |
| **SEC** | Security / gate |
| **CUST** | The customer |

---

## 3. The journey at a glance

```
ENQUIRY ─► QUALIFY ─► TEST DRIVE ─► QUOTE ─► NEGOTIATE ─► BOOK ─► VERIFY ─► ALLOCATE ─► PAY ─► INVOICE ─► REGISTER ─► PDI ─► DELIVER ─► FOLLOW-UP
   │          │           │           │          │          │        │         │         │        │          │         │        │           │
  BDC        FIN?        STK          TL        TL/SM      ACC      CR        STK       ACC      RTO        PDI      DEL       CR          CR
  SC         EXC?        SEC          CUST      ACC(view)  ADM      SM        ADM       ADM      INS        DEL      ACC       MKT         BDC (referrals)
  TL         ADM(stock)  SC                                CR       ADM       SC        SC       FIN        STK      SEC       HR          ACC (claims)
                                                           ACC-S             INS       DEL      ADM        SC       CR        ACC
                                                           INS               FIN                ACC        CUST     HR
                                                           FIN?              ACC-S              HR                  FIN, INS
                                                           EXC?              RTO                CUST                MKT, ADM, STK
                                                           STK/ADM           PDI, DEL
                                                           MKT, HR
                                                           CUST
```

The busiest moments, where the most departments start work at once:

1. **Booking created (C01):** 10+ departments.
2. **Chassis allocated (E05):** 9 departments.
3. **Invoice raised (F07):** 9 departments.
4. **Car delivered (H09):** 12 departments.
5. **Booking cancelled (J02):** 10 departments reverse their work.

---

## 4. Event roadmap, stage by stage

Columns:
- **Event:** what happened.
- **Done by:** who caused it.
- **Notified → what they must do:** `[A]` action, `[P]` approval, `[I]` info.
- **Time limit:** how fast the action must be done.
- **If not done:** who is told next.

### A. Enquiry and lead

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| A01 | **Digital lead received** (website, portal, ad, WhatsApp, missed call, online booking) | System / BDC | • **BDC [A]** call the customer, qualify, book a visit or test drive<br>• **SC [I]** assigned owner sees the new lead<br>• **TL [I]** in team feed<br>• **MKT [I]** counted against source and campaign<br>• **CUST** welcome message with brochure and showroom location | BDC call: 5 min (working hours) | TL at 15 min, SM at 60 min |
| A02 | **Walk-in registered** | REC | • **SC [A]** attend the customer now<br>• If mobile matches an open lead: **owner SC [A]** comes to the floor, **TL [I]**<br>• **TL [I]** walk-in count<br>• **CUST** thank-you message after the visit | SC on floor: 2 min | TL at 5 min |
| A03 | **Duplicate lead detected** (same mobile already open) | System | • **Owner SC [A]** contact the customer again (new interest signal)<br>• **TL [I]** to settle ownership if another SC entered it<br>• **BDC [I]** do not call as new | 30 min | TL |
| A04 | **Lead assigned or reassigned** | TL / System | • **New SC [A]** call within time limit<br>• **Old SC [I]** lead removed<br>• **TL [I]** | 30 min | TL |
| A05 | **First contact time limit missed** | System | • **TL [A]** reassign or call personally<br>• **SM [I]** if still not contacted | — | SM, then SH in daily summary |
| A06 | **Lead qualified** (requirement captured) | SC | • **TL [I]** pipeline update<br>• **ADM [A]** stock check for the model/variant/colour; reply with available stock or waiting period<br>• **FIN [A]** if loan wanted: early eligibility check<br>• **EXC [A]** if old car declared: schedule evaluation | ADM: 2 hours<br>FIN: same day<br>EXC: 24 hours | TL |
| A07 | **Lead marked hot** | SC | • **TL [A]** join the deal; plan closing<br>• **SM [I]** hot-lead list | Same day | SM |
| A08 | **Follow-up due today** | System | • **SC [A]** make the follow-up and record the outcome | By end of day | — |
| A09 | **Follow-up overdue** | System | • **SC [A]** reminder<br>• **TL [A]** after 1 day: check with SC<br>• **SM [I]** after 3 days or if hot lead | — | TL → SM |
| A10 | **Lead marked lost / dropped** | SC | • **TL [A]** review reason; try to save hot or warm leads<br>• **SM [I]** if lost to competitor or price<br>• **BDC [A]** recycle call after a set period (for example 30 days)<br>• **MKT [I]** lost reason by source | TL review: 24 hours | SM |
| A11 | **Lead dormant** (no activity for X days) | System | • **SC [A]** contact or close<br>• **BDC [A]** if SC does not act, re-engage | 2 days | TL |

### B. Test drive, quotation, negotiation

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| B01 | **Test drive booked** (showroom or home) | SC / BDC | • **STK [A]** keep the demo car ready (clean, fuelled/charged) at the slot<br>• **SEC [I]** expected car movement<br>• **TL [I]** schedule<br>• For home test drive: **driver [A]** assigned<br>• **CUST** confirmation and reminder 2 hours before | Ready 30 min before slot | TL |
| B02 | **Demo car not available for slot** | STK | • **SC [A]** reschedule with customer<br>• **TL [A]** arrange another car<br>• **SM [I]** if repeated (demo fleet shortage) | 1 hour | SM |
| B03 | **Test drive started** (car out) | SC / SEC | • **SEC [A]** record out-time, km, fuel, licence checked<br>• **STK [I]** car out of yard | At gate | — |
| B04 | **Test drive completed** (car in) | SC / SEC | • **SEC [A]** record in-time, km, fuel, damage<br>• **SC [A]** record feedback; send quotation within 24 hours<br>• **TL [I]** test drive count<br>• **CUST** thank-you message, feedback link | Quote: 24 hours | TL |
| B05 | **Demo car damage or excess km found** | SEC / STK | • **SM [A]** investigate<br>• **STK [A]** repair; take car out of demo pool<br>• **ACC [I]** cost<br>• **INS [A]** claim if needed | Same day | SH |
| B06 | **Old car evaluated, offer made** | EXC | • **SC [I]** offer value for the quotation<br>• **EXC manager [P]** if offer is above evaluator's limit<br>• **CUST** offer details | Approval: 2 hours | SM |
| B07 | **Quotation shared with customer** | SC | • **TL [I]** quotation value and discount<br>• **CUST** quotation PDF/WhatsApp with validity date<br>• **SC [A]** follow-up set (24–48 hours) | — | — |
| B08 | **Discount requested above SC limit** | SC | • **TL [P]** approve, reject or counter (within TL limit)<br>• Above TL limit: **SM [P]**; above SM limit: **SH/OWN [P]**<br>• Approver sees margin, scheme income, F&I and accessories income | TL: 30 min<br>SM: 1 hour<br>SH: 2 hours | Next level up |
| B09 | **Discount approved / rejected / countered** | TL / SM / SH | • **SC [A]** go back to customer with the answer<br>• **ACC [I]** approved discount recorded for the deal | 1 hour | TL |
| B10 | **Free items requested** (accessories, insurance, warranty) | SC | Same as B08, valued at cost<br>• **ACC-S [I]** item cost confirmation | Same as B08 | Same as B08 |

### C. Booking

The single biggest hand-off point.

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| **C01** | **Booking created** (form filled, booking amount paid) | SC | • **ACC [A]** check the booking amount is really received (bank/UPI/card/cash), approve the receipt<br>• **ADM [A]** enter booking in OEM DMS; put it in the allocation queue; check stock<br>• **CR [A]** verification call: price, discount, free items, delivery promise, no off-record payment<br>• **TL / SM [P]** approve the deal sheet<br>• **ACC-S [A]** contact the customer to sell accessories and protection products<br>• **INS [A]** prepare insurance quote; confirm dealer policy or own policy<br>• **FIN [A]** if loan: start or continue the loan file<br>• **EXC [A]** if exchange: fix the date to take the old car and collect its documents<br>• **STK [A]** if car not in stock: add to OEM order plan<br>• **RTO [I]** registration city, fancy/BH number interest noted<br>• **MKT [I]** booking against source<br>• **HR [I]** booking counted for the consultant<br>• **CUST** booking confirmation with booking number, receipt and next steps | ACC: 2 hours<br>ADM: same day<br>CR: 24 hours<br>Deal sheet: 24 hours<br>ACC-S: 48 hours<br>INS: 48 hours<br>FIN: 24 hours<br>EXC: 48 hours | Each team's lead, then SM |
| C02 | **Booking amount confirmed by Accounts** | ACC | • **SC [I]** booking money confirmed<br>• **ADM [I]** booking valid for allocation | — | — |
| C03 | **Booking amount not found / payment failed** | ACC | • **SC [A]** contact customer<br>• **TL [I]**<br>• **ADM [A]** hold booking out of allocation queue | 4 hours | SM |
| C04 | **Verification call: all matches** | CR | • **ADM [I]** verified<br>• **SM [I]** clear for deal approval | — | — |
| C05 | **Verification call: mismatch** (different price, promise, cash paid off-record) | CR | • **SM [A]** investigate and correct<br>• **SC [I]** issue noted<br>• **SH [I]** if money is involved<br>• **OWN [I]** if off-record cash suspected | 24 hours | SH |
| C06 | **Customer not reachable for verification** | CR | • **SC [A]** arrange a time with customer<br>• **CR [A]** retry (3 attempts) | 48 hours | SM |
| C07 | **Deal sheet approved** | SM | • **ADM [I]** booking cleared<br>• **ACC [I]** final price, discount and offers locked | — | — |
| C08 | **Booking change requested** (variant, colour, fuel, transmission) | SC | • **SM [P]** approve<br>On approval:<br>• **ADM [A]** update DMS and allocation (may lose queue position)<br>• **ACC [A]** recalculate price and balance; offers re-checked<br>• **ACC-S [A]** update accessories kit<br>• **INS [A]** re-quote<br>• **FIN [A]** inform lender if loan amount changes<br>• **CUST** revised price and expected date | Approval: 4 hours<br>Others: 24 hours | SH |
| C09 | **Name change / booking transfer** | SC | • **SM [P]** approve per OEM rule<br>• **ACC [A]** update receipts; KYC of new name<br>• **ADM [A]** update DMS<br>• **FIN [A]** new loan file if needed<br>• **INS [A]** policy name<br>• **RTO [I]** new owner details | 24 hours | SH |

### D. Finance, insurance, exchange, accessories during waiting

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| D01 | **Loan documents incomplete** | FIN | • **SC [A]** collect missing documents from customer<br>• **CUST** list of documents pending | 48 hours | TL |
| D02 | **Loan file logged with lender(s)** | FIN | • **SC [I]** status<br>• **CUST** message that the loan is in process | — | — |
| D03 | **Loan sanctioned** | FIN | • **SC [I]** inform customer; confirm down payment<br>• **ACC [A]** record expected disbursement and down payment due<br>• **ADM [I]** payment plan for allocation priority<br>• **CUST** sanction details | — | — |
| D04 | **Loan rejected** | FIN | • **SC [A]** talk to customer: other lender, higher down payment, co-applicant, or cash<br>• **FIN [A]** try another lender<br>• **TL [I]** deal at risk<br>• **ADM [I]** allocation may be held | 24 hours | SM |
| D05 | **Delivery order (DO) received from lender** | FIN | • **ACC [A]** record loan amount as receivable; check total covered<br>• **ADM [I]** payment side ready for invoice<br>• **RTO [I]** hypothecation details for Form 34<br>• **INS [A]** add lender's name to policy | Same day | — |
| D06 | **Customer chooses own insurance** | INS | • **SC [A]** collect the policy copy (with lender's name if loan)<br>• **RTO [I]** policy expected from customer | Before invoice | DEL gate |
| D07 | **Insurance policy issued** | INS | • **RTO [I]** policy for Vahan<br>• **ACC [A]** record premium and collect it<br>• **DEL [I]** item ready<br>• **FIN [I]** copy to lender<br>• **CUST** policy PDF | — | — |
| D08 | **Exchange price agreed** | EXC | • **ACC [A]** record exchange value as an adjustment against the new car<br>• **SC [I]**<br>• **ADM [I]** for OEM exchange bonus proof | Same day | — |
| D09 | **Old car received** | EXC | • **ACC [A]** pay seller or adjust; arrange closure of old loan if any<br>• **STK [A]** used-car yard entry<br>• **SEC [I]** gate in<br>• **SC [I]**<br>• **CUST** receipt for old car | Same day | EXC manager |
| D10 | **Old car documents pending** (RC, NOC, Form 29/30) | EXC | • **SC [A]** collect from customer<br>• **ACC [I]** hold payment<br>• **CUST** list of pending documents | 3 days | EXC manager |
| D11 | **Accessories ordered by customer** | ACC-S | • **ACC [A]** add to amount due (or record as free, if approved)<br>• **ADM [I]** add to booking<br>• **PDI [I]** fitment needed after allocation<br>• **ACC-S [A]** check accessory stock; order if short | Order: 24 hours | ACC-S manager |
| D12 | **Accessory out of stock** | ACC-S | • **SC [A]** tell customer; offer alternative<br>• **DEL [I]** possible delivery delay | 24 hours | SM |
| D13 | **Extended warranty / RSA / coating sold** | INS / ACC-S | • **ACC [A]** add to amount due<br>• **PDI [I]** coating job (if applicable)<br>• **DEL [I]** certificate in delivery kit | — | — |

### E. Stock and allocation

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| E01 | **Booking waiting for stock** (no matching car) | System / ADM | • **STK [A]** include in OEM order<br>• **SM [I]** demand vs stock<br>• **SC [A]** tell customer the waiting period<br>• **CUST** expected waiting time | Order: next OEM order cycle | SH |
| E02 | **OEM order placed / OEM wholesale invoice received** | STK / ACC | • **ACC [A]** record OEM payable and funding bank entry<br>• **ADM [I]** incoming chassis list<br>• **SM [I]** | Same day | — |
| E03 | **Car in transit** | STK | • **ADM [A]** pre-match to waiting bookings<br>• **SC [I]** for matched bookings<br>• **CUST** "your car is on its way" (when matched) | — | — |
| E04 | **Car received at yard** | STK | • **ADM [A]** match to booking<br>• **ACC [I]** stock in; funding interest starts<br>• **SEC [I]** gate in<br>• **SM [I]** stock update | ADM: same day | SM |
| E04a | **Transit damage found** | STK | • **SM [A]** decide: repair or reject<br>• **ACC [A]** damage claim with transporter/OEM<br>• **ADM [A]** do not allocate until fixed<br>• **INS [I]** transit insurance claim if needed | 24 hours | SH |
| **E05** | **Chassis allocated to booking** | ADM | • **SC [A]** call customer with chassis details and expected date; collect balance and pending documents<br>• **ACC [A]** raise balance due; follow up payment<br>• **INS [A]** issue policy with chassis and engine numbers<br>• **FIN [A]** send chassis details/proforma to lender for DO<br>• **ACC-S [A]** start accessory fitment on this chassis<br>• **RTO [A]** prepare registration documents<br>• **PDI [A]** schedule PDI<br>• **DEL [I]** tentative delivery slot<br>• **STK [A]** tag and block the car in yard<br>• **CUST** chassis allotted message | SC: same day<br>INS: 24 hours<br>FIN: 24 hours<br>ACC-S: 48 hours<br>PDI: by 2 days before delivery | Each team lead, then SM |
| E06 | **Re-allocation** (chassis moved to another booking) | ADM (with SM approval) | • **SM [P]** before it happens<br>• **Old booking SC [A]** inform customer of new date<br>• **New booking SC [A]** inform customer<br>• **INS, FIN, ACC-S, RTO, PDI [A]** redo chassis-linked work for both bookings<br>• **CUST** (both) updated date | Approval first | SH |
| E07 | **Stock ageing crosses limit** (for example 60 / 90 days) | System | • **SM [A]** push plan (offer, priority allocation)<br>• **SH [I]**<br>• **ACC [I]** funding interest cost<br>• **SC [I]** cars to push | Weekly review | SH → OWN |
| E08 | **Physical stock audit mismatch** | STK / bank | • **SM [A]** and **ACC [A]** reconcile<br>• **SH, OWN [I]** | 24 hours | OWN |

### F. Payment and invoice

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| F01 | **Payment received** (part or balance) | ACC | • **ACC [A]** confirm in bank; issue receipt<br>• **SC [I]** updated balance<br>• **ADM [I]** payment status<br>• **CUST** receipt | Receipt: same day | — |
| F02 | **Cheque bounced / payment reversed** | ACC | • **SC [A]** contact customer<br>• **TL, SM [I]**<br>• **ADM [A]** hold invoice/delivery<br>• **CUST** notice | Same day | SH |
| F03 | **Cash above legal limit attempted** | System | • **ACC [I]** blocked<br>• **SM [I]** | Blocked instantly | — |
| F04 | **Loan disbursement received** | ACC | • **FIN [I]** close disbursement follow-up<br>• **SC [I]**<br>• **ADM [I]** | — | — |
| F05 | **Balance fully cleared** (customer + lender + exchange + approved credit = deal price) | ACC | • **ADM [A]** prepare invoice<br>• **SC [I]** fix delivery date with customer<br>• **RTO [I]** invoice coming<br>• **DEL [I]** payment gate cleared<br>• **CUST** "payment complete" message | Invoice: same day | SM |
| F06 | **Invoice pre-check failed** (missing KYC, PAN/Form 60, insurance, DO, approval, verification) | System / ADM | • **The team that owns the missing item [A]** (for example SC for KYC, INS for policy, FIN for DO, SM for approval)<br>• **ADM [I]** blocked list | 24 hours | SM |
| **F07** | **Invoice raised** | ACC / ADM | • **RTO [A]** start Vahan registration<br>• **ADM [A]** OEM DMS retail entry (warranty start, schemes)<br>• **FIN [A]** send invoice to lender for disbursement<br>• **INS [A]** confirm policy matches invoice<br>• **ACC [A]** TCS entry if applicable; scheme claim becomes eligible<br>• **SC [I]**<br>• **DEL [I]**<br>• **HR [I]** retail counted<br>• **SM [I]** retail count<br>• **CUST** invoice copy | RTO: same day<br>ADM: 24 hours<br>FIN: 24 hours | SM |
| F08 | **OEM retail entry done** | ADM | • **ACC [A]** file scheme claims with proofs<br>• **CR [I]** OEM survey will come to the customer | Per OEM claim deadline | SH |
| F09 | **Invoice cancellation / rebilling requested** | ADM / SM | • **SH [P]** and **ACC [P]** approve<br>On approval:<br>• **ACC [A]** credit note, new invoice<br>• **ADM [A]** OEM rebilling<br>• **RTO [A]** stop or correct registration<br>• **INS [A]** correct policy<br>• **FIN [A]** inform lender<br>• **OWN [I]** | Approval: 24 hours | OWN |

### G. Registration and FASTag

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| G01 | **Registration documents pending** (Form 20 signature, address proof, Form 34) | RTO | • **SC [A]** collect from customer<br>• **CUST** list of pending documents | 24 hours | TL |
| G02 | **Applied on Vahan, tax paid** | RTO | • **ACC [I]** road tax and fees paid<br>• **SC [I]**<br>• **CUST** application number | — | — |
| G03 | **Registration number allotted** | RTO | • **PDI [A]** fit HSRP when plates arrive<br>• **DEL [I]** item ready<br>• **FIN [I]** registration number for lender<br>• **INS [A]** add registration number to policy<br>• **FASTag desk [A]** issue FASTag on the number<br>• **SC [I]**<br>• **CUST** registration number | INS/FASTag: 24 hours | RTO lead |
| G04 | **Fancy / choice number requested** | SC | • **RTO [A]** apply or bid<br>• **ACC [A]** collect fee<br>• **DEL [I]** possible delay | Per auction | SM |
| G05 | **HSRP received and fitted** | RTO / PDI | • **DEL [I]** item ready | — | — |
| G06 | **Registration delayed beyond limit** | System | • **RTO lead [A]**<br>• **SM [I]**<br>• **SC [A]** update customer | Limit: for example 3 working days | SH |
| G07 | **RC received** | RTO | • **SC / DEL [A]** hand over to customer (or courier)<br>• **FIN [A]** copy to lender<br>• **CUST** RC ready message | 3 days | SM |

### H. PDI and delivery

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| H01 | **Delivery date requested by customer** | SC | • **DEL [A]** check bay capacity; book slot<br>• **ACC [I]** confirm payment clearance by that date<br>• **RTO [I]** registration needed by that date<br>• **PDI [A]** PDI done one day before<br>• **ACC-S [A]** fitment done before PDI<br>• **SM [I]** if VIP or festival-day peak | DEL: 4 hours | SM |
| H02 | **PDI scheduled** | PDI | • **STK [A]** move car to PDI bay<br>• **SEC [I]** car movement | Before slot | — |
| H03 | **Accessories fitted** | ACC-S / PDI | • **PDI [A]** check fitment in PDI<br>• **ACC [A]** bill accessories | — | — |
| H04 | **PDI passed** | PDI | • **DEL [I]** car ready<br>• **SC [I]**<br>• **CUST** (optional) invite to see the car | — | — |
| H05 | **PDI failed** (defect found) | PDI | • **SM [A]** decide: fix or swap chassis<br>• **STK [A]** fix arrangement<br>• **ADM [A]** re-allocate if swapping (triggers E06)<br>• **SC [A]** inform customer if date moves<br>• **DEL [I]** slot at risk | 24 hours | SH |
| H06 | **Delivery confirmed (day before)** | DEL | • **SC [A]** confirm time with customer<br>• **CR [I]**<br>• **SEC [I]** expected gate pass<br>• **CUST** reminder with time, what to bring (ID, original documents if any) | 24 hours before | — |
| H07 | **Delivery gate check failed** (balance due, invoice missing, insurance missing, registration/HSRP/FASTag pending, PDI not passed) | System / DEL | • **The team that owns the gap [A]**<br>• **SM [I]**<br>• **SC [A]** manage customer expectations | Before delivery time | SH |
| H08 | **Delivery with balance pending: approval requested** | SC / DEL | • **SH / OWN [P]** approve or reject<br>• **ACC [I]** credit to follow up | 1 hour | — |
| **H09** | **Car delivered** (delivery note signed, gate pass issued) | DEL | • **SEC [A]** check gate pass; log car out<br>• **CR [A]** feedback calls on day 1–2, 7, 30; review request<br>• **ACC [A]** close the deal ledger; confirm all receivables (lender, insurer payout, OEM schemes)<br>• **ADM [A]** mark delivered in DMS<br>• **FIN [A]** send delivery and RC documents to lender; claim payout<br>• **INS [I]** renewal date stored<br>• **STK [I]** car out of stock<br>• **SC [A]** thank-you call; referral request<br>• **HR [I]** delivery counted for incentive<br>• **MKT [I]** photo for social media (with consent)<br>• **SM, SH [I]** retail/delivery count<br>• **CUST** thank-you message, photo, review link, service contact | CR day-1 call: 48 hours<br>FIN docs: 3 days | CR lead / SM |
| H10 | **Customer refuses delivery** | DEL | • **SM [A]** resolve<br>• **SC [A]**<br>• **SH [I]** | Same day | SH |

### I. After delivery

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| I01 | **Feedback call due** (day 1–2, 7, 30) | System | • **CR [A]** call and record score | On due day | CR lead |
| I02 | **Low score / negative feedback** | CR | • **SM [A]** call customer; fix<br>• **SC [I]**<br>• **Department concerned [A]** (for example RTO for RC delay)<br>• Creates a complaint (K01) if needed | 24 hours | SH |
| I03 | **Google review posted** | MKT | • **MKT [A]** reply<br>• **SM [I]** if negative | 24 hours | SH |
| I04 | **Referral given by customer** | CR / SC | • **BDC [A]** create and call the new lead (A01)<br>• **SC [I]** referral linked to the customer<br>• **CR [I]** reward when the referral buys | BDC: same day | TL |
| I05 | **RC not handed over after X days** | System | • **RTO [A]**<br>• **SM [I]** | Limit: for example 15 days | SH |
| I06 | **Lender payout due / overdue** | System | • **FIN [A]** chase lender<br>• **ACC [I]** | Monthly | SH |
| I07 | **Insurer commission statement received** | ACC | • **ACC [A]** match policy by policy<br>• **INS [A]** resolve missing policies | Monthly | SH |
| I08 | **Scheme claim filed** | ACC | • **SM [I]** | — | — |
| I09 | **Scheme claim settled / short-paid / rejected** | ACC | • **SM [I]** settled<br>• Short-paid or rejected: **SM [A]** fix proofs or appeal; **SC [I]** if their paperwork caused it; **OWN [I]** loss | 7 days | SH → OWN |
| I10 | **Birthday / purchase anniversary** | System | • **CUST** greeting<br>• **SC [I]** chance to ask for referrals | — | — |
| I11 | **Upgrade window** (for example 3–5 years after purchase) | System | • **BDC [A]** call for upgrade/exchange (A01)<br>• **SC [I]** | — | — |

### J. Cancellation and refund

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| J01 | **Cancellation requested** | SC / CR | • **SM [A]** retention attempt; then approve or reject<br>• **TL [I]**<br>• **ADM [I]** possible chassis release<br>• **CUST** request received, reference number | SM: 24 hours | SH |
| **J02** | **Cancellation approved** | SM | • **ACC [A]** compute refund per booking terms; pay by bank transfer<br>• **ADM [A]** release chassis; cancel OEM booking; credit note if invoiced<br>• **STK [I]** car back to free stock<br>• **INS [A]** cancel policy / refund premium<br>• **FIN [A]** cancel loan with lender<br>• **RTO [A]** withdraw Vahan application if started<br>• **ACC-S [A]** stop or remove accessories<br>• **EXC [A]** return old car or settle (if already taken)<br>• **HR [A]** reverse incentive<br>• **CR [A]** exit call; reason record<br>• **MKT [I]** cancellation reason<br>• **CUST** cancellation confirmed; refund amount and date | ACC refund: 7 days (or as policy says)<br>Others: 48 hours | SH |
| J03 | **Refund paid** | ACC | • **SC [I]**<br>• **SM [I]**<br>• **CUST** refund reference | — | — |
| J04 | **Refund delayed beyond limit** | System | • **ACC lead [A]**<br>• **SH [I]** | — | OWN |

### K. Complaints

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| K01 | **Complaint logged** | CR / any | • **Department owning the category [A]** (for example RTO for RC, ACC for refund, SC/SM for promise not kept, DEL for delivery)<br>• **SM [I]**<br>• **CUST** complaint number | Reply: 24 hours; fix: per category | SH |
| K02 | **Complaint time limit missed** | System | • **SH [A]**<br>• **OWN [I]** if high priority | — | OWN |
| K03 | **Complaint resolved** | Owner department | • **CR [A]** confirm with customer before closing<br>• **SM [I]** | 48 hours | — |
| K04 | **Complaint from OEM call centre** | ADM / CR | Same as K01; **SH [I]** always (OEM-visible) | Per OEM | OWN |

### L. Master data and periodic events

| ID | Event | Done by | Notified → what they must do | Time limit | If not done |
|---|---|---|---|---|---|
| L01 | **New price list from OEM** | ADM / ACC | • **All SC, TL, SM [I]** new prices and effective date<br>• **SC [A]** re-send quotations that are still open and affected<br>• **ACC [A]** check bookings not yet invoiced (price at invoice date usually applies)<br>• **CUST** (open bookings) price change notice where it applies | Before effective date | SM |
| L02 | **New scheme / offer circular** | ADM / ACC | • **All SC, TL, SM [I]** new offers and conditions<br>• **ACC [A]** set up claim rules<br>• **MKT [A]** promote<br>• **BDC [A]** call relevant cold/warm leads | Same day | SM |
| L03 | **Scheme ending in X days** | System | • **SC [A]** close eligible leads and bookings<br>• **ACC [A]** make sure proofs are complete | 3 days before end | SM |
| L04 | **Daily summary (end of day)** | System | • **TL** team numbers; **SM** showroom numbers; **SH/OWN** all showrooms: enquiries, test drives, bookings, retails, deliveries, collections, cancellations, overdue tasks | 8 pm | — |
| L05 | **Morning task list** | System | • **Each person [I]** today's follow-ups, deliveries, pending approvals and overdue items | 9 am | — |
| L06 | **Month-end** | System | • **ACC [A]** claims, reconciliation<br>• **HR [A]** incentive calculation<br>• **SM, SH [I]** target vs achievement | Month end + 5 days | OWN |

---

## 5. Gates: steps that cannot happen until others are done

A gate is a check the CRM runs before a step is allowed. When it fails, the CRM tells the team that owns the missing item (events F06, H07).

### 5.1 Allocation gate

| Must be true | Owner if missing |
|---|---|
| Booking amount confirmed by Accounts (C02) | ACC |
| Verification call done and matched (C04) | CR |
| Deal sheet approved (C07) | SM |
| Dealer policy met: full payment or lender DO (for high-demand models) | SC / FIN |

### 5.2 Invoice gate

| Must be true | Owner if missing |
|---|---|
| Chassis allocated | ADM |
| Balance cleared, or lender DO covers the rest (F05 / D05) | ACC / FIN |
| KYC complete; PAN or Form 60 | SC |
| Insurance issued or own policy received (D06 / D07) | INS / SC |
| Discount and free items approved (B09) | SM |
| Exchange value settled (if exchange) (D08) | EXC |
| Offers' proofs collected | SC |

### 5.3 Registration gate

| Must be true | Owner if missing |
|---|---|
| Invoice raised (F07) | ACC |
| Insurance issued | INS |
| Form 20 signed, address proof, Form 34 if loan | SC / RTO |

### 5.4 Delivery gate

| Must be true | Owner if missing |
|---|---|
| Balance zero, or delivery-with-balance approved (H08) | ACC / SH |
| Invoice raised | ACC |
| Insurance in force | INS |
| Registration number or temporary registration | RTO |
| HSRP fitted | RTO / PDI |
| FASTag issued | FASTag desk |
| Accessories fitted | ACC-S |
| PDI passed (H04) | PDI |
| Delivery slot booked (H01) | DEL |

### 5.5 Refund gate

| Must be true | Owner if missing |
|---|---|
| Cancellation approved (J02) | SM |
| Invoice reversed by credit note (if invoiced) | ACC / ADM |
| Insurance and loan cancelled | INS / FIN |
| Old car settled (if exchange) | EXC |

---

## 6. Department inbox view

What each department receives. This is what their CRM home screen should show.

| Department | Action items they receive | Approvals they give | Info they see |
|---|---|---|---|
| **REC** | — | — | Expected appointments today |
| **BDC** | New digital leads (A01), recycled lost leads (A10), dormant leads (A11), referral leads (I04), upgrade calls (I11), scheme campaign calls (L02) | — | Appointment show/no-show |
| **SC** | Walk-ins (A02), assigned leads (A04), follow-ups (A08–A09), quotes after test drive (B04), approval answers (B09), payment failures (C03, F02), loan document gaps (D01), insurance copy (D06), exchange documents (D10), accessory stock-outs (D12), chassis allotted (E05), registration documents (G01), delivery confirmation (H06), cancellation requests (J01) | — | Own pipeline, booking status, payment balance, registration status |
| **TL** | First-contact misses (A05), overdue follow-ups (A09), hot leads (A07), lost-lead review (A10), demo car shortage (B02) | Discount within TL limit (B08) | Team funnel, daily summary |
| **SM** | Verification mismatches (C05), transit damage (E04a), stock ageing (E07), PDI failures (H05), delivery refusals (H10), low feedback (I02), claim rejections (I09), complaints (K01) | Discounts (B08), deal sheets (C01), booking changes (C08–C09), re-allocation (E06), cancellations (J01) | Showroom dashboard |
| **SH / OWN** | Escalations from all teams; stock audit mismatch (E08) | Large discounts (B08), invoice cancellation (F09), delivery with balance (H08) | All showrooms, money summaries |
| **EXC** | Evaluations (A06), old-car pickup (C01), old-car documents (D10), cancellation returns (J02) | Offers above evaluator limit (B06) | Exchange pipeline |
| **FIN** | Early eligibility (A06), loan files (C01), lender DO requests (E05), invoice to lender (F07), post-delivery documents (H09), payout chasing (I06), loan cancellation (J02) | — | Sanction, disbursement and payout status |
| **INS** | Quotes (C01), policy with chassis (E05), lender name (D05), registration number on policy (G03), cancellations (J02) | — | Policy and commission status |
| **ACC-S** | Upsell call after booking (C01), fitment after allocation (E05), fitment before delivery (H01), stock-outs (D12), cancellations (J02) | — | Accessory orders by booking |
| **ADM** | DMS entry and allocation (C01), changes (C08–C09), vehicle matching (E03–E04), re-allocation (E06), invoice preparation (F05), OEM retail entry (F07), rebilling (F09), PDI-fail swaps (H05), chassis release (J02) | — | Allocation queue, stock, blocked invoices |
| **STK** | OEM order needs (C01, E01), receiving (E04), transit damage (E04a), car blocking (E05), demo car ready (B01), PDI moves (H02) | — | Stock list, ageing |
| **ACC** | Booking money check (C01), every payment (F01–F02), exchange adjustments (D08–D09), invoice and TCS (F07), scheme claims (F08, I08–I09), refunds (J02), reconciliations (I06–I07), month-end (L06) | Invoice cancellation (F09), refund release | Receivables, collections, claim status |
| **RTO** | Registration preparation (E05), Vahan filing (F07), fancy numbers (G04), HSRP (G03), delays (G06), RC handover (G07, I05), withdrawal (J02) | — | Registration tracker |
| **PDI** | PDI scheduling (E05, H01), HSRP fitment (G03), fitment check (H03) | — | Delivery calendar |
| **DEL** | Slot booking (H01), confirmation (H06), gate failures (H07) | — | Delivery calendar, gate checklist |
| **CR** | Verification calls (C01), feedback calls (H09, I01), exit calls (J02), complaint closure (K03) | — | Scores, complaint ageing |
| **MKT** | Review replies (I03), scheme promotion (L02) | — | Leads, bookings, lost reasons, cancellations by source |
| **HR** | Incentive reversal (J02), month-end incentives (L06) | — | Bookings, retails, deliveries per consultant |
| **SEC** | Test-drive gate log (B03–B04), delivery gate pass check (H09) | — | Expected movements |

---

## 7. Event × department matrix

`A` = action, `P` = approval, `I` = info, blank = not involved. Key events only.

| Event | BDC | SC | TL | SM | SH | EXC | FIN | INS | ACC-S | ADM | STK | ACC | RTO | PDI | DEL | CR | MKT | HR | SEC | CUST |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| A01 Digital lead | A | I | I | | | | | | | | | | | | | | I | | | ✉ |
| A02 Walk-in | | A | I | | | | | | | | | | | | | | | | | ✉ |
| A06 Lead qualified | | | I | | | A | A | | | A | | | | | | | | | | |
| A10 Lead lost | A | | A | I | | | | | | | | | | | | | I | | | |
| B01 Test drive booked | | | I | | | | | | | | A | | | | | | | | I | ✉ |
| B04 Test drive done | | A | I | | | | | | | | | | | | | | | | A | ✉ |
| B08 Discount request | | | P | P | P | | | | | | | I | | | | | | | | |
| **C01 Booking created** | | | P | P | | A | A | A | A | A | A | A | I | | | A | I | I | | ✉ |
| C05 Verification mismatch | | I | | A | I | | | | | | | | | | | | | | | |
| C08 Booking change | | | | P | | | A | A | A | A | | A | | | | | | | | ✉ |
| D04 Loan rejected | | A | I | | | | A | | | I | | | | | | | | | | |
| D05 DO received | | | | | | | | A | | I | | A | I | | | | | | | |
| D09 Old car received | | I | | | | | | | | | A | A | | | | | | | I | ✉ |
| **E05 Chassis allocated** | | A | | | | | A | A | A | | A | A | A | A | I | | | | | ✉ |
| E06 Re-allocation | | A | | P | | | A | A | A | A | | | A | A | | | | | | ✉ |
| F05 Balance cleared | | I | | | | | | | | A | | | I | | I | | | | | ✉ |
| **F07 Invoice raised** | | I | | I | | | A | A | | A | | A | A | | I | | | I | | ✉ |
| G03 Number allotted | | I | | | | | I | A | | | | | | A | I | | | | | ✉ |
| H01 Delivery date set | | | | I | | | | | A | | | I | I | A | A | | | | | |
| H05 PDI failed | | A | | A | | | | | | A | A | | | | I | | | | | |
| **H09 Delivered** | | A | | I | I | | A | I | | A | I | A | | | | A | I | I | A | ✉ |
| I02 Low feedback | | I | | A | | | | | | | | | | | | | | | | |
| **J02 Cancellation approved** | | | | | | A | A | A | A | A | I | A | A | | | A | I | A | | ✉ |
| K01 Complaint | | | | I | | | | | | | | | | | | | | | | ✉ |

✉ = message to customer.

---

## 8. Customer messages

| Step | Message | Channel |
|---|---|---|
| Lead received (A01) | Welcome, brochure, showroom location, consultant name and number | WhatsApp / SMS |
| After walk-in (A02) | Thank you, quotation if given, consultant contact | WhatsApp |
| Test drive booked (B01) | Date, time, address; reminder 2 hours before | WhatsApp / SMS |
| After test drive (B04) | Thank you, feedback link | WhatsApp |
| Quotation (B07) | Quotation PDF with validity | WhatsApp / email |
| Exchange offer (B06) | Offer value and validity | WhatsApp |
| Booking (C01) | Booking number, receipt, model/variant/colour, expected waiting, next steps, consultant contact | WhatsApp / SMS / email |
| Booking change (C08) | Revised price and date | WhatsApp |
| Loan sanctioned / documents pending (D01, D03) | Status and document list | WhatsApp |
| Insurance issued (D07) | Policy PDF | WhatsApp / email |
| Old car received (D09) | Receipt | WhatsApp |
| Waiting update (E01, E03) | Waiting time; car on its way | WhatsApp |
| Chassis allotted (E05) | Chassis allotted, balance due, documents needed | WhatsApp |
| Payment received (F01) | Receipt and balance | WhatsApp / SMS |
| Payment complete (F05) | Confirmation; book delivery date | WhatsApp |
| Invoice (F07) | Invoice copy | WhatsApp / email |
| Registration (G02, G03, G07) | Application number, registration number, RC ready | WhatsApp |
| Delivery reminder (H06) | Date, time, what to bring | WhatsApp / SMS |
| Delivered (H09) | Thank you, delivery photo, review link, service contact, roadside number | WhatsApp |
| Feedback (I01) | Short survey | WhatsApp / call |
| Cancellation (J01–J03) | Request received; confirmation; refund reference | WhatsApp / email |
| Complaint (K01, K03) | Complaint number; resolution confirmation | WhatsApp / SMS |
| Birthday / anniversary (I10) | Greeting | WhatsApp |

---

## 9. Escalation ladder and time limits

### 9.1 Ladder

```
Assigned person
   │ time limit missed
   ▼
Team lead of that department (TL for sales; desk lead for FIN/INS/ACC/RTO/etc.)
   │ 2× time limit, or high value/high priority
   ▼
Showroom Sales Manager (SM)
   │ 24 hours more, or money/OEM/complaint risk
   ▼
Sales Head / GM (SH)
   │ unresolved money or reputation risk
   ▼
Owner (OWN)
```

### 9.2 Priority levels

| Priority | Examples | Behaviour |
|---|---|---|
| **Critical** | Off-record cash suspected (C05), cheque bounced after delivery, stock audit mismatch (E08), invoice cancellation (F09) | Instant alert to SM, SH and OWN; cannot be muted |
| **High** | New digital lead (A01), walk-in (A02), booking created (C01), discount approval (B08), delivery gate failure (H07), PDI failure (H05) | Push alert plus task; short time limit |
| **Normal** | Follow-ups, documents pending, registration updates | Task in list; reminder at time limit |
| **Info** | Counts, status changes | Feed and daily summary only |

### 9.3 Suggested default time limits

| Work | Limit |
|---|---|
| First call on a digital lead | 5 minutes |
| Consultant attends walk-in | 2 minutes |
| Quotation after test drive | 24 hours |
| Discount approval | TL 30 min · SM 1 hour · SH 2 hours |
| Booking money check (ACC) | 2 hours |
| Verification call (CR) | 24 hours |
| Deal sheet approval | 24 hours |
| Accessories call after booking | 48 hours |
| Insurance policy after allocation | 24 hours |
| Loan DO request after allocation | 24 hours |
| Invoice after balance cleared | Same day |
| Vahan filing after invoice | Same day |
| PDI | 1 day before delivery |
| First feedback call after delivery | 48 hours |
| Refund after cancellation approval | 7 days (or booking terms) |
| Complaint first reply | 24 hours |

---

## 10. Rules for building the notification engine

1. **Every event is recorded first.** A notification comes from an event in the record's history (for example "booking created"), never from a person remembering to tell someone.
2. **Action notifications are tasks.** They have an owner, a time limit and a status. They close themselves when the matching work is recorded (for example the ACC task from C01 closes when the receipt is approved, C02).
3. **Send to roles, resolve to people.** The rule says "ACC"; the CRM sends it to the accounts user(s) for that branch. The consultant's own TL and SM get the sales escalations.
4. **Branch-aware.** A booking at branch X notifies branch X's teams, plus central teams (for example central accounts) if the dealer is set up that way.
5. **One event, one message per person.** If a person is in two notified roles, they get one notification. Repeated reminders are bundled.
6. **Channels by priority.** Critical and high: in-app push plus WhatsApp/SMS to staff. Normal: in-app task list. Info: feed and daily summary.
7. **Escalation timers run on working hours** set per branch (holidays excluded). Lead response timers may run on extended hours.
8. **Gates block the button.** Invoice, delivery and refund buttons stay disabled until the gate passes, and the screen shows which team still owes what.
9. **Approvals are recorded with who, when and why.** Editing an approved deal re-opens the approval.
10. **Customer messages use approved templates** (WhatsApp Business templates) and respect opt-out.
11. **Every notification links to the record** (lead, booking, chassis, payment) so the receiver can act in one tap.
12. **Settings screen** for the owner: who gets what, time limits, escalation levels, quiet hours, channels.
13. **Reports on the notifications themselves:** tasks overdue by department and person, average time to act, escalations per month. This shows where the hand-offs break down.
