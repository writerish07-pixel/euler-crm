/**
 * InsuranceService.gs — Insurance Register + insurer payout calculator.
 *
 * Payout rates (of Insurance Amount / premium):
 *   • Storm / Strom / Turbo  → 49%
 *   • All other models       → 36.5%
 */

function ensureInsuranceRegisterSheet_() {
  var ss = getSpreadsheet_();
  var name = CRM.SHEETS.INSURANCE_REGISTER;
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  var cols = (CRM.INSURANCE_REGISTER && CRM.INSURANCE_REGISTER.COLS) || [];
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW || 1);
  var mismatch = headers.length !== cols.length;
  if (!mismatch) {
    for (var i = 0; i < cols.length; i++) {
      if (String(headers[i] || '').trim() !== cols[i]) { mismatch = true; break; }
    }
  }
  if (mismatch || sheet.getLastRow() < 1) {
    if (sheet.getLastRow() < 1) {
      sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    } else {
      cols.forEach(function (c) {
        if (findHeaderIndex_(headers, c) < 0) {
          sheet.getRange(1, headers.length + 1).setValue(c).setFontWeight('bold');
          headers = getHeaders_(sheet, 1);
        }
      });
    }
    sheet.setFrozenRows(1);
  }
  return sheet;
}

/**
 * Suggested default payout rate (decimal) by model — NOT locked.
 * Operator must enter/adjust Payout Rate % whenever the company rate changes.
 */
function getSuggestedInsurancePayoutRate_(model, variant) {
  var cfg = CRM.INSURANCE_REGISTER || {};
  var stormTurbo = Number(cfg.SUGGESTED_RATE_STORM_TURBO != null ? cfg.SUGGESTED_RATE_STORM_TURBO : cfg.PAYOUT_RATE_STORM_TURBO);
  var other = Number(cfg.SUGGESTED_RATE_OTHER != null ? cfg.SUGGESTED_RATE_OTHER : cfg.PAYOUT_RATE_OTHER);
  if (!isFinite(stormTurbo) || stormTurbo <= 0) stormTurbo = 0.49;
  if (!isFinite(other) || other <= 0) other = 0.365;

  var family = '';
  if (typeof normalizeSchemeModelKey_ === 'function') {
    family = String(normalizeSchemeModelKey_(model, variant) || '').toLowerCase();
  } else {
    var s = String(model || '').toLowerCase().replace(/[^a-z0-9]/g, '');
    if (s.indexOf('storm') >= 0 || s.indexOf('strom') >= 0) family = 'storm';
    else if (s.indexOf('turbo') >= 0) family = 'turbo';
  }
  if (family === 'storm' || family === 'turbo') return stormTurbo;
  return other;
}

/** @deprecated use getSuggestedInsurancePayoutRate_ */
function getInsurancePayoutRate_(model, variant) {
  return getSuggestedInsurancePayoutRate_(model, variant);
}

/**
 * @param {number} premium
 * @param {string} model
 * @param {string} variant
 * @param {number=} ratePercentOverride  manual % (e.g. 49 or 36.5). Required for accurate payout when rates change.
 */
function computeInsurancePayout_(premium, model, variant, ratePercentOverride) {
  var amt = round2_(num_(premium));
  var ratePercent = ratePercentOverride != null && ratePercentOverride !== ''
    ? num_(ratePercentOverride)
    : round2_(getSuggestedInsurancePayoutRate_(model, variant) * 100);
  if (!isFinite(ratePercent) || ratePercent < 0) {
    throw fieldError_('Payout Rate %', 'Enter a valid payout percentage.', 'VALIDATION');
  }
  var rate = ratePercent / 100;
  return {
    premium: amt,
    rate: rate,
    ratePercent: round2_(ratePercent),
    expectedPayout: round2_(amt * rate),
    suggested: ratePercentOverride == null || ratePercentOverride === ''
  };
}

