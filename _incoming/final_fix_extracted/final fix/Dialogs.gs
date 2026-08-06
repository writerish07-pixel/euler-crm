/**
 * Dialog-based UI – smart lead picker on all operational forms.
 */

/**
 * HtmlService.createHtmlOutput treats "<" inside <script> as HTML tags
 * (e.g. "'<div'", "</option>") and throws Malformed HTML content.
 *
 * Escape ONLY tag-like sequences. Do NOT escape JS operators (<=, <, <<):
 * turning "amt<=0" into "amt\u003c=0" is a SyntaxError and kills the dialog JS
 * (picker stuck on "Loading leads...").
 */
function htmlSafeJs_(code) {
  // Inside a <script> block the ONLY sequences that can terminate or corrupt it are
  // a literal "</script" and the legacy comment opener "<!--". Escaping every "<"
  // followed by a letter also rewrote JS comparison operators — e.g.
  //   for (var i = 0; i < OFFER_IDS.length; i++)
  // became  i\u003cOFFER_IDS.length , a SyntaxError that killed the ENTIRE script
  // block. The block then never ran, so window.onLeadPicked was never defined and
  // the lead picker silently skipped it (it only fires the callback when
  // typeof window.onLeadPicked === "function"). That is what left Scheme Update
  // with empty dropdowns and no error.
  //
  // \u003c is a valid escape for "<" inside JS strings and regex literals, so the
  // two targeted replacements below stay correct wherever they legitimately occur.
  // Note: makeVoidElementsXmlSafe_() already skips <script> blocks, so script
  // content never needs XML-safe escaping.
  return String(code || '')
    .replace(/<\/(script)/gi, '\\u003c/$1')
    .replace(/<!--/g, '\\u003c!--');
}

function htmlScript_(code) {
  return '<script>' + htmlSafeJs_(code) + '</script>';
}

/**
 * HtmlService IFRAME mode needs well-formed void tags (self-closing inputs)
 * and a full HTML document wrapper.
 */
function makeVoidElementsXmlSafe_(html) {
  var parts = String(html || '').split(/(<script\b[^>]*>[\s\S]*?<\/script>)/i);
  for (var i = 0; i < parts.length; i++) {
    if (/^<script\b/i.test(parts[i])) continue;
    parts[i] = parts[i].replace(
      /<(input|br|hr|img|meta|link|col|area|base|embed|param|source|track|wbr)(\s[^>]*?)?\s*\/?>/gi,
      function (m, tag, attrs) {
        attrs = attrs || '';
        attrs = attrs.replace(/\s(disabled|required|checked|readonly|selected|multiple)(?=(\s|\/|$))/gi, function (_, a) {
          return ' ' + a.toLowerCase() + '="' + a.toLowerCase() + '"';
        });
        attrs = attrs.replace(/\s*\/\s*$/, '');
        return '<' + String(tag).toLowerCase() + attrs + ' />';
      }
    );
  }
  return parts.join('');
}

function createDialogOutput_(innerHtml, width, height) {
  var body = makeVoidElementsXmlSafe_(innerHtml);
  // IFRAME sandbox requires XML-safe void tags (including <base />).
  var doc = '<!DOCTYPE html><html><head><base target="_top" /></head><body>' + body + '</body></html>';
  var out = HtmlService.createHtmlOutput(doc);
  if (width) out.setWidth(width);
  if (height) out.setHeight(height);
  return out;
}

/** Shared client-side JS injected into every dialog. */
function dialogClientHelpersJs_() {
  return [
    'function setSaving(on,label){var b=document.getElementById("btn");if(!b)return;b.disabled=!!on;b.textContent=on?"Saving...":(label||b.getAttribute("data-label")||"Save");}',
    'function kickDeferredCrmRefresh(cb){var done=false;function fin(){if(done)return;done=true;if(cb)cb();}try{google.script.run.withSuccessHandler(fin).withFailureHandler(fin).refreshDashboardNow();}catch(_e){fin();}setTimeout(fin,1200);}',
    'function softTimeoutAlert(opName){',
    '  alert((opName||"Save")+" is taking longer than usual.\\n\\nOften the data IS already saved.\\nCheck the sheet / Audit Log before saving again.\\n\\nIf the record is there, close this form and continue.");',
    '}',
    'function parseServerError(e){',
    '  if(!e)return"Unknown error";',
    '  if(typeof e==="string")return e;',
    '  var raw=(e.message||"").trim();',
    '  if(e.fieldLabel)return String(e.fieldLabel)+": "+String(e.detail||raw);',
    '  var low=raw.toLowerCase();',
    '  if(low.indexOf("authorization is required")>=0||low.indexOf("permission_denied")>=0){',
    '    return "CRM authorization required.\\n\\n1. Click OK and retry Save\\n2. When Google asks, click Allow\\n3. Owner: CRM → Go-Live Quick Fix\\n4. Shared as Editor on this spreadsheet";',
    '  }',
    '  if(e.success===false){',
    '    if(raw.indexOf("Please fix")>=0)return raw;',
    '    if(raw.indexOf("Function:")===-1)return raw||"Operation failed";',
    '    return raw||"Operation failed";',
    '  }',
    '  if(raw.indexOf("Function:")>=0){',
    '    var ix=raw.indexOf("Error:");',
    '    if(ix>=0){',
    '      var rest=raw.substring(ix+6);',
    '      var cut=rest.indexOf("\\nCode:");',
    '      if(cut===-1)cut=rest.indexOf("\\nSuggested");',
    '      if(cut>=0)rest=rest.substring(0,cut);',
    '      return rest.trim()||raw;',
    '    }',
    '  }',
    '  return raw||JSON.stringify(e);',
    '}',
    'function handleServerSuccess(res,onOk){',
    '  if(res&&res.success===false){alert(parseServerError(res));return;}',
    '  kickDeferredCrmRefresh();',
    '  if(typeof onOk==="function")onOk(res);',
    '}',
    'function runDialogAction(label,serverFn,getData,onOk){',
    '  var b=document.getElementById("btn");if(b&&!b.getAttribute("data-label"))b.setAttribute("data-label",label);',
    '  setSaving(true,label);',
    '  var done=false;',
    '  var timer=setTimeout(function(){',
    '    if(done)return;done=true;setSaving(false,label);',
    '    softTimeoutAlert(label||serverFn);',
    '  },45000);',
    '  try{',
    '    var payload=(typeof getData==="function")?getData():{};',
    '    var runner=google.script.run',
    '      .withSuccessHandler(function(res){try{if(done)return;done=true;clearTimeout(timer);setSaving(false,label);handleServerSuccess(res,function(r){if(onOk)onOk(r);});}finally{setSaving(false,label);}})',
    '      .withFailureHandler(function(e){try{if(done)return;done=true;clearTimeout(timer);alert(parseServerError(e));}finally{setSaving(false,label);}});',
    '    runner[serverFn](payload);',
    '  }catch(ex){try{if(!done){done=true;clearTimeout(timer);alert(parseServerError(ex));}}finally{setSaving(false,label);}}',
    '}'
  ].join('\n');
}

function dialogBaseCss_(btnColor) {
  return '<style>'
    + 'body{font-family:Arial,sans-serif;padding:12px;margin:0}'
    + 'label{display:block;margin-top:10px;font-size:13px;font-weight:600}'
    + 'input,select,textarea{width:100%;margin:4px 0 0;padding:8px;box-sizing:border-box;font-size:14px}'
    + '.btn{margin-top:16px;background:' + btnColor + ';color:#fff;border:none;padding:12px;width:100%;'
    + 'cursor:pointer;border-radius:4px;font-size:14px;font-weight:600}'
    + '.btn:disabled{opacity:0.55;cursor:wait}'
    + '</style>';
}

function showNewLeadDialog_() {
  var m = getMergedMasters_();
  var variantByModel = getVariantOptionsByModel_();
  var today = nowDate_();
  var html = createDialogOutput_(
dialogBaseCss_('#1976D2') +
    '<h3>New Lead</h3>' +
    '<label>Created Date *</label><input id="createdDate" type="date" value="' + today + '">' +
    '<label>Customer Name *</label><input id="name">' +
    '<label>Mobile *</label><input id="mobile" maxlength="10">' +
    '<label>Lead Source</label><select id="source">' + buildSelectOptionsHtml_(m['Lead Sources']) + '</select>' +
    '<label>Model</label><select id="model">' + buildSelectOptionsHtml_(m['Models'], true) + '</select>' +
    '<label>Variant</label><select id="variant"></select>' +
    '<label>Executive</label><select id="exec">' + buildSelectOptionsHtml_(m['Executives'], true) + '</select>' +
    '<label>Priority</label><select id="priority">' + buildSelectOptionsHtml_(m['Priority']) + '</select>' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Create Lead" onclick="doSave()">Create Lead</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
    'var VARIANT_BY_MODEL=' + jsonForHtml_(variantByModel) + ';' +
    'var ALL_VARIANTS=' + jsonForHtml_(m['Variants'] || []) + ';' +
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/\\u003c/g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}' +
    'function setVariantOptions(list){' +
    '  var el=document.getElementById("variant");' +
    '  var opts=["<option value=\\"\\"></option>"];' +
    '  (list||[]).forEach(function(v){opts.push("<option value=\\""+esc(v)+"\\">"+esc(v)+"</option>");});' +
    '  el.innerHTML=opts.join("");' +
    '}' +
    'function refreshVariantByModel(){' +
    '  var model=document.getElementById("model").value||"";' +
    '  var list=VARIANT_BY_MODEL[model]||[];' +
    '  if(!list.length&&model){' +
    '    var mk=Object.keys(VARIANT_BY_MODEL).find(function(k){return String(k).toLowerCase()===String(model).toLowerCase();});' +
    '    if(mk) list=VARIANT_BY_MODEL[mk]||[];' +
    '  }' +
    '  if(!list.length) list=ALL_VARIANTS;' +
    '  setVariantOptions(list);' +
    '}' +
    'function doSave(){' +
    'runDialogAction("Create Lead","createNewLeadFromDialog",function(){' +
    'return{createdDate:document.getElementById("createdDate").value,customerName:document.getElementById("name").value,mobile:document.getElementById("mobile").value,' +
    'leadSource:document.getElementById("source").value,interestedModel:document.getElementById("model").value,' +
    'variant:document.getElementById("variant").value,executive:document.getElementById("exec").value,priority:document.getElementById("priority").value,' +
    'remarks:document.getElementById("remarks").value};},function(res){' +
    'var id=(res&&res.data&&res.data.leadId)||(res&&res.data)||res;' +
    'alert("Lead created: "+id);' +
    'try{google.script.run.withFailureHandler(function(){}).refreshCrmAfterDialogSave();}catch(_e){}' +
    'google.script.host.close();});}' +
    'document.getElementById("model").addEventListener("change",refreshVariantByModel);' +
    'refreshVariantByModel();'
    ),
    380,
    560
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'New Lead');
}

function createNewLeadFromDialog(data) {
  try {
    if (!data || !String(data.customerName || '').trim()) {
      return crmFailStructured_('Lead', 'createNewLeadFromDialog', 'validate',
        fieldError_('Customer Name', 'Enter the customer name.', 'VALIDATION'), 0);
    }
    if (!data.mobile) {
      return crmFailStructured_('Lead', 'createNewLeadFromDialog', 'validate',
        fieldError_('Mobile', 'Enter a valid 10-digit mobile number.', 'VALIDATION'), 0);
    }
    if (!data.createdDate) {
      return crmFailStructured_('Lead', 'createNewLeadFromDialog', 'validate',
        fieldError_('Created Date', 'Select the lead created date.', 'VALIDATION'), 0);
    }
    data.createdDate = formatDate_(data.createdDate);
    if (!data.createdDate) {
      return crmFailStructured_('Lead', 'createNewLeadFromDialog', 'validate',
        fieldError_('Created Date', 'Enter a valid date.', 'VALIDATION'), 0);
    }
    return createNewLead_(data);
  } catch (e) {
    return crmFailStructured_('Lead', 'createNewLeadFromDialog', 'handler', e, 0);
  }
}

function showAddActivityDialog_() {
  var m = getMergedMasters_();
  var activityTypes = getFollowUpActivityTypes_();
  if (!activityTypes.length) activityTypes = getActivityTypeMaster_();
  var seedLeads = getActiveLeadsForPicker_({ activeOnly: true });
  dialogWithLeadPicker_('Add Activity', '#388E3C', 'Add Activity',
    '<h3>Add Activity</h3>' +
    '<div class="hint">Open leads only — follow-up activities (Call, Visit, Follow-up, etc.)</div>' +
    leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true }) +
    '<label>Activity Type</label><select id="type">' + buildSelectOptionsHtml_(activityTypes) + '</select>' +
    '<label>Discussion</label><textarea id="discussion" rows="3"></textarea>' +
    '<label>Next Follow-up Date</label><input id="followup" type="date">' +
    '<label>Executive</label><select id="exec">' + buildSelectOptionsHtml_(m['Executives'], true) + '</select>',
    'function doSave(){if(!validateLeadPick())return;var b=document.getElementById("btn");b.disabled=true;b.textContent="Saving...";' +
    'var done=false;function reset(){b.disabled=false;b.textContent="Add Activity";}' +
    'var t=setTimeout(function(){if(done)return;done=true;reset();softTimeoutAlert("Activity save");},45000);' +
    'try{var d={leadId:getPickedLeadId(),activityType:document.getElementById("type").value,' +
    'discussion:document.getElementById("discussion").value,nextFollowUp:document.getElementById("followup").value,' +
    'executive:document.getElementById("exec").value};' +
    'google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(t);reset();' +
    'if(res&&res.success===false){alert(parseServerError(res));return;}' +
    'var rc=(res&&res.data&&res.data.activityId)||res;' +
    'alert("Activity added: "+rc);kickDeferredCrmRefresh(function(){google.script.host.close();});})' +
    '.withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(e.message||e);})' +
    '.addActivityFromDialog(d);}catch(ex){if(done)return;done=true;clearTimeout(t);reset();alert(ex.message||ex);}}',
    { height: 640, activeOnly: true, seedLeads: seedLeads }
  );
}

