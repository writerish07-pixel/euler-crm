/**
 * Utility functions - batch operations, caching, mobile validation.
 */

function getSpreadsheet_() {
  return SpreadsheetApp.getActiveSpreadsheet();
}

/** True when the active user owns this spreadsheet (owner-only menu items). */
function isSpreadsheetOwner_() {
  try {
    var owner = String(getSpreadsheet_().getOwner().getEmail() || '').toLowerCase();
    var user = String(Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail() || '').toLowerCase();
    if (!owner || !user) return false;
    return owner === user;
  } catch (e) {
    return false;
  }
}

function getSheet_(name) {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(name);
  if (!sheet) throw new Error('Sheet not found: ' + name);
  return sheet;
}

function colIndex_(headers, name) {
  var idx = headers.indexOf(name);
  if (idx === -1) throw new Error('Column not found: ' + name);
  return idx + 1;
}

function colLetter_(n) {
  var s = '';
  while (n > 0) {
    var m = (n - 1) % 26;
    s = String.fromCharCode(65 + m) + s;
    n = Math.floor((n - 1) / 26);
  }
  return s;
}

function getHeaders_(sheet, headerRow) {
  var lastCol = sheet.getLastColumn();
  if (lastCol === 0) return [];
  return sheet.getRange(headerRow, 1, 1, lastCol).getValues()[0].map(function (h) {
    return String(h || '').trim();
  });
}

/** Normalize header text for tolerant matching (case, spaces, line breaks). */
function normalizeHeaderKey_(name) {
  return String(name || '')
    .replace(/[\r\n]+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ');
}

/** Case-insensitive header lookup; returns 0-based index or -1. */
function findHeaderIndex_(headers, name) {
  var target = normalizeHeaderKey_(name);
  for (var i = 0; i < headers.length; i++) {
    if (normalizeHeaderKey_(headers[i]) === target) return i;
  }
  return -1;
}

function normalizeStatus_(status) {
  return String(status || '').trim();
}

/** Normalize Yes/No style values used by pricing/commercial flows. */
function normalizeYesNo_(value) {
  var s = String(value || '').trim().toLowerCase();
  if (!s) return 'No';
  if (s === 'yes' || s === 'y' || s === 'true' || s === '1') return 'Yes';
  if (s === 'no' || s === 'n' || s === 'false' || s === '0') return 'No';
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/**
 * Normalize Model/Variant for Price Master lookup.
 * Handles: trim, case, NBSP, extra spaces, punctuation.
 */
function normalizePriceKey_(v) {
  return String(v || '')
    .replace(/\u00A0/g, ' ')
    .replace(/[\r\n\t]+/g, ' ')
    .trim()
    .toLowerCase()
    .replace(/\s+/g, ' ')
    .replace(/\s*\(\s*/g, '(')
    .replace(/\s*\)\s*/g, ')')
    .replace(/[^a-z0-9]/g, '');
}

/**
 * Convert date/string to yyyyMMdd number key.
 * Supports: Date objects, ISO YYYY-MM-DD, Indian DD/MM/YYYY.
 */
function normalizeDateKey_(v) {
  if (v === '' || v === null || v === undefined) return 0;
  if (typeof v === 'number' && v > 19000101 && v < 30000101) return Math.floor(v);
  if (v instanceof Date) {
    if (isNaN(v.getTime())) return 0;
    return Number(Utilities.formatDate(v, Session.getScriptTimeZone(), 'yyyyMMdd'));
  }
  var s = String(v).trim();
  if (!s) return 0;
  var m = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})$/);
  if (m) {
    var dd = Number(m[1]), mm = Number(m[2]), yy = Number(m[3]);
    if (mm >= 1 && mm <= 12 && dd >= 1 && dd <= 31) return yy * 10000 + mm * 100 + dd;
  }
  var iso = s.match(/^(\d{4})[\/\-.](\d{1,2})[\/\-.](\d{1,2})/);
  if (iso) {
    var iy = Number(iso[1]), im = Number(iso[2]), idd = Number(iso[3]);
    if (im >= 1 && im <= 12 && idd >= 1 && idd <= 31) return iy * 10000 + im * 100 + idd;
  }
  var d = new Date(s);
  if (isNaN(d.getTime())) return 0;
  return Number(Utilities.formatDate(d, Session.getScriptTimeZone(), 'yyyyMMdd'));
}

var CRM_COUNTER_KEYS_ = {
  lead: { prop: 'crm_counter_lead', settings: 'nextLeadCounter', prefixKey: 'leadPrefix', defaultPrefix: 'LD26' },
  activity: { prop: 'crm_counter_activity', settings: 'nextActivityCounter', prefixKey: null, defaultPrefix: 'AC26' },
  receipt: { prop: 'crm_counter_receipt', settings: 'nextReceiptCounter', prefixKey: 'receiptPrefix', defaultPrefix: 'RC26' },
  financeFile: { prop: 'crm_counter_finance_file', settings: 'nextFinanceFileCounter', prefixKey: 'financeFilePrefix', defaultPrefix: 'FN26' }
};

function readSettingsFromSheetBestEffort_() {
  var settings = Object.assign({}, CRM.SETTINGS_DEFAULTS);
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.SETTINGS);
    if (!sheet) return settings;
    var data = sheet.getDataRange().getValues();
    for (var i = 1; i < data.length; i++) {
      if (data[i][0]) settings[data[i][0]] = data[i][1];
    }
  } catch (e) {
    Logger.log('readSettingsFromSheetBestEffort_: ' + e.message);
  }
  return settings;
}