function resolveLeadInsuranceAmount_(leadId, store) {
  store = store || loadCrmStore_();
  leadId = String(leadId || '').trim();
  var lead = store.leads.byId[leadId] || {};
  var h = store.leads.headers || [];
  var rowIdx = store.leads.sheetRow && store.leads.sheetRow[leadId]
    ? store.leads.sheetRow[leadId] - CRM.LEAD.DATA_START : -1;
  var row = rowIdx >= 0 ? store.leads.rows[rowIdx] : null;
  if (row) {
    var fromLead = parseNumber_(rowVal_(row, h, 'Insurance Amount'));
    if (fromLead > 0) return fromLead;
  }
  var entry = store.commercial && store.commercial.byLeadId
    ? store.commercial.byLeadId[leadId] : null;
  var snap = entry ? (entry.full || entry) : null;
  if (snap && num_(snap.insurance) > 0) return num_(snap.insurance);
  var model = String(lead.interestedModel || '').trim();
  var variant = String(lead.variant || '').trim();
  if (model && variant && typeof getCommercialBreakup_ === 'function') {
    try {
      return num_(getCommercialBreakup_(model, variant, nowDate_()).price.insurance);
    } catch (e) {}
  }
  return 0;
}

function readAllInsuranceEntries_() {
  ensureInsuranceRegisterSheet_();
  var sheet = getSheet_(CRM.SHEETS.INSURANCE_REGISTER);
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
  var last = sheet.getLastRow();
  if (last < CRM.INSURANCE_REGISTER.DATA_START) return [];
  var numRows = last - CRM.INSURANCE_REGISTER.DATA_START + 1;
  var data = sheet.getRange(
    CRM.INSURANCE_REGISTER.DATA_START, 1,
    last, headers.length
  ).getValues();
  return data.map(function (row, i) {
    var map = {};
    headers.forEach(function (h, c) { map[h] = row[c]; });
    return {
      sheetRow: CRM.INSURANCE_REGISTER.DATA_START + i,
      entryId: String(map['Entry ID'] || '').trim(),
      leadId: String(map['Lead ID'] || '').trim(),
      customerName: String(map['Customer Name'] || '').trim(),
      mobile: String(map['Mobile'] || '').trim(),
      model: String(map['Model'] || '').trim(),
      variant: String(map['Variant'] || '').trim(),
      insuranceCompany: String(map['Insurance Company'] || '').trim(),
      policyNumber: String(map['Policy Number'] || '').trim(),
      insuranceAmount: parseNumber_(map['Insurance Amount']),
      payoutRatePercent: parseNumber_(map['Payout Rate %']),
      expectedPayout: parseNumber_(map['Expected Payout']),
      receivedPayout: parseNumber_(map['Received Payout']),
      payoutOutstanding: parseNumber_(map['Payout Outstanding']),
      status: String(map['Status'] || '').trim(),
      policyDate: formatDate_(map['Policy Date']),
      deliveryDate: formatDate_(map['Delivery Date']),
      lastUpdated: String(map['Last Updated'] || ''),
      remarks: String(map['Remarks'] || '')
    };
  }).filter(function (e) { return !!e.entryId || !!e.leadId; });
}

function findInsuranceRowByLead_(sheet, headers, leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return -1;
  var col = findHeaderIndex_(headers, 'Lead ID') + 1;
  if (col < 1) return -1;
  var last = sheet.getLastRow();
  if (last < CRM.INSURANCE_REGISTER.DATA_START) return -1;
  var vals = sheet.getRange(CRM.INSURANCE_REGISTER.DATA_START, col, Math.max(0, last - CRM.INSURANCE_REGISTER.DATA_START + 1), 1).getValues();
  for (var i = 0; i < vals.length; i++) {
    if (String(vals[i][0] || '').trim() === leadId) return CRM.INSURANCE_REGISTER.DATA_START + i;
  }
  return -1;
}

function insuranceStatusFromAmounts_(expected, received) {
  expected = num_(expected);
  received = num_(received);
  if (received <= 0.01) return 'Pending';
  if (received + 0.01 >= expected) return 'Received';
  return 'Partial';
}

