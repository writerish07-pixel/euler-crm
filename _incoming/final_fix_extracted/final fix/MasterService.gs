/**
 * MasterService – single source for all dropdown values (Masters sheet + Config defaults).
 */

/** @returns {Object.<string, string[]>} */
function getMergedMasters_() {
  var cache = CacheService.getScriptCache();
  var cached = cache.get('masters_merged');
  if (cached) return JSON.parse(cached);

  var sheetMasters = readMastersFromSheet_();
  var merged = {};
  Object.keys(CRM.MASTERS.SECTIONS).forEach(function (section) {
    merged[section] = mergeMasterList_(section, sheetMasters[section] || []);
  });
  Object.keys(sheetMasters).forEach(function (section) {
    if (!merged[section]) merged[section] = mergeMasterList_(section, sheetMasters[section]);
  });

  cache.put('masters_merged', JSON.stringify(merged), 300);
  return merged;
}

function readMastersFromSheet_() {
  var sheet = getSheet_(CRM.SHEETS.MASTERS);
  var data = sheet.getDataRange().getValues();
  var masters = {};
  var currentSection = '';
  for (var i = 0; i < data.length; i++) {
    if (data[i][0] && !data[i][1]) {
      currentSection = String(data[i][0]).trim();
      masters[currentSection] = [];
    } else if (currentSection && data[i][1]) {
      masters[currentSection].push(String(data[i][1]).trim());
    }
  }
  return masters;
}

/** Merge Config defaults with sheet values; dedupe and normalize. */
function mergeMasterList_(section, sheetValues) {
  var defaults = CRM.MASTERS.SECTIONS[section] || [];
  var seen = {};
  var result = [];

  function add(raw) {
    var v = normalizeMasterValue_(section, raw);
    if (!v) return;
    var key = v.toLowerCase();
    if (seen[key]) return;
    seen[key] = true;
    result.push(v);
  }

  defaults.forEach(add);
  (sheetValues || []).forEach(add);
  return result.sort(function (a, b) { return a.localeCompare(b); });
}

function normalizeMasterValue_(section, val) {
  if (val === null || val === undefined) return '';
  var s = String(val).trim();
  if (!s) return '';

  if (section === 'Executives') return normalizeExecutiveName_(s);

  if (section === 'Lead Sources') {
    if (s.indexOf('/') >= 0) s = s.split('/')[0].trim();
    if (isLikelyExecutiveName_(s)) return '';
    return s;
  }

  if (section === 'Models') return matchMasterValue_(s, CRM.MASTERS.SECTIONS['Models']) || s;
  if (section === 'Status') return matchMasterValue_(s, CRM.MASTERS.SECTIONS['Status']) || s;
  if (section === 'Activity Types') return matchMasterValue_(s, CRM.MASTERS.SECTIONS['Activity Types']) || s;
  if (section === 'Payment Modes') return matchMasterValue_(s, CRM.MASTERS.SECTIONS['Payment Modes']) || s;
  if (section === 'Priority') return matchMasterValue_(s, CRM.MASTERS.SECTIONS['Priority']) || s;

  return s;
}

function isLikelyExecutiveName_(val) {
  var lower = String(val).trim().toLowerCase();
  var execs = CRM.MASTERS.SECTIONS['Executives'].concat(['Devansh', 'Ganesh', 'Harish Bhatnagar']);
  return execs.some(function (e) {
    var el = e.toLowerCase();
    return el === lower;
  });
}

function matchMasterValue_(value, allowed) {
  if (!value) return '';
  var v = String(value).trim();
  if (!v) return '';
  for (var i = 0; i < allowed.length; i++) {
    if (allowed[i] === v) return allowed[i];
  }
  var lower = v.toLowerCase();
  for (var j = 0; j < allowed.length; j++) {
    if (allowed[j].toLowerCase() === lower) return allowed[j];
  }
  var aliases = {
    'HI LOAD DV': 'Hi-Load',
    'HI LOAD': 'Hi-Load',
    'HI-LOAD': 'Hi-Load',
    'HILOAD': 'Hi-Load',
    'HIGH RANGE': 'Neo HiRange',
    'HI RANGE': 'Neo HiRange',
    'HIRANGE': 'Neo HiRange',
    'NEO HIRANGE': 'Neo HiRange',
    'HICITY': 'Hi-Load',
    'HI CITY': 'Hi-Load',
    'MAXX DV': 'Turbo DV',
    'TYRBO MAX DV': 'Turbo DV',
    'TURBO MAX': 'Turbo Max',
    'TURBO': 'Turbo Max',
    'STROM': 'Storm',
    'STORM': 'Storm',
    'NEO HICITY MAX': 'Turbo Max',
    'HICITY XR': 'Turbo Max'
  };
  var upper = v.toUpperCase();
  if (aliases[upper]) {
    var mapped = aliases[upper];
    for (var k = 0; k < allowed.length; k++) {
      if (allowed[k] === mapped) return mapped;
    }
  }
  for (var key in aliases) {
    if (upper.indexOf(key) >= 0) {
      var aliasVal = aliases[key];
      for (var m = 0; m < allowed.length; m++) {
        if (allowed[m] === aliasVal) return aliasVal;
      }
    }
  }
  for (var n = 0; n < allowed.length; n++) {
    if (allowed[n].toLowerCase().indexOf(lower) >= 0 || lower.indexOf(allowed[n].toLowerCase()) >= 0) {
      return allowed[n];
    }
  }
  return '';
}

