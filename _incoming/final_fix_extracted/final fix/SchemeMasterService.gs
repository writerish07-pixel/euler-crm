/**
 * SchemeMasterService — monthly OEM consumer scheme + manpower incentive masters.
 *
 * Circular July 2026 (EM/07-2026/004) is seeded as Scheme Month 2026-07.
 * Each month: copy last month's rows, change Scheme Month / dates / ₹ shares, set Status=Active.
 *
 * Company Outstanding uses Company Share (₹) from Scheme Master by Model+Variant+Component.
 * Dealer Share (₹) is the dealer's portion of total benefit for that component.
 */

function ensureSchemeAndIncentiveSheets_() {
  ensureSchemeMasterSheet_();
  ensureIncentiveMasterSheet_();
  ensureIncentiveRegisterSheet_();
}

function ensureSchemeMasterSheet_() {
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.SCHEME_MASTER;
  var cols = (CRM.SCHEME_MASTER && CRM.SCHEME_MASTER.COLS) || [];
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var headers = getHeaders_(sheet, 1);
  if (sheet.getLastRow() < 1 || !headers.length) {
    sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold').setBackground('#E3F2FD');
    sheet.setFrozenRows(1);
    headers = cols.slice();
  } else {
    cols.forEach(function (c) {
      if (findHeaderIndex_(headers, c) < 0) {
        sheet.getRange(1, headers.length + 1).setValue(c).setFontWeight('bold');
        headers = getHeaders_(sheet, 1);
      }
    });
  }
  if (sheet.getLastRow() < 2) {
    seedJuly2026SchemeMaster_(sheet, cols);
  }
  return sheet;
}

function ensureIncentiveMasterSheet_() {
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.INCENTIVE_MASTER;
  var cols = (CRM.INCENTIVE_MASTER && CRM.INCENTIVE_MASTER.COLS) || [];
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var headers = getHeaders_(sheet, 1);
  if (sheet.getLastRow() < 1 || !headers.length) {
    sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold').setBackground('#FFF3E0');
    sheet.setFrozenRows(1);
  } else {
    cols.forEach(function (c) {
      if (findHeaderIndex_(headers, c) < 0) {
        sheet.getRange(1, headers.length + 1).setValue(c).setFontWeight('bold');
        headers = getHeaders_(sheet, 1);
      }
    });
  }
  if (sheet.getLastRow() < 2) {
    seedJuly2026IncentiveMaster_(sheet, cols);
  }
  return sheet;
}

function ensureIncentiveRegisterSheet_() {
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.INCENTIVE_REGISTER;
  var cols = (CRM.INCENTIVE_REGISTER && CRM.INCENTIVE_REGISTER.COLS) || [];
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var headers = getHeaders_(sheet, 1);
  if (sheet.getLastRow() < 1 || !headers.length) {
    sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold').setBackground('#F3E5F5');
    sheet.setFrozenRows(1);
  } else {
    cols.forEach(function (c) {
      if (findHeaderIndex_(headers, c) < 0) {
        sheet.getRange(1, headers.length + 1).setValue(c).setFontWeight('bold');
        headers = getHeaders_(sheet, 1);
      }
    });
  }
  return sheet;
}

/** Seed from July 2026 Freedom From Fuel circular EM/07-2026/004. */
function seedJuly2026SchemeMaster_(sheet, cols) {
  cols = cols || CRM.SCHEME_MASTER.COLS;
  var month = '2026-07';
  var from = '2026-07-01';
  var to = '2026-07-31';
  var ref = 'EM/07-2026/004';
  // [model, variant, componentKey, componentLabel, dealer, company]
  var rowsSpec = [
    // HiLoad (Non-GBT)
    ['HiLoad', 'Non-GBT', 'consumerDiscount', 'Consumer Scheme', 5000, 5000],
    ['HiLoad', 'Non-GBT', 'exchangeBonus', 'Exchange Benefit', 5000, 5000],
    ['HiLoad', 'Non-GBT', 'dsaDiscount', 'DSA', 3000, 7000],
    ['HiLoad', 'Non-GBT', 'referralBonus', 'Referral', 0, 5000],
    ['HiLoad', 'Non-GBT', 'loyaltyBonus', 'Loyalty', 0, 5000],
    // HiCity (XR)
    ['HiCity', 'XR', 'consumerDiscount', 'Consumer Scheme', 0, 0],
    ['HiCity', 'XR', 'rtoInsuranceBenefit', 'Free RTO + Free Insurance', 0, 20000],
    ['HiCity', 'XR', 'exchangeBonus', 'Exchange Benefit', 5000, 7500],
    ['HiCity', 'XR', 'dsaDiscount', 'DSA', 0, 0],
    ['HiCity', 'XR', 'referralBonus', 'Referral', 0, 5000],
    ['HiCity', 'XR', 'loyaltyBonus', 'Loyalty', 0, 5000],
    // Hirange (XR)
    ['Hirange', 'XR', 'consumerDiscount', 'Consumer Scheme', 0, 25000],
    ['Hirange', 'XR', 'rtoInsuranceBenefit', 'Free RTO + Free Insurance', 0, 20000],
    ['Hirange', 'XR', 'exchangeBonus', 'Exchange Benefit', 5000, 7500],
    ['Hirange', 'XR', 'dsaDiscount', 'DSA', 0, 0],
    ['Hirange', 'XR', 'referralBonus', 'Referral', 0, 5000],
    ['Hirange', 'XR', 'loyaltyBonus', 'Loyalty', 0, 5000],
    // Hirange (TR)
    ['Hirange', 'TR', 'consumerDiscount', 'Consumer Scheme', 0, 25000],
    ['Hirange', 'TR', 'rtoInsuranceBenefit', 'Free RTO + Free Insurance', 0, 20000],
    ['Hirange', 'TR', 'exchangeBonus', 'Exchange Benefit', 5000, 7500],
    ['Hirange', 'TR', 'dsaDiscount', 'DSA', 0, 0],
    ['Hirange', 'TR', 'referralBonus', 'Referral', 0, 5000],
    ['Hirange', 'TR', 'loyaltyBonus', 'Loyalty', 0, 5000],
    // Storm
    ['Storm', '', 'consumerDiscount', 'Consumer Scheme', 10000, 20000],
    ['Storm', '', 'exchangeBonus', 'Exchange Benefit', 5000, 12500],
    ['Storm', '', 'dsaDiscount', 'DSA', 3000, 7000],
    ['Storm', '', 'referralBonus', 'Referral', 0, 5000],
    ['Storm', '', 'loyaltyBonus', 'Loyalty', 0, 5000],
    // Turbo (Price Master "Turbo Max" / variant Maxx HD also maps here)
    ['Turbo', '', 'consumerDiscount', 'Consumer Scheme', 0, 0],
    ['Turbo', '', 'exchangeBonus', 'Exchange Benefit', 5000, 10000],
    ['Turbo', '', 'dsaDiscount', 'DSA', 5000, 5000],
    ['Turbo', '', 'referralBonus', 'Referral', 0, 5000],
    ['Turbo', '', 'loyaltyBonus', 'Loyalty', 0, 5000]
  ];

  var out = rowsSpec.map(function (r) {
    var dealer = Number(r[4]) || 0;
    var company = Number(r[5]) || 0;
    return [
      month, from, to, ref, r[0], r[1], r[3], r[2],
      dealer, company, dealer + company, 'Active',
      'Freedom From Fuel — July 2026'
    ];
  });
  sheet.getRange(2, 1, out.length, cols.length).setValues(out);
  sheet.getRange(2, 9, out.length, 3).setNumberFormat('#,##0');
}