function addActivityFromDialog(data) {
  try {
    if (!data.leadId) {
      return crmFailStructured_('Activity', 'addActivityFromDialog', 'validate',
        businessError_('Lead ID is required', 'VALIDATION'), 0);
    }
    assertActivityTypeValid_(data.activityType);
    requireActiveLead_(data.leadId);
    return addActivity_(data);
  } catch (e) {
    return crmFailStructured_('Activity', 'addActivityFromDialog', 'handler', e, 0);
  }
}

function showAddPaymentDialog_() {
  var m = getMergedMasters_();
  var today = nowDate_();
  var seedLeads = getActiveLeadsForPicker_();
  var financers = m['Financers'] || CRM.MASTERS.SECTIONS['Financers'] || [];
  dialogWithLeadPicker_('Add Payment', '#F57C00', 'Record Payment',
    '<h3>Add Payment</h3>' + leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true }) +
    '<label>Payment Date *</label><input id="payDate" type="date" value="' + today + '">' +
    '<div style="font-size:12px;color:#455A64;margin:8px 0 4px;">Record the full down payment in one go — add a line per mode (e.g. part Card, part Cash, balance Finance).</div>' +
    '<div id="payRows"></div>' +
    '<button type="button" id="addRowBtn" style="margin:6px 0 10px;padding:6px 10px;font-size:13px;cursor:pointer;">+ Add another payment line</button>' +
    '<div id="payTotal" style="font-weight:bold;margin:4px 0 8px;"></div>' +
    '<label>Narration</label><input id="narration" autocomplete="off">' +
    '<script id="payModeOpts" type="text/template">' + buildSelectOptionsHtml_(m['Payment Modes']) + '</script>' +
    '<script id="payFinOpts" type="text/template">' + buildSelectOptionsHtml_(financers, true) + '</script>',
    'var MODE_OPTS=(document.getElementById("payModeOpts")||{}).innerHTML||"";' +
    'var FIN_OPTS=(document.getElementById("payFinOpts")||{}).innerHTML||"";' +
    'var ROW_N=0;' +
    'function addPayRow(){' +
    '  ROW_N++;var i=ROW_N;var box=document.getElementById("payRows");if(!box)return;' +
    '  var d=document.createElement("div");d.className="payRow";d.setAttribute("data-i",i);' +
    '  d.style.cssText="border:1px solid #E0E0E0;border-radius:4px;padding:8px;margin-bottom:8px;";' +
    '  d.innerHTML="<div style=\'display:flex;gap:6px;align-items:flex-end\'>"+' +
    '    "<div style=\'flex:1\'><label>Amount *</label><input class=\'payAmt\' id=\'amt_"+i+"\' type=\'number\' min=\'0\' step=\'0.01\' /></div>"+' +
    '    "<div style=\'flex:1\'><label>Mode</label><select class=\'payMode\' id=\'mode_"+i+"\'>"+MODE_OPTS+"</select></div>"+' +
    '    "<button type=\'button\' class=\'rmRow\' data-i=\'"+i+"\' style=\'padding:6px 8px;cursor:pointer\'>\u2715</button></div>"+' +
    '    "<div class=\'finBlk\' id=\'fin_"+i+"\' style=\'display:none;margin-top:6px;padding:6px;background:#FFF3E0;border-radius:4px\'>"+' +
    '    "<label>Financer Name *</label><select class=\'payFin\' id=\'financer_"+i+"\'>"+FIN_OPTS+"</select>"+' +
    '    "<div style=\'font-size:11px;color:#666;margin-top:4px\'>Finance File Number is auto-generated (FN26\u2026); an existing open file is reused.</div></div>";' +
    '  box.appendChild(d);togglePayRow(i);updatePayCalc();' +
    '}' +
    'function togglePayRow(i){var sel=document.getElementById("mode_"+i);var blk=document.getElementById("fin_"+i);' +
    '  if(!sel||!blk)return;blk.style.display=(String(sel.value||"").toLowerCase()==="finance")?"block":"none";}' +
    'function payRows(){var out=[];var els=document.querySelectorAll(".payRow");' +
    '  for(var k=0;k<els.length;k++){var i=els[k].getAttribute("data-i");' +
    '    var a=document.getElementById("amt_"+i);var mo=document.getElementById("mode_"+i);var fi=document.getElementById("financer_"+i);' +
    '    var amt=a?Number(a.value||0):0;if(!(amt>0))continue;' +
    '    out.push({amount:amt,paymentMode:mo?mo.value:"",financerName:fi?fi.value:""});}' +
    '  return out;}' +
    'document.addEventListener("change",function(e){if(e.target&&e.target.className&&String(e.target.className).indexOf("payMode")>=0){togglePayRow(e.target.id.replace("mode_",""));}});' +
    'document.addEventListener("input",function(e){if(e.target&&e.target.className&&String(e.target.className).indexOf("payAmt")>=0)updatePayCalc();});' +
    'document.addEventListener("click",function(e){' +
    '  if(e.target&&e.target.id==="addRowBtn"){addPayRow();}' +
    '  else if(e.target&&e.target.className&&String(e.target.className).indexOf("rmRow")>=0){' +
    '    var els=document.querySelectorAll(".payRow");if(els.length<=1)return;' +
    '    var i=e.target.getAttribute("data-i");var n=document.querySelector(".payRow[data-i=\'"+i+"\']");if(n)n.parentNode.removeChild(n);updatePayCalc();}' +
    '});' +
    'function updatePayCalc(){' +
    '  var hint=document.getElementById("payCalcHint"); if(!hint||!window.SELECTED_LEAD)return;' +
    '  var rws=payRows();var amt=0;for(var q=0;q<rws.length;q++)amt+=Number(rws[q].amount||0);' +
    '  var tEl=document.getElementById("payTotal");if(tEl)tEl.textContent=rws.length?("Total this entry: \u20B9"+Number(amt).toLocaleString("en-IN",{maximumFractionDigits:2})+" across "+rws.length+" line(s)"):"";' +
    '  var recv=Number(SELECTED_LEAD.amountReceived)||0;' +
    '  var os=Number(SELECTED_LEAD.outstanding)||0;' +
    '  var fmt=function(n){return Number(n||0).toLocaleString("en-IN",{maximumFractionDigits:2});};' +
    '  if(!(amt>0)){hint.textContent="Ledger: Received \\u20B9"+fmt(recv)+" | Outstanding \\u20B9"+fmt(os);return;}' +
    '  hint.textContent="After this payment \\u2192 Received \\u20B9"+fmt(recv+amt)+" | Outstanding \\u20B9"+fmt(Math.max(0,os-amt));' +
    '}' +
    'document.getElementById("amount").addEventListener("input",updatePayCalc);' +
    'window.onLeadPicked=function(){updatePayCalc();};' +
    'addPayRow();' +
    'function doSave(){' +
    'if(!validateLeadPick())return;' +
    'var b=document.getElementById("btn");b.disabled=true;b.textContent="Saving...";' +
    'var done=false;' +
    'function resetBtn(){b.disabled=false;b.textContent="Record Payment";}' +
    'var watchdog=setTimeout(function(){if(done)return;done=true;resetBtn();softTimeoutAlert("Payment save");},45000);' +
    'try{' +
    'var rows=payRows();' +
    'var d={leadId:getPickedLeadId(),date:document.getElementById("payDate").value,' +
    'payments:rows,narration:document.getElementById("narration").value};' +
    'if(!d.date){clearTimeout(watchdog);done=true;resetBtn();alert("Payment date is required");return;}' +
    'if(!rows.length){clearTimeout(watchdog);done=true;resetBtn();alert("Enter at least one payment amount");return;}' +
    'for(var q=0;q<rows.length;q++){' +
    '  if(String(rows[q].paymentMode||"").toLowerCase()==="finance"&&!String(rows[q].financerName||"").trim()){' +
    '    clearTimeout(watchdog);done=true;resetBtn();alert("Financer name is required for the Finance line (line "+(q+1)+")");return;}' +
    '}' +
    'for(var q2=0;q2<rows.length;q2++){rows[q2].narration=d.narration;}' +
    'google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(watchdog);' +
    'if(res&&res.success===false){resetBtn();alert(res.message||res);return;}' +
    'var rcs=(res&&res.data&&res.data.receipts)||[];' +
    'var msg="Payment Saved Successfully\\n"+(rcs.length>1?("Receipts: "+rcs.join(", ")):("Receipt Number: "+(rcs[0]||"")));' +
    'var fn=(res&&res.data&&res.data.financeFileNumber)||"";' +
    'if(fn)msg+="\\nFinance File: "+fn;' +
    'var w=(res&&res.data&&res.data.warning)?res.data.warning:(res&&res.warning?res.warning:null);' +
    'if(w){msg+="\\n\\nNote: "+w;}alert(msg);kickDeferredCrmRefresh(function(){google.script.host.close();});})' +
    '.withFailureHandler(function(e){if(done)return;done=true;clearTimeout(watchdog);resetBtn();alert("Payment save failed: "+(e&&e.message?e.message:e));})' +
    '.addPaymentsBatchFromDialog(d);' +
    '}catch(ex){if(done)return;done=true;clearTimeout(watchdog);resetBtn();alert("Payment form error: "+(ex&&ex.message?ex.message:ex));}' +
    '}',
    { height: 700, activeOnly: true, seedLeads: seedLeads }
  );
}

/**
 * Record money received from financer against an existing pending file.
 * Only pending (Open / File Outstanding > 0) files appear in the list.
 */
function showRecordFinancerReceiptDialog_() {
  var today = nowDate_();
  var html = createDialogOutput_(
'<style>body{font-family:Arial,sans-serif;padding:12px;font-size:13px}' +
    'label{display:block;margin-top:10px;font-weight:600}input,select,textarea{width:100%;padding:8px;box-sizing:border-box;margin-top:4px}' +
    'button{margin-top:16px;width:100%;padding:10px;background:#E65100;color:#fff;border:none;border-radius:4px;font-size:14px;cursor:pointer}' +
    'button:disabled{opacity:.55}.hint{font-size:12px;color:#666;margin:6px 0 10px}.meta{font-size:12px;background:#FFF8E1;padding:8px;border-radius:4px;margin-top:8px}</style>' +
    '<h3 style="margin:0 0 6px">Record Financer Receipt</h3>' +
    '<div class="hint">Only pending finance files are listed. Settled files are hidden.</div>' +
    '<div id="status">Loading pending files…</div>' +
    '<label>Pending File *</label><select id="fileSelect"><option value="">— Select —</option></select>' +
    '<div id="meta" class="meta" style="display:none"></div>' +
    '<label>Receipt Date *</label><input id="payDate" type="date" value="' + today + '">' +
    '<label>Amount Received *</label><input id="amount" type="number" min="1" step="0.01">' +
    '<label>Narration</label><input id="narration" placeholder="Financer disbursement / tranche">' +
    '<button id="btn" type="button" onclick="doSave()">Save Financer Receipt</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
    'var FILES=[];' +
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/\\u003c/g,"&lt;").replace(/"/g,"&quot;");}' +
    'function fmt(n){return Number(n||0).toLocaleString("en-IN");}' +
    'function parseServerError(e){if(!e)return"Error";if(typeof e==="string")return e;var raw=(e.message||"").trim();if(e.fieldLabel)return String(e.fieldLabel)+": "+String(e.detail||raw);if(raw.indexOf("Function:")>=0){var ix=raw.indexOf("Error:");if(ix>=0){var rest=raw.substring(ix+6);var cut=rest.indexOf("\\nCode:");if(cut===-1)cut=rest.indexOf("\\nSuggested");if(cut>=0)rest=rest.substring(0,cut);return rest.trim()||raw;}}return raw||JSON.stringify(e);}' +
    'function applyFiles(res){' +
    '  var st=document.getElementById("status");' +
    '  if(!res||res.success===false){st.textContent=(res&&res.message)||"Failed to load files";return;}' +
    '  FILES=res.files||[];' +
    '  var sel=document.getElementById("fileSelect");' +
    '  sel.innerHTML="<option value=\\"\\">— Select —</option>";' +
    '  if(!FILES.length){st.textContent="No pending finance files.";return;}' +
    '  st.textContent=FILES.length+" pending file(s)";' +
    '  FILES.forEach(function(f){' +
    '    var o=document.createElement("option");o.value=f.fileNumber;' +
    '    o.textContent=f.fileNumber+" | "+(f.customerName||"")+" | "+(f.financer||"")+" | OS \\u20B9"+fmt(f.fileOutstanding);' +
    '    sel.appendChild(o);' +
    '  });' +
    '}' +
    'function onFileChange(){' +
    '  var id=document.getElementById("fileSelect").value;' +
    '  var f=FILES.filter(function(x){return x.fileNumber===id;})[0];' +
    '  var meta=document.getElementById("meta");' +
    '  if(!f){meta.style.display="none";document.getElementById("amount").value="";return;}' +
    '  meta.style.display="block";' +
    '  meta.innerHTML="<div><b>Lead:</b> "+esc(f.leadId)+" — "+esc(f.customerName)+"</div>"' +
    '    +"<div><b>Financer:</b> "+esc(f.financer)+"</div>"' +
    '    +"<div><b>Sanctioned:</b> \\u20B9"+fmt(f.sanctionedAmount)+" | <b>Received:</b> \\u20B9"+fmt(f.receivedAgainstFile)+"</div>"' +
    '    +"<div><b>File Outstanding:</b> \\u20B9"+fmt(f.fileOutstanding)+"</div>";' +
    '  document.getElementById("amount").value=Number(f.fileOutstanding||0);' +
    '}' +
    'document.getElementById("fileSelect").addEventListener("change",onFileChange);' +
    'function doSave(){' +
    '  var fileNumber=document.getElementById("fileSelect").value;' +
    '  if(!fileNumber){alert("Select a pending file");return;}' +
    '  var amount=document.getElementById("amount").value;' +
    '  var date=document.getElementById("payDate").value;' +
    '  if(!date){alert("Date is required");return;}' +
    '  if(!(Number(amount)>0)){alert("Enter a valid amount");return;}' +
    '  var b=document.getElementById("btn");b.disabled=true;b.textContent="Saving...";' +
    '  var done=false;function reset(){b.disabled=false;b.textContent="Save Financer Receipt";}' +
    '  var t=setTimeout(function(){if(done)return;done=true;reset();softTimeoutAlert("Financer receipt save");},45000);' +
    '  google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(t);reset();' +
    '    if(res&&res.success===false){alert(parseServerError(res));return;}' +
    '    var d=res&&res.data?res.data:{};' +
    '    alert("Saved\\nFile: "+(d.fileNumber||fileNumber)+"\\nReceipt: "+(d.receiptNo||"")+"\\nFile outstanding now: \\u20B9"+fmt(d.fileOutstanding));' +
    '    kickDeferredCrmRefresh(function(){google.script.host.close();});' +
    '  }).withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(parseServerError(e));})' +
    '  .recordFinanceFileReceiptFromDialog({fileNumber:fileNumber,amount:amount,date:date,narration:document.getElementById("narration").value});' +
    '}' +
    'google.script.run.withSuccessHandler(applyFiles).withFailureHandler(function(e){document.getElementById("status").textContent=e.message||e;}).getPendingFinanceFilesForDialog();'
    ),
    440,
    560
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Record Financer Receipt');
}

