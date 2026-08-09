# Google Sheets Data Contract

**Spreadsheet** `Euler Master` (`173a0LK-L7sgEBmkxwpZI3ovkxDNCdwf7DTyH8AZyn7w`) · **102 tabs · 1,056 columns** · generated from a live read-only pull, not from the .xlsx export.

Repo baseline `f92e1d2`. Every row below was derived by resolving the live header text through `gsheets.SYNC_MAP` + `HEADER_ALIASES` (the same code the sync uses), then cross-referencing `backend/server.py` writers and the live cell contents. Nothing here is inferred from naming.

## Legend

| Class | Meaning |
|---|---|
| **App-authoritative** | CRM (Mongo) is the source of truth; sync overwrites the cell |
| **Sheet-authoritative** | Dealership owns the value; CRM reads only, never writes |
| **Derived** | Computed — either a sheet formula, or a CRM-rebuilt report tab |
| **Audit/log** | Append-only history; never mutated or deleted |
| **Helper/navigation** | Search/lookup UI for staff (Lead Register A:I, nav tabs) |
| **Legacy/unused** | Written by nothing today — **no source of truth** |

## Totals

| Column class | Count | Share |
|---|---:|---:|
| Derived | 627 | 59.4% |
| App-authoritative | 234 | 22.2% |
| Sheet-authoritative | 69 | 6.5% |
| Helper/navigation | 66 | 6.2% |
| Audit/log | 56 | 5.3% |
| Legacy/unused | 4 | 0.4% |
| **TOTAL** | **1056** | 100% |

- **Formula-driven cells:** 23 columns contain live formulas (mostly `=HYPERLINK` ID navigation)
- **Currently populated:** 286 columns hold at least one value
- **Columns with NO source of truth:** 665 — these are **two different problems**:
  - **4 in the 9 operational registers.** Every other operational column is now either
    mapped to a Mongo/computed source or explicitly declared in `gsheets.SOURCE_REQUIRED` with the
    reason and the source that must be built. `test_iter20_column_contract.py` asserts that no
    operational column is silently unaccounted for. (Was 67 before implementation.)
  - **661 in derived/report and helper tabs** — legacy Apps-Script report columns that
    no longer refresh. They need a *rebuilder*, not a per-column source. See P2-1 / P2-2 of the repair plan.
- **Stale (derived tab behind lead data):** 391

### Operational coverage after implementation

| | Before | After |
|---|---:|---:|
| App-authoritative (mapped) columns | 171 | **234** |
| Operational columns with no classification | 67 | **4** |
| Declared `SOURCE_REQUIRED` (blank by design, reason recorded) | 0 | **5** |

### The 20 contract attributes

Each per-tab table below carries: column position, header, class, Mongo collection, Mongo field, frontend, backend writer, sheet writer/mapping, formula, CRM-write, Sheet-write, preserve-on-sync, populated, stale, no-source-of-truth, and the create/update/close semantics. Where an attribute is uniform for a whole tab it is stated once in that tab's preamble instead of repeated on all 78 columns.

---