function seedJuly2026IncentiveMaster_(sheet, cols) {
  cols = cols || CRM.INCENTIVE_MASTER.COLS;
  var month = '2026-07';
  var from = '2026-07-01';
  var to = '2026-07-31';
  var ref = 'EM/07-2026/004';
  var notes = 'Min 2 retails to qualify; then incentive on all retails. Max slab ₹20,000. 100% vahan/TR retail.';
  var rows = [
    [month, from, to, ref, 'Pax', 3000, 2, 20000, 'Active', notes],
    [month, from, to, ref, '3WC', 3000, 2, 20000, 'Active', notes],
    [month, from, to, ref, 'Storm', 7500, 2, 20000, 'Active', notes],
    [month, from, to, ref, 'Turbo', 5000, 2, 20000, 'Active', notes]
  ];
  sheet.getRange(2, 1, rows.length, cols.length).setValues(rows);
  sheet.getRange(2, 6, rows.length, 3).setNumberFormat('#,##0');
}

function schemeMonthFromDate_(dateIso) {
  var d = formatDate_(dateIso) || nowDate_();
  return d.substring(0, 7);
}

/**
 * Normalize Scheme Month cells (text "2026-07", Date objects, "Jul-2026", etc.).
 * Date cells were stringified as "Wed Jul 01 ..." and never matched booking month
 * → Scheme Update greyed out all fields even when Turbo schemes existed.
 */
