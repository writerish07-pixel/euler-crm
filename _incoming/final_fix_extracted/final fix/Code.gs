/**
 * Code.gs — Euler Motors Dealership CRM v2.1
 *
 * Changes from v2.0:
 *   ✔ onEditHandler_ now ALWAYS calls refreshDashboard_() directly so any
 *     manual cell edit (Payment Ledger, Activity Log, Delivery, Lead Register)
 *     updates the dashboard immediately without a separate Refresh click.
 *   ✔ onChangeHandler_ calls refreshDashboard_() on any INSERT_ROW event.
 *   ✔ installTriggers_() also installs the 1-minute time-based auto-refresh
 *     trigger from FixesService.gs (idempotent).
 *   ✔ Admin submenu gains "Setup Auto-Refresh" and "Remove Auto-Refresh" items.
 *   ✔ Navigate → Navigation Home added (NavigationService.gs).
 */

// ═══════════════════════════════════════════════════════════════════════════
//  STARTUP
// ═══════════════════════════════════════════════════════════════════════════

function onOpen() {
  try {
    buildMenu_();
  } catch (menuErr) {
    try { installBasicCrmMenu_(); } catch (e) {}
  }
  try {
    ensureCoreCrmSheets_();
  } catch (e) {
    Logger.log('onOpen ensureCoreCrmSheets_: ' + e.message);
  }
  try {
    ensureTriggersInstalled_();
  } catch (e) {
    if (typeof logCrash_ === 'function') logCrash_('System', 'onOpen.triggers', e);
  }
  try {
    if (typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_()) {
      runNonCriticalStartupTasks_();
    }
  } catch (e) {
    Logger.log('onOpen startup: ' + e.message);
  }
}

/** Ensure optional sheets exist (Quotation Log, Finance Register) on every open. */
function ensureCoreCrmSheets_() {
  try { if (typeof ensureQuotationLogSheet_ === 'function') ensureQuotationLogSheet_(); } catch (e) {}
  try { if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_(); } catch (e) {}
  try { if (typeof ensureInsuranceRegisterSheet_ === 'function') ensureInsuranceRegisterSheet_(); } catch (e) {}
  try { if (typeof ensureExtraIncomeRegisterSheet_ === 'function') ensureExtraIncomeRegisterSheet_(); } catch (e) {}
  try { if (typeof ensureExtraIncomeAnalyticsSheet_ === 'function') ensureExtraIncomeAnalyticsSheet_(); } catch (e) {}
  try { if (typeof ensureOemExtraSupportRegisterSheet_ === 'function') ensureOemExtraSupportRegisterSheet_(); } catch (e) {}
  try { if (typeof ensureCommercialSnapshotHeaders_ === 'function') ensureCommercialSnapshotHeaders_(); } catch (e) {}
}

function runNonCriticalStartupTasks_() {
  try { if (typeof ensurePhase3Sheets_              === 'function') ensurePhase3Sheets_(); }              catch (e) {}
  try { if (typeof ensureCommercialSnapshotSheet_    === 'function') ensureCommercialSnapshotSheet_(); }    catch (e) {}
  try { if (typeof ensureLeadSchema_                 === 'function') ensureLeadSchema_(); }                 catch (e) {}
  try { if (typeof ensureDeliverySchema_             === 'function') ensureDeliverySchema_(); }             catch (e) {}
  try { if (typeof ensurePaymentLedgerSchema_        === 'function') ensurePaymentLedgerSchema_(); }        catch (e) {}
  try { if (typeof ensureFinanceRegisterSheet_       === 'function') ensureFinanceRegisterSheet_(); }       catch (e) {}
  try { if (typeof ensureInsuranceRegisterSheet_     === 'function') ensureInsuranceRegisterSheet_(); }     catch (e) {}
  try { if (typeof ensureExtraIncomeRegisterSheet_   === 'function') ensureExtraIncomeRegisterSheet_(); }   catch (e) {}
  try { if (typeof ensureExtraIncomeAnalyticsSheet_  === 'function') ensureExtraIncomeAnalyticsSheet_(); }  catch (e) {}
  try { if (typeof ensureDealerEarningsRegisterSheet_ === 'function') ensureDealerEarningsRegisterSheet_(); } catch (e) {}
  try { if (typeof ensureDealerEarningsAnalyticsSheet_ === 'function') ensureDealerEarningsAnalyticsSheet_(); } catch (e) {}
  try { if (typeof ensureSchemeShareSettingsRows_    === 'function') ensureSchemeShareSettingsRows_(); }    catch (e) {}
  try { if (typeof ensureSchemeAndIncentiveSheets_   === 'function') ensureSchemeAndIncentiveSheets_(); }   catch (e) {}
  try { if (typeof refreshFinancePendingView_        === 'function') refreshFinancePendingView_(); }        catch (e) {}
  // Ensure the 1-minute auto-refresh trigger is installed on every open.
  try { if (typeof ensureAutoRefreshTrigger_         === 'function') ensureAutoRefreshTrigger_(); }         catch (e) {}
  try { if (typeof organizeSpreadsheetTabs_          === 'function') organizeSpreadsheetTabs_(); }          catch (e) {}
}

