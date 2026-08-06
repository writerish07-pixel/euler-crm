/**
 * SyncEngine – writes all computed fields via batch operations.
 * No cross-sheet FILTER/INDEX formulas.
 */

/** Full sync: leads, activities, payments, delivery, dashboard. */
function syncAll_(options) {
  options = options || {};
  var syncStart = Date.now();
  var lock = LockService.getDocumentLock();
  var locked = false;
  try {
    locked = lock.tryLock(15000);
    if (!locked) throw new Error('Sync is busy. Please retry.');
    ensureLeadSchema_();
    syncComputedFields_(options);
    refreshAllDropdowns_();
    logAudit_('SYNC_ALL', 'Computed fields synchronized');
    recordPerf_('sync', Date.now() - syncStart);
  } catch (err) {
    logAudit_('SYNC_ERROR', err.message + '\n' + (err.stack || ''));
    throw err;
  } finally {
    if (locked) lock.releaseLock();
  }
}

/**
 * Full workbook refresh — every CRM tab / computed column / report view.
 * Used by CRM → Refresh Dashboard (manual full update).
 */
function refreshEntireWorkbook_() {
  var start = Date.now();
  var lock = LockService.getDocumentLock();
  var locked = false;
  var steps = [];
  function step(name, fn) {
    try {
      fn();
      steps.push(name + ': OK');
    } catch (e) {
      steps.push(name + ': ' + ((e && e.message) || String(e)));
      Logger.log('refreshEntireWorkbook_ [' + name + ']: ' + ((e && e.message) || e));
    }
  }

  try {
    locked = lock.tryLock(30000);
    if (!locked) throw businessError_('Workbook refresh is busy. Please retry in a moment.', 'LOCK_BUSY');

    step('schemas', function () {
      if (typeof ensureLeadSchema_ === 'function') ensureLeadSchema_();
      if (typeof ensureDeliverySchema_ === 'function') ensureDeliverySchema_();
      if (typeof ensurePaymentLedgerSchema_ === 'function') ensurePaymentLedgerSchema_();
      if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_();
      if (typeof ensureSchemeAndIncentiveSheets_ === 'function') ensureSchemeAndIncentiveSheets_();
      if (typeof ensurePhase3Sheets_ === 'function') ensurePhase3Sheets_();
      if (typeof ensureCommercialSnapshotSheet_ === 'function') ensureCommercialSnapshotSheet_();
      if (typeof ensureSchemeShareSettingsRows_ === 'function') ensureSchemeShareSettingsRows_();
    });

    step('store', function () {
      // Invalidate only — syncComputedFields_ (next step) does its own fresh load,
      // so building the store here was a pure duplicate full-workbook read.
      invalidateCrmStore_();
    });

    step('computed', function () {
      // dashboard:false here — we refresh dashboard explicitly after claim/finance views
      syncComputedFields_({ dashboard: false });
    });

    step('schemeClaims', function () {
      if (typeof rebuildSchemeClaimRegister_ === 'function') rebuildSchemeClaimRegister_();
    });

    step('financePending', function () {
      if (typeof ensureFinanceRegisterSynced_ === 'function') ensureFinanceRegisterSynced_();
      if (typeof refreshFinancePendingView_ === 'function') refreshFinancePendingView_();
      // refreshFinancePendingView_ also refreshes Finance Overdue
    });

    step('scorecard', function () {
      if (typeof refreshExecutiveScorecard_ === 'function') refreshExecutiveScorecard_();
    });

    step('dealerDaily', function () {
      if (typeof refreshDealerDailyRegister_ === 'function') refreshDealerDailyRegister_();
    });

    step('dashboard', function () {
      invalidateCrmStore_();
      refreshDashboard_();
    });

    step('tabs', function () {
      // Apply VISIBLE_ORDER + keep KPI drill-downs visible for Dashboard HYPERLINKs
      if (typeof organizeSpreadsheetTabs_ === 'function') organizeSpreadsheetTabs_();
    });

    step('navigation', function () {
      if (typeof navRefreshAllHyperlinks_ === 'function') navRefreshAllHyperlinks_();
    });

    step('dropdowns', function () {
      if (typeof refreshAllDropdowns_ === 'function') refreshAllDropdowns_();
    });

    step('counters', function () {
      if (typeof syncCountersToSettingsSheet_ === 'function') syncCountersToSettingsSheet_();
    });

    SpreadsheetApp.flush();
    var ms = Date.now() - start;
    recordPerf_('full_refresh', ms);
    logAudit_('FULL_WORKBOOK_REFRESH', JSON.stringify({ ms: ms, steps: steps }));
    return { success: true, executionMs: ms, steps: steps };
  } finally {
    if (locked) lock.releaseLock();
  }
}

