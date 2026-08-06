/**
 * Historical data import from embedded migration payload.
 */

function importHistoricalData_() {
  assertOperational_('import');
  var ui = SpreadsheetApp.getUi();
  var response = ui.alert(
    'Import Historical Data',
    'This will import all historical records from BOOKING LIST.xlsx.\nExisting data with same mobile will be merged.\n\nContinue?',
    ui.ButtonSet.YES_NO
  );
  if (response !== ui.Button.YES) return;
  runImport_({ showUi: true });
}

function importHistoricalDataSilent_() {
  runImport_({ showUi: false, clearExisting: true, silent: true });
}

function runImport_(options) {
  options = options || { showUi: true, clearExisting: false };
  if (!options.silent) assertOperational_('import');
  var ui = SpreadsheetApp.getUi();

  if (options.showUi && !options.silent) {
    createVersionedBackup_('Pre-import snapshot');
  }

  var payload = getImportPayload_();
  if (!payload || !payload.leads) {
    var msg = 'Import payload not found. Run migration script locally and update ImportData.gs';
    if (options.showUi) ui.alert(msg);
    throw new Error(msg);
  }

  var report = {
    imported: 0,
    duplicates: 0,
    ignored: 0,
    errors: [],
    missingData: []
  };

  try {
    if (payload.masters) {
      payload.masters = expandMastersFromPayload_(payload);
      updateMastersFromImport_(payload.masters);
    }
    if (payload.settings) {
      Object.keys(payload.settings).forEach(function (k) {
        saveSetting_(k, payload.settings[k]);
      });
    }

    if (options.clearExisting) {
      clearImportedData_();
    }

    clearAllImportValidations_();
    var leadResult = batchImportLeads_(payload.leads);
    report.imported = leadResult.count;
    var leadIdRemap = leadResult.remap || {};

    if (payload.activities) {
      batchImportActivities_(payload.activities, leadIdRemap);
    }
    if (payload.payments) {
      batchImportPayments_(payload.payments, leadIdRemap);
    }

    if (payload.importLog) {
      report.duplicates = payload.importLog.duplicates || 0;
      report.ignored = payload.importLog.ignored || 0;
      report.errors = payload.importLog.errors || [];
      report.missingData = payload.importLog.missing_data || payload.importLog.missingData || [];
    }

    applyDataValidations_();
    repairMastersSheet_();
    clearComputedFormulas_();
    syncAll_({ dashboard: true });
    clearCache_();

    logImport_('IMPORT_COMPLETE', report.imported,
      'Duplicates: ' + report.duplicates + ', Ignored: ' + report.ignored +
      ', Missing mobile: ' + report.missingData.length);
    logAudit_('IMPORT', JSON.stringify(report));

    if (options.showUi) {
      var msg = 'IMPORT REPORT\n\n' +
        'Imported rows: ' + report.imported + '\n' +
        'Duplicate rows merged: ' + report.duplicates + '\n' +
        'Ignored rows: ' + report.ignored + '\n' +
        'Errors: ' + report.errors.length + '\n' +
        'Missing data (mobile): ' + report.missingData.length + '\n\n' +
        'See Import Log sheet for details.';
      ui.alert('Import Complete', msg, ui.ButtonSet.OK);
    }

  } catch (err) {
    logImport_('IMPORT_ERROR', 0, err.message);
    if (options.showUi) ui.alert('Import failed: ' + err.message);
    throw err;
  }
}

function clearImportedData_() {
  var lr = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var lastRow = lr.getLastRow();
  if (lastRow >= CRM.LEAD.DATA_START) {
    lr.getRange(CRM.LEAD.DATA_START, 1, lastRow - CRM.LEAD.DATA_START + 1, CRM.LEAD.COLS.length).clearContent();
  }
  [CRM.SHEETS.ACTIVITY_LOG, CRM.SHEETS.PAYMENT_LEDGER, CRM.SHEETS.DELIVERY_TRACKER].forEach(function (name) {
    var s = getSheet_(name);
    var lr2 = s.getLastRow();
    if (lr2 >= 2) s.getRange(2, 1, lr2 - 1, s.getLastColumn()).clearContent();
  });
}

