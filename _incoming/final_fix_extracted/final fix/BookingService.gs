/**
 * BookingService – Convert active lead to booking.
 *
 * v2.2 changes (Convert to Booking dialog):
 *   ✔ Ex Showroom is ALWAYS from Price Master and is non-editable (locked).
 *   ✔ All other charges (Insurance, Registration, Accessories, Handling, TRC,
 *     Fastag, Extended Warranty, Other Charges, GST%, TCS Rule) are now editable
 *     by default — pre-filled from Price Master but fully adjustable.
 *   ✔ Owner Override checkbox removed from applyOwnerOverridePolicy — it now only
 *     controls whether exShowroom can be typed (always locked for non-owner).
 *   ✔ Server-side buildBookingSnapshotFromForm_: exShowroom always from Price Master;
 *     all other fields use client-submitted value with Price Master as fallback.
 *
 * Pricing contract (production):
 * - Browser NEVER looks up price locally (no PRICE_MAP).
 * - Browser ALWAYS calls public Apps Script endpoints.
 * - PRICE MASTER via PricingService is the only pricing authority.
 * - Save re-validates price server-side from PRICE MASTER.
 */

function showConvertToBookingDialog_() {
  var m = getMergedMasters_();
  var seedLeads = getActiveLeadsForPickerLight_({ activeOnly: true });
  var html = createDialogOutput_(
    dialogBaseCss_('#1565C0') + '<style>' + leadPickerCss_() + '</style>' +
    '<style>input:disabled,select:disabled{background:#f5f5f5;color:#333;cursor:not-allowed}</style>' +
    '<h3>Convert to Booking</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 8px;">Booking only — set price later via <b>CRM → Price Structure</b>. Scheme via <b>Scheme Update</b>.</p>' +
    leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true, label: 'Lead ID *' }) +
    '<div id="custBox" style="margin-top:8px;font-size:12px;color:#555"></div>' +

    '<h4 style="margin-top:14px">Customer & Booking</h4>' +
    '<label>Customer Name</label><input id="customerName" disabled="disabled" />' +
    '<label>Model</label><input id="model" disabled="disabled" />' +
    '<label>Variant</label><input id="variant" disabled="disabled" />' +
    '<label>Booking Date *</label><input id="bookingDate" type="date" />' +
    '<label>Booking Amount *</label><input id="bookingAmount" type="number" min="1" step="0.01" required="required" />' +
    '<label>Payment Mode (for booking amount)</label><select id="bookingPaymentMode">' + buildSelectOptionsHtml_(m['Payment Modes']) + '</select>' +
    '<label>Executive</label><input id="executive" disabled="disabled" />' +

    '<div id="exchangeSection" style="display:none">' +
    '<h4 style="margin-top:14px">Exchange</h4>' +
    '<label>Brand</label><input id="oldVehicleBrand" />' +
    '<label>Model</label><input id="oldVehicleModel" />' +
    '<label>Registration Number</label><input id="oldVehicleRegistration" />' +
    '<label>Evaluated Value</label><input id="evaluatedExchangeValue" type="number" min="0" step="0.01" value="0" />' +
    '<label>Final Exchange Value</label><input id="finalExchangeValue" type="number" min="0" step="0.01" value="0" />' +
    '</div>' +

    '<div id="financeSection" style="display:none">' +
    '<h4 style="margin-top:14px">Finance</h4>' +
    '<label>Financer</label><input id="financer" />' +
    '<label>Loan Amount</label><input id="loanAmount" type="number" min="0" step="0.01" value="0" />' +
    '<label>Down Payment</label><input id="downPayment" type="number" min="0" step="0.01" value="0" />' +
    '</div>' +

    '<button class="btn" id="btn" data-label="Save Booking" type="button" onclick="doSave()">Save Booking</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_('window.__LEAD_CACHE_SEEDED=' + jsonForHtml_(seedLeads) + ';') +
    htmlScript_(leadPickerClientJs_(true, 'booking')) +
    htmlScript_(bookingDialogClientJs_()),
    420,
    640
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Convert to Booking');
}

