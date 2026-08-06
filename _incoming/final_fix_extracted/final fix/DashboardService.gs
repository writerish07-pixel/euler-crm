/**
 * DashboardService – all KPIs computed in Apps Script, written as values.
 * No spreadsheet formulas on the Dashboard sheet.
 *
 * v2.2 changes:
 *   ✔ Finance Total Outstanding KPI (B35) — clickable link to Finance Pending sheet.
 *     Shows total ₹ outstanding across all open finance files (financer has not paid yet).
 *   ✔ Bifurcation section added to Finance Pending view (by Financer) — see FinanceService.gs.
 */

/**
 * FAST dashboard refresh — KPI metrics + recent activities only. No drill-down
 * sheet rebuilds, no finance-view repaints, no hyperlink work. This is what runs
 * synchronously after a dialog save (via refreshDashboardNow) so the dashboard
 * updates RELIABLY without depending on time-based triggers (which cap at 20 per
 * project and silently fail once exhausted — the reason the dashboard "never"
 * auto-updated). ~1–2s.
 */
function refreshDashboardFast_(prebuiltStore) {
  return safeRun_('refreshDashboardFast', function () {
    var store = prebuiltStore || loadCrmStore_(true);
    var debug = computeDashboardMetrics_(store, true);
    writeDashboardMetrics_(debug.metrics);
    writeRecentActivities_(store);
    return { ok: true };
  });
}

/**
 * Public, client-callable: refresh the dashboard right now and return. Called by
 * the dialogs' kickDeferredCrmRefresh() AFTER a save succeeds. Runs the fast KPI
 * refresh (reliable, no triggers), then best-effort queues the heavier cold work
 * (drill-downs, earnings, claims, views) — but the KPIs the operator watches are
 * already updated by the time this returns.
 */
function refreshDashboardNow() {
  try {
    var store = loadCrmStore_(true);
    refreshDashboardFast_(store);
  } catch (e) {
    Logger.log('refreshDashboardNow fast: ' + e.message);
  }
  try { scheduleDeferredCrmSync_({ reason: 'post_save_cold', dashboard: false }); } catch (e2) {}
  return { ok: true };
}

function refreshDashboard_(prebuiltStore) {
  return safeRun_('refreshDashboard', function () {
    var start = Date.now();
    try {
      try {
        if (typeof ensureFinanceRegisterSynced_ === 'function') ensureFinanceRegisterSynced_();
      } catch (fr) {
        Logger.log('finance register sync: ' + fr.message);
      }
      var store = prebuiltStore || loadCrmStore_(true);
      var debug = computeDashboardMetrics_(store, true);
      try { buildDashboardDrillDownGids_(store); } catch (dd) { Logger.log('dashboard drill-downs: ' + dd.message); }
      writeDashboardMetrics_(debug.metrics);
      writeRecentActivities_(store);
      try { if (typeof refreshFinancePendingView_ === 'function') refreshFinancePendingView_(); } catch (fe) {}
      try { if (typeof refreshFinanceOverdueView_ === 'function') refreshFinanceOverdueView_(); } catch (fo) {}
      var ms = Date.now() - start;
      recordPerf_('dashboard', ms);
      logAudit_('DASHBOARD_REFRESH', JSON.stringify({
        rowsRead: debug.rowsRead,
        todayLeads: debug.metrics.todayLeads,
        monthlyLeads: debug.metrics.monthlyLeads,
        revenue: debug.metrics.revenue,
        outstanding: debug.metrics.outstanding,
        financeOutstanding: debug.metrics.financeOutstanding,
        executionMs: ms
      }));
      logTransaction_('Dashboard', 'Refresh', {
        status: 'OK',
        executionMs: ms,
        message: 'KPIs updated'
      });
      try {
        if (typeof organizeSpreadsheetTabs_ === 'function') organizeSpreadsheetTabs_();
      } catch (tabErr) {
        Logger.log('organizeSpreadsheetTabs_: ' + tabErr.message);
      }
    } finally {
    }
  });
}

/**
 * Compute all dashboard KPIs from in-memory store.
 */
