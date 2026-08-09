# Google Sheets Repair Plan

**Baseline** repo `f92e1d2` · workbook `Euler Master` (`173a0LK-…yn7w`) · 102 tabs · 1,056 columns.
Evidence: live read-only pull of the whole workbook + code trace of `backend/server.py`,
`backend/gsheets.py`, `backend/commercial.py`. Companion: `GOOGLE_SHEETS_DATA_CONTRACT.md`.

**Nothing in this plan has been executed.** No production data was modified, no writes were
issued (a read-only OAuth scope was used, so writes were not merely avoided but impossible).

## Verification gap — read this before acting on anything

The production API and its MongoDB are **unreachable from the build environment**
(`onrender.com` → `CONNECT tunnel failed, 403`). Therefore:

- Every **Sheet-side** finding below is **observed fact**.
- Every **App-side** value is **UNVERIFIED**. Anything described as a mismatch between Sheet
  and Mongo is a *candidate* until `/api/integrations/gsheets/reconcile` is run against production.

No repair in P0 may execute before that reconcile output exists.

---

# P0 — Financial / data integrity

### P0-1 · Foreign preview records inside the production workbook
`BK26000102` and `RC26000102` each occupy **two rows** with **different underlying records**.

| | Booking row 6 | Booking row 7 |
|---|---|---|
| LeadID | LD26000013 | **LD26000002** |
| Customer | CLOUD END-TO-END QA | **Hari Narayan** |
| Booking Status | Booked | *(blank)* |
| Finance Required | No | **"UPI"** ← value belongs to Payment Mode |

Row 7 asserts `LD26000002 = Hari Narayan`. Production asserts `LD26000002 = Satya Narayan`
(Lead Register row 10) and `LD26000003 = Hari Narayan`. Row 7 also uses ISO dates (CRM-era, not
the Excel serials of the genuine legacy rows 2–4) and is column-shifted by one position from
`Finance Required` onward.

**Diagnosis:** a preview deployment sharing the production `GSHEET_ID` wrote rows from a
*different* Mongo whose ID counter had reached the same values. This is the exact failure the
`env_safety` guard in `f92e1d2` was built to stop — the guard is **inert until configured**.

**Repair:** none until production Mongo is queried for `BK26000102` / `RC26000102`. Then remove
the row that has no counterpart in production Mongo. Never merge the two.

### P0-2 · `ENVIRONMENT` / `PRODUCTION_GSHEET_ID` unverified on both services
The guard ships but is off by default. Until confirmed, P0-1 **can recur at any time**, and any
repair performed now can be re-corrupted by the next preview deploy. **This blocks every other
repair.**

### P0-3 · Structurally damaged Lead Register rows
Rows **4, 5, 6, 7, 9** carry no Lead ID. Row 9 holds `Customer Outstanding 230000` with no owning
record — an unattributed financial figure visible to staff. `LD26000001` sits at row 29 (last),
out of ID order, while rows 4–7 are gutted: the signature of a partial overwrite.

**Repair:** classify each row against production Mongo, then clear only rows proven to be
orphaned residue. Do not renumber; do not re-sort the register.

### P0-4 · Bookings persisted with `Customer Payable ₹0`
`LD26000012` (₹50,000 received), `LD26000013` (₹50,000), `LD26000019` (₹5,000) are Booked with
Customer Payable ₹0 — money received against no commercial structure. These predate strict
booking mode (`78c2880`), which now prevents new occurrences.

**Repair:** re-run `recompute_lead` for each after confirming a Price Master row exists.

### P0-5 · Finance file `55` bypassed the `FN26` contract
`db.finance` holds one file: number **`55`**, `LD26000021`, SUNDARAM, sanctioned ₹433. The
generator produces `FN26000101`-style numbers **only when the caller supplies none** — a typed
value is accepted verbatim. Confirmed in `_resolve_finance_file_for_payment`.

**Repair:** reject non-conforming numbers on new records; classify `55` as legacy/historical.
Do **not** renumber it — `RC26000110` references it.

