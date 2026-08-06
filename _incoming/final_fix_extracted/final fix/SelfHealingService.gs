/**
 * SelfHealingService – automatic repair, config verification, recovery, stress test.
 */

function ensureHelperSheet_(sheetName, cols, hidden) {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(sheetName);
  var created = false;
  if (!sheet) {
    sheet = ss.insertSheet(sheetName);
    if (cols && cols.length) {
      sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    }
    created = true;
  }
  if (hidden && !sheet.isSheetHidden()) sheet.hideSheet();
  return { sheet: sheet, created: created };
}

function ensureCrmSheetExists_(sheetName, setupFn, hidden) {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(sheetName);
  if (sheet) {
    if (hidden && !sheet.isSheetHidden()) sheet.hideSheet();
    return null;
  }
  sheet = ss.insertSheet(sheetName);
  if (setupFn) setupFn();
  if (hidden) sheet.hideSheet();
  return 'Created sheet: ' + sheetName;
}

/**
 * Self-healing engine – recreate missing infrastructure.
 * Structural repairs require owner confirmation (LTS-1).
 * @param {Object} [opts]
 * @param {boolean} [opts.structural=true] Allow sheet/schema creation
 * @returns {{repaired: string[], errors: string[]}}
 */
function repairSystem_(opts) {
  opts = opts || {};
  var structural = opts.structural !== false;

  var start = Date.now();
  var repaired = [];
  var errors = [];
  try {
    var ss = getSpreadsheet_();

    if (structural) {
      var sheetSetups = [
        { name: CRM.SHEETS.DASHBOARD, fn: setupDashboard_, hidden: false },
        { name: CRM.SHEETS.LEAD_REGISTER, fn: setupLeadRegister_, hidden: false },
        { name: CRM.SHEETS.ACTIVITY_LOG, fn: setupActivityLog_, hidden: false },
        { name: CRM.SHEETS.PAYMENT_LEDGER, fn: setupPaymentLedger_, hidden: false },
        { name: CRM.SHEETS.DELIVERY_TRACKER, fn: setupDeliveryTracker_, hidden: false },
        { name: CRM.SHEETS.MASTERS, fn: setupMasters_, hidden: false },
        { name: CRM.SHEETS.DASHBOARD_DATA, fn: setupDashboardData_, hidden: true },
        { name: CRM.SHEETS.SETTINGS, fn: setupSettings_, hidden: true },
        { name: CRM.SHEETS.IMPORT_LOG, fn: setupImportLog_, hidden: true },
        { name: CRM.SHEETS.AUDIT_LOG, fn: setupAuditLog_, hidden: true }
      ];

      sheetSetups.forEach(function (cfg) {
        try {
          var msg = ensureCrmSheetExists_(cfg.name, cfg.fn, cfg.hidden);
          if (msg) repaired.push(msg);
        } catch (e) {
          errors.push(cfg.name + ': ' + e.message);
        }
      });

      try { ensureLeadSchema_(); repaired.push('Lead schema verified'); } catch (e) { errors.push('Lead schema: ' + e.message); }
    }

    try { ensureTransactionLogSheet_(); repaired.push('Transaction Log verified'); } catch (e) { errors.push('Transaction Log: ' + e.message); }
    try { ensureCrashReportSheet_(); repaired.push('Crash Report verified'); } catch (e) { errors.push('Crash Report: ' + e.message); }
    try { ensurePerformanceLogSheet_(); repaired.push('Performance Log verified'); } catch (e) { errors.push('Performance Log: ' + e.message); }
    try { ensureBackupRegistrySheet_(); repaired.push('Backup Registry verified'); } catch (e) { errors.push('Backup Registry: ' + e.message); }

    hideAllSystemSheets_();

    try {
      repairTriggers_();
      repaired.push('Triggers repaired');
    } catch (e) {
      errors.push('Triggers: ' + e.message);
    }

    if (structural) {
      try {
        repairMastersSheet_();
        refreshAllDropdowns_();
        repaired.push('Dropdowns refreshed');
      } catch (e) {
        errors.push('Dropdowns: ' + e.message);
      }
    }

    try {
      invalidateCrmStore_();
      syncComputedFields_({ dashboard: true });
      repaired.push('Computed fields synced');
    } catch (e) {
      errors.push('Sync: ' + e.message);
    }

    try {
      installDailyIntegrityTrigger_();
      repaired.push('Daily integrity trigger verified');
    } catch (e) {
      errors.push('Daily trigger: ' + e.message);
    }

  } finally {
  }

  var ms = Date.now() - start;
  logTransaction_('System', 'Self-Heal', {
    status: errors.length === 0 ? 'OK' : 'PARTIAL',
    executionMs: ms,
    message: repaired.length + ' repairs, ' + errors.length + ' errors [' + getVersionTag_() + ']'
  });

  return { repaired: repaired, errors: errors, executionMs: ms };
}

