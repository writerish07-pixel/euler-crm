/**
 * Price Structure — set/correct deal price after booking (no price at booking).
 */
(function () {
  'use strict';

  var PS = { tcsRate: 0, tcs: 0, paid: 0, booking: 0 };

  function el(id) { return document.getElementById(id); }
  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function setVal(id, v) {
    var x = el(id);
    if (x) x.value = (v === undefined || v === null) ? '' : v;
  }

  function calc() {
    var gross = num(el('exShowroom').value) + num(el('insurance').value) + num(el('registrationRto').value) +
      num(el('accessories').value) + num(el('handlingCharges').value) + num(el('trc').value) +
      num(el('fastag').value) + num(el('extendedWarranty').value) + num(el('otherCharges').value);
    var tcsRule = String(el('tcsApplicable').value || 'No').toLowerCase() === 'yes';
    var payable = Math.max(0, gross + (tcsRule ? num(PS.tcs) : 0));
    setVal('customerPayable', payable.toFixed(2));
    setVal('outstanding', Math.max(0, payable - num(PS.booking) - num(PS.paid)).toFixed(2));
  }

  function fillFromPrice(p) {
    p = p || {};
    setVal('exShowroom', p.exShowroom || 0);
    setVal('insurance', p.insurance || 0);
    setVal('registrationRto', p.registrationRto || 0);
    setVal('accessories', p.accessories || 0);
    setVal('handlingCharges', p.handlingCharges || 0);
    setVal('trc', p.trc || 0);
    setVal('fastag', p.fastag || 0);
    setVal('extendedWarranty', p.extendedWarranty || 0);
    setVal('otherCharges', p.otherCharges || 0);
    setVal('gstPercent', p.gstPercent || 0);
    setVal('tcsApplicable', p.tcsApplicable || 'No');
    calc();
  }

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Price Structure</h1>' +
      '<p>Set or correct price for a booked lead. Booking itself has no fixed price.</p></div></div>' +
      '<form id="ps-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="psStatus" class="sheet-status">Pick a booked lead…</div>' +
        '<label class="field"><span>Ex Showroom (Price Master)</span><input id="exShowroom" type="number" min="0" step="0.01" disabled /></label>' +
        '<p class="sheet-hint">Other charges pre-fill from Price Master — edit for this deal.</p>' +
        '<label class="field"><span>Insurance</span><input id="insurance" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Registration / RTO</span><input id="registrationRto" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Accessories</span><input id="accessories" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Handling</span><input id="handlingCharges" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>TRC</span><input id="trc" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Fastag</span><input id="fastag" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Extended Warranty</span><input id="extendedWarranty" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>Other Charges</span><input id="otherCharges" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>GST %</span><input id="gstPercent" type="number" min="0" step="0.01" /></label>' +
        '<label class="field"><span>TCS Applicable</span><select id="tcsApplicable"><option>No</option><option>Yes</option></select></label>' +
        '<label class="field"><span>Customer Payable (preview)</span><input id="customerPayable" disabled /></label>' +
        '<label class="field"><span>Outstanding (preview)</span><input id="outstanding" disabled /></label>' +
        '<div style="margin-top:16px;"><button type="submit" class="btn">Save Price Structure</button></div>' +
      '</form>';

    var form = document.getElementById('ps-form');
    form.addEventListener('input', calc);

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'payment',
      onChange: function (id) { if (id) loadCtx(id); }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var leadId = picker.getLeadId();
      if (!leadId) { U.toast('Select a lead', 'warn'); return; }
      if (!(num(el('exShowroom').value) > 0)) {
        U.toast('Ex Showroom must be > 0 (needs Price Master for model/variant)', 'warn');
        return;
      }
      try {
        var res = await U.withLoading(CRM_API.savePriceStructure({
          leadId: leadId,
          insurance: el('insurance').value,
          registrationRto: el('registrationRto').value,
          accessories: el('accessories').value,
          handlingCharges: el('handlingCharges').value,
          trc: el('trc').value,
          fastag: el('fastag').value,
          extendedWarranty: el('extendedWarranty').value,
          otherCharges: el('otherCharges').value,
          gstPercent: el('gstPercent').value,
          tcsApplicable: el('tcsApplicable').value
        }));
        U.toast((res && res.message) || 'Price structure saved', 'ok');
      } catch (err) { U.handleApiError(err); }
    });
  }

  async function loadCtx(id) {
    var U = CRM_UTIL;
    var st = el('psStatus');
    st.textContent = 'Loading…';
    try {
      var res = await U.withLoading(CRM_API.getPriceStructureContext(id));
      if (!res || res.success === false) {
        st.textContent = (res && res.message) || 'Failed to load';
        return;
      }
      PS.paid = num(res.paymentsReceived);
      PS.booking = num(res.bookingAmount);
      if (res.tcsRate != null) PS.tcsRate = num(res.tcsRate);
      if (res.tcs != null) PS.tcs = num(res.tcs);
      var snap = res.snapshot || {};
      if (num(snap.exShowroom) > 0) {
        fillFromPrice(snap);
        st.textContent = 'Loaded saved price — edit and save.';
      } else if (res.price && num(res.price.exShowroom) > 0) {
        if (res.tcs != null) PS.tcs = num(res.tcs);
        fillFromPrice(res.price);
        st.textContent = 'Pre-filled from Price Master — adjust if needed.';
      } else {
        st.textContent = 'No Price Master row — ensure model/variant has a price.';
      }
    } catch (err) {
      U.handleApiError(err);
      st.textContent = err.message || 'Error';
    }
  }

  CRM_BOOT.register('price-structure', { title: 'Price Structure', init: init });
})();
