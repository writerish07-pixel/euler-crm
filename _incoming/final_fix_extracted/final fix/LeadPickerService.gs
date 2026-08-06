/**
 * LeadPickerService – searchable autocomplete lead selector for HTML dialogs.
 * Loads lead index once per dialog open; filters client-side in JavaScript.
 */

var ACCOUNT_STATUS = {
  ACTIVE: 'Active',
  CLOSED: 'Closed',
  CANCELLED: 'Cancelled',
  ARCHIVED: 'Archived'
};

function normalizeAccountStatus_(status) {
  var s = String(status || '').trim();
  if (!s) return ACCOUNT_STATUS.ACTIVE;
  var lower = s.toLowerCase();
  if (lower === 'active') return ACCOUNT_STATUS.ACTIVE;
  if (lower === 'closed') return ACCOUNT_STATUS.CLOSED;
  if (lower === 'cancelled' || lower === 'canceled') return ACCOUNT_STATUS.CANCELLED;
  if (lower === 'archived') return ACCOUNT_STATUS.ARCHIVED;
  return s;
}

function isOperationalLead_(lead) {
  return normalizeAccountStatus_(lead.accountStatus) === ACCOUNT_STATUS.ACTIVE;
}

function isActiveLead_(lead) {
  return isOperationalLead_(lead);
}

/** Assert lead exists and is active for operational forms. */
function requireActiveLead_(leadId) {
  var lead = getLead_(leadId);
  if (!lead) throw new Error('Lead not found: ' + leadId);
  if (!isActiveLead_(lead)) {
    throw new Error('Lead ' + leadId + ' is ' + normalizeAccountStatus_(lead.accountStatus) +
      '. Only Active leads can be used in this form.');
  }
  return lead;
}

/**
 * Soft gate: lead must exist and not be Archived.
 * Allows Finance receipt + Claim receipt after Close (money can arrive later).
 */
function requireExistingLead_(leadId) {
  var lead = getLead_(leadId);
  if (!lead) throw new Error('Lead not found: ' + leadId);
  var st = normalizeAccountStatus_(lead.accountStatus);
  if (st === ACCOUNT_STATUS.ARCHIVED) {
    throw new Error('Lead ' + leadId + ' is Archived and cannot receive finance/claim updates.');
  }
  return lead;
}

function maskMobile_(mobile) {
  var m = String(mobile || '');
  if (m.length < 6) return m;
  return m.substring(0, 5) + 'XXXXX';
}

/** Build compact lead list for client-side autocomplete (one load per dialog). */
function getLeadPickerCache_() {
  return getActiveLeadsForPicker_({ activeOnly: true });
}

/**
 * Server endpoint for dialog lead loading (public for google.script.run).
 * @param {{activeOnly?: boolean}} [options] activeOnly=true for operational forms
 */
function getActiveLeadsForPicker(options) {
  return getActiveLeadsForPicker_(options);
}

function getActiveLeadsForPicker_(options) {
  options = options || {};
  try {
    return getActiveLeadsForPickerLight_(options);
  } catch (err) {
    var msg = 'Lead picker load failed: ' + err.message;
    Logger.log(msg + '\n' + (err.stack || ''));
    try { logAudit_('LEAD_PICKER_ERROR', msg + '\n' + (err.stack || '')); } catch (e) {}
    throw new Error(msg);
  }
}

/**
 * One Payment Ledger scan → paid total + last Outstanding Balance per lead.
 * Used by Add Payment / picker so display matches ledger (not stale Lead Register).
 */