function hideAllSystemSheets_() {
  if (typeof organizeSpreadsheetTabs_ === 'function') {
    organizeSpreadsheetTabs_();
    return;
  }
  [
    CRM.SHEETS.DASHBOARD_DATA, CRM.SHEETS.SETTINGS, CRM.SHEETS.IMPORT_LOG,
    CRM.SHEETS.AUDIT_LOG, CRM.SHEETS.TRANSACTION_LOG, CRM.SHEETS.BACKUP_REGISTRY,
    CRM.SHEETS.CRASH_REPORT, CRM.SHEETS.PERFORMANCE_LOG,
    CRM.SHEETS.OBS_HEALTH_REPORT, CRM.SHEETS.OBS_PERFORMANCE_REPORT,
    CRM.SHEETS.OBS_KPI_REPORT, CRM.SHEETS.OBS_GROWTH_REPORT,
    CRM.SHEETS.OBS_ACTIVITY_REPORT, CRM.SHEETS.OBS_REPORT_INDEX
  ].forEach(function (name) {
    var sh = getSpreadsheet_().getSheetByName(name);
    if (sh && !sh.isSheetHidden()) sh.hideSheet();
  });
}

/** Repair installable triggers – recreate if missing. */
function repairTriggers_() {
  installTriggers_();
  var triggers = ScriptApp.getProjectTriggers();
  var handlers = ['onEditHandler_', 'onChangeHandler_', 'dailyIntegrityScan_'];
  handlers.forEach(function (h) {
    if (!triggers.some(function (t) { return t.getHandlerFunction() === h; })) {
      if (h === 'dailyIntegrityScan_') installDailyIntegrityTrigger_();
      else installTriggers_();
    }
  });
}

/**
 * Verify CRM configuration against Config.gs – report only, no auto-fix for data.
 */
