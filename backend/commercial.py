"""
Commercial engine — faithful Python port of the Apps Script CommercialEngineService.

Single source of truth for all commercial math:
  Gross Vehicle Cost, TCS, Total Discount, Customer Payable, Dealer Margin, Claims.

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


def resolve_customer_benefit_passed(s):
    oem_pool = sum_oem_offers(s)
    mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))
    if mode == "No Benefit":
        return 0.0
    if mode == "Partial Benefit":
        breakup = s.get("benefitPassedBreakup")
        if isinstance(breakup, str) and breakup:
            import json
            try:
                breakup = json.loads(breakup)
            except Exception:
                breakup = None
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


def compute_commercial_totals(s):
    """The ONLY place Customer Payable is derived."""
    s = s or {}
    gross_vehicle_cost = round2(sum(num(s.get(k)) for k in CHARGE_KEYS))
    tcs_applicable = str(s.get("tcsApplicable") or "No").lower() == "yes"
    tcs = calculate_tcs(gross_vehicle_cost) if tcs_applicable else 0.0

    oem_pool = sum_oem_offers(s)
    dealer_pool = sum_dealer_offers(s)
    passed_oem = resolve_customer_benefit_passed(s)
    oem_extra_passed = max(0.0, num(s.get("oemExtraSupportPassed")))
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
        "benefitMode": normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode")),
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


def resolve_passed_breakup(s):
    """Full vs passed OEM offer amounts per component, honouring benefit mode."""
    mode = normalize_benefit_mode(s.get("benefitMode") or s.get("customerBenefitMode"))
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
        breakup = s.get("benefitPassedBreakup")
        if isinstance(breakup, str) and breakup:
            import json
            try:
                breakup = json.loads(breakup)
            except Exception:
                breakup = None
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
    # No Benefit -> passed stays {}
    return {"full": full, "passed": passed, "mode": mode}


def compute_scheme_income_breakdown(s, scheme_rows):
    """Dealer retained income (company unpassed − dealer passed) + OEM claim total per component."""
    bk = resolve_passed_breakup(s)
    model = str(s.get("model") or s.get("interestedModel") or "").strip()
    variant = str(s.get("variant") or "").strip()
    booking_date = s.get("bookingDate") or ""
    offers_all = _oem_offers(s)
    out = {"retainedIncomeTotal": 0.0, "retainedByComponent": {}, "oemClaimTotal": 0.0,
           "oemClaimByComponent": {}, "dealerCostPassed": 0.0,
           "passedByComponent": bk["passed"], "fullByComponent": bk["full"], "shareSplitAvailable": False}
    if model and scheme_rows:
        full_split = scheme_share_split_for(model, variant, booking_date, offers_all, scheme_rows)
        pass_split = scheme_share_split_for(model, variant, booking_date, bk["passed"], scheme_rows)
        f_by = full_split["byComponent"]
        p_by = pass_split["byComponent"]
        keys = set(list(f_by.keys()) + list(p_by.keys()))
        for k in keys:
            c_full = num(f_by.get(k, {}).get("companyShare"))
            c_pass = num(p_by.get(k, {}).get("companyShare"))
            d_pass = num(p_by.get(k, {}).get("dealerShare"))
            retained = round2((c_full - c_pass) - d_pass)
            if c_full > 0:
                out["oemClaimByComponent"][k] = c_full
            if retained != 0:
                out["retainedByComponent"][k] = retained
            out["oemClaimTotal"] = round2(out["oemClaimTotal"] + c_full)
            out["retainedIncomeTotal"] = round2(out["retainedIncomeTotal"] + retained)
            out["dealerCostPassed"] = round2(out["dealerCostPassed"] + d_pass)
        has_oem_offer = len(bk["full"]) > 0
        out["shareSplitAvailable"] = (out["oemClaimTotal"] > 0) if has_oem_offer else True
        return out
    # Fallback: treat each component as 100% company-funded
    for k, f in bk["full"].items():
        p = num(bk["passed"].get(k))
        retained = round2(f - p)
        if retained != 0:
            out["retainedByComponent"][k] = retained
        if f > 0:
            out["oemClaimByComponent"][k] = f
        out["retainedIncomeTotal"] = round2(out["retainedIncomeTotal"] + retained)
        out["oemClaimTotal"] = round2(out["oemClaimTotal"] + f)
    return out


def compute_scheme_claim_shares(s, scheme_rows, approvals=None):
    """Company-share amounts for claim register: display (all) vs eligible (DSA needs approval)."""
    approvals = approvals or {}
    model = str(s.get("model") or s.get("interestedModel") or "").strip()
    variant = str(s.get("variant") or "").strip()
    booking_date = s.get("bookingDate") or ""
    offers_all = _oem_offers(s)
    offers_eligible = {}
    for key, amt in offers_all.items():
        pol = COMPONENT_POLICY.get(key)
        status = approvals.get(key) or "Pending"
        # DSA applied on a booked deal is treated approved unless explicitly rejected
        if key == "dsaDiscount" and pol and pol["approvalRequired"] and status == "Pending" and amt > 0:
            status = "Approved"
        if pol and pol["approvalRequired"] and status != "Approved":
            continue
        offers_eligible[key] = amt
    out = {"displayByComponent": {}, "eligibleByComponent": {},
           "displayTotal": 0.0, "eligibleTotal": 0.0, "shareSplitAvailable": False}
    if model and scheme_rows:
        disp = scheme_share_split_for(model, variant, booking_date, offers_all, scheme_rows)["byComponent"]
        elig = scheme_share_split_for(model, variant, booking_date, offers_eligible, scheme_rows)["byComponent"]
        for k, v in disp.items():
            c = num(v.get("companyShare"))
            if c > 0:
                out["displayByComponent"][k] = c
                out["displayTotal"] = round2(out["displayTotal"] + c)
        for k, v in elig.items():
            c = num(v.get("companyShare"))
            if c > 0:
                out["eligibleByComponent"][k] = c
                out["eligibleTotal"] = round2(out["eligibleTotal"] + c)
        has_oem_offer = len(offers_all) > 0
        out["shareSplitAvailable"] = (out["displayTotal"] > 0) if has_oem_offer else True
        return out
    for k, amt in offers_all.items():
        out["displayByComponent"][k] = amt
        out["displayTotal"] = round2(out["displayTotal"] + amt)
    for k, amt in offers_eligible.items():
        out["eligibleByComponent"][k] = amt
        out["eligibleTotal"] = round2(out["eligibleTotal"] + amt)
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
                      "choices": build_scheme_amount_choices(dealer, company, max_amt),
                      "hint": f"Enter amount up to \u20b9{max_amt} (Scheme Master {m.get('label', '')} \u00b7 {month})"}
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
            "automatic": True,
            "hint": f"Automatic entitlement — claimed from OEM at ₹{company} "
                    f"company share{f' (dealer funds ₹{dealer})' if dealer > 0 else ''}. "
                    f"Not entered by staff.",
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



def compute_full_commercials(s, scheme_rows=None):
    """Convenience: returns totals + margin + claim (+ scheme share-split when scheme rows given)."""
    totals = compute_commercial_totals(s)
    margin = compute_dealer_margin(s)
    claim = derive_claim(s)
    result = {**totals, "margin": margin, "claim": claim}
    if scheme_rows is not None:
        income = compute_scheme_income_breakdown(s, scheme_rows)
        shares = compute_scheme_claim_shares(s, scheme_rows)
        result["schemeIncome"] = income
        result["schemeClaimShares"] = shares
        # Report-facing truths derived from the share split
        result["oemClaimCompanyShare"] = shares["eligibleTotal"]
        result["dealerSchemeRetained"] = income["retainedIncomeTotal"]
    return result