function writeInsuranceRowMap_(sheet, row, headers, map) {
  Object.keys(map).forEach(function (name) {
    var col = findHeaderIndex_(headers, name) + 1;
    if (col > 0) setValueSafe_(sheet.getRange(row, col), map[name]);
  });
}

/**
 * Create or update Insurance Register row for a lead.
 * Preserves Received Payout when updating an existing entry.
 */
function upsertInsuranceEntryForLead_(leadId, opts) {
  opts = opts || {};
  leadId = String(leadId || '').trim();
  if (!leadId) throw fieldError_('Lead ID', 'Select a lead.', 'VALIDATION');

  ensureInsuranceRegisterSheet_();
  var store = loadCrmStore_(true);
  var lead = store.leads.byId[leadId];
  if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');

  var sheet = getSheet_(CRM.SHEETS.INSURANCE_REGISTER);
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
  var existingRow = findInsuranceRowByLead_(sheet, headers, leadId);

  var company = String(opts.insuranceCompany || opts.insurerName || lead.insurerName || '').trim();
  if (!company && existingRow > 0) {
    var companyCol = findHeaderIndex_(headers, 'Insurance Company') + 1;
    if (companyCol > 0) company = String(sheet.getRange(existingRow, companyCol).getValue() || '').trim();
  }
  if (!company) throw fieldError_('Insurance Company', 'Enter the insurance company name.', 'VALIDATION');

  var premium = opts.insuranceAmount != null && opts.insuranceAmount !== ''
    ? num_(opts.insuranceAmount)
    : resolveLeadInsuranceAmount_(leadId, store);
  if (premium <= 0) throw fieldError_('Insurance Amount', 'Insurance amount must be greater than zero.', 'VALIDATION');

  var model = String(opts.model || lead.interestedModel || '').trim();
  var variant = String(opts.variant || lead.variant || '').trim();

  // Payout % is manual / variable. Resolve order:
  // 1) explicit opts.payoutRatePercent  2) existing row rate  3) suggested default for model
  var ratePercent = null;
  if (opts.payoutRatePercent != null && opts.payoutRatePercent !== '') {
    ratePercent = num_(opts.payoutRatePercent);
  } else if (existingRow > 0) {
    var rateCol = findHeaderIndex_(headers, 'Payout Rate %') + 1;
    if (rateCol > 0) {
      var prevRate = parseNumber_(sheet.getRange(existingRow, rateCol).getValue());
      if (prevRate > 0) ratePercent = prevRate;
    }
  }
  if (ratePercent == null || !isFinite(ratePercent) || ratePercent < 0) {
    ratePercent = round2_(getSuggestedInsurancePayoutRate_(model, variant) * 100);
  }

  var calc = computeInsurancePayout_(premium, model, variant, ratePercent);

  var received = 0;
  var entryId = '';
  if (existingRow > 0) {
    var recvCol = findHeaderIndex_(headers, 'Received Payout') + 1;
    var idCol = findHeaderIndex_(headers, 'Entry ID') + 1;
    if (recvCol > 0) received = parseNumber_(sheet.getRange(existingRow, recvCol).getValue());
    if (idCol > 0) entryId = String(sheet.getRange(existingRow, idCol).getValue() || '').trim();
  }
  if (opts.receivedPayout != null && opts.receivedPayout !== '') {
    received = num_(opts.receivedPayout);
  }
  if (!entryId) entryId = generateId_('insurance');

  var expected = calc.expectedPayout;
  var outstanding = round2_(Math.max(0, expected - received));
  var status = insuranceStatusFromAmounts_(expected, received);
  var del = store.deliveryByLead[leadId] || {};

  var map = {
    'Entry ID': entryId,
    'Lead ID': leadId,
    'Customer Name': lead.customerName || '',
    'Mobile': lead.mobile || '',
    'Model': model,
    'Variant': variant,
    'Insurance Company': company,
    'Policy Number': String(opts.policyNumber || '').trim(),
    'Insurance Amount': calc.premium,
    'Payout Rate %': calc.ratePercent,
    'Expected Payout': expected,
    'Received Payout': received,
    'Payout Outstanding': outstanding,
    'Status': status,
    'Policy Date': formatDate_(opts.policyDate) || nowDate_(),
    'Delivery Date': formatDate_(opts.deliveryDate || del.deliveryDate) || '',
    'Insurance Executive': String(opts.insuranceExecutive || '').trim() || 'Jayash',
    'Last Updated': nowDateTime_(),
    'Remarks': String(opts.remarks || '').trim()
  };

  // Keep prior policy number / remarks / executive if not supplied on update.
  if (existingRow > 0) {
    ['Policy Number', 'Remarks', 'Policy Date', 'Insurance Executive'].forEach(function (k) {
      var optKey = k === 'Policy Number' ? 'policyNumber'
        : (k === 'Remarks' ? 'remarks'
          : (k === 'Policy Date' ? 'policyDate' : 'insuranceExecutive'));
      if (opts[optKey] != null && String(opts[optKey]).trim() !== '') return;
      if (String(map[k] || '').trim() && k !== 'Insurance Executive') return;
      var c = findHeaderIndex_(headers, k) + 1;
      if (c > 0) {
        var prev = sheet.getRange(existingRow, c).getValue();
        if (prev !== '' && prev != null) map[k] = k.indexOf('Date') >= 0 ? formatDate_(prev) || prev : prev;
      }
    });
  }
  if (!String(map['Insurance Executive'] || '').trim()) map['Insurance Executive'] = 'Jayash';

  var row = existingRow > 0 ? existingRow : Math.max(sheet.getLastRow() + 1, CRM.INSURANCE_REGISTER.DATA_START);
  writeInsuranceRowMap_(sheet, row, headers, map);

  // Mirror insurer + amount onto Lead Register.
  try {
    updateLeadRegisterFields_(leadId, {
      'Insurer Name': company,
      'Insurance Amount': calc.premium,
      'Insurance Status': opts.insuranceStatus || 'Yes'
    });
  } catch (eLead) {
    Logger.log('upsertInsuranceEntryForLead_ lead mirror: ' + eLead.message);
  }

  try {
    if (typeof upsertExtraIncomeForLead_ === 'function') {
      upsertExtraIncomeForLead_(leadId, { reason: 'insurance_upsert' });
    }
  } catch (eXi) {
    Logger.log('upsertExtraIncomeForLead_ after insurance: ' + eXi.message);
  }

  return {
    entryId: entryId,
    leadId: leadId,
    insuranceAmount: calc.premium,
    payoutRatePercent: calc.ratePercent,
    expectedPayout: expected,
    receivedPayout: received,
    payoutOutstanding: outstanding,
    status: status
  };
}

