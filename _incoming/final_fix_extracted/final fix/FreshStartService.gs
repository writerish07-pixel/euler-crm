/**
 * FreshStartService – owner-only wipe of leads + related transactional data.
 *
 * CLEARS: all lead-linked operational data + ephemeral drill-down tabs.
 * KEEPS: PRICE MASTER, Masters, Settings, Scheme Master, Incentive Master, Backup Registry.
 * AFTER CLEAR: applies latest commercial / OEM / earnings schema headers.
 */

function clearSheetDataFromRow_(sheet, dataStartRow, numCols) {
  if (!sheet) return 0;
  var lastRow = sheet.getLastRow();
  if (lastRow < dataStartRow) return 0;
  // Always clear full used width so leftover columns are not left behind.
  var cols = Math.max(Number(numCols) || 0, sheet.getLastColumn(), 1);
  var rows = lastRow - dataStartRow + 1;
  var range = sheet.getRange(dataStartRow, 1, rows, cols);
  range.clearContent();
  try { range.clearNote(); } catch (e) {}
  return rows;
}

function clearNamedSheetData_(sheetName, dataStart, numCols) {
  try {
    var sh = getSpreadsheet_().getSheetByName(sheetName);
    if (!sh) return 0;
    return clearSheetDataFromRow_(sh, dataStart || 2, numCols || sh.getLastColumn());
  } catch (e) {
    Logger.log('clearNamedSheetData_ ' + sheetName + ': ' + e.message);
    return 0;
  }
}

/** True for ephemeral KPI / model performance drill-down tabs. */
function isEphemeralDrillDownSheetName_(name) {
  name = String(name || '');
  return /^MP\s*[—\-–]\s*/.test(name) ||
    /^DE\s*[—\-–]\s*/.test(name) ||
    /^Payments\s*[—\-–]\s*/.test(name) ||
    /^Today's\s/.test(name) ||
    name.indexOf('Monthly ') === 0 ||
    name === 'Pending Deliveries' ||
    name === 'Pending Follow-ups' ||
    name === 'Outstanding Leads' ||
    name === 'Navigation Matrix';
}

function clearAllBusinessDataForFreshStart_() {
  var cleared = {};

  cleared.leads = clearNamedSheetData_(CRM.SHEETS.LEAD_REGISTER, CRM.LEAD.DATA_START);
  cleared.activities = clearNamedSheetData_(CRM.SHEETS.ACTIVITY_LOG, CRM.ACTIVITY.DATA_START);
  cleared.payments = clearNamedSheetData_(CRM.SHEETS.PAYMENT_LEDGER, CRM.PAYMENT.DATA_START);
  cleared.deliveries = clearNamedSheetData_(CRM.SHEETS.DELIVERY_TRACKER, CRM.DELIVERY.DATA_START);

  cleared.bookingRegister = clearNamedSheetData_(CRM.SHEETS.BOOKING_REGISTER, 2);
  cleared.relationshipIndex = clearNamedSheetData_(CRM.SHEETS.RELATIONSHIP_INDEX, 2);
  cleared.bookingStatusHistory = clearNamedSheetData_(CRM.SHEETS.BOOKING_STATUS_HISTORY, 2);
  cleared.vehicleAllocation = clearNamedSheetData_(CRM.SHEETS.VEHICLE_ALLOCATION, 2);
  cleared.quotationSchema = clearNamedSheetData_(CRM.SHEETS.QUOTATION_SCHEMA, 2);

  cleared.commercialSnapshot = clearNamedSheetData_(CRM.SHEETS.COMMERCIAL_SNAPSHOT, CRM.COMMERCIAL.DATA_START);
  cleared.commercialAudit = clearNamedSheetData_(CRM.SHEETS.COMMERCIAL_AUDIT, 2);
  cleared.schemeClaim = clearNamedSheetData_(CRM.SHEETS.SCHEME_CLAIM_REGISTER, 2);
  cleared.oemClaimDashboard = clearNamedSheetData_(CRM.SHEETS.OEM_CLAIM_DASHBOARD, 2);
  cleared.ownerCommercial = clearNamedSheetData_(CRM.SHEETS.OWNER_COMMERCIAL_REPORT, 2);
  cleared.claimException = clearNamedSheetData_(CRM.SHEETS.CLAIM_EXCEPTION, 2);

  cleared.financeRegister = clearNamedSheetData_(CRM.SHEETS.FINANCE_REGISTER, 2);
  cleared.financePending = clearNamedSheetData_(CRM.SHEETS.FINANCE_PENDING, 2);
  cleared.financeOverdue = clearNamedSheetData_(CRM.SHEETS.FINANCE_OVERDUE, 2);
  cleared.incentiveRegister = clearNamedSheetData_(CRM.SHEETS.INCENTIVE_REGISTER, 2);

  cleared.insuranceRegister = clearNamedSheetData_(CRM.SHEETS.INSURANCE_REGISTER, 2);
  cleared.dealerEarnings = clearNamedSheetData_(
    CRM.SHEETS.DEALER_EARNINGS_REGISTER || CRM.SHEETS.EXTRA_INCOME_REGISTER, 2);
  cleared.dealerEarningsAnalytics = clearNamedSheetData_(
    CRM.SHEETS.DEALER_EARNINGS_ANALYTICS || CRM.SHEETS.EXTRA_INCOME_ANALYTICS, 2);
  cleared.extraIncomeLegacy = clearNamedSheetData_('Extra Income Register', 2);
  cleared.extraIncomeAnalyticsLegacy = clearNamedSheetData_('Extra Income Analytics', 2);
  cleared.oemExtraSupport = clearNamedSheetData_(
    CRM.SHEETS.OEM_EXTRA_SUPPORT_REGISTER || 'OEM Extra Support Register', 2);
  cleared.quotationLog = clearNamedSheetData_(CRM.SHEETS.QUOTATION_LOG, 2);
  cleared.migrationImportLog = clearNamedSheetData_('Migration Import Log', 2);

  cleared.executiveScorecard = clearNamedSheetData_(CRM.SHEETS.EXECUTIVE_SCORECARD, 2);
  cleared.dealerDaily = clearNamedSheetData_(CRM.SHEETS.DEALER_DAILY_REGISTER, 2);
  cleared.outstandingLeads = clearNamedSheetData_('Outstanding Leads', 2);

  cleared.drillDownSheets = clearLeadLinkedDrillDownSheets_();
  return cleared;
}

