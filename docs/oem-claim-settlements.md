# OEM Claim Settlements (Coulson "debit notes")

Euler's claim workflow, mirrored read-only into the CRM and tied to leads by chassis.

## Two registers, deliberately kept apart

| | Scheme Claim Register (`/claims`) | OEM Claim Settlements (`/oem-claims`) |
|---|---|---|
| Collection | `db.claims` | `db.oem_portal_claims` |
| Whose record | The dealer's own | Euler's |
| What it says | What Scheme Master says Euler owes, per lead per component | What was actually filed with Euler, and how far it has moved |
| Keyed on | `(leadId, componentKey)` | Coulson debit-note id, linked to leads by chassis |
| Feeds | Owner Commercial, Dealer Earnings, OEM Claim Dashboard | Nothing financial — it is a mirror |

**These must never be merged on money.** One Coulson debit note can carry line items for several
leads, and its claim types (`"Referral Commission"`) share no vocabulary with the
register's component keys. Writing Coulson **amounts** into `db.claims` would
corrupt every report that sums `eligibleClaim - receivedAmount`. A test pins this
(`test_claim_sync_never_writes_money_into_the_scheme_claim_register`).

Filing **status, dates and claim reference** do follow Euler: when a register row
matches a live debit note, `claimStatus` becomes Submitted / Approved / Rejected,
`claimReference` takes the Coulson number, and empty submitted/approved dates fill
from the note. `eligibleClaim`, `claimAmount` and `receivedAmount` stay the dealer's.

The two are compared in four places:

- **In Euler** on every Scheme Claim Register row (chassis + invoice columns join
  that row to `/oem-claims?chassis=` / `?invoice=` / `?q=<claim number>`)
- **In Euler but not in this register** below the Scheme Claim Register
- **In this app** on every OEM Claim Settlements row (`registerMatch`: green in
  the register, violet filed-in-Euler-only, grey unmatched lead)
- the lead-level **Claim Reconciliation** report (`/claim-reconciliation`, owner-only)

Join key is the lead's **chassis**, then **source invoice**, then `leadId` if the
sync already stamped it. Opening the Scheme Claim Register **relinks** stored Euler
lines against current lead chassis/invoice, so a debit note mirrored before those
ids landed on the lead still reads as Filed (not Not claimed). Auto-generated
Coulson lines such as `Insurance Benefits Up to for invoice AF-122-I26270162` map
to `insuranceBenefit`.

## The two-way cross-check

Each register row carries an `oemMatch` state. **The mirror never writes money into
`db.claims`.** It does stamp filing status / dates / the Coulson claim number so the
Scheme Claim Register STATUS column matches the OEM app.

| State | Colour | Means | Do |
|---|---|---|---|
| `accepted` | green | Euler generated a credit note / sales invoice, or settled | nothing |
| `filed` | blue | In Euler's ladder | wait, or chase on stage-days |
| `resubmitted` | sky | Was rejected, a newer claim exists for that chassis | nothing |
| `unmapped` | amber | The lead has claims, none reads as this component | **look** — not a gap |
| `rejected` | rose | Rejected and nothing refiled | **refile** |
| `not_filed` | red | Nothing filed for this lead | **raise the claim** |
| `not_applicable` | — | Manual / executive-incentive claim, not filed as a scheme line | nothing |

