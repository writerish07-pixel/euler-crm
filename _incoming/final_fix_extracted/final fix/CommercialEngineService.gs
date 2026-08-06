/**
 * CommercialEngineService – single source of truth for commercial math.
 *
 * Guarantees (per DMS spec):
 *  - Every booking gets ONE permanent, immutable Commercial Snapshot.
 *  - Snapshots are append-only + versioned: amendments supersede, never overwrite.
 *  - TCS, Total Discount, Payable and Outstanding are ALWAYS derived, never typed.
 *  - Every component's payer / approval / claimability comes from CRM.COMMERCIAL.COMPONENT_POLICY.
 *
 * The pure functions below (round2_, num_, calculateTcs_, computeCommercialTotals_,
 * deriveClaim_) are the implementation certified in tests/commercial_test.js.
 */

function getCommercialSheetConfig_() {
  return CRM.COMMERCIAL || {};
}

/* ----------------------------- pure math core ----------------------------- */

function round2_(n) {
  n = Number(n) || 0;
  return Math.round(n * 100) / 100;
}

/** Safe numeric coercion — one bad field never poisons a whole sum. */
function num_(v) { var n = Number(v); return isNaN(n) ? 0 : n; }

/** Centralised TCS engine — never entered manually. */
function calculateTcs_(taxableAmount, rate, threshold) {
  var cfg = getCommercialSheetConfig_();
  rate = (rate === undefined) ? Number(cfg.TCS_RATE || 0) : Number(rate) || 0;
  threshold = (threshold === undefined) ? Number(cfg.TCS_THRESHOLD || 0) : Number(threshold) || 0;
  var taxable = Math.max(0, Number(taxableAmount) || 0);
  if (taxable < threshold) return 0;
  return round2_(taxable * rate);
}

/** FINAL COMMERCIAL CALCULATION chain — the only place payable is derived.
 *
 * Eligible scheme amounts stay on offer fields (OEM/claim engine).
 * Customer Payable reduces ONLY by Customer Benefit Passed:
 *   Full Benefit (default / legacy blank) → all offers
 *   Partial Benefit → entered amount (capped at eligible)
 *   No Benefit → ₹0
 */
function sumEligibleSchemeOffers_(snapshot) {
  var s = snapshot || {};
  return round2_(
    num_(s.consumerDiscount) + num_(s.exchangeBonus) + num_(s.loyaltyBonus) +
    num_(s.referralBonus) + num_(s.dsaDiscount) + num_(s.additionalDiscount)
  );
}

/**
 * V3 TWO-POOL MODEL (blueprint §5) — the fix for the negative Dealer Retained bug.
 *
 * OEM Benefit Pool ("Eligible"): OEM-funded, claimable components, counting
 * approval-required ones (DSA) only once Approved. The benefit mode (Full /
 * Partial / None) applies to THIS pool only.
 *
 * Dealer Discount Pool: dealer-funded components (Additional Discount). Always
 * passed to the customer — the dealer chose to give them; they are dealer COST,
 * never "retained OEM benefit".
 *
 * The old code applied the mode to the sum of BOTH pools and then subtracted that
 * from the OEM pool, which went negative whenever a dealer-funded or pending
 * component existed (reproduced at −5,000 / −15,000). With separated pools,
 * Retained = oemPool − passedOem ∈ [0, oemPool] by construction.
 */
function resolveApprovalsFromSnapshot_(s) {
  s = s || {};
  return {
    dsaDiscount: s.dsaApproval || s['DSA Approval'] || (s._approvals && s._approvals.dsaDiscount) || 'Pending',
    additionalDiscount: 'N/A' // dealer-funded; approval affects workflow, not pools
  };
}

/**
 * OEM offer amounts recorded on the snapshot (deal truth).
 * DSA approval gates CLAIM eligibility only — never whether the scheme was applied.
 */
function snapshotOemOffers_(snapshot) {
  var s = snapshot || {};
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
  var out = {};
  keys.forEach(function (key) {
    var pol = policy[key];
    if (!pol || pol.payer !== 'OEM') return;
    var amt = Math.max(0, num_(s[key]));
    if (amt > 0) out[key] = amt;
  });
  return out;
}

function sumOemSchemeOffers_(snapshot, approvals) {
  var s = snapshot || {};
  var offers = snapshotOemOffers_(s);
  var total = 0;
  Object.keys(offers).forEach(function (key) { total += offers[key]; });
  return round2_(total);
}

function sumDealerSchemeOffers_(snapshot) {
  var s = snapshot || {};
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
  var total = 0;
  keys.forEach(function (key) {
    var pol = policy[key];
    if (!pol || pol.payer === 'OEM') return;
    total += Math.max(0, num_(s[key]));
  });
  return round2_(total);
}

function normalizeBenefitMode_(mode) {
  var m = String(mode || '').trim().toLowerCase();
  if (!m || m === 'full' || m === 'full benefit') return 'Full Benefit';
  if (m === 'partial' || m === 'partial benefit') return 'Partial Benefit';
  if (m === 'none' || m === 'no' || m === 'no benefit') return 'No Benefit';
  return 'Full Benefit';
}

/**
 * ₹ of COMPANY benefit passed to the customer (OEM pool only, mode applied).
 * Legacy snapshots with blank Benefit Mode = Full Benefit.
 */
function resolveCustomerBenefitPassed_(snapshot, approvals) {
  var s = snapshot || {};
  var oemPool = sumOemSchemeOffers_(s, approvals);
  var mode = normalizeBenefitMode_(s.benefitMode || s.customerBenefitMode);
  if (mode === 'No Benefit') return 0;
  if (mode === 'Partial Benefit') {
    // Prefer the per-component breakup (operator enters how much of EACH benefit is
    // passed, e.g. 10,000 of a 30,000 consumer discount). Sum the OEM-pool
    // components only; fall back to the legacy lump-sum field if no breakup.
    var breakup = s.benefitPassedBreakup;
    if (typeof breakup === 'string' && breakup) {
      try { breakup = JSON.parse(breakup); } catch (e) { breakup = null; }
    }
    if (breakup && typeof breakup === 'object') {
      var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
      var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
      var sum = 0;
      keys.forEach(function (key) {
        var pol = policy[key];
        if (!pol || pol.payer !== 'OEM') return;
        var cap = num_(s[key]);
        sum += Math.max(0, Math.min(num_(breakup[key]), cap));
      });
      return round2_(Math.max(0, Math.min(sum, oemPool)));
    }
    var passed = num_(s.customerBenefitPassed);
    return round2_(Math.max(0, Math.min(passed, oemPool)));
  }
  return oemPool; // Full Benefit
}

