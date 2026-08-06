/**
 * BusinessRulesService – single source for business calculations.
 */

function calcTotalDiscount_(offer) {
  offer = offer || {};
  return round2_(
    num_(offer.consumerDiscount) +
    num_(offer.exchangeBonus) +
    num_(offer.loyaltyBonus) +
    num_(offer.referralBonus) +
    num_(offer.dsaDiscount) +
    num_(offer.additionalDiscount)
  );
}

/**
 * Price + offer totals for dialogs/prefill — a thin ADAPTER over the one engine.
 *
 * DO NOT re-implement the money chain here. This function has been rewritten as a
 * duplicate implementation twice, and both times the copies drifted (different TCS
 * defaults → different Customer Payable for the same booking). All money math
 * lives in computeCommercialTotals_ (CommercialEngineService) — blueprint §4.
 *
 * Note: prefill has no Benefit Mode yet (mode is chosen at Scheme Update), so the
 * offer amounts are treated as Full Benefit here, matching the engine's default.
 */
function calcPriceTotals_(price, offer, finalExchangeValue) {
  price = price || {};
  offer = offer || {};
  var snap = {};
  Object.keys(price).forEach(function (k) { snap[k] = price[k]; });
  ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus',
    'dsaDiscount', 'additionalDiscount'].forEach(function (k) {
    snap[k] = num_(offer[k]);
  });
  // Prefill context: DSA entered at booking is intended, treat as approved for the
  // customer-facing quote; claim eligibility still gates on real approval later.
  snap._approvals = { dsaDiscount: 'Approved' };
  snap.finalExchangeValue = num_(finalExchangeValue);
  return computeCommercialTotals_(snap);
}

/** Outstanding = customer payable minus all payments received. */
function calcOutstanding_(customerPayable, bookingAmount, paymentsReceived) {
  if (arguments.length >= 2 && num_(bookingAmount) > 0 && num_(paymentsReceived) === 0) {
    return round2_(Math.max(0, num_(customerPayable) - num_(bookingAmount)));
  }
  return round2_(Math.max(0, num_(customerPayable) - num_(paymentsReceived)));
}

/** Lead-level outstanding from store (canonical — booked/commercial only, for payments). */
function computeLeadOutstanding_(leadId, store) {
  store = store || loadCrmStore_();
  var lead = store.leads.byId[leadId];
  var payable = getCommercialPayable_(leadId, store);
  var paid = store.paymentsByLead[leadId] || 0;
  var bookingAmt = lead ? num_(lead.bookingAmount || 0) : 0;
  return calcOutstanding_(payable, bookingAmt, paid);
}

/**
 * Estimated payable for pipeline leads — uses Price Master when model+variant set
 * but no booking snapshot yet. Used by Dashboard / Outstanding Leads / Lead Register.
 */
function getEstimatedCustomerPayable_(leadId, store) {
  store = store || loadCrmStore_();
  var bookedPayable = getCommercialPayable_(leadId, store);
  if (bookedPayable > 0) return bookedPayable;
  var lead = store.leads.byId[leadId] || {};
  var model = String(lead.interestedModel || '').trim();
  var variant = String(lead.variant || '').trim();
  if (!model || !variant) return 0;
  try {
    var breakup = getCommercialBreakup_(model, variant, nowDate_());
    var totals = calcPriceTotals_(breakup.price, {}, 0);
    return round2_(totals.customerPayable);
  } catch (e) {
    Logger.log('getEstimatedCustomerPayable_: ' + leadId + ' — ' + e.message);
    return 0;
  }
}

/** Dashboard / Outstanding tab — includes pipeline estimate for active non-delivered leads. */
function computeDashboardOutstanding_(leadId, store) {
  store = store || loadCrmStore_();
  var lead = store.leads.byId[leadId];
  if (!lead || !isActiveLead_(lead)) return 0;
  var status = String(lead.currentStatus || '').toLowerCase();
  if (status === 'delivered' || status === 'lost') {
    return computeLeadOutstanding_(leadId, store);
  }
  var payable = getEstimatedCustomerPayable_(leadId, store);
  if (payable <= 0) return 0;
  var paid = store.paymentsByLead[leadId] || 0;
  var bookingAmt = num_(lead.bookingAmount || 0);
  return calcOutstanding_(payable, bookingAmt, paid);
}

/** Write Price Master charge breakup + payable / outstanding to Lead Register. */
function syncLeadCommercialEstimate_(leadId, store) {
  leadId = String(leadId || '').trim();
  if (!leadId) return;
  store = store || loadCrmStore_(true);
  var lead = store.leads.byId[leadId];
  if (!lead) return;
  var model = String(lead.interestedModel || '').trim();
  var variant = String(lead.variant || '').trim();
  var customerOs = computeDashboardOutstanding_(leadId, store);
  var financeOs = typeof getFinanceOutstandingForLead_ === 'function'
    ? getFinanceOutstandingForLead_(leadId) : 0;
  var fields = {
    'Outstanding Amount': round2_(customerOs + financeOs),
    'Customer Outstanding': customerOs
  };
  if (model && variant) {
    try {
      var breakup = getCommercialBreakup_(model, variant, nowDate_());
      var price = breakup.price || {};
      var totals = calcPriceTotals_(price, {}, 0);
      fields['Ex Showroom'] = price.exShowroom;
      fields['RTO'] = price.registrationRto;
      fields['Insurance Amount'] = price.insurance;
      fields['Accessories Amount'] = price.accessories;
      fields['Handling Charges'] = price.handlingCharges;
      fields['TRC'] = price.trc;
      fields['Fastag'] = price.fastag;
      fields['Extended Warranty'] = price.extendedWarranty;
      fields['Other Charges'] = price.otherCharges;
      fields['Gross Vehicle Cost'] = breakup.grossVehicleCost != null
        ? breakup.grossVehicleCost : calculateGross_(price);
      fields['Customer Payable'] = totals.customerPayable;
      fields['Outstanding Amount'] = round2_(customerOs + financeOs);
    } catch (e) {
      Logger.log('syncLeadCommercialEstimate_: ' + leadId + ' — ' + e.message);
    }
  }
  updateLeadRegisterFields_(leadId, fields);
}