function computeDashboardMetrics_(store, withDebug) {

  var today = nowDate_();
  var monthStart = today.substring(0, 8) + '01';
  var h = store.leads.headers;

  var idx = {
    created: findHeaderIndex_(h, 'Created Date'),
    status: findHeaderIndex_(h, 'Current Status'),
    fu: findHeaderIndex_(h, 'Next Follow-up Date'),
    bookingDate: findHeaderIndex_(h, 'Booking Date'),
    bookingStatus: findHeaderIndex_(h, 'Booking Status'),
    source: findHeaderIndex_(h, 'Lead Source'),
    model: findHeaderIndex_(h, 'Interested Model')
  };

  if (idx.created < 0) throw new Error('Dashboard: column "Created Date" not found in Lead Register');
  if (idx.status  < 0) throw new Error('Dashboard: column "Current Status" not found in Lead Register');

  var m = {
    todayLeads: 0, todayFollowups: 0, todayBookings: 0, todayDeliveries: 0,
    pendingDeliveries: 0, pendingFollowups: 0, pendingPayments: 0,
    monthlyLeads: 0, monthlyBookings: 0, monthlyNewBookings: 0, activeBookings: 0, monthlyDeliveries: 0,
    conversion: 0, topSource: '', topModel: '', revenue: 0, outstanding: 0,
    paymentsCash: 0, paymentsUpi: 0, paymentsFinance: 0, paymentsOther: 0,
    customerOutstanding: 0, companyOutstanding: 0,
    financeOverdueCount: 0, financeOverdueAmount: 0,
    financeOutstanding: 0,   // total outstanding across ALL pending finance files
    insurancePremium: 0,
    insuranceExpected: 0,
    insuranceReceived: 0,
    insuranceOutstanding: 0
  };

  var sourceCount = {};
  var modelCount  = {};
  var statusDist  = {};
  var rowsProcessed  = 0;
  var outstandingLeads = [];
  var financeByLead = typeof getFinanceOutstandingMapByLead_ === 'function'
    ? getFinanceOutstandingMapByLead_() : {};

  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    rowsProcessed++;
    var created     = formatDate_(l.createdDate);
    var status      = normalizeStatus_(l.currentStatus);
    var fu          = formatDate_(l.nextFollowUpDate);
    var bookingDate = formatDate_(l.bookingDate);
    var del         = store.deliveryByLead[id] || {};
    var delDate     = formatDate_(del.deliveryDate);
    var isDelivered = status === 'Delivered' ||
      String(del.delivered || '').toLowerCase() === 'yes';
    var customerOs  = computeDashboardOutstanding_(id, store);
    var financeOs   = Number(financeByLead[id] || 0);
    var totalOs     = round2_(customerOs + financeOs);
    var companyOs   = typeof computeCompanyOutstanding_ === 'function' ? computeCompanyOutstanding_(id, store) : 0;
    var active      = isActiveLead_(l);

    statusDist[status || '(blank)'] = (statusDist[status || '(blank)'] || 0) + 1;

    if (created === today) m.todayLeads++;

    if (active) {
      if (fu === today) m.todayFollowups++;
      if (bookingDate === today) m.todayBookings++;
      if (delDate === today || (status === 'Delivered' && delDate === today)) m.todayDeliveries++;
      if (status !== 'Delivered' && status !== 'Lost') {
        if (fu && fu < today) m.pendingFollowups++;
        if (String(del.delivered || '').toLowerCase() !== 'yes') m.pendingDeliveries++;
      }
      if (totalOs > 0.01) {
        if (active) m.pendingPayments++;
        m.customerOutstanding += customerOs;
        m.financeOutstanding  += financeOs;
        outstandingLeads.push({
          leadId:        l.leadId,
          customerName:  l.customerName || '',
          mobile:        l.mobile || '',
          model:         l.interestedModel || '',
          variant:       l.variant || '',
          bookingAmount: Number(l.bookingAmount || 0),
          received:      Number((store.paymentsByLead && store.paymentsByLead[id]) || 0),
          customerOutstanding: customerOs,
          financeOutstanding:  financeOs,
          outstanding:   totalOs,
          status:        l.currentStatus || '',
          executive:     l.executive || '',
          sheetRow:      l.sheetRow || (store.leads.sheetRow && store.leads.sheetRow[id]) || 0
        });
      }
      m.companyOutstanding += companyOs;
      var src   = String(l.leadSource || 'Unknown').trim();
      var model = String(l.interestedModel || '').trim();
      sourceCount[src] = (sourceCount[src] || 0) + 1;
      if (model) modelCount[model] = (modelCount[model] || 0) + 1;
    }

    if (created && created >= monthStart && created <= today) m.monthlyLeads++;
    if (bookingDate && bookingDate >= monthStart && bookingDate <= today) m.monthlyNewBookings++;
    if (status === 'Booked' && bookingDate && !isDelivered) m.activeBookings++;
    if (status === 'Delivered' && delDate && delDate >= monthStart && delDate <= today) m.monthlyDeliveries++;
  });

  m.monthlyBookings = m.activeBookings;
  m.conversion = m.monthlyLeads > 0 ? m.monthlyNewBookings / m.monthlyLeads : 0;
  m.topSource  = topKey_(sourceCount);
  m.topModel   = topKey_(modelCount);
  m.revenue    = computeRevenue_(store, monthStart, today);

  var monthPayments = computePaymentsByMode_(store, monthStart, today);
  m.paymentsCash    = monthPayments.cash;
  m.paymentsUpi     = monthPayments.upi;
  m.paymentsFinance = monthPayments.finance;
  m.paymentsOther   = monthPayments.other;
  m.outstandingLeadsList = outstandingLeads;

  // Finance overdue (files past SLA after delivery)
  try {
    if (typeof listFinanceOverdueFiles_ === 'function') {
      var finOver = listFinanceOverdueFiles_();
      m.financeOverdueCount  = finOver.length;
      m.financeOverdueAmount = finOver.reduce(function (s, f) {
        return s + Number(f.fileOutstanding || 0);
      }, 0);
      m.financeOverdueList = finOver;
    }
  } catch (fe) {
    Logger.log('finance overdue metrics: ' + fe.message);
  }

  // Round aggregated outstanding buckets.
  m.customerOutstanding = round2_(m.customerOutstanding);
  try {
    if (typeof getTotalFinanceOutstanding_ === 'function') {
      m.financeOutstanding = getTotalFinanceOutstanding_();
    } else {
      m.financeOutstanding = round2_(m.financeOutstanding);
    }
  } catch (fe2) {
    m.financeOutstanding = round2_(m.financeOutstanding);
    Logger.log('finance outstanding metric: ' + fe2.message);
  }
  m.outstanding = round2_(m.customerOutstanding + m.financeOutstanding);

  try {
    if (typeof computeInsuranceDashboardMetrics_ === 'function') {
      var ins = computeInsuranceDashboardMetrics_();
      if (ins) {
        m.insurancePremium = ins.insurancePremium;
        m.insuranceExpected = ins.insuranceExpected;
        m.insuranceReceived = ins.insuranceReceived;
        m.insuranceOutstanding = ins.insuranceOutstanding;
      }
    }
  } catch (insErr) {
    Logger.log('insurance metrics: ' + insErr.message);
  }

  try {
    m.modelPerformance = computeModelPerformance_(store, financeByLead);
  } catch (mpErr) {
    m.modelPerformance = [];
    Logger.log('model performance metrics: ' + mpErr.message);
  }

  if (withDebug) {
    logAudit_('DASHBOARD_DEBUG', [
      'today=' + today,
      'monthStart=' + monthStart,
      'rowsProcessed=' + rowsProcessed,
      'paymentRows=' + store.payments.rows.length,
      'todayLeads=' + m.todayLeads,
      'todayBookings=' + m.todayBookings,
      'todayFollowups=' + m.todayFollowups,
      'todayDeliveries=' + m.todayDeliveries,
      'pendingDeliveries=' + m.pendingDeliveries,
      'pendingPayments=' + m.pendingPayments,
      'monthlyLeads=' + m.monthlyLeads,
      'revenue=' + m.revenue,
      'outstanding=' + m.outstanding,
      'financeOutstanding=' + m.financeOutstanding,
      'statusDist=' + JSON.stringify(statusDist)
    ].join(' | '));
    return { metrics: m, rowsRead: rowsProcessed, statusDist: statusDist };
  }
  return { metrics: m };
}

/**
 * Company share board — active bookings + retail (deliveries) for current month.
 * Safe for GitHub Pages: no mobiles, no outstanding, no finance details.
 */
function getShareDashboard_() {
  var store = loadCrmStore_(true);
  var today = nowDate_();
  var monthStart = today.substring(0, 8) + '01';
  var monthLabel = '';
  try {
    var parts = today.split('-');
    var months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
    var mi = Number(parts[1] || 1) - 1;
    monthLabel = (months[mi] || '') + ' ' + (parts[0] || '');
  } catch (eL) {
    monthLabel = today.substring(0, 7);
  }

  var settings = typeof getSettings_ === 'function' ? getSettings_() : {};
  var companyName = String((settings && settings.companyName) || 'Euler Motors').trim() || 'Euler Motors';

  var bookings = [];
  var retails = [];
  var todayBookings = 0;
  var todayRetails = 0;
  var monthlyNewBookings = 0;
  var modelBook = {};
  var modelRetail = {};

  Object.keys(store.leads.byId || {}).forEach(function (id) {
    var l = store.leads.byId[id];
    var bookingDate = formatDate_(l.bookingDate);
    var status = normalizeStatus_(l.currentStatus);
    var del = store.deliveryByLead[id] || {};
    var delDate = formatDate_(del.deliveryDate);
    var model = String(l.interestedModel || '').trim();
    var variant = String(l.variant || '').trim();
    var name = String(l.customerName || '').trim();
    var exec = String(l.executive || '').trim();
    var isDelivered = status === 'Delivered' ||
      String(del.delivered || '').toLowerCase() === 'yes';

    if (bookingDate && bookingDate >= monthStart && bookingDate <= today) {
      monthlyNewBookings++;
      if (bookingDate === today) todayBookings++;
    }

    if (status === 'Booked' && bookingDate && !isDelivered) {
      bookings.push({
        leadId: l.leadId,
        customerName: name,
        model: model,
        variant: variant,
        bookingDate: bookingDate,
        executive: exec,
        status: status,
        isNewThisMonth: !!(bookingDate >= monthStart && bookingDate <= today)
      });
      if (model) modelBook[model] = (modelBook[model] || 0) + 1;
    }

    var isRetail = (status === 'Delivered' && delDate && delDate >= monthStart && delDate <= today) ||
      (String(del.delivered || '').toLowerCase() === 'yes' && delDate && delDate >= monthStart && delDate <= today);
    if (isRetail) {
      retails.push({
        leadId: l.leadId,
        customerName: name,
        model: model,
        variant: variant,
        deliveryDate: delDate,
        executive: exec
      });
      if (model) modelRetail[model] = (modelRetail[model] || 0) + 1;
      if (delDate === today) todayRetails++;
    }
  });

  function sortByDateDesc(a, b, key) {
    var da = String(a[key] || '');
    var db = String(b[key] || '');
    return da < db ? 1 : da > db ? -1 : 0;
  }
  bookings.sort(function (a, b) { return sortByDateDesc(a, b, 'bookingDate'); });
  retails.sort(function (a, b) { return sortByDateDesc(a, b, 'deliveryDate'); });

  function topModels(map) {
    return Object.keys(map).map(function (k) {
      return { model: k, count: map[k] };
    }).sort(function (a, b) { return b.count - a.count; }).slice(0, 6);
  }

  return {
    companyName: companyName,
    monthLabel: monthLabel,
    monthStart: monthStart,
    today: today,
    generatedAt: nowDateTime_(),
    todayBookings: todayBookings,
    todayRetail: todayRetails,
    monthlyBookings: monthlyNewBookings,
    activeBookings: bookings.length,
    monthlyRetail: retails.length,
    bookings: bookings,
    retails: retails,
    topBookingModels: topModels(modelBook),
    topRetailModels: topModels(modelRetail)
  };
}