function computeCommercialTotals_(snapshot) {
  var s = snapshot || {};
  var grossVehicleCost = round2_(
    num_(s.exShowroom) + num_(s.accessories) + num_(s.insurance) +
    num_(s.registrationRto) + num_(s.fastag) + num_(s.handlingCharges) +
    num_(s.trc) + num_(s.extendedWarranty) + num_(s.rsaAmc) + num_(s.otherCharges)
  );
  // TCS only when the Price Master row explicitly says Yes; blank = legacy = No.
  // (Single default project-wide — the Yes/No split across engines is what caused
  // the per-booking payable divergence.)
  var tcsApplicable = String(s.tcsApplicable || 'No').toLowerCase() === 'yes';
  var tcs = tcsApplicable ? calculateTcs_(grossVehicleCost) : 0;

  var approvals = resolveApprovalsFromSnapshot_(s);
  var oemPool = sumOemSchemeOffers_(s, approvals);          // "Eligible"
  var dealerPool = sumDealerSchemeOffers_(s);               // always passed
  var passedOem = resolveCustomerBenefitPassed_(s, approvals);
  var oemExtraSupportPassed = Math.max(0, num_(s.oemExtraSupportPassed));
  var dealerRetained = round2_(Math.max(0, oemPool - passedOem)); // ∈ [0, oemPool]
  var totalPassedToCustomer = round2_(passedOem + dealerPool + oemExtraSupportPassed);

  var grossInvoiceAmount = round2_(grossVehicleCost + tcs);
  var netVehicleCost = round2_(grossInvoiceAmount - totalPassedToCustomer);
  var customerPayable = round2_(netVehicleCost - num_(s.finalExchangeValue));
  return {
    grossVehicleCost: grossVehicleCost,
    tcs: tcs,
    totalDiscount: round2_(oemPool + dealerPool),
    oemEligible: oemPool,
    dealerDiscount: dealerPool,
    customerBenefitPassed: passedOem,
    oemExtraSupportPassed: oemExtraSupportPassed,
    totalPassedToCustomer: totalPassedToCustomer,
    dealerRetained: dealerRetained,
    benefitMode: normalizeBenefitMode_(s.benefitMode || s.customerBenefitMode),
    grossInvoiceAmount: grossInvoiceAmount,
    netVehicleCost: netVehicleCost,
    customerPayable: customerPayable
  };
}

/** Dealer margin: 4% of pre-GST ex-showroom, then split GST part from margin. */
function resolveSnapshotExShowroom_(snapshot, lead) {
  var s = snapshot || {};
  lead = lead || {};
  var ex = num_(s.exShowroom);
  if (ex > 0) return ex;
  ex = num_(lead.budget) || num_(lead.bookingAmount) || 0;
  if (ex > 0) return ex;
  if (typeof getPriceMasterRecordForBooking_ === 'function') {
    try {
      var pm = getPriceMasterRecordForBooking_(
        s.model || s.vehicleModel || lead.interestedModel,
        s.variant || lead.variant,
        s.bookingDate || lead.bookingDate
      );
      if (pm && num_(pm.exShowroom) > 0) return num_(pm.exShowroom);
    } catch (e) {}
  }
  return 0;
}

function computeDealerMarginBreakdown_(snapshot) {
  var s = snapshot || {};
  var cfg = getCommercialSheetConfig_();
  var marginRate = Number(cfg.DEALER_MARGIN_RATE || 0.04);
  var marginGstRate = Number(cfg.DEALER_MARGIN_GST_RATE || 0.05);
  var exShowroomInclGst = Math.max(0, resolveSnapshotExShowroom_(s));
  var preGstExShowroom = marginGstRate > 0
    ? round2_(exShowroomInclGst / (1 + marginGstRate))
    : exShowroomInclGst;
  var marginGrossInclGst = round2_(preGstExShowroom * marginRate);
  var marginNetExGst = marginGstRate > 0
    ? round2_(marginGrossInclGst / (1 + marginGstRate))
    : marginGrossInclGst;
  var marginGst = round2_(marginGrossInclGst - marginNetExGst);
  return {
    preGstExShowroom: preGstExShowroom,
    marginGrossInclGst: marginGrossInclGst,
    marginGst: marginGst,
    marginNetExGst: marginNetExGst
  };
}

/** OEM Eligible = scheme-engine claimable OEM reimbursement (reuse deriveClaim_). */
function getOemEligibleAmount_(snapshot, approvals) {
  var claim = deriveClaim_(snapshot, approvals);
  return round2_(num_(claim.claimEligible));
}

/** Dealer Benefit Retained — single source: the engine's two-pool computation. */
function getDealerBenefitRetained_(snapshot, approvals) {
  var s = snapshot || {};
  var oemPool = sumOemSchemeOffers_(s, approvals || resolveApprovalsFromSnapshot_(s));
  var passedOem = resolveCustomerBenefitPassed_(s, approvals || resolveApprovalsFromSnapshot_(s));
  return round2_(Math.max(0, oemPool - passedOem));
}

/**
 * SCHEME INCOME MODEL (operator business rule):
 * Dealer share is NEVER income — it is only a cost when you pass it to the customer.
 * What you EARN by withholding benefit is the COMPANY share still claimable from OEM.
 *
 * Per component i with full amount f_i and passed amount p_i (company-first split):
 *   oemClaim_i = companyShare(f_i)                         // always claim full company share
 *   earn_i     = companyShare(f_i) − companyShare(p_i) − dealerShare(p_i)
 *             = company_unpassed − dealer_passed
 *             (can be NEGATIVE when Full Benefit spends your dealer share)
 *
 * Turbo example (Exchange ₹15k + Referral ₹5k + DSA ₹10k = ₹30k;
 *   company ₹20k / dealer ₹10k):
 *   Partial — pass company-only on Exchange+DSA (₹10k+₹5k):
 *     earn = Referral company unpassed ₹5,000  (NOT ₹15,000 — that ₹10k is your
 *     unspent dealer share, not income)
 *   Full ₹30k passed → earn = −₹10,000 (your dealer share spent)
 */
function resolvePassedBreakup_(snapshot, approvals) {
  var s = snapshot || {};
  approvals = approvals || resolveApprovalsFromSnapshot_(s);
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
  var mode = normalizeBenefitMode_(s.benefitMode || s.customerBenefitMode);

  var full = {}, passed = {};
  keys.forEach(function (key) {
    var pol = policy[key];
    if (!pol || pol.payer !== 'OEM') return;
    var amt = Math.max(0, num_(s[key]));
    if (amt > 0) full[key] = amt;
  });

  if (mode === 'Full Benefit') {
    Object.keys(full).forEach(function (k) { passed[k] = full[k]; });
  } else if (mode === 'Partial Benefit') {
    var breakup = s.benefitPassedBreakup;
    if (typeof breakup === 'string' && breakup) {
      try { breakup = JSON.parse(breakup); } catch (e) { breakup = null; }
    }
    if (breakup && typeof breakup === 'object') {
      Object.keys(full).forEach(function (k) {
        passed[k] = Math.max(0, Math.min(num_(breakup[k]), full[k]));
      });
    } else {
      var remaining = Math.max(0, num_(s.customerBenefitPassed));
      keys.forEach(function (k) {
        if (!full[k]) return;
        var take = Math.min(full[k], remaining);
        passed[k] = take;
        remaining = round2_(remaining - take);
      });
    }
  } // No Benefit → passed stays {}

  return { full: full, passed: passed, mode: mode };
}

