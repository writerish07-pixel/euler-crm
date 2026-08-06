/**
 * DashboardCertificationService – cross-check dashboard KPIs against source data.
 * Throws on mismatch so incorrect values never pass silently.
 */

/** Read numeric KPI from dashboard cell. */
function readDashboardKpi_(sheet, a1) {
  var v = sheet.getRange(a1).getValue();
  if (v === '' || v === null) return 0;
  if (typeof v === 'number') return v;
  return parseNumber_(v);
}

/** Read dashboard KPIs currently displayed on sheet. */
function readDashboardDisplayed_(dash) {
  var c = CRM.DASHBOARD.VALUE_CELLS;
  return {
    todayLeads: readDashboardKpi_(dash, c.todayLeads),
    todayFollowups: readDashboardKpi_(dash, c.todayFollowups),
    todayBookings: readDashboardKpi_(dash, c.todayBookings),
    todayDeliveries: readDashboardKpi_(dash, c.todayDeliveries),
    pendingDeliveries: readDashboardKpi_(dash, c.pendingDeliveries),
    pendingFollowups: readDashboardKpi_(dash, c.pendingFollowups),
    pendingPayments: readDashboardKpi_(dash, c.pendingPayments),
    monthlyLeads: readDashboardKpi_(dash, c.monthlyLeads),
    monthlyBookings: readDashboardKpi_(dash, c.monthlyBookings),
    monthlyDeliveries: readDashboardKpi_(dash, c.monthlyDeliveries),
    conversion: readDashboardKpi_(dash, c.conversion),
    topSource: String(dash.getRange(c.topSource).getValue() || ''),
    topModel: String(dash.getRange(c.topModel).getValue() || ''),
    revenue: readDashboardKpi_(dash, c.revenue),
    outstanding: readDashboardKpi_(dash, c.outstanding)
  };
}

/**
 * Certify dashboard values match in-memory computation.
 * @param {boolean} [throwOnFail] default true
 * @returns {{passed: boolean, mismatches: string[], expected: Object, displayed: Object}}
 */
function certifyDashboard_(throwOnFail) {
  if (throwOnFail === undefined) throwOnFail = true;
  var start = Date.now();
  invalidateCrmStore_();
  var store = loadCrmStore_(true);
  var expected = computeDashboardMetrics_(store).metrics;
  var dash = getSheet_(CRM.SHEETS.DASHBOARD);
  var displayed = readDashboardDisplayed_(dash);
  var mismatches = [];

  function cmpNum(label, exp, disp, tolerance) {
    tolerance = tolerance || 0.01;
    if (Math.abs(Number(exp) - Number(disp)) > tolerance) {
      mismatches.push(label + ': expected=' + exp + ', displayed=' + disp);
    }
  }

  cmpNum('Today Leads', expected.todayLeads, displayed.todayLeads, 0);
  cmpNum('Today Follow-ups', expected.todayFollowups, displayed.todayFollowups, 0);
  cmpNum('Today Bookings', expected.todayBookings, displayed.todayBookings, 0);
  cmpNum('Today Deliveries', expected.todayDeliveries, displayed.todayDeliveries, 0);
  cmpNum('Pending Deliveries', expected.pendingDeliveries, displayed.pendingDeliveries, 0);
  cmpNum('Pending Follow-ups', expected.pendingFollowups, displayed.pendingFollowups, 0);
  cmpNum('Pending Payments', expected.pendingPayments, displayed.pendingPayments, 0);
  cmpNum('Monthly Leads', expected.monthlyLeads, displayed.monthlyLeads, 0);
  cmpNum('Monthly Bookings', expected.monthlyBookings, displayed.monthlyBookings, 0);
  cmpNum('Monthly Deliveries', expected.monthlyDeliveries, displayed.monthlyDeliveries, 0);
  cmpNum('Conversion %', expected.conversion, displayed.conversion, 0.0001);
  cmpNum('Revenue', expected.revenue, displayed.revenue, 0.01);
  cmpNum('Outstanding', expected.outstanding, displayed.outstanding, 0.01);

  if (String(expected.topSource) !== String(displayed.topSource)) {
    mismatches.push('Top Source: expected=' + expected.topSource + ', displayed=' + displayed.topSource);
  }
  if (String(expected.topModel) !== String(displayed.topModel)) {
    mismatches.push('Top Model: expected=' + expected.topModel + ', displayed=' + displayed.topModel);
  }

  var recentOk = certifyRecentActivities_(store, dash);
  if (!recentOk.passed) {
    mismatches = mismatches.concat(recentOk.mismatches);
  }

  var passed = mismatches.length === 0;
  var ms = Date.now() - start;

  logTransaction_('Dashboard', 'Certification', {
    status: passed ? 'PASS' : 'FAIL',
    executionMs: ms,
    errorCode: passed ? '' : 'DASHBOARD_MISMATCH',
    message: passed ? 'All KPIs match source data' : mismatches.join('; ')
  });

  if (!passed) {
    logAudit_('DASHBOARD_CERT_FAIL', mismatches.join('\n'));
    if (throwOnFail) {
      throw new Error('Dashboard certification failed:\n' + mismatches.join('\n'));
    }
  } else {
    logAudit_('DASHBOARD_CERT_PASS', 'All KPIs verified in ' + ms + 'ms');
  }

  return { passed: passed, mismatches: mismatches, expected: expected, displayed: displayed, executionMs: ms };
}

