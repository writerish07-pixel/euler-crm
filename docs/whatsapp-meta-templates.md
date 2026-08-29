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

## F. `exec_eod_scorecard`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `exec_eod_scorecard` |
| Sent | every executive, 20:00 IST |

**Body**
```
Today's numbers for {{1}}.

Bookings today: {{2}}
Bookings this month: {{3}}
Deliveries this month: {{4}}
Follow-ups still overdue: {{5}}

Open the app for details.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Executive name | Amit |
| {{2}} | Bookings dated today | 2 |
| {{3}} | Bookings MTD | 11 |
| {{4}} | Deliveries MTD vs target | 8 of 10 (80.0%) |
| {{5}} | Overdue follow-ups | 1 |

> {{4}} carries the target inline when one is set on the staff master, and just
> the count when it is not — a single variable either way.

---

## G. `manager_eod_volume`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `manager_eod_volume` |
| Sent | every RM and ASM, 20:00 IST |

**Body**
```
Euler CRM - EOD {{1}}

Bookings today: {{2}} | Month: {{3}}
Deliveries today: {{4}} | Month: {{5}}
Top today: {{6}}

Open the app for the full list.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Date | 2026-08-26 |
| {{2}} | Bookings today | 4 |
| {{3}} | Bookings MTD | 37 |
| {{4}} | Deliveries today | 3 |
| {{5}} | Deliveries MTD | 29 |
| {{6}} | Top 3 executives, one line | Amit (2), Sanjay (1) |

> **No money in this template, by design.** Revenue, customer outstanding and
> finance amounts are owner-only; `/api/reports/daily/manager` strips them
> server-side, so a manager cannot receive them even by accident.

---

## H. `owner_eod_summary`

| Field | Value |
|---|---|
| Category | **Utility** |
| Language | English (`en`) |
| Name | `owner_eod_summary` |
| Sent | owner, 20:00 IST |

**Body**
```
Euler CRM - EOD {{1}}

Bookings today: {{2}} | Month: {{3}}
Deliveries today: {{4}}
Deliveries this month: {{5}}

Revenue this month: Rs {{6}}
Customer outstanding: Rs {{7}}
Finance pending: Rs {{8}}
Top today: {{9}}

Open the app for the full breakdown.
```

| Variable | Meaning | Sample |
|---|---|---|
| {{1}} | Date | 2026-08-26 |
| {{2}} | Bookings today | 4 |
| {{3}} | Bookings MTD | 37 |
| {{4}} | Deliveries today | 3 |
| {{5}} | Deliveries MTD vs target | 29 of 40 (72.5%) |
| {{6}} | Retail value delivered MTD | 1,84,50,000 |
| {{7}} | Open customer outstanding | 21,40,000 |
| {{8}} | Financer money not yet received | 12,40,000 (6 files) |
| {{9}} | Top 3 executives, one line | Amit (2), Sanjay (1) |

**Button (URL):** `Open dashboard` → your app URL

> **Revenue** = customer payable on vehicles retailed this month, i.e. what you
> sold. Cash actually collected is a different number (`collectedMtd` on
> `/api/reports/daily/owner`); say the word if you would rather the message
> carried that instead.
>
> The per-financer split cannot be a variable (it is a list). {{8}} carries the
> total and file count; the Finance Register's "By financer" card has the
> breakdown.

---

## If a report says "not delivered to maintain healthy ecosystem engagement"

This is Meta error **131049**, and it is not a rejection — Meta **accepted** the
send, returned success, and then refused to deliver it. That is why the app
originally reported these as sent.

**It is the per-user marketing frequency cap, and it applies only to
MARKETING-category templates.** Utility templates are not subject to it. So
seeing this error means Meta has categorised that template as **Marketing**,
regardless of the category requested when it was submitted — Meta
auto-categorises from the body text and its decision overrides yours.

It also explains why the morning report kept working while every EOD report
failed: `exec_day_ahead` reads as an operational task list and was categorised
Utility, while the EOD bodies read as business/performance summaries and were
categorised Marketing.

### The fix, in order of preference

1. **Get the category changed.** WhatsApp Manager → Message Templates → open the
   template → check **Category**. If it says Marketing, request Utility. Meta
   allows a category appeal; if it is refused, delete the template and re-create
   it with wording that reads as an account/status update rather than a
   performance summary — avoid superlatives, rankings and anything that sounds
   promotional. "Top today: …" is the kind of line that pushes a body into
   Marketing.

2. **Have each recipient reply once.** The app now sends a report as a plain
   **session message** whenever the recipient's 24-hour window is open. A session
   message is not a template at all, so it has no category and the cap cannot
   touch it. Anyone who replies to their morning report keeps the window open
   through the evening one. This works today with no Meta changes.

3. **Read it in the app.** Every report is also a page:
   `/reports/daily/owner`, `/reports/daily/manager`,
   `/reports/daily/executive/{name}`. The WhatsApp copy is a convenience, not
   the only route to the numbers.

**Diagnosing it:** Staff & Reports → *Daily report health* shows the last run per
slot, the template each report used, and Meta's verbatim reason against each
recipient. Reports carry no leadId, so they never appear in the WhatsApp Inbox
or the Sent box — that panel is where they surface.

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
