# WhatsApp templates to submit in BotSpace → Meta

Submit these **exactly** in BotSpace → WhatsApp Templates.  
Language: **Hindi (`hi`)**. Template **names** stay English (Meta requires that).

Until Meta approves them, Euler CRM still books and delivers as today. Auto WhatsApp will show as failed on the lead until approval.

Use your real Google review URL in template C before submit.

---

## A. `lead_followup_3day`

| Field | Value |
|---|---|
| Category | **Marketing** |
| Language | Hindi (`hi`) |
| Name | `lead_followup_3day` |

**Body**
```
नमस्ते {{1}} जी,

आपने हमारे शोरूम में {{2}} के लिए रुचि दिखाई थी। लीड नंबर: {{3}}।

क्या आप टेस्ट ड्राइव या बुकिंग के लिए बात करना चाहेंगे? इस मैसेज का जवाब दें, हमारी टीम आपसे संपर्क करेगी।
```

| Variable | Meaning | Sample for Meta |
|---|---|---|
| {{1}} | Customer name | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Lead ID | LD26000008 |

**Buttons (quick reply):** `हाँ, कॉल करें` · `बाद में`  
**Footer:** `जवाब न हो तो STOP लिखें`

---

## B. `booking_confirm`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | Hindi (`hi`) |
| Name | `booking_confirm` |

**Body**
```
नमस्ते {{1}} जी,

आपकी {{2}} की बुकिंग कन्फर्म हो गई है। बुकिंग डेट: {{3}}। आपके कार्यकारी: {{4}}।

अगली प्रक्रिया के लिए हमारी टीम आपसे संपर्क करेगी। धन्यवाद।
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Customer | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Booking date | 15-08-2026 |
| {{4}} | Executive | अमित |

---

## C. `delivery_review`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | Hindi (`hi`) |
| Name | `delivery_review` |

**Body**
```
नमस्ते {{1}} जी,

आपका {{2}} डिलीवर हो गया है। डिलीवरी डेट: {{3}}।

हमारे साथ अपने अनुभव की Google रेटिंग और रिव्यू ज़रूर दें। नीचे लिंक पर टैप करें।
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Customer | सुरेन्द्र |
| {{2}} | Model | Turbo Max |
| {{3}} | Delivery date | 15-08-2026 |

**Button:** URL — label `Google रिव्यू दें` → **paste your real Google review link here**

---

## D. `finance_overdue_exec`

This goes to the **executive**, not the customer.

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | Hindi (`hi`) |
| Name | `finance_overdue_exec` |

**Body**
```
फाइनेंस रिमाइंडर

ग्राहक: {{1}}
फाइनेंसर: {{2}}
फाइल: {{3}}
बकाया: ₹{{4}}
डिलीवरी: {{5}}

डिलीवरी के 2 दिन बाद भी फाइनेंसर पेमेंट पेंडिंग है। कृपया रिकवरी फॉलो-अप करें।
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Customer | सुरेन्द्र कुमार |
| {{2}} | Financer | HDFC |
| {{3}} | File no. | FN260012 |
| {{4}} | Outstanding | 170000 |
| {{5}} | Delivery date | 10-08-2026 |

---

## After Meta approves

1. Euler Settings → WhatsApp: confirm template names match (defaults are the four names above).
2. Paste BotSpace **Channel ID** (Settings → channel for the WhatsApp number).
3. In BotSpace webhooks, set callback to  
   `https://euler-crm-production.up.railway.app/api/integrations/botspace/webhook`
4. Add each executive name (as typed on the lead) + their WhatsApp number.
5. Paste the Google review URL.

---

# Internal daily reports (staff only)

These four go to **your own team**, not customers. Category **Utility**,
language **English (`en`)** — chosen so ₹ amounts, financer names and model
names read unambiguously.

### Two rules govern every body

**A body may not START or END with a variable.** Meta rejects it with
"Leading or trailing params not allowed". Every body below therefore opens and
closes with plain text — that is why each report ends with an "Open the app…"
line rather than the top-executives variable.

### The rule that governs every variable

**A template variable may not contain a newline, a tab, or 4+ consecutive
spaces.** Meta rejects the whole send with a parameter-format error. That is why
none of these templates contains a list: totals and a single-line "top
executives" string go in the message, and the **button links to the app** for the
full breakdown. `botspace._one_line()` enforces this on every value, and
`test_iter29_daily_reports.py` asserts it on real payloads.

Recipients, roles and targets are managed in the app at **Settings → Staff &
Reports** — nothing here is hard-coded.

---

