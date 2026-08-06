/**
 * OemClaimService.gs
 * ---------------------------------------------------------------------------
 * Management + audit layer on top of the Commercial Snapshot / Claim Register:
 *
 *   1. OEM Claim Dashboard      — claim lifecycle counts + values, OEM liability,
 *                                 monthly / scheme / executive summaries.
 *   2. Owner Commercial Report  — dealer vs OEM discount cost, scheme liability,
 *                                 claim ageing, ROI, exec usage, averages.
 *   3. Claim Exception Report   — automatic reconciliation of Register vs Snapshot
 *                                 vs Payments vs Booking → Missing / Duplicate /
 *                                 Incorrect / Unapproved / Overpayment / Negative.
 *
 * All money is derived from the certified pure core (deriveClaim_,
 * computeCommercialTotals_, ownerAggregates_, reconcileBooking_).
 * ---------------------------------------------------------------------------
 */

/* ============================ shared pure core ============================ */

/** Aggregate dealer/OEM cost + averages across a set of snapshots. */
function ownerAggregates_(bookings) {
  var agg = {
    count: 0, dealerDiscountCost: 0, oemDiscountCost: 0, totalDiscount: 0,
    exchangeBonusTotal: 0, exchangeBonusCount: 0, customerPayableTotal: 0,
    claimTotal: 0, claimEligible: 0, byExecutive: {}
  };
  (bookings || []).forEach(function (snap) {
    var dsaApproval = typeof resolveDsaApprovalForClaim_ === 'function'
      ? resolveDsaApprovalForClaim_(snap, snap._approvals && snap._approvals.dsaDiscount)
      : ((snap._approvals && snap._approvals.dsaDiscount) || 'Pending');
    var claimApprovals = { dsaDiscount: dsaApproval };
    var claim = deriveClaim_(snap, claimApprovals);
    var totals = computeCommercialTotals_(snap);
    // Company-share economics (July-2026 circular): only the OEM's share is
    // claimable/receivable; the dealer's own share is cost, never a claim.
    var income = (typeof computeSchemeIncomeBreakdown_ === 'function')
      ? computeSchemeIncomeBreakdown_(snap, claimApprovals) : null;
    var shares = (typeof computeSchemeClaimShares_ === 'function')
      ? computeSchemeClaimShares_(snap, claimApprovals) : null;
    var useShares = !!(shares && shares.shareSplitAvailable);
    var companyClaim = useShares ? shares.eligibleTotal
      : ((income && income.shareSplitAvailable) ? income.oemClaimTotal : claim.claimEligible);
    var companyOem = useShares ? shares.displayTotal
      : ((income && income.shareSplitAvailable) ? income.oemClaimTotal : claim.oemDiscount);
    agg.count++;
    agg.dealerDiscountCost = round2_(agg.dealerDiscountCost + claim.dealerDiscount);
    agg.oemDiscountCost = round2_(agg.oemDiscountCost + companyOem);
    agg.totalDiscount = round2_(agg.totalDiscount + totals.totalDiscount);
    agg.claimTotal = round2_(agg.claimTotal + companyClaim);
    agg.claimEligible = round2_(agg.claimEligible + companyClaim);
    agg.retainedIncome = round2_((agg.retainedIncome || 0) + (income ? income.retainedIncomeTotal : 0));
    agg.customerPayableTotal = round2_(agg.customerPayableTotal + totals.customerPayable);
    var eb = round2_(num_(snap.exchangeBonus));
    if (eb > 0) { agg.exchangeBonusTotal = round2_(agg.exchangeBonusTotal + eb); agg.exchangeBonusCount++; }
    var ex = String(snap.bookingExecutive || 'Unassigned');
    if (!agg.byExecutive[ex]) agg.byExecutive[ex] = { bookings: 0, totalDiscount: 0, dealerDiscount: 0, oemDiscount: 0 };
    agg.byExecutive[ex].bookings++;
    agg.byExecutive[ex].totalDiscount = round2_(agg.byExecutive[ex].totalDiscount + totals.totalDiscount);
    agg.byExecutive[ex].dealerDiscount = round2_(agg.byExecutive[ex].dealerDiscount + claim.dealerDiscount);
    agg.byExecutive[ex].oemDiscount = round2_(agg.byExecutive[ex].oemDiscount + companyOem);
  });
  agg.avgDiscount = agg.count ? round2_(agg.totalDiscount / agg.count) : 0;
  agg.avgExchangeBonus = agg.exchangeBonusCount ? round2_(agg.exchangeBonusTotal / agg.exchangeBonusCount) : 0;
  agg.avgCustomerPayable = agg.count ? round2_(agg.customerPayableTotal / agg.count) : 0;
  return agg;
}