## Dashboard

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 2 · **columns:** 8
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Last Updated: | Derived | `—` | — | no | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| B | 2026-08-08 17:17:21 | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| E | Lead ID | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| F | Customer | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| G | Type | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| H | Discussion | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| I | Executive | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Last Updated:`, `B 2026-08-08 17:17:21`, `D Date`, `E Lead ID`, `F Customer`, `G Type`, `H Discussion`, `I Executive`

---

## Lead Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 3 · **columns:** 78
- **Column classes:** App-authoritative × 68, Helper/navigation × 9, Legacy/unused × 1
- **Mongo source:** `db.leads` · **backend writers:** `create_lead, import_commit, recompute_lead, update_lead`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | <helper area col A — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| B | <helper area col B — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| C | <helper area col C — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| D | <helper area col D — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| E | <helper area col E — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| F | <helper area col F — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| G | <helper area col G — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| H | <helper area col H — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| I | <helper area col I — masked> | Helper/navigation | `—` | — | no | NO | YES | YES | YES | no | NO (sheet/user owned) |
| J | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| K | Created Date | App-authoritative | `createdDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| M | Mobile | App-authoritative | `mobile` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| N | Alternate Mobile | App-authoritative | `altMobile` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | Village | App-authoritative | `village` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| P | City | App-authoritative | `city` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Q | Lead Source | App-authoritative | `leadSource` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| R | Interested Model | App-authoritative | `interestedModel` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| S | Variant | App-authoritative | `variant` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| T | Executive | App-authoritative | `executive` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| U | Current Status | App-authoritative | `currentStatus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| V | Priority | App-authoritative | `priority` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| W | Budget | App-authoritative | `budget` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| X | Last Activity | App-authoritative | `lastActivity` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| Y | Next Follow-up Date | App-authoritative | `nextFollowupDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Z | Next Follow-up Time | Legacy/unused | `—` | — | no | NO | YES | YES | no | no | YES — NO SOURCE OF TRUTH |
| AA | Booking Date | App-authoritative | `bookingDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AB | Booking Amount | App-authoritative | `bookingAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AC | Finance Required | App-authoritative | `financeRequired` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AD | Exchange Required | App-authoritative | `exchangeRequired` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AE | Delivery Status | App-authoritative | `deliveryStatus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AF | Delivery Date | App-authoritative | `deliveryDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AG | Outstanding Amount | App-authoritative | `outstandingAmount` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AH | Remarks | App-authoritative | `remarks` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AI | Last Updated | App-authoritative | `lastUpdated` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AJ | Last Updated By | App-authoritative | `lastUpdatedBy` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AK | Account Status | App-authoritative | `accountStatus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AL | Closed Date | App-authoritative | `closedDate` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AM | Close Reason | App-authoritative | `closeReason` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AN | Final Outstanding | App-authoritative | `finalOutstanding` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AO | Closed By | App-authoritative | `closedBy` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AP | Close Timestamp | App-authoritative | `closeTimestamp` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AQ | Ex Showroom | App-authoritative | `exShowroom` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AR | RTO | App-authoritative | `rto` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AS | Insurance Amount | App-authoritative | `insuranceAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AT | Accessories Amount | App-authoritative | `accessoriesAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AU | Handling Charges | App-authoritative | `handlingCharges` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AV | TRC | App-authoritative | `trc` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AW | Fastag | App-authoritative | `fastag` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AX | Extended Warranty | App-authoritative | `extendedWarranty` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AY | Other Charges | App-authoritative | `otherCharges` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AZ | Gross Vehicle Cost | App-authoritative | `grossVehicleCost` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BA | Customer Payable | App-authoritative | `customerPayable` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BB | Financer Name | App-authoritative | `financerName` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BC | Finance File Number | App-authoritative | `financeFileNumber` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BD | Last Payment Mode | App-authoritative | `lastPaymentMode` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BE | Total Received | App-authoritative | `totalReceived` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BF | Consumer Discount | App-authoritative | `consumerDiscount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BG | Exchange Bonus | App-authoritative | `exchangeBonus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BH | Loyalty Bonus | App-authoritative | `loyaltyBonus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BI | Referral Bonus | App-authoritative | `referralBonus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BJ | DSA Bonus | App-authoritative | `dsaDiscount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BK | Additional Discount | App-authoritative | `additionalDiscount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BL | Total Discount | App-authoritative | `totalDiscount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BM | OEM Scheme Amount | App-authoritative | `oemSchemeAmount` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BN | Dealer Scheme Amount | App-authoritative | `dealerSchemeAmount` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BO | Customer Outstanding | App-authoritative | `customerOutstanding` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BP | Company Outstanding | App-authoritative | `companyOutstanding` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BQ | Insurer Name | App-authoritative | `insurerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BR | Invoice Number | App-authoritative | `invoiceNumber` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BS | Chassis Number | App-authoritative | `chassisNumber` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| BT | Number Plate | App-authoritative | `numberPlate` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| BU | Insurance Status | App-authoritative | `insuranceStatus` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BV | Registration Status | App-authoritative | `registrationStatus` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BW | Invoice Status | App-authoritative | `invoiceStatus` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BX | RC Status | App-authoritative | `rcStatus` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BY | PDI Status | App-authoritative | `pdiStatus` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| BZ | Dealer Earnings | App-authoritative | `dealerTotalEarnings` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |

> ⚠️ **1 column(s) with no source of truth** in this tab: `Z Next Follow-up Time`

---

## Activity Log

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 12
- **Column classes:** App-authoritative × 11, Legacy/unused × 1
- **Mongo source:** `db.activities` · **backend writers:** `add_activity, convert_booking, create_lead`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Activity ID | App-authoritative | `activityId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| C | Date | App-authoritative | `date` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| D | Time | App-authoritative | `time` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| E | Activity Type | App-authoritative | `activityType` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| F | Discussion | App-authoritative | `discussion` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| G | Next Follow-up | App-authoritative | `nextFollowup` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| H | Reminder | Legacy/unused | `—` | — | no | NO | YES | YES | no | no | YES — NO SOURCE OF TRUTH |
| I | Executive | App-authoritative | `executive` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| J | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| K | Mobile | App-authoritative | `mobile` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Model | App-authoritative | `model` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |

> ⚠️ **1 column(s) with no source of truth** in this tab: `H Reminder`

---

