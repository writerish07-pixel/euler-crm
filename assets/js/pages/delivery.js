/**
 * Mark Delivered â€” same checklist fields as Spreadsheet CRM dialog.
 */
(function () {
  'use strict';

  var STATUS_OPTS = ['Yes', 'No', 'Pending', 'Done'];

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Mark Delivered</h1>' +
      '<p>Same feeding style as Spreadsheet CRM â†’ Mark Delivered.</p></div></div>' +
      '<form id="d-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div id="deliveryStatus" class="sheet-status">Pick a lead to load delivery checklistâ€¦</div>' +
        '<h4 class="sheet-h4">Delivery Checklist</h4>' +
        '<div class="form-stack">' +
          '<label class="field"><span>Insurance *</span><select id="insurance" name="insurance"></select></label>' +
          '<label class="field"><span>Insurer Name *</span><input id="insurerName" name="insurerName" placeholder="e.g. Bajaj Allianz" /></label>' +
          '<label class="field"><span>Registration *</span><select id="registration" name="registration"></select></label>' +
          '<label class="field"><span>Invoice *</span><select id="invoice" name="invoice"></select></label>' +
          '<label class="field"><span>Invoice Number *</span><input id="invoiceNumber" name="invoiceNumber" /></label>' +
          '<label class="field"><span>Chassis Number *</span><input id="chassisNumber" name="chassisNumber" /></label>' +
          '<label class="field"><span>Accessories</span><select id="accessories" name="accessories"></select></label>' +
          '<label class="field"><span>PDI *</span><select id="pdi" name="pdi"></select></label>' +
          '<label class="field"><span>Delivery Date *</span><input id="deliveryDate" name="deliveryDate" type="date" required /></label>' +
          '<label class="field"><span>Feedback</span><textarea id="feedback" name="feedback" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:16px;"><button type="submit" class="btn">Mark Delivered</button></div>' +
      '</form>';

    ['insurance', 'registration', 'invoice', 'accessories', 'pdi'].forEach(function (id) {
      U.fillSelect(document.getElementById(id), STATUS_OPTS, false);
    });
    document.getElementById('deliveryDate').value = U.todayISO();
    document.getElementById('insurance').value = 'Yes';
    document.getElementById('registration').value = 'Yes';
    document.getElementById('invoice').value = 'Yes';
    document.getElementById('pdi').value = 'Yes';
    document.getElementById('accessories').value = 'Pending';
    CRM_CONTEXT.clear(document.getElementById('ctx'));

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'delivery',
      onChange: async function (id) {
        var st = document.getElementById('deliveryStatus');
        if (!id) {
          CRM_CONTEXT.clear(document.getElementById('ctx'));
          st.textContent = 'Pick a lead to load delivery checklistâ€¦';
          return;
        }
        st.textContent = 'Loading delivery checklistâ€¦';
        try {
          var res = await U.withLoading(CRM_API.getDeliveryContext(id));
          applyDeliveryCtx(res);
          var money = null;
          try { money = await CRM_API.getSchemeContext(id); } catch (e) {
            try { money = await CRM_API.getBookingContext(id); } catch (e2) {}
          }
          CRM_CONTEXT.render(document.getElementById('ctx'), Object.assign({}, money || {}, res || {}));
        } catch (err) {
          st.textContent = err.message || String(err);
          U.handleApiError(err);
        }
      }
    });

    document.getElementById('d-form').addEventListener('submit', async function (e) {
      e.preventDefault();
      var d = {
        leadId: picker.getLeadId(),
        insurance: document.getElementById('insurance').value,
        insurerName: document.getElementById('insurerName').value,
        registration: document.getElementById('registration').value,
        invoice: document.getElementById('invoice').value,
        invoiceNumber: document.getElementById('invoiceNumber').value,
        chassisNumber: document.getElementById('chassisNumber').value,
        accessories: document.getElementById('accessories').value,
        pdi: document.getElementById('pdi').value,
        deliveryDate: document.getElementById('deliveryDate').value,
        feedback: document.getElementById('feedback').value
      };
      if (!d.leadId) { U.toast('Select a lead', 'warn'); return; }
      if (!d.deliveryDate) { U.toast('Delivery date is required', 'warn'); return; }
      if (!/^(yes|done)$/i.test(d.insurance)) { U.toast('Insurance must be Yes', 'warn'); return; }
      if (!String(d.insurerName || '').trim()) { U.toast('Insurer name is required', 'warn'); return; }
      if (!/^(yes|done)$/i.test(d.registration)) { U.toast('Registration must be Yes', 'warn'); return; }
      if (!/^(yes|done)$/i.test(d.invoice)) { U.toast('Invoice must be Yes', 'warn'); return; }
      if (!String(d.invoiceNumber || '').trim()) { U.toast('Invoice number is required', 'warn'); return; }
      if (!String(d.chassisNumber || '').trim()) { U.toast('Chassis number is required', 'warn'); return; }
      if (!/^(yes|done)$/i.test(d.pdi)) { U.toast('PDI must be Yes', 'warn'); return; }
      if (!(await U.confirmDialog('Confirm delivery?', 'Mark Delivered'))) return;
      try {
        var res = await U.withLoading(CRM_API.markDelivered(d));
        U.toast((res && res.message) || 'Marked delivered', 'ok');
      } catch (err) { U.handleApiError(err); }
    });
  }

  function applyDeliveryCtx(res) {
    var st = document.getElementById('deliveryStatus');
    if (!res || res.success === false) {
      st.textContent = (res && res.message) || 'Could not load delivery row';
      return;
    }
    var d = res.delivery || {};
    function setSel(id, v) {
      var x = document.getElementById(id);
      if (x && v) x.value = v;
    }
    function setVal(id, v) {
      var x = document.getElementById(id);
      if (x && v != null) x.value = v;
    }
    setSel('insurance', d.insurance || 'Yes');
    setVal('insurerName', d.insurerName);
    setSel('registration', d.registration || 'Yes');
    setSel('invoice', d.invoice || 'Yes');
    setVal('invoiceNumber', d.invoiceNumber);
    setVal('chassisNumber', d.chassisNumber || res.chassisNumber || '');
    setSel('accessories', d.accessories || 'Pending');
    setSel('pdi', d.pdi || 'Yes');
    setVal('feedback', d.feedback);
    if (d.deliveryDate) setVal('deliveryDate', d.deliveryDate);
    var msg = 'Customer outstanding: â‚¹' + Number(res.outstanding || 0).toLocaleString('en-IN');
    if (!res.eligible) msg += ' â€” delivery blocked until customer outstanding is zero';
    else if (d.delivered === 'Yes') msg += ' â€” previously marked delivered (update checklist below)';
    st.textContent = msg;
  }

  CRM_BOOT.register('delivery', { title: 'Delivery', init: init });
})();