function mergeScriptCountersIntoSettings_(settings) {
  try {
    var props = PropertiesService.getScriptProperties();
    if (props.getProperty('crm_counter_lead')) settings.nextLeadCounter = Number(props.getProperty('crm_counter_lead'));
    if (props.getProperty('crm_counter_activity')) settings.nextActivityCounter = Number(props.getProperty('crm_counter_activity'));
    if (props.getProperty('crm_counter_receipt')) settings.nextReceiptCounter = Number(props.getProperty('crm_counter_receipt'));
    if (props.getProperty('crm_counter_finance_file')) settings.nextFinanceFileCounter = Number(props.getProperty('crm_counter_finance_file'));
  } catch (e) {}
  settings.nextLeadCounter = Number(settings.nextLeadCounter) || 1;
  settings.nextActivityCounter = Number(settings.nextActivityCounter) || 1;
  settings.nextReceiptCounter = Number(settings.nextReceiptCounter) || 1;
  settings.nextFinanceFileCounter = Number(settings.nextFinanceFileCounter) || 1;
  return settings;
}

function getSettings_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('settings');
  if (cached) return JSON.parse(cached);

  var settings = mergeScriptCountersIntoSettings_(readSettingsFromSheetBestEffort_());
  try { cache.put('settings', JSON.stringify(settings), 300); } catch (ce) {}
  return settings;
}

function initScriptCountersFromSettings_() {
  var props = PropertiesService.getScriptProperties();
  if (props.getProperty('crm_counters_init') === '1') return;
  try {
    var settings = readSettingsFromSheetBestEffort_();
    props.setProperty('crm_counter_lead', String(settings.nextLeadCounter || 1));
    props.setProperty('crm_counter_activity', String(settings.nextActivityCounter || 1));
    props.setProperty('crm_counter_receipt', String(settings.nextReceiptCounter || 1));
    props.setProperty('crm_counter_finance_file', String(settings.nextFinanceFileCounter || 1));
    props.setProperty('crm_counters_init', '1');
  } catch (e) {
    Logger.log('initScriptCountersFromSettings_: ' + e.message);
  }
}

function syncCountersToSettingsSheet_() {
  try {
    var props = PropertiesService.getScriptProperties();
    saveSettingSilent_('nextLeadCounter', Number(props.getProperty('crm_counter_lead') || 1));
    saveSettingSilent_('nextActivityCounter', Number(props.getProperty('crm_counter_activity') || 1));
    saveSettingSilent_('nextReceiptCounter', Number(props.getProperty('crm_counter_receipt') || 1));
    saveSettingSilent_('nextFinanceFileCounter', Number(props.getProperty('crm_counter_finance_file') || 1));
    CacheService.getScriptCache().remove('settings');
  } catch (e) {
    Logger.log('syncCountersToSettingsSheet_: ' + e.message);
  }
}

function saveSettingSilent_(key, value) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.SETTINGS);
  if (!sheet) return;
  var data = sheet.getDataRange().getValues();
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] === key) {
      sheet.getRange(i + 1, 2).setValue(value);
      return;
    }
  }
  sheet.appendRow([key, value]);
}

function saveSetting_(key, value) {
  try {
    saveSettingSilent_(key, value);
    CacheService.getScriptCache().remove('settings');
  } catch (e) {
    Logger.log('saveSetting_ deferred to script props: ' + e.message);
    CacheService.getScriptCache().remove('settings');
  }
}

function getMasters_() {
  return getMergedMasters_();
}

function clearCache_() {
  var cache = CacheService.getScriptCache();
  cache.remove('settings');
  cache.remove('masters');
  cache.remove('masters_merged');
  cache.remove('price_master_active_v1');
  try { invalidatePriceMasterCache_(); } catch (e) {}
  invalidateCrmStore_();
}

/** Wrap public operations with error logging + crash report. */
function safeRun_(label, fn) {
  var start = Date.now();
  try {
    return fn();
  } catch (err) {
    safeLogError_(label, err, Date.now() - start);
    throw err;
  }
}

/** Non-throwing error log chain for safeRun / background tasks. */
function safeLogError_(label, err, ms) {
  try {
    logCrash_('System', label, err, { executionMs: ms, errorCode: 'ERROR_' + label });
  } catch (e) { Logger.log('safeLogError_ crash: ' + e.message); }
  try { logAudit_('ERROR_' + label, (err && err.message) || String(err)); } catch (e) {}
  try {
    logTransaction_('System', 'Error: ' + label, {
      status: 'FAIL',
      errorCode: 'ERROR_' + label,
      executionMs: ms,
      message: (err && err.message) || String(err)
    });
  } catch (e) {}
}

function businessError_(message, code) {
  var e = new Error(message);
  e.errorCode = code || 'BUSINESS_ERROR';
  return e;
}

/** Staff-friendly validation error — always names the exact form field. */
function fieldError_(fieldLabel, detail, code) {
  var label = String(fieldLabel || 'Field').trim();
  var msg = label + ': ' + String(detail || 'Please check this field.').trim();
  var e = new Error(msg);
  e.errorCode = code || 'VALIDATION';
  e.fieldLabel = label;
  e.detail = detail;
  return e;
}

function requireField_(value, fieldLabel, detail) {
  if (value === undefined || value === null || String(value).trim() === '') {
    throw fieldError_(fieldLabel, detail || 'This field is required.', 'VALIDATION');
  }
}

