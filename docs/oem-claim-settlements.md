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

**These must never be merged.** One Coulson debit note can carry line items for several
leads, and its claim types (`"Referral Commission"`) share no vocabulary with the
register's component keys. Writing Coulson statuses into `db.claims.claimStatus` would
corrupt every report that sums `eligibleClaim - receivedAmount`. A test pins this
(`test_claim_sync_never_writes_to_the_scheme_claim_register`).

The two are compared on **Claim Reconciliation** (`/claim-reconciliation`, owner-only).

## Endpoints used on Euler's side

All on `https://coulson.eulerlogistics.com/api/v1`, Bearer auth with the same pasted
session the yard sync uses. No second login is ever made.

| Call | Purpose |
|---|---|
| `GET debit-note?limit=&offset=` | The claim list. `{success, data[], extras.total_count}` — same envelope as `vehicle-inventory/transfer` |
| `GET journey?debit_note_id=<uuid>` | `{header, line_items[], timeline{}}`. **Chassis and source invoice exist only here** |
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