function computeRevenue_(store, monthStart, monthEnd) {
  return computePaymentsByMode_(store, monthStart, monthEnd).total;
}

/** Payment Ledger date — canonical column is Date (legacy alias: Payment Date). */
function paymentLedgerDate_(row, headers) {
  return formatDate_(rowVal_(row, headers, 'Date') || rowVal_(row, headers, 'Payment Date'));
}

/**
 * Bucket Payment Mode into Cash / UPI / Finance / Other.
 * Same rules for Dashboard totals AND drill-down sheets (must not diverge).
 */
function paymentModeBucket_(mode) {
  var norm = matchMasterValue_(String(mode || '').trim(), ['Cash', 'UPI', 'Finance']) || '';
  if (norm === 'Cash') return 'cash';
  if (norm === 'UPI') return 'upi';
  if (norm === 'Finance') return 'finance';
  return 'other';
}

/** Aggregate payment ledger amounts by mode (Cash / UPI / Finance / Other). */
function computePaymentsByMode_(store, dateStart, dateEnd) {
  var out = { total: 0, cash: 0, upi: 0, finance: 0, other: 0 };
  var h = store.payments.headers;
  var amtIdx = findHeaderIndex_(h, 'Amount');
  var modeIdx = findHeaderIndex_(h, 'Payment Mode');
  if (amtIdx < 0) return out;

  store.payments.rows.forEach(function (row) {
    var d = paymentLedgerDate_(row, h);
    if (!d || d < dateStart || d > dateEnd) return;
    var amt = parseNumber_(row[amtIdx]);
    out.total += amt;
    var bucket = paymentModeBucket_(modeIdx >= 0 ? row[modeIdx] : '');
    out[bucket] += amt;
  });
  return out;
}

/**
 * Ensure Dashboard payment/finance label rows are present.
 * Row layout (A column):
 *   A26 = PAYMENTS (MONTH)  A27 = Cash  A28 = UPI  A29 = Finance  A30 = Other
 *   A31 = Outstanding (Customer)  A32 = Customer Outstanding  A33 = Company Outstanding
 *   A34 = Finance Overdue  A35 = Finance Total Outstanding
 *   A36 = INSURANCE  A37 = Premium  A38 = Expected Payout  A39 = Received  A40 = Payout OS
 *   A42 = MODEL PERFORMANCE (dynamic table from row 43)
 */
function ensureDashboardPaymentLabels_(dash) {
  dash = dash || getSheet_(CRM.SHEETS.DASHBOARD);

  // Clear stale old layout artefacts.
  var a25 = String(dash.getRange('A25').getValue() || '').toLowerCase();
  if (a25.indexOf('outstanding') >= 0) {
    dash.getRange('A25').setValue('');
    dash.getRange('B25').clearContent();
  }
  dash.getRange('B26').clearContent();

  dash.getRange('A26').setValue('PAYMENTS (MONTH)').setFontWeight('bold');
  dash.getRange('A27').setValue('Cash').setFontWeight('bold');
  dash.getRange('A28').setValue('UPI').setFontWeight('bold');
  dash.getRange('A29').setValue('Finance').setFontWeight('bold');
  dash.getRange('A30').setValue('Other').setFontWeight('bold');
  dash.getRange('A31').setValue('Total Outstanding (Customer + Finance)').setFontWeight('bold');
  dash.getRange('A32').setValue('— Customer Outstanding (customer pays)').setFontWeight('bold');
  dash.getRange('A33').setValue('Company Outstanding (OEM schemes)').setFontWeight('bold');
  dash.getRange('A34').setValue('Finance Overdue (past delivery SLA)').setFontWeight('bold');
  dash.getRange('A35').setValue('— Finance Outstanding (financer pays)').setFontWeight('bold');
  dash.getRange('A36').setValue('INSURANCE (PAYOUT)').setFontWeight('bold');
  dash.getRange('A37').setValue('— Insurance Premium Total').setFontWeight('bold');
  dash.getRange('A38').setValue('— Expected Insurer Payout').setFontWeight('bold');
  dash.getRange('A39').setValue('— Received from Insurer').setFontWeight('bold');
  dash.getRange('A40').setValue('— Payout Outstanding').setFontWeight('bold');
  dash.getRange('A41').setValue('').clearNote();
  dash.getRange('A42').setValue('MODEL PERFORMANCE').setFontWeight('bold').setFontSize(12);

  dash.getRange('B24').setNumberFormat('#,##0');
  dash.getRange('B27:B35').setNumberFormat('#,##0');
  dash.getRange('B37:B40').setNumberFormat('#,##0');
}

