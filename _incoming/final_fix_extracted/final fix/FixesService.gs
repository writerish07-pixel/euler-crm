/**
 * FixesService.gs  — Euler Motors Dealership CRM v2.1 critical fixes
 *
 * ADD this file as a new script file in your Apps Script project.
 *
 * If you already have a setValueSafe_ function defined elsewhere, REMOVE the
 * old definition first — Apps Script does not allow duplicate function names.
 *
 * Fixes bundled here:
 *  1. setValueSafe_()           — bypasses "Reject input" data-validation so
 *                                  Finance Required / Financer Name / Outstanding
 *                                  are always written regardless of dropdown rules.
 *  2. Auto-refresh infrastructure — time-based trigger fires refreshDashboard_()
 *                                   every minute so the dashboard stays live even
 *                                   without clicking Refresh.
 *  3. menuSetupAutoRefresh()    — CRM menu item to install the time trigger.
 *  4. menuRemoveAutoRefresh()   — CRM menu item to remove the time trigger.
 *  5. refreshCrmAfterDialogSave_() — called at the end of every dialog save so
 *                                   Dashboard + Recent Activity update immediately.
 */

// ═══════════════════════════════════════════════════════════════════════════
//  FIX 1 — setValueSafe_
//  Clears the cell's data-validation rule, writes the value, then restores
//  the rule. This lets the CRM always win over "Reject input" dropdowns on
//  computed columns (Finance Required, Outstanding, Financer Name, etc.).
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Write a value to a range, bypassing any "Reject input" data-validation.
 * Drop-in replacement — call signature is identical to the old stub.
 *
 * @param {GoogleAppsScript.Spreadsheet.Range} range
 * @param {*} value
 */
// setValueSafe_ moved to Utils.gs (single, validation-preserving definition).

// ═══════════════════════════════════════════════════════════════════════════
//  FIX 2 — Auto-refresh infrastructure
//  A 1-minute time-based trigger ensures the Dashboard, Recent Activities,
//  Finance Pending, and Finance Overdue sheets are always current — even when
//  entries are saved via dialogs (which don't fire onEdit).
// ═══════════════════════════════════════════════════════════════════════════

var AUTO_REFRESH_HANDLER_ = 'onTimeTriggerRefresh_';
var AUTO_REFRESH_PROP_    = 'crm_auto_refresh_trigger_id';

/**
 * Handler for the time-based trigger. Runs every minute and refreshes all
 * computed sheets. Skips if another refresh ran in the last 50 seconds.
 */
function onTimeTriggerRefresh_() {
  try {
    // V3: this minute-trigger is a SAFETY NET, not a worker. The deferred one-shot
    // trigger handles refreshes on change. Previously this ran a full store rebuild
    // + dashboard repaint every 60 seconds even when nothing had changed — constant
    // background load on an idle spreadsheet. Now it only acts if a deferred queue
    // item exists (i.e. a one-shot trigger failed to fire or was quota-dropped).
    var props = PropertiesService.getScriptProperties();
    var pending = props.getProperty('crm_deferred_sync');
    if (!pending || pending === '[]') return; // nothing dirty — do nothing
    var lock = LockService.getScriptLock();
    if (!lock.tryLock(3000)) return; // another instance is running
    try {
      processDeferredCrmSync_();
    } finally {
      lock.releaseLock();
    }
  } catch (e) {
    Logger.log('onTimeTriggerRefresh_ error: ' + e.message);
  }
}

/**
 * Installs the 1-minute time-based auto-refresh trigger (idempotent).
 * Run once from CRM → Admin → Setup Auto-Refresh, or call installAutoRefreshTrigger_()
 * in your onOpen / menuInitialSetup.
 */
function installAutoRefreshTrigger_() {
  // Remove any existing auto-refresh triggers first (avoid duplicates).
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === AUTO_REFRESH_HANDLER_) {
      ScriptApp.deleteTrigger(t);
    }
  });
  var trigger = ScriptApp.newTrigger(AUTO_REFRESH_HANDLER_)
    .timeBased()
    .everyMinutes(1)
    .create();
  try {
    PropertiesService.getScriptProperties().setProperty(AUTO_REFRESH_PROP_, trigger.getUniqueId());
  } catch (e) {}
  return trigger.getUniqueId();
}

/**
 * Removes the auto-refresh time trigger.
 */
function removeAutoRefreshTrigger_() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === AUTO_REFRESH_HANDLER_) {
      ScriptApp.deleteTrigger(t);
    }
  });
  try {
    PropertiesService.getScriptProperties().deleteProperty(AUTO_REFRESH_PROP_);
  } catch (e) {}
}

/** Menu handler — sets up the auto-refresh trigger. */
function menuSetupAutoRefresh() {
  try {
    installAutoRefreshTrigger_();
    SpreadsheetApp.getUi().alert(
      'Auto-Refresh Enabled',
      'Dashboard will now refresh automatically every minute.\n\n' +
      'You do NOT need to click "Refresh Dashboard" after entries.\n\n' +
      'To disable, run CRM → Admin → Remove Auto-Refresh.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

/** Menu handler — removes the auto-refresh trigger. */
function menuRemoveAutoRefresh() {
  try {
    removeAutoRefreshTrigger_();
    SpreadsheetApp.getUi().alert(
      'Auto-Refresh Disabled',
      'The 1-minute background refresh has been removed.\n\n' +
      'To re-enable, run CRM → Admin → Setup Auto-Refresh.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  FIX 3 — Immediate post-dialog-save refresh
//  Called at the end of every dialog save (addPaymentFromDialog,
//  createNewLeadFromDialog, etc.) so the dashboard reflects the new data
//  right away instead of waiting for the next minute trigger.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Light, non-blocking dashboard refresh called after every dialog save.
 * Wraps refreshDashboard_ with error isolation so a bad metric never
 * crashes the save response that the dialog is waiting for.
 */
function refreshCrmAfterDialogSave_() {
  // V3 hot/cold split: a save writes its own rows only; the reporting surface
  // (dashboard, drill-downs, views) is rebuilt once per burst by the deferred
  // worker. This used to call refreshDashboard_() synchronously, which made every
  // Booking/Payment/Finance/Insurance save wait for a full store rebuild + ~20
  // sheet writes.
  try {
    invalidateCrmStore_();
    scheduleDeferredCrmSync_({ reason: 'dialog_save', dashboard: true });
  } catch (e) {
    Logger.log('refreshCrmAfterDialogSave_ error: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  FIX 4 — ensureAutoRefreshTrigger_ (call once from onOpen/Initial Setup)
//  Checks at startup whether the trigger exists and installs it if not.
// ═══════════════════════════════════════════════════════════════════════════

function ensureAutoRefreshTrigger_() {
  var has = ScriptApp.getProjectTriggers().some(function (t) {
    return t.getHandlerFunction() === AUTO_REFRESH_HANDLER_;
  });
  if (!has) {
    try { installAutoRefreshTrigger_(); } catch (e) {
      Logger.log('ensureAutoRefreshTrigger_ could not install: ' + e.message);
    }
  }
}