/**
 * Reconcile a single booking. ctx:
 *   { snapshot, register|null, paidTotal, seenRefs }
 * Returns an array of exception objects.
 */
function reconcileBooking_(ctx) {
  var snap = ctx.snapshot || {};
  var reg = ctx.register || null;
  var paidTotal = round2_(num_(ctx.paidTotal));
  var seenRefs = ctx.seenRefs || {};
  var out = [];
  var leadId = snap.leadId;
  var bookingId = snap.bookingId || (reg && reg.bookingId) || '';

  var claim = deriveClaim_(snap, reg ? reg.approvals : null);
  var totals = computeCommercialTotals_(snap);
  var dsaApproval = typeof resolveDsaApprovalForClaim_ === 'function'
    ? resolveDsaApprovalForClaim_(snap, reg && reg.approvals ? reg.approvals.dsaDiscount : '')
    : ((reg && reg.approvals && reg.approvals.dsaDiscount) || 'Pending');
  var claimApprovals = { dsaDiscount: dsaApproval };
  // Exceptions must compare against the COMPANY SHARE (what is actually claimable
  // from the OEM). Comparing against full benefit amounts raised false "Incorrect
  // Claim Amount" flags on every correctly-filed claim.
  var income = (typeof computeSchemeIncomeBreakdown_ === 'function')
    ? computeSchemeIncomeBreakdown_(snap, claimApprovals) : null;
  var shares = (typeof computeSchemeClaimShares_ === 'function')
    ? computeSchemeClaimShares_(snap, claimApprovals) : null;
  var useShares = !!(shares && shares.shareSplitAvailable);
  var companyClaim = useShares ? shares.eligibleTotal
    : ((income && income.shareSplitAvailable) ? income.oemClaimTotal : claim.claimEligible);

  // MISSING CLAIM — OEM-funded money exists but no register row / zero claim.
  // Applies whether the benefit was passed to the customer or absorbed: either way
  // the dealer fronted the OEM's share and must recover it.
  if (companyClaim > 0) {
    if (!reg) {
      out.push({ leadId: leadId, bookingId: bookingId, type: 'Missing Claim', severity: 'High',
        detail: 'Claimable ' + companyClaim + ' (company share) but no register row' });
    } else if (round2_(num_(reg.claimAmount)) <= 0) {
      out.push({ leadId: leadId, bookingId: bookingId, type: 'Missing Claim', severity: 'High',
        detail: 'Claimable ' + companyClaim + ' (company share) but register claim is 0' });
    }
  }

  if (reg) {
    var regClaim = round2_(num_(reg.claimAmount));
    // INCORRECT CLAIM AMOUNT — register claim exceeds the company share.
    if (regClaim > round2_(companyClaim) + 0.01) {
      out.push({ leadId: leadId, bookingId: bookingId, type: 'Incorrect Claim Amount', severity: 'High',
        detail: 'Register ' + regClaim + ' exceeds claimable company share ' + companyClaim });
    } else if (regClaim && Math.abs(regClaim - round2_(companyClaim)) > 0.01) {
      out.push({ leadId: leadId, bookingId: bookingId, type: 'Claim Amount Mismatch', severity: 'Medium',
        detail: 'Register ' + regClaim + ' vs eligible company share ' + companyClaim });
    }
    // UNAPPROVED CLAIM — approval-required claimable component claimed unapproved.
    claim.breakdown.forEach(function (b) {
      if (b.claimable && b.approvalRequired && b.approvalStatus !== 'Approved' &&
          regClaim && regClaim >= b.amount) {
        out.push({ leadId: leadId, bookingId: bookingId, type: 'Unapproved Claim', severity: 'High',
          detail: b.label + ' ' + b.amount + ' claimed, approval=' + b.approvalStatus });
      }
    });
    // DUPLICATE CLAIM — same claim reference on more than one booking.
    var ref = String(reg.claimRef || '').trim();
    if (ref) {
      seenRefs[ref] = (seenRefs[ref] || 0) + 1;
      if (seenRefs[ref] > 1) {
        out.push({ leadId: leadId, bookingId: bookingId, type: 'Duplicate Claim', severity: 'High',
          detail: 'Claim reference reused: ' + ref });
      }
    }
  }

  // PAYMENT INTEGRITY — payments may never exceed customer payable.
  if (paidTotal > round2_(totals.customerPayable) + 0.01) {
    out.push({ leadId: leadId, bookingId: bookingId, type: 'Overpayment', severity: 'High',
      detail: 'Paid ' + paidTotal + ' > payable ' + totals.customerPayable });
  }

  // DATA INTEGRITY — negatives never allowed.
  if (totals.totalDiscount < 0) out.push({ leadId: leadId, bookingId: bookingId, type: 'Negative Discount', severity: 'High', detail: '' });
  if (num_(snap.finalExchangeValue) < 0) out.push({ leadId: leadId, bookingId: bookingId, type: 'Negative Exchange', severity: 'High', detail: '' });
  if (totals.customerPayable < 0) out.push({ leadId: leadId, bookingId: bookingId, type: 'Negative Payable', severity: 'High', detail: '' });

  return out;
}