function showMarkDeliveredDialog_() {
  var today = nowDate_();
  var seedLeads = getActiveLeadsForPicker_();
  var statusOpts = deliveryChecklistOptionsHtml_();
  dialogWithLeadPicker_('Mark Delivered', '#7B1FA2', 'Mark Delivered',
    '<h3>Mark Delivered</h3>' + leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true }) +
    '<div id="deliveryStatus" style="font-size:12px;color:#666;margin:8px 0;">Pick a lead to load delivery checklist…</div>' +
    '<h4 style="margin:12px 0 6px;font-size:13px">Delivery Checklist</h4>' +
    '<label>Insurance *</label><select id="insurance">' + statusOpts + '</select>' +
    '<label>Insurer Name *</label><input id="insurerName" placeholder="e.g. Bajaj Allianz">' +
    '<label>Registration *</label><select id="registration">' + statusOpts + '</select>' +
    '<label>Invoice *</label><select id="invoice">' + statusOpts + '</select>' +
    '<label>Invoice Number *</label><input id="invoiceNumber" placeholder="Invoice no.">' +
    '<label>Chassis Number *</label><input id="chassisNumber" placeholder="Chassis / frame number">' +
    '<label>Accessories</label><select id="accessories">' + statusOpts + '</select>' +
    '<label>PDI *</label><select id="pdi">' + statusOpts + '</select>' +
    '<label>Delivery Date *</label><input id="date" type="date" value="' + today + '">' +
    '<label>Feedback</label><textarea id="feedback" rows="2"></textarea>',
    deliveryDialogClientJs_(),
    { height: 800, activeOnly: true, seedLeads: seedLeads, stage: 'delivery' }
  );
}

function deliveryDialogClientJs_() {
  return [
    'function setSel(id,v){var x=document.getElementById(id);if(!x)return;var s=String(v||"");for(var i=0;i!==x.options.length;i++){if(x.options[i].value===s){x.selectedIndex=i;return;}}if(s)x.value=s;}',
    'function setVal(id,v){var x=document.getElementById(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function applyDeliveryCtx(res){',
    '  var st=document.getElementById("deliveryStatus");',
    '  if(!res||res.success===false){if(st)st.textContent=(res&&res.message)||"Could not load delivery row";return;}',
    '  var d=res.delivery||{};',
    '  setSel("insurance",d.insurance||"Yes");setVal("insurerName",d.insurerName);',
    '  setSel("registration",d.registration||"Yes");setSel("invoice",d.invoice||"Yes");',
    '  setVal("invoiceNumber",d.invoiceNumber);setVal("chassisNumber",d.chassisNumber||res.chassisNumber||"");',
    '  setSel("accessories",d.accessories||"Pending");',
    '  setSel("pdi",d.pdi||"Yes");',
    '  setVal("feedback",d.feedback);',
    '  if(d.deliveryDate)setVal("date",d.deliveryDate);',
    '  if(st){',
    '    var msg="Customer outstanding: \\u20B9"+Number(res.outstanding||0).toLocaleString("en-IN");',
    '    if(!res.eligible)msg+=" \\u2014 delivery blocked until customer outstanding is zero";',
    '    else if(d.delivered==="Yes")msg+=" \\u2014 previously marked delivered (update checklist below)";',
    '    st.textContent=msg;',
    '  }',
    '}',
    'window.onLeadPicked=function(l){',
    '  if(!l||!l.leadId)return;',
    '  var st=document.getElementById("deliveryStatus");if(st)st.textContent="Loading delivery checklist \\u2026";',
    '  google.script.run.withSuccessHandler(applyDeliveryCtx).withFailureHandler(function(e){',
    '    if(st)st.textContent=e.message||String(e);',
    '  }).getDeliveryContextForDialog(l.leadId);',
    '};',
    'function doSave(){',
    '  if(!validateLeadPick())return;',
    '  var b=document.getElementById("btn");b.disabled=true;b.textContent="Saving...";',
    '  var done=false;function reset(){b.disabled=false;b.textContent="Mark Delivered";}',
    '  var t=setTimeout(function(){if(done)return;done=true;reset();softTimeoutAlert("Delivery update");},45000);',
    '  try{',
    '    var d={leadId:getPickedLeadId(),',
    '      insurance:document.getElementById("insurance").value,',
    '      insurerName:document.getElementById("insurerName").value,',
    '      registration:document.getElementById("registration").value,',
    '      invoice:document.getElementById("invoice").value,',
    '      invoiceNumber:document.getElementById("invoiceNumber").value,',
    '      chassisNumber:document.getElementById("chassisNumber").value,',
    '      accessories:document.getElementById("accessories").value,',
    '      pdi:document.getElementById("pdi").value,',
    '      deliveryDate:document.getElementById("date").value,',
    '      feedback:document.getElementById("feedback").value};',
    '    if(!d.deliveryDate){clearTimeout(t);done=true;reset();alert("Delivery date is required");return;}',
    '    if(String(d.insurance).toLowerCase()!=="yes"&&String(d.insurance).toLowerCase()!=="done"){clearTimeout(t);done=true;reset();alert("Insurance must be Yes");return;}',
    '    if(!String(d.insurerName||"").trim()){clearTimeout(t);done=true;reset();alert("Insurer name is required");return;}',
    '    if(String(d.registration).toLowerCase()!=="yes"&&String(d.registration).toLowerCase()!=="done"){clearTimeout(t);done=true;reset();alert("Registration must be Yes");return;}',
    '    if(String(d.invoice).toLowerCase()!=="yes"&&String(d.invoice).toLowerCase()!=="done"){clearTimeout(t);done=true;reset();alert("Invoice must be Yes");return;}',
    '    if(!String(d.invoiceNumber||"").trim()){clearTimeout(t);done=true;reset();alert("Invoice number is required");return;}',
    '    if(!String(d.chassisNumber||"").trim()){clearTimeout(t);done=true;reset();alert("Chassis number is required");return;}',
    '    if(String(d.pdi).toLowerCase()!=="yes"&&String(d.pdi).toLowerCase()!=="done"){clearTimeout(t);done=true;reset();alert("PDI must be Yes");return;}',
    '    google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(t);reset();',
    '      if(res&&res.success===false){alert(parseServerError(res));return;}',
    '      alert("Marked delivered");kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '    }).withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(parseServerError(e));})',
    '    .markDeliveredFromDialog(d);',
    '  }catch(ex){if(done)return;done=true;clearTimeout(t);reset();alert(ex.message||ex);}',
    '}'
  ].join('');
}

function markDeliveredFromDialog(data) {
  try {
    if (!data.leadId) {
      return crmFailStructured_('Delivery', 'markDeliveredFromDialog', 'validate',
        businessError_('Lead ID is required', 'VALIDATION'), 0);
    }
    requireActiveLead_(data.leadId);
    return markDeliveredFromData_(data);
  } catch (e) {
    return crmFailStructured_('Delivery', 'markDeliveredFromDialog', 'handler', e, 0);
  }
}

function showCloseLeadDialog_() {
  var today = nowDate_();
  var seedLeads = getActiveLeadsForPicker_();
  var statusOpts = deliveryChecklistOptionsHtml_();
  dialogWithLeadPicker_('Close Lead', '#C62828', 'Close Lead Account',
    '<h3>Close Lead (Accounts)</h3>' + leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true, label: 'Select Active Lead *' }) +
    '<div id="closeStatus" style="font-size:12px;color:#666;margin:8px 0;">Pick a lead to load RC &amp; plate details…</div>' +
    '<label>RC *</label><select id="rc">' + statusOpts + '</select>' +
    '<label>Number Plate *</label><input id="numberPlate" placeholder="e.g. RJ14-AB-1234">' +
    '<label>Close Reason *</label><textarea id="reason" rows="2" placeholder="e.g. Fully settled, Customer cancelled"></textarea>' +
    '<label>Final Outstanding (System Calculated — Read Only)</label>' +
    '<input id="finalOutstanding" type="text" disabled="disabled" readonly="readonly" ' +
    'style="background:#F5F5F5;color:#333;cursor:default;border:1px solid #BDBDBD;" ' +
    'placeholder="Loads automatically when you pick a lead">' +
    '<div style="font-size:11px;color:#666;margin:2px 0 8px;">Locked · System Calculated · Customer Payable − Payments Received</div>' +
    '<label>Closing Date *</label><input id="closeDate" type="date" value="' + today + '">' +
    '<label>Remarks</label><textarea id="closeRemarks" rows="2"></textarea>',
    closeLeadDialogClientJs_(),
    { height: 780, activeOnly: true, seedLeads: seedLeads, stage: 'close' }
  );
}

function closeLeadDialogClientJs_() {
  return [
    'function setSel(id,v){var x=document.getElementById(id);if(!x)return;var s=String(v||"");for(var i=0;i<x.options.length;i++){if(x.options[i].value===s){x.selectedIndex=i;return;}}if(s)x.value=s;}',
    'function setVal(id,v){var x=document.getElementById(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function applyCloseCtx(res){',
    '  var st=document.getElementById("closeStatus");',
    '  if(!res||res.success===false){if(st)st.textContent=(res&&res.message)||"Could not load lead details";return;}',
    '  setSel("rc",res.rc||"Pending");setVal("numberPlate",res.numberPlate);',
    '  var os=Number(res.outstanding);',
    '  setVal("finalOutstanding",isFinite(os)?"\\u20B9"+os.toLocaleString("en-IN",{maximumFractionDigits:2}):"Calculating\\u2026");',
    '  if(st)st.textContent="Enter RC status and number plate before closing. Outstanding is system-calculated (read only).";',
    '}',
    'window.onLeadPicked=function(l){',
    '  if(!l||!l.leadId)return;',
    '  var st=document.getElementById("closeStatus");if(st)st.textContent="Loading RC & plate \\u2026";',
    '  google.script.run.withSuccessHandler(applyCloseCtx).withFailureHandler(function(e){',
    '    if(st)st.textContent=e.message||String(e);',
    '  }).getCloseLeadContextForDialog(l.leadId);',
    '};',
    'function doSave(){',
    '  if(!validateLeadPick())return;',
    '  var b=document.getElementById("btn");b.disabled=true;b.textContent="Closing...";',
    '  var done=false;function reset(){b.disabled=false;b.textContent="Close Lead Account";}',
    '  var t=setTimeout(function(){if(done)return;done=true;reset();softTimeoutAlert("Close lead");},45000);',
    '  var d={leadId:getPickedLeadId(),',
    '    rc:document.getElementById("rc").value,',
    '    numberPlate:document.getElementById("numberPlate").value,',
    '    reason:document.getElementById("reason").value,',
    '    closeDate:document.getElementById("closeDate").value,',
    '    remarks:document.getElementById("closeRemarks").value};',
    '  if(String(d.rc).toLowerCase()!=="yes"&&String(d.rc).toLowerCase()!=="done"){clearTimeout(t);done=true;reset();alert("RC must be Yes or Done");return;}',
    '  if(!String(d.numberPlate||"").trim()){clearTimeout(t);done=true;reset();alert("Number plate is required");return;}',
    '  if(!d.reason){clearTimeout(t);done=true;reset();alert("Close reason is required");return;}',
    '  if(!d.closeDate){clearTimeout(t);done=true;reset();alert("Closing date is required");return;}',
    '  google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(t);reset();',
    '    if(res&&res.success===false){alert(res.message||res);return;}',
    '    var id=(res&&res.data&&res.data.leadId)||res;',
    '    alert("Lead closed: "+id);kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '  }).withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(e.message||e);})',
    '  .closeLeadFromDialog(d);',
    '}'
  ].join('');
}

function closeLeadFromDialog(data) {
  try {
    if (!data || !data.leadId) {
      return crmFailStructured_('Lead', 'closeLeadFromDialog', 'validate',
        businessError_('Lead is required', 'VALIDATION'), 0);
    }
    requireActiveLead_(data.leadId);
    return closeLead_(data);
  } catch (e) {
    return crmFailStructured_('Lead', 'closeLeadFromDialog', 'handler', e, 0);
  }
}