function computeSchemeIncomeBreakdown_(snapshot, approvals) {
  var s = snapshot || {};
  var bk = resolvePassedBreakup_(s, approvals);
  var model = String(s.model || s.interestedModel || '').trim();
  var variant = String(s.variant || '').trim();
  var bookingDate = s.bookingDate || nowDate_();

  var out = {
    retainedIncomeTotal: 0,
    retainedByComponent: {},
    oemClaimTotal: 0,
    oemClaimByComponent: {},
    dealerCostPassed: 0,
    passedByComponent: bk.passed,
    fullByComponent: bk.full,
    shareSplitAvailable: false
  };

  var offersAll = snapshotOemOffers_(s);

  if (typeof schemeShareSplitFor_ === 'function' && model) {
    try {
      var fullSplit = schemeShareSplitFor_(model, variant, bookingDate, offersAll) || {};
      var passSplit = schemeShareSplitFor_(model, variant, bookingDate, bk.passed) || {};
      var fBy = fullSplit.byComponent || {};
      var pBy = passSplit.byComponent || {};
      var keys = {};
      Object.keys(fBy).forEach(function (k) { keys[k] = 1; });
      Object.keys(pBy).forEach(function (k) { keys[k] = 1; });
      Object.keys(keys).forEach(function (k) {
        // schemeShareSplitFor_ returns { actual, dealerShare, companyShare, label }
        var cFull = num_(fBy[k] && fBy[k].companyShare);
        var cPass = num_(pBy[k] && pBy[k].companyShare);
        var dPass = num_(pBy[k] && pBy[k].dealerShare);
        // Company unpassed minus dealer share that was passed (can go negative).
        // Dealer unpassed is NOT income — you simply did not spend your own share.
        var retained = round2_((cFull - cPass) - dPass);
        if (cFull > 0) out.oemClaimByComponent[k] = cFull;
        if (retained !== 0) out.retainedByComponent[k] = retained;
        out.oemClaimTotal = round2_(out.oemClaimTotal + cFull);
        out.retainedIncomeTotal = round2_(out.retainedIncomeTotal + retained);
        out.dealerCostPassed = round2_(out.dealerCostPassed + dPass);
      });
      // Guardrail: if Scheme Master split returns zero company share for all OEM
      // components while OEM benefit exists on the snapshot, treat shares as not
      // usable and fall back to legacy claim math. This prevents silent "all claim
      // amounts = 0" in reports when share data is incomplete/misconfigured.
      var hasOemOffer = Object.keys(bk.full || {}).length > 0;
      var hasCompanyShare = num_(out.oemClaimTotal) > 0;
      out.shareSplitAvailable = hasOemOffer ? hasCompanyShare : true;
      return out;
    } catch (splitErr) {
      try { Logger.log('computeSchemeIncomeBreakdown_ split fallback: ' + splitErr.message); } catch (lg) {}
    }
  }

  // Fallback (no Scheme Master shares): treat component as 100% company-funded.
  // earn = unpassed; dealer_passed = 0. Full pass → 0 (cannot know dealer share).
  Object.keys(bk.full).forEach(function (k) {
    var f = bk.full[k], p = num_(bk.passed[k]);
    var retained = round2_(f - p); // may be 0 on full pass; no dealer-share cost without master
    if (retained !== 0) out.retainedByComponent[k] = retained;
    if (f > 0) out.oemClaimByComponent[k] = f;
    out.retainedIncomeTotal = round2_(out.retainedIncomeTotal + retained);
    out.oemClaimTotal = round2_(out.oemClaimTotal + f);
  });
  return out;
}

/**
 * Company-share amounts for claim register / OEM reports.
 * display* = all snapshot OEM offers (July-2026 circular splits).
 * eligible* = DSA included only when DSA Approval = Approved.
 */
function computeSchemeClaimShares_(snapshot, approvals) {
  var s = snapshot || {};
  approvals = approvals || resolveApprovalsFromSnapshot_(s);
  var model = String(s.model || s.interestedModel || '').trim();
  var variant = String(s.variant || '').trim();
  var bookingDate = s.bookingDate || nowDate_();
  var offersAll = snapshotOemOffers_(s);
  var offersEligible = {};
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  Object.keys(offersAll).forEach(function (key) {
    var pol = policy[key];
    if (pol && pol.approvalRequired && String(approvals[key] || 'Pending') !== 'Approved') return;
    offersEligible[key] = offersAll[key];
  });

  var out = {
    displayByComponent: {},
    eligibleByComponent: {},
    displayTotal: 0,
    eligibleTotal: 0,
    shareSplitAvailable: false
  };

  if (typeof schemeShareSplitFor_ === 'function' && model) {
    try {
      var dispSplit = schemeShareSplitFor_(model, variant, bookingDate, offersAll) || {};
      var eligSplit = schemeShareSplitFor_(model, variant, bookingDate, offersEligible) || {};
      var dBy = dispSplit.byComponent || {};
      var eBy = eligSplit.byComponent || {};
      Object.keys(dBy).forEach(function (k) {
        var c = num_(dBy[k] && dBy[k].companyShare);
        if (c > 0) {
          out.displayByComponent[k] = c;
          out.displayTotal = round2_(out.displayTotal + c);
        }
      });
      Object.keys(eBy).forEach(function (k) {
        var c = num_(eBy[k] && eBy[k].companyShare);
        if (c > 0) {
          out.eligibleByComponent[k] = c;
          out.eligibleTotal = round2_(out.eligibleTotal + c);
        }
      });
      var hasOemOffer = Object.keys(offersAll).length > 0;
      out.shareSplitAvailable = hasOemOffer ? out.displayTotal > 0 : true;
      return out;
    } catch (splitErr) {
      try { Logger.log('computeSchemeClaimShares_ split fallback: ' + splitErr.message); } catch (lg) {}
    }
  }

  Object.keys(offersAll).forEach(function (k) {
    out.displayByComponent[k] = offersAll[k];
    out.displayTotal = round2_(out.displayTotal + offersAll[k]);
  });
  Object.keys(offersEligible).forEach(function (k) {
    out.eligibleByComponent[k] = offersEligible[k];
    out.eligibleTotal = round2_(out.eligibleTotal + offersEligible[k]);
  });
  return out;
}

/** When DSA is applied on a booked deal, treat as ASM-approved unless explicitly Rejected. */
function resolveDsaApprovalForClaim_(snapshot, savedApproval) {
  var status = String(savedApproval || '').trim() || 'Pending';
  if (status === 'Rejected') return status;
  if (num_((snapshot || {}).dsaDiscount) > 0) return 'Approved';
  return status;
}

/**
 * Split discounts by payer and derive OEM-claimable amounts using COMPONENT_POLICY.
 * approvals: { dsaDiscount:'Approved'|'Pending'|'Rejected', additionalDiscount:... }
 */
function deriveClaim_(snapshot, approvals) {
  var s = snapshot || {};
  approvals = approvals || {};
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
  var dealerDiscount = 0, oemDiscount = 0, claimTotal = 0, claimEligible = 0;
  var breakdown = [];
  keys.forEach(function (key) {
    var amt = round2_(num_(s[key]));
    if (amt <= 0) return;
    var pol = policy[key];
    if (!pol) return;
    var approvalStatus = pol.approvalRequired ? (approvals[key] || 'Pending') : 'N/A';
    if (pol.payer === 'OEM') oemDiscount = round2_(oemDiscount + amt);
    else dealerDiscount = round2_(dealerDiscount + amt);
    if (pol.claimable) {
      claimTotal = round2_(claimTotal + amt);
      if (!pol.approvalRequired || approvalStatus === 'Approved') claimEligible = round2_(claimEligible + amt);
    }
    breakdown.push({
      key: key, label: pol.label, amount: amt, payer: pol.payer,
      approvalRequired: pol.approvalRequired, approvalStatus: approvalStatus, claimable: pol.claimable
    });
  });
  return {
    dealerDiscount: dealerDiscount, oemDiscount: oemDiscount,
    claimTotal: claimTotal, claimEligible: claimEligible,
    claimRequired: claimTotal > 0 ? 'Yes' : 'No', breakdown: breakdown
  };
}

