# Trade Advance WhatsApp templates — Botspace / Meta submit

Submit these **three** templates in **Botspace → WhatsApp Templates** so Meta can approve them. Until they are **Active** on the same WABA/channel as the CRM API key, TA alerts fail with “template not found / not approved”.

| Field | Value for all three |
|---|---|
| Category | **Utility** |
| Language | **English (`en`)** — not Hindi |
| Buttons | none |
| Footer | optional / none |

Also set **Settings → WhatsApp → Finance Manager mobile** and ensure Owner staff have WhatsApp numbers with `owner_eod`. Cron: `POST /api/integrations/botspace/cron?slot=ta&token=…` at **10:30 IST**.

Full variable notes: `docs/whatsapp-meta-templates.md` sections I–K.

---

## 1. `ta_daily_statement`

**Name (exact):** `ta_daily_statement`  
**When:** every open TA, 10:30 IST (owner + Finance Manager)  
**Variables:** 3

**Body (paste exactly):**
```
Trade Advance statement dated {{1}}.

Open tranches: {{2}}
Total balance: Rs {{3}}

Open Euler CRM → Finance to clear or renew.
```

| Var | Sample for Meta |
|---|---|
| {{1}} | 2026-11-26 |
| {{2}} | Shriram drawn 2026-11-01 due 2026-12-01 bal Rs 88,00,000 days left 5 |
| {{3}} | 88,00,000 |

> {{2}} must be a **single line** (pipe-separated if several tranches). Meta rejects newlines inside a variable.

---

## 2. `ta_day25_clear`

**Name (exact):** `ta_day25_clear`  
**When:** once per tranche on day ≥25 after drawn  
**Variables:** 4

**Body (paste exactly):**
```
Trade Advance clear window for {{1}}.

Tranche drawn {{2}}, due {{3}}. Balance Rs {{4}}.

Clear by the due date so a new Trade Advance can be taken.
```

| Var | Sample for Meta |
|---|---|
| {{1}} | Shriram |
| {{2}} | 2026-11-01 |
| {{3}} | 2026-12-01 |
| {{4}} | 8,50,000 |

---

## 3. `ta_low_balance`

**Name (exact):** `ta_low_balance`  
**When:** once per tranche when balance &lt; ₹10 lakh  
**Variables:** 4

**Body (paste exactly):**
```
Trade Advance low for {{1}}.

Balance Rs {{2}} is under 10 lakh. {{3}} days left on tranche drawn {{4}}.

Renew or raise a new Trade Advance.
```

| Var | Sample for Meta |
|---|---|
| {{1}} | Shriram |
| {{2}} | 9,50,000 |
| {{3}} | 12 |
| {{4}} | 2026-11-01 |

---

## After Meta marks Active

1. Confirm names match exactly (underscore, no spaces).
2. Settings → WhatsApp → Channel ID + API key saved.
3. Finance Manager mobile set.
4. Optional smoke: `POST /api/integrations/botspace/send-daily-report?slot=ta` (owner).
