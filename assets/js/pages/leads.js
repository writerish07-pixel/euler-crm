(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Leads</h1><p>Active pipeline from the server. Search and filter locally.</p></div>' +
      '<a class="btn" href="#/new-lead">New Lead</a></div>' +
      '<div class="card card-pad"><div id="leads-table"></div></div>';

    var q = (window.CRM_ROUTER && CRM_ROUTER.getQuery().q) ||
      (window.CRM_ROUTE_QUERY && CRM_ROUTE_QUERY.q) || '';
    try {
      var res = await U.withLoading(q ? CRM_API.searchLeads(q) : CRM_API.getLeads({ activeOnly: false }));
      var rows = Array.isArray(res) ? res : (res && (res.leads || res.items || res.results)) || [];
      rows = rows.map(function (l) {
        return {
          leadId: l.leadId || l.id || '',
          customerName: l.customerName || l.name || '',
          mobile: l.mobile || '',
          model: l.interestedModel || l.model || '',
          variant: l.variant || '',
          status: l.currentStatus || l.status || '',
          executive: l.executive || '',
          source: l.leadSource || l.source || ''
        };
      });
      CRM_TABLE.create(document.getElementById('leads-table'), {
        exportName: 'leads',
        columns: [
          { key: 'leadId', label: 'Lead ID', render: function (v) {
            return '<a href="#/customer360?leadId=' + encodeURIComponent(v) + '">' + CRM_UTIL.escapeHtml(v) + '</a>';
          }},
          { key: 'customerName', label: 'Customer' },
          { key: 'mobile', label: 'Mobile' },
          { key: 'model', label: 'Model' },
          { key: 'variant', label: 'Variant' },
          { key: 'status', label: 'Status' },
          { key: 'executive', label: 'Executive' },
          { key: 'source', label: 'Source' }
        ],
        rows: rows
      });
      if (q) {
        var filter = document.querySelector('#leads-table [data-role="filter"]');
        if (filter) { filter.value = q; filter.dispatchEvent(new Event('input')); }
      }
    } catch (err) {
      root.querySelector('#leads-table').innerHTML = '<div class="empty">' + U.escapeHtml(err.message) + '</div>';
    }
  }
  CRM_BOOT.register('leads', { title: 'Leads', init: init });
})();