/* ------------------------------ ID generation ----------------------------- */

function nextCommercialId_(kind) {
  var cfg = getCommercialSheetConfig_();
  var map = {
    booking:  { prefix: cfg.BOOKING_PREFIX || 'BK26',  key: 'nextBookingCounter' },
    snapshot: { prefix: cfg.SNAPSHOT_PREFIX || 'SN26', key: 'nextSnapshotCounter' },
    claim:    { prefix: cfg.CLAIM_PREFIX || 'CLM26',   key: 'nextClaimCounter' }
  };
  var m = map[kind];
  var settings = getSettings_();
  var counter = Number(settings[m.key] || 1);
  var id = m.prefix + String(counter).padStart(6, '0');
  saveSetting_(m.key, counter + 1);
  return id;
}

/* ---------------------------- sheet management ---------------------------- */

function ensureCommercialSnapshotSheet_() {
  if (!CRM || !CRM.SHEETS || !CRM.SHEETS.COMMERCIAL_SNAPSHOT) return null;
  var cfg = getCommercialSheetConfig_();
  if (!cfg.COLS || cfg.COLS.length === 0) return null;

  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) sheet = ss.insertSheet(CRM.SHEETS.COMMERCIAL_SNAPSHOT);

  // APPEND-ONLY headers. Never rewrite existing header row in place — that
  // mislabels live data (e.g. Total Discount / Exchange Bonus appear as
  // "OEM Extra Support Received"). Missing columns are added at the end.
  var hdrRow = cfg.HEADER_ROW || 1;
  var headers = getHeaders_(sheet, hdrRow);
  if (!headers.length) {
    sheet.getRange(hdrRow, 1, 1, cfg.COLS.length).setValues([cfg.COLS]).setFontWeight('bold');
  } else {
    ensureCommercialSnapshotHeaders_();
  }

  if (!sheet.isSheetHidden()) sheet.hideSheet();
  return sheet;
}

function ensureCommercialAuditSheet_() {
  var cfg = CRM.COMMERCIAL_AUDIT;
  if (!cfg) return null;
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.COMMERCIAL_AUDIT);
  if (!sheet) sheet = ss.insertSheet(CRM.SHEETS.COMMERCIAL_AUDIT);
  var header = sheet.getRange(cfg.HEADER_ROW, 1, 1, cfg.COLS.length).getValues()[0];
  if (String(header[0] || '').trim() !== cfg.COLS[0]) {
    sheet.getRange(cfg.HEADER_ROW, 1, 1, cfg.COLS.length).setValues([cfg.COLS]).setFontWeight('bold');
  }
  if (!sheet.isSheetHidden()) sheet.hideSheet();
  return sheet;
}

/** Immutable commercial audit trail: old value → new value, user, time, reason. */
function logCommercialAudit_(bookingId, leadId, field, oldValue, newValue, reason, approvedBy) {
  try {
    var sheet = ensureCommercialAuditSheet_();
    if (!sheet) return;
    sheet.appendRow([
      nowDateTime_(), getUserEmail_(), bookingId || '', leadId || '', field || '',
      (oldValue === undefined ? '' : oldValue), (newValue === undefined ? '' : newValue),
      reason || '', approvedBy || '', getVersionTag_()
    ]);
  } catch (e) { Logger.log('logCommercialAudit_ failed: ' + e.message); }
}

/* --------------------------- snapshot construction ------------------------ */

function yesNo_(value) {
  var v = String(value || '').trim().toLowerCase();
  if (v === 'yes' || v === 'y' || v === 'true' || v === '1') return 'Yes';
  return 'No';
}

function buildCommercialSnapshotFromLead_(lead) {
  lead = lead || {};
  var now = nowDateTime_();
  // At booking we usually know booking amount + the quoted price (Budget). Use
  // Budget as Ex-Showroom when present so payable ≈ price; components default 0.
  var exShowroom = round2_(num_(lead.budget) || num_(lead.bookingAmount) || 0);
  return {
    leadId: String(lead.leadId || '').trim(),
    bookingId: nextCommercialId_('booking'),
    snapshotId: nextCommercialId_('snapshot'),
    snapshotStatus: 'Active',
    supersededBy: '',
    amendmentReason: '',
    bookingDate: lead.bookingDate || nowDate_(),
    priceListVersion: getVersionTag_(),
    priceMasterRowId: '',
    priceEffectiveDate: nowDate_(),
    model: lead.interestedModel || '',
    variant: lead.variant || '',
    bodyType: '',
    batteryType: '',
    bookingAmount: round2_(num_(lead.bookingAmount)),
    bookingExecutive: lead.executive || '',
    bookingMode: '',
    financeRequired: yesNo_(lead.financeRequired),
    exchangeRequired: yesNo_(lead.exchangeRequired),
    exShowroom: exShowroom,
    accessories: 0, insurance: 0, registrationRto: 0, fastag: 0, handlingCharges: 0, trc: 0,
    extendedWarranty: 0, rsaAmc: 0, otherCharges: 0, gstPercent: 0, tcsApplicable: 'Yes',
    consumerDiscount: 0, exchangeBonus: 0, loyaltyBonus: 0, referralBonus: 0, dsaDiscount: 0, additionalDiscount: 0,
    oemExtraSupportReceived: 0, oemExtraSupportPassed: 0, oemExtraSupportRetained: 0,
    oldVehicleBrand: '', oldVehicleModel: '', oldVehicleRegistration: '',
    evaluatedExchangeValue: 0, finalExchangeValue: 0,
    financer: '', loanAmount: 0, downPayment: 0,
    bookingLocked: 'Yes', bookingLockReason: 'Auto snapshot at booking',
    createdAt: now, updatedAt: now, updatedBy: getUserEmail_()
  };
}

/** Ensure Commercial Snapshot has required headers (append-only; never clears data). */
function ensureCommercialSnapshotHeaders_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet || !CRM.COMMERCIAL || !CRM.COMMERCIAL.COLS) return null;
  var hdrRow = CRM.COMMERCIAL.HEADER_ROW || 1;
  var headers = getHeaders_(sheet, hdrRow);
  if (!headers.length) {
    sheet.getRange(hdrRow, 1, 1, CRM.COMMERCIAL.COLS.length)
      .setValues([CRM.COMMERCIAL.COLS]).setFontWeight('bold');
    return sheet;
  }
  // Legacy single column → Received
  var oldIdx = findHeaderIndex_(headers, 'OEM Extra Support');
  var recvIdx = findHeaderIndex_(headers, 'OEM Extra Support Received');
  if (oldIdx >= 0 && recvIdx < 0) {
    sheet.getRange(hdrRow, oldIdx + 1).setValue('OEM Extra Support Received');
    headers = getHeaders_(sheet, hdrRow);
  }
  CRM.COMMERCIAL.COLS.forEach(function (c) {
    headers = getHeaders_(sheet, hdrRow);
    if (findHeaderIndex_(headers, c) < 0) {
      sheet.getRange(hdrRow, headers.length + 1).setValue(c).setFontWeight('bold');
    }
  });
  return sheet;
}

