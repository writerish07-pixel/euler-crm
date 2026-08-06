/**
 * FinanceService.gs — Euler Motors Dealership CRM v2.2
 *
 * Changes from v2.1:
 *   ✔ recordFinanceFileReceipt_ no longer calls validatePaymentAmount_.
 *       Finance receipt = money from FINANCER to DEALER. This is NOT a customer
 *       payment. Customer outstanding was already zeroed when Add Payment
 *       (Finance mode) was saved. Re-validating against Customer Payable caused
 *       a spurious "Payment exceeds Customer Payable" error.
 *   ✔ Payment Ledger write removed from financer receipt path.
 *       Payment Ledger tracks CUSTOMER payments only. Finance Register is the
 *       authoritative ledger for financer transactions.
 *   ✔ Customer outstanding NOT changed on financer receipt (already correct).
 *   ✔ Finance Pending view now writes Lead ID as clickable HYPERLINK backlinks.
 *   ✔ Finance Pending view adds bifurcation summary by Financer at the bottom.
 */

// ═══════════════════════════════════════════════════════════════════════════
//  SCHEMA
// ═══════════════════════════════════════════════════════════════════════════

function ensureFinanceRegisterSheet_() {
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.FINANCE_REGISTER;
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var cols = (CRM.FINANCE_REGISTER && CRM.FINANCE_REGISTER.COLS) || [
    'File Number', 'Lead ID', 'Customer Name', 'Financer', 'Sanctioned Amount',
    'Received Against File', 'File Outstanding', 'Status', 'Last Payment Date', 'Last Updated'
  ];
  var headers = getHeaders_(sheet, 1);
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
  return sheet;
}

function isSchemeClaimReceivedForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId || !CRM.SHEETS.SCHEME_CLAIM_REGISTER) return false;
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
    if (!sheet) return false;
    var headers = getHeaders_(sheet, CRM.CLAIM_REGISTER.HEADER_ROW);
    var leadCol = findHeaderIndex_(headers, 'Lead ID');
    var statusCol = findHeaderIndex_(headers, 'Claim Status');
    if (leadCol < 0 || statusCol < 0) return false;
    var last = sheet.getLastRow();
    if (last < CRM.CLAIM_REGISTER.DATA_START) return false;
    var data = sheet.getRange(CRM.CLAIM_REGISTER.DATA_START, 1, last - CRM.CLAIM_REGISTER.DATA_START + 1, headers.length).getValues();
    for (var i = 0; i < data.length; i++) {
      if (String(data[i][leadCol] || '').trim() !== leadId) continue;
      var st = String(data[i][statusCol] || '').trim().toLowerCase();
      if (st === 'received') return true;
    }
  } catch (e) {}
  return false;
}

function findFinanceRowByFile_(sheet, headers, fileNumber) {
  fileNumber = String(fileNumber || '').trim();
  if (!fileNumber) return -1;
  var col = findHeaderIndex_(headers, 'File Number') + 1;
  if (col < 1) return -1;
  var last = sheet.getLastRow();
  if (last < 2) return -1;
  var vals = sheet.getRange(2, col, Math.max(0, last - 1), 1).getValues();
  for (var i = 0; i < vals.length; i++) {
    if (String(vals[i][0] || '').trim() === fileNumber) return i + 2;
  }
  return -1;
}

/** Reuse open file for lead, else existing Lead Register file, else auto-generate FN…. */
function resolveFinanceFileNumberForLead_(leadId, preferred) {
  leadId = String(leadId || '').trim();
  preferred = String(preferred || '').trim();
  if (preferred) return preferred;

  // Prefer an existing Open file for this lead.
  try {
    var open = listPendingFinanceFiles_().filter(function (f) { return f.leadId === leadId; });
    if (open.length) return open[0].fileNumber;
  } catch (e) {}

  // Else reuse Lead Register value if present.
  try {
    var lead = getLeadFromRegisterLight_(leadId) || (loadCrmStore_().leads.byId[leadId]);
    var existing = lead && (lead.financeFileNumber || lead['Finance File Number']);
    if (!existing && leadId) {
      var lrSheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
      var lrHeaders = getHeaders_(lrSheet, CRM.LEAD.HEADER_ROW);
      var row = findLeadById_(leadId);
      if (row && row.row) {
        var col = findHeaderIndex_(lrHeaders, 'Finance File Number') + 1;
        if (col > 0) existing = String(lrSheet.getRange(row.row, col).getValue() || '').trim();
      }
    }
    if (existing) return String(existing).trim();
  } catch (e2) {}

  return generateId_('financeFile');
}

/**
 * Push Finance Required / Financer / File Number to every tab that carries those fields.
 */