function requirePositiveAmount_(value, fieldLabel) {
  var amt = Number(value);
  if (!isFinite(amt) || amt <= 0) {
    throw fieldError_(fieldLabel, 'Enter an amount greater than zero.', 'VALIDATION');
  }
}

/** Extract the message staff should see (no function/step noise for validation). */
function formatStaffErrorMessage_(err) {
  if (!err) return 'Unknown error';
  if (typeof err === 'string') return err;
  if (err.fieldLabel && err.detail) {
    return String(err.fieldLabel).trim() + ': ' + String(err.detail).trim();
  }
  var msg = String((err && err.message) || err || '').trim();
  var code = inferErrorCode_(err);
  if (code === 'VALIDATION' || code === 'SCHEME_VALIDATION' || code === 'SCHEME_NOT_AVAILABLE' ||
      code === 'DUPLICATE' || code === 'NOT_FOUND') {
    return msg;
  }
  var m = msg.match(/Error:\s*([\s\S]+?)(?:\nCode:|\nSuggested|$)/i);
  if (m && m[1]) return m[1].trim();
  return msg;
}

function inferErrorCode_(err) {
  var msg = String((err && err.message) || err || '').toLowerCase();
  if (msg.indexOf('maintenance mode') >= 0) return 'MAINTENANCE_MODE';
  if (msg.indexOf('permission') >= 0 || msg.indexOf('authorization') >= 0) return 'PERMISSION_DENIED';
  if (msg.indexOf('busy') >= 0) return 'LOCK_BUSY';
  return (err && err.errorCode) || 'ERROR';
}

function buildCrmErrorMessage_(module, fnName, step, err) {
  var code = inferErrorCode_(err);
  if (err && err.fieldLabel) {
    return formatStaffErrorMessage_(err);
  }
  if (code === 'VALIDATION' || code === 'SCHEME_VALIDATION' || code === 'SCHEME_NOT_AVAILABLE' ||
      code === 'DUPLICATE' || code === 'NOT_FOUND' || code === 'PRICE_INCOMPLETE') {
    return formatStaffErrorMessage_(err);
  }
  var hint = '';
  if (code === 'MAINTENANCE_MODE') {
    hint = '\nSuggested action: Owner runs CRM → Exit Maintenance Mode.';
  } else if (code === 'PERMISSION_DENIED') {
    hint = '\nSuggested action: Confirm you have Editor access to this spreadsheet, then retry.';
  }
  return formatStaffErrorMessage_(err) + (hint ? '\n' + hint : '');
}

function crmFailStructured_(module, fnName, step, err, executionTime) {
  return {
    success: false,
    message: buildCrmErrorMessage_(module, fnName, step, err),
    module: module,
    function: fnName,
    errorCode: inferErrorCode_(err),
    stack: (err && err.stack) || '',
    executionTime: executionTime || 0,
    data: null
  };
}

/**
 * Standard public handler – timed execution, structured response, transaction log.
 * @param {string} module
 * @param {string} action
 * @param {Function} fn
 * @returns {{success: boolean, message: string, data: *, errorCode: string|null, executionTime: number}}
 */
function crmRun_(module, action, fn) {
  var start = Date.now();
  try {
    var data = fn();
    var ms = Date.now() - start;
    logTransaction_(module, action, { status: 'OK', executionMs: ms, message: 'Success' });
    return {
      success: true,
      message: action + ' completed',
      data: data,
      errorCode: null,
      executionTime: ms
    };
  } catch (err) {
    var ms = Date.now() - start;
    logCrash_(module, action, err, { executionMs: ms, errorCode: err.errorCode || 'ERROR' });
    logTransaction_(module, action, {
      status: 'FAIL',
      executionMs: ms,
      errorCode: err.errorCode || 'ERROR',
      message: err.message
    });
    logAudit_('ERROR_' + module, action + ': ' + err.message);
    throw err;
  }
}

/**
 * Standard API response for dialog and menu handlers.
 * @returns {{success: boolean, message: string, data: *, errorCode: string|null, executionTime: number}}
 */
function crmOk_(message, data, executionTime, meta) {
  meta = meta || {};
  return {
    success: true,
    message: message || 'OK',
    data: data !== undefined ? data : null,
    module: meta.module || null,
    function: meta.function || null,
    errorCode: null,
    executionTime: executionTime || 0
  };
}

function crmFail_(message, errorCode, executionTime) {
  return {
    success: false,
    message: message || 'Operation failed',
    data: null,
    errorCode: errorCode || 'ERROR',
    executionTime: executionTime || 0
  };
}

/**
 * Safe setValue that bypasses Google Sheets "Reject input" data validation.
 *
 * Apps Script's Range.setValue() throws when a cell has a data-validation rule
 * set to "Reject input" and the value doesn't match the list — even for
 * programmatic writes from trusted server code. This helper catches that error,
 * clears the validation on just that one cell (computed/auto columns should
 * never block writes), and retries. If the second attempt still fails it logs
 * and continues so the caller is never interrupted by a formatting constraint.
 *
 * Use this everywhere the CRM script writes computed values (outstanding,
 * financer name, finance flag, etc.) to sheets that may have user-configured
 * dropdowns set to "Reject input".
 */
/**
 * SINGLE definition (a divergent duplicate previously lived in FixesService — the
 * loaded winner depended on file order). This variant PRESERVES the cell's data
 * validation: it lifts the rule, writes, and restores it, so dropdowns keep
 * guiding manual entry instead of being silently stripped.
 */