/* ==================== register hydration (for reconcile) ================== */

/**
 * Read the Scheme Claim Register into a map: leadId -> register context object
 * used by reconcileBooking_ (approvals, claimAmount, claimRef, status).
 */
function readClaimRegisterForReconcile_() {
  var cfg = getClaimRegisterConfig_();
  var byLead = {};
  if (!cfg) return byLead;
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
  if (!sheet) return byLead;
  var lastRow = sheet.getLastRow();
  if (lastRow < cfg.DATA_START) return byLead;

  var headers = getHeaders_(sheet, cfg.HEADER_ROW);
  var numRows = lastRow - cfg.DATA_START + 1;
  var rows = sheet.getRange(cfg.DATA_START, 1, numRows, headers.length).getValues();
  rows.forEach(function (row) {
    var leadId = String(rowVal_(row, headers, 'Lead ID') || '').trim();
    if (!leadId) return;
    byLead[leadId] = {
      bookingId: String(rowVal_(row, headers, 'Booking ID') || '').trim(),
      claimAmount: parseNumber_(rowVal_(row, headers, 'Claim Amount')),
      claimRef: rowVal_(row, headers, 'Claim Reference Number'),
      claimStatus: String(rowVal_(row, headers, 'Claim Status') || '').trim(),
      submitted: formatDate_(rowVal_(row, headers, 'Claim Submitted Date')),
      approved: formatDate_(rowVal_(row, headers, 'Claim Approved Date')),
      received: formatDate_(rowVal_(row, headers, 'Claim Received Date')),
      approvals: { dsaDiscount: String(rowVal_(row, headers, 'DSA Approval') || 'Pending').trim() }
    };
  });
  return byLead;
}

/* ========================== OEM Claim Dashboard ========================== */

function ensureSimpleSheet_(sheetName, hidden) {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) sheet = ss.insertSheet(sheetName);
  sheet.clear();
  if (hidden && !sheet.isSheetHidden()) sheet.hideSheet();
  if (!hidden && sheet.isSheetHidden()) sheet.showSheet();
  return sheet;
}

function writeBlock_(sheet, startRow, title, headerRow, dataRows) {
  var r = startRow;
  sheet.getRange(r, 1).setValue(title).setFontWeight('bold').setFontSize(12);
  r += 1;
  if (headerRow && headerRow.length) {
    sheet.getRange(r, 1, 1, headerRow.length).setValues([headerRow]).setFontWeight('bold');
    r += 1;
  }
  if (dataRows && dataRows.length) {
    var width = headerRow && headerRow.length ? headerRow.length : dataRows[0].length;
    var norm = dataRows.map(function (row) {
      var out = row.slice(0, width);
      while (out.length < width) out.push('');
      return out;
    });
    sheet.getRange(r, 1, norm.length, width).setValues(norm);
    r += norm.length;
  }
  return r + 1; // trailing spacer
}

