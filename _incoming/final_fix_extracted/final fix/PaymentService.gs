/**
 * PaymentService.gs  — Euler Motors Dealership CRM v2.1
 *
 * Changes from v2.0:
 *   ✔ Duplicate-entry guard: second save of the same payment within 90 seconds
 *     returns the already-saved receipt instead of writing a new row.
 *   ✔ Dialog lifecycle: success returns immediately after durable commit.
 *     Dashboard / full sync / counter sync run via deferred trigger (and the
 *     client kickDeferredCrmRefresh fire-and-forget). Never block "Saving…".
 *   ✔ Payment Ledger writes use setValueSafe_() (via updateLeadRegisterFields_)
 *     so Finance Required / Financer Name / Outstanding are always saved.
 */

// ═══════════════════════════════════════════════════════════════════════════
//  SCHEMA
// ═══════════════════════════════════════════════════════════════════════════

function ensurePaymentLedgerSchema_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
  if (!sheet) return;
  var headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
  var required = CRM.PAYMENT.COLS || [];
  required.forEach(function (c) {
    if (findHeaderIndex_(headers, c) < 0) {
      sheet.getRange(CRM.PAYMENT.HEADER_ROW, headers.length + 1).setValue(c).setFontWeight('bold');
      headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
    }
  });
}

/** Lightweight step timer for payment lifecycle profiling (Logger only). */
function payProfileMark_(profile, label) {
  profile = profile || { t0: Date.now(), steps: [] };
  var now = Date.now();
  var prev = profile._last || profile.t0;
  profile.steps.push({ label: label, ms: now - prev, at: now - profile.t0 });
  profile._last = now;
  return profile;
}

function payProfileSummary_(profile) {
  if (!profile || !profile.steps) return '';
  return profile.steps.map(function (s) {
    return s.label + '=' + s.ms + 'ms';
  }).join(' | ') + ' | total=' + (Date.now() - profile.t0) + 'ms';
}

// ═══════════════════════════════════════════════════════════════════════════
//  DUPLICATE-ENTRY GUARD
//  Stores a fingerprint (leadId + amount + date) in ScriptProperties with a
//  90-second TTL. A second addPayment_ call with the same fingerprint within
//  that window returns the first receipt instead of creating a duplicate row.
// ═══════════════════════════════════════════════════════════════════════════

var PAY_IDEM_PREFIX_ = 'pay_idem_';
var PAY_IDEM_TTL_MS_ = 90 * 1000; // 90 seconds

function payGetIdemKey_(leadId, amount, date) {
  return PAY_IDEM_PREFIX_ + String(leadId) + '_' + String(amount) + '_' + String(date || '').replace(/[^0-9]/g, '');
}

function payCheckIdem_(key) {
  try {
    var props = PropertiesService.getScriptProperties();
    var raw   = props.getProperty(key);
    if (!raw) return null;
    var saved = JSON.parse(raw);
    if (Date.now() - saved.ts < PAY_IDEM_TTL_MS_) return saved; // still valid
    props.deleteProperty(key);                                    // expired
  } catch (e) {}
  return null;
}

function payStoreIdem_(key, receiptNo, leadId) {
  try {
    PropertiesService.getScriptProperties().setProperty(key, JSON.stringify({
      receiptNo: receiptNo, leadId: leadId, ts: Date.now()
    }));
  } catch (e) {}
}

function payDeleteIdem_(key) {
  try { PropertiesService.getScriptProperties().deleteProperty(key); } catch (e) {}
}

// ═══════════════════════════════════════════════════════════════════════════
//  CORE SAVE
// ═══════════════════════════════════════════════════════════════════════════