function setValueSafe_(range, value) {
  var existingRule = null;
  try { existingRule = range.getDataValidation(); } catch (e) {}
  try {
    if (existingRule !== null) range.clearDataValidations();
    range.setValue(value);
  } catch (writeErr) {
    Logger.log('setValueSafe_ write error: ' + writeErr.message +
               ' | cell=' + range.getA1Notation() +
               ' | value=' + String(value));
  } finally {
    try {
      if (existingRule !== null) range.setDataValidation(existingRule);
    } catch (restoreErr) { /* best-effort */ }
  }
}

/** Write one data row at sheet row (batch-safe). Owner / full-unlock path. */
function writeSheetRow_(sheet, row, values) {
  sheet.getRange(row, 1, 1, values.length).setValues([values]);
}

/** Direct row write — no protection, no column filtering. */
function writeBusinessRow_(sheet, row, values) {
  writeSheetRow_(sheet, row, values);
}

function sheetRef_(sheetName) {
  return "'" + String(sheetName).replace(/'/g, "''") + "'";
}

function sheetRange_(sheetName, a1Range) {
  return sheetRef_(sheetName) + '!' + a1Range;
}

function resolveLeadId_(leadId, remap) {
  if (!leadId || !remap) return leadId;
  var id = String(leadId);
  var safety = 0;
  while (remap[id] && safety < 10) {
    id = remap[id];
    safety++;
  }
  return id;
}

function normalizeMobile_(mobile) {
  if (!mobile) return '';
  var s = String(mobile).replace(/\D/g, '');
  if (s.length === 12 && s.indexOf('91') === 0) s = s.substring(2);
  if (s.length === 11 && s.indexOf('0') === 0) s = s.substring(1);
  if (s.length > 10) s = s.substring(s.length - 10);
  return s.length === 10 ? s : '';
}

function isValidMobile_(mobile) {
  return /^\d{10}$/.test(normalizeMobile_(mobile));
}

function generateId_(type) {
  initScriptCountersFromSettings_();
  var counterCfg = CRM_COUNTER_KEYS_[type];
  if (counterCfg) {
    var props = PropertiesService.getScriptProperties();
    var n = Number(props.getProperty(counterCfg.prop) || 1);
    var settings = getSettings_();
    var prefix = counterCfg.prefixKey
      ? String(settings[counterCfg.prefixKey] || counterCfg.defaultPrefix)
      : counterCfg.defaultPrefix;
    var id = prefix + String(n).padStart(6, '0');
    props.setProperty(counterCfg.prop, String(n + 1));
    return id;
  }

  var prefixes = { payment: 'PY', delivery: 'DL', claim: 'CLM', incentive: 'INCN', insurance: 'INS' };
  var pfx = prefixes[type] || 'ID';
  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyMMddHHmmss');
  return pfx + ts + String(Math.floor(Math.random() * 900 + 100));
}

function getUserEmail_() {
  try {
    return Session.getActiveUser().getEmail() || Session.getEffectiveUser().getEmail() || 'System';
  } catch (e) {
    return 'System';
  }
}

function formatDate_(date) {
  if (date === '' || date === null || date === undefined) return '';
  if (date instanceof Date && !isNaN(date.getTime())) {
    return Utilities.formatDate(date, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  }
  var s = String(date).trim();
  if (!s) return '';
  if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.substring(0, 10);
  var dmy = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{4})/);
  if (dmy) {
    return dmy[3] + '-' + ('0' + dmy[2]).slice(-2) + '-' + ('0' + dmy[1]).slice(-2);
  }
  var mdy = s.match(/^(\d{1,2})[\/\-.](\d{1,2})[\/\-.](\d{2,4})$/);
  if (mdy && Number(mdy[3]) > 31) {
    return mdy[3] + '-' + ('0' + mdy[1]).slice(-2) + '-' + ('0' + mdy[2]).slice(-2);
  }
  var parsed = new Date(s);
  if (!isNaN(parsed.getTime())) {
    return Utilities.formatDate(parsed, Session.getScriptTimeZone(), 'yyyy-MM-dd');
  }
  return s;
}

function formatTime_(date) {
  if (!date) return '';
  if (date instanceof Date) {
    return Utilities.formatDate(date, Session.getScriptTimeZone(), 'HH:mm');
  }
  return String(date);
}

function nowDate_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
}

function nowDateTime_() {
  return Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
}

function logAudit_(action, details) {
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.AUDIT_LOG);
    if (!sheet) return;
    sheet.appendRow([
      nowDateTime_(), getUserEmail_(), action,
      String(details || '').substring(0, 1000), getVersionTag_()
    ]);
  } catch (e) {
    Logger.log('logAudit_ failed: ' + e.message);
  }
}

function logImport_(category, count, details) {
  var sheet = getSheet_(CRM.SHEETS.IMPORT_LOG);
  sheet.appendRow([nowDateTime_(), category, count, details + ' [' + getVersionTag_() + ']']);
}


function showToast_(message, title) {
  getSpreadsheet_().toast(message, title || 'CRM', 5);
}

function showAlert_(message) {
  SpreadsheetApp.getUi().alert(message);
}

/* ----- PostTransactionProcessor (inlined for deploy safety) ----- */

var POST_TX = {
  INVALIDATE_STORE: 'invalidate_store',
  SYNC_COMPUTED: 'sync_computed',
  AUDIT: 'audit',
  TRANSACTION_OK: 'transaction_ok',
  TRANSACTION_FAIL: 'transaction_fail',
  PERF: 'perf',
  SYNC_COUNTERS: 'sync_counters'
};

