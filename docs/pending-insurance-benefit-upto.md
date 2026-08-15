# PENDING — Insurance Benefit is “upto” (do not implement until company confirms)

Status: **parked**. Owner asked to remember this. Implement only after they say the company has confirmed it.

Insurance payout (premium × 49% / 36.5%) is a **separate** ledger. This note is only **Insurance Benefit** on scheme / OEM claim / Tally / dealer-funded cost.

## Rule

Scheme Master amount = **maximum cap**, not a fixed cash entitlement. Live premium on the lead (`insuranceAmount`) is what actually gets funded.

```
covered            = min(actual premium, scheme “upto”)
company reimburses = min(company share, covered)
dealer sharing     = covered − company reimburses
                     (never more than dealer share)
```

- Unused cap is **not claimed** and **not retained income**.
- Unused dealer share is **not a cost** and **not income**.
- If premium > cap, the extra is **not** company and **not** automatic dealer scheme cost (customer pays, unless given separately as Additional Dealer).
- **Use Scheme = No** stays full opt-out: no claim, no dealer sharing, customer pays full premium.
- Storm treated as **₹30,000 company / ₹0 dealer** unless Scheme Master says otherwise.

## Confirmed examples (from owner)

**Storm — upto ₹30,000 (company). Actual insurance ₹21,000**

| | Amount |
|---|---|
| Company reimburses | ₹21,000 (not ₹30,000) |
| Dealer sharing | ₹0 |
| Unused ₹9,000 of cap | not claimed, not retained |

**Turbo — upto ₹20,000 (₹10,000 company + ₹10,000 dealer). Actual ₹17,000**

| | Amount |
|---|---|
| Company reimburses | ₹10,000 |
| Dealer sharing | ₹7,000 |
| Unused ₹3,000 of dealer share | not a cost, not income |

Same Turbo, other premiums:

- ₹8,000 → company ₹8,000, dealer ₹0
- ₹25,000 → covered ₹20,000 → company ₹10,000, dealer ₹10,000, customer pays extra ₹5,000

## Where it must land (when confirmed)

- **Scheme step:** show circular as “upto”, lock live split to actual premium.
- **OEM Claims:** Storm ₹21k → claim ₹21k; Turbo ₹17k → claim ₹10k.
- **Tally / Billing Summary:** charge actual premium; if benefit is used, discount = **covered** amount, not the full circular.
- **Dealer Earnings:** Turbo ₹17k → ₹7,000 dealer-funded cost. Storm ₹21k → ₹0 dealer cost.

## What live app does today (the gap)

`compute_scheme_allocation` does **not** cap Insurance Benefit on `insuranceAmount`.

- Storm used → OEM claim full ₹30,000 even if premium is ₹21,000
- Turbo used + pass ₹0 → claim ₹10,000 **and** ₹10,000 retained income
- Turbo used + pass ₹20,000 → customer discount ₹20,000 even if premium is ₹17,000