`unmapped` exists because Euler describes a claim in prose ("Referral Commission for
invoice AF-122-…") and types many of them `"Scheme Claim"`, while the register
speaks component keys. `CLAIM_TYPE_KEYS` maps Coulson's own chips first
(`Additional Support`, `Dealer Incentive` / Support Scheme (BTL) → OEM Extra Support)
so a line whose description still says "Insurance Benefits Up to…" is not stolen by
the word "insurance". `COMPONENT_PHRASES` then maps Scheme Claim prose, most specific
first. **A mapping miss must never render as "not claimed"** — that would send
the money desk chasing money already sitting in Euler's queue. A test pins it.

**OEM Extra Support is a staff-typed side ledger, not a Scheme Master component.**
Coulson files it as **Additional Support**, **Dealer Incentive**, or Support Scheme
(BTL) — or as prose that names extra/additional support (`CLAIM_TYPE_KEYS` first, so
a line whose description still says “Insurance Benefits Up to…” is not stolen).
A Scheme Claim for Insurance / Loyalty / Referral on the same vehicle is **not**
that filing. Extra Support then reads **Not claimed** until the OEM app actually
has an Extra Support line. Other scheme components stay per-component the same way.

The reverse colour on OEM Claim Settlements is `registerMatch`:

| State | Colour | Means |
|---|---|---|
| `in_register` | green | Chassis/invoice joined a scheme-register row |
| `missing_register` | violet | Euler filed it; this register has no row |
| `unmapped` | amber | Lead matched, wording did not map to a component |
| `unknown_lead` | grey | No chassis or invoice matched a lead |

The reverse direction is also `GET /claims/oem-only`: claim lines with no register row, each
tagged `unknown_lead` (chassis never matched a lead), `unmapped_component`, or
`missing_register_row`. Cancelled claims are excluded — nobody should chase those.

## Rejections and resubmission

Euler does not reopen a rejected debit note. A resubmission is a **new note for the same
chassis**, so `annotate_resubmissions` looks for a later, non-cancelled claim on that
chassis after each rejection:

- found → `resubmittedBy` is set, and the register reads `resubmitted`
- not found → `needsResubmission`, surfaced on both pages as money that quietly stopped
  being chased

A live claim always outranks an older rejection on the same component, so refiling makes
the register read `filed` again rather than staying red.

## Backlinks

Every lead id on the three claim pages opens the same lead 360 drawer the Lead Register
opens (`components/LeadLink.js`), so the claim desk never has to go and search for the
file by hand. The scheme drawer (and the delivery tab) also show Euler's claims next to
the register rows they created, with jumps to both `/claims?leadId=` and `/oem-claims`.
Claim numbers, chassis and invoice on the Scheme Claim Register are links into the OEM
tab; the OEM tab links back.

## Endpoints used on Euler's side

All on `https://coulson.eulerlogistics.com/api/v1`, Bearer auth with the same pasted
session the yard sync uses. No second login is ever made.

| Call | Purpose |
|---|---|
| `GET debit-note?limit=&offset=` | The claim list. `{success, data[], extras.total_count}` — same envelope as `vehicle-inventory/transfer` |
| `GET debit-note/journey?debit_note_id=<uuid>` | `{header, line_items[], timeline{}}`. **This is the path the dealer SPA uses** (`getDebitNoteDetails`). Chassis and source invoice exist only on those line items. A bare `GET journey` 404s / returns no lines, which is why OEM Claim Settlements stayed on "Not pulled — sync again". Fallbacks: `GET journey?debit_note_id=` / `?id=` and `GET debit-note/{id}`. Envelopes unwrap `{success, data: {header, line_items, timeline}}`. |
| `GET status-counts?showroom_id=` | The eleven bucket totals, pre-aggregated |
| `GET allowed-showrooms` | Showroom scoping |

## Completeness: why a plain sweep is not trusted

Their dealer UI ships a default status filter. We never confirmed whether the API
applies one too, and a mirror holding 27 of 129 claims is worse than no mirror — it
looks like an answer.

So `fetch_all_claims` sweeps unfiltered, checks the result against `status-counts`, and
walks the eleven buckets when the sweep comes up short. Either way the sync records
`claimsMirrored`, `claimsExpected`, `claimsFetchMode` and `claimsIncomplete`, and both
Settings and the OEM Claims page show a red banner when the mirror is short.

## Two dates, 5½ hours apart

Coulson returns the same instant in two formats and two zones:

```
list    "_created_at": "2 Sep 2026 13:34:38"    <- IST wall clock
detail   "created_at": "2026-09-02 08:04:38"    <- UTC
```

`parse_list_datetime` and `parse_detail_datetime` handle them separately. Reading one
with the other's rule shifts every ageing figure by a day. (Coulson's own detail screen
renders the UTC value unconverted, so their UI shows "8:04 am" for a 1:34 pm claim.)

## Linking to leads

1. **Chassis** — normalised via `oem_sync._norm_chassis`, matched against
   `leads.chassisNumber`. One-to-one with the vehicle, already unique across live leads.
2. **Source invoice** — fallback when the line has no chassis.

A line matching on chassis but disagreeing on invoice is linked **and flagged**
(`invoiceMismatch`), surfaced under "Invoice disagreements". Unmatched claims are kept
and listed under "Not linked", never dropped.

## Ledger rules

- **Upsert only.** A claim that disappears from Coulson is marked `missingFromOem`,
  never deleted — same rule the Scheme Claim Register follows for money records.
- **Detail is re-fetched only when it can have changed** (first sight, or Euler moved
  the status or the approved amount), keeping steady state at a couple of calls per sync.
- **Customer photographs are not mirrored.** Line items carry `documents[]` with S3
  URLs to customer WhatsApp images on an open bucket; only `documentCount` is stored.
  The claim PDF (`debit_note_s3_link`) is a business document and is kept.

## Google Sheet (Scheme Claim Register)

Opening the register or syncing claims stamps filing onto `db.claims`, then upserts
the Scheme Claim Register tab. Settings → **Add Scheme Claim Euler columns** (and
Backfill) append, never rename:

- Chassis Number, Invoice Number
- In Euler (`oemMatchState`), Euler Status, Euler Stage
- Claim Reference Number (already on the tab) receives the Coulson debit-note number
- Claim Status / Submitted / Approved dates follow Euler as above

OEM Extra Support Register also receives chassis / invoice / claim reference and
the stamped status. Money columns are unchanged.

## Access

`/oem-claims` and the sync are money-desk (owner, TL, accounts). `/claim-reconciliation`
is owner-only. The external `oem_finance` role reaches neither — it stays allowlisted to
its single report.

## Cadence

Claims ride the existing 15-minute Coulson loop, in their own `try` so a claim-side
failure can never stop the yard pull that Price Master and delivery depend on. Owners
can force a pull from **OEM Claim Settlements → Sync from Euler**.

## Not built (deliberately)

Raising or approving a claim from the CRM. Coulson has a Create button and the API
presumably accepts writes, but that needs write permissions, an approval path and a
liability discussion. This integration is read-only.
