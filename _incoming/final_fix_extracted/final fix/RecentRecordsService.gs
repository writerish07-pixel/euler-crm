/**
 * RecentRecordsService.gs
 * Enterprise Recent Records & Navigation History — Euler Motors Dealership CRM
 *
 * Tracks recently viewed records across every module and supports pinning.
 * Data is stored in PropertiesService (UserProperties) so each operator gets
 * their own personal history without touching any spreadsheet.
 *
 * Public API (called via CRM menu and google.script.run):
 *   menuRecentRecords()                  — Opens the Recent Records panel
 *   menuPinRecord()                      — Pins the currently selected record
 *   trackRecentRecord(type, id, label)   — Called by every navigation function
 *   getRecentRecordsData()               — Returns data for dialogs
 *   getPinnedRecords()                   — Returns pinned records
 *   pinRecord(type, id, label)           — Pins a record
 *   unpinRecord(type, id)                — Unpins a record
 *   clearRecentHistory()                 — Clears history (keeps pins)
 */

// ═══════════════════════════════════════════════════════════════════════════
//  CONSTANTS
// ═══════════════════════════════════════════════════════════════════════════

var RR_HISTORY_KEY_ = 'crm_recent_history';
var RR_PINS_KEY_    = 'crm_pinned_records';
var RR_MAX_PER_TYPE_= 10;   // max recent items stored per record type
var RR_TYPES_       = ['Lead', 'Booking', 'Payment', 'Finance', 'Delivery', 'Claim', 'Search'];

// ═══════════════════════════════════════════════════════════════════════════
//  STORAGE HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function rrGetProps_()  { return PropertiesService.getUserProperties(); }

function rrLoadHistory_() {
  try {
    var raw = rrGetProps_().getProperty(RR_HISTORY_KEY_);
    return raw ? JSON.parse(raw) : {};
  } catch (e) { return {}; }
}

function rrSaveHistory_(hist) {
  try { rrGetProps_().setProperty(RR_HISTORY_KEY_, JSON.stringify(hist)); } catch (e) {}
}

function rrLoadPins_() {
  try {
    var raw = rrGetProps_().getProperty(RR_PINS_KEY_);
    return raw ? JSON.parse(raw) : [];
  } catch (e) { return []; }
}

function rrSavePins_(pins) {
  try { rrGetProps_().setProperty(RR_PINS_KEY_, JSON.stringify(pins)); } catch (e) {}
}