/** Client JS for slim booking dialog — no price fields. */
function bookingDialogClientJs_() {
  return [
    'function el(id){return document.getElementById(id);}',
    'function setVal(id,v){var x=el(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function setValIf(id,v){if(v===undefined||v===null||v==="")return;var x=el(id);if(x)x.value=v;}',
    'function applyLeadFromPicker(p){',
    '  if(!p)return;window.__PICKED_LEAD=p;',
    '  setVal("customerName",p.customerName||"");setVal("model",p.model||"");setVal("variant",p.variant||"");setVal("executive",p.executive||"");',
    '  if(p.bookingAmount)setVal("bookingAmount",p.bookingAmount);',
    '  var box=el("custBox");if(box&&p.leadId)box.textContent="Lead: "+p.leadId+" | Status: "+(p.accountStatus||"Active");',
    '  var exReq=String(p.exchangeRequired||"").toLowerCase();',
    '  var finReq=String(p.financeRequired||"").toLowerCase();',
    '  var exSec=el("exchangeSection");if(exSec)exSec.style.display=exReq==="yes"?"block":"none";',
    '  var finSec=el("financeSection");if(finSec)finSec.style.display=finReq==="yes"?"block":"none";',
    '}',
    'function applyLeadCtx(ctx){',
    '  ctx=ctx||{};var l=ctx.lead||{};var pick=window.__PICKED_LEAD||{};',
    '  setValIf("customerName",l.customerName||pick.customerName);',
    '  setValIf("model",l.model||l.interestedModel||pick.model);',
    '  setValIf("variant",l.variant||pick.variant);',
    '  setValIf("executive",l.executive||pick.executive);',
    '  if(ctx.today)setVal("bookingDate",ctx.today);',
    '  if(l.bookingAmount!=null&&l.bookingAmount!=="")setVal("bookingAmount",l.bookingAmount);',
    '  var exReq=String(l.exchangeRequired||pick.exchangeRequired||"").toLowerCase();',
    '  var finReq=String(l.financeRequired||pick.financeRequired||"").toLowerCase();',
    '  var exSec=el("exchangeSection");if(exSec)exSec.style.display=exReq==="yes"?"block":"none";',
    '  var finSec=el("financeSection");if(finSec)finSec.style.display=finReq==="yes"?"block":"none";',
    '  var lid=l.leadId||pick.leadId;if(lid){var box=el("custBox");if(box)box.textContent="Lead: "+lid+" | Status: "+(l.accountStatus||pick.accountStatus||"Active");}',
    '}',
    'function loadLeadById(id){',
    '  id=id||getPickedLeadId();if(!id)return;',
    '  google.script.run.withSuccessHandler(function(res){',
    '    if(!res||res.success===false)return;applyLeadCtx(res);',
    '  }).withFailureHandler(function(){}).getBookingLeadContext(id);',
    '}',
    'window.onLeadPicked=function(l){applyLeadFromPicker(l);loadLeadById(l.leadId);};',
    'function doSave(){',
    '  if(window.__BOOKING_SAVE_BUSY)return;',
    '  if(!validateLeadPick())return;',
    '  window.__BOOKING_SAVE_BUSY=true;',
    '  var b=el("btn");var label="Save Booking";',
    '  if(b){b.disabled=true;b.textContent="Saving...";if(!b.getAttribute("data-label"))b.setAttribute("data-label",label);}',
    '  var done=false;',
    '  var timer=setTimeout(function(){',
    '    if(done)return;done=true;window.__BOOKING_SAVE_BUSY=false;',
    '    if(b){b.disabled=false;b.textContent=label;}',
    '    alert("Booking save is still processing.\\nDo NOT click Save again.");',
    '  },45000);',
    '  try{',
    '    var payload={',
    '      leadId:getPickedLeadId(),',
    '      variant:(el("variant")?el("variant").value:""),',
    '      bookingDate:(el("bookingDate")?el("bookingDate").value:""),',
    '      bookingAmount:(el("bookingAmount")?el("bookingAmount").value:""),',
    '      bookingPaymentMode:(el("bookingPaymentMode")?el("bookingPaymentMode").value:""),',
    '      executive:(el("executive")?el("executive").value:""),',
    '      oldVehicleBrand:(el("oldVehicleBrand")?el("oldVehicleBrand").value:""),',
    '      oldVehicleModel:(el("oldVehicleModel")?el("oldVehicleModel").value:""),',
    '      oldVehicleRegistration:(el("oldVehicleRegistration")?el("oldVehicleRegistration").value:""),',
    '      evaluatedExchangeValue:(el("evaluatedExchangeValue")?el("evaluatedExchangeValue").value:""),',
    '      finalExchangeValue:(el("finalExchangeValue")?el("finalExchangeValue").value:""),',
    '      financer:(el("financer")?el("financer").value:""),',
    '      loanAmount:(el("loanAmount")?el("loanAmount").value:""),',
    '      downPayment:(el("downPayment")?el("downPayment").value:""),',
    '      deferPrice:true',
    '    };',
    '    if(!(Number(payload.bookingAmount)>0)){clearTimeout(timer);done=true;window.__BOOKING_SAVE_BUSY=false;if(b){b.disabled=false;b.textContent=label;}alert("Booking amount must be greater than zero.");return;}',
    '    if(!String(payload.bookingPaymentMode||"").trim()){clearTimeout(timer);done=true;window.__BOOKING_SAVE_BUSY=false;if(b){b.disabled=false;b.textContent=label;}alert("Select payment mode for booking advance.");return;}',
    '    google.script.run',
    '      .withSuccessHandler(function(res){',
    '        if(done)return;done=true;clearTimeout(timer);window.__BOOKING_SAVE_BUSY=false;',
    '        if(b){b.disabled=false;b.textContent=label;}',
    '        if(res&&res.success===false){alert(parseServerError(res));return;}',
    '        var msg=(res&&res.message)||"Booking saved";',
    '        if(res&&res.data&&res.data.alreadyBooked)msg+=" (duplicate save blocked)";',
    '        else msg+="\\n\\nNext: CRM → Price Structure (when price is known).";',
    '        alert(msg);kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '      })',
    '      .withFailureHandler(function(err){',
    '        if(done)return;done=true;clearTimeout(timer);window.__BOOKING_SAVE_BUSY=false;',
    '        if(b){b.disabled=false;b.textContent=label;}',
    '        alert(parseServerError(err));',
    '      })',
    '      .saveBookingFromDialog(payload);',
    '  }catch(ex){',
    '    if(!done){done=true;clearTimeout(timer);window.__BOOKING_SAVE_BUSY=false;',
    '    if(b){b.disabled=false;b.textContent=label;}',
    '    alert(parseServerError(ex));}',
    '  }',
    '}',
    'setVal("bookingDate",new Date().toISOString().slice(0,10));'
  ].join('');
}

/** JSON-safe lead for HTML dialogs (google.script.run cannot serialize sheet rows). */
function serializeLeadForClient_(lead) {
  if (!lead) return null;
  return {
    leadId:           String(lead.leadId || ''),
    customerName:     String(lead.customerName || ''),
    model:            String(lead.interestedModel || lead.model || ''),
    interestedModel:  String(lead.interestedModel || lead.model || ''),
    variant:          String(lead.variant || ''),
    executive:        String(lead.executive || ''),
    bookingAmount:    Number(lead.bookingAmount || 0),
    financeRequired:  String(lead.financeRequired || ''),
    exchangeRequired: String(lead.exchangeRequired || ''),
    accountStatus:    String(lead.accountStatus || 'Active'),
    mobile:           String(lead.mobile || '')
  };
}

// ═══════════════════════════════════════════════════════════════════════════
//  SERVER-SIDE BOOKING HANDLERS (unchanged from original except snapshot build)
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Light payment total for one lead — reads only the Payment Ledger instead of
 * rebuilding the entire CRM store. Restored: it was called by the Scheme Update
 * dialog but no longer defined, which silently forced a full store reload on
 * every lead pick.
 */
function sumPaymentsForLeadLight_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return 0;
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
    if (!sheet) return 0;
    var headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
    var idIdx = findHeaderIndex_(headers, 'Lead ID');
    var amtIdx = findHeaderIndex_(headers, 'Amount');
    if (idIdx < 0 || amtIdx < 0) return 0;
    var lastRow = sheet.getLastRow();
    if (lastRow < CRM.PAYMENT.DATA_START) return 0;
    var numRows = lastRow - CRM.PAYMENT.DATA_START + 1;
    var data = sheet.getRange(CRM.PAYMENT.DATA_START, 1, lastRow, Math.max(idIdx, amtIdx) + 1).getValues();
    var total = 0;
    for (var i = 0; i < data.length; i++) {
      if (String(data[i][idIdx] || '').trim() === leadId) total += parseNumber_(data[i][amtIdx]);
    }
    return total;
  } catch (e) {
    Logger.log('sumPaymentsForLeadLight_: ' + e.message);
    return 0;
  }
}

function formatPriceForClient_(price) {
  if (!price) return {};
  var p = Object.assign({}, price);
  if (p.effectiveFrom) p.effectiveFrom = formatDate_(p.effectiveFrom) || String(p.effectiveFrom);
  return p;
}

function isOwnerPriceOverrideEnabled_() {
  try {
    var settings = getSettings_();
    if (String(settings.ownerPriceOverrideEnabled || 'No').toLowerCase() !== 'yes') return false;
    var owner = String(getSpreadsheet_().getOwner().getEmail() || '').toLowerCase();
    var user = String(getUserEmail_() || '').toLowerCase();
    return !!owner && owner === user;
  } catch (e) {
    return false;
  }
}