/**
 * Sync computed columns only – no document lock, protection, or dropdown refresh.
 * Safe to call after merge/payment when caller already released its lock.
 */
function syncComputedFields_(options) {
  options = options || {};
  try {
    invalidateCrmStore_();
    var store = loadCrmStore_(true);
    syncCommercialSnapshots_(store);
    invalidateCrmStore_();
    store = loadCrmStore_(true);

    syncLeadComputed_(store);
    syncActivityLookups_(store);
    syncPaymentComputed_(store);
    syncDeliveryLookups_(store);

    invalidateCrmStore_();
    if (options.dashboard !== false) {
      try {
        // Pass the already-built store so refreshDashboard_ does not run a third
        // full rebuild inside the same worker run.
        store = loadCrmStore_(true);
        refreshDashboard_(store);
      } catch (dashErr) {
        logAudit_('SYNC_DASHBOARD_WARN', dashErr.message + '\n' + (dashErr.stack || ''));
      }
    }
    try {
      if (typeof refreshExecutiveScorecard_ === 'function') refreshExecutiveScorecard_();
    } catch (scoreErr) {
      logAudit_('SYNC_SCORECARD_WARN', scoreErr.message + '\n' + (scoreErr.stack || ''));
    }
    try {
      if (typeof refreshDealerDailyRegister_ === 'function') refreshDealerDailyRegister_();
    } catch (dailyErr) {
      logAudit_('SYNC_DAILY_WARN', dailyErr.message + '\n' + (dailyErr.stack || ''));
    }
  } catch (syncErr) {
    logAudit_('SYNC_COMPUTED_ERROR', syncErr.message + '\n' + (syncErr.stack || ''));
    throw syncErr;
  }
}

function syncCommercialSnapshots_(store) {
  store = store || loadCrmStore_();
  var changed = false;
  Object.keys(store.leads.byId).forEach(function (id) {
    if (ensureCommercialSnapshotForLead_(store.leads.byId[id], store)) changed = true;
  });
  if (changed) invalidateCrmStore_();
}

