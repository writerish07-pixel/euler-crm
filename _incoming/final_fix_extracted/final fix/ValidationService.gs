/**
 * ValidationService – fast integrity checks using DataStore indexes.
 */

function runValidation_() {
  var valStart = Date.now();
  invalidateCrmStore_();
  var store = loadCrmStore_(true);
  var report = [];
  var pass = 0, fail = 0;

  function check(name, ok, detail) {
    report.push({ check: name, pass: ok, detail: detail || '' });
    if (ok) pass++; else fail++;
  }

  var ss = getSpreadsheet_();
  if (typeof ensureCommercialSnapshotSheet_ === 'function') {
    try { ensureCommercialSnapshotSheet_(); } catch (e) {}
  }
  try { if (typeof ensureQuotationLogSheet_ === 'function') ensureQuotationLogSheet_(); } catch (eQ) {}
  try { if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_(); } catch (eF) {}
  Object.values(CRM.SHEETS).forEach(function (name) {
    check('Sheet exists: ' + name, !!ss.getSheetByName(name));
  });
  ensureTransactionLogSheet_();
  check('Transaction Log exists', !!ss.getSheetByName(CRM.SHEETS.TRANSACTION_LOG));

  var dupIds = findDuplicateLeadIds_(store);
  check('No duplicate Lead IDs', dupIds.length === 0, dupIds.join(', '));

  var dupMobiles = findDuplicateMobilesInStore_(store);
  check('No duplicate mobiles', dupMobiles.length === 0, dupMobiles.slice(0, 5).join(', '));

  var brokenAct = countBrokenRefs_(store.activities.rows, store.activities.headers, 'Lead ID', store.leads.byId);
  check('Activity Lead ID lookups', brokenAct === 0, brokenAct + ' broken references');

  var brokenPay = countBrokenRefs_(store.payments.rows, store.payments.headers, 'Lead ID', store.leads.byId);
  check('Payment Lead ID lookups', brokenPay === 0, brokenPay + ' broken references');

  var brokenDel = countBrokenRefs_(store.deliveries.rows, store.deliveries.headers, 'Lead ID', store.leads.byId);
  check('Delivery Lead ID lookups', brokenDel === 0, brokenDel + ' broken references');

  var missingNames = countMissingField_(store.leads.byId, 'customerName');
  check('All leads have customer name', missingNames === 0, missingNames + ' missing');

  var activeCount = 0;
  var closedCount = 0;
  Object.keys(store.leads.byId).forEach(function (id) {
    var st = normalizeAccountStatus_(store.leads.byId[id].accountStatus);
    if (st === ACCOUNT_STATUS.ACTIVE) activeCount++;
    if (st === ACCOUNT_STATUS.CLOSED) closedCount++;
  });
  check('Active leads indexed', activeCount > 0 || Object.keys(store.leads.byId).length === 0,
    'active=' + activeCount + ', closed=' + closedCount);

  var pickerCache = getLeadPickerCache_();
  check('Lead picker cache loads', pickerCache.length >= 0, pickerCache.length + ' leads in cache');
  var activeInPicker = pickerCache.filter(function (l) { return l.accountStatus === ACCOUNT_STATUS.ACTIVE; }).length;
  check('Picker active leads match', activeInPicker === activeCount,
    'picker=' + activeInPicker + ', store=' + activeCount);

  var invalidMobiles = countInvalidMobiles_(store);
  check('Mobile numbers valid or empty', invalidMobiles === 0, invalidMobiles + ' invalid');

  var metricsResult = computeDashboardMetrics_(store);
  var metrics = metricsResult.metrics || metricsResult;
  var leadCount = Object.keys(store.leads.byId).length;
  check('Dashboard metrics populated',
    leadCount === 0 || metrics.monthlyLeads > 0 || metrics.revenue > 0 || metrics.outstanding > 0,
    'monthlyLeads=' + metrics.monthlyLeads + ', revenue=' + metrics.revenue +
    ', outstanding=' + metrics.outstanding + ', totalLeads=' + leadCount);

  var masters = getMasters_();
  check('Masters dropdowns loaded', Object.keys(masters).length >= 5);
  check('Executive dropdown complete', (masters['Executives'] || []).length >= 5,
    'count=' + (masters['Executives'] || []).length);
  // Models are NOT a magic count — the dealership sells whatever Price Master prices.
  // The real requirement is that every model priced in Price Master is selectable
  // when creating a lead, otherwise that model can never be booked.
  var modelList = masters['Models'] || [];
  var pricedModels = [];
  try {
    if (typeof getActivePriceMasterRecords_ === 'function') {
      var seen = {};
      (getActivePriceMasterRecords_().rows || []).forEach(function (r) {
        var m = String(r.model || '').trim();
        if (m && !seen[m.toLowerCase()]) { seen[m.toLowerCase()] = 1; pricedModels.push(m); }
      });
    }
  } catch (e) { pricedModels = []; }
  var missingModels = pricedModels.filter(function (m) {
    return !modelList.some(function (x) { return String(x).trim().toLowerCase() === m.toLowerCase(); });
  });
  check('Model dropdown covers all priced models',
    pricedModels.length ? missingModels.length === 0 : modelList.length > 0,
    'dropdown=' + modelList.length + ', priced=' + pricedModels.length +
    (missingModels.length ? ', MISSING: ' + missingModels.join(', ') : ''));
  check('Lead Source dropdown complete', (masters['Lead Sources'] || []).length >= 5,
    'count=' + (masters['Lead Sources'] || []).length);

  var settings = getSettings_();
  check('Settings configured', !!settings.leadPrefix && !!settings.receiptPrefix);

  var outMismatches = countOutstandingMismatches_(store);
  check('Outstanding balances consistent', outMismatches === 0, outMismatches + ' mismatches');
  var commercialVal = validateCommercialEngine_(store);
  check('Commercial engine valid', commercialVal.ok, commercialVal.details.join('; '));
  var activityTypeAudit = auditActivityTypeWriters_();
  check('Activity type writers valid', activityTypeAudit.ok, activityTypeAudit.invalid.join('; '));

  try {
    var cert = certifyDashboard_(false);
    check('Dashboard certified', cert.passed, cert.mismatches.join('; '));
  } catch (certErr) {
    check('Dashboard certified', false, certErr.message);
  }

  writeQAReport_(report, pass, fail);
  logAudit_('VALIDATION', pass + ' passed, ' + fail + ' failed');

  var failed = report.filter(function (r) { return !r.pass; });
  var failDetail = failed.map(function (r) {
    return '• ' + r.check + (r.detail ? ': ' + r.detail : '');
  }).join('\n');

  SpreadsheetApp.getUi().alert('QA Report',
    pass + ' checks passed, ' + fail + ' failed.' +
    (failDetail ? '\n\nFailed:\n' + failDetail : '') +
    '\n\nSee Audit Log for full details.',
    SpreadsheetApp.getUi().ButtonSet.OK);
  recordPerf_('validation', Date.now() - valStart);
  return { pass: pass, fail: fail, report: report };
}