function syncFinanceFlagAcrossTabs_(leadId, opts) {
  leadId = String(leadId || '').trim();
  if (!leadId) return;
  opts = opts || {};
  var financeRequired = opts.financeRequired;
  if (financeRequired === true)  financeRequired = 'Yes';
  if (financeRequired === false) financeRequired = 'No';
  if (financeRequired != null) {
    financeRequired = String(financeRequired).trim();
    if (financeRequired && financeRequired.toLowerCase() !== 'yes' && financeRequired.toLowerCase() !== 'no') {
      if (!opts.financerName) opts.financerName = financeRequired;
      financeRequired = 'Yes';
    }
  }
  var financerName = String(opts.financerName || '').trim();
  var fileNumber   = String(opts.financeFileNumber || opts.fileNumber || '').trim();
  var paymentMode  = String(opts.paymentMode || '').trim();

  // Lead Register
  var leadFields = { 'Last Updated': nowDateTime_(), 'Last Updated By': getUserEmail_() };
  if (financeRequired) leadFields['Finance Required']      = financeRequired;
  if (financerName)    leadFields['Financer Name']         = financerName;
  if (fileNumber)      leadFields['Finance File Number']   = fileNumber;
  if (paymentMode)     leadFields['Last Payment Mode']     = paymentMode;
  try { updateLeadRegisterFields_(leadId, leadFields); } catch (e1) {}

  // Booking Register
  try { updateBookingRegisterFinanceFlag_(leadId, financeRequired, financerName, paymentMode); } catch (e2) {}

  // Active Commercial Snapshot
  try {
    var store = loadCrmStore_(true);
    var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
    if (entry && entry.sheetRow) {
      var csSheet  = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
      if (csSheet) {
        var csHeaders = getHeaders_(csSheet, CRM.COMMERCIAL.HEADER_ROW);
        function setSnap(name, val) {
          if (val === undefined || val === null || val === '') return;
          var c = findHeaderIndex_(csHeaders, name) + 1;
          if (c > 0) setValueSafe_(csSheet.getRange(entry.sheetRow, c), val);
        }
        if (financeRequired) setSnap('Finance Required', financeRequired);
        if (financerName)    setSnap('Financer', financerName);
      }
    }
  } catch (e3) {}

  // Finance Register row for this file (if any)
  try {
    if (fileNumber && typeof ensureFinanceRegisterSheet_ === 'function') {
      var fSheet   = ensureFinanceRegisterSheet_();
      var fHeaders = getHeaders_(fSheet, 1);
      var fRow     = findFinanceRowByFile_(fSheet, fHeaders, fileNumber);
      if (fRow > 0) {
        if (financerName) {
          var fc = findHeaderIndex_(fHeaders, 'Financer') + 1;
          if (fc > 0) setValueSafe_(fSheet.getRange(fRow, fc), financerName);
        }
        var lc = findHeaderIndex_(fHeaders, 'Lead ID') + 1;
        if (lc > 0) setValueSafe_(fSheet.getRange(fRow, lc), leadId);
      }
    }
  } catch (e4) {}
}

function getLatestPaymentMetaForLead_(leadId, store) {
  store = store || loadCrmStore_();
  leadId = String(leadId || '').trim();
  var h    = store.payments.headers;
  var best = null;
  store.payments.rows.forEach(function (row) {
    if (String(rowVal_(row, h, 'Lead ID') || '').trim() !== leadId) return;
    var d    = formatDate_(rowVal_(row, h, 'Date')) || '';
    var meta = {
      mode:       String(rowVal_(row, h, 'Payment Mode') || ''),
      financer:   String(rowVal_(row, h, 'Financer Name') || ''),
      fileNumber: String(rowVal_(row, h, 'Finance File Number') || ''),
      date:       d
    };
    if (!best || (d && (!best.date || d >= best.date))) best = meta;
  });
  return best;
}

function readAllFinanceFiles_() {
  var sheet   = ensureFinanceRegisterSheet_();
  var headers = getHeaders_(sheet, 1);
  var last    = sheet.getLastRow();
  if (last < 2) return [];
  var data = sheet.getRange(2, 1, Math.max(0, last - 1), headers.length).getValues();
  return data.map(function (row, i) {
    function val(name) {
      var idx = findHeaderIndex_(headers, name);
      return idx >= 0 ? row[idx] : '';
    }
    var sanctioned = Number(val('Sanctioned Amount'))    || 0;
    var received   = Number(val('Received Against File')) || 0;
    var fileOs     = Number(val('File Outstanding'));
    if (!isFinite(fileOs)) fileOs = round2_(Math.max(0, sanctioned - received));
    var status = String(val('Status') || '').trim();
    if (!status) status = fileOs <= 0.01 ? 'Settled' : 'Open';
    return {
      sheetRow:           i + 2,
      fileNumber:         String(val('File Number')   || '').trim(),
      leadId:             String(val('Lead ID')       || '').trim(),
      customerName:       String(val('Customer Name') || '').trim(),
      financer:           String(val('Financer')      || '').trim(),
      sanctionedAmount:   sanctioned,
      receivedAgainstFile: received,
      fileOutstanding:    round2_(fileOs),
      status:             status,
      lastPaymentDate:    formatDate_(val('Last Payment Date')) || ''
    };
  }).filter(function (f) { return !!f.fileNumber; });
}

/** Pending = Open status OR File Outstanding > 0. Settled files are excluded. */
function listPendingFinanceFiles_() {
  return readAllFinanceFiles_().filter(function (f) {
    var st = String(f.status || '').toLowerCase();
    if (st === 'settled' || st === 'closed' || st === 'received') return false;
    return Number(f.fileOutstanding) > 0.01;
  });
}

