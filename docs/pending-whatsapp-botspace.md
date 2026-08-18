# WhatsApp via BotSpace — implemented

Status: **shipped in code**. Auto-send only works after Meta approves the templates and Channel ID is saved in Settings.

See `docs/whatsapp-meta-templates.md` for the four templates to submit.

Euler-only filter: inbound webhook matches phone to CRM `lead.mobile`. Tata / other BotSpace chats are ignored.

Booking and delivery saves do not wait on WhatsApp and cannot fail because of it.
