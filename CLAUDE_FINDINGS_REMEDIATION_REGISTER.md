# Claude findings remediation register

Baseline before these edits (Python 3.12.3, full `pytest tests/`): 1560 passed, 63 failed, 28 errors. The 11 live-HTTP collection errors are in that 28. That run is `docs/remediation/baseline/backend.txt`.

| ID | Status | What changed |
|---|---|---|
| CLD-01 | FIXED AND VERIFIED | GET /leads and boot no longer purge. Owner POST /leads/repair-retry-duplicates dry-runs by default. Deletion requires same mobile, model, variant, a 10-minute window, and no history. Copies go to leads_purged_archive with an audit row. |
| CLD-02 | FIXED AND VERIFIED | Public share board keeps counts and model/variant/status/date. Customer name, mobile, and lead id are not returned. |
| CLD-03 | FIXED AND VERIFIED | Demo users only when SEED_DEMO_USERS is 1/true. Existing users are not rewritten. Owner list has usingDefaultPassword. Production without OWNER_PASSWORD does not create a default owner. |
| CLD-04 | FIXED AND VERIFIED | passwordPlain is not written. Login hashes a legacy plaintext row once and unsets it. User list returns passwordSet, not the password. Reset returns the new password once. |
| CLD-05 | FIXED AND VERIFIED | A Sold row with a blank invoice on a cancelled chassis is ambiguous: the chassis stays and the Sold row is not deleted. Removed Sold rows are copied to oem_sold_removed. Created-list and different-customer rebills were already on main (PR 294). |
| CLD-06 | FIXED AND VERIFIED | Claim receipts dedupe within 10 seconds, reject over-eligible unless allowExcess, and $inc receivedAmount. Financer receipts $inc as well. The frontend does not retry those posts. |
| CLD-07 | FIXED AND VERIFIED | Exotel gather/recorded/status do not write without a webhook secret. BotSpace without a secret returns 200 and writes nothing. Tokens are compared with hmac.compare_digest. |
| CLD-08 | BLOCKED | Workflows backend-full, frontend-tests, and regression_claude on critical-regression are added. Required checks need a repository admin. See docs/remediation/BRANCH_PROTECTION.md. |
| CLD-09 | FIXED BUT NOT FULLY VERIFIED | schemeAllocationSummary and unit copies are passed through the staff share redaction. No new staff-payload scan test was added. |
| CLD-10 | FIXED BUT NOT FULLY VERIFIED | Go-live reset also deletes lead documents, WhatsApp threads, messages, outbox, and lead requests. |
| CLD-11 | FIXED BUT NOT FULLY VERIFIED | Turbo September uplift records system marker turbo_sept_uplift and an audit row, then skips later boots. The sync-flag formula was not changed. |
| CLD-12 | FIXED BUT NOT FULLY VERIFIED | Startup adds a unique leadId and receiptNumber index only when there are no duplicates. duplicate_census.py is read-only. mongomock already had a non-unique leadId index, so the unique index was skipped there. |
| CLD-13 | FIXED AND VERIFIED | Sales GM is denied on customer and Finance receipts before the lead is loaded. Refund stays on the money desk. Booking stays on sales staff. |
| CLD-14 | FIXED BUT NOT FULLY VERIFIED | Payments, deliveries, dealer-earnings inputs, scheme rows, and the share board no longer cap the scan that feeds their totals. |
| CLD-15 | FIXED BUT NOT FULLY VERIFIED | CORS_ORIGINS is used when set. Cron tokens are compared with hmac.compare_digest and already accepted from a header. JWT lifetime was not changed. |
| CLD-16 | REQUIRES BUSINESS DECISION | Dealer margin still divides GST out twice. Characterization test locks ₹7,85,000. |
| CLD-17 | REQUIRES BUSINESS DECISION | Lead and receipt prefixes stay LD26 and RC26. |
| CLD-18 | FIXED AND VERIFIED | The scheme-allocation comment now says the flat decision wins. |
| CLD-19 | FIXED AND VERIFIED | PDF compression tries pypdf 7 arguments, then older ones. pypdf is pinned below 8. |
| CLD-20 | NOT FIXED | Live-HTTP files skip when REACT_APP_BACKEND_URL is unset. The rest of the historical failures (Sheets fakes, price-master fixtures, order-dependent modules) were not all repaired. The suite is not at 0 failed. |
| CLD-21 | FIXED AND VERIFIED | The Close Won test inserted a non-manual claim with no scheme, so the register rebuild dropped it. The fixture is now a manual claim, which the register keeps. The test passes. |
| CLD-22 | FIXED AND VERIFIED | README describes frontend/ and backend/. Legacy portal files stay. |
| CLD-23 | REQUIRES BUSINESS DECISION | Full Benefit remains the default when nobody has allocated the scheme. |
| CLD-24 | FIXED BUT NOT FULLY VERIFIED | scheme_share_split_for is documented as diagnostics only. The earnings equality test was not added. |

Test changes and why:

- tests/test_same_order_multi_unit.py: GET /leads must not purge; different variants and different-model same-day packs are not deleted.
- tests/test_user_account_password.py: the owner list no longer returns a password.
- tests/test_exotel_deal_verify.py and tests/test_whatsapp_botspace.py: fixtures set a webhook secret so existing handler tests still run.
- tests/test_iter32_lead_cancel.py: the Close Won row is a manual claim because it has no scheme allocation.
- Live-HTTP modules skip at import when REACT_APP_BACKEND_URL is unset.
