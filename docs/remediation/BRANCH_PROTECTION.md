# Branch protection

Status: BLOCKED. This change cannot mark checks required. A repository admin has to do that on `main`.

Mark these checks required:

- backend-full
- critical-regression
- frontend-tests
- wrangler-dry-run

Also require branches to be up to date before merge.

The Cloudflare Workers Builds check that starts and finishes in the same second is an external miss. `wrangler-dry-run` is the build check to require. `CI=false` on the frontend build in `cloudflare-validate.yml` was left as-is.