function syncLeadComputed_(store) {
  store = store || loadCrmStore_();
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  // Ensure price columns exist; refresh headers from sheet (not stale store).
  try {
    if (typeof ensureLeadCommercialPriceColumns_ === 'function') ensureLeadCommercialPriceColumns_();
  } catch (eCol) {}
  var h = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  store.leads.headers = h;
  var schemeCols = [
    'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Bonus', 'Additional Discount',
    'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount', 'Customer Payable', 'Ex Showroom',
    'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges',
    'TRC', 'Fastag', 'Extended Warranty', 'Other Charges', 'Gross Vehicle Cost',
    'Last Payment Mode', 'Financer Name', 'Finance File Number'
  ];
  var cols = {
    lastActivity: findHeaderIndex_(h, 'Last Activity') + 1,
    deliveryStatus: findHeaderIndex_(h, 'Delivery Status') + 1,
    deliveryDate: findHeaderIndex_(h, 'Delivery Date') + 1,
    outstanding: findHeaderIndex_(h, 'Outstanding Amount') + 1,
    finalOutstanding: findHeaderIndex_(h, 'Final Outstanding') + 1,
    customerOs: findHeaderIndex_(h, 'Customer Outstanding') + 1,
    companyOs: findHeaderIndex_(h, 'Company Outstanding') + 1,
    totalReceived: findHeaderIndex_(h, 'Total Received') + 1
  };
  if (cols.outstanding < 1 && cols.lastActivity < 1 && cols.finalOutstanding < 1) return;

  var updates = {
    lastActivity: [], deliveryStatus: [], deliveryDate: [],
    outstanding: [], finalOutstanding: [], customerOs: [], companyOs: [], totalReceived: []
  };
  var schemeUpdates = {};
  schemeCols.forEach(function (name) { schemeUpdates[name] = []; });
  var rows = [];
  var hasAnySchemeCol = schemeCols.some(function (name) { return findHeaderIndex_(h, name) >= 0; });

  store.leads.rows.forEach(function (row, i) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var sheetRow = (store.leads.sheetRow && store.leads.sheetRow[id]) || (CRM.LEAD.DATA_START + i);
    rows.push(sheetRow);
    var del = store.deliveryByLead[id] || {};
    var truth = typeof buildLeadCommercialTruthFields_ === 'function'
      ? buildLeadCommercialTruthFields_(id, store)
      : {};
    var customerOs = truth['Customer Outstanding'] != null ? truth['Customer Outstanding'] : computeDashboardOutstanding_(id, store);
    var totalOs = truth['Outstanding Amount'] != null ? truth['Outstanding Amount'] : customerOs;
    var companyOs = truth['Company Outstanding'] != null ? truth['Company Outstanding'] : 0;
    var paid = truth['Total Received'] != null ? truth['Total Received'] : Number(store.paymentsByLead[id] || 0);
    updates.lastActivity.push([store.lastActivityByLead[id] || '']);
    updates.deliveryStatus.push([del.delivered || '']);
    updates.deliveryDate.push([del.deliveryDate || '']);
    updates.outstanding.push([totalOs]);
    updates.finalOutstanding.push([totalOs]);
    updates.customerOs.push([customerOs]);
    updates.companyOs.push([companyOs]);
    updates.totalReceived.push([paid]);
    if (hasAnySchemeCol) {
      schemeCols.forEach(function (name) {
        var v = truth[name];
        schemeUpdates[name].push([v === undefined || v === null ? '' : v]);
      });
    }
  });

  if (rows.length === 0) return;
  if (cols.lastActivity > 0) writeColumnBatch_(sheet, rows, cols.lastActivity, updates.lastActivity);
  if (cols.deliveryStatus > 0) writeColumnBatch_(sheet, rows, cols.deliveryStatus, updates.deliveryStatus);
  if (cols.deliveryDate > 0) writeColumnBatch_(sheet, rows, cols.deliveryDate, updates.deliveryDate);
  if (cols.outstanding > 0) writeColumnBatch_(sheet, rows, cols.outstanding, updates.outstanding);
  if (cols.finalOutstanding > 0) writeColumnBatch_(sheet, rows, cols.finalOutstanding, updates.finalOutstanding);
  if (cols.customerOs > 0) writeColumnBatch_(sheet, rows, cols.customerOs, updates.customerOs);
  if (cols.companyOs > 0) writeColumnBatch_(sheet, rows, cols.companyOs, updates.companyOs);
  if (cols.totalReceived > 0) writeColumnBatch_(sheet, rows, cols.totalReceived, updates.totalReceived);

  if (hasAnySchemeCol) {
    schemeCols.forEach(function (name) {
      var col = findHeaderIndex_(h, name) + 1;
      if (col > 0) writeColumnBatch_(sheet, rows, col, schemeUpdates[name]);
    });
  }
}

function syncActivityLookups_(store) {
  store = store || loadCrmStore_();
  var sheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  var h = store.activities.headers;
  var cName = findHeaderIndex_(h, 'Customer Name') + 1;
  var cMob = findHeaderIndex_(h, 'Mobile') + 1;
  var cModel = findHeaderIndex_(h, 'Model') + 1;
  if (cName < 1) return;

  var rows = [];
  var names = [], mobiles = [], models = [];

  store.activities.rows.forEach(function (row, i) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var lead = store.leads.byId[id];
    rows.push(CRM.ACTIVITY.DATA_START + i);
    names.push([lead ? lead.customerName : '']);
    mobiles.push([lead ? lead.mobile : '']);
    models.push([lead ? lead.interestedModel : '']);
  });

  if (rows.length === 0) return;
  writeColumnBatch_(sheet, rows, cName, names);
  writeColumnBatch_(sheet, rows, cMob, mobiles);
  writeColumnBatch_(sheet, rows, cModel, models);
}