/**
 * PUBLIC google.script.run endpoint — lead context + Price Master price.
 * Lead data is ALWAYS returned when found; price lookup failure does not wipe lead.
 */
function getBookingLeadContext(leadId) {
  leadId = String(leadId || '').trim();
  var lead = getLeadFromRegisterLight_(leadId);
  if (!lead) {
    return { success: false, message: 'Lead not found: ' + leadId, errorCode: 'NOT_FOUND' };
  }

  var clientLead = serializeLeadForClient_(lead);
  var paymentsReceived = sumPaymentsForLeadLight_(leadId);
  var variant = String(lead.variant || '').trim();
  var model = String(lead.interestedModel || '').trim();
  var today = nowDate_();
  var alreadyBooked = typeof isLeadAlreadyBooked_ === 'function' ? isLeadAlreadyBooked_(lead) : false;

  // Already booked → return SAVED commercial truth (snapshot / lead register),
  // not a fresh Price Master preview (that caused wrong RTO/insurance/outstanding in portal).
  if (alreadyBooked) {
    var snap = null;
    try {
      if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
        snap = getLatestCommercialSnapshotForLead_(leadId);
      }
    } catch (eSnap) {}
    var price = {};
    var totals = {};
    var tcs = 0;
    if (snap) {
      price = {
        exShowroom: num_(snap.exShowroom),
        insurance: num_(snap.insurance),
        registrationRto: num_(snap.registrationRto),
        accessories: num_(snap.accessories),
        handlingCharges: num_(snap.handlingCharges),
        trc: num_(snap.trc),
        fastag: num_(snap.fastag),
        extendedWarranty: num_(snap.extendedWarranty),
        otherCharges: num_(snap.otherCharges),
        gstPercent: num_(snap.gstPercent),
        tcsApplicable: snap.tcsApplicable || 'No',
        priceVersion: snap.priceVersion || '',
        effectiveFrom: snap.bookingDate || ''
      };
      tcs = num_(snap.tcs);
      var payable = num_(snap.customerPayable);
      if (!(payable > 0) && typeof calcPriceTotals_ === 'function') {
        var tCalc = calcPriceTotals_(price, {
          consumerDiscount: num_(snap.consumerDiscount),
          exchangeBonus: num_(snap.exchangeBonus),
          loyaltyBonus: num_(snap.loyaltyBonus),
          referralBonus: num_(snap.referralBonus),
          dsaDiscount: num_(snap.dsaDiscount),
          additionalDiscount: num_(snap.additionalDiscount),
          finalExchangeValue: num_(snap.finalExchangeValue)
        }, num_(snap.customerBenefitPassed));
        payable = tCalc.customerPayable;
        totals = {
          grossVehicleCost: tCalc.grossVehicleCost,
          tcs: tCalc.tcs,
          grossInvoiceAmount: tCalc.grossInvoiceAmount,
          netVehicleCost: tCalc.netVehicleCost,
          customerPayable: payable,
          outstanding: calcOutstanding_(payable, lead.bookingAmount || 0, paymentsReceived)
        };
      } else {
        totals = {
          grossVehicleCost: num_(snap.grossVehicleCost),
          tcs: tcs,
          grossInvoiceAmount: num_(snap.grossInvoiceAmount),
          netVehicleCost: num_(snap.netVehicleCost),
          customerPayable: payable,
          outstanding: calcOutstanding_(payable, lead.bookingAmount || snap.bookingAmount || 0, paymentsReceived)
        };
      }
    } else {
      // Fall back to Lead Register commercial columns
      var payableLead = num_(lead.customerPayable);
      totals = {
        grossVehicleCost: num_(lead.grossVehicleCost),
        tcs: num_(lead.tcs),
        grossInvoiceAmount: num_(lead.grossInvoiceAmount) || num_(lead.grossVehicleCost),
        netVehicleCost: num_(lead.netVehicleCost),
        customerPayable: payableLead,
        outstanding: calcOutstanding_(payableLead, lead.bookingAmount || 0, paymentsReceived)
      };
      price = {
        exShowroom: num_(lead.exShowroom || lead.budget),
        insurance: num_(lead.insuranceAmount || lead.insurance),
        registrationRto: num_(lead.rto || lead.registrationRto),
        accessories: num_(lead.accessoriesAmount || lead.accessories),
        handlingCharges: num_(lead.handlingCharges),
        trc: num_(lead.trc),
        fastag: num_(lead.fastag),
        extendedWarranty: num_(lead.extendedWarranty),
        otherCharges: num_(lead.otherCharges)
      };
    }
    return {
      success: true,
      alreadyBooked: true,
      lead: clientLead,
      today: today,
      paymentsReceived: paymentsReceived,
      price: price,
      totals: totals,
      ownerOverrideEnabled: isOwnerPriceOverrideEnabled_(),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcs: tcs || num_(totals.tcs)
    };
  }

  if (!variant) {
    return {
      success: true, lead: clientLead, today: today, paymentsReceived: paymentsReceived,
      price: {}, priceError: 'Lead has no Variant. Update the lead before booking.',
      ownerOverrideEnabled: isOwnerPriceOverrideEnabled_(),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0), tcs: 0
    };
  }
  if (!model) {
    return {
      success: true, lead: clientLead, today: today, paymentsReceived: paymentsReceived,
      price: {}, priceError: 'Lead has no Model. Update the lead before booking.',
      ownerOverrideEnabled: isOwnerPriceOverrideEnabled_(),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0), tcs: 0
    };
  }

  try {
    var breakdown = getCommercialBreakup_(model, variant, today);
    var priceFresh = formatPriceForClient_(breakdown.price);
    var totalsFresh = calcPriceTotals_(priceFresh, {}, 0);
    var outstandingFresh = calcOutstanding_(totalsFresh.customerPayable, lead.bookingAmount || 0, paymentsReceived);

    return {
      success: true,
      alreadyBooked: false,
      lead: clientLead,
      today: today,
      paymentsReceived: paymentsReceived,
      price: priceFresh,
      totals: {
        grossVehicleCost: breakdown.grossVehicleCost,
        tcs: breakdown.tcs,
        grossInvoiceAmount: totalsFresh.grossInvoiceAmount,
        netVehicleCost: totalsFresh.netVehicleCost,
        customerPayable: totalsFresh.customerPayable,
        outstanding: outstandingFresh
      },
      ownerOverrideEnabled: isOwnerPriceOverrideEnabled_(),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcs: breakdown.tcs
    };
  } catch (priceErr) {
    return {
      success: true,
      alreadyBooked: false,
      lead: clientLead,
      today: today,
      paymentsReceived: paymentsReceived,
      price: {},
      priceError: (priceErr && priceErr.message) || String(priceErr),
      errorCode: (priceErr && priceErr.errorCode) || 'PRICE_NOT_FOUND',
      ownerOverrideEnabled: isOwnerPriceOverrideEnabled_(),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcs: 0
    };
  }
}

