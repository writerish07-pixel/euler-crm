# WhatsApp via BotSpace — implemented

Status: **shipped in code**. Auto-send only works after Meta approves the templates and Channel ID is saved in Settings.

## Customer templates (Hindi Utility / Marketing)

See `docs/whatsapp-meta-templates.md` for booking, follow-up, delivery review, finance overdue, and marketing bodies.

## Trade Advance templates (English Utility) — submit for approval

Paste these three in Botspace → WhatsApp Templates as **Utility / English (`en`)**:

| Name | Vars | When |
|---|---|---|
| `ta_daily_statement` | 3 | Daily open-TA statement, 10:30 IST |
| `ta_day25_clear` | 4 | Day ≥25 clear window (once per tranche) |
| `ta_low_balance` | 4 | Balance under ₹10L (once per tranche) |

**Copy-paste sheet:** `docs/ta-whatsapp-botspace-submit.md`  
**Full bodies + samples:** `docs/whatsapp-meta-templates.md` sections I–K

Also set **Finance Manager mobile** in Settings → WhatsApp, and cron  
`POST /api/integrations/botspace/cron?slot=ta&token=…` at 10:30 IST.

---

Euler-only filter: inbound webhook matches phone to CRM `lead.mobile`. Tata / other BotSpace chats are ignored.

Booking and delivery saves do not wait on WhatsApp and cannot fail because of it.