/** PUBLIC — for Finance Receipt dialog. */
function getPendingFinanceFilesForDialog() {
  try {
    refreshFinancePendingView_();
    var files = listPendingFinanceFiles_();
    return {
      success: true,
      files:   files,
      count:   files.length,
      today:   nowDate_()
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e), errorCode: 'ERROR' };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  BACKLINK HELPER
//  Writes the Lead ID cell as a HYPERLINK formula so clicking it navigates
//  directly to the lead's row in the Lead Register (backlink).
// ═══════════════════════════════════════════════════════════════════════════

function writeLeadIdBacklink_(sheet, sheetRow, col, leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId || col < 1) return;
  try {
    var formula = typeof navLeadIdBacklinkFormula_ === 'function'
      ? navLeadIdBacklinkFormula_(leadId)
      : null;
    if (formula) {
      sheet.getRange(sheetRow, col).setFormula(formula);
      return;
    }
  } catch (e) {}
  try { sheet.getRange(sheetRow, col).setValue(leadId); } catch (e2) {}
}

// ═══════════════════════════════════════════════════════════════════════════
//  UPSERT FINANCE FILE
//
//  info.isReceipt controls how the amount is applied:
//
//    isReceipt: false  (default — called from Add Payment, Finance mode)
//      The amount is the sanctioned/DO amount approved by the financer.
//      It has NOT been received as cash yet.
//      → Sanctioned Amount = max(info.sanctionedAmount, amt)
//      → Received Against File stays at 0 (new row) or unchanged (update)
//      → File Outstanding = Sanctioned Amount
//      → Status = 'Open'
//      → File appears in the Record Financer Receipt dropdown ✔
//
//    isReceipt: true  (called from Record Financer Receipt dialog)
//      The amount is actual cash received from the financer.
//      → Received Against File += amt
//      → File Outstanding = Sanctioned - Received
//      → Status = 'Settled' when fully paid
// ═══════════════════════════════════════════════════════════════════════════

function upsertFinanceFilePayment_(info) {
  info = info || {};
  var fileNumber = String(info.fileNumber || '').trim();
  var leadId     = String(info.leadId     || '').trim();
  if (!fileNumber || !leadId) return null;

  var isReceipt  = info.isReceipt === true; // false = DO entry, true = cash receipt
  var amt        = Number(info.amount         || 0);
  var sanctioned = Number(info.sanctionedAmount || 0);

  var sheet   = ensureFinanceRegisterSheet_();
  var headers = getHeaders_(sheet, 1);
  var cols    = (CRM.FINANCE_REGISTER && CRM.FINANCE_REGISTER.COLS) || headers;
  var row     = findFinanceRowByFile_(sheet, headers, fileNumber);

  var received         = 0;
  var prevReceived     = 0;
  var existingFinancer = '';
  var existingCustomer = '';

  if (row > 0) {
    // ── Existing row ───────────────────────────────────────────────────
    var recvCol = findHeaderIndex_(headers, 'Received Against File');
    var sancCol = findHeaderIndex_(headers, 'Sanctioned Amount');
    var existData = sheet.getRange(row, 1, 1, headers.length).getValues()[0];

    prevReceived = Number(recvCol >= 0 ? existData[recvCol] : 0) || 0;
    if (sancCol >= 0 && Number(existData[sancCol]) > 0) sanctioned = Number(existData[sancCol]);

    var finIdx  = findHeaderIndex_(headers, 'Financer');
    var custIdx = findHeaderIndex_(headers, 'Customer Name');
    if (finIdx  >= 0) existingFinancer = String(existData[finIdx]  || '');
    if (custIdx >= 0) existingCustomer = String(existData[custIdx] || '');

    if (isReceipt) {
      // Cash received from financer — accumulate.
      received = round2_(prevReceived + amt);
    } else {
      // DO update — update sanctioned if new value is larger, don't touch received.
      received  = prevReceived;
      if (!(sanctioned > 0)) sanctioned = amt;
      if (amt > sanctioned) sanctioned = amt;
    }
  } else {
    // ── New row ────────────────────────────────────────────────────────
    row = Math.max(sheet.getLastRow() + 1, 2);

    if (isReceipt) {
      if (!(sanctioned > 0)) sanctioned = amt;
      received = amt;
    } else {
      if (!(sanctioned > 0)) sanctioned = amt;
      received = 0;
    }
  }

  var fileOutstanding = round2_(Math.max(0, sanctioned - received));
  var status          = (isReceipt && fileOutstanding <= 0.01) ? 'Settled' : 'Open';

  var rowMap = {
    'File Number':          fileNumber,
    'Lead ID':              leadId,
    'Customer Name':        info.customerName || existingCustomer || '',
    'Financer':             info.financer     || existingFinancer || '',
    'Sanctioned Amount':    sanctioned,
    'Received Against File': received,
    'File Outstanding':     fileOutstanding,
    'Status':               status,
    'Last Payment Date':    isReceipt ? (formatDate_(info.payDate) || nowDate_()) : (formatDate_(info.payDate) || ''),
    'Last Updated':         nowDateTime_()
  };

  cols.forEach(function (c) {
    if (c === 'Lead ID') return; // handled separately as backlink below
    var col = findHeaderIndex_(headers, c) + 1;
    if (col > 0 && rowMap[c] !== undefined) setValueSafe_(sheet.getRange(row, col), rowMap[c]);
  });

  // Write Lead ID as a clickable hyperlink → navigates to the lead in Lead Register.
  var leadIdCol = findHeaderIndex_(headers, 'Lead ID') + 1;
  writeLeadIdBacklink_(sheet, row, leadIdCol, leadId);

  if (!info.skipPendingRefresh) {
    try { refreshFinancePendingView_(); } catch (e) {}
  }
  return {
    fileNumber:      fileNumber,
    leadId:          leadId,
    received:        received,
    fileOutstanding: fileOutstanding,
    status:          status,
    sanctionedAmount: sanctioned
  };
}

