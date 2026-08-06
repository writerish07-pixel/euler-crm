/**
 * ExtraIncomeService.gs — Dealer Earnings Engine (Owner Only)
 *
 * Evolved from Extra Income Register. Single source of truth for dealership
 * profitability per Lead. Never affects Customer Payable / Outstanding.
 *
 * Reuses: CommercialEngine (OEM / Benefit Passed / Retained), Insurance Engine.
 * Sheet: Dealer Earnings Register (always visible). One Lead ID = one row.
 */

var DEALER_EARNINGS_MANUAL_COLS_ = [
  'Other Income',
  'Customer Insurance Benefit Passed',
  'Finance Incentive',
  'Accessories Margin',
  'Exchange Margin',
  'Documentation Income',
  'Warranty Income',
  'RSA Income',
  'Referral Income',
  'Campaign Incentive'
];

function dealerEarningsRegisterName_() {
  return (CRM.SHEETS && CRM.SHEETS.DEALER_EARNINGS_REGISTER) ||
    CRM.SHEETS.EXTRA_INCOME_REGISTER || 'Dealer Earnings Register';
}

function dealerEarningsAnalyticsName_() {
  return (CRM.SHEETS && CRM.SHEETS.DEALER_EARNINGS_ANALYTICS) ||
    CRM.SHEETS.EXTRA_INCOME_ANALYTICS || 'Dealer Earnings Analytics';
}

function dealerEarningsCols_() {
  return (CRM.DEALER_EARNINGS_REGISTER && CRM.DEALER_EARNINGS_REGISTER.COLS) ||
    (CRM.EXTRA_INCOME_REGISTER && CRM.EXTRA_INCOME_REGISTER.COLS) || [];
}

function dealerEarningsHeaderRow_() {
  return (CRM.DEALER_EARNINGS_REGISTER && CRM.DEALER_EARNINGS_REGISTER.HEADER_ROW) ||
    (CRM.EXTRA_INCOME_REGISTER && CRM.EXTRA_INCOME_REGISTER.HEADER_ROW) || 1;
}

function dealerEarningsDataStart_() {
  return (CRM.DEALER_EARNINGS_REGISTER && CRM.DEALER_EARNINGS_REGISTER.DATA_START) ||
    (CRM.EXTRA_INCOME_REGISTER && CRM.EXTRA_INCOME_REGISTER.DATA_START) || 2;
}

/** Rename legacy Extra Income sheets → Dealer Earnings (one-time soft migrate). */
function migrateDealerEarningsSheetNames_() {
  var ss = getSpreadsheet_();
  var pairs = [
    ['Extra Income Register', dealerEarningsRegisterName_()],
    ['Extra Income Analytics', dealerEarningsAnalyticsName_()]
  ];
  pairs.forEach(function (p) {
    var oldName = p[0];
    var newName = p[1];
    if (!newName || oldName === newName) return;
    var oldSh = ss.getSheetByName(oldName);
    var newSh = ss.getSheetByName(newName);
    if (oldSh && !newSh) {
      try { oldSh.setName(newName); } catch (e) {
        Logger.log('migrateDealerEarningsSheetNames_: ' + e.message);
      }
    }
  });
}

function ensureDealerEarningsRegisterSheet_() {
  migrateDealerEarningsSheetNames_();
  var name = dealerEarningsRegisterName_();
  if (!name) return null;
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var cols = dealerEarningsCols_();
  var headerRow = dealerEarningsHeaderRow_();
  var headers = getHeaders_(sheet, headerRow);
  var mismatch = headers.length !== cols.length;
  if (!mismatch) {
    for (var i = 0; i < cols.length; i++) {
      if (String(headers[i] || '').trim() !== cols[i]) { mismatch = true; break; }
    }
  }
  if (mismatch || sheet.getLastRow() < 1) {
    if (sheet.getLastRow() < 1) {
      sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    } else {
      cols.forEach(function (c) {
        if (findHeaderIndex_(headers, c) < 0) {
          sheet.getRange(1, headers.length + 1).setValue(c).setFontWeight('bold');
          headers = getHeaders_(sheet, 1);
        }
      });
    }
    sheet.setFrozenRows(1);
  }
  // Always migrate aliases / fix OEM Extra Support header duplicates
  migrateDealerEarningsHeaderAliases_(sheet);
  // Always visible — never auto-hide.
  if (sheet.isSheetHidden()) sheet.showSheet();
  return sheet;
}

function migrateDealerEarningsHeaderAliases_(sheet) {
  var aliases = {
    'Customer': 'Customer Name',
    'Salesperson': 'Executive',
    'OEM Eligible': 'OEM Eligible Scheme',
    'Dealer Benefit Retained': 'Dealer Scheme Retained',
    'Insurance Income': 'Dealer Insurance Income',
    'Total Extra Income': 'TOTAL DEALER EARNINGS',
    'Profit Status': 'Claim Status'
  };
  var headers = getHeaders_(sheet, 1);
  Object.keys(aliases).forEach(function (oldName) {
    var idx = findHeaderIndex_(headers, oldName);
    var neu = aliases[oldName];
    if (idx >= 0 && findHeaderIndex_(headers, neu) < 0) {
      sheet.getRange(1, idx + 1).setValue(neu);
    }
  });
  headers = getHeaders_(sheet, 1);

  repairOemExtraSupportDealerEarningsHeaders_(sheet);
}

/** Canonical OEM Extra Support column names on Dealer Earnings Register. */
var OEM_EXTRA_SUPPORT_DEALER_COLS_ = [
  'OEM Extra Support Received',
  'OEM Extra Support Passed To Customer',
  'OEM Extra Support Retained'
];

/** Fix duplicate / legacy OEM Extra Support headers (AV/AW/AX triple-column bug). */
function repairOemExtraSupportDealerEarningsHeaders_(sheet) {
  if (!sheet) return;
  var headerRow = dealerEarningsHeaderRow_();
  var headers = getHeaders_(sheet, headerRow);
  if (!headers.length) return;

  var legacyIdxs = [];
  var targetIdxs = {};
  OEM_EXTRA_SUPPORT_DEALER_COLS_.forEach(function (t) { targetIdxs[t] = []; });
  for (var i = 0; i < headers.length; i++) {
    var h = String(headers[i] || '').trim();
    if (h === 'OEM Extra Support') legacyIdxs.push(i);
    OEM_EXTRA_SUPPORT_DEALER_COLS_.forEach(function (t) {
      if (normalizeHeaderKey_(h) === normalizeHeaderKey_(t)) targetIdxs[t].push(i);
    });
  }

  OEM_EXTRA_SUPPORT_DEALER_COLS_.forEach(function (t) {
    if (targetIdxs[t].length === 0) {
      if (legacyIdxs.length > 0) {
        var idx = legacyIdxs.shift();
        sheet.getRange(headerRow, idx + 1).setValue(t).setFontWeight('bold');
      } else {
        headers = getHeaders_(sheet, headerRow);
        sheet.getRange(headerRow, headers.length + 1).setValue(t).setFontWeight('bold');
      }
    } else if (targetIdxs[t].length > 1) {
      for (var d = 1; d < targetIdxs[t].length; d++) {
        sheet.getRange(headerRow, targetIdxs[t][d] + 1).setValue('');
      }
    }
  });

  headers = getHeaders_(sheet, headerRow);
  for (var k = 0; k < headers.length; k++) {
    if (String(headers[k] || '').trim() === 'OEM Extra Support') {
      sheet.getRange(headerRow, k + 1).setValue('');
    }
  }
}

/** Fill missing ex-showroom on snapshot so dealer margin can compute. */
function enrichSnapshotForEarnings_(snap, lead) {
  if (!snap) return snap;
  var out = {};
  Object.keys(snap).forEach(function (k) { out[k] = snap[k]; });
  lead = lead || {};

  if (num_(out.exShowroom) <= 0) {
    out.exShowroom = num_(out.exShowroomPrice) || num_(lead.budget) || num_(lead.bookingAmount) || 0;
    if (num_(out.exShowroom) <= 0 && typeof getPriceMasterRecordForBooking_ === 'function') {
      try {
        var pm = getPriceMasterRecordForBooking_(
          out.model || out.vehicleModel || lead.interestedModel,
          out.variant || lead.variant,
          out.bookingDate || lead.bookingDate
        );
        if (pm && num_(pm.exShowroom) > 0) out.exShowroom = num_(pm.exShowroom);
      } catch (pmErr) {
        Logger.log('enrichSnapshotForEarnings_ price lookup: ' + pmErr.message);
      }
    }
  }
  return out;
}