function recordInsurancePayout_(entryId, amount, opts) {
  opts = opts || {};
  entryId = String(entryId || '').trim();
  var amt = num_(amount);
  if (!entryId) throw fieldError_('Entry ID', 'Select an insurance entry.', 'VALIDATION');
  if (amt <= 0) throw fieldError_('Amount', 'Enter payout amount greater than zero.', 'VALIDATION');

  ensureInsuranceRegisterSheet_();
  var sheet = getSheet_(CRM.SHEETS.INSURANCE_REGISTER);
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
  var idCol = findHeaderIndex_(headers, 'Entry ID') + 1;
  if (idCol < 1) throw businessError_('Insurance Register missing Entry ID column', 'SCHEMA');

  var last = sheet.getLastRow();
  if (last < CRM.INSURANCE_REGISTER.DATA_START) throw businessError_('No insurance entries found', 'NOT_FOUND');
  var ids = sheet.getRange(CRM.INSURANCE_REGISTER.DATA_START, idCol, Math.max(0, last - CRM.INSURANCE_REGISTER.DATA_START + 1), 1).getValues();
  var row = -1;
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0] || '').trim() === entryId) {
      row = CRM.INSURANCE_REGISTER.DATA_START + i;
      break;
    }
  }
  if (row < 0) throw businessError_('Insurance entry not found: ' + entryId, 'NOT_FOUND');

  var recvCol = findHeaderIndex_(headers, 'Received Payout') + 1;
  var expCol = findHeaderIndex_(headers, 'Expected Payout') + 1;
  var osCol = findHeaderIndex_(headers, 'Payout Outstanding') + 1;
  var stCol = findHeaderIndex_(headers, 'Status') + 1;
  var remCol = findHeaderIndex_(headers, 'Remarks') + 1;
  var updCol = findHeaderIndex_(headers, 'Last Updated') + 1;

  var prevRecv = recvCol > 0 ? parseNumber_(sheet.getRange(row, recvCol).getValue()) : 0;
  var expected = expCol > 0 ? parseNumber_(sheet.getRange(row, expCol).getValue()) : 0;
  var newRecv = round2_(prevRecv + amt);
  var outstanding = round2_(Math.max(0, expected - newRecv));
  var status = insuranceStatusFromAmounts_(expected, newRecv);

  if (recvCol > 0) setValueSafe_(sheet.getRange(row, recvCol), newRecv);
  if (osCol > 0) setValueSafe_(sheet.getRange(row, osCol), outstanding);
  if (stCol > 0) setValueSafe_(sheet.getRange(row, stCol), status);
  if (updCol > 0) setValueSafe_(sheet.getRange(row, updCol), nowDateTime_());
  if (remCol > 0 && opts.remarks) {
    var prevRem = String(sheet.getRange(row, remCol).getValue() || '');
    var note = 'Payout ₹' + amt + ' on ' + nowDate_();
    if (opts.remarks) note += ' — ' + opts.remarks;
    setValueSafe_(sheet.getRange(row, remCol), prevRem ? prevRem + ' | ' + note : note);
  }

  var leadIdCol = findHeaderIndex_(headers, 'Lead ID') + 1;
  var leadId = leadIdCol > 0 ? String(sheet.getRange(row, leadIdCol).getValue() || '').trim() : '';
  if (leadId) {
    try {
      if (typeof upsertDealerEarningsForLead_ === 'function') {
        upsertDealerEarningsForLead_(leadId, { reason: 'insurance_payout' });
      } else if (typeof upsertExtraIncomeForLead_ === 'function') {
        upsertExtraIncomeForLead_(leadId, { reason: 'insurance_payout' });
      }
    } catch (eXi) {
      Logger.log('dealer earnings after insurance payout: ' + eXi.message);
    }
  }

  return {
    entryId: entryId,
    receivedPayout: newRecv,
    payoutOutstanding: outstanding,
    status: status,
    amountAdded: amt,
    leadId: leadId
  };
}