/** Write KPI values directly to Dashboard sheet (no formulas except hyperlinks). */
function writeDashboardMetrics_(m) {
  var dash      = getSheet_(CRM.SHEETS.DASHBOARD);
  var dataSheet = getSheet_(CRM.SHEETS.DASHBOARD_DATA);
  var cells     = CRM.DASHBOARD.VALUE_CELLS;

  ensureDashboardPaymentLabels_(dash);

  dash.getRange(cells.lastUpdated).setValue(nowDateTime_());

  var drill = typeof getDashboardDrillDownGids_ === 'function' ? getDashboardDrillDownGids_() : {};

  function kpiLink(cellKey, value, gidKey, label) {
    var gid = drill[gidKey];
    if (gid && cells[cellKey]) {
      dash.getRange(cells[cellKey]).setFormula(
        typeof navDrillDownLink_ === 'function' ? navDrillDownLink_(gid, value, label || value) : value);
    } else if (cells[cellKey]) {
      dash.getRange(cells[cellKey]).setValue(value);
    }
  }

  kpiLink('todayLeads', m.todayLeads, 'todayLeads', m.todayLeads);
  kpiLink('todayFollowups', m.todayFollowups, 'todayFollowups', m.todayFollowups);
  kpiLink('todayBookings', m.todayBookings, 'todayBookings', m.todayBookings);
  kpiLink('todayDeliveries', m.todayDeliveries, 'todayDeliveries', m.todayDeliveries);
  kpiLink('pendingDeliveries', m.pendingDeliveries, 'pendingDeliveries', m.pendingDeliveries);
  kpiLink('pendingFollowups', m.pendingFollowups, 'pendingFollowups', m.pendingFollowups);
  kpiLink('pendingPayments', m.pendingPayments, 'pendingPayments', m.pendingPayments);
  kpiLink('monthlyLeads', m.monthlyLeads, 'monthlyLeads', m.monthlyLeads);
  kpiLink('monthlyBookings', m.monthlyBookings, 'monthlyBookings', m.monthlyBookings);
  kpiLink('monthlyDeliveries', m.monthlyDeliveries, 'monthlyDeliveries', m.monthlyDeliveries);
  kpiLink('revenue', m.revenue, 'revenue', m.revenue);

  dash.getRange(cells.conversion).setValue(m.conversion);
  dash.getRange(cells.topSource).setValue(m.topSource);
  dash.getRange(cells.topModel).setValue(m.topModel);

  if (cells.paymentsCash) {
    var cashGid = drill.paymentsCash;
    if (cashGid) dash.getRange(cells.paymentsCash).setFormula(navDrillDownLink_(cashGid, m.paymentsCash || 0));
    else dash.getRange(cells.paymentsCash).setValue(m.paymentsCash || 0);
  }
  if (cells.paymentsUpi) {
    var upiGid = drill.paymentsUpi;
    if (upiGid) dash.getRange(cells.paymentsUpi).setFormula(navDrillDownLink_(upiGid, m.paymentsUpi || 0));
    else dash.getRange(cells.paymentsUpi).setValue(m.paymentsUpi || 0);
  }
  if (cells.paymentsFinance) {
    var finGid = drill.paymentsFinance;
    if (finGid) dash.getRange(cells.paymentsFinance).setFormula(navDrillDownLink_(finGid, m.paymentsFinance || 0));
    else dash.getRange(cells.paymentsFinance).setValue(m.paymentsFinance || 0);
  }
  if (cells.paymentsOther) {
    var othGid = drill.paymentsOther;
    if (othGid) dash.getRange(cells.paymentsOther).setFormula(navDrillDownLink_(othGid, m.paymentsOther || 0));
    else dash.getRange(cells.paymentsOther).setValue(m.paymentsOther || 0);
  }

  var osGid = writeOutstandingLeadsView_(m.outstandingLeadsList || []);
  if (osGid && cells.pendingPayments) {
    dash.getRange(cells.pendingPayments).setFormula(navDrillDownLink_(osGid, m.pendingPayments || 0));
  }
  if (osGid !== null && osGid !== undefined) {
    dash.getRange(cells.outstanding).setFormula(navDrillDownLink_(osGid, m.outstanding || 0));
  } else {
    dash.getRange(cells.outstanding).setValue(m.outstanding);
  }
  if (cells.customerOutstanding) {
    var custOsGid = drill.customerOutstanding || osGid;
    if (custOsGid) dash.getRange(cells.customerOutstanding).setFormula(navDrillDownLink_(custOsGid, m.customerOutstanding || 0));
    else dash.getRange(cells.customerOutstanding).setValue(Number(m.customerOutstanding || 0));
  }
  if (cells.companyOutstanding)  dash.getRange(cells.companyOutstanding).setValue(m.companyOutstanding  || 0);

  // Finance Overdue KPI (B34) — clickable to Finance Overdue sheet.
  if (cells.financeOverdue) {
    var foCount = Number(m.financeOverdueCount || 0);
    var foAmt   = Number(m.financeOverdueAmount || 0);
    var foView  = null;
    try { if (typeof refreshFinanceOverdueView_ === 'function') foView = refreshFinanceOverdueView_(); } catch (foe) {}
    var foGid   = foView && foView.gid != null ? foView.gid : null;
    if (!foGid) {
      try {
        var foSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.FINANCE_OVERDUE || 'Finance Overdue');
        if (foSheet) foGid = foSheet.getSheetId();
      } catch (e2) {}
    }
    var foLabel = foCount + (foAmt > 0 ? ' (₹' + Math.round(foAmt).toLocaleString('en-IN') + ')' : '');
    if (foGid != null) {
      dash.getRange(cells.financeOverdue).setFormula(navDrillDownLink_(foGid, foLabel, foLabel));
    } else {
      dash.getRange(cells.financeOverdue).setValue(foCount);
    }
  }

  // Finance Total Outstanding KPI (B35) — clickable to Finance Pending sheet.
  if (cells.financeOutstanding) {
    var fpOs    = Number(m.financeOutstanding || 0);
    var fpGid   = null;
    try {
      var fpSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.FINANCE_PENDING || 'Finance Pending');
      if (fpSheet) fpGid = fpSheet.getSheetId();
    } catch (e3) {}
    var fpLabel = '₹' + Math.round(fpOs).toLocaleString('en-IN');
    if (fpGid != null) {
      dash.getRange(cells.financeOutstanding).setFormula(navDrillDownLink_(fpGid, fpLabel, fpLabel));
    } else {
      dash.getRange(cells.financeOutstanding).setValue(fpOs);
    }
  }

  // Insurance payout KPIs (B37–B40) — clickable to Insurance Register.
  var insGid = null;
  try {
    if (typeof ensureInsuranceRegisterSheet_ === 'function') ensureInsuranceRegisterSheet_();
    var insSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.INSURANCE_REGISTER);
    if (insSheet) insGid = insSheet.getSheetId();
  } catch (eIns) {}
  function writeInsKpi(key, value) {
    if (!cells[key]) return;
    var n = Number(value || 0);
    var label = '₹' + Math.round(n).toLocaleString('en-IN');
    if (insGid != null && typeof navDrillDownLink_ === 'function') {
      dash.getRange(cells[key]).setFormula(navDrillDownLink_(insGid, label, label));
    } else {
      dash.getRange(cells[key]).setValue(n);
    }
  }
  writeInsKpi('insurancePremium', m.insurancePremium);
  writeInsKpi('insuranceExpected', m.insuranceExpected);
  writeInsKpi('insuranceReceived', m.insuranceReceived);
  writeInsKpi('insuranceOutstanding', m.insuranceOutstanding);

  try {
    writeModelPerformanceSection_(dash, m.modelPerformance || [], drill);
  } catch (mpWriteErr) {
    Logger.log('writeModelPerformanceSection_: ' + mpWriteErr.message);
  }

  try {
    if (typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_()) {
      if (typeof rebuildDealerEarningsAnalytics_ === 'function') {
        try { rebuildDealerEarningsAnalytics_(); } catch (eA) {}
      }
      var deMetrics = typeof computeDealerEarningsDashboardMetrics_ === 'function'
        ? computeDealerEarningsDashboardMetrics_() : null;
      if (typeof writeDealerEarningsDashboardSection_ === 'function') {
        writeDealerEarningsDashboardSection_(dash, deMetrics, drill.dealerEarnings || {});
      }
    }
  } catch (deWriteErr) {
    Logger.log('writeDealerEarningsDashboardSection_: ' + deWriteErr.message);
  }

  // Mirror to hidden Dashboard Data for audit/backup.
  var mirror = CRM.DASHBOARD.MIRROR_CELLS;
  dataSheet.getRange(mirror.lastUpdated).setValue(nowDateTime_());
  dataSheet.getRange(mirror.todayLeads).setValue(m.todayLeads);
  dataSheet.getRange(mirror.todayFollowups).setValue(m.todayFollowups);
  dataSheet.getRange(mirror.todayBookings).setValue(m.todayBookings);
  dataSheet.getRange(mirror.todayDeliveries).setValue(m.todayDeliveries);
  dataSheet.getRange(mirror.pendingDeliveries).setValue(m.pendingDeliveries);
  dataSheet.getRange(mirror.pendingFollowups).setValue(m.pendingFollowups);
  dataSheet.getRange(mirror.pendingPayments).setValue(m.pendingPayments);
  dataSheet.getRange(mirror.monthlyLeads).setValue(m.monthlyLeads);
  dataSheet.getRange(mirror.monthlyBookings).setValue(m.monthlyBookings);
  dataSheet.getRange(mirror.monthlyDeliveries).setValue(m.monthlyDeliveries);
  dataSheet.getRange(mirror.conversion).setValue(m.conversion);
  dataSheet.getRange(mirror.topSource).setValue(m.topSource);
  dataSheet.getRange(mirror.topModel).setValue(m.topModel);
  dataSheet.getRange(mirror.revenue).setValue(m.revenue);
  if (mirror.paymentsCash)    dataSheet.getRange(mirror.paymentsCash).setValue(m.paymentsCash    || 0);
  if (mirror.paymentsUpi)     dataSheet.getRange(mirror.paymentsUpi).setValue(m.paymentsUpi      || 0);
  if (mirror.paymentsFinance) dataSheet.getRange(mirror.paymentsFinance).setValue(m.paymentsFinance || 0);
  if (mirror.paymentsOther)   dataSheet.getRange(mirror.paymentsOther).setValue(m.paymentsOther  || 0);
  dataSheet.getRange(mirror.outstanding).setValue(m.outstanding);
  if (mirror.customerOutstanding) dataSheet.getRange(mirror.customerOutstanding).setValue(m.customerOutstanding || 0);
  if (mirror.companyOutstanding)  dataSheet.getRange(mirror.companyOutstanding).setValue(m.companyOutstanding  || 0);
  if (mirror.financeOverdue)      dataSheet.getRange(mirror.financeOverdue).setValue(m.financeOverdueCount || 0);
  if (mirror.financeOutstanding)  dataSheet.getRange(mirror.financeOutstanding).setValue(m.financeOutstanding  || 0);
  if (mirror.insurancePremium)    dataSheet.getRange(mirror.insurancePremium).setValue(m.insurancePremium || 0);
  if (mirror.insuranceExpected)   dataSheet.getRange(mirror.insuranceExpected).setValue(m.insuranceExpected || 0);
  if (mirror.insuranceReceived)   dataSheet.getRange(mirror.insuranceReceived).setValue(m.insuranceReceived || 0);
  if (mirror.insuranceOutstanding) dataSheet.getRange(mirror.insuranceOutstanding).setValue(m.insuranceOutstanding || 0);
}

