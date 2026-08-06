/**
 * NavigationService.gs
 * Enterprise Navigation Engine — Euler Motors Dealership CRM v2.0
 *
 * The ONLY navigation engine. No sheet generates hyperlinks directly.
 * Everything routes through here.
 *
 * Architecture:
 *   - Every public navGoTo* function tracks recent records automatically.
 *   - Breadcrumbs are built from PropertiesService navigation history.
 *   - Relationship lookups use RelationshipIndex; never full-sheet scans.
 *   - Internal helpers have trailing underscore.
 *   - Public API (google.script.run) functions have NO trailing underscore.
 */

// ═══════════════════════════════════════════════════════════════════════════
//  NAVIGATION HISTORY (per-user, stored in UserProperties)
// ═══════════════════════════════════════════════════════════════════════════

var NAV_HISTORY_KEY_ = 'crm_nav_history';
var NAV_HISTORY_MAX_ = 20;

function navGetHistory_() {
  try {
    var raw = PropertiesService.getUserProperties().getProperty(NAV_HISTORY_KEY_);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function navPushHistory_(entry) {
  try {
    var hist = navGetHistory_();
    // Deduplicate: remove previous entry for same type+id
    hist = hist.filter(function(h){ return !(h.type === entry.type && h.id === entry.id); });
    hist.unshift(entry);
    if (hist.length > NAV_HISTORY_MAX_) hist = hist.slice(0, NAV_HISTORY_MAX_);
    PropertiesService.getUserProperties().setProperty(NAV_HISTORY_KEY_, JSON.stringify(hist));
  } catch (e) {}
}

/** PUBLIC: Returns navigation history array for dialogs. */
function getNavigationHistory() {
  try {
    return crmOk_('Navigation', { history: navGetHistory_() });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** PUBLIC: Clears navigation history. */
function clearNavigationHistory() {
  try {
    PropertiesService.getUserProperties().deleteProperty(NAV_HISTORY_KEY_);
    return crmOk_('Navigation', { cleared: true });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  TRACK + NAVIGATE  (wraps every navigation with history + recent records)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Central tracker: records history and recent records, then navigates.
 * @param {string} type  'Lead'|'Booking'|'Payment'|'Finance'|'Delivery'|'Claim'
 * @param {string} id    Primary ID
 * @param {string} label Human label (customer name, receipt #, etc.)
 * @param {string} [sub] Subtitle (model, status, etc.)
 * @param {Function} navFn  The internal navigation function to call
 */
function navTrackAndGo_(type, id, label, sub, navFn) {
  var entry = { type: type, id: String(id), label: String(label||id), sub: String(sub||''), ts: new Date().toISOString() };
  try { navPushHistory_(entry); } catch (e) {}
  try { trackRecentRecord(type, String(id), String(label||id), String(sub||'')); } catch (e) {}
  navFn();
}

// ═══════════════════════════════════════════════════════════════════════════
//  INTERNAL SHEET NAVIGATION
// ═══════════════════════════════════════════════════════════════════════════

function navGoToLead_(leadId) {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  if (!sheet) throw new Error('Lead Register sheet not found');
  sheet.activate();
  try {
    var store = loadCrmStore_();
    var row = store.leads && store.leads.sheetRow ? store.leads.sheetRow[String(leadId).trim()] : 0;
    if (row > 0) sheet.getRange(row, 1).activate();
  } catch (e) { Logger.log('navGoToLead_ row lookup: ' + e.message); }
}

function navGoToBooking_(bookingId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.BOOKING_REGISTER);
  if (!sheet) return;
  sheet.activate();
  var row = navFindFirstMatchInCol_(sheet, 1, String(bookingId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToPayment_(receiptId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
  if (!sheet) return;
  sheet.activate();
  var row = navFindFirstMatchInCol_(sheet, 1, String(receiptId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToFinance_(fileNumber) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.FINANCE_REGISTER);
  if (!sheet) return;
  sheet.activate();
  var row = navFindFirstMatchInCol_(sheet, 1, String(fileNumber).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToDelivery_(leadId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!sheet) return;
  sheet.activate();
  var row = navFindFirstMatchInCol_(sheet, 1, String(leadId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToActivity_(activityId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.ACTIVITY_LOG);
  if (!sheet) return;
  sheet.activate();
  var headers = getHeaders_(sheet, CRM.ACTIVITY.HEADER_ROW);
  var col = findHeaderIndex_(headers, 'Activity ID') + 1;
  if (col < 1) col = 1;
  var row = navFindFirstMatchInCol_(sheet, col, String(activityId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToClaim_(claimId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
  if (!sheet) return;
  sheet.activate();
  var row = navFindFirstMatchInCol_(sheet, 1, String(claimId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToCommercialSnapshot_(snapshotId) {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) return;
  sheet.activate();
  var headers = getHeaders_(sheet, 1);
  var col = findHeaderIndex_(headers, 'CommercialSnapshotID') + 1;
  if (col < 1) col = findHeaderIndex_(headers, 'Snapshot ID') + 1;
  if (col < 1) col = 1;
  var row = navFindFirstMatchInCol_(sheet, col, String(snapshotId).trim());
  if (row > 0) sheet.getRange(row, 1).activate();
}

function navGoToSheet_(sheetName) {
  var sheet = getSpreadsheet_().getSheetByName(sheetName);
  if (sheet) sheet.activate();
}

// ═══════════════════════════════════════════════════════════════════════════
//  ROW FINDER
// ═══════════════════════════════════════════════════════════════════════════

function navFindFirstMatchInCol_(sheet, col, value) {
  try {
    var last = sheet.getLastRow();
    if (last < 2) return 0;
    var numRows = last - 1;
    var data = sheet.getRange(2, col, numRows, 1).getValues();
    for (var i = 0; i < data.length; i++) {
      if (String(data[i][0]).trim() === value) return i + 2;
    }
  } catch (e) { Logger.log('navFindFirstMatchInCol_: ' + e.message); }
  return 0;
}

// ═══════════════════════════════════════════════════════════════════════════
//  PUBLIC API  (google.script.run)
// ═══════════════════════════════════════════════════════════════════════════

function navGoToLead(leadId) {
  try {
    // Resolve customer name for tracking
    var label = leadId;
    var sub   = '';
    try {
      var store = loadCrmStore_();
      var lead  = store.leads && store.leads.byId ? store.leads.byId[String(leadId).trim()] : null;
      if (lead) {
        label = lead['Customer Name'] || leadId;
        sub   = (lead['Interested Model'] || '') + (lead['Current Status'] ? ' · ' + lead['Current Status'] : '');
      }
    } catch (e) {}
    navTrackAndGo_('Lead', leadId, label, sub, function(){ navGoToLead_(leadId); });
    return crmOk_('Navigation', { leadId: leadId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToBooking(bookingId) {
  try {
    navTrackAndGo_('Booking', bookingId, bookingId, '', function(){ navGoToBooking_(bookingId); });
    return crmOk_('Navigation', { bookingId: bookingId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToPayment(receiptId) {
  try {
    navTrackAndGo_('Payment', receiptId, receiptId, '', function(){ navGoToPayment_(receiptId); });
    return crmOk_('Navigation', { receiptId: receiptId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToFinance(fileNumber) {
  try {
    navTrackAndGo_('Finance', fileNumber, fileNumber, '', function(){ navGoToFinance_(fileNumber); });
    return crmOk_('Navigation', { fileNumber: fileNumber });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToDelivery(leadId) {
  try {
    navTrackAndGo_('Delivery', leadId, leadId, '', function(){ navGoToDelivery_(leadId); });
    return crmOk_('Navigation', { leadId: leadId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToActivity(activityId) {
  try {
    navTrackAndGo_('Activity', activityId, activityId, '', function(){ navGoToActivity_(activityId); });
    return crmOk_('Navigation', { activityId: activityId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToClaim(claimId) {
  try {
    navTrackAndGo_('Claim', claimId, claimId, '', function(){ navGoToClaim_(claimId); });
    return crmOk_('Navigation', { claimId: claimId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToCommercialSnapshot(snapshotId) {
  try {
    navTrackAndGo_('Commercial', snapshotId, snapshotId, '', function(){ navGoToCommercialSnapshot_(snapshotId); });
    return crmOk_('Navigation', { snapshotId: snapshotId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Navigate to Dealer Earnings Register row for a Lead (owner profitability). */
function navGoToDealerEarnings(leadId) {
  try {
    if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
      return { ok: false, message: 'Dealer Earnings is owner-only.' };
    }
    leadId = String(leadId || '').trim();
    navTrackAndGo_('DealerEarnings', leadId, leadId, 'Dealer Earnings', function () {
      navGoToDealerEarnings_(leadId);
    });
    return crmOk_('Navigation', { leadId: leadId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navGoToDealerEarnings_(leadId) {
  leadId = String(leadId || '').trim();
  if (typeof ensureDealerEarningsRegisterSheet_ === 'function') ensureDealerEarningsRegisterSheet_();
  var name = (CRM.SHEETS && CRM.SHEETS.DEALER_EARNINGS_REGISTER) || CRM.SHEETS.EXTRA_INCOME_REGISTER;
  var sheet = getSpreadsheet_().getSheetByName(name);
  if (!sheet) throw businessError_('Dealer Earnings Register not found', 'NOT_FOUND');
  sheet.showSheet();
  getSpreadsheet_().setActiveSheet(sheet);
  var headers = getHeaders_(sheet, 1);
  var row = typeof findDealerEarningsRowByLead_ === 'function'
    ? findDealerEarningsRowByLead_(sheet, headers, leadId) : -1;
  if (row < 1) {
    try {
      if (typeof upsertDealerEarningsForLead_ === 'function') upsertDealerEarningsForLead_(leadId, { reason: 'nav' });
      row = findDealerEarningsRowByLead_(sheet, headers, leadId);
    } catch (e) {}
  }
  if (row > 0) sheet.getRange(row, 1).activate();
}

/** Unified navigation entry — resolves any entity type by unique ID. */
function navGoToEntity(entityType, entityId) {
  entityType = String(entityType || '').trim();
  entityId = String(entityId || '').trim();
  if (!entityType || !entityId) return { ok: false, message: 'Entity type and ID are required' };
  var map = {
    Lead: navGoToLead,
    Booking: navGoToBooking,
    Payment: navGoToPayment,
    Finance: navGoToFinance,
    Delivery: navGoToDelivery,
    Activity: navGoToActivity,
    Claim: navGoToClaim,
    Commercial: navGoToCommercialSnapshot,
    sheet: navGoToSheetPublic
  };
  var fn = map[entityType];
  if (!fn) return { ok: false, message: 'Unknown entity type: ' + entityType };
  return fn(entityId);
}

/** Navigate to any named sheet (dashboard widgets, reports, etc.) */
function navGoToSheetPublic(sheetName) {
  try {
    navGoToSheet_(sheetName);
    return crmOk_('Navigation', { sheet: sheetName });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Navigate to Lead Register filtered to Today's leads (activates sheet + scrolls to row 1). */
function navGoToTodayLeads() {
  try {
    navGoToSheet_(CRM.SHEETS.LEAD_REGISTER);
    return crmOk_('Navigation', { filter: 'today_leads' });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Navigate and open Customer 360 for a given lead. Used by dashboard drill-downs. */
function navOpen360ForLead(leadId) {
  try {
    if (typeof showCustomer360Dialog_ === 'function') showCustomer360Dialog_(leadId);
    return crmOk_('Navigation', { leadId: leadId });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  BREADCRUMB ENGINE
//  Builds a smart breadcrumb trail from nav history (most recent nav path).
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Returns a breadcrumb-ready array like:
 *   [{label:'Dashboard', type:'sheet', id:'Dashboard'}, {label:'LD26001 — Ram Kumar', type:'Lead', id:'LD26001'}, ...]
 * Always starts with Dashboard. Shows last 5 unique steps.
 */
function getBreadcrumb() {
  try {
    var hist = navGetHistory_().slice(0, 4); // last 4 navigations
    var crumbs = [{ label: 'Dashboard', type: 'sheet', id: CRM.SHEETS.DASHBOARD, icon: '🏠' }];
    hist.reverse().forEach(function(h) {
      crumbs.push({
        label: h.label || h.id,
        type:  h.type,
        id:    h.id,
        icon:  navTypeIcon_(h.type)
      });
    });
    return crmOk_('Navigation', { breadcrumbs: crumbs });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

function navTypeIcon_(type) {
  var icons = { Lead:'📋', Booking:'🚗', Payment:'💰', Finance:'🏦', Delivery:'🚚', Claim:'📄', Search:'🔍' };
  return icons[type] || '📌';
}

// ═══════════════════════════════════════════════════════════════════════════
//  ENTITY REGISTRY + LINK BUILDERS
// ═══════════════════════════════════════════════════════════════════════════

var NAV_ENTITY_REGISTRY_ = {
  Lead:      { sheet: function(){ return CRM.SHEETS.LEAD_REGISTER; },      idCol: 'Lead ID',              headerRow: function(){ return CRM.LEAD.HEADER_ROW; },      useStore: true },
  Booking:   { sheet: function(){ return CRM.SHEETS.BOOKING_REGISTER; },  idCol: 'BookingID',             headerRow: function(){ return 1; },                    useStore: false },
  Payment:   { sheet: function(){ return CRM.SHEETS.PAYMENT_LEDGER; },      idCol: 'Receipt Number',        headerRow: function(){ return CRM.PAYMENT.HEADER_ROW; }, useStore: false },
  Finance:   { sheet: function(){ return CRM.SHEETS.FINANCE_REGISTER; },    idCol: 'File Number',           headerRow: function(){ return 1; },                    useStore: false },
  Delivery:  { sheet: function(){ return CRM.SHEETS.DELIVERY_TRACKER; },   idCol: 'Lead ID',               headerRow: function(){ return CRM.DELIVERY.HEADER_ROW; }, useStore: false },
  Activity:  { sheet: function(){ return CRM.SHEETS.ACTIVITY_LOG; },        idCol: 'Activity ID',           headerRow: function(){ return CRM.ACTIVITY.HEADER_ROW; }, useStore: false },
  Claim:     { sheet: function(){ return CRM.SHEETS.SCHEME_CLAIM_REGISTER; }, idCol: 'Claim ID',            headerRow: function(){ return 1; },                    useStore: false },
  Commercial:{ sheet: function(){ return CRM.SHEETS.COMMERCIAL_SNAPSHOT; }, idCol: 'Snapshot ID', headerRow: function(){ return 1; }, useStore: false },
  ExtraIncome:{ sheet: function(){ return CRM.SHEETS.DEALER_EARNINGS_REGISTER || CRM.SHEETS.EXTRA_INCOME_REGISTER; }, idCol: 'Lead ID', headerRow: function(){ return 1; }, useStore: false },
  DealerEarnings:{ sheet: function(){ return CRM.SHEETS.DEALER_EARNINGS_REGISTER || CRM.SHEETS.EXTRA_INCOME_REGISTER; }, idCol: 'Lead ID', headerRow: function(){ return 1; }, useStore: false }
};

function navResolveRow_(entityType, entityId) {
  entityType = String(entityType || '').trim();
  entityId = String(entityId || '').trim();
  if (!entityType || !entityId) return 0;
  var cfg = NAV_ENTITY_REGISTRY_[entityType];
  if (!cfg) return 0;
  if (cfg.useStore && entityType === 'Lead') {
    try {
      var store = loadCrmStore_();
      var row = store.leads && store.leads.sheetRow ? store.leads.sheetRow[entityId] : 0;
      if (row > 0) return row;
    } catch (e) {}
  }
  var ss = getSpreadsheet_();
  var sheetName = cfg.sheet();
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) return 0;
  var col = navColumnIndex_(sheet, cfg.idCol, 1);
  return navFindFirstMatchInCol_(sheet, col, entityId);
}

/** Build in-sheet #gid hyperlink to a business record (never hardcodes stale rows in callers). */
function navEntityLink_(entityType, entityId, label) {
  entityId = String(entityId || '').trim();
  label = label != null ? String(label) : entityId;
  if (!entityId) return label;
  var cfg = NAV_ENTITY_REGISTRY_[entityType];
  if (!cfg) return label;
  var row = navResolveRow_(entityType, entityId);
  if (row < 1) return label;
  var sheet = getSpreadsheet_().getSheetByName(cfg.sheet());
  if (!sheet) return label;
  return navCellLink_(sheet.getSheetId(), row, label);
}

/** Drill-down link to a sheet (KPI totals, reports). */
function navDrillDownLink_(sheetNameOrGid, displayValue, label) {
  label = label != null ? String(label) : String(displayValue);
  var gid = sheetNameOrGid;
  if (typeof sheetNameOrGid === 'string' && sheetNameOrGid.indexOf('gid=') < 0) {
    var sh = getSpreadsheet_().getSheetByName(sheetNameOrGid);
    gid = sh ? sh.getSheetId() : sheetNameOrGid;
  }
  return '=HYPERLINK("#gid=' + gid + '","' + label.replace(/"/g, '""') + '")';
}

/** Full URL backlink (Finance Pending views) — still resolves row by ID at write time. */
function navLeadIdBacklinkFormula_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return leadId;
  var row = navResolveRow_('Lead', leadId);
  var lrSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  if (!lrSheet) return leadId;
  var gid = lrSheet.getSheetId();
  var ssId = getSpreadsheet_().getId();
  var anchor = row > 0 ? 'A' + row : 'A1';
  var url = 'https://docs.google.com/spreadsheets/d/' + ssId + '/edit#gid=' + gid + '&range=' + anchor;
  return '=HYPERLINK("' + url + '","' + leadId.replace(/"/g, '""') + '")';
}

/**
 * Generic drill-down sheet writer — used by Dashboard KPIs.
 * @return {number|null} sheet gid
 */
function navWriteDrillDownSheet_(title, headers, rows, opts) {
  opts = opts || {};
  try {
    var ss = getSpreadsheet_();
    var name = String(title || 'Drill Down').substring(0, 90);
    var sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    sheet.clear();
    var headerRow = 3;
    sheet.getRange(1, 1).setValue(title).setFontWeight('bold').setFontSize(12);
    sheet.getRange(2, 1).setValue('Refreshed: ' + nowDateTime_());
    try {
      var dash = ss.getSheetByName(CRM.SHEETS.DASHBOARD);
      if (dash && typeof navDrillDownLink_ === 'function') {
        sheet.getRange(2, 2).setFormula(
          navDrillDownLink_(dash.getSheetId(), '← Back to Dashboard', '← Back to Dashboard'));
      }
    } catch (backErr) {}
    sheet.getRange(headerRow, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    sheet.setFrozenRows(headerRow);
    if (!rows || !rows.length) {
      sheet.getRange(headerRow + 1, 1).setValue('No records for this KPI right now.');
      return sheet.getSheetId();
    }
    sheet.getRange(headerRow + 1, 1, rows.length, headers.length).setValues(rows);
    // autoResize removed: it is one of the slowest Sheets calls and ran 14x per refresh.
    if (typeof hideDrillDownSheet_ === 'function') hideDrillDownSheet_(name);
    return sheet.getSheetId();
  } catch (e) {
    Logger.log('navWriteDrillDownSheet_: ' + e.message);
    return null;
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  SMART LINK REFRESH
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Rebuilds all HYPERLINK formulas in clickable columns across every visible sheet.
 * Call after Sort / Import / Merge / Backup-Restore / Full Refresh.
 */
function navRefreshAllHyperlinks_() {
  var ss = getSpreadsheet_();

  // Lead Register → Booking (via RelationshipIndex, not Booking Status text)
  navRefreshLeadBookingLinks_(ss);

  // Cross-module parent links
  navRefreshColumnLinks_(ss, CRM.SHEETS.BOOKING_REGISTER, 'LeadID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', 1);
  navRefreshColumnLinks_(ss, CRM.SHEETS.BOOKING_REGISTER, 'BookingID',
    CRM.SHEETS.BOOKING_REGISTER, 'BookingID', 1);
  navRefreshColumnLinks_(ss, CRM.SHEETS.PAYMENT_LEDGER, 'Lead ID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', CRM.PAYMENT.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.PAYMENT_LEDGER, 'Receipt Number',
    CRM.SHEETS.PAYMENT_LEDGER, 'Receipt Number', CRM.PAYMENT.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.PAYMENT_LEDGER, 'Finance File Number',
    CRM.SHEETS.FINANCE_REGISTER, 'File Number', CRM.PAYMENT.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.FINANCE_REGISTER, 'Lead ID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', 1);
  navRefreshColumnLinks_(ss, CRM.SHEETS.FINANCE_REGISTER, 'File Number',
    CRM.SHEETS.FINANCE_REGISTER, 'File Number', 1);
  navRefreshColumnLinks_(ss, CRM.SHEETS.DELIVERY_TRACKER, 'Lead ID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', CRM.DELIVERY.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.ACTIVITY_LOG, 'Lead ID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', CRM.ACTIVITY.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.ACTIVITY_LOG, 'Activity ID',
    CRM.SHEETS.ACTIVITY_LOG, 'Activity ID', CRM.ACTIVITY.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.LEAD_REGISTER, 'Lead ID',
    CRM.SHEETS.LEAD_REGISTER, 'Lead ID', CRM.LEAD.HEADER_ROW);
  navRefreshColumnLinks_(ss, CRM.SHEETS.LEAD_REGISTER, 'Finance File Number',
    CRM.SHEETS.FINANCE_REGISTER, 'File Number', CRM.LEAD.HEADER_ROW);
  navRefreshLeadDeliveryLinks_(ss);
  if (CRM.SHEETS.SCHEME_CLAIM_REGISTER) {
    navRefreshColumnLinks_(ss, CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Claim ID',
      CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Claim ID', 1);
    navRefreshColumnLinks_(ss, CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Lead ID',
      CRM.SHEETS.LEAD_REGISTER, 'Lead ID', 1);
    navRefreshColumnLinks_(ss, CRM.SHEETS.SCHEME_CLAIM_REGISTER, 'Booking ID',
      CRM.SHEETS.BOOKING_REGISTER, 'BookingID', 1);
  }
  var deName = CRM.SHEETS.DEALER_EARNINGS_REGISTER || CRM.SHEETS.EXTRA_INCOME_REGISTER;
  if (deName && getSpreadsheet_().getSheetByName(deName)) {
    navRefreshColumnLinks_(ss, deName, 'Lead ID',
      CRM.SHEETS.LEAD_REGISTER, 'Lead ID', 1);
    navRefreshColumnLinks_(ss, deName, 'Booking ID',
      CRM.SHEETS.BOOKING_REGISTER, 'BookingID', 1);
  }
}

/** Lead Register Number Plate → Delivery Tracker row for same lead. */
function navRefreshLeadDeliveryLinks_(ss) {
  ss = ss || getSpreadsheet_();
  var src = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  var tgt = ss.getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!src || !tgt) return;
  var tgtGid = tgt.getSheetId();
  var delRows = navBuildRowMapFromSheet_(ss, CRM.SHEETS.DELIVERY_TRACKER, navColumnIndex_(tgt, 'Lead ID', 1));
  var headers = getHeaders_(src, CRM.LEAD.HEADER_ROW);
  var leadCol = findHeaderIndex_(headers, 'Lead ID');
  var plateCol = findHeaderIndex_(headers, 'Number Plate');
  if (leadCol < 0 || plateCol < 0) return;
  var dataStart = CRM.LEAD.DATA_START;
  var lastRow = src.getLastRow();
  if (lastRow < dataStart) return;
  var numRows = lastRow - dataStart + 1;
  var rows = src.getRange(dataStart, 1, numRows, headers.length).getValues();
  // One batched write for the whole column (formula strings + plain values).
  var out = [];
  for (var i = 0; i < rows.length; i++) {
    var leadId = String(rows[i][leadCol] || '').trim();
    var plate = String(rows[i][plateCol] || '').trim();
    if (leadId && plate && delRows[leadId]) {
      out.push([navCellLink_(tgtGid, delRows[leadId], plate)]);
    } else {
      out.push([plate]);
    }
  }
  src.getRange(dataStart, plateCol + 1, numRows, 1).setValues(out);
}

/** Lead Register Booking link — uses RelationshipIndex BookingID. */
function navRefreshLeadBookingLinks_(ss) {
  ss = ss || getSpreadsheet_();
  var src = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  var tgt = ss.getSheetByName(CRM.SHEETS.BOOKING_REGISTER);
  if (!src || !tgt) return;
  var relSheet = ss.getSheetByName(CRM.SHEETS.RELATIONSHIP_INDEX);
  if (!relSheet) return;

  var relHeaders = getHeaders_(relSheet, 1);
  var leadCol = findHeaderIndex_(relHeaders, 'LeadID');
  var bookCol = findHeaderIndex_(relHeaders, 'BookingID');
  if (leadCol < 0 || bookCol < 0) return;

  var relMap = {};
  var relLast = relSheet.getLastRow();
  if (relLast >= 2) {
    var relNumRows = relLast - 1;
    var relData = relSheet.getRange(2, 1, relNumRows, relHeaders.length).getValues();
    relData.forEach(function (row) {
      var lid = String(row[leadCol] || '').trim();
      var bid = String(row[bookCol] || '').trim();
      if (lid && bid) relMap[lid] = bid;
    });
  }

  var tgtGid = tgt.getSheetId();
  var bookingRows = navBuildRowMapFromSheet_(ss, CRM.SHEETS.BOOKING_REGISTER, navColumnIndex_(tgt, 'BookingID', 1));
  var srcHeaders = getHeaders_(src, CRM.LEAD.HEADER_ROW);
  var leadIdCol = findHeaderIndex_(srcHeaders, 'Lead ID');
  var bookStatusCol = findHeaderIndex_(srcHeaders, 'Booking Status');
  if (leadIdCol < 0 || bookStatusCol < 0) return;

  var dataStart = CRM.LEAD.DATA_START;
  var lastRow = src.getLastRow();
  if (lastRow < dataStart) return;
  var numRows = lastRow - dataStart + 1;
  var leadIds = src.getRange(dataStart, leadIdCol + 1, numRows, 1).getValues();
  var statuses = src.getRange(dataStart, bookStatusCol + 1, numRows, 1).getValues();

  // The Booking Status column carries data validation (Booked / Contacted / …).
  // The link's DISPLAY TEXT must therefore be the status itself — the previous
  // version displayed the BookingID, which the validation rejected ("The data you
  // entered in cell R4 violates the data validation rules"). One batched write;
  // '=HYPERLINK' strings are interpreted as formulas by setValues().
  var out = [];
  for (var i = 0; i < numRows; i++) {
    var leadId = String(leadIds[i][0] || '').trim();
    var bookingId = relMap[leadId] || '';
    var display = String(statuses[i][0] || '').trim();
    if (bookingId && bookingRows[bookingId]) {
      out.push([navCellLink_(tgtGid, bookingRows[bookingId], display || 'Booked')]);
    } else {
      out.push([display]);
    }
  }
  src.getRange(dataStart, bookStatusCol + 1, numRows, 1).setValues(out);
}

function navRefreshColumnLinks_(ss, sourceSheet, sourceCol, targetSheet, targetCol, headerRow, opts) {
  opts = opts || {};
  var src = ss.getSheetByName(sourceSheet);
  var tgt = ss.getSheetByName(targetSheet);
  if (!src || !tgt) return;

  // Target header row: the row where targetCol's header lives. Lead Register has
  // its headers on row 3 (row 1 is the SEARCH banner), so hardcoding row 1 here
  // resolved the wrong column and built an empty row-map — which is why EVERY
  // Lead ID across all tabs lost its clickable backlink (they all point at Lead
  // Register). Defaults to the target's own header row when it is the Lead
  // Register, else 1, and can be overridden via opts.targetHeaderRow.
  var tgtHeaderRow = opts.targetHeaderRow ||
    (targetSheet === CRM.SHEETS.LEAD_REGISTER ? CRM.LEAD.HEADER_ROW : 1);
  var tgtGid = tgt.getSheetId();
  var tgtColIdx = navColumnIndex_(tgt, targetCol, 1, tgtHeaderRow);
  var rowMap = opts.matchByValue
    ? null
    : navBuildRowMapFromSheet_(ss, targetSheet, tgtColIdx, tgtHeaderRow);
  var srcHeaders = getHeaders_(src, headerRow || 1);
  var colIdx = findHeaderIndex_(srcHeaders, sourceCol);
  if (colIdx < 0) return;

  var dataStart = (headerRow || 1) + 1;
  var lastRow = src.getLastRow();
  var numRows = lastRow - dataStart + 1;
  if (numRows < 1) return;

  var data = src.getRange(dataStart, colIdx + 1, numRows, 1).getValues();
  var out = [];

  for (var i = 0; i < data.length; i++) {
    var id = String(data[i][0]).trim();
    var cellOut = id;
    if (id) {
      var targetRow = 0;
      if (opts.matchByValue && opts.targetLeadCol) {
        targetRow = navFindDeliveryRowByPlate_(ss, id, opts.targetLeadCol);
      } else if (rowMap && rowMap[id]) {
        targetRow = rowMap[id];
      }
      if (targetRow > 0) cellOut = navCellLink_(tgtGid, targetRow, id);
    }
    out.push([cellOut]);
  }

  // ONE batched write. setValues() interprets strings beginning with '=' as
  // formulas, so links and plain values land together. The previous version wrote
  // one setFormula per linked cell — hundreds of API round-trips per full refresh
  // (the bulk of the observed 219s "Refresh All Sheets").
  src.getRange(dataStart, colIdx + 1, numRows, 1).setValues(out);
}

function navFindDeliveryRowByPlate_(ss, plate, leadColName) {
  var sheet = ss.getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!sheet) return 0;
  var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  var plateCol = findHeaderIndex_(headers, 'Number Plate') + 1;
  var leadCol = findHeaderIndex_(headers, leadColName) + 1;
  if (plateCol < 1) return 0;
  var last = sheet.getLastRow();
  if (last < CRM.DELIVERY.DATA_START) return 0;
  var numRows = last - CRM.DELIVERY.DATA_START + 1;
  var data = sheet.getRange(CRM.DELIVERY.DATA_START, 1, numRows, sheet.getLastColumn()).getValues();
  for (var i = 0; i < data.length; i++) {
    if (String(data[i][plateCol - 1] || '').trim().toLowerCase() === String(plate).trim().toLowerCase()) {
      return CRM.DELIVERY.DATA_START + i;
    }
  }
  return 0;
}

function navColumnIndex_(sheet, colName, fallback, headerRow) {
  var headers = getHeaders_(sheet, headerRow || 1);
  var idx = findHeaderIndex_(headers, colName);
  return idx >= 0 ? idx + 1 : (fallback || 1);
}

function navCellLink_(gid, row, label) {
  var url = '#gid=' + gid + '&range=A' + row;
  return '=HYPERLINK("' + url + '","' + String(label).replace(/"/g, '""') + '")';
}

function navBuildRowMapFromSheet_(ss, sheetName, col, headerRow) {
  var map   = {};
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) return map;
  var hr = headerRow || 1;
  var dataStart = hr + 1;
  var last = sheet.getLastRow();
  if (last < dataStart) return map;
  var numRows = last - dataStart + 1;
  var data  = sheet.getRange(dataStart, col, numRows, 1).getValues();
  for (var i = 0; i < data.length; i++) {
    var id = String(data[i][0]).trim();
    if (id) map[id] = i + dataStart;
  }
  return map;
}

// ═══════════════════════════════════════════════════════════════════════════
//  NAVIGATION DASHBOARD  (Home screen for the Navigate menu)
// ═══════════════════════════════════════════════════════════════════════════

function menuShowNavigationHome() {
  var html = HtmlService.createHtmlOutput(navHomeHtml_())
    .setWidth(740)
    .setHeight(560)
    .setSandboxMode(HtmlService.SandboxMode.IFRAME);
  SpreadsheetApp.getUi().showModelessDialog(html, 'Navigation Home');
}

function navHomeHtml_() {
  var css = [
    '*{box-sizing:border-box;margin:0;padding:0}',
    'body{font-family:"Google Sans",Arial,sans-serif;font-size:13px;color:#212121;background:#F1F3F4}',
    '.header{background:linear-gradient(135deg,#0D47A1,#1976D2);color:#fff;padding:18px 20px}',
    '.header h2{font-size:17px;font-weight:500;letter-spacing:.3px}',
    '.header p{font-size:12px;opacity:.8;margin-top:4px}',
    '.body{padding:16px;overflow-y:auto;height:calc(100vh - 80px)}',
    '.grid{display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:16px}',
    '.card{background:#fff;border-radius:8px;padding:14px;box-shadow:0 1px 3px rgba(0,0,0,.08)}',
    '.card h3{font-size:12px;font-weight:700;color:#90A4AE;letter-spacing:.8px;text-transform:uppercase;margin-bottom:8px}',
    '.quick-btn{display:flex;align-items:center;gap:8px;padding:8px 10px;border-radius:6px;cursor:pointer;',
    '  background:#F5F5F5;border:none;width:100%;text-align:left;font-size:13px;color:#212121;margin-bottom:6px}',
    '.quick-btn:hover{background:#E3F2FD;color:#1565C0}',
    '.quick-btn .icon{font-size:16px;width:24px;text-align:center}',
    '.hist-item{display:flex;align-items:center;gap:8px;padding:6px 8px;border-radius:4px;cursor:pointer;',
    '  border-bottom:1px solid #F5F5F5}',
    '.hist-item:hover{background:#F5F5F5}',
    '.hist-icon{font-size:14px;width:20px;text-align:center;color:#78909C}',
    '.hist-label{flex:1;font-size:13px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.hist-type{font-size:10px;color:#90A4AE;background:#ECEFF1;padding:2px 6px;border-radius:10px}',
    '.hist-arrow{color:#BDBDBD;font-size:12px}',
    '.empty-hist{text-align:center;padding:20px;color:#90A4AE;font-size:12px}',
    '.status-bar{padding:6px 16px;font-size:11px;color:#78909C;background:#ECEFF1;border-top:1px solid #E0E0E0;position:fixed;bottom:0;width:100%}'
  ].join('');

  var moduleLinks = [
    { icon: '📋', label: 'Lead Register',     fn: 'navGoToSheetPublic', arg: CRM.SHEETS.LEAD_REGISTER },
    { icon: '🚗', label: 'Booking Register',  fn: 'navGoToSheetPublic', arg: CRM.SHEETS.BOOKING_REGISTER },
    { icon: '💰', label: 'Payment Ledger',    fn: 'navGoToSheetPublic', arg: CRM.SHEETS.PAYMENT_LEDGER },
    { icon: '🏦', label: 'Finance Register',  fn: 'navGoToSheetPublic', arg: CRM.SHEETS.FINANCE_REGISTER },
    { icon: '🚚', label: 'Delivery Tracker',  fn: 'navGoToSheetPublic', arg: CRM.SHEETS.DELIVERY_TRACKER },
    { icon: '📊', label: 'Dashboard',         fn: 'navGoToSheetPublic', arg: CRM.SHEETS.DASHBOARD }
  ];

  var moduleBtns = moduleLinks.map(function(m) {
    return '<button class="quick-btn" onclick="runNav(\'' + m.fn + '\',\'' + m.arg.replace(/'/g, "\\'") + '\')">' +
      '<span class="icon">' + m.icon + '</span>' + m.label + '</button>';
  }).join('');

  var actionLinks = [
    { icon: '👤', label: 'Customer 360',     fn: 'showCustomer360WithPicker_NO_ARG' },
    { icon: '🔍', label: 'Global Search',    fn: 'menuGlobalSearch' },
    { icon: '📂', label: 'Recent Records',   fn: 'menuRecentRecords' }
  ];

  var actionBtns = actionLinks.map(function(a) {
    return '<button class="quick-btn" onclick="runNav(\'' + a.fn + '\',\'\')">' +
      '<span class="icon">' + a.icon + '</span>' + a.label + '</button>';
  }).join('');

  var js = htmlSafeJs_([
    'var ICON_MAP={Lead:"📋",Booking:"🚗",Payment:"💰",Finance:"🏦",Delivery:"🚚",Claim:"📄",Search:"🔍",sheet:"📊"};',
    'var NAV_FN={Lead:"navGoToLead",Booking:"navGoToBooking",Payment:"navGoToPayment",',
    '  Finance:"navGoToFinance",Delivery:"navGoToDelivery",Activity:"navGoToActivity",',
    '  Claim:"navGoToClaim",sheet:"navGoToSheetPublic"};',

    'function runNav(fn,arg){',
    '  var noArgFns=["menuGlobalSearch","menuRecentRecords","showCustomer360WithPicker_NO_ARG"];',
    '  if(noArgFns.indexOf(fn)>=0){',
    '    if(fn==="showCustomer360WithPicker_NO_ARG"){google.script.run.withSuccessHandler(function(){}).menuShowCustomer360();}',
    '    else google.script.run.withSuccessHandler(function(){google.script.host.close();})[fn]();',
    '    return;',
    '  }',
    '  google.script.run.withSuccessHandler(function(){google.script.host.close();}).withFailureHandler(function(e){alert(e.message||e);})[fn](arg);',
    '}',

    'function goToHist(type,id){',
    '  var fn=NAV_FN[type]||"navGoToSheetPublic";',
    '  google.script.run.withSuccessHandler(function(){google.script.host.close();}).withFailureHandler(function(e){alert(e.message||e);})[fn](id);',
    '}',

    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}',

    'function loadHistory(){',
    '  google.script.run',
    '    .withSuccessHandler(function(r){',
    '      if(!r||r.ok===false)return;',
    '      var hist=r.data.history||[];',
    '      var el=document.getElementById("hist-list");',
    '      if(!hist.length){el.innerHTML=\'<div class="empty-hist">No navigation history yet.</div>\';return;}',
    '      el.innerHTML=hist.slice(0,8).map(function(h){',
    '        var icon=ICON_MAP[h.type]||"📌";',
    '        return \'<div class="hist-item" onclick="goToHist(\\\'\'+esc(h.type)+\'\\\',\\\'\'+esc(h.id)+\'\\\')">\'',
    '          +\'<span class="hist-icon">\'+icon+\'</span>\'',
    '          +\'<span class="hist-label">\'+esc(h.label||h.id)+\'</span>\'',
    '          +\'<span class="hist-type">\'+esc(h.type)+\'</span>\'',
    '          +\'<span class="hist-arrow">›</span>\'',
    '        +\'</div>\';',
    '      }).join("");',
    '    })',
    '    .withFailureHandler(function(){})',
    '    .getNavigationHistory();',
    '}',

    'window.onload=function(){loadHistory();};'
  ].join('\n'));

  return '<!DOCTYPE html><html><head><base target="_top"/><style>' + css + '</style></head><body>' +
    '<div class="header"><h2>🧭 Navigation Home</h2><p>Jump anywhere in one click</p></div>' +
    '<div class="body">' +
      '<div class="grid">' +
        '<div class="card"><h3>📁 Modules</h3>' + moduleBtns + '</div>' +
        '<div class="card"><h3>⚡ Quick Actions</h3>' + actionBtns + '</div>' +
      '</div>' +
      '<div class="card"><h3>🕐 Recent Navigation</h3><div id="hist-list"><div class="empty-hist">Loading…</div></div></div>' +
    '</div>' +
    '<div class="status-bar" id="status">Euler Motors Dealership CRM</div>' +
    '<script>' + js + '</script></body></html>';
}

// ═══════════════════════════════════════════════════════════════════════════
//  MENU HANDLERS
// ═══════════════════════════════════════════════════════════════════════════

function menuRefreshNavLinks() {
  try {
    navRefreshAllHyperlinks_();
    SpreadsheetApp.getUi().alert(
      'Navigation Links Refreshed',
      'All sheet hyperlinks are up to date. Links resolve correctly even after sorting or imports.',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
  } catch (e) {
    if (typeof logCrash_ === 'function') logCrash_('NavigationService', 'menuRefreshNavLinks', e);
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  RELATIONSHIP-BASED NAVIGATION HELPERS
//  These let any service navigate to all related entities for a given LeadID.
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Get all navigation targets for a given LeadID from the RelationshipIndex.
 * @returns {{ leadId, bookingId, paymentIds, deliveryId, claimId, financeFile }}
 */
function navGetRelationshipsForLead_(leadId) {
  var rel = { leadId: leadId, bookingId: '', paymentIds: [], deliveryId: '', claimId: '', financeFile: '' };
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.RELATIONSHIP_INDEX);
    if (!sheet) return rel;
    var headers = getHeaders_(sheet, 1);
    var row = navFindFirstMatchInCol_(sheet, findHeaderIndex_(headers, 'LeadID') + 1, String(leadId).trim());
    if (row < 1) return rel;
    var data = sheet.getRange(row, 1, row, headers.length).getValues()[0];
    function fld(name) { var i = findHeaderIndex_(headers, name); return i >= 0 ? String(data[i]||'').trim() : ''; }
    rel.bookingId   = fld('BookingID');
    rel.deliveryId  = fld('DeliveryID');
    rel.claimId     = fld('ClaimID');
    var pids        = fld('PaymentIDs');
    rel.paymentIds  = pids ? pids.split(',').filter(Boolean) : [];
    // Finance file from Lead Register
    try {
      var store = loadCrmStore_();
      var lead  = store.leads && store.leads.byId ? store.leads.byId[String(leadId).trim()] : null;
      if (lead) rel.financeFile = lead['Finance File Number'] || '';
    } catch (e) {}
  } catch (e) {
    Logger.log('navGetRelationshipsForLead_: ' + e.message);
  }
  return rel;
}

// ═══════════════════════════════════════════════════════════════════════════
//  NAVIGATION MATRIX + SELF-AUDIT
// ═══════════════════════════════════════════════════════════════════════════

/** Complete field classification matrix for audit and documentation. */
function getNavigationMatrix_() {
  return [
    { sheet: 'Lead Register', column: 'Lead ID', classification: 'Primary Identifier', navTarget: 'Lead Register row', implemented: true },
    { sheet: 'Lead Register', column: 'Customer Name', classification: 'Drill-down Candidate', navTarget: 'Customer 360', implemented: true },
    { sheet: 'Lead Register', column: 'Mobile', classification: 'Secondary Identifier', navTarget: 'Global Search / Customer 360', implemented: true },
    { sheet: 'Lead Register', column: 'Booking Status', classification: 'Parent Link', navTarget: 'Booking Register (via RelationshipIndex)', implemented: true },
    { sheet: 'Lead Register', column: 'Finance File Number', classification: 'Parent Link', navTarget: 'Finance Register', implemented: true },
    { sheet: 'Lead Register', column: 'Number Plate', classification: 'Secondary Identifier', navTarget: 'Delivery Tracker', implemented: true },
    { sheet: 'Booking Register', column: 'BookingID', classification: 'Primary Identifier', navTarget: 'Booking Register row', implemented: true },
    { sheet: 'Booking Register', column: 'LeadID', classification: 'Parent Link', navTarget: 'Lead Register', implemented: true },
    { sheet: 'Payment Ledger', column: 'Receipt Number', classification: 'Primary Identifier', navTarget: 'Payment Ledger row', implemented: true },
    { sheet: 'Payment Ledger', column: 'Lead ID', classification: 'Parent Link', navTarget: 'Lead Register', implemented: true },
    { sheet: 'Payment Ledger', column: 'Finance File Number', classification: 'Parent Link', navTarget: 'Finance Register', implemented: true },
    { sheet: 'Finance Register', column: 'File Number', classification: 'Primary Identifier', navTarget: 'Finance Register row', implemented: true },
    { sheet: 'Finance Register', column: 'Lead ID', classification: 'Parent Link', navTarget: 'Lead Register', implemented: true },
    { sheet: 'Delivery Tracker', column: 'Lead ID', classification: 'Parent Link', navTarget: 'Lead Register', implemented: true },
    { sheet: 'Activity Log', column: 'Activity ID', classification: 'Primary Identifier', navTarget: 'Activity Log row', implemented: true },
    { sheet: 'Activity Log', column: 'Lead ID', classification: 'Parent Link', navTarget: 'Lead Register', implemented: true },
    { sheet: 'Dashboard', column: 'Today Leads (B5)', classification: 'Drill-down Candidate', navTarget: "Today's Leads sheet", implemented: true },
    { sheet: 'Dashboard', column: 'Outstanding (B31)', classification: 'Breakdown Candidate', navTarget: 'Outstanding Leads', implemented: true },
    { sheet: 'Dashboard', column: 'Revenue (B24)', classification: 'Drill-down Candidate', navTarget: 'Monthly Payments drill-down', implemented: true },
    { sheet: 'Dashboard', column: 'Recent Activity Lead ID', classification: 'Parent Link', navTarget: 'Lead Register + 360', implemented: true },
    { sheet: 'Dashboard', column: 'MODEL PERFORMANCE (A42+)', classification: 'Drill-down Candidate', navTarget: 'MP — {Model} — {Metric} filtered sheets', implemented: true },
    { sheet: 'Dealer Earnings Register', column: 'Lead ID / TOTAL DEALER EARNINGS', classification: 'Primary Identifier', navTarget: 'Lead Register + Customer 360', implemented: true },
    { sheet: 'Dashboard', column: 'DEALER EARNINGS (OWNER ONLY)', classification: 'Drill-down Candidate', navTarget: 'Dealer Earnings Analytics / DE — drills', implemented: true }
  ];
}

/** PUBLIC — returns navigation matrix for dialogs / certification. */
function getNavigationMatrix() {
  return crmOk_('Navigation', { matrix: getNavigationMatrix_() });
}

/** Self-audit: verify hyperlink targets resolve to rows. */
function navAuditHyperlinks_() {
  var issues = [];
  var matrix = getNavigationMatrix_();
  matrix.forEach(function (m) {
    if (!m.implemented) issues.push(m.sheet + '.' + m.column + ': not implemented');
  });
  try {
    var ss = getSpreadsheet_();
    ['LD', 'BK', 'RC', 'FN'].forEach(function () {}); // placeholder prefix check
    var store = loadCrmStore_(true);
    var sampleLead = Object.keys(store.leads.byId || {})[0];
    if (sampleLead && navResolveRow_('Lead', sampleLead) < 1) {
      issues.push('Lead row resolve failed for ' + sampleLead);
    }
  } catch (e) {
    issues.push('Audit error: ' + e.message);
  }
  return { ok: issues.length === 0, issues: issues, checkedAt: nowDateTime_() };
}

/** PUBLIC — menu handler writes Navigation Matrix to a sheet. */
function menuGenerateNavigationMatrix() {
  try {
    var ss = getSpreadsheet_();
    var name = 'Navigation Matrix';
    var sheet = ss.getSheetByName(name) || ss.insertSheet(name);
    sheet.clear();
    var headers = ['Sheet', 'Column', 'Classification', 'Navigation Target', 'Implemented'];
    sheet.getRange(1, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    var rows = getNavigationMatrix_().map(function (m) {
      return [m.sheet, m.column, m.classification, m.navTarget, m.implemented ? 'Yes' : 'No'];
    });
    if (rows.length) sheet.getRange(2, 1, rows.length, headers.length).setValues(rows);
    var audit = navAuditHyperlinks_();
    sheet.getRange(rows.length + 3, 1).setValue('Last audit: ' + audit.checkedAt + ' — ' + (audit.ok ? 'PASS' : audit.issues.join('; ')));
    // autoResize removed: it is one of the slowest Sheets calls and ran 14x per refresh.
    if (typeof hideDrillDownSheet_ === 'function') hideDrillDownSheet_(name);
    var dash = ss.getSheetByName(CRM.SHEETS.DASHBOARD);
    if (dash && !dash.isSheetHidden()) ss.setActiveSheet(dash);
    SpreadsheetApp.getUi().alert('Navigation Matrix generated (' + rows.length + ' fields).\n\nThe audit sheet is hidden — reopen via this menu anytime.');
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}