function queuePostTransaction_(tasks, ctx) {
  ctx = ctx || {};
  var results = [];
  (tasks || []).forEach(function (task) {
    try {
      runPostTransactionTask_(task, ctx);
      results.push({ task: task, ok: true });
    } catch (err) {
      results.push({ task: task, ok: false, error: err.message });
      safeLogBackgroundError_('PostTransaction', task, err, ctx);
    }
  });
  return results;
}

function runPostTransactionTask_(task, ctx) {
  switch (task) {
    case POST_TX.INVALIDATE_STORE:
      invalidateCrmStore_();
      break;
    case POST_TX.SYNC_COMPUTED:
      runImmediateCrmRefresh_(ctx);
      break;
    case POST_TX.AUDIT:
      if (ctx.auditAction) logAudit_(ctx.auditAction, ctx.auditDetail || '');
      break;
    case POST_TX.TRANSACTION_OK:
      logTransaction_(ctx.module || 'System', ctx.action || 'OK', {
        leadId: ctx.leadId || '', status: 'OK',
        executionMs: ctx.executionMs || 0, message: ctx.message || ''
      });
      break;
    case POST_TX.TRANSACTION_FAIL:
      logTransaction_(ctx.module || 'System', ctx.action || 'FAIL', {
        leadId: ctx.leadId || '', status: 'FAIL',
        errorCode: ctx.errorCode || 'ERROR',
        executionMs: ctx.executionMs || 0, message: ctx.message || ''
      });
      break;
    case POST_TX.PERF:
      if (ctx.perfOp) recordPerf_(ctx.perfOp, ctx.executionMs || 0);
      break;
    case POST_TX.SYNC_COUNTERS:
      syncCountersToSettingsSheet_();
      break;
    default:
      Logger.log('Unknown post-transaction task: ' + task);
  }
}

function runCriticalBusinessTransaction_(opts) {
  opts = opts || {};
  var start = Date.now();
  var step = 'init';
  var ctx = opts.context || {};
  var leadId = '';
  try {
    step = 'commit';
    var commitResult = opts.commitFn(function (s) { step = s; });
    if (commitResult && commitResult.leadId) leadId = commitResult.leadId;
    ctx.leadId = ctx.leadId || leadId;
    ctx.executionMs = Date.now() - start;
    queuePostTransaction_(opts.postTasks || [
      POST_TX.INVALIDATE_STORE, POST_TX.SYNC_COMPUTED,
      POST_TX.AUDIT, POST_TX.TRANSACTION_OK, POST_TX.PERF
    ], ctx);
    return crmOk_(opts.successMessage || 'Operation completed', commitResult, ctx.executionMs, {
      module: opts.module, function: opts.action
    });
  } catch (err) {
    var ms = Date.now() - start;
    ctx.executionMs = ms;
    ctx.errorCode = err.errorCode || 'BUSINESS_ERROR';
    ctx.message = step + ': ' + (err.message || String(err));
    queuePostTransaction_([POST_TX.TRANSACTION_FAIL], ctx);
    safeLogBackgroundError_(opts.module || 'Business', opts.action || step, err, ctx);
    return crmFailStructured_(
      opts.module || 'Business', opts.action || 'runCriticalBusinessTransaction_', step, err, ms
    );
  }
}

function safeLogBackgroundError_(module, fnName, err, opts) {
  opts = opts || {};
  try {
    logCrash_(module, fnName, err, {
      leadId: opts.leadId || '', errorCode: 'BG_' + fnName, executionMs: opts.executionMs || 0
    });
  } catch (e) {
    Logger.log('safeLogBackgroundError_: ' + e.message);
  }
}

/** Run dashboard + report tabs after dialog returns (never block google.script.run). */
function runImmediateCrmRefresh_(ctx) {
  ctx = ctx || {};
  try {
    if (ctx.indexEntry) upsertRelationshipIndex_(ctx.indexEntry);
    else if (ctx.leadId) upsertRelationshipIndex_({ LeadID: ctx.leadId });
    invalidateCrmStore_();
  } catch (e) {
    Logger.log('Quick CRM index refresh: ' + e.message);
  }
  // Full syncComputedFields_ / dashboard / claim rebuild are too slow for HtmlService
  // dialogs (~30–60s client timeout). Always queue background work instead.
  scheduleDeferredCrmSync_(ctx);
}

/** Queue dashboard/index sync to run after dialog returns (avoids server timeout). */
function scheduleDeferredCrmSync_(item) {
  item = item || {};
  try {
    var props = PropertiesService.getScriptProperties();
    var queue = [];
    try {
      queue = JSON.parse(props.getProperty('crm_deferred_sync') || '[]');
    } catch (e) {}
    queue.push(item);
    props.setProperty('crm_deferred_sync', JSON.stringify(queue));

    // TRIGGER-CHEAP SCHEDULING. ScriptApp trigger calls (getProjectTriggers /
    // delete / create) are among the slowest Apps Script APIs (~1–3s each), and a
    // booking save reaches this function 2–3 times — the churn alone added many
    // seconds per save. So: only touch triggers if we haven't created one in the
    // last 60s (property timestamp). Self-healing is preserved — a crashed worker
    // just means the NEXT schedule after 60s replaces the stale trigger, and the
    // minute safety-net (onTimeTriggerRefresh_) drains the queue meanwhile.
    var now = Date.now();
    var lastAt = Number(props.getProperty('crm_deferred_trigger_at') || 0);
    if (now - lastAt > 60000) {
      ScriptApp.getProjectTriggers().forEach(function (t) {
        if (t.getHandlerFunction() === 'processDeferredCrmSync_') ScriptApp.deleteTrigger(t);
      });
      ScriptApp.newTrigger('processDeferredCrmSync_').timeBased().after(2000).create();
      props.setProperty('crm_deferred_trigger_at', String(now));
    }
  } catch (e) {
    Logger.log('scheduleDeferredCrmSync_: ' + e.message);
  }
}

