# Euler CRM — Test Credentials

**Authentication:** JWT email+password with roles (Owner / Executive). Bearer token in `Authorization` header, stored in localStorage on the frontend.

## Accounts (seeded on backend startup)
| Role | Email | Password |
|------|-------|----------|
| Owner | `owner@euler.com` | `euler@123` |
| Executive | `executive@euler.com` | `euler@123` |

- **Owner** sees everything incl. **Dealer Earnings** (owner-only route `/dealer-earnings`, backend `GET /api/dealer-earnings` requires owner) and **Settings → User Accounts**.
- **Executive** sees everything EXCEPT Dealer Earnings and User management (gets 403 / redirected).
- Owner can create/delete users via Settings page (`POST /api/auth/users`).

## Public (no login)
- `/share` → Company Share Board (read-only monthly bookings/retail, no customer or staff data). Backend `GET /api/share/dashboard` is public.

## Integrations
- Google Sheets one-way sync: appends new Lead/Booking/Payment/Delivery/Claim to the Euler Master sheet. Activates when `/app/backend/gsheets_credentials.json` (Service Account key) is present and the sheet (`GSHEET_ID` in backend/.env) is shared with the service account email. Currently NOT configured (graceful no-op). Status: `GET /api/integrations/gsheets`.
- Excel export: `GET /api/export` → one .xlsx with a sheet per module.

## Seed data (migrated from Euler Master.xlsx)
10 leads (LD26000001–10; 1-3 Booked), 69 price rows, 33 scheme rows, 4 incentives, 3 bookings/payments/dealer-earnings.