function findDuplicateLeadIds_(store) {
  var seen = {};
  var dupes = {};
  var rows = store.leads.rows || [];
  var h = store.leads.headers || [];
  rows.forEach(function (row) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    if (seen[id]) dupes[id] = true;
    seen[id] = true;
  });
  return Object.keys(dupes);
}

function findDuplicateMobilesInStore_(store) {
  var seen = {}, dupes = [];
  Object.keys(store.leads.byId).forEach(function (id) {
    var m = store.leads.byId[id].mobile;
    if (!m) return;
    if (seen[m]) dupes.push(m);
    seen[m] = true;
  });
  return dupes;
}

function countBrokenRefs_(rows, headers, colName, byId) {
  var count = 0;
  rows.forEach(function (row) {
    var id = String(rowVal_(row, headers, colName)).trim();
    if (id && !byId[id]) count++;
  });
  return count;
}

function countMissingField_(byId, field) {
  var n = 0;
  Object.keys(byId).forEach(function (id) {
    if (!String(byId[id][field] || '').trim()) n++;
  });
  return n;
}

function countInvalidMobiles_(store) {
  var n = 0;
  Object.keys(store.leads.byId).forEach(function (id) {
    var m = store.leads.byId[id].mobile;
    if (m && !isValidMobile_(m)) n++;
  });
  return n;
}

