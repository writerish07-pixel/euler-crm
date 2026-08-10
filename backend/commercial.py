"""
Commercial engine — faithful Python port of the Apps Script CommercialEngineService.

Single source of truth for commercial math:
  Gross Vehicle Cost, TCS, Total Discount, Customer Payable, Dealer Margin, Claims,
  and SCHEME ALLOCATION (compute_scheme_allocation).

Scheme allocation contract (every component):
  schemeAvailable, oemShare, dealerFundedShare, customerBenefit,
  dealerRetained = schemeAvailable − customerBenefit,
  oemClaimable   = oemShare (authoritative Scheme Master company share).

Customer Payable reduction = Σ customerBenefit (NOT schemeAvailable / oemShare / retained).
Dealer Scheme Earnings     = Σ dealerRetained.
OEM Claim                  = Σ oemClaimable.
Insurance Payout (premium × rate) is a SEPARATE ledger from Insurance Scheme Benefit.

Component policy (from Config.gs COMMERCIAL.COMPONENT_POLICY):
  consumerDiscount / exchangeBonus / loyaltyBonus / referralBonus -> OEM, claimable, no approval
  dsaDiscount -> OEM, claimable, approval required
  additionalDiscount -> Dealer, NOT claimable, dealer-funded (always passed to customer)
"""

TCS_RATE = 0.01
TCS_THRESHOLD = 1_000_000
DEALER_MARGIN_RATE = 0.04
DEALER_MARGIN_GST_RATE = 0.05

COMPONENT_POLICY = {
    "consumerDiscount":   {"col": "Consumer Discount",   "label": "Consumer Discount",   "payer": "OEM",    "approvalRequired": False, "claimable": True},
    "exchangeBonus":      {"col": "Exchange Bonus",       "label": "Exchange Bonus",      "payer": "OEM",    "approvalRequired": False, "claimable": True},
    "loyaltyBonus":       {"col": "Loyalty Bonus",        "label": "Loyalty Bonus",       "payer": "OEM",    "approvalRequired": False, "claimable": True},
    "referralBonus":      {"col": "Referral Bonus",       "label": "Referral Bonus",      "payer": "OEM",    "approvalRequired": False, "claimable": True},
    "dsaDiscount":        {"col": "DSA Discount",         "label": "DSA Bonus",           "payer": "OEM",    "approvalRequired": True,  "claimable": True},
    "additionalDiscount": {"col": "Additional Discount",  "label": "Additional Discount", "payer": "Dealer", "approvalRequired": True,  "claimable": False},
}
OFFER_KEYS = ["consumerDiscount", "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount", "additionalDiscount"]
BENEFIT_MODES = ["Full Benefit", "Partial Benefit", "No Benefit"]

# Entitlement-based scheme components: NOT typed as an offer amount by staff.
# They are auto-claimed from the Scheme Master's own dealer/company share whenever
# a row exists for the model/variant/month, regardless of what's on the lead
# (port of the schemeShareSplitFor_ `forceInclude` branch for 'rtoInsuranceBenefit',
# extended to the Aug'26 split RTO / Insurance benefit components).
AUTO_SCHEME_COMPONENT_KEYS = ["rtoInsuranceBenefit", "rtoBenefit", "insuranceBenefit"]

CHARGE_KEYS = ["exShowroom", "accessories", "insurance", "registrationRto", "fastag",
               "handlingCharges", "trc", "extendedWarranty", "rsaAmc", "otherCharges"]


def num(v):
    try:
        if v is None or v == "":
            return 0.0
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def round2(n):
    return round(num(n) * 100) / 100


def calculate_tcs(taxable, rate=TCS_RATE, threshold=TCS_THRESHOLD):
    taxable = max(0.0, num(taxable))
    if taxable < threshold:
        return 0.0
    return round2(taxable * rate)


def normalize_benefit_mode(mode):
    m = str(mode or "").strip().lower()
    if not m or m in ("full", "full benefit"):
        return "Full Benefit"
    if m in ("partial", "partial benefit"):
        return "Partial Benefit"
    if m in ("none", "no", "no benefit"):
        return "No Benefit"
    return "Full Benefit"


def _oem_offers(s):
    out = {}
    for key in OFFER_KEYS:
        pol = COMPONENT_POLICY.get(key)
        if not pol or pol["payer"] != "OEM":
            continue
        amt = max(0.0, num(s.get(key)))
        if amt > 0:
            out[key] = amt
    return out


def sum_oem_offers(s):
    return round2(sum(_oem_offers(s).values()))


def sum_dealer_offers(s):
    total = 0.0
    for key in OFFER_KEYS:
        pol = COMPONENT_POLICY.get(key)
        if not pol or pol["payer"] == "OEM":
            continue
        total += max(0.0, num(s.get(key)))
    return round2(total)


def _parse_benefit_breakup(s):
    """Normalize benefitPassedBreakup to a dict (or None)."""
    breakup = (s or {}).get("benefitPassedBreakup")
    if isinstance(breakup, str) and breakup:
        import json
        try:
            breakup = json.loads(breakup)
        except Exception:
            breakup = None
    return breakup if isinstance(breakup, dict) else None