function addPayment_(data) {
  var profile = payProfileMark_({ t0: Date.now(), steps: [], _last: Date.now() }, 'start');
  var postCtx = {
    module: 'Payment',
    action: 'Payment Saved',
    auditAction: 'ADD_PAYMENT',
    auditDetail: '',
    perfOp: 'payment',
    sheets: [CRM.SHEETS.PAYMENT_LEDGER, CRM.SHEETS.LEAD_REGISTER],
    reason: 'payment',
    dashboard: true
  };
  return runCriticalBusinessTransaction_({
    module: 'Payment',
    action: 'addPayment_',
    successMessage: 'Payment saved successfully',
    context: postCtx,
    commitFn: function (setStep) {
      var lock = LockService.getDocumentLock();
      var locked = false;
      var receiptNo = '';
      var leadId = '';
      var amt = 0;
      var payDate = '';
      var idemKey = '';

      try {
        setStep('lock');
        // If the caller already holds the document lock (e.g. the booking flow
        // recording its advance payment), DO NOT try to re-acquire it. Apps Script
        // document locks are not re-entrant, so a nested tryLock(10000) blocks for
        // the full 10 seconds every time before proceeding — this was ~10s of dead
        // wait on every booking that has an advance amount.
        if (data.skipLock) {
          locked = false; // caller owns the lock; we neither acquire nor release
        } else {
          locked = lock.tryLock(10000);
          if (!locked) throw businessError_('Payment save is busy. Please retry.', 'LOCK_BUSY');
        }
        payProfileMark_(profile, 'Lock');

        setStep('validate');
        leadId = String(data.leadId || '').trim();
        postCtx.leadId = leadId;
        requireField_(leadId, 'Lead ID', 'Select a lead before saving payment.');
        var store = loadCrmStore_();
        var lead = store.leads.byId[leadId];
        if (!lead) throw fieldError_('Lead ID', 'No lead found with ID ' + leadId + '.', 'NOT_FOUND');
        requireActiveLead_(leadId);

        var paymentMode = String(data.paymentMode || 'Cash').trim();
        var financerName = String(data.financerName || '').trim();
        var fileNumber = String(data.financeFileNumber || data.fileNumber || '').trim();
        var isFinance = paymentMode.toLowerCase() === 'finance';
        if (isFinance) {
          requireField_(financerName, 'Financer Name', 'Required when Payment Mode is Finance.');
          fileNumber = resolveFinanceFileNumberForLead_(leadId, fileNumber);
        }

        amt     = Number(data.amount) || 0;
        payDate = formatDate_(data.date) || nowDate_();

        // ── Duplicate-entry guard ──────────────────────────────────────
        idemKey = payGetIdemKey_(leadId, amt, payDate);
        var existing = payCheckIdem_(idemKey);
        if (existing) {
          Logger.log('addPayment_: idempotent return for ' + idemKey);
          payProfileMark_(profile, 'IdempotentHit');
          Logger.log('PAY_PROFILE ' + payProfileSummary_(profile));
          return {
            receiptNo:         existing.receiptNo,
            leadId:            leadId,
            amount:            amt,
            financeFileNumber: isFinance ? fileNumber : '',
            financerName:      isFinance ? financerName : '',
            warning:           'Duplicate save detected — original receipt returned.',
            profile:           payProfileSummary_(profile)
          };
        }
        payProfileMark_(profile, 'Validation');

        setStep('generateId');
        ensurePaymentLedgerSchema_();
        var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
        if (!sheet) throw businessError_('Payment Ledger not found', 'MISSING_SHEET');
        receiptNo  = generateId_('receipt');
        var paymentId = generateId_('payment');
        var payCalc   = validatePaymentAmount_(leadId, amt, store, {
          allowProvisional: !!data.allowProvisional || !!data.skipPayableCheck ||
            /booking\s*advance/i.test(String(data.narration || ''))
        });
        var running   = payCalc.running;
        var outstanding = Math.max(0, payCalc.outstanding);
        payProfileMark_(profile, 'Id+AmountValidate');

        setStep('write');
        var headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
        var newRow  = Math.max(sheet.getLastRow() + 1, CRM.PAYMENT.DATA_START);
        var hasFinCols = findHeaderIndex_(headers, 'Financer Name') >= 0;

        if (hasFinCols) {
          var rowMap = {
            'Receipt Number':     receiptNo,
            'Lead ID':            leadId,
            'Customer Name':      lead.customerName,
            'Date':               payDate,
            'Amount':             amt,
            'Payment Mode':       paymentMode,
            'Financer Name':      isFinance ? financerName : '',
            'Finance File Number': isFinance ? fileNumber : '',
            'Narration':          data.narration || '',
            'Running Total':      running,
            'Outstanding Balance': outstanding,
            'Payment ID':         paymentId
          };
          Object.keys(rowMap).forEach(function (name) {
            var col = findHeaderIndex_(headers, name) + 1;
            if (col < 1) return;
            if (name === 'Lead ID' && typeof writeLeadIdBacklink_ === 'function') {
              writeLeadIdBacklink_(sheet, newRow, col, leadId);
            } else {
              sheet.getRange(newRow, col).setValue(rowMap[name]);
            }
          });
        } else {
          writeSheetRow_(sheet, newRow, [
            receiptNo, leadId, lead.customerName, payDate, amt,
            paymentMode, data.narration || '', running, outstanding, paymentId
          ]);
          var leadIdColPlain = findHeaderIndex_(headers, 'Lead ID') + 1;
          if (leadIdColPlain > 0 && typeof writeLeadIdBacklink_ === 'function') {
            writeLeadIdBacklink_(sheet, newRow, leadIdColPlain, leadId);
          }
        }
        SpreadsheetApp.flush();
        // ★ DURABILITY POINT — ledger row is committed and flushed.
        payStoreIdem_(idemKey, receiptNo, leadId);
        payProfileMark_(profile, 'LedgerWrite+Flush(DURABLE)');

        setStep('updateLead');
        // Reuse the store already loaded at the top of this function. The ledger
        // append we just made doesn't change any snapshot-derived field, and every
        // payment-dependent number (outstanding, running, mode) is overridden
        // locally below — so the invalidate + reload that used to sit here was a
        // full-workbook read for nothing. We invalidate AFTER the writes so the
        // deferred worker rebuilds fresh.
        if (typeof buildLeadCommercialTruthFields_ !== 'function') {
          throw businessError_(
            'CRM Utils.gs is outdated — missing buildLeadCommercialTruthFields_. Copy Utils.gs from final fix, Save, reload, retry.',
            'MISSING_MODULE'
          );
        }
        var truth = buildLeadCommercialTruthFields_(leadId, store);
        // Customer OS from this payment; Total Outstanding keeps finance OS (do not wipe it).
        var financeOsNow = typeof getFinanceOutstandingForLead_ === 'function'
          ? num_(getFinanceOutstandingForLead_(leadId)) : 0;
        truth['Customer Outstanding'] = outstanding;
        truth['Outstanding Amount']   = round2_(outstanding + financeOsNow);
        truth['Final Outstanding']    = truth['Outstanding Amount'];
        truth['Last Payment Mode']    = paymentMode;
        truth['Total Received']       = running;
        truth['Last Updated']         = nowDateTime_();
        truth['Last Updated By']      = getUserEmail_();
        if (isFinance) {
          truth['Finance Required']      = 'Yes';
          truth['Financer Name']         = financerName;
          truth['Finance File Number']   = fileNumber;
        }
        updateLeadRegisterFields_(leadId, truth);
        invalidateCrmStore_(); // worker's next load sees the new ledger row + lead fields
        payProfileMark_(profile, 'LeadOutstandingUpdate');

        if (isFinance && !data.skipFinanceUpsert) {
          // Finance file upsert is cold-path work (it reads/writes the Finance
          // Register and its views). Running it inside the payment lock is what
          // made Finance-mode payments slow enough to trip the client watchdog,
          // even though the ledger row was already durable. Queue it instead.
          setStep('finance');
          postCtx.financeUpsert = {
            leadId: leadId, customerName: lead.customerName, financer: financerName,
            fileNumber: fileNumber, amount: amt, payDate: payDate,
            sanctionedAmount: Number(data.sanctionedAmount || amt), isReceipt: false
          };
        }
        if (isFinance && typeof syncFinanceFlagAcrossTabs_ === 'function') {
          syncFinanceFlagAcrossTabs_(leadId, {
            financeRequired:   'Yes',
            financerName:      financerName,
            financeFileNumber: fileNumber,
            paymentMode:       paymentMode
          });
          payProfileMark_(profile, 'FinanceFlagSync');
        }

        postCtx.auditDetail = receiptNo + ' - ' + amt + ' on ' + payDate + ' for ' + leadId;
        postCtx.message = receiptNo + ' amount=' + amt;
        appendRelationshipPayment_(leadId, paymentId);
        payProfileMark_(profile, 'RelationshipPaymentAppend');

        Logger.log('PAY_PROFILE ' + payProfileSummary_(profile));
        return {
          receiptNo:         receiptNo,
          leadId:            leadId,
          amount:            amt,
          financeFileNumber: isFinance ? fileNumber : '',
          financerName:      isFinance ? financerName : '',
          financeUpsert:     postCtx.financeUpsert || null,
          warning:           null,
          profile:           payProfileSummary_(profile)
        };
      } finally {
        if (locked) lock.releaseLock();
      }
    },
    // Lightweight post-tasks only — never SYNC_COMPUTED / dashboard here.
    // When called as a nested advance inside a booking (data.skipLock), skip these
    // entirely: the booking transaction already runs its own invalidate/audit/log,
    // so repeating them here was 4 redundant sheet/property writes per booking.
    postTasks: data.skipLock ? [] : [
      POST_TX.INVALIDATE_STORE,
      POST_TX.AUDIT,
      POST_TX.TRANSACTION_OK,
      POST_TX.PERF
    ]
  });
}

