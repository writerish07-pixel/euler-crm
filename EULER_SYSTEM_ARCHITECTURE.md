# Euler CRM — system architecture

Audit date: 18 Nov 2026. Baseline: `adef670` on `origin/main`.

## Runtime

| Layer | What it is |
|---|---|
| Frontend | React (Create React App) in `frontend/`. Routes are declared in `frontend/src/App.js`. |
| API | FastAPI in `backend/server.py`, plus `auth.py`, `workshop_api.py`. |
| Commercial rules | `backend/commercial.py`. Scheme month rows in `sept_2026_schemes.py`, `oct_2026_schemes.py`, `nov_2026_schemes.py`. |
| OEM | `backend/oem_sync.py`, `oem_catalog.py`, `coulson.py`, `oem_claims.py`, `oem_live_catalog.py`. |
| Data | MongoDB via Motor. Collections include leads, price_master, scheme_master, payments, finance, insurance, claims, deliveries, activities, audit_log, oem_sold, oem_cancelled_invoices. |
| Sheets | `backend/gsheets.py`. One-way sync. Disabled when credentials are absent. Tests must not write the live workbook. |
| WhatsApp | `backend/botspace.py`. |
| Calls | `backend/exotel.py`. |
| Deploy | Frontend: Cloudflare Workers (wrangler dry-run in `.github/workflows/cloudflare-validate.yml`) and the Render static site. API: Railway, Python 3.12 (`backend/.python-version` / requirements comment). |

Production data was not connected during this audit. No migration was run.

## Request path

Staff browser → React route → `/api/...` with JWT → FastAPI dependency (`current_user`, `owner_only`, `deal_desk_only`, and the role sets in `auth.py`) → handler in `server.py` or a satellite module → `commercial.py` for money → Mongo write → optional Google Sheet sync → JSON back to the drawer.

OEM path: saved Coulson session → invoice and sold pull → `oem_sold` / `oem_cancelled_invoices` → `apply_sold_vehicle_ids_to_leads` and `delink_cancelled_sold_invoices` → lead units.

## Dependency map (as implemented)

```
Lead
  → Booking (status, booking date, advance receipt)
  → Price Master (ex-showroom, family RTO/insurance defaults)
  → Scheme Master for the billed month
  → Payments
  → Customer outstanding
  → Finance file (when the receipt mode is finance)
  → Delivery checklist
  → Claims (company share) and Dealer Earnings (owner)

OEM Sold chassis
  → unit chassis / invoice / billed variant
  → scheme month (sold date)
  → claim match
  → Tally summary

Pack lead
  → units[] each with own price, scheme, payment, documents, delivery date
  → header totals are the order, not unit 1
```

Shared high-risk functions:

- `recompute_lead` and `_normalize_lead_units` in `server.py`. A field dropped here disappears on the next save. Confirmed-variant flags are copied on purpose (`_copy_oem_sku_answer`).
- `fill_lead_skus` / `fill_pack_unit_skus` in `oem_sync.py`. They write a chassis only from that chassis's invoice.
- `get_scheme_shares_for_lead`. Month tag must match. Last month does not leak.
- `default_rto_insurance_for_model`. New Price Master rows only. Existing typed RTO is kept.

## Roles at the edge

`EXTERNAL_ROLES` (`oem_finance`) is denied every authenticated route except an explicit allow-list, because most GET handlers only require a valid token.

Money posting is `MONEY_ROLES` (owner, showroom admin `tl`, accounts). Deal steps are `DEAL_DESK_ROLES`. Inventory sold/received ledgers are hidden from executive, team_lead, and showroom admin.

## What this audit did not map line by line

Background schedulers for WhatsApp morning/EOD and Exotel queues exist (pull requests 69, 102, 217–226). Their cron host is Railway, not a workflow file in this repo. The exact cron expression was not re-read in this pass.

`server.py` route inventory is larger than the sidebar. The routes listed in `frontend/src/App.js` (login through settings, including `/service` and `/oem-billing`) are the staff-facing map used here.