def resolve_customer_benefit_passed(s, scheme_rows=None):
    """OEM + entitlement amount actually passed to the customer.

    When scheme_rows are available this delegates to compute_scheme_allocation
    (the single source of truth). Without scheme rows it falls back to the
    legacy offer-only benefit-mode logic so call sites that only have a charge
    snapshot (price preview, unit tests) keep working.
    """
    if scheme_rows is not None:
        alloc = compute_scheme_allocation(s, scheme_rows)
        # additionalDiscount is dealer-funded and counted separately as dealerDiscount
        return round2(sum(
            c["customerBenefit"] for c in alloc["components"]
            if c["key"] != "additionalDiscount"
        ))
    oem_pool = sum_oem_offers(s)
    mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))
    if mode == "No Benefit":
        return 0.0
    if mode == "Partial Benefit":
        breakup = _parse_benefit_breakup(s)
        if isinstance(breakup, dict):
            total = 0.0
            for key in OFFER_KEYS:
                pol = COMPONENT_POLICY.get(key)
                if not pol or pol["payer"] != "OEM":
                    continue
                cap = num(s.get(key))
                total += max(0.0, min(num(breakup.get(key)), cap))
            return round2(max(0.0, min(total, oem_pool)))
        passed = num(s.get("customerBenefitPassed"))
        return round2(max(0.0, min(passed, oem_pool)))
    return oem_pool  # Full Benefit


def compute_commercial_totals(s, scheme_rows=None):
    """The ONLY place Customer Payable is derived.

    Customer Payable may be reduced ONLY by amounts actually passed to the
    customer (Σ customerBenefit + OEM extra support passed). When scheme_rows
    are supplied, customerBenefit comes from compute_scheme_allocation.
    """
    s = s or {}
    gross_vehicle_cost = round2(sum(num(s.get(k)) for k in CHARGE_KEYS))
    tcs_applicable = str(s.get("tcsApplicable") or "No").lower() == "yes"
    tcs = calculate_tcs(gross_vehicle_cost) if tcs_applicable else 0.0

    oem_pool = sum_oem_offers(s)
    dealer_pool = sum_dealer_offers(s)
    oem_extra_passed = max(0.0, num(s.get("oemExtraSupportPassed")))
    benefit_mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))

    if scheme_rows is not None:
        alloc = compute_scheme_allocation(s, scheme_rows)
        # Scheme customer-payable reduction = Σ customerBenefit across every
        # component (offers + entitlements + dealer-funded additional).
        scheme_passed = alloc["totals"]["customerBenefit"]
        passed_oem = round2(sum(
            c["customerBenefit"] for c in alloc["components"]
            if c["key"] != "additionalDiscount"
        ))
        dealer_retained = alloc["totals"]["dealerRetained"]
        total_passed = round2(scheme_passed + oem_extra_passed)
    else:
        passed_oem = resolve_customer_benefit_passed(s)
        dealer_retained = round2(max(0.0, oem_pool - passed_oem))
        total_passed = round2(passed_oem + dealer_pool + oem_extra_passed)

    gross_invoice = round2(gross_vehicle_cost + tcs)
    net_vehicle_cost = round2(gross_invoice - total_passed)
    customer_payable = round2(net_vehicle_cost - num(s.get("finalExchangeValue")))
    return {
        "grossVehicleCost": gross_vehicle_cost,
        "tcs": tcs,
        "totalDiscount": round2(oem_pool + dealer_pool),
        "oemEligible": oem_pool,
        "dealerDiscount": dealer_pool,
        "customerBenefitPassed": passed_oem,
        "oemExtraSupportPassed": oem_extra_passed,
        "totalPassedToCustomer": total_passed,
        "dealerRetained": dealer_retained,
        "benefitMode": benefit_mode,
        "grossInvoiceAmount": gross_invoice,
        "netVehicleCost": net_vehicle_cost,
        "customerPayable": customer_payable,
    }


def compute_dealer_margin(s):
    """Dealer margin: 4% of pre-GST ex-showroom, then split 5% GST out of it."""
    ex_incl_gst = max(0.0, num(s.get("exShowroom")))
    pre_gst = round2(ex_incl_gst / (1 + DEALER_MARGIN_GST_RATE)) if DEALER_MARGIN_GST_RATE > 0 else ex_incl_gst
    gross_incl = round2(pre_gst * DEALER_MARGIN_RATE)
    net_ex = round2(gross_incl / (1 + DEALER_MARGIN_GST_RATE)) if DEALER_MARGIN_GST_RATE > 0 else gross_incl
    gst = round2(gross_incl - net_ex)
    return {
        "preGstExShowroom": pre_gst,
        "marginGrossInclGst": gross_incl,
        "marginGst": gst,
        "marginNetExGst": net_ex,
    }


def derive_claim(s, approvals=None):
    """Split discounts by payer and compute OEM-claimable amounts."""
    s = s or {}
    approvals = approvals or {}
    dealer_discount = oem_discount = claim_total = claim_eligible = 0.0
    breakdown = []
    for key in OFFER_KEYS:
        amt = round2(num(s.get(key)))
        if amt <= 0:
            continue
        pol = COMPONENT_POLICY.get(key)
        if not pol:
            continue
        approval_status = (approvals.get(key) or "Pending") if pol["approvalRequired"] else "N/A"
        # DSA applied on a booked deal is treated as approved unless explicitly rejected
        if key == "dsaDiscount" and pol["approvalRequired"] and amt > 0 and approval_status == "Pending":
            approval_status = "Approved"
        if pol["payer"] == "OEM":
            oem_discount = round2(oem_discount + amt)
        else:
            dealer_discount = round2(dealer_discount + amt)
        if pol["claimable"]:
            claim_total = round2(claim_total + amt)
            if not pol["approvalRequired"] or approval_status == "Approved":
                claim_eligible = round2(claim_eligible + amt)
        breakdown.append({
            "key": key, "label": pol["label"], "amount": amt, "payer": pol["payer"],
            "approvalRequired": pol["approvalRequired"], "approvalStatus": approval_status,
            "claimable": pol["claimable"],
        })
    return {
        "dealerDiscount": dealer_discount, "oemDiscount": oem_discount,
        "claimTotal": claim_total, "claimEligible": claim_eligible,
        "claimRequired": "Yes" if claim_total > 0 else "No", "breakdown": breakdown,
    }