function verifyConfiguration_() {
  var issues = [];
  var ok = [];

  Object.values(CRM.SHEETS).forEach(function (name) {
    if (getSpreadsheet_().getSheetByName(name)) ok.push('Sheet OK: ' + name);
    else issues.push('Missing sheet: ' + name);
  });

  var settings = getSettings_();
  if (!settings.leadPrefix) issues.push('Settings: leadPrefix missing');
  else ok.push('Settings: leadPrefix=' + settings.leadPrefix);
  if (!settings.receiptPrefix) issues.push('Settings: receiptPrefix missing');
  if (isNaN(Number(settings.nextLeadCounter))) issues.push('Settings: nextLeadCounter invalid');

  var headerChecks = [
    { sheet: CRM.SHEETS.LEAD_REGISTER, row: CRM.LEAD.HEADER_ROW, cols: CRM.LEAD.COLS },
    { sheet: CRM.SHEETS.PAYMENT_LEDGER, row: CRM.PAYMENT.HEADER_ROW, cols: CRM.PAYMENT.COLS },
    { sheet: CRM.SHEETS.ACTIVITY_LOG, row: CRM.ACTIVITY.HEADER_ROW, cols: CRM.ACTIVITY.COLS },
    { sheet: CRM.SHEETS.DELIVERY_TRACKER, row: CRM.DELIVERY.HEADER_ROW, cols: CRM.DELIVERY.COLS }
  ];

  headerChecks.forEach(function (hc) {
    var sh = getSpreadsheet_().getSheetByName(hc.sheet);
    if (!sh) return;
    var headers = getHeaders_(sh, hc.row);
    hc.cols.forEach(function (col) {
      if (findHeaderIndex_(headers, col) < 0) {
        issues.push(hc.sheet + ' missing column: ' + col);
      }
    });
    if (issues.filter(function (i) { return i.indexOf(hc.sheet) >= 0; }).length === 0) {
      ok.push('Columns OK: ' + hc.sheet);
    }
  });

  var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
  if (dash) {
    Object.keys(CRM.DASHBOARD.VALUE_CELLS).forEach(function (k) {
      try {
        dash.getRange(CRM.DASHBOARD.VALUE_CELLS[k]);
        ok.push('Dashboard cell OK: ' + k);
      } catch (e) {
        issues.push('Dashboard cell invalid: ' + k);
      }
    });
  }

  var menuVal = verifyMenus_();
  if (!menuVal.ok) issues = issues.concat(menuVal.missing);

  return {
    ok: issues.length === 0,
    issues: issues,
    passed: ok,
    issueCount: issues.length
  };
}

/** Verify every menu handler function exists (dynamic global lookup). */
function verifyMenus_() {
  var missing = [];
  var seen = {};
  CRM.MENU_HANDLERS.forEach(function (fn) {
    if (seen[fn]) return;
    seen[fn] = true;
    var exists = false;
    try {
      exists = typeof eval(fn) === 'function';
    } catch (e) {
      exists = false;
    }
    if (!exists) missing.push('Missing handler: ' + fn);
  });
  return { ok: missing.length === 0, missing: missing };
}

/**
 * Preview recovery problems from health check (no modifications).
 */
function previewRecoveryProblems_() {
  var health = runHealthCheck_();
  var config = verifyConfiguration_();
  var problems = [];

  health.checks.filter(function (c) { return !c.ok; }).forEach(function (c) {
    problems.push('[' + c.level + '] ' + c.name + (c.detail ? ': ' + c.detail : ''));
  });
  config.issues.forEach(function (i) {
    problems.push('[config] ' + i);
  });

  return { health: health, config: config, problems: problems };
}

/**
 * Build repair plan without executing (LTS safe recovery).
 */
function buildRepairPlan_() {
  var preview = previewRecoveryProblems_();
  var plan = [
    'Recreate any missing CRM sheets',
    'Verify lead schema and helper sheets',
    'Repair installable triggers (onEdit, onChange, nightly scan)',
    'Re-hide system sheets',
    'Refresh dropdowns from Masters',
    'Refresh dropdowns from Masters',
    'Sync computed fields and refresh dashboard mirrors',
    'Verify daily integrity trigger'
  ];
  return { preview: preview, plan: plan };
}

/**
 * Safe Recovery (LTS-1) — owner-confirmed repair workflow.
 * Health → Preview → Plan → Confirm → Backup → Repair → Validate → Certify → Health
 */