function loadPaymentMoneyByLeadLight_() {
  var out = {};
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.PAYMENT_LEDGER);
    if (!sheet) return out;
    var headers = getHeaders_(sheet, CRM.PAYMENT.HEADER_ROW);
    var idIdx = findHeaderIndex_(headers, 'Lead ID');
    var amtIdx = findHeaderIndex_(headers, 'Amount');
    var osIdx = findHeaderIndex_(headers, 'Outstanding Balance');
    if (idIdx < 0 || amtIdx < 0) return out;
    var lastRow = sheet.getLastRow();
    if (lastRow < CRM.PAYMENT.DATA_START) return out;
    var lastCol = Math.max(idIdx, amtIdx, osIdx) + 1;
    var data = sheet.getRange(CRM.PAYMENT.DATA_START, 1, Math.max(0, lastRow - CRM.PAYMENT.DATA_START + 1), lastCol).getValues();
    for (var i = 0; i < data.length; i++) {
      var id = String(data[i][idIdx] || '').trim();
      // HYPERLINK cells may return the display value already via getValues
      if (!id) continue;
      if (!out[id]) out[id] = { paid: 0, lastOutstanding: null };
      out[id].paid = round2_(out[id].paid + parseNumber_(data[i][amtIdx]));
      if (osIdx >= 0 && data[i][osIdx] !== '' && data[i][osIdx] != null) {
        out[id].lastOutstanding = parseNumber_(data[i][osIdx]);
      }
    }
  } catch (e) {
    Logger.log('loadPaymentMoneyByLeadLight_: ' + e.message);
  }
  return out;
}

