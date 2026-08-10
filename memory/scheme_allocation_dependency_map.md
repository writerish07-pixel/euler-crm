# Scheme Allocation Dependency Map (pre-fix audit)

## Root cause
`compute_scheme_income_breakdown` uses formula:
  retained = (companyFull - companyPassed) - dealerPassed
For AUTO entitlements (insuranceBenefit/rtoBenefit/rtoInsuranceBenefit), both
full_split and pass_split always include the entitlement at full master shares,
so retained becomes `0 - dealerShare` (e.g. Turbo insurance → **-10,000**).
That cancels Loyalty No-Benefit retention (+10,000) → Dealer Scheme Retained **₹0**.

OEM claim path (`compute_scheme_claim_shares`) correctly uses companyShare only,
so Claim Register can show Loyalty+Insurance while Dealer Earnings is wrong.

Customer payable only sums OFFER_KEYS via benefitMode — entitlements never reduce payable (correct historically if CB=0).

## Independent calculation sites (must converge)
1. commercial.py `compute_commercial_totals` — customer payable / passed OEM
2. commercial.py `compute_scheme_income_breakdown` — dealer retained / oem claim by component
3. commercial.py `compute_scheme_claim_shares` — claim register display/eligible
4. commercial.py `scheme_share_split_for` — company-first share split
5. commercial.py `get_scheme_offer_rules_for_vehicle` — UI rules + entitlements
6. server.py `recompute_lead` — persists totals to lead + sheets
7. server.py `list_claims` — derives claims from claim shares
8. server.py `_owner_booking_metrics` / oem-claim-dashboard / owner-commercial
9. server.py `dealer_earnings_report` — live margin+scheme+insurance
10. server.py GET `/dealer-earnings` — reads Mongo dealer_earnings (seed/sheet; NOT updated by recompute!)
11. frontend LeadDrawer SchemeTab — displays c.* from 360 commercials
12. frontend DealerEarnings / EarningsReport / OemClaimDashboard / Claims
13. gsheets.py mappings — mirror only
14. Insurance payout: `_upsert_insurance_on_delivery` + `_insurance_derive` (SEPARATE ledger)

## Authoritative formulas (target)
schemeAvailable = master totalBenefit (entitlements) OR staff offer capped by master (offers)
oemShare / oemClaimable = master companyShare (company-first capped by available for offers)
dealerFundedShare = master dealerShare (capped for offers)
customerBenefit ∈ [0, schemeAvailable] from benefitMode / benefitPassedBreakup
dealerRetained = schemeAvailable - customerBenefit
Customer payable reduction = Σ customerBenefit (+ dealer-funded additionalDiscount + oemExtraSupportPassed)
Dealer scheme earnings = Σ dealerRetained
OEM claim = Σ oemClaimable
Insurance payout = premium × rate (NOT oem claim)