/** Read OEM Extra Support trio from snapshot (never from scheme fields). */
function readOemExtraSupportFromSnapshot_(snap) {
  snap = snap || {};
  var received = num_(snap.oemExtraSupportReceived);
  // Legacy alias only if it does not match scheme bleed signatures.
  if (!(received > 0) && num_(snap.oemExtraSupport) > 0) {
    var legacy = num_(snap.oemExtraSupport);
    var schemeSum = round2_(
      num_(snap.consumerDiscount) + num_(snap.exchangeBonus) + num_(snap.loyaltyBonus) +
      num_(snap.referralBonus) + num_(snap.dsaDiscount) + num_(snap.additionalDiscount)
    );
    if (legacy !== schemeSum && legacy !== num_(snap.totalDiscount) && legacy !== num_(snap.exchangeBonus)) {
      received = legacy;
    }
  }
  var passed = Math.max(0, num_(snap.oemExtraSupportPassed));
  var retained = round2_(Math.max(0, received - passed));
  if (retained <= 0 && num_(snap.oemExtraSupportRetained) > 0 && received > 0) {
    retained = num_(snap.oemExtraSupportRetained);
  }
  return { received: received, passed: passed, retained: retained };
}

/** Write one earnings cell — matches canonical header or legacy triple OEM columns. */
function writeDealerEarningsField_(sheet, headers, row, canonicalName, value) {
  var col = findHeaderIndex_(headers, canonicalName) + 1;
  if (col > 0) {
    setValueSafe_(sheet.getRange(row, col), value);
    return true;
  }
  var legacyPos = {
    'OEM Extra Support Received': 0,
    'OEM Extra Support Passed To Customer': 1,
    'OEM Extra Support Retained': 2
  };
  if (legacyPos.hasOwnProperty(canonicalName)) {
    var legacyIdxs = [];
    for (var i = 0; i < headers.length; i++) {
      if (String(headers[i] || '').trim() === 'OEM Extra Support') legacyIdxs.push(i);
    }
    var pos = legacyPos[canonicalName];
    if (legacyIdxs.length > pos) {
      setValueSafe_(sheet.getRange(row, legacyIdxs[pos] + 1), value);
      return true;
    }
  }
  return false;
}

function writeDealerEarningsMap_(sheet, headers, row, map) {
  Object.keys(map || {}).forEach(function (name) {
    writeDealerEarningsField_(sheet, headers, row, name, map[name]);
  });
  ['OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained',
   'Dealer Margin Gross (Incl GST)', 'Dealer Margin GST (5%)', 'Dealer Margin Net (Ex GST)',
   'TOTAL DEALER EARNINGS'].forEach(function (name) {
    var col = findHeaderIndex_(headers, name) + 1;
    if (col > 0) {
      try { sheet.getRange(row, col).setNumberFormat('#,##0.00'); } catch (eN) {}
    }
  });
}

function ensureDealerEarningsAnalyticsSheet_() {
  migrateDealerEarningsSheetNames_();
  var name = dealerEarningsAnalyticsName_();
  if (!name) return null;
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (!sheet.isSheetHidden()) sheet.hideSheet();
  return sheet;
}

// Backward-compatible aliases
function ensureExtraIncomeRegisterSheet_() { return ensureDealerEarningsRegisterSheet_(); }
function ensureExtraIncomeAnalyticsSheet_() { return ensureDealerEarningsAnalyticsSheet_(); }

function oemExtraSupportRegisterName_() {
  return (CRM.SHEETS && CRM.SHEETS.OEM_EXTRA_SUPPORT_REGISTER) || 'OEM Extra Support Register';
}

function ensureOemExtraSupportRegisterSheet_() {
  var name = oemExtraSupportRegisterName_();
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var cfg = CRM.OEM_EXTRA_SUPPORT_REGISTER || {};
  var cols = cfg.COLS || [
    'Lead ID', 'Booking ID', 'Customer Name', 'Vehicle Model', 'Variant',
    'Booking Date', 'OEM Extra Support Received', 'OEM Extra Support Passed To Customer',
    'OEM Extra Support Retained', 'Status', 'Last Updated', 'Remarks'
  ];
  var hdrRow = cfg.HEADER_ROW || 1;
  var headers = getHeaders_(sheet, hdrRow);
  if (sheet.getLastRow() < 1 || !headers.length) {
    sheet.getRange(hdrRow, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    sheet.setFrozenRows(hdrRow);
    return sheet;
  }
  // Legacy single column rename
  var oldIdx = findHeaderIndex_(headers, 'OEM Extra Support');
  var recvIdx = findHeaderIndex_(headers, 'OEM Extra Support Received');
  if (oldIdx >= 0 && recvIdx < 0) {
    sheet.getRange(hdrRow, oldIdx + 1).setValue('OEM Extra Support Received');
    headers = getHeaders_(sheet, hdrRow);
  }
  cols.forEach(function (c) {
    headers = getHeaders_(sheet, hdrRow);
    if (findHeaderIndex_(headers, c) < 0) {
      sheet.getRange(hdrRow, headers.length + 1).setValue(c).setFontWeight('bold');
    }
  });
  sheet.setFrozenRows(hdrRow);
  return sheet;
}

/**
 * Portal / WebApi path — persist OEM Extra Support even when the scheme amend
 * branch was skipped (common when only Extra Support changed or Web App deployment
 * lagged behind the bound spreadsheet script).
 */
function forcePersistOemExtraSupportForLead_(leadId, data) {
  leadId = String(leadId || '').trim();
  if (!leadId) return { persisted: false, reason: 'no_lead' };
  if (typeof normalizeOemExtraSupportPayload_ === 'function') {
    data = normalizeOemExtraSupportPayload_(data || {});
  } else {
    data = data || {};
  }
  var recv = Math.max(0, num_(data.oemExtraSupportReceived));
  var pass = Math.max(0, Math.min(num_(data.oemExtraSupportPassed), recv));
  var ret = round2_(Math.max(0, recv - pass));
  if (!(recv > 0 || pass > 0 || ret > 0)) {
    return { persisted: false, reason: 'zero_oem', oemExtraSupportReceived: recv };
  }

  var lead = typeof getLeadFromRegisterLight_ === 'function' ? getLeadFromRegisterLight_(leadId) : null;
  var snap = null;
  var sheetRow = 0;
  try {
    if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
      snap = getLatestCommercialSnapshotForLead_(leadId);
    }
  } catch (eSnap) {}
  try {
    var store = loadCrmStore_(true);
    var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
    if (entry) {
      if (!snap) snap = entry.full || entry;
      sheetRow = Number(entry.sheetRow || 0);
    }
  } catch (eStore) {}
  if (snap && Number(snap.sheetRow) > 0) sheetRow = Number(snap.sheetRow);

  try {
    if (sheetRow > 0 && typeof patchOemExtraSupportOnSnapshotRow_ === 'function') {
      var csSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
      if (csSheet) {
        if (typeof ensureOemExtraSupportCommercialColumns_ === 'function') {
          ensureOemExtraSupportCommercialColumns_();
        }
        var hdrs = getHeaders_(csSheet, (CRM.COMMERCIAL && CRM.COMMERCIAL.HEADER_ROW) || 1);
        patchOemExtraSupportOnSnapshotRow_(csSheet, sheetRow, hdrs, {
          oemExtraSupportReceived: recv,
          oemExtraSupportPassed: pass,
          oemExtraSupportRetained: ret
        });
      }
    }
  } catch (ePatch) {
    Logger.log('forcePersistOemExtraSupport snapshot: ' + ePatch.message);
  }

  var schemeModel = (snap && (snap.model || snap.vehicleModel)) || (lead && lead.interestedModel) || '';
  var schemeVariant = (snap && snap.variant) || (lead && lead.variant) || '';
  var bookingDate = (snap && snap.bookingDate) || (lead && lead.bookingDate) || '';

  try {
    if (typeof upsertOemExtraSupportCase_ === 'function') {
      upsertOemExtraSupportCase_({
        'Lead ID': leadId,
        'Booking ID': (snap && snap.bookingId) || '',
        'Customer Name': (lead && lead.customerName) || '',
        'Vehicle Model': schemeModel,
        'Variant': schemeVariant,
        'Booking Date': formatDate_(bookingDate) || '',
        'OEM Extra Support Received': recv,
        'OEM Extra Support Passed To Customer': pass,
        'OEM Extra Support Retained': ret
      }, { remarks: 'Scheme Update (portal)' });
    }
  } catch (eReg) {
    Logger.log('forcePersistOemExtraSupport register: ' + eReg.message);
  }
  try {
    if (typeof upsertDealerEarningsForLead_ === 'function') {
      upsertDealerEarningsForLead_(leadId, {
        reason: 'portal_oem_extra',
        oemExtraSupportReceived: recv,
        oemExtraSupportPassed: pass,
        oemExtraSupportRetained: ret,
        rebuildAnalytics: false
      });
    }
  } catch (eEarn) {
    Logger.log('forcePersistOemExtraSupport earnings: ' + eEarn.message);
  }
  try {
    invalidateCrmStore_();
    SpreadsheetApp.flush();
  } catch (eFlush) {}

  return {
    persisted: true,
    oemExtraSupportReceived: recv,
    oemExtraSupportPassed: pass,
    oemExtraSupportRetained: ret
  };
}