## Booking Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 17
- **Column classes:** App-authoritative × 17
- **Mongo source:** `db.bookings` · **backend writers:** `convert_booking`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | BookingID | App-authoritative | `bookingId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | LeadID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| C | CustomerName | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| D | Booking Date | App-authoritative | `bookingDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| E | Vehicle Model | App-authoritative | `model` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| F | Variant | App-authoritative | `variant` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| G | Booking Amount | App-authoritative | `bookingAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| H | Finance Required | App-authoritative | `financeRequired` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| I | Exchange Required | App-authoritative | `exchangeRequired` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| J | CommercialSnapshotID | App-authoritative | `snapshotId` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| K | Booking Status | App-authoritative | `bookingStatus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Created By | App-authoritative | `createdBy` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| M | Created Date | App-authoritative | `createdDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| N | Last Updated | App-authoritative | `lastUpdated` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | Amount Received | App-authoritative | `amountReceived` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| P | Payment Mode | App-authoritative | `paymentMode` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Q | Dealer Earnings | App-authoritative | `dealerTotalEarnings` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |

---

## Payment Ledger

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 12
- **Column classes:** App-authoritative × 12
- **Mongo source:** `db.payments` · **backend writers:** `_add_payment_internal`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt Number | App-authoritative | `receiptNumber` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| C | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| D | Date | App-authoritative | `date` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| E | Amount | App-authoritative | `amount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| F | Payment Mode | App-authoritative | `paymentMode` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| G | Narration | App-authoritative | `narration` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| H | Running Total | App-authoritative | `runningTotal` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| I | Outstanding Balance | App-authoritative | `outstandingBalance` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| J | Payment ID | App-authoritative | `paymentId` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| K | Financer Name | App-authoritative | `financerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Finance File Number | App-authoritative | `financeFileNumber` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |

---

## Delivery Tracker

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 17
- **Column classes:** App-authoritative × 17
- **Mongo source:** `db.deliveries` · **backend writers:** `mark_delivery`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| C | Insurance | App-authoritative | `insurance` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| D | Registration | App-authoritative | `registration` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| E | Invoice | App-authoritative | `invoice` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| F | Accessories | App-authoritative | `accessories` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| G | RC | App-authoritative | `rc` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| H | Number Plate | App-authoritative | `numberPlate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| I | PDI | App-authoritative | `pdi` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| J | Delivered | App-authoritative | `delivered` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| K | Delivery Date | App-authoritative | `deliveryDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Feedback | App-authoritative | `feedback` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| M | Delivery ID | App-authoritative | `deliveryId` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| N | Insurer Name | App-authoritative | `insurerName` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | Invoice Number | App-authoritative | `invoiceNumber` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| P | Dealer Earnings | App-authoritative | `dealerTotalEarnings` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| Q | Chassis Number | App-authoritative | `chassisNumber` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |

---

## Finance Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 10
- **Column classes:** App-authoritative × 10
- **Mongo source:** `db.finance` · **backend writers:** `sync_finance_file`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | File Number | App-authoritative | `financeFileNumber` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| C | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| D | Financer | App-authoritative | `financerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| E | Sanctioned Amount | App-authoritative | `committedAmount` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| F | Received Against File | App-authoritative | `disbursedAmount` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| G | File Outstanding | App-authoritative | `financeOutstanding` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| H | Status | App-authoritative | `status` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| I | Last Payment Date | App-authoritative | `lastPaymentDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| J | Last Updated | App-authoritative | `lastUpdated` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |

---

## Finance Pending

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 13
- **Last 'Refreshed:' stamp in sheet:** `2026-08-09 18:43:56`
- **Column classes:** Derived × 13

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | File Number | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| B | Lead ID | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| C | Customer | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| D | Financer | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| E | Sanctioned Amount | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| F | Received | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| G | File Outstanding | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| H | Status | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| I | Delivery Date | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| J | Days Since Delivery | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| K | Due By | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| L | Overdue | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| M | Last Payment Date | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |

---

## Finance Overdue

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 10
- **Last 'Refreshed:' stamp in sheet:** `2026-08-09 18:43:56`
- **Column classes:** Derived × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | File Number | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | YES | YES | NO |
| B | Lead ID | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| C | Customer | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| D | Financer | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| E | Sanctioned Amount | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| F | File Outstanding | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| G | Status | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| H | Delivery Date | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| I | Days Since Delivery | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |
| J | Due By | Derived | `—` | — | no | YES (full mirror) | YES | N/A (full rewrite) | no | YES | NO |

---

## Insurance Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 19
- **Column classes:** App-authoritative × 19
- **Mongo source:** `db.insurance` · **backend writers:** `create_insurance`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Entry ID | App-authoritative | `entryId` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| B | Lead ID | App-authoritative | `leadId` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| C | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| D | Mobile | App-authoritative | `mobile` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| E | Model | App-authoritative | `model` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| F | Variant | App-authoritative | `variant` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| G | Insurance Company | App-authoritative | `insuranceCompany` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| H | Policy Number | App-authoritative | `policyNumber` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| I | Insurance Amount | App-authoritative | `insuranceAmount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| J | Payout Rate % | App-authoritative | `payoutRatePct` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| K | Expected Payout | App-authoritative | `expectedPayout` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| L | Received Payout | App-authoritative | `receivedPayout` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| M | Payout Outstanding | App-authoritative | `payoutOutstanding` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| N | Status | App-authoritative | `status` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | Policy Date | App-authoritative | `policyDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| P | Delivery Date | App-authoritative | `deliveryDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| Q | Last Updated | App-authoritative | `lastUpdated` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| R | Remarks | App-authoritative | `remarks` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| S | Insurance Executive | App-authoritative | `insuranceExecutive` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |

---

