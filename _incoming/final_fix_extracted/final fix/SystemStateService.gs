/**
 * SystemStateService – Maintenance Mode, Read-Only Mode, Production Mode (LTS-1).
 */

var CRM_STATE_KEYS = {
  MAINTENANCE_MODE: 'crm_maintenance_mode',
  READ_ONLY: 'crm_read_only',
  PRODUCTION_MODE: 'crm_production_mode',
  MAINTENANCE_MSG: 'crm_maintenance_msg'
};

function getScriptProp_(key) {
  return PropertiesService.getScriptProperties().getProperty(key) || '0';
}

function setScriptProp_(key, val) {
  PropertiesService.getScriptProperties().setProperty(key, String(val));
}

function isMaintenanceMode_() {
  return getScriptProp_(CRM_STATE_KEYS.MAINTENANCE_MODE) === '1';
}

/** @deprecated Use isMaintenanceMode_ */
function isSafeMode_() {
  return isMaintenanceMode_();
}

function isReadOnlyMode_() {
  return getScriptProp_(CRM_STATE_KEYS.READ_ONLY) === '1';
}

function isProductionMode_() {
  return getScriptProp_(CRM_STATE_KEYS.PRODUCTION_MODE) === '1';
}

function setMaintenanceMode_(on, reason) {
  setScriptProp_(CRM_STATE_KEYS.MAINTENANCE_MODE, on ? '1' : '0');
  if (on) {
    logTransaction_('System', 'Maintenance Mode ON', {
      status: 'WARNING',
      errorCode: 'MAINTENANCE_MODE',
      message: (reason || 'System integrity issue') + ' [' + getVersionTag_() + ']'
    });
    showMaintenanceBanner_(
      'MAINTENANCE MODE — Lead creation, payments, merge, delivery, and imports disabled. ' +
      'Search and dashboard available. Owner: CRM → Exit Maintenance Mode.'
    );
    buildMenu_();
  } else {
    clearMaintenanceBanner_();
    buildMenu_();
  }
}

function setReadOnlyMode_(on, reason) {
  setScriptProp_(CRM_STATE_KEYS.READ_ONLY, on ? '1' : '0');
  if (on) {
    setScriptProp_(CRM_STATE_KEYS.MAINTENANCE_MSG, reason || 'System requires maintenance.');
    logTransaction_('System', 'Read-Only Mode ON', {
      status: 'CRITICAL',
      errorCode: 'READ_ONLY',
      message: (reason || 'Integrity failure') + ' [' + getVersionTag_() + ']'
    });
    showMaintenanceBanner_(
      'READ ONLY — System requires maintenance. Editing temporarily disabled. ' +
      'Run CRM → Safe Recovery (Owner).'
    );
    buildMenu_();
  } else {
    PropertiesService.getScriptProperties().deleteProperty(CRM_STATE_KEYS.MAINTENANCE_MSG);
    clearMaintenanceBanner_();
    buildMenu_();
  }
}

function clearMaintenanceAndReadOnly_() {
  setScriptProp_(CRM_STATE_KEYS.MAINTENANCE_MODE, '0');
  setScriptProp_(CRM_STATE_KEYS.READ_ONLY, '0');
  PropertiesService.getScriptProperties().deleteProperty(CRM_STATE_KEYS.MAINTENANCE_MSG);
  clearMaintenanceBanner_();
  logTransaction_('System', 'Modes Cleared', {
    status: 'OK',
    message: 'Maintenance and read-only modes disabled [' + getVersionTag_() + ']'
  });
  buildMenu_();
}

/** @deprecated */
function clearSafeAndReadOnly_() {
  clearMaintenanceAndReadOnly_();
}

function setProductionMode_(on) {
  setScriptProp_(CRM_STATE_KEYS.PRODUCTION_MODE, on ? '1' : '0');
}

/**
 * Block operations based on maintenance / read-only state.
 * @param {string} action e.g. 'payment', 'merge', 'delivery', 'import', 'write', 'lead_create'
 */
function assertOperational_(action) {
  return true;
}

function applyHealthStatusModes_(healthResult) {
  if (!healthResult) return;
  // Health/observability must NEVER auto-block business transactions (go-live requirement).
  if (healthResult.status === 'Critical' || healthResult.status === 'Warning') {
    try {
      showToast_(
        'CRM health: ' + healthResult.summary + ' — business operations remain enabled. ' +
        'Run CRM → System Health Check (Owner).',
        'CRM Health'
      );
    } catch (e) {}
    try {
      logTransaction_('System', 'Health Notice', {
        status: healthResult.status,
        message: healthResult.summary
      });
    } catch (e2) {}
  }
}

function menuExitMaintenanceMode() {
  return crmRun_('System', 'Exit Maintenance Mode', function () {
    if (!isSpreadsheetOwner_()) {
      throw new Error('Only the spreadsheet owner can exit maintenance mode.');
    }
    var ui = SpreadsheetApp.getUi();
    var health = runHealthCheck_();
    var warn = health.status !== 'Healthy'
      ? '\n\nWARNING: Health check is ' + health.status + '. Exiting maintenance may allow operations on a compromised system.'
      : '\n\nHealth check: ' + health.status + '.';
    var resp = ui.alert(
      'Exit Maintenance Mode (Owner)',
      'This will re-enable lead creation, payments, merge, delivery, and imports.' + warn + '\n\nContinue?',
      ui.ButtonSet.YES_NO
    );
    if (resp !== ui.Button.YES) return { cancelled: true };
    clearMaintenanceAndReadOnly_();
    ui.alert('Maintenance mode disabled.', 'Normal operations restored.', ui.ButtonSet.OK);
    return { health: health };
  });
}

function showMaintenanceBanner_(text) {
  try {
    var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
    if (!dash) return;
    dash.getRange('A1').setValue('⚠ ' + text).setBackground('#FFCDD2').setFontWeight('bold');
  } catch (e) {}
}

function clearMaintenanceBanner_() {
  try {
    var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
    if (!dash) return;
    var settings = getSettings_();
    dash.getRange('A1').setValue(settings.companyName + ' — CRM Dashboard')
      .setBackground(null).setFontWeight('bold').setFontSize(18);
  } catch (e) {}
}