// ═══════════════════════════════════════════════════════════════════════════
//  EDIT HANDLER
// ═══════════════════════════════════════════════════════════════════════════

function handlePaymentLedgerEdit_(e) {
  if (!e || !e.range) return;
  var row = e.range.getRow();
  if (row < CRM.PAYMENT.DATA_START) return;
  var sheet   = e.range.getSheet();
  var headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
  var col     = e.range.getColumn();
  var colName = headers[col - 1];
  var receiptCol = findHeaderIndex_(headers, 'Receipt Number') + 1;
  var dateCol    = findHeaderIndex_(headers, 'Date') + 1;

  // Outstanding Balance is system-calculated — never manually editable.
  if (colName === 'Outstanding Balance' || colName === 'Running Total') {
    if (e.oldValue !== undefined) {
      sheet.getRange(row, col).setValue(e.oldValue);
    } else {
      sheet.getRange(row, col).setValue('');
    }
    try {
      SpreadsheetApp.getUi().alert(
        'Outstanding is Read Only',
        'Outstanding Balance and Running Total are system-calculated and cannot be edited.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
    } catch (uiErr) {}
    return;
  }

  if (receiptCol > 0 && col === receiptCol && !e.value) {
    sheet.getRange(row, receiptCol).setValue(generateId_('receipt'));
    if (dateCol > 0) sheet.getRange(row, dateCol).setValue(nowDate_());
  }

  invalidateCrmStore_();
  queuePostTransaction_([POST_TX.SYNC_COMPUTED], { dashboard: true });
}

// ═══════════════════════════════════════════════════════════════════════════
//  BATCH IMPORT
// ═══════════════════════════════════════════════════════════════════════════

function getTotalPaymentsByLead_(store) {
  store = store || loadCrmStore_();
  return store.paymentsByLead || {};
}

function batchImportPayments_(payments, leadIdRemap) {
  var sheet    = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  var settings = getSettings_();
  var counter  = settings.nextReceiptCounter;
  leadIdRemap  = leadIdRemap || {};
  invalidateCrmStore_();
  var store    = loadCrmStore_();

  var rows = [];
  var runningByLead = Object.assign({}, store.paymentsByLead);

  payments.forEach(function (p) {
    var lid  = resolveLeadId_(p.leadId, leadIdRemap);
    var lead = store.leads.byId[lid];
    var amt  = Number(p.amount) || 0;
    runningByLead[lid] = (runningByLead[lid] || 0) + amt;
    var id  = settings.receiptPrefix + String(counter++).padStart(6, '0');
    var pid = generateId_('payment');
    rows.push([
      id, lid,
      lead ? lead.customerName : (p.customerName || ''),
      p.date || nowDate_(), amt,
      p.paymentMode || 'Cash', p.financerName || '', p.financeFileNumber || '', p.narration || '',
      runningByLead[lid],
      lead ? Math.max(0, getLeadDealAmount_(lead) - runningByLead[lid]) : 0,
      pid
    ]);
  });

  saveSetting_('nextReceiptCounter', counter);
  if (rows.length === 0) return 0;
  writeBatchData_(sheet, CRM.PAYMENT.DATA_START, rows);
  invalidateCrmStore_();
  return rows.length;
}

function getTotalRevenue_(monthStart, monthEnd) {
  return computeRevenue_(loadCrmStore_(), monthStart, monthEnd);
}

// ═══════════════════════════════════════════════════════════════════════════
//  PUBLIC DIALOG HANDLERS  (called via google.script.run)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Public dialog handler for Add Payment.
 * Critical path: validate → addPayment_ (ledger durable + lead OS).
 * Non-blocking: dashboard / full sync / counters via deferred trigger.
 * Client also calls kickDeferredCrmRefresh() after success (fire-and-forget).
 */
function addPaymentFromDialog(data) {
  var t0 = Date.now();
  try {
    var leadId = String(data.leadId || '').trim();
    if (!leadId) return crmFailStructured_('Payment', 'addPaymentFromDialog', 'validate',
      fieldError_('Lead ID', 'Select a lead before saving payment.', 'VALIDATION'), 0);

    var amt = Number(data.amount);
    if (!amt || amt <= 0) return crmFailStructured_('Payment', 'addPaymentFromDialog', 'validate',
      fieldError_('Amount', 'Enter an amount greater than zero.', 'VALIDATION'), 0);

    if (!data.date) return crmFailStructured_('Payment', 'addPaymentFromDialog', 'validate',
      fieldError_('Payment Date', 'Select the payment date.', 'VALIDATION'), 0);

    requireActiveLead_(leadId);

    var result = addPayment_({
      leadId:            leadId,
      amount:            amt,
      date:              formatDate_(data.date),
      paymentMode:       data.paymentMode,
      financerName:      data.financerName,
      financeFileNumber: data.financeFileNumber || data.fileNumber,
      narration:         data.narration
    });

    // ★ SUCCESS RETURN PATH — do NOT call refreshCrmAfterDialogSave_() here.
    // That function runs refreshDashboard_() synchronously (~2–5s+) and was
    // keeping google.script.run blocked while the UI showed "Saving…", even
    // though the ledger row was already durable.
    try {
      scheduleDeferredCrmSync_({
        leadId: leadId,
        reason: 'payment',
        dashboard: true,
        // Finance file upsert moved off the save lock (see addPayment_); hand the
        // payload to the worker so the Finance Register still gets updated.
        financeUpsert: (result && result.data && result.data.financeUpsert) || null
      });
    } catch (schedErr) {
      Logger.log('addPaymentFromDialog scheduleDeferred: ' + schedErr.message);
    }

    var dialogMs = Date.now() - t0;
    Logger.log('PAY_DIALOG_RETURN ms=' + dialogMs +
      ' | commitProfile=' + ((result && result.data && result.data.profile) || (result && result.profile) || ''));
    return result;
  } catch (e) {
    return crmFailStructured_('Payment', 'addPaymentFromDialog', 'handler', e, Date.now() - t0);
  }
}

/**
 * Public dialog handler: record MULTIPLE payments for one lead in a single save.
 * Use case: a down payment split across modes (e.g. part Cash, part UPI) plus a
 * Finance disbursement — all captured at once instead of clicking Record Payment
 * several times.
 *
 * data = { leadId, date, payments: [ {amount, paymentMode, financerName?, narration?}, ... ] }
 *
 * All rows are written under ONE document lock (each addPayment_ call passes
 * skipLock:true so it doesn't re-acquire), the ledger stays consistent, and the
 * dashboard is refreshed once at the end.
 */
function addPaymentsBatchFromDialog(data) {
  var t0 = Date.now();
  try {
    var leadId = String(data.leadId || '').trim();
    if (!leadId) return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'validate',
      fieldError_('Lead ID', 'Select a lead before saving payment.', 'VALIDATION'), 0);
    if (!data.date) return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'validate',
      fieldError_('Payment Date', 'Select the payment date.', 'VALIDATION'), 0);

    var rows = (data.payments || []).filter(function (p) { return Number(p.amount) > 0; });
    if (!rows.length) return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'validate',
      fieldError_('Amount', 'Enter at least one payment amount greater than zero.', 'VALIDATION'), 0);

    // Validate finance rows have a financer BEFORE writing anything.
    for (var i = 0; i < rows.length; i++) {
      if (String(rows[i].paymentMode || '').toLowerCase() === 'finance' &&
          !String(rows[i].financerName || '').trim()) {
        return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'validate',
          fieldError_('Financer Name', 'Financer is required for a Finance payment (row ' + (i + 1) + ').', 'VALIDATION'), 0);
      }
    }

    requireActiveLead_(leadId);

    var lock = LockService.getDocumentLock();
    var locked = lock.tryLock(15000);
    if (!locked) return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'lock',
      businessError_('Payment save is busy. Please retry.', 'LOCK_BUSY'), 0);

    var receipts = [];
    var financeJobs = [];
    try {
      rows.forEach(function (p) {
        var res = addPayment_({
          leadId:            leadId,
          amount:            Number(p.amount),
          date:              formatDate_(data.date),
          paymentMode:       p.paymentMode,
          financerName:      p.financerName,
          financeFileNumber: p.financeFileNumber || p.fileNumber,
          narration:         p.narration,
          skipLock:          true   // batch holds the lock
        });
        if (res && res.data && res.data.receiptNo) receipts.push(res.data.receiptNo);
        if (res && res.data && res.data.financeUpsert) financeJobs.push(res.data.financeUpsert);
      });
    } finally {
      lock.releaseLock();
    }

    try {
      scheduleDeferredCrmSync_({
        leadId: leadId, reason: 'payment', dashboard: true,
        financeUpsert: financeJobs.length ? financeJobs[financeJobs.length - 1] : null
      });
    } catch (schedErr) {
      Logger.log('addPaymentsBatchFromDialog scheduleDeferred: ' + schedErr.message);
    }

    return crmOk_('Recorded ' + rows.length + ' payment(s).',
      { leadId: leadId, receipts: receipts, count: rows.length }, Date.now() - t0,
      { module: 'Payment', function: 'addPaymentsBatchFromDialog' });
  } catch (e) {
    return crmFailStructured_('Payment', 'addPaymentsBatchFromDialog', 'handler', e, Date.now() - t0);
  }
}