function showSearchDialog_() {
  var seedLeads = getActiveLeadsForPicker_({ activeOnly: false });
  var html = createDialogOutput_(
dialogBaseCss_('#455A64') + '<style>' + leadPickerCss_() + '</style>' +
    '<h3>Search Lead</h3>' +
    leadPickerHtml_({ showClosedCheckbox: true, activeOnly: false, label: 'Search Lead' }) +
    '<button class="btn" type="button" onclick="goToLead()">Go to Selected Lead</button>' +
    htmlScript_('window.__LEAD_CACHE_SEEDED=' + jsonForHtml_(seedLeads) + ';') +
    htmlScript_(
      leadPickerClientJs_(false) +
      'function goToLead(){var id=getPickedLeadId();if(!id){alert("Select a lead first");return;}' +
      'google.script.run.withSuccessHandler(function(){google.script.host.close();})' +
      '.withFailureHandler(function(e){alert("Go to lead failed: "+(e.message||e));}).goToLeadFromDialog(id);}'
    ),
    440,
    520
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Search Lead');
}

/**
 * Scheme Update — scheme / discount amounts only (lead summary already shows customer).
 * Amounts are manual number entry; Scheme Master supplies max/hints when matched.
 */
function showUpdateLeadDialog_() {
  showSchemeUpdateDialog_();
}

function showSchemeUpdateDialog_() {
  var seedLeads = getActiveLeadsForPicker_({ activeOnly: true });
  dialogWithLeadPicker_('Scheme Update', '#1565C0', 'Save Scheme',
    '<h3>Scheme Update</h3>' +
    leadPickerHtml_({ showClosedCheckbox: false, activeOnly: true, label: 'Select Lead *' }) +
    '<div id="updateStatus" style="font-size:12px;color:#666;margin:6px 0;">Pick a booked lead to load scheme limits…</div>' +
    '<h4 style="margin-top:14px;font-size:13px">Commercial Offer / Scheme (Eligible)</h4>' +
    '<div id="offerHint" style="font-size:12px;color:#666;margin:2px 0 8px;">Pick amounts (₹) from Scheme Master. Fields with no scheme for this model stay at ₹0.</div>' +
    '<div class="field"><label id="lbl_consumerDiscount">Consumer Discount</label>' +
    '<select class="offer" id="consumerDiscount"><option value="0">₹0</option></select></div>' +
    '<div class="field"><label id="lbl_exchangeBonus">Exchange Bonus</label>' +
    '<select class="offer" id="exchangeBonus"><option value="0">₹0</option></select></div>' +
    '<div class="field"><label id="lbl_loyaltyBonus">Loyalty Bonus</label>' +
    '<select class="offer" id="loyaltyBonus"><option value="0">₹0</option></select></div>' +
    '<div class="field"><label id="lbl_referralBonus">Referral Bonus</label>' +
    '<select class="offer" id="referralBonus"><option value="0">₹0</option></select></div>' +
    '<div class="field"><label id="lbl_dsaDiscount">DSA Bonus</label>' +
    '<select class="offer" id="dsaDiscount"><option value="0">₹0</option></select></div>' +
    '<div class="field"><label id="lbl_additionalDiscount">Additional Discount (enter amount)</label>' +
    '<input class="offer" id="additionalDiscount" type="number" min="0" step="0.01" value="0" placeholder="Type amount ₹" /></div>' +
    '<h4 style="margin-top:16px;font-size:13px;color:#0D47A1">OEM Extra Support (NOT Scheme)</h4>' +
    '<div style="font-size:12px;color:#455A64;background:#E3F2FD;border:1px solid #90CAF9;border-radius:6px;padding:8px;margin:0 0 8px">' +
    '<b>Separate from Scheme Master.</b> Case-wise amount you take from OEM to increase dealer profit. ' +
    'Does <b>not</b> use Exchange / Loyalty / Referral / DSA / Consumer. Type only if OEM gave extra support for this booking.' +
    '</div>' +
    '<div class="field"><label id="lbl_oemExtraSupportReceived">OEM Extra Support Received (₹)</label>' +
    '<input id="oemExtraSupportReceived" type="number" min="0" step="0.01" value="0" placeholder="Type amount ₹ (0 if none)" /></div>' +
    '<div class="field"><label id="lbl_oemExtraSupportPassed">OEM Extra Support Passed To Customer (₹)</label>' +
    '<input id="oemExtraSupportPassed" type="number" min="0" step="0.01" value="0" placeholder="Usually 0 — type if passed to customer" /></div>' +
    '<label>OEM Extra Support Retained (dealer profit)</label><input id="oemExtraSupportRetained" disabled="disabled" />' +
    '<label>Eligible Scheme Total</label><input id="totalDiscount" disabled="disabled" />' +
    '<label>OEM Scheme Eligible</label><input id="oemEligible" disabled="disabled" />' +
    '<h4 style="margin-top:14px;font-size:13px">Owner Decision — Customer Benefit</h4>' +
    '<p style="font-size:12px;color:#555;margin:0 0 8px">Customer Payable reduces only by Benefit Passed. OEM Eligible stays available for owner receivable.</p>' +
    '<div class="field" style="margin:6px 0">' +
    '<label style="display:block"><input type="radio" name="benefitMode" value="Full Benefit" checked="checked" /> Full Benefit</label>' +
    '<label style="display:block"><input type="radio" name="benefitMode" value="Partial Benefit" /> Partial Benefit</label>' +
    '<label style="display:block"><input type="radio" name="benefitMode" value="No Benefit" /> No Benefit</label>' +
    '</div>' +
    '<div id="partialWrap" style="display:none">' +
    '<div style="font-size:12px;color:#455A64;margin:4px 0 2px">Enter how much of each scheme is passed. Company share is applied first. Dealer Benefit Retained = company share you did <b>not</b> pass, minus any dealer share you did pass (your unspent dealer share is not income).</div>' +
    '<div id="partialComponents"></div>' +
    '<input id="benefitPassed" type="hidden" />' +
    '</div>' +
    '<label>Customer Benefit Passed</label><input id="benefitPassedShow" disabled="disabled" />' +
    '<label>Dealer Benefit Retained</label><input id="dealerRetained" disabled="disabled" />' +
    '<label>Customer Payable</label><input id="customerPayable" disabled="disabled" style="background:#F5F5F5;cursor:default;" />' +
    '<label>Booking Advance (already received)</label><input id="bookingAdvanceShow" disabled="disabled" style="background:#ECEFF1;cursor:default;" />' +
    '<label>Other Payments Received</label><input id="paymentsReceivedShow" disabled="disabled" style="background:#ECEFF1;cursor:default;" />' +
    '<label>Outstanding (Payable − Advance − Payments)</label>' +
    '<input id="outstanding" disabled="disabled" readonly="readonly" style="background:#ECEFF1;color:#455A64;cursor:default;border:1px solid #BDBDBD;" />'
    ,
    schemeUpdateDialogClientJs_(),
    { height: 780, width: 480, activeOnly: true, seedLeads: seedLeads }
  );
}

/** Scheme-only client JS — eligible offers + Owner Decision (Benefit Passed). */
function schemeUpdateDialogClientJs_() {
  return [
    'var UPDATE_CTX={hasBooking:false,payableBase:0,paid:0,bookingAmount:0,pendingOffers:null,model:"",variant:"",oemEligible:0,benefitMode:"Full Benefit",benefitPassed:0};',
    'var SCHEME_RULES={rules:{}};',
    'var OFFER_IDS=["consumerDiscount","exchangeBonus","loyaltyBonus","referralBonus","dsaDiscount","additionalDiscount"];',
    'var OEM_OFFER_IDS=["consumerDiscount","exchangeBonus","loyaltyBonus","referralBonus","dsaDiscount"];',
    'var OFFER_LABELS={consumerDiscount:"Consumer Discount",exchangeBonus:"Exchange Bonus",loyaltyBonus:"Loyalty Bonus",referralBonus:"Referral Bonus",dsaDiscount:"DSA Bonus",additionalDiscount:"Additional Discount"};',
    'function el(id){return document.getElementById(id);}',
    'function num(v){var n=Number(v);return isFinite(n)?n:0;}',
    'function setVal(id,v){var x=el(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function fmtInr(n){try{return Number(n||0).toLocaleString("en-IN");}catch(e){return String(n||0);}}',
    'function getBenefitMode(){var radios=document.getElementsByName("benefitMode");for(var i=0;i<radios.length;i++){if(radios[i].checked)return radios[i].value;}return "Full Benefit";}',
    'function setBenefitMode(mode){mode=mode||"Full Benefit";var radios=document.getElementsByName("benefitMode");for(var i=0;i<radios.length;i++){radios[i].checked=(radios[i].value===mode);}var wrap=el("partialWrap");if(wrap)wrap.style.display=(mode==="Partial Benefit")?"":"none";}',
    'function eligibleTotal(){var total=0;for(var i=0;i<OFFER_IDS.length;i++){var x=el(OFFER_IDS[i]);if(x&&!x.disabled)total+=num(x.value);}return total;}',
    'function oemEligibleClient(){',
    // Always from current dropdowns — stale server oemEligible was treating part of
    // OEM schemes as "dealer pool" and always-passing them (wrong payable).
    '  var t=0;for(var i=0;i<OEM_OFFER_IDS.length;i++){var x=el(OEM_OFFER_IDS[i]);if(x&&!x.disabled)t+=num(x.value);}return t;',
    '}',
    'function calcOutstandingClient(payable){',
    // Mirror calcOutstanding_: if ledger paid is 0, subtract booking advance;
    // if ledger already includes booking payment, subtract paid only (no double).
    '  var paid=num(UPDATE_CTX.paid);var booking=num(UPDATE_CTX.bookingAmount);',
    '  if(paid>0.009)return Math.max(0,payable-paid);',
    '  return Math.max(0,payable-booking);',
    '}',
    'function renderPartialComponents(){',
    '  var box=el("partialComponents");if(!box)return;',
    '  var html="";',
    '  for(var i=0;i<OEM_OFFER_IDS.length;i++){var id=OEM_OFFER_IDS[i];var x=el(id);var amt=x&&!x.disabled?num(x.value):0;',
    '    if(amt>0){var pid="pass_"+id;var cur=el(pid)?num(el(pid).value):amt;if(cur>amt)cur=amt;',
    '      html+="<div style=\'margin:6px 0\'><label style=\'display:block;font-size:12px;color:#455A64\'>"+(OFFER_LABELS[id]||id)+" — eligible \u20B9"+fmtInr(amt)+"</label>"+',
    '        "<input type=\'number\' class=\'passAmt\' id=\'"+pid+"\' data-comp=\'"+id+"\' min=\'0\' max=\'"+amt+"\' step=\'0.01\' value=\'"+cur+"\' style=\'width:100%\' /></div>";}',
    '  }',
    '  if(!html)html="<div style=\'font-size:12px;color:#999\'>No scheme amounts selected above.</div>";',
    '  box.innerHTML=html;',
    '}',
    'function passedBreakup(){',
    // per-component ₹ passed, keyed by offer id — the recorded WHICH, not just the amount
    '  var mode=getBenefitMode();var bk={};',
    '  for(var i=0;i<OEM_OFFER_IDS.length;i++){var id=OEM_OFFER_IDS[i];var x=el(id);var amt=x&&!x.disabled?num(x.value):0;if(amt<=0){bk[id]=0;continue;}',
    '    if(mode==="Full Benefit")bk[id]=amt;',
    '    else if(mode==="No Benefit")bk[id]=0;',
    '    else{var pi=el("pass_"+id);var v=pi?num(pi.value):0;if(v<0)v=0;if(v>amt)v=amt;bk[id]=v;}',
    '  }',
    '  return bk;',
    '}',
    'function resolvePassed(eligible){',
    '  var bk=passedBreakup();var t=0;for(var k in bk)t+=num(bk[k]);',
    '  return Math.max(0,Math.min(t,eligible));',
    '}',
    'function retainedIncomeClient(){',
    // earn = companyUnpassed − dealerPassed (company-first). Dealer unpassed ≠ income.
    '  var bk=passedBreakup();var t=0;',
    '  for(var i=0;i<OEM_OFFER_IDS.length;i++){var id=OEM_OFFER_IDS[i];var x=el(id);var amt=x&&!x.disabled?num(x.value):0;if(amt<=0)continue;',
    '    var passed=num(bk[id]);if(passed<0)passed=0;if(passed>amt)passed=amt;',
    '    var rule=SCHEME_RULES.rules&&SCHEME_RULES.rules[id];',
    '    var cs=rule?num(rule.companyShare):0;var ds=rule?num(rule.dealerShare):0;',
    '    if(cs>0||ds>0){',
    '      var cFull=Math.min(cs,amt);',
    '      var cPass=Math.min(cs,passed);',
    '      var dPass=Math.min(ds,Math.max(0,passed-cPass));',
    '      t+=(cFull-cPass)-dPass;',
    '    }else{t+=Math.max(0,amt-passed);}',
    '  }',
    '  return t;',
    '}',
    'function calcOffer(){',
    // Two-pool model (mirrors server): mode applies to OEM pool only; dealer-funded
    // discounts always pass; Retained = oemPool − passedOem, never negative.
    '  var all=eligibleTotal();',
    '  var oem=oemEligibleClient();',
    '  var dealerPool=Math.max(0,all-oem);',
    '  var passedOem=resolvePassed(oem);',
    '  var extraRecv=Math.max(0,num(el("oemExtraSupportReceived")&&el("oemExtraSupportReceived").value));',
    '  var extraPass=Math.max(0,Math.min(num(el("oemExtraSupportPassed")&&el("oemExtraSupportPassed").value),extraRecv));',
    '  if(el("oemExtraSupportPassed")&&num(el("oemExtraSupportPassed").value)!==extraPass)setVal("oemExtraSupportPassed",extraPass);',
    '  var extraRet=Math.max(0,extraRecv-extraPass);',
    '  var totalPass=passedOem+dealerPool+extraPass;',
    '  setVal("totalDiscount",all.toFixed(2));',
    '  setVal("oemEligible",oem.toFixed(2));',
    '  setVal("benefitPassedShow",passedOem.toFixed(2));',
    '  setVal("dealerRetained",Number(retainedIncomeClient()).toFixed(2));',
    '  setVal("oemExtraSupportRetained",extraRet.toFixed(2));',
    '  if(UPDATE_CTX.hasBooking){',
    '    var payable=Math.max(0,num(UPDATE_CTX.payableBase)-totalPass);',
    '    setVal("customerPayable",payable.toFixed(2));',
    '    setVal("bookingAdvanceShow",num(UPDATE_CTX.bookingAmount).toFixed(2));',
    '    setVal("paymentsReceivedShow",num(UPDATE_CTX.paid).toFixed(2));',
    '    setVal("outstanding",calcOutstandingClient(payable).toFixed(2));',
    '  }',
    '}',
    'function fillChoices(id,rule,current){',
    '  var sel=el(id);if(!sel)return 0;',
    '  var list=(rule&&rule.choices&&rule.choices.length)?rule.choices.slice():[0];',
    '  var out=[];var seen={};',
    '  for(var i=0;i<list.length;i++){var n=num(list[i]);if(n>=0&&!seen[n]){seen[n]=1;out.push(n);}}',
    '  var cur=num(current);',
    '  if(cur>0&&!seen[cur]){seen[cur]=1;out.push(cur);}',
    '  if(!out.length)out=[0];',
    '  out.sort(function(a,b){return a-b;});',
    '  while(sel.options.length)sel.remove(0);',
    '  for(var j=0;j<out.length;j++){',
    '    var o=document.createElement("option");',
    '    o.value=String(out[j]);',
    '    o.text=(out[j]===0)?"Rs 0":("Rs "+fmtInr(out[j]));',
    '    sel.add(o);',
    '  }',
    '  sel.value=String(seen[cur]?cur:0);',
    '  return out.length;',
    '}',
    'function countKeys(o){var n=0;for(var k in o){if(Object.prototype.hasOwnProperty.call(o,k))n++;}return n;}',
    'function applySchemeRules(rulesObj){',
    '  SCHEME_RULES=rulesObj||{rules:{}};',
    '  var rules=SCHEME_RULES.rules||{};',
    '  var pending=UPDATE_CTX.pendingOffers||{};',
    '  var open=0;var parts=[];',
    '  for(var i=0;i<OFFER_IDS.length;i++){',
    '    var id=OFFER_IDS[i];',
    '    var rule=rules[id]||{};',
    '    var sel=el(id);',
    '    var lbl=el("lbl_"+id);',
    '    var base=OFFER_LABELS[id]||id;',
    '    var max=num(rule.maxAmount);',
    '    var allowed=(id==="additionalDiscount")?true:!!rule.allowed;',
    '    if(id==="additionalDiscount"){',
    '      var addMax=max||50000;',
    '      var curAdd=num(pending[id]);if(curAdd<0)curAdd=0;if(curAdd>addMax)curAdd=addMax;',
    '      if(sel){sel.disabled=false;sel.min="0";sel.max=String(addMax);sel.step="0.01";sel.value=String(curAdd);',
    '        sel.style.background="";sel.title=rule.hint||("Type any amount up to Rs "+fmtInr(addMax));}',
    '      if(lbl)lbl.textContent=base+" (enter amount, max Rs "+fmtInr(addMax)+")";',
    '      open++;parts.push(base+": type up to "+fmtInr(addMax));',
    '      continue;',
    '    }',
    '    var nOpts=fillChoices(id,rule,pending[id]);',
    '    if(sel){',
    '      sel.disabled=false;',
    '      sel.style.background=(allowed&&nOpts>1)?"":"#f5f5f5";',
    '      sel.title=rule.hint||(allowed?"Pick an amount from Scheme Master":"Not in Scheme Master for this model — stays Rs 0");',
    '    }',
    '    if(lbl){',
    '      if(allowed&&max>0){lbl.textContent=base+" (max Rs "+fmtInr(max)+")";open++;parts.push(base+": max "+fmtInr(max));}',
    '      else if(!allowed){lbl.textContent=base+" (N/A — Rs 0)";}',
    '      else{lbl.textContent=base;}',
    '    }',
    '  }',
    '  var hint=el("offerHint");',
    '  if(hint){',
    '    var fam=SCHEME_RULES.modelFamily||SCHEME_RULES.model||UPDATE_CTX.model||"";',
    '    var mon=SCHEME_RULES.schemeMonth||"";',
    '    if(open){',
    '      hint.textContent="Scheme matched: "+fam+(mon?" · "+mon:"")+". Scheme fields = lists; Additional Discount = type any amount. "+parts.slice(0,4).join(" | ");',
    '      hint.style.color="#2e7d32";',
    '    }else{',
    '      hint.textContent="No Scheme Master row for "+(fam||"this model")+(mon?" in "+mon:"")+" — scheme fields stay Rs 0. Additional Discount: type any amount.";',
    '      hint.style.color="#c62828";',
    '    }',
    '  }',
    '  calcOffer();',
    '}',
    'function loadSchemeForLead(leadId,model,variant){',
    '  leadId=String(leadId||"");',
    '  model=String(model||UPDATE_CTX.model||"");',
    '  variant=String(variant||UPDATE_CTX.variant||"");',
    '  var st=el("updateStatus");',
    '  function onRules(r){',
    '    if(!r){if(st)st.textContent="Scheme rules empty — manual entry enabled.";applySchemeRules({rules:{}});return;}',
    '    applySchemeRules(r);',
    '    if(st&&UPDATE_CTX.hasBooking)st.textContent="Lead: "+leadId+" | "+(UPDATE_CTX.model||model)+" / "+(UPDATE_CTX.variant||variant)+" | Booked";',
    '  }',
    '  function onFail(e){',
    '    if(st)st.textContent="Scheme load failed — manual entry enabled. "+(e&&e.message?e.message:"");',
    '    if(model){',
    '      google.script.run.withSuccessHandler(onRules).withFailureHandler(function(){applySchemeRules({rules:{}});})',
    '        .getSchemeRulesForDialog(model,variant,"");',
    '    }else{applySchemeRules({rules:{}});}',
    '  }',
    '  if(leadId){',
    '    google.script.run.withSuccessHandler(onRules).withFailureHandler(onFail).getSchemeRulesForLeadDialog(leadId);',
    '  }else if(model){',
    '    google.script.run.withSuccessHandler(onRules).withFailureHandler(onFail).getSchemeRulesForDialog(model,variant,"");',
    '  }',
    '}',
    'function applyUpdateCtx(res){',
    '  var st=el("updateStatus");',
    '  try{',
    '    if(!res||res.success===false){if(st)st.textContent=(res&&res.message)||"Failed to load lead";return;}',
    // Do NOT early-return when hasBooking looks false. Booking detection has proven
    // fragile (status text edits, snapshot lookup timing), and bailing out here left
    // Customer Payable / Outstanding blank and blocked a save the SERVER would have
    // accepted. Populate everything we can; the server re-validates on save and
    // returns a precise error if the lead genuinely is not booked.
    '    var l=res.lead||{};var o=res.offer||{};',
    '    UPDATE_CTX.hasBooking=(res.hasBooking!==false)||!!num(res.payableBeforeOffer)||String(l.currentStatus||"").toLowerCase()==="booked"||String(l.currentStatus||"").toLowerCase()==="delivered"||num(l.bookingAmount)>0;',
    '    UPDATE_CTX.payableBase=num(res.payableBeforeOffer);',
    '    UPDATE_CTX.paid=num(res.paymentsReceived);',
    '    UPDATE_CTX.bookingAmount=num(l.bookingAmount||res.bookingAmount);',
    '    UPDATE_CTX.oemEligible=num(res.oemEligible);',
    '    UPDATE_CTX.model=l.interestedModel||l.model||UPDATE_CTX.model||"";',
    '    UPDATE_CTX.variant=l.variant||UPDATE_CTX.variant||"";',
    '    UPDATE_CTX.pendingOffers={consumerDiscount:o.consumerDiscount||0,exchangeBonus:o.exchangeBonus||0,loyaltyBonus:o.loyaltyBonus||0,referralBonus:o.referralBonus||0,dsaDiscount:o.dsaDiscount||0,additionalDiscount:o.additionalDiscount||0,oemExtraSupportReceived:o.oemExtraSupportReceived||0,oemExtraSupportPassed:o.oemExtraSupportPassed||0,oemExtraSupportRetained:o.oemExtraSupportRetained||0};',
    '    if(el("oemExtraSupportReceived"))setVal("oemExtraSupportReceived",num(o.oemExtraSupportReceived||res.oemExtraSupportReceived||0));',
    '    if(el("oemExtraSupportPassed"))setVal("oemExtraSupportPassed",num(o.oemExtraSupportPassed||res.oemExtraSupportPassed||0));',
    '    if(el("oemExtraSupportRetained"))setVal("oemExtraSupportRetained",num(res.oemExtraSupportRetained||0).toFixed(2));',
    '    setBenefitMode(res.benefitMode||"Full Benefit");',
    '    renderPartialComponents();',
    '    if(el("benefitPassed"))setVal("benefitPassed",res.customerBenefitPassed!=null?res.customerBenefitPassed:0);',
    '    if(st)st.textContent="Lead: "+(l.leadId||"")+" | "+(UPDATE_CTX.model||"")+" / "+(UPDATE_CTX.variant||"")+" | Booked";',
    '    if(res.schemeRules&&res.schemeRules.rules&&countKeys(res.schemeRules.rules))applySchemeRules(res.schemeRules);',
    // RACE FIX: the scheme-rules call and this lead-context call are independent and
    // either can land first. If rules already arrived, they were rendered with
    // pendingOffers=null and every dropdown fell back to Rs 0 — which then computed
    // Customer Payable as if NO scheme were applied (payable-before-offer), and it
    // disagreed with the lead\'s real Outstanding. Re-apply the rules we already have
    // now that the saved offers are known.
    '    else if(SCHEME_RULES&&SCHEME_RULES.rules&&countKeys(SCHEME_RULES.rules))applySchemeRules(SCHEME_RULES);',
    '    else loadSchemeForLead(l.leadId,UPDATE_CTX.model,UPDATE_CTX.variant);',
    '    calcOffer();',
    '  }catch(err){if(st)st.textContent="Form error: "+(err.message||err);}',
    '}',
    'window.onLeadPicked=function(l){',
    '  if(!l||!l.leadId)return;',
    '  var st=el("updateStatus");',
    '  if(st)st.textContent="Loading scheme limits…";',
    '  UPDATE_CTX.model=l.model||"";',
    '  UPDATE_CTX.variant=l.variant||"";',
    '  UPDATE_CTX.hasBooking=false;',
    '  UPDATE_CTX.pendingOffers=null;',
    '  loadSchemeForLead(l.leadId,l.model,l.variant);',
    '  google.script.run.withSuccessHandler(applyUpdateCtx).withFailureHandler(function(e){',
    '    if(st)st.textContent="Could not load lead: "+(e&&e.message?e.message:e);',
    '    loadSchemeForLead(l.leadId,l.model,l.variant);',
    '  }).getUpdateLeadContext(l.leadId);',
    '};',
    'function validateOffersClient(){',
    '  var rules=(SCHEME_RULES&&SCHEME_RULES.rules)||{};',
    '  var hasMaster=(SCHEME_RULES.matchedComponents||[]).length>0;',
    '  var lines=[];',
    '  for(var i=0;i<OFFER_IDS.length;i++){',
    '    var id=OFFER_IDS[i];var inp=el(id);if(!inp)continue;',
    '    var amt=num(inp.value);var rule=rules[id]||{};',
    '    if(amt<0)lines.push("- "+(OFFER_LABELS[id]||id)+": cannot be negative");',
    '    if(id==="additionalDiscount"){',
    '      var addMax=num(rule.maxAmount)||50000;',
    '      if(amt>addMax)lines.push("- Additional Discount: max Rs "+fmtInr(addMax));',
    '      continue;',
    '    }',
    '    if(amt<=0)continue;',
    '    if(!hasMaster)continue;',
    '    if(!rule.allowed||!(num(rule.maxAmount)>0))lines.push("- "+(OFFER_LABELS[id]||id)+": not in Scheme Master — enter 0");',
    '    else if(amt>num(rule.maxAmount))lines.push("- "+(OFFER_LABELS[id]||id)+": max Rs "+fmtInr(rule.maxAmount));',
    '  }',
    '  var mode=getBenefitMode();var eligible=eligibleTotal();',
    // Partial mode uses per-component checkboxes; sum is always within eligible.
    '  if(lines.length){alert("Please fix these scheme fields:\\n"+lines.join("\\n"));return false;}',
    '  return true;',
    '}',
    'function doSave(){',
    '  if(!validateLeadPick())return;',
    '  if(!UPDATE_CTX.hasBooking&&!num(UPDATE_CTX.payableBase)){if(!confirm("This lead does not look booked. Save scheme anyway?"))return;}',
    '  if(!validateOffersClient())return;',
    '  var b=el("btn");b.disabled=true;b.textContent="Saving...";',
    '  var done=false;function reset(){b.disabled=false;b.textContent="Save Scheme";}',
    '  var t=setTimeout(function(){if(done)return;done=true;reset();if(typeof softTimeoutAlert==="function")softTimeoutAlert("Scheme update");else alert("Scheme update timed out. Check sheet before retrying.");},45000);',
    '  try{',
    '    var mode=getBenefitMode();var eligible=eligibleTotal();var passed=resolvePassed(eligible);',
    '    var d={leadId:getPickedLeadId(),editCustomer:false,',
    '      consumerDiscount:(el("consumerDiscount")?el("consumerDiscount").value:"0"),',
    '      exchangeBonus:(el("exchangeBonus")?el("exchangeBonus").value:"0"),',
    '      loyaltyBonus:(el("loyaltyBonus")?el("loyaltyBonus").value:"0"),',
    '      referralBonus:(el("referralBonus")?el("referralBonus").value:"0"),',
    '      dsaDiscount:(el("dsaDiscount")?el("dsaDiscount").value:"0"),',
    '      additionalDiscount:(el("additionalDiscount")?el("additionalDiscount").value:"0"),',
    '      oemExtraSupportReceived:(el("oemExtraSupportReceived")?el("oemExtraSupportReceived").value:"0"),',
    '      oemExtraSupportPassed:(el("oemExtraSupportPassed")?el("oemExtraSupportPassed").value:"0"),',
    '      benefitMode:mode,customerBenefitPassed:passed,benefitPassedBreakup:JSON.stringify(passedBreakup())};',
    '    google.script.run.withSuccessHandler(function(res){if(done)return;done=true;clearTimeout(t);reset();',
    '      if(res&&res.success===false){alert(typeof parseServerError==="function"?parseServerError(res):(res.message||"Failed"));return;}',
    '      alert((res&&res.message)||"Scheme updated");',
    '      if(typeof kickDeferredCrmRefresh==="function"){kickDeferredCrmRefresh(function(){google.script.host.close();});}',
    '      else{google.script.host.close();}',
    '    }).withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);reset();alert(typeof parseServerError==="function"?parseServerError(e):(e.message||e));})',
    '    .updateLeadFromDialog(d);',
    '  }catch(ex){if(done)return;done=true;clearTimeout(t);reset();alert(ex.message||ex);}',
    '}',
    'document.addEventListener("input",function(e){if(e.target&&((e.target.className&&String(e.target.className).indexOf("offer")>=0)||e.target.id==="benefitPassed"||e.target.id==="oemExtraSupportReceived"||e.target.id==="oemExtraSupportPassed")){renderPartialComponents();calcOffer();}});',
    'document.addEventListener("input",function(e){if(e.target&&e.target.className&&String(e.target.className).indexOf("passAmt")>=0){if(num(e.target.value)>num(e.target.max))e.target.value=e.target.max;calcOffer();}});',
    'document.addEventListener("change",function(e){',
    '  if(e.target&&e.target.name==="benefitMode"){setBenefitMode(e.target.value);renderPartialComponents();calcOffer();}',
    '  if(e.target&&((e.target.className&&String(e.target.className).indexOf("offer")>=0)||e.target.id==="oemExtraSupportReceived"||e.target.id==="oemExtraSupportPassed"))calcOffer();',
    '});'
  ].join('\n');
}


function updateLeadFromDialog(data) {
  try {
    if (!data || !data.leadId) {
      return crmFailStructured_('Lead', 'updateLeadFromDialog', 'validate',
        businessError_('Lead is required', 'VALIDATION'), 0);
    }
    requireActiveLead_(data.leadId);
    data = normalizeOemExtraSupportPayload_(data);
    return updateLeadFromDialog_(data);
  } catch (e) {
    return crmFailStructured_('Lead', 'updateLeadFromDialog', 'handler', e, 0);
  }
}

/**
 * Accept OEM Extra Support from portal / dialog under any common alias.
 * Guarantees oemExtraSupportReceived / Passed are set before scheme save.
 */
function normalizeOemExtraSupportPayload_(data) {
  data = data || {};
  // Some portal clients wrap payload under data/body/payload.
  var wrapped = data.data || data.payload || data.body || null;
  if (wrapped && typeof wrapped === 'object') {
    var merged = {};
    Object.keys(data).forEach(function (k) { merged[k] = data[k]; });
    Object.keys(wrapped).forEach(function (k) { merged[k] = wrapped[k]; });
    data = merged;
  }
  function parseLooseNum(v) {
    if (v === undefined || v === null || v === '') return null;
    if (typeof parseNumber_ === 'function') return parseNumber_(v);
    var s = String(v).replace(/[^0-9.\-]/g, '');
    if (!s) return null;
    var n = Number(s);
    return isFinite(n) ? n : null;
  }
  function firstNum(keys) {
    for (var i = 0; i < keys.length; i++) {
      var v = data[keys[i]];
      if (v !== undefined && v !== null && String(v).trim() !== '') {
        var n = parseLooseNum(v);
        if (n != null && isFinite(n)) return n;
      }
    }
    return null;
  }
  var recv = firstNum([
    'oemExtraSupportReceived', 'oemExtraSupport', 'oem_extra_support_received',
    'OEM Extra Support Received', 'OEM Extra Support', 'extraSupportReceived',
    'extraSupport', 'oemExtra'
  ]);
  var pass = firstNum([
    'oemExtraSupportPassed', 'oem_extra_support_passed',
    'OEM Extra Support Passed To Customer', 'extraSupportPassed'
  ]);
  var ret = firstNum([
    'oemExtraSupportRetained', 'oem_extra_support_retained',
    'OEM Extra Support Retained', 'extraSupportRetained'
  ]);
  if (recv != null) data.oemExtraSupportReceived = Math.max(0, recv);
  else if (data.oemExtraSupportReceived == null) data.oemExtraSupportReceived = 0;
  if (pass != null) data.oemExtraSupportPassed = Math.max(0, pass);
  else if (data.oemExtraSupportPassed == null) data.oemExtraSupportPassed = 0;
  if (ret != null) data.oemExtraSupportRetained = Math.max(0, ret);
  var recvNum = parseLooseNum(data.oemExtraSupportReceived);
  var passNum = parseLooseNum(data.oemExtraSupportPassed);
  recvNum = Math.max(0, recvNum == null ? 0 : recvNum);
  passNum = Math.max(0, Math.min(passNum == null ? 0 : passNum, recvNum));
  data.oemExtraSupportReceived = recvNum;
  data.oemExtraSupportPassed = passNum;
  data.oemExtraSupportRetained = Math.max(0, recvNum - passNum);
  return data;
}

function getUpdateLeadContext(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead ID is required', errorCode: 'VALIDATION' };
    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) return { success: false, message: 'Lead not found: ' + leadId, errorCode: 'NOT_FOUND' };

    // Prefer light paths so Scheme Update form fills even when full store load is slow.
    var full = null;
    var paid = 0;
    try {
      if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
        full = getLatestCommercialSnapshotForLead_(leadId);
      }
    } catch (e1) {}
    try {
      paid = Number(sumPaymentsForLeadLight_(leadId) || 0);
    } catch (e2) {
      try {
        paid = Number((loadCrmStore_(true).paymentsByLead || {})[leadId] || 0);
      } catch (e3) { paid = 0; }
    }
    if (!full) {
      try {
        var store = loadCrmStore_(true);
        var snap = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
        full = snap ? (snap.full || snap) : null;
        if (!paid) paid = Number(store.paymentsByLead[leadId] || 0);
      } catch (e4) {}
    }

    var hasBooking = !!full || isLeadAlreadyBooked_(lead);
    var offer = {
      consumerDiscount: full ? Number(full.consumerDiscount || 0) : 0,
      exchangeBonus: full ? Number(full.exchangeBonus || 0) : 0,
      loyaltyBonus: full ? Number(full.loyaltyBonus || 0) : 0,
      referralBonus: full ? Number(full.referralBonus || 0) : 0,
      dsaDiscount: full ? Number(full.dsaDiscount || 0) : 0,
      additionalDiscount: full ? Number(full.additionalDiscount || 0) : 0,
      oemExtraSupportReceived: full ? Number(full.oemExtraSupportReceived || 0) : 0,
      oemExtraSupportPassed: full ? Number(full.oemExtraSupportPassed || 0) : 0,
      oemExtraSupportRetained: full ? Number(full.oemExtraSupportRetained || 0) : 0
    };
    // Show exactly what is stored — do not auto-clear typed Extra Support.
    var payableBeforeOffer = 0;

    // AUTHORITATIVE PATH: the Lead Register already holds this deal's real
    // Customer Payable (it is what the operator sees and what Outstanding is
    // derived from). "Payable before offer" is simply that value with the
    // currently-applied benefits added back. Deriving it this way makes the Scheme
    // dialog agree with the Lead Register BY CONSTRUCTION.
    //
    // Previously this recomputed from the commercial snapshot and, when the
    // snapshot's price fields came back empty, a Price-Master fallback refilled
    // them with DEFAULTS — producing 770000+22000+15000 = 807,000 instead of the
    // real 770000+19000+5500 = 794,500 (a ₹12,500 phantom difference).
    var leadPayable = Number(lead.customerPayable || 0);
    var appliedPassed = 0;
    if (full) {
      try {
        appliedPassed = Number(resolveCustomerBenefitPassed_(full) || 0) +
          Number(full.additionalDiscount || 0) +
          Number(full.oemExtraSupportPassed || 0);
      } catch (ap) { appliedPassed = 0; }
    }
    if (leadPayable > 0) {
      payableBeforeOffer = round2_(leadPayable + appliedPassed);
    }

    if (!(payableBeforeOffer > 0) && full && typeof computeCommercialTotals_ === 'function') {
      var baseSnap = {};
      Object.keys(full).forEach(function (k) { baseSnap[k] = full[k]; });
      baseSnap.consumerDiscount = 0;
      baseSnap.exchangeBonus = 0;
      baseSnap.loyaltyBonus = 0;
      baseSnap.referralBonus = 0;
      baseSnap.dsaDiscount = 0;
      baseSnap.additionalDiscount = 0;
      // Only re-price from Price Master when the snapshot has NO usable price data
      // at all — and never let it override a value the snapshot actually holds.
      var snapHasPrice = Number(baseSnap.exShowroom) > 0 || Number(baseSnap.insurance) > 0 ||
        Number(baseSnap.registrationRto) > 0;
      if (!snapHasPrice && typeof getActivePrice_ === 'function') {
        try {
          var pmFix = getActivePrice_(baseSnap.model || lead.interestedModel || '',
            baseSnap.variant || lead.variant || '', baseSnap.bookingDate || nowDate_());
          if (pmFix && Number(pmFix.exShowroom) > 0) {
            // Ex-showroom only. Charges (insurance / RTO / TRC …) are deal-specific
            // and editable per booking — pulling Price Master defaults for those is
            // what created the phantom ₹12,500.
            baseSnap.exShowroom = pmFix.exShowroom;
            if (baseSnap.tcsApplicable === undefined) baseSnap.tcsApplicable = pmFix.tcsApplicable;
          }
        } catch (pmErr) { Logger.log('scheme payable re-price: ' + pmErr.message); }
      }
      payableBeforeOffer = computeCommercialTotals_(baseSnap).customerPayable;
      if (!(payableBeforeOffer > 0)) {
        payableBeforeOffer = Number(lead.customerPayable || lead.outstandingAmount || 0) || 0;
      }
    } else {
      payableBeforeOffer = Number(lead.customerPayable || lead.outstandingAmount || 0) || 0;
    }
    var currentOfferTotal = offer.consumerDiscount + offer.exchangeBonus + offer.loyaltyBonus +
      offer.referralBonus + offer.dsaDiscount + offer.additionalDiscount;
    var benefitMode = full
      ? (typeof normalizeBenefitMode_ === 'function'
        ? normalizeBenefitMode_(full.benefitMode)
        : (full.benefitMode || 'Full Benefit'))
      : 'Full Benefit';
    var customerBenefitPassed = full && typeof resolveCustomerBenefitPassed_ === 'function'
      ? resolveCustomerBenefitPassed_(full)
      : currentOfferTotal;
    var oemEligible = 0;
    if (full && typeof getOemEligibleAmount_ === 'function') {
      oemEligible = getOemEligibleAmount_(full);
    } else {
      oemEligible = offer.consumerDiscount + offer.exchangeBonus + offer.loyaltyBonus +
        offer.referralBonus + offer.dsaDiscount;
    }
    var previewSnap = {};
    if (full) {
      Object.keys(full).forEach(function (k) { previewSnap[k] = full[k]; });
    }
    previewSnap.benefitMode = benefitMode;
    previewSnap.customerBenefitPassed = customerBenefitPassed;
    previewSnap.oemExtraSupportReceived = Number(offer.oemExtraSupportReceived || 0);
    previewSnap.oemExtraSupportPassed = Math.max(0, Math.min(
      Number(offer.oemExtraSupportPassed || 0),
      Number(offer.oemExtraSupportReceived || 0)
    ));
    previewSnap.oemExtraSupportRetained = round2_(
      Math.max(0, previewSnap.oemExtraSupportReceived - previewSnap.oemExtraSupportPassed)
    );
    var dealerMargin = (typeof computeDealerMarginBreakdown_ === 'function')
      ? computeDealerMarginBreakdown_(previewSnap)
      : { marginGrossInclGst: 0, marginGst: 0, marginNetExGst: 0 };
    var payableNow = payableBeforeOffer;
    if (typeof computeCommercialTotals_ === 'function') {
      var withOffers = {};
      Object.keys(previewSnap).forEach(function (k) { withOffers[k] = previewSnap[k]; });
      withOffers.consumerDiscount = offer.consumerDiscount;
      withOffers.exchangeBonus = offer.exchangeBonus;
      withOffers.loyaltyBonus = offer.loyaltyBonus;
      withOffers.referralBonus = offer.referralBonus;
      withOffers.dsaDiscount = offer.dsaDiscount;
      withOffers.additionalDiscount = offer.additionalDiscount;
      withOffers.benefitMode = benefitMode;
      withOffers.customerBenefitPassed = customerBenefitPassed;
      payableNow = computeCommercialTotals_(withOffers).customerPayable;
    } else {
      payableNow = Math.max(0, payableBeforeOffer - customerBenefitPassed);
    }

    var schemeRules = null;
    try {
      schemeRules = getSchemeRulesForLeadDialog_(leadId);
    } catch (e5) {
      try {
        schemeRules = getSchemeOfferRulesForVehicle_(
          lead.interestedModel || '',
          lead.variant || '',
          (full && full.bookingDate) || lead.bookingDate || nowDate_()
        );
      } catch (e6) {
        schemeRules = { rules: {} };
      }
    }

    return {
      success: true,
      lead: {
        leadId: lead.leadId,
        customerName: lead.customerName || '',
        mobile: lead.mobile || '',
        leadSource: lead.leadSource || '',
        interestedModel: lead.interestedModel || '',
        model: lead.interestedModel || '',
        variant: lead.variant || '',
        executive: lead.executive || '',
        currentStatus: lead.currentStatus || '',
        priority: lead.priority || '',
        nextFollowUpDate: formatDate_(lead.nextFollowUpDate) || '',
        financeRequired: lead.financeRequired || '',
        exchangeRequired: lead.exchangeRequired || '',
        remarks: lead.remarks || '',
        bookingStatus: lead.bookingStatus || '',
        bookingAmount: Number(lead.bookingAmount || 0)
      },
      offer: offer,
      schemeRules: schemeRules,
      hasBooking: hasBooking,
      paymentsReceived: paid,
      bookingAmount: Number(lead.bookingAmount || 0),
      payableBeforeOffer: payableBeforeOffer,
      benefitMode: benefitMode,
      customerBenefitPassed: customerBenefitPassed,
      oemEligible: oemEligible,
      dealerBenefitRetained: (function () {
        try {
          if (full && typeof computeSchemeIncomeBreakdown_ === 'function') {
            return computeSchemeIncomeBreakdown_(full).retainedIncomeTotal;
          }
        } catch (eRet) {}
        return round2_(oemEligible - customerBenefitPassed);
      })(),
      customerPayable: payableNow,
      dealerMarginGrossInclGst: Number(dealerMargin.marginGrossInclGst || 0),
      dealerMarginGst: Number(dealerMargin.marginGst || 0),
      dealerMarginNetExGst: Number(dealerMargin.marginNetExGst || 0),
      oemExtraSupportReceived: Number(previewSnap.oemExtraSupportReceived || 0),
      oemExtraSupportPassed: Number(previewSnap.oemExtraSupportPassed || 0),
      oemExtraSupportRetained: Number(previewSnap.oemExtraSupportRetained || 0),
      outstanding: (typeof calcOutstanding_ === 'function')
        ? calcOutstanding_(payableNow, Number(lead.bookingAmount || 0), paid)
        : Math.max(0, payableNow - (paid > 0 ? paid : Number(lead.bookingAmount || 0)))
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e), errorCode: (e && e.errorCode) || 'ERROR' };
  }
}