/** Field map for header-aligned writes (avoids column-shift bugs). */
function commercialFieldMap_(s) {
  var totals = computeCommercialTotals_(s);
  var margin = computeDealerMarginBreakdown_(s);
  var benefitMode = totals.benefitMode || normalizeBenefitMode_(s.benefitMode);
  // OEM Extra Support is case-wise profit from OEM — independent of Scheme Master.
  // Never fall back to legacy alias when it equals scheme totals (header-bleed bug).
  var oemRecv = Math.max(0, num_(s.oemExtraSupportReceived));
  if (!(oemRecv > 0) && num_(s.oemExtraSupport) > 0) {
    var legacy = num_(s.oemExtraSupport);
    var schemeSumLegacy = round2_(
      num_(s.consumerDiscount) + num_(s.exchangeBonus) + num_(s.loyaltyBonus) +
      num_(s.referralBonus) + num_(s.dsaDiscount) + num_(s.additionalDiscount)
    );
    if (legacy !== schemeSumLegacy && legacy !== num_(s.totalDiscount) && legacy !== num_(s.exchangeBonus)) {
      oemRecv = legacy;
    }
  }
  var oemPass = Math.max(0, Math.min(num_(s.oemExtraSupportPassed), oemRecv));
  var oemRet = round2_(Math.max(0, oemRecv - oemPass));
  var breakup = (typeof s.benefitPassedBreakup === 'object' && s.benefitPassedBreakup !== null)
    ? JSON.stringify(s.benefitPassedBreakup) : String(s.benefitPassedBreakup || '');
  return {
    'Lead ID': s.leadId,
    'Booking Date': s.bookingDate,
    'Price List Version': s.priceListVersion,
    'Price Master Row ID': s.priceMasterRowId || '',
    'Price Effective Date': s.priceEffectiveDate || '',
    'Vehicle Model': s.model,
    'Variant': s.variant,
    'Body Type': s.bodyType || s.batteryType || '',
    'Booking Amount': num_(s.bookingAmount),
    'Booking Executive': s.bookingExecutive,
    'Booking Mode': s.bookingMode,
    'Finance Required': s.financeRequired,
    'Exchange Required': s.exchangeRequired,
    'Ex Showroom Price': num_(s.exShowroom),
    'Accessories': num_(s.accessories),
    'Insurance': num_(s.insurance),
    'Registration / RTO': num_(s.registrationRto),
    'Fastag': num_(s.fastag),
    'Handling Charges': num_(s.handlingCharges),
    'TRC': num_(s.trc || 0),
    'Extended Warranty': num_(s.extendedWarranty),
    'RSA / AMC': num_(s.rsaAmc),
    'Other Charges': num_(s.otherCharges),
    'GST %': num_(s.gstPercent),
    'TCS Applicable': yesNo_(s.tcsApplicable),
    'TCS': totals.tcs,
    'Consumer Discount': num_(s.consumerDiscount),
    'Exchange Bonus': num_(s.exchangeBonus),
    'Loyalty Bonus': num_(s.loyaltyBonus),
    'Referral Bonus': num_(s.referralBonus),
    'DSA Discount': num_(s.dsaDiscount),
    'Additional Discount': num_(s.additionalDiscount),
    'OEM Extra Support Received': oemRecv,
    'OEM Extra Support Passed To Customer': oemPass,
    'OEM Extra Support Retained': oemRet,
    'Total Discount': totals.totalDiscount,
    'Benefit Mode': benefitMode,
    'Customer Benefit Passed': totals.customerBenefitPassed,
    'Old Vehicle Brand': s.oldVehicleBrand,
    'Old Vehicle Model': s.oldVehicleModel,
    'Registration Number': s.oldVehicleRegistration,
    'Evaluated Value': num_(s.evaluatedExchangeValue),
    'Final Exchange Value': num_(s.finalExchangeValue),
    'Financer': s.financer,
    'Loan Amount': num_(s.loanAmount),
    'Down Payment': num_(s.downPayment),
    'Gross Vehicle Cost': totals.grossVehicleCost,
    'Gross Invoice Amount': totals.grossInvoiceAmount,
    'Net Vehicle Cost': totals.netVehicleCost,
    'Customer Payable': totals.customerPayable,
    'Dealer Margin Gross (Incl GST)': margin.marginGrossInclGst,
    'Dealer Margin GST (5%)': margin.marginGst,
    'Dealer Margin Net (Ex GST)': margin.marginNetExGst,
    'Booking Locked': s.bookingLocked || 'Yes',
    'Lock Reason': s.bookingLockReason || '',
    'Created At': s.createdAt || nowDateTime_(),
    'Updated At': nowDateTime_(),
    'Updated By': getUserEmail_(),
    'Booking ID': s.bookingId || '',
    'Snapshot ID': s.snapshotId || '',
    'Snapshot Status': s.snapshotStatus || 'Active',
    'Superseded By': s.supersededBy || '',
    'Amendment Reason': s.amendmentReason || '',
    'Benefit Passed Breakup': breakup
  };
}

/**
 * OEM Extra Support is case-wise dealer profit from OEM — NOT Scheme Master.
 * Do NOT auto-clear on read: that wiped real typed amounts (e.g. Extra Support
 * ₹15,000 when Exchange was also ₹15,000). Bleed cleanup is owner-menu only.
 */
function sanitizeOemExtraSupportSnapshot_(snap, opts) {
  snap = snap || {};
  opts = opts || {};
  var recv = num_(snap.oemExtraSupportReceived);
  if (!(recv > 0) && num_(snap.oemExtraSupport) > 0) recv = num_(snap.oemExtraSupport);
  snap.oemExtraSupportReceived = Math.max(0, recv);
  snap.oemExtraSupportPassed = Math.max(0, Math.min(num_(snap.oemExtraSupportPassed), snap.oemExtraSupportReceived));
  snap.oemExtraSupportRetained = round2_(Math.max(0, snap.oemExtraSupportReceived - snap.oemExtraSupportPassed));
  // Optional one-time bleed clear — ONLY when repair menu passes forceClearBleed.
  if (opts.forceClearBleed) {
    var schemeSum = round2_(
      num_(snap.consumerDiscount) + num_(snap.exchangeBonus) + num_(snap.loyaltyBonus) +
      num_(snap.referralBonus) + num_(snap.dsaDiscount) + num_(snap.additionalDiscount)
    );
    var totalDisc = num_(snap.totalDiscount);
    var onlyExchange = num_(snap.exchangeBonus) > 0 &&
      num_(snap.consumerDiscount) === 0 && num_(snap.loyaltyBonus) === 0 &&
      num_(snap.referralBonus) === 0 && num_(snap.dsaDiscount) === 0 &&
      num_(snap.additionalDiscount) === 0;
    var looksLikeSchemeBleed =
      (totalDisc > 0 && recv === totalDisc) ||
      (schemeSum > 0 && recv === schemeSum) ||
      (onlyExchange && recv === num_(snap.exchangeBonus));
    if (looksLikeSchemeBleed && num_(snap.oemExtraSupportPassed) === 0) {
      snap.oemExtraSupportReceived = 0;
      snap.oemExtraSupportPassed = 0;
      snap.oemExtraSupportRetained = 0;
      snap.oemExtraSupport = 0;
    }
  }
  return snap;
}