/** Fast lead list — Lead Register + Payment Ledger money (no full CRM store). */
function getActiveLeadsForPickerLight_(options) {
  options = options || {};
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.LEAD_REGISTER);
  if (!sheet) return [];
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var col = function (name) { return findHeaderIndex_(headers, name); };
  var idIdx = col('Lead ID');
  if (idIdx < 0) return [];
  var lastRow = sheet.getLastRow();
  if (lastRow < CRM.LEAD.DATA_START) return [];
  var numRows = lastRow - CRM.LEAD.DATA_START + 1;
  var data = sheet.getRange(CRM.LEAD.DATA_START, 1, numRows, sheet.getLastColumn()).getValues();
  var payMoney = loadPaymentMoneyByLeadLight_();
  var activeOnly = options.activeOnly !== false;
  var list = [];
  for (var i = 0; i < data.length; i++) {
    var row = data[i];
    var leadId = String(row[idIdx] || '').trim();
    if (!leadId) continue;
    var acct = col('Account Status') >= 0
      ? normalizeAccountStatus_(row[col('Account Status')])
      : ACCOUNT_STATUS.ACTIVE;
    if (activeOnly && acct !== ACCOUNT_STATUS.ACTIVE) continue;
    if (!activeOnly && acct === ACCOUNT_STATUS.ARCHIVED) continue;
    var customerName = col('Customer Name') >= 0 ? String(row[col('Customer Name')] || '') : '';
    var mobile = col('Mobile') >= 0 ? normalizeMobile_(row[col('Mobile')]) : '';
    var bookingAmount = col('Booking Amount') >= 0 ? parseNumber_(row[col('Booking Amount')]) : 0;
    var money = payMoney[leadId] || { paid: 0, lastOutstanding: null };
    var paid = num_(money.paid);
    var customerPayable = col('Customer Payable') >= 0 ? parseNumber_(row[col('Customer Payable')]) : 0;
    var customerOsCol = col('Customer Outstanding') >= 0 ? parseNumber_(row[col('Customer Outstanding')]) : null;
    var sheetOs = col('Outstanding Amount') >= 0 ? parseNumber_(row[col('Outstanding Amount')]) : 0;
    var totalDiscount = col('Total Discount') >= 0 ? parseNumber_(row[col('Total Discount')]) : 0;
    var benefitMode = col('Benefit Mode') >= 0 ? String(row[col('Benefit Mode')] || '').trim() : '';
    var consumerDiscount = col('Consumer Discount') >= 0 ? parseNumber_(row[col('Consumer Discount')]) : 0;
    var exchangeBonus = col('Exchange Bonus') >= 0 ? parseNumber_(row[col('Exchange Bonus')]) : 0;
    var loyaltyBonus = col('Loyalty Bonus') >= 0 ? parseNumber_(row[col('Loyalty Bonus')]) : 0;
    var referralBonus = col('Referral Bonus') >= 0 ? parseNumber_(row[col('Referral Bonus')]) : 0;
    var dsaBonus = col('DSA Bonus') >= 0 ? parseNumber_(row[col('DSA Bonus')])
      : (col('DSA Discount') >= 0 ? parseNumber_(row[col('DSA Discount')]) : 0);
    var additionalDiscount = col('Additional Discount') >= 0 ? parseNumber_(row[col('Additional Discount')]) : 0;
    var offerSum = consumerDiscount + exchangeBonus + loyaltyBonus + referralBonus + dsaBonus + additionalDiscount;
    var bmLower = benefitMode.toLowerCase();
    var hasScheme = totalDiscount > 0.01 || offerSum > 0.01 ||
      bmLower === 'partial benefit' || bmLower === 'no benefit';
    var bookingDate = col('Booking Date') >= 0 ? String(row[col('Booking Date')] || '').trim() : '';
    var bookingId = col('Booking ID') >= 0 ? String(row[col('Booking ID')] || '').trim() : '';
    var currentStatus = col('Current Status') >= 0 ? String(row[col('Current Status')] || '') : '';
    var csLower = currentStatus.toLowerCase();
    var isBooked = csLower === 'booked' || csLower === 'delivered' ||
      !!bookingId || !!bookingDate || bookingAmount > 0;

    // Display truth for Add Payment: ledger Outstanding Balance → payable−paid → sheet
    var outstanding;
    if (money.lastOutstanding != null && isFinite(money.lastOutstanding)) {
      outstanding = Math.max(0, round2_(money.lastOutstanding));
    } else if (customerPayable > 0) {
      outstanding = Math.max(0, round2_(customerPayable - paid));
    } else if (customerOsCol != null && isFinite(customerOsCol)) {
      if (paid <= 0.01) outstanding = Math.max(0, round2_(customerOsCol));
      else outstanding = Math.max(0, round2_(customerOsCol + num_(bookingAmount) - paid));
    } else if (paid > 0.01 && bookingAmount > 0) {
      outstanding = Math.max(0, round2_(sheetOs + bookingAmount - paid));
    } else {
      outstanding = Math.max(0, round2_(sheetOs));
    }

    list.push({
      leadId: leadId,
      customerName: customerName,
      mobile: mobile,
      mobileDisplay: maskMobile_(mobile),
      alternateMobile: col('Alternate Mobile') >= 0 ? normalizeMobile_(row[col('Alternate Mobile')]) : '',
      model: col('Interested Model') >= 0 ? row[col('Interested Model')] : '',
      interestedModel: col('Interested Model') >= 0 ? row[col('Interested Model')] : '',
      variant: col('Variant') >= 0 ? row[col('Variant')] : '',
      currentStatus: currentStatus,
      accountStatus: acct,
      bookingAmount: bookingAmount,
      bookingDate: bookingDate,
      bookingId: bookingId,
      amountReceived: paid,
      outstanding: outstanding,
      customerPayable: customerPayable || null,
      financeStatus: col('Finance Required') >= 0 ? row[col('Finance Required')] : '',
      financeRequired: col('Finance Required') >= 0 ? row[col('Finance Required')] : '',
      exchangeRequired: col('Exchange Required') >= 0 ? row[col('Exchange Required')] : '',
      deliveryStatus: col('Delivery Status') >= 0 ? row[col('Delivery Status')] : '',
      executive: col('Executive') >= 0 ? row[col('Executive')] : '',
      lastActivity: col('Last Activity') >= 0 ? row[col('Last Activity')] : '',
      nextFollowUp: col('Next Follow-up Date') >= 0 ? row[col('Next Follow-up Date')] : '',
      totalDiscount: totalDiscount,
      benefitMode: benefitMode,
      isBooked: isBooked,
      hasScheme: hasScheme,
      searchKey: [leadId, customerName, mobile].join(' ').toUpperCase(),
      nameMatchKey: customerMatchKey_(customerName)
    });
  }
  list.sort(function (a, b) {
    return String(a.customerName).localeCompare(String(b.customerName));
  });
  return list;
}