function mergeDialogCss_() {
  return '<style>'
    + '.hint{font-size:12px;color:#555;line-height:1.4}'
    + '.grp{border:1px solid #ddd;border-radius:6px;padding:10px;margin:10px 0;background:#fafafa}'
    + '.grp-title{font-weight:600;font-size:13px;margin-bottom:8px}'
    + '.lead-line{font-size:12px;padding:4px 0;border-bottom:1px solid #eee}'
    + '.lead-line:last-child{border-bottom:none}'
    + '.grp-actions{margin-top:8px}'
    + '.grp-actions select{padding:6px;font-size:13px;width:100%}'
    + '.btn-sm{margin-top:8px;background:#6A1B9A;color:#fff;border:none;padding:8px;width:100%;cursor:pointer;border-radius:4px;font-size:13px}'
    + '.btn-sm:disabled{opacity:0.55}'
    + 'hr{border:none;border-top:1px solid #ddd;margin:16px 0}'
    + 'h4{margin:0 0 8px;font-size:14px}'
    + '</style>';
}

function mergeDialogClientJs_() {
  return [
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/\\u003c/g,"&lt;").replace(/>/g,"&gt;");}',
    'function fmt(n){return Number(n||0).toLocaleString("en-IN");}',
    'function renderGroups(groups){',
    '  var el=document.getElementById("groups");',
    '  if(!groups||groups.length===0){el.innerHTML="<em>No automatic duplicates found. Use manual merge below.</em>";return;}',
    '  el.innerHTML=groups.map(function(g,gi){',
    '    var opts=g.leads.map(function(l){return \'<option value="\'+esc(l.leadId)+\'">Keep \'+esc(l.leadId)+\' – \'+esc(l.customerName)+\'</option>\';}).join("");',
    '    var lines=g.leads.map(function(l){',
    '      return \'<div class="lead-line"><b>\'+esc(l.leadId)+\'</b> \'+esc(l.customerName)+\' &middot; \'+esc(l.accountStatus)+\' &middot; Outstanding &#8377;\'+fmt(l.outstanding)+\'</div>\';',
    '    }).join("");',
    '    return \'<div class="grp"><div class="grp-title">\'+esc(g.reason)+\'</div>\'+lines+\'<div class="grp-actions"><label>Keep this Lead ID</label><select id="keep_\'+gi+\'">\'+opts+\'</select><button class="btn-sm" type="button" onclick="mergeGroup(\'+gi+\')">Merge others into selected</button></div></div>\';',
    '  }).join("");',
    '  window.__MERGE_GROUPS=groups;',
    '}',
    'function mergeGroup(gi){',
    '  var g=window.__MERGE_GROUPS[gi];',
    '  var keep=document.getElementById("keep_"+gi).value;',
    '  var others=g.leads.filter(function(l){return l.leadId!==keep;});',
    '  if(others.length===0){alert("Select a lead to keep");return;}',
    '  var sec=others[0].leadId;',
    '  if(others.length>1&&!confirm("Merge "+others.length+" leads into "+keep+" one at a time. Continue with "+sec+" first?"))return;',
    '  document.getElementById("primaryId").value=keep;',
    '  document.getElementById("secondaryId").value=sec;',
    '  doMerge();',
    '}',
    'function doMerge(){',
    '  var p=document.getElementById("primaryId").value.trim();',
    '  var s=document.getElementById("secondaryId").value.trim();',
    '  if(!p||!s){alert("Enter both Lead IDs");return;}',
    '  if(p===s){alert("Cannot merge a lead into itself");return;}',
    '  if(!confirm("Keep "+p+" and merge "+s+" into it?\\n\\nPayments and activities will move. "+s+" will be archived."))return;',
    '  var b=document.getElementById("btnMerge");b.disabled=true;b.textContent="Merging...";',
    '  var done=false;',
    '  var t=setTimeout(function(){if(done)return;done=true;b.disabled=false;b.textContent="Merge Leads";alert("Merge is taking longer than expected. Check Audit Log — merge may still have completed.");},120000);',
    '  google.script.run.withSuccessHandler(function(r){if(done)return;done=true;clearTimeout(t);alert(r.message||"Merge complete");google.script.host.close();})',
    '    .withFailureHandler(function(e){if(done)return;done=true;clearTimeout(t);b.disabled=false;b.textContent="Merge Leads";alert(e.message||e);})',
    '    .mergeLeadsFromDialog({primaryId:p,secondaryId:s});',
    '}',
    'google.script.run.withSuccessHandler(renderGroups).withFailureHandler(function(e){',
    '  document.getElementById("groups").innerHTML="<em>Could not load duplicates: "+esc(e.message||e)+"</em>";',
    '}).getDuplicateLeadGroups();'
  ].join('\n');
}