function installBasicCrmMenu_() {
  SpreadsheetApp.getUi().createMenu('CRM')
    .addItem('New Lead',              'menuNewLead')
    .addItem('Add Payment',           'menuAddPayment')
    .addItem('Refresh All Sheets',    'menuRefreshDashboard')
    .addItem('Refresh Dashboard Only','menuSyncDashboardNow')
    .addToUi();
}

// ═══════════════════════════════════════════════════════════════════════════
//  MENU
// ═══════════════════════════════════════════════════════════════════════════

function buildMenu_() {
  var ui    = SpreadsheetApp.getUi();
  var owner = typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_();

  var menu = ui.createMenu('CRM');

  // ── Daily operations ──────────────────────────────────────────────────
  menu
    .addItem('New Lead',                'menuNewLead')
    .addItem('Open Web Portal',         'menuOpenWebPortal')
    .addItem('Deal Quotation',          'menuDealQuotation')
    .addItem('Convert to Booking',      'menuConvertToBooking')
    .addItem('Price Structure',         'menuPriceStructure')
    .addItem('Edit Lead',               'menuEditLead')
    .addItem('Scheme Update',           'menuSchemeUpdate')
    .addItem('Add Payment',             'menuAddPayment')
    .addItem('Record Financer Receipt', 'menuRecordFinancerReceipt')
    .addItem('Mark Delivered',          'menuMarkDelivered')
    .addItem('Close Lead',              'menuCloseLead')
    .addItem('Add Activity',            'menuAddActivity')
    .addItem('Search Lead',             'menuSearchLead')
    .addItem('Refresh Dashboard',       'menuSyncDashboardNow');

  // ── Go to sheets ──────────────────────────────────────────────────────
  var navigate = ui.createMenu('Go To');
  navigate
    .addItem('Lead Register',      'menuNavToLeadRegister')
    .addItem('Booking Register',   'menuNavToBookingRegister')
    .addItem('Payment Ledger',     'menuNavToPaymentLedger')
    .addItem('Finance Register',   'menuNavToFinanceRegister')
    .addItem('Delivery Tracker',   'menuNavToDeliveryTracker')
    .addItem('Dashboard',          'menuNavToDashboard')
    .addSeparator()
    .addItem('Customer 360',       'menuShowCustomer360');
  menu.addSeparator().addSubMenu(navigate);

  // ── Claims ────────────────────────────────────────────────────────────
  if (typeof menuOpenClaimRegister === 'function') {
    var claimsMenu = ui.createMenu('Claims');
    claimsMenu
      .addItem('Open Claim Register',   'menuOpenClaimRegister')
      .addItem('Record Claim Received', 'menuRecordClaimReceived')
      .addItem('Update Claim Status',   'menuUpdateClaimStatus')
      .addItem('Add Manual Claim',      'menuAddManualClaim');
    menu.addSubMenu(claimsMenu);
  }

  // ── Insurance ─────────────────────────────────────────────────────────
  if (typeof menuOpenInsuranceRegister === 'function') {
    var insMenu = ui.createMenu('Insurance');
    insMenu
      .addItem('Open Insurance Register', 'menuOpenInsuranceRegister')
      .addItem('Add Insurance Entry',     'menuAddInsuranceEntry')
      .addItem('Record Insurer Payout',   'menuRecordInsurancePayout');
    menu.addSubMenu(insMenu);
  }

  // ── Owner reports / earnings ──────────────────────────────────────────
  if (owner) {
    var reports = ui.createMenu('Reports');
    reports
      .addItem('Dealer Earnings Register',  'menuOpenDealerEarningsRegister')
      .addItem('Rebuild Dealer Earnings',   'menuRebuildDealerEarnings')
      .addItem('Repair OEM Support Headers', 'menuRepairOemExtraSupportHeaders')
      .addItem('Repair Missing Booking Payments', 'menuRepairMissingBookingPayments')
      .addSeparator()
      .addItem('OEM Claim Dashboard',       'menuOemClaimDashboard')
      .addItem('Rebuild Claim Register',    'menuRebuildClaimRegister')
      .addItem('Scheme Master',             'menuOpenSchemeMaster')
      .addItem('Incentive Master',          'menuOpenIncentiveMaster')
      .addItem('Seed Aug 2026 Schemes',     'menuSeedAugust2026Schemes');
    menu.addSubMenu(reports);
  }

  // ── Admin (owner only, short) ─────────────────────────────────────────
  var admin = ui.createMenu('Admin');
  admin
    .addItem('Backup Database', 'menuBackupDatabase')
    .addItem('Settings',        'menuSettings');
  if (owner) {
    admin.addSeparator()
      .addItem('Import Price Master 2026', 'menuImportPriceMaster2026')
      .addItem('Repair Missing Booking Payments', 'menuRepairMissingBookingPayments')
      .addItem('Restore Tab Order',        'menuRestoreTabOrder')
      .addItem('Fresh Start (Clear All Data)', 'menuFreshStartClearAllData');
  }
  menu.addSeparator().addSubMenu(admin);
  menu.addToUi();
}

