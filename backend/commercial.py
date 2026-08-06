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


def compute_full_commercials(s):
    """Convenience: returns totals + margin + claim in one object."""
    totals = compute_commercial_totals(s)
    margin = compute_dealer_margin(s)
    claim = derive_claim(s)
    return {**totals, "margin": margin, "claim": claim}