/** Normalize dashboard cell for certification compare. */
function normalizeCertCell_(val, colIndex) {
  if (colIndex === 0) return formatDate_(val);
  return String(val === null || val === undefined ? '' : val).trim();
}

function certifyRecentActivities_(store, dash) {
  var h = store.activities.headers;
  var acts = [];
  store.activities.rows.forEach(function (row) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var lead = store.leads.byId[id];
    acts.push({
      date: formatDate_(rowVal_(row, h, 'Date')),
      leadId: id,
      customer: lead ? lead.customerName : '',
      type: String(rowVal_(row, h, 'Activity Type') || ''),
      discussion: String(rowVal_(row, h, 'Discussion') || ''),
      executive: String(rowVal_(row, h, 'Executive') || '')
    });
  });
  acts.sort(function (a, b) {
    return String(b.date).localeCompare(String(a.date));
  });
  acts = acts.slice(0, CRM.DASHBOARD.RECENT_COUNT);

  var startRow = CRM.DASHBOARD.RECENT_START_ROW;
  var colStart = CRM.DASHBOARD.RECENT_COLS.date;
  var numRows = CRM.DASHBOARD.RECENT_COUNT;
  var displayed = dash.getRange(startRow, colStart, numRows, 6).getValues();
  var mismatches = [];

  for (var i = 0; i < CRM.DASHBOARD.RECENT_COUNT; i++) {
    var exp = acts[i];
    var disp = displayed[i];
    var expRow = exp
      ? [exp.date, exp.leadId, exp.customer, exp.type, exp.discussion, exp.executive]
      : ['', '', '', '', '', ''];
    for (var c = 0; c < 6; c++) {
      if (normalizeCertCell_(expRow[c], c) !== normalizeCertCell_(disp[c], c)) {
        mismatches.push('Recent Activity row ' + (i + 1) + ' col ' + (c + 1) +
          ': expected="' + normalizeCertCell_(expRow[c], c) + '", displayed="' + normalizeCertCell_(disp[c], c) + '"');
        break;
      }
    }
  }

  return { passed: mismatches.length === 0, mismatches: mismatches };
}

/** Menu handler – refresh then certify. */
function menuCertifyDashboard() {
  return crmRun_('Dashboard', 'Certify Dashboard', function () {
    refreshDashboard_();
    var result = certifyDashboard_(true);
    showToast_('Dashboard certified – all KPIs match source data');
    return result;
  });
}