/** Time-based trigger handler — runs heavy sync after form save completes. */
function processDeferredCrmSync_() {
  // Clean our own stale one-shot triggers FIRST — a prior crashed run must never
  // be able to wedge future scheduling (see scheduleDeferredCrmSync_).
  try {
    ScriptApp.getProjectTriggers().forEach(function (t) {
      if (t.getHandlerFunction() === 'processDeferredCrmSync_') ScriptApp.deleteTrigger(t);
    });
  } catch (tErr) {}

  var props = PropertiesService.getScriptProperties();
  // Clear the trigger-created timestamp: this run consumes the trigger, so the
  // next schedule (even seconds from now) must be allowed to create a new one.
  try { props.deleteProperty('crm_deferred_trigger_at'); } catch (tsErr) {}
  var queue = [];
  try {
    queue = JSON.parse(props.getProperty('crm_deferred_sync') || '[]');
  } catch (e) {}
  props.deleteProperty('crm_deferred_sync');

  var needClaimRebuild = false;
  var needDashboard = false;
  var earningsLeads = {};
  queue.forEach(function (item) {
    try {
      if (item.indexEntry) upsertRelationshipIndex_(item.indexEntry);
      else if (item.leadId) upsertRelationshipIndex_({ LeadID: item.leadId });
    } catch (e) {
      Logger.log('Deferred index [' + (item.leadId || '?') + ']: ' + e.message);
    }
    if (item.runEstimate && item.leadId && typeof syncLeadCommercialEstimate_ === 'function') {
      try { syncLeadCommercialEstimate_(item.leadId); } catch (estErr) {
        Logger.log('Deferred estimate [' + item.leadId + ']: ' + estErr.message);
      }
    }
    if (item.leadId && (item.reason === 'booking' || item.reason === 'scheme_update' ||
        item.reason === 'payment' || item.reason === 'delivery' || item.reason === 'deferred')) {
      earningsLeads[item.leadId] = true;
    }
    // Delivery moved its insurance + incentive upserts here (off the save lock).
    if (item.reason === 'delivery' && item.leadId) {
      try {
        if (typeof upsertInsuranceEntryForLead_ === 'function' && item.insurerName) {
          upsertInsuranceEntryForLead_(item.leadId, {
            insuranceCompany: item.insurerName,
            deliveryDate: item.deliveryDate,
            insuranceStatus: item.insuranceStatus
          });
        }
      } catch (diErr) { Logger.log('Deferred insurance [' + item.leadId + ']: ' + diErr.message); }
      try {
        if (typeof upsertIncentiveRegisterOnDelivery_ === 'function') {
          upsertIncentiveRegisterOnDelivery_(item.leadId, item.deliveryDate);
        }
      } catch (dncErr) { Logger.log('Deferred incentive [' + item.leadId + ']: ' + dncErr.message); }
    }
    // Finance file upsert moved off the payment save lock (Finance-mode payments
    // were tripping the client watchdog). Perform it here.
    if (item.financeUpsert) {
      try {
        if (typeof upsertFinanceFilePayment_ === 'function') {
          upsertFinanceFilePayment_(item.financeUpsert);
        }
      } catch (fuErr) { Logger.log('Deferred finance upsert: ' + fuErr.message); }
    }
    if (item.reason === 'booking' || item.reason === 'scheme_update') needClaimRebuild = true;
    if (item.dashboard !== false || item.reason === 'payment') needDashboard = true;
  });

  // Dealer Earnings — cold path, but MUST run for every queued leadId that had a
  // commercial change. Force-fresh upsert (see upsertDealerEarningsForLead_).
  Object.keys(earningsLeads).forEach(function (lid) {
    try {
      if (typeof upsertDealerEarningsForLead_ === 'function') upsertDealerEarningsForLead_(lid, { reason: 'deferred' });
      else if (typeof upsertExtraIncomeForLead_ === 'function') upsertExtraIncomeForLead_(lid, { reason: 'deferred' });
    } catch (deErr) {
      Logger.log('Deferred earnings [' + lid + ']: ' + deErr.message);
    }
  });

  try {
    syncComputedFields_({ dashboard: needDashboard });
    if (typeof refreshExecutiveScorecard_ === 'function') refreshExecutiveScorecard_();
    if (typeof refreshDealerDailyRegister_ === 'function') refreshDealerDailyRegister_();
    if (typeof refreshFinancePendingView_ === 'function') refreshFinancePendingView_();
    if (typeof refreshFinanceOverdueView_ === 'function') refreshFinanceOverdueView_();
  } catch (e2) {
    Logger.log('Deferred sync: ' + e2.message);
  }
  if (needClaimRebuild) {
    try {
      rebuildSchemeClaimRegister_();
    } catch (e3) {
      Logger.log('Deferred claim register: ' + e3.message);
    }
    // Re-upsert earnings after claim rebuild so Claim Status on earnings matches.
    Object.keys(earningsLeads).forEach(function (lid) {
      try {
        if (typeof upsertDealerEarningsForLead_ === 'function') {
          upsertDealerEarningsForLead_(lid, { reason: 'post_claim_rebuild', rebuildAnalytics: false });
        }
      } catch (de2) {
        Logger.log('Post-claim earnings [' + lid + ']: ' + de2.message);
      }
    });
  }
  try {
    if (Object.keys(earningsLeads).length && typeof rebuildDealerEarningsAnalytics_ === 'function') {
      rebuildDealerEarningsAnalytics_();
    }
  } catch (eAn) {
    Logger.log('Deferred earnings analytics: ' + eAn.message);
  }
  try {
    syncCountersToSettingsSheet_();
  } catch (e4) {}

  // Backlinks (finding: new Payment Ledger rows had plain Lead IDs until the next
  // manual Refresh All). Batched single-write per column now, so cheap enough to
  // run every worker pass — new rows get their clickable chain automatically.
  try {
    if (typeof navRefreshAllHyperlinks_ === 'function') navRefreshAllHyperlinks_();
  } catch (navErr) {
    Logger.log('Deferred nav links: ' + navErr.message);
  }

  // Heartbeat so the operator can verify the worker actually ran (Audit Log).
  try { logAudit_('DEFERRED_SYNC_OK', 'items=' + queue.length + ' dashboard=' + needDashboard); } catch (hb) {}

  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'processDeferredCrmSync_') ScriptApp.deleteTrigger(t);
  });
}

