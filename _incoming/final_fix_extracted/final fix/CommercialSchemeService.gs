/**
 * CommercialSchemeService.gs
 * ---------------------------------------------------------------------------
 * Builds and refreshes the SCHEME CLAIM REGISTER — one row per booking.
 *
 * Design contract:
 *   - Derived columns (discounts, dealer/OEM split, claim required/eligible)
 *     are recomputed from the ACTIVE Commercial Snapshot on every rebuild via
 *     the certified pure core (deriveClaim_).
 *   - Operator lifecycle columns (DSA Approval, Claim Status, references, dates,
 *     remarks) and the operator-entered Claim Amount are PRESERVED across every
 *     rebuild, keyed by Booking ID (Lead ID fallback).
 *   - DSA Approval feeds back into claim eligibility: an approval-required OEM
 *     component (DSA Bonus) only becomes eligible once the operator marks it
 *     'Approved' in the register.
 * ---------------------------------------------------------------------------
 */

function getClaimRegisterConfig_() {
  return (CRM && CRM.CLAIM_REGISTER) || null;
}

/** Whole-day difference between two yyyy-MM-dd strings; '' if unparseable. */
function daysBetween_(fromIso, toIso) {
  if (!fromIso) return '';
  var a = new Date(String(fromIso).substring(0, 10) + 'T00:00:00');
  var b = new Date(String(toIso || fromIso).substring(0, 10) + 'T00:00:00');
  if (isNaN(a.getTime()) || isNaN(b.getTime())) return '';
  return Math.round((b - a) / 86400000);
}

/** Create the register sheet (visible — operators edit it) and sync its header. */
function ensureClaimRegisterSheet_() {
  var cfg = getClaimRegisterConfig_();
  if (!cfg || !cfg.COLS || !cfg.COLS.length) return null;
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.SCHEME_CLAIM_REGISTER;
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);

  // Append-only missing headers (never rewrite in place — preserves column data).
  var headers = getHeaders_(sheet, cfg.HEADER_ROW);
  if (!headers.length) {
    sheet.getRange(cfg.HEADER_ROW, 1, 1, cfg.COLS.length).setValues([cfg.COLS]).setFontWeight('bold');
    sheet.setFrozenRows(cfg.HEADER_ROW);
  } else {
    cfg.COLS.forEach(function (colName) {
      headers = getHeaders_(sheet, cfg.HEADER_ROW);
      if (findHeaderIndex_(headers, colName) < 0) {
        sheet.getRange(cfg.HEADER_ROW, headers.length + 1).setValue(colName).setFontWeight('bold');
      }
    });
  }
  if (typeof ensureClaimRegisterValidation_ === 'function') ensureClaimRegisterValidation_(sheet);
  return sheet;
}

/**
 * Read the existing register and return a map of preserved operator values,
 * keyed by Booking ID (and mirrored by Lead ID for resilience).
 */
function readClaimRegisterLifecycle_() {
  var cfg = getClaimRegisterConfig_();
  var out = { byBooking: {}, byLead: {} };
  if (!cfg) return out;
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
  if (!sheet) return out;
  var lastRow = sheet.getLastRow();
  if (lastRow < cfg.DATA_START) return out;

  var headers = getHeaders_(sheet, cfg.HEADER_ROW);
  var numRows = lastRow - cfg.DATA_START + 1;
  var rows = sheet.getRange(cfg.DATA_START, 1, numRows, headers.length).getValues();
  var preserveCols = (cfg.LIFECYCLE_COLS || []).concat(['Claim Amount', 'Claim ID']);

  rows.forEach(function (row) {
    var bookingId = String(rowVal_(row, headers, 'Booking ID') || '').trim();
    var leadId = String(rowVal_(row, headers, 'Lead ID') || '').trim();
    if (!bookingId && !leadId) return;
    var saved = {};
    preserveCols.forEach(function (col) { saved[col] = rowVal_(row, headers, col); });
    if (bookingId) out.byBooking[bookingId] = saved;
    if (leadId) out.byLead[leadId] = saved;
  });
  return out;
}

/** Pull the preserved operator record for a booking, if any. */
function preservedClaimValues_(preserved, bookingId, leadId) {
  if (!preserved) return {};
  if (bookingId && preserved.byBooking[bookingId]) return preserved.byBooking[bookingId];
  if (leadId && preserved.byLead[leadId]) return preserved.byLead[leadId];
  return {};
}

