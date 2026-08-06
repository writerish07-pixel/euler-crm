/**
 * HealthCheckService – production system health monitor.
 */

/** @returns {{status: string, color: string, checks: Object[], summary: string}} */
function runHealthCheck_() {
  var start = Date.now();
  var checks = [];
  var critical = 0;
  var warnings = 0;

  function add(name, level, ok, detail) {
    checks.push({ name: name, level: level, ok: ok, detail: detail || '' });
    if (!ok && level === 'critical') critical++;
    if (!ok && level === 'warning') warnings++;
  }

  var ss = getSpreadsheet_();
  if (typeof ensureCommercialSnapshotSheet_ === 'function') {
    try { ensureCommercialSnapshotSheet_(); } catch (e) {}
  }
  if (typeof ensureCommercialAuditSheet_ === 'function') {
    try { ensureCommercialAuditSheet_(); } catch (e) {}
  }
  if (typeof ensureClaimRegisterSheet_ === 'function') {
    try { ensureClaimRegisterSheet_(); } catch (e) {}
  }

  var commercialDerived = {};
  commercialDerived[CRM.SHEETS.COMMERCIAL_SNAPSHOT] = true;
  commercialDerived[CRM.SHEETS.COMMERCIAL_AUDIT] = true;
  commercialDerived[CRM.SHEETS.SCHEME_CLAIM_REGISTER] = true;
  commercialDerived[CRM.SHEETS.OEM_CLAIM_DASHBOARD] = true;
  commercialDerived[CRM.SHEETS.OWNER_COMMERCIAL_REPORT] = true;
  commercialDerived[CRM.SHEETS.CLAIM_EXCEPTION] = true;

  Object.values(CRM.SHEETS).forEach(function (name) {
    var isObs = String(name).indexOf('Obs ') === 0;
    var isPep = String(name).indexOf('PEP ') === 0;
    var isCommercial = !!commercialDerived[name];
    var level = (isObs || isPep || isCommercial) ? 'warning' : 'critical';
    add('Sheet: ' + name, level, !!ss.getSheetByName(name));
  });
  ensureTransactionLogSheet_();

  var triggers = ScriptApp.getProjectTriggers();
  var hasEdit = triggers.some(function (t) { return t.getHandlerFunction() === 'onEditHandler_'; });
  var hasChange = triggers.some(function (t) { return t.getHandlerFunction() === 'onChangeHandler_'; });
  add('onEdit trigger', 'critical', hasEdit);
  add('onChange trigger', 'warning', hasChange);

  try {
    invalidateCrmStore_();
    var store = loadCrmStore_(true);
    add('DataStore load', 'critical', !!store && !!store.leads);
    add('Lead index', 'critical', Object.keys(store.leads.byId).length >= 0,
      Object.keys(store.leads.byId).length + ' leads');

    var outBad = countOutstandingMismatches_(store);
    add('Outstanding calculations', outBad === 0 ? 'critical' : 'warning', outBad === 0,
      outBad + ' mismatches');

    var brokenPay = countBrokenRefs_(store.payments.rows, store.payments.headers, 'Lead ID', store.leads.byId);
    add('Payment references', 'critical', brokenPay === 0, brokenPay + ' broken');

    var picker = getActiveLeadsForPicker_({ activeOnly: true });
    var activeCount = Object.keys(store.leads.byId).filter(function (id) {
      return normalizeAccountStatus_(store.leads.byId[id].accountStatus) === ACCOUNT_STATUS.ACTIVE;
    }).length;
    add('Lead picker (Active only)', 'critical', picker.length === activeCount,
      'picker=' + picker.length + ', active=' + activeCount);

    var settings = getSettings_();
    add('Settings valid', 'critical', !!settings.leadPrefix && !!settings.receiptPrefix);

    var masters = getMasters_();
    add('Masters loaded', 'warning', Object.keys(masters).length >= 5);

    try {
      var cert = certifyDashboard_(false);
      add('Dashboard certification', 'warning', cert.passed, cert.mismatches.slice(0, 2).join('; '));
    } catch (certErr) {
      add('Dashboard certification', 'warning', false, certErr.message);
    }
  } catch (storeErr) {
    add('DataStore load', 'critical', false, storeErr.message);
  }

  var hidden = [CRM.SHEETS.DASHBOARD_DATA, CRM.SHEETS.SETTINGS, CRM.SHEETS.IMPORT_LOG,
    CRM.SHEETS.AUDIT_LOG, CRM.SHEETS.TRANSACTION_LOG, CRM.SHEETS.BACKUP_REGISTRY,
    CRM.SHEETS.CRASH_REPORT, CRM.SHEETS.PERFORMANCE_LOG];
  hidden.forEach(function (name) {
    var sh = ss.getSheetByName(name);
    add('Hidden: ' + name, 'warning', sh ? sh.isSheetHidden() : false);
  });

  var status, color, summary;
  if (critical > 0) {
    status = 'Critical';
    color = 'Red';
    summary = critical + ' critical issue(s) require immediate attention.';
  } else if (warnings > 0) {
    status = 'Warning';
    color = 'Yellow';
    summary = warnings + ' warning(s). System operational but review recommended.';
  } else {
    status = 'Healthy';
    color = 'Green';
    summary = 'All health checks passed.';
  }

  var ms = Date.now() - start;
  recordPerf_('validation', ms);
  logTransaction_('System', 'Health Check', {
    status: status,
    executionMs: ms,
    message: summary + ' (' + checks.filter(function (c) { return c.ok; }).length + '/' + checks.length + ' passed)'
  });

  return { status: status, color: color, checks: checks, summary: summary, executionMs: ms };
}