// ═══════════════════════════════════════════════════════════════════════════
//  NAVIGATE MENU HANDLERS
// ═══════════════════════════════════════════════════════════════════════════

function menuNavToLeadRegister()    { navGoToSheet_(CRM.SHEETS.LEAD_REGISTER);    }
function menuNavToBookingRegister() { navGoToSheet_(CRM.SHEETS.BOOKING_REGISTER); }
function menuNavToPaymentLedger()   { navGoToSheet_(CRM.SHEETS.PAYMENT_LEDGER);   }
function menuNavToDeliveryTracker() { navGoToSheet_(CRM.SHEETS.DELIVERY_TRACKER); }
function menuNavToFinanceRegister() { navGoToSheet_(CRM.SHEETS.FINANCE_REGISTER); }
function menuNavToDashboard()       { navGoToSheet_(CRM.SHEETS.DASHBOARD);        }

// ═══════════════════════════════════════════════════════════════════════════
//  EXISTING MENU HANDLERS (unchanged — preserved from original Code.gs)
// ═══════════════════════════════════════════════════════════════════════════

function menuInitialSetup() {
  var ui = SpreadsheetApp.getUi();
  var wrapped = runDestructiveOp_({
    label: 'INITIAL_SETUP',
    confirmTitle: 'CRM Initial Setup',
    confirmMessage: 'Create/rebuild all sheets, formatting, and import historical data?',
    fn: function () {
      setupAllSheets_();
      ensureLeadSchema_();
      ensurePhase3Sheets_();
      ensureTransactionLogSheet_();
      ensureCrashReportSheet_();
      ensureBackupRegistrySheet_();
      ensurePerformanceLogSheet_();
      importHistoricalDataSilent_();
      setupFormulas_();
      repairMastersSheet_();
      syncAll_({ dashboard: true });
      applyAllConditionalFormatting_();
      installTriggers_();
      refreshDashboard_();
      return { setup: true };
    },
    skipValidation: false
  });
  if (wrapped.cancelled) return;
  ui.alert('Setup complete!', 'Your CRM is ready.\n\nBackup #' +
    (wrapped.backup ? wrapped.backup.backupNo : 'n/a'), ui.ButtonSet.OK);
}

