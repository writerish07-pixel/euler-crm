# PENDING — WhatsApp via BotSpace (do not implement until owner asks)

Status: **parked**. Owner will implement this later. Do not build until they say go.

Channel: **BotSpace** WhatsApp Public API (paid plan) + webhooks.  
CRM already knows booked vs not booked (`convert-booking`, `_is_booked_lead`) and finance 2-day SLA after delivery.

---

## Why

Executives are **not filling Next Follow-up**. Auto WhatsApp must **not** depend on that field. Clock starts from **lead `createdDate`**.

Customer replies must appear **inside the CRM** (lead thread), not only in BotSpace Inbox.

---

## Four message streams

### 1. Customer follow-up — every 3rd day until booked

- **To:** lead `mobile`
- **When:** day 3, 6, 9… from `createdDate`
- **Who:** Active, not booked, not lost (New / Contacted / Follow-up / In Progress)
- **Stop:** Booked, Lost, Closed, or customer STOP / DND
- **Do not use** `nextFollowupDate`

### 2. Executive reminder — finance delayed 2 days

- **To:** that lead’s executive WhatsApp (number stored in Settings; users have no phone today)
- **When:** finance file still outstanding **2 days after delivery** (same SLA as Finance Register)
- **Until:** financer receipt recorded, or cap (e.g. every 2 days, max 3)
- **Not** a customer chase

Owner will provide each executive name (as on the lead) + mobile.

### 3. Booking confirmation

- **To:** customer
- **When:** immediately on Convert to Booking

### 4. Delivered + Google review (same message, same time)

- **To:** customer
- **When:** immediately on Mark Delivered (not next day)
- **Once only**
- Needs real **Google review URL** in the template button

---

## Replies in the app (required)

BotSpace **incoming-message webhook** → match `phone` to `lead.mobile` → show thread on the lead (Activity or WhatsApp tab).

- Outbound: follow-up / booking / delivered / (exec finance is on a staff log, not the customer lead thread unless useful)
- Inbound: customer text + button taps (`हाँ, कॉल करें`, `बाद में`)
- Delivery events: sent / delivered / read / failed
- Staff reply **from the app only inside the 24-hour window** (after customer writes). Outside 24h: templates only.

---

## Runtime (when built)

- Railway daily morning job: 3-day follow-ups + finance-overdue exec pings
- Instant send on booking save and delivery save
- Quiet hours TBD (default proposal: no customer WhatsApp before 9am / after 8pm; queue to next morning)
- Failed / not-on-WhatsApp numbers stay visible on the lead
- Never auto-follow-up booked / delivered / closed customers

---

## Owner must provide before build

1. BotSpace **API key** + **channel** (Settings → API Keys)
2. Executive name → WhatsApp number list
3. Meta-approved template names (after they submit the copy below)
4. Real **Google review link**
5. Confirm quiet hours if different from 9am–8pm

BotSpace Public API is paid-only; send endpoints ~40 req/s/channel (fine).

---

## Hindi templates to submit in BotSpace → Meta

Language: **Hindi (`hi`)**. Template **names** stay English (Meta). No templates were approved yet when this was parked.

Replace `YOUR_GOOGLE_REVIEW_LINK` and showroom wording before submit.

### A. `lead_followup_3day` — Marketing — Hindi

**Body**
```text
नमस्ते {{1}} जी,

आपने हमारे शोरूम में {{2}} के लिए रुचि दिखाई थी। लीड नंबर: {{3}}।

क्या आप टेस्ट ड्राइव या बुकिंग के लिए बात करना चाहेंगे? इस मैसेज का जवाब दें, हमारी टीम आपसे संपर्क करेगी।
```

| Var | Meaning | Sample |
|-----|---------|--------|
| {{1}} | Customer name | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Lead ID | LD26000008 |

**Buttons:** Quick reply — `हाँ, कॉल करें` · `बाद में`  
**Footer:** `जवाब न हो तो STOP लिखें`

### B. `booking_confirm` — Utility — Hindi

**Body**
```text
नमस्ते {{1}} जी,

आपकी {{2}} की बुकिंग कन्फर्म हो गई है। बुकिंग डेट: {{3}}। आपके कार्यकारी: {{4}}।

अगली प्रक्रिया के लिए हमारी टीम आपसे संपर्क करेगी। धन्यवाद।
```

| Var | Meaning | Sample |
|-----|---------|--------|
| {{1}} | Customer | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Booking date | 15-08-2026 |
| {{4}} | Executive | अमित |

### C. `delivery_review` — Utility — Hindi

Review **in the same Delivered message**.

**Body**
```text
नमस्ते {{1}} जी,

आपका {{2}} डिलीवर हो गया है। डिलीवरी डेट: {{3}}।

हमारे साथ अपने अनुभव की Google रेटिंग और रिव्यू ज़रूर दें। नीचे लिंक पर टैप करें।
```

| Var | Meaning | Sample |
|-----|---------|--------|
| {{1}} | Customer | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Delivery date | 15-08-2026 |

**Button:** URL — `Google रिव्यू दें` → `YOUR_GOOGLE_REVIEW_LINK`

### D. `finance_overdue_exec` — Utility — Hindi (executive only)

**Body**
```text
फाइनेंस रिमाइंडर

ग्राहक: {{1}}
फाइनेंसर: {{2}}
फाइल: {{3}}
बकाया: ₹{{4}}
डिलीवरी: {{5}}

डिलीवरी के 2 दिन बाद भी फाइनेंसर पेमेंट पेंडिंग है। कृपया रिकवरी फॉलो-अप करें।
```

| Var | Meaning | Sample |
|-----|---------|--------|
| {{1}} | Customer | सुरेन्द्र कुमार |
| {{2}} | Financer | HDFC |
| {{3}} | File no. | FN260012 |
| {{4}} | Outstanding | 170000 |
| {{5}} | Delivery date | 10-08-2026 |

---

## Build checklist (when owner says go)

- Settings: BotSpace API key, channel, executive mobiles, review URL
- `GET/POST` wrapper for BotSpace send-template + send-text (24h replies)
- Webhook endpoint for incoming + delivery events (verify BotSpace secret)
- Daily job: unbooked 3-day cadence; finance SLA → exec template
- Hooks on convert-booking and mark-delivered
- Lead WhatsApp thread UI + Activity lines
- India/Meta: only approved templates to customers outside 24h; opt-out honored

Insurance payout ledger and Insurance Benefit “upto” rule are **unrelated** — see `docs/pending-insurance-benefit-upto.md`.