function clearLeadRegisterValidations_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var numRows = CRM.MAX_ROWS;
  var cols = ['Lead Source', 'Interested Model', 'Variant', 'Colour', 'Executive', 'Current Status', 'Priority', 'Booking Status'];
  cols.forEach(function (name) {
    var col = CRM.LEAD.COLS.indexOf(name) + 1;
    if (col > 0) {
      sheet.getRange(CRM.LEAD.DATA_START, col, numRows, 1).clearDataValidations();
    }
  });
}

function clearActivityLogValidations_() {
  var sheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  var headers = getHeaders_(sheet, CRM.ACTIVITY.HEADER_ROW);
  var activityTypeCol = headers.indexOf('Activity Type') + 1;
  var executiveCol = headers.indexOf('Executive') + 1;
  if (activityTypeCol > 0) sheet.getRange(CRM.ACTIVITY.DATA_START, activityTypeCol, 5000, 1).clearDataValidations();
  if (executiveCol > 0) sheet.getRange(CRM.ACTIVITY.DATA_START, executiveCol, 5000, 1).clearDataValidations();
}

function clearPaymentLogValidations_() {
  var sheet = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  sheet.getRange(CRM.PAYMENT.DATA_START, 6, 5000, 1).clearDataValidations();
}

function clearAllImportValidations_() {
  clearLeadRegisterValidations_();
  clearActivityLogValidations_();
  clearPaymentLogValidations_();
}

function expandMastersFromPayload_(payload) {
  var masters = JSON.parse(JSON.stringify(payload.masters || {}));
  var execSet = {};

  function addExec(val) {
    var e = normalizeExecutiveName_(val);
    if (e) execSet[e.toLowerCase()] = e;
  }

  mergeMasterList_('Executives', []).forEach(function (e) { addExec(e); });
  (masters.executives || masters['Executives'] || []).forEach(addExec);
  (payload.leads || []).forEach(function (l) { addExec(l.executive); });
  (payload.activities || []).forEach(function (a) { addExec(a.executive); });
  masters.executives = Object.keys(execSet).map(function (k) { return execSet[k]; }).sort();

  var sourceSet = {};
  mergeMasterList_('Lead Sources', []).forEach(function (s) { sourceSet[s.toLowerCase()] = s; });
  (masters.leadSources || masters['Lead Sources'] || []).forEach(function (s) {
    var n = normalizeMasterValue_('Lead Sources', s);
    if (n) sourceSet[n.toLowerCase()] = n;
  });
  (payload.leads || []).forEach(function (l) {
    var n = normalizeMasterValue_('Lead Sources', l.leadSource);
    if (n) sourceSet[n.toLowerCase()] = n;
  });
  masters.leadSources = Object.keys(sourceSet).map(function (k) { return sourceSet[k]; }).sort();

  var modelSet = {};
  mergeMasterList_('Models', []).forEach(function (m) { modelSet[m.toLowerCase()] = m; });
  (masters.models || masters['Models'] || []).forEach(function (m) {
    var n = normalizeMasterValue_('Models', m);
    if (n) modelSet[n.toLowerCase()] = n;
  });
  masters.models = Object.keys(modelSet).map(function (k) { return modelSet[k]; }).sort();

  if (!masters.activityTypes && !masters['Activity Types']) {
    masters.activityTypes = CRM.MASTERS.SECTIONS['Activity Types'].slice();
  }

  return masters;
}

