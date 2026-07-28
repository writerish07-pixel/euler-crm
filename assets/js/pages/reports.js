(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Reports</h1><p>Snapshot of dashboard metrics for export. Charts use Chart.js.</p></div>' +
      '<button type="button" class="btn" id="btn-run">Run report</button></div>' +
      '<div class="card card-pad"><canvas id="chart" height="120"></canvas></div>' +
      '<div class="card card-pad" style="margin-top:14px;"><div id="tbl"></div></div>';

    document.getElementById('btn-run').addEventListener('click', run);
    await run();

    async function run() {
      try {
        var data = await U.withLoading(CRM_API.getDashboard());
        var m = (data && (data.metrics || data)) || {};
        var rows = [
          { metric: "Today's Leads", value: m.todayLeads },
          { metric: "Today's Bookings", value: m.todayBookings },
          { metric: "Today's Deliveries", value: m.todayDeliveries },
          { metric: 'MTD Leads', value: m.monthlyLeads },
          { metric: 'MTD Bookings', value: m.monthlyBookings },
          { metric: 'MTD Deliveries', value: m.monthlyDeliveries },
          { metric: 'Customer Outstanding', value: m.customerOutstanding },
          { metric: 'Finance Outstanding', value: m.financeOutstanding },
          { metric: 'Revenue (MTD)', value: m.revenue }
        ];
        CRM_TABLE.create(document.getElementById('tbl'), {
          exportName: 'crm-report',
          columns: [
            { key: 'metric', label: 'Metric' },
            { key: 'value', label: 'Value', render: function (v, r) {
              if (String(r.metric).indexOf('Outstanding') >= 0 || String(r.metric).indexOf('Revenue') >= 0) {
                return U.escapeHtml(U.formatINR(v));
              }
              return U.escapeHtml(U.formatNumber(v));
            }}
          ],
          rows: rows
        });
        if (typeof Chart !== 'undefined') {
          var ctx = document.getElementById('chart');
          if (ctx._chart) ctx._chart.destroy();
          ctx._chart = new Chart(ctx, {
            type: 'line',
            data: {
              labels: ['Leads', 'Bookings', 'Deliveries'],
              datasets: [{
                label: 'MTD',
                data: [m.monthlyLeads || 0, m.monthlyBookings || 0, m.monthlyDeliveries || 0],
                borderColor: '#0f3d68',
                backgroundColor: 'rgba(15,61,104,.12)',
                tension: 0.2
              }]
            },
            options: { animation: false, plugins: { legend: { display: false } } }
          });
        }
      } catch (err) { U.handleApiError(err); }
    }
  }
  CRM_BOOT.register('reports', { title: 'Reports', init: init });
})();