## Scheme Claim Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 33
- **Column classes:** App-authoritative × 33
- **Mongo source:** `db.claims` · **backend writers:** `create_manual_claim, recompute_lead, record_claim_receipt, settle_claim`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Claim ID | App-authoritative | `claimId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Source | App-authoritative | `source` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| C | Booking ID | App-authoritative | `bookingId` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| D | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| E | Customer | App-authoritative | `customer` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| F | Model | App-authoritative | `model` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| G | Variant | App-authoritative | `variant` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| H | Booking Date | App-authoritative | `bookingDate` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| I | Scheme Month | App-authoritative | `schemeMonth` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| J | Executive | App-authoritative | `executive` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| K | Component | App-authoritative | `component` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| L | Component Key | App-authoritative | `componentKey` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| M | Consumer Discount | App-authoritative | `consumerDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| N | Exchange Bonus | App-authoritative | `exchangeBonus` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | Loyalty Bonus | App-authoritative | `loyaltyBonus` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| P | Referral Bonus | App-authoritative | `referralBonus` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| Q | DSA Discount | App-authoritative | `dsaDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| R | Additional Discount | App-authoritative | `additionalDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| S | Total Discount | App-authoritative | `totalDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| T | Dealer Discount | App-authoritative | `dealerDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| U | OEM Discount | App-authoritative | `oemDiscount` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| V | DSA Approval | App-authoritative | `dsaApproval` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| W | Claim Required | App-authoritative | `claimRequired` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| X | Eligible Claim | App-authoritative | `eligibleClaim` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Y | Claim Amount | App-authoritative | `claimAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Z | Received Amount | App-authoritative | `receivedAmount` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AA | Claim Status | App-authoritative | `claimStatus` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AB | Claim Reference Number | App-authoritative | `claimReference` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AC | Claim Submitted Date | App-authoritative | `submittedDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AD | Claim Approved Date | App-authoritative | `approvedDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AE | Claim Received Date | App-authoritative | `claimReceivedDate` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AF | Claim Ageing (Days) | App-authoritative | `ageingDays` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AG | Claim Remarks | App-authoritative | `claimRemarks` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |

---

## Quotation Log

- **Tab class:** helper / other · **header row:** 1 · **columns:** 31
- **Column classes:** Helper/navigation × 31

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Quote ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| B | Date | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| C | Customer Name | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| D | Mobile | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| E | Model | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| F | Variant | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| G | Ex Showroom | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| H | Insurance | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| I | Registration | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| J | Accessories | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| K | Handling | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| L | TRC | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| M | Fastag | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| N | Ext Warranty | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| O | Other Charges | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| P | Gross Vehicle Cost | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| Q | Consumer Discount | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| R | Exchange Bonus | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| S | Loyalty Bonus | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| T | Referral Bonus | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| U | DSA Bonus | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| V | Additional Discount | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| W | Total Discount | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| X | Customer Payable | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| Y | OEM Share (Dealer Gets) | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| Z | Finance Required | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| AA | Exchange Value | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| AB | Financer | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| AC | Narration | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| AD | Generated By | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| AE | Price Version | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |

> ⚠️ **31 column(s) with no source of truth** in this tab: `A Quote ID`, `B Date`, `C Customer Name`, `D Mobile`, `E Model`, `F Variant`, `G Ex Showroom`, `H Insurance`, `I Registration`, `J Accessories`, `K Handling`, `L TRC`, `M Fastag`, `N Ext Warranty` …

---

## Scheme Master

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 13
- **Column classes:** Sheet-authoritative × 13

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Scheme Month | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| B | Effective From | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| C | Effective To | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| D | Circular Ref | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| E | Model | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| F | Variant | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| G | Component | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| H | Component Key | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| I | Dealer Share | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| J | Company Share | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| K | Total Benefit | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| L | Status | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| M | Notes | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |

---

## Incentive Master

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 10
- **Column classes:** Sheet-authoritative × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Scheme Month | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| B | Effective From | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| C | Effective To | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| D | Circular Ref | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| E | Product Category | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| F | Incentive Per Retail | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| G | Min Retails | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| H | Max Slab | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| I | Status | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| J | Notes | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |

---

## Incentive Register

- **Tab class:** helper / other · **header row:** 1 · **columns:** 14
- **Column classes:** Helper/navigation × 14

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Incentive ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| B | Scheme Month | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| C | Executive | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| D | Lead ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| E | Booking ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| F | Model | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| G | Variant | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| H | Product Category | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| I | Delivery Date | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| J | Incentive Amount | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| K | Status | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| L | Paid Date | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| M | Remarks | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| N | Last Updated | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |

> ⚠️ **14 column(s) with no source of truth** in this tab: `A Incentive ID`, `B Scheme Month`, `C Executive`, `D Lead ID`, `E Booking ID`, `F Model`, `G Variant`, `H Product Category`, `I Delivery Date`, `J Incentive Amount`, `K Status`, `L Paid Date`, `M Remarks`, `N Last Updated`

---

## PRICE MASTER

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 19
- **Column classes:** Sheet-authoritative × 19

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Model | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| B | Variant | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| C | Body Type | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| D | Ex Showroom Price | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| E | RTO | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| F | Insurance | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| G | Accessories | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| H | Handling Charges | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| I | TRC | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| J | Fastag | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| K | Extended Warranty | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| L | Other Charges | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| M | GST % | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| N | TCS Applicable | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| O | Effective From | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| P | Effective To | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| Q | Price Version | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| R | Status | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| S | Remarks | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |

---

## OEM Claim Dashboard

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 2
- **Column classes:** Derived × 2

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | OEM CLAIM DASHBOARD | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Generated: 2026-07-23 16:42:19 | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **2 column(s) with no source of truth** in this tab: `A OEM CLAIM DASHBOARD`, `D Generated: 2026-07-23 16:42:19`

---

## Owner Commercial Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 2
- **Column classes:** Derived × 2

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | OWNER COMMERCIAL REPORT | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Generated: 2026-07-23 15:10:39 | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **2 column(s) with no source of truth** in this tab: `A OWNER COMMERCIAL REPORT`, `D Generated: 2026-07-23 15:10:39`

---

## Claim Exception Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Generated At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Booking ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Exception Type | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Severity | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Detail | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Generated At`, `B Lead ID`, `C Booking ID`, `D Exception Type`, `E Severity`, `F Detail`, `G Version`

---

## Dealer Earnings Register