/**
 * Public fire-and-forget refresh after dialog save (no underscore = callable from HtmlService).
 *
 * V3 hot/cold split: the save must NOT wait for the reporting surface. Mark the
 * store dirty and let the debounced deferred worker rebuild dashboard/views once
 * per burst. (This function's previous synchronous refreshDashboard_() was the
 * second of two identical leaks — the other was refreshCrmAfterDialogSave_ in
 * FixesService — that made every dialog save cost a full store rebuild.)
 */
function refreshCrmAfterDialogSave() {
  try {
    invalidateCrmStore_();
    scheduleDeferredCrmSync_({ reason: 'dialog_save', dashboard: true });
  } catch (dashErr) {
    Logger.log('refreshCrmAfterDialogSave defer: ' + dashErr.message);
    // Fallback: attempt the deferred sync (heavy path)
    try { processDeferredCrmSync_(); } catch (e2) {
      Logger.log('refreshCrmAfterDialogSave fallback: ' + e2.message);
    }
    return { success: false, message: dashErr.message };
  }
  // Queue the heavier column-sync in the background (trigger fires ~2s later).
  try { scheduleDeferredCrmSync_({ dashboard: false }); } catch (e) {}
  return { success: true };
}

/**
 * Lead Register commercial truth fields (Outstanding, scheme mirrors, payable…).
 * Lives in Utils.gs so Payment / Booking / Scheme Update always find it —
 * even when an older BusinessRulesService.gs is still deployed in Apps Script.
 */