// ═══════════════════════════════════════════════════════════════════════════
//  CORE TRACKING API
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Record a recently viewed item. Called by every navGoTo* function.
 * @param {string} type  One of 'Lead','Booking','Payment','Finance','Delivery','Claim','Search'
 * @param {string} id    The record ID (LeadID, BookingID, receipt #, etc.)
 * @param {string} label Human-readable label (Customer Name, or search query, etc.)
 * @param {string} [sub] Optional subtitle (Model, status, etc.)
 */
function trackRecentRecord(type, id, label, sub) {
  try {
    var hist = rrLoadHistory_();
    if (!hist[type]) hist[type] = [];
    // Remove existing entry for same id so we can re-add at front
    hist[type] = hist[type].filter(function(r){ return r.id !== String(id); });
    hist[type].unshift({
      type:  type,
      id:    String(id   || ''),
      label: String(label|| id  || ''),
      sub:   String(sub  || ''),
      ts:    new Date().toISOString()
    });
    // Trim to max
    if (hist[type].length > RR_MAX_PER_TYPE_) {
      hist[type] = hist[type].slice(0, RR_MAX_PER_TYPE_);
    }
    rrSaveHistory_(hist);
  } catch (e) {
    Logger.log('trackRecentRecord: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  PIN / UNPIN
// ═══════════════════════════════════════════════════════════════════════════

/**
 * Pin a record for quick access from the top of the Recent Records panel.
 */
function pinRecord(type, id, label, sub) {
  try {
    var pins = rrLoadPins_();
    // Don't duplicate
    var exists = pins.some(function(p){ return p.type === type && p.id === String(id); });
    if (!exists) {
      pins.unshift({ type: type, id: String(id), label: String(label||id), sub: String(sub||''), ts: new Date().toISOString() });
      if (pins.length > 20) pins = pins.slice(0, 20);
      rrSavePins_(pins);
    }
    return crmOk_('RecentRecords', { pinned: true, id: id });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/**
 * Unpin a record.
 */
function unpinRecord(type, id) {
  try {
    var pins = rrLoadPins_();
    pins = pins.filter(function(p){ return !(p.type === type && p.id === String(id)); });
    rrSavePins_(pins);
    return crmOk_('RecentRecords', { pinned: false, id: id });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  DATA ACCESS (called via google.script.run from dialogs)
// ═══════════════════════════════════════════════════════════════════════════

/** Returns { history: {Lead:[...], Booking:[...], ...}, pins: [...] } */
function getRecentRecordsData() {
  try {
    var hist = rrLoadHistory_();
    var pins = rrLoadPins_();
    return crmOk_('RecentRecords', { history: hist, pins: pins });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Returns just the pins array. */
function getPinnedRecords() {
  try {
    return crmOk_('RecentRecords', { pins: rrLoadPins_() });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Clear history but preserve pins. */
function clearRecentHistory() {
  try {
    rrGetProps_().deleteProperty(RR_HISTORY_KEY_);
    return crmOk_('RecentRecords', { cleared: true });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

/** Clear all pins. */
function clearPinnedRecords() {
  try {
    rrGetProps_().deleteProperty(RR_PINS_KEY_);
    return crmOk_('RecentRecords', { cleared: true });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  MENU HANDLER — opens the Recent Records panel dialog
// ═══════════════════════════════════════════════════════════════════════════

function menuRecentRecords() {
  var html = HtmlService.createHtmlOutput(recentRecordsHtml_())
    .setWidth(700)
    .setHeight(540)
    .setSandboxMode(HtmlService.SandboxMode.IFRAME);
  SpreadsheetApp.getUi().showModelessDialog(html, 'Recent Records');
}

// ═══════════════════════════════════════════════════════════════════════════
//  HTML DIALOG
// ═══════════════════════════════════════════════════════════════════════════

function recentRecordsHtml_() {
  var typeIconMap = {
    Lead:     { icon: '📋', color: '#1565C0' },
    Booking:  { icon: '🚗', color: '#2E7D32' },
    Payment:  { icon: '💰', color: '#E65100' },
    Finance:  { icon: '🏦', color: '#6A1B9A' },
    Delivery: { icon: '🚚', color: '#00695C' },
    Claim:    { icon: '📄', color: '#B71C1C' },
    Search:   { icon: '🔍', color: '#37474F' }
  };

  var navFnMap = JSON.stringify({
    Lead:     'navGoToLead',
    Booking:  'navGoToBooking',
    Payment:  'navGoToPayment',
    Finance:  'navGoToFinance',
    Delivery: 'navGoToDelivery',
    Claim:    'navGoToSheetPublic',
    Search:   'menuGlobalSearch'
  });

  var iconMap  = JSON.stringify(typeIconMap);

  var css = [
    '*{box-sizing:border-box;margin:0;padding:0}',
    'body{font-family:"Google Sans",Arial,sans-serif;font-size:13px;color:#212121;background:#F8F9FA}',
    '.header{background:#1565C0;color:#fff;padding:14px 18px;display:flex;align-items:center;justify-content:space-between}',
    '.header h2{font-size:16px;font-weight:500;letter-spacing:.3px}',
    '.header-actions{display:flex;gap:8px}',
    '.hbtn{background:rgba(255,255,255,.15);border:none;color:#fff;padding:5px 12px;border-radius:4px;cursor:pointer;font-size:12px}',
    '.hbtn:hover{background:rgba(255,255,255,.25)}',
    '.tabs{display:flex;background:#fff;border-bottom:2px solid #E3F2FD;overflow-x:auto;padding:0 12px}',
    '.tab{padding:10px 14px;cursor:pointer;font-size:12px;font-weight:500;color:#546E7A;white-space:nowrap;border-bottom:2px solid transparent;margin-bottom:-2px}',
    '.tab.active{color:#1565C0;border-bottom-color:#1565C0}',
    '.tab:hover:not(.active){background:#F5F5F5;border-radius:4px 4px 0 0}',
    '.panel{display:none;padding:12px;overflow-y:auto;max-height:420px}',
    '.panel.active{display:block}',
    '.section-title{font-size:11px;font-weight:700;color:#90A4AE;letter-spacing:.8px;text-transform:uppercase;margin:10px 0 6px}',
    '.rec{display:flex;align-items:center;gap:10px;padding:8px 10px;border-radius:6px;cursor:pointer;border:1px solid #E8EAF6;background:#fff;margin-bottom:6px;transition:box-shadow .15s}',
    '.rec:hover{box-shadow:0 2px 8px rgba(0,0,0,.12);border-color:#BBDEFB}',
    '.rec-icon{font-size:18px;width:32px;text-align:center;flex-shrink:0}',
    '.rec-body{flex:1;min-width:0}',
    '.rec-label{font-weight:500;color:#212121;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.rec-sub{font-size:11px;color:#78909C;margin-top:1px}',
    '.rec-id{font-size:11px;color:#90A4AE;font-family:monospace}',
    '.rec-actions{display:flex;gap:6px;flex-shrink:0}',
    '.rbtn{border:none;background:transparent;cursor:pointer;font-size:12px;padding:4px 8px;border-radius:4px;color:#1565C0}',
    '.rbtn:hover{background:#E3F2FD}',
    '.rbtn.pin{color:#FF8F00}',
    '.rbtn.pin:hover{background:#FFF8E1}',
    '.rbtn.unpin{color:#E53935}',
    '.rbtn.unpin:hover{background:#FFEBEE}',
    '.ts{font-size:10px;color:#BDBDBD;margin-left:auto;white-space:nowrap;padding-left:8px}',
    '.empty{text-align:center;padding:40px;color:#90A4AE}',
    '.empty-icon{font-size:32px;margin-bottom:8px}',
    '.status-bar{padding:6px 16px;font-size:11px;color:#78909C;background:#ECEFF1;border-top:1px solid #E0E0E0}'
  ].join('');

  var js = htmlSafeJs_([
    'var ICON_MAP=' + iconMap + ';',
    'var NAV_FN_MAP=' + navFnMap + ';',
    'var allData={history:{},pins:[]};',

    // Tab switching
    'function switchTab(name){',
    '  document.querySelectorAll(".tab").forEach(function(t){t.classList.toggle("active",t.dataset.tab===name)});',
    '  document.querySelectorAll(".panel").forEach(function(p){p.classList.toggle("active",p.id==="panel-"+name)});',
    '}',

    // Format timestamp
    'function fmtTs(iso){try{var d=new Date(iso);return d.toLocaleDateString("en-IN",{day:"2-digit",month:"short"})+" "+d.toLocaleTimeString("en-IN",{hour:"2-digit",minute:"2-digit"});}catch(e){return "";}}',

    // Escape HTML
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}',

    // Render a single record card
    'function recCard(item,isPinned){',
    '  var meta=ICON_MAP[item.type]||{icon:"📌",color:"#546E7A"};',
    '  var pinBtn=isPinned',
    '    ?\'<button class="rbtn unpin" onclick="doUnpin(event,\\\'\'+esc(item.type)+\'\\\',\\\'\'+esc(item.id)+\'\\\')">Unpin</button>\'',
    '    :\'<button class="rbtn pin" onclick="doPin(event,\\\'\'+esc(item.type)+\'\\\',\\\'\'+esc(item.id)+\'\\\',\\\'\'+esc(item.label)+\'\\\',\\\'\'+esc(item.sub||"")+\'\\\')">📌 Pin</button>\';',
    '  return \'<div class="rec" onclick="goTo(\\\'\'+esc(item.type)+\'\\\',\\\'\'+esc(item.id)+\'\\\')">\'+',
    '    \'<div class="rec-icon">\'+meta.icon+\'</div>\'+',
    '    \'<div class="rec-body">\'+',
    '      \'<div class="rec-label">\'+esc(item.label)+\'</div>\'+',
    '      \'<div class="rec-sub">\'+esc(item.type)+\' · \'+esc(item.sub||"")+\'</div>\'+',
    '      \'<div class="rec-id">\'+esc(item.id)+\'</div>\'+',
    '    \'</div>\'+',
    '    \'<div class="ts">\'+fmtTs(item.ts||"")+\'</div>\'+',
    '    \'<div class="rec-actions">\'+pinBtn+',
    '      \'<button class="rbtn" onclick="goTo(event,\\\'\'+esc(item.type)+\'\\\',\\\'\'+esc(item.id)+\'\\\')">Open →</button>\'+',
    '    \'</div>\'+',
    '  \'</div>\';',
    '}',

    // Render a type section
    'function renderSection(type,items){',
    '  if(!items||!items.length)return\'<div class="empty"><div class="empty-icon">—</div><div>No recent \'+type+\' records</div></div>\';',
    '  return items.map(function(it){return recCard(it,false);}).join("");',
    '}',

    // Render the "All" panel
    'function renderAll(){',
    '  var h=allData.history;',
    '  var types=["Lead","Booking","Payment","Finance","Delivery","Claim","Search"];',
    '  var html="";',
    '  types.forEach(function(t){',
    '    var items=h[t];',
    '    if(!items||!items.length)return;',
    '    var meta=ICON_MAP[t]||{icon:"📌"};',
    '    html+=\'<div class="section-title">\'+meta.icon+" "+t+"s</div>";',
    '    items.slice(0,5).forEach(function(it){html+=recCard(it,false);});',
    '  });',
    '  if(!html)html=\'<div class="empty"><div class="empty-icon">📂</div><div>No records viewed yet</div></div>\';',
    '  document.getElementById("panel-All").innerHTML=html;',
    '}',

    // Render pinned panel
    'function renderPins(){',
    '  var pins=allData.pins;',
    '  var html=pins.length?pins.map(function(it){return recCard(it,true);}).join("")',
    '    :\'<div class="empty"><div class="empty-icon">📌</div><div>No pinned records yet<br><small>Click Pin on any record to add it here</small></div></div>\';',
    '  document.getElementById("panel-Pinned").innerHTML=html;',
    '}',

    // Render a specific type panel
    'function renderType(type){',
    '  var items=(allData.history[type]||[]);',
    '  document.getElementById("panel-"+type).innerHTML=renderSection(type,items);',
    '}',

    // Load all data
    'function loadData(){',
    '  document.getElementById("status").textContent="Loading...";',
    '  google.script.run',
    '    .withSuccessHandler(function(r){',
    '      if(!r||r.ok===false){document.getElementById("status").textContent="Error: "+(r?r.message:"Unknown");return;}',
    '      allData=r.data||{history:{},pins:[]};',
    '      renderAll();renderPins();',
    '      ["Lead","Booking","Payment","Finance","Delivery","Claim","Search"].forEach(renderType);',
    '      document.getElementById("status").textContent="Last updated: "+new Date().toLocaleTimeString("en-IN");',
    '    })',
    '    .withFailureHandler(function(e){document.getElementById("status").textContent="Error: "+(e.message||e);})',
    '    .getRecentRecordsData();',
    '}',

    // Navigate to record
    'function goTo(e,type,id){',
    '  if(e&&e.stopPropagation)e.stopPropagation();',
    '  var fn=NAV_FN_MAP[type];',
    '  if(!fn)return;',
    '  if(type==="Search"){google.script.run.withSuccessHandler(function(){}).menuGlobalSearch();return;}',
    '  google.script.run',
    '    .withSuccessHandler(function(){google.script.host.close();})',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    [fn](id);',
    '}',

    // Pin actions
    'function doPin(e,type,id,label,sub){',
    '  if(e&&e.stopPropagation)e.stopPropagation();',
    '  google.script.run',
    '    .withSuccessHandler(function(){loadData();})',
    '    .withFailureHandler(function(err){alert(err.message||err);})',
    '    .pinRecord(type,id,label,sub);',
    '}',
    'function doUnpin(e,type,id){',
    '  if(e&&e.stopPropagation)e.stopPropagation();',
    '  google.script.run',
    '    .withSuccessHandler(function(){loadData();})',
    '    .withFailureHandler(function(err){alert(err.message||err);})',
    '    .unpinRecord(type,id);',
    '}',

    // Clear actions
    'function doClearHistory(){',
    '  if(!confirm("Clear all recent history? Pinned records will be kept."))return;',
    '  google.script.run.withSuccessHandler(function(){allData.history={};renderAll();["Lead","Booking","Payment","Finance","Delivery","Claim","Search"].forEach(renderType);}).clearRecentHistory();',
    '}',
    'function doClearPins(){',
    '  if(!confirm("Remove all pinned records?"))return;',
    '  google.script.run.withSuccessHandler(function(){allData.pins=[];renderPins();}).clearPinnedRecords();',
    '}',

    'window.onload=function(){loadData();};'
  ].join('\n'));

  // Build tab headers
  var allTypes = ['All', 'Pinned', 'Lead', 'Booking', 'Payment', 'Finance', 'Delivery', 'Claim', 'Search'];
  var tabsHtml = allTypes.map(function(t, i) {
    return '<div class="tab' + (i === 0 ? ' active' : '') + '" data-tab="' + t + '" onclick="switchTab(\'' + t + '\')">' + t + '</div>';
  }).join('');

  var panelsHtml = allTypes.map(function(t, i) {
    return '<div class="panel' + (i === 0 ? ' active' : '') + '" id="panel-' + t + '"><div class="empty"><div class="empty-icon">⏳</div><div>Loading...</div></div></div>';
  }).join('');

  return '<!DOCTYPE html><html><head><base target="_top" /><style>' + css + '</style></head><body>' +
    '<div class="header">' +
      '<h2>📂 Recent Records</h2>' +
      '<div class="header-actions">' +
        '<button class="hbtn" onclick="doClearHistory()">Clear History</button>' +
        '<button class="hbtn" onclick="doClearPins()">Clear Pins</button>' +
        '<button class="hbtn" onclick="loadData()">↻ Refresh</button>' +
      '</div>' +
    '</div>' +
    '<div class="tabs">' + tabsHtml + '</div>' +
    '<div style="flex:1;overflow:hidden">' + panelsHtml + '</div>' +
    '<div class="status-bar" id="status">Loading…</div>' +
    '<script>' + js + '</script>' +
    '</body></html>';
}
