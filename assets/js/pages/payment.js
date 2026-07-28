(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var masters = {};
    try { masters = await CRM_API.getMasters() || {}; } catch (e) {}
    var financers = masters['Financers'] || [];
    var modes = masters['Payment Modes'] || ['Cash', 'UPI', 'Card', 'Finance', 'Cheque', 'Bank Transfer'];

    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Add Payment</h1><p>Same as Spreadsheet CRM â†’ Add Payment. Financer appears only for Finance mode.</p></div></div>' +
      '<form id="p-form" class="card card-pad sheet-form" style="max-width:720px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<label class="field" style="max-width:240px;margin:4px 0 12px;"><span>Payment Date *</span><input name="paymentDate" type="date" required /></label>' +
        '<div class="sheet-hint">Record the full down payment in one go â€” add a line per mode (e.g. part Card, part Cash, balance Finance).</div>' +
        '<div id="rows"></div>' +
        '<button type="button" class="btn btn-secondary" id="add-row" style="margin:8px 0;">+ Add another payment line</button>' +
        '<div id="total" style="font-weight:700;margin:8px 0;"></div>' +
        '<label class="field"><span>Narration</span><input name="narration" autocomplete="off" /></label>' +
        '<button type="submit" class="btn" style="margin-top:12px;">Record Payment</button>' +
      '</form>';

    var form = document.getElementById('p-form');
    var ctxEl = document.getElementById('ctx');
    form.paymentDate.value = U.todayISO();
    CRM_CONTEXT.clear(ctxEl);
    var rowsEl = document.getElementById('rows');
    var rowCount = 0;

    function modeOpts() {
      return modes.map(function (m) { return '<option value="' + U.escapeAttr(m) + '">' + U.escapeHtml(m) + '</option>'; }).join('');
    }
    function finOpts() {
      return '<option value="">â€”</option>' + financers.map(function (f) {
        return '<option value="' + U.escapeAttr(f) + '">' + U.escapeHtml(f) + '</option>';
      }).join('');
    }
    function toggleFin(row) {
      var mode = row.querySelector('.mode');
      var finBlk = row.querySelector('.fin-blk');
      if (!mode || !finBlk) return;
      finBlk.style.display = String(mode.value || '').toLowerCase() === 'finance' ? 'block' : 'none';
    }
    function addRow() {
      var i = rowCount++;
      var div = document.createElement('div');
      div.className = 'pay-row';
      div.dataset.row = String(i);
      div.style.cssText = 'border:1px solid var(--border);border-radius:8px;padding:10px;margin-bottom:8px;';
      div.innerHTML =
        '<div class="form-grid">' +
          '<label class="field"><span>Amount *</span><input class="amt" type="number" min="0" step="0.01" required /></label>' +
          '<label class="field"><span>Mode</span><select class="mode">' + modeOpts() + '</select></label>' +
          '<label class="field"><span></span><button type="button" class="btn btn-ghost rm">âœ•</button></label>' +
        '</div>' +
        '<div class="fin-blk" style="display:none;margin-top:8px;padding:8px;background:#FFF3E0;border-radius:6px;">' +
          '<label class="field"><span>Financer Name *</span><select class="fin">' + finOpts() + '</select></label>' +
          '<div class="sheet-hint">Finance File Number is auto-generated; an existing open file is reused.</div>' +
        '</div>';
      rowsEl.appendChild(div);
      div.querySelector('.rm').addEventListener('click', function () {
        if (rowsEl.querySelectorAll('.pay-row').length <= 1) return;
        div.remove();
        sum();
      });
      div.querySelector('.amt').addEventListener('input', sum);
      div.querySelector('.mode').addEventListener('change', function () { toggleFin(div); });
      toggleFin(div);
      sum();
    }
    function sum() {
      var t = 0;
      var n = 0;
      rowsEl.querySelectorAll('.pay-row').forEach(function (row) {
        var a = Number(row.querySelector('.amt').value) || 0;
        if (a > 0) { t += a; n++; }
      });
      document.getElementById('total').textContent = n
        ? ('Total this entry: ' + U.formatINR(t) + ' across ' + n + ' line(s)')
        : '';
    }
    document.getElementById('add-row').addEventListener('click', addRow);
    addRow();

    async function loadCtx(id) {
      if (!id) { CRM_CONTEXT.clear(ctxEl); return; }
      try {
        var ctx = await CRM_API.getSchemeContext(id);
        CRM_CONTEXT.render(ctxEl, ctx);
      } catch (err) {
        try {
          var b = await CRM_API.getBookingContext(id);
          CRM_CONTEXT.render(ctxEl, b);
        } catch (e2) {
          CRM_CONTEXT.clear(ctxEl, err.message || 'Could not load outstanding');
        }
      }
    }

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      stage: 'payment',
      activeOnly: true,
      onChange: function (id) { loadCtx(id); }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var payments = [];
      rowsEl.querySelectorAll('.pay-row').forEach(function (row) {
        var amt = Number(row.querySelector('.amt').value) || 0;
        if (!(amt > 0)) return;
        payments.push({
          amount: amt,
          paymentMode: row.querySelector('.mode').value,
          financerName: row.querySelector('.fin').value
        });
      });
      for (var q = 0; q < payments.length; q++) {
        if (String(payments[q].paymentMode || '').toLowerCase() === 'finance' &&
            !String(payments[q].financerName || '').trim()) {
          U.toast('Financer name is required for Finance line ' + (q + 1), 'warn');
          return;
        }
      }
      var payload = {
        leadId: picker.getLeadId(),
        paymentDate: form.paymentDate.value,
        date: form.paymentDate.value,
        payments: payments,
        narration: form.narration.value
      };
      if (!payload.leadId) { U.toast('Select a lead', 'warn'); return; }
      if (!payments.length) { U.toast('Enter at least one payment amount', 'warn'); return; }
      try {
        var res = await U.withLoading(CRM_API.savePayment(payload));
        U.toast((res && res.message) || 'Payment recorded', 'ok');
        rowsEl.innerHTML = '';
        rowCount = 0;
        addRow();
        await loadCtx(payload.leadId);
        if (picker.reload) await picker.reload();
      } catch (err) { U.handleApiError(err); }
    });
  }
  CRM_BOOT.register('payment', { title: 'Payment', init: init });
})();