function buildOemClaimDashboard_() {
  var store = loadCrmStore_(true);
  var register = readClaimRegisterForReconcile_();
  var byLead = store.commercial.byLeadId || {};

  var statusCount = { Pending: 0, Submitted: 0, Approved: 0, Rejected: 0, Received: 0, 'Not Applicable': 0 };
  var statusValue = { Pending: 0, Submitted: 0, Approved: 0, Rejected: 0, Received: 0, 'Not Applicable': 0 };
  var totalOemClaimValue = 0, dealerShareValue = 0, companyShareValue = 0, totalDiscountValue = 0, eligibleValue = 0;
  var monthly = {}, scheme = {}, execu = {};

  Object.keys(byLead).forEach(function (leadId) {
    var snap = byLead[leadId].full || byLead[leadId];
    var reg = register[leadId] || null;
    var dsaApproval = typeof resolveDsaApprovalForClaim_ === 'function'
      ? resolveDsaApprovalForClaim_(snap, reg && reg.approvals ? reg.approvals.dsaDiscount : '')
      : ((reg && reg.approvals && reg.approvals.dsaDiscount) || 'Pending');
    var claimApprovals = { dsaDiscount: dsaApproval };
    var claim = deriveClaim_(snap, claimApprovals);
    var totals = computeCommercialTotals_(snap);

    // OEM receivable is the COMPANY SHARE only — the dealer's own share is never
    // claimable (July-2026 circular EM/07-2026/004 splits every component into
    // Dealer Share + Company Share). Falls back to full amounts only when Scheme
    // Master has no share rows for the model.
    var income = (typeof computeSchemeIncomeBreakdown_ === 'function')
      ? computeSchemeIncomeBreakdown_(snap, claimApprovals) : null;
    var shares = (typeof computeSchemeClaimShares_ === 'function')
      ? computeSchemeClaimShares_(snap, claimApprovals) : null;
    var useShares = !!(shares && shares.shareSplitAvailable);
    var companyClaim = useShares ? shares.eligibleTotal
      : ((income && income.shareSplitAvailable) ? income.oemClaimTotal : claim.claimEligible);
    var claimByComp = useShares ? shares.displayByComponent
      : ((income && income.shareSplitAvailable) ? income.oemClaimByComponent : null);

    var dealerScheme = 0;
    try {
      if (typeof schemeShareSplitFor_ === 'function') {
        var split = schemeShareSplitFor_(
          snap.model || '', snap.variant || '', snap.bookingDate || nowDate_(),
          typeof snapshotOemOffers_ === 'function' ? snapshotOemOffers_(snap) : snap
        );
        dealerScheme = num_(split && split.dealerTotal);
      }
    } catch (eSplit) { dealerScheme = 0; }
    if (!(dealerScheme > 0) && !useShares) dealerScheme = num_(claim.dealerDiscount);

    totalDiscountValue = round2_(totalDiscountValue + num_(totals.totalDiscount));
    dealerShareValue = round2_(dealerShareValue + dealerScheme);
    companyShareValue = round2_(companyShareValue + companyClaim);
    eligibleValue = round2_(eligibleValue + companyClaim);

    var claimAmt = reg ? round2_(num_(reg.claimAmount)) : 0;
    // A claim exists whenever the OEM funds any part — passed to customer or
    // absorbed by the dealer. "Not Applicable" only when company share is zero.
    var status = (reg && reg.claimStatus) ? reg.claimStatus :
      (companyClaim > 0 ? 'Pending' : 'Not Applicable');
    if (statusCount[status] === undefined) { statusCount[status] = 0; statusValue[status] = 0; }
    statusCount[status] += 1;
    statusValue[status] = round2_(statusValue[status] + (claimAmt || companyClaim));
    if (companyClaim > 0) totalOemClaimValue = round2_(totalOemClaimValue + companyClaim);

    var month = String(snap.bookingDate || '').substring(0, 7) || 'Unknown';
    if (!monthly[month]) monthly[month] = { bookings: 0, claim: 0, oem: 0 };
    monthly[month].bookings++;
    monthly[month].claim = round2_(monthly[month].claim + companyClaim);
    monthly[month].oem = round2_(monthly[month].oem + companyClaim);

    // Scheme-wise bifurcation at COMPANY-SHARE values (this is what gets submitted
    // to the OEM, component by component).
    claim.breakdown.forEach(function (b) {
      if (!b.claimable) return;
      var val = claimByComp ? num_(claimByComp[b.key]) : b.amount;
      if (!(val > 0)) return;
      if (!scheme[b.label]) scheme[b.label] = { count: 0, value: 0 };
      scheme[b.label].count++;
      scheme[b.label].value = round2_(scheme[b.label].value + val);
    });

    var ex = String(snap.bookingExecutive || 'Unassigned');
    if (!execu[ex]) execu[ex] = { bookings: 0, claim: 0 };
    execu[ex].bookings++;
    execu[ex].claim = round2_(execu[ex].claim + companyClaim); // company share, not full benefit
  });

  var bookingCount = Object.keys(byLead).length;
  var sheet = ensureSimpleSheet_(CRM.SHEETS.OEM_CLAIM_DASHBOARD, false);
  var r = 1;
  sheet.getRange(r, 1).setValue('OEM CLAIM DASHBOARD').setFontWeight('bold').setFontSize(14);
  sheet.getRange(r, 4).setValue('Generated: ' + nowDateTime_());
  r += 2;

  if (bookingCount === 0) {
    sheet.getRange(r, 1).setValue('No commercial data available.').setFontStyle('italic');
    sheet.autoResizeColumns(1, 4);
    return { bookings: 0, totalOemClaimValue: 0, empty: true };
  }

  r = writeBlock_(sheet, r, 'Claim Status Summary', ['Status', 'Bookings', 'Claim Value'],
    ['Pending', 'Submitted', 'Approved', 'Rejected', 'Received', 'Not Applicable'].map(function (s) {
      return [s, statusCount[s] || 0, statusValue[s] || 0];
    }));

  // Value Summary — matches operator semantics (row order matters for their sheet):
  // Total Discount → Eligible Claim → Company Share → Your Share → Not received
  r = writeBlock_(sheet, r, 'Value Summary', ['Metric', 'Amount'], [
    ['Total Discount Given (full scheme)', totalDiscountValue],
    ['Eligible Claim (company share)', eligibleValue],
    ['Euler Company Share', companyShareValue],
    ['Your Own Share (non-claimable)', dealerShareValue],
    ['OEM Liability (eligible not yet received)', round2_(eligibleValue - (statusValue['Received'] || 0))]
  ]);

  var monthKeys = Object.keys(monthly).sort();
  r = writeBlock_(sheet, r, 'Monthly Claim Summary', ['Scheme Month', 'Bookings', 'Claim Value', 'OEM Discount'],
    monthKeys.map(function (m) { return [m, monthly[m].bookings, monthly[m].claim, monthly[m].oem]; }));

  var schemeKeys = Object.keys(scheme).sort();
  r = writeBlock_(sheet, r, 'Scheme-wise Claim Summary', ['Scheme', 'Bookings', 'Claim Value'],
    schemeKeys.map(function (s) { return [s, scheme[s].count, scheme[s].value]; }));

  var execKeys = Object.keys(execu).sort();
  r = writeBlock_(sheet, r, 'Executive-wise Claim Summary', ['Executive', 'Bookings', 'Claim Value'],
    execKeys.map(function (e) { return [e, execu[e].bookings, execu[e].claim]; }));

  sheet.autoResizeColumns(1, 4);
  return { bookings: Object.keys(byLead).length, totalOemClaimValue: totalOemClaimValue };
}