- **Tab class:** AUTHORITATIVE OPERATIONAL · **header row:** 1 · **columns:** 49
- **Column classes:** App-authoritative × 47, Legacy/unused × 2
- **Mongo source:** `db.leads (computed in recompute_lead)` · **backend writers:** `recompute_lead`
- **On create:** append one row · **on update:** upsert by stable ID · **on close/delete:** row retained, status fields updated (no hard delete)

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | App-authoritative | `leadId` | yes | YES | YES | NO | YES (formula present) | YES | no | NO |
| B | Booking ID | App-authoritative | `bookingId` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| C | Customer Name | App-authoritative | `customerName` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| D | Executive | App-authoritative | `executive` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| E | Team Leader | Legacy/unused | `—` | — | no | NO | YES | YES | no | no | YES — NO SOURCE OF TRUTH |
| F | Lead Source | App-authoritative | `leadSource` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| G | Vehicle Model | App-authoritative | `model` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| H | Variant | App-authoritative | `variant` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| I | Colour | Legacy/unused | `—` | — | no | NO | YES | YES | no | no | YES — NO SOURCE OF TRUTH |
| J | Current Stage | App-authoritative | `currentStage` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| K | Booking Date | App-authoritative | `bookingDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| L | Delivery Date | App-authoritative | `deliveryDate` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| M | Invoice Number | App-authoritative | `invoiceNumber` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| N | Customer Payable | App-authoritative | `customerPayable` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| O | OEM Eligible Scheme | App-authoritative | `oemEligible` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| P | Customer Scheme Benefit Passed | App-authoritative | `customerSchemeBenefitPassed` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| Q | Dealer Scheme Retained | App-authoritative | `dealerSchemeRetained` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| R | Insurance Payout | App-authoritative | `insurancePayout` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| S | Customer Insurance Benefit Passed | App-authoritative | `customerInsuranceBenefitPassed` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| T | Dealer Insurance Income | App-authoritative | `dealerInsuranceIncome` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| U | Finance Incentive | App-authoritative | `financeIncentive` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| V | Accessories Margin | App-authoritative | `accessoriesMargin` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| W | Exchange Margin | App-authoritative | `exchangeMargin` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| X | Documentation Income | App-authoritative | `documentationIncome` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Y | Warranty Income | App-authoritative | `warrantyIncome` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| Z | RSA Income | App-authoritative | `rsaIncome` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AA | Referral Income | App-authoritative | `referralIncome` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AB | Campaign Incentive | App-authoritative | `campaignIncentive` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AC | Other Income | App-authoritative | `otherIncome` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AD | TOTAL DEALER EARNINGS | App-authoritative | `dealerTotalEarnings` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AE | Claim Status | App-authoritative | `claimStatus` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AF | Insurance Status | App-authoritative | `insuranceStatus` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AG | Last Updated | App-authoritative | `lastUpdated` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AH | Created By | App-authoritative | `createdBy` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AI | Modified By | App-authoritative | `modifiedBy` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AJ | Timestamp | App-authoritative | `timestamp` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AK | Remarks | App-authoritative | `remarks` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AL | Consumer Retained | App-authoritative | `consumerRetained` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AM | Exchange Retained | App-authoritative | `exchangeRetained` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AN | Loyalty Retained | App-authoritative | `loyaltyRetained` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AO | Referral Retained | App-authoritative | `referralRetained` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AP | DSA Retained | App-authoritative | `dsaRetained` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AQ | Scheme Retained Breakup | App-authoritative | `schemeRetainedBreakup` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AR | Dealer Margin Gross (Incl GST) | App-authoritative | `dealerMarginGrossInclGst` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AS | Dealer Margin GST (5%) | App-authoritative | `dealerMarginGst` | no | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AT | Dealer Margin Net (Ex GST) | App-authoritative | `dealerMarginNetExGst` | yes | no | YES | NO | NO (CRM overwrites) | YES | no | NO |
| AV | OEM Extra Support Received | App-authoritative | `oemExtraSupportReceived` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AW | OEM Extra Support Passed To Customer | App-authoritative | `oemExtraSupportPassed` | yes | no | YES | NO | NO (CRM overwrites) | no | no | NO |
| AX | OEM Extra Support Retained | App-authoritative | `oemExtraSupportRetained` | no | no | YES | NO | NO (CRM overwrites) | YES | no | NO |

> ⚠️ **2 column(s) with no source of truth** in this tab: `E Team Leader`, `I Colour`

---

## OEM Extra Support Register

- **Tab class:** helper / other · **header row:** 1 · **columns:** 12
- **Column classes:** Helper/navigation × 12

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| B | Booking ID | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| C | Customer Name | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| D | Vehicle Model | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| E | Variant | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| F | Booking Date | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| G | OEM Extra Support Received | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| H | OEM Extra Support Passed To Customer | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| I | OEM Extra Support Retained | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| J | Status | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| K | Last Updated | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |
| L | Remarks | Helper/navigation | `—` | — | no | NO | YES | YES | no | no | YES — unclassified |

> ⚠️ **12 column(s) with no source of truth** in this tab: `A Lead ID`, `B Booking ID`, `C Customer Name`, `D Vehicle Model`, `E Variant`, `F Booking Date`, `G OEM Extra Support Received`, `H OEM Extra Support Passed To Customer`, `I OEM Extra Support Retained`, `J Status`, `K Last Updated`, `L Remarks`

---

## Today's Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:17`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Today's Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:18`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Today's Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:18`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Today's Follow-ups

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:25`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Pending Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:19`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Pending Follow-ups

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:19`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Monthly Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:20`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Monthly Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 1
- **Column classes:** Derived × 1

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Monthly Bookings | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **1 column(s) with no source of truth** in this tab: `A Monthly Bookings`

---

## Monthly Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:21`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Monthly Payments

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:21`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## Payments — Cash (Month)

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:22`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## Payments — UPI (Month)

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:23`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## Payments — Finance (Month)

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:24`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## Payments — Other (Month)

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:25`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## Outstanding Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 12
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:21`
- **Column classes:** Derived × 12

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Booking Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Received | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Customer OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| J | Total OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| K | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| L | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **12 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Booking Amount`, `G Received`, `H Customer OS`, `I Finance OS`, `J Total OS`, `K Status`, `L Executive`

---

## Navigation Matrix

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 5
- **Column classes:** Sheet-authoritative × 5

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Sheet | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| B | Column | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| C | Classification | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| D | Navigation Target | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| E | Implemented | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |

---

## MP — Hi-Load — Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:32`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:33`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:34`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Pending Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:35`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Cancelled

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:36`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Outstanding

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:37`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Hi-Load — Revenue

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:38`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## MP — Hi-Load — Dealer Earnings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 8
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:41`
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Vehicle | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Dealer Retained | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Insurance Income | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Other | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Total Extra | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Vehicle`, `D Dealer Retained`, `E Insurance Income`, `F Other`, `G Total Extra`, `H Status`