function showMergeLeadsDialog_() {
  var html = createDialogOutput_(
dialogBaseCss_('#6A1B9A') + mergeDialogCss_() +
    '<h3>Merge Duplicate Leads</h3>' +
    '<p class="hint">Same customer with two Lead IDs (spelling mistake or duplicate feed)? ' +
    'Choose which ID to <b>keep</b>. All payments and activities move to the kept lead; the other is archived (not deleted).</p>' +
    '<div id="groups"><em>Scanning for similar names...</em></div>' +
    '<hr><h4>Manual merge</h4>' +
    '<label>Keep Lead ID *</label><input id="primaryId" placeholder="e.g. LD26000028">' +
    '<label>Merge this Lead ID into kept *</label><input id="secondaryId" placeholder="e.g. LD26000151">' +
    '<button class="btn" id="btnMerge" type="button" onclick="doMerge()">Merge Leads</button>' +
    htmlScript_(mergeDialogClientJs_()),
    500,
    640
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Merge Duplicate Leads');
}

function showSettingsDialog_() {
  ensureSchemeShareSettingsRows_();
  try { if (typeof ensureSchemeAndIncentiveSheets_ === 'function') ensureSchemeAndIncentiveSheets_(); } catch (e) {}
  var s = getSettings_();
  var html = createDialogOutput_(
'<style>body{font-family:Arial,sans-serif;padding:12px;font-size:13px}label{display:block;margin-top:10px;font-weight:600}' +
    'input{width:100%;padding:8px;box-sizing:border-box;margin-top:4px}button{margin-top:14px;width:100%;padding:10px;background:#1565C0;color:#fff;border:none;border-radius:4px}' +
    '.hint{font-size:12px;color:#555;margin:8px 0 12px;line-height:1.4}.sec{font-weight:700;margin-top:14px;border-top:1px solid #ddd;padding-top:10px}' +
    '.box{background:#E3F2FD;padding:10px;border-radius:6px;font-size:12px;line-height:1.45}</style>' +
    '<h3 style="margin:0">Settings</h3>' +
    '<div class="box"><b>Scheme shares (₹)</b> are maintained on sheet <b>Scheme Master</b> by Model + Component each month ' +
    '(Dealer Share / Company Share from OEM circular). Use <b>CRM → Scheme Master</b>. ' +
    'Manpower incentives: <b>Incentive Master</b>. These Settings fields are fallback only if Scheme Master has no match.</div>' +
    '<div class="sec">Company</div>' +
    '<label>Company Name</label><input id="companyName" value="' + escHtmlAttr_(s.companyName) + '">' +
    '<label>Financial Year</label><input id="financialYear" value="' + escHtmlAttr_(s.financialYear) + '">' +
    '<div class="sec">Fallback share amounts (₹) — only if Scheme Master miss</div>' +
    '<label>Consumer Discount share ₹</label><input id="schemeShareConsumerDiscount" type="number" min="0" step="0.01" value="' + Number(s.schemeShareConsumerDiscount || 0) + '">' +
    '<label>Exchange Bonus share ₹</label><input id="schemeShareExchangeBonus" type="number" min="0" step="0.01" value="' + Number(s.schemeShareExchangeBonus || 0) + '">' +
    '<label>Loyalty Bonus share ₹</label><input id="schemeShareLoyaltyBonus" type="number" min="0" step="0.01" value="' + Number(s.schemeShareLoyaltyBonus || 0) + '">' +
    '<label>Referral Bonus share ₹</label><input id="schemeShareReferralBonus" type="number" min="0" step="0.01" value="' + Number(s.schemeShareReferralBonus || 0) + '">' +
    '<label>DSA Bonus share ₹</label><input id="schemeShareDsaDiscount" type="number" min="0" step="0.01" value="' + Number(s.schemeShareDsaDiscount || 0) + '">' +
    '<button type="button" onclick="doSave()">Save Settings</button>' +
    htmlScript_(
    'function doSave(){' +
    '  var d={' +
    '    companyName:document.getElementById("companyName").value,' +
    '    financialYear:document.getElementById("financialYear").value,' +
    '    schemeShareConsumerDiscount:document.getElementById("schemeShareConsumerDiscount").value,' +
    '    schemeShareExchangeBonus:document.getElementById("schemeShareExchangeBonus").value,' +
    '    schemeShareLoyaltyBonus:document.getElementById("schemeShareLoyaltyBonus").value,' +
    '    schemeShareReferralBonus:document.getElementById("schemeShareReferralBonus").value,' +
    '    schemeShareDsaDiscount:document.getElementById("schemeShareDsaDiscount").value' +
    '  };' +
    '  google.script.run.withSuccessHandler(function(r){alert((r&&r.message)||"Saved");google.script.host.close();})' +
    '    .withFailureHandler(function(e){alert(e.message||e);}).saveSettingsFromDialog(d);' +
    '}'
    ),
    440,
    640
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Settings');
}

function escHtmlAttr_(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;');
}

function ensureSchemeShareSettingsRows_() {
  var keys = [
    'schemeShareConsumerDiscount', 'schemeShareExchangeBonus', 'schemeShareLoyaltyBonus',
    'schemeShareReferralBonus', 'schemeShareDsaDiscount', 'financeFilePrefix', 'nextFinanceFileCounter'
  ];
  var defaults = CRM.SETTINGS_DEFAULTS || {};
  keys.forEach(function (k) {
    try {
      var cur = getSettings_()[k];
      if (cur === undefined || cur === null || cur === '') {
        saveSettingSilent_(k, defaults[k] != null ? defaults[k] : 0);
      }
    } catch (e) {}
  });
  try { CacheService.getScriptCache().remove('settings'); } catch (e2) {}
}

function saveSettingsFromDialog(data) {
  try {
    data = data || {};
    function amt(v) {
      var n = Number(v);
      if (!isFinite(n) || n < 0) n = 0;
      return Math.round(n * 100) / 100;
    }
    if (data.companyName != null) saveSetting_('companyName', String(data.companyName).trim() || 'EV Dealership CRM');
    if (data.financialYear != null) saveSetting_('financialYear', String(data.financialYear).trim());
    saveSetting_('schemeShareConsumerDiscount', amt(data.schemeShareConsumerDiscount));
    saveSetting_('schemeShareExchangeBonus', amt(data.schemeShareExchangeBonus));
    saveSetting_('schemeShareLoyaltyBonus', amt(data.schemeShareLoyaltyBonus));
    saveSetting_('schemeShareReferralBonus', amt(data.schemeShareReferralBonus));
    saveSetting_('schemeShareDsaDiscount', amt(data.schemeShareDsaDiscount));
    try { CacheService.getScriptCache().remove('settings'); } catch (e) {}
    try { invalidateCrmStore_(); } catch (e2) {}
    return crmOk_('Scheme share amounts (₹) saved. Refresh Dashboard to recalculate company outstanding.', {});
  } catch (e) {
    return crmFailStructured_('Settings', 'saveSettingsFromDialog', 'handler', e, 0);
  }
}

/* ═══════════════════════════════════════════════════════════════════════════
   CLAIM DIALOGS — settle, manual entry, status update
   ═══════════════════════════════════════════════════════════════════════════ */

function showRecordClaimReceivedDialog_() {
  var today = nowDate_();
  var html = createDialogOutput_(
    dialogBaseCss_('#2E7D32') +
    '<h3>Record Claim Received</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 10px">When OEM / company pays the claim amount, record settlement here. Status → Received and Company Outstanding clears.</p>' +
    '<label>Claim *</label><select id="claimId"><option value="">Loading claims…</option></select>' +
    '<label>Received Date *</label><input id="receivedDate" type="date" value="' + today + '">' +
    '<label>Received Amount *</label><input id="receivedAmount" type="number" step="0.01" placeholder="Amount from OEM">' +
    '<label>OEM Reference / UTR *</label><input id="reference" placeholder="Claim ref / payment UTR (mandatory)">' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Record Received" onclick="doSave()">Record Received</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(claimSettleDialogJs_()),
    480, 520
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Record Claim Received');
}

function claimSettleDialogJs_() {
  return [
    'var claims=[];',
    'function loadClaims(){',
    '  google.script.run.withSuccessHandler(function(r){',
    '    if(!r||r.ok===false){alert(r&&r.message||"Could not load claims");return;}',
    '    claims=r.data.claims||[];',
    '    var el=document.getElementById("claimId");',
    '    if(!claims.length){el.innerHTML=\'<option value="">No open claims</option>\';return;}',
    '    el.innerHTML=claims.map(function(c){return \'<option value="\'+c.claimId+\'">\'+c.label+\'</option>\';}).join("");',
    '    onClaimPick();',
    '  }).withFailureHandler(function(e){alert(e.message||e);}).getOpenClaimsForDialog();',
    '}',
    'function onClaimPick(){',
    '  var id=document.getElementById("claimId").value;',
    '  var c=claims.find(function(x){return x.claimId===id;});',
    '  if(c&&!document.getElementById("receivedAmount").value)document.getElementById("receivedAmount").value=c.claimAmount;',
    '}',
    'function doSave(){',
    '  runDialogAction("Record Received","settleClaimFromDialog",function(){',
    '    var id=document.getElementById("claimId").value;',
    '    if(!id){alert("Select a claim");return null;}',
    '    var utr=String(document.getElementById("reference").value||"").trim();',
    '    if(!utr){alert("OEM Reference / UTR is mandatory");return null;}',
    '    return{claimId:id,receivedDate:document.getElementById("receivedDate").value,',
    '      receivedAmount:document.getElementById("receivedAmount").value,',
    '      reference:utr,remarks:document.getElementById("remarks").value};',
    '  },function(res){',
    '    alert("Claim settled: "+((res&&res.data&&res.data.claimId)||""));',
    '    kickDeferredCrmRefresh(function(){google.script.host.close();});});',
    '}',
    'document.getElementById("claimId").addEventListener("change",onClaimPick);',
    'window.onload=loadClaims;'
  ].join('');
}

function showAddManualClaimDialog_() {
  var today = nowDate_();
  var m = getMergedMasters_();
  var html = createDialogOutput_(
    dialogBaseCss_('#6A1B9A') +
    '<h3>Add Manual Claim</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 10px">For claims not tied to a booking snapshot. Entry is permanent — never archived.</p>' +
    '<label>Customer Name *</label><input id="customerName">' +
    '<label>Lead ID</label><input id="leadId" placeholder="Optional — LD…">' +
    '<label>Booking ID</label><input id="bookingId" placeholder="Optional">' +
    '<label>Model</label><select id="model">' + buildSelectOptionsHtml_(m['Models'], true) + '</select>' +
    '<label>Variant</label><input id="variant" placeholder="Optional">' +
    '<label>Claim Amount *</label><input id="claimAmount" type="number" step="0.01">' +
    '<label>Scheme Month</label><input id="schemeMonth" placeholder="YYYY-MM" value="' + today.substring(0, 7) + '">' +
    '<label>Status</label><select id="status"><option>Pending</option><option>Submitted</option><option>Approved</option><option>Received</option></select>' +
    '<label>Submitted Date</label><input id="submittedDate" type="date">' +
    '<label>OEM Reference</label><input id="reference">' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Add Claim" onclick="doSave()">Add Claim</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
      'function doSave(){runDialogAction("Add Claim","addManualClaimFromDialog",function(){' +
      'var cn=document.getElementById("customerName").value.trim();if(!cn){alert("Customer name required");return null;}' +
      'var amt=document.getElementById("claimAmount").value;if(!amt||Number(amt)<=0){alert("Claim amount required");return null;}' +
      'return{customerName:cn,leadId:document.getElementById("leadId").value,bookingId:document.getElementById("bookingId").value,' +
      'model:document.getElementById("model").value,variant:document.getElementById("variant").value,claimAmount:amt,' +
      'schemeMonth:document.getElementById("schemeMonth").value,status:document.getElementById("status").value,' +
      'submittedDate:document.getElementById("submittedDate").value,reference:document.getElementById("reference").value,' +
      'remarks:document.getElementById("remarks").value};},function(res){' +
      'alert("Claim added: "+((res&&res.data&&res.data.claimId)||""));kickDeferredCrmRefresh(function(){google.script.host.close();});});}'
    ),
    480, 620
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Add Manual Claim');
}

function showUpdateClaimStatusDialog_() {
  var today = nowDate_();
  var html = createDialogOutput_(
    dialogBaseCss_('#E65100') +
    '<h3>Update Claim Status</h3>' +
    '<label>Claim *</label><select id="claimId"><option value="">Loading…</option></select>' +
    '<label>New Status *</label><select id="status">' +
    '<option>Pending</option><option>Submitted</option><option>Approved</option><option>Rejected</option></select>' +
    '<label>Submitted Date</label><input id="submittedDate" type="date">' +
    '<label>Approved Date</label><input id="approvedDate" type="date">' +
    '<label>OEM Reference</label><input id="reference">' +
    '<label>DSA Approval</label><select id="dsaApproval"><option>Pending</option><option>Approved</option><option>Rejected</option></select>' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Update Status" onclick="doSave()">Update Status</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
      'var claims=[];function loadClaims(){google.script.run.withSuccessHandler(function(r){' +
      'if(!r||r.ok===false)return;claims=r.data.claims||[];' +
      'var el=document.getElementById("claimId");el.innerHTML=claims.length?claims.map(function(c){return \'<option value="\'+c.claimId+\'">\'+c.label+\'</option>\';}).join(""):\'<option value="">No open claims</option>\';' +
      '}).getOpenClaimsForDialog();}' +
      'function doSave(){runDialogAction("Update Status","updateClaimStatusFromDialog",function(){' +
      'var id=document.getElementById("claimId").value;if(!id){alert("Select claim");return null;}' +
      'return{claimId:id,status:document.getElementById("status").value,submittedDate:document.getElementById("submittedDate").value,' +
      'approvedDate:document.getElementById("approvedDate").value,reference:document.getElementById("reference").value,' +
      'dsaApproval:document.getElementById("dsaApproval").value,remarks:document.getElementById("remarks").value};},' +
      'function(){alert("Status updated");kickDeferredCrmRefresh(function(){google.script.host.close();});});}' +
      'window.onload=loadClaims;'
    ),
    480, 560
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Update Claim Status');
}

function menuRecordClaimReceived() { showRecordClaimReceivedDialog_(); }
function menuAddManualClaim() { showAddManualClaimDialog_(); }
function menuUpdateClaimStatus() { showUpdateClaimStatusDialog_(); }

// ═══════════════════════════════════════════════════════════════════════════
//  INSURANCE DIALOGS
// ═══════════════════════════════════════════════════════════════════════════

function showAddInsuranceEntryDialog_() {
  var today = nowDate_();
  var html = createDialogOutput_(
    dialogBaseCss_('#00695C') +
    '<h3>Add Insurance Entry</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 10px"><b>Payout Rate % is manual</b> — rates change. Suggested default fills for Storm/Turbo (49%) or others (36.5%); edit whenever needed.</p>' +
    '<label>Lead ID *</label><input id="leadId" placeholder="LD…">' +
    '<button type="button" class="btn" style="margin-bottom:8px;background:#455A64" onclick="loadCtx()">Load Lead</button>' +
    '<div id="info" style="font-size:12px;color:#333;margin:0 0 8px"></div>' +
    '<label>Insurance Company *</label><input id="company" placeholder="e.g. Bajaj Allianz">' +
    '<label>Insurance Amount (Premium) *</label><input id="amount" type="number" min="0" step="0.01">' +
    '<label>Payout Rate % *</label><input id="rate" type="number" min="0" step="0.1" placeholder="e.g. 49 or 36.5">' +
    '<div id="rateHint" style="font-size:11px;color:#666;margin:-4px 0 8px"></div>' +
    '<label>Expected Payout</label><input id="expected" disabled="disabled">' +
    '<label>Policy Number</label><input id="policy">' +
    '<label>Policy Date</label><input id="policyDate" type="date" value="' + today + '">' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Save Entry" onclick="doSave()">Save Entry</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
      'function recalc(){var amt=Number(document.getElementById("amount").value)||0;var rate=Number(document.getElementById("rate").value)||0;' +
      'document.getElementById("expected").value=Math.round(amt*(rate/100)*100)/100;}' +
      'function loadCtx(){var id=(document.getElementById("leadId").value||"").trim();if(!id){alert("Enter Lead ID");return;}' +
      'google.script.run.withSuccessHandler(function(r){' +
      'if(!r||!r.success){alert((r&&r.message)||"Lead not found");return;}' +
      'document.getElementById("info").textContent=(r.lead.customerName||"")+" | "+(r.lead.model||"")+" "+(r.lead.variant||"");' +
      'if(r.lead.insurerName)document.getElementById("company").value=r.lead.insurerName;' +
      'document.getElementById("amount").value=r.insuranceAmount||0;' +
      'document.getElementById("rate").value=r.payoutRatePercent||r.suggestedRatePercent||0;' +
      'document.getElementById("rateHint").textContent="Suggested for this model: "+(r.suggestedRatePercent||"—")+"% (edit if company rate differs)";' +
      'recalc();' +
      '}).withFailureHandler(function(e){alert(parseServerError(e));}).getInsuranceContextForDialog(id);}' +
      'document.getElementById("amount").addEventListener("input",recalc);' +
      'document.getElementById("rate").addEventListener("input",recalc);' +
      'function doSave(){runDialogAction("Save Insurance","saveInsuranceEntryFromDialog",function(){' +
      'var id=(document.getElementById("leadId").value||"").trim();var co=(document.getElementById("company").value||"").trim();' +
      'var amt=document.getElementById("amount").value;var rate=document.getElementById("rate").value;' +
      'if(!id){alert("Lead ID required");return null;}' +
      'if(!co){alert("Insurance company required");return null;}' +
      'if(!(Number(amt)>0)){alert("Insurance amount required");return null;}' +
      'if(rate===""||!(Number(rate)>=0)){alert("Enter payout rate % (manual — rates change)");return null;}' +
      'return{leadId:id,insuranceCompany:co,insuranceAmount:amt,payoutRatePercent:rate,' +
      'policyNumber:document.getElementById("policy").value,' +
      'policyDate:document.getElementById("policyDate").value,remarks:document.getElementById("remarks").value};},' +
      'function(res){var d=(res&&res.data)||res||{};alert("Saved. Expected payout ₹"+(d.expectedPayout||""));kickDeferredCrmRefresh(function(){google.script.host.close();});});}'
    ),
    480, 660
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Add Insurance Entry');
}

function showUpdateInsurancePayoutRateDialog_() {
  var html = createDialogOutput_(
    dialogBaseCss_('#00838F') +
    '<h3>Update Payout Rate %</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 10px">Change the % whenever the insurer rate changes. Expected payout and outstanding recalculate automatically.</p>' +
    '<label>Insurance Entry *</label><select id="entryId"><option value="">Loading…</option></select>' +
    '<label>New Payout Rate % *</label><input id="rate" type="number" min="0" step="0.1" placeholder="e.g. 42">' +
    '<div id="preview" style="font-size:12px;color:#333;margin:8px 0"></div>' +
    '<button class="btn" id="btn" type="button" data-label="Update Rate" onclick="doSave()">Update Rate</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
      'var byId={};' +
      'function loadEntries(){google.script.run.withSuccessHandler(function(r){' +
      'var sel=document.getElementById("entryId");var list=(r&&r.entries)||[];byId={};' +
      'if(!list.length){sel.innerHTML="<option value=\\"\\">No entries</option>";return;}' +
      'sel.innerHTML="<option value=\\"\\">Select…</option>";' +
      'list.forEach(function(e){byId[e.entryId]=e;var o=document.createElement("option");o.value=e.entryId;o.textContent=e.label;sel.appendChild(o);});' +
      '}).withFailureHandler(function(e){alert(parseServerError(e));}).getAllInsuranceEntriesForDialog();}' +
      'function onPick(){var e=byId[document.getElementById("entryId").value];if(!e){document.getElementById("preview").textContent="";return;}' +
      'document.getElementById("rate").value=e.payoutRatePercent||"";preview();}' +
      'function preview(){var e=byId[document.getElementById("entryId").value];if(!e)return;' +
      'var rate=Number(document.getElementById("rate").value)||0;var exp=Math.round((e.insuranceAmount||0)*(rate/100)*100)/100;' +
      'document.getElementById("preview").textContent="Premium ₹"+Math.round(e.insuranceAmount||0)+" → Expected ₹"+exp;}' +
      'document.getElementById("entryId").addEventListener("change",onPick);' +
      'document.getElementById("rate").addEventListener("input",preview);' +
      'function doSave(){runDialogAction("Update Rate","updateInsurancePayoutRateFromDialog",function(){' +
      'var id=document.getElementById("entryId").value;var rate=document.getElementById("rate").value;' +
      'if(!id){alert("Select entry");return null;}' +
      'if(rate===""||!(Number(rate)>=0)){alert("Enter payout rate %");return null;}' +
      'return{entryId:id,payoutRatePercent:rate};},' +
      'function(res){var d=(res&&res.data)||{};alert("Rate updated. Expected payout ₹"+(d.expectedPayout||""));kickDeferredCrmRefresh(function(){google.script.host.close();});});}' +
      'window.onload=loadEntries;'
    ),
    460, 420
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Update Payout Rate %');
}

function showRecordInsurancePayoutDialog_() {
  var html = createDialogOutput_(
    dialogBaseCss_('#2E7D32') +
    '<h3>Record Insurance Payout</h3>' +
    '<p style="font-size:12px;color:#666;margin:0 0 10px">Record amount received from the insurance company against an entry.</p>' +
    '<label>Insurance Entry *</label><select id="entryId"><option value="">Loading…</option></select>' +
    '<label>Amount Received *</label><input id="amount" type="number" min="0.01" step="0.01">' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<button class="btn" id="btn" type="button" data-label="Record Payout" onclick="doSave()">Record Payout</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_(
      'function loadEntries(){google.script.run.withSuccessHandler(function(r){' +
      'var sel=document.getElementById("entryId");var list=(r&&r.entries)||[];' +
      'if(!list.length){sel.innerHTML="<option value=\\"\\">No pending payouts</option>";return;}' +
      'sel.innerHTML="<option value=\\"\\">Select…</option>"+list.map(function(e){' +
      'return "<option value=\\""+e.entryId+"\\">"+String(e.label||e.entryId).replace(/</g,"")+"</option>";}).join("");' +
      '}).withFailureHandler(function(e){alert(parseServerError(e));}).getPendingInsurancePayoutsForDialog();}' +
      'function doSave(){runDialogAction("Record Payout","recordInsurancePayoutFromDialog",function(){' +
      'var id=document.getElementById("entryId").value;var amt=document.getElementById("amount").value;' +
      'if(!id){alert("Select entry");return null;}if(!(Number(amt)>0)){alert("Enter amount");return null;}' +
      'return{entryId:id,amount:amt,remarks:document.getElementById("remarks").value};},' +
      'function(){alert("Payout recorded");kickDeferredCrmRefresh(function(){google.script.host.close();});});}' +
      'window.onload=loadEntries;'
    ),
    440, 420
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Record Insurance Payout');
}