/**
 * PUBLIC google.script.run endpoint — Price Master lookup for booking dialog.
 * Always reads live PRICE MASTER via PricingService (restored from working build).
 */
function getPriceForBookingContext(leadId, variant, bookingDate) {
  try {
    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');
    var model = String(lead.interestedModel || '').trim();
    var requestedVariant = String(variant || lead.variant || '').trim();
    var requestedDate = formatDate_(bookingDate) || nowDate_();
    if (!model) throw businessError_('Lead has no Model.', 'VALIDATION');
    if (!requestedVariant) throw businessError_('Variant is required for price lookup.', 'VALIDATION');

    var breakdown = getCommercialBreakup_(model, requestedVariant, requestedDate);
    var price = formatPriceForClient_(breakdown.price);
    var paymentsReceived = sumPaymentsForLeadLight_(lead.leadId);
    var totals = calcPriceTotals_(price, {}, 0);
    var outstanding = calcOutstanding_(totals.customerPayable, 0, paymentsReceived);

    return {
      success: true,
      price: price,
      totals: {
        grossVehicleCost: breakdown.grossVehicleCost,
        tcs: breakdown.tcs,
        grossInvoiceAmount: totals.grossInvoiceAmount,
        netVehicleCost: totals.netVehicleCost,
        customerPayable: totals.customerPayable,
        outstanding: outstanding
      },
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcs: breakdown.tcs
    };
  } catch (err) {
    Logger.log('getPriceForBookingContext: ' + ((err && err.message) || err));
    return {
      success: false,
      message: (err && err.message) || String(err),
      errorCode: (err && err.errorCode) || 'ERROR',
      price: {}
    };
  }
}

/** Legacy private alias — do not call from HTML. */
function getPriceForBookingContext_(leadId, variant, bookingDate) {
  return getPriceForBookingContext(leadId, variant, bookingDate);
}

function readPriceMasterForLead_(model, variant, bookingDate) {
  return getCommercialBreakup_(model, variant, bookingDate).price;
}

function saveBookingFromDialog(data) {
  var start = Date.now();
  try {
    var lock   = LockService.getDocumentLock();
    var locked = false;
    try {
      locked = lock.tryLock(15000);
      if (!locked) {
        return crmFailStructured_('Booking', 'saveBookingFromDialog', 'lock',
          businessError_('Booking system is busy. Retry in 30 seconds.', 'LOCK_BUSY'),
          Date.now() - start);
      }
      return saveBookingCommit_(data, start);
    } finally {
      if (locked) lock.releaseLock();
    }
  } catch (err) {
    logTransaction_('Booking', 'Save Failed', {
      status: 'ERROR', executionMs: Date.now() - start,
      message: (err && err.message) || String(err)
    }, Date.now() - start, { module: 'Booking', function: 'saveBookingFromDialog' });
    return crmFailStructured_('Booking', 'saveBookingFromDialog', 'commit', err, Date.now() - start);
  }
}

function saveBookingCommit_(data, start) {
  var _t = Date.now();
  var _steps = [];
  function _lap(label) { var n = Date.now(); _steps.push(label + '=' + (n - _t) + 'ms'); _t = n; }

  var leadId = String(data.leadId || '').trim();
  if (!leadId) throw fieldError_('Lead ID', 'Select a lead before saving booking.', 'VALIDATION');

  requireActiveLead_(leadId);
  var store = loadCrmStore_();
  var lead  = store.leads.byId[leadId];
  if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');
  _lap('loadStore');

  if (isLeadAlreadyBooked_(lead) && !data.allowRebook) {
    return { success: true, data: { alreadyBooked: true }, message: 'Lead is already booked. Booking record preserved.' };
  }

  var bookingDate = formatDate_(data.bookingDate) || nowDate_();
  var variant     = String(data.variant || lead.variant || '').trim();
  // Booking never locks price — Price Structure menu sets it later.
  var deferPrice  = true;
  var pm = {};
  var tcs = 0;
  _lap('price');

  var snapshot = buildBookingSnapshotFromForm_(lead, data, pm, tcs);
  snapshot.exShowroom = 0;
  snapshot.insurance = 0;
  snapshot.registrationRto = 0;
  snapshot.accessories = 0;
  snapshot.handlingCharges = 0;
  snapshot.trc = 0;
  snapshot.fastag = 0;
  snapshot.extendedWarranty = 0;
  snapshot.otherCharges = 0;
  snapshot.gstPercent = 0;
  snapshot.tcsApplicable = 'No';
  snapshot.priceListVersion = '';
  snapshot.amendmentReason = 'Booking created — price deferred to Price Structure';

  var totals      = computeCommercialTotals_(snapshot);
  var paid        = Number((store.paymentsByLead || {})[leadId] || 0);
  var outstanding = calcOutstanding_(totals.customerPayable, Number(data.bookingAmount || 0), paid);

  var snapRes = upsertOrAmendBookingSnapshot_(leadId, snapshot);
  _lap('snapshot');
  updateLeadForBooking_(leadId, data, outstanding);
  _lap('leadUpdate');
  upsertBookingAndRelationship_(lead, data, snapRes, outstanding);
  _lap('bookingReg');

  // Record booking advance payment if bookingAmount > 0.
  // Must succeed even when Customer Payable is still 0 (price deferred to Price Structure).
  var bookingAmt = Number(data.bookingAmount || 0);
  var paymentWarning = '';
  if (bookingAmt > 0) {
    try {
      addPayment_({
        leadId:      leadId,
        amount:      bookingAmt,
        date:        bookingDate,
        paymentMode: normalizeBookingPaymentMode_(data.bookingPaymentMode || 'Cash'),
        narration:   'Booking advance',
        allowProvisional: true,
        skipFinanceUpsert: true,
        skipLock:    true
      });
    } catch (pe) {
      paymentWarning = String((pe && pe.message) || pe);
      Logger.log('saveBookingCommit_: payment record failed: ' + paymentWarning);
      try {
        logAudit_('BOOKING_PAYMENT_FAILED', leadId + ' | ₹' + bookingAmt + ' | ' + paymentWarning);
      } catch (aePay) {}
    }
  }
  _lap('advancePayment');

  try { addActivity_({ leadId: leadId, activityType: 'Booking', discussion: 'Booking converted.', executive: data.executive || lead.executive || '', skipLock: true, skipPostTasks: true }); } catch (ae) {}
  _lap('activity');
  // Dealer Earnings + dashboard rebuild happen in the deferred worker. Queue ONCE
  // here (a single trigger set). refreshCrmAfterDialogSave_ is intentionally NOT
  // called — it would schedule the worker a second time (double trigger churn).
  // runEstimate: sync Price Master outstanding when price is still deferred.
  try {
    scheduleDeferredCrmSync_({
      leadId: leadId,
      reason: 'booking',
      dashboard: true,
      runEstimate: true
    });
  } catch (sde) {}
  try { invalidateCrmStore_(); } catch (ie) {}
  _lap('schedule');

  var totalMs = Date.now() - start;
  try { logAudit_('BOOKING_SAVE_TIMING', leadId + ' | total=' + totalMs + 'ms | ' + _steps.join(' ')); } catch (te) {}
  logTransaction_('Booking', 'Save OK', {
    status: 'OK', executionMs: totalMs,
    message: 'Booking saved for ' + leadId + ' | ' + _steps.join(' ')
  }, totalMs, { module: 'Booking', function: 'saveBookingCommit_' });

  var msg = deferPrice
    ? ('Booking saved for ' + lead.customerName + '. Set price via CRM → Price Structure.')
    : ('Booking saved for ' + lead.customerName + '. Outstanding: ₹' + outstanding);
  if (paymentWarning) {
    msg += ' Warning: booking advance was not written to Payment Ledger — ' + paymentWarning;
  }
  return {
    success: true,
    message: msg,
    data: {
      leadId: leadId,
      outstanding: outstanding,
      bookingId: snapRes && snapRes.bookingId,
      priceDeferred: !!deferPrice,
      paymentWarning: paymentWarning || ''
    }
  };
}

