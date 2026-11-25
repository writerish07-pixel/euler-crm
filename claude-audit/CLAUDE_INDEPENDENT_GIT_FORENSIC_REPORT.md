# Independent Git Forensic Report (Claude)

## 1. Scope and method

- The session clone was **shallow** (131 commits). Claude ran `git fetch --unshallow` and fetched all remote heads (read-only for the repository: no branch, ref on GitHub, or working-tree file was changed). Full history: **752 commits on `origin/main`**, 783 across all refs, 263 remote branches, **no tags or releases**.
- Commands: `git log`, `git cherry` (patch-equivalence), `git log -S` (pickaxe), `git log --diff-filter=D`, per-commit assertion add/remove counts, GitHub Actions run list and PR #293/#294 check runs via the GitHub API (read-only).
- Limits: PR review threads were read only for #294. Production deploy history (Railway/Render/Cloudflare) is outside Git and was not inspected.

## 2. Repository facts

| Item | Value |
|---|---|
| First commit | `4c8b2e6` 28 Jul 2026 "Euler Motors CRM portal — ready for GitHub Pages" |
| Head of `main` | `fbb0e21` 18 Nov 2026 — merge of PR #293 (Cursor audit) |
| Commits by author on `main` | Cursor Agent 340, writerish07-pixel 295 (mostly merge commits), Claude 66, emergent-agent-e1 40, rishab 9, Euler CRM 2 |
| Merge commits | 299 |
| PRs | #1–#294. #293 merged 18 Nov 08:21 UTC; **#294 open** (Cursor follow-up to its own repair); #161 open (Android/iOS); #32 closed |
| Reverts | 3: `3b80aae` (10 Aug, upward-growing Lead Register), `f63f27d` + `d21f30e` (13 Oct, AI Agents desk PR #203/#204) |
| Development model | Almost every change is an AI-agent branch (`cursor/*-996c`, `claude/*`) merged by the owner, frequently within minutes and many per day (e.g. 102 PRs in September). |

## 3. Architecture lineage (independently reconstructed)

1. **28 Jul – 6 Aug:** static GitHub-Pages portal over a Google Apps Script backend (`files/`, `assets/js/`, `_incoming/final_fix_extracted/*.gs`). Still in the repo; root `README.md` still points to it.
2. **6 Aug onward:** FastAPI + MongoDB port (emergent-agent auto-commits), React frontend in `frontend/`. Apps Script logic ported into `commercial.py` ("faithful port of SchemeMasterService.gs …").
3. **Aug:** data-loss fix for `PUT /leads/{id}` (PR #3), Price Master required at booking (#11–#13), scheme allocation engine (#20–#21), Google Sheets sync (#5–#19).
4. **Sep:** roles, Coulson OEM integration (#80–#88), claims settlements (#107–#113), packs, retry-duplicate cleanup (22 Sep).
5. **Oct:** OEM Billing, Tally, Exotel, per-unit pack commercials, Cursor phase-1 audit (#267, 27 Oct).
6. **Nov:** workshop desk + Gmail, OEM exact-variant, Nov scheme, Cursor phase-2 audit (#293), follow-up #294.

## 4. Suspicious changes — findings with commit evidence

| Ref | Commit(s) | What changed | Assessment |
|---|---|---|---|
| G-1 | `f12168b`, `f1e648e`, `11bc1d1` (22 Sep) | Duplicate-lead cleanup went from an owner button (`POST /leads/repair-retry-duplicates`) to an automatic background purge triggered by `GET /api/leads` and boot. The test was rewritten from the HTTP endpoint to the internal function (`test_same_order_multi_unit.py`). | **Approved behaviour weakened** (explicit owner action → silent deletion). Root of CLD-01 (data loss, reproduced). |
| G-2 | `e06f5b0` (15 Sep) | `apply_catalog` began filling family RTO/insurance on new rows. `test_apply_catalog_renames_and_drops` still expected 0. | Test **red on `main` for 64 days** until Cursor's AUD-002 (18 Nov). Proves no test gate existed. Cursor's test change is a correct alignment, not a weakening. |
| G-3 | `19667af` (18 Nov, PR #293) → `36cf78f`, `5e9b03a` (PR #294, open) | Cancel/rebill logic changed, then partially corrected two minutes after merge. | **A fix merged before it was complete**; `main` now carries a known-incomplete rebill rule (CLD-05). |
| G-4 | `0052549`, `b06aac0` (6 Aug, emergent auto-commits) | Public share board added `allLeads` with customer names. | Pre-existing PII exposure (CLD-02). |
| G-5 | PR #92 (2 Sep), PR #101 | "Optional email and owner-visible staff passwords". | Introduced `passwordPlain` (CLD-04). Deliberate feature; security regression. |
| G-6 | `572da25` (13 Oct) | Test renamed `…hides_new` → `…includes_new`; 8 assertions removed, 5 added. | **Intentional rule change** (Showroom Admin now sees New leads). Not a hidden weakening; consistent with PR title. |
| G-7 | `31b8d79` (16 Oct) | 10 assertions removed, 5 added — Exotel prompt clip restored. | Audio-asset test change; no business logic. |
| G-8 | `3a7d98a` (10 Aug) | 42 assertions removed, 39 added — Lead Register sheet layout. | Layout rule change; paired with the `3b80aae` revert. |
| G-9 | `f63f27d`, `d21f30e` (13 Oct) | AI Agents desk removed with its tests (51 + 6 assertions). | Intentional revert; Cursor baseline also records it as a non-goal. |

Across all history, **718 assertion lines were removed** in test diffs; only the six commits above removed more assertions than they added, and all six were reviewed. No test file was deleted other than with a revert. **Apart from G-1, Claude found no case where a test was weakened to hide a regression.**

## 5. Unmerged branches with unique work (patch-equivalence checked with `git cherry`)

| Branch | Unique commits | Last commit | Assessment |
|---|---|---|---|
| `cursor/crm-enterprise-audit-996c` | 2 | 18 Nov — PR #294 rebill follow-up | **Needed** to complete AUD-001 (CLD-05); has unresolved Codex review findings |
| `cursor/deal-pass-meet-cx-996c` | 1 (`133dd28`) | 23 Sep — "Keep customer payable on Cx Demand…" | **Equivalent logic is on `main`** (`server.py` ~1576 `customer_payable = _deal_price_payable(lead)` and margin + `extra_from_cx`). Not lost. |
| `cursor/pack-claim-units-scheme-month-996c` | 1 | 16 Oct — per-unit Cx Demand grouping | Same title merged via PR #249 (`39e6c09`); branch copy superseded |
| `cursor/native-android-ios-996c` | 5 | 15 Sep | PR #161 open; outside web app |
| `claude/sleepy-einstein-9dsymr` | 5 | 2 Nov — roadmap doc | Documentation only |
| `cursor/lead-bulk-upload-template-996c` | 2 | 17 Aug | Refund work moved to its own branch (merged as PR #55) |
| `cursor/render-spa-refresh-fix-996c` | 1 | 11 Aug | PR #32 closed (doc) |
| `cursor/whatsapp-ui-deploy-fix-996c` | 1 | 18 Aug | Build config; superseded by PR #58/#63 |

**No approved business logic was found stranded on an unmerged branch.**

## 6. Multiple implementations / old code alongside replacements

- **Legacy Apps Script implementation** remains in the repository (`_incoming/final_fix_extracted/*.gs`, `files/*.html`, `assets/js/*`, root `index.html`, `worker.js`, `wrangler.jsonc`, `package.json`). Root `README.md` still directs staff to it (also Cursor phase-1 AUD-008). Risk: a deploy pipeline or a person uses the stale portal. The root `wrangler.jsonc` is validated by CI in addition to `frontend/wrangler.toml`; which one serves production is not determinable from the repository.
- **Two scheme split engines:** `scheme_share_split_for` (always claims entitlement components) and `compute_scheme_allocation` (claims only "used" components, PR #33). Only the latter is used for money; the former remains for a diagnostics endpoint (`server.py` ~16469). Low risk, but a future caller could pick the wrong one.
- **Two dealer-earnings totals:** `recompute_lead` (`dealerTotalEarnings`) and `list_dealer_earnings` recompute the same sum from different inputs (lead fields vs `insurance` collection). Formulae match today; drift risk.
- **Customer payable** has several derivations (`compute_commercial_totals`, `_deal_price_payable`, `_sum_unit_payables`, `_receipt_payable`). Phase-1 AUD-009 named this as the reason the pack-refund bug survived.

## 7. Before vs after Cursor's audit

| | Before (`adef670`) | After (`fbb0e21`) |
|---|---|---|
| CI | Cloudflare wrangler dry-run only | + 10-file pytest job (not required) |
| Functional code | — | `oem_sync.py` cancel/rebill only (CLD-05) |
| Tests | 1 test red on `main` since 15 Sep | Green for the 10 files; full-suite state: see test report |
| Documentation | phase-1 register (open P0s) | 8 new docs; open P0s not carried forward |

## 8. Conclusions

- Historical functionality has not disappeared through unmerged branches.
- One approved control was silently weakened (G-1 → CLD-01, critical).
- One fix was merged incomplete and is still open (G-3 → CLD-05).
- Long-lived red tests and same-day agent merges show that, before 18 Nov, nothing enforced test health; after 18 Nov, enforcement is still not configured.
- Claude did not invent causation: each row above cites the commit where the behaviour appears; where intent is unclear (G-6, CLD-13) it is reported as needing an owner decision.