function clearLeadLinkedDrillDownSheets_() {
  var cleared = 0;
  try {
    var ss = getSpreadsheet_();
    var keepVisible = (CRM.SHEET_LAYOUT && CRM.SHEET_LAYOUT.VISIBLE_ORDER) || [];
    // Snapshot first — deleting while iterating getSheets() can skip sheets.
    var sheets = ss.getSheets().slice();
    sheets.forEach(function (sh) {
      var name = sh.getName();
      if (keepVisible.indexOf(name) >= 0) return;
      if (!isEphemeralDrillDownSheetName_(name)) return;
      try {
        cleared += clearSheetDataFromRow_(sh, 2, sh.getLastColumn());
        if (/^MP\s*[—\-–]\s*/.test(name) ||
            /^DE\s*[—\-–]\s*/.test(name) ||
            /^Payments\s*[—\-–]\s*/.test(name)) {
          if (ss.getSheets().length > 1) ss.deleteSheet(sh);
        }
      } catch (eDel) {
        Logger.log('clearLeadLinkedDrillDownSheets_ ' + name + ': ' + eDel.message);
      }
    });
  } catch (e) {
    Logger.log('clearLeadLinkedDrillDownSheets_: ' + e.message);
  }
  return cleared;
}

function clearSystemLogsForFreshStart_() {
  var names = [
    { sheet: CRM.SHEETS.IMPORT_LOG, start: 2 },
    { sheet: CRM.SHEETS.AUDIT_LOG, start: (CRM.AUDIT_LOG && CRM.AUDIT_LOG.DATA_START) || 2 },
    { sheet: CRM.SHEETS.TRANSACTION_LOG, start: (CRM.TRANSACTION_LOG && CRM.TRANSACTION_LOG.DATA_START) || 2 },
    { sheet: CRM.SHEETS.CRASH_REPORT, start: (CRM.CRASH_REPORT && CRM.CRASH_REPORT.DATA_START) || 2 },
    { sheet: CRM.SHEETS.PERFORMANCE_LOG, start: (CRM.PERFORMANCE_LOG && CRM.PERFORMANCE_LOG.DATA_START) || 2 }
  ];
  names.forEach(function (entry) {
    try {
      clearNamedSheetData_(entry.sheet, entry.start);
    } catch (e) {}
  });
}

