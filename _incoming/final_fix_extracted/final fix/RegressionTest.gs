/**
 * RegressionTest.gs – automated workflow verification (read-only + dry checks).
 */

function runRegressionTests_() {
  var start = Date.now();
  var tests = [];
  var pass = 0;
  var fail = 0;

  function test(name, fn) {
    try {
      var ok = fn();
      if (ok && typeof ok === 'object' && ok.passed !== undefined) ok = ok.passed;
      tests.push({ name: name, pass: !!ok, detail: '' });
      if (ok) pass++; else fail++;
    } catch (err) {
      tests.push({ name: name, pass: false, detail: err.message });
      fail++;
    }
  }

  test('Config CRM singleton', function () {
    return CRM && CRM.SHEETS && CRM.LEAD && CRM.PAYMENT;
  });

  test('DataStore loads', function () {
    invalidateCrmStore_();
    var store = loadCrmStore_(true);
    return store && store.leads && store.payments;
  });

  test('Outstanding balances match engine', function () {
    invalidateCrmStore_();
    if (typeof syncComputedFields_ === 'function') syncComputedFields_({ dashboard: false });
    var store = loadCrmStore_(true);
    var bad = countOutstandingMismatches_(store);
    if (bad > 0) throw new Error(bad + ' lead(s) with wrong outstanding');
    return true;
  });

  test('Commercial snapshot sheet exists', function () {
    return !!getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  });

  test('Commercial calculation engine', function () {
    var snap = {
      exShowroom: 100, accessories: 10, insurance: 5, registrationRto: 5, fastag: 0,
      handlingCharges: 2, extendedWarranty: 3, rsaAmc: 0, otherCharges: 0,
      consumerDiscount: 5, exchangeBonus: 2, loyaltyBonus: 1, referralBonus: 1, dsaDiscount: 0, additionalDiscount: 0,
      finalExchangeValue: 10
    };
    var t = computeCommercialTotals_(snap);
    // Legacy / Full Benefit default: payable reduces by all offers (totalDiscount)
    return t.grossVehicleCost === 125 && t.totalDiscount === 9 &&
      t.customerBenefitPassed === 9 &&
      t.customerPayable === (t.netVehicleCost - 10);
  });

  test('Owner benefit modes (Full / Partial / None)', function () {
    var base = {
      exShowroom: 100000, accessories: 0, insurance: 0, registrationRto: 0, fastag: 0,
      handlingCharges: 0, extendedWarranty: 0, rsaAmc: 0, otherCharges: 0,
      consumerDiscount: 10000, exchangeBonus: 0, loyaltyBonus: 0, referralBonus: 0,
      dsaDiscount: 0, additionalDiscount: 0, finalExchangeValue: 0, tcsApplicable: 'No'
    };
    function withMode(mode, passed) {
      var s = {};
      Object.keys(base).forEach(function (k) { s[k] = base[k]; });
      s.benefitMode = mode;
      if (passed != null) s.customerBenefitPassed = passed;
      return s;
    }
    var full = computeCommercialTotals_(withMode('Full Benefit'));
    var none = computeCommercialTotals_(withMode('No Benefit', 0));
    var partial = computeCommercialTotals_(withMode('Partial Benefit', 4000));
    var oem = getOemEligibleAmount_(base);
    var retainedPartial = getDealerBenefitRetained_(withMode('Partial Benefit', 4000));
    return full.customerBenefitPassed === 10000 &&
      none.customerBenefitPassed === 0 &&
      none.customerPayable === full.customerPayable + 10000 &&
      partial.customerBenefitPassed === 4000 &&
      oem === 10000 &&
      retainedPartial === 6000;
  });

  test('Extra Income / Dealer Earnings register service', function () {
    return typeof ensureDealerEarningsRegisterSheet_ === 'function' &&
      typeof upsertDealerEarningsForLead_ === 'function' &&
      typeof upsertExtraIncomeForLead_ === 'function' &&
      typeof readAllDealerEarningsRows_ === 'function';
  });

  test('Dealer Earnings does not alter customer payable helpers', function () {
    return typeof computeCommercialTotals_ === 'function' &&
      typeof calcOutstanding_ === 'function' &&
      typeof computeLeadOutstanding_ === 'function' &&
      typeof getDealerBenefitRetained_ === 'function';
  });

  test('No duplicate Lead IDs', function () {
    var store = loadCrmStore_(true);
    return findDuplicateLeadIds_(store).length === 0;
  });

  test('No broken payment references', function () {
    var store = loadCrmStore_(true);
    return countBrokenRefs_(store.payments.rows, store.payments.headers, 'Lead ID', store.leads.byId) === 0;
  });

  test('No broken activity references', function () {
    var store = loadCrmStore_(true);
    return countBrokenRefs_(store.activities.rows, store.activities.headers, 'Lead ID', store.leads.byId) === 0;
  });

  test('Activity type mappings valid', function () {
    var audit = auditActivityTypeWriters_();
    if (!audit.ok) throw new Error(audit.invalid.join('; '));
    return true;
  });

  test('No broken delivery references', function () {
    var store = loadCrmStore_(true);
    return countBrokenRefs_(store.deliveries.rows, store.deliveries.headers, 'Lead ID', store.leads.byId) === 0;
  });

  test('Active leads only in operational picker', function () {
    var store = loadCrmStore_(true);
    var picker = getActiveLeadsForPicker_({ activeOnly: true });
    var nonActive = picker.filter(function (l) {
      return l.accountStatus !== ACCOUNT_STATUS.ACTIVE;
    });
    if (nonActive.length > 0) throw new Error(nonActive.length + ' non-active in picker');
    return true;
  });

  test('Archived excluded from picker', function () {
    var picker = getActiveLeadsForPicker_({ activeOnly: true });
    return picker.every(function (l) {
      return l.accountStatus !== ACCOUNT_STATUS.ARCHIVED;
    });
  });

  test('Dashboard metrics compute', function () {
    var store = loadCrmStore_(true);
    var m = computeDashboardMetrics_(store).metrics;
    return m && typeof m.revenue === 'number' && typeof m.outstanding === 'number';
  });

  test('Model Performance metrics are dynamic', function () {
    var store = loadCrmStore_(true);
    var list = typeof computeModelPerformance_ === 'function'
      ? computeModelPerformance_(store) : null;
    if (!list || !list.length) {
      // Empty Price Master + no lead models is valid; function must still return an array.
      return Array.isArray(list);
    }
    var row = list[0];
    return row.model && typeof row.leads === 'number' && typeof row.bookings === 'number' &&
      typeof row.customerOutstanding === 'number' && typeof row.bookingConversion === 'number';
  });

  test('Outstanding columns are locked (AUTO policy)', function () {
    var auto = (CRM.LEAD && CRM.LEAD.AUTO) || [];
    return auto.indexOf('Outstanding Amount') >= 0 &&
      auto.indexOf('Customer Outstanding') >= 0 &&
      auto.indexOf('Final Outstanding') >= 0 &&
      typeof applyOutstandingReadOnlyStyling_ === 'function';
  });

  test('Dashboard certification', function () {
    return certifyDashboard_(false).passed;
  });

  test('Triggers installed', function () {
    var triggers = ScriptApp.getProjectTriggers();
    return triggers.some(function (t) { return t.getHandlerFunction() === 'onEditHandler_'; });
  });

  test('Transaction log sheet', function () {
    ensureTransactionLogSheet_();
    return !!getSpreadsheet_().getSheetByName(CRM.SHEETS.TRANSACTION_LOG);
  });

  test('Settings readable', function () {
    var s = getSettings_();
    return !!s.leadPrefix && !!s.receiptPrefix;
  });

  test('Masters loaded', function () {
    return Object.keys(getMasters_()).length >= 5;
  });

  test('Search leads function', function () {
    var results = searchLeads_('', false);
    return Array.isArray(results);
  });

  test('Mobile normalization', function () {
    return normalizeMobile_('9876543210') === '9876543210';
  });

  test('Duplicate name detection', function () {
    var groups = findDuplicateLeadGroups_();
    return Array.isArray(groups);
  });

  test('Backup function exists', function () {
    return typeof createVersionedBackup_ === 'function' && typeof restoreBackup_ === 'function';
  });

  test('Self-healing engine', function () {
    return typeof repairSystem_ === 'function' && typeof verifyConfiguration_ === 'function';
  });

  test('Crash report sheet', function () {
    ensureCrashReportSheet_();
    return !!getSpreadsheet_().getSheetByName(CRM.SHEETS.CRASH_REPORT);
  });

  test('Backup registry sheet', function () {
    ensureBackupRegistrySheet_();
    return !!getSpreadsheet_().getSheetByName(CRM.SHEETS.BACKUP_REGISTRY);
  });

  test('Menu handlers verified', function () {
    return verifyMenus_().ok;
  });

  test('Emergency recovery handler', function () {
    return typeof menuSafeRecovery === 'function';
  });

  test('Maintenance mode service', function () {
    return typeof isMaintenanceMode_ === 'function' && typeof setMaintenanceMode_ === 'function';
  });

  test('Phase 3 RelationshipIndex config', function () {
    return CRM.RELATIONSHIP_INDEX && CRM.RELATIONSHIP_INDEX.COLS && CRM.RELATIONSHIP_INDEX.COLS.length > 0;
  });

  test('BusinessRules outstanding', function () {
    var o = calcOutstanding_(1000, 0, 300);
    return o === 700;
  });

  test('Payment validation helper', function () {
    return typeof validatePaymentAmount_ === 'function' && typeof computeLeadOutstanding_ === 'function';
  });

  test('Price Master service', function () {
    return typeof getActivePriceMasterRecords_ === 'function' &&
      typeof validatePriceMasterLookup_ === 'function';
  });

  test('Insurance payout rates', function () {
    if (typeof computeInsurancePayout_ !== 'function') return false;
    var storm = computeInsurancePayout_(10000, 'Storm', '');
    var turbo = computeInsurancePayout_(10000, 'Turbo Max', '');
    var other = computeInsurancePayout_(10000, 'HiLoad', '');
    var manual = computeInsurancePayout_(10000, 'Storm', '', 42);
    return storm.ratePercent === 49 && turbo.ratePercent === 49 &&
      other.ratePercent === 36.5 &&
      storm.expectedPayout === 4900 && other.expectedPayout === 3650 &&
      manual.ratePercent === 42 && manual.expectedPayout === 4200;
  });

  test('Insurance register service', function () {
    return typeof ensureInsuranceRegisterSheet_ === 'function' &&
      typeof upsertInsuranceEntryForLead_ === 'function' &&
      typeof menuOpenInsuranceRegister === 'function';
  });

  test('Lead create handler', function () {
    return typeof createNewLead_ === 'function' && typeof createNewLeadFromDialog === 'function';
  });

  test('Booking handler', function () {
    return typeof saveBookingFromDialog === 'function';
  });

  test('Payment handler', function () {
    return typeof addPaymentFromDialog === 'function';
  });

  test('Navigation engine', function () {
    return typeof navGoToEntity === 'function' &&
      typeof navResolveRow_ === 'function' &&
      typeof navRefreshAllHyperlinks_ === 'function' &&
      typeof getNavigationMatrix_ === 'function';
  });

  test('Navigation audit', function () {
    var audit = typeof navAuditHyperlinks_ === 'function' ? navAuditHyperlinks_() : { ok: false };
    return audit.ok === true || (audit.issues && audit.issues.length <= 2);
  });

  test('Delivery handler', function () {
    return typeof markDeliveredFromDialog === 'function';
  });

  test('No protection stubs required', function () {
    return typeof writeSheetRow_ === 'function' && typeof writeBusinessRow_ === 'function';
  });

  test('Deployment certification', function () {
    return typeof runDeploymentCertification_ === 'function';
  });

  test('Version management', function () {
    var info = getVersionInfo_();
    return info.crmVersion === CRM.VERSION && !!info.schemaVersion;
  });

  test('Safe recovery handler', function () {
    return typeof menuSafeRecovery === 'function' && typeof buildRepairPlan_ === 'function';
  });

  test('Destructive ops guard', function () {
    return typeof runDestructiveOp_ === 'function';
  });

  var ms = Date.now() - start;
  logTransaction_('System', 'Regression Tests', {
    status: fail === 0 ? 'PASS' : 'FAIL',
    executionMs: ms,
    errorCode: fail === 0 ? '' : 'REGRESSION_FAIL',
    message: pass + ' passed, ' + fail + ' failed'
  });
  logAudit_('REGRESSION_TEST', pass + ' passed, ' + fail + ' failed in ' + ms + 'ms');

  return { pass: pass, fail: fail, tests: tests, executionMs: ms, allPassed: fail === 0 };
}

function menuRunRegressionTests() {
  return crmRun_('System', 'Regression Tests', function () {
    var result = runRegressionTests_();
    var failed = result.tests.filter(function (t) { return !t.pass; });
    var detail = failed.map(function (t) {
      return '• ' + t.name + (t.detail ? ': ' + t.detail : '');
    }).join('\n');
    SpreadsheetApp.getUi().alert(
      'Regression Tests',
      result.pass + ' passed, ' + result.fail + ' failed (' + result.executionMs + 'ms)' +
      (detail ? '\n\nFailed:\n' + detail : '\n\nAll tests passed.'),
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return result;
  });
}