/**
 * Public dialog handler for Record Financer Receipt.
 * Returns after durable finance write; dashboard refresh is deferred.
 */
// recordFinanceFileReceiptFromDialog lives in FinanceService.gs (single definition).

/**
 * Backfill Payment Ledger for booked leads that have Booking Amount but no
 * matching payment row. Also refreshes Outstanding from Price Master / snapshot.
 * Fixes the slim-booking bug where advance was rejected when payable was ₹0.
 */
function repairMissingBookingPayments_() {
  var store = loadCrmStore_(true);
  var fixed = 0;
  var skipped = 0;
  var errors = [];
  var osSynced = 0;

  Object.keys(store.leads.byId || {}).forEach(function (id) {
    var lead = store.leads.byId[id];
    var bookingAmt = num_(lead.bookingAmount);
    if (bookingAmt <= 0) return;
    var status = normalizeStatus_(lead.currentStatus);
    var hasBooking = status === 'Booked' || status === 'Delivered' ||
      !!String(lead.bookingDate || '').trim();
    if (!hasBooking) return;

    var paid = num_((store.paymentsByLead || {})[id]);
    if (paid + 0.01 >= bookingAmt) {
      skipped++;
    } else {
      var missing = round2_(bookingAmt - paid);
      try {
        addPayment_({
          leadId: id,
          amount: missing,
          date: formatDate_(lead.bookingDate) || nowDate_(),
          paymentMode: 'Cash',
          narration: 'Booking advance (backfill)',
          allowProvisional: true,
          skipFinanceUpsert: true
        });
        fixed++;
        try { invalidateCrmStore_(); } catch (inv) {}
        store = loadCrmStore_(true);
      } catch (pe) {
        errors.push(id + ': ' + ((pe && pe.message) || pe));
      }
    }

    try {
      if (typeof syncLeadCommercialEstimate_ === 'function') {
        syncLeadCommercialEstimate_(id, store);
        osSynced++;
      } else if (typeof syncLeadOutstandingForId_ === 'function') {
        syncLeadOutstandingForId_(id, store);
        osSynced++;
      }
    } catch (osErr) {
      errors.push(id + ' OS: ' + ((osErr && osErr.message) || osErr));
    }
  });

  try { invalidateCrmStore_(); } catch (eInv) {}
  try {
    scheduleDeferredCrmSync_({ reason: 'payment_backfill', dashboard: true });
  } catch (eSched) {}

  logAudit_('REPAIR_BOOKING_PAYMENTS',
    'fixed=' + fixed + ' skipped=' + skipped + ' osSynced=' + osSynced +
    (errors.length ? ' errors=' + errors.join('; ') : ''));

  return {
    fixed: fixed,
    skipped: skipped,
    osSynced: osSynced,
    errors: errors
  };
}

/** Menu — backfill booking advances missing from Payment Ledger. */
function menuRepairMissingBookingPayments() {
  var ui = SpreadsheetApp.getUi();
  var confirm = ui.alert(
    'Repair booking payments',
    'This will write missing Booking Amount rows into Payment Ledger and refresh Outstanding for booked leads.\n\nContinue?',
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return;
  try {
    var res = repairMissingBookingPayments_();
    var msg = 'Payment Ledger backfill done.\n\n' +
      'Added: ' + res.fixed + '\n' +
      'Already had payment: ' + res.skipped + '\n' +
      'Outstanding refreshed: ' + res.osSynced;
    if (res.errors && res.errors.length) {
      msg += '\n\nErrors:\n' + res.errors.slice(0, 8).join('\n');
    }
    ui.alert(msg);
  } catch (e) {
    ui.alert('Repair failed: ' + ((e && e.message) || e));
  }
}