function computeInsuranceDashboardMetrics_() {
  var entries = [];
  try { entries = readAllInsuranceEntries_(); } catch (e) { return null; }
  var m = {
    insurancePremium: 0,
    insuranceExpected: 0,
    insuranceReceived: 0,
    insuranceOutstanding: 0,
    insuranceCount: entries.length,
    insurancePendingCount: 0
  };
  entries.forEach(function (e) {
    m.insurancePremium += num_(e.insuranceAmount);
    m.insuranceExpected += num_(e.expectedPayout);
    m.insuranceReceived += num_(e.receivedPayout);
    m.insuranceOutstanding += num_(e.payoutOutstanding);
    if (String(e.status || '').toLowerCase() !== 'received') m.insurancePendingCount++;
  });
  m.insurancePremium = round2_(m.insurancePremium);
  m.insuranceExpected = round2_(m.insuranceExpected);
  m.insuranceReceived = round2_(m.insuranceReceived);
  m.insuranceOutstanding = round2_(m.insuranceOutstanding);
  return m;
}

function listPendingInsurancePayouts_() {
  return readAllInsuranceEntries_().filter(function (e) {
    return num_(e.payoutOutstanding) > 0.01;
  });
}

// ── Dialog / menu public handlers ─────────────────────────────────────────