function buildLeadCommercialTruthFields_(leadId, store, snapOverride) {
  leadId = String(leadId || '').trim();
  var snap = snapOverride || null;
  if (!snap) {
    store = store || loadCrmStore_();
    var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
    snap = entry ? (entry.full || entry) : null;
  }
  var paid = 0;
  try {
    paid = typeof sumPaymentsForLeadLight_ === 'function'
      ? Number(sumPaymentsForLeadLight_(leadId) || 0)
      : Number((store && store.paymentsByLead && store.paymentsByLead[leadId]) || 0);
  } catch (payErr) {
    try {
      store = store || loadCrmStore_();
      paid = Number(store.paymentsByLead[leadId] || 0);
    } catch (payErr2) { paid = 0; }
  }
  var payable = snap && typeof computeCommercialTotals_ === 'function'
    ? computeCommercialTotals_(snap).customerPayable
    : (snap ? num_(snap.customerPayable) : 0);
  var lead = null;
  try {
    lead = typeof getLeadFromRegisterLight_ === 'function' ? getLeadFromRegisterLight_(leadId) : null;
  } catch (leadErr) {}
  var bookingAmt = lead ? num_(lead.bookingAmount) : 0;
  var customerOs = typeof calcOutstanding_ === 'function'
    ? calcOutstanding_(payable, bookingAmt, paid)
    : Math.max(0, round2_(payable - (paid > 0 ? paid : bookingAmt)));
  var financeOs = 0;
  try {
    financeOs = typeof getFinanceOutstandingForLead_ === 'function'
      ? getFinanceOutstandingForLead_(leadId) : 0;
  } catch (finErr) { financeOs = 0; }
  var totalOs = round2_(customerOs + financeOs);
  var companyOs = 0;
  try {
    if (typeof computeCompanyOutstanding_ === 'function') {
      companyOs = computeCompanyOutstanding_(leadId, store || null);
    }
  } catch (coErr) { companyOs = 0; }
  var fields = {
    'Customer Outstanding': customerOs,
    'Company Outstanding': companyOs,
    'Outstanding Amount': totalOs,
    'Final Outstanding': totalOs,
    'Total Received': paid
  };
  if (snap) {
    var totals = typeof computeCommercialTotals_ === 'function'
      ? computeCommercialTotals_(snap)
      : { totalDiscount: 0, customerPayable: num_(snap.customerPayable), grossVehicleCost: num_(snap.exShowroom) };
    var claim = typeof deriveClaim_ === 'function' ? deriveClaim_(snap, null) : { oemDiscount: 0, dealerDiscount: 0 };
    fields['Consumer Discount'] = num_(snap.consumerDiscount);
    fields['Exchange Bonus'] = num_(snap.exchangeBonus);
    fields['Loyalty Bonus'] = num_(snap.loyaltyBonus);
    fields['Referral Bonus'] = num_(snap.referralBonus);
    fields['DSA Bonus'] = num_(snap.dsaDiscount);
    fields['Additional Discount'] = num_(snap.additionalDiscount);
    fields['Total Discount'] = totals.totalDiscount;
    try {
      if (typeof schemeShareSplitFor_ === 'function' && snap) {
        var split = schemeShareSplitFor_(
          snap.model || '', snap.variant || '', snap.bookingDate || nowDate_(),
          typeof snapshotOemOffers_ === 'function' ? snapshotOemOffers_(snap) : snap
        );
        if (split) {
          fields['OEM Scheme Amount'] = split.companyTotal;
          fields['Dealer Scheme Amount'] = split.dealerTotal;
          fields['Company Outstanding'] = companyOs;
        } else {
          fields['OEM Scheme Amount'] = claim.oemDiscount;
          fields['Dealer Scheme Amount'] = claim.dealerDiscount;
        }
      } else if (typeof computeSchemeShareSplit_ === 'function') {
        var split2 = computeSchemeShareSplit_(leadId, store);
        if (split2) {
          fields['OEM Scheme Amount'] = split2.companyTotal;
          fields['Dealer Scheme Amount'] = split2.dealerTotal;
          fields['Company Outstanding'] = companyOs;
        } else {
          fields['OEM Scheme Amount'] = claim.oemDiscount;
          fields['Dealer Scheme Amount'] = claim.dealerDiscount;
        }
      } else {
        fields['OEM Scheme Amount'] = claim.oemDiscount;
        fields['Dealer Scheme Amount'] = claim.dealerDiscount;
      }
    } catch (eSplit) {
      fields['OEM Scheme Amount'] = claim.oemDiscount;
      fields['Dealer Scheme Amount'] = claim.dealerDiscount;
    }
    fields['Customer Payable'] = totals.customerPayable;
    if (snap.exShowroom != null) fields['Ex Showroom'] = num_(snap.exShowroom);
    if (snap.registrationRto != null) fields['RTO'] = num_(snap.registrationRto);
    if (snap.insurance != null) fields['Insurance Amount'] = num_(snap.insurance);
    if (snap.accessories != null) fields['Accessories Amount'] = num_(snap.accessories);
    if (snap.handlingCharges != null) fields['Handling Charges'] = num_(snap.handlingCharges);
    if (snap.trc != null) fields['TRC'] = num_(snap.trc);
    if (snap.fastag != null) fields['Fastag'] = num_(snap.fastag);
    if (snap.extendedWarranty != null) fields['Extended Warranty'] = num_(snap.extendedWarranty);
    if (snap.otherCharges != null) fields['Other Charges'] = num_(snap.otherCharges);
    if (totals.grossVehicleCost != null) fields['Gross Vehicle Cost'] = totals.grossVehicleCost;
    if (snap.financer) fields['Financer Name'] = snap.financer;
  } else {
    try {
      store = store || loadCrmStore_();
      var lead2 = (store.leads && store.leads.byId && store.leads.byId[leadId]) || lead || {};
      var model = String(lead2.interestedModel || '').trim();
      var variant = String(lead2.variant || '').trim();
      if (model && variant && typeof getCommercialBreakup_ === 'function') {
        var breakup = getCommercialBreakup_(model, variant, nowDate_());
        var price = breakup.price || {};
        var est = typeof calcPriceTotals_ === 'function' ? calcPriceTotals_(price, {}, 0) : {};
        fields['Ex Showroom'] = price.exShowroom;
        fields['RTO'] = price.registrationRto;
        fields['Insurance Amount'] = price.insurance;
        fields['Accessories Amount'] = price.accessories;
        fields['Handling Charges'] = price.handlingCharges;
        fields['TRC'] = price.trc;
        fields['Fastag'] = price.fastag;
        fields['Extended Warranty'] = price.extendedWarranty;
        fields['Other Charges'] = price.otherCharges;
        fields['Gross Vehicle Cost'] = breakup.grossVehicleCost;
        fields['Customer Payable'] = est.customerPayable;
      }
    } catch (ePm) {}
  }
  try {
    if (typeof getLatestPaymentMetaForLead_ === 'function') {
      var payMeta = getLatestPaymentMetaForLead_(leadId, store);
      if (payMeta) {
        if (payMeta.mode) fields['Last Payment Mode'] = payMeta.mode;
        if (payMeta.financer) fields['Financer Name'] = payMeta.financer;
        if (payMeta.fileNumber) fields['Finance File Number'] = payMeta.fileNumber;
      }
    }
    if (typeof readAllFinanceFiles_ === 'function') {
      var files = readAllFinanceFiles_().filter(function (f) { return f.leadId === leadId; });
      if (files.length) {
        var open = files.filter(function (f) { return Number(f.fileOutstanding) > 0.01; });
        var pick = open.length ? open[0] : files[files.length - 1];
        if (pick.fileNumber) fields['Finance File Number'] = pick.fileNumber;
        if (pick.financer) fields['Financer Name'] = pick.financer;
      }
    }
  } catch (e) {}
  return fields;
}