function clearReportSheetsForFreshStart_() {
  if (typeof getObsSheetConfigs_ === 'function') {
    getObsSheetConfigs_().forEach(function (entry) {
      try {
        var sh = getSpreadsheet_().getSheetByName(entry.name);
        if (sh && entry.cfg) {
          clearSheetDataFromRow_(sh, entry.cfg.DATA_START || 2, sh.getLastColumn());
        }
      } catch (e) {}
    });
  }
  if (typeof getPepSheetConfigs_ === 'function') {
    getPepSheetConfigs_().forEach(function (entry) {
      try {
        var sh = getSpreadsheet_().getSheetByName(entry.name);
        if (sh && entry.cfg) {
          clearSheetDataFromRow_(sh, entry.cfg.DATA_START || 2, sh.getLastColumn());
        }
      } catch (e) {}
    });
  }
}

function clearDashboardOwnerPanelsForFreshStart_() {
  var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
  if (!dash) return;
  try { dash.getRange(1, 11, 30, 12).clearContent(); } catch (e) {}
  try { dash.getRange(1, 14, 30, 15).clearContent(); } catch (e) {}
}

function resetIdCountersForFreshStart_() {
  saveSetting_('nextLeadCounter', 1);
  saveSetting_('nextActivityCounter', 1);
  saveSetting_('nextReceiptCounter', 1);
  saveSetting_('nextFinanceFileCounter', 1);
  saveSetting_('nextBookingCounter', 1);
  saveSetting_('nextSnapshotCounter', 1);
  saveSetting_('nextClaimCounter', 1);
  try { saveSetting_('nextPaymentCounter', 1); } catch (e) {}
  try { saveSetting_('nextDeliveryCounter', 1); } catch (e) {}

  try {
    var props = PropertiesService.getScriptProperties();
    props.setProperty('crm_counter_lead', '1');
    props.setProperty('crm_counter_activity', '1');
    props.setProperty('crm_counter_receipt', '1');
    props.setProperty('crm_counter_finance_file', '1');
    try { CacheService.getScriptCache().remove('settings'); } catch (ce) {}
  } catch (e2) {}
}

/** Apply latest schema headers after wipe (OEM Extra Support, dealer margin, etc.). */
function applyFreshStartSchemaUpdates_() {
  try { if (typeof ensureCommercialSnapshotHeaders_ === 'function') ensureCommercialSnapshotHeaders_(); } catch (e1) {}
  try { if (typeof ensureOemExtraSupportRegisterSheet_ === 'function') ensureOemExtraSupportRegisterSheet_(); } catch (e2) {}
  try { if (typeof ensureDealerEarningsRegisterSheet_ === 'function') ensureDealerEarningsRegisterSheet_(); } catch (e3) {}
  try { if (typeof ensureDealerEarningsAnalyticsSheet_ === 'function') ensureDealerEarningsAnalyticsSheet_(); } catch (e4) {}
  try { if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_(); } catch (e5) {}
  try { if (typeof ensureInsuranceRegisterSheet_ === 'function') ensureInsuranceRegisterSheet_(); } catch (e6) {}
  try { if (typeof ensureSchemeAndIncentiveSheets_ === 'function') ensureSchemeAndIncentiveSheets_(); } catch (e7) {}
  try { if (typeof ensureLeadSchema_ === 'function') ensureLeadSchema_(); } catch (e8) {}
  try { if (typeof organizeSpreadsheetTabs_ === 'function') organizeSpreadsheetTabs_(); } catch (e9) {}
}

function executeFreshStart_() {
  var cleared = clearAllBusinessDataForFreshStart_();
  clearSystemLogsForFreshStart_();
  clearReportSheetsForFreshStart_();
  clearDashboardOwnerPanelsForFreshStart_();
  resetIdCountersForFreshStart_();
  applyFreshStartSchemaUpdates_();

  try { clearCache_(); } catch (eC) {}
  try { invalidateCrmStore_(); } catch (eI) {}
  try { if (typeof clearComputedFormulas_ === 'function') clearComputedFormulas_(); } catch (eF) {}
  try { if (typeof syncAll_ === 'function') syncAll_({ dashboard: true }); } catch (eS) {}
  try { if (typeof refreshDashboard_ === 'function') refreshDashboard_(); } catch (eD) {}
  try { if (typeof refreshFinancePendingView_ === 'function') refreshFinancePendingView_(); } catch (eP) {}
  try { if (typeof applyAllConditionalFormatting_ === 'function') applyAllConditionalFormatting_(); } catch (eA) {}
  try { if (typeof buildMenu_ === 'function') buildMenu_(); } catch (eM) {}

  logAudit_('FRESH_START', 'TEST wipe + schema apply. ' +
    'Leads=' + cleared.leads +
    ' Pay=' + cleared.payments +
    ' Snap=' + cleared.commercialSnapshot +
    ' Earn=' + cleared.dealerEarnings +
    ' OemExtra=' + cleared.oemExtraSupport +
    ' Drill=' + cleared.drillDownSheets);

  return {
    cleared: cleared,
    countersReset: true,
    schemaApplied: true,
    kept: [
      'PRICE MASTER',
      'Masters',
      'Settings',
      'Scheme Master',
      'Incentive Master',
      'Backup Registry'
    ],
    version: getVersionTag_()
  };
}

