# Deploy Euler CRM as a phone web app (GitHub Pages)

Staff open one URL on phone or laptop — no installing HTML files.

## Before you deploy

1. Apps Script Web App must include `WebApi.gs` (`doGet` / `doPost`).
2. Deploy → **Execute as: Me** · **Who has access: Anyone**
3. Put the `/exec` URL in `assets/js/config.js` → `API_BASE_URL` (already set if working locally).

## Deploy on GitHub (free)

### A. Create repo + upload

1. Go to [https://github.com/new](https://github.com/new)
2. Repository name: `euler-crm-portal` (public is fine for GitHub Pages free tier)
3. **Do not** add README if you will push this folder
4. On your PC, open PowerShell:

```powershell
cd C:\Users\hp\Desktop\euler-crm-portal
git init
git add .
git commit -m "Euler Motors CRM web portal"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/euler-crm-portal.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

### B. Turn on Pages

1. Repo → **Settings** → **Pages**
2. Source: **Deploy from a branch**
3. Branch: **main** / folder: **/ (root)**
4. Save

After 1–2 minutes your app URL is:

```
https://YOUR_USERNAME.github.io/euler-crm-portal/
```

### Company share board (bookings + retail)

Separate read-only page for company people (no CRM login forms):

```
https://YOUR_USERNAME.github.io/euler-crm-portal/share.html
```

Shows **current-month bookings**, **retail (deliveries)**, today counts, and lists. No customer mobiles. Auto-refreshes every 3 minutes.

Requires Apps Script Web App with `getShareDashboard` (in `DashboardService.gs` + `WebApi.gs`).

### C. Share with staff

Send that link (WhatsApp / email). On phone:

- Open in Chrome / Safari
- Optional: **Add to Home Screen** → opens like an app

### D. Sheet menu

In CRM Settings, set `webPortalUrl` to the GitHub Pages URL above.

## Phone tips

- Use the **☰** menu on small screens
- Forms use larger tap targets
- Keep phone on internet (data talks to Apps Script)

## Updates later

Change files on your PC, then:

```powershell
cd C:\Users\hp\Desktop\euler-crm-portal
git add .
git commit -m "Update CRM portal"
git push
```

GitHub Pages refreshes in about a minute.