/**
 * Build booking snapshot from form data.
 *
 * Key rule: exShowroom is ALWAYS taken from Price Master (pm.exShowroom).
 * The client payload intentionally omits exShowroom.
 * All other charges use client-submitted value if positive, else Price Master fallback.
 */
function buildBookingSnapshotFromForm_(lead, data, pm, tcs) {
  var base = buildCommercialSnapshotFromLead_(lead);
  pm = pm || {};
  base.variant          = data.variant || lead.variant || '';
  base.bookingDate      = formatDate_(data.bookingDate) || nowDate_();
  base.bookingAmount    = Number(data.bookingAmount || 0);
  base.bookingExecutive = data.executive || lead.executive || '';
  base.bookingMode      = normalizeBookingPaymentMode_(data.bookingPaymentMode || '');
  base.model            = lead.interestedModel || '';
  base.priceListVersion = pm.priceVersion || base.priceListVersion || '';
  base.priceMasterRowId = pm.rowNumber || pm.priceMasterRowId || '';
  base.priceEffectiveDate = pm.effectiveFrom || '';
  base.bodyType         = pm.bodyType || pm.batteryType || '';
  base.batteryType      = base.bodyType;
  base.financeRequired  = String(lead.financeRequired || '').toLowerCase() === 'yes' ? 'Yes' : 'No';
  base.exchangeRequired = String(lead.exchangeRequired || '').toLowerCase() === 'yes' ? 'Yes' : 'No';

  base.consumerDiscount = 0;
  base.exchangeBonus    = 0;
  base.loyaltyBonus     = 0;
  base.referralBonus    = 0;
  base.dsaDiscount      = 0;
  base.additionalDiscount = 0;

  base.oldVehicleBrand        = data.oldVehicleBrand || '';
  base.oldVehicleModel        = data.oldVehicleModel || '';
  base.oldVehicleRegistration = data.oldVehicleRegistration || '';
  base.evaluatedExchangeValue = Number(data.evaluatedExchangeValue || 0);
  base.finalExchangeValue     = Number(data.finalExchangeValue     || 0);

  base.financer    = data.financer    || '';
  base.loanAmount  = Number(data.loanAmount  || 0);
  base.downPayment = Number(data.downPayment || 0);

  // ── Price fields ──────────────────────────────────────────────────────
  // exShowroom: ALWAYS from Price Master. Client value is ignored.
  base.exShowroom = Number(pm.exShowroom || 0);

  // All other charges: the client value wins WHENEVER THE FIELD WAS SENT — including
  // an explicit 0. The old rule (client only when > 0) made it impossible to zero a
  // charge: TRC edited 3000 → 0 fell back to Price Master's 3000 and the customer
  // was billed anyway. Absent/blank fields still fall back to Price Master.
  function clientOrPm(field, pmField) {
    var raw = data[field];
    if (raw !== undefined && raw !== null && String(raw).trim() !== '') {
      var clientVal = Number(raw);
      if (!isNaN(clientVal) && clientVal >= 0) return clientVal;
    }
    return Number(pm[pmField || field] || 0);
  }
  base.insurance        = clientOrPm('insurance');
  base.registrationRto  = clientOrPm('registrationRto');
  base.accessories      = clientOrPm('accessories');
  base.handlingCharges  = clientOrPm('handlingCharges');
  base.trc              = clientOrPm('trc');
  base.fastag           = clientOrPm('fastag');
  base.extendedWarranty = clientOrPm('extendedWarranty');
  base.otherCharges     = clientOrPm('otherCharges');
  base.gstPercent       = clientOrPm('gstPercent');
  base.tcsApplicable    = normalizeYesNo_(data.tcsApplicable || pm.tcsApplicable || 'No');
  base.rsaAmc           = 0;
  return base;
}

function updateLeadForBooking_(leadId, data, outstanding) {
  var found = findLeadById_(leadId);
  if (!found) throw businessError_('Lead not found while booking update', 'NOT_FOUND');
  updateLeadRegisterFields_(leadId, {
    'Variant':         data.variant || found.lead.variant || '',
    'Booking Date':    formatDate_(data.bookingDate) || nowDate_(),
    'Booking Amount':  Number(data.bookingAmount || 0),
    'Executive':       data.executive || found.lead.executive || '',
    'Current Status':  'Booked',
    'Outstanding Amount': Number(outstanding || 0),
    'Last Updated':    nowDateTime_(),
    'Last Updated By': getUserEmail_()
  });
}

function upsertOrAmendBookingSnapshot_(leadId, snapshot) {
  var store    = loadCrmStore_();
  var existing = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
  if (!existing) {
    upsertCommercialSnapshot_(snapshot, 'Created from Convert to Booking form');
    // upsertCommercialSnapshot_ assigns bookingId/snapshotId onto the snapshot
    // object itself — reading them back via a full-workbook store rebuild (the old
    // loadCrmStore_(true) here) was one of the main reasons booking save was slow.
    return { bookingId: snapshot.bookingId || '', snapshotId: snapshot.snapshotId || '' };
  }
  return amendCommercialSnapshot_(leadId, snapshot, 'Updated from Convert to Booking form', getUserEmail_());
}

