(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    var leadId = (window.CRM_ROUTER && CRM_ROUTER.getQuery().leadId) ||
      (window.CRM_ROUTE_QUERY && CRM_ROUTE_QUERY.leadId) || '';
    root.innerHTML =
      '<div class="page-header"><div><h1>Customer 360</h1><p>Unified view from the business engine.</p></div></div>' +
      '<div class="card card-pad" style="margin-bottom:14px;"><div id="picker"></div>' +
      '<button type="button" class="btn" id="btn-load" style="margin-top:10px;">Load 360</button></div>' +
      '<div id="ctx"></div>' +
      '<div id="extra" style="margin-top:14px;"></div>';

    var ctxEl = document.getElementById('ctx');
    CRM_CONTEXT.clear(ctxEl, 'Select a lead');

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: false,
      preselect: leadId
    });

    async function load() {
      var id = picker.getLeadId() || leadId;
      if (!id) { U.toast('Select a lead', 'warn'); return; }
      try {
        var data = await U.withLoading(CRM_API.getCustomer360(id));
        var money = null;
        try { money = await CRM_API.getSchemeContext(id); } catch (e) {
          try { money = await CRM_API.getBookingContext(id); } catch (e2) {}
        }
        var merged = Object.assign({}, money || {}, {
          lead: (data && data.lead) || (money && money.lead) || data,
          outstanding: data.outstanding != null ? data.outstanding : (money && money.outstanding),
          paymentsReceived: data.paymentsReceived != null ? data.paymentsReceived : (money && money.paymentsReceived),
          customerPayable: data.customerPayable != null ? data.customerPayable : (money && money.customerPayable),
          totals: data.totals || (money && money.totals),
          price: data.price || (money && money.price)
        });
        CRM_CONTEXT.render(ctxEl, merged, { footer: 'Customer 360 â€” presentation of server truth only.' });

        var extra = document.getElementById('extra');
        var sections = [];
        if (data.activities || data.activity) {
          sections.push('<div class="card card-pad"><h3 style="margin:0 0 8px;font-size:14px;">Recent activity</h3><p style="margin:0;font-size:13px;color:var(--muted);">Loaded from server payload.</p></div>');
        }
        if (data.payments) {
          sections.push('<div class="card card-pad" style="margin-top:12px;"><h3 style="margin:0 0 8px;font-size:14px;">Payments</h3><p style="margin:0;font-size:13px;color:var(--muted);">See Payment screen for new receipts.</p></div>');
        }
        extra.innerHTML = sections.join('') || '';
      } catch (err) {
        CRM_CONTEXT.clear(ctxEl, err.message || 'Could not load 360');
        U.handleApiError(err);
      }
    }

    document.getElementById('btn-load').addEventListener('click', load);
    if (leadId) load();
  }
  CRM_BOOT.register('customer360', { title: 'Customer 360', init: init });
})();
