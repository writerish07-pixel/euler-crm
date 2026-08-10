# Cloudflare Workers deploy (euler-crm)

GitHub check **Workers Builds: euler-crm** is the Cloudflare Git integration.
It has been failing on every commit (including long before the scheme PRs).

## What this repo expects

| Setting | Repo root | If Root Directory = `frontend` |
|---|---|---|
| Config file | `wrangler.jsonc` | `frontend/wrangler.toml` |
| Build command | `npm run build` | `yarn build` or `npm run build` |
| Deploy command | `npx wrangler deploy` | `npx wrangler deploy` |
| Assets | `frontend/build` | `build` |
| Worker name | `euler-crm` | `euler-crm` |

`frontend/build/` is gitignored — the **build command must run** before deploy.

## Dashboard checklist

1. Workers → **euler-crm** → Settings → Build  
2. Open the latest failed build → copy the error log  
3. Confirm build/deploy commands match the table above  
4. Branch control: production branch = `main`  
5. If the log says the build token is stale, create a new API token and select it  

## Render API (separate)

Static frontend on Render already serves the new Scheme UI.
`https://euler-crm-api.onrender.com` OpenAPI still lacks `schemeComponentsUsed`
until **euler-crm-api** is manually redeployed from `main`.