function getInsuranceContextForDialog(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead ID required' };
    var store = loadCrmStore_(true);
    var lead = store.leads.byId[leadId];
    if (!lead) return { success: false, message: 'Lead not found' };
    var premium = resolveLeadInsuranceAmount_(leadId, store);

    // Prefer existing manual rate on Insurance Register if lead already has a row.
    var existingRate = null;
    try {
      var sheet = ensureInsuranceRegisterSheet_();
      var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
      var row = findInsuranceRowByLead_(sheet, headers, leadId);
      if (row > 0) {
        var rateCol = findHeaderIndex_(headers, 'Payout Rate %') + 1;
        if (rateCol > 0) {
          var pr = parseNumber_(sheet.getRange(row, rateCol).getValue());
          if (pr > 0) existingRate = pr;
        }
      }
    } catch (eR) {}

    var calc = computeInsurancePayout_(
      premium, lead.interestedModel, lead.variant, existingRate
    );
    var suggested = round2_(getSuggestedInsurancePayoutRate_(lead.interestedModel, lead.variant) * 100);
    return {
      success: true,
      lead: {
        leadId: leadId,
        customerName: lead.customerName || '',
        mobile: lead.mobile || '',
        model: lead.interestedModel || '',
        variant: lead.variant || '',
        insurerName: lead.insurerName || ''
      },
      insuranceAmount: calc.premium,
      payoutRatePercent: calc.ratePercent,
      suggestedRatePercent: suggested,
      expectedPayout: calc.expectedPayout,
      rateIsManual: existingRate != null
    };
  } catch (e) {
    return { success: false, message: e.message };
  }
}

function saveInsuranceEntryFromDialog(data) {
  return crmRun_('Insurance', 'Save Entry', function () {
    if (data.payoutRatePercent == null || data.payoutRatePercent === '' || !(Number(data.payoutRatePercent) >= 0)) {
      throw fieldError_('Payout Rate %', 'Enter the insurer payout percentage (rates change — enter manually).', 'VALIDATION');
    }
    var result = upsertInsuranceEntryForLead_(data.leadId, {
      insuranceCompany: data.insuranceCompany || data.insurerName,
      insuranceAmount: data.insuranceAmount,
      payoutRatePercent: data.payoutRatePercent,
      policyNumber: data.policyNumber,
      policyDate: data.policyDate,
      remarks: data.remarks
    });
    try { if (typeof refreshCrmAfterDialogSave_ === 'function') refreshCrmAfterDialogSave_(); } catch (e) {}
    return result;
  });
}

function getAllInsuranceEntriesForDialog() {
  try {
    return {
      success: true,
      entries: readAllInsuranceEntries_().map(function (e) {
        return {
          entryId: e.entryId,
          payoutRatePercent: e.payoutRatePercent,
          insuranceAmount: e.insuranceAmount,
          expectedPayout: e.expectedPayout,
          label: e.entryId + ' | ' + e.customerName + ' | ' + e.insuranceCompany +
            ' | ' + e.payoutRatePercent + '% | Prem ₹' + Math.round(e.insuranceAmount)
        };
      })
    };
  } catch (e) {
    return { success: false, message: e.message, entries: [] };
  }
}

