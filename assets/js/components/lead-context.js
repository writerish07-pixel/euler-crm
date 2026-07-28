/**
 * Lead context card — enterprise summary for every workflow step.
 * Never dumps raw JSON. Outstanding always shown from server values.
 */
(function (global) {
  'use strict';

  function pick(obj, keys, fallback) {
    if (!obj) return fallback;
    for (var i = 0; i < keys.length; i++) {
      if (obj[keys[i]] != null && obj[keys[i]] !== '') return obj[keys[i]];
    }
    return fallback;
  }

  function normalize(raw) {
    raw = raw || {};
    var lead = raw.lead || raw;
    var price = raw.price || {};
    var totals = raw.totals || {};

    var customerPayable = Number(
      pick(totals, ['customerPayable'], null) != null ? totals.customerPayable :
      pick(raw, ['customerPayable', 'payableBeforeOffer'], 0)
    );
    var paid = Number(pick(raw, ['paymentsReceived', 'paid'], 0));
    var bookingAmt = Number(pick(raw, ['bookingAmount'], pick(lead, ['bookingAmount'], 0)));
    var outstanding = Number(
      pick(totals, ['outstanding'], null) != null ? totals.outstanding :
      pick(raw, ['outstanding'], NaN)
    );
    if (!isFinite(outstanding)) {
      outstanding = Math.max(0, customerPayable - (paid > 0 ? paid : bookingAmt));
    }

    return {
      leadId: pick(lead, ['leadId', 'id'], ''),
      customerName: pick(lead, ['customerName', 'name'], ''),
      mobile: pick(lead, ['mobile'], ''),
      status: pick(lead, ['currentStatus', 'status'], ''),
      model: pick(lead, ['interestedModel', 'model'], ''),
      variant: pick(lead, ['variant'], ''),
      executive: pick(lead, ['executive', 'bookingExecutive'], ''),
      source: pick(lead, ['leadSource', 'source'], ''),
      bookingAmount: bookingAmt,
      paymentsReceived: paid,
      customerPayable: customerPayable,
      outstanding: outstanding,
      exShowroom: Number(pick(price, ['exShowroom'], pick(totals, ['exShowroom'], 0))),
      insurance: Number(pick(price, ['insurance'], 0)),
      registrationRto: Number(pick(price, ['registrationRto', 'rto'], 0)),
      tcs: Number(pick(totals, ['tcs'], pick(raw, ['tcs'], pick(price, ['tcs'], 0)))),
      grossInvoice: Number(pick(totals, ['grossInvoiceAmount', 'grossVehicleCost'], 0)),
      benefitMode: pick(raw, ['benefitMode'], ''),
      oemEligible: Number(pick(raw, ['oemEligible'], 0)),
      customerBenefitPassed: Number(pick(raw, ['customerBenefitPassed'], 0)),
      priceError: raw.priceError || '',
      priceVersion: pick(price, ['priceVersion', 'version'], '')
    };
  }

  function metric(label, value, emphasize) {
    return '<div class="ctx-metric' + (emphasize ? ' emphasize' : '') + '">' +
      '<div class="ctx-metric-label">' + label + '</div>' +
      '<div class="ctx-metric-value">' + value + '</div></div>';
  }

  function row(label, value) {
    if (value == null || value === '') return '';
    return '<div class="ctx-row"><span>' + label + '</span><strong>' + value + '</strong></div>';
  }

  /**
   * @param {HTMLElement} mount
   * @param {object} raw - API response (booking / scheme / delivery / etc.)
   * @param {object} [options]
   */
  function render(mount, raw, options) {
    options = options || {};
    var U = global.CRM_UTIL;
    if (!mount) return null;
    if (!raw) {
      mount.innerHTML = '<div class="ctx-card empty">Select a lead to load context</div>';
      return null;
    }

    var n = normalize(raw);
    var err = n.priceError
      ? '<div class="ctx-warn">' + U.escapeHtml(n.priceError) + '</div>'
      : '';

    var moneyRows = '';
    if (n.exShowroom) moneyRows += row('Ex-Showroom', U.escapeHtml(U.formatINR(n.exShowroom)));
    if (n.insurance) moneyRows += row('Insurance', U.escapeHtml(U.formatINR(n.insurance)));
    if (n.registrationRto) moneyRows += row('RTO / Registration', U.escapeHtml(U.formatINR(n.registrationRto)));
    if (n.tcs) moneyRows += row('TCS', U.escapeHtml(U.formatINR(n.tcs)));
    if (n.grossInvoice) moneyRows += row('Gross Invoice', U.escapeHtml(U.formatINR(n.grossInvoice)));
    if (n.customerPayable) moneyRows += row('Customer Payable', U.escapeHtml(U.formatINR(n.customerPayable)));
    if (n.bookingAmount) moneyRows += row('Booking Advance', U.escapeHtml(U.formatINR(n.bookingAmount)));
    moneyRows += row('Payments Received', U.escapeHtml(U.formatINR(n.paymentsReceived)));
    if (n.benefitMode) moneyRows += row('Benefit Mode', U.escapeHtml(n.benefitMode));
    if (n.oemEligible) moneyRows += row('OEM Eligible', U.escapeHtml(U.formatINR(n.oemEligible)));
    if (n.customerBenefitPassed) moneyRows += row('Benefit Passed', U.escapeHtml(U.formatINR(n.customerBenefitPassed)));
    if (n.priceVersion) moneyRows += row('Price Version', U.escapeHtml(n.priceVersion));

    mount.innerHTML =
      '<div class="ctx-card">' +
        '<div class="ctx-head">' +
          '<div>' +
            '<div class="ctx-title">' + U.escapeHtml(n.customerName || '—') + '</div>' +
            '<div class="ctx-sub">' +
              U.escapeHtml([n.leadId, n.mobile, n.model, n.variant].filter(Boolean).join(' · ')) +
            '</div>' +
          '</div>' +
          '<div class="ctx-status">' + U.escapeHtml(n.status || '—') + '</div>' +
        '</div>' +
        err +
        '<div class="ctx-metrics">' +
          metric('Current Outstanding', U.escapeHtml(U.formatINR(n.outstanding)), true) +
          metric('Customer Payable', U.escapeHtml(U.formatINR(n.customerPayable))) +
          metric('Received', U.escapeHtml(U.formatINR(n.paymentsReceived))) +
          metric('Booking Advance', U.escapeHtml(U.formatINR(n.bookingAmount))) +
        '</div>' +
        '<div class="ctx-grid">' +
          '<div>' +
            row('Executive', U.escapeHtml(n.executive)) +
            row('Source', U.escapeHtml(n.source)) +
            row('Model', U.escapeHtml(n.model)) +
            row('Variant', U.escapeHtml(n.variant)) +
          '</div>' +
          '<div>' + moneyRows + '</div>' +
        '</div>' +
        (options.footer ? '<div class="ctx-footer">' + options.footer + '</div>' : '') +
      '</div>';

    return n;
  }

  function clear(mount, message) {
    if (!mount) return;
    mount.innerHTML = '<div class="ctx-card empty">' +
      (global.CRM_UTIL ? global.CRM_UTIL.escapeHtml(message || 'Select a lead to load context') : (message || 'Select a lead')) +
      '</div>';
  }

  global.CRM_CONTEXT = { render: render, clear: clear, normalize: normalize };
})(window);
