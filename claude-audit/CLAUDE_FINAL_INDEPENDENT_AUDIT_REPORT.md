# Euler CRM — Final Independent Audit Report (Claude)

Date: 18 Nov 2026 · Baseline: `origin/main` `fbb0e21` (includes Cursor's PR #293) · Open follow-up: PR #294
Companion reports in this folder: executive summary, Cursor verification, Git forensics, business-logic verification, additional findings (CLD-01…CLD-21), database & integration, test coverage.

## Overall status: **RED**

Reason: two independently reproduced CRITICAL issues that affect data integrity and personal data on the current `main` (CLD-01 silent deletion of genuine leads; CLD-02 public customer list), plus CRITICAL credential exposure whose production state could not be checked (CLD-03). Cursor's AMBER rested on not carrying forward its own earlier P0 findings.

## 1. What was done

- Read all 8 Cursor deliverables and its 27 Oct phase-1 audit; built a claim-by-claim verification matrix.
- Recovered full Git history (752 commits on `main`, 263 branches, 294 PRs); traced every suspicious behaviour to a commit.
- Ran the full backend suite (1,648 tests), Cursor's critical suite (251), frontend Jest (193) and the production build.
- Wrote and ran 21 independent in-process probes against the real FastAPI app (in-memory MongoDB) covering lead → booking → Price Master → payment → outstanding, concurrency, roles, public routes, webhooks and Cursor's repair.
- No application code, tests, configuration, branches or production data were changed; nothing was committed or pushed. All reports are in `claude-audit/` (uncommitted).

## 2. Findings by severity

| Severity | Count | IDs |
|---|---|---|
| CRITICAL | 3 | CLD-01 lead purge on read/boot (data loss) · CLD-02 public customer names · CLD-03 default credentials |
| HIGH | 6 | CLD-04 plaintext passwords · CLD-05 Cursor rebill repair incomplete on `main` · CLD-06 claim receipts double-count · CLD-07 forgeable webhooks · CLD-08 no enforced regression gate · CLD-13 Sales GM cash posting |
| MEDIUM | 8 | CLD-09 P&L keys to executives · CLD-10 reset KYC inheritance · CLD-11 boot jobs change money · CLD-12 no DB uniqueness · CLD-14 unbounded scans · CLD-19 PDF compression disabled · CLD-20 broken test suites · CLD-21 claim after Close Won (unverified) |
| LOW | 4 | CLD-15 CORS/JWT hardening · CLD-16 margin GST formula (confirm) · CLD-17 year in IDs · CLD-18 comment |

By origin: **New issue introduced by Cursor:** CLD-05. **Missed by Cursor:** CLD-01, CLD-06, CLD-09, CLD-11, CLD-19, CLD-20 (and CLD-21 unverified). **Found by Cursor on 27 Oct but dropped from the final reports:** CLD-02, CLD-03, CLD-04, CLD-07, CLD-10, CLD-12, CLD-13, CLD-15. **Architectural:** CLD-08, CLD-11, CLD-12, CLD-14.

## 3. Performance and scalability (no measurements were possible)

- **Measured:** none. No production-size dataset or load tool was used; Claude does not report latency numbers.
- **Theoretical, from code:** many endpoints load whole collections into memory (`to_list(2000…15000)`) and filter in Python, with silent caps that truncate totals beyond the cap (CLD-14). `GET /api/leads` can trigger a 15,000-row purge scan every 15 s. Dashboards recompute from full scans. `recompute_lead` runs many queries per lead and, when the seed flag is set, is called on boot for every lead (up to 3,000). The code's own comments record past timeouts (25 s register loads, Railway 502s during boot). Indexes exist for the main lookup fields but there is no pagination.
- **Recommendation:** add server-side pagination and aggregation for registers and reports; move boot heals to one-off scripts; measure with production-like volume before go-live.

## 4. Independent final verdict

1. **Is Cursor's audit reliable?** **Partly.** The 10-file test claims, the AUD-002 analysis and the Git counts are accurate. The headline conclusions are not: "Critical: 0" was reached by dropping its own open P0/P1 findings from 27 Oct, AUD-001 was merged incomplete (Cursor's own PR #294 admits it), the roles baseline contradicts the code, and the number of live-HTTP test files is wrong (4 vs 11).
2. **Did Cursor miss important historical business logic?** **Yes.** The owner-controlled duplicate cleanup became a silent automatic deletion (G-1/CLD-01). The "Sales GM does not post cash" rule was lost on 27 Sep (CLD-13). No approved logic was found stranded on unmerged branches.
3. **Did Cursor miss regressions?** **Yes.** CLD-01, CLD-06, CLD-13, CLD-19, plus 50 persistently failing tests and 28 errors it did not run.
4. **Did Cursor introduce new problems?** **Yes, one.** CLD-05 (rebilled chassis can be cleared). Its documentation also misstates readiness.
5. **Are its repairs correct?** AUD-002: correct. AUD-001: fixes the tested case, regresses two others; needs PR #294 completed (Codex review findings unresolved) plus the blank-invoice case.
6. **Are critical workflows independently verified?** **Partly.** Verified in-process: lead → booking with automatic Price Master values (owner and executive with KYC) → partial payments → outstanding; over-payment and duplicate-receipt guards; executive data scoping; price lock after booking. Not verified: browser UI, live OEM sync, Sheets, finance and insurance end to end, multi-worker concurrency.
7. **Are database operations reliable?** **No.** Destructive deletes on read paths, no unique constraints for core identifiers, read-modify-write totals, no transactions, boot jobs mutating money.
8. **Are financial calculations correct?** **Core formulas: consistent where tested.** Customer payable, scheme allocation (company-share-first, unused components not claimed), customer benefit kept out of dealer-retained, and lead/report earnings use the same terms. **Exceptions:** OEM claim receipts can be over-counted (CLD-06); the margin formula needs business confirmation (CLD-16); legacy vs explicit allocation rules differ; boot uplift can change payable (CLD-11).
9. **Are permissions and security adequate?** **No.** Public PII endpoint, default credentials, plaintext passwords, fail-open webhooks, owner P&L keys in staff payloads, CORS `*`. Role checks on mutating routes are otherwise present and executive scoping works.
10. **Is permanent regression protection operational?** **No.** CI runs 10 of 111 backend files and no frontend tests; nothing is required before merge; the wider suite is red and partly order-dependent.
11. **Is Euler CRM ready for further development?** **Only after a short stabilisation step.** New features on top of the current state will keep producing silent regressions. First stop data loss and exposure, then make the test suite green and required.
12. **What must be corrected before production deployment?**
    - **Immediately (before any further deploy):** CLD-01 (remove the purge from `GET /api/leads` and boot), CLD-02 (strip names from the public board), CLD-03 (check production for `euler@123` accounts; stop seeding demo users in production), CLD-05 (complete and merge PR #294, or revert AUD-001).
    - **Next:** CLD-04, CLD-06, CLD-07, CLD-13 (owner decision), CLD-19 (pin pypdf), CLD-09, CLD-10.
    - **Then:** CLD-08/CLD-20 (green full suite, required checks, frontend tests in CI), CLD-11, CLD-12 (after a read-only production duplicate census), CLD-14.
    - **Production checks Claude could not do (read-only, owner-authorised):** count of leads deleted by `RETRY_DUP_LEADS_REPAIRED` (application logs); users whose hash verifies `euler@123`; Exotel/BotSpace `webhookSecret` configured?; duplicate `leadId` / `receiptNumber` / claim rows; claims where `receivedAmount > eligibleClaim`; installed pypdf version.

## 5. Uncertainty statement

Everything marked REPRODUCED ran against the real application code with an in-memory database, not production. Production configuration (secrets, worker count, installed package versions, deployed commit) and production data were not visible; where impact depends on them it is stated as conditional. Claude did not modify anything to obtain these results.
