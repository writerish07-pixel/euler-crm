# Euler Motors CRM — Web Portal

Premium HTML frontend that **replaces Google Sheet menus/dialogs only**.

Business logic stays in **Google Apps Script**. The spreadsheet remains the database until you migrate.

```
Browser  →  REST JSON (WebApi.gs)  →  Existing .gs services  →  Spreadsheet
```

Tomorrow you can swap Apps Script + Sheets for FastAPI + PostgreSQL **without changing this frontend**, as long as the API contract stays the same.

## Stack

- HTML5 / CSS3 / Tailwind CDN
- Vanilla JavaScript (modular)
- Chart.js (dashboard / reports)
- No React / Vue / Angular / Next.js

## One file for staff

Staff only need to open **`index.html`**.

```
euler-crm-portal/
  index.html          ← OPEN THIS (master app)
  assets/             ← keep beside index.html
  README.md
```

All screens (Dashboard, Booking, Scheme, Payment, …) open inside that one page via the sidebar.

Share the whole **`euler-crm-portal`** folder (zip it). Do not send only the HTML without `assets`.

Bookmark examples:
- `index.html#/dashboard`
- `index.html#/booking`
- `index.html#/scheme`

Old `booking.html` etc. still work — they redirect into the master app.

---


```
euler-crm-portal/
  index.html
  dashboard.html
  new-lead.html … settings.html
  assets/css/app.css
  assets/js/config.js          ← set API_BASE_URL here
  assets/js/api/api.js
  assets/js/components/
  assets/js/pages/
```

## Fix: “Failed to fetch” / API error

Your current Web App URL responds with:

**`Script function not found: doGet`**

That means the **deployed** Apps Script project does **not** include `WebApi.gs` yet (or an old deployment is still live).

### Fix in Apps Script (required)

1. Open the spreadsheet → **Extensions → Apps Script**
2. Create a new file named `WebApi.gs`
3. Paste the full contents of `Desktop/final fix/WebApi.gs`
4. **Deploy → Manage deployments → Edit (pencil)**
   - Version: **New version**
   - Execute as: **Me**
   - Who has access: **Anyone** (needed for browser `fetch`)
5. Click **Deploy**, copy the `/exec` URL
6. Put that URL in `assets/js/config.js` → `API_BASE_URL`
7. Test in browser: open  
   `YOUR_EXEC_URL?action=ping`  
   You should see JSON like `{ "ok": true, "data": { "pong": true, ... } }`  
   If you still see HTML “Script function not found”, the new version was not selected.

### Fix how you open the portal

Do **not** double-click `dashboard.html` (`file://` is blocked from calling the API).

```bash
cd C:\Users\hp\Desktop\euler-crm-portal
npx --yes serve .
```

Then open the printed `http://localhost:…` URL.

---


### 1. Apps Script Web App

1. Copy `final fix/WebApi.gs` into the Apps Script project (same project as the CRM).
2. Ensure `Code.gs` has menu item **Open Web Portal** (`menuOpenWebPortal`).
3. **Deploy → New deployment → Web app**
   - Execute as: **Me**
   - Who has access: your Google Workspace users (or “Anyone with Google account”)
4. Copy the `/exec` URL.

### 2. Portal config

Edit `assets/js/config.js`:

```js
API_BASE_URL: 'https://script.google.com/macros/s/XXXX/exec',
```

### 3. Host the portal

Options:

- Open `index.html` locally (file://) — may hit CORS limits; prefer hosting
- GitHub Pages / Netlify / Firebase Hosting / IIS / any static host
- Or serve with: `npx serve .`

### 4. Sheet menu link

In CRM Settings (or portal Settings page), set `webPortalUrl` to your hosted portal URL.  
Sheet menu **Open Web Portal** uses that value.

## API contract

```http
POST /exec
Content-Type: application/json

{ "action": "saveLead", "payload": { ... } }
```

```json
{ "ok": true, "data": { ... } }
{ "ok": false, "error": { "message": "...", "code": "..." } }
```

Actions map 1:1 to existing dialog handlers (`createNewLeadFromDialog`, `saveBookingFromDialog`, …). **No commercial math in the browser.**

## Demo mode

If `API_BASE_URL` is empty and `ALLOW_DEMO` is true, pages load with empty/demo data so UI can be reviewed offline.

## Security

- Never put spreadsheet IDs in the frontend
- Never trust client amounts for payable / scheme / earnings
- Server re-validates every write

## Keyboard

- `Ctrl+K` — focus global search