// ═══════════════════════════════════════════════════════════════════════════
//  RECORD FINANCER RECEIPT
//
//  IMPORTANT — conceptual model:
//
//    Add Payment (Finance mode) = customer's obligation fulfilled.
//      • Payment Ledger: customer paid via Finance (amount = vehicle cost).
//      • Lead Outstanding → 0.
//      • Finance Register: Sanctioned = amount, Received = 0, Status = Open.
//
//    Record Financer Receipt = financer pays the dealer.
//      • Finance Register: Received += amount, Outstanding goes down.
//      • Payment Ledger: NOT written (this is not a customer payment).
//      • Lead Outstanding: NOT changed (already correct from above).
//      • Only Finance Register is updated.
//
// ═══════════════════════════════════════════════════════════════════════════

function recordFinanceFileReceipt_(data) {
  data = data || {};
  var postCtx = {
    module:      'Finance',
    action:      'Financer Receipt',
    auditAction: 'FINANCE_FILE_RECEIPT',
    auditDetail: '',
    perfOp:      'finance_receipt',
    sheets:      [CRM.SHEETS.FINANCE_REGISTER]
  };
  return runCriticalBusinessTransaction_({
    module:         'Finance',
    action:         'recordFinanceFileReceipt_',
    successMessage: 'Financer receipt recorded',
    context:        postCtx,
    commitFn: function (setStep) {
      var lock   = LockService.getDocumentLock();
      var locked = false;
      try {
        setStep('lock');
        locked = lock.tryLock(10000);
        if (!locked) throw businessError_('Finance update is busy. Please retry.', 'LOCK_BUSY');

        setStep('validate');
        var fileNumber = String(data.fileNumber || '').trim();
        var amt        = Number(data.amount) || 0;
        var payDate    = formatDate_(data.date) || nowDate_();
        if (!fileNumber) throw fieldError_('Finance File Number', 'Select a pending finance file.', 'VALIDATION');
        if (!(amt > 0))  throw fieldError_('Amount Received',    'Enter an amount greater than zero.', 'VALIDATION');

        var pending = listPendingFinanceFiles_();
        var file = null;
        for (var i = 0; i < pending.length; i++) {
          if (pending[i].fileNumber === fileNumber) { file = pending[i]; break; }
        }
        if (!file) throw fieldError_('Finance File Number',
          'File not found or already settled: ' + fileNumber + '.', 'NOT_FOUND');

        // Validate only against the FINANCE file outstanding (not customer payable).
        // This is money from the financer — it has no relation to the customer payable limit.
        if (amt > file.fileOutstanding + 0.01) {
          throw fieldError_('Amount Received',
            'Amount (₹' + amt + ') cannot exceed file outstanding ₹' + file.fileOutstanding + '.', 'VALIDATION');
        }

        var leadId = file.leadId;
        postCtx.leadId = leadId;
        // Finance receipts allowed after Close (payment arrives later).
        if (typeof requireExistingLead_ === 'function') requireExistingLead_(leadId);
        else requireActiveLead_(leadId);

        setStep('file');
        // isReceipt: true — actual cash received from financer; accumulates Received Against File.
        var upd = upsertFinanceFilePayment_({
          leadId:           leadId,
          customerName:     file.customerName,
          financer:         file.financer,
          fileNumber:       fileNumber,
          amount:           amt,
          payDate:          payDate,
          sanctionedAmount: file.sanctionedAmount,
          isReceipt:        true
        });

        // ── Sync financer info to Lead Register (but do NOT change customer outstanding) ──
        setStep('lead');
        var leadSyncFields = {
          'Finance Required':     'Yes',
          'Financer Name':        file.financer,
          'Finance File Number':  fileNumber,
          'Last Updated':         nowDateTime_(),
          'Last Updated By':      getUserEmail_()
        };
        try { updateLeadRegisterFields_(leadId, leadSyncFields); } catch (le) {}

        if (typeof syncFinanceFlagAcrossTabs_ === 'function') {
          try {
            syncFinanceFlagAcrossTabs_(leadId, {
              financeRequired:   'Yes',
              financerName:      file.financer,
              financeFileNumber: fileNumber
            });
          } catch (se) {}
        }

        postCtx.auditDetail = fileNumber + ' +' + amt + ' receipt on ' + payDate;
        SpreadsheetApp.flush();
        // Finance Pending view rebuild moved off the lock into the deferred worker
        // (it repaints a whole sheet). postCtx already schedules deferred sync.
        return {
          fileNumber:      fileNumber,
          leadId:          leadId,
          amount:          amt,
          fileOutstanding: upd && upd.fileOutstanding,
          status:          upd && upd.status
        };
      } finally {
        if (locked) lock.releaseLock();
      }
    },
    postTasks: [
      POST_TX.INVALIDATE_STORE,
      POST_TX.SYNC_COMPUTED,
      POST_TX.AUDIT,
      POST_TX.TRANSACTION_OK,
      POST_TX.PERF
    ]
  });
}