function updateInsurancePayoutRate_(entryId, ratePercent) {
  entryId = String(entryId || '').trim();
  var rate = num_(ratePercent);
  if (!entryId) throw fieldError_('Entry ID', 'Select an insurance entry.', 'VALIDATION');
  if (!isFinite(rate) || rate < 0) {
    throw fieldError_('Payout Rate %', 'Enter a valid payout percentage.', 'VALIDATION');
  }

  ensureInsuranceRegisterSheet_();
  var sheet = getSheet_(CRM.SHEETS.INSURANCE_REGISTER);
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
  var idCol = findHeaderIndex_(headers, 'Entry ID') + 1;
  if (idCol < 1) throw businessError_('Insurance Register missing Entry ID column', 'SCHEMA');

  var last = sheet.getLastRow();
  if (last < CRM.INSURANCE_REGISTER.DATA_START) throw businessError_('No insurance entries found', 'NOT_FOUND');
  var ids = sheet.getRange(CRM.INSURANCE_REGISTER.DATA_START, idCol, Math.max(0, last - CRM.INSURANCE_REGISTER.DATA_START + 1), 1).getValues();
  var row = -1;
  for (var i = 0; i < ids.length; i++) {
    if (String(ids[i][0] || '').trim() === entryId) {
      row = CRM.INSURANCE_REGISTER.DATA_START + i;
      break;
    }
  }
  if (row < 0) throw businessError_('Insurance entry not found: ' + entryId, 'NOT_FOUND');

  var premCol = findHeaderIndex_(headers, 'Insurance Amount') + 1;
  var rateCol = findHeaderIndex_(headers, 'Payout Rate %') + 1;
  var expCol = findHeaderIndex_(headers, 'Expected Payout') + 1;
  var recvCol = findHeaderIndex_(headers, 'Received Payout') + 1;
  var osCol = findHeaderIndex_(headers, 'Payout Outstanding') + 1;
  var stCol = findHeaderIndex_(headers, 'Status') + 1;
  var updCol = findHeaderIndex_(headers, 'Last Updated') + 1;

  var premium = premCol > 0 ? parseNumber_(sheet.getRange(row, premCol).getValue()) : 0;
  var received = recvCol > 0 ? parseNumber_(sheet.getRange(row, recvCol).getValue()) : 0;
  var expected = round2_(premium * (rate / 100));
  var outstanding = round2_(Math.max(0, expected - received));
  var status = insuranceStatusFromAmounts_(expected, received);

  if (rateCol > 0) setValueSafe_(sheet.getRange(row, rateCol), round2_(rate));
  if (expCol > 0) setValueSafe_(sheet.getRange(row, expCol), expected);
  if (osCol > 0) setValueSafe_(sheet.getRange(row, osCol), outstanding);
  if (stCol > 0) setValueSafe_(sheet.getRange(row, stCol), status);
  if (updCol > 0) setValueSafe_(sheet.getRange(row, updCol), nowDateTime_());

  var leadIdCol2 = findHeaderIndex_(headers, 'Lead ID') + 1;
  var leadId2 = leadIdCol2 > 0 ? String(sheet.getRange(row, leadIdCol2).getValue() || '').trim() : '';
  if (leadId2) {
    try {
      if (typeof upsertDealerEarningsForLead_ === 'function') {
        upsertDealerEarningsForLead_(leadId2, { reason: 'insurance_rate' });
      } else if (typeof upsertExtraIncomeForLead_ === 'function') {
        upsertExtraIncomeForLead_(leadId2, { reason: 'insurance_rate' });
      }
    } catch (eXi2) {
      Logger.log('dealer earnings after insurance rate: ' + eXi2.message);
    }
  }

  return {
    entryId: entryId,
    payoutRatePercent: round2_(rate),
    expectedPayout: expected,
    payoutOutstanding: outstanding,
    status: status
  };
}

function updateInsurancePayoutRateFromDialog(data) {
  return crmRun_('Insurance', 'Update Payout Rate', function () {
    var result = updateInsurancePayoutRate_(data.entryId, data.payoutRatePercent);
    try { if (typeof refreshCrmAfterDialogSave_ === 'function') refreshCrmAfterDialogSave_(); } catch (e) {}
    return result;
  });
}

function getPendingInsurancePayoutsForDialog() {
  try {
    return {
      success: true,
      entries: listPendingInsurancePayouts_().map(function (e) {
        return {
          entryId: e.entryId,
          label: e.entryId + ' | ' + e.customerName + ' | ' + e.insuranceCompany +
            ' | OS ₹' + Math.round(e.payoutOutstanding)
        };
      })
    };
  } catch (e) {
    return { success: false, message: e.message, entries: [] };
  }
}