function upsertBookingAndRelationship_(lead, data, snapRes, outstanding) {
  var bookingId  = snapRes.bookingId  || '';
  var snapshotId = snapRes.snapshotId || '';
  var payMode    = normalizeBookingPaymentMode_(data.bookingPaymentMode || '');
  var bookingAmt = Number(data.bookingAmount || 0);
  var financeYes = String(data.financeRequired || lead.financeRequired || '').toLowerCase() === 'yes' ||
    payMode.toLowerCase() === 'finance';
  upsertBookingRegister_({
    BookingID:    bookingId,
    LeadID:       lead.leadId,
    CustomerName: lead.customerName,
    'Booking Date':   formatDate_(data.bookingDate) || nowDate_(),
    'Vehicle Model':  lead.interestedModel || '',
    Variant:          data.variant || lead.variant || '',
    'Booking Amount': bookingAmt,
    'Amount Received': bookingAmt,
    'Payment Mode':    payMode,
    'Finance Required': financeYes ? 'Yes' : 'No',
    'Exchange Required': String(lead.exchangeRequired || '').toLowerCase() === 'yes' ? 'Yes' : 'No',
    CommercialSnapshotID: snapshotId,
    'Booking Status': 'Booked',
    'Created By':     getUserEmail_(),
    'Created Date':   nowDate_(),
    'Last Updated':   nowDateTime_()
  });
  try { appendRelationshipBooking_(lead.leadId, bookingId); } catch (e) {}
}

function isLeadAlreadyBooked_(lead) {
  if (!lead) return false;
  var status = normalizeStatus_(lead.currentStatus || lead.bookingStatus || '');
  if (status === 'Booked' || status === 'Delivered') return true;
  // Fall back to hard booking evidence on the lead row. The status text alone is
  // fragile (it can be edited, and the separate Booking Status column has been
  // retired in favour of Current Status), so a lead that carries a Booking ID,
  // booking date or booking amount is booked regardless of the status label.
  if (String(lead.bookingId || '').trim()) return true;
  if (String(lead.bookingDate || '').trim()) return true;
  if (Number(lead.bookingAmount || 0) > 0) return true;
  return false;
}

function normalizeBookingPaymentMode_(raw) {
  raw = String(raw || '').trim();
  if (!raw) return 'Cash';
  var norm = matchMasterValue_(raw, ['Cash', 'UPI', 'Finance', 'Cheque', 'NEFT', 'Card']) || '';
  return norm || raw;
}

/* ═══════════════════════════════════════════════════════════════════════════
 * Price Structure — separate CRM step after booking (price not fixed at book).
 * ═══════════════════════════════════════════════════════════════════════════ */

function showPriceStructureDialog_() {
  var seedLeads = getActiveLeadsForPickerLight_({ activeOnly: true });
  var html = createDialogOutput_(
    dialogBaseCss_('#2E7D32') + '<style>' + leadPickerCss_() + '</style>' +
    '<style>input:disabled{background:#f5f5f5}.pm-note{font-size:11px;color:#2E7D32;margin:2px 0 6px}</style>' +
    '<h3>Price Structure</h3>' +
    '<p style="font-size:12px;color:#666;">Set or correct deal price for a booked lead. Scheme stays in Scheme Update.</p>' +
    leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true, label: 'Booked Lead *' }) +
    '<div id="priceStatus" style="font-size:12px;color:#666;margin:8px 0;">Pick a booked lead…</div>' +
    '<label>Ex Showroom <span style="font-size:11px;color:#c62828">(from Price Master)</span></label>' +
    '<input id="exShowroom" type="number" min="0" step="0.01" disabled="disabled" />' +
    '<div class="pm-note">Other charges pre-fill from Price Master — edit for this deal.</div>' +
    '<label>Insurance</label><input id="insurance" type="number" min="0" step="0.01" />' +
    '<label>Registration / RTO</label><input id="registrationRto" type="number" min="0" step="0.01" />' +
    '<label>Accessories</label><input id="accessories" type="number" min="0" step="0.01" />' +
    '<label>Handling</label><input id="handlingCharges" type="number" min="0" step="0.01" />' +
    '<label>TRC</label><input id="trc" type="number" min="0" step="0.01" />' +
    '<label>Fastag</label><input id="fastag" type="number" min="0" step="0.01" />' +
    '<label>Extended Warranty</label><input id="extendedWarranty" type="number" min="0" step="0.01" />' +
    '<label>Other Charges</label><input id="otherCharges" type="number" min="0" step="0.01" />' +
    '<label>GST %</label><input id="gstPercent" type="number" min="0" step="0.01" />' +
    '<label>TCS Applicable</label><select id="tcsApplicable"><option>No</option><option>Yes</option></select>' +
    '<label>Customer Payable (preview)</label><input id="customerPayable" disabled="disabled" />' +
    '<label>Outstanding (preview)</label><input id="outstanding" disabled="disabled" />' +
    '<button class="btn" id="btn" type="button" onclick="doSave()">Save Price Structure</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_('window.__LEAD_CACHE_SEEDED=' + jsonForHtml_(seedLeads) + ';') +
    htmlScript_(leadPickerClientJs_(true, 'scheme')) +
    htmlScript_(priceStructureDialogClientJs_()),
    440,
    720
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Price Structure');
}

