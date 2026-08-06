# Final Phase — Euler CRM (Aug 2026)

**Source (Apps Script):** `C:\Users\hp\Desktop\final fix`  
**Portal (GitHub Pages):** `C:\Users\hp\Desktop\euler-crm-portal`  
**Remote:** https://github.com/writerish07-pixel/euler-crm-portal  
**Staff portal:** https://writerish07-pixel.github.io/euler-crm-portal/  
**Company share board:** https://writerish07-pixel.github.io/euler-crm-portal/share.html  
**Date:** 6 Aug 2026

---

## Goal of this phase

Close the dealership operating loop for live use:

1. Book without locking price → set price later  
2. Edit leads safely from the spreadsheet  
3. Settle finance & claims after close  
4. Split OEM claims by scheme component  
5. Share monthly bookings/retail with company (read-only)  
6. Fix payment ledger + outstanding gaps from slim booking  
7. Align dashboard / share board counts with real booked pipeline  

---

## 1. Process redesign (approved → implemented)

### Booking without price
| Before | After |
|--------|--------|
| Convert to Booking locked Price Master charges in one step | **Convert to Booking** = date, advance, executive, finance/exchange only |
| Hard to fix wrong price after booking | **CRM → Price Structure** (sheet + portal) sets Ex-showroom, Insurance, RTO, charges later |

**Key files:** `BookingService.gs`, `Code.gs`, portal `booking.js`, `price-structure.js`

### Edit Lead (spreadsheet only)
- **CRM → Edit Lead** — name, mobile, model, variant, flags, remarks, account status  
- **Not** on the web portal (by design)

**Key files:** `LeadService.gs`, `Code.gs`

### After Close
- Closed leads can still take **Finance receipt** and **Claim receipt**  
- Booking / payment / scheme / delivery still require **Active**

**Key files:** `LeadPickerService.gs` (`requireExistingLead_`), `FinanceService.gs`, `ClaimService.gs`

### Per-component claims
- Claim Register rebuild creates **one row per scheme component with company share**  
- Settle each component separately (own amount / UTR)  
- Columns: `Component`, `Component Key`, plus existing claim fields  

**Key files:** `CommercialSchemeService.gs`, `ClaimService.gs`, `Config.gs`  
**Portal:** Claims page (`claims.js` + shell nav)

---

## 2. Company share board (GitHub)

Read-only board for company people — **no staff CRM link**, no mobiles.

| Metric | Meaning |
|--------|---------|
| **Active bookings** | All leads with status **Booked**, not delivered |
| **New this month** | Booking date in current calendar month |
| **Retail** | Deliveries in current month |

**Backend:** `getShareDashboard_()` in `DashboardService.gs` · API action `getShareDashboard` in `WebApi.gs`  
**Frontend:** `share.html`, `assets/css/share.css`, `assets/js/pages/share-dashboard.js`  
**Auto-refresh:** every 3 minutes  

**Share URL:**  
https://writerish07-pixel.github.io/euler-crm-portal/share.html

---

## 3. Dashboard booking count fix

**Problem:** Sheet Dashboard and share board showed **2** while Lead Register had **3 Booked**.  
**Cause:** Counts used **booking date in current month only**. Roshan (booked Jul 2026) was excluded.

**Fix:**
- Spreadsheet Dashboard **Monthly Bookings** KPI → **active Booked** count  
- Conversion % still uses **new bookings this month ÷ monthly leads**  
- Share board KPI → **Active bookings** + hint “N new in [month]”  
- Drill-down sheet renamed conceptually to **Active Bookings**

**Key files:** `DashboardService.gs`, portal `share-dashboard.js`, `dashboard.js`

---

## 4. Payment Ledger + Outstanding (slim booking bug)

**Problem:**
- Booking amount received but **Payment Ledger empty**  
- Leads 2 & 3 showed **Outstanding ₹0** (Lead 1 OK after price was set)

**Cause:** After slim booking, Customer Payable is **₹0** until Price Structure.  
`validatePaymentAmount_` rejected the advance (`exceeds Customer Payable ₹0`). Error was logged and swallowed → no ledger row. Outstanding stayed 0 without a vehicle price.