function getExpectedLeadOutstanding_(leadId, store) {
  if (typeof buildLeadCommercialTruthFields_ === 'function') {
    return num_(buildLeadCommercialTruthFields_(leadId, store)['Outstanding Amount']);
  }
  var customerOs = computeDashboardOutstanding_(leadId, store);
  var financeOs = typeof getFinanceOutstandingForLead_ === 'function'
    ? getFinanceOutstandingForLead_(leadId) : 0;
  return round2_(customerOs + financeOs);
}

function countOutstandingMismatches_(store) {
  var mismatches = 0;
  Object.keys(store.leads.byId).forEach(function (id) {
    var lead = store.leads.byId[id];
    if (typeof isActiveLead_ === 'function' && lead && !isActiveLead_(lead)) return;
    var expected = getExpectedLeadOutstanding_(id, store);
    var h = store.leads.headers;
    var rowIdx = store.leads.sheetRow[id] - CRM.LEAD.DATA_START;
    var row = store.leads.rows[rowIdx];
    if (!row) return;
    var stored = parseNumber_(rowVal_(row, h, 'Outstanding Amount'));
    if (Math.abs(stored - expected) > 0.01) mismatches++;
  });
  return mismatches;
}

function findDuplicateMobiles_() {
  return findDuplicateMobilesInStore_(loadCrmStore_());
}

function validateCommercialEngine_(store) {
  store = store || loadCrmStore_();
  var bad = [];
  Object.keys(store.commercial.byLeadId || {}).forEach(function (leadId) {
    var s = store.commercial.byLeadId[leadId];
    if (!String(s.model || '').trim()) bad.push(leadId + ': blank model');
    if (!String(s.variant || '').trim()) bad.push(leadId + ': blank variant');
    if (Number(s.totalDiscount) < 0) bad.push(leadId + ': negative discount');
    if (Number(s.finalExchangeValue) < 0) bad.push(leadId + ': negative exchange');
    if (Number(s.customerPayable) < 0) bad.push(leadId + ': negative payable');

    // Structural engine invariants (only where the pure core is available).
    var snap = s.full || s;
    if (typeof computeCommercialTotals_ === 'function' && typeof deriveClaim_ === 'function') {
      var totals = computeCommercialTotals_(snap);
      var claim = deriveClaim_(snap, null);
      if (Math.abs((claim.dealerDiscount + claim.oemDiscount) - totals.totalDiscount) > 0.01) {
        bad.push(leadId + ': dealer+OEM != total discount');
      }
      if (claim.claimEligible > claim.claimTotal + 0.01) {
        bad.push(leadId + ': eligible claim exceeds claimable');
      }
      if (typeof calculateTcs_ === 'function') {
        var tcsEngine = String(snap.tcsApplicable || 'No').toLowerCase() === 'yes'
          ? calculateTcs_(totals.grossVehicleCost)
          : 0;
        if (Math.abs(Number(totals.tcs) - Number(tcsEngine)) > 0.01) {
          bad.push(leadId + ': TCS not centralised');
        }
      }
    }
  });
  return { ok: bad.length === 0, details: bad.slice(0, 20) };
}

function auditActivityTypeWriters_() {
  var master = getActivityTypeMaster_();
  var workflowTypes = {
    leadCreate: normalizeActivityTypeForWrite_('Lead Created', { allowFallback: true, fallbackType: 'Note' }),
    addActivityDefault: normalizeActivityTypeForWrite_('Call', { allowFallback: false }),
    bookingCreate: normalizeActivityTypeForWrite_('Booking', { allowFallback: true, fallbackType: 'Note' }),
    importFallback: normalizeActivityTypeForWrite_('Import', { allowFallback: true, fallbackType: 'Note' })
  };
  var invalid = [];
  Object.keys(workflowTypes).forEach(function (k) {
    if (master.indexOf(workflowTypes[k]) < 0) invalid.push(k + '->' + workflowTypes[k]);
  });
  return {
    ok: invalid.length === 0,
    master: master,
    mapping: workflowTypes,
    invalid: invalid
  };
}

function writeQAReport_(report, pass, fail) {
  var details = report.map(function (r) {
    return r.check + ': ' + (r.pass ? 'PASS' : 'FAIL') + (r.detail ? ' (' + r.detail + ')' : '');
  }).join('\n');
  logAudit_('QA_REPORT', pass + '/' + (pass + fail) + '\n' + details);
}