function menuFreshStartClearAllData() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert(
      'Owner Only',
      'Only the spreadsheet owner can run Fresh Start.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }

  var ui = SpreadsheetApp.getUi();
  var pre = ui.alert(
    'Fresh Start — Clear All Test Data',
    'Deletes leads and ALL related transactional data, then applies latest schema.\n\n' +
      'DELETED:\n' +
      '• Lead / Activity / Payment / Delivery / Booking\n' +
      '• Commercial Snapshot + OEM Extra Support Register\n' +
      '• Finance / Insurance / Claims / Dealer Earnings\n' +
      '• Quotation Log + dashboard drill-down tabs\n' +
      '• ID counters reset (next lead = 000001)\n\n' +
      'KEPT:\n' +
      '• PRICE MASTER, Masters, Scheme Master, Incentive Master\n' +
      '• Settings + Backup Registry\n\n' +
      'Tip: run Backup Database first if you want a copy.\n\nContinue?',
    ui.ButtonSet.YES_NO
  );
  if (pre !== ui.Button.YES) return;

  var wrapped = runDestructiveOp_({
    label: 'FRESH_START',
    skipBackup: true,
    confirmTitle: 'Confirm Fresh Start',
    confirmMessage:
      'Final confirmation:\n\n' +
      'All test leads and related data will be deleted.\n' +
      'Latest commercial / OEM Extra Support columns will be applied.\n\n' +
      'Continue?',
    fn: function () {
      return executeFreshStart_();
    }
  });

  if (wrapped.cancelled) return;

  var settings = getSettings_();
  ui.alert(
    'Fresh Start Complete',
    'All test data cleared and latest schema applied.\n\n' +
      'KEPT: Scheme Master, Incentive Master, PRICE MASTER, Masters\n' +
      'Next lead ID: ' + (settings.leadPrefix || 'LD') + '000001\n\n' +
      'Ready for a clean test run.',
    ui.ButtonSet.OK
  );
}

/** Alias — same as Fresh Start (kept for older menu references). */
function menuFreshSetup() {
  return menuFreshStartClearAllData();
}

/**
 * ONE-TIME MIGRATION (owner only): delete duplicate "Booking Status" from Lead Register.
 */
function menuRemoveBookingStatusColumn() {
  var ui = SpreadsheetApp.getUi();
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    ui.alert('Only the spreadsheet owner can run this migration.');
    return;
  }
  var resp = ui.alert('Remove Booking Status Column',
    'This permanently deletes the "Booking Status" column from the Lead Register. ' +
    'Current Status remains the single source of truth. Continue?',
    ui.ButtonSet.YES_NO);
  if (resp !== ui.Button.YES) return;

  try {
    var ss = getSpreadsheet_();
    var sheet = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    if (!sheet) { ui.alert('Lead Register not found.'); return; }
    var headerRow = CRM.LEAD.HEADER_ROW;
    var headers = getHeaders_(sheet, headerRow);
    var idx = findHeaderIndex_(headers, 'Booking Status');
    if (idx < 0) {
      ui.alert('Booking Status column already removed. Nothing to do.');
      return;
    }
    sheet.deleteColumn(idx + 1);
    try { logAudit_('MIGRATION', 'Removed Booking Status column from Lead Register (was col ' + (idx + 1) + ')'); } catch (e) {}
    try { if (typeof navRefreshAllHyperlinks_ === 'function') navRefreshAllHyperlinks_(); } catch (e2) {}
    ui.alert('Booking Status column removed. Current Status is now the only stage field.');
  } catch (err) {
    ui.alert('Migration failed: ' + err.message);
  }
}