/** Ensure the three OEM Extra Support columns exist on Commercial Snapshot. */
function ensureOemExtraSupportCommercialColumns_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return null;
  var hdrRow = (CRM.COMMERCIAL && CRM.COMMERCIAL.HEADER_ROW) || 1;
  var needed = [
    'OEM Extra Support Received',
    'OEM Extra Support Passed To Customer',
    'OEM Extra Support Retained'
  ];
  var headers = getHeaders_(sheet, hdrRow);
  // Rename legacy single column first
  var oldIdx = findHeaderIndex_(headers, 'OEM Extra Support');
  var recvIdx = findHeaderIndex_(headers, 'OEM Extra Support Received');
  if (oldIdx >= 0 && recvIdx < 0) {
    sheet.getRange(hdrRow, oldIdx + 1).setValue('OEM Extra Support Received').setFontWeight('bold');
    headers = getHeaders_(sheet, hdrRow);
  }
  needed.forEach(function (name) {
    headers = getHeaders_(sheet, hdrRow);
    if (findHeaderIndex_(headers, name) < 0) {
      sheet.getRange(hdrRow, headers.length + 1).setValue(name).setFontWeight('bold');
    }
  });
  return getHeaders_(sheet, hdrRow);
}

/**
 * Force-write OEM Extra Support trio onto a Commercial Snapshot row by header name.
 * Survives missing/misordered columns that blank out positional row writes.
 */
function patchOemExtraSupportOnSnapshotRow_(sheet, row, headers, snap) {
  if (!sheet || !(row > 0)) return false;
  headers = headers || getHeaders_(sheet, (CRM.COMMERCIAL && CRM.COMMERCIAL.HEADER_ROW) || 1);
  var recv = Math.max(0, num_(snap && (snap.oemExtraSupportReceived != null ? snap.oemExtraSupportReceived : snap['OEM Extra Support Received'])));
  var pass = Math.max(0, Math.min(num_(snap && (snap.oemExtraSupportPassed != null ? snap.oemExtraSupportPassed : snap['OEM Extra Support Passed To Customer'])), recv));
  var ret = round2_(Math.max(0, recv - pass));
  var pairs = [
    ['OEM Extra Support Received', recv],
    ['OEM Extra Support Passed To Customer', pass],
    ['OEM Extra Support Retained', ret]
  ];
  var wrote = false;
  pairs.forEach(function (p) {
    var col = findHeaderIndex_(headers, p[0]) + 1;
    if (col > 0) {
      try {
        sheet.getRange(row, col).setNumberFormat('#,##0.00');
        setValueSafe_(sheet.getRange(row, col), p[1]);
        wrote = true;
      } catch (e) {
        Logger.log('patchOemExtraSupportOnSnapshotRow_: ' + e.message);
      }
    }
  });
  return wrote;
}

function toCommercialRowForSheet_(s, headers) {
  var map = commercialFieldMap_(s);
  if (!headers || !headers.length) {
    return (CRM.COMMERCIAL.COLS || []).map(function (h) {
      return map.hasOwnProperty(h) ? map[h] : '';
    });
  }
  return headers.map(function (h) {
    if (map.hasOwnProperty(h)) return map[h];
    // Tolerant match (spacing / case) so OEM Extra Support columns always write.
    var target = normalizeHeaderKey_(h);
    var keys = Object.keys(map);
    for (var i = 0; i < keys.length; i++) {
      if (normalizeHeaderKey_(keys[i]) === target) return map[keys[i]];
    }
    return '';
  });
}

/** @deprecated positional helper — prefer toCommercialRowForSheet_ */
function toCommercialRow_(s) {
  return toCommercialRowForSheet_(s, (CRM.COMMERCIAL && CRM.COMMERCIAL.COLS) || []);
}

/* ------------------------ immutable create + amend ------------------------ */

/**
 * Create-only. Never overwrites an existing ACTIVE snapshot (immutability).
 * Amendments must go through amendCommercialSnapshot_.
 */
function upsertCommercialSnapshot_(snapshot, reason) {
  var leadId = String((snapshot && snapshot.leadId) || '').trim();
  if (!leadId) return null;
  ensureCommercialSnapshotSheet_();
  var store = loadCrmStore_();
  var existing = (store.commercial && store.commercial.byLeadId) ? store.commercial.byLeadId[leadId] : null;
  if (existing) return true; // already snapshotted → immutable, do nothing

  if (!snapshot.bookingId) snapshot.bookingId = nextCommercialId_('booking');
  if (!snapshot.snapshotId) snapshot.snapshotId = nextCommercialId_('snapshot');
  snapshot.snapshotStatus = 'Active';

  ensureCommercialSnapshotHeaders_();
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return null;
  var headers = getHeaders_(sheet, CRM.COMMERCIAL.HEADER_ROW || 1);
  var row = toCommercialRowForSheet_(snapshot, headers);
  var newRow = Math.max(sheet.getLastRow() + 1, CRM.COMMERCIAL.DATA_START);
  sheet.getRange(newRow, 1, 1, Math.max(row.length, headers.length)).setValues([row]);
  logCommercialAudit_(snapshot.bookingId, leadId, 'SNAPSHOT_CREATE', '', 'Customer Payable=' + computeCommercialTotals_(snapshot).customerPayable, reason || 'Booking snapshot', '');
  if (reason) logAudit_('COMMERCIAL_SNAPSHOT', leadId + ' | ' + reason);
  invalidateCrmStore_();
  return true;
}

/**
 * Amend a locked snapshot: supersede the current Active row and append a new
 * version. Requires a reason; logs field-level old→new audit entries.
 * @param changes {Object} snapshot-field deltas (e.g. { consumerDiscount: 15000 }).
 */
function amendCommercialSnapshot_(leadId, changes, reason, approvedBy) {
  leadId = String(leadId || '').trim();
  if (!leadId) throw new Error('Lead ID required to amend snapshot');
  if (!reason) throw new Error('Amendment reason is mandatory (audit requirement)');
  changes = changes || {};

  ensureCommercialSnapshotSheet_();
  ensureCommercialSnapshotHeaders_();
  // Guarantee OEM Extra Support columns exist BEFORE building the row.
  ensureOemExtraSupportCommercialColumns_();
  var store = loadCrmStore_(true);
  var current = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  if (!current) throw new Error('No snapshot to amend for ' + leadId);

  var full = current.full || current;                 // hydrated field map
  var newSnap = {};
  Object.keys(full).forEach(function (k) { newSnap[k] = full[k]; });
  var newSnapshotId = nextCommercialId_('snapshot');

  Object.keys(changes).forEach(function (k) {
    if (String(full[k]) !== String(changes[k])) {
      logCommercialAudit_(full.bookingId, leadId, k, full[k], changes[k], reason, approvedBy);
    }
    newSnap[k] = changes[k];
  });
  // Normalize OEM Extra Support on the new snapshot (never drop typed amounts).
  newSnap.oemExtraSupportReceived = Math.max(0, num_(newSnap.oemExtraSupportReceived));
  newSnap.oemExtraSupportPassed = Math.max(0, Math.min(num_(newSnap.oemExtraSupportPassed), newSnap.oemExtraSupportReceived));
  newSnap.oemExtraSupportRetained = round2_(Math.max(0, newSnap.oemExtraSupportReceived - newSnap.oemExtraSupportPassed));
  newSnap.snapshotId = newSnapshotId;
  newSnap.bookingId = full.bookingId;                 // Booking ID stable across versions
  newSnap.snapshotStatus = 'Active';
  newSnap.supersededBy = '';
  newSnap.amendmentReason = reason;
  newSnap.createdAt = full.createdAt;

  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  var headers = getHeaders_(sheet, CRM.COMMERCIAL.HEADER_ROW);
  // Re-read after ensure — columns may have been appended.
  headers = ensureOemExtraSupportCommercialColumns_() || headers;
  var statusCol = findHeaderIndex_(headers, 'Snapshot Status') + 1;
  var supersededCol = findHeaderIndex_(headers, 'Superseded By') + 1;
  if (current.sheetRow && statusCol > 0) {
    sheet.getRange(current.sheetRow, statusCol).setValue('Superseded');
    if (supersededCol > 0) sheet.getRange(current.sheetRow, supersededCol).setValue(newSnapshotId);
  }
  var row = toCommercialRowForSheet_(newSnap, headers);
  var newRow = Math.max(sheet.getLastRow() + 1, CRM.COMMERCIAL.DATA_START);
  sheet.getRange(newRow, 1, 1, Math.max(row.length, headers.length)).setValues([row]);
  // Belt-and-suspenders: patch OEM Extra Support by header name after row write.
  patchOemExtraSupportOnSnapshotRow_(sheet, newRow, headers, newSnap);
  logAudit_('COMMERCIAL_AMEND', leadId + ' | ' + reason + ' | new=' + newSnapshotId +
    ' | OEM Extra Support Received=' + newSnap.oemExtraSupportReceived);
  invalidateCrmStore_();
  return {
    bookingId: full.bookingId,
    snapshotId: newSnapshotId,
    sheetRow: newRow,
    oemExtraSupportReceived: newSnap.oemExtraSupportReceived,
    oemExtraSupportPassed: newSnap.oemExtraSupportPassed,
    oemExtraSupportRetained: newSnap.oemExtraSupportRetained
  };
}