function upsertOemExtraSupportCase_(earningsMap, opts) {
  var m = earningsMap || {};
  var received = num_(m['OEM Extra Support Received']);
  var passed = num_(m['OEM Extra Support Passed To Customer']);
  var retained = num_(m['OEM Extra Support Retained']);
  var leadId = String(m['Lead ID'] || '').trim();
  if (!leadId) return null;
  var sheet = ensureOemExtraSupportRegisterSheet_();
  if (!sheet) return null;
  var cfg = CRM.OEM_EXTRA_SUPPORT_REGISTER || {};
  var dataStart = cfg.DATA_START || 2;
  var headers = getHeaders_(sheet, cfg.HEADER_ROW || 1);
  var leadCol = findHeaderIndex_(headers, 'Lead ID') + 1;
  var row = -1;
  if (leadCol > 0 && sheet.getLastRow() >= dataStart) {
    var vals = sheet.getRange(dataStart, leadCol, sheet.getLastRow() - dataStart + 1, 1).getValues();
    for (var i = 0; i < vals.length; i++) {
      var plain = String(vals[i][0] || '');
      if (plain.indexOf('HYPERLINK') >= 0) {
        var mm = plain.match(/"([A-Z0-9\-]+)"\s*\)\s*$/i);
        if (mm) plain = mm[1];
      }
      if (plain.trim() === leadId) { row = dataStart + i; break; }
    }
  }
  var hasMoney = received > 0 || passed > 0 || retained > 0;
  // No Extra Support and no existing row → skip (scheme-only booking).
  if (!hasMoney && row < 0) return null;
  if (row < 0) row = Math.max(sheet.getLastRow() + 1, dataStart);
  var map = {
    'Lead ID': leadId,
    'Booking ID': m['Booking ID'] || '',
    'Customer Name': m['Customer Name'] || '',
    'Vehicle Model': m['Vehicle Model'] || '',
    'Variant': m['Variant'] || '',
    'Booking Date': m['Booking Date'] || '',
    'OEM Extra Support Received': received,
    'OEM Extra Support Passed To Customer': passed,
    'OEM Extra Support Retained': retained,
    'Status': received > 0 ? 'Open' : (hasMoney ? 'Passed Only' : 'Cleared / Not Applicable'),
    'Last Updated': nowDateTime_(),
    'Remarks': (opts && opts.remarks != null) ? String(opts.remarks) : (hasMoney ? '' : 'Cleared — was not OEM Extra Support (scheme-independent)')
  };
  writeDealerEarningsMap_(sheet, headers, row, map);
  // Force money columns to NUMBER format (fixes Retained showing as date 1941-01-24).
  ['OEM Extra Support Received', 'OEM Extra Support Passed To Customer', 'OEM Extra Support Retained'].forEach(function (name) {
    var col = findHeaderIndex_(headers, name) + 1;
    if (col > 0) {
      try {
        sheet.getRange(row, col).setNumberFormat('#,##0.00');
        setValueSafe_(sheet.getRange(row, col), map[name]);
      } catch (eFmt) {}
    }
  });
  try {
    if (leadCol > 0 && typeof navEntityLink_ === 'function') {
      setValueSafe_(sheet.getRange(row, leadCol), navEntityLink_('Lead', leadId, leadId));
    }
  } catch (e) {}
  return map;
}

function findDealerEarningsRowByLead_(sheet, headers, leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return -1;
  var col = findHeaderIndex_(headers, 'Lead ID') + 1;
  if (col < 1) return -1;
  var last = sheet.getLastRow();
  var start = dealerEarningsDataStart_();
  if (last < start) return -1;
  var vals = sheet.getRange(start, col, last - start + 1, 1).getValues();
  for (var i = 0; i < vals.length; i++) {
    var cell = String(vals[i][0] || '');
    var plain = cell;
    if (cell.indexOf('HYPERLINK') >= 0) {
      var m = cell.match(/"([A-Z0-9\-]+)"\s*\)\s*$/i);
      if (m) plain = m[1];
    }
    if (plain.trim() === leadId) return start + i;
  }
  return -1;
}

function findExtraIncomeRowByLead_(sheet, headers, leadId) {
  return findDealerEarningsRowByLead_(sheet, headers, leadId);
}

function readInsurancePayoutForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId || typeof readAllInsuranceEntries_ !== 'function') {
    return { payout: 0, status: '' };
  }
  try {
    var entries = readAllInsuranceEntries_().filter(function (e) { return e.leadId === leadId; });
    if (!entries.length) return { payout: 0, status: '' };
    var e = entries[0];
    return {
      payout: num_(e.expectedPayout),
      status: String(e.status || '').trim()
    };
  } catch (err) {
    return { payout: 0, status: '' };
  }
}

function resolveDealerClaimStatus_(leadId, oemEligible) {
  if (num_(oemEligible) <= 0.01) return 'Not Applicable';
  try {
    if (typeof isSchemeClaimReceivedForLead_ === 'function' && isSchemeClaimReceivedForLead_(leadId)) {
      return 'Received';
    }
  } catch (e) {}
  return 'Pending';
}

function resolveDealerInsuranceStatus_(leadId, insurancePayout, fallbackStatus) {
  if (num_(insurancePayout) <= 0.01) return fallbackStatus || 'Not Applicable';
  try {
    var pending = typeof listPendingInsurancePayouts_ === 'function'
      ? listPendingInsurancePayouts_().some(function (x) { return x.leadId === leadId; })
      : false;
    if (pending) return 'Pending';
  } catch (e) {}
  return fallbackStatus || 'Received';
}

/** @deprecated use resolveDealerClaimStatus_ / resolveDealerInsuranceStatus_ */
function resolveExtraIncomeProfitStatus_(row) {
  var claim = resolveDealerClaimStatus_(row.leadId, row.oemEligible);
  var ins = resolveDealerInsuranceStatus_(row.leadId, row.insurancePayout, '');
  if (claim === 'Pending' && ins === 'Pending') return 'Pending OEM + Insurance';
  if (claim === 'Pending') return 'Pending OEM';
  if (ins === 'Pending') return 'Pending Insurance';
  if (num_(row.dealerBenefitRetained) > 0.01 || num_(row.insuranceIncome) > 0.01 || num_(row.otherIncome) > 0.01) {
    return 'Realized';
  }
  return 'Tracked';
}

