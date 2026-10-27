# Euler CRM audit

Started 27 October 2026 (IST). This folder is the working record for the enterprise audit. It is a baseline and a plan. It is not a claim that the CRM is enterprise-ready, and it is not a rebuild.

The live application is the React app in `frontend/` talking to the FastAPI app in `backend/`. MongoDB is the database. Coulson is the OEM app. Google Sheets is a one-way register mirror.

## How to read this

| Document | What it is |
|---|---|
| [00-progress.md](00-progress.md) | What is done, what is next, and how to resume |
| [01-baseline-and-plan.md](01-baseline-and-plan.md) | Architecture, checks actually run, and the phased plan |
| [FINDINGS.md](FINDINGS.md) | The findings register. Plain English. One row per item |

Older notes that are **not** this audit:

- `AUDIT_REPORT_2026-10-16.md` — previous code audit. Some of its critical items are still present. Others were not re-checked on 27 October.
- `frontend/public/docs/GO_LIVE_CHECKLIST.md` — June 2026 checklist. It still describes only Owner and Executive. The app now has more roles. Do not treat that checklist as current.
- `memory/PRD.md` — June 2026 migration notes. Later conversations changed several of those decisions (login was added; the share board does show customer names).
- `README.md` at the repo root — still describes the old Apps Script portal in `assets/js`. Staff do not use that portal.

## Rule for this audit

No business calculation, permission, or deletion is changed until the finding is verified and, where money, privacy, or a business rule is involved, the owner has agreed. Phase 1 does not change application code.
