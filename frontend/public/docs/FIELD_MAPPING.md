# FIELD_MAPPING — Spreadsheet Column → Backend Field → UI

**Legend:** SS = original spreadsheet column · DB = MongoDB field (`leads` unless noted) · UI = where it appears. Derived fields are computed by `commercial.py` / `recompute_lead`.
_Version 2.2 · 2026-06_

## LEADS / CUSTOMER
| Spreadsheet column | DB field | UI location |
|---|---|---|
| Lead ID | leadId | Lead Register, drawer header |
| Customer Name | customerName | Register, drawer header, Edit |
| Mobile | mobile | Register, Edit (unique) |
| Interested Model | interestedModel | Register, Price/Scheme |
| Variant | variant | Register, Price/Scheme |
| Source | source | Edit |
| Executive | executive | Edit, reports |
| Current Status | currentStatus | Status badge |
| Account Status | accountStatus | Status badge |

## BOOKING
| SS | DB | UI |
|---|---|---|
| Booking Date | bookingDate | Booking modal / Overview |
| Booking Amount / Advance | bookingAmount | Booking modal; recorded as payment |

## PRICE STRUCTURE (charges)
| SS | DB | UI (Price Structure tab) |
|---|---|---|
| Ex-showroom | exShowroom | Ex-showroom |
| RTO / Road Tax | registrationRto (rto) | RTO |
| Insurance (premium) | insurance / insuranceAmount | Insurance |
| Accessories | accessories | Accessories |
| Handling Charges | handlingCharges | Handling |
| TRC | trc | TRC |
| FASTag | fastag | FASTag |
| Extended Warranty | extendedWarranty | Extended Warranty |
| RSA / AMC | rsaAmc | (engine sums; input pending — H5) |
| Other Charges | otherCharges | Other |
| TCS Applicable | tcsApplicable | TCS Applicable (Yes/No) |
| Final Exchange Value | finalExchangeValue | Final Exchange Value |

## SCHEME (offers)
| SS | DB | UI (Scheme tab) |
|---|---|---|
| Consumer Scheme | consumerDiscount | Consumer (if available) |
| Exchange Benefit | exchangeBonus | Exchange |
| Loyalty | loyaltyBonus | Loyalty |
| Referral | referralBonus | Referral |
| DSA | dsaDiscount | DSA |
| Additional Discount | additionalDiscount | Additional Discount |
| Benefit Mode | benefitMode | Benefit Mode |
| Benefit Passed Breakup | benefitPassedBreakup (JSON) | Partial breakup inputs |
| OEM Extra Support Received | oemExtraSupportReceived | OEM Extra Support Received |
| OEM Extra Support Passed | oemExtraSupportPassed | OEM Extra Support Passed |

## DERIVED COMMERCIALS
| SS (formula cell) | DB | UI |
|---|---|---|
| Gross Vehicle Cost | grossVehicleCost | Overview / Price preview |
| TCS | (in totals) | Price preview |
| Total Discount | totalDiscount | Overview |
| Customer Payable | customerPayable | Overview, header |
| Total Received | totalReceived | Payments |
| Customer Outstanding | customerOutstanding / outstandingAmount | Header, Payments |
| OEM Claimable (company share) | companyOutstanding / oemClaimCompanyShare | Overview, Scheme preview, Claims |
| Scheme Company Total | schemeCompanyTotal | reports |
| Dealer Scheme Retained | dealerSchemeRetained | Overview, Scheme preview, Earnings |
| OEM Extra Support Retained | oemExtraSupportRetained | Earnings |
| Dealer Margin (net GST) | dealerMarginNetExGst | Overview, Earnings |

## PAYMENTS (collection `payments`)
| SS | DB | UI |
|---|---|---|
| Amount | amount | Payments tab, Ledger |
| Mode | paymentMode | Payments |
| Narration | narration | Payments |
| Financer Name | financerName | Payments (Finance mode) |
| Finance File No. | financeFileNumber | Payments (Finance mode) |
| Date | date | Payments/Ledger |

## FINANCE (collection `finance`)
| SS | DB | UI (Finance Register) |
|---|---|---|
| File Number | fileNumber | File # |
| Financer | financer | Financer |
| Sanctioned/Committed | sanctionedAmount | Committed |
| Received/Disbursed | receivedAgainstFile | Disbursed |
| File Outstanding | fileOutstanding | Outstanding |
| Status | status | Status |
| Receipt history | receipts[] | (history) |

## INSURANCE (collection `insurance`)
| SS | DB | UI (Insurance / per-lead) |
|---|---|---|
| Insurer | insuranceCompany | Insurer |
| Policy Number | policyNumber | Policy Number |
| Premium | insuranceAmount | Premium (pre-filled) |
| Payout Rate | payoutRate | Payout Rate % |
| Expected Payout | expectedPayout | Expected |
| Received Payout | receivedPayout | Received |
| Payout Outstanding | payoutOutstanding | Outstanding |
| Status | status | Status |
| Receipt history | receipts[] | (history) |

## OEM CLAIMS (collection `claims`)
| SS | DB | UI (Claims) |
|---|---|---|
| Component | componentKey/component | Component |
| Claim (company share) | claimAmount | Claim Amount |
| Eligible | eligibleClaim | Eligible |
| Received | receivedAmount | Received |
| Status | claimStatus | Status |
| Reference | claimReference | (settle) |
| Receipt history | receipts[] | (history) |

## DELIVERY (collection `deliveries` + lead)
| SS | DB | UI (Delivery tab) |
|---|---|---|
| Insurance/Registration/Invoice/RC/PDI | insurance/registration/invoice/rc/pdi | checklist toggles |
| Invoice Number | invoiceNumber | Invoice Number |
| Chassis Number | chassisNumber | Chassis Number |
| Number Plate | numberPlate | Number Plate |
| Delivered | deliveryStatus | Mark Delivered? |
| Delivery Date | deliveryDate | Delivery Date |

## DEALER EXTRA INCOME (C1 — collection `leads`, via PUT /leads/{id}/extra-income)
| SS | DB | UI |
|---|---|---|
| Documentation Income | documentationIncome | Lead drawer → Scheme tab → Dealer Extra Income |
| Warranty Income | warrantyIncome | Lead drawer → Scheme tab → Dealer Extra Income |
| RSA Income | rsaIncome | Lead drawer → Scheme tab → Dealer Extra Income |
| Referral Income | referralIncome | Lead drawer → Scheme tab → Dealer Extra Income |
| (derived) Extra income total | extraDealerIncomeTotal | Dealer Earnings Report |
| (derived) Total dealer earnings | dealerTotalEarnings | Overview / Earnings |

## AUDIT TRAIL (H4 — collection `audit_log`, GET /audit-log owner-only)
| Field | DB | UI |
|---|---|---|
| Who / role / IP | user / role / ip | Audit Trail page |
| When | timestamp | Audit Trail page |
| Action / Module | action / module | Audit Trail page |
| Old / New value | oldValue / newValue | Audit Trail page |
| Refs | leadId / paymentId / claimId / financeFileNumber | Audit Trail page |

## RESOLVED GAPS (were "source not yet captured")
- Documentation / Warranty / RSA / Referral income (C1) — ✅ now captured (extra-income fields, folded into Dealer Earnings).
- Claim Submitted/Approved dates + ageing (H3) — ✅ now captured (settle/receipt set submittedDate/approvedDate; list returns ageingDays).
- RSA/AMC charge input (H5) — ✅ `rsaAmc` now has a Price Structure input and flows into GVC/Customer Payable.