function normalizeExecutiveName_(value) {
  if (!value) return '';
  var e = String(value).trim();
  if (!e || e.length > 40) return '';
  var lower = e.toLowerCase();
  var aliases = {
    'lokesh': 'Lokesh', 'lokesk': 'Lokesh',
    'sanjay': 'Sanjay', 'sanjay ji': 'Sanjay', 'sanjay sir': 'Sanjay',
    'amit': 'Amit', 'dharmendra': 'Dharmendra',
    'prasun': 'Prasun', 'parsun': 'Prasun', 'parsun sir': 'Prasun',
    'devansh': 'Devansh', 'devang': 'Devansh',
    'ganesh': 'Ganesh', 'harish bhatnagar': 'Harish Bhatnagar', 'harish sir': 'Harish Bhatnagar'
  };
  if (aliases[lower]) return aliases[lower];
  if (lower.indexOf('lokesh') >= 0 || lower.indexOf('lokesk') >= 0) return 'Lokesh';
  if (lower.indexOf('sanjay') >= 0) return 'Sanjay';
  if (lower.indexOf('prasun') >= 0 || lower.indexOf('parsun') >= 0) return 'Prasun';
  if (lower.indexOf('harish') >= 0) return 'Harish Bhatnagar';
  if (lower.indexOf('ganesh') >= 0) return 'Ganesh';
  if (lower.indexOf('devansh') >= 0 || lower.indexOf('devang') >= 0) return 'Devansh';
  if (e.split(/\s+/).length > 4) return '';
  return e.replace(/\([^)]*\)/g, '').trim().split(/\s+/).map(function (w) {
    return w.charAt(0).toUpperCase() + w.slice(1).toLowerCase();
  }).join(' ');
}

function updateMastersFromImport_(masters) {
  var merged = {};
  var keyMap = {
    leadSources: 'Lead Sources',
    models: 'Models',
    variants: 'Variants',
    colours: 'Colours',
    status: 'Status',
    executives: 'Executives',
    paymentModes: 'Payment Modes',
    priority: 'Priority',
    activityTypes: 'Activity Types'
  };

  Object.keys(keyMap).forEach(function (key) {
    var section = keyMap[key];
    var raw = masters[key] || masters[section] || [];
    merged[section] = mergeMasterList_(section, raw);
  });

  writeMastersSheet_(merged);
}

function getImportPayload_() {
  try {
    return IMPORT_PAYLOAD;
  } catch (e) {
    return null;
  }
}

function sanitizeLeadForImport_(lead) {
  var masters = getMasters_();
  var models = masters['Models'] || CRM.MASTERS.SECTIONS['Models'];
  var statuses = masters['Status'] || CRM.MASTERS.SECTIONS['Status'];
  var executives = masters['Executives'] || CRM.MASTERS.SECTIONS['Executives'];
  var sources = masters['Lead Sources'] || CRM.MASTERS.SECTIONS['Lead Sources'];

  lead.interestedModel = matchMasterValue_(lead.interestedModel, models);
  lead.currentStatus = matchMasterValue_(lead.currentStatus, statuses) || 'New';
  lead.bookingStatus = matchMasterValue_(lead.bookingStatus, statuses) || lead.bookingStatus || '';
  lead.executive = matchMasterValue_(normalizeExecutiveName_(lead.executive), executives) || '';
  lead.leadSource = matchMasterValue_(lead.leadSource, sources) || 'Walk-in';
  lead.priority = matchMasterValue_(lead.priority, masters['Priority'] || []) || 'Normal';
  lead.accountStatus = lead.accountStatus || ACCOUNT_STATUS.ACTIVE;
  return lead;
}

function sanitizeActivityForImport_(activity) {
  var masters = getMasters_();
  var executives = masters['Executives'] || CRM.MASTERS.SECTIONS['Executives'];
  activity.executive = matchMasterValue_(normalizeExecutiveName_(activity.executive), executives) || '';
  activity.activityType = normalizeActivityTypeForWrite_(activity.activityType, { allowFallback: true, fallbackType: 'Note' });
  return activity;
}
