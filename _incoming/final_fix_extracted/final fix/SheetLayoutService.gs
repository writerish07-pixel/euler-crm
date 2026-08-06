/**
 * SheetLayoutService.gs — user-facing tab order and backend sheet visibility.
 */

var MANUAL_INPUT_HIGHLIGHT_ = '#FFF9C4';

/** Resolve configured hidden/backend sheet names (actual tab titles). */
function getBackendSheetNames_() {
  var names = [];
  var push = function (n) {
    n = String(n || '').trim();
    if (n && names.indexOf(n) < 0) names.push(n);
  };

  (CRM.HIDDEN_SHEETS || []).forEach(function (entry) {
    push(CRM.SHEETS[entry] || entry);
  });
  // NOTE: DRILL_DOWN_SHEETS stay visible — Google Sheets blocks HYPERLINK into hidden tabs.
  if (CRM.SHEET_LAYOUT && CRM.SHEET_LAYOUT.BACKEND) {
    CRM.SHEET_LAYOUT.BACKEND.forEach(push);
  }
  push('Migration Import Log');
  return names;
}

function isDrillDownSheetName_(name) {
  name = String(name || '').trim();
  if (!name) return false;
  if ((CRM.DRILL_DOWN_SHEETS || []).indexOf(name) >= 0) return true;
  if (/^MP — /.test(name) || /^DE — /.test(name) || /^Payments — /.test(name)) return true;
  if (/^Today's /.test(name) || name.indexOf('Monthly ') === 0) return true;
  if (name === 'Pending Deliveries' || name === 'Pending Follow-ups' ||
      name === 'Outstanding Leads' || name === 'Navigation Matrix') return true;
  return false;
}

function isBackendSheetName_(name) {
  name = String(name || '').trim();
  if (isDrillDownSheetName_(name)) return false;
  if (getBackendSheetNames_().indexOf(name) >= 0) return true;
  return false;
}

/**
 * Hide backend/working tabs only.
 * KPI drill-downs stay visible (far right) so Dashboard HYPERLINKs work.
 */
function hideBackendSheets_() {
  var ss = getSpreadsheet_();
  var visible = (CRM.SHEET_LAYOUT && CRM.SHEET_LAYOUT.VISIBLE_ORDER) || [];
  var visibleSet = {};
  visible.forEach(function (n) { visibleSet[String(n)] = true; });

  ss.getSheets().forEach(function (sh) {
    var name = sh.getName();
    if (visibleSet[name] || isDrillDownSheetName_(name)) {
      if (sh.isSheetHidden()) sh.showSheet();
      return;
    }
    if (!sh.isSheetHidden()) sh.hideSheet();
  });
}

/**
 * Reorder: primary VISIBLE_ORDER first, then drill-down tabs to the right.
 */
function reorderVisibleTabs_() {
  var ss = getSpreadsheet_();
  var order = (CRM.SHEET_LAYOUT && CRM.SHEET_LAYOUT.VISIBLE_ORDER) || [];
  if (!order.length) return;

  var pos = 1;
  for (var i = 0; i < order.length; i++) {
    var sh = ss.getSheetByName(order[i]);
    if (!sh) continue;
    if (sh.isSheetHidden()) sh.showSheet();
    ss.setActiveSheet(sh);
    ss.moveActiveSheet(pos);
    pos++;
  }

  var drillNames = (CRM.DRILL_DOWN_SHEETS || []).slice();
  ss.getSheets().forEach(function (d) {
    var n = d.getName();
    if (isDrillDownSheetName_(n) && drillNames.indexOf(n) < 0) drillNames.push(n);
  });
  drillNames.forEach(function (name) {
    if (order.indexOf(name) >= 0) return;
    var dsh = ss.getSheetByName(name);
    if (!dsh) return;
    if (dsh.isSheetHidden()) dsh.showSheet();
    ss.setActiveSheet(dsh);
    ss.moveActiveSheet(pos);
    pos++;
  });
}

/** Hide backend tabs, reorder user-facing tabs, focus Dashboard. */
function organizeSpreadsheetTabs_() {
  try {
    hideBackendSheets_();
    reorderVisibleTabs_();
    var dash = getSpreadsheet_().getSheetByName(CRM.SHEETS.DASHBOARD);
    if (dash && !dash.isSheetHidden()) getSpreadsheet_().setActiveSheet(dash);
    return { ok: true };
  } catch (e) {
    Logger.log('organizeSpreadsheetTabs_: ' + e.message);
    return { ok: false, error: e.message };
  }
}

/** Owner/admin menu — restore Dashboard → Lead Register → … tab order. */
function menuRestoreTabOrder() {
  var result = organizeSpreadsheetTabs_();
  try {
    if (typeof navRefreshAllHyperlinks_ === 'function') navRefreshAllHyperlinks_();
  } catch (eNav) {
    Logger.log('menuRestoreTabOrder nav: ' + eNav.message);
  }
  if (result && result.ok) {
    SpreadsheetApp.getUi().alert(
      'Tab order restored',
      'Primary tabs (left → right):\n\n' +
        ((CRM.SHEET_LAYOUT && CRM.SHEET_LAYOUT.VISIBLE_ORDER) || []).join('\n') +
        '\n\nKPI drill-down sheets stay visible on the far right so Dashboard links work.\n' +
        'Lead ID backlinks refreshed.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } else {
    SpreadsheetApp.getUi().alert(
      'Tab order failed',
      (result && result.error) || 'Unknown error',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  }
  return result;
}

/**
 * Kept for call-site compatibility. Drill-downs must stay visible for HYPERLINKs.
 */
function hideDrillDownSheet_(name) {
  try {
    var sh = getSpreadsheet_().getSheetByName(name);
    if (sh && sh.isSheetHidden()) sh.showSheet();
  } catch (e) {}
}

// ── Lead Register menu helpers (referenced by CRM menu + regression tests) ──

function highlightManualInputColumns_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var lastRow = Math.max(sheet.getLastRow(), CRM.LEAD.DATA_START);
  var numRows = lastRow - CRM.LEAD.DATA_START + 1;
  (CRM.LEAD.EDITABLE || []).forEach(function (colName) {
    var col = findHeaderIndex_(headers, colName) + 1;
    if (col < 1) return;
    sheet.getRange(CRM.LEAD.HEADER_ROW, col).setBackground(MANUAL_INPUT_HIGHLIGHT_).setFontWeight('bold');
    if (numRows > 0) sheet.getRange(CRM.LEAD.DATA_START, col, numRows, 1).setBackground(MANUAL_INPUT_HIGHLIGHT_);
  });
}

function clearManualInputHighlights_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var lastRow = Math.max(sheet.getLastRow(), CRM.LEAD.HEADER_ROW);
  (CRM.LEAD.EDITABLE || []).forEach(function (colName) {
    var col = findHeaderIndex_(headers, colName) + 1;
    if (col < 1) return;
    sheet.getRange(CRM.LEAD.HEADER_ROW, col, lastRow - CRM.LEAD.HEADER_ROW + 1, 1).setBackground(null);
  });
}

function refreshAllLeadPrices_() {
  invalidateCrmStore_();
  var store = loadCrmStore_(true);
  var count = 0;
  Object.keys(store.leads.byId).forEach(function (id) {
    if (typeof syncLeadCommercialEstimate_ !== 'function') return;
    try {
      syncLeadCommercialEstimate_(id, store);
      count++;
    } catch (e) {
      Logger.log('refreshAllLeadPrices_: ' + id + ' — ' + e.message);
    }
  });
  invalidateCrmStore_();
  if (typeof syncComputedFields_ === 'function') syncComputedFields_({ dashboard: true });
  return count;
}

function menuHighlightManualInputs() {
  return crmRun_('Lead', 'Highlight Manual Inputs', function () {
    highlightManualInputColumns_();
    SpreadsheetApp.getActiveSpreadsheet().toast(
      'Editable columns highlighted on Lead Register', 'CRM', 4);
    return { ok: true };
  });
}

function menuClearManualHighlights() {
  return crmRun_('Lead', 'Clear Manual Highlights', function () {
    clearManualInputHighlights_();
    SpreadsheetApp.getActiveSpreadsheet().toast('Manual highlights cleared', 'CRM', 3);
    return { ok: true };
  });
}

function menuRefreshLeadPrices() {
  return crmRun_('Lead', 'Refresh Lead Prices', function () {
    var count = refreshAllLeadPrices_();
    SpreadsheetApp.getUi().alert(
      'Lead prices refreshed from Price Master.\n\nUpdated ' + count + ' lead(s).',
      SpreadsheetApp.getUi().ButtonSet.OK);
    return { count: count };
  });
}

function menuMigrateLeadRegister() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Only the spreadsheet owner can migrate the Lead Register.');
    return { denied: true };
  }
  return crmRun_('Lead', 'Migrate Lead Register', function () {
    ensureLeadSchema_();
    if (typeof applyLeadRegisterFormatting_ === 'function') applyLeadRegisterFormatting_();
    if (typeof navRefreshLeadBookingLinks_ === 'function') {
      navRefreshLeadBookingLinks_(getSpreadsheet_());
    }
    if (typeof organizeSpreadsheetTabs_ === 'function') organizeSpreadsheetTabs_();
    SpreadsheetApp.getUi().alert(
      'Lead Register migration complete.\n\nMissing columns were added and Account Status backfilled.',
      SpreadsheetApp.getUi().ButtonSet.OK);
    return { ok: true };
  });
}