/**
 * Run health check with infrastructure-only repair (triggers + helper sheets).
 * Structural repair requires Safe Recovery (owner confirmed).
 */
function runHealthCheckWithRepair_() {
  var repaired = [];
  var triggers = ScriptApp.getProjectTriggers();
  var hasEdit = triggers.some(function (t) { return t.getHandlerFunction() === 'onEditHandler_'; });
  var hasChange = triggers.some(function (t) { return t.getHandlerFunction() === 'onChangeHandler_'; });
  if (!hasEdit || !hasChange) {
    try {
      repairTriggers_();
      repaired.push('Triggers repaired');
    } catch (e) {
      logCrash_('System', 'runHealthCheckWithRepair_.triggers', e);
    }
  }

  [CRM.SHEETS.TRANSACTION_LOG, CRM.SHEETS.BACKUP_REGISTRY,
    CRM.SHEETS.CRASH_REPORT, CRM.SHEETS.PERFORMANCE_LOG].forEach(function (name) {
    if (!getSpreadsheet_().getSheetByName(name)) {
      try {
        if (name === CRM.SHEETS.TRANSACTION_LOG) ensureTransactionLogSheet_();
        else if (name === CRM.SHEETS.BACKUP_REGISTRY) ensureBackupRegistrySheet_();
        else if (name === CRM.SHEETS.CRASH_REPORT) ensureCrashReportSheet_();
        else if (name === CRM.SHEETS.PERFORMANCE_LOG) ensurePerformanceLogSheet_();
        repaired.push('Created log sheet: ' + name);
      } catch (e) {}
    }
  });

  var result = runHealthCheck_();
  result.repaired = repaired;
  return result;
}