function recordInsurancePayoutFromDialog(data) {
  return crmRun_('Insurance', 'Record Payout', function () {
    var result = recordInsurancePayout_(data.entryId, data.amount, { remarks: data.remarks });
    try { if (typeof refreshCrmAfterDialogSave_ === 'function') refreshCrmAfterDialogSave_(); } catch (e) {}
    return result;
  });
}

function menuOpenInsuranceRegister() {
  ensureInsuranceRegisterSheet_();
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.INSURANCE_REGISTER);
  if (sheet) {
    if (sheet.isSheetHidden()) sheet.showSheet();
    ss.setActiveSheet(sheet);
  }
  SpreadsheetApp.getActiveSpreadsheet().toast('Insurance Register opened', 'CRM', 3);
}

function menuAddInsuranceEntry() {
  showAddInsuranceEntryDialog_();
}

function menuRecordInsurancePayout() {
  showRecordInsurancePayoutDialog_();
}

function menuUpdateInsurancePayoutRate() {
  showUpdateInsurancePayoutRateDialog_();
}

/** Recalculate Expected / Outstanding when Payout Rate % or premium is edited on the sheet. */
function handleInsuranceRegisterEdit_(e) {
  if (!e || !e.range) return;
  var sheet = e.range.getSheet();
  var row = e.range.getRow();
  if (row < CRM.INSURANCE_REGISTER.DATA_START) return;
  var headers = getHeaders_(sheet, CRM.INSURANCE_REGISTER.HEADER_ROW);
  var col = e.range.getColumn();
  var header = String(headers[col - 1] || '').trim();

  // Expected / Outstanding are system-calculated — never manually editable.
  if (header === 'Payout Outstanding' || header === 'Expected Payout') {
    if (e.oldValue !== undefined) {
      sheet.getRange(row, col).setValue(e.oldValue);
    } else {
      sheet.getRange(row, col).setValue('');
    }
    try {
      SpreadsheetApp.getUi().alert(
        'Outstanding is Read Only',
        'Expected Payout and Payout Outstanding are system-calculated and cannot be edited.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
    } catch (uiErr) {}
    return;
  }

  if (header !== 'Payout Rate %' && header !== 'Insurance Amount' && header !== 'Received Payout') return;

  var premCol = findHeaderIndex_(headers, 'Insurance Amount') + 1;
  var rateCol = findHeaderIndex_(headers, 'Payout Rate %') + 1;
  var expCol = findHeaderIndex_(headers, 'Expected Payout') + 1;
  var recvCol = findHeaderIndex_(headers, 'Received Payout') + 1;
  var osCol = findHeaderIndex_(headers, 'Payout Outstanding') + 1;
  var stCol = findHeaderIndex_(headers, 'Status') + 1;
  var updCol = findHeaderIndex_(headers, 'Last Updated') + 1;

  var premium = premCol > 0 ? parseNumber_(sheet.getRange(row, premCol).getValue()) : 0;
  var rate = rateCol > 0 ? parseNumber_(sheet.getRange(row, rateCol).getValue()) : 0;
  var received = recvCol > 0 ? parseNumber_(sheet.getRange(row, recvCol).getValue()) : 0;
  var expected = round2_(premium * (rate / 100));
  var outstanding = round2_(Math.max(0, expected - received));
  var status = insuranceStatusFromAmounts_(expected, received);

  if (expCol > 0) setValueSafe_(sheet.getRange(row, expCol), expected);
  if (osCol > 0) setValueSafe_(sheet.getRange(row, osCol), outstanding);
  if (stCol > 0) setValueSafe_(sheet.getRange(row, stCol), status);
  if (updCol > 0) setValueSafe_(sheet.getRange(row, updCol), nowDateTime_());
}