/**
 * Build/refresh the "Outstanding Leads" drill-down sheet.
 * @return {number|null} sheet gid for Dashboard hyperlink.
 */
function writeOutstandingLeadsView_(outstandingLeads) {
  try {
    var ss   = getSpreadsheet_();
    var name = 'Outstanding Leads';
    var sheet = ss.getSheetByName(name);
    if (!sheet) sheet = ss.insertSheet(name);
    sheet.clear();

    var leadReg    = ss.getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    var leadRegGid = leadReg ? leadReg.getSheetId() : null;

    var headers = ['Lead ID', 'Customer', 'Mobile', 'Model', 'Variant',
      'Booking Amount', 'Received', 'Customer OS', 'Finance OS', 'Total OS', 'Status', 'Executive'];
    sheet.getRange(1, 1, 1, 1).setValue('Outstanding Leads — click a Lead ID to open it in the Lead Register')
      .setFontWeight('bold').setFontSize(12);
    sheet.getRange(2, 1).setValue('Refreshed: ' + nowDateTime_());
    var headerRow = 3;
    sheet.getRange(headerRow, 1, 1, headers.length).setValues([headers]).setFontWeight('bold');
    sheet.setFrozenRows(headerRow);

    var list = (outstandingLeads || []).slice().sort(function (a, b) {
      return Number(b.outstanding) - Number(a.outstanding);
    });

    if (!list.length) {
      sheet.getRange(headerRow + 1, 1).setValue('No leads currently have an outstanding balance.');
      if (typeof hideDrillDownSheet_ === 'function') hideDrillDownSheet_(name);
      return sheet.getSheetId();
    }

    var values = list.map(function (o) {
      var idCell = (typeof navEntityLink_ === 'function')
        ? navEntityLink_('Lead', o.leadId, o.leadId)
        : ((leadRegGid !== null && o.sheetRow)
          ? '=HYPERLINK("#gid=' + leadRegGid + '&range=A' + o.sheetRow + '","' + o.leadId + '")'
          : o.leadId);
      return [idCell, o.customerName, o.mobile, o.model, o.variant,
        o.bookingAmount, o.received,
        Number(o.customerOutstanding || 0),
        Number(o.financeOutstanding || 0),
        o.outstanding, o.status, o.executive];
    });

    sheet.getRange(headerRow + 1, 1, values.length, headers.length).setValues(values);

    var totalRow = headerRow + 1 + values.length;
    sheet.getRange(totalRow, 1).setValue('TOTAL (' + values.length + ' leads)').setFontWeight('bold');
    var totalCustomer = list.reduce(function (s, o) { return s + Number(o.customerOutstanding || 0); }, 0);
    var totalFinance  = list.reduce(function (s, o) { return s + Number(o.financeOutstanding || 0); }, 0);
    var totalOutstanding = list.reduce(function (s, o) { return s + Number(o.outstanding || 0); }, 0);
    sheet.getRange(totalRow, 8).setValue(totalCustomer).setFontWeight('bold');
    sheet.getRange(totalRow, 9).setValue(totalFinance).setFontWeight('bold');
    sheet.getRange(totalRow, 10).setValue(totalOutstanding).setFontWeight('bold');

    sheet.autoResizeColumns(1, headers.length);
    if (typeof hideDrillDownSheet_ === 'function') hideDrillDownSheet_(name);
    return sheet.getSheetId();
  } catch (e) {
    Logger.log('writeOutstandingLeadsView_ failed: ' + e.message);
    return null;
  }
}