# ===========================================================================
# SCHEME SHARE-SPLIT ENGINE — faithful port of SchemeMasterService.gs
# (schemeShareSplitFor_, getSchemeSharesForLead_, model/variant matchers) +
# CommercialEngineService.gs (computeSchemeIncomeBreakdown_, computeSchemeClaimShares_)
# ===========================================================================
import re
from datetime import datetime, timezone

# component key -> master label used for byComponent output
SCHEME_COMPONENT_LABELS = {
    "consumerDiscount": "Consumer Scheme",
    "exchangeBonus": "Exchange Benefit",
    "loyaltyBonus": "Loyalty",
    "referralBonus": "Referral",
    "dsaDiscount": "DSA",
    "additionalDiscount": "Additional Discount",
    "rtoInsuranceBenefit": "Free RTO + Free Insurance",
    "rtoBenefit": "RTO Benefit",
    "insuranceBenefit": "Insurance Benefit",
}


def _alnum(v):
    return re.sub(r"[^a-z0-9]", "", str(v or "").lower().strip())


def normalize_scheme_model_key(model, variant=""):
    raw = str(model or "").lower().strip()
    s = _alnum(raw)
    v_raw = str(variant or "").lower().strip()
    v = _alnum(v_raw)
    if "storm" in s or "strom" in s:
        return "storm"
    if "turbo" in s or "tyrbo" in s:
        return "turbo"
    if ("hirange" in s or "highrange" in s or "neohirange" in s
            or "high range" in raw or "hi range" in raw or "hi-range" in raw):
        return "hirange"
    if "hicity" in s or "hi city" in raw or "hi-city" in raw:
        return "hicity"
    if "hiload" in s:
        if v == "xr" or "hicity" in v_raw:
            return "hicity"
        return "hiload"
    if "hi load" in raw or "hi-load" in raw:
        return "hiload"
    return s


def normalize_scheme_variant_key(variant):
    s = _alnum(variant)
    if not s:
        return ""
    if "nongbt" in s or "trnc" in s:
        return "nongbt"
    if "withgbt" in s or ("gbt" in s and "nongbt" not in s):
        return "gbt"
    if s == "xr" or s.startswith("xr"):
        return "xr"
    if s == "tr" or s.startswith("tr"):
        return "tr"
    if s == "sr" or s.startswith("sr"):
        return "sr"
    return s


def models_match_scheme(lead_model, master_model, lead_variant=""):
    return normalize_scheme_model_key(lead_model, lead_variant) == normalize_scheme_model_key(master_model)


def variants_match_scheme(lead_variant, master_variant, master_model):
    mv = str(master_variant or "").strip()
    if not mv:
        return True  # Storm / Turbo — any variant
    a = normalize_scheme_variant_key(lead_variant)
    b = normalize_scheme_variant_key(mv)
    if a == b:
        return True
    family = normalize_scheme_model_key(master_model)
    if family == "hiload":
        if not a:
            return True
        if b == "nongbt":
            return a != "gbt"
    if family in ("hicity", "hirange"):
        if b == "xr" and (a == "xr" or "xr" in a):
            return True
        if b == "tr" and (a == "tr" or a.startswith("tr")):
            return True
    return False


def scheme_month_from_date(date_iso):
    d = str(date_iso or "")[:10]
    if re.match(r"^\d{4}-\d{2}", d):
        return d[:7]
    return d[:7]


def _norm_month(value):
    s = str(value or "").strip()
    if re.match(r"^\d{4}-\d{2}", s):
        return s[:7]
    return s


def get_scheme_shares_for_lead(model, variant, booking_date, scheme_rows):
    """Active scheme rows for a lead model/variant on a booking date -> map componentKey -> shares.

    booking_date falls back to today's date when empty (e.g. Scheme applied before Booking,
    which the API allows since canScheme only requires an Active lead, not a Booked one) so the
    effective date is always deterministic. Previously an empty booking_date produced iso="",
    which silently disabled the effectiveFrom/effectiveTo window check below (`iso and ...`
    short-circuited to False) -- every active Scheme Master row for the model, from every
    circular month, was treated as "in window" and merged by componentKey. That was harmless
    when a component's key stayed the same across months (the later month simply overwrote the
    earlier one), but broke silently when a component's key changed between circulars (e.g. July's
    combined 'rtoInsuranceBenefit' vs August's split 'rtoBenefit'+'insuranceBenefit') -- the merge
    doesn't overwrite distinct keys, it adds them, double-claiming the same entitlement. Falling
    back to today's date makes Scheme-before-Booking and Scheme-after-Booking resolve to the
    identical Scheme Master rows for the same business date."""
    effective_date = str(booking_date or "")[:10]
    if not effective_date:
        effective_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    month = scheme_month_from_date(effective_date)
    iso = effective_date
    exact, in_window, any_family = {}, {}, {}
    for r in (scheme_rows or []):
        if str(r.get("status") or "").lower() != "active":
            continue
        if not models_match_scheme(model, r.get("model"), variant):
            continue
        if not variants_match_scheme(variant, r.get("variant"), r.get("model")):
            continue
        key = r.get("componentKey")
        if not key:
            continue
        r_month = _norm_month(r.get("schemeMonth") or month)
        payload = {
            "dealerShare": num(r.get("dealerShare")),
            "companyShare": num(r.get("companyShare")),
            "totalBenefit": num(r.get("totalBenefit")) or (num(r.get("dealerShare")) + num(r.get("companyShare"))),
            "label": r.get("component") or SCHEME_COMPONENT_LABELS.get(key, key),
            "schemeMonth": r_month,
        }
        eff_from = str(r.get("effectiveFrom") or "")[:10]
        eff_to = str(r.get("effectiveTo") or "")[:10]
        window_ok = True
        if eff_from and iso and iso < eff_from:
            window_ok = False
        if eff_to and iso and iso > eff_to:
            window_ok = False
        if r_month == month and window_ok:
            exact[key] = payload
        if window_ok:
            if key not in in_window or r_month >= str(in_window[key].get("schemeMonth") or ""):
                in_window[key] = payload
        if key not in any_family or r_month >= str(any_family[key].get("schemeMonth") or ""):
            any_family[key] = payload
    if exact:
        return exact
    if in_window:
        return in_window
    return any_family


