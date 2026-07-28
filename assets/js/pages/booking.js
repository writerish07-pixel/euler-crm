/**
 * Convert to Booking â€” mirrors Spreadsheet CRM dialog field-for-field.
 * Display math only; ex-showroom locked from Price Master; server re-validates on save.
 */
(function () {
  'use strict';

  var BOOKING_CTX = { pricingLoaded: false, tcsRate: 0, tcs: 0 };

  function el(id) { return document.getElementById(id); }
  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function setVal(id, v) {
    var x = el(id);
    if (x) x.value = (v === undefined || v === null) ? '' : v;
  }
  function setValIf(id, v) {
    if (v === undefined || v === null || v === '') return;
    setVal(id, v);
  }
  function pstat(m) {
    var s = el('priceStatus');
    if (s) s.textContent = m;
  }

  async function init() {
    var U = CRM_UTIL;
    var masters = {};
    try { masters = await CRM_API.getMasters() || {}; } catch (e) {}
    var payModes = masters['Payment Modes'] || ['Cash', 'UPI', 'Card', 'Finance', 'Cheque', 'Bank Transfer'];

    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Convert to Booking</h1>' +
      '<p>Same feeding style as Spreadsheet CRM â†’ Convert to Booking.</p></div></div>' +
      '<form id="b-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div id="custBox" class="sheet-status"></div>' +

        '<h4 class="sheet-h4">Section 1 â€“ Customer & Booking</h4>' +
        '<div class="form-stack">' +
          '<label class="field"><span>Customer Name</span><input id="customerName" name="customerName" disabled /></label>' +
          '<label class="field"><span>Model</span><input id="model" name="model" disabled /></label>' +
          '<label class="field"><span>Variant</span><input id="variant" name="variant" disabled /></label>' +
          '<label class="field"><span>Booking Date *</span><input id="bookingDate" name="bookingDate" type="date" required /></label>' +
          '<label class="field"><span>Booking Amount *</span><input id="bookingAmount" name="bookingAmount" type="number" min="1" step="0.01" required /></label>' +
          '<label class="field"><span>Payment Mode (for booking amount)</span><select id="bookingPaymentMode" name="bookingPaymentMode"></select></label>' +
          '<label class="field"><span>Executive</span><input id="executive" name="executive" disabled /></label>' +
        '</div>' +
        '<p class="sheet-hint">Commercial offers (discounts / bonuses) are set in <b>Scheme Update</b> after booking.</p>' +

        '<div id="exchangeSection" style="display:none">' +
          '<h4 class="sheet-h4">Section 2 â€“ Exchange</h4>' +
          '<div class="form-stack">' +
            '<label class="field"><span>Brand</span><input id="oldVehicleBrand" name="oldVehicleBrand" /></label>' +
            '<label class="field"><span>Model</span><input id="oldVehicleModel" name="oldVehicleModel" /></label>' +
            '<label class="field"><span>Registration Number</span><input id="oldVehicleRegistration" name="oldVehicleRegistration" /></label>' +
            '<label class="field"><span>Evaluated Value</span><input id="evaluatedExchangeValue" name="evaluatedExchangeValue" type="number" min="0" step="0.01" value="0" /></label>' +
            '<label class="field"><span>Final Exchange Value</span><input id="finalExchangeValue" name="finalExchangeValue" type="number" min="0" step="0.01" value="0" /></label>' +
          '</div>' +
        '</div>' +

        '<div id="financeSection" style="display:none">' +
          '<h4 class="sheet-h4">Section 3 â€“ Finance</h4>' +
          '<div class="form-stack">' +
            '<label class="field"><span>Financer</span><input id="financer" name="financer" /></label>' +
            '<label class="field"><span>Loan Amount</span><input id="loanAmount" name="loanAmount" type="number" min="0" step="0.01" value="0" /></label>' +
            '<label class="field"><span>Down Payment</span><input id="downPayment" name="downPayment" type="number" min="0" step="0.01" value="0" /></label>' +
          '</div>' +
        '</div>' +

        '<h4 class="sheet-h4">Section 4 â€“ Price Structure (Price Master)</h4>' +
        '<div id="priceStatus" class="sheet-status">Pick a lead to load price from Price Masterâ€¦</div>' +
        '<div class="form-stack">' +
          '<label class="field"><span>Ex Showroom <span style="color:#c62828;font-size:11px">(fixed from Price Master)</span></span>' +
            '<input id="exShowroom" name="exShowroom" type="number" step="0.01" disabled /></label>' +
          '<div class="pm-note">Fields below are pre-filled from Price Master. Edit as needed for this deal.</div>' +
          '<label class="field"><span>Insurance</span><input id="insurance" name="insurance" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Registration / RTO</span><input id="registrationRto" name="registrationRto" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Accessories</span><input id="accessories" name="accessories" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Handling</span><input id="handlingCharges" name="handlingCharges" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>TRC</span><input id="trc" name="trc" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Fastag</span><input id="fastag" name="fastag" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Extended Warranty</span><input id="extendedWarranty" name="extendedWarranty" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>Other Charges</span><input id="otherCharges" name="otherCharges" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>GST %</span><input id="gstPercent" name="gstPercent" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>TCS Rule</span><input id="tcsApplicable" name="tcsApplicable" /></label>' +
          '<label class="field"><span>TCS</span><input id="tcs" name="tcs" disabled /></label>' +
          '<label class="field"><span>Price Version</span><input id="priceVersion" name="priceVersion" disabled /></label>' +
          '<label class="field"><span>Price Effective Date</span><input id="priceEffectiveDate" name="priceEffectiveDate" disabled /></label>' +
        '</div>' +

        '<h4 class="sheet-h4">Section 5 â€“ Calculation Engine</h4>' +
        '<div class="form-stack">' +
          '<label class="field"><span>Gross Vehicle Cost</span><input id="grossVehicleCost" disabled /></label>' +
          '<label class="field"><span>Gross Invoice</span><input id="grossInvoiceAmount" disabled /></label>' +
          '<label class="field"><span>Net Vehicle Cost</span><input id="netVehicleCost" disabled /></label>' +
          '<label class="field"><span>Customer Payable</span><input id="customerPayable" disabled /></label>' +
          '<label class="field"><span>Payments Received</span><input id="paymentsReceived" disabled /></label>' +
          '<label class="field"><span>Outstanding</span><input id="outstanding" disabled /></label>' +
        '</div>' +

        '<div style="margin-top:16px;"><button type="submit" class="btn" id="btn-save">Save Booking</button></div>' +
      '</form>';

    U.fillSelect(el('bookingPaymentMode'), payModes, false);
    el('bookingDate').value = U.todayISO();
    CRM_CONTEXT.clear(el('ctx'));

    ['insurance', 'registrationRto', 'accessories', 'handlingCharges', 'trc', 'fastag',
      'extendedWarranty', 'otherCharges', 'gstPercent', 'bookingAmount', 'finalExchangeValue'
    ].forEach(function (id) {
      el(id).addEventListener('input', calc);
    });

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

  function clearPriceFields() {
    ['exShowroom', 'insurance', 'registrationRto', 'accessories', 'handlingCharges', 'trc', 'fastag',
      'extendedWarranty', 'otherCharges', 'gstPercent', 'tcs', 'grossVehicleCost', 'grossInvoiceAmount',
      'netVehicleCost', 'customerPayable', 'outstanding'
    ].forEach(function (id) { setVal(id, ''); });
    setVal('tcsApplicable', 'No');
    setVal('priceVersion', '');
    setVal('priceEffectiveDate', '');
    BOOKING_CTX.pricingLoaded = false;
  }

  function calc() {
    var gross = num(el('exShowroom').value) + num(el('insurance').value) + num(el('registrationRto').value) +
      num(el('accessories').value) + num(el('handlingCharges').value) + num(el('trc').value) +
      num(el('fastag').value) + num(el('extendedWarranty').value) + num(el('otherCharges').value);
    setVal('grossVehicleCost', gross.toFixed(2));
    var tcsRule = String(el('tcsApplicable').value || 'No').toLowerCase() === 'yes';
    var tcs = (tcsRule && num(BOOKING_CTX.tcsRate) > 0) ? gross * num(BOOKING_CTX.tcsRate) : num(BOOKING_CTX.tcs || 0);
    if (tcsRule && num(BOOKING_CTX.tcs) > 0) tcs = num(BOOKING_CTX.tcs);
    setVal('tcs', tcs.toFixed(2));
    var grossInv = gross + tcs;
    setVal('grossInvoiceAmount', grossInv.toFixed(2));
    setVal('netVehicleCost', grossInv.toFixed(2));
    var exch = num(el('finalExchangeValue').value);
    var payable = grossInv - exch;
    setVal('customerPayable', payable.toFixed(2));
    var paid = num(el('paymentsReceived').value);
    var booking = num(el('bookingAmount').value);
    setVal('outstanding', Math.max(0, payable - booking - paid).toFixed(2));
  }

  function applyPriceObj(p, meta) {
    p = p || {};
    meta = meta || {};
    setVal('exShowroom', p.exShowroom || 0);
    if (!(num(el('insurance').value) > 0)) setVal('insurance', p.insurance || 0);
    if (!(num(el('registrationRto').value) > 0)) setVal('registrationRto', p.registrationRto || 0);
    if (!(num(el('accessories').value) > 0)) setVal('accessories', p.accessories || 0);
    if (!(num(el('handlingCharges').value) > 0)) setVal('handlingCharges', p.handlingCharges || 0);
    if (!(num(el('trc').value) > 0)) setVal('trc', p.trc || 0);
    if (!(num(el('fastag').value) > 0)) setVal('fastag', p.fastag || 0);
    if (!(num(el('extendedWarranty').value) > 0)) setVal('extendedWarranty', p.extendedWarranty || 0);
    if (!(num(el('otherCharges').value) > 0)) setVal('otherCharges', p.otherCharges || 0);
    if (!(num(el('gstPercent').value) > 0)) setVal('gstPercent', p.gstPercent || 0);
    if (!el('tcsApplicable').value) setVal('tcsApplicable', p.tcsApplicable || 'No');
    setVal('priceVersion', p.priceVersion || '');
    setVal('priceEffectiveDate', p.effectiveFrom || '');
    if (meta.tcsRate !== undefined) BOOKING_CTX.tcsRate = num(meta.tcsRate);
    if (meta.tcs !== undefined) BOOKING_CTX.tcs = num(meta.tcs);
    BOOKING_CTX.pricingLoaded = !!(p && p.priceVersion && num(p.exShowroom) > 0);
    if (BOOKING_CTX.pricingLoaded) {
      pstat('âœ“ Price Master: ' + p.priceVersion + ' â€” Ex â‚¹' + Number(p.exShowroom).toLocaleString('en-IN') + ' (fixed). Other charges editable.');
    } else {
      pstat('âœ— Price Master returned no usable price.');
    }
    calc();
  }

  function applyTotalsObj(t) {
    if (!t) return;
    if (t.grossVehicleCost != null) setVal('grossVehicleCost', Number(t.grossVehicleCost).toFixed(2));
    if (t.grossInvoiceAmount != null) setVal('grossInvoiceAmount', Number(t.grossInvoiceAmount).toFixed(2));
    if (t.customerPayable != null) setVal('customerPayable', Number(t.customerPayable).toFixed(2));
    if (t.outstanding != null) setVal('outstanding', Number(t.outstanding).toFixed(2));
    if (t.tcs != null) { BOOKING_CTX.tcs = num(t.tcs); setVal('tcs', Number(t.tcs).toFixed(2)); }
    calc();
  }

  function applyLeadCtx(ctx, pick) {
    ctx = ctx || {};
    pick = pick || {};
    var l = ctx.lead || {};
    var p = ctx.price || {};
    setValIf('customerName', l.customerName || pick.customerName || pick.name);
    setValIf('model', l.model || l.interestedModel || pick.model || pick.interestedModel);
    setValIf('variant', l.variant || pick.variant);
    setValIf('executive', l.executive || pick.executive);
    if (ctx.today) setVal('bookingDate', ctx.today);
    if (l.bookingAmount != null && l.bookingAmount !== '') setVal('bookingAmount', l.bookingAmount);
    if (ctx.paymentsReceived != null) setVal('paymentsReceived', ctx.paymentsReceived);
    if (ctx.tcsRate != null) BOOKING_CTX.tcsRate = num(ctx.tcsRate);
    if (ctx.tcs != null) BOOKING_CTX.tcs = num(ctx.tcs);

    var exReq = String(l.exchangeRequired || pick.exchangeRequired || '').toLowerCase();
    var finReq = String(l.financeRequired || pick.financeRequired || '').toLowerCase();
    el('exchangeSection').style.display = exReq === 'yes' ? 'block' : 'none';
    el('financeSection').style.display = finReq === 'yes' ? 'block' : 'none';

    var lid = l.leadId || pick.leadId;
    if (lid) el('custBox').textContent = 'Lead: ' + lid + ' | Status: ' + (l.currentStatus || pick.accountStatus || 'Active');

    if (p && p.priceVersion && num(p.exShowroom) > 0) {
      applyPriceObj(p, { tcsRate: ctx.tcsRate, tcs: ctx.tcs });
      if (ctx.totals) applyTotalsObj(ctx.totals);
    } else if (ctx.priceError) {
      pstat('âœ— ' + ctx.priceError);
    }
  }

  async function onLeadPicked(id, lead) {
    var U = CRM_UTIL;
    if (!id) {
      CRM_CONTEXT.clear(el('ctx'));
      clearPriceFields();
      return;
    }
    clearPriceFields();
    if (lead) {
      setVal('customerName', lead.customerName || lead.name || '');
      setVal('model', lead.interestedModel || lead.model || '');
      setVal('variant', lead.variant || '');
      setVal('executive', lead.executive || '');
      el('custBox').textContent = 'Lead: ' + id;
    }
    try {
      var ctx = await U.withLoading(CRM_API.getBookingContext(id));
      applyLeadCtx(ctx, lead || {});
      CRM_CONTEXT.render(el('ctx'), ctx);
      if (!BOOKING_CTX.pricingLoaded) {
        var price = await CRM_API.getPriceForBooking({
          leadId: id,
          variant: el('variant').value,
          bookingDate: el('bookingDate').value
        });
        if (price && price.success !== false) {
          applyPriceObj(price.price || {}, { tcsRate: price.tcsRate, tcs: price.tcs });
          if (price.totals) applyTotalsObj(price.totals);
        } else {
          pstat('âœ— ' + ((price && price.message) || 'Price Master lookup failed'));
        }
      }
    } catch (err) {
      U.handleApiError(err);
      CRM_CONTEXT.clear(el('ctx'), err.message);
    }
  }

  async function doSave(picker) {
    var U = CRM_UTIL;
    var leadId = picker.getLeadId();
    if (!leadId) { U.toast('Select a lead', 'warn'); return; }
    if (!BOOKING_CTX.pricingLoaded) {
      U.toast('No active price found for this Model + Variant in Price Master.', 'warn');
      return;
    }
    if (!String(el('bookingPaymentMode').value || '').trim()) {
      U.toast('Select payment mode for booking advance.', 'warn');
      return;
    }
    if (!(await U.confirmDialog('Save booking? Server will recalculate commercial totals.', 'Confirm booking'))) return;

    var payload = {
      leadId: leadId,
      variant: el('variant').value,
      bookingDate: el('bookingDate').value,
      bookingAmount: el('bookingAmount').value,
      bookingPaymentMode: el('bookingPaymentMode').value,
      executive: el('executive').value,
      oldVehicleBrand: el('oldVehicleBrand').value,
      oldVehicleModel: el('oldVehicleModel').value,
      oldVehicleRegistration: el('oldVehicleRegistration').value,
      evaluatedExchangeValue: el('evaluatedExchangeValue').value,
      finalExchangeValue: el('finalExchangeValue').value,
      financer: el('financer').value,
      loanAmount: el('loanAmount').value,
      downPayment: el('downPayment').value,
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
    };

    try {
      var res = await U.withLoading(CRM_API.convertBooking(payload));
      U.toast((res && res.message) || 'Booking saved', 'ok');
      if (picker.reload) await picker.reload();
      CRM_CONTEXT.clear(el('ctx'), 'Booking saved. Lead removed from this list (already booked). Open Scheme Update next.');
      clearPriceFields();
    } catch (err) {
      // Apps Script often finishes after client timeout â€” verify from server truth
      if (err && err.code === 'TIMEOUT') {
        try {
          var check = await CRM_API.getBookingContext(leadId);
          if (check && (check.alreadyBooked || (check.lead && Number(check.lead.bookingAmount || 0) > 0))) {
            U.toast('Booking was saved on the server (response timed out). Reloading correct figuresâ€¦', 'ok');
            applyLeadCtx(check, {});
            CRM_CONTEXT.render(el('ctx'), check);
            if (picker.reload) await picker.reload();
            return;
          }
        } catch (e2) { /* fall through */ }
      }
      U.handleApiError(err);
    }
  }

  CRM_BOOT.register('booking', { title: 'Booking', init: init });
})();