function upsertDealerEarningsForLead_(leadId, opts) {
  opts = opts || {};
  leadId = String(leadId || '').trim();
  if (!leadId) return null;

  var sheet = ensureDealerEarningsRegisterSheet_();
  if (!sheet) return null;
  var headers = getHeaders_(sheet, dealerEarningsHeaderRow_());
  var existingRow = findDealerEarningsRowByLead_(sheet, headers, leadId);

  // LIGHT PATH — never force a full workbook rebuild here. Scheme Update / booking
  // saves were timing out because loadCrmStore_(true) re-read every sheet.
  // Snapshot comes from a direct Commercial Snapshot read; lead from light lookup.
  var snap = null;
  if (typeof readCommercialSnapshotForLead_ === 'function') {
    try { snap = readCommercialSnapshotForLead_(leadId); } catch (rcErr) {
      Logger.log('earnings snapshot re-read [' + leadId + ']: ' + rcErr.message);
    }
  }
  var lead = {};
  try {
    lead = (typeof getLeadFromRegisterLight_ === 'function' ? getLeadFromRegisterLight_(leadId) : null) || {};
  } catch (leadErr) { lead = {}; }
  if (!snap || !lead.leadId) {
    try {
      var storeFallback = loadCrmStore_(); // cached OK — do not force
      if (!lead.leadId) lead = (storeFallback.leads && storeFallback.leads.byId && storeFallback.leads.byId[leadId]) || lead;
      if (!snap) {
        var entry = storeFallback.commercial && storeFallback.commercial.byLeadId
          ? storeFallback.commercial.byLeadId[leadId] : null;
        snap = entry ? (entry.full || entry) : null;
      }
    } catch (sfErr) {}
  }
  if (typeof enrichSnapshotForEarnings_ === 'function') {
    snap = enrichSnapshotForEarnings_(snap, lead);
  }
  // Re-read headers after ensure/migration (fixes AV/AW/AX triple OEM column bug).
  headers = getHeaders_(sheet, dealerEarningsHeaderRow_());
  var entry = snap ? { bookingId: snap.bookingId, full: snap } : null;

  var oemEligible = 0;
  var benefitPassed = 0;
  var retained = 0;
  var oemExtraSupportReceived = 0;
  var oemExtraSupportPassed = 0;
  var oemExtraSupportRetained = 0;
  var dealerMarginGross = 0;
  var dealerMarginGst = 0;
  var dealerMarginNet = 0;
  var customerPayable = 0;
  var incomeBk = null;
  if (snap) {
    oemEligible = typeof getOemEligibleAmount_ === 'function' ? getOemEligibleAmount_(snap) : 0;
    benefitPassed = typeof resolveCustomerBenefitPassed_ === 'function'
      ? resolveCustomerBenefitPassed_(snap) : num_(snap.customerBenefitPassed);
    // BUSINESS RULE: scheme earnings = companyUnpassed − dealerPassed.
    // Dealer unpassed is not income. Can be negative on Full Benefit.
    incomeBk = typeof computeSchemeIncomeBreakdown_ === 'function'
      ? computeSchemeIncomeBreakdown_(snap) : null;
    var oemExtra = typeof readOemExtraSupportFromSnapshot_ === 'function'
      ? readOemExtraSupportFromSnapshot_(snap)
      : {
        received: num_(snap.oemExtraSupportReceived || snap.oemExtraSupport),
        passed: Math.max(0, num_(snap.oemExtraSupportPassed)),
        retained: round2_(Math.max(0, num_(snap.oemExtraSupportReceived || snap.oemExtraSupport) - num_(snap.oemExtraSupportPassed)))
      };
    oemExtraSupportReceived = oemExtra.received;
    oemExtraSupportPassed = oemExtra.passed;
    oemExtraSupportRetained = oemExtra.retained;
    // Explicit overrides from Scheme Update / portal save (authoritative).
    if (opts.oemExtraSupportReceived != null && opts.oemExtraSupportReceived !== '') {
      oemExtraSupportReceived = Math.max(0, num_(opts.oemExtraSupportReceived));
      oemExtraSupportPassed = Math.max(0, Math.min(
        num_(opts.oemExtraSupportPassed != null ? opts.oemExtraSupportPassed : oemExtraSupportPassed),
        oemExtraSupportReceived
      ));
      oemExtraSupportRetained = round2_(Math.max(0, oemExtraSupportReceived - oemExtraSupportPassed));
    } else if (opts['OEM Extra Support Received'] != null && opts['OEM Extra Support Received'] !== '') {
      oemExtraSupportReceived = Math.max(0, num_(opts['OEM Extra Support Received']));
      oemExtraSupportPassed = Math.max(0, Math.min(
        num_(opts['OEM Extra Support Passed To Customer'] != null ? opts['OEM Extra Support Passed To Customer'] : oemExtraSupportPassed),
        oemExtraSupportReceived
      ));
      oemExtraSupportRetained = round2_(Math.max(0, oemExtraSupportReceived - oemExtraSupportPassed));
    }
    if (typeof computeDealerMarginBreakdown_ === 'function') {
      var marginBk = computeDealerMarginBreakdown_(snap);
      dealerMarginGross = num_(marginBk.marginGrossInclGst);
      dealerMarginGst = num_(marginBk.marginGst);
      dealerMarginNet = num_(marginBk.marginNetExGst);
    }
    // Use stored snapshot margin when live compute is zero but snapshot has values.
    if (dealerMarginNet <= 0 && num_(snap.dealerMarginNetExGst) > 0) {
      dealerMarginGross = num_(snap.dealerMarginGrossInclGst);
      dealerMarginGst = num_(snap.dealerMarginGst);
      dealerMarginNet = num_(snap.dealerMarginNetExGst);
    }
    retained = incomeBk ? incomeBk.retainedIncomeTotal
      : (typeof getDealerBenefitRetained_ === 'function'
        ? getDealerBenefitRetained_(snap) : round2_(oemEligible - benefitPassed));
    customerPayable = num_(snap.customerPayable);
  }
  if (!customerPayable) customerPayable = num_(lead.customerPayable || lead['Customer Payable']);

  var ins = readInsurancePayoutForLead_(leadId);
  var manual = {
    'Other Income': 0,
    'Customer Insurance Benefit Passed': 0,
    'Finance Incentive': 0,
    'Accessories Margin': 0,
    'Exchange Margin': 0,
    'Documentation Income': 0,
    'Warranty Income': 0,
    'RSA Income': 0,
    'Referral Income': 0,
    'Campaign Incentive': 0,
    _remarks: '',
    _createdBy: ''
  };
  if (existingRow > 0) {
    DEALER_EARNINGS_MANUAL_COLS_.forEach(function (name) {
      var col = findHeaderIndex_(headers, name) + 1;
      if (col > 0) manual[name] = parseNumber_(sheet.getRange(existingRow, col).getValue());
    });
    var remCol = findHeaderIndex_(headers, 'Remarks') + 1;
    if (remCol > 0) manual._remarks = String(sheet.getRange(existingRow, remCol).getValue() || '');
    var createdCol = findHeaderIndex_(headers, 'Created By') + 1;
    if (createdCol > 0) manual._createdBy = String(sheet.getRange(existingRow, createdCol).getValue() || '');
  }

  // Optional overrides from opts (never overwrite manual blanks unless explicitly passed)
  DEALER_EARNINGS_MANUAL_COLS_.forEach(function (name) {
    var key = name.replace(/\s+/g, '');
    var camel = name.charAt(0).toLowerCase() + name.slice(1).replace(/\s+/g, '');
    if (opts[camel] != null && opts[camel] !== '') manual[name] = num_(opts[camel]);
    if (opts[name] != null && opts[name] !== '') manual[name] = num_(opts[name]);
  });
  if (opts.otherIncome != null && opts.otherIncome !== '') manual['Other Income'] = num_(opts.otherIncome);
  if (opts.customerInsuranceBenefitPassed != null && opts.customerInsuranceBenefitPassed !== '') {
    manual['Customer Insurance Benefit Passed'] = num_(opts.customerInsuranceBenefitPassed);
  }

  var custInsBenefit = num_(manual['Customer Insurance Benefit Passed']);
  var dealerInsIncome = round2_(num_(ins.payout) - custInsBenefit);

  var total = round2_(
    num_(retained) +
    dealerMarginNet +
    oemExtraSupportRetained +
    dealerInsIncome +
    num_(manual['Finance Incentive']) +
    num_(manual['Accessories Margin']) +
    num_(manual['Exchange Margin']) +
    num_(manual['Documentation Income']) +
    num_(manual['Warranty Income']) +
    num_(manual['RSA Income']) +
    num_(manual['Referral Income']) +
    num_(manual['Campaign Incentive']) +
    num_(manual['Other Income'])
  );

  var del = {};
  var invoice = '';
  var colour = '';
  var teamLeader = '';
  try {
    var storeLazy = loadCrmStore_(); // cached; never force-rebuild on this path
    del = (storeLazy.deliveryByLead && storeLazy.deliveryByLead[leadId]) || {};
    var h = (storeLazy.leads && storeLazy.leads.headers) || [];
    var sheetRow = storeLazy.leads && storeLazy.leads.sheetRow && storeLazy.leads.sheetRow[leadId]
      ? storeLazy.leads.sheetRow[leadId] : 0;
    var rowIdx = sheetRow ? sheetRow - CRM.LEAD.DATA_START : -1;
    if (rowIdx >= 0 && storeLazy.leads.rows && storeLazy.leads.rows[rowIdx]) {
      invoice = String(rowVal_(storeLazy.leads.rows[rowIdx], h, 'Invoice Number') || '').trim();
      colour = String(rowVal_(storeLazy.leads.rows[rowIdx], h, 'Colour') || rowVal_(storeLazy.leads.rows[rowIdx], h, 'Color') || '').trim();
      teamLeader = String(rowVal_(storeLazy.leads.rows[rowIdx], h, 'Team Leader') || '').trim();
    }
  } catch (eInv) {}
  var model = String(lead.interestedModel || (snap && snap.model) || '').trim();
  var variant = String(lead.variant || (snap && snap.variant) || '').trim();

  var claimStatus = resolveDealerClaimStatus_(leadId, oemEligible);
  var insuranceStatus = resolveDealerInsuranceStatus_(leadId, ins.payout, ins.status);

  var map = {
    'Lead ID': leadId,
    'Booking ID': (snap && snap.bookingId) || (entry && entry.bookingId) || '',
    'Customer Name': lead.customerName || lead['Customer Name'] || '',
    'Executive': lead.executive || (snap && snap.bookingExecutive) || '',
    'Team Leader': teamLeader,
    'Lead Source': lead.leadSource || lead['Lead Source'] || '',
    'Vehicle Model': model,
    'Variant': variant,
    'Colour': colour,
    'Current Stage': lead.currentStatus || lead['Current Status'] || '',
    'Booking Date': formatDate_(lead.bookingDate || lead['Booking Date'] || (snap && snap.bookingDate)) || '',
    'Delivery Date': formatDate_(del.deliveryDate) || '',
    'Invoice Number': invoice,
    'Customer Payable': customerPayable,
    'OEM Eligible Scheme': oemEligible,
    'Customer Scheme Benefit Passed': benefitPassed,
    'Dealer Scheme Retained': retained,
    'Dealer Margin Gross (Incl GST)': dealerMarginGross,
    'Dealer Margin GST (5%)': dealerMarginGst,
    'Dealer Margin Net (Ex GST)': dealerMarginNet,
    'OEM Extra Support Received': oemExtraSupportReceived,
    'OEM Extra Support Passed To Customer': oemExtraSupportPassed,
    'OEM Extra Support Retained': oemExtraSupportRetained,
    'Consumer Retained': num_(incomeBk && incomeBk.retainedByComponent && incomeBk.retainedByComponent.consumerDiscount),
    'Exchange Retained': num_(incomeBk && incomeBk.retainedByComponent && incomeBk.retainedByComponent.exchangeBonus),
    'Loyalty Retained': num_(incomeBk && incomeBk.retainedByComponent && incomeBk.retainedByComponent.loyaltyBonus),
    'Referral Retained': num_(incomeBk && incomeBk.retainedByComponent && incomeBk.retainedByComponent.referralBonus),
    'DSA Retained': num_(incomeBk && incomeBk.retainedByComponent && incomeBk.retainedByComponent.dsaDiscount),
    'Scheme Retained Breakup': incomeBk ? schemeBreakupText_(incomeBk.retainedByComponent) : '',
    'Insurance Payout': num_(ins.payout),
    'Customer Insurance Benefit Passed': custInsBenefit,
    'Dealer Insurance Income': dealerInsIncome,
    'Finance Incentive': num_(manual['Finance Incentive']),
    'Accessories Margin': num_(manual['Accessories Margin']),
    'Exchange Margin': num_(manual['Exchange Margin']),
    'Documentation Income': num_(manual['Documentation Income']),
    'Warranty Income': num_(manual['Warranty Income']),
    'RSA Income': num_(manual['RSA Income']),
    'Referral Income': num_(manual['Referral Income']),
    'Campaign Incentive': num_(manual['Campaign Incentive']),
    'Other Income': num_(manual['Other Income']),
    'TOTAL DEALER EARNINGS': total,
    'Claim Status': claimStatus,
    'Insurance Status': insuranceStatus,
    'Last Updated': nowDateTime_(),
    'Created By': manual._createdBy || getUserEmail_(),
    'Modified By': getUserEmail_(),
    'Timestamp': nowDateTime_(),
    'Remarks': opts.remarks != null ? String(opts.remarks) : manual._remarks
  };

  // Also write legacy column names if still present (pre-migration sheets)
  var legacyMirror = {
    'Customer': map['Customer Name'],
    'Salesperson': map['Executive'],
    'Vehicle': [model, variant].join(' ').trim(),
    'OEM Eligible': map['OEM Eligible Scheme'],
    'Dealer Benefit Retained': map['Dealer Scheme Retained'],
    'Insurance Income': map['Dealer Insurance Income'],
    'Total Extra Income': map['TOTAL DEALER EARNINGS'],
    'Profit Status': claimStatus === 'Pending'
      ? (insuranceStatus === 'Pending' ? 'Pending OEM + Insurance' : 'Pending OEM')
      : (insuranceStatus === 'Pending' ? 'Pending Insurance' : 'Realized')
  };

  var row = existingRow > 0 ? existingRow : Math.max(sheet.getLastRow() + 1, dealerEarningsDataStart_());
  writeDealerEarningsMap_(sheet, headers, row, map);
  Object.keys(legacyMirror).forEach(function (name) {
    writeDealerEarningsField_(sheet, headers, row, name, legacyMirror[name]);
  });

  try {
    var leadCol = findHeaderIndex_(headers, 'Lead ID') + 1;
    if (leadCol > 0 && typeof navEntityLink_ === 'function') {
      setValueSafe_(sheet.getRange(row, leadCol), navEntityLink_('Lead', leadId, leadId));
    }
    var bookCol = findHeaderIndex_(headers, 'Booking ID') + 1;
    var bookingId = map['Booking ID'];
    if (bookCol > 0 && bookingId && typeof navEntityLink_ === 'function') {
      setValueSafe_(sheet.getRange(row, bookCol), navEntityLink_('Booking', bookingId, bookingId));
    }
    var totalCol = findHeaderIndex_(headers, 'TOTAL DEALER EARNINGS') + 1;
    if (totalCol < 1) totalCol = findHeaderIndex_(headers, 'Total Extra Income') + 1;
    if (totalCol > 0 && typeof navEntityLink_ === 'function') {
      var label = '₹' + Math.round(total).toLocaleString('en-IN');
      setValueSafe_(sheet.getRange(row, totalCol),
        navEntityLink_('DealerEarnings', leadId, label));
    }
  } catch (eNav) {}

  if (sheet.isSheetHidden()) sheet.showSheet();

  try {
    syncDealerEarningsDisplayColumns_(leadId, total, row);
  } catch (eDisp) {
    Logger.log('syncDealerEarningsDisplayColumns_: ' + eDisp.message);
  }

  if (opts.rebuildAnalytics) {
    try { rebuildDealerEarningsAnalytics_(); } catch (eA) {
      Logger.log('rebuildDealerEarningsAnalytics_: ' + eA.message);
    }
  }

  try { upsertOemExtraSupportCase_(map, opts); } catch (eOes) {
    Logger.log('upsertOemExtraSupportCase_: ' + eOes.message);
  }

  map._sheetRow = row;
  return map;
}