/**
 * Rebuild the Scheme Claim Register from Active snapshots.
 * NEVER deletes rows — manual entries and settled claims are permanent.
 * Auto rows refresh derived columns; lifecycle fields are preserved by Claim ID.
 */
function rebuildSchemeClaimRegister_() {
  var cfg = getClaimRegisterConfig_();
  if (!cfg) throw new Error('CLAIM_REGISTER config missing.');

  var store = loadCrmStore_(true);
  var sheet = ensureClaimRegisterSheet_();
  if (!sheet) throw new Error('Could not create Scheme Claim Register sheet.');
  if (typeof ensureClaimRegisterValidation_ === 'function') ensureClaimRegisterValidation_(sheet);

  // Index ALL existing rows by Claim ID — nothing removed on rebuild.
  var claimById = {};
  if (typeof readAllClaims_ === 'function') {
    readAllClaims_().forEach(function (c) {
      claimById[c.claimId] = c.map;
    });
  } else {
    var preserved = readClaimRegisterLifecycle_();
    Object.keys(preserved.byBooking).forEach(function (bid) {
      var s = preserved.byBooking[bid];
      var cid = String(s['Claim ID'] || '').trim();
      if (cid) claimById[cid] = s;
    });
  }

  var byLead = store.commercial.byLeadId || {};
  var preservedLegacy = readClaimRegisterLifecycle_();
  var leadIds = Object.keys(byLead);
  leadIds.sort(function (a, b) {
    var da = String((byLead[a].full && byLead[a].full.bookingDate) || byLead[a].bookingDate || '');
    var db = String((byLead[b].full && byLead[b].full.bookingDate) || byLead[b].bookingDate || '');
    if (da !== db) return da < db ? -1 : 1;
    return String(byLead[a].bookingId) < String(byLead[b].bookingId) ? -1 : 1;
  });

  var touchedBookingIds = {};

  var COMP_LABELS = {
    consumerDiscount: 'Consumer Discount',
    exchangeBonus: 'Exchange Bonus',
    loyaltyBonus: 'Loyalty Bonus',
    referralBonus: 'Referral Bonus',
    dsaDiscount: 'DSA Discount',
    rtoInsuranceBenefit: 'Free RTO + Free Insurance',
    rtoBenefit: 'RTO Benefits Up to',
    insuranceBenefit: 'Insurance Benefits Up to'
  };
  var COMP_COL = {
    consumerDiscount: 'Consumer Discount',
    exchangeBonus: 'Exchange Bonus',
    loyaltyBonus: 'Loyalty Bonus',
    referralBonus: 'Referral Bonus',
    dsaDiscount: 'DSA Discount'
  };

  leadIds.forEach(function (leadId) {
    var entry = byLead[leadId];
    var snap = entry.full || entry;
    var lead = store.leads.byId[leadId] || {};
    var bookingId = String(entry.bookingId || '').trim();
    touchedBookingIds[bookingId] = true;

    var dsaApproval = 'Pending';
    Object.keys(claimById).forEach(function (cid) {
      var m = claimById[cid];
      if (String(m['Source'] || '').trim() === 'Manual') return;
      if (bookingId && String(m['Booking ID'] || '').trim() === bookingId) {
        if (m['DSA Approval']) dsaApproval = String(m['DSA Approval']);
      }
    });
    dsaApproval = resolveDsaApprovalForClaim_(snap, dsaApproval);
    var claimApprovals = { dsaDiscount: dsaApproval };
    var claim = deriveClaim_(snap, claimApprovals);
    var totals = computeCommercialTotals_(snap);
    var income = typeof computeSchemeIncomeBreakdown_ === 'function'
      ? computeSchemeIncomeBreakdown_(snap, claimApprovals) : null;
    var claimShares = typeof computeSchemeClaimShares_ === 'function'
      ? computeSchemeClaimShares_(snap, claimApprovals) : null;
    var fullSplit = null;
    try {
      if (typeof schemeShareSplitFor_ === 'function') {
        fullSplit = schemeShareSplitFor_(
          snap.model || lead.interestedModel || '',
          snap.variant || lead.variant || '',
          snap.bookingDate || entry.bookingDate || nowDate_(),
          typeof snapshotOemOffers_ === 'function' ? snapshotOemOffers_(snap) : snap
        );
      }
    } catch (splitErr) {
      fullSplit = null;
    }
    var byComp = (claimShares && claimShares.eligibleByComponent) || {};
    var compKeys = Object.keys(byComp).filter(function (k) { return num_(byComp[k]) > 0; });
    // Fallback: if no share split, one aggregate row (legacy behaviour).
    if (!compKeys.length) {
      var fallbackAmt = (claimShares && claimShares.shareSplitAvailable)
        ? claimShares.eligibleTotal
        : ((income && income.shareSplitAvailable) ? income.oemClaimTotal : claim.claimEligible);
      if (fallbackAmt > 0) {
        byComp = { _aggregate: fallbackAmt };
        compKeys = ['_aggregate'];
      }
    }

    var dealerSchemeShare = fullSplit ? num_(fullSplit.dealerTotal) : 0;
    var dealerDiscountTotal = round2_(dealerSchemeShare + num_(snap.additionalDiscount));
    var oemSchemeTotal = round2_(num_(totals.oemEligible) || num_(claim.oemDiscount));
    var bookingDate = String(snap.bookingDate || entry.bookingDate || '');
    var schemeMonth = bookingDate ? bookingDate.substring(0, 7) : '';

    // Preserve Received / Manual aggregate rows for this booking; drop open auto aggregates
    // once we have per-component rows (avoid double-counting open claims).
    Object.keys(claimById).forEach(function (cid) {
      var m = claimById[cid];
      if (String(m['Source'] || '').trim() === 'Manual') return;
      if (!(bookingId && String(m['Booking ID'] || '').trim() === bookingId) &&
          String(m['Lead ID'] || '').trim() !== leadId) return;
      var hasComp = String(m['Component Key'] || m['Component'] || '').trim();
      var st = String(m['Claim Status'] || '').toLowerCase();
      if (!hasComp && st !== 'received' && compKeys.length && compKeys[0] !== '_aggregate') {
        delete claimById[cid];
      }
    });

    compKeys.forEach(function (compKey) {
      var companyAmt = round2_(num_(byComp[compKey]));
      if (!(companyAmt > 0)) return;
      var compLabel = COMP_LABELS[compKey] || (compKey === '_aggregate' ? 'OEM Scheme Total' : compKey);
      var existingMap = null;
      var existingId = '';
      Object.keys(claimById).forEach(function (cid) {
        var m = claimById[cid];
        if (String(m['Source'] || '').trim() === 'Manual') return;
        var sameBooking = bookingId && String(m['Booking ID'] || '').trim() === bookingId;
        var sameLead = String(m['Lead ID'] || '').trim() === leadId;
        if (!sameBooking && !sameLead) return;
        var mk = String(m['Component Key'] || '').trim();
        var ml = String(m['Component'] || '').trim();
        if (mk === compKey || ml === compLabel) {
          existingMap = m; existingId = cid;
        } else if (!mk && !ml && compKey === '_aggregate') {
          existingMap = m; existingId = cid;
        }
      });

      var saved = existingMap;
      if (!saved || !saved['Claim ID']) {
        saved = preservedClaimValues_(preservedLegacy, bookingId, leadId);
      }
      var claimRequired = 'Yes';
      var claimStatus = (saved && String(saved['Claim Status'] || '').trim()) || 'Pending';
      var submitted = (saved && saved['Claim Submitted Date']) || '';
      var approved = (saved && saved['Claim Approved Date']) || '';
      var received = (saved && saved['Claim Received Date']) || '';
      var receivedAmt = saved ? saved['Received Amount'] : '';
      var ageing = submitted ? daysBetween_(submitted, received || approved || nowDate_()) : '';
      var claimAmountRaw = saved ? saved['Claim Amount'] : undefined;
      var claimAmount = (claimAmountRaw === '' || claimAmountRaw === undefined || claimAmountRaw === null)
        ? companyAmt : num_(claimAmountRaw);

      var claimId = (saved && String(saved['Claim ID'] || '').trim()) || generateId_('claim');
      var rowMap = {
        'Claim ID': claimId,
        'Source': (saved && saved['Source']) ? saved['Source'] : 'Auto',
        'Booking ID': bookingId,
        'Lead ID': leadId,
        'Customer': lead.customerName || '',
        'Model': snap.model || lead.interestedModel || '',
        'Variant': snap.variant || lead.variant || '',
        'Booking Date': bookingDate,
        'Scheme Month': schemeMonth,
        'Executive': snap.bookingExecutive || lead.executive || '',
        'Component': compLabel,
        'Component Key': compKey === '_aggregate' ? '' : compKey,
        'Consumer Discount': 0,
        'Exchange Bonus': 0,
        'Loyalty Bonus': 0,
        'Referral Bonus': 0,
        'DSA Discount': 0,
        'Additional Discount': 0,
        'Total Discount': companyAmt,
        'Dealer Discount': dealerDiscountTotal,
        'OEM Discount': oemSchemeTotal,
        'DSA Approval': dsaApproval,
        'Claim Required': claimRequired,
        'Eligible Claim': companyAmt,
        'Claim Amount': round2_(claimAmount),
        'Received Amount': receivedAmt === '' || receivedAmt === undefined ? '' : round2_(num_(receivedAmt)),
        'Claim Status': claimStatus,
        'Claim Reference Number': (saved && saved['Claim Reference Number']) || '',
        'Claim Submitted Date': submitted,
        'Claim Approved Date': approved,
        'Claim Received Date': received,
        'Claim Ageing (Days)': ageing,
        'Claim Remarks': (saved && saved['Claim Remarks']) || ''
      };
      // Put full scheme amount in the matching component column for readability.
      if (COMP_COL[compKey]) {
        rowMap[COMP_COL[compKey]] = num_(snap[compKey]);
      } else if (compKey === '_aggregate') {
        rowMap['Consumer Discount'] = num_(snap.consumerDiscount);
        rowMap['Exchange Bonus'] = num_(snap.exchangeBonus);
        rowMap['Loyalty Bonus'] = num_(snap.loyaltyBonus);
        rowMap['Referral Bonus'] = num_(snap.referralBonus);
        rowMap['DSA Discount'] = num_(snap.dsaDiscount);
        rowMap['Additional Discount'] = num_(snap.additionalDiscount);
        rowMap['Total Discount'] = totals.totalDiscount;
      }
      claimById[claimId] = rowMap;
      try {
        upsertRelationshipIndex_({
          LeadID: leadId,
          BookingID: bookingId,
          ClaimID: claimId,
          'Current Status': claimStatus || 'Booked'
        });
      } catch (re) {}
    });
  });

  // Write ALL claims (auto updated + manual + orphaned auto rows — never archive).
  var outRows = Object.keys(claimById).map(function (cid) {
    var rowMap = claimById[cid];
    return cfg.COLS.map(function (c) { return rowMap[c] === undefined ? '' : rowMap[c]; });
  });

  outRows.sort(function (a, b) {
    var da = String(a[cfg.COLS.indexOf('Booking Date')] || a[cfg.COLS.indexOf('Scheme Month')] || '');
    var db = String(b[cfg.COLS.indexOf('Booking Date')] || b[cfg.COLS.indexOf('Scheme Month')] || '');
    return da < db ? -1 : da > db ? 1 : 0;
  });

  // Align header row to config order before rewriting data (Component columns).
  sheet.getRange(cfg.HEADER_ROW, 1, 1, cfg.COLS.length).setValues([cfg.COLS]).setFontWeight('bold');
  sheet.setFrozenRows(cfg.HEADER_ROW);

  var lastRow = sheet.getLastRow();
  if (lastRow >= cfg.DATA_START) {
    sheet.getRange(cfg.DATA_START, 1, lastRow - cfg.DATA_START + 1, Math.max(cfg.COLS.length, sheet.getLastColumn())).clearContent();
  }
  if (outRows.length) {
    sheet.getRange(cfg.DATA_START, 1, outRows.length, cfg.COLS.length).setValues(outRows);
  }
  if (typeof ensureClaimRegisterValidation_ === 'function') ensureClaimRegisterValidation_(sheet);
  try {
    if (typeof navRefreshColumnLinks_ === 'function') {
      navRefreshColumnLinks_(getSpreadsheet_(), CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Claim ID',
        CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Claim ID', cfg.HEADER_ROW);
      navRefreshColumnLinks_(getSpreadsheet_(), CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Lead ID',
        CRM.SHEETS.LEAD_REGISTER, 'Lead ID', cfg.HEADER_ROW);
    }
  } catch (nl) {}
  return { rows: outRows.length };
}

/* --------------------------------- menu ---------------------------------- */

function menuRebuildClaimRegister() {
  try {
    var res = rebuildSchemeClaimRegister_();
    try {
      SpreadsheetApp.getActive().toast(res.rows + ' bookings written to Scheme Claim Register.', 'Claim Register', 5);
    } catch (toastErr) {}
    try { logAudit_('Rebuild Claim Register', res.rows + ' bookings'); } catch (aErr) {}
    return res;
  } catch (e) {
    try { SpreadsheetApp.getUi().alert('Rebuild Claim Register failed: ' + e.message); } catch (uiErr) {}
    throw e;
  }
}
