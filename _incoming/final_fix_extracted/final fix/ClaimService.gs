/**
 * ClaimService.gs — Scheme / OEM claim lifecycle
 *
 * Scheme Claim Register = permanent ledger (never archive, never delete on rebuild).
 *   • Auto rows — rebuilt from Commercial Snapshot (derived cols refresh; lifecycle preserved)
 *   • Manual rows — operator-entered; always kept
 *
 * Menus:
 *   Record Claim Received  — settle when OEM pays
 *   Add Manual Claim       — ad-hoc claim entry
 *   Update Claim Status    — Submit / Approve / Reject
 *   Open Claim Register    — navigate to All Claims tab
 */

function getClaimCfg_() {
  return (CRM && CRM.CLAIM_REGISTER) || null;
}

function ensureClaimRegisterReady_() {
  var sheet = typeof ensureClaimRegisterSheet_ === 'function' ? ensureClaimRegisterSheet_() : null;
  if (sheet && sheet.isSheetHidden()) sheet.showSheet();
  if (sheet) ensureClaimRegisterValidation_(sheet);
  return sheet;
}

/** Dropdown validation on lifecycle columns — never archive rows. */
function ensureClaimRegisterValidation_(sheet) {
  sheet = sheet || ensureClaimRegisterReady_();
  if (!sheet) return;
  var cfg = getClaimCfg_();
  if (!cfg) return;
  var lastRow = Math.max(sheet.getLastRow(), cfg.DATA_START + 500);
  var numRows = lastRow - cfg.DATA_START + 1;
  var headers = getHeaders_(sheet, cfg.HEADER_ROW);

  function setListValidation(colName, options) {
    var col = findHeaderIndex_(headers, colName) + 1;
    if (col < 1 || !options || !options.length) return;
    var rule = SpreadsheetApp.newDataValidation()
      .requireValueInList(options, true)
      .setAllowInvalid(false)
      .build();
    sheet.getRange(cfg.DATA_START, col, numRows, 1).setDataValidation(rule);
  }

  setListValidation('Claim Status', cfg.CLAIM_STATUSES || ['Pending', 'Submitted', 'Approved', 'Rejected', 'Received', 'Not Applicable']);
  setListValidation('DSA Approval', cfg.APPROVAL_STATUSES || ['Pending', 'Approved', 'Rejected']);
  setListValidation('Source', ['Auto', 'Manual']);
}

/** Read every claim row — never filtered by status. */
function readAllClaims_() {
  var cfg = getClaimCfg_();
  var out = [];
  if (!cfg) return out;
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
  if (!sheet) return out;
  var lastRow = sheet.getLastRow();
  if (lastRow < cfg.DATA_START) return out;
  var headers = getHeaders_(sheet, cfg.HEADER_ROW);
  var numRows = lastRow - cfg.DATA_START + 1;
  var data = sheet.getRange(cfg.DATA_START, 1, numRows, headers.length).getValues();
  data.forEach(function (row, i) {
    var claimId = String(rowVal_(row, headers, 'Claim ID') || '').trim();
    if (!claimId) return;
    var map = {};
    cfg.COLS.forEach(function (col) { map[col] = rowVal_(row, headers, col); });
    out.push({
      claimId: claimId,
      sheetRow: cfg.DATA_START + i,
      row: row,
      map: map,
      source: String(map['Source'] || 'Auto').trim(),
      status: String(map['Claim Status'] || '').trim(),
      leadId: String(map['Lead ID'] || '').trim(),
      bookingId: String(map['Booking ID'] || '').trim(),
      claimAmount: round2_(num_(map['Claim Amount'])),
      receivedAmount: round2_(num_(map['Received Amount']))
    });
  });
  return out;
}

function findClaimById_(claimId) {
  claimId = String(claimId || '').trim();
  if (!claimId) return null;
  var all = readAllClaims_();
  for (var i = 0; i < all.length; i++) {
    if (all[i].claimId === claimId) return all[i];
  }
  return null;
}

function claimRowFromMap_(map) {
  var cfg = getClaimCfg_();
  if (!cfg) return [];
  return cfg.COLS.map(function (c) { return map[c] === undefined || map[c] === null ? '' : map[c]; });
}

function computeClaimAgeing_(submitted, received, approved) {
  if (!submitted) return '';
  var endIso = received || approved || nowDate_();
  return daysBetween_(submitted, endIso);
}