function upsertExtraIncomeForLead_(leadId, opts) {
  return upsertDealerEarningsForLead_(leadId, opts);
}

/**
 * Owner-only display columns on Lead / Booking / Delivery.
 * Soft gating: only write when spreadsheet owner is the active user.
 */
function syncDealerEarningsDisplayColumns_(leadId, total, earningsRow) {
  if (typeof isSpreadsheetOwner_ !== 'function' || !isSpreadsheetOwner_()) return;
  leadId = String(leadId || '').trim();
  if (!leadId) return;
  total = num_(total);
  var label = '₹' + Math.round(total).toLocaleString('en-IN');
  var link = typeof navEntityLink_ === 'function'
    ? navEntityLink_('DealerEarnings', leadId, label)
    : label;

  // Lead Register
  try {
    ensureLeadDealerEarningsColumn_();
    var found = findLeadById_(leadId);
    if (found && found.row) {
      var lr = getSheet_(CRM.SHEETS.LEAD_REGISTER);
      var lh = getHeaders_(lr, CRM.LEAD.HEADER_ROW);
      var col = findHeaderIndex_(lh, 'Dealer Earnings') + 1;
      if (col > 0) setValueSafe_(lr.getRange(found.row, col), link);
    }
  } catch (eL) {}

  // Booking Register
  try {
    ensureBookingDealerEarningsColumn_();
    var br = getSpreadsheet_().getSheetByName(CRM.SHEETS.BOOKING_REGISTER);
    if (br) {
      var bh = getHeaders_(br, 1);
      var leadCol = findHeaderIndex_(bh, 'LeadID') + 1;
      if (leadCol < 1) leadCol = findHeaderIndex_(bh, 'Lead ID') + 1;
      var earnCol = findHeaderIndex_(bh, 'Dealer Earnings') + 1;
      if (leadCol > 0 && earnCol > 0) {
        var last = br.getLastRow();
        if (last >= 2) {
          var vals = br.getRange(2, leadCol, Math.max(0, last - 1), 1).getValues();
          for (var i = 0; i < vals.length; i++) {
            if (String(vals[i][0] || '').trim() === leadId) {
              setValueSafe_(br.getRange(2 + i, earnCol), link);
              break;
            }
          }
        }
      }
    }
  } catch (eB) {}

  // Delivery Tracker
  try {
    ensureDeliveryDealerEarningsColumn_();
    var dr = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
    if (dr) {
      var dh = getHeaders_(dr, CRM.DELIVERY.HEADER_ROW);
      var dLeadCol = findHeaderIndex_(dh, 'Lead ID') + 1;
      var dEarnCol = findHeaderIndex_(dh, 'Dealer Earnings') + 1;
      if (dLeadCol > 0 && dEarnCol > 0) {
        var dLast = dr.getLastRow();
        if (dLast >= CRM.DELIVERY.DATA_START) {
          var dVals = dr.getRange(CRM.DELIVERY.DATA_START, dLeadCol, dLast, dLeadCol).getValues();
          for (var j = 0; j < dVals.length; j++) {
            if (String(dVals[j][0] || '').trim() === leadId) {
              setValueSafe_(dr.getRange(CRM.DELIVERY.DATA_START + j, dEarnCol), link);
              break;
            }
          }
        }
      }
    }
  } catch (eD) {}
}

