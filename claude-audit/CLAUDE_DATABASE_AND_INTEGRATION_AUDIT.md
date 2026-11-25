# Database, API and Integration Audit (Claude)

Production MongoDB was **not** accessed. Everything below comes from code and an in-memory MongoDB (`mongomock`) used by the app's own test approach. Statements about production data are therefore risks, not observations.

## 1. Data model (as implemented)

MongoDB via Motor; no ORM, no schema validation, no migration framework. Main collections: `leads` (one large document per customer file, including `units[]` for packs and many derived money fields), `payments`, `bookings`, `deliveries`, `finance`, `insurance`, `claims`, `activities`, `dealer_earnings`, `quotations`, `price_master`, `scheme_master`, `incentive_*`, `users`, `audit_log`, `edit_log`, `lead_documents`, `whatsapp_*`, `oem_sold`, `oem_invoices`, `oem_cancelled_invoices`, `oem_inventory*`, `oem_chassis_ledger`, `counters`, `system`, `workshop_*`.

Derived values (customer payable, outstanding, earnings, scheme allocation summary) are **stored on the lead** and rebuilt by `recompute_lead`. The stored value is only as fresh as the last recompute; boot jobs and many endpoints call it.

## 2. Indexes and constraints

| Collection | Unique constraints present | Missing (recommended after a production duplicate census) |
|---|---|---|
| users | `email` | `loginIdNorm` (login lookup uniqueness is app-enforced) |
| finance | `leadId` (partial), `fileNumber` (partial) | — |
| leads | **none** (`leadId`, `mobile`, `currentStatus`, `bookingDate` non-unique) | `leadId` unique; partial unique on live `chassisNumber`, `invoiceNumber`, `numberPlate` |
| payments | none (`leadId` index only) | `receiptNumber` unique |
| claims | none | `(leadId, componentKey, unitSno)` unique |
| oem_sold | none (`chassis`, `mobile`) | `chassis` unique is assumed by upsert logic |
| incentive_register, masters_list, insurance_agents, staff, whatsapp_threads, cancel_reasons, oem_chassis_ledger, inventory_checks | unique keys present | — |

Consequence: every "no duplicate" rule in the CRM is application logic (read, then write). Claude's in-process concurrency probes did not break these rules, but a multi-worker deployment can (CLD-12). The production worker/replica count is configured outside the repository and was not verifiable.

## 3. Write-path integrity

| Path | Pattern | Risk |
|---|---|---|
| Customer receipt | read last receipt → insert → `recompute_lead` | Dedupe/over-payment race across workers (theoretical) |
| Financer receipt | read file → compute → `$set` total + `$push` receipt | Lost update across workers; totals can diverge from receipt history |
| Claim receipt | read claim → compute → `$set receivedAmount` + `$push` | No dedupe, no cap (REPRODUCED, CLD-06); lost update (theoretical) |
| Payment insert failure | deletes the just-created empty finance file | Good compensating action; no transactions used anywhere |
| Lead purge | `delete_many` across 13 collections, no audit | Data loss (REPRODUCED, CLD-01) |
| OEM delink | `delete_many` on `oem_sold` (stale rows, cancelled chassis) | Rebill cleared (CLD-05) |
| Boot maintenance | 13 heal/backfill jobs on every start | Unaudited mutations (CLD-11) |

No multi-document transactions are used. A failure between `payments.insert_one` and `recompute_lead` leaves stored lead totals stale until the next recompute (self-healing on next save, but dashboards read the stored value).

## 4. Historical-record compatibility

- Legacy leads are deliberately "grandfathered": scheme entitlement components are not auto-passed unless `schemeAllocationV2` is set, and dealer-funded benefit is not deducted unless an authoritative allocation exists. This avoids silent historical rewrites, but means **old and new leads are computed under different rules**; reports mix both.
- Cursor's AUD-001 changes how existing `oem_sold` rows are treated on the next sync (deletion of stale rows). No migration was run by Cursor; the effect happens at runtime on production when the code deploys.
- `schemeAllocation` (decision map) and `schemeAllocationSummary` (engine output) were split to stop summaries being mistaken for decisions; `_explicit_allocation` ignores summary-shaped objects. Correct.

## 5. API contract and validation

- Pydantic models on request bodies; `num()` rejects NaN/Infinity; negative payment amounts rejected (PR #4).
- Errors are FastAPI `HTTPException` with human text; frontend shows them. Success responses return the saved document (`clean(doc)`), so the UI reflects persisted state.
- Authorization: global `current_user` dependency on the `/api` router; role checks per route. Claude's scan of 123 mutating routes found none without a role or visibility check (19 flagged by pattern were each checked manually).
- Public routes: `/health`, `/`, `/api/ping`, `/api/share/dashboard` (**PII leak, CLD-02**), BotSpace webhook/cron, Exotel audio/voice/gather/recorded/status/cron (**fail-open, CLD-07**).
- Frontend/backend mismatch checks: owner-only keys are stripped at the top level of lead responses but not inside `schemeAllocationSummary` (CLD-09). The frontend treats an HTML body from the API as an error (`ERR_BAD_PAYLOAD`), which prevents "false success" on proxy pages.

## 6. External integrations

| Integration | Module | Direction | Observations |
|---|---|---|---|
| Google Sheets | `gsheets.py` | One-way CRM → sheet | Disabled without credentials; tests mock it via `conftest.py` autouse. Claude's runs had no credentials in the environment. |
| Coulson (Euler OEM dealer portal) | `coulson.py`, `oem_sync.py`, `oem_claims.py`, `oem_live_catalog.py` | Pull | Stores a pasted session/password in Mongo settings (owner-only). Not exercised (no credentials). Sync writes `oem_sold`, Price Master and Scheme Master rows. |
| Exotel | `exotel.py` | Outbound calls + inbound webhooks | Fail-open webhooks (CLD-07). |
| BotSpace WhatsApp | `botspace.py` | Outbound + webhook + cron | Webhook secret optional; cron requires a token. |
| Gmail (workshop) | `workshop_gmail.py` | Pull | Not exercised. |
| Web Push | `web_push.py` | Outbound | Optional. |
| Tally | `tally_pack.py` | File export/check | Tests pass in full suite (see test report). |

None of the integrations was called live during this audit.

## 7. Secrets and configuration

- No API keys or service-account JSON committed (`frontend/.env.*` contain only the public API URL).
- Committed: the default password `euler@123` and demo logins (`memory/test_credentials.md`, `auth.py`) — CLD-03.
- `JWT_SECRET` required from environment (no default) — good.
- `OWNER_PASSWORD` falls back to `euler@123` — CLD-03.
- CORS `*` with bearer tokens — CLD-15.