/* ========================= Owner Commercial Report ======================= */

function buildOwnerCommercialReport_() {
  var store = loadCrmStore_(true);
  var register = readClaimRegisterForReconcile_();
  var byLead = store.commercial.byLeadId || {};

  var bookings = Object.keys(byLead).map(function (leadId) {
    var snap = byLead[leadId].full || byLead[leadId];
    var reg = register[leadId];
    if (reg) {
      snap._approvals = {
        dsaDiscount: typeof resolveDsaApprovalForClaim_ === 'function'
          ? resolveDsaApprovalForClaim_(snap, reg.approvals.dsaDiscount)
          : reg.approvals.dsaDiscount
      };
    } else if (typeof resolveDsaApprovalForClaim_ === 'function') {
      snap._approvals = { dsaDiscount: resolveDsaApprovalForClaim_(snap, '') };
    }
    return snap;
  });
  var agg = ownerAggregates_(bookings);

  // Claim lifecycle + ageing from register.
  var pendingClaims = 0, pendingValue = 0, ageingSum = 0, ageingCount = 0, receivedValue = 0;
  Object.keys(register).forEach(function (leadId) {
    var reg = register[leadId];
    var amt = round2_(num_(reg.claimAmount));
    var status = reg.claimStatus || 'Pending';
    if (status === 'Received') { receivedValue = round2_(receivedValue + amt); }
    else if (amt > 0 && status !== 'Rejected' && status !== 'Not Applicable') {
      pendingClaims++; pendingValue = round2_(pendingValue + amt);
    }
    if (reg.submitted) {
      var end = reg.received || reg.approved || nowDate_();
      var d = daysBetween_(reg.submitted, end);
      if (d !== '' && !isNaN(d)) { ageingSum += d; ageingCount++; }
    }
  });
  var avgAgeing = ageingCount ? round2_(ageingSum / ageingCount) : 0;

  // Scheme ROI = OEM-funded discount as a share of total discount cost.
  var schemeRoi = agg.totalDiscount > 0 ? round2_((agg.oemDiscountCost / agg.totalDiscount) * 100) : 0;

  var bookingCount = Object.keys(byLead).length;
  var sheet = ensureSimpleSheet_(CRM.SHEETS.OWNER_COMMERCIAL_REPORT, false);
  var r = 1;
  sheet.getRange(r, 1).setValue('OWNER COMMERCIAL REPORT').setFontWeight('bold').setFontSize(14);
  sheet.getRange(r, 4).setValue('Generated: ' + nowDateTime_());
  r += 2;

  if (bookingCount === 0) {
    sheet.getRange(r, 1).setValue('No commercial data available.').setFontStyle('italic');
    sheet.autoResizeColumns(1, 4);
    return { bookings: 0, empty: true };
  }

  r = writeBlock_(sheet, r, 'Discount Cost Ownership', ['Metric', 'Amount'], [
    ['Total Bookings', agg.count],
    ['Your Own Share Given (dealer cost)', agg.dealerDiscountCost],
    ['OEM-Funded (company share)', agg.oemDiscountCost],
    ['Total Discount Given', agg.totalDiscount],
    ['OEM Receivable (company share)', agg.claimTotal],
    ['Scheme Income Retained (absorbed, company share)', agg.retainedIncome || 0]
  ]);

  r = writeBlock_(sheet, r, 'Claim Position', ['Metric', 'Value'], [
    ['Pending Claims (count)', pendingClaims],
    ['Pending Claim Value', pendingValue],
    ['Received Claim Value', receivedValue],
    ['Average Claim Ageing (days)', avgAgeing],
    ['Scheme ROI (OEM % of total discount)', schemeRoi]
  ]);

  r = writeBlock_(sheet, r, 'Averages', ['Metric', 'Amount'], [
    ['Average Discount / Booking', agg.avgDiscount],
    ['Average Exchange Bonus', agg.avgExchangeBonus],
    ['Average Customer Payable', agg.avgCustomerPayable]
  ]);

  var execKeys = Object.keys(agg.byExecutive).sort();
  r = writeBlock_(sheet, r, 'Executive Discount Usage',
    ['Executive', 'Bookings', 'Total Discount', 'Dealer Discount', 'OEM Discount'],
    execKeys.map(function (e) {
      var x = agg.byExecutive[e];
      return [e, x.bookings, x.totalDiscount, x.dealerDiscount, x.oemDiscount];
    }));

  sheet.autoResizeColumns(1, 5);
  return { bookings: agg.count, dealer: agg.dealerDiscountCost, oem: agg.oemDiscountCost };
}

