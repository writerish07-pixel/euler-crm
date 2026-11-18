# Production follow-up

Do not run these against production from the remediation branch. They are for the owner, read-only first.

1. After deploy, open owner Settings and list accounts where `usingDefaultPassword` is true. Change those passwords. Demo users are no longer created unless `SEED_DEMO_USERS=1`.
2. `backend/scripts/drop_plaintext_passwords.py` prints how many users still have `passwordPlain`. It unsets that field only with `--apply`.
3. `backend/scripts/duplicate_census.py` prints duplicate `leadId` and `receiptNumber` samples. Startup creates a unique index only when the count is zero. It never deletes documents.
4. Chassis, invoice, number plate, and claim-component uniqueness are not indexed in this change. That is the recommended next step after the census is clean.
5. Go-live reset now also deletes lead documents, WhatsApp threads, messages, outbox, and lead requests. Confirm that is still wanted before anyone presses reset.