function ensureLeadDealerEarningsColumn_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  if (findHeaderIndex_(headers, 'Dealer Earnings') >= 0) return;
  sheet.getRange(CRM.LEAD.HEADER_ROW, headers.length + 1)
    .setValue('Dealer Earnings').setFontWeight('bold')
    .setNote('OWNER ONLY · System Calculated · Click to open Dealer Earnings Register');
}

function ensureBookingDealerEarningsColumn_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.BOOKING_REGISTER);
  if (!sheet) return;
  var headers = getHeaders_(sheet, 1);
  if (findHeaderIndex_(headers, 'Dealer Earnings') >= 0) return;
  sheet.getRange(1, headers.length + 1)
    .setValue('Dealer Earnings').setFontWeight('bold')
    .setNote('OWNER ONLY · System Calculated');
}

function ensureDeliveryDealerEarningsColumn_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!sheet) return;
  var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  if (findHeaderIndex_(headers, 'Dealer Earnings') >= 0) return;
  sheet.getRange(CRM.DELIVERY.HEADER_ROW, headers.length + 1)
    .setValue('Dealer Earnings').setFontWeight('bold')
    .setNote('OWNER ONLY · System Calculated');
}

function readAllDealerEarningsRows_() {
  var sheet = ensureDealerEarningsRegisterSheet_();
  if (!sheet) return [];
  var headers = getHeaders_(sheet, dealerEarningsHeaderRow_());
  var last = sheet.getLastRow();
  var start = dealerEarningsDataStart_();
  if (last < start) return [];
  var data = sheet.getRange(start, 1, Math.max(0, last - start + 1), headers.length).getValues();

  function cell(map, primary, fallback) {
    if (map[primary] != null && map[primary] !== '') return map[primary];
    if (fallback && map[fallback] != null) return map[fallback];
    return '';
  }
  function money(map, primary, fallback) {
    return parseNumber_(cell(map, primary, fallback));
  }

  return data.map(function (row, i) {
    var map = {};
    headers.forEach(function (h, c) { map[h] = row[c]; });
    var leadRaw = String(cell(map, 'Lead ID') || '');
    var leadId = leadRaw;
    if (leadRaw.indexOf('HYPERLINK') >= 0) {
      var m = leadRaw.match(/"([A-Z0-9\-]+)"\s*\)\s*$/i);
      if (m) leadId = m[1];
    }
    leadId = String(leadId || '').trim();
    var total = money(map, 'TOTAL DEALER EARNINGS', 'Total Extra Income');
    return {
      sheetRow: start + i,
      leadId: leadId,
      bookingId: String(cell(map, 'Booking ID') || '').trim(),
      customer: String(cell(map, 'Customer Name', 'Customer') || '').trim(),
      salesperson: String(cell(map, 'Executive', 'Salesperson') || '').trim(),
      executive: String(cell(map, 'Executive', 'Salesperson') || '').trim(),
      teamLeader: String(cell(map, 'Team Leader') || '').trim(),
      leadSource: String(cell(map, 'Lead Source') || '').trim(),
      model: String(cell(map, 'Vehicle Model') || '').trim(),
      variant: String(cell(map, 'Variant') || '').trim(),
      vehicle: String(cell(map, 'Vehicle') || [cell(map, 'Vehicle Model'), cell(map, 'Variant')].join(' ').trim()),
      colour: String(cell(map, 'Colour') || '').trim(),
      currentStage: String(cell(map, 'Current Stage') || '').trim(),
      bookingDate: formatDate_(cell(map, 'Booking Date')),
      invoiceNumber: String(cell(map, 'Invoice Number') || '').trim(),
      deliveryDate: formatDate_(cell(map, 'Delivery Date')),
      customerPayable: money(map, 'Customer Payable'),
      oemEligible: money(map, 'OEM Eligible Scheme', 'OEM Eligible'),
      customerSchemeBenefitPassed: money(map, 'Customer Scheme Benefit Passed'),
      dealerBenefitRetained: money(map, 'Dealer Scheme Retained', 'Dealer Benefit Retained'),
      dealerSchemeRetained: money(map, 'Dealer Scheme Retained', 'Dealer Benefit Retained'),
      insurancePayout: money(map, 'Insurance Payout'),
      customerInsuranceBenefitPassed: money(map, 'Customer Insurance Benefit Passed'),
      insuranceIncome: money(map, 'Dealer Insurance Income', 'Insurance Income'),
      dealerInsuranceIncome: money(map, 'Dealer Insurance Income', 'Insurance Income'),
      financeIncentive: money(map, 'Finance Incentive'),
      accessoriesMargin: money(map, 'Accessories Margin'),
      exchangeMargin: money(map, 'Exchange Margin'),
      documentationIncome: money(map, 'Documentation Income'),
      warrantyIncome: money(map, 'Warranty Income'),
      rsaIncome: money(map, 'RSA Income'),
      referralIncome: money(map, 'Referral Income'),
      campaignIncentive: money(map, 'Campaign Incentive'),
      otherIncome: money(map, 'Other Income'),
      totalExtraIncome: total,
      totalDealerEarnings: total,
      claimStatus: String(cell(map, 'Claim Status', 'Profit Status') || '').trim(),
      insuranceStatus: String(cell(map, 'Insurance Status') || '').trim(),
      profitStatus: String(cell(map, 'Claim Status', 'Profit Status') || '').trim()
    };
  }).filter(function (r) { return !!r.leadId; });
}

function readAllExtraIncomeRows_() {
  return readAllDealerEarningsRows_();
}

function getDealerEarningsForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return null;
  var rows = readAllDealerEarningsRows_();
  for (var i = 0; i < rows.length; i++) {
    if (rows[i].leadId === leadId) return rows[i];
  }
  return null;
}