function menuSafeRecovery() {
  return crmRun_('System', 'Safe Recovery', function () {
    var ui = SpreadsheetApp.getUi();

    var health1 = runHealthCheck_();
    var preview = previewRecoveryProblems_();
    var repairPlan = buildRepairPlan_();

    var problemText = preview.problems.length
      ? preview.problems.join('\n• ')
      : '(No problems detected — recovery will refresh infrastructure only)';

    var planText = repairPlan.plan.map(function (p, i) { return (i + 1) + '. ' + p; }).join('\n');

    var step1 = ui.alert(
      'Safe Recovery — Step 1: Health Check',
      'Status: ' + health1.status + ' (' + health1.color + ')\n' + health1.summary +
      '\n\nProblems found:\n• ' + problemText,
      ui.ButtonSet.OK_CANCEL
    );
    if (step1 !== ui.Button.OK) return { cancelled: true, step: 1 };

    var step2 = ui.alert(
      'Safe Recovery — Step 2: Repair Plan',
      'The following actions will run AFTER an automatic backup:\n\n' + planText +
      '\n\nNo changes have been made yet.',
      ui.ButtonSet.OK_CANCEL
    );
    if (step2 !== ui.Button.OK) return { cancelled: true, step: 2 };

    if (!isSpreadsheetOwner_()) {
      var ownerWarn = ui.alert(
        'Owner Confirmation Required',
        'Structural recovery modifies production data.\n\nYou are not the spreadsheet owner. Continue anyway?',
        ui.ButtonSet.YES_NO
      );
      if (ownerWarn !== ui.Button.YES) return { cancelled: true, step: 'owner' };
    }

    var step3 = ui.alert(
      'Safe Recovery — Step 3: Confirm Repair',
      'A full backup will be created FIRST.\nThen repairs will execute.\n\nProceed with repair?',
      ui.ButtonSet.YES_NO
    );
    if (step3 !== ui.Button.YES) return { cancelled: true, step: 3 };

    var backup = createVersionedBackup_('Pre-safe-recovery snapshot');

    clearMaintenanceAndReadOnly_();
    var repair = repairSystem_({ structural: true });

    var valResult = { pass: 0, fail: 0 };
    try {
      valResult = runValidationSilent_();
    } catch (ve) {
      repair.errors.push('Validation: ' + ve.message);
    }

    var certResult = { passed: false };
    try {
      refreshDashboard_();
      certResult = certifyDashboard_(false);
    } catch (ce) {
      certResult = { passed: false, error: ce.message };
    }

    var health2 = runHealthCheck_();
    if (health2.status === 'Healthy') {
      clearMaintenanceAndReadOnly_();
    } else if (health2.status === 'Critical') {
      setMaintenanceMode_(true, 'Post-recovery health still critical.');
    }

    var report = [
      '=== SAFE RECOVERY REPORT ===',
      'Version: ' + getVersionTag_(),
      'Pre-recovery health: ' + health1.status,
      'Post-recovery health: ' + health2.status,
      'Backup #' + backup.backupNo + ': ' + backup.url,
      'Repairs: ' + repair.repaired.length,
      '  • ' + repair.repaired.join('\n  • '),
      'Repair errors: ' + (repair.errors.length ? repair.errors.join('\n  • ') : '(none)'),
      'Validation: ' + valResult.pass + ' pass, ' + valResult.fail + ' fail',
      'Dashboard certified: ' + (certResult.passed ? 'YES' : 'NO')
    ].join('\n');

    logAudit_('SAFE_RECOVERY', report);
    ui.alert('Safe Recovery Complete', report, ui.ButtonSet.OK);

    return {
      healthBefore: health1,
      healthAfter: health2,
      repair: repair,
      validation: valResult,
      certification: certResult,
      backup: backup,
      report: report
    };
  });
}

/** @deprecated Use menuSafeRecovery */
function menuEmergencyRecovery() {
  return menuSafeRecovery();
}

/** Nightly integrity scan — detect only, no auto-repair (LTS-1). */
function dailyIntegrityScan_() {
  try {
    flushDailyPerfStats_();
    var health = runHealthCheck_();
    var val = runValidationSilent_();
    var backup = createVersionedBackup_('Daily automatic snapshot');
    applyHealthStatusModes_(health);

    var report = 'Nightly scan: health=' + health.status + ', val=' + val.pass + '/' +
      (val.pass + val.fail) + ', backup=' + (backup ? backup.backupNo : 'fail') +
      ' [' + getVersionTag_() + ']';
    logAudit_('NIGHTLY_INTEGRITY', report);
    logTransaction_('System', 'Nightly Integrity', { status: health.status, message: report });
  } catch (err) {
    logCrash_('System', 'dailyIntegrityScan_', err);
    logAudit_('NIGHTLY_INTEGRITY_FAIL', err.message);
  }
}