**Fix:**
| Change | File |
|--------|------|
| Allow **provisional** payment when payable is ₹0 | `BusinessRulesService.gs` |
| Booking advance passes `allowProvisional: true` | `BookingService.gs`, `PaymentService.gs` |
| Deferred sync runs Price Master **estimate** after booking | `BookingService.gs` → `runEstimate: true` |
| Menu **Repair Missing Booking Payments** (backfill + OS refresh) | `PaymentService.gs`, `Code.gs` |

**Operator steps after deploy:**
1. Paste updated `.gs` files → Save → **Deploy → New version**  
2. **CRM → Reports** (or Admin) → **Repair Missing Booking Payments**  
3. For each booked lead without price: **CRM → Price Structure**  

---

## 5. OEM Extra Support (earlier in phase)

Separated OEM Extra Support from scheme bleed; portal `saveScheme` hardened.  
Requires deployed `CommercialEngineService.gs`, `ExtraIncomeService.gs`, `LeadService.gs`, `WebApi.gs`.

---

## 6. Portal restore

Local folder was deleted accidentally and **re-cloned** from GitHub (6 Aug 2026):

```text
C:\Users\hp\Desktop\euler-crm-portal
```

Latest known main: includes share board, active bookings UI, staff dashboard Active Bookings card.  
`config.js` already points at the Apps Script `/exec` Web App URL.

---

## Recommended operating flow (final)

```text
New Lead
  → Convert to Booking          (advance → Payment Ledger)
  → Price Structure             (payable + outstanding)
  → Scheme Update               (offers / OEM extra support)
  → Add Payment                 (as needed)
  → Finance / Claims            (as needed; claims after close OK)
  → Mark Delivered
  → Close Lead
```

Company visibility anytime via **share board** (active bookings + MTD retail).

---

## Deploy checklist (must do for live sheet)

### Apps Script (Euler Master)
Copy from `final fix`, **Save**, then **Deploy → Manage deployments → Edit → New version**:

| Priority | Files |
|----------|--------|
| High | `DashboardService.gs`, `WebApi.gs` |
| High | `BusinessRulesService.gs`, `PaymentService.gs`, `BookingService.gs`, `Code.gs` |
| If not yet | `LeadService.gs`, `LeadPickerService.gs`, `CommercialSchemeService.gs`, `ClaimService.gs`, `Config.gs`, `DataStore.gs`, `FinanceService.gs` |

Then run: **Repair Missing Booking Payments** once.

### GitHub portal
Already on Pages if `euler-crm-portal` was pushed. After local edits:

```powershell
cd C:\Users\hp\Desktop\euler-crm-portal
git status
git add -A
git commit -m "Your message"
git push
```

Hard-refresh portal / share board after ~1–2 minutes.

---

## Performance note (final phase)

Publishing the **UI** as an Apps Script HtmlService web app does **not** make the portal fast.  
GitHub only hosts static files; all slowness is **Apps Script + spreadsheet reads** (`loadCrmStore_`).  

Keep: GitHub Pages UI + Apps Script Web App API.  
Next speed work (optional): lighter API endpoints, less `force` store reload, real DB later.

---

## Done vs still operator-side

| Done in code | You must do on sheet |
|--------------|----------------------|
| Slim booking + Price Structure | Paste `.gs` + new Web App version |
| Edit Lead / Claims / Close rules | Rebuild Claim Register once after claim deploy |
| Share board + active booking counts | Repair Missing Booking Payments |
| Provisional booking advance | Set Price Structure on leads 2 & 3 (etc.) |
| Portal restored from GitHub | Hard-refresh Pages URLs |

---

## Quick links

| Item | Location |
|------|----------|
| Apps Script source | `C:\Users\hp\Desktop\final fix` |
| Portal source | `C:\Users\hp\Desktop\euler-crm-portal` |
| Earlier Jul MR | `MR.md` |
| Knowledge base | `CRM_KB.md` |
| Staff CRM | https://writerish07-pixel.github.io/euler-crm-portal/ |
| Share board | https://writerish07-pixel.github.io/euler-crm-portal/share.html |