function buildLeadPickerRecord_(leadId, store) {
  store = store || loadCrmStore_();
  var l = store.leads.byId[leadId];
  if (!l) return null;
  var del = store.deliveryByLead[leadId] || {};
  var paid = store.paymentsByLead[leadId] || 0;
  var outstanding = computeDashboardOutstanding_(leadId, store);
  var searchParts = [
    leadId,
    l.customerName,
    l.mobile,
    l.alternateMobile,
    l.interestedModel,
    l.executive,
    String(outstanding)
  ];
  return {
    leadId: leadId,
    customerName: l.customerName || '',
    mobile: l.mobile || '',
    mobileDisplay: maskMobile_(l.mobile),
    alternateMobile: l.alternateMobile || '',
    model: l.interestedModel || '',
    variant: l.variant || '',
    currentStatus: l.currentStatus || '',
    accountStatus: normalizeAccountStatus_(l.accountStatus),
    bookingAmount: l.bookingAmount || 0,
    amountReceived: paid,
    outstanding: outstanding,
    financeStatus: l.financeRequired || '',
    deliveryStatus: del.delivered || '',
    executive: l.executive || '',
    lastActivity: store.lastActivityByLead[leadId] || '',
    nextFollowUp: l.nextFollowUpDate || '',
    searchKey: searchParts.join(' ').toUpperCase(),
    nameMatchKey: customerMatchKey_(l.customerName || '')
  };
}

function jsonForHtml_(obj) {
  return JSON.stringify(obj)
    .replace(/</g, '\\u003c')
    .replace(/>/g, '\\u003e')
    .replace(/&/g, '\\u0026')
    .replace(/\u2028/g, '\\u2028')
    .replace(/\u2029/g, '\\u2029');
}

function leadPickerCss_() {
  return '.lp{margin-bottom:12px}'
    + '.lp-search{width:100%;padding:10px;border:1px solid #ccc;border-radius:6px;font-size:14px;box-sizing:border-box}'
    + '.lp-opt{margin-top:8px;font-size:12px;color:#555}'
    + '.lp-status{font-size:12px;color:#666;margin:4px 0}'
    + '.lp-results{max-height:200px;overflow-y:auto;border:1px solid #e0e0e0;border-radius:6px;margin-top:6px}'
    + '.lp-hit{padding:10px 12px;border-bottom:1px solid #eee;cursor:pointer}'
    + '.lp-hit:hover{background:#E3F2FD}'
    + '.lp-hit-id{font-weight:700;font-size:13px;color:#1565C0}'
    + '.lp-hit-name{font-size:14px;margin-top:2px}'
    + '.lp-hit-mob{font-size:12px;color:#666}'
    + '.lp-hit-meta{font-size:12px;color:#444;margin-top:4px}'
    + '.lp-none{padding:12px;color:#c62828;font-size:13px}'
    + '.lp-dup-hint{margin:8px 0;padding:10px;background:#FFF3E0;border:1px solid #FFB74D;border-radius:6px;font-size:12px;color:#333}'
    + '.lp-summary{display:none;margin-top:12px;padding:12px;background:#F5F5F5;border-radius:6px;font-size:12px;line-height:1.6}'
    + '.lp-summary b{color:#333}'
    + '.lp-summary .grid{display:grid;grid-template-columns:1fr 1fr;gap:4px 12px}';
}

/** @param {Object} opts - {showClosedCheckbox:boolean, activeOnly:boolean, label:string} */
function leadPickerHtml_(opts) {
  opts = opts || {};
  var showCb = opts.showClosedCheckbox !== false;
  var label = opts.label || 'Search Lead *';
  var html = '<div class="lp">'
    + '<label>' + label + '</label>'
    + '<input type="text" id="leadSearch" class="lp-search" placeholder="Search by Lead ID, Name or Mobile..." autocomplete="off" />'
    + '<input type="hidden" id="leadId" value="" />';
  if (showCb) {
    html += '<label class="lp-opt"><input type="checkbox" id="showClosed" /> Show Closed Leads</label>';
  }
  html += '<div id="pickerStatus" class="lp-status">Loading leads...</div>'
    + '<div id="leadResults" class="lp-results"></div>'
    + '<div id="leadSummary" class="lp-summary"></div>'
    + '</div>';
  return html;
}