function priceStructureDialogClientJs_() {
  return [
    'var PS={tcsRate:0,tcs:0,paid:0,booking:0};',
    'function el(id){return document.getElementById(id);}',
    'function num(v){var n=Number(v);return isFinite(n)?n:0;}',
    'function setVal(id,v){var x=el(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function pstat(m){var s=el("priceStatus");if(s)s.textContent=m;}',
    'function calc(){',
    '  var gross=num(el("exShowroom").value)+num(el("insurance").value)+num(el("registrationRto").value)+num(el("accessories").value)+num(el("handlingCharges").value)+num(el("trc").value)+num(el("fastag").value)+num(el("extendedWarranty").value)+num(el("otherCharges").value);',
    '  var tcsRule=String(el("tcsApplicable").value||"No").toLowerCase()==="yes";',
    '  var tcs=tcsRule?num(PS.tcs):0;',
    '  var payable=Math.max(0,gross+tcs);',
    '  setVal("customerPayable",payable.toFixed(2));',
    '  setVal("outstanding",Math.max(0,payable-num(PS.booking)-num(PS.paid)).toFixed(2));',
    '}',
    'function fillFromPrice(p,meta){',
    '  p=p||{};meta=meta||{};',
    '  setVal("exShowroom",p.exShowroom||0);',
    '  setVal("insurance",p.insurance||0);setVal("registrationRto",p.registrationRto||0);',
    '  setVal("accessories",p.accessories||0);setVal("handlingCharges",p.handlingCharges||0);',
    '  setVal("trc",p.trc||0);setVal("fastag",p.fastag||0);setVal("extendedWarranty",p.extendedWarranty||0);',
    '  setVal("otherCharges",p.otherCharges||0);setVal("gstPercent",p.gstPercent||0);',
    '  setVal("tcsApplicable",p.tcsApplicable||"No");',
    '  if(meta.tcsRate!=null)PS.tcsRate=num(meta.tcsRate);',
    '  if(meta.tcs!=null)PS.tcs=num(meta.tcs);',
    '  calc();',
    '}',
    'function loadCtx(id){',
    '  pstat("Loading…");',
    '  google.script.run.withSuccessHandler(function(res){',
    '    if(!res||res.success===false){pstat((res&&res.message)||"Failed");return;}',
    '    PS.paid=num(res.paymentsReceived);PS.booking=num(res.bookingAmount);',
    '    if(res.tcsRate!=null)PS.tcsRate=num(res.tcsRate);',
    '    if(res.tcs!=null)PS.tcs=num(res.tcs);',
    '    var snap=res.snapshot||{};',
    '    var lead=res.lead||{};',
    '    var preferPm=!!(res.preferPriceMaster||res.vehicleChanged);',
    '    var label=(lead.interestedModel||lead.model||"")+" / "+(lead.variant||"");',
    '    if(preferPm&&res.price&&num(res.price.exShowroom)>0){',
    '      fillFromPrice(res.price,{tcs:res.tcs,tcsRate:res.tcsRate});',
    '      pstat((res.vehicleChanged?"Variant/model changed — ":"")+"Price Master for "+label+" — review and save.");',
    '    }else if(num(snap.exShowroom)>0){',
    '      fillFromPrice(snap,{tcs:snap.tcs,tcsRate:PS.tcsRate});',
    '      pstat("Loaded saved price for "+label+" — edit and save.");',
    '    }else if(res.price&&num(res.price.exShowroom)>0){',
    '      fillFromPrice(res.price,{tcs:res.tcs,tcsRate:res.tcsRate});',
    '      pstat("Pre-filled from Price Master for "+label+" — adjust if needed.");',
    '    }else{pstat("No Price Master row for "+label+" — check model/variant.");}',
    '  }).withFailureHandler(function(e){pstat(parseServerError(e));}).getPriceStructureContext(id);',
    '}',
    'window.onLeadPicked=function(l){loadCtx(l.leadId);};',
    'document.addEventListener("input",function(e){if(e.target&&e.target.id!=="leadSearch")calc();});',
    'function doSave(){',
    '  if(!validateLeadPick())return;',
    '  if(!(num(el("exShowroom").value)>0)){alert("Ex Showroom must be > 0. Load from Price Master or ensure Price Master has this model/variant.");return;}',
    '  var b=el("btn");b.disabled=true;b.textContent="Saving…";',
    '  var d={leadId:getPickedLeadId(),insurance:el("insurance").value,registrationRto:el("registrationRto").value,',
    '    accessories:el("accessories").value,handlingCharges:el("handlingCharges").value,trc:el("trc").value,',
    '    fastag:el("fastag").value,extendedWarranty:el("extendedWarranty").value,otherCharges:el("otherCharges").value,',
    '    gstPercent:el("gstPercent").value,tcsApplicable:el("tcsApplicable").value};',
    '  google.script.run.withSuccessHandler(function(res){',
    '    b.disabled=false;b.textContent="Save Price Structure";',
    '    if(res&&res.success===false){alert(parseServerError(res));return;}',
    '    alert((res&&res.message)||"Price saved");kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '  }).withFailureHandler(function(e){b.disabled=false;b.textContent="Save Price Structure";alert(parseServerError(e));})',
    '  .savePriceStructureFromDialog(d);',
    '}'
  ].join('');
}

