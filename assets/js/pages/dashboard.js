/**
 * Dashboard page â€” KPIs + Chart.js. No business math on client.
 */
(function () {
  'use strict';

  var charts = [];

  function destroyCharts() {
    charts.forEach(function (c) { try { c.destroy(); } catch (e) {} });
    charts = [];
  }

  function kpiCard(label, value, hint) {
    return '<div class="card card-pad kpi">' +
      '<div class="label">' + label + '</div>' +
      '<div class="value">' + value + '</div>' +
      (hint ? '<div class="hint">' + hint + '</div>' : '') +
      '</div>';
  }

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('dash-root');
    if (!root) return;

    root.innerHTML = '<div class="empty">Loading dashboardâ€¦</div>';
    try {
      var data = await U.withLoading(CRM_API.getDashboard());
      var m = (data && (data.metrics || data)) || {};
      destroyCharts();
      var mtdBookings = m.monthlyNewBookings != null ? m.monthlyNewBookings : m.monthlyBookings;
      var activeBookings = m.activeBookings != null ? m.activeBookings : m.monthlyBookings;

      root.innerHTML =
        '<div class="page-header">' +
          '<div><h1>Dashboard</h1><p>Live metrics from the business engine Â· ' +
            U.escapeHtml(data.generatedAt || '') + '</p></div>' +
          '<div style="display:flex;gap:8px;">' +
            '<button type="button" class="btn btn-secondary" id="btn-refresh">Refresh</button>' +
            '<a class="btn" href="#/new-lead">New Lead</a>' +
          '</div>' +
        '</div>' +
        '<div class="kpi-grid" style="margin-bottom:16px;">' +
          kpiCard("Today's Leads", U.formatNumber(m.todayLeads)) +
          kpiCard("Today's Bookings", U.formatNumber(m.todayBookings)) +
          kpiCard("Today's Deliveries", U.formatNumber(m.todayDeliveries)) +
          kpiCard('Pending Delivery', U.formatNumber(m.pendingDeliveries)) +
        '</div>' +
        '<div class="kpi-grid" style="margin-bottom:16px;">' +
          kpiCard('Customer Outstanding', U.formatINR(m.customerOutstanding || m.outstanding)) +
          kpiCard('Finance Outstanding', U.formatINR(m.financeOutstanding)) +
          kpiCard('Finance Overdue', U.formatNumber(m.financeOverdueCount), U.formatINR(m.financeOverdueAmount)) +
          kpiCard('MTD Conversion', U.formatPct(m.conversion), U.formatNumber(mtdBookings) + ' / ' + U.formatNumber(m.monthlyLeads)) +
          kpiCard('Active Bookings', U.formatNumber(activeBookings), mtdBookings + ' new this month') +
        '</div>' +
        '<div style="display:grid;grid-template-columns:1.2fr 1fr;gap:14px;">' +
          '<div class="card card-pad"><h3 style="margin:0 0 12px;font-size:14px;">Payment collection (MTD)</h3><canvas id="chart-pay" height="160"></canvas></div>' +
          '<div class="card card-pad"><h3 style="margin:0 0 12px;font-size:14px;">Monthly funnel</h3><canvas id="chart-funnel" height="160"></canvas></div>' +
        '</div>' +
        '<div class="card card-pad" style="margin-top:14px;">' +
          '<div class="page-header" style="margin:0 0 10px;"><h3 style="margin:0;font-size:14px;">Outstanding leads</h3></div>' +
          '<div id="os-table"></div>' +
        '</div>';

      document.getElementById('btn-refresh').addEventListener('click', function () {
        CRM_API.clearCache();
        init();
      });

      if (typeof Chart !== 'undefined') {
        var payCtx = document.getElementById('chart-pay');
        charts.push(new Chart(payCtx, {
          type: 'bar',
          data: {
            labels: ['Cash', 'UPI', 'Finance', 'Other'],
            datasets: [{
              label: 'Amount',
              data: [m.paymentsCash || 0, m.paymentsUpi || 0, m.paymentsFinance || 0, m.paymentsOther || 0],
              backgroundColor: ['#0f3d68', '#1a5f8f', '#0d9488', '#64748b']
            }]
          },
          options: {
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } },
            animation: false
          }
        }));

        var funnelCtx = document.getElementById('chart-funnel');
        charts.push(new Chart(funnelCtx, {
          type: 'doughnut',
          data: {
            labels: ['Leads', 'Bookings', 'Deliveries'],
            datasets: [{
              data: [m.monthlyLeads || 0, mtdBookings || 0, m.monthlyDeliveries || 0],
              backgroundColor: ['#0f3d68', '#1a5f8f', '#0d9488']
            }]
          },
          options: { plugins: { legend: { position: 'bottom' } }, animation: false }
        }));
      }

      var os = m.outstandingLeadsList || [];
      CRM_TABLE.create(document.getElementById('os-table'), {
        exportName: 'outstanding-leads',
        columns: [
          { key: 'leadId', label: 'Lead' },
          { key: 'customerName', label: 'Customer' },
          { key: 'mobile', label: 'Mobile' },
          { key: 'model', label: 'Model' },
          { key: 'outstanding', label: 'Outstanding', render: function (v) { return U.escapeHtml(U.formatINR(v)); } },
          { key: 'executive', label: 'Executive' },
          { key: 'status', label: 'Status' }
        ],
        rows: os
      });
    } catch (err) {
      root.innerHTML = '<div class="card card-pad empty">' +
        '<p><strong>Could not load dashboard</strong></p>' +
        '<p style="max-width:520px;margin:8px auto 0;line-height:1.45;">' + U.escapeHtml(err.message || err) + '</p>' +
        '<ol style="text-align:left;max-width:520px;margin:16px auto;font-size:13px;color:var(--muted);line-height:1.5;">' +
          '<li>In Apps Script, add file <code>WebApi.gs</code> from <code>final fix/WebApi.gs</code> (must define <code>doGet</code> / <code>doPost</code>).</li>' +
          '<li>Deploy â†’ Manage deployments â†’ âœŽ Edit â†’ Version: New version â†’ Deploy.</li>' +
          '<li>Access: Execute as <b>Me</b>, Who has access: <b>Anyone</b>.</li>' +
          '<li>Paste the new <code>/exec</code> URL into <code>assets/js/config.js</code>.</li>' +
          '<li>Do not open via <code>file://</code> â€” run <code>npx serve .</code> in the portal folder.</li>' +
        '</ol>' +
        '<button type="button" class="btn" id="retry">Retry</button></div>';
      document.getElementById('retry').addEventListener('click', init);
    }
  }

  CRM_BOOT.register('dashboard', { title: 'Dashboard', init: init });
})();
