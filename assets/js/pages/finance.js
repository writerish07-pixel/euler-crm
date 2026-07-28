(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Record Financer Receipt</h1><p>Against pending finance files. Outstanding from the engine.</p></div></div>' +
      '<form id="f-form" class="card card-pad" style="max-width:720px;">' +
        '<label class="field"><span>Pending file *</span><select name="fileNumber" id="file" required></select></label>' +
        '<div id="ctx"></div>' +
        '<div class="form-grid">' +
          '<label class="field"><span>Receipt Date *</span><input name="receiptDate" type="date" required /></label>' +
          '<label class="field"><span>Amount Received *</span><input name="amount" type="number" step="0.01" data-number required /></label>' +
          '<label class="field"><span>UTR / Reference</span><input name="utr" /></label>' +
          '<label class="field full"><span>Remarks</span><textarea name="remarks" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:14px;"><button type="submit" class="btn">Save Receipt</button></div>' +
      '</form>';

    var form = document.getElementById('f-form');
    var ctxEl = document.getElementById('ctx');
    form.receiptDate.value = U.todayISO();
    CRM_CONTEXT.clear(ctxEl, 'Select a pending finance file');

    var files = [];
    try {
      var res = await U.withLoading(CRM_API.getPendingFinanceFiles());
      files = Array.isArray(res) ? res : (res && (res.files || res.items)) || [];
    } catch (err) { U.handleApiError(err); }

    U.fillSelect(form.fileNumber, files.map(function (f) {
      return {
        value: f.fileNumber || f.id,
        label: (f.fileNumber || '') + ' | ' + (f.customerName || '') + ' | ' + (f.financer || '') + ' | OS â‚¹' + (f.fileOutstanding || 0)
      };
    }), true);

    form.fileNumber.addEventListener('change', async function () {
      var f = files.find(function (x) { return String(x.fileNumber || x.id) === form.fileNumber.value; });
      if (!f) { CRM_CONTEXT.clear(ctxEl, 'Select a pending finance file'); return; }
      if (f.fileOutstanding) form.amount.value = f.fileOutstanding;

      var card = {
        lead: {
          leadId: f.leadId || '',
          customerName: f.customerName || '',
          mobile: f.mobile || '',
          interestedModel: f.model || '',
          variant: f.variant || '',
          currentStatus: 'Finance Pending',
          executive: f.executive || ''
        },
        outstanding: Number(f.fileOutstanding || 0),
        paymentsReceived: Number(f.received || 0),
        customerPayable: Number(f.loanAmount || f.fileOutstanding || 0),
        bookingAmount: 0
      };
      CRM_CONTEXT.render(ctxEl, card, {
        footer: 'File ' + (f.fileNumber || '') + ' Â· Financer: ' + (f.financer || 'â€”')
      });

      if (f.leadId) {
        try {
          var money = await CRM_API.getSchemeContext(f.leadId);
          var merged = Object.assign({}, money, {
            outstanding: Number(f.fileOutstanding != null ? f.fileOutstanding : money.outstanding)
          });
          CRM_CONTEXT.render(ctxEl, merged, {
            footer: 'File ' + (f.fileNumber || '') + ' Â· Financer: ' + (f.financer || 'â€”') + ' Â· Lead outstanding from engine.'
          });
        } catch (e) { /* keep file card */ }
      }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var data = U.readForm(form);
      var f = files.find(function (x) { return String(x.fileNumber || x.id) === data.fileNumber; });
      if (f) data.leadId = f.leadId;
      try {
        var res = await U.withLoading(CRM_API.saveFinanceReceipt(data));
        U.toast((res && res.message) || 'Finance receipt saved', 'ok');
        location.reload();
      } catch (err) { U.handleApiError(err); }
    });
  }
  CRM_BOOT.register('finance', { title: 'Finance', init: init });
})();