---

## MP — Neo HiRange — Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:42`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:43`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:44`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Pending Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:45`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Cancelled

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:46`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Outstanding

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:47`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Neo HiRange — Revenue

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:48`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## MP — Neo HiRange — Dealer Earnings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 8
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:52`
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Vehicle | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Dealer Retained | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Insurance Income | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Other | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Total Extra | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Vehicle`, `D Dealer Retained`, `E Insurance Income`, `F Other`, `G Total Extra`, `H Status`

---

## MP — Storm — Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:53`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:54`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:55`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Pending Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:56`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Cancelled

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:57`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Outstanding

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:58`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Storm — Revenue

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:59`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## MP — Storm — Dealer Earnings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 8
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:02`
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Vehicle | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Dealer Retained | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Insurance Income | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Other | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Total Extra | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Vehicle`, `D Dealer Retained`, `E Insurance Income`, `F Other`, `G Total Extra`, `H Status`

---

## MP — Turbo Max — Leads

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:03`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:05`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:06`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Pending Deliveries

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:07`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Cancelled

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:09`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Outstanding

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 9
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:10`
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Variant | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Cust OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| I | Finance OS | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Variant`, `F Status`, `G Executive`, `H Cust OS`, `I Finance OS`

---

## MP — Turbo Max — Revenue

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:12`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Receipt | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Date | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Amount | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Mode | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Receipt`, `B Lead ID`, `C Customer`, `D Date`, `E Amount`, `F Mode`

---

## MP — Turbo Max — Dealer Earnings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 8
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:17:17`
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Vehicle | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Dealer Retained | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Insurance Income | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Other | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| G | Total Extra | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| H | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Vehicle`, `D Dealer Retained`, `E Insurance Income`, `F Other`, `G Total Extra`, `H Status`

---

## Active Bookings

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 3 · **columns:** 6
- **Last 'Refreshed:' stamp in sheet:** `2026-08-08 17:16:20`
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | YES | YES | YES — derived tab with no rebuilder |
| B | Customer | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| C | Mobile | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| D | Model | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| E | Status | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |
| F | Executive | Derived | `—` | — | no | NO | YES | YES | no | YES | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Lead ID`, `B Customer`, `C Mobile`, `D Model`, `E Status`, `F Executive`

---

## Migration Import Log

- **Tab class:** audit / log · **header row:** 1 · **columns:** 10
- **Column classes:** Audit/log × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| B | Batch ID | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| C | Action | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| D | Temp ID | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| E | Lead ID | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| F | Customer | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| G | Mobile | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| H | Status | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| I | Detail | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| J | User | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |

---

## Dealer Earnings Analytics

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 2 · **columns:** 2
- **Column classes:** Derived × 2

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Generated | Derived | `—` | — | no | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| B | 2026-08-08 17:17:30 | Derived | `—` | — | YES | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |

> ⚠️ **2 column(s) with no source of truth** in this tab: `A Generated`, `B 2026-08-08 17:17:30`

---

## RelationshipIndex

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 11
- **Column classes:** Sheet-authoritative × 11

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | LeadID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| B | CustomerName | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| C | Mobile | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| D | BookingID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| E | CommercialSnapshotID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| F | PaymentIDs | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| G | DeliveryID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| H | ClaimID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| I | LatestActivityID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| J | Current Status | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| K | Last Updated | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |

---

## Booking Status History

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | LeadID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | BookingID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Old Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | New Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Remark | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Updated By | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Timestamp`, `B LeadID`, `C BookingID`, `D Old Status`, `E New Status`, `F Remark`, `G Updated By`

---

## Vehicle Allocation

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 9
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | AllocationID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | LeadID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | BookingID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | VIN | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Motor Number | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Chassis Number | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Allocated Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Remark | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A AllocationID`, `B LeadID`, `C BookingID`, `D VIN`, `E Motor Number`, `F Chassis Number`, `G Allocated Date`, `H Status`, `I Remark`

---

## Quotation Schema

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 8
- **Column classes:** Sheet-authoritative × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | QuotationID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| B | LeadID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| C | BookingID | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| D | QuotationVersion | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| E | PriceVersion | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| F | SchemeVersion | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| G | CommercialTermsHash | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |
| H | Generated At | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | no | no | NO (sheet is SoT) |

---

## Executive Scorecard

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 11
- **Column classes:** Derived × 11

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Executive | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Assigned Leads | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Today Activities | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Pending Follow-ups | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Bookings | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Deliveries | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Outstanding Collections | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Conversion % | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Avg Discount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| J | Avg Booking Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| K | Updated At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **11 column(s) with no source of truth** in this tab: `A Executive`, `B Assigned Leads`, `C Today Activities`, `D Pending Follow-ups`, `E Bookings`, `F Deliveries`, `G Outstanding Collections`, `H Conversion %`, `I Avg Discount`, `J Avg Booking Value`, `K Updated At`

