# Deploy on Render (SPA refresh / deep links)

Euler CRM is a React SPA with client-side routes (`/leads`, `/bookings`, …).

## Why refresh works on `/` but not on `/leads`

- Opening `/` loads `index.html`; React Router then changes the URL in the browser **without** asking Render for a new file.
- Refreshing `/leads` asks Render for a real file at `/leads`. That file does not exist, so Render returns plain **Not Found** unless a **rewrite** serves `index.html` for unknown paths.

`frontend/public/_redirects` is a Netlify/Cloudflare Pages convention. **Render ignores it.**

## Fix (about 30 seconds) — do this on the live static site

1. Open [Render Dashboard](https://dashboard.render.com) → static site **euler-crm**.
2. **Redirects/Rewrites** → **Add Rule**:
   - **Source:** `/*`
   - **Destination:** `/index.html`
   - **Action:** **Rewrite** (not Redirect)
3. Save. No redeploy required.

Then hard-refresh `https://euler-crm.onrender.com/leads` — the app should load.

## Blueprint (`render.yaml`)

The same rule is already declared under `routes` for Blueprint-managed services. If the site was created manually in the Dashboard, Blueprint routes are **not** applied until the service is linked to this Blueprint (or you add the rule above by hand).

## Check

```bash
curl -sI https://euler-crm.onrender.com/leads | head -5
# Expect: HTTP/2 200  and content-type: text/html
# Broken: HTTP/2 404  and content-type: text/plain
```