function menuNewLead()                { showNewLeadDialog_(); }
function menuConvertToBooking()       { showConvertToBookingDialog_(); }
function menuPriceStructure()         { showPriceStructureDialog_(); }
function menuEditLead()               { showEditLeadDialog_(); }
function menuUpdateLead()             { showEditLeadDialog_(); }
function menuSchemeUpdate()           { showSchemeUpdateDialog_(); }
function menuAddActivity()            { showAddActivityDialog_(); }
function menuAddPayment()             { showAddPaymentDialog_(); }
function menuRecordFinancerReceipt()  { showRecordFinancerReceiptDialog_(); }
// menuRefreshFinancePending lives in FinanceService.gs (single definition).
function menuMarkDelivered()  { showMarkDeliveredDialog_(); }
function menuCloseLead()      { showCloseLeadDialog_(); }
function menuSearchLead()     { showSearchDialog_(); }

function menuRefreshDashboard() {
  var ui = SpreadsheetApp.getUi();
  try {
    showToast_('Refreshing entire spreadsheet…');
    var result = refreshEntireWorkbook_();
    var ms    = (result && result.executionMs) || 0;
    var lines = (result && result.steps) ? result.steps.join('\n') : 'Done';
    ui.alert('Full refresh complete',
      'All CRM sheets were updated (' + Math.round(ms / 1000) + 's).\n\n' + lines,
      ui.ButtonSet.OK);
    showToast_('Full spreadsheet refresh complete');
  } catch (e) {
    ui.alert('Refresh failed', (e && e.message) || String(e), ui.ButtonSet.OK);
  }
}

function menuSyncDashboardNow() {
  var ui = SpreadsheetApp.getUi();
  try {
    showToast_('Refreshing dashboard…');
    invalidateCrmStore_();
    refreshDashboard_();
    showToast_('Dashboard refreshed ✔');
  } catch (e) {
    ui.alert('Dashboard refresh failed', (e && e.message) || String(e), ui.ButtonSet.OK);
  }
}

function menuImportHistoricalData() { importHistoricalData_(); }
function menuValidateDatabase()     { runValidation_(); }
function menuSettings()             { showSettingsDialog_(); }

function menuGoLiveQuickFix() {
  if (!isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Only the spreadsheet owner can run Go-Live Quick Fix.');
    return { denied: true };
  }
  try {
    clearMaintenanceAndReadOnly_();
    ensurePhase3Sheets_();
    if (typeof ensureQuotationLogSheet_ === 'function') ensureQuotationLogSheet_();
    if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_();
    if (typeof ensureInsuranceRegisterSheet_ === 'function') ensureInsuranceRegisterSheet_();
    if (typeof ensureLeadSchema_ === 'function') ensureLeadSchema_();
    if (typeof rebuildFinanceRegisterFromLedger_ === 'function') rebuildFinanceRegisterFromLedger_();
    // repairMastersSheet_ syncs Models/Variants from PRICE MASTER and refreshes dropdowns.
    repairMastersSheet_();
    refreshDashboard_();
    if (typeof organizeSpreadsheetTabs_ === 'function') organizeSpreadsheetTabs_();
    try {
      if (typeof navRefreshAllHyperlinks_ === 'function') navRefreshAllHyperlinks_();
    } catch (eNav) {}
    buildMenu_();
    SpreadsheetApp.getUi().alert(
      'Go-Live Quick Fix complete.\n\n' +
      '• Tab order restored (drill-downs visible for KPI links)\n' +
      '• Lead ID backlinks refreshed\n\n' +
      'Try CRM → New Lead / Add Payment now.',
      SpreadsheetApp.getUi().ButtonSet.OK);
    return { ok: true };
  } catch (e) {
    SpreadsheetApp.getUi().alert('Go-Live Quick Fix failed: ' + e.message);
    return { ok: false, error: e.message };
  }
}

function goToLeadFromDialog(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) throw new Error('Lead ID is required');
  goToLead_(leadId);
  return crmOk_('Navigated to lead', { leadId: leadId });
}

