(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Deal Quotation</h1><p>Pricing & scheme context from the engine. Amounts are not recalculated here.</p></div></div>' +
      '<form id="q-form" class="card card-pad" style="max-width:900px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div class="form-grid" style="margin-top:4px;">' +
          '<label class="field"><span>Quote Date</span><input name="quoteDate" type="date" /></label>' +
          '<label class="field"><span>Model</span><input name="model" /></label>' +
          '<label class="field"><span>Variant</span><input name="variant" /></label>' +
          '<label class="field"><span>Ex-Showroom (server)</span><input name="exShowroom" data-number readonly /></label>' +
          '<label class="field full"><span>Notes</span><textarea name="notes" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:14px;display:flex;gap:8px;">' +
          '<button type="button" class="btn btn-secondary" id="btn-load">Load pricing</button>' +
          '<button type="submit" class="btn">Save Quotation</button>' +
        '</div>' +
      '</form>';

    var form = document.getElementById('q-form');
    var ctxEl = document.getElementById('ctx');
    form.quoteDate.value = U.todayISO();
    U.wireAutoSave(form, 'quotation');
    CRM_CONTEXT.clear(ctxEl);

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      stage: 'quotation',
      onChange: async function (id, lead) {
        if (lead) {
          form.model.value = lead.interestedModel || lead.model || '';
          form.variant.value = lead.variant || '';
        }
        if (!id) { CRM_CONTEXT.clear(ctxEl); return; }
        try {
          var ctx = await CRM_API.getLeadContext(id);
          CRM_CONTEXT.render(ctxEl, ctx);
        } catch (err) {
          try {
            var b = await CRM_API.getBookingContext(id);
            CRM_CONTEXT.render(ctxEl, b);
          } catch (e2) {
            CRM_CONTEXT.clear(ctxEl, 'Select model/variant and load pricing');
          }
        }
      }
    });

    document.getElementById('btn-load').addEventListener('click', async function () {
      try {
        var ctx = await U.withLoading(CRM_API.getQuotationContext({
          model: form.model.value,
          variant: form.variant.value,
          quoteDate: form.quoteDate.value
        }));
        var wrapped = {
          lead: {
            leadId: picker.getLeadId(),
            customerName: (picker.getLead() && (picker.getLead().customerName || picker.getLead().name)) || '',
            mobile: (picker.getLead() && picker.getLead().mobile) || '',
            interestedModel: form.model.value,
            variant: form.variant.value,
            currentStatus: 'Quotation'
          },
          price: ctx.price || ctx,
          totals: ctx.totals || {},
          outstanding: (ctx.totals && ctx.totals.outstanding) || ctx.outstanding || 0,
          paymentsReceived: ctx.paymentsReceived || 0
        };
        if (ctx.exShowroom != null || (ctx.price && ctx.price.exShowroom != null)) {
          form.exShowroom.value = ctx.exShowroom != null ? ctx.exShowroom : ctx.price.exShowroom;
        } else if (ctx.price != null && typeof ctx.price === 'number') {
          form.exShowroom.value = ctx.price;
        }
        CRM_CONTEXT.render(ctxEl, wrapped, { footer: 'Quotation pricing loaded from Price Master.' });
      } catch (err) { U.handleApiError(err); }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var data = U.readForm(form);
      data.leadId = picker.getLeadId();
      if (!data.leadId) { U.toast('Select a lead', 'warn'); return; }
      try {
        var res = await U.withLoading(CRM_API.saveQuotation(data));
        U.clearDraft('quotation');
        U.toast((res && res.message) || 'Quotation saved', 'ok');
      } catch (err) { U.handleApiError(err); }
    });
  }
  CRM_BOOT.register('quotation', { title: 'Quotation', init: init });
})();