function rebuildDealerEarningsAnalytics_() {
  var sheet = ensureDealerEarningsAnalyticsSheet_();
  if (!sheet) return;
  var rows = readAllDealerEarningsRows_();
  sheet.clear();

  var totalExtra = 0, oemIncome = 0, insIncome = 0, otherIncome = 0;
  var financeInc = 0, accessories = 0, exchange = 0;
  var pendingOem = 0, pendingIns = 0;
  var byMonth = {}, byYear = {}, byModel = {}, byVariant = {}, bySales = {};
  var bySource = {}, byLead = {}, byInvoice = {};

  rows.forEach(function (r) {
    var tot = num_(r.totalDealerEarnings);
    totalExtra += tot;
    oemIncome += num_(r.dealerSchemeRetained);
    insIncome += num_(r.dealerInsuranceIncome);
    otherIncome += num_(r.otherIncome);
    financeInc += num_(r.financeIncentive);
    accessories += num_(r.accessoriesMargin);
    exchange += num_(r.exchangeMargin);

    if (String(r.claimStatus || r.profitStatus || '').indexOf('Pending') >= 0 &&
        String(r.claimStatus || '').indexOf('Insurance') < 0) {
      pendingOem += num_(r.oemEligible);
    } else if (String(r.claimStatus || '') === 'Pending') {
      pendingOem += num_(r.oemEligible);
    }
    if (String(r.insuranceStatus || r.profitStatus || '').indexOf('Pending') >= 0) {
      pendingIns += Math.max(0, num_(r.insurancePayout) - num_(r.customerInsuranceBenefitPassed));
    }

    var month = (r.deliveryDate || r.bookingDate || '').substring(0, 7) || 'Unknown';
    var year = (r.deliveryDate || r.bookingDate || '').substring(0, 4) || 'Unknown';
    byMonth[month] = (byMonth[month] || 0) + tot;
    byYear[year] = (byYear[year] || 0) + tot;
    var model = r.model || (String(r.vehicle || '').split(/\s+/)[0]) || 'Unknown';
    var variant = r.variant || 'Unknown';
    byModel[model] = (byModel[model] || 0) + tot;
    byVariant[variant] = (byVariant[variant] || 0) + tot;
    bySales[r.executive || 'Unknown'] = (bySales[r.executive || 'Unknown'] || 0) + tot;
    bySource[r.leadSource || 'Unknown'] = (bySource[r.leadSource || 'Unknown'] || 0) + tot;
    byLead[r.leadId] = (byLead[r.leadId] || 0) + tot;
    if (r.invoiceNumber) byInvoice[r.invoiceNumber] = (byInvoice[r.invoiceNumber] || 0) + tot;
  });

  var deliveredCount = rows.filter(function (r) { return !!r.deliveryDate; }).length;
  var execKeys = Object.keys(bySales).filter(function (k) { return k !== 'Unknown'; });
  var modelKeys = Object.keys(byModel).filter(function (k) { return k !== 'Unknown'; });
  var avgDel = deliveredCount > 0 ? round2_(totalExtra / deliveredCount) : 0;
  var avgExec = execKeys.length > 0 ? round2_(totalExtra / execKeys.length) : 0;
  var avgModel = modelKeys.length > 0 ? round2_(totalExtra / modelKeys.length) : 0;

  var dashGid = null;
  try {
    var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
    if (dash) dashGid = dash.getSheetId();
  } catch (e) {}

  var out = [];
  out.push(['DEALER EARNINGS ANALYTICS (OWNER ONLY)', '', '']);
  out.push(['Generated', nowDateTime_(), '']);
  if (dashGid != null && typeof navDrillDownLink_ === 'function') {
    out.push(['Navigation', '← Back to Dashboard', '']);
  } else {
    out.push(['', '', '']);
  }
  out.push(['KPI', 'Value', '']);
  out.push(['Total Dealer Earnings', round2_(totalExtra), '']);
  out.push(['OEM Scheme Income (Dealer Scheme Retained)', round2_(oemIncome), '']);
  out.push(['Insurance Income', round2_(insIncome), '']);
  out.push(['Finance Incentives', round2_(financeInc), '']);
  out.push(['Accessories Income', round2_(accessories), '']);
  out.push(['Exchange Margin', round2_(exchange), '']);
  out.push(['Other Income', round2_(otherIncome), '']);
  out.push(['Average Earnings Per Delivery', avgDel, '']);
  out.push(['Average Earnings Per Executive', avgExec, '']);
  out.push(['Average Earnings Per Model', avgModel, '']);
  out.push(['Pending OEM Claims', round2_(pendingOem), '']);
  out.push(['Pending Insurance Receivables', round2_(pendingIns), '']);
  out.push(['Rows', rows.length, '']);
  out.push(['', '', '']);

  function dump(title, map) {
    out.push([title, 'Amount', '']);
    Object.keys(map).sort().forEach(function (k) {
      out.push([k, round2_(map[k]), '']);
    });
    out.push(['', '', '']);
  }
  dump('Month Wise', byMonth);
  dump('Year Wise', byYear);
  dump('Model Wise', byModel);
  dump('Variant Wise', byVariant);
  dump('Executive Wise', bySales);
  dump('Lead Source Wise', bySource);
  dump('Lead Wise', byLead);
  dump('Invoice Wise', byInvoice);

  sheet.getRange(1, 1, out.length, 3).setValues(out);
  sheet.getRange(1, 1).setFontWeight('bold').setFontSize(12);
  if (dashGid != null && typeof navDrillDownLink_ === 'function') {
    sheet.getRange(3, 2).setFormula(navDrillDownLink_(dashGid, '← Back to Dashboard', '← Back to Dashboard'));
  }
  if (!sheet.isSheetHidden()) sheet.hideSheet();

  return {
    totalDealerEarnings: round2_(totalExtra),
    oemSchemeIncome: round2_(oemIncome),
    insuranceIncome: round2_(insIncome),
    financeIncentives: round2_(financeInc),
    accessoriesIncome: round2_(accessories),
    exchangeMargin: round2_(exchange),
    otherIncome: round2_(otherIncome),
    avgPerDelivery: avgDel,
    avgPerExecutive: avgExec,
    avgPerModel: avgModel,
    pendingOemClaims: round2_(pendingOem),
    pendingInsurance: round2_(pendingIns),
    byModel: byModel,
    byExecutive: bySales,
    bySource: bySource,
    byMonth: byMonth,
    rows: rows.length
  };
}

function rebuildExtraIncomeAnalytics_() {
  return rebuildDealerEarningsAnalytics_();
}

/** Aggregate metrics for owner Dashboard (no customer KPI impact). */
function computeDealerEarningsDashboardMetrics_() {
  var rows = readAllDealerEarningsRows_();
  var m = {
    totalDealerEarnings: 0,
    oemSchemeIncome: 0,
    insuranceIncome: 0,
    financeIncentives: 0,
    accessoriesIncome: 0,
    otherIncome: 0,
    avgPerDelivery: 0,
    avgPerExecutive: 0,
    avgPerModel: 0,
    pendingOemClaims: 0,
    pendingInsurance: 0,
    byModel: {},
    byExecutive: {},
    bySource: {},
    byMonth: {}
  };
  var delivered = 0;
  rows.forEach(function (r) {
    var tot = num_(r.totalDealerEarnings);
    m.totalDealerEarnings += tot;
    m.oemSchemeIncome += num_(r.dealerSchemeRetained);
    m.insuranceIncome += num_(r.dealerInsuranceIncome);
    m.financeIncentives += num_(r.financeIncentive);
    m.accessoriesIncome += num_(r.accessoriesMargin);
    m.otherIncome += num_(r.otherIncome);
    if (r.deliveryDate) delivered++;
    if (String(r.claimStatus || '') === 'Pending') m.pendingOemClaims += num_(r.oemEligible);
    if (String(r.insuranceStatus || '') === 'Pending') {
      m.pendingInsurance += Math.max(0, num_(r.insurancePayout) - num_(r.customerInsuranceBenefitPassed));
    }
    var model = r.model || 'Unknown';
    var exec = r.executive || 'Unknown';
    var src = r.leadSource || 'Unknown';
    var month = (r.deliveryDate || r.bookingDate || '').substring(0, 7) || 'Unknown';
    m.byModel[model] = (m.byModel[model] || 0) + tot;
    m.byExecutive[exec] = (m.byExecutive[exec] || 0) + tot;
    m.bySource[src] = (m.bySource[src] || 0) + tot;
    m.byMonth[month] = (m.byMonth[month] || 0) + tot;
  });
  m.totalDealerEarnings = round2_(m.totalDealerEarnings);
  m.oemSchemeIncome = round2_(m.oemSchemeIncome);
  m.insuranceIncome = round2_(m.insuranceIncome);
  m.financeIncentives = round2_(m.financeIncentives);
  m.accessoriesIncome = round2_(m.accessoriesIncome);
  m.otherIncome = round2_(m.otherIncome);
  m.pendingOemClaims = round2_(m.pendingOemClaims);
  m.pendingInsurance = round2_(m.pendingInsurance);
  m.avgPerDelivery = delivered > 0 ? round2_(m.totalDealerEarnings / delivered) : 0;
  var execN = Object.keys(m.byExecutive).length;
  var modelN = Object.keys(m.byModel).length;
  m.avgPerExecutive = execN > 0 ? round2_(m.totalDealerEarnings / execN) : 0;
  m.avgPerModel = modelN > 0 ? round2_(m.totalDealerEarnings / modelN) : 0;
  return m;
}