/**
 * Validate payment does not exceed payable.
 * When Customer Payable is still 0 (booking before Price Structure), allow the
 * payment as provisional so booking advances still hit Payment Ledger.
 */
function validatePaymentAmount_(leadId, amount, store, opts) {
  opts = opts || {};
  store = store || loadCrmStore_();
  var payable = getCommercialPayable_(leadId, store);
  var paid = store.paymentsByLead[leadId] || 0;
  var amt = num_(amount);
  if (amt <= 0) throw fieldError_('Amount', 'Enter an amount greater than zero.', 'VALIDATION');

  // Slim booking: price not set yet → Customer Payable is ₹0. Still record cash.
  if (payable <= 0.01) {
    return {
      payable: 0,
      paidSoFar: paid,
      running: paid + amt,
      outstanding: 0,
      provisional: true
    };
  }

  if (paid + amt > payable + 0.01) {
    if (opts.allowProvisional || opts.skipPayableCheck) {
      return {
        payable: payable,
        paidSoFar: paid,
        running: paid + amt,
        outstanding: Math.max(0, payable - paid - amt),
        provisional: true
      };
    }
    throw fieldError_('Amount', 'Payment exceeds Customer Payable (₹' + round2_(payable) + ').', 'VALIDATION');
  }
  return { payable: payable, paidSoFar: paid, running: paid + amt, outstanding: payable - paid - amt };
}

/** Delivery allowed when customer outstanding is zero (or negligible). */
function isDeliveryEligible_(leadId, store) {
  return computeLeadOutstanding_(leadId, store) <= 0.01;
}

/**
 * Company (OEM) outstanding from Scheme Master (Company Share ₹ by Model/Variant/Component).
 * Falls back to Settings share amounts only if Scheme Master has no matching row.
 */
function getSchemeShareAmount_(key) {
  var settings = getSettings_() || {};
  var map = {
    consumerDiscount: 'schemeShareConsumerDiscount',
    exchangeBonus: 'schemeShareExchangeBonus',
    loyaltyBonus: 'schemeShareLoyaltyBonus',
    referralBonus: 'schemeShareReferralBonus',
    dsaDiscount: 'schemeShareDsaDiscount'
  };
  var settingKey = map[key];
  if (!settingKey) return 0;
  var amt = Number(settings[settingKey]);
  if (!isFinite(amt) || amt < 0) amt = 0;
  return round2_(amt);
}

/** @deprecated */
function getSchemeSharePercent_(key) {
  return getSchemeShareAmount_(key);
}

function computeCompanyOutstanding_(leadId, store) {
  store = store || loadCrmStore_();
  leadId = String(leadId || '').trim();
  if (!leadId) return 0;

  // If claim already received, company outstanding is cleared.
  try {
    if (typeof isSchemeClaimReceivedForLead_ === 'function' && isSchemeClaimReceivedForLead_(leadId, store)) {
      return 0;
    }
  } catch (e) {}

  // Preferred: monthly Scheme Master (dealer/company ₹ from circular)
  try {
    if (typeof computeSchemeShareSplit_ === 'function') {
      var split = computeSchemeShareSplit_(leadId, store);
      if (split && (split.companyTotal > 0 || Object.keys(split.byComponent || {}).length)) {
        return round2_(split.companyTotal);
      }
    }
  } catch (e2) {
    Logger.log('computeCompanyOutstanding_ scheme master: ' + e2.message);
  }

  // Fallback: Settings amounts × applied OEM components on snapshot
  var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  if (!entry) return 0;
  var snap = entry.full || entry;
  var claim = deriveClaim_(snap, null);
  var company = 0;
  (claim.breakdown || []).forEach(function (b) {
    if (!b || b.payer !== 'OEM' || !b.claimable) return;
    var actual = num_(b.amount);
    if (actual <= 0) return;
    var shareAmt = getSchemeShareAmount_(b.key);
    var part = shareAmt > 0 ? Math.min(actual, shareAmt) : actual;
    company = round2_(company + part);
  });
  return company;
}

// buildLeadCommercialTruthFields_ is defined in Utils.gs (always deployed).
// Do not re-declare here — older Apps Script projects were missing this function
// and every Payment / Booking / Scheme save crashed.

function buildBookingComputation_(input) {
  input = input || {};
  var totals = calcPriceTotals_(input.price || {}, input.offer || {}, input.finalExchangeValue);
  var outstanding = calcOutstanding_(totals.customerPayable, input.bookingAmount, input.paymentsReceived);
  return { totals: totals, outstanding: outstanding };
}