function getPriceStructureContext(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead required' };
    requireActiveLead_(leadId);
    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) return { success: false, message: 'Lead not found' };
    if (!isLeadAlreadyBooked_(lead)) {
      return { success: false, message: 'Lead is not booked yet. Convert to Booking first.' };
    }
    var snap = null;
    try {
      if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
        snap = getLatestCommercialSnapshotForLead_(leadId);
      }
    } catch (e1) {}
    if (snap && snap.full && typeof snap.full === 'object') {
      snap = snap.full;
    }
    var paid = 0;
    try { paid = Number(sumPaymentsForLeadLight_(leadId) || 0); } catch (e2) {}

    // Lead Register model/variant is authoritative after Edit Lead.
    var leadModel = String(lead.interestedModel || lead.model || '').trim();
    var leadVariant = String(lead.variant || '').trim();
    var snapModel = String((snap && snap.model) || '').trim();
    var snapVariant = String((snap && snap.variant) || '').trim();
    var modelMismatch = leadModel && snapModel &&
      leadModel.toLowerCase() !== snapModel.toLowerCase();
    var variantMismatch = leadVariant && snapVariant &&
      leadVariant.toLowerCase() !== snapVariant.toLowerCase();
    var vehicleChanged = !!(modelMismatch || variantMismatch ||
      (leadVariant && !snapVariant) || (leadModel && !snapModel));

    var bookingDate = formatDate_((snap && snap.bookingDate) || lead.bookingDate) || nowDate_();
    var price = {};
    var tcs = 0;
    try {
      var breakdown = getCommercialBreakup_(leadModel, leadVariant, bookingDate);
      price = formatPriceForClient_(breakdown.price) || {};
      tcs = Number(breakdown.tcs || 0);
    } catch (pe) {}

    var flatSnap = flattenPriceSnapshotForClient_(snap);
    // When Edit Lead changed variant/model, do NOT return old snapshot ex-showroom
    // as the fill source — Prefer Price Master for the CURRENT lead vehicle.
    if (vehicleChanged && Number(price.exShowroom || 0) > 0) {
      flatSnap.model = leadModel;
      flatSnap.variant = leadVariant;
      flatSnap.exShowroom = Number(price.exShowroom || 0);
      // Seed charges from PM when vehicle changed (old deal charges belong to old variant).
      flatSnap.insurance = Number(price.insurance || 0);
      flatSnap.registrationRto = Number(price.registrationRto || 0);
      flatSnap.accessories = Number(price.accessories || 0);
      flatSnap.handlingCharges = Number(price.handlingCharges || 0);
      flatSnap.trc = Number(price.trc || 0);
      flatSnap.fastag = Number(price.fastag || 0);
      flatSnap.extendedWarranty = Number(price.extendedWarranty || 0);
      flatSnap.otherCharges = Number(price.otherCharges || 0);
      flatSnap.gstPercent = Number(price.gstPercent || 0);
      flatSnap.tcsApplicable = String(price.tcsApplicable || 'No');
      flatSnap.priceListVersion = String(price.priceVersion || '');
      flatSnap.priceEffectiveDate = String(price.effectiveFrom || '');
    } else {
      // Keep saved snap amounts, but always expose current lead vehicle identity.
      flatSnap.model = leadModel || flatSnap.model;
      flatSnap.variant = leadVariant || flatSnap.variant;
    }

    return {
      success: true,
      lead: serializeLeadForClient_(lead),
      snapshot: flatSnap,
      price: price,
      vehicleChanged: vehicleChanged,
      preferPriceMaster: vehicleChanged || !(Number((snap && snap.exShowroom) || 0) > 0),
      paymentsReceived: paid,
      bookingAmount: Number(lead.bookingAmount || (snap && snap.bookingAmount) || 0),
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcs: tcs
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

/** Plain price fields only — safe for JSON / portal (no circular .full). */
function flattenPriceSnapshotForClient_(snap) {
  snap = snap || {};
  if (snap.full && typeof snap.full === 'object' && snap.full !== snap) {
    snap = snap.full;
  }
  return {
    leadId: String(snap.leadId || ''),
    bookingId: String(snap.bookingId || ''),
    model: String(snap.model || ''),
    variant: String(snap.variant || ''),
    bookingDate: String(snap.bookingDate || ''),
    bookingAmount: Number(snap.bookingAmount || 0),
    exShowroom: Number(snap.exShowroom || 0),
    insurance: Number(snap.insurance || 0),
    registrationRto: Number(snap.registrationRto || 0),
    accessories: Number(snap.accessories || 0),
    handlingCharges: Number(snap.handlingCharges || 0),
    trc: Number(snap.trc || 0),
    fastag: Number(snap.fastag || 0),
    extendedWarranty: Number(snap.extendedWarranty || 0),
    otherCharges: Number(snap.otherCharges || 0),
    gstPercent: Number(snap.gstPercent || 0),
    tcsApplicable: String(snap.tcsApplicable || 'No'),
    tcs: Number(snap.tcs || 0),
    customerPayable: Number(snap.customerPayable || 0),
    priceListVersion: String(snap.priceListVersion || snap.priceVersion || ''),
    priceEffectiveDate: String(snap.priceEffectiveDate || '')
  };
}

function savePriceStructureFromDialog(data) {
  try {
    data = data || {};
    var leadId = String(data.leadId || '').trim();
    if (!leadId) {
      return crmFailStructured_('Booking', 'savePriceStructureFromDialog', 'validate',
        businessError_('Lead is required', 'VALIDATION'), 0);
    }
    requireActiveLead_(leadId);
    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');
    if (!isLeadAlreadyBooked_(lead)) {
      throw businessError_('Lead is not booked yet. Convert to Booking first.', 'VALIDATION');
    }

    var snap = null;
    try {
      snap = typeof getLatestCommercialSnapshotForLead_ === 'function'
        ? getLatestCommercialSnapshotForLead_(leadId) : null;
    } catch (eS) {}
    if (snap && snap.full) snap = snap.full;

    // Lead Register vehicle is authoritative (Edit Lead may have changed variant).
    var model = String(lead.interestedModel || lead.model || '').trim();
    var variant = String(lead.variant || '').trim();
    var bookingDate = formatDate_((snap && snap.bookingDate) || lead.bookingDate) || nowDate_();
    var pm = getActivePrice_(model, variant, bookingDate);
    validatePrice_(pm);
    var tcs = calculateTCS_(pm);

    var snapModel = String((snap && snap.model) || '').trim();
    var snapVariant = String((snap && snap.variant) || '').trim();
    var vehicleChanged =
      (model && snapModel && model.toLowerCase() !== snapModel.toLowerCase()) ||
      (variant && snapVariant && variant.toLowerCase() !== snapVariant.toLowerCase()) ||
      !(Number((snap && snap.exShowroom) || 0) > 0);

    function pickCharge(field, pmField) {
      // After variant change, prefer Price Master defaults (not old variant charges).
      if (vehicleChanged) {
        if (data[field] !== undefined && data[field] !== null && String(data[field]).trim() !== '') {
          return Number(data[field]);
        }
        return Number(pm[pmField || field] || 0);
      }
      if (data[field] !== undefined && data[field] !== null && String(data[field]).trim() !== '') {
        return Number(data[field]);
      }
      return Number((snap && snap[field]) || pm[pmField || field] || 0);
    }

    var changes = {
      model: model,
      variant: variant,
      exShowroom: Number(pm.exShowroom || 0),
      insurance: pickCharge('insurance'),
      registrationRto: pickCharge('registrationRto'),
      accessories: pickCharge('accessories'),
      handlingCharges: pickCharge('handlingCharges'),
      trc: pickCharge('trc'),
      fastag: pickCharge('fastag'),
      extendedWarranty: pickCharge('extendedWarranty'),
      otherCharges: pickCharge('otherCharges'),
      gstPercent: pickCharge('gstPercent'),
      tcsApplicable: normalizeYesNo_(
        data.tcsApplicable ||
        (vehicleChanged ? pm.tcsApplicable : ((snap && snap.tcsApplicable) || pm.tcsApplicable || 'No'))
      ),
      priceListVersion: pm.priceVersion || '',
      priceEffectiveDate: pm.effectiveFrom || '',
      priceMasterRowId: pm.rowNumber || pm.priceMasterRowId || ''
    };

    var offerResult = amendCommercialSnapshot_(leadId, changes, 'Price Structure update', getUserEmail_());
    invalidateCrmStore_();
    var truthSnap = null;
    try {
      truthSnap = typeof getLatestCommercialSnapshotForLead_ === 'function'
        ? getLatestCommercialSnapshotForLead_(leadId) : null;
    } catch (ts) {}
    if (truthSnap && truthSnap.full) truthSnap = truthSnap.full;
    if (typeof ensureLeadCommercialPriceColumns_ === 'function') {
      try { ensureLeadCommercialPriceColumns_(); } catch (eCol) {}
    }
    if (typeof buildLeadCommercialTruthFields_ === 'function') {
      var truth = buildLeadCommercialTruthFields_(leadId, null, truthSnap);
      truth['Last Updated'] = nowDateTime_();
      truth['Last Updated By'] = getUserEmail_();
      // Force explicit price keys so Lead Register never stays blank after Price Structure.
      truth['Ex Showroom'] = Number(changes.exShowroom || 0);
      truth['RTO'] = Number(changes.registrationRto || 0);
      truth['Insurance Amount'] = Number(changes.insurance || 0);
      truth['Accessories Amount'] = Number(changes.accessories || 0);
      truth['Handling Charges'] = Number(changes.handlingCharges || 0);
      truth['TRC'] = Number(changes.trc || 0);
      truth['Fastag'] = Number(changes.fastag || 0);
      truth['Extended Warranty'] = Number(changes.extendedWarranty || 0);
      truth['Other Charges'] = Number(changes.otherCharges || 0);
      updateLeadRegisterFields_(leadId, truth);
    }
    try {
      if (typeof upsertDealerEarningsForLead_ === 'function') {
        upsertDealerEarningsForLead_(leadId, { reason: 'price_structure', rebuildAnalytics: false });
      }
    } catch (eE) {}
    scheduleDeferredCrmSync_({ leadId: leadId, reason: 'price_structure', dashboard: true });
    SpreadsheetApp.flush();
    var payable = truthSnap ? Number(truthSnap.customerPayable || 0) : 0;
    return crmOk_('Price structure saved. Customer Payable: ₹' + payable, {
      leadId: leadId,
      bookingId: offerResult && offerResult.bookingId,
      customerPayable: payable
    });
  } catch (e) {
    return crmFailStructured_('Booking', 'savePriceStructureFromDialog', 'handler', e, 0);
  }
}