/** Write owner-only Dealer Earnings analytics block on Dashboard (row 96+). */
function writeDealerEarningsDashboardSection_(dash, metrics, drill) {
  if (typeof isSpreadsheetOwner_ !== 'function' || !isSpreadsheetOwner_()) return;
  dash = dash || getSheet_(CRM.SHEETS.DASHBOARD);
  metrics = metrics || computeDealerEarningsDashboardMetrics_();
  drill = drill || {};

  var start = 96;
  dash.getRange(start, 1, 30, 4).clearContent().clearFormat();
  dash.getRange(start, 1).setValue('DEALER EARNINGS (OWNER ONLY)').setFontWeight('bold').setFontSize(12);
  dash.getRange(start, 2).setValue('Hidden from non-owners · Click any value for drill-down')
    .setFontColor('#666666').setFontSize(10);

  var analyticsGid = null;
  try {
    var aSheet = ensureDealerEarningsAnalyticsSheet_();
    if (aSheet) analyticsGid = aSheet.getSheetId();
  } catch (e) {}

  function linkVal(gid, value, label) {
    var lab = label != null ? label : ('₹' + Math.round(Number(value || 0)).toLocaleString('en-IN'));
    if (gid != null && typeof navDrillDownLink_ === 'function') {
      return navDrillDownLink_(gid, lab, lab);
    }
    return lab;
  }

  var kpis = [
    ['Total Dealer Earnings', metrics.totalDealerEarnings, analyticsGid],
    ['OEM Scheme Income', metrics.oemSchemeIncome, analyticsGid],
    ['Insurance Income', metrics.insuranceIncome, analyticsGid],
    ['Finance Incentives', metrics.financeIncentives, analyticsGid],
    ['Accessories Income', metrics.accessoriesIncome, analyticsGid],
    ['Other Income', metrics.otherIncome, analyticsGid],
    ['Avg Earnings / Delivery', metrics.avgPerDelivery, analyticsGid],
    ['Avg Earnings / Executive', metrics.avgPerExecutive, analyticsGid],
    ['Avg Earnings / Model', metrics.avgPerModel, analyticsGid],
    ['Pending OEM Claims', metrics.pendingOemClaims, analyticsGid],
    ['Pending Insurance Receivables', metrics.pendingInsurance, analyticsGid]
  ];

  kpis.forEach(function (row, i) {
    var r = start + 2 + i;
    dash.getRange(r, 1).setValue(row[0]).setFontWeight('bold');
    var f = linkVal(row[2], row[1]);
    if (typeof f === 'string' && f.indexOf('=HYPERLINK') === 0) {
      dash.getRange(r, 2).setFormula(f);
    } else {
      dash.getRange(r, 2).setValue(f);
    }
  });

  // Model / Executive / Source mini tables with drill sheets
  var col = 4;
  function writeBreak(title, map, metricKey) {
    dash.getRange(start, col).setValue(title).setFontWeight('bold');
    var keys = Object.keys(map || {}).sort();
    keys.slice(0, 12).forEach(function (k, i) {
      var gid = drill[metricKey] && drill[metricKey][k.toLowerCase()];
      dash.getRange(start + 1 + i, col).setValue(k);
      var lab = '₹' + Math.round(map[k]).toLocaleString('en-IN');
      if (gid != null && typeof navDrillDownLink_ === 'function') {
        dash.getRange(start + 1 + i, col + 1).setFormula(navDrillDownLink_(gid, lab, lab));
      } else if (analyticsGid != null) {
        dash.getRange(start + 1 + i, col + 1).setFormula(navDrillDownLink_(analyticsGid, lab, lab));
      } else {
        dash.getRange(start + 1 + i, col + 1).setValue(lab);
      }
    });
    col += 3;
  }

  writeBreak('Model Wise', metrics.byModel, 'byModel');
  writeBreak('Executive Wise', metrics.byExecutive, 'byExecutive');
  writeBreak('Lead Source Wise', metrics.bySource, 'bySource');
}

function buildDealerEarningsDrillDowns_(gids) {
  if (typeof isSpreadsheetOwner_ !== 'function' || !isSpreadsheetOwner_()) return gids;
  gids = gids || {};
  gids.dealerEarnings = gids.dealerEarnings || { byModel: {}, byExecutive: {}, bySource: {}, byMonth: {} };
  var rows = readAllDealerEarningsRows_();
  var hdr = ['Lead ID', 'Customer', 'Model', 'Executive', 'Source', 'Total Earnings', 'Claim Status', 'Insurance Status'];

  function group(keyFn) {
    var bags = {};
    rows.forEach(function (r) {
      var k = keyFn(r) || 'Unknown';
      if (!bags[k]) bags[k] = [];
      bags[k].push([
        typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', r.leadId, r.leadId) : r.leadId,
        r.customer,
        r.model || r.vehicle,
        r.executive,
        r.leadSource,
        r.totalDealerEarnings,
        r.claimStatus,
        r.insuranceStatus
      ]);
    });
    return bags;
  }

  var byModel = group(function (r) { return r.model || 'Unknown'; });
  Object.keys(byModel).forEach(function (k) {
    gids.dealerEarnings.byModel[k.toLowerCase()] =
      navWriteDrillDownSheet_('DE — Model — ' + k, hdr, byModel[k]);
  });
  var byExec = group(function (r) { return r.executive || 'Unknown'; });
  Object.keys(byExec).forEach(function (k) {
    gids.dealerEarnings.byExecutive[k.toLowerCase()] =
      navWriteDrillDownSheet_('DE — Executive — ' + k, hdr, byExec[k]);
  });
  var bySrc = group(function (r) { return r.leadSource || 'Unknown'; });
  Object.keys(bySrc).forEach(function (k) {
    gids.dealerEarnings.bySource[k.toLowerCase()] =
      navWriteDrillDownSheet_('DE — Source — ' + k, hdr, bySrc[k]);
  });
  return gids;
}

/** Owner menu — open Dealer Earnings Register. */
function menuOpenDealerEarningsRegister() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Dealer Earnings is available to the spreadsheet owner only.');
    return;
  }
  ensureDealerEarningsRegisterSheet_();
  var sh = getSpreadsheet_().getSheetByName(dealerEarningsRegisterName_());
  if (sh) {
    sh.showSheet();
    getSpreadsheet_().setActiveSheet(sh);
  }
}

function menuOpenDealerEarningsAnalytics() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Dealer Earnings is available to the spreadsheet owner only.');
    return;
  }
  rebuildDealerEarningsAnalytics_();
  var sh = getSpreadsheet_().getSheetByName(dealerEarningsAnalyticsName_());
  if (sh) {
    sh.showSheet();
    getSpreadsheet_().setActiveSheet(sh);
  }
}

function menuRebuildDealerEarnings() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Dealer Earnings is available to the spreadsheet owner only.');
    return;
  }
  return crmRun_('DealerEarnings', 'Rebuild All', function () {
    var store = loadCrmStore_(true);
    var n = 0;
    var ids = {};
    // Prefer booked leads (have commercial snapshot) — these are the ones with scheme earnings.
    Object.keys((store.commercial && store.commercial.byLeadId) || {}).forEach(function (id) {
      ids[id] = true;
    });
    Object.keys(store.leads.byId || {}).forEach(function (id) {
      ids[id] = true;
    });
    Object.keys(ids).forEach(function (id) {
      try {
        upsertDealerEarningsForLead_(id, { reason: 'rebuild_all', rebuildAnalytics: false });
        n++;
      } catch (e) {
        Logger.log('rebuild earnings ' + id + ': ' + e.message);
      }
    });
    rebuildDealerEarningsAnalytics_();
    SpreadsheetApp.getUi().alert('Dealer Earnings rebuilt for ' + n + ' lead(s).');
    return { count: n };
  });
}

/** One-click safe header repair for OEM Extra Support columns (owner). */
function menuRepairOemExtraSupportHeaders() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Owner only.');
    return;
  }
  try {
    if (typeof ensureCommercialSnapshotHeaders_ === 'function') ensureCommercialSnapshotHeaders_();
    if (typeof ensureDealerEarningsRegisterSheet_ === 'function') ensureDealerEarningsRegisterSheet_();
    if (typeof ensureOemExtraSupportRegisterSheet_ === 'function') ensureOemExtraSupportRegisterSheet_();
    var bleed = { cleared: 0 };
    if (typeof repairOemExtraSupportSchemeBleed_ === 'function') {
      bleed = repairOemExtraSupportSchemeBleed_() || { cleared: 0 };
    }
    invalidateCrmStore_();
    var rebuilt = 0;
    try {
      var store = loadCrmStore_(true);
      var ids = {};
      Object.keys((store.commercial && store.commercial.byLeadId) || {}).forEach(function (id) { ids[id] = true; });
      Object.keys(store.leads.byId || {}).forEach(function (id) { ids[id] = true; });
      Object.keys(ids).forEach(function (id) {
        try {
          upsertDealerEarningsForLead_(id, { reason: 'header_repair', rebuildAnalytics: false });
          rebuilt++;
        } catch (eRb) {
          Logger.log('header repair rebuild ' + id + ': ' + eRb.message);
        }
      });
      if (typeof rebuildDealerEarningsAnalytics_ === 'function') rebuildDealerEarningsAnalytics_();
    } catch (eAll) {
      Logger.log('menuRepair rebuild: ' + eAll.message);
    }
    SpreadsheetApp.getUi().alert(
      'OEM Extra Support repaired.\n\n' +
      'Cleared scheme-bleed Extra Support rows: ' + bleed.cleared + '\n' +
      'Dealer Earnings rebuilt for ' + rebuilt + ' lead(s).\n\n' +
      'Remember: OEM Extra Support is NOT Exchange/Loyalty/Referral/DSA.\n' +
      'It is a separate case-wise amount from OEM to increase dealer profit.\n\n' +
      'If a lead truly has Extra Support, open Scheme Update and type it again.'
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Repair failed: ' + (e && e.message ? e.message : e));
  }
}

/** "Exchange ₹10,000 · Referral ₹5,000" — includes negative retained (full benefit). */
function schemeBreakupText_(byComponent) {
  var labels = { consumerDiscount: 'Consumer', exchangeBonus: 'Exchange', loyaltyBonus: 'Loyalty',
    referralBonus: 'Referral', dsaDiscount: 'DSA' };
  var parts = [];
  Object.keys(byComponent || {}).forEach(function (k) {
    var v = Number(byComponent[k] || 0);
    if (v !== 0) parts.push((labels[k] || k) + ' \u20B9' + v.toLocaleString('en-IN'));
  });
  return parts.join(' \u00B7 ');
}