function normalizeSchemeMonth_(value) {
  if (value instanceof Date && !isNaN(value.getTime())) {
    return Utilities.formatDate(value, Session.getScriptTimeZone(), 'yyyy-MM');
  }
  if (value === '' || value === null || value === undefined) return '';
  if (typeof value === 'number' && isFinite(value)) {
    // Sheets serial date
    try {
      var asDate = new Date(Math.round((value - 25569) * 86400 * 1000));
      if (!isNaN(asDate.getTime())) {
        return Utilities.formatDate(asDate, Session.getScriptTimeZone(), 'yyyy-MM');
      }
    } catch (e) {}
  }
  var s = String(value).trim();
  if (!s) return '';
  if (/^\d{4}-\d{2}/.test(s)) return s.substring(0, 7);
  var iso = formatDate_(s);
  if (iso && /^\d{4}-\d{2}/.test(iso)) return iso.substring(0, 7);
  var named = s.match(/^(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*[\s\-_/]+(\d{4})$/i);
  if (named) {
    var map = {
      jan: '01', feb: '02', mar: '03', apr: '04', may: '05', jun: '06',
      jul: '07', aug: '08', sep: '09', oct: '10', nov: '11', dec: '12'
    };
    var mm = map[named[1].toLowerCase().substring(0, 3)];
    if (mm) return named[2] + '-' + mm;
  }
  return s;
}

/**
 * Map Price Master / lead Model (+ optional Variant) → Scheme circular family key.
 *
 * Price Master              Scheme circular / Scheme Master
 * ------------------------  --------------------------------
 * Hi-Load / Hi Load         HiLoad
 * HiCity / Hi City          HiCity
 * Neo HiRange / High Range  Hirange
 * Turbo Max / Turbo         Turbo
 * Storm / Strom             Storm
 */
function normalizeSchemeModelKey_(model, variant) {
  var raw = String(model || '').toLowerCase().trim();
  var s = raw.replace(/[^a-z0-9]/g, '');
  var vRaw = String(variant || '').toLowerCase().trim();
  var v = vRaw.replace(/[^a-z0-9]/g, '');

  // Storm (accept circular typo "Strom")
  if (s.indexOf('storm') >= 0 || s.indexOf('strom') >= 0) return 'storm';

  // Turbo Max / Turbo / Tyrbo
  if (s.indexOf('turbo') >= 0 || s.indexOf('tyrbo') >= 0) return 'turbo';

  // High Range / Neo HiRange / Hirange — before generic "hi*" checks
  if (
    s.indexOf('hirange') >= 0 ||
    s.indexOf('highrange') >= 0 ||
    s.indexOf('neohirange') >= 0 ||
    raw.indexOf('high range') >= 0 ||
    raw.indexOf('hi range') >= 0 ||
    raw.indexOf('hi-range') >= 0
  ) {
    return 'hirange';
  }

  // Explicit HiCity / Hi City
  if (
    s.indexOf('hicity') >= 0 ||
    raw.indexOf('hi city') >= 0 ||
    raw.indexOf('hi-city') >= 0
  ) {
    return 'hicity';
  }

  // Hi-Load / HiLoad / Hi Load
  // Price Master sometimes puts HiCity under Model=Hi-Load with Variant=XR only
  if (s.indexOf('hiload') >= 0) {
    if (v === 'xr' || vRaw.indexOf('hicity') >= 0 || s.indexOf('hicity') >= 0) {
      return 'hicity';
    }
    return 'hiload';
  }

  // Spaced / hyphenated leftovers
  if (raw.indexOf('hi load') >= 0 || raw.indexOf('hi-load') >= 0) return 'hiload';

  return s;
}

function normalizeSchemeVariantKey_(variant) {
  var s = String(variant || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (!s) return '';
  if (s.indexOf('nongbt') >= 0 || s.indexOf('trnc') >= 0) return 'nongbt';
  if (s.indexOf('withgbt') >= 0 || (s.indexOf('gbt') >= 0 && s.indexOf('nongbt') < 0)) return 'gbt';
  // XR / TR for HiCity & Hirange
  if (s === 'xr' || s.indexOf('xr') === 0) return 'xr';
  if (s === 'tr' || s.indexOf('tr') === 0) return 'tr';
  if (s === 'sr' || s.indexOf('sr') === 0) return 'sr';
  return s;
}

function modelsMatchScheme_(leadModel, masterModel, leadVariant) {
  return normalizeSchemeModelKey_(leadModel, leadVariant) === normalizeSchemeModelKey_(masterModel);
}

function variantsMatchScheme_(leadVariant, masterVariant, masterModel) {
  var mv = String(masterVariant || '').trim();
  if (!mv) return true; // Storm / Turbo — any variant (e.g. Maxx HD)
  var a = normalizeSchemeVariantKey_(leadVariant);
  var b = normalizeSchemeVariantKey_(mv);
  if (a === b) return true;

  var family = normalizeSchemeModelKey_(masterModel);

  // Circular HiLoad = Non-GBT. Match TR-NC / XR-without-GBT; exclude "With GBT".
  if (family === 'hiload') {
    if (!a) return true;
    if (b === 'nongbt') {
      if (a === 'gbt') return false;
      return true;
    }
  }

  // HiCity / Hirange: XR or TR must align with circular row
  if (family === 'hicity' || family === 'hirange') {
    if (b === 'xr' && (a === 'xr' || a.indexOf('xr') >= 0)) return true;
    if (b === 'tr' && (a === 'tr' || a.indexOf('tr') === 0)) return true;
    // Neo HiRange SR: no circular row today — do not force-match XR/TR
  }

  return false;
}

/** Map Component / Component Key text from sheet → offer field key. */
function normalizeSchemeComponentKey_(key, label) {
  var k = String(key || '').trim();
  var low = k.toLowerCase().replace(/[^a-z0-9]/g, '');
  var known = {
    consumerdiscount: 'consumerDiscount',
    consumerscheme: 'consumerDiscount',
    exchangebonus: 'exchangeBonus',
    exchangebenefit: 'exchangeBonus',
    loyaltybonus: 'loyaltyBonus',
    loyalty: 'loyaltyBonus',
    referralbonus: 'referralBonus',
    referral: 'referralBonus',
    dsadiscount: 'dsaDiscount',
    dsa: 'dsaDiscount',
    dsabonus: 'dsaDiscount',
    rtoinsurancebenefit: 'rtoInsuranceBenefit',
    freertofreeinsurance: 'rtoInsuranceBenefit'
  };
  if (known[low]) return known[low];
  if (/^(consumerDiscount|exchangeBonus|loyaltyBonus|referralBonus|dsaDiscount|rtoInsuranceBenefit|additionalDiscount)$/.test(k)) {
    return k;
  }
  var fromLabel = String(label || '').toLowerCase().replace(/[^a-z0-9]/g, '');
  if (known[fromLabel]) return known[fromLabel];
  return k;
}

/** Flexible header lookup for Scheme Master (handles ₹ / aliases). */
function schemeMasterHeaderIndex_(headers, names) {
  var list = Array.isArray(names) ? names : [names];
  var i;
  for (i = 0; i < list.length; i++) {
    var idx = findHeaderIndex_(headers, list[i]);
    if (idx >= 0) return idx;
  }
  // Fuzzy: header contains all significant words
  for (i = 0; i < list.length; i++) {
    var words = String(list[i] || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim().split(/\s+/);
    if (!words.length || !words[0]) continue;
    for (var h = 0; h < headers.length; h++) {
      var hk = String(headers[h] || '').toLowerCase().replace(/[^a-z0-9]+/g, ' ');
      var ok = true;
      for (var w = 0; w < words.length; w++) {
        if (hk.indexOf(words[w]) < 0) { ok = false; break; }
      }
      if (ok) return h;
    }
  }
  return -1;
}

function schemeMasterNum_(v) {
  if (typeof v === 'number' && isFinite(v)) return v;
  var s = String(v == null ? '' : v).replace(/[₹,\s]/g, '').trim();
  if (!s) return 0;
  var n = Number(s);
  return isFinite(n) ? n : 0;
}

var __SCHEME_SEED_CHECKED__ = false;

function readSchemeMasterRows_() {
  var sheet = ensureSchemeMasterSheet_();
  // Seed missing Turbo/etc once per execution.
  if (!__SCHEME_SEED_CHECKED__) {
    __SCHEME_SEED_CHECKED__ = true;
    try { ensureSchemeMasterSeededForMonth_(schemeMonthFromDate_(nowDate_())); } catch (eSeed) {}
  }
  var headers = getHeaders_(sheet, 1);
  var last = sheet.getLastRow();
  if (last < 2) return [];
  var data = sheet.getRange(2, 1, last - 1, headers.length).getValues();
  return data.map(function (row) {
    function val(names) {
      var i = schemeMasterHeaderIndex_(headers, names);
      return i >= 0 ? row[i] : '';
    }
    var component = String(val(['Component', 'Scheme Component', 'Benefit']) || '').trim();
    var rawKey = val(['Component Key', 'Key', 'Offer Key']);
    var monthRaw = val(['Scheme Month', 'Month', 'SchemeMonth']);
    var schemeMonth = normalizeSchemeMonth_(monthRaw);
    var effectiveFrom = formatDate_(val(['Effective From', 'From', 'Start Date'])) || '';
    var effectiveTo = formatDate_(val(['Effective To', 'To', 'End Date'])) || '';
    if (!schemeMonth && effectiveFrom) schemeMonth = String(effectiveFrom).substring(0, 7);
    var status = String(val(['Status', 'Active']) || 'Active').trim();
    if (!status) status = 'Active';
    var dealer = schemeMasterNum_(val(['Dealer Share', 'Dealer', 'Dealer Amount']));
    var company = schemeMasterNum_(val(['Company Share', 'Company', 'OEM Share', 'Company Amount']));
    var total = schemeMasterNum_(val(['Total Benefit', 'Total', 'Total Amount']));
    if (!total) total = dealer + company;
    return {
      schemeMonth: schemeMonth,
      effectiveFrom: effectiveFrom,
      effectiveTo: effectiveTo,
      circularRef: String(val(['Circular Ref', 'Circular', 'Ref']) || '').trim(),
      model: String(val(['Model', 'Vehicle Model', 'Product']) || '').trim(),
      variant: String(val(['Variant', 'Var']) || '').trim(),
      component: component,
      componentKey: normalizeSchemeComponentKey_(rawKey, component),
      dealerShare: dealer,
      companyShare: company,
      totalBenefit: total,
      status: status
    };
  }).filter(function (r) {
    return r.model && r.componentKey && String(r.status).toLowerCase() === 'active';
  });
}

/**
 * If Scheme Master has no Active rows for this month's Turbo/HiLoad families,
 * append the July-2026 circular seed (or remapped to requested month).
 */
function ensureSchemeMasterSeededForMonth_(month) {
  month = normalizeSchemeMonth_(month) || schemeMonthFromDate_(nowDate_());
  var sheet = ensureSchemeMasterSheet_();
  var headers = getHeaders_(sheet, 1);
  var last = sheet.getLastRow();
  if (last < 2) {
    seedJuly2026SchemeMaster_(sheet, CRM.SCHEME_MASTER.COLS);
    if (month !== '2026-07') remapSchemeMasterMonth_(sheet, '2026-07', month);
    return;
  }
  var rows = [];
  try {
    // Lightweight scan without recursion into ensureSchemeMasterSeeded_
    var data = sheet.getRange(2, 1, last - 1, headers.length).getValues();
    var mi = schemeMasterHeaderIndex_(headers, ['Scheme Month', 'Month']);
    var moi = schemeMasterHeaderIndex_(headers, ['Model', 'Vehicle Model']);
    var sti = schemeMasterHeaderIndex_(headers, ['Status']);
    for (var i = 0; i < data.length; i++) {
      var st = sti >= 0 ? String(data[i][sti] || 'Active').toLowerCase() : 'active';
      if (st && st !== 'active') continue;
      var m = moi >= 0 ? String(data[i][moi] || '') : '';
      var sm = mi >= 0 ? normalizeSchemeMonth_(data[i][mi]) : '';
      rows.push({ model: m, schemeMonth: sm });
    }
  } catch (e) { return; }

  var hasFamily = { turbo: false, hiload: false, storm: false, hirange: false, hicity: false };
  rows.forEach(function (r) {
    var fam = normalizeSchemeModelKey_(r.model);
    if (hasFamily[fam] !== undefined) {
      if (!r.schemeMonth || r.schemeMonth === month || r.schemeMonth === '2026-07') {
        hasFamily[fam] = true;
      }
    }
  });
  if (hasFamily.turbo) return; // Turbo present ⇒ sheet already configured

  // Append Turbo (and other missing) circular rows for the requested month
  var cols = CRM.SCHEME_MASTER.COLS;
  var startRow = sheet.getLastRow() + 1;
  seedJuly2026SchemeMasterAppend_(sheet, cols, month, startRow, hasFamily);
}

function remapSchemeMasterMonth_(sheet, fromMonth, toMonth) {
  var headers = getHeaders_(sheet, 1);
  var mi = findHeaderIndex_(headers, 'Scheme Month');
  var fi = findHeaderIndex_(headers, 'Effective From');
  var ti = findHeaderIndex_(headers, 'Effective To');
  var last = sheet.getLastRow();
  if (last < 2 || mi < 0) return;
  var vals = sheet.getRange(2, 1, last - 1, headers.length).getValues();
  var y = String(toMonth).substring(0, 4);
  var m = String(toMonth).substring(5, 7);
  var from = y + '-' + m + '-01';
  var to = y + '-' + m + '-28';
  try {
    var lastDay = new Date(Number(y), Number(m), 0).getDate();
    to = y + '-' + m + '-' + (lastDay < 10 ? '0' : '') + lastDay;
  } catch (e) {}
  for (var i = 0; i < vals.length; i++) {
    if (normalizeSchemeMonth_(vals[i][mi]) !== fromMonth) continue;
    vals[i][mi] = toMonth;
    if (fi >= 0) vals[i][fi] = from;
    if (ti >= 0) vals[i][ti] = to;
  }
  sheet.getRange(2, 1, last - 1, headers.length).setValues(vals);
}

function seedJuly2026SchemeMasterAppend_(sheet, cols, month, startRow, hasFamily) {
  cols = cols || CRM.SCHEME_MASTER.COLS;
  month = month || '2026-07';
  hasFamily = hasFamily || {};
  var y = String(month).substring(0, 4);
  var m = String(month).substring(5, 7);
  var from = y + '-' + m + '-01';
  var lastDay = 28;
  try { lastDay = new Date(Number(y), Number(m), 0).getDate(); } catch (e) {}
  var to = y + '-' + m + '-' + (lastDay < 10 ? '0' : '') + lastDay;
  var ref = 'EM/' + m + '-' + y + '/004';
  var allSpec = [
    ['hiload', 'HiLoad', 'Non-GBT', 'consumerDiscount', 'Consumer Scheme', 5000, 5000],
    ['hiload', 'HiLoad', 'Non-GBT', 'exchangeBonus', 'Exchange Benefit', 5000, 5000],
    ['hiload', 'HiLoad', 'Non-GBT', 'dsaDiscount', 'DSA', 3000, 7000],
    ['hiload', 'HiLoad', 'Non-GBT', 'referralBonus', 'Referral', 0, 5000],
    ['hiload', 'HiLoad', 'Non-GBT', 'loyaltyBonus', 'Loyalty', 0, 5000],
    ['hicity', 'HiCity', 'XR', 'exchangeBonus', 'Exchange Benefit', 5000, 7500],
    ['hicity', 'HiCity', 'XR', 'referralBonus', 'Referral', 0, 5000],
    ['hicity', 'HiCity', 'XR', 'loyaltyBonus', 'Loyalty', 0, 5000],
    ['hirange', 'Hirange', 'XR', 'consumerDiscount', 'Consumer Scheme', 0, 25000],
    ['hirange', 'Hirange', 'XR', 'exchangeBonus', 'Exchange Benefit', 5000, 7500],
    ['hirange', 'Hirange', 'XR', 'referralBonus', 'Referral', 0, 5000],
    ['hirange', 'Hirange', 'XR', 'loyaltyBonus', 'Loyalty', 0, 5000],
    ['storm', 'Storm', '', 'consumerDiscount', 'Consumer Scheme', 10000, 20000],
    ['storm', 'Storm', '', 'exchangeBonus', 'Exchange Benefit', 5000, 12500],
    ['storm', 'Storm', '', 'dsaDiscount', 'DSA', 3000, 7000],
    ['storm', 'Storm', '', 'referralBonus', 'Referral', 0, 5000],
    ['storm', 'Storm', '', 'loyaltyBonus', 'Loyalty', 0, 5000],
    ['turbo', 'Turbo', '', 'consumerDiscount', 'Consumer Scheme', 0, 0],
    ['turbo', 'Turbo', '', 'exchangeBonus', 'Exchange Benefit', 5000, 10000],
    ['turbo', 'Turbo', '', 'dsaDiscount', 'DSA', 5000, 5000],
    ['turbo', 'Turbo', '', 'referralBonus', 'Referral', 0, 5000],
    ['turbo', 'Turbo', '', 'loyaltyBonus', 'Loyalty', 0, 5000]
  ];
  var rowsSpec = allSpec.filter(function (r) { return !hasFamily[r[0]]; });
  if (!rowsSpec.length) return;
  var out = rowsSpec.map(function (r) {
    var dealer = Number(r[5]) || 0;
    var company = Number(r[6]) || 0;
    return [
      month, from, to, ref, r[1], r[2], r[4], r[3],
      dealer, company, dealer + company, 'Active',
      'Auto-seeded scheme circular'
    ];
  });
  sheet.getRange(startRow, 1, startRow + out.length - 1, cols.length).setValues(out);
}

/**
 * Active scheme rows for a lead model/variant on a booking date.
 * Matches Model aliases (Hi-Load↔HiLoad, Neo HiRange↔Hirange, Turbo Max↔Turbo).
 * Falls back to any Active row for the model family when month text doesn't match.
 * @return {Object} map componentKey → { dealerShare, companyShare, totalBenefit, label }
 */
function getSchemeSharesForLead_(model, variant, bookingDate) {
  var month = schemeMonthFromDate_(bookingDate);
  var iso = formatDate_(bookingDate) || nowDate_();
  var rows = readSchemeMasterRows_();
  var exact = {};
  var inWindow = {};
  var anyFamily = {};

  rows.forEach(function (r) {
    if (String(r.status).toLowerCase() !== 'active') return;
    if (!modelsMatchScheme_(model, r.model, variant)) return;
    if (!variantsMatchScheme_(variant, r.variant, r.model)) return;

    var payload = {
      dealerShare: r.dealerShare,
      companyShare: r.companyShare,
      totalBenefit: r.totalBenefit || (r.dealerShare + r.companyShare),
      label: r.component,
      model: r.model,
      variant: r.variant,
      schemeMonth: r.schemeMonth || month
    };

    var windowOk = true;
    if (r.effectiveFrom && iso < r.effectiveFrom) windowOk = false;
    if (r.effectiveTo && iso > r.effectiveTo) windowOk = false;

    if (r.schemeMonth === month && windowOk) {
      exact[r.componentKey] = payload;
    }
    if (windowOk) {
      if (!inWindow[r.componentKey] || String(r.schemeMonth) >= String(inWindow[r.componentKey].schemeMonth || '')) {
        inWindow[r.componentKey] = payload;
      }
    }
    // Last resort: ignore month/window — keep newest schemeMonth for family
    if (!anyFamily[r.componentKey] || String(r.schemeMonth) >= String(anyFamily[r.componentKey].schemeMonth || '')) {
      anyFamily[r.componentKey] = payload;
    }
  });

  if (Object.keys(exact).length) return exact;
  if (Object.keys(inWindow).length) return inWindow;
  return anyFamily;
}

/**
 * Split applied lead scheme amounts into dealer vs company using Scheme Master.
 * - Offer components with amount > 0: use master company/dealer shares (capped by actual).
 * - Free RTO+Insurance: included as company share when master has it (product entitlement).
 */
function computeSchemeShareSplit_(leadId, store) {
  store = store || loadCrmStore_();
  leadId = String(leadId || '').trim();
  var lead = (store.leads && store.leads.byId && store.leads.byId[leadId]) || {};
  var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  var snap = entry ? (entry.full || entry) : null;
  if (!snap && !lead.interestedModel) {
    return { dealerTotal: 0, companyTotal: 0, byComponent: {}, schemeMonth: '' };
  }

  var model = (snap && (snap.model || snap.vehicleModel)) || lead.interestedModel || '';
  var variant = (snap && snap.variant) || lead.variant || '';
  var bookingDate = (snap && snap.bookingDate) || lead.bookingDate || nowDate_();
  return schemeShareSplitFor_(model, variant, bookingDate, snap || {});
}

/**
 * PURE share splitter — the single implementation of "who pays what" for a set of
 * offer amounts on a model/variant/month. Used by both saved leads
 * (computeSchemeShareSplit_) and un-saved quotations, so a quotation's OEM
 * recovery can never disagree with the booking's.
 *
 * Partial / under-package rule (business): company share is applied FIRST.
 * Example: master company ₹27,000 + dealer ₹13,000; passed ₹5,000 →
 * company ₹5,000, dealer ₹0. Passed ₹30,000 → company ₹27,000, dealer ₹3,000.
 * This keeps Partial Benefit simple — amount is not a fixed ratio of any one scheme.
 *
 * @param {string} model
 * @param {string} variant
 * @param {string} bookingDate  yyyy-MM-dd
 * @param {Object} offers  { consumerDiscount, exchangeBonus, loyaltyBonus,
 *                           referralBonus, dsaDiscount, additionalDiscount }
 * @return {{dealerTotal:number, companyTotal:number, byComponent:Object,
 *           schemeMonth:string, model:string, variant:string}}
 */
function schemeShareSplitFor_(model, variant, bookingDate, offers) {
  model = String(model || '').trim();
  variant = String(variant || '').trim();
  bookingDate = bookingDate || nowDate_();
  var snap = offers || {};
  var master = getSchemeSharesForLead_(model, variant, bookingDate);

  var byComponent = {};
  var dealerTotal = 0;
  var companyTotal = 0;

  function addPart(key, actualAmt, forceInclude) {
    var m = master[key];
    if (!m) return;
    var actual = num_(actualAmt);
    if (!forceInclude && actual <= 0 && key !== 'rtoInsuranceBenefit') return;

    var company = Number(m.companyShare) || 0;
    var dealer = Number(m.dealerShare) || 0;

    if (key === 'rtoInsuranceBenefit') {
      // Entitlement-based: company share from circular when product qualifies
      company = Number(m.companyShare) || 0;
      dealer = Number(m.dealerShare) || 0;
    } else if (actual > 0) {
      // Cap shares by what was actually given on the lead.
      // Company share FIRST (partial / under-package): consume OEM company
      // portion before any dealer share. Avoids proportional splits that make
      // the same ₹5,000 mean different company/dealer mixes per component.
      company = round2_(Math.min(company, actual));
      dealer = round2_(Math.min(dealer, Math.max(0, actual - company)));
    } else {
      return;
    }

    byComponent[key] = {
      actual: actual,
      dealerShare: dealer,
      companyShare: company,
      label: m.label || key
    };
    dealerTotal = round2_(dealerTotal + dealer);
    companyTotal = round2_(companyTotal + company);
  }

  if (snap) {
    addPart('consumerDiscount', snap.consumerDiscount);
    addPart('exchangeBonus', snap.exchangeBonus);
    addPart('loyaltyBonus', snap.loyaltyBonus);
    addPart('referralBonus', snap.referralBonus);
    addPart('dsaDiscount', snap.dsaDiscount);
    // Additional discount stays 100% dealer (not in master OEM shares)
    var addl = num_(snap.additionalDiscount);
    if (addl > 0) {
      byComponent.additionalDiscount = {
        actual: addl, dealerShare: addl, companyShare: 0, label: 'Additional Discount'
      };
      dealerTotal = round2_(dealerTotal + addl);
    }
  }

  // Free RTO + Insurance entitlement from master (even if not typed as an offer line)
  if (master.rtoInsuranceBenefit && Number(master.rtoInsuranceBenefit.companyShare) > 0) {
    addPart('rtoInsuranceBenefit', master.rtoInsuranceBenefit.totalBenefit, true);
  }

  return {
    dealerTotal: dealerTotal,
    companyTotal: companyTotal,
    byComponent: byComponent,
    schemeMonth: schemeMonthFromDate_(bookingDate),
    model: model,
    variant: variant
  };
}

function readIncentiveMasterRows_() {
  var sheet = ensureIncentiveMasterSheet_();
  var headers = getHeaders_(sheet, 1);
  var last = sheet.getLastRow();
  if (last < 2) return [];
  var data = sheet.getRange(2, 1, last - 1, headers.length).getValues();
  return data.map(function (row) {
    function val(name) {
      var i = findHeaderIndex_(headers, name);
      return i >= 0 ? row[i] : '';
    }
    return {
      schemeMonth: String(val('Scheme Month') || '').trim(),
      effectiveFrom: formatDate_(val('Effective From')) || '',
      effectiveTo: formatDate_(val('Effective To')) || '',
      productCategory: String(val('Product Category') || '').trim(),
      incentivePerRetail: Number(val('Incentive Per Retail')) || 0,
      minRetails: Number(val('Min Retails')) || 0,
      maxSlab: Number(val('Max Slab')) || 0,
      status: String(val('Status') || 'Active').trim(),
      notes: String(val('Notes') || '')
    };
  }).filter(function (r) { return r.schemeMonth && r.productCategory; });
}

function mapLeadToIncentiveCategory_(model, variant) {
  var m = normalizeSchemeModelKey_(model, variant);
  if (m === 'storm') return 'Storm';
  if (m === 'turbo') return 'Turbo';
  if (m === 'hiload' || m === 'hicity' || m === 'hirange') return '3WC';
  // default passenger-ish
  return 'Pax';
}

function getIncentiveRateForLead_(model, variant, deliveryDate) {
  var month = schemeMonthFromDate_(deliveryDate);
  var cat = mapLeadToIncentiveCategory_(model, variant);
  var rows = readIncentiveMasterRows_();
  for (var i = 0; i < rows.length; i++) {
    var r = rows[i];
    if (String(r.status).toLowerCase() !== 'active') continue;
    if (r.schemeMonth !== month) continue;
    if (String(r.productCategory).toLowerCase() !== String(cat).toLowerCase()) continue;
    return r;
  }
  return null;
}

/** Staff-facing label for each commercial offer field key. */
function getSchemeOfferFieldLabel_(key) {
  var policy = (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {};
  if (policy[key] && policy[key].label) return policy[key].label;
  var labels = {
    consumerDiscount: 'Consumer Discount',
    exchangeBonus: 'Exchange Bonus',
    loyaltyBonus: 'Loyalty Bonus',
    referralBonus: 'Referral Bonus',
    dsaDiscount: 'DSA Bonus',
    additionalDiscount: 'Additional Discount'
  };
  return labels[key] || key;
}

/** Cap for Additional Discount free entry (suggestions kept for other UIs). */
function getAdditionalDiscountChoices_() {
  return [0, 1000, 2000, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 40000, 50000];
}

/** Build selectable ₹ amounts: 0 + shares + full max (never above max). */
function buildSchemeAmountChoices_(dealerShare, companyShare, totalMax) {
  var maxAmt = round2_(Number(totalMax) || 0);
  var set = {};
  function add(v) {
    var n = round2_(Number(v) || 0);
    if (!(n >= 0)) return;
    if (maxAmt > 0 && n > maxAmt + 0.009) return;
    set[String(n)] = n;
  }
  add(0);
  if (maxAmt > 0) {
    add(dealerShare);
    add(companyShare);
    add(maxAmt);
    if (maxAmt >= 10000) add(round2_(maxAmt / 2));
  }
  return Object.keys(set).map(function (k) { return set[k]; }).sort(function (a, b) { return a - b; });
}

/**
 * Which scheme offer fields are allowed for Model + Variant on a booking date.
 * Each rule includes `choices` for dropdown-only UI (no manual amount entry).
 */
function getSchemeOfferRulesForVehicle_(model, variant, bookingDate) {
  var master = getSchemeSharesForLead_(model, variant, bookingDate);
  var keys = (CRM.COMMERCIAL && CRM.COMMERCIAL.OFFER_KEYS) || [];
  var rules = {};
  var modelDisp = String(model || '').trim() || 'selected model';
  var variantDisp = String(variant || '').trim();
  var month = schemeMonthFromDate_(bookingDate);
  var masterKeys = Object.keys(master || {});
  var family = normalizeSchemeModelKey_(model, variant);
  var familyLabel = ({
    hiload: 'HiLoad / Hi-Load',
    hicity: 'HiCity',
    hirange: 'Hirange / Neo HiRange / High Range',
    turbo: 'Turbo / Turbo Max',
    storm: 'Storm'
  })[family] || modelDisp;

  keys.forEach(function (key) {
    var label = getSchemeOfferFieldLabel_(key);
    if (key === 'additionalDiscount') {
      var addChoices = getAdditionalDiscountChoices_();
      rules[key] = {
        key: key,
        label: label,
        allowed: true,
        maxAmount: addChoices[addChoices.length - 1],
        choices: addChoices,
        hint: 'Dealer-funded — type any amount (max ₹' + addChoices[addChoices.length - 1] + ')'
      };
      return;
    }
    var m = master[key];
    if (!m) {
      var noneHint = masterKeys.length
        ? ('Not available for ' + modelDisp + (variantDisp ? ' / ' + variantDisp : '') + ' in Scheme Master')
        : ('No Scheme Master row for ' + familyLabel +
          ' in ' + month + '. Check Scheme Month = ' + month + ' and Status = Active.');
      rules[key] = {
        key: key,
        label: label,
        allowed: false,
        maxAmount: 0,
        choices: [0],
        hint: noneHint
      };
      return;
    }
    var total = Number(m.totalBenefit);
    if (!isFinite(total) || total <= 0) {
      total = round2_((Number(m.dealerShare) || 0) + (Number(m.companyShare) || 0));
    }
    if (total <= 0) {
      rules[key] = {
        key: key,
        label: label,
        allowed: false,
        maxAmount: 0,
        choices: [0],
        hint: 'Scheme Master total is ₹0 for ' + label + ' on this model'
      };
      return;
    }
    var dealer = round2_(Number(m.dealerShare) || 0);
    var company = round2_(Number(m.companyShare) || 0);
    var maxAmt = round2_(total);
    rules[key] = {
      key: key,
      label: label,
      allowed: true,
      maxAmount: maxAmt,
      dealerShare: dealer,
      companyShare: company,
      choices: buildSchemeAmountChoices_(dealer, company, maxAmt),
      hint: 'Enter amount up to ₹' + maxAmt + ' (Scheme Master ' + (m.model || '') + ' · ' + month + ')'
    };
  });

  return {
    schemeMonth: month,
    model: modelDisp,
    variant: variantDisp,
    modelFamily: family,
    matchedComponents: masterKeys,
    rules: rules
  };
}

/**
 * Validate scheme amounts.
 * - When Scheme Master has a max for the field: amount must be 0..max (manual entry OK).
 * - When master has no match for this model: allow manual entry (no hard block).
 * - When master matched the model but this component is ₹0 / N/A: block amount > 0.
 */
function validateSchemeOffersForVehicle_(model, variant, bookingDate, offers) {
  var ctx = getSchemeOfferRulesForVehicle_(model, variant, bookingDate);
  var lines = [];
  var modelDisp = ctx.model || 'selected model';
  var variantPart = ctx.variant ? (' / ' + ctx.variant) : '';
  var hasMaster = (ctx.matchedComponents || []).length > 0;

  Object.keys(offers || {}).forEach(function (key) {
    var amt = round2_(num_(offers[key]));
    if (amt < 0) {
      lines.push('• ' + (ctx.rules[key] && ctx.rules[key].label || key) + ': amount cannot be negative');
      return;
    }
    var rule = ctx.rules[key];
    if (!rule) return;

    if (key === 'additionalDiscount') {
      if (rule.maxAmount != null && amt > rule.maxAmount + 0.01) {
        lines.push('• ' + rule.label + ': ₹' + amt + ' exceeds maximum ₹' + rule.maxAmount);
      }
      return;
    }

    if (amt <= 0) return;

    if (!hasMaster) return; // no Scheme Master match — allow manual feed

    if (!rule.allowed || !(Number(rule.maxAmount) > 0)) {
      lines.push('• ' + rule.label + ': not in Scheme Master for ' + modelDisp + variantPart + ' — enter 0');
      return;
    }
    if (amt > rule.maxAmount + 0.01) {
      lines.push('• ' + rule.label + ': ₹' + amt + ' exceeds Scheme Master max ₹' + rule.maxAmount);
    }
  });

  if (lines.length) {
    throw businessError_(
      'Please fix these scheme fields:\n' + lines.join('\n'),
      'SCHEME_VALIDATION'
    );
  }
  return ctx;
}

/** Dialog helper — scheme rules for a lead or model/variant pair. */
function getSchemeRulesForDialog(model, variant, bookingDate) {
  try {
    return getSchemeOfferRulesForVehicle_(model, variant, bookingDate || nowDate_());
  } catch (e) {
    return { schemeMonth: '', model: model || '', variant: variant || '', rules: {}, error: e.message };
  }
}

function getSchemeRulesForLeadDialog(leadId) {
  return getSchemeRulesForLeadDialog_(leadId);
}

function getSchemeRulesForLeadDialog_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return { rules: {} };
  var lead = getLeadFromRegisterLight_(leadId) || {};
  var snap = null;
  try {
    if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
      snap = getLatestCommercialSnapshotForLead_(leadId);
    }
  } catch (e) {}
  // Prefer Lead Register model/variant (Price Master names like Turbo Max);
  // snapshot model is only a fallback.
  var model = lead.interestedModel || lead.model ||
    (snap && (snap.model || snap.vehicleModel)) || '';
  var variant = lead.variant || (snap && snap.variant) || '';
  var bookingDate = (snap && snap.bookingDate) || lead.bookingDate || nowDate_();
  return getSchemeOfferRulesForVehicle_(model, variant, bookingDate);
}

/**
 * On Mark Delivered: create Incentive Register row from Incentive Master rate.
 * Skips if Lead ID already has a register row. Status starts as Pending (min-retails check is manual).
 */
function upsertIncentiveRegisterOnDelivery_(leadId, deliveryDate, store) {
  leadId = String(leadId || '').trim();
  if (!leadId) return null;
  store = store || loadCrmStore_();
  var lead = (store.leads && store.leads.byId && store.leads.byId[leadId]) || {};
  var entry = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  var snap = entry ? (entry.full || entry) : null;
  var model = (snap && (snap.model || snap.vehicleModel)) || lead.interestedModel || '';
  var variant = (snap && snap.variant) || lead.variant || '';
  var executive = (snap && snap.bookingExecutive) || lead.executive || '';
  var bookingId = (snap && snap.bookingId) || '';
  var delDate = formatDate_(deliveryDate) || nowDate_();
  var rate = getIncentiveRateForLead_(model, variant, delDate);
  if (!rate) return null;

  var sheet = ensureIncentiveRegisterSheet_();
  var headers = getHeaders_(sheet, 1);
  var last = sheet.getLastRow();
  var leadCol = findHeaderIndex_(headers, 'Lead ID') + 1;
  if (leadCol > 0 && last >= 2) {
    var leadIds = sheet.getRange(2, leadCol, Math.max(0, last - 1), 1).getValues();
    for (var i = 0; i < leadIds.length; i++) {
      if (String(leadIds[i][0] || '').trim() === leadId) return null; // already logged
    }
  }

  var cat = mapLeadToIncentiveCategory_(model, variant);
  var rowObj = {
    'Incentive ID': generateId_('incentive'),
    'Scheme Month': rate.schemeMonth || schemeMonthFromDate_(delDate),
    'Executive': executive,
    'Lead ID': leadId,
    'Booking ID': bookingId,
    'Model': model,
    'Variant': variant,
    'Product Category': cat,
    'Delivery Date': delDate,
    'Incentive Amount': rate.incentivePerRetail,
    'Status': 'Pending',
    'Paid Date': '',
    'Remarks': rate.minRetails
      ? ('Rate from Incentive Master. Min retails: ' + rate.minRetails + (rate.maxSlab ? '; Max slab: ' + rate.maxSlab : ''))
      : '',
    'Last Updated': nowDateTime_()
  };
  var values = headers.map(function (c) {
    return rowObj[c] != null ? rowObj[c] : '';
  });
  sheet.appendRow(values);
  return rowObj;
}

/** Menu: jump to Scheme Master for monthly edit. */
function menuOpenSchemeMaster() {
  ensureSchemeAndIncentiveSheets_();
  var sheet = getSheet_(CRM.SHEETS.SCHEME_MASTER);
  getSpreadsheet_().setActiveSheet(sheet);
  SpreadsheetApp.getUi().alert(
    'Scheme Master (monthly)',
    'Update Dealer Share / Company Share (₹) for each Model + Component.\n\n' +
    'Each new month:\n1) Copy last month rows\n2) Change Scheme Month + Effective From/To\n3) Edit ₹ amounts from the circular\n4) Keep Status = Active\n5) CRM → Refresh All Sheets\n\n' +
    'July 2026 (EM/07-2026/004) is already seeded.',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function menuOpenIncentiveMaster() {
  ensureSchemeAndIncentiveSheets_();
  var sheet = getSheet_(CRM.SHEETS.INCENTIVE_MASTER);
  getSpreadsheet_().setActiveSheet(sheet);
  SpreadsheetApp.getUi().alert(
    'Incentive Master (monthly)',
    'Manpower incentive from OEM circular.\n\n' +
    'Each month: copy rows, set Scheme Month / dates / Incentive Per Retail / Max Slab.\n' +
    'Incentive Register tracks executive payouts per retail.\n\n' +
    'July 2026 seeded: Pax ₹3000, 3WC ₹3000, Storm ₹7500, Turbo ₹5000 (min 2 retails, max ₹20000).',
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function menuOpenIncentiveRegister() {
  ensureSchemeAndIncentiveSheets_();
  getSpreadsheet_().setActiveSheet(getSheet_(CRM.SHEETS.INCENTIVE_REGISTER));
}

/** Re-seed July 2026 only if user confirms (owner). */
function menuReseedJuly2026Schemes() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Only spreadsheet owner can reseed scheme masters.');
    return;
  }
  var ui = SpreadsheetApp.getUi();
  var res = ui.alert(
    'Reseed July 2026 schemes?',
    'This appends July 2026 rows if missing, or you can clear the Scheme Master manually first.\nContinue?',
    ui.ButtonSet.YES_NO
  );
  if (res !== ui.Button.YES) return;
  var sheet = ensureSchemeMasterSheet_();
  // Append only if no 2026-07 rows
  var rows = readSchemeMasterRows_().filter(function (r) { return r.schemeMonth === '2026-07'; });
  if (rows.length) {
    ui.alert('July 2026 scheme rows already exist (' + rows.length + '). Clear them manually if you want a clean reseed.');
    return;
  }
  seedJuly2026SchemeMaster_(sheet, CRM.SCHEME_MASTER.COLS);
  var inc = ensureIncentiveMasterSheet_();
  var irows = readIncentiveMasterRows_().filter(function (r) { return r.schemeMonth === '2026-07'; });
  if (!irows.length) seedJuly2026IncentiveMaster_(inc, CRM.INCENTIVE_MASTER.COLS);
  ui.alert('July 2026 Scheme Master + Incentive Master seeded.');
}