### P0-6 · `Customer Payable` is not reduced by auto-entitlement benefits — **needs owner ruling**
`compute_commercial_totals` reads only `OFFER_KEYS` (staff-typed), never
`AUTO_SCHEME_COMPONENT_KEYS` (`rtoBenefit`, `insuranceBenefit`, `rtoInsuranceBenefit`). So the
August "Insurance Benefits Up to ₹10,000/₹20,000" **never reduces what the customer pays**; it
only raises `companyOutstanding` and the claim.

The circular calls this a *consumer* scheme ("Euler Festive Benefit – Insurance Support on
eligible vehicle purchases"). If the customer is meant to receive it, Customer Payable on every
August lead is **overstated by the benefit amount**. If it is a dealer↔OEM settlement only, the
current behaviour is right.

I cannot resolve this from code or the circular alone — it changes customer-facing invoice
amounts, so it needs your explicit ruling. **Do not change the numbers until then.**

---

## Resolved, NOT a defect — negative `Dealer Scheme Retained` (item J)

Traced Price Master → Scheme Master → `compute_scheme_income_breakdown` → dealer earnings, and
reproduced it numerically against the **live** Scheme Master.

```
retained = (c_full − c_pass) − d_pass          # commercial.py:475
```

For Turbo in Aug-2026 the auto-entitlement `insuranceBenefit` is force-included identically in
both the "full" and "passed" splits, so `c_full − c_pass = 0`, leaving `retained = −d_pass`.

The August circular EM/08-2026/001 specifies for **Turbo**:

| Scheme | Dealer Share | Company Share | Total |
|---|---:|---:|---:|
| Insurance Benefits Up to | **₹10,000** | ₹10,000 | ₹20,000 |

The live Scheme Master matches the letter exactly. **−₹10,000 is the dealer's own contractually
mandated contribution** — a real dealer cost, correctly signed, on exactly the 8 Turbo leads that
show it (`LD26000002`–`07`, `09`, `10`, `19`). It reconciles: dealer ₹10,000 + OEM claim ₹10,000 =
₹20,000 customer benefit, and `Company Outstanding ₹10,000` matches the Claim Register.

**Action: none. Do not "fix" these numbers.** (P0-6 above is a separate question about the
*customer* side of the same benefit.)

> ⚠️ Separately: the circular's own **HiLoad total row is internally inconsistent** — it lists
> Consumer Scheme dealer ₹5,000 but totals dealer share as ₹0, and totals ₹25,000 against a
> ₹20,000 company sum. That is an OEM document error, not a CRM defect. Worth raising with your ASM.

---

# P1 — Operational

### P1-1 · 67 operational columns have no source of truth — 50 need only mapping
Traced every one against the codebase. **They are not all new work:**

| Verdict | Count | Meaning |
|---|---:|---|
| **MAP ONLY** | **50** | Value already computed/stored in Mongo; needs a `SYNC_MAP` field + `HEADER_ALIASES` entry |
| **NEEDS IMPLEMENTATION** | **17** | No source anywhere in the codebase |

**MAP ONLY** — e.g. `closedDate`, `closeReason`, `finalOutstanding`, `insuranceStatus`,
`registrationStatus`, `invoiceStatus`, `rcStatus`, `pdiStatus` (Lead Register); `createdBy`,
`lastUpdated`, `dealerTotalEarnings` (Booking); `deliveryId` (Delivery); `lastPaymentDate`
(Finance); `bookingId`, `schemeMonth`, `executive`, and the full discount breakdown (Claims);
`marginGrossInclGst`, `marginGst`, `claimStatus` (Dealer Earnings).

*Caveat:* the five per-component `… Retained` columns and `Scheme Retained Breakup` map to
`retainedByComponent`, which **is computed** in `compute_scheme_income_breakdown` but is **not
persisted** to `db.leads` — only the `dealerSchemeRetained` total is. These need persistence plus
mapping, not new calculation.

**NEEDS IMPLEMENTATION (17):** `lastActivity`, `nextFollowUpTime`, `lastUpdatedBy`, `closedBy`,
`closeTimestamp` (Lead); `nextFollowUp`, `reminder` (Activity); `feedback` (Delivery);
`insuranceExecutive` (Insurance); `source`, `dsaApproval`, `claimReceivedDate`, `claimRemarks`
(Claims); `teamLeader`, `colour`, `currentStage`, `modifiedBy` (Dealer Earnings).

### P1-2 · `LD26000021` is Delivered with no Delivery Tracker row
Lead Register says `Delivered` / `Closed`; Delivery Tracker contains only `LD26000020`. Also its
delivery date is `2026-12-31` — a future date that should not have passed validation.

### P1-3 · Orphan reference — `Commercial Snapshot` is empty
`BK26000102` references `SN26000102`; the tab holds a header row and nothing else. Every
snapshot reference in the workbook is currently an orphan.

### P1-4 · Insurance Register is empty
Zero data rows despite `create_insurance` being wired to `sheet_sync("insurance")`. Either no
insurance has been recorded in production, or the sync never fired. Needs the production reconcile
to distinguish.

### P1-5 · Sync queue never inspected
`sheet_sync_log` lives in production Mongo. Pending/failed counts, oldest pending timestamp and
failed IDs are all **unknown**.

### P1-6 · New rows do not receive ID navigation hyperlinks
Existing ID cells are `=HYPERLINK("#gid=…&range=A29","LD26000001")` — 23 such cells live across
Lead/Booking/Payment/Claim registers. `_formula_cells` correctly **preserves** them on update, but
the append path writes plain text, so every new record loses cross-register navigation. Needs the
formula *template* implemented for appends, not just preservation.

---

# P2 — Reporting

### P2-1 · 47 derived tabs stale by ~26 hours
All stamped `2026-08-08 17:16–17:17`; newest lead data is `2026-08-09T19:27:48Z`. These were
written by the legacy Apps Script, which no longer runs. Only **Finance Pending** and **Finance
Overdue** are current (`2026-08-09 18:43:56`) — they are the two the CRM now rebuilds.

### P2-2 · 29 derived tabs have no refresh mechanism at all
No `Refreshed:` stamp and no rebuilder: **Dashboard**, **Dealer Earnings Analytics**, **OEM Claim
Dashboard**, **Owner Commercial Report**, **Commercial Snapshot**, **Executive Scorecard**,
**Claim Exception Report**, **Booking Status History**, **Vehicle Allocation**, **Dealer Daily
Register**, plus the `Obs *` and `PEP *` families.

**Cadence must not be assumed uniform.** Proposed classification for your confirmation:

| Cadence | Tabs | Rationale |
|---|---|---|
| **Event-driven** | Finance Pending/Overdue, Commercial Snapshot, Booking Status History | Must be correct the instant a record changes |
| **Daily** | Today's *, Pending *, Dealer Daily Register, PEP Daily | Day-scoped by definition |
| **Monthly** | Monthly *, MP — <model> — * (40 tabs), Executive Scorecard | Month-scoped aggregates |
| **On-demand** | Dashboard, Owner Commercial Report, OEM Claim Dashboard, Obs * | Expensive; rebuild when opened |

### P2-3 · Claim Register semantics
All 17 claims read `Eligible Claim ₹10,000`, `Claim Status Pending`, `Scheme Month` **blank** on
every row. `schemeMonth` is computed but unmapped (P1-1).

---

# P3 — Cosmetic / legacy

- **P3-1 · A:I helper area contradicts the register by one ID position.** Helper says
  `LD26000001 = Satya Narayan Saini`; register says `Roshan sharma`. Helper row 2 holds a test
  record (`First Real Lead`, `9800000001`). This is legacy pre-migration ID assignment, **visible
  to staff** — cosmetic only in that no calculation reads it.
- **P3-2 · `LD26000020` delivery fields are junk** — invoice, chassis and number plate all `"33"`.
- **P3-3 · 661 derived/helper columns** in non-operational tabs have no rebuilder (subset of P2).
- **P3-4 · Legacy rows 2–4** store dates as Excel serials (`46206`, `46238`) while CRM rows use ISO.

---

# Item I — per-record proposed action

**Nothing deleted. No record is actioned until production Mongo is reachable and classified.**

| Record | Classification | Proposed | Rationale |
|---|---|---|---|
| `BK26000102` row 6 (LD26000013) | Synthetic QA | **ARCHIVE** | CRM-authoritative but QA data |
| `BK26000102` row 7 (LD26000002) | Preview artifact | **UNKNOWN → DELETE if absent from prod Mongo** | Foreign env; contradicts production identity |
| `RC26000102` row 6 (LD26000013) | Synthetic QA | **ARCHIVE** | Pairs with booking row 6 |
| `RC26000102` row 7 (LD26000002) | Preview artifact | **UNKNOWN → DELETE if absent from prod Mongo** | Same as above |
| `LD26000001` | Real production | **REPAIR** | Genuine customer (Roshan sharma); row position + helper mismatch only |
| `LD26000021` | Synthetic lifecycle test | **UNKNOWN** | Full lifecycle but `9999999988`, delivery `2026-12-31`, missing delivery row |
| `LD26000020` | Synthetic lifecycle test | **UNKNOWN** | Junk delivery fields |
| `LD26000002`–`LD26000010` | Real production | **KEEP** | Genuine customers, consistent commercials |
| `LD26000011` | Synthetic ("Production Te…") | **ARCHIVE** | Test |
| `LD26000012`, `LD26000013` | Synthetic QA | **ARCHIVE** | Also P0-4 (payable ₹0) |
| `LD26000014`–`LD26000018` | Synthetic ("ZZ QA SMOKE TEST") | **ARCHIVE** | Test |
| `BK26000103` | Synthetic QA | **ARCHIVE** | Belongs to `LD26000018` |
| `PY52085906819c` | Synthetic QA | **ARCHIVE** | Payment ID on `RC26000103` |
| Lead Register rows 4–7, 9 | Structural residue | **UNKNOWN → REPAIR** | Row 9 carries ₹230,000 unattributed |
| Finance file `55` | Legacy/historical | **KEEP + flag** | Referenced by `RC26000110`; do not renumber |

**Contamination scale: 11 of 21 leads are synthetic.** Only `LD26000001`–`LD26000010` are real.

---

# Sequencing

Repairs must run in this order; each stage's evidence gates the next.

1. **P0-2** — set `ENVIRONMENT` + `PRODUCTION_GSHEET_ID` on production, and a **separate**
   `GSHEET_ID` on preview. Verify `env-safety` → `writeBlocked:false` / `environment:production`.
   *Until this holds, every later step can be silently re-corrupted.*
2. Capture production evidence: `reconcile`, `sync-log?status=PENDING`, and a Mongo dump of the
   15 records above.
3. **P0-1, P0-3** — classify and remove only rows proven foreign.
4. **P0-6** — obtain the owner ruling on Customer Payable. **Blocking.**
5. **P0-4, P0-5** — recompute the ₹0-payable leads; enforce the `FN26` contract.
6. **P1-1** — add the 50 MAP-ONLY columns; schedule the 17 that need implementation.
7. **P1-2 … P1-6**, then P2, then P3.

---

# Go-live gate

| Gate | Status |
|---|---|
| All P0 resolved | ❌ 6 open (1 needs an owner decision) |
| Every operational column has a source of truth | ❌ 67 open (50 mapping, 17 implementation) |
| Production/preview isolation verified | ❌ unverified |
| Production Mongo ↔ Sheet reconcile clean | ❌ not run |
| Duplicate IDs resolved | ❌ 2 open |
| Orphan references resolved | ❌ Commercial Snapshot empty |
| Derived tabs refreshed | ❌ 47 stale, 29 with no rebuilder |
| Finance Register/Pending/Overdue reconcile | ✅ the three agree (file `55`) |
| Lifecycle passes | ✅ 214 harness checks + 54 offline tests green at `f92e1d2` |
| Sheet write test passes | ⚠️ not re-tested — read-only scope by instruction |
| No formulas damaged | ✅ 23 formula cells intact; protection verified in code |
| No production data deleted without classification | ✅ nothing deleted |

## Readiness: 🔴 RED

Unchanged from the reconciliation. The engine itself is sound — the commercial calculations
reconcile against the August circular, and the one figure that looked alarming (negative dealer
retention) is provably correct. What blocks go-live is **environment isolation, workbook
contamination, and one unresolved business question about who receives the insurance benefit**.