def scheme_share_split_for(model, variant, booking_date, offers, scheme_rows):
    """PURE share splitter — company share applied FIRST (partial/under-package rule)."""
    master = get_scheme_shares_for_lead(model, variant, booking_date, scheme_rows)
    by_component = {}
    dealer_total = 0.0
    company_total = 0.0
    for key in ["consumerDiscount", "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount"]:
        m = master.get(key)
        actual = num((offers or {}).get(key))
        if not m or actual <= 0:
            continue
        company = min(num(m.get("companyShare")), actual)
        company = round2(company)
        dealer = round2(min(num(m.get("dealerShare")), max(0.0, actual - company)))
        by_component[key] = {"actual": actual, "dealerShare": dealer,
                             "companyShare": company, "label": m.get("label") or key}
        dealer_total = round2(dealer_total + dealer)
        company_total = round2(company_total + company)
    addl = num((offers or {}).get("additionalDiscount"))
    if addl > 0:
        by_component["additionalDiscount"] = {"actual": addl, "dealerShare": addl,
                                              "companyShare": 0.0, "label": "Additional Discount"}
        dealer_total = round2(dealer_total + addl)
    # Entitlement-based components (Free RTO+Insurance / RTO Benefit / Insurance
    # Benefit): auto-claimed at the Scheme Master's own share whenever a row
    # exists, even though staff never typed an offer amount for them.
    for auto_key in AUTO_SCHEME_COMPONENT_KEYS:
        m = master.get(auto_key)
        if not m or num(m.get("companyShare")) <= 0:
            continue
        company = round2(num(m.get("companyShare")))
        dealer = round2(num(m.get("dealerShare")))
        actual = round2(num(m.get("totalBenefit")) or (company + dealer))
        by_component[auto_key] = {"actual": actual, "dealerShare": dealer,
                                  "companyShare": company,
                                  "label": m.get("label") or SCHEME_COMPONENT_LABELS.get(auto_key, auto_key)}
        dealer_total = round2(dealer_total + dealer)
        company_total = round2(company_total + company)
    return {"dealerTotal": dealer_total, "companyTotal": company_total,
            "byComponent": by_component, "schemeMonth": scheme_month_from_date(booking_date),
            "model": model, "variant": variant}


def resolve_passed_breakup(s, scheme_rows=None):
    """Full vs passed amounts per component, honouring benefit mode.

    When scheme_rows are given, values come from compute_scheme_allocation
    (includes entitlements). Otherwise falls back to offer-only mode logic.
    """
    mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))
    if scheme_rows is not None:
        alloc = compute_scheme_allocation(s, scheme_rows)
        full, passed = {}, {}
        for c in alloc["components"]:
            if c["key"] == "additionalDiscount":
                continue
            if c["schemeAvailable"] > 0:
                full[c["key"]] = c["schemeAvailable"]
            if c["customerBenefit"] > 0:
                passed[c["key"]] = c["customerBenefit"]
        return {"full": full, "passed": passed, "mode": mode}
    full, passed = {}, {}
    for key in OFFER_KEYS:
        pol = COMPONENT_POLICY.get(key)
        if not pol or pol["payer"] != "OEM":
            continue
        amt = max(0.0, num(s.get(key)))
        if amt > 0:
            full[key] = amt
    if mode == "Full Benefit":
        passed = dict(full)
    elif mode == "Partial Benefit":
        breakup = _parse_benefit_breakup(s)
        if isinstance(breakup, dict):
            for k, cap in full.items():
                passed[k] = max(0.0, min(num(breakup.get(k)), cap))
        else:
            remaining = max(0.0, num(s.get("customerBenefitPassed")))
            for k in OFFER_KEYS:
                if k not in full:
                    continue
                take = min(full[k], remaining)
                passed[k] = take
                remaining = round2(remaining - take)
    return {"full": full, "passed": passed, "mode": mode}


def _component_customer_benefit(key, scheme_available, mode, breakup, s, offer_waterfall):
    """Resolve numeric customerBenefit for one component.

    Formulas:
      customerBenefit ∈ [0, schemeAvailable]
      dealerRetained  = schemeAvailable − customerBenefit   (computed by caller)

    Explicit assignment model (schemeAllocationExplicit):
      Scheme Master eligibility ≠ assignment. Missing breakup key ⇒ CB = 0.
      Only an explicit benefitPassedBreakup amount assigns customer benefit.
      Benefit Mode is ignored for CB resolution when explicit.

    Legacy (non-explicit) — preserved for historical leads / older API clients:
      Explicit benefitPassedBreakup[key] still wins when present.
      No Benefit → 0; Full Benefit → schemeAvailable; Partial → breakup/waterfall.
      schemeAllocationV2 grandfathering: entitlements absent from breakup stay CB=0
      under Full Benefit when V2 is unset (no silent historical rewrite).
    """
    cap = max(0.0, num(scheme_available))
    if key == "additionalDiscount":
        return round2(cap)  # dealer-funded — always passed to customer

    # Explicit per-component allocation is authoritative when present.
    if isinstance(breakup, dict) and key in breakup:
        return round2(max(0.0, min(num(breakup.get(key)), cap)))

    # New UI / explicit saves: eligibility alone never assigns customer benefit.
    if bool(s.get("schemeAllocationExplicit")):
        return 0.0

    # Grandfather pre-V2 entitlement rows that never recorded an allocation key.
    v2 = bool(s.get("schemeAllocationV2"))
    if key in AUTO_SCHEME_COMPONENT_KEYS and not v2:
        return 0.0

    if mode == "No Benefit":
        return 0.0
    if mode == "Full Benefit":
        return round2(cap)
    # Partial Benefit without an explicit key: offer waterfall (legacy) or 0.
    if key in AUTO_SCHEME_COMPONENT_KEYS:
        return 0.0
    take = min(cap, max(0.0, num(offer_waterfall.get(key))))
    return round2(take)