## E. `exec_day_ahead`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `exec_day_ahead` |
| Sent | every executive, 08:30 IST |

**Body**
```
Good morning {{1}}.

Pending deliveries: {{2}}
To collect: Rs {{3}}
Follow-ups due today: {{4}}
Overdue follow-ups: {{5}}

Open the app for the customer list.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Executive name | Amit |
| {{2}} | Booked, not yet delivered | 6 |
| {{3}} | Outstanding on those bookings | 4,20,000 |
| {{4}} | Follow-ups dated today | 3 |
| {{5}} | Follow-ups already past due | 2 |

**Button (URL):** `Open my leads` → your app URL

---

## F. `exec_eod_statement` (replaces `exec_eod_scorecard`)

| Field | Value |
|---|---|
| Category | **Utility** — see the note below |
| Language | English (`en`) |
| Name | `exec_eod_statement` |
| Sent | every executive, 20:00 IST |

**Body**
```
Daily activity summary for {{1}}, dated {{2}}.

Bookings recorded today: {{3}}
Bookings recorded this month: {{4}}
Deliveries completed this month: {{5}}
Follow-ups past their due date: {{6}}

Open the Euler CRM app to view these records.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Executive name | Amit |
| {{2}} | Statement date | 2026-08-27 |
| {{3}} | Bookings dated today | 2 |
| {{4}} | Bookings MTD | 11 |
| {{5}} | Deliveries MTD vs target | 8 of 10 (80.0%) |
| {{6}} | Overdue follow-ups | 1 |

> {{5}} carries the target inline when one is set on the staff master, and just
> the count when it is not — a single variable either way.

---

## G. `manager_eod_statement` (replaces `manager_eod_volume`)

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `manager_eod_statement` |
| Sent | every RM and ASM, 20:00 IST |

**Body**
```
Daily activity summary for the dealership, dated {{1}}.

Bookings recorded today: {{2}}
Bookings recorded this month: {{3}}
Deliveries completed today: {{4}}
Deliveries completed this month: {{5}}

Open the Euler CRM app for the executive-wise records.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Statement date | 2026-08-27 |
| {{2}} | Bookings today | 4 |
| {{3}} | Bookings MTD | 37 |
| {{4}} | Deliveries today | 3 |
| {{5}} | Deliveries MTD | 29 |

> **No money in this template, by design.** Revenue, customer outstanding and
> finance amounts are owner-only; `/api/reports/daily/manager` strips them
> server-side, so a manager cannot receive them even by accident.

---

## H. `owner_eod_statement` (replaces `owner_eod_summary`)

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `owner_eod_statement` |
| Sent | owner, 20:00 IST |

**Body**
```
Daily account statement for the dealership, dated {{1}}.

Bookings recorded today: {{2}}
Bookings recorded this month: {{3}}
Deliveries completed today: {{4}}
Deliveries completed this month: {{5}}

Billed value this month: Rs {{6}}
Amount receivable from customers: Rs {{7}}
Amount receivable from financers: Rs {{8}}

Open the Euler CRM app for the record-wise statement.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Statement date | 2026-08-27 |
| {{2}} | Bookings today | 4 |
| {{3}} | Bookings MTD | 37 |
| {{4}} | Deliveries today | 3 |
| {{5}} | Deliveries MTD vs target | 29 of 40 (72.5%) |
| {{6}} | Value billed MTD | 1,84,50,000 |
| {{7}} | Open customer receivable | 21,40,000 |
| {{8}} | Financer money not yet received | 12,40,000 (6 files) |

> **Billed value** = customer payable on vehicles retailed this month. Cash
> actually collected is a different number (`collectedMtd` on
> `/api/reports/daily/owner`).
>
> The per-financer split cannot be a variable (it is a list). {{8}} carries the
> total and file count; the Finance Register's "By financer" card has the
> breakdown.

---

## Why these three were rewritten, and what changed

The originals were categorised **Marketing** by Meta and hit the per-user
marketing frequency cap — accepted, then not delivered. Meta categorises from
the body text and its decision overrides the category you pick at submission, so
the body had to change.

**Submit these under the NEW names.** A template already classified Marketing
keeps that classification; editing it re-opens review but starts from a body Meta
has already judged. New names get a clean assessment. Leave the old three in
place until the new ones are approved — the app will simply use whichever names
are configured.

`exec_day_ahead` is **not** changed. It was categorised Utility and delivers, and
the reason is instructive: it reads as a task list ("pending deliveries",
"follow-ups due"), not as a performance report.

What changed, and why each thing matters:

