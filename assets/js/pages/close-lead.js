/**
 * Close Lead â€” same fields as Spreadsheet CRM dialog.
 */
(function () {
  'use strict';

  var STATUS_OPTS = ['Yes', 'No', 'Pending', 'Done'];

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Close Lead (Accounts)</h1>' +
      '<p>Same feeding style as Spreadsheet CRM â†’ Close Lead.</p></div></div>' +
      '<form id="c-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div id="closeStatus" class="sheet-status">Pick a lead to load RC & plate detailsâ€¦</div>' +
        '<div class="form-stack">' +
          '<label class="field"><span>RC *</span><select id="rc" name="rc"></select></label>' +
          '<label class="field"><span>Number Plate *</span><input id="numberPlate" name="numberPlate" placeholder="e.g. RJ14-AB-1234" /></label>' +
          '<label class="field"><span>Close Reason *</span><textarea id="reason" name="reason" rows="2" placeholder="e.g. Fully settled, Customer cancelled" required></textarea></label>' +
          '<label class="field"><span>Final Outstanding (System Calculated â€” Read Only)</span>' +
            '<input id="finalOutstanding" name="finalOutstanding" disabled readonly /></label>' +
          '<div class="sheet-hint">Locked Â· System Calculated Â· Customer Payable âˆ’ Payments Received</div>' +
          '<label class="field"><span>Closing Date *</span><input id="closeDate" name="closeDate" type="date" required /></label>' +
          '<label class="field"><span>Remarks</span><textarea id="closeRemarks" name="remarks" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:16px;"><button type="submit" class="btn btn-danger">Close Lead Account</button></div>' +
      '</form>';

    U.fillSelect(document.getElementById('rc'), STATUS_OPTS, false);
    document.getElementById('rc').value = 'Pending';
    document.getElementById('closeDate').value = U.todayISO();
    CRM_CONTEXT.clear(document.getElementById('ctx'));

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'close',
      onChange: async function (id) {
        var st = document.getElementById('closeStatus');
        if (!id) {
          CRM_CONTEXT.clear(document.getElementById('ctx'));
          st.textContent = 'Pick a lead to load RC & plate detailsâ€¦';
          return;
        }
        st.textContent = 'Loading RC & plateâ€¦';
        try {
          var res = await U.withLoading(CRM_API.getCloseLeadContext(id));
          applyCloseCtx(res);
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

    document.getElementById('c-form').addEventListener('submit', async function (e) {
      e.preventDefault();
      var d = {
        leadId: picker.getLeadId(),
        rc: document.getElementById('rc').value,
        numberPlate: document.getElementById('numberPlate').value,
        reason: document.getElementById('reason').value,
        closeDate: document.getElementById('closeDate').value,
        remarks: document.getElementById('closeRemarks').value
      };
      if (!d.leadId) { U.toast('Select a lead', 'warn'); return; }
      if (!/^(yes|done)$/i.test(d.rc)) { U.toast('RC must be Yes or Done', 'warn'); return; }
      if (!String(d.numberPlate || '').trim()) { U.toast('Number plate is required', 'warn'); return; }
      if (!d.reason) { U.toast('Close reason is required', 'warn'); return; }
      if (!d.closeDate) { U.toast('Closing date is required', 'warn'); return; }
      if (!(await U.confirmDialog('Close this lead account?', 'Close Lead'))) return;
      try {
        var res = await U.withLoading(CRM_API.closeLead(d));
        U.toast((res && res.message) || 'Lead closed', 'ok');
      } catch (err) { U.handleApiError(err); }
    });
  }

  function applyCloseCtx(res) {
    var st = document.getElementById('closeStatus');
    if (!res || res.success === false) {
      st.textContent = (res && res.message) || 'Could not load lead details';
      return;
    }
    if (res.rc) document.getElementById('rc').value = res.rc;
    if (res.numberPlate != null) document.getElementById('numberPlate').value = res.numberPlate;
    var os = Number(res.outstanding);
    document.getElementById('finalOutstanding').value = isFinite(os)
      ? ('â‚¹' + os.toLocaleString('en-IN', { maximumFractionDigits: 2 }))
      : 'Calculatingâ€¦';
    st.textContent = 'Enter RC status and number plate before closing. Outstanding is system-calculated (read only).';
  }

  CRM_BOOT.register('close-lead', { title: 'Close Lead', init: init });
})();