/* --------------------------- auto-capture hooks --------------------------- */

function shouldCreateSnapshotForLead_(lead) {
  if (!lead) return false;
  var booked = String(lead.bookingStatus || '').toLowerCase();
  var hasBookingDate = !!String(lead.bookingDate || '').trim();
  var hasBookingAmount = num_(lead.bookingAmount) > 0;
  return booked.indexOf('book') >= 0 || hasBookingDate || hasBookingAmount;
}

function ensureCommercialSnapshotForLead_(lead, store) {
  if (!shouldCreateSnapshotForLead_(lead)) return false;
  store = store || loadCrmStore_();
  var leadId = String(lead.leadId || '').trim();
  if (!leadId) return false;
  if (store.commercial && store.commercial.byLeadId && store.commercial.byLeadId[leadId]) return false;
  var snap = buildCommercialSnapshotFromLead_(lead);
  return !!upsertCommercialSnapshot_(snap, 'Auto-captured booking snapshot');
}

/** The ONLY payable source of truth (used by payments + outstanding). */
function getCommercialPayable_(leadId, store) {
  store = store || loadCrmStore_();
  var snap = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  if (snap) return round2_(num_(snap.customerPayable));
  var lead = store.leads.byId[leadId] || {};
  return round2_(num_(lead.bookingAmount) || num_(lead.budget));
}

/**
 * One-time backfill: assign Booking ID / Snapshot ID / Status='Active' to any
 * historical snapshot rows that predate the immutability columns.
 */
function backfillCommercialIds_() {
  ensureCommercialSnapshotSheet_();
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return 0;
  var headers = getHeaders_(sheet, CRM.COMMERCIAL.HEADER_ROW);
  var last = sheet.getLastRow();
  if (last < CRM.COMMERCIAL.DATA_START) return 0;
  var bkCol = headers.indexOf('Booking ID') + 1;
  var snCol = headers.indexOf('Snapshot ID') + 1;
  var stCol = headers.indexOf('Snapshot Status') + 1;
  if (bkCol < 1 || snCol < 1 || stCol < 1) return 0;

  var n = last - CRM.COMMERCIAL.DATA_START + 1;
  var bk = sheet.getRange(CRM.COMMERCIAL.DATA_START, bkCol, n, 1).getValues();
  var sn = sheet.getRange(CRM.COMMERCIAL.DATA_START, snCol, n, 1).getValues();
  var st = sheet.getRange(CRM.COMMERCIAL.DATA_START, stCol, n, 1).getValues();
  var filled = 0;
  for (var i = 0; i < n; i++) {
    if (!String(bk[i][0] || '').trim()) { bk[i][0] = nextCommercialId_('booking'); filled++; }
    if (!String(sn[i][0] || '').trim()) sn[i][0] = nextCommercialId_('snapshot');
    if (!String(st[i][0] || '').trim()) st[i][0] = 'Active';
  }
  sheet.getRange(CRM.COMMERCIAL.DATA_START, bkCol, n, 1).setValues(bk);
  sheet.getRange(CRM.COMMERCIAL.DATA_START, snCol, n, 1).setValues(sn);
  sheet.getRange(CRM.COMMERCIAL.DATA_START, stCol, n, 1).setValues(st);
  invalidateCrmStore_();
  logAudit_('COMMERCIAL_BACKFILL', filled + ' snapshot rows assigned Booking IDs');
  return filled;
}