def _offer_partial_waterfall(s, full_by_key):
    """Distribute a single customerBenefitPassed total across offer keys in order."""
    remaining = max(0.0, num(s.get("customerBenefitPassed")))
    out = {}
    for k in OFFER_KEYS:
        if k not in full_by_key:
            continue
        take = min(full_by_key[k], remaining)
        out[k] = take
        remaining = round2(remaining - take)
    return out


# ============================================================================

def _explicit_allocation(s):
    """Persisted per-component customer benefit: {componentKey: amount}.

    Ignores engine summary objects (those have 'components'/'totals') so they are
    never mistaken for dealer allocation decisions.
    """
    raw = s.get("schemeAllocation")
    if isinstance(raw, str) and raw.strip():
        import json
        try:
            raw = json.loads(raw)
        except Exception:
            raw = None
    if not isinstance(raw, dict):
        return {}
    if "components" in raw or "totals" in raw:
        return {}
    out = {}
    for k, v in raw.items():
        if isinstance(v, (dict, list)):
            continue
        out[str(k)] = num(v)
    return out


def compute_scheme_allocation(s, scheme_rows):
    """AUTHORITATIVE scheme allocation engine — single source of truth.

    For every active scheme component returns the six independent values:

      schemeAvailable    — total entitlement under the scheme
      oemShare           — contractual OEM/company share (oemClaimable)
      dealerFundedShare  — portion funded by the dealer (contractual; ≠ retained)
      customerBenefit    — amount the dealer actually passes to the customer
      dealerRetained     — schemeAvailable − customerBenefit
      oemClaimable       — amount claimable from OEM (== oemShare)

    schemeAllocationExplicit:
      Eligible offer components are included from Scheme Master even when the
      lead offer field is 0 (eligibility ≠ assignment). Customer benefit comes
      only from benefitPassedBreakup — never auto-filled from Benefit Mode.

    Insurance Payout (premium × rate) is a SEPARATE ledger and must never appear here.
    """
    s = s or {}
    mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))
    breakup = _parse_benefit_breakup(s)
    # Flat schemeAllocation decision map (PUT /scheme-allocation) merges under
    # benefitPassedBreakup so both persistence shapes feed one engine. Breakup wins
    # on key conflict. Summary objects from recompute_lead are ignored.
    flat_decisions = _explicit_allocation(s)
    if flat_decisions or isinstance(breakup, dict):
        merged = {}
        if isinstance(breakup, dict):
            merged.update(breakup)
        # Flat schemeAllocation decisions (PUT /scheme-allocation) win on conflict.
        merged.update(flat_decisions or {})
        breakup = merged
    explicit = bool(s.get("schemeAllocationExplicit")) or bool(flat_decisions)
    model = str(s.get("model") or s.get("interestedModel") or "").strip()
    variant = str(s.get("variant") or "").strip()
    booking_date = s.get("bookingDate") or ""
    master = get_scheme_shares_for_lead(model, variant, booking_date, scheme_rows) if (model and scheme_rows) else {}

    # Pre-compute offer available amounts so Partial waterfall can run once
    offer_full = {}
    for key in ["consumerDiscount", "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount"]:
        m = master.get(key)
        master_total = 0.0
        if m:
            master_total = num(m.get("totalBenefit")) or (num(m.get("dealerShare")) + num(m.get("companyShare")))
        actual = max(0.0, num(s.get(key)))
        if explicit and master_total > 0:
            # Eligibility from Scheme Master — available is the master amount.
            # Lead offer field may still carry a typed amount for legacy columns;
            # never exceed master_total.
            offer_full[key] = round2(min(actual, master_total) if actual > 0 else master_total)
        elif actual > 0:
            if m and master_total > 0:
                offer_full[key] = round2(min(actual, master_total))
            else:
                offer_full[key] = round2(actual)
    waterfall = {}
    if (not explicit) and mode == "Partial Benefit" and not (isinstance(breakup, dict) and any(k in breakup for k in offer_full)):
        waterfall = _offer_partial_waterfall(s, offer_full)

    components = []

    def _push(key, label, scheme_available, oem_share, dealer_funded_share, source):
        scheme_available = round2(max(0.0, num(scheme_available)))
        oem_share = round2(max(0.0, num(oem_share)))
        dealer_funded_share = round2(max(0.0, num(dealer_funded_share)))
        customer_benefit = _component_customer_benefit(
            key, scheme_available, mode, breakup, s, waterfall)
        # Never invent negative retention — clamp at 0 unless an explicit rule
        # requires it (none does under this contract).
        dealer_retained = round2(max(0.0, scheme_available - customer_benefit))
        used_map = s.get("schemeComponentsUsed") or {}
        if isinstance(used_map, str):
            try:
                import json as _json
                used_map = _json.loads(used_map) if used_map.strip() else {}
            except Exception:
                used_map = {}
        if not isinstance(used_map, dict):
            used_map = {}
        if key in used_map:
            used = bool(used_map.get(key))
        else:
            used = customer_benefit > 0
        components.append({
            "key": key,
            "label": label,
            "schemeAvailable": scheme_available,
            "oemShare": oem_share,
            "dealerFundedShare": dealer_funded_share,
            "customerBenefit": customer_benefit,
            "dealerRetained": dealer_retained,
            "oemClaimable": oem_share,
            "source": source,
            # Compat for callers that filter entitlements via `automatic`
            # (scheme-allocation impact report / older recompute paths).
            "automatic": source == "entitlement" or key in AUTO_SCHEME_COMPONENT_KEYS,
            "used": used,
        })

    # --- Staff-entered OEM offer components ---
    for key in ["consumerDiscount", "exchangeBonus", "loyaltyBonus", "referralBonus", "dsaDiscount"]:
        if key not in offer_full:
            continue
        scheme_available = offer_full[key]
        m = master.get(key)
        if m:
            # Company-share-first: OEM claimable capped by available; dealer funded
            # takes the remainder up to its master share.
            oem_share = round2(min(num(m.get("companyShare")), scheme_available))
            dealer_funded_share = round2(min(
                num(m.get("dealerShare")), max(0.0, scheme_available - oem_share)))
            label = m.get("label") or SCHEME_COMPONENT_LABELS.get(key, key)
        else:
            # No Scheme Master row — treat the typed offer as 100% company-funded.
            oem_share = scheme_available
            dealer_funded_share = 0.0
            label = SCHEME_COMPONENT_LABELS.get(key, key)
        _push(key, label, scheme_available, oem_share, dealer_funded_share, "offer")

    # --- Dealer-funded additional discount (always passed; never claimable) ---
    addl = max(0.0, num(s.get("additionalDiscount")))
    if addl > 0:
        _push("additionalDiscount", "Additional Discount", addl, 0.0, addl, "dealer")

    # --- Entitlement components from Scheme Master (not staff-typed offers) ---
    for auto_key in AUTO_SCHEME_COMPONENT_KEYS:
        m = master.get(auto_key)
        if not m:
            continue
        company = round2(num(m.get("companyShare")))
        dealer = round2(num(m.get("dealerShare")))
        total = round2(num(m.get("totalBenefit")) or (company + dealer))
        if total <= 0 and company <= 0:
            continue
        label = m.get("label") or SCHEME_COMPONENT_LABELS.get(auto_key, auto_key)
        _push(auto_key, label, total, company, dealer, "entitlement")

    totals = {
        "schemeAvailable": round2(sum(c["schemeAvailable"] for c in components)),
        "customerBenefit": round2(sum(c["customerBenefit"] for c in components)),
        "dealerRetained": round2(sum(c["dealerRetained"] for c in components)),
        "oemClaimable": round2(sum(c["oemClaimable"] for c in components)),
        "dealerFundedShare": round2(sum(c["dealerFundedShare"] for c in components)),
        "oemShare": round2(sum(c["oemShare"] for c in components)),
    }
    by_key = {c["key"]: c for c in components}
    return {
        "components": components,
        "totals": totals,
        "byKey": by_key,
        "benefitMode": mode,
        "schemeMonth": scheme_month_from_date(booking_date),
        "model": model,
        "variant": variant,
        "shareSplitAvailable": bool(master) or bool(components),
        "explicit": explicit,
    }