---

## Dealer Daily Register

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 12
- **Column classes:** Derived × 12

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Leads | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Bookings | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Payments Total | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Cash | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | UPI | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Finance | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Other Payments | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Deliveries | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| J | Outstanding | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| K | Top Executive | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| L | Updated At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **12 column(s) with no source of truth** in this tab: `A Date`, `B Leads`, `C Bookings`, `D Payments Total`, `E Cash`, `F UPI`, `G Finance`, `H Other Payments`, `I Deliveries`, `J Outstanding`, `K Top Executive`, `L Updated At`

---

## Commercial Audit

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 10
- **Column classes:** Derived × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | User | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Booking ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Field | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Old Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | New Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Reason | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Approved By | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| J | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **10 column(s) with no source of truth** in this tab: `A Timestamp`, `B User`, `C Booking ID`, `D Lead ID`, `E Field`, `F Old Value`, `G New Value`, `H Reason`, `I Approved By`, `J Version`

---

## Commercial Snapshot

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 70
- **Column classes:** Derived × 70

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Booking Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Price List Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Price Master Row ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Price Effective Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Vehicle Model | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Variant | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Body Type | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Booking Amount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| J | Booking Executive | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| K | Booking Mode | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| L | Finance Required | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| M | Exchange Required | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| N | Ex Showroom Price | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| O | Accessories | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| P | Insurance | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| Q | Registration / RTO | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| R | Fastag | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| S | Handling Charges | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| T | TRC | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| U | Extended Warranty | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| V | RSA / AMC | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| W | Other Charges | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| X | GST % | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| Y | TCS Applicable | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| Z | TCS | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AA | Consumer Discount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AB | Exchange Bonus | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AC | Loyalty Bonus | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AD | Referral Bonus | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AE | DSA Discount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AF | Additional Discount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AG | Total Discount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AH | Benefit Mode | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AI | Customer Benefit Passed | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AJ | Old Vehicle Brand | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AK | Old Vehicle Model | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AL | Registration Number | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AM | Evaluated Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AN | Final Exchange Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AO | Financer | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AP | Loan Amount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AQ | Down Payment | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AR | Gross Vehicle Cost | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AS | Gross Invoice Amount | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AT | Net Vehicle Cost | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AU | Customer Payable | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AV | Booking Locked | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AW | Lock Reason | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AX | Created At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AY | Updated At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| AZ | Updated By | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BA | Booking ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BB | Snapshot ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BC | Snapshot Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BD | Superseded By | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BE | Amendment Reason | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BF | Benefit Passed Breakup | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BG | Booking ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BH | Snapshot ID | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BI | Snapshot Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BJ | Superseded By | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BK | Amendment Reason | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BL | Benefit Passed Breakup | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BM | OEM Extra Support Received | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BN | OEM Extra Support Passed To Customer | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BO | OEM Extra Support Retained | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BP | Dealer Margin Gross (Incl GST) | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BQ | Dealer Margin GST (5%) | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| BR | Dealer Margin Net (Ex GST) | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **70 column(s) with no source of truth** in this tab: `A Lead ID`, `B Booking Date`, `C Price List Version`, `D Price Master Row ID`, `E Price Effective Date`, `F Vehicle Model`, `G Variant`, `H Body Type`, `I Booking Amount`, `J Booking Executive`, `K Booking Mode`, `L Finance Required`, `M Exchange Required`, `N Ex Showroom Price` …

---

## Performance Log

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 6
- **Column classes:** Audit/log × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| B | Operation | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| C | Avg Ms | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| D | Max Ms | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| E | Count | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| F | Warning | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |

---

## Backup Registry

- **Tab class:** audit / log · **header row:** 1 · **columns:** 10
- **Column classes:** Audit/log × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Backup No | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| B | Timestamp | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| C | Version | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| D | Drive URL | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| E | Spreadsheet ID | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| F | Row Count | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| G | Sheet Count | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| H | Settings Hash | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| I | Protection Hash | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| J | Notes | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |

---

## Crash Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 11
- **Column classes:** Audit/log × 11

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| B | User | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| C | Module | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| D | Function | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| E | Lead ID | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| F | Error Code | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| G | Message | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| H | Stack Trace | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| I | Execution Ms | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| J | Spreadsheet ID | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| K | Version | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |

---

## Transaction Log

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 10
- **Column classes:** Audit/log × 10

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| B | User | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| C | Module | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| D | Action | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| E | Lead ID | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| F | Execution Ms | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| G | Status | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| H | Error Code | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| I | Message | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| J | Version | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |

---

## Obs Health Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 9
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Color | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Passed | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Failed | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Critical | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Warnings | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Summary | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Date`, `B Status`, `C Color`, `D Passed`, `E Failed`, `F Critical`, `G Warnings`, `H Summary`, `I Version`

---

## Obs Performance Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Operation | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Avg Ms | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Max Ms | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Count | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Over Threshold | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Date`, `B Operation`, `C Avg Ms`, `D Max Ms`, `E Count`, `F Over Threshold`, `G Version`

---

## Obs KPI Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 4
- **Column classes:** Derived × 4

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Metric | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Value | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **4 column(s) with no source of truth** in this tab: `A Date`, `B Metric`, `C Value`, `D Version`

---