function writeRecentActivities_(store) {
  var h    = store.activities.headers;
  var acts = [];
  store.activities.rows.forEach(function (row) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var lead = store.leads.byId[id];
    acts.push({
      date:       rowVal_(row, h, 'Date'),
      leadId:     id,
      customer:   lead ? lead.customerName : '',
      type:       rowVal_(row, h, 'Activity Type'),
      discussion: rowVal_(row, h, 'Discussion'),
      executive:  rowVal_(row, h, 'Executive')
    });
  });
  acts.sort(function (a, b) {
    return String(formatDate_(b.date)).localeCompare(String(formatDate_(a.date)));
  });
  acts = acts.slice(0, CRM.DASHBOARD.RECENT_COUNT);

  var dataSheet = getSheet_(CRM.SHEETS.DASHBOARD_DATA);
  dataSheet.getRange(CRM.DASHBOARD.RECENT_DATA_START_ROW, 1, CRM.DASHBOARD.RECENT_COUNT, 6).clearContent();
  if (acts.length > 0) {
    var rows = acts.map(function (a) {
      return [formatDate_(a.date), a.leadId, a.customer, a.type, a.discussion, a.executive];
    });
    dataSheet.getRange(CRM.DASHBOARD.RECENT_DATA_START_ROW, 1, rows.length, 6).setValues(rows);
  }

  var dash     = getSheet_(CRM.SHEETS.DASHBOARD);
  var startRow = CRM.DASHBOARD.RECENT_START_ROW;
  var colStart = CRM.DASHBOARD.RECENT_COLS.date;
  var numRows  = CRM.DASHBOARD.RECENT_COUNT;
  var table    = [];
  for (var i = 0; i < numRows; i++) {
    var a = acts[i];
    var leadCell = a && typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', a.leadId, a.leadId) : (a ? a.leadId : '');
    table.push([
      a ? formatDate_(a.date) : '',
      leadCell,
      a ? a.customer          : '',
      a ? a.type              : '',
      a ? a.discussion        : '',
      a ? a.executive         : ''
    ]);
  }
  dash.getRange(startRow, colStart, numRows, numCols_()).setValues(table);
}

var DASHBOARD_DRILL_GIDS_ = {};

function getDashboardDrillDownGids_() {
  return DASHBOARD_DRILL_GIDS_ || {};
}

/** Build drill-down sheets for every major Dashboard KPI. */
function buildDashboardDrillDownGids_(store) {
  store = store || loadCrmStore_(true);
  var today = nowDate_();
  var monthStart = today.substring(0, 8) + '01';
  var gids = {};

  function leadRow(l) {
    return [
      typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', l.leadId, l.leadId) : l.leadId,
      l.customerName || '', l.mobile || '', l.interestedModel || '', l.currentStatus || '', l.executive || ''
    ];
  }

  var todayLeads = [], todayBookings = [], todayDeliveries = [], pendingDel = [], pendingFu = [];
  var monthlyLeads = [], monthlyBookings = [], monthlyDeliveries = [];
  var monthPayments = { cash: [], upi: [], finance: [], other: [] };

  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    var created = formatDate_(l.createdDate);
    var bookingDate = formatDate_(l.bookingDate);
    var fu = formatDate_(l.nextFollowUpDate);
    var status = normalizeStatus_(l.currentStatus);
    var del = store.deliveryByLead[id] || {};
    var delDate = formatDate_(del.deliveryDate);
    var isDelivered = status === 'Delivered' ||
      String(del.delivered || '').toLowerCase() === 'yes';
    var row = leadRow(l);
    if (created === today) todayLeads.push(row);
    if (bookingDate === today) todayBookings.push(row);
    if (delDate === today || (status === 'Delivered' && delDate === today)) todayDeliveries.push(row);
    if (isActiveLead_(l) && status !== 'Delivered' && status !== 'Lost' && String(del.delivered || '').toLowerCase() !== 'yes') {
      pendingDel.push(row);
    }
    if (isActiveLead_(l) && status !== 'Delivered' && status !== 'Lost' && fu && fu < today) pendingFu.push(row);
    if (created && created >= monthStart && created <= today) monthlyLeads.push(row);
    if (status === 'Booked' && bookingDate && !isDelivered) monthlyBookings.push(row);
    if (status === 'Delivered' && delDate && delDate >= monthStart && delDate <= today) monthlyDeliveries.push(row);
  });

  var ph = store.payments.headers;
  store.payments.rows.forEach(function (r) {
    // Must use Date (same as computePaymentsByMode_) — Payment Date does not exist on ledger
    var pDate = paymentLedgerDate_(r, ph);
    if (!pDate || pDate < monthStart || pDate > today) return;
    var lid = String(rowVal_(r, ph, 'Lead ID')).trim();
    var rcpt = String(rowVal_(r, ph, 'Receipt Number')).trim();
    var modeRaw = rowVal_(r, ph, 'Payment Mode');
    var bucket = paymentModeBucket_(modeRaw);
    var row = [
      typeof navEntityLink_ === 'function' ? navEntityLink_('Payment', rcpt, rcpt) : rcpt,
      typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', lid, lid) : lid,
      rowVal_(r, ph, 'Customer Name'), pDate, rowVal_(r, ph, 'Amount'), modeRaw
    ];
    monthPayments[bucket].push(row);
  });

  var hdr = ['Lead ID', 'Customer', 'Mobile', 'Model', 'Status', 'Executive'];
  var payHdr = ['Receipt', 'Lead ID', 'Customer', 'Date', 'Amount', 'Mode'];
  gids.todayLeads = navWriteDrillDownSheet_("Today's Leads", hdr, todayLeads);
  gids.todayBookings = navWriteDrillDownSheet_("Today's Bookings", hdr, todayBookings);
  gids.todayDeliveries = navWriteDrillDownSheet_("Today's Deliveries", hdr, todayDeliveries);
  gids.pendingDeliveries = navWriteDrillDownSheet_('Pending Deliveries', hdr, pendingDel);
  gids.pendingFollowups = navWriteDrillDownSheet_('Pending Follow-ups', hdr, pendingFu);
  gids.monthlyLeads = navWriteDrillDownSheet_('Monthly Leads', hdr, monthlyLeads);
  gids.monthlyBookings = navWriteDrillDownSheet_('Active Bookings', hdr, monthlyBookings);
  gids.monthlyDeliveries = navWriteDrillDownSheet_('Monthly Deliveries', hdr, monthlyDeliveries);
  gids.revenue = navWriteDrillDownSheet_('Monthly Payments', payHdr,
    monthPayments.cash.concat(monthPayments.upi, monthPayments.finance, monthPayments.other));
  gids.paymentsCash = navWriteDrillDownSheet_('Payments — Cash (Month)', payHdr, monthPayments.cash);
  gids.paymentsUpi = navWriteDrillDownSheet_('Payments — UPI (Month)', payHdr, monthPayments.upi);
  gids.paymentsFinance = navWriteDrillDownSheet_('Payments — Finance (Month)', payHdr, monthPayments.finance);
  gids.paymentsOther = navWriteDrillDownSheet_('Payments — Other (Month)', payHdr, monthPayments.other);

  var todayFu = [];
  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    if (formatDate_(l.nextFollowUpDate) === today && isActiveLead_(l)) todayFu.push(leadRow(l));
  });
  gids.todayFollowups = navWriteDrillDownSheet_("Today's Follow-ups", hdr, todayFu);

  try {
    buildModelPerformanceDrillDowns_(store, gids);
  } catch (mpDd) {
    Logger.log('model performance drill-downs: ' + mpDd.message);
  }

  try {
    if (typeof buildDealerEarningsDrillDowns_ === 'function') {
      buildDealerEarningsDrillDowns_(gids);
    }
  } catch (deDd) {
    Logger.log('dealer earnings drill-downs: ' + deDd.message);
  }

  DASHBOARD_DRILL_GIDS_ = gids;
  return gids;
}

function numCols_() { return 6; }

function topKey_(obj) {
  var max = 0, key = '';
  Object.keys(obj).forEach(function (k) {
    if (obj[k] > max) { max = obj[k]; key = k; }
  });
  return key;
}

// ═══════════════════════════════════════════════════════════════════════════
//  MODEL PERFORMANCE (dynamic — Price Master ∪ Lead models)
// ═══════════════════════════════════════════════════════════════════════════

