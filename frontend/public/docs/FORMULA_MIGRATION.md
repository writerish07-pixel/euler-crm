# FORMULA_MIGRATION — Spreadsheet/Apps-Script Formula → Code

Maps every calculation from the source (`CommercialEngineService.gs`, `SchemeMasterService.gs`, `InsuranceService.gs`, `ExtraIncomeService.gs`, `OemClaimService.gs`, `Config.gs`) to its Python implementation in `backend/commercial.py` / `backend/server.py`.
_Version 2.2 · 2026-06 · ✅ = ported & test-verified · ⚠ = partial/pending_

## CONSTANTS (Config.gs COMMERCIAL)
| Constant | Value | Code | Status |
|---|---|---|---|
| TCS_RATE | 0.01 | `commercial` TCS | ✅ |
| Dealer margin rate | 4% of ex-showroom | `compute_dealer_margin` | ✅ |
| GST on margin | 5% | `marginNetExGst = gross/1.05` | ✅ |
| Insurance rate Storm/Turbo | 0.49 | `INSURANCE_RATE_STORM_TURBO` | ✅ |
| Insurance rate other | 0.365 | `INSURANCE_RATE_OTHER` | ✅ |

## COMMERCIAL TOTALS
| Source formula | Code | Status |
|---|---|---|
| GVC = Σ charge columns | `compute_commercial_totals` (Σ `CHARGE_KEYS`) | ✅ |
| TCS = 1% × GVC if applicable | `compute_commercial_totals` | ✅ |
| Total Discount = Σ offers | `compute_commercial_totals` | ✅ |
| Benefit passed (Full/Partial/No) | `resolve_passed_breakup` + mode | ✅ |
| Customer Payable = GVC + TCS − passed − exchange | `compute_commercial_totals` | ✅ |
| Customer Outstanding = max(0, payable − received) | `recompute_lead` | ✅ |
| Dealer Margin net = (4%×exShowroom)/1.05 | `compute_dealer_margin` | ✅ |
| deriveClaim (per-component OEM/dealer, DSA approval) | `derive_claim` | ✅ |

## SCHEME (SchemeMasterService.gs)
| Source function | Code | Status |
|---|---|---|
| normalizeSchemeModelKey_ / variant aliases | `normalize_scheme_model_key` / `normalize_scheme_variant_key` | ✅ |
| modelsMatchScheme_ / variantsMatchScheme_ | `models_match_scheme` / `variants_match_scheme` | ✅ |
| schemeMonthFromDate_ | `scheme_month_from_date` | ✅ |
| getSchemeSharesForLead_ | `get_scheme_shares_for_lead` | ✅ |
| schemeShareSplitFor_ (company-first) | `scheme_share_split_for` | ✅ |
| computeSchemeIncomeBreakdown_ | `compute_scheme_income_breakdown` | ✅ |
| computeSchemeClaimShares_ (DSA auto-approve) | `compute_scheme_claim_shares` | ✅ |
| getSchemeOfferRulesForVehicle_ (availability, caps, choices) | `get_scheme_offer_rules_for_vehicle` | ✅ |
| validateSchemeOffersForVehicle_ | `validate_scheme_offers` (422) | ✅ |
| buildSchemeAmountChoices_ / getAdditionalDiscountChoices_ | `build_scheme_amount_choices` / `additional_discount_choices` | ✅ |
| Scheme Retained = Σ(company kept − dealer given) | `compute_scheme_income_breakdown.retainedIncomeTotal` | ✅ |
| OEM claimable = eligible company share | `compute_scheme_claim_shares.eligibleTotal` → `companyOutstanding` | ✅ |

## INSURANCE (InsuranceService.gs)
| Source | Code | Status |
|---|---|---|
| getSuggestedInsurancePayoutRate_ (49% / 36.5%) | `suggested_insurance_payout_rate` | ✅ |
| computeInsurancePayout_ = premium × rate | `_insurance_derive` | ✅ |
| payout outstanding = expected − received | `_insurance_derive` / receipt | ✅ |

## FINANCE (BusinessRulesService / FinanceService)
| Source | Code | Status |
|---|---|---|
| validatePaymentAmount_ (paid ≤ payable, provisional at 0) | `_add_payment_internal` (422 guard) | ✅ |
| Finance-mode shifts customer→financer liability | `_add_payment_internal` + `_upsert_finance_file` | ✅ |
| File outstanding = committed − disbursed | `_upsert_finance_file` / `/finance/{file}/receipt` | ✅ |

## CLAIMS / OWNER REPORTS (OemClaimService.gs)
| Source | Code | Status |
|---|---|---|
| ownerAggregates_ / buildOwnerCommercialReport_ | `/reports/owner-commercial` | ✅ |
| buildOemClaimDashboard_ | `/reports/oem-claim-dashboard` | ✅ |
| reconcileAllClaims_ / reconcileBooking_ | `/reports/claim-exceptions` | ✅ |
| Claim receipt accrual + history | `/claims/receipt` | ✅ |

## DEALER EARNINGS (ExtraIncomeService.gs)
| Source income line | Code | Status |
|---|---|---|
| Dealer Margin | `compute_dealer_margin` | ✅ |
| Scheme Retained | `compute_scheme_income_breakdown` | ✅ |
| Insurance Income | insurance expectedPayout aggregate | ✅ |
| OEM Extra Support retained | `oemExtraSupportRetained` | ✅ |
| Documentation Income | lead.documentationIncome → `dealer_earnings_report` (C1) | ✅ |
| Warranty Income | lead.warrantyIncome → `dealer_earnings_report` (C1) | ✅ |
| RSA Income | lead.rsaIncome → `dealer_earnings_report` (C1) | ✅ |
| Referral Income | lead.referralIncome → `dealer_earnings_report` (C1) | ✅ |

## DASHBOARD (DashboardService.gs)
| Source KPI | Code | Status |
|---|---|---|
| today/monthly leads, bookings, deliveries | `/dashboard` | ✅ |
| payments by mode; outstanding; model perf | `/dashboard` | ✅ |
| conversion %, MTD revenue | `/dashboard` kpis.conversion / kpis.revenue | ✅ |
| finance outstanding, follow-up due/overdue (H1) | `/dashboard` kpis.financeOutstanding / followupDue / followupOverdue | ✅ |

## NOT PORTED (Apps-Script runtime infra — N/A)
LockService, SyncEngine internals, SelfHealing/Backup/CrashReport/HealthCheck/PerformanceMonitor/VersionManagement, DataStore/SheetLayout, Dialogs UI. Replaced by MongoDB + FastAPI.
