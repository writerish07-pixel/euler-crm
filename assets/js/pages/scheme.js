/**
 * Scheme Update page â€” mirrors Spreadsheet CRM â†’ Scheme Update dialog exactly:
 * - Offer selects from Scheme Master choices
 * - Components not in master for this model are HIDDEN (N/A)
 * - Additional Discount = free number entry
 * - Benefit Mode Full / Partial / No + partial pass amounts
 * - Read-only: Eligible Total, OEM Eligible, Benefit Passed, Dealer Retained,
 *   Customer Payable, Booking Advance, Payments, Outstanding
 * - Save payload matches updateLeadFromDialog
 */
(function () {
  'use strict';

  var OFFER_IDS = ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus', 'dsaDiscount', 'additionalDiscount'];
  var OEM_OFFER_IDS = ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus', 'dsaDiscount'];
  var OFFER_LABELS = {
    consumerDiscount: 'Consumer Discount',
    exchangeBonus: 'Exchange Bonus',
    loyaltyBonus: 'Loyalty Bonus',
    referralBonus: 'Referral Bonus',
    dsaDiscount: 'DSA Bonus',
    additionalDiscount: 'Additional Discount'
  };

  var CTX = {
    hasBooking: false,
    payableBase: 0,
    paid: 0,
    bookingAmount: 0,
    pendingOffers: null,
    model: '',
    variant: '',
    oemEligible: 0,
    marginGrossInclGst: 0,
    marginGst: 0,
    marginNetExGst: 0
  };
  var SCHEME_RULES = { rules: {} };

  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }
  function fmtInr(n) {
    try { return Number(n || 0).toLocaleString('en-IN'); } catch (e) { return String(n || 0); }
  }

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Scheme Update</h1>' +
      '<p>Same feeding style as Spreadsheet CRM â†’ Scheme Update. Scheme fields without a master row for this model are hidden.</p></div></div>' +
      '<form id="s-form" class="card card-pad sheet-form" style="max-width:560px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div id="updateStatus" class="sheet-status">Pick a booked lead to load scheme limitsâ€¦</div>' +

        '<h4 class="sheet-h4">Commercial Offer / Scheme (Eligible)</h4>' +
        '<div id="offerHint" class="sheet-hint">Pick amounts (â‚¹) from Scheme Master. Fields with no scheme for this model stay hidden.</div>' +
        '<div id="offerFields"></div>' +

        '<label class="field"><span>Eligible Scheme Total</span><input id="totalDiscount" disabled /></label>' +
        '<label class="field"><span>OEM Scheme Eligible</span><input id="oemEligible" disabled /></label>' +
        '<label class="field"><span>Dealer Margin Gross (Incl GST)</span><input id="dealerMarginGross" disabled /></label>' +
        '<label class="field"><span>Dealer Margin GST (5%)</span><input id="dealerMarginGst" disabled /></label>' +
        '<label class="field"><span>Dealer Margin Net (Ex GST)</span><input id="dealerMarginNet" disabled /></label>' +

        '<h4 class="sheet-h4">Owner Decision â€” Customer Benefit</h4>' +
        '<p class="sheet-hint">Customer Payable reduces only by Benefit Passed. OEM Eligible stays available for owner receivable.</p>' +
        '<div class="field benefit-radios">' +
          '<label><input type="radio" name="benefitMode" value="Full Benefit" checked /> Full Benefit</label>' +
          '<label><input type="radio" name="benefitMode" value="Partial Benefit" /> Partial Benefit</label>' +
          '<label><input type="radio" name="benefitMode" value="No Benefit" /> No Benefit</label>' +
        '</div>' +
        '<div id="partialWrap" style="display:none">' +
          '<div class="sheet-hint">Enter how much of each scheme is passed. Company share is applied first on the server.</div>' +
          '<div id="partialComponents"></div>' +
        '</div>' +

        '<label class="field"><span>Customer Benefit Passed</span><input id="benefitPassedShow" disabled /></label>' +
        '<label class="field"><span>Dealer Benefit Retained</span><input id="dealerRetained" disabled /></label>' +
        '<label class="field"><span>Customer Payable</span><input id="customerPayable" disabled /></label>' +
        '<label class="field"><span>Booking Advance (already received)</span><input id="bookingAdvanceShow" disabled /></label>' +
        '<label class="field"><span>Other Payments Received</span><input id="paymentsReceivedShow" disabled /></label>' +
        '<label class="field"><span>Outstanding (Payable âˆ’ Advance âˆ’ Payments)</span><input id="outstanding" disabled /></label>' +

        '<div style="margin-top:16px;"><button type="submit" class="btn" id="btn-save">Save Scheme</button></div>' +
      '</form>';

    buildOfferFields();
    CRM_CONTEXT.clear(document.getElementById('ctx'));

    var form = document.getElementById('s-form');
    form.addEventListener('change', onFormChange);
    form.addEventListener('input', onFormChange);

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'scheme',
      onChange: function (id, lead) { onLeadPicked(id, lead); }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      await doSave(picker);
    });
  }

  function buildOfferFields() {
    var box = document.getElementById('offerFields');
    box.innerHTML = OFFER_IDS.map(function (id) {
      if (id === 'additionalDiscount') {
        return '<div class="field offer-wrap" data-offer="' + id + '" id="wrap_' + id + '">' +
          '<label id="lbl_' + id + '"><span>Additional Discount (enter amount)</span></label>' +
          '<input class="offer" id="' + id + '" name="' + id + '" type="number" min="0" step="0.01" value="0" placeholder="Type amount â‚¹" />' +
          '</div>';
      }
      return '<div class="field offer-wrap" data-offer="' + id + '" id="wrap_' + id + '" hidden>' +
        '<label id="lbl_' + id + '"><span>' + OFFER_LABELS[id] + '</span></label>' +
        '<select class="offer" id="' + id + '" name="' + id + '"><option value="0">â‚¹0</option></select>' +
        '</div>';
    }).join('');
    box.insertAdjacentHTML('beforeend',
      '<div class="field offer-wrap" data-offer="oemExtraSupport" id="wrap_oemExtraSupport">' +
      '<label id="lbl_oemExtraSupport"><span>OEM Extra Support (case-wise)</span></label>' +
      '<input class="offer" id="oemExtraSupport" name="oemExtraSupport" type="number" min="0" step="0.01" value="0" placeholder="Type amount ₹" />' +
      '</div>'
    );
  }

  function el(id) { return document.getElementById(id); }
  function setVal(id, v) {
    var x = el(id);
    if (x) x.value = (v === undefined || v === null) ? '' : v;
  }
  function getBenefitMode() {
    var radios = document.getElementsByName('benefitMode');
    for (var i = 0; i < radios.length; i++) if (radios[i].checked) return radios[i].value;
    return 'Full Benefit';
  }
  function setBenefitMode(mode) {
    mode = mode || 'Full Benefit';
    var radios = document.getElementsByName('benefitMode');
    for (var i = 0; i < radios.length; i++) radios[i].checked = (radios[i].value === mode);
    var wrap = el('partialWrap');
    if (wrap) wrap.style.display = (mode === 'Partial Benefit') ? '' : 'none';
  }

  function eligibleTotal() {
    var total = 0;
    OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var x = el(id);
      if (wrap && wrap.hidden) return;
      if (x && !x.disabled) total += num(x.value);
    });
    return total;
  }

  function oemEligibleClient() {
    var t = 0;
    OEM_OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var x = el(id);
      if (wrap && wrap.hidden) return;
      if (x && !x.disabled) t += num(x.value);
    });
    return t;
  }

  function calcOutstandingClient(payable) {
    var paid = num(CTX.paid);
    var booking = num(CTX.bookingAmount);
    if (paid > 0.009) return Math.max(0, payable - paid);
    return Math.max(0, payable - booking);
  }

  function renderPartialComponents() {
    var box = el('partialComponents');
    if (!box) return;
    var html = '';
    OEM_OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var x = el(id);
      if (wrap && wrap.hidden) return;
      var amt = x && !x.disabled ? num(x.value) : 0;
      if (amt <= 0) return;
      var pid = 'pass_' + id;
      var curEl = el(pid);
      var cur = curEl ? num(curEl.value) : amt;
      if (cur > amt) cur = amt;
      html += '<label class="field"><span>' + OFFER_LABELS[id] + ' â€” eligible â‚¹' + fmtInr(amt) + '</span>' +
        '<input type="number" class="passAmt" id="' + pid + '" data-comp="' + id + '" min="0" max="' + amt + '" step="0.01" value="' + cur + '" /></label>';
    });
    box.innerHTML = html || '<div class="sheet-hint">No scheme amounts selected above.</div>';
  }

  function passedBreakup() {
    var mode = getBenefitMode();
    var bk = {};
    OEM_OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var x = el(id);
      var amt = (wrap && !wrap.hidden && x && !x.disabled) ? num(x.value) : 0;
      if (amt <= 0) { bk[id] = 0; return; }
      if (mode === 'Full Benefit') bk[id] = amt;
      else if (mode === 'No Benefit') bk[id] = 0;
      else {
        var pi = el('pass_' + id);
        var v = pi ? num(pi.value) : 0;
        if (v < 0) v = 0;
        if (v > amt) v = amt;
        bk[id] = v;
      }
    });
    return bk;
  }

  function resolvePassed(eligible) {
    var bk = passedBreakup();
    var t = 0;
    Object.keys(bk).forEach(function (k) { t += num(bk[k]); });
    return Math.max(0, Math.min(t, eligible));
  }

  function retainedIncomeClient() {
    var bk = passedBreakup();
    var t = 0;
    OEM_OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var x = el(id);
      if (wrap && wrap.hidden) return;
      var amt = x && !x.disabled ? num(x.value) : 0;
      if (amt <= 0) return;
      var passed = num(bk[id]);
      if (passed < 0) passed = 0;
      if (passed > amt) passed = amt;
      var rule = SCHEME_RULES.rules && SCHEME_RULES.rules[id];
      var cs = rule ? num(rule.companyShare) : 0;
      var ds = rule ? num(rule.dealerShare) : 0;
      if (cs > 0 || ds > 0) {
        var cFull = Math.min(cs, amt);
        var cPass = Math.min(cs, passed);
        var dPass = Math.min(ds, Math.max(0, passed - cPass));
        t += (cFull - cPass) - dPass;
      } else {
        t += Math.max(0, amt - passed);
      }
    });
    return t;
  }

  function calcOffer() {
    var all = eligibleTotal();
    var oem = oemEligibleClient();
    var dealerPool = Math.max(0, all - oem);
    var passedOem = resolvePassed(oem);
    var totalPass = passedOem + dealerPool;
    setVal('totalDiscount', all.toFixed(2));
    setVal('oemEligible', oem.toFixed(2));
    setVal('dealerMarginGross', num(CTX.marginGrossInclGst).toFixed(2));
    setVal('dealerMarginGst', num(CTX.marginGst).toFixed(2));
    setVal('dealerMarginNet', num(CTX.marginNetExGst).toFixed(2));
    setVal('benefitPassedShow', passedOem.toFixed(2));
    setVal('dealerRetained', Number(retainedIncomeClient()).toFixed(2));
    if (CTX.hasBooking) {
      var payable = Math.max(0, num(CTX.payableBase) - totalPass);
      setVal('customerPayable', payable.toFixed(2));
      setVal('bookingAdvanceShow', num(CTX.bookingAmount).toFixed(2));
      setVal('paymentsReceivedShow', num(CTX.paid).toFixed(2));
      setVal('outstanding', calcOutstandingClient(payable).toFixed(2));
    }
  }

  function fillChoices(id, rule, current) {
    var sel = el(id);
    if (!sel || sel.tagName !== 'SELECT') return 0;
    var list = (rule && rule.choices && rule.choices.length) ? rule.choices.slice() : [0];
    var out = [];
    var seen = {};
    list.forEach(function (item) {
      var n = num(item);
      if (n >= 0 && !seen[n]) { seen[n] = 1; out.push(n); }
    });
    var cur = num(current);
    if (cur > 0 && !seen[cur]) { seen[cur] = 1; out.push(cur); }
    if (!out.length) out = [0];
    out.sort(function (a, b) { return a - b; });
    sel.innerHTML = out.map(function (v) {
      return '<option value="' + v + '">' + (v === 0 ? 'â‚¹0' : ('â‚¹' + fmtInr(v))) + '</option>';
    }).join('');
    sel.value = String(seen[cur] ? cur : 0);
    return out.length;
  }

  function countKeys(o) {
    var n = 0;
    if (!o) return 0;
    for (var k in o) if (Object.prototype.hasOwnProperty.call(o, k)) n++;
    return n;
  }

  /**
   * Spreadsheet behaviour:
   * - allowed + max > 0 â†’ SHOW select with choices
   * - !allowed â†’ HIDE field (N/A for this model)
   * - additionalDiscount â†’ always SHOW number input
   */
  function applySchemeRules(rulesObj) {
    SCHEME_RULES = rulesObj || { rules: {} };
    var rules = SCHEME_RULES.rules || {};
    var pending = CTX.pendingOffers || {};
    var open = 0;
    var parts = [];

    OFFER_IDS.forEach(function (id) {
      var rule = rules[id] || {};
      var wrap = el('wrap_' + id);
      var sel = el(id);
      var lbl = el('lbl_' + id);
      var base = OFFER_LABELS[id] || id;
      var max = num(rule.maxAmount);
      var allowed = (id === 'additionalDiscount') ? true : !!rule.allowed;

      if (id === 'additionalDiscount') {
        if (wrap) wrap.hidden = false;
        var addMax = max || 50000;
        var curAdd = num(pending[id]);
        if (curAdd < 0) curAdd = 0;
        if (curAdd > addMax) curAdd = addMax;
        if (sel) {
          sel.disabled = false;
          sel.min = '0';
          sel.max = String(addMax);
          sel.value = String(curAdd);
          sel.title = rule.hint || ('Type any amount up to â‚¹' + fmtInr(addMax));
        }
        if (lbl) lbl.innerHTML = '<span>' + base + ' (enter amount, max â‚¹' + fmtInr(addMax) + ')</span>';
        open++;
        parts.push(base + ': type up to ' + fmtInr(addMax));
        return;
      }

      // Hide scheme components not in master for this model (exact Sheet intent)
      if (!allowed || !(max > 0)) {
        if (wrap) wrap.hidden = true;
        if (sel) { sel.value = '0'; sel.disabled = true; }
        if (lbl) lbl.innerHTML = '<span>' + base + ' (N/A)</span>';
        return;
      }

      if (wrap) wrap.hidden = false;
      var nOpts = fillChoices(id, rule, pending[id]);
      if (sel) {
        sel.disabled = false;
        sel.style.background = (nOpts > 1) ? '' : '#f5f5f5';
        sel.title = rule.hint || 'Pick an amount from Scheme Master';
      }
      if (lbl) lbl.innerHTML = '<span>' + base + ' (max â‚¹' + fmtInr(max) + ')</span>';
      open++;
      parts.push(base + ': max ' + fmtInr(max));
    });

    var hint = el('offerHint');
    if (hint) {
      var fam = SCHEME_RULES.modelFamily || SCHEME_RULES.model || CTX.model || '';
      var mon = SCHEME_RULES.schemeMonth || '';
      var schemeOpen = open > 1 || (open === 1 && parts[0] && parts[0].indexOf('Additional') < 0);
      // open counts additional always â€” check OEM visibility
      var anyOem = OEM_OFFER_IDS.some(function (id) {
        var w = el('wrap_' + id);
        return w && !w.hidden;
      });
      if (anyOem) {
        hint.textContent = 'Scheme matched: ' + fam + (mon ? ' Â· ' + mon : '') + '. ' + parts.slice(0, 4).join(' | ');
        hint.style.color = '#2e7d32';
      } else {
        hint.textContent = 'No Scheme Master row for ' + (fam || 'this model') + (mon ? ' in ' + mon : '') +
          ' â€” scheme fields hidden. Additional Discount: type any amount.';
        hint.style.color = '#c62828';
      }
    }
    renderPartialComponents();
    calcOffer();
  }

  function onFormChange(e) {
    var t = e.target;
    if (!t) return;
    if (t.name === 'benefitMode') {
      setBenefitMode(t.value);
      renderPartialComponents();
      calcOffer();
      return;
    }
    if (t.classList && (t.classList.contains('offer') || t.classList.contains('passAmt'))) {
      if (t.classList.contains('passAmt') && num(t.value) > num(t.max)) t.value = t.max;
      if (t.classList.contains('offer')) renderPartialComponents();
      calcOffer();
    }
  }

  async function onLeadPicked(id, lead) {
    var U = CRM_UTIL;
    var st = el('updateStatus');
    if (!id) {
      CRM_CONTEXT.clear(document.getElementById('ctx'));
      if (st) st.textContent = 'Pick a booked lead to load scheme limitsâ€¦';
      return;
    }
    if (st) st.textContent = 'Loading scheme limitsâ€¦';
    CTX.model = (lead && (lead.model || lead.interestedModel)) || '';
    CTX.variant = (lead && lead.variant) || '';
    CTX.hasBooking = false;
    CTX.pendingOffers = null;

    try {
      var res = await U.withLoading(CRM_API.getSchemeContext(id));
      applyUpdateCtx(res);
      CRM_CONTEXT.render(document.getElementById('ctx'), res, {
        footer: 'Outstanding below updates as you change scheme / benefit mode (same math as Sheet dialog).'
      });
    } catch (err) {
      U.handleApiError(err);
      if (st) st.textContent = 'Could not load lead: ' + (err.message || err);
      try {
        var rules = await CRM_API.getSchemeRules({ leadId: id });
        applySchemeRules(rules);
      } catch (e2) {
        applySchemeRules({ rules: {} });
      }
    }
  }

  function applyUpdateCtx(res) {
    var st = el('updateStatus');
    if (!res || res.success === false) {
      if (st) st.textContent = (res && res.message) || 'Failed to load lead';
      return;
    }
    var l = res.lead || {};
    var o = res.offer || {};
    CTX.hasBooking = (res.hasBooking !== false) ||
      !!num(res.payableBeforeOffer) ||
      String(l.currentStatus || '').toLowerCase() === 'booked' ||
      String(l.currentStatus || '').toLowerCase() === 'delivered' ||
      num(l.bookingAmount) > 0;
    CTX.payableBase = num(res.payableBeforeOffer);
    CTX.paid = num(res.paymentsReceived);
    CTX.bookingAmount = num(l.bookingAmount || res.bookingAmount);
    CTX.oemEligible = num(res.oemEligible);
    CTX.model = l.interestedModel || l.model || CTX.model || '';
    CTX.variant = l.variant || CTX.variant || '';
    CTX.pendingOffers = {
      consumerDiscount: o.consumerDiscount || 0,
      exchangeBonus: o.exchangeBonus || 0,
      loyaltyBonus: o.loyaltyBonus || 0,
      referralBonus: o.referralBonus || 0,
      dsaDiscount: o.dsaDiscount || 0,
      additionalDiscount: o.additionalDiscount || 0,
      oemExtraSupport: o.oemExtraSupport || 0
    };
    CTX.marginGrossInclGst = num(res.dealerMarginGrossInclGst);
    CTX.marginGst = num(res.dealerMarginGst);
    CTX.marginNetExGst = num(res.dealerMarginNetExGst);
    setVal('oemExtraSupport', num(o.oemExtraSupport || res.oemExtraSupport || 0));
    setBenefitMode(res.benefitMode || 'Full Benefit');
    if (st) {
      st.textContent = 'Lead: ' + (l.leadId || '') + ' | ' + (CTX.model || '') + ' / ' + (CTX.variant || '') +
        (CTX.hasBooking ? ' | Booked' : '');
    }

    if (res.schemeRules && res.schemeRules.rules && countKeys(res.schemeRules.rules)) {
      applySchemeRules(res.schemeRules);
    } else if (SCHEME_RULES && SCHEME_RULES.rules && countKeys(SCHEME_RULES.rules)) {
      applySchemeRules(SCHEME_RULES);
    } else {
      // load rules async
      CRM_API.getSchemeRules({ leadId: l.leadId }).then(applySchemeRules).catch(function () {
        applySchemeRules({ rules: {} });
      });
    }
    calcOffer();
  }

  function validateOffersClient() {
    var rules = (SCHEME_RULES && SCHEME_RULES.rules) || {};
    var hasMaster = (SCHEME_RULES.matchedComponents || []).length > 0;
    var lines = [];
    OFFER_IDS.forEach(function (id) {
      var wrap = el('wrap_' + id);
      var inp = el(id);
      if (!inp || (wrap && wrap.hidden)) return;
      var amt = num(inp.value);
      var rule = rules[id] || {};
      if (amt < 0) lines.push('- ' + OFFER_LABELS[id] + ': cannot be negative');
      if (id === 'additionalDiscount') {
        var addMax = num(rule.maxAmount) || 50000;
        if (amt > addMax) lines.push('- Additional Discount: max â‚¹' + fmtInr(addMax));
        return;
      }
      if (amt <= 0) return;
      if (!hasMaster) return;
      if (!rule.allowed || !(num(rule.maxAmount) > 0)) {
        lines.push('- ' + OFFER_LABELS[id] + ': not in Scheme Master â€” enter 0');
      } else if (amt > num(rule.maxAmount)) {
        lines.push('- ' + OFFER_LABELS[id] + ': max â‚¹' + fmtInr(rule.maxAmount));
      }
    });
    if (lines.length) {
      CRM_UTIL.toast('Please fix scheme fields:\n' + lines.join('\n'), 'warn');
      return false;
    }
    return true;
  }

  async function doSave(picker) {
    var U = CRM_UTIL;
    var leadId = picker.getLeadId();
    if (!leadId) { U.toast('Select a lead', 'warn'); return; }
    if (!CTX.hasBooking && !num(CTX.payableBase)) {
      if (!(await U.confirmDialog('This lead does not look booked. Save scheme anyway?', 'Scheme Update'))) return;
    }
    if (!validateOffersClient()) return;

    var mode = getBenefitMode();
    var eligible = eligibleTotal();
    var passed = resolvePassed(eligible);
    var d = {
      leadId: leadId,
      editCustomer: false,
      consumerDiscount: el('consumerDiscount') && !el('wrap_consumerDiscount').hidden ? el('consumerDiscount').value : '0',
      exchangeBonus: el('exchangeBonus') && !el('wrap_exchangeBonus').hidden ? el('exchangeBonus').value : '0',
      loyaltyBonus: el('loyaltyBonus') && !el('wrap_loyaltyBonus').hidden ? el('loyaltyBonus').value : '0',
      referralBonus: el('referralBonus') && !el('wrap_referralBonus').hidden ? el('referralBonus').value : '0',
      dsaDiscount: el('dsaDiscount') && !el('wrap_dsaDiscount').hidden ? el('dsaDiscount').value : '0',
      additionalDiscount: el('additionalDiscount') ? el('additionalDiscount').value : '0',
      oemExtraSupport: el('oemExtraSupport') ? el('oemExtraSupport').value : '0',
      benefitMode: mode,
      customerBenefitPassed: passed,
      benefitPassedBreakup: JSON.stringify(passedBreakup())
    };

    try {
      var res = await U.withLoading(CRM_API.updateScheme(d));
      U.toast((res && res.message) || 'Scheme updated', 'ok');
      if (picker.reload) await picker.reload();
      CRM_CONTEXT.clear(document.getElementById('ctx'), 'Scheme saved. Lead removed from this list. Continue on Payment / Delivery.');
      el('updateStatus').textContent = 'Scheme saved for ' + leadId;
    } catch (err) {
      U.handleApiError(err);
    }
  }

  CRM_BOOT.register('scheme', { title: 'Scheme', init: init });
})();