/** Canonical model list: active Price Master models + any model present on leads. */
function getDashboardModelList_(store) {
  var map = {};
  try {
    if (typeof getPricingRows_ === 'function' && typeof parsePricingRow_ === 'function') {
      var pricing = getPricingRows_();
      pricing.rows.forEach(function (row, i) {
        var rec = parsePricingRow_(pricing.headers, row, pricing.dataStart + i);
        if (!rec || !rec.model) return;
        if (String(rec.status || '').toLowerCase() === 'inactive') return;
        map[rec.model] = true;
      });
    }
  } catch (e) {
    Logger.log('getDashboardModelList_ price master: ' + e.message);
  }
  Object.keys((store && store.leads && store.leads.byId) || {}).forEach(function (id) {
    var m = String(store.leads.byId[id].interestedModel || '').trim();
    if (m) map[m] = true;
  });
  return Object.keys(map).sort(function (a, b) {
    return a.toLowerCase().localeCompare(b.toLowerCase());
  });
}

function modelKeyMatch_(leadModel, targetModel) {
  return String(leadModel || '').trim().toLowerCase() === String(targetModel || '').trim().toLowerCase();
}

function modelPerfSheetTitle_(model, metric) {
  return ('MP — ' + String(model || '').trim() + ' — ' + metric).substring(0, 90);
}

function modelPerfLeadRow_(l, store, financeByLead) {
  var id = l.leadId;
  var customerOs = typeof computeDashboardOutstanding_ === 'function'
    ? computeDashboardOutstanding_(id, store) : 0;
  var financeOs = Number((financeByLead && financeByLead[id]) || 0);
  return [
    typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', id, id) : id,
    l.customerName || '',
    l.mobile || '',
    l.interestedModel || '',
    l.variant || '',
    l.currentStatus || '',
    l.executive || '',
    round2_(customerOs),
    round2_(financeOs)
  ];
}

/** Aggregate Extra Income by model (from Extra Income Register ↔ Lead model). */
function getExtraIncomeByModelMap_(store) {
  var byModel = {};
  if (typeof readAllExtraIncomeRows_ !== 'function') return byModel;
  try {
    readAllExtraIncomeRows_().forEach(function (r) {
      var model = '';
      var lead = store.leads.byId[r.leadId];
      if (lead) model = String(lead.interestedModel || '').trim();
      if (!model && r.vehicle) {
        model = String(r.vehicle || '').trim().split(/\s+/)[0] || '';
      }
      if (!model) model = 'Unknown';
      byModel[model] = (byModel[model] || 0) + Number(r.totalExtraIncome || 0);
    });
  } catch (e) {
    Logger.log('getExtraIncomeByModelMap_: ' + e.message);
  }
  Object.keys(byModel).forEach(function (k) {
    byModel[k] = round2_(byModel[k]);
  });
  return byModel;
}

/**
 * Per-model KPI bag used by Dashboard MODEL PERFORMANCE + filtered drill-downs.
 * Uses existing Commercial / Outstanding / Finance engines — no duplicate math.
 */
function computeModelPerformance_(store, financeByLead) {
  store = store || loadCrmStore_();
  financeByLead = financeByLead || (typeof getFinanceOutstandingMapByLead_ === 'function'
    ? getFinanceOutstandingMapByLead_() : {});
  var models = getDashboardModelList_(store);
  var extraByModel = {};
  var owner = typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_();
  if (owner) extraByModel = getExtraIncomeByModelMap_(store);

  var buckets = {};
  models.forEach(function (model) {
    buckets[model] = {
      model: model,
      leads: 0,
      bookings: 0,
      deliveries: 0,
      pendingDeliveries: 0,
      cancelled: 0,
      customerOutstanding: 0,
      financeAmount: 0,
      revenue: 0,
      extraIncome: owner ? Number(extraByModel[model] || 0) : null,
      bookingConversion: 0,
      deliveryConversion: 0,
      leadIds: { leads: [], bookings: [], deliveries: [], pending: [], cancelled: [], outstanding: [] }
    };
  });

  // Lifetime revenue by lead (all payments) — model performance is not month-scoped.
  var paidByLead = store.paymentsByLead || {};

  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    var model = String(l.interestedModel || '').trim();
    if (!model) return;
    // Ensure orphan models still appear
    if (!buckets[model]) {
      var matched = null;
      Object.keys(buckets).forEach(function (k) {
        if (modelKeyMatch_(model, k)) matched = k;
      });
      if (matched) model = matched;
      else {
        buckets[model] = {
          model: model, leads: 0, bookings: 0, deliveries: 0, pendingDeliveries: 0, cancelled: 0,
          customerOutstanding: 0, financeAmount: 0, revenue: 0,
          extraIncome: owner ? Number(extraByModel[model] || 0) : null,
          bookingConversion: 0, deliveryConversion: 0,
          leadIds: { leads: [], bookings: [], deliveries: [], pending: [], cancelled: [], outstanding: [] }
        };
      }
    }
    var b = buckets[model];
    if (!b) return;

    var status = normalizeStatus_(l.currentStatus);
    var bookingDate = formatDate_(l.bookingDate);
    var del = store.deliveryByLead[id] || {};
    var delivered = String(del.delivered || '').toLowerCase() === 'yes' || status === 'Delivered';
    var booked = !!bookingDate || status === 'Booked' || delivered;
    var cancelled = status === 'Lost' || status === 'Cancelled';
    var customerOs = typeof computeDashboardOutstanding_ === 'function'
      ? computeDashboardOutstanding_(id, store) : 0;
    var financeOs = Number(financeByLead[id] || 0);

    b.leads++;
    b.leadIds.leads.push(id);
    b.revenue += Number(paidByLead[id] || 0);
    b.customerOutstanding += customerOs;
    b.financeAmount += financeOs;

    if (booked) {
      b.bookings++;
      b.leadIds.bookings.push(id);
    }
    if (delivered) {
      b.deliveries++;
      b.leadIds.deliveries.push(id);
    }
    if (booked && !delivered && !cancelled && isActiveLead_(l)) {
      b.pendingDeliveries++;
      b.leadIds.pending.push(id);
    }
    if (cancelled) {
      b.cancelled++;
      b.leadIds.cancelled.push(id);
    }
    if (customerOs + financeOs > 0.01) {
      b.leadIds.outstanding.push(id);
    }
  });

  return Object.keys(buckets).sort(function (a, b) {
    return a.toLowerCase().localeCompare(b.toLowerCase());
  }).map(function (key) {
    var b = buckets[key];
    b.customerOutstanding = round2_(b.customerOutstanding);
    b.financeAmount = round2_(b.financeAmount);
    b.revenue = round2_(b.revenue);
    if (b.extraIncome != null) b.extraIncome = round2_(b.extraIncome);
    b.bookingConversion = b.leads > 0 ? round2_((b.bookings / b.leads) * 100) : 0;
    b.deliveryConversion = b.bookings > 0 ? round2_((b.deliveries / b.bookings) * 100) : 0;
    return b;
  });
}

