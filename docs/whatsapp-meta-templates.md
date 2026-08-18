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