def compute_scheme_income_breakdown(s, scheme_rows):
    """Dealer retained income + OEM claim total per component.

    Thin adapter over compute_scheme_allocation — do NOT invent a second formula.
    retained = schemeAvailable − customerBenefit
    oemClaim = oemShare (authoritative company share)
    """
    alloc = compute_scheme_allocation(s, scheme_rows)
    out = {
        "retainedIncomeTotal": alloc["totals"]["dealerRetained"],
        "retainedByComponent": {},
        "oemClaimTotal": alloc["totals"]["oemClaimable"],
        "oemClaimByComponent": {},
        "dealerCostPassed": 0.0,
        "passedByComponent": {},
        "fullByComponent": {},
        "shareSplitAvailable": alloc["shareSplitAvailable"],
        "allocation": alloc,
    }
    for c in alloc["components"]:
        k = c["key"]
        if c["dealerRetained"] != 0:
            out["retainedByComponent"][k] = c["dealerRetained"]
        if c["oemClaimable"] > 0:
            out["oemClaimByComponent"][k] = c["oemClaimable"]
        if c["customerBenefit"] > 0:
            out["passedByComponent"][k] = c["customerBenefit"]
        if c["schemeAvailable"] > 0 and k != "additionalDiscount":
            out["fullByComponent"][k] = c["schemeAvailable"]
        # Dealer-funded portion that was passed through to the customer
        if c["dealerFundedShare"] > 0 and c["customerBenefit"] > 0:
            passed_dealer = min(c["dealerFundedShare"], c["customerBenefit"])
            out["dealerCostPassed"] = round2(out["dealerCostPassed"] + passed_dealer)
    return out


def compute_scheme_claim_shares(s, scheme_rows, approvals=None):
    """Company-share amounts for claim register: display (all) vs eligible (DSA needs approval).

    Reads oemClaimable from compute_scheme_allocation — never invents a parallel total.
    """
    approvals = approvals or {}
    alloc = compute_scheme_allocation(s, scheme_rows)
    out = {"displayByComponent": {}, "eligibleByComponent": {},
           "displayTotal": 0.0, "eligibleTotal": 0.0,
           "shareSplitAvailable": alloc["shareSplitAvailable"],
           "allocation": alloc}
    for c in alloc["components"]:
        claimable = c["oemClaimable"]
        if claimable <= 0:
            continue
        k = c["key"]
        out["displayByComponent"][k] = claimable
        out["displayTotal"] = round2(out["displayTotal"] + claimable)
        pol = COMPONENT_POLICY.get(k)
        status = approvals.get(k) or "Pending"
        if k == "dsaDiscount" and pol and pol.get("approvalRequired") and status == "Pending" and claimable > 0:
            status = "Approved"
        if pol and pol.get("approvalRequired") and status != "Approved":
            continue
        out["eligibleByComponent"][k] = claimable
        out["eligibleTotal"] = round2(out["eligibleTotal"] + claimable)
    return out


def additional_discount_choices():
    return [0, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 40000, 50000]