function writeClaimRowAt_(sheetRow, map) {
  var sheet = ensureClaimRegisterReady_();
  var cfg = getClaimCfg_();
  if (!sheet || !cfg) throw businessError_('Claim Register not available', 'MISSING_SHEET');
  var headers = getHeaders_(sheet, cfg.HEADER_ROW);
  var rowArr = claimRowFromMap_(map);
  if (sheetRow > 0) {
    sheet.getRange(sheetRow, 1, 1, rowArr.length).setValues([rowArr]);
  } else {
    var newRow = Math.max(sheet.getLastRow() + 1, cfg.DATA_START);
    sheet.getRange(newRow, 1, 1, rowArr.length).setValues([rowArr]);
    sheetRow = newRow;
  }
  try {
    if (map['Lead ID']) {
      upsertRelationshipIndex_({
        LeadID: map['Lead ID'],
        BookingID: map['Booking ID'] || '',
        ClaimID: map['Claim ID'],
        'Current Status': map['Claim Status'] || 'Pending'
      });
    }
  } catch (e) {}
  return sheetRow;
}

function updateClaimFields_(claimId, fields) {
  claimId = String(claimId || '').trim();
  fields = fields || {};
  var found = findClaimById_(claimId);
  if (!found) throw businessError_('Claim not found: ' + claimId, 'NOT_FOUND');
  var map = found.map;
  Object.keys(fields).forEach(function (k) {
    if (fields[k] !== undefined) map[k] = fields[k];
  });
  if (fields['Claim Submitted Date'] !== undefined || fields['Claim Received Date'] !== undefined || fields['Claim Approved Date'] !== undefined) {
    map['Claim Ageing (Days)'] = computeClaimAgeing_(
      map['Claim Submitted Date'],
      map['Claim Received Date'],
      map['Claim Approved Date']
    );
  }
  writeClaimRowAt_(found.sheetRow, map);
  return { claimId: claimId, map: map };
}

