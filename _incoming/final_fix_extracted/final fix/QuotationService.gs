/**
 * QuotationService.gs — Euler Motors Dealership CRM v2.2
 *
 * Deal Format / Quotation Generator
 * ──────────────────────────────────
 * Generates a structured price quote for any Model + Variant:
 *   • Ex Showroom — fixed from Price Master (non-editable)
 *   • All other charges — editable per deal (pre-filled from Price Master)
 *   • Scheme — from Scheme Master (consumer discount, exchange bonus, etc.)
 *   • Calculations — Gross, Total Discount, Customer Payable
 *   • OEM Share — amount dealer recovers from OEM per scheme circular
 *   • Output — written to "Quotation Log" sheet + shown as formatted summary
 *
 * Menu entry: CRM → Generate Deal Quotation
 */

// ═══════════════════════════════════════════════════════════════════════════
//  PUBLIC SERVER FUNCTIONS (called via google.script.run)
// ═══════════════════════════════════════════════════════════════════════════

/** Returns models list from Price Master for dialog dropdowns. */
function getModelsForQuotation() {
  try {
    var data = getPricingRows_();
    var seen = {};
    var models = [];
    data.rows.forEach(function (row) {
      var rec = parsePricingRow_(data.headers, row, 0);
      if (!rec) return;
      var status = String(rec.status || 'active').toLowerCase();
      if (status !== 'active') return;
      var model = String(rec.model || '').trim();
      if (model && !seen[model]) { seen[model] = true; models.push(model); }
    });
    models.sort();
    return { success: true, models: models };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

/** Returns variants for a given model from Price Master. */
function getVariantsForQuotationModel(model) {
  try {
    model = String(model || '').trim();
    if (!model) return { success: true, variants: [] };
    var modelNorm = normalizePriceKey_(model);
    var data  = getPricingRows_();
    var seen  = {};
    var vars  = [];
    data.rows.forEach(function (row) {
      var rec = parsePricingRow_(data.headers, row, 0);
      if (!rec) return;
      var status = String(rec.status || 'active').toLowerCase();
      if (status !== 'active') return;
      if (rec.modelNorm !== modelNorm) return;
      var v = String(rec.variant || '').trim();
      if (v && !seen[v]) { seen[v] = true; vars.push(v); }
    });
    vars.sort();
    return { success: true, variants: vars };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

/** Returns Price Master + Scheme Master data for the quotation dialog. */
function getPriceAndSchemeForQuotation(model, variant, quoteDate) {
  try {
    model   = String(model   || '').trim();
    variant = String(variant || '').trim();
    quoteDate = quoteDate || nowDate_();
    if (!model || !variant) {
      return { success: false, message: 'Model and Variant are required.' };
    }

    // Price Master
    var breakup  = getCommercialBreakup_(model, variant, quoteDate);
    var price = formatPriceForClient_(breakup.price);

    // Scheme Master — returns rules object with per-component choices and OEM/Dealer shares
    var schemeRules = null;
    try {
      schemeRules = getSchemeOfferRulesForVehicle_(model, variant, quoteDate);
    } catch (se) {
      schemeRules = { rules: {} };
    }

    return {
      success:     true,
      price: {
        exShowroom:       price.exShowroom,
        insurance:        price.insurance,
        registrationRto:  price.registrationRto,
        accessories:      price.accessories,
        handlingCharges:  price.handlingCharges,
        trc:              price.trc,
        fastag:           price.fastag,
        extendedWarranty: price.extendedWarranty,
        otherCharges:     price.otherCharges,
        gstPercent:       price.gstPercent,
        tcsApplicable:    price.tcsApplicable,
        priceVersion:     price.priceVersion,
        effectiveFrom:    price.effectiveFrom
      },
      grossVehicleCost: breakup.grossVehicleCost,
      tcs:     breakup.tcs || 0,
      scheme:  schemeRules,
      today:   quoteDate
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

/**
 * OEM recovery for a quotation's selected offers — "what do I get back from OEM
 * after the OEM/dealer share split".
 *
 * Uses the SAME canonical splitter as a real booking (schemeShareSplitFor_), so a
 * quotation can never promise a recovery the booking won't deliver. The previous
 * client-side math added the FULL company share whenever any amount was picked,
 * which over-stated OEM recovery whenever the operator gave less than the full
 * scheme package.
 *
 * @return {{success:boolean, oemShare:number, dealerCost:number,
 *           totalDiscount:number, byComponent:Object, schemeMonth:string}}
 */
function getQuotationShareSplit(model, variant, quoteDate, offers) {
  try {
    offers = offers || {};
    var clean = {};
    ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus',
      'dsaDiscount', 'additionalDiscount'].forEach(function (k) {
      clean[k] = Math.max(0, Number(offers[k]) || 0);
    });
    var split = schemeShareSplitFor_(
      String(model || '').trim(),
      String(variant || '').trim(),
      quoteDate || nowDate_(),
      clean
    );
    var totalDiscount = 0;
    Object.keys(clean).forEach(function (k) { totalDiscount += clean[k]; });
    return {
      success: true,
      oemShare: round2_(split.companyTotal || 0),
      dealerCost: round2_(split.dealerTotal || 0),
      totalDiscount: round2_(totalDiscount),
      byComponent: split.byComponent || {},
      schemeMonth: split.schemeMonth || ''
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e), oemShare: 0, dealerCost: 0 };
  }
}

/**
 * DIAGNOSTIC — runs the exact Convert-to-Booking price path server-side and reports
 * precisely where it breaks. Exists because the dialog can only ever show
 * "Price Master lookup failed" when google.script.run itself fails, which hides the
 * real cause. Select a cell with a Lead ID (or leave any cell selected) and run
 * CRM ▸ Admin ▸ Diagnose Price Lookup.
 */
function menuDiagnosePriceLookup() {
  var ui = SpreadsheetApp.getUi();
  var lines = [];
  function say(s) { lines.push(s); }
  try {
    // 1. Which lead?
    var leadId = '';
    try {
      var cell = SpreadsheetApp.getActiveRange();
      var tok = cell ? String(cell.getDisplayValue() || '').trim() : '';
      if (/^LD\d+/i.test(tok)) leadId = tok;
    } catch (e) {}
    if (!leadId) {
      var resp = ui.prompt('Diagnose Price Lookup', 'Lead ID to test:', ui.ButtonSet.OK_CANCEL);
      if (resp.getSelectedButton() !== ui.Button.OK) return;
      leadId = String(resp.getResponseText() || '').trim();
    }
    if (!leadId) { ui.alert('No Lead ID given.'); return; }

    // 2. Lead present?
    var lead = null;
    try { lead = getLeadFromRegisterLight_(leadId); } catch (e) { say('Lead read ERROR: ' + e.message); }
    if (!lead) { ui.alert('Diagnose Price Lookup', 'Lead ' + leadId + ' not found in Lead Register.', ui.ButtonSet.OK); return; }
    say('Lead: ' + leadId);
    say('  Model   = "' + (lead.interestedModel || '') + '"');
    say('  Variant = "' + (lead.variant || '') + '"');

    // 3. PRICE MASTER sheet state
    var ss = getSpreadsheet_();
    var pm = ss.getSheetByName(CRM.SHEETS.PRICE_MASTER);
    if (!pm) { say(''); say('PRICE MASTER sheet: MISSING  <-- run Admin > Import Price Master 2026'); }
    else {
      say('');
      say('PRICE MASTER: found, lastRow=' + pm.getLastRow() + ', lastCol=' + pm.getLastColumn());
      try {
        var rows = getPricingRows_();
        say('  header cols : ' + (rows.headers || []).length);
        say('  data rows   : ' + (rows.rows || []).length);
      } catch (e) { say('  getPricingRows_ ERROR: ' + e.message); }
    }

    // 4. The actual lookup
    say('');
    var out = null;
    try {
      out = getPriceForBookingContext(leadId, lead.variant || '', nowDate_());
    } catch (e) {
      say('getPriceForBookingContext THREW (uncaught): ' + e.message);
      say('  -> this is why the dialog shows the generic failure.');
    }
    if (out) {
      if (out.success) {
        say('LOOKUP OK');
        say('  Ex Showroom  = ' + out.price.exShowroom);
        say('  Price Version= ' + out.priceVersion);
        say('  Payable      = ' + (out.totals && out.totals.customerPayable));
        say('');
        say('Server side is WORKING. If the dialog still fails, it is the browser:');
        say('  close the whole sheet tab, reopen, retry (cached dialog).');
      } else {
        say('LOOKUP FAILED');
        say('  errorCode = ' + out.errorCode);
        say('  message   = ' + out.message);
      }
    }
    try { logAudit_('DIAGNOSE_PRICE', lines.join(' | ')); } catch (e) {}
    ui.alert('Diagnose Price Lookup', lines.join('\n'), ui.ButtonSet.OK);
  } catch (err) {
    ui.alert('Diagnostic failed: ' + err.message + '\n\n' + lines.join('\n'));
  }
}

/**
 * Create the Quotation Log sheet if missing, using CRM.QUOTATION_LOG.COLS as the
 * single header authority (the header list used to be duplicated inline here,
 * which would drift from Config). Called at setup and before every save, so the
 * sheet exists even before the first quotation is raised.
 */
function ensureQuotationLogSheet_() {
  var ss = getSpreadsheet_();
  var name = (CRM.SHEETS && CRM.SHEETS.QUOTATION_LOG) || 'Quotation Log';
  var cols = (CRM.QUOTATION_LOG && CRM.QUOTATION_LOG.COLS) || [];
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  if (cols.length) {
    var hr = (CRM.QUOTATION_LOG && CRM.QUOTATION_LOG.HEADER_ROW) || 1;
    var existing = sheet.getRange(hr, 1, 1, cols.length).getValues()[0];
    var needs = false;
    for (var i = 0; i < cols.length; i++) {
      if (String(existing[i] || '').trim() !== cols[i]) { needs = true; break; }
    }
    if (needs) {
      sheet.getRange(hr, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
      sheet.setFrozenRows(hr);
    }
  }
  return sheet;
}

/** Saves a completed quotation to the Quotation Log sheet and returns the quote ID. */
function saveQuotationFromDialog(data) {
  try {
    data = data || {};
    var model   = String(data.model   || '').trim();
    var variant = String(data.variant || '').trim();
    if (!model || !variant) {
      return { success: false, message: 'Model and Variant are required.' };
    }

    var sheet = ensureQuotationLogSheet_();

    var quoteId   = generateId_('QT');
    var quoteDate = formatDate_(data.quoteDate) || nowDate_();

    var exShowroom        = Number(data.exShowroom        || 0);
    var insurance         = Number(data.insurance         || 0);
    var registrationRto   = Number(data.registrationRto   || 0);
    var accessories       = Number(data.accessories       || 0);
    var handlingCharges   = Number(data.handlingCharges   || 0);
    var trc               = Number(data.trc               || 0);
    var fastag            = Number(data.fastag            || 0);
    var extendedWarranty  = Number(data.extendedWarranty  || 0);
    var otherCharges      = Number(data.otherCharges      || 0);
    var gross             = exShowroom + insurance + registrationRto + accessories +
                            handlingCharges + trc + fastag + extendedWarranty + otherCharges;

    var consumerDiscount  = Number(data.consumerDiscount  || 0);
    var exchangeBonus     = Number(data.exchangeBonus     || 0);
    var loyaltyBonus      = Number(data.loyaltyBonus      || 0);
    var referralBonus     = Number(data.referralBonus     || 0);
    var dsaBonus          = Number(data.dsaBonus          || 0);
    var additionalDiscount = Number(data.additionalDiscount || 0);
    var totalDiscount     = consumerDiscount + exchangeBonus + loyaltyBonus +
                            referralBonus + dsaBonus + additionalDiscount;
    var exchangeValue     = Number(data.exchangeValue || 0);
    var customerPayable   = Math.max(0, gross - totalDiscount - exchangeValue);
    var oemShare          = Number(data.oemShare || 0); // passed from client calculation

    var newRow = Math.max(sheet.getLastRow() + 1, 2);
    var rowData = [
      quoteId, quoteDate,
      String(data.customerName || ''), String(data.mobile || ''),
      model, variant,
      exShowroom, insurance, registrationRto, accessories, handlingCharges,
      trc, fastag, extendedWarranty, otherCharges, gross,
      consumerDiscount, exchangeBonus, loyaltyBonus, referralBonus,
      dsaBonus, additionalDiscount, totalDiscount,
      customerPayable, oemShare,
      String(data.financeRequired || 'No'),
      exchangeValue,
      String(data.financer || ''),
      String(data.narration || ''),
      getUserEmail_(),
      String(data.priceVersion || '')
    ];
    sheet.getRange(newRow, 1, 1, rowData.length).setValues([rowData]);

    // Format currency columns
    try { sheet.getRange(newRow, 7, 1, 10).setNumberFormat('#,##0.00'); } catch (fe) {}
    try { sheet.getRange(newRow, 17, 1, 9).setNumberFormat('#,##0.00'); } catch (fe2) {}

    return {
      success:         true,
      quoteId:         quoteId,
      gross:           gross,
      totalDiscount:   totalDiscount,
      customerPayable: customerPayable,
      oemShare:        oemShare,
      message:         'Quotation ' + quoteId + ' saved.'
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  DIALOG
// ═══════════════════════════════════════════════════════════════════════════

function showDealQuotationDialog_() {
  var today = nowDate_();
  var html  = createDialogOutput_(
    dialogBaseCss_('#2E7D32') +
    '<style>' +
    'input:disabled{background:#f0f4f8;color:#333;cursor:not-allowed}' +
    '.sec{font-weight:700;font-size:13px;margin:14px 0 4px;padding-top:10px;border-top:1px solid #ddd}' +
    '.calc{background:#E8F5E9;border-radius:4px;padding:10px;margin-top:10px}' +
    '.calc label{margin-top:6px}.calc input{background:#fff}' +
    '.oem{background:#E3F2FD;border-radius:4px;padding:10px;margin-top:8px}' +
    '.hint{font-size:11px;color:#666;margin:2px 0 6px}' +
    '.locked-note{font-size:11px;color:#c62828;font-style:italic}' +
    '.scheme-row{display:flex;align-items:center;margin:4px 0}' +
    '.scheme-row label{flex:1;margin:0;font-size:12px}' +
    '.scheme-row select{width:160px;padding:4px;font-size:13px}' +
    '</style>' +
    '<h3 style="margin:0 0 8px">Deal Quotation</h3>' +

    '<label>Quote Date</label>' +
    '<input id="quoteDate" type="date" value="' + today + '" />' +
    '<label>Customer Name</label><input id="customerName" placeholder="Optional" />' +
    '<label>Mobile</label><input id="mobile" placeholder="Optional" maxlength="10" />' +

    '<div class="sec">Vehicle</div>' +
    '<label>Model *</label>' +
    '<select id="model"><option value="">— Loading —</option></select>' +
    '<label>Variant *</label>' +
    '<select id="variant"><option value="">— Select Model first —</option></select>' +
    '<div id="priceStatus" style="font-size:12px;color:#1565C0;margin:6px 0;min-height:18px"></div>' +

    '<div class="sec">Price Structure</div>' +
    '<span class="locked-note">Ex Showroom is fixed from Price Master and cannot be changed.</span>' +
    '<label>Ex Showroom</label>' +
    '<input id="exShowroom" type="number" disabled="disabled" />' +
    '<div class="hint">Fields below are pre-filled from Price Master. Edit as needed for this deal.</div>' +
    '<label>Insurance</label><input id="insurance" type="number" min="0" step="0.01" />' +
    '<label>Registration / RTO</label><input id="registrationRto" type="number" min="0" step="0.01" />' +
    '<label>Accessories</label><input id="accessories" type="number" min="0" step="0.01" />' +
    '<label>Handling</label><input id="handlingCharges" type="number" min="0" step="0.01" />' +
    '<label>TRC</label><input id="trc" type="number" min="0" step="0.01" />' +
    '<label>Fastag</label><input id="fastag" type="number" min="0" step="0.01" />' +
    '<label>Extended Warranty</label><input id="extendedWarranty" type="number" min="0" step="0.01" />' +
    '<label>Other Charges</label><input id="otherCharges" type="number" min="0" step="0.01" />' +

    '<div class="sec">Scheme / Discounts</div>' +
    '<div class="hint">Scheme amounts from Scheme Master. Additional Discount is manual.</div>' +
    '<div class="scheme-row"><label>Consumer Discount</label><select id="consumerDiscount"><option value="0">₹0</option></select></div>' +
    '<div class="scheme-row"><label>Exchange Bonus</label><select id="exchangeBonus"><option value="0">₹0</option></select></div>' +
    '<div class="scheme-row"><label>Loyalty Bonus</label><select id="loyaltyBonus"><option value="0">₹0</option></select></div>' +
    '<div class="scheme-row"><label>Referral Bonus</label><select id="referralBonus"><option value="0">₹0</option></select></div>' +
    '<div class="scheme-row"><label>DSA Bonus</label><select id="dsaBonus"><option value="0">₹0</option></select></div>' +
    '<label>Additional Discount (manual)</label>' +
    '<input id="additionalDiscount" type="number" min="0" step="0.01" value="0" />' +

    '<div class="sec">Exchange / Finance</div>' +
    '<label>Exchange Value (deduct from payable)</label>' +
    '<input id="exchangeValue" type="number" min="0" step="0.01" value="0" />' +
    '<label>Finance Required</label>' +
    '<select id="financeRequired"><option value="No">No</option><option value="Yes">Yes</option></select>' +
    '<div id="financerBlock" style="display:none">' +
    '<label>Financer Name</label><input id="financer" />' +
    '</div>' +

    '<div class="calc">' +
    '<div style="font-weight:700;margin-bottom:6px">Deal Summary</div>' +
    '<label>Gross Vehicle Cost</label><input id="grossVehicleCost" disabled="disabled" />' +
    '<label>Total Discount</label><input id="totalDiscount" disabled="disabled" />' +
    '<label>Customer Payable</label><input id="customerPayable" disabled="disabled" style="font-weight:700;font-size:15px" />' +
    '</div>' +

    '<div class="oem">' +
    '<div style="font-weight:700;margin-bottom:6px">OEM Share (What You Recover from OEM)</div>' +
    '<div class="hint">Sum of Company Share from Scheme Master for each applied scheme component.</div>' +
    '<label>OEM Share</label><input id="oemShare" disabled="disabled" />' +
    '<label>Dealer Cost (you absorb)</label><input id="dealerCost" disabled="disabled" />' +
    '</div>' +

    '<label style="margin-top:12px">Narration / Notes</label>' +
    '<input id="narration" placeholder="Optional notes for this quote" />' +

    '<button class="btn" id="btn" type="button" onclick="doSave()">Save Quotation</button>' +

    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(quotationDialogClientJs_()),
    480, 900
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Generate Deal Quotation');
}

function quotationDialogClientJs_() {
  return [
    'var PRICE_DATA={};',
    'var SCHEME_DATA={rules:{}};',
    'var OFFER_IDS=["consumerDiscount","exchangeBonus","loyaltyBonus","referralBonus","dsaBonus"];',
    'var OEM_SHARE_BY_ID={};',   // key = offer id, value = OEM share amount for selected value

    'function el(id){return document.getElementById(id);}',
    'function num(v){var n=Number(v);return isFinite(n)?n:0;}',
    'function setVal(id,v){var x=el(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function fmt(n){try{return "₹"+Number(n||0).toLocaleString("en-IN",{minimumFractionDigits:0,maximumFractionDigits:0});}catch(e){return "₹"+String(Math.round(n||0));}}',
    'function pstat(m,color){var s=el("priceStatus");if(!s)return;s.textContent=m;s.style.color=color||"#1565C0";}',

    // Keep ex showroom always disabled
    '(function(){var x=el("exShowroom");if(x)x.disabled=true;})();',

    // Calculation
    'function calc(){',
    '  var gross=num(el("exShowroom")&&el("exShowroom").value)+num(el("insurance")&&el("insurance").value)+num(el("registrationRto")&&el("registrationRto").value)+num(el("accessories")&&el("accessories").value)+num(el("handlingCharges")&&el("handlingCharges").value)+num(el("trc")&&el("trc").value)+num(el("fastag")&&el("fastag").value)+num(el("extendedWarranty")&&el("extendedWarranty").value)+num(el("otherCharges")&&el("otherCharges").value);',
    '  setVal("grossVehicleCost",gross.toFixed(2));',
    '  var disc=0;',
    '  OFFER_IDS.forEach(function(id){disc+=num(el(id)&&el(id).value);});',
    '  disc+=num(el("additionalDiscount")&&el("additionalDiscount").value);',
    '  setVal("totalDiscount",disc.toFixed(2));',
    '  var exch=num(el("exchangeValue")&&el("exchangeValue").value);',
    '  var payable=Math.max(0,gross-disc-exch);',
    '  setVal("customerPayable",payable.toFixed(2));',
    '  refreshOemShare();',
    '}',
    // OEM recovery is computed SERVER-side by the same splitter a real booking uses,
    // so the quote can never promise a recovery the booking will not deliver.
    'var OEM_TIMER=null;',
    'function refreshOemShare(){',
    '  clearTimeout(OEM_TIMER);',
    '  OEM_TIMER=setTimeout(function(){',
    '    var offers={};',
    '    OFFER_IDS.forEach(function(id){var k=(id==="dsaBonus")?"dsaDiscount":id;offers[k]=num(el(id)&&el(id).value);});',
    '    var model=el("model")?el("model").value:"";',
    '    var variant=el("variant")?el("variant").value:"";',
    '    var d=el("quoteDate")?el("quoteDate").value:"";',
    '    google.script.run',
    '      .withSuccessHandler(function(r){',
    '        if(!r||r.success===false){setVal("oemShare","0.00");return;}',
    '        setVal("oemShare",Number(r.oemShare||0).toFixed(2));',
    '        var dc=el("dealerCost");if(dc)dc.value=Number(r.dealerCost||0).toFixed(2);',
    '      })',
    '      .withFailureHandler(function(){setVal("oemShare","0.00");})',
    '      .getQuotationShareSplit(model,variant,d,offers);',
    '  },250);',
    '}',

    // Build scheme dropdown for one offer id
    'function buildSchemeSelect(id,rule){',
    '  var sel=el(id);if(!sel)return;',
    '  var choices=(rule&&rule.choices&&rule.choices.length)?rule.choices.slice():[0];',
    '  var out=[0];var seen={0:1};',
    '  choices.forEach(function(c){var n=Number(c);if(!isNaN(n)&&!seen[n]){seen[n]=1;out.push(n);}});',
    '  out.sort(function(a,b){return a-b;});',
    '  sel.innerHTML=out.map(function(n){return \'<option value="\'+n+\'">\'+("₹"+Number(n).toLocaleString("en-IN"))+\'</option>\';}).join("");',
    '  sel.value="0";',
    '  // Store OEM share: first dealer share from choices (company share per unit)',
    '  OEM_SHARE_BY_ID[id]=num(rule&&rule.companyShare)||0;',
    '}',

    // Apply scheme rules
    'function applyScheme(rules){',
    '  SCHEME_DATA=rules||{rules:{}};',
    '  var r=SCHEME_DATA.rules||{};',
    '  var schemeIds={dsaBonus:"dsaDiscount"};', // map dialog id → scheme key if different
    '  OFFER_IDS.forEach(function(id){',
    '    var key=schemeIds[id]||id;',
    '    var rule=r[key]||{};',
    '    if(rule.allowed){',
    '      buildSchemeSelect(id,rule);',
    '      var sel=el(id);if(sel)sel.disabled=false;',
    '    } else {',
    '      var sel=el(id);if(sel){sel.innerHTML=\'<option value="0">₹0</option>\';sel.disabled=true;}',
    '      OEM_SHARE_BY_ID[id]=0;',
    '    }',
    '  });',
    '  calc();',
    '}',

    // Apply price from server
    'function applyPrice(p){',
    '  p=p||{};',
    '  setVal("exShowroom",p.exShowroom||0);',
    '  setVal("insurance",p.insurance||0);',
    '  setVal("registrationRto",p.registrationRto||0);',
    '  setVal("accessories",p.accessories||0);',
    '  setVal("handlingCharges",p.handlingCharges||0);',
    '  setVal("trc",p.trc||0);',
    '  setVal("fastag",p.fastag||0);',
    '  setVal("extendedWarranty",p.extendedWarranty||0);',
    '  setVal("otherCharges",p.otherCharges||0);',
    '  PRICE_DATA=p;',
    '  calc();',
    '}',

    // Load price + scheme on model/variant selection
    'function loadPriceAndScheme(){',
    '  var model=el("model")&&el("model").value;',
    '  var variant=el("variant")&&el("variant").value;',
    '  var date=el("quoteDate")&&el("quoteDate").value;',
    '  if(!model||!variant){pstat("Select Model and Variant to load price.","#666");return;}',
    '  pstat("Loading Price Master for "+variant+" \\u2026","#1565C0");',
    '  google.script.run',
    '    .withSuccessHandler(function(res){',
    '      if(!res||res.success===false){',
    // NOTE: parentheses matter. "x "+(res&&res.message)||"fallback" parses as
    // ("x "+(res&&res.message))||"fallback" — always truthy, so the fallback never
    // fired and a null response rendered literally as "null".
    '        var m=(res&&res.message)?res.message:(res?"Price lookup failed":"No response from server (reload the sheet tab).");',
    '        pstat("\\u2717 "+m,"#c62828");return;',
    '      }',
    '      applyPrice(res.price||{});',
    '      if(res.scheme)applyScheme(res.scheme);',
    '      pstat("\\u2713 "+((res.price&&res.price.priceVersion)||"Price loaded")+' +
    '            " — Ex ₹"+Number((res.price&&res.price.exShowroom)||0).toLocaleString("en-IN")+" (fixed)","#2e7d32");',
    '    })',
    '    .withFailureHandler(function(e){pstat("\\u2717 "+(e&&e.message||e),"#c62828");})',
    '    .getPriceAndSchemeForQuotation(model,variant,date);',
    '}',

    // Load variants when model changes
    'function loadVariants(callback){',
    '  var model=el("model")&&el("model").value;',
    '  var sel=el("variant");if(!sel)return;',
    '  if(!model){sel.innerHTML=\'<option value="">— Select Model first —</option>\';return;}',
    '  sel.innerHTML=\'<option value="">Loading…</option>\';',
    '  google.script.run',
    '    .withSuccessHandler(function(res){',
    '      if(!res||!res.variants){sel.innerHTML=\'<option value="">No variants found</option>\';return;}',
    '      sel.innerHTML=\'<option value="">— Select Variant —</option>\'+',
    '        res.variants.map(function(v){return \'<option value="\'+v+\'">\'+v+\'</option>\';}).join("");',
    '      if(typeof callback==="function")callback();',
    '    })',
    '    .withFailureHandler(function(e){sel.innerHTML=\'<option value="">Error loading variants</option>\';',
    '    }).getVariantsForQuotationModel(model);',
    '}',

    // Load models on open
    'google.script.run',
    '  .withSuccessHandler(function(res){',
    '    var sel=el("model");if(!sel)return;',
    '    if(!res||!res.models){sel.innerHTML=\'<option value="">No models in Price Master</option>\';return;}',
    '    sel.innerHTML=\'<option value="">— Select Model —</option>\'+',
    '      res.models.map(function(m){return \'<option value="\'+m+\'">\'+m+\'</option>\';}).join("");',
    '  })',
    '  .withFailureHandler(function(e){var s=el("model");if(s)s.innerHTML=\'<option value="">Error: \'+e.message+\'</option>\';})',
    '  .getModelsForQuotation();',

    'el("model").addEventListener("change",function(){loadVariants();el("variant").value="";});',
    'el("variant").addEventListener("change",loadPriceAndScheme);',
    'el("quoteDate").addEventListener("change",loadPriceAndScheme);',

    // Finance block toggle
    'el("financeRequired").addEventListener("change",function(){',
    '  var show=this.value==="Yes";',
    '  el("financerBlock").style.display=show?"block":"none";',
    '});',

    // Recalculate on any input change
    'document.addEventListener("input",function(e){',
    '  if(e.target&&e.target.id!=="customerName"&&e.target.id!=="mobile"&&e.target.id!=="narration")calc();',
    '});',
    'document.addEventListener("change",function(e){',
    '  if(e.target&&e.target.className==="scheme-row")calc();',
    '  else if(e.target&&["consumerDiscount","exchangeBonus","loyaltyBonus","referralBonus","dsaBonus"].indexOf(e.target.id)>=0)calc();',
    '});',

    // Save
    'function doSave(){',
    '  var model=el("model")&&el("model").value;',
    '  var variant=el("variant")&&el("variant").value;',
    '  if(!model){alert("Select a Model.");return;}',
    '  if(!variant){alert("Select a Variant.");return;}',
    '  if(!(num(el("exShowroom")&&el("exShowroom").value)>0)){alert("Ex Showroom price not loaded. Pick a valid Model and Variant.");return;}',
    '  var b=el("btn");b.disabled=true;b.textContent="Saving...";',
    '  var done=false;function reset(){b.disabled=false;b.textContent="Save Quotation";}',
    '  var t=setTimeout(function(){if(done)return;done=true;reset();softTimeoutAlert("Quotation save");},60000);',
    '  var payload={',
    '    quoteDate:el("quoteDate")?el("quoteDate").value:"",',
    '    customerName:el("customerName")?el("customerName").value:"",',
    '    mobile:el("mobile")?el("mobile").value:"",',
    '    model:model,variant:variant,',
    '    exShowroom:el("exShowroom")?el("exShowroom").value:0,',
    '    insurance:el("insurance")?el("insurance").value:0,',
    '    registrationRto:el("registrationRto")?el("registrationRto").value:0,',
    '    accessories:el("accessories")?el("accessories").value:0,',
    '    handlingCharges:el("handlingCharges")?el("handlingCharges").value:0,',
    '    trc:el("trc")?el("trc").value:0,',
    '    fastag:el("fastag")?el("fastag").value:0,',
    '    extendedWarranty:el("extendedWarranty")?el("extendedWarranty").value:0,',
    '    otherCharges:el("otherCharges")?el("otherCharges").value:0,',
    '    consumerDiscount:el("consumerDiscount")?el("consumerDiscount").value:0,',
    '    exchangeBonus:el("exchangeBonus")?el("exchangeBonus").value:0,',
    '    loyaltyBonus:el("loyaltyBonus")?el("loyaltyBonus").value:0,',
    '    referralBonus:el("referralBonus")?el("referralBonus").value:0,',
    '    dsaBonus:el("dsaBonus")?el("dsaBonus").value:0,',
    '    additionalDiscount:el("additionalDiscount")?el("additionalDiscount").value:0,',
    '    exchangeValue:el("exchangeValue")?el("exchangeValue").value:0,',
    '    financeRequired:el("financeRequired")?el("financeRequired").value:"No",',
    '    financer:el("financer")?el("financer").value:"",',
    '    oemShare:el("oemShare")?el("oemShare").value:0,',
    '    narration:el("narration")?el("narration").value:"",',
    '    priceVersion:PRICE_DATA.priceVersion||""',
    '  };',
    '  google.script.run',
    '    .withSuccessHandler(function(res){',
    '      if(done)return;done=true;clearTimeout(t);reset();',
    '      if(!res||res.success===false){alert((res&&res.message)||"Save failed");return;}',
    '      var msg="Quotation Saved!\\n\\n"',
    '        +"Quote ID: "+res.quoteId+"\\n"',
    '        +"Gross Vehicle Cost: "+fmt(res.gross)+"\\n"',
    '        +"Total Discount: "+fmt(res.totalDiscount)+"\\n"',
    '        +"Customer Payable: "+fmt(res.customerPayable)+"\\n"',
    '        +"OEM Share (you recover): "+fmt(res.oemShare)+"\\n\\n"',
    '        +"Saved to Quotation Log sheet.";',
    '      alert(msg);',
    '      kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '    })',
    '    .withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(parseServerError(e));})',
    '    .saveQuotationFromDialog(payload);',
    '}'
  ].join('\n');
}

/** Menu handler. */
function menuDealQuotation() {
  try {
    showDealQuotationDialog_();
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error opening Deal Quotation: ' + e.message);
  }
}