/** Light read of active commercial snapshot for one lead (no full CRM store). */
function getLatestCommercialSnapshotForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return null;
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return null;
  var headers = getHeaders_(sheet, CRM.COMMERCIAL.HEADER_ROW);
  var idIdx = findHeaderIndex_(headers, 'Lead ID');
  if (idIdx < 0) return null;
  var last = sheet.getLastRow();
  if (last < CRM.COMMERCIAL.DATA_START) return null;
  var numRows = last - CRM.COMMERCIAL.DATA_START + 1;
  var data = sheet.getRange(CRM.COMMERCIAL.DATA_START, 1, numRows, headers.length).getValues();
  var statusIdx = findHeaderIndex_(headers, 'Snapshot Status');
  var best = null;
  function cell(obj, names) {
    for (var i = 0; i < names.length; i++) {
      if (obj[names[i]] !== undefined && obj[names[i]] !== '') return obj[names[i]];
    }
    return '';
  }
  for (var i = data.length - 1; i >= 0; i--) {
    if (String(data[i][idIdx] || '').trim() !== leadId) continue;
    if (statusIdx >= 0) {
      var st = String(data[i][statusIdx] || '').trim().toLowerCase();
      if (st && st !== 'active') continue;
    }
    var obj = {};
    for (var h = 0; h < headers.length; h++) {
      obj[headers[h]] = data[i][h];
    }
    // Normalize to engine field names (must include Benefit Mode / Breakup for Partial).
    best = {
      leadId: leadId,
      bookingId: String(cell(obj, ['Booking ID']) || ''),
      snapshotId: String(cell(obj, ['Snapshot ID']) || ''),
      snapshotStatus: String(cell(obj, ['Snapshot Status']) || 'Active'),
      bookingDate: cell(obj, ['Booking Date']),
      model: cell(obj, ['Vehicle Model', 'Model']),
      vehicleModel: cell(obj, ['Vehicle Model', 'Model']),
      variant: cell(obj, ['Variant']),
      bookingExecutive: cell(obj, ['Booking Executive']),
      exShowroom: num_(cell(obj, ['Ex Showroom Price', 'Ex Showroom'])),
      accessories: num_(cell(obj, ['Accessories'])),
      insurance: num_(cell(obj, ['Insurance'])),
      registrationRto: num_(cell(obj, ['Registration / RTO', 'Registration RTO', 'Registration'])),
      fastag: num_(cell(obj, ['Fastag'])),
      handlingCharges: num_(cell(obj, ['Handling Charges', 'Handling'])),
      trc: num_(cell(obj, ['TRC'])),
      extendedWarranty: num_(cell(obj, ['Extended Warranty'])),
      rsaAmc: num_(cell(obj, ['RSA / AMC', 'RSA'])),
      otherCharges: num_(cell(obj, ['Other Charges'])),
      gstPercent: num_(cell(obj, ['GST %'])),
      tcsApplicable: cell(obj, ['TCS Applicable']) || 'No',
      tcs: num_(cell(obj, ['TCS'])),
      consumerDiscount: num_(cell(obj, ['Consumer Discount'])),
      exchangeBonus: num_(cell(obj, ['Exchange Bonus'])),
      loyaltyBonus: num_(cell(obj, ['Loyalty Bonus'])),
      referralBonus: num_(cell(obj, ['Referral Bonus'])),
      dsaDiscount: num_(cell(obj, ['DSA Discount', 'DSA Bonus'])),
      additionalDiscount: num_(cell(obj, ['Additional Discount'])),
      oemExtraSupportReceived: num_(cell(obj, ['OEM Extra Support Received'])),
      oemExtraSupportPassed: num_(cell(obj, ['OEM Extra Support Passed To Customer'])),
      oemExtraSupportRetained: num_(cell(obj, ['OEM Extra Support Retained'])),
      benefitMode: String(cell(obj, ['Benefit Mode']) || 'Full Benefit'),
      customerBenefitPassed: num_(cell(obj, ['Customer Benefit Passed'])),
      benefitPassedBreakup: String(cell(obj, ['Benefit Passed Breakup']) || ''),
      finalExchangeValue: num_(cell(obj, ['Final Exchange Value'])),
      evaluatedExchangeValue: num_(cell(obj, ['Evaluated Value', 'Evaluated Exchange Value'])),
      customerPayable: num_(cell(obj, ['Customer Payable'])),
      dealerMarginGrossInclGst: num_(cell(obj, ['Dealer Margin Gross (Incl GST)'])),
      dealerMarginGst: num_(cell(obj, ['Dealer Margin GST (5%)'])),
      dealerMarginNetExGst: num_(cell(obj, ['Dealer Margin Net (Ex GST)'])),
      grossInvoiceAmount: num_(cell(obj, ['Gross Invoice Amount'])),
      grossVehicleCost: num_(cell(obj, ['Gross Vehicle Cost'])),
      netVehicleCost: num_(cell(obj, ['Net Vehicle Cost'])),
      totalDiscount: num_(cell(obj, ['Total Discount'])),
      bookingAmount: num_(cell(obj, ['Booking Amount']))
    };
    // Keep typed OEM Extra Support; bleed cleanup is owner repair only.
    best.oemExtraSupportReceived = Math.max(0, num_(best.oemExtraSupportReceived));
    best.oemExtraSupportPassed = Math.max(0, Math.min(num_(best.oemExtraSupportPassed), best.oemExtraSupportReceived));
    best.oemExtraSupportRetained = round2_(Math.max(0, best.oemExtraSupportReceived - best.oemExtraSupportPassed));
    best.full = best;
    break;
  }
  return best;
}

/**
 * Owner repair: clear OEM Extra Support values that were falsely copied from
 * Scheme (Exchange / Total Discount), rewrite money formats, rebuild earnings.
 */
function repairOemExtraSupportSchemeBleed_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return { cleared: 0 };
  var hdrRow = CRM.COMMERCIAL.HEADER_ROW || 1;
  var dataStart = CRM.COMMERCIAL.DATA_START || 2;
  var headers = getHeaders_(sheet, hdrRow);
  var recvCol = findHeaderIndex_(headers, 'OEM Extra Support Received') + 1;
  var passCol = findHeaderIndex_(headers, 'OEM Extra Support Passed To Customer') + 1;
  var retCol = findHeaderIndex_(headers, 'OEM Extra Support Retained') + 1;
  var exchCol = findHeaderIndex_(headers, 'Exchange Bonus') + 1;
  var totCol = findHeaderIndex_(headers, 'Total Discount') + 1;
  var consCol = findHeaderIndex_(headers, 'Consumer Discount') + 1;
  var loyCol = findHeaderIndex_(headers, 'Loyalty Bonus') + 1;
  var refCol = findHeaderIndex_(headers, 'Referral Bonus') + 1;
  var dsaCol = findHeaderIndex_(headers, 'DSA Discount') + 1;
  if (dsaCol < 1) dsaCol = findHeaderIndex_(headers, 'DSA Bonus') + 1;
  var addCol = findHeaderIndex_(headers, 'Additional Discount') + 1;
  var statusCol = findHeaderIndex_(headers, 'Snapshot Status') + 1;
  if (recvCol < 1 || sheet.getLastRow() < dataStart) return { cleared: 0 };
  var n = sheet.getLastRow() - dataStart + 1;
  var cleared = 0;
  for (var r = 0; r < n; r++) {
    var row = dataStart + r;
    if (statusCol > 0) {
      var st = String(sheet.getRange(row, statusCol).getValue() || '').trim().toLowerCase();
      if (st && st !== 'active') continue;
    }
    var recv = num_(sheet.getRange(row, recvCol).getValue());
    if (!(recv > 0)) continue;
    var passed = passCol > 0 ? num_(sheet.getRange(row, passCol).getValue()) : 0;
    var exchange = exchCol > 0 ? num_(sheet.getRange(row, exchCol).getValue()) : 0;
    var totalDisc = totCol > 0 ? num_(sheet.getRange(row, totCol).getValue()) : 0;
    var schemeSum = round2_(
      (consCol > 0 ? num_(sheet.getRange(row, consCol).getValue()) : 0) +
      exchange +
      (loyCol > 0 ? num_(sheet.getRange(row, loyCol).getValue()) : 0) +
      (refCol > 0 ? num_(sheet.getRange(row, refCol).getValue()) : 0) +
      (dsaCol > 0 ? num_(sheet.getRange(row, dsaCol).getValue()) : 0) +
      (addCol > 0 ? num_(sheet.getRange(row, addCol).getValue()) : 0)
    );
    var onlyExchange = exchange > 0 && schemeSum === exchange;
    var bleed = (totalDisc > 0 && recv === totalDisc) ||
      (schemeSum > 0 && recv === schemeSum) ||
      (onlyExchange && recv === exchange);
    if (bleed && passed === 0) {
      sheet.getRange(row, recvCol).setNumberFormat('#,##0.00').setValue(0);
      if (passCol > 0) sheet.getRange(row, passCol).setNumberFormat('#,##0.00').setValue(0);
      if (retCol > 0) sheet.getRange(row, retCol).setNumberFormat('#,##0.00').setValue(0);
      cleared++;
    } else {
      sheet.getRange(row, recvCol).setNumberFormat('#,##0.00');
      if (passCol > 0) sheet.getRange(row, passCol).setNumberFormat('#,##0.00');
      if (retCol > 0) sheet.getRange(row, retCol).setNumberFormat('#,##0.00');
    }
  }
  return { cleared: cleared };
}