function buildModelPerformanceDrillDowns_(store, gids) {
  store = store || loadCrmStore_(true);
  var financeByLead = typeof getFinanceOutstandingMapByLead_ === 'function'
    ? getFinanceOutstandingMapByLead_() : {};
  var list = computeModelPerformance_(store, financeByLead);
  var hdr = ['Lead ID', 'Customer', 'Mobile', 'Model', 'Variant', 'Status', 'Executive', 'Cust OS', 'Finance OS'];
  gids.modelPerformance = gids.modelPerformance || {};

  function rowsForIds(ids) {
    return (ids || []).map(function (id) {
      var l = store.leads.byId[id];
      return l ? modelPerfLeadRow_(l, store, financeByLead) : null;
    }).filter(Boolean);
  }

  list.forEach(function (b) {
    var model = b.model;
    var keyBase = model.toLowerCase();
    var mp = {};
    mp.leads = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Leads'), hdr, rowsForIds(b.leadIds.leads));
    mp.bookings = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Bookings'), hdr, rowsForIds(b.leadIds.bookings));
    mp.deliveries = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Deliveries'), hdr, rowsForIds(b.leadIds.deliveries));
    mp.pending = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Pending Deliveries'), hdr, rowsForIds(b.leadIds.pending));
    mp.cancelled = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Cancelled'), hdr, rowsForIds(b.leadIds.cancelled));
    mp.outstanding = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Outstanding'), hdr, rowsForIds(b.leadIds.outstanding));
    mp.finance = mp.outstanding;
    mp.bookingConversion = mp.bookings;
    mp.deliveryConversion = mp.deliveries;

    // Revenue = payment rows for this model's leads
    var payHdr = ['Receipt', 'Lead ID', 'Customer', 'Date', 'Amount', 'Mode'];
    var payRows = [];
    var leadSet = {};
    (b.leadIds.leads || []).forEach(function (id) { leadSet[id] = true; });
    var ph = store.payments.headers;
    store.payments.rows.forEach(function (r) {
      var lid = String(rowVal_(r, ph, 'Lead ID')).trim();
      if (!leadSet[lid]) return;
      var rcpt = String(rowVal_(r, ph, 'Receipt Number')).trim();
      payRows.push([
        typeof navEntityLink_ === 'function' ? navEntityLink_('Payment', rcpt, rcpt) : rcpt,
        typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', lid, lid) : lid,
        rowVal_(r, ph, 'Customer Name'),
        typeof paymentLedgerDate_ === 'function'
          ? paymentLedgerDate_(r, ph)
          : formatDate_(rowVal_(r, ph, 'Date') || rowVal_(r, ph, 'Payment Date')),
        rowVal_(r, ph, 'Amount'),
        rowVal_(r, ph, 'Payment Mode')
      ]);
    });
    mp.revenue = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Revenue'), payHdr, payRows);

    if (typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_() &&
        typeof readAllExtraIncomeRows_ === 'function') {
      var eiHdr = ['Lead ID', 'Customer', 'Vehicle', 'Dealer Retained', 'Insurance Income', 'Other', 'Total Extra', 'Status'];
      var eiRows = [];
      try {
        readAllExtraIncomeRows_().forEach(function (r) {
          var lead = store.leads.byId[r.leadId];
          var m = lead ? String(lead.interestedModel || '').trim() : '';
          if (!m && r.vehicle) m = String(r.vehicle).trim().split(/\s+/)[0] || '';
          if (!modelKeyMatch_(m, model)) return;
          eiRows.push([
            typeof navEntityLink_ === 'function' ? navEntityLink_('Lead', r.leadId, r.leadId) : r.leadId,
            r.customer || '',
            r.vehicle || '',
            r.dealerBenefitRetained,
            r.insuranceIncome,
            r.otherIncome,
            r.totalExtraIncome,
            r.profitStatus || ''
          ]);
        });
      } catch (eiErr) {}
      mp.extraIncome = navWriteDrillDownSheet_(modelPerfSheetTitle_(model, 'Dealer Earnings'), eiHdr, eiRows);
    }

    gids.modelPerformance[keyBase] = mp;
  });
}

/** Write MODEL PERFORMANCE table on Dashboard (row 42+). Extra Income column = owner only. */
function writeModelPerformanceSection_(dash, modelList, drill) {
  dash = dash || getSheet_(CRM.SHEETS.DASHBOARD);
  drill = drill || {};
  var owner = typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_();
  var startRow = 42;
  var headerRow = 43;
  var dataStart = 44;
  var colCount = owner ? 12 : 11;

  // Clear previous dynamic block (up to ~40 models).
  dash.getRange(startRow, 1, startRow + 50, 12).clearContent().clearFormat();
  dash.getRange(startRow, 1).setValue('MODEL PERFORMANCE').setFontWeight('bold').setFontSize(12);
  dash.getRange(startRow, 2).setValue('All models from Price Master + Lead Register — click any value to open filtered records')
    .setFontColor('#666666').setFontSize(10);

  var headers = [
    'Model', 'Leads', 'Bookings', 'Deliveries', 'Pending Del', 'Cancelled',
    'Book Conv %', 'Del Conv %', 'Customer OS', 'Finance Amt', 'Revenue'
  ];
  if (owner) headers.push('Dealer Earnings');
  dash.getRange(headerRow, 1, 1, headers.length).setValues([headers])
    .setFontWeight('bold').setBackground('#E8EEF4');

  var list = modelList || [];
  if (!list.length) {
    dash.getRange(dataStart, 1).setValue('No vehicle models found in Price Master or Lead Register.');
    return;
  }

  function linkOrValue(gid, value, label) {
    if (gid != null && typeof navDrillDownLink_ === 'function') {
      return navDrillDownLink_(gid, label != null ? label : value, label != null ? label : value);
    }
    return value;
  }

  var mpRoot = (drill.modelPerformance) || {};
  list.forEach(function (b, i) {
    var row = dataStart + i;
    var mp = mpRoot[String(b.model || '').toLowerCase()] || {};
    var cells = [
      b.model,
      linkOrValue(mp.leads, b.leads),
      linkOrValue(mp.bookings, b.bookings),
      linkOrValue(mp.deliveries, b.deliveries),
      linkOrValue(mp.pending, b.pendingDeliveries),
      linkOrValue(mp.cancelled, b.cancelled),
      linkOrValue(mp.bookingConversion, b.bookingConversion, b.bookingConversion + '%'),
      linkOrValue(mp.deliveryConversion, b.deliveryConversion, b.deliveryConversion + '%'),
      linkOrValue(mp.outstanding, b.customerOutstanding,
        '₹' + Math.round(b.customerOutstanding).toLocaleString('en-IN')),
      linkOrValue(mp.finance, b.financeAmount,
        '₹' + Math.round(b.financeAmount).toLocaleString('en-IN')),
      linkOrValue(mp.revenue, b.revenue,
        '₹' + Math.round(b.revenue).toLocaleString('en-IN'))
    ];
    if (owner) {
      cells.push(linkOrValue(mp.extraIncome, b.extraIncome || 0,
        '₹' + Math.round(Number(b.extraIncome || 0)).toLocaleString('en-IN')));
    }

    // Write formulas vs values cell-by-cell (mixed types).
    cells.forEach(function (val, c) {
      var range = dash.getRange(row, c + 1);
      if (typeof val === 'string' && val.indexOf('=HYPERLINK') === 0) {
        range.setFormula(val);
      } else {
        range.setValue(val);
      }
    });
    dash.getRange(row, 1).setFontWeight('bold');
  });

  dash.getRange(dataStart, 2, list.length, colCount - 1).setHorizontalAlignment('center');
  try {
    dash.autoResizeColumns(1, colCount);
  } catch (e) {}
}