def build_scheme_amount_choices(dealer_share, company_share, total_max):
    max_amt = round2(total_max)
    out = set()

    def add(v):
        n = round2(v)
        if n < 0:
            return
        if max_amt > 0 and n > max_amt + 0.009:
            return
        out.add(n)
    add(0)
    if max_amt > 0:
        add(dealer_share)
        add(company_share)
        add(max_amt)
        if max_amt >= 10000:
            add(round2(max_amt / 2))
    return sorted(out)


FAMILY_LABELS = {
    "hiload": "HiLoad / Hi-Load",
    "hicity": "HiCity",
    "hirange": "Hirange / Neo HiRange / High Range",
    "turbo": "Turbo / Turbo Max",
    "storm": "Storm",
}

# Insurer payout rate of premium (InsuranceService.getSuggestedInsurancePayoutRate_)
INSURANCE_RATE_STORM_TURBO = 0.49
INSURANCE_RATE_OTHER = 0.365


# ===========================================================================
# INCENTIVE REGISTER — port of SchemeMasterService.gs mapLeadToIncentiveCategory_ /
# getIncentiveRateForLead_ / upsertIncentiveRegisterOnDelivery_. Extended for the
# Aug'26 Manpower Incentive Power Drive circular, which splits HiCity and HiRange
# into their own categories (previously both folded into '3WC' with HiLoad).
# ===========================================================================
INCENTIVE_CATEGORY_LABELS = {
    "hiload": "3WC",
    "hicity": "Hi-City (SR & TR)",
    "hirange": "HiRange",
    "storm": "Storm",
    "turbo": "Turbo",
}


def map_lead_to_incentive_category(model, variant=""):
    fam = normalize_scheme_model_key(model, variant)
    return INCENTIVE_CATEGORY_LABELS.get(fam, "Pax")


def get_incentive_rate_for_lead(model, variant, delivery_date, incentive_rows):
    """Active Incentive Master row for the lead's category + delivery month, or None."""
    month = scheme_month_from_date(delivery_date)
    cat = map_lead_to_incentive_category(model, variant)
    for r in (incentive_rows or []):
        if str(r.get("status") or "").lower() != "active":
            continue
        if _norm_month(r.get("schemeMonth")) != month:
            continue
        if str(r.get("productCategory") or "").strip().lower() != cat.lower():
            continue
        return r
    return None


def suggested_insurance_payout_rate(model, variant=""):
    """Storm/Turbo -> 49%, all other models -> 36.5% (decimal)."""
    fam = normalize_scheme_model_key(model, variant)
    if fam in ("storm", "turbo"):
        return INSURANCE_RATE_STORM_TURBO
    return INSURANCE_RATE_OTHER


def get_scheme_offer_rules_for_vehicle(model, variant, booking_date, scheme_rows):
    """Which scheme offer fields are allowed for Model+Variant on a booking date (port of getSchemeOfferRulesForVehicle_)."""
    master = get_scheme_shares_for_lead(model, variant, booking_date, scheme_rows)
    rules = {}
    model_disp = str(model or "").strip() or "selected model"
    variant_disp = str(variant or "").strip()
    month = scheme_month_from_date(booking_date)
    master_keys = list(master.keys())
    family = normalize_scheme_model_key(model, variant)
    family_label = FAMILY_LABELS.get(family, model_disp)
    for key in OFFER_KEYS:
        label = COMPONENT_POLICY[key]["label"]
        if key == "additionalDiscount":
            add_choices = additional_discount_choices()
            rules[key] = {"key": key, "label": label, "allowed": True,
                          "maxAmount": add_choices[-1], "choices": add_choices,
                          "hint": f"Dealer-funded — type any amount (max \u20b9{add_choices[-1]})"}
            continue
        m = master.get(key)
        if not m:
            note = (f"Not available for {model_disp}" + (f" / {variant_disp}" if variant_disp else "") + " in Scheme Master") \
                if master_keys else \
                (f"No Scheme Master row for {family_label} in {month}. Check Scheme Month = {month} and Status = Active.")
            rules[key] = {"key": key, "label": label, "allowed": False,
                          "maxAmount": 0, "choices": [0], "hint": note}
            continue
        total = num(m.get("totalBenefit"))
        if not total or total <= 0:
            total = round2(num(m.get("dealerShare")) + num(m.get("companyShare")))
        if total <= 0:
            rules[key] = {"key": key, "label": label, "allowed": False, "maxAmount": 0,
                          "choices": [0], "hint": f"Scheme Master total is \u20b90 for {label} on this model"}
            continue
        dealer = round2(num(m.get("dealerShare")))
        company = round2(num(m.get("companyShare")))
        max_amt = round2(total)
        rules[key] = {"key": key, "label": label, "allowed": True, "maxAmount": max_amt,
                      "dealerShare": dealer, "companyShare": company,
                      "schemeAvailable": max_amt, "oemShare": company,
                      "dealerFundedShare": dealer, "oemClaimable": company,
                      "allocatable": True,
                      "choices": build_scheme_amount_choices(dealer, company, max_amt),
                      "hint": f"Enter amount up to ₹{max_amt} (Scheme Master {m.get('label', '')} · {month}). "
                              f"Then allocate how much of that amount passes to the customer."}
    # Entitlement components (Free RTO / Free Insurance) are NOT staff-entered offers, so
    # they have no rule/input — but they are part of the scheme and are claimed from the
    # OEM automatically. They must still be visible, or the Scheme screen understates the
    # scheme (e.g. Turbo Aug'26 showing only Loyalty 10,000 while the Claim Register
    # correctly carries Loyalty 10,000 + Insurance Benefit 10,000).
    entitlements = []
    for key in AUTO_SCHEME_COMPONENT_KEYS:
        m = master.get(key)
        if not m:
            continue
        company = round2(num(m.get("companyShare")))
        dealer = round2(num(m.get("dealerShare")))
        total = round2(num(m.get("totalBenefit")) or (company + dealer))
        if total <= 0 and company <= 0:
            continue
        entitlements.append({
            "key": key,
            "label": m.get("label") or SCHEME_COMPONENT_LABELS.get(key, key),
            "dealerShare": dealer, "companyShare": company, "totalBenefit": total,
            # Allocation contract fields (Scheme Master is authoritative for these).
            "schemeAvailable": total,
            "oemShare": company,
            "dealerFundedShare": dealer,
            "oemClaimable": company,
            "automatic": True,
            "allocatable": True,
            "hint": (
                f"Eligible from Scheme Master — available ₹{total}, "
                f"OEM claimable ₹{company}"
                + (f", dealer contractual ₹{dealer}" if dealer > 0 else "")
                + ". Dealer must explicitly choose Use Scheme and Customer Benefit."
            ),
        })
    return {"schemeMonth": month, "model": model_disp, "variant": variant_disp,
            "modelFamily": family, "matchedComponents": master_keys, "rules": rules,
            "entitlements": entitlements,
            "entitlementCompanyTotal": round2(sum(e["companyShare"] for e in entitlements)),
            "entitlementDealerTotal": round2(sum(e["dealerShare"] for e in entitlements))}


