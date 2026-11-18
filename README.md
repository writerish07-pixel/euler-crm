# Euler Motors CRM

The live product is the React app in `frontend/` and the FastAPI service in `backend/`. Staff open the deployed web app. The HTML files and Apps Script portal in this repository are historical.

## Staff link (after GitHub Pages)

```
https://YOUR_USERNAME.github.io/euler-crm-portal/
```

## Company share board (bookings + retail)

```
https://YOUR_USERNAME.github.io/euler-crm-portal/share.html
```

Read-only: MTD bookings, MTD retail (deliveries), today counts. Safe to WhatsApp to company people.

See **[DEPLOY-GITHUB.md](DEPLOY-GITHUB.md)** for step-by-step deploy.

## Local

Open `index.html` (or serve the folder). Set `API_BASE_URL` in `assets/js/config.js` to your Apps Script `/exec` URL.

## Architecture

```
Phone / Laptop  →  GitHub Pages (this HTML app)  →  Apps Script API  →  Spreadsheet
```

Frontend is presentation only. Business rules stay in Apps Script.