function syncPaymentComputed_(store) {
  store = store || loadCrmStore_();
  var sheet = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  var h = store.payments.headers;
  var cName = findHeaderIndex_(h, 'Customer Name') + 1;
  var cRun = findHeaderIndex_(h, 'Running Total') + 1;
  var cOut = findHeaderIndex_(h, 'Outstanding Balance') + 1;
  if (cName < 1) return;

  var runningByLead = {};
  var rows = [];
  var names = [], runs = [], outs = [];

  // Pre-compute each lead's payable from the already-loaded store so we avoid
  // N calls to loadCrmStore_() inside getLeadDealAmount_() — one store load only.
  var payableByLead = {};
  if (store.leads && store.leads.byId) {
    Object.keys(store.leads.byId).forEach(function (lid) {
      payableByLead[lid] = getCommercialPayable_(lid, store) || 0;
    });
  }

  store.payments.rows.forEach(function (row, i) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var lead = store.leads.byId[id];
    var amt = parseNumber_(rowVal_(row, h, 'Amount'));
    runningByLead[id] = (runningByLead[id] || 0) + amt;

    rows.push(CRM.PAYMENT.DATA_START + i);
    names.push([lead ? lead.customerName : '']);
    runs.push([runningByLead[id]]);
    // Use the pre-computed payable — getLeadDealAmount_ would reload the store on every row.
    var payable = payableByLead[id] || 0;
    outs.push([Math.max(0, payable - runningByLead[id])]);
  });

  if (rows.length === 0) return;
  writeColumnBatch_(sheet, rows, cName, names);
  writeColumnBatch_(sheet, rows, cRun, runs);
  writeColumnBatch_(sheet, rows, cOut, outs);
}

function syncDeliveryLookups_(store) {
  store = store || loadCrmStore_();
  var sheet = getSheet_(CRM.SHEETS.DELIVERY_TRACKER);
  var h = store.deliveries.headers;
  var cName = findHeaderIndex_(h, 'Customer Name') + 1;
  if (cName < 1) return;

  var rows = [];
  var names = [];

  store.deliveries.rows.forEach(function (row, i) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var lead = store.leads.byId[id];
    rows.push(CRM.DELIVERY.DATA_START + i);
    names.push([lead ? lead.customerName : '']);
  });

  if (rows.length === 0) return;
  writeColumnBatch_(sheet, rows, cName, names);
}

/** Write values to a column – one batch write when rows are contiguous. */
function writeColumnBatch_(sheet, rowNumbers, col, values) {
  if (!rowNumbers || rowNumbers.length === 0) return;
  var contiguous = true;
  for (var i = 1; i < rowNumbers.length; i++) {
    if (rowNumbers[i] !== rowNumbers[i - 1] + 1) {
      contiguous = false;
      break;
    }
  }
  if (contiguous && rowNumbers.length === values.length) {
    sheet.getRange(rowNumbers[0], col, rowNumbers.length, 1).setValues(values);
    return;
  }
  for (var j = 0; j < rowNumbers.length; j++) {
    // setValueSafe_ prevents computed-column writes from failing on cells with 'Reject input' validation.
    setValueSafe_(sheet.getRange(rowNumbers[j], col), values[j][0]);
  }
}

/** Clear all cross-sheet formulas from computed columns. */
function clearComputedFormulas_() {
  var sheets = [
    { name: CRM.SHEETS.LEAD_REGISTER, cols: ['Last Activity', 'Delivery Status', 'Delivery Date', 'Outstanding Amount'], header: CRM.LEAD.HEADER_ROW, start: CRM.LEAD.DATA_START, colNames: CRM.LEAD.COLS },
    { name: CRM.SHEETS.ACTIVITY_LOG, cols: ['Customer Name', 'Mobile', 'Model'], header: CRM.ACTIVITY.HEADER_ROW, start: CRM.ACTIVITY.DATA_START, colNames: CRM.ACTIVITY.COLS },
    { name: CRM.SHEETS.PAYMENT_LEDGER, cols: ['Customer Name', 'Running Total', 'Outstanding Balance'], header: CRM.PAYMENT.HEADER_ROW, start: CRM.PAYMENT.DATA_START, colNames: CRM.PAYMENT.COLS },
    { name: CRM.SHEETS.DELIVERY_TRACKER, cols: ['Customer Name'], header: CRM.DELIVERY.HEADER_ROW, start: CRM.DELIVERY.DATA_START, colNames: CRM.DELIVERY.COLS }
  ];
  sheets.forEach(function (cfg) {
    var sheet = getSheet_(cfg.name);
    var lastRow = Math.max(sheet.getLastRow(), cfg.start);
    if (lastRow < cfg.start) return;
    var numRows = lastRow - cfg.start + 1;
    cfg.cols.forEach(function (colName) {
      var col = cfg.colNames.indexOf(colName) + 1;
      if (col > 0) sheet.getRange(cfg.start, col, numRows, 1).clearContent();
    });
  });
}