/** Build option HTML for dialog dropdowns. */
function buildSelectOptionsHtml_(values, allowEmpty) {
  var html = allowEmpty ? '<option value=""></option>' : '';
  (values || []).forEach(function (v) {
    html += '<option value="' + escapeHtml_(v) + '">' + escapeHtml_(v) + '</option>';
  });
  return html;
}

function escapeHtml_(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Fill Masters Models/Variants from live PRICE MASTER when empty or incomplete.
 * Config defaults for Models/Variants are intentionally empty — prices are the source of truth.
 * @returns {{ masters: Object, changed: boolean }}
 */
function ensureMastersModelsFromPriceMaster_(masters) {
  masters = masters || getMergedMasters_();
  var models = (masters['Models'] || []).slice();
  var variants = (masters['Variants'] || []).slice();
  var changed = false;

  var pricedModels = [];
  var pricedVariants = [];
  try {
    if (typeof getActivePriceMasterRecords_ === 'function') {
      var seenM = {};
      var seenV = {};
      (getActivePriceMasterRecords_().rows || []).forEach(function (r) {
        var m = String(r.model || '').trim();
        var v = String(r.variant || '').trim();
        if (m && !seenM[m.toLowerCase()]) { seenM[m.toLowerCase()] = 1; pricedModels.push(m); }
        if (v && !seenV[v.toLowerCase()]) { seenV[v.toLowerCase()] = 1; pricedVariants.push(v); }
      });
    }
  } catch (e) { /* PRICE MASTER empty / missing — leave Masters as-is */ }

  if (pricedModels.length) {
    var modelSet = {};
    models.forEach(function (m) { modelSet[String(m).toLowerCase()] = m; });
    pricedModels.forEach(function (m) {
      var k = m.toLowerCase();
      if (!modelSet[k]) { modelSet[k] = m; changed = true; }
    });
    models = Object.keys(modelSet).map(function (k) { return modelSet[k]; }).sort();
  }
  if (pricedVariants.length) {
    var variantSet = {};
    variants.forEach(function (v) { variantSet[String(v).toLowerCase()] = v; });
    pricedVariants.forEach(function (v) {
      var k = v.toLowerCase();
      if (!variantSet[k]) { variantSet[k] = v; changed = true; }
    });
    variants = Object.keys(variantSet).map(function (k) { return variantSet[k]; }).sort();
  }

  // If still empty but bundled import rows exist, use those (offline / empty sheet bootstrap).
  if (!models.length && typeof PRICE_MASTER_2026_ROWS_ !== 'undefined' && PRICE_MASTER_2026_ROWS_.length) {
    var bootM = {};
    var bootV = {};
    PRICE_MASTER_2026_ROWS_.forEach(function (row) {
      var m = String(row[0] || '').trim();
      var v = String(row[1] || '').trim();
      if (m) bootM[m.toLowerCase()] = m;
      if (v) bootV[v.toLowerCase()] = v;
    });
    models = Object.keys(bootM).map(function (k) { return bootM[k]; }).sort();
    variants = Object.keys(bootV).map(function (k) { return bootV[k]; }).sort();
    changed = models.length > 0;
  }

  masters['Models'] = models;
  masters['Variants'] = variants;
  return { masters: masters, changed: changed };
}

/** Apply data validation dropdowns to all editable columns across the spreadsheet. */
function refreshAllDropdowns_() {
  var ensured = ensureMastersModelsFromPriceMaster_(getMergedMasters_());
  var masters = ensured.masters;
  if (ensured.changed) {
    writeMastersSheet_(masters);
    clearCache_();
    masters = getMergedMasters_();
    ensureMastersModelsFromPriceMaster_(masters); // keep in-memory Models/Variants after cache rebuild
  }

  var lrSheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var numRows = CRM.MAX_ROWS;
  var skipped = [];

  function dvFromList(vals, label) {
    var list = (vals || []).filter(function (v) { return String(v).trim(); });
    if (list.length === 0) {
      skipped.push(label || 'list');
      return null;
    }
    return SpreadsheetApp.newDataValidation()
      .requireValueInList(list, true)
      .setAllowInvalid(false)
      .build();
  }

  function applyDv_(range, rule) {
    if (rule) range.setDataValidation(rule);
  }

  var leadValidations = {
    'Lead Source': 'Lead Sources',
    'Interested Model': 'Models',
    'Variant': 'Variants',
    'Executive': 'Executives',
    'Current Status': 'Status',
    'Priority': 'Priority',
    'Booking Status': 'Status'
  };

  var leadCols = CRM.LEAD.COLS;
  Object.keys(leadValidations).forEach(function (colName) {
    var col = leadCols.indexOf(colName) + 1;
    if (col > 0) {
      applyDv_(
        lrSheet.getRange(CRM.LEAD.DATA_START, col, numRows, 1),
        dvFromList(masters[leadValidations[colName]], colName)
      );
    }
  });

  var actSheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  var actCols = CRM.ACTIVITY.COLS;
  var activityTypeMaster = getActivityTypeMaster_();
  applyDv_(
    actSheet.getRange(CRM.ACTIVITY.DATA_START, actCols.indexOf('Activity Type') + 1, numRows, 1),
    dvFromList(activityTypeMaster, 'Activity Type')
  );
  applyDv_(
    actSheet.getRange(CRM.ACTIVITY.DATA_START, actCols.indexOf('Executive') + 1, numRows, 1),
    dvFromList(masters['Executives'], 'Activity Executive')
  );

  var delSheet = getSheet_(CRM.SHEETS.DELIVERY_TRACKER);
  var delCols = getHeaders_(delSheet, CRM.DELIVERY.HEADER_ROW);
  if (!delCols.length) delCols = CRM.DELIVERY.COLS;
  var yesNoPd = dvFromList(['Yes', 'No', 'Pending', 'Done'], 'Delivery Yes/No');
  var statusCols = (CRM.DELIVERY.STATUS_COLS || ['Insurance', 'Registration', 'Invoice', 'Accessories', 'RC', 'PDI', 'Delivered']);
  statusCols.forEach(function (colName) {
    var col = delCols.indexOf(colName) + 1;
    if (col > 0) applyDv_(delSheet.getRange(CRM.DELIVERY.DATA_START, col, numRows, 1), yesNoPd);
  });
  // Free-text delivery columns — never Yes/No validation (fixes Number Plate H2 error).
  ['Number Plate', 'Insurer Name', 'Invoice Number', 'Chassis Number', 'Feedback', 'Customer Name', 'Delivery ID'].forEach(function (colName) {
    var col = delCols.indexOf(colName) + 1;
    if (col > 0) delSheet.getRange(CRM.DELIVERY.DATA_START, col, numRows, 1).clearDataValidations();
  });

  var paySheet = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  var payHeaders = getHeaders_(paySheet, CRM.PAYMENT.HEADER_ROW);
  var modeCol = payHeaders.indexOf('Payment Mode') + 1;
  if (modeCol > 0) {
    applyDv_(
      paySheet.getRange(CRM.PAYMENT.DATA_START, modeCol, numRows, 1),
      dvFromList(masters['Payment Modes'], 'Payment Mode')
    );
  }
  var finCol = payHeaders.indexOf('Financer Name') + 1;
  if (finCol > 0 && masters['Financers']) {
    applyDv_(
      paySheet.getRange(CRM.PAYMENT.DATA_START, finCol, numRows, 1),
      dvFromList(masters['Financers'], 'Financer Name')
    );
  }

  if (skipped.length) {
    logAudit_('DROPDOWNS_SKIPPED', 'Empty lists skipped: ' + skipped.join(', '));
  }
  logAudit_('DROPDOWNS_REFRESH', 'All data validations applied from Masters');
}

/** Rewrite Masters sheet from merged/normalized lists. */
function writeMastersSheet_(mastersObj) {
  var sheet = getSheet_(CRM.SHEETS.MASTERS);
  sheet.clear();
  var row = 1;
  var order = [
    'Lead Sources', 'Models', 'Variants', 'Status', 'Account Status',
    'Executives', 'Payment Modes', 'Financers', 'Priority', 'Activity Types'
  ];
  order.forEach(function (section) {
    var vals = mastersObj[section] || mergeMasterList_(section, []);
    sheet.getRange(row, 1).setValue(section).setFontWeight('bold').setBackground('#ECEFF1');
    row++;
    vals.forEach(function (v) {
      sheet.getRange(row, 2).setValue(v);
      row++;
    });
    row++;
  });
  clearCache_();
}

function menuRefreshDropdownsFromMasters_() {
  safeRun_('refreshDropdowns', function () {
    repairMastersSheet_();
    showToast_('Masters normalized and all dropdowns refreshed');
  });
}

function repairMastersSheet_() {
  clearCache_();
  var merged = getMergedMasters_();
  ensureMastersModelsFromPriceMaster_(merged);
  writeMastersSheet_(merged);
  clearCache_();
  refreshAllDropdowns_();
}