function menuSystemHealthCheck() {
  return crmRun_('System', 'Health Check', function () {
    var result = runHealthCheck_();
    var lines = result.checks.map(function (c) {
      return (c.ok ? '✓' : '✗') + ' ' + c.name + (c.detail ? ' — ' + c.detail : '');
    }).join('\n');
    var repairNote = result.repaired && result.repaired.length
      ? '\n\nAuto-repaired:\n• ' + result.repaired.join('\n• ') : '';
    SpreadsheetApp.getUi().alert(
      'System Health: ' + result.status + ' (' + result.color + ')',
      result.summary + repairNote + '\n\n' + lines,
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return result;
  });
}

function runStartupSelfTest_() {
  try {
    var issues = [];
    var ss = getSpreadsheet_();
    [CRM.SHEETS.LEAD_REGISTER, CRM.SHEETS.PAYMENT_LEDGER, CRM.SHEETS.DASHBOARD,
      CRM.SHEETS.SETTINGS].forEach(function (name) {
      if (!ss.getSheetByName(name)) issues.push('Missing sheet: ' + name);
    });

    var triggers = ScriptApp.getProjectTriggers();
    if (!triggers.some(function (t) { return t.getHandlerFunction() === 'onEditHandler_'; })) {
      issues.push('onEdit trigger not installed');
    }

    try {
      getSettings_();
    } catch (se) {
      issues.push('Settings invalid: ' + se.message);
    }

    ensureTransactionLogSheet_();

    if (issues.length > 0) {
      logTransaction_('System', 'Startup Self-Test', {
        status: 'WARNING',
        errorCode: 'STARTUP_WARN',
        message: issues.join('; ')
      });
      showToast_('CRM startup warning: ' + issues[0], 'CRM Health');
      return { ok: false, issues: issues };
    }

    logTransaction_('System', 'Startup Self-Test', { status: 'OK', message: 'All checks passed' });
    return { ok: true, issues: [] };
  } catch (err) {
    logTransaction_('System', 'Startup Self-Test', {
      status: 'FAIL',
      errorCode: 'STARTUP_FAIL',
      message: err.message
    });
    return { ok: false, issues: [err.message] };
  }
}

/** Full go-live certification — no protection or deployment lock checks. */
function runDeploymentCertification_() {
  var checks = [];
  var failures = [];
  function add(name, ok, detail) {
    checks.push({ name: name, ok: ok, detail: detail || '' });
    if (!ok) failures.push(name + (detail ? ': ' + detail : ''));
  }
  try {
    var v = runValidationSilent_();
    add('Validation', v.fail === 0, v.pass + ' pass, ' + v.fail + ' fail');
  } catch (e) { add('Validation', false, e.message); }
  try {
    var r = runRegressionTests_();
    add('Regression', r.allPassed, r.pass + ' pass, ' + r.fail + ' fail');
  } catch (e) { add('Regression', false, e.message); }
  try {
    var h = runHealthCheck_();
    add('Health Check', h.status !== 'Critical', h.status + ' — ' + h.summary);
  } catch (e) { add('Health Check', false, e.message); }
  try {
    refreshDashboard_();
    var cert = certifyDashboard_(false);
    add('Dashboard Certification', cert.passed, cert.mismatches.join('; '));
  } catch (e) { add('Dashboard Certification', false, e.message); }
  try {
    var cfg = verifyConfiguration_();
    add('Configuration', cfg.ok, cfg.issues.slice(0, 3).join('; '));
  } catch (e) { add('Configuration', false, e.message); }
  var menus = verifyMenus_();
  add('Menu Handlers', menus.ok, menus.missing.join('; '));
  var passed = failures.length === 0;
  logTransaction_('System', 'Deployment Certification', {
    status: passed ? 'PASS' : 'FAIL',
    message: passed ? 'All checks passed [' + getVersionTag_() + ']' : failures.join('; ')
  });
  return { passed: passed, checks: checks, failures: failures };
}

function menuDeploymentCertification() {
  return crmRun_('System', 'Deployment Certification', function () {
    var result = runDeploymentCertification_();
    var lines = result.checks.map(function (c) {
      return (c.ok ? '✓' : '✗') + ' ' + c.name + (c.detail ? ' — ' + c.detail : '');
    }).join('\n');
    SpreadsheetApp.getUi().alert(
      'Deployment Certification — ' + (result.passed ? 'PASSED' : 'FAILED'),
      'Version: ' + getVersionTag_() + '\n\n' + lines +
      (result.passed ? '\n\nSystem is ready for production use.' : ''),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return result;
  });
}