// ═══════════════════════════════════════════════════════════════════════════
//  TRIGGERS
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Installs/reinstalls all triggers:
 *   - onEdit  → onEditHandler_
 *   - onChange → onChangeHandler_
 *   - time-based (1 min) → onTimeTriggerRefresh_  (from FixesService.gs)
 */
function installTriggers_() {
  var ss = getSpreadsheet_();

  // Remove old edit / change triggers before re-creating them.
  ScriptApp.getProjectTriggers().forEach(function (t) {
    var fn = t.getHandlerFunction();
    if (fn === 'onEditHandler_' || fn === 'onChangeHandler_') {
      ScriptApp.deleteTrigger(t);
    }
  });
  ScriptApp.newTrigger('onEditHandler_').forSpreadsheet(ss).onEdit().create();
  ScriptApp.newTrigger('onChangeHandler_').forSpreadsheet(ss).onChange().create();

  // Install the 1-minute auto-refresh trigger (idempotent — FixesService.gs).
  if (typeof installAutoRefreshTrigger_ === 'function') {
    try { installAutoRefreshTrigger_(); } catch (e) {
      Logger.log('installTriggers_: could not install auto-refresh — ' + e.message);
    }
  }
}

function ensureTriggersInstalled_() {
  var triggers  = ScriptApp.getProjectTriggers();
  var hasEdit   = false;
  var hasChange = false;
  triggers.forEach(function (t) {
    if (t.getHandlerFunction() === 'onEditHandler_')   hasEdit   = true;
    if (t.getHandlerFunction() === 'onChangeHandler_') hasChange = true;
  });
  if (!hasEdit || !hasChange) installTriggers_();
}

// ═══════════════════════════════════════════════════════════════════════════
//  onEdit HANDLER
//  Fires for every direct cell edit on any sheet.
//  Always refreshes the dashboard so KPIs + Recent Activities are current.
// ═══════════════════════════════════════════════════════════════════════════

function onEditHandler_(e) {
  if (!e || !e.range) return;
  var sheetName = e.range.getSheet().getName();

  // Run sheet-specific logic first (fast path — field auto-fill, audit, etc.)
  if      (sheetName === CRM.SHEETS.LEAD_REGISTER)    { try { handleLeadRegisterEdit_(e);   } catch (err) {} }
  else if (sheetName === CRM.SHEETS.ACTIVITY_LOG)     { try { handleActivityLogEdit_(e);    } catch (err) {} }
  else if (sheetName === CRM.SHEETS.PAYMENT_LEDGER)   { try { handlePaymentLedgerEdit_(e);  } catch (err) {} }
  else if (sheetName === CRM.SHEETS.DELIVERY_TRACKER) { try { handleDeliveryTrackerEdit_(e);} catch (err) {} }
  else if (sheetName === CRM.SHEETS.INSURANCE_REGISTER) { try { handleInsuranceRegisterEdit_(e); } catch (err) {} }
  else if (sheetName === CRM.SHEETS.FINANCE_REGISTER) { try { handleFinanceRegisterEdit_(e); } catch (err) {} }

  // V3 hot/cold split: edits NEVER rebuild the reporting surface synchronously.
  // Mark the store dirty and let the deferred worker (debounced one-shot trigger)
  // refresh dashboard/drill-downs/views once per burst. Previously this ran a full
  // refreshDashboard_() on EVERY keystroke — 4 full sheet reads + ~20 sheet writes.
  try {
    invalidateCrmStore_();
    scheduleDeferredCrmSync_({ reason: 'edit', dashboard: true });
  } catch (dashErr) {
    try { logAudit_('ONEDIT_DEFER_WARN', dashErr.message); } catch (e) {}
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  onChange HANDLER
//  Fires for structural changes (INSERT_ROW, DELETE_ROW, etc.).
// ═══════════════════════════════════════════════════════════════════════════

function onChangeHandler_(e) {
  if (!e) return;
  // V3: structural changes also defer — same debounced worker, once per burst.
  try {
    invalidateCrmStore_();
    scheduleDeferredCrmSync_({ reason: 'change', dashboard: true });
  } catch (err) {
    try { logAudit_('ONCHANGE_DEFER_WARN', err.message); } catch (e) {}
  }
}