## Obs Growth Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 4
- **Column classes:** Derived × 4

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Sheet | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Data Rows | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **4 column(s) with no source of truth** in this tab: `A Date`, `B Sheet`, `C Data Rows`, `D Version`

---

## Obs Activity Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 6
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | User | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Module | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Action Count | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Top Actions | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Date`, `B User`, `C Module`, `D Action Count`, `E Top Actions`, `F Version`

---

## Obs Report Index

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 9
- **Column classes:** Derived × 9

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Overall Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Health Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Perf Warnings | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Total Rows | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Active Users | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Email Sent | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Generated At | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **9 column(s) with no source of truth** in this tab: `A Date`, `B Overall Status`, `C Health Status`, `D Perf Warnings`, `E Total Rows`, `F Active Users`, `G Email Sent`, `H Generated At`, `I Version`

---

## Masters

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 1
- **Column classes:** Sheet-authoritative × 1

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Lead Sources | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |

---

## PEP Daily Report

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 11
- **Column classes:** Derived × 11

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Leads | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Activities | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Payments | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Deliveries | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Outstanding | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Errors | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Health | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| I | SLA Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| J | Capacity Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| K | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **11 column(s) with no source of truth** in this tab: `A Date`, `B Leads`, `C Activities`, `D Payments`, `E Deliveries`, `F Outstanding`, `G Errors`, `H Health`, `I SLA Status`, `J Capacity Status`, `K Version`

---

## PEP Backup Verify

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Backup No | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Passed | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Row Match | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Sheets OK | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Detail | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Date`, `B Backup No`, `C Passed`, `D Row Match`, `E Sheets OK`, `F Detail`, `G Version`

---

## PEP Capacity Log

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Total Rows | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | File MB | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Perf Max Ms | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Quota Risk | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Warning | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Date`, `B Total Rows`, `C File MB`, `D Perf Max Ms`, `E Quota Risk`, `F Warning`, `G Version`

---

## PEP SLA Log

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 7
- **Column classes:** Derived × 7

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Operation | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Avg Ms | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Max Ms | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Threshold | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | SLA Status | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **7 column(s) with no source of truth** in this tab: `A Date`, `B Operation`, `C Avg Ms`, `D Max Ms`, `E Threshold`, `F SLA Status`, `G Version`

---

## PEP Operator Summary

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 8
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | User | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Leads | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Activities | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Payments | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Deliveries | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Total Actions | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Date`, `B User`, `C Leads`, `D Activities`, `E Payments`, `F Deliveries`, `G Total Actions`, `H Version`

---

## PEP DR Validation

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 8
- **Column classes:** Derived × 8

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Backup No | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Passed | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Health | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Dashboard | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Reports | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| G | Detail | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| H | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **8 column(s) with no source of truth** in this tab: `A Date`, `B Backup No`, `C Passed`, `D Health`, `E Dashboard`, `F Reports`, `G Detail`, `H Version`

---

## PEP Alerts

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 6
- **Column classes:** Derived × 6

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Date | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| B | Alert Type | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| C | Severity | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| D | Message | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| E | Notified | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |
| F | Version | Derived | `—` | — | no | NO | YES | YES | no | no | YES — derived tab with no rebuilder |

> ⚠️ **6 column(s) with no source of truth** in this tab: `A Date`, `B Alert Type`, `C Severity`, `D Message`, `E Notified`, `F Version`

---

## Dashboard Data

- **Tab class:** derived / report (projection — rebuildable) · **header row:** 1 · **columns:** 2
- **Column classes:** Derived × 2

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Last Refresh | Derived | `—` | — | no | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |
| B | 2026-08-08 17:17:32 | Derived | `—` | — | no | NO | YES | YES | YES | no | YES — derived tab with no rebuilder |

> ⚠️ **2 column(s) with no source of truth** in this tab: `A Last Refresh`, `B 2026-08-08 17:17:32`

---

## Settings

- **Tab class:** master / config (sheet-authoritative) · **header row:** 1 · **columns:** 2
- **Column classes:** Sheet-authoritative × 2

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Key | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |
| B | Value | Sheet-authoritative | `(imported)` | — | no | NO | YES | YES | YES | no | NO (sheet is SoT) |

---

## Import Log

- **Tab class:** audit / log · **header row:** 1 · **columns:** 4
- **Column classes:** Audit/log × 4

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | Timestamp | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| B | Category | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| C | Count | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |
| D | Details | Audit/log | `—` | — | no | NO | YES | YES | no | no | NO (append-only log) |

---

## Audit Log

- **Tab class:** audit / log · **header row:** 2 · **columns:** 5
- **Column classes:** Audit/log × 5

| Col | Header | Class | Mongo field | FE | Formula | CRM write | Sheet write | Preserve | Populated | Stale | No SoT |
|---|---|---|---|---|---|---|---|---|---|---|---|
| A | 2026-08-08 17:16:17 | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| B | writerish07@gmail.com | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| C | DASHBOARD_DEBUG | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| D | today=2026-08-08 | monthStart=2026-08-01 | rowsProcessed=0 | paymentRows=0 | todayLeads=0 | todayBookings=0 | todayFollowups=0 | todayDeliveries=0 | pendingDeliveries=0 | pendingPayments=0 | monthlyLeads=0 | revenue=0 | outstanding=0 | financeOutstanding=0 | statusDist={} | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |
| E | GO-LIVE-2+v2.2-quotation-finance-fix|sch:1.0|mig:1 | Audit/log | `—` | — | no | NO | YES | YES | YES | no | NO (append-only log) |

---