/* ======================== Claim Exception Report ========================= */

function ensureClaimExceptionSheet_() {
  var cfg = CRM.CLAIM_EXCEPTION;
  var sheet = ensureSimpleSheet_(CRM.SHEETS.CLAIM_EXCEPTION, false);
  sheet.getRange(cfg.HEADER_ROW, 1, 1, cfg.COLS.length).setValues([cfg.COLS]).setFontWeight('bold');
  sheet.setFrozenRows(cfg.HEADER_ROW);
  return sheet;
}

function reconcileAllClaims_() {
  var cfg = CRM.CLAIM_EXCEPTION;
  var store = loadCrmStore_(true);
  var register = readClaimRegisterForReconcile_();
  var byLead = store.commercial.byLeadId || {};
  var seenRefs = {};
  var exceptions = [];

  Object.keys(byLead).forEach(function (leadId) {
    var snap = byLead[leadId].full || byLead[leadId];
    var reg = register[leadId] || null;
    var paid = store.paymentsByLead[leadId] || 0;
    var rows = reconcileBooking_({ snapshot: snap, register: reg, paidTotal: paid, seenRefs: seenRefs });
    rows.forEach(function (ex) { exceptions.push(ex); });
  });

  var sheet = ensureClaimExceptionSheet_();
  var gen = nowDateTime_();
  var version = (typeof getVersionTag_ === 'function') ? getVersionTag_() : '';
  if (exceptions.length) {
    var out = exceptions.map(function (ex) {
      return [gen, ex.leadId || '', ex.bookingId || '', ex.type, ex.severity, ex.detail || '', version];
    });
    sheet.getRange(cfg.DATA_START, 1, out.length, cfg.COLS.length).setValues(out);
  } else {
    sheet.getRange(cfg.DATA_START, 1, 1, cfg.COLS.length)
      .setValues([[gen, '', '', 'None', 'Info', 'No exceptions — register reconciles cleanly.', version]]);
  }
  return { exceptions: exceptions.length };
}