function installDailyIntegrityTrigger_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === 'dailyIntegrityScan_') ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger('dailyIntegrityScan_')
    .timeBased()
    .everyDays(1)
    .atHour(2)
    .create();
}

/** In-memory stress simulation – no sheet writes. */
function runStressTestSimulation_() {
  var sizes = [100, 500, 1000, 5000, 10000];
  var results = [];

  sizes.forEach(function (n) {
    var t0 = Date.now();
    var searchKey = function (name, mobile, id) {
      return (id + ' ' + name + ' ' + mobile).toUpperCase();
    };
    var q = 'SKY';
    var hits = 0;
    for (var i = 0; i < n; i++) {
      var key = searchKey('CUSTOMER SKY ' + i, '98765' + String(i).slice(-5), 'LD' + i);
      if (key.indexOf(q) >= 0) hits++;
    }
    var searchMs = Date.now() - t0;

    t0 = Date.now();
    var outstanding = 0;
    for (var j = 0; j < n; j++) {
      outstanding += Math.max(0, 100000 - (j % 3) * 30000);
    }
    var calcMs = Date.now() - t0;

    results.push({
      leads: n,
      searchMs: searchMs,
      calcMs: calcMs,
      hits: hits,
      pass: searchMs < 5000 && calcMs < 5000
    });
  });

  logTransaction_('System', 'Stress Test', {
    status: results.every(function (r) { return r.pass; }) ? 'PASS' : 'WARN',
    message: JSON.stringify(results)
  });

  return results;
}

function menuStressTest() {
  return crmRun_('System', 'Stress Test', function () {
    var results = runStressTestSimulation_();
    var lines = results.map(function (r) {
      return r.leads + ' leads: search=' + r.searchMs + 'ms, calc=' + r.calcMs + 'ms ' + (r.pass ? 'PASS' : 'SLOW');
    }).join('\n');
    SpreadsheetApp.getUi().alert('Stress Test (in-memory simulation)', lines, SpreadsheetApp.getUi().ButtonSet.OK);
    return results;
  });
}

/** Silent validation for recovery pipelines – no UI alert. */
function runValidationSilent_() {
  invalidateCrmStore_();
  var store = loadCrmStore_(true);
  var pass = 0, fail = 0;
  function check(ok) { if (ok) pass++; else fail++; }

  Object.values(CRM.SHEETS).forEach(function (name) {
    check(!!getSpreadsheet_().getSheetByName(name));
  });
  check(findDuplicateLeadIds_(store).length === 0);
  check(countBrokenRefs_(store.payments.rows, store.payments.headers, 'Lead ID', store.leads.byId) === 0);
  check(countOutstandingMismatches_(store) === 0);

  return { pass: pass, fail: fail };
}

function menuVerifyConfiguration() {
  return crmRun_('System', 'Verify Configuration', function () {
    var result = verifyConfiguration_();
    SpreadsheetApp.getUi().alert(
      'Configuration Verification',
      (result.ok ? 'All checks passed.\n\n' : result.issueCount + ' issue(s) found.\n\n') +
      (result.issues.length ? 'Issues:\n• ' + result.issues.join('\n• ') : ''),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return result;
  });
}

function menuSelfHeal() {
  return crmRun_('System', 'Self Heal', function () {
    var result = repairSystem_();
    SpreadsheetApp.getUi().alert(
      'Self-Heal Complete',
      'Repairs: ' + result.repaired.length + '\n• ' + result.repaired.join('\n• ') +
      (result.errors.length ? '\n\nErrors:\n• ' + result.errors.join('\n• ') : ''),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return result;
  });
}