| Change | Reason |
|---|---|
| **The "Top today" leaderboard is gone** | A ranking of people is the strongest Marketing signal in these bodies. It is still on the report pages, which have no category to lose. |
| Opens "Daily activity summary / account statement … dated {{n}}" | Meta names *recurring billing statements* as Utility. A dated statement for a named account reads that way; "Euler CRM - EOD" reads as a branded broadcast. |
| "Revenue" → "Billed value" | Account-ledger language rather than business-performance language. |
| "Customer outstanding" → "Amount receivable from customers" | Same reason, and it is plainer English. |
| "Finance pending" → "Amount receivable from financers" | Same. |
| Neutral closing line, no exclamation, no promotional verb | "Open the app for the full breakdown" is fine; anything urging action is not. |

**No guarantee.** Meta's categoriser is not published and not deterministic. This
removes the signals that are known to push a body into Marketing, but if a
template still comes back Marketing, appeal the category in WhatsApp Manager, and
use the session-message route below in the meantime.

---

## Scheduling — read this before going live

The in-process ticker only fires if the API happens to be awake in the right
hour. **An idle or restarting host silently skips a day**, which is not
acceptable for reports people rely on. Point an external cron at:

```
POST https://<your-api>/api/integrations/botspace/cron?slot=morning&token=<cronToken>   # 08:30 IST
POST https://<your-api>/api/integrations/botspace/cron?slot=eod&token=<cronToken>       # 20:00 IST
```

cron-job.org or Railway cron both work. Every job is idempotent per day and
slot, so the ticker and cron can run together and nobody gets messaged twice.

To resend a slot after fixing something:
`DELETE /api/integrations/botspace/daily-report-marker?slot=eod`, then
**Settings → Staff & Reports → Send EOD now**.

**Cost:** roughly 6 staff x 2 messages x 30 days = ~360 Utility messages/month.
In India that is around ₹40/month.

---

## Template I — `lead_model_interest` (MARKETING)

**This is the only Marketing-category template in the app.** Everything above is
Utility. That difference matters more than it looks:

* Marketing templates need the customer to have opted in, count against a
  per-number marketing send limit, and are the ones people report as spam.
* Enough reports and Meta cuts your WABA quality rating; at the bottom of that
  scale you lose template sending altogether — including the Utility templates
  that run your booking confirmations and delivery reviews.

So this one is sent deliberately from **Settings → WhatsApp → Model interest
campaign**, never on a schedule, and the app shows you exactly who would receive
it before anything leaves.

**Category:** Marketing
**Language:** English
**Name:** `lead_model_interest`

```
Namaste {{1}}, thank you for your interest in Euler Motors electric vehicles.

Could you tell us which vehicle you are looking for? Just reply with the number:

{{2}}

Reply STOP to stop receiving messages.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Customer name | Ramesh |
| {{2}} | Numbered model menu, built from Price Master | 1 Hi-Load / 2 Neo HiRange / 3 Storm / 4 Turbo Max |

**Both Meta rules this template already respects:**

1. The body does **not** start or end with a variable — it opens with "Namaste"
   and closes with the STOP line. This is what got three of the earlier
   templates rejected.
2. `{{2}}` contains no newline, tab, or run of 4+ spaces — the menu is joined
   with " / " for exactly this reason. **Do not** reformat it into a vertical
   list inside the variable; Meta rejects the send.

**Optional quick-reply buttons.** WhatsApp allows up to 3. Adding your three
highest-volume models as buttons is worth doing — a tap returns an exact value,
where typed text has to be parsed. The numbered menu stays in the body for
everything else, and both paths are handled.

### What happens to the reply

The reply is matched against Price Master. It understands a tapped button, a
menu number, the model name in any spacing or case ("hi load", "HILOAD",
"Hi-Load"), and a name inside a sentence ("mujhe storm chahiye").

It writes a model onto the lead **only** when all three of these hold:

* the lead's Interested Model is currently **empty** — a model an executive
  entered is never overwritten;
* exactly one model matches — "storm or turbo max?" updates nothing;
* the value is stamped `modelSource = whatsapp-reply`, so a customer-stated
  model is always distinguishable from a staff-entered one.

Anything else is left alone and shows up in the WhatsApp Inbox for a human. A
wrong model written onto a lead is worse than an empty one: the executive stops
asking, and nobody notices until someone quotes the wrong vehicle.

When a model IS captured, the customer gets an immediate confirmation. That
needs no template — they just messaged you, so the 24-hour session is open and
free-form text is allowed.

**Cool-off:** the same lead is not asked again for 45 days.