/* --------------------------------- menu ---------------------------------- */

function menuOemClaimDashboard() {
  try {
    var res = buildOemClaimDashboard_();
    var msg = res.empty
      ? 'No commercial data available.'
      : 'OEM Claim Dashboard refreshed (' + res.bookings + ' bookings).';
    try { SpreadsheetApp.getActive().toast(msg, 'OEM Claims', 5); } catch (e) {}
    try { logAudit_('OEM Claim Dashboard', res.empty ? 'empty' : res.bookings + ' bookings'); } catch (e) {}
    return res;
  } catch (err) {
    try {
      SpreadsheetApp.getUi().alert('OEM Claim Dashboard', 'No commercial data available.\n\nDetail: ' + err.message, SpreadsheetApp.getUi().ButtonSet.OK);
    } catch (e) {}
    return { bookings: 0, empty: true, error: err.message };
  }
}

function menuOwnerCommercialReport() {
  try {
    var res = buildOwnerCommercialReport_();
    var msg = res.empty ? 'No commercial data available.' : 'Owner Commercial Report refreshed.';
    try { SpreadsheetApp.getActive().toast(msg, 'Owner Report', 5); } catch (e) {}
    try { logAudit_('Owner Commercial Report', res.empty ? 'empty' : res.bookings + ' bookings'); } catch (e) {}
    return res;
  } catch (err) {
    try {
      SpreadsheetApp.getUi().alert('Owner Commercial Report', 'No commercial data available.\n\nDetail: ' + err.message, SpreadsheetApp.getUi().ButtonSet.OK);
    } catch (e) {}
    return { bookings: 0, empty: true, error: err.message };
  }
}

function menuReconcileClaims() {
  try {
    var res = reconcileAllClaims_();
    try { SpreadsheetApp.getActive().toast(res.exceptions + ' exception(s) found.', 'Claim Reconciliation', 5); } catch (e) {}
    try { logAudit_('Claim Reconciliation', res.exceptions + ' exceptions'); } catch (e) {}
    return res;
  } catch (err) {
    try { SpreadsheetApp.getUi().alert('Claim Reconciliation failed: ' + err.message); } catch (e) {}
    throw err;
  }
}