/**
 * Lead picker client JS — DOM-only (no HTML tags in JS strings).
 * HtmlService rejects raw angle-bracket tags inside script content.
 */
function leadPickerClientJs_(activeOnly, stage) {
  var activeOnlyFlag = activeOnly ? 'true' : 'false';
  var stageStr = stage ? String(stage) : '';
  return [
    '(function(){',
    '  var LEAD_CACHE=[];',
    '  var SELECTED_LEAD=null;',
    '  var PICKER_HITS=[];',
    '  var REQUIRE_ACTIVE=' + activeOnlyFlag + ';',
    '  var PICKER_STAGE="' + stageStr + '";',
    '  var LP_INIT_DONE=false;',
    '  function fmt(n){return Number(n||0).toLocaleString("en-IN");}',
    '  function setPickerStatus(msg){var el=document.getElementById("pickerStatus");if(el)el.textContent=msg;}',
    '  function clearNode(el){while(el&&el.firstChild)el.removeChild(el.firstChild);}',
    '  function el(tag,cls,text){var n=document.createElement(tag);if(cls)n.className=cls;if(text!=null)n.textContent=String(text);return n;}',
    '  function showMessage(box,msg){clearNode(box);box.appendChild(el("div","lp-none",msg));}',
    '  function loadLeadCache(){',
    '    if(Array.isArray(window.__LEAD_CACHE_SEEDED)){',
    '      LEAD_CACHE=window.__LEAD_CACHE_SEEDED;',
    '      setPickerStatus(LEAD_CACHE.length + " Active Leads Loaded");',
    '      var q0=document.getElementById("leadSearch"); if(q0&&q0.value.trim()){onLeadSearch();}',
    '      return;',
    '    }',
    '    setPickerStatus("Loading leads...");',
    '    google.script.run',
    '      .withSuccessHandler(function(data){',
    '        LEAD_CACHE=data||[];',
    '        setPickerStatus(LEAD_CACHE.length + " Active Leads Loaded");',
    '        var q=document.getElementById("leadSearch");',
    '        if(q&&q.value.trim()){onLeadSearch();}',
    '      })',
    '      .withFailureHandler(function(e){',
    '        var msg=(e&&e.message)?e.message:String(e);',
    '        setPickerStatus("Unable to load leads. Reason: " + msg);',
    '        var box=document.getElementById("leadResults");',
    '        if(box)showMessage(box,"Unable to load leads. Reason: "+msg);',
    '      })',
    '      .getActiveLeadsForPicker();',
    '  }',
    '  function onLeadSearch(){',
    '    var q=document.getElementById("leadSearch").value.trim().toUpperCase();',
    '    var box=document.getElementById("leadResults");',
    '    var showClosedEl=document.getElementById("showClosed");',
    '    var showClosed=showClosedEl?showClosedEl.checked:false;',
    '    SELECTED_LEAD=null;document.getElementById("leadId").value="";',
    '    document.getElementById("leadSummary").style.display="none";',
    '    if(!q.length){clearNode(box);return;}',
    '    PICKER_HITS=LEAD_CACHE.filter(function(l){',
    '      if(l.accountStatus==="Archived") return false;',
    '      if(!showClosed){if(l.accountStatus!=="Active") return false;}',
    '      else {if(["Active","Closed","Cancelled"].indexOf(l.accountStatus)===-1) return false;}',
    '      if(REQUIRE_ACTIVE&&!showClosed&&l.accountStatus!=="Active") return false;',
    '      if(typeof PICKER_STAGE!=="undefined"&&PICKER_STAGE){',
    '        var cs=String(l.currentStatus||"").toLowerCase();',
    '        var ds=String(l.deliveryStatus||"").toLowerCase();',
    '        if(PICKER_STAGE==="delivery"&&(ds==="delivered"||cs==="delivered")) return false;',
    '        if(PICKER_STAGE==="booking"&&(cs==="booked"||cs==="delivered")) return false;',
    '        if(PICKER_STAGE==="close"&&(cs==="delivered"||l.accountStatus!=="Active")) return false;',
    '      }',
    '      return l.searchKey.indexOf(q)>=0;',
    '    }).slice(0,25);',
    '    clearNode(box);',
    '    if(PICKER_HITS.length===0){showMessage(box,"No active lead found.");return;}',
    '    if(PICKER_HITS.length>=2){',
    '      var keys={};PICKER_HITS.forEach(function(l){if(l.nameMatchKey)keys[l.nameMatchKey]=(keys[l.nameMatchKey]||0)+1;});',
    '      var dupKey=null;Object.keys(keys).forEach(function(k){if(keys[k]>=2)dupKey=k;});',
    '      if(dupKey){',
    '        var ids=PICKER_HITS.filter(function(l){return l.nameMatchKey===dupKey;}).map(function(l){return l.leadId;});',
    '        var hint=el("div","lp-dup-hint");',
    '        hint.appendChild(el("b",null,"Same company? "));',
    '        hint.appendChild(document.createTextNode("Multiple Lead IDs found: "+ids.join(", ")+". Use CRM - Merge Duplicate Leads to combine them."));',
    '        box.appendChild(hint);',
    '      }',
    '    }',
    '    PICKER_HITS.forEach(function(l,i){',
    '      var hit=el("div","lp-hit");',
    '      hit.onclick=(function(idx){return function(){pickLead(idx);};})(i);',
    '      hit.appendChild(el("div","lp-hit-id",l.leadId));',
    '      hit.appendChild(el("div","lp-hit-name",l.customerName));',
    '      hit.appendChild(el("div","lp-hit-mob",l.mobileDisplay));',
    '      hit.appendChild(el("div","lp-hit-meta",(l.currentStatus||"")+" · Outstanding \u20B9"+fmt(l.outstanding)));',
    '      box.appendChild(hit);',
    '    });',
    '  }',
    '  function pickLead(i){',
    '    SELECTED_LEAD=PICKER_HITS[i];',
    '    window.SELECTED_LEAD=SELECTED_LEAD;',
    '    document.getElementById("leadId").value=SELECTED_LEAD.leadId;',
    '    document.getElementById("leadSearch").value=SELECTED_LEAD.leadId+" - "+SELECTED_LEAD.customerName;',
    '    clearNode(document.getElementById("leadResults"));',
    '    fillLeadSummary(SELECTED_LEAD);',
    '    if(typeof window.onLeadPicked==="function"){try{window.onLeadPicked(SELECTED_LEAD);}catch(cbErr){console.error("onLeadPicked:",cbErr);}}',
    '    if(document.getElementById("finalOutstanding")){document.getElementById("finalOutstanding").value=SELECTED_LEAD.outstanding;}',
    '    if(document.getElementById("exec")&&SELECTED_LEAD.executive){',
    '      var ex=document.getElementById("exec");',
    '      for(var j=0;j!==ex.options.length;j++){if(ex.options[j].value===SELECTED_LEAD.executive){ex.selectedIndex=j;break;}}',
    '    }',
    '  }',
    '  function addSummaryRow(grid,label,value){',
    '    var row=el("div");',
    '    row.appendChild(el("b",null,label+": "));',
    '    row.appendChild(document.createTextNode(value==null?"":String(value)));',
    '    grid.appendChild(row);',
    '  }',
    '  function fillLeadSummary(l){',
    '    var s=document.getElementById("leadSummary");',
    '    s.style.display="block";',
    '    clearNode(s);',
    '    var grid=el("div","grid");',
    '    addSummaryRow(grid,"Customer",l.customerName);',
    '    addSummaryRow(grid,"Lead ID",l.leadId);',
    '    addSummaryRow(grid,"Mobile",l.mobile);',
    '    addSummaryRow(grid,"Model",l.model);',
    '    addSummaryRow(grid,"Variant",l.variant);',
    '    addSummaryRow(grid,"Status",l.currentStatus);',
    '    addSummaryRow(grid,"Booking Amt","\u20B9"+fmt(l.bookingAmount));',
    '    addSummaryRow(grid,"Received","\u20B9"+fmt(l.amountReceived));',
    '    addSummaryRow(grid,"Outstanding","\u20B9"+fmt(l.outstanding));',
    '    var calc=el("div"); calc.id="payCalcHint"; calc.style.cssText="grid-column:1/-1;margin-top:6px;padding:6px 8px;background:#E8F5E9;border-radius:4px;font-size:12px;color:#1B5E20";',
    '    calc.textContent="Enter amount to preview Received + Outstanding after payment.";',
    '    grid.appendChild(calc);',
    '    addSummaryRow(grid,"Finance",l.financeStatus);',
    '    addSummaryRow(grid,"Delivery",l.deliveryStatus);',
    '    addSummaryRow(grid,"Executive",l.executive);',
    '    addSummaryRow(grid,"Last Activity",l.lastActivity);',
    '    addSummaryRow(grid,"Next Follow-up",l.nextFollowUp);',
    '    addSummaryRow(grid,"Account",l.accountStatus);',
    '    s.appendChild(grid);',
    '  }',
    '  window.validateLeadPick=function(){',
    '    if(!SELECTED_LEAD||!SELECTED_LEAD.leadId){alert("No active lead found. Please search and select a lead.");return false;}',
    '    if(REQUIRE_ACTIVE&&SELECTED_LEAD.accountStatus!=="Active"){alert("This lead is not active. Select an active lead or check Show Closed Leads.");return false;}',
    '    return true;',
    '  };',
    '  window.getPickedLeadId=function(){return SELECTED_LEAD?SELECTED_LEAD.leadId:"";};',
    '  window.updatePickedLeadSummary=function(fields){',
    '    if(!SELECTED_LEAD||!fields)return;',
    '    if(fields.outstanding!=null)SELECTED_LEAD.outstanding=Number(fields.outstanding)||0;',
    '    if(fields.bookingAmount!=null)SELECTED_LEAD.bookingAmount=Number(fields.bookingAmount)||0;',
    '    if(fields.amountReceived!=null)SELECTED_LEAD.amountReceived=Number(fields.amountReceived)||0;',
    '    fillLeadSummary(SELECTED_LEAD);',
    '  };',
    '  window.pickLead=pickLead;',
    '  function initializeLeadPicker(){',
    '    if(LP_INIT_DONE) return;',
    '    LP_INIT_DONE=true;',
    '    setPickerStatus("Initialization started...");',
    '    var s=document.getElementById("leadSearch"); if(s){s.addEventListener("input",onLeadSearch);}',
    '    var cb=document.getElementById("showClosed"); if(cb){cb.addEventListener("change",onLeadSearch);}',
    '    loadLeadCache();',
    '  }',
    '  try {',
    '    if(document.readyState==="loading"){document.addEventListener("DOMContentLoaded",initializeLeadPicker);} else {initializeLeadPicker();}',
    '    window.addEventListener("load",initializeLeadPicker);',
    '    setTimeout(initializeLeadPicker,0);',
    '  } catch(initErr) {',
    '    setPickerStatus("Unable to initialize lead search. Reason: " + (initErr.message||initErr));',
    '  }',
    '})();'
  ].join('\n');
}

function dialogWithLeadPicker_(title, btnColor, btnLabel, bodyHtml, saveJs, opts) {
  opts = opts || {};
  var activeOnly = opts.activeOnly !== false;
  var seeded = opts.seedLeads || [];
  var html = createDialogOutput_(
    dialogBaseCss_(btnColor) + '<style>' + leadPickerCss_() + '</style>'
    + bodyHtml
    + '<button class="btn" id="btn" type="button" onclick="doSave()">' + btnLabel + '</button>'
    + htmlScript_(dialogClientHelpersJs_())
    + htmlScript_('window.__LEAD_CACHE_SEEDED=' + jsonForHtml_(seeded) + ';')
    + htmlScript_(leadPickerClientJs_(activeOnly, opts.stage))
    + (saveJs ? htmlScript_(saveJs) : ''),
    opts.width || 440,
    opts.height || 580
  );
  SpreadsheetApp.getUi().showModalDialog(html, title);
}