/** PUBLIC — open claims for settle/status dialogs. */
function getOpenClaimsForDialog() {
  try {
    var list = readAllClaims_().filter(function (c) {
      var st = String(c.status || '').toLowerCase();
      return st && st !== 'received' && st !== 'not applicable';
    }).map(function (c) {
      return {
        claimId: c.claimId,
        label: c.claimId + ' | ' + (c.map['Component'] || 'Claim') + ' | ' +
          (c.map['Customer'] || c.leadId) + ' | ₹' + c.claimAmount + ' | ' + c.status,
        customer: c.map['Customer'] || '',
        leadId: c.leadId,
        component: c.map['Component'] || '',
        componentKey: c.map['Component Key'] || '',
        claimAmount: c.claimAmount,
        status: c.status,
        reference: c.map['Claim Reference Number'] || ''
      };
    });
    return crmOk_('Claim', { claims: list });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** PUBLIC — load one claim for dialog prefill. */
function getClaimContextForDialog(claimId) {
  try {
    var found = findClaimById_(claimId);
    if (!found) return { ok: false, message: 'Claim not found' };
    return crmOk_('Claim', {
      claim: {
        claimId: found.claimId,
        customer: found.map['Customer'] || '',
        leadId: found.leadId,
        component: found.map['Component'] || '',
        componentKey: found.map['Component Key'] || '',
        claimAmount: found.claimAmount,
        receivedAmount: found.receivedAmount || found.claimAmount,
        status: found.status,
        reference: found.map['Claim Reference Number'] || '',
        submitted: found.map['Claim Submitted Date'] || '',
        approved: found.map['Claim Approved Date'] || '',
        received: found.map['Claim Received Date'] || '',
        remarks: found.map['Claim Remarks'] || ''
      }
    });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function settleClaimFromData_(data) {
  data = data || {};
  var claimId = String(data.claimId || '').trim();
  if (!claimId) throw fieldError_('Claim ID', 'Select a claim to settle.', 'VALIDATION');
  if (!data.receivedDate) throw fieldError_('Received Date', 'Enter the date OEM payment was received.', 'VALIDATION');
  var utr = String(data.reference || data.claimReference || '').trim();
  if (!utr) throw fieldError_('OEM Reference / UTR', 'UTR / OEM payment reference is mandatory.', 'VALIDATION');

  var receivedAmt = data.receivedAmount !== undefined && data.receivedAmount !== ''
    ? round2_(num_(data.receivedAmount))
    : round2_(num_(data.claimAmount));
  if (receivedAmt <= 0) throw fieldError_('Received Amount', 'Enter the amount received from OEM.', 'VALIDATION');

  var fields = {
    'Claim Status': 'Received',
    'Claim Received Date': formatDate_(data.receivedDate),
    'Received Amount': receivedAmt,
    'Claim Reference Number': utr,
    'Claim Remarks': String(data.remarks || '').trim()
  };
  if (data.submittedDate) fields['Claim Submitted Date'] = formatDate_(data.submittedDate);
  if (data.approvedDate) fields['Claim Approved Date'] = formatDate_(data.approvedDate);

  var res = updateClaimFields_(claimId, fields);
  invalidateCrmStore_();
  try {
    var lid = res.map && res.map['Lead ID'];
    if (lid && typeof upsertDealerEarningsForLead_ === 'function') {
      upsertDealerEarningsForLead_(lid, { reason: 'claim_received' });
    } else if (lid && typeof upsertExtraIncomeForLead_ === 'function') {
      upsertExtraIncomeForLead_(lid, { reason: 'claim_received' });
    }
  } catch (eDe) {
    Logger.log('dealer earnings after claim: ' + eDe.message);
  }
  queuePostTransaction_([POST_TX.SYNC_COMPUTED], { dashboard: true, leadId: res.map['Lead ID'] });
  logAudit_('CLAIM_SETTLED', claimId + ' | ₹' + receivedAmt);
  return { claimId: claimId, receivedAmount: receivedAmt, status: 'Received' };
}

function updateClaimStatusFromData_(data) {
  data = data || {};
  var claimId = String(data.claimId || '').trim();
  var status = String(data.status || '').trim();
  if (!claimId) throw fieldError_('Claim ID', 'Select a claim.', 'VALIDATION');
  if (!status) throw fieldError_('Claim Status', 'Select a status.', 'VALIDATION');

  var cfg = getClaimCfg_();
  var allowed = (cfg && cfg.CLAIM_STATUSES) || [];
  if (allowed.indexOf(status) < 0) {
    throw fieldError_('Claim Status', 'Invalid status: ' + status, 'VALIDATION');
  }

  var fields = { 'Claim Status': status };
  if (status === 'Submitted' && data.submittedDate) {
    fields['Claim Submitted Date'] = formatDate_(data.submittedDate);
  } else if (status === 'Submitted') {
    fields['Claim Submitted Date'] = nowDate_();
  }
  if (status === 'Approved' && data.approvedDate) {
    fields['Claim Approved Date'] = formatDate_(data.approvedDate);
  } else if (status === 'Approved') {
    fields['Claim Approved Date'] = nowDate_();
  }
  if (data.reference) fields['Claim Reference Number'] = String(data.reference).trim();
  if (data.remarks) fields['Claim Remarks'] = String(data.remarks).trim();
  if (data.dsaApproval) fields['DSA Approval'] = String(data.dsaApproval).trim();

  var res = updateClaimFields_(claimId, fields);
  invalidateCrmStore_();
  logAudit_('CLAIM_STATUS', claimId + ' → ' + status);
  return { claimId: claimId, status: status };
}

function addManualClaimFromData_(data) {
  data = data || {};
  if (!String(data.customerName || '').trim()) {
    throw fieldError_('Customer Name', 'Enter customer name.', 'VALIDATION');
  }
  var amt = round2_(num_(data.claimAmount));
  if (amt <= 0) throw fieldError_('Claim Amount', 'Enter claim amount greater than zero.', 'VALIDATION');

  var claimId = generateId_('claim');
  var leadId = String(data.leadId || '').trim();
  var bookingId = String(data.bookingId || '').trim();
  var status = String(data.status || 'Pending').trim();
  var submitted = formatDate_(data.submittedDate) || (status === 'Submitted' ? nowDate_() : '');

  var map = {
    'Claim ID': claimId,
    'Source': 'Manual',
    'Booking ID': bookingId,
    'Lead ID': leadId,
    'Customer': String(data.customerName).trim(),
    'Model': String(data.model || '').trim(),
    'Variant': String(data.variant || '').trim(),
    'Booking Date': formatDate_(data.bookingDate) || '',
    'Scheme Month': String(data.schemeMonth || '').trim() || (data.bookingDate ? String(data.bookingDate).substring(0, 7) : nowDate_().substring(0, 7)),
    'Executive': String(data.executive || '').trim(),
    'Consumer Discount': num_(data.consumerDiscount),
    'Exchange Bonus': num_(data.exchangeBonus),
    'Loyalty Bonus': num_(data.loyaltyBonus),
    'Referral Bonus': num_(data.referralBonus),
    'DSA Discount': num_(data.dsaDiscount),
    'Additional Discount': num_(data.additionalDiscount),
    'Total Discount': round2_(num_(data.totalDiscount)),
    'Dealer Discount': round2_(num_(data.dealerDiscount)),
    'OEM Discount': round2_(num_(data.oemDiscount)),
    'DSA Approval': String(data.dsaApproval || 'Pending').trim(),
    'Claim Required': 'Yes',
    'Eligible Claim': amt,
    'Claim Amount': amt,
    'Received Amount': '',
    'Claim Status': status,
    'Claim Reference Number': String(data.reference || '').trim(),
    'Claim Submitted Date': submitted,
    'Claim Approved Date': formatDate_(data.approvedDate) || '',
    'Claim Received Date': formatDate_(data.receivedDate) || '',
    'Claim Ageing (Days)': submitted ? computeClaimAgeing_(submitted, data.receivedDate, data.approvedDate) : '',
    'Claim Remarks': String(data.remarks || 'Manual claim entry').trim()
  };

  if (map['Claim Received Date']) {
    map['Claim Status'] = 'Received';
    map['Received Amount'] = data.receivedAmount ? round2_(num_(data.receivedAmount)) : amt;
  }

  writeClaimRowAt_(0, map);
  invalidateCrmStore_();
  logAudit_('CLAIM_MANUAL', claimId + ' | ' + map['Customer'] + ' | ₹' + amt);
  return { claimId: claimId };
}

/** Refresh read-only status summary at top of Claim Register (does not remove data rows). */
function refreshClaimRegisterSummary_() {
  var sheet = ensureClaimRegisterReady_();
  if (!sheet) return;
  var all = readAllClaims_();
  var byStatus = {};
  all.forEach(function (c) {
    var st = c.status || 'Pending';
    if (!byStatus[st]) byStatus[st] = { count: 0, amount: 0 };
    byStatus[st].count++;
    byStatus[st].amount = round2_(byStatus[st].amount + c.claimAmount);
  });
  return { total: all.length, byStatus: byStatus };
}

function menuOpenClaimRegister() {
  try {
    ensureClaimRegisterReady_();
    if (typeof navGoToSheetPublic === 'function') navGoToSheetPublic(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
    else {
      var sh = getSpreadsheet_().getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
      if (sh) sh.activate();
    }
    SpreadsheetApp.getUi().alert(
      'Scheme Claim Register',
      'All claims are listed here permanently — nothing is archived or deleted.\n\n' +
      '• Pending / Submitted / Approved — use CRM → Claims → Update Claim Status\n' +
      '• When OEM pays — use CRM → Claims → Record Claim Received\n' +
      '• Ad-hoc claims — use CRM → Claims → Add Manual Claim',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

function settleClaimFromDialog(data) {
  try {
    return runCriticalBusinessTransaction_({
      module: 'Claim',
      action: 'settleClaimFromDialog',
      successMessage: 'Claim settled — OEM payment recorded',
      commitFn: function () { return settleClaimFromData_(data); },
      context: { module: 'Claim', action: 'Claim Received', auditAction: 'CLAIM_SETTLED', perfOp: 'claim_settle', sheets: [CRM.SHEETS.SCHEME_CLAIM_REGISTER] },
      postTasks: [POST_TX.INVALIDATE_STORE, POST_TX.SYNC_COMPUTED, POST_TX.AUDIT]
    });
  } catch (e) {
    return crmFailStructured_('Claim', 'settleClaimFromDialog', 'handler', e, 0);
  }
}

function updateClaimStatusFromDialog(data) {
  try {
    return runCriticalBusinessTransaction_({
      module: 'Claim',
      action: 'updateClaimStatusFromDialog',
      successMessage: 'Claim status updated',
      commitFn: function () { return updateClaimStatusFromData_(data); },
      context: { module: 'Claim', action: 'Claim Status', auditAction: 'CLAIM_STATUS', perfOp: 'claim_status', sheets: [CRM.SHEETS.SCHEME_CLAIM_REGISTER] },
      postTasks: [POST_TX.INVALIDATE_STORE, POST_TX.AUDIT]
    });
  } catch (e) {
    return crmFailStructured_('Claim', 'updateClaimStatusFromDialog', 'handler', e, 0);
  }
}

function addManualClaimFromDialog(data) {
  try {
    return runCriticalBusinessTransaction_({
      module: 'Claim',
      action: 'addManualClaimFromDialog',
      successMessage: 'Manual claim added',
      commitFn: function () { return addManualClaimFromData_(data); },
      context: { module: 'Claim', action: 'Manual Claim', auditAction: 'CLAIM_MANUAL', perfOp: 'claim_manual', sheets: [CRM.SHEETS.SCHEME_CLAIM_REGISTER] },
      postTasks: [POST_TX.INVALIDATE_STORE, POST_TX.AUDIT]
    });
  } catch (e) {
    return crmFailStructured_('Claim', 'addManualClaimFromDialog', 'handler', e, 0);
  }
}