def validate_scheme_offers(model, variant, booking_date, offers, scheme_rows):
    """Port of validateSchemeOffersForVehicle_ — returns list of error lines (empty = OK)."""
    ctx = get_scheme_offer_rules_for_vehicle(model, variant, booking_date, scheme_rows)
    lines = []
    model_disp = ctx["model"]
    variant_part = f" / {ctx['variant']}" if ctx["variant"] else ""
    has_master = len(ctx["matchedComponents"]) > 0
    for key, val in (offers or {}).items():
        rule = ctx["rules"].get(key)
        if not rule:
            continue
        amt = round2(num(val))
        if amt < 0:
            lines.append(f"\u2022 {rule['label']}: amount cannot be negative")
            continue
        if key == "additionalDiscount":
            if rule.get("maxAmount") is not None and amt > num(rule["maxAmount"]) + 0.01:
                lines.append(f"\u2022 {rule['label']}: \u20b9{amt} exceeds maximum \u20b9{rule['maxAmount']}")
            continue
        if amt <= 0:
            continue
        if not has_master:
            continue
        if not rule["allowed"] or not (num(rule["maxAmount"]) > 0):
            lines.append(f"\u2022 {rule['label']}: not in Scheme Master for {model_disp}{variant_part} — enter 0")
            continue
        if amt > num(rule["maxAmount"]) + 0.01:
            lines.append(f"\u2022 {rule['label']}: \u20b9{amt} exceeds Scheme Master max \u20b9{rule['maxAmount']}")
    return lines


def validate_scheme_allocation_breakup(model, variant, booking_date, breakup, scheme_rows):
    """Validate explicit per-component customerBenefit decisions against Scheme Master.

    Returns a list of error lines (empty = OK). Rejects unknown keys, non-numeric /
    negative amounts, and amounts above schemeAvailable. Eligibility comes only from
    Scheme Master — unknown or ineligible keys are rejected.
    """
    if breakup is None:
        return []
    if isinstance(breakup, str):
        try:
            import json as _json
            breakup = _json.loads(breakup) if breakup.strip() else {}
        except Exception:
            return ["• benefitPassedBreakup must be valid JSON"]
    if not isinstance(breakup, dict):
        return ["• benefitPassedBreakup must be an object of component → amount"]

    ctx = get_scheme_offer_rules_for_vehicle(model, variant, booking_date, scheme_rows)
    eligible = {}
    for key, rule in (ctx.get("rules") or {}).items():
        if key == "additionalDiscount":
            continue
        if rule.get("allowed") and num(rule.get("maxAmount") or rule.get("schemeAvailable")) > 0:
            eligible[key] = num(rule.get("schemeAvailable") or rule.get("maxAmount"))
    for ent in ctx.get("entitlements") or []:
        eligible[ent["key"]] = num(ent.get("schemeAvailable") or ent.get("totalBenefit"))

    lines = []
    for key, raw in breakup.items():
        if key == "additionalDiscount":
            continue
        if key not in eligible:
            lines.append(f"• Unknown or ineligible scheme component: {key}")
            continue
        try:
            amt = float(raw)
        except (TypeError, ValueError):
            lines.append(f"• {key}: customer benefit must be numeric")
            continue
        if amt < 0:
            lines.append(f"• {key}: customer benefit cannot be negative")
            continue
        avail = eligible[key]
        if amt > avail + 0.01:
            lines.append(f"• {key}: customer benefit ₹{round2(amt)} exceeds available ₹{round2(avail)}")
    return lines



def compute_full_commercials(s, scheme_rows=None):
    """Convenience: returns totals + margin + claim (+ scheme allocation when scheme rows given)."""
    totals = compute_commercial_totals(s, scheme_rows)
    margin = compute_dealer_margin(s)
    claim = derive_claim(s)
    result = {**totals, "margin": margin, "claim": claim}
    if scheme_rows is not None:
        alloc = compute_scheme_allocation(s, scheme_rows)
        income = compute_scheme_income_breakdown(s, scheme_rows)
        shares = compute_scheme_claim_shares(s, scheme_rows)
        result["schemeAllocation"] = alloc
        result["schemeIncome"] = income
        result["schemeClaimShares"] = shares
        # Report-facing truths — all from the single allocation engine
        result["oemClaimCompanyShare"] = shares["eligibleTotal"]
        result["dealerSchemeRetained"] = income["retainedIncomeTotal"]
        result["schemeCustomerBenefit"] = alloc["totals"]["customerBenefit"]
        result["schemeOemClaimable"] = alloc["totals"]["oemClaimable"]
    return result
