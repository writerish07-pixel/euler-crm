/**
 * Convert to Booking — booking only (no price). Use Price Structure after.
 */
(function () {
  'use strict';

  function el(id) { return document.getElementById(id); }
  function setVal(id, v) {
    var x = el(id);
    if (x) x.value = (v === undefined || v === null) ? '' : v;
  }
  function setValIf(id, v) {
    if (v === undefined || v === null || v === '') return;
    setVal(id, v);
  }

  async function init() {
    var U = CRM_UTIL;
    var masters = {};
    try { masters = await CRM_API.getMasters() || {}; } catch (e) {}
    var payModes = masters['Payment Modes'] || ['Cash', 'UPI', 'Card', 'Finance', 'Cheque', 'Bank Transfer'];

    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Convert to Booking</h1>' +
      '<p>Booking only — set price later via <b>Price Structure</b>. Scheme via Scheme Update.</p></div></div>' +
      '<form id="b-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="custBox" class="sheet-status"></div>' +
        '<h4 class="sheet-h4">Customer & Booking</h4>' +
        '<div class="form-stack">' +
          '<label class="field"><span>Customer Name</span><input id="customerName" disabled /></label>' +
          '<label class="field"><span>Model</span><input id="model" disabled /></label>' +
          '<label class="field"><span>Variant</span><input id="variant" disabled /></label>' +
          '<label class="field"><span>Booking Date *</span><input id="bookingDate" type="date" required /></label>' +
          '<label class="field"><span>Booking Amount *</span><input id="bookingAmount" type="number" min="1" step="0.01" required /></label>' +
          '<label class="field"><span>Payment Mode</span><select id="bookingPaymentMode"></select></label>' +
          '<label class="field"><span>Executive</span><input id="executive" disabled /></label>' +
        '</div>' +
        '<div id="exchangeSection" style="display:none">' +
          '<h4 class="sheet-h4">Exchange</h4>' +
          '<label class="field"><span>Brand</span><input id="oldVehicleBrand" /></label>' +
          '<label class="field"><span>Model</span><input id="oldVehicleModel" /></label>' +
          '<label class="field"><span>Registration</span><input id="oldVehicleRegistration" /></label>' +
          '<label class="field"><span>Evaluated Value</span><input id="evaluatedExchangeValue" type="number" min="0" step="0.01" value="0" /></label>' +
          '<label class="field"><span>Final Exchange Value</span><input id="finalExchangeValue" type="number" min="0" step="0.01" value="0" /></label>' +
        '</div>' +
        '<div id="financeSection" style="display:none">' +
          '<h4 class="sheet-h4">Finance</h4>' +
          '<label class="field"><span>Financer</span><input id="financer" /></label>' +
          '<label class="field"><span>Loan Amount</span><input id="loanAmount" type="number" min="0" step="0.01" value="0" /></label>' +
          '<label class="field"><span>Down Payment</span><input id="downPayment" type="number" min="0" step="0.01" value="0" /></label>' +
        '</div>' +
        '<div style="margin-top:16px;"><button type="submit" class="btn" id="btn-save">Save Booking</button></div>' +
      '</form>';

    U.fillSelect(el('bookingPaymentMode'), payModes.map(function (m) {
      return { value: m, label: m };
    }), false);
    setVal('bookingDate', U.todayISO());

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'booking',
      onChange: function (id, lead) { onLeadPicked(id, lead); }
    });

    document.getElementById('b-form').addEventListener('submit', async function (e) {
      e.preventDefault();
      await doSave(picker);
    });
  }

  function applyLead(p) {
    if (!p) return;
    setVal('customerName', p.customerName || '');
    setVal('model', p.model || p.interestedModel || '');
    setVal('variant', p.variant || '');
    setVal('executive', p.executive || '');
    if (p.bookingAmount) setVal('bookingAmount', p.bookingAmount);
    var box = el('custBox');
    if (box && p.leadId) box.textContent = 'Lead: ' + p.leadId + ' | Status: ' + (p.accountStatus || 'Active');
    var exReq = String(p.exchangeRequired || '').toLowerCase();
    var finReq = String(p.financeRequired || '').toLowerCase();
    var exSec = el('exchangeSection'); if (exSec) exSec.style.display = exReq === 'yes' ? 'block' : 'none';
    var finSec = el('financeSection'); if (finSec) finSec.style.display = finReq === 'yes' ? 'block' : 'none';
  }

  async function onLeadPicked(id, lead) {
    applyLead(lead || {});
    if (!id) return;
    try {
      var res = await CRM_API.getBookingContext(id);
      if (res && res.success !== false) {
        var l = res.lead || {};
        applyLead(Object.assign({}, lead || {}, l, {
          model: l.model || l.interestedModel || (lead && lead.model),
          exchangeRequired: l.exchangeRequired || (lead && lead.exchangeRequired),
          financeRequired: l.financeRequired || (lead && lead.financeRequired)
        }));
        if (res.today) setVal('bookingDate', res.today);
      }
    } catch (e) { /* keep picker data */ }
  }

  async function doSave(picker) {
    var U = CRM_UTIL;
    var leadId = picker.getLeadId();
    if (!leadId) { U.toast('Select a lead', 'warn'); return; }
    var amt = Number(el('bookingAmount').value);
    if (!(amt > 0)) { U.toast('Booking amount must be greater than zero', 'warn'); return; }
    if (!String(el('bookingPaymentMode').value || '').trim()) {
      U.toast('Select payment mode', 'warn'); return;
    }
    var payload = {
      leadId: leadId,
      variant: el('variant').value,
      bookingDate: el('bookingDate').value,
      bookingAmount: el('bookingAmount').value,
      bookingPaymentMode: el('bookingPaymentMode').value,
      executive: el('executive').value,
      oldVehicleBrand: el('oldVehicleBrand') ? el('oldVehicleBrand').value : '',
      oldVehicleModel: el('oldVehicleModel') ? el('oldVehicleModel').value : '',
      oldVehicleRegistration: el('oldVehicleRegistration') ? el('oldVehicleRegistration').value : '',
      evaluatedExchangeValue: el('evaluatedExchangeValue') ? el('evaluatedExchangeValue').value : '',
      finalExchangeValue: el('finalExchangeValue') ? el('finalExchangeValue').value : '',
      financer: el('financer') ? el('financer').value : '',
      loanAmount: el('loanAmount') ? el('loanAmount').value : '',
      downPayment: el('downPayment') ? el('downPayment').value : '',
      deferPrice: true
    };
    try {
      var res = await U.withLoading(CRM_API.convertBooking(payload));
      var msg = (res && res.message) || 'Booking saved';
      if (!(res && res.data && res.data.alreadyBooked)) {
        msg += ' — next: Price Structure';
      }
      U.toast(msg, 'ok');
      if (picker.reload) await picker.reload();
    } catch (err) { U.handleApiError(err); }
  }

  CRM_BOOT.register('booking', { title: 'Booking', init: init });
})();