/** PUBLIC dialog handler. */
function recordFinanceFileReceiptFromDialog(data) {
  try {
    var result = recordFinanceFileReceipt_(data);
    try { refreshCrmAfterDialogSave_(); } catch (re) {}
    return result;
  } catch (e) {
    return crmFailStructured_('Finance', 'recordFinanceFileReceiptFromDialog', 'handler', e, 0);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  FINANCE PENDING VIEW  (with clickable Lead ID backlinks + bifurcation)
// ═══════════════════════════════════════════════════════════════════════════

function refreshFinancePendingView_() {
  var ss   = getSpreadsheet_();
  var name = CRM.SHEETS.FINANCE_PENDING || 'Finance Pending';
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);

  var sla          = getFinanceReceiptSlaDays_();
  var pending      = enrichFinanceFilesWithDelivery_(listPendingFinanceFiles_());
  var overdueCount = pending.filter(function (f) { return f.overdue; }).length;
  var totalOs      = pending.reduce(function (s, f) { return s + Number(f.fileOutstanding || 0); }, 0);

  var headers = [
    'File Number', 'Lead ID', 'Customer', 'Financer',
    'Sanctioned Amount', 'Received', 'File Outstanding', 'Status',
    'Delivery Date', 'Days Since Delivery', 'Due By', 'Overdue', 'Last Payment Date'
  ];
  sheet.clear();
  sheet.getRange(1, 1).setValue(
    'Finance Pending — open files awaiting financer payment (SLA: ' + sla + ' days after delivery)'
  ).setFontWeight('bold').setFontSize(12);
  sheet.getRange(2, 1).setValue(
    'Refreshed: ' + nowDateTime_() +
    ' | Pending: ' + pending.length +
    ' | Overdue: ' + overdueCount +
    ' | Total Outstanding: ₹' + Math.round(totalOs).toLocaleString('en-IN')
  );
  sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#FFF3E0');
  sheet.setFrozenRows(3);

  var ss2     = getSpreadsheet_();
  var lrSheet = ss2.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  var lrGid   = lrSheet ? lrSheet.getSheetId() : null;
  var ssId    = ss2.getId();

  if (pending.length) {
    pending.sort(function (a, b) {
      if (a.overdue !== b.overdue) return a.overdue ? -1 : 1;
      return Number(b.daysSinceDelivery || 0) - Number(a.daysSinceDelivery || 0);
    });

    var startRow = 4;
    for (var i = 0; i < pending.length; i++) {
      var f = pending[i];
      var rowNum = startRow + i;
      var rowData = [
        f.fileNumber,
        f.leadId,       // placeholder; replaced by HYPERLINK below
        f.customerName,
        f.financer,
        f.sanctionedAmount,
        f.receivedAgainstFile,
        f.fileOutstanding,
        f.status,
        f.deliveryDate || '',
        f.daysSinceDelivery === '' ? '' : f.daysSinceDelivery,
        f.dueBy || '',
        f.overdue ? 'Yes' : (f.deliveryDate ? 'No' : 'Not delivered'),
        f.lastPaymentDate
      ];
      sheet.getRange(rowNum, 1, 1, headers.length).setValues([rowData]);

      // Write Lead ID as clickable backlink to Lead Register row.
      var leadId  = String(f.leadId || '').trim();
      var leadRef = null;
      try { leadRef = findLeadById_(leadId); } catch (ex) {}
      var anchor  = (leadRef && leadRef.row) ? 'A' + leadRef.row : 'A1';
      if (lrGid !== null && leadId) {
        var url     = 'https://docs.google.com/spreadsheets/d/' + ssId +
                      '/edit#gid=' + lrGid + '&range=' + anchor;
        var formula = '=HYPERLINK("' + url + '","' + leadId.replace(/"/g, '') + '")';
        sheet.getRange(rowNum, 2).setFormula(formula);
      }

      if (f.overdue) {
        sheet.getRange(rowNum, 1, 1, headers.length).setBackground('#FFCDD2');
      }
    }
    sheet.getRange(startRow, 5, pending.length, 3).setNumberFormat('#,##0.00');

    // ── Bifurcation by Financer ──────────────────────────────────────────
    var bifurStartRow = startRow + pending.length + 2;
    sheet.getRange(bifurStartRow, 1).setValue('OUTSTANDING BY FINANCER')
      .setFontWeight('bold').setBackground('#E3F2FD');
    sheet.getRange(bifurStartRow, 1, 1, 4).setBackground('#E3F2FD');

    var bifurHeaders = ['Financer', 'Files Pending', 'Total Sanctioned', 'Total Outstanding'];
    sheet.getRange(bifurStartRow + 1, 1, 1, 4).setValues([bifurHeaders]).setFontWeight('bold');

    var byFinancer = {};
    pending.forEach(function (f) {
      var fin = String(f.financer || 'Unknown').trim();
      if (!byFinancer[fin]) byFinancer[fin] = { count: 0, sanctioned: 0, outstanding: 0 };
      byFinancer[fin].count++;
      byFinancer[fin].sanctioned  += Number(f.sanctionedAmount  || 0);
      byFinancer[fin].outstanding += Number(f.fileOutstanding   || 0);
    });

    var bifurRows = Object.keys(byFinancer).sort().map(function (fin) {
      return [fin, byFinancer[fin].count, byFinancer[fin].sanctioned, byFinancer[fin].outstanding];
    });
    if (bifurRows.length) {
      sheet.getRange(bifurStartRow + 2, 1, bifurRows.length, 4).setValues(bifurRows);
      sheet.getRange(bifurStartRow + 2, 3, bifurRows.length, 2).setNumberFormat('#,##0.00');
      // Totals row
      var bifurTotalRow = bifurStartRow + 2 + bifurRows.length;
      sheet.getRange(bifurTotalRow, 1).setValue('TOTAL').setFontWeight('bold');
      sheet.getRange(bifurTotalRow, 2).setValue(pending.length).setFontWeight('bold');
      sheet.getRange(bifurTotalRow, 4).setValue(totalOs).setFontWeight('bold').setNumberFormat('#,##0.00');
    }
  } else {
    sheet.getRange(4, 1).setValue('No pending finance files.');
  }

  try { refreshFinanceOverdueView_(); } catch (e) {}
  return { rows: pending.length, overdue: overdueCount, totalOutstanding: totalOs, slaDays: sla, gid: sheet.getSheetId() };
}

function getFinanceReceiptSlaDays_() {
  var n = Number((CRM.FINANCE_REGISTER && CRM.FINANCE_REGISTER.RECEIPT_SLA_DAYS) || 2);
  if (!isFinite(n) || n < 1) n = 2;
  return Math.floor(n);
}

function addCalendarDaysIso_(isoDate, days) {
  var d = formatDate_(isoDate);
  if (!d) return '';
  var parts = d.split('-');
  if (parts.length < 3) return '';
  var dt = new Date(Number(parts[0]), Number(parts[1]) - 1, Number(parts[2]));
  if (isNaN(dt.getTime())) return '';
  dt.setDate(dt.getDate() + Number(days || 0));
  return Utilities.formatDate(dt, Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

function daysSinceIso_(fromIso, toIso) {
  var a = formatDate_(fromIso);
  var b = formatDate_(toIso) || nowDate_();
  if (!a || !b) return '';
  var da = new Date(a + 'T00:00:00');
  var db = new Date(b + 'T00:00:00');
  if (isNaN(da.getTime()) || isNaN(db.getTime())) return '';
  return Math.round((db - da) / 86400000);
}

function enrichFinanceFilesWithDelivery_(files) {
  var sla   = getFinanceReceiptSlaDays_();
  var today = nowDate_();
  var store = null;
  try { store = loadCrmStore_(true); } catch (e) {}

  return (files || []).map(function (f) {
    var out = {};
    Object.keys(f).forEach(function (k) { out[k] = f[k]; });
    var leadId       = String(f.leadId || '').trim();
    var deliveryDate = '';
    var lead         = null;
    if (store && leadId) {
      lead = store.leads.byId[leadId];
      var del = store.deliveryByLead && store.deliveryByLead[leadId];
      if (del && del.deliveryDate) deliveryDate = formatDate_(del.deliveryDate) || '';
    }
    if (!deliveryDate && lead) {
      deliveryDate = formatDate_(lead.deliveryDate) || '';
    }
    out.deliveryDate = deliveryDate;
    if (deliveryDate) {
      var days = daysSinceIso_(deliveryDate, today);
      out.daysSinceDelivery = (typeof days === 'number') ? days : '';
      out.dueBy  = addCalendarDaysIso_(deliveryDate, sla);
      out.overdue = (typeof days === 'number') && days > sla;
    } else {
      out.daysSinceDelivery = '';
      out.dueBy  = '';
      out.overdue = false;
    }
    return out;
  });
}

function listFinanceOverdueFiles_() {
  return enrichFinanceFilesWithDelivery_(listPendingFinanceFiles_()).filter(function (f) {
    return !!f.overdue;
  });
}

function refreshFinanceOverdueView_() {
  try {
    var ss    = getSpreadsheet_();
    var name  = CRM.SHEETS.FINANCE_OVERDUE || 'Finance Overdue';
    var sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);

    var overdue = listFinanceOverdueFiles_();
    var headers = [
      'File Number', 'Lead ID', 'Customer', 'Financer',
      'Sanctioned Amount', 'File Outstanding', 'Status',
      'Delivery Date', 'Days Since Delivery', 'Due By'
    ];

    sheet.clear();
    sheet.getRange(1, 1).setValue(
      'Finance Overdue — files past ' + getFinanceReceiptSlaDays_() + '-day SLA'
    ).setFontWeight('bold').setFontSize(12);
    sheet.getRange(2, 1).setValue('Refreshed: ' + nowDateTime_() + ' | Overdue: ' + overdue.length);
    sheet.getRange(3, 1, 1, headers.length).setValues([headers]).setFontWeight('bold').setBackground('#FFCDD2');
    sheet.setFrozenRows(3);

    var lrSheet = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    var lrGid   = lrSheet ? lrSheet.getSheetId() : null;
    var ssId    = ss.getId();

    if (overdue.length) {
      var startRow = 4;
      for (var i = 0; i < overdue.length; i++) {
        var f = overdue[i];
        var rowNum = startRow + i;
        sheet.getRange(rowNum, 1, 1, headers.length).setValues([[
          f.fileNumber, f.leadId, f.customerName, f.financer,
          f.sanctionedAmount, f.fileOutstanding, f.status,
          f.deliveryDate, f.daysSinceDelivery, f.dueBy
        ]]);
        // Clickable Lead ID backlink
        var leadId  = String(f.leadId || '').trim();
        var leadRef = null;
        try { leadRef = findLeadById_(leadId); } catch (ex) {}
        var anchor = (leadRef && leadRef.row) ? 'A' + leadRef.row : 'A1';
        if (lrGid !== null && leadId) {
          var url     = 'https://docs.google.com/spreadsheets/d/' + ssId +
                        '/edit#gid=' + lrGid + '&range=' + anchor;
          var formula = '=HYPERLINK("' + url + '","' + leadId.replace(/"/g, '') + '")';
          sheet.getRange(rowNum, 2).setFormula(formula);
        }
        sheet.getRange(rowNum, 1, 1, headers.length).setBackground('#FFCDD2');
      }
      sheet.getRange(startRow, 5, overdue.length, 2).setNumberFormat('#,##0.00');
    } else {
      sheet.getRange(4, 1).setValue('No overdue finance files. ✔');
    }
    return { gid: sheet.getSheetId(), count: overdue.length };
  } catch (e) {
    Logger.log('refreshFinanceOverdueView_: ' + e.message);
    return null;
  }
}

/** Rebuild Finance Register from Payment Ledger (Finance mode) + finance leads. */
function rebuildFinanceRegisterFromLedger_() {
  ensureFinanceRegisterSheet_();
  var created = 0;
  var updated = 0;
  var seen = {};

  function upsertFromLedger_(entry) {
    if (!entry || !entry.leadId) return;
    var fileNumber = String(entry.fileNumber || '').trim();
    if (!fileNumber) {
      try { fileNumber = resolveFinanceFileNumberForLead_(entry.leadId, ''); } catch (e) {}
    }
    if (!fileNumber) return;
    if (seen[fileNumber]) return;
    seen[fileNumber] = true;
    var sheet = ensureFinanceRegisterSheet_();
    var headers = getHeaders_(sheet, 1);
    var existed = findFinanceRowByFile_(sheet, headers, fileNumber) > 0;
    upsertFinanceFilePayment_({
      leadId: entry.leadId,
      customerName: entry.customerName || '',
      financer: entry.financer || '',
      fileNumber: fileNumber,
      amount: entry.sanctioned,
      payDate: entry.payDate || '',
      sanctionedAmount: entry.sanctioned,
      isReceipt: false
    });
    if (existed) updated++; else created++;
  }

  try {
    var paySheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
    if (paySheet && paySheet.getLastRow() >= CRM.PAYMENT.DATA_START) {
      var payHeaders = getHeaders_(paySheet, CRM.PAYMENT.HEADER_ROW);
      var payData = paySheet.getRange(CRM.PAYMENT.DATA_START, 1, paySheet.getLastRow(), payHeaders.length).getValues();
      var byFile = {};
      payData.forEach(function (row) {
        var mode = String(rowVal_(row, payHeaders, 'Payment Mode') || '').trim();
        if (matchMasterValue_(mode, ['Finance']) !== 'Finance') return;
        var leadId = String(rowVal_(row, payHeaders, 'Lead ID') || '').trim();
        var amt = Number(rowVal_(row, payHeaders, 'Amount')) || 0;
        if (!leadId || !(amt > 0)) return;
        var fileNumber = String(rowVal_(row, payHeaders, 'Finance File Number') || '').trim();
        var financer = String(rowVal_(row, payHeaders, 'Financer Name') || '').trim();
        var payDate = formatDate_(rowVal_(row, payHeaders, 'Date')) || '';
        var customer = String(rowVal_(row, payHeaders, 'Customer Name') || '').trim();
        var key = fileNumber || leadId;
        if (!byFile[key]) {
          byFile[key] = { leadId: leadId, fileNumber: fileNumber, financer: financer,
            customerName: customer, sanctioned: 0, payDate: payDate };
        }
        byFile[key].sanctioned = Math.max(byFile[key].sanctioned, amt);
        if (fileNumber) byFile[key].fileNumber = fileNumber;
        if (financer) byFile[key].financer = financer;
        if (customer) byFile[key].customerName = customer;
        if (payDate && (!byFile[key].payDate || payDate > byFile[key].payDate)) {
          byFile[key].payDate = payDate;
        }
      });
      Object.keys(byFile).forEach(function (k) { upsertFromLedger_(byFile[k]); });
    }
  } catch (e1) {
    Logger.log('rebuildFinanceRegisterFromLedger_ ledger: ' + e1.message);
  }

  try {
    var lrSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    if (lrSheet && lrSheet.getLastRow() >= CRM.LEAD.DATA_START) {
      var lrHeaders = getHeaders_(lrSheet, CRM.LEAD.HEADER_ROW);
      var lrData = lrSheet.getRange(CRM.LEAD.DATA_START, 1, lrSheet.getLastRow(), lrHeaders.length).getValues();
      lrData.forEach(function (row) {
        var finReq = String(rowVal_(row, lrHeaders, 'Finance Required') || '').toLowerCase();
        if (finReq !== 'yes') return;
        var leadId = String(rowVal_(row, lrHeaders, 'Lead ID') || '').trim();
        if (!leadId) return;
        upsertFromLedger_({
          leadId: leadId,
          fileNumber: String(rowVal_(row, lrHeaders, 'Finance File Number') || '').trim(),
          financer: String(rowVal_(row, lrHeaders, 'Financer Name') || '').trim(),
          customerName: String(rowVal_(row, lrHeaders, 'Customer Name') || '').trim(),
          sanctioned: Number(rowVal_(row, lrHeaders, 'Outstanding Amount') || 0),
          payDate: ''
        });
      });
    }
  } catch (e2) {
    Logger.log('rebuildFinanceRegisterFromLedger_ leads: ' + e2.message);
  }

  return { created: created, updated: updated, total: Object.keys(seen).length };
}

/** Auto-rebuild when register is empty but ledger has finance payments. */
function ensureFinanceRegisterSynced_() {
  try {
    if (readAllFinanceFiles_().length > 0) {
      return { synced: false, reason: 'register_has_data' };
    }
    var paySheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
    if (!paySheet || paySheet.getLastRow() < CRM.PAYMENT.DATA_START) {
      return { synced: false, reason: 'no_finance_payments' };
    }
    var payHeaders = getHeaders_(paySheet, CRM.PAYMENT.HEADER_ROW);
    var payData = paySheet.getRange(CRM.PAYMENT.DATA_START, 1, paySheet.getLastRow(), payHeaders.length).getValues();
    var hasFinance = payData.some(function (row) {
      return matchMasterValue_(String(rowVal_(row, payHeaders, 'Payment Mode') || ''), ['Finance']) === 'Finance';
    });
    if (!hasFinance) return { synced: false, reason: 'no_finance_payments' };
    return rebuildFinanceRegisterFromLedger_();
  } catch (e) {
    Logger.log('ensureFinanceRegisterSynced_: ' + e.message);
    return { synced: false, error: e.message };
  }
}

/** Menu — rebuild Finance Register from Payment Ledger. */
function menuRebuildFinanceRegister() {
  try {
    var res = rebuildFinanceRegisterFromLedger_();
    if (typeof refreshFinancePendingView_ === 'function') refreshFinancePendingView_();
    SpreadsheetApp.getUi().alert(
      'Finance Register rebuilt',
      'Created: ' + (res.created || 0) + ' | Updated: ' + (res.updated || 0) +
      ' | Total: ' + (res.total || 0),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Rebuild failed: ' + e.message);
  }
}

/** PUBLIC: total outstanding across all pending finance files (for dashboard). */
function getTotalFinanceOutstanding_() {
  try {
    return listPendingFinanceFiles_().reduce(function (s, f) {
      return s + Number(f.fileOutstanding || 0);
    }, 0);
  } catch (e) {
    return 0;
  }
}

/** Per-lead open finance file outstanding (sum if multiple files on same lead). */
function getFinanceOutstandingMapByLead_() {
  var map = {};
  try {
    listPendingFinanceFiles_().forEach(function (f) {
      var id = String(f.leadId || '').trim();
      if (!id) return;
      var os = Number(f.fileOutstanding || 0);
      if (os <= 0.01) return;
      map[id] = round2_((map[id] || 0) + os);
    });
  } catch (e) {
    Logger.log('getFinanceOutstandingMapByLead_: ' + e.message);
  }
  return map;
}

function getFinanceOutstandingForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return 0;
  var map = getFinanceOutstandingMapByLead_();
  return Number(map[leadId] || 0);
}

/** PUBLIC menu handler — refresh Finance Pending and navigate to it. */
function menuRefreshFinancePending() {
  try {
    if (typeof ensureFinanceRegisterSynced_ === 'function') ensureFinanceRegisterSynced_();
    refreshFinancePendingView_();
    var ss    = getSpreadsheet_();
    var sheet = ss.getSheetByName(CRM.SHEETS.FINANCE_PENDING || 'Finance Pending');
    if (sheet) ss.setActiveSheet(sheet);
    SpreadsheetApp.getUi().alert('Finance Pending refreshed.');
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

/** PUBLIC menu handler — open Finance Overdue sheet. */
function menuOpenFinanceOverdue() {
  try {
    refreshFinanceOverdueView_();
    var ss    = getSpreadsheet_();
    var sheet = ss.getSheetByName(CRM.SHEETS.FINANCE_OVERDUE || 'Finance Overdue');
    if (sheet) ss.setActiveSheet(sheet);
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

/** Block manual edits to File Outstanding (system-calculated: Sanctioned − Received). */
function handleFinanceRegisterEdit_(e) {
  if (!e || !e.range) return;
  var row = e.range.getRow();
  if (row < 2) return;
  var sheet = e.range.getSheet();
  var headers = getHeaders_(sheet, 1);
  var col = e.range.getColumn();
  var colName = headers[col - 1];
  if (colName !== 'File Outstanding') return;
  if (e.oldValue !== undefined) {
    sheet.getRange(row, col).setValue(e.oldValue);
  } else {
    sheet.getRange(row, col).setValue('');
  }
  try {
    SpreadsheetApp.getUi().alert(
      'Outstanding is Read Only',
      'File Outstanding is system-calculated (Sanctioned − Received) and cannot be edited.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (uiErr) {}
}
