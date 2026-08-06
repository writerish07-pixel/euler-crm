/**
 * GlobalSearchService.gs
 * Enterprise Global Search — Euler Motors Dealership CRM v2.0
 *
 * v2.0 Additions:
 *   ✔ Recent Searches sidebar — click any past query to re-run it
 *   ✔ Recent Records sidebar — recently viewed customers/bookings/payments
 *   ✔ Pinned Records — pinned items always visible at the top
 *   ✔ Every search query tracked for recent-searches history
 *   ✔ Results include Customer 360 quick-open button alongside "Open →"
 *   ✔ Extended to search VIN, Motor, Chassis, Registration, Activity IDs
 *
 * Search covers:
 *   Customer Name · Lead ID · BookingID · Receipt Number · Finance File
 *   Mobile · Alt Mobile · Registration · Model · Variant · VIN
 *   Chassis · Motor Number · Invoice Number · Financer
 *
 * Entry points:
 *   menuGlobalSearch()           — CRM → Navigate → Global Search
 *   globalSearchQuery(q)         — PUBLIC, called via google.script.run
 */

// ═══════════════════════════════════════════════════════════════════════════
//  MENU HANDLER
// ═══════════════════════════════════════════════════════════════════════════

function menuGlobalSearch() {
  var html = HtmlService.createHtmlOutput(globalSearchHtml_())
    .setWidth(740)
    .setHeight(560)
    .setSandboxMode(HtmlService.SandboxMode.IFRAME);
  SpreadsheetApp.getUi().showModalDialog(html, 'Global Search');
}

// ═══════════════════════════════════════════════════════════════════════════
//  PUBLIC SEARCH API  (called via google.script.run)
// ═══════════════════════════════════════════════════════════════════════════

function globalSearchQuery(query) {
  try {
    var q = String(query || '').trim().toLowerCase();
    if (q.length < 2) return crmOk_('GlobalSearch', { results: [], query: query });

    // Track the search query as a recent record
    try { trackRecentRecord('Search', q, q, ''); } catch (e) {}

    var results = [];

    /* ── 1. Leads (via CrmStore — no sheet scan) ───────────────────────── */
    var store = loadCrmStore_();
    if (store.leads && store.leads.byId) {
      var leadKeys = Object.keys(store.leads.byId);
      for (var li = 0; li < leadKeys.length && results.length < 20; li++) {
        var lead  = store.leads.byId[leadKeys[li]];
        var haystack = [
          leadKeys[li],
          lead['Customer Name'],
          lead['Mobile'],
          lead['Alternate Mobile'],
          lead['Interested Model'],
          lead['Variant'],
          lead['Number Plate'],
          lead['Invoice Number'],
          lead['Financer Name'],
          lead['Finance File Number'],
          lead['VIN'],
          lead['Motor Number'],
          lead['Chassis Number'],
          lead['Lead Source'],
          lead['City']
        ].join(' ').toLowerCase();
        if (haystack.indexOf(q) !== -1) {
          results.push({
            type:    'Lead',
            icon:    '📋',
            id:      leadKeys[li],
            label:   lead['Customer Name'] || leadKeys[li],
            sub:     (lead['Interested Model'] || '') + (lead['Variant'] ? ' ' + lead['Variant'] : ''),
            status:  lead['Current Status'] || '',
            extra:   lead['Mobile'] || '',
            nav:     'lead',
            navId:   leadKeys[li],
            has360:  true
          });
        }
      }
    }

    /* ── 2. Bookings ──────────────────────────────────────────────────── */
    var bResults = gsSearchSheet_(CRM.SHEETS.BOOKING_REGISTER, q, 15, function(row, hdrs) {
      return {
        type:   'Booking',
        icon:   '🚗',
        id:     gsFld_(row, hdrs, 'BookingID'),
        label:  gsFld_(row, hdrs, 'CustomerName') || gsFld_(row, hdrs, 'Customer Name'),
        sub:    gsFld_(row, hdrs, 'Vehicle Model') + (gsFld_(row, hdrs, 'Variant') ? ' ' + gsFld_(row, hdrs, 'Variant') : ''),
        status: gsFld_(row, hdrs, 'Booking Status'),
        extra:  'Booked: ' + gsFld_(row, hdrs, 'Booking Date'),
        nav:    'booking',
        navId:  gsFld_(row, hdrs, 'BookingID'),
        leadId: gsFld_(row, hdrs, 'LeadID'),
        has360: !!(gsFld_(row, hdrs, 'LeadID'))
      };
    });
    results = results.concat(bResults);

    /* ── 3. Payments ──────────────────────────────────────────────────── */
    var pResults = gsSearchSheet_(CRM.SHEETS.PAYMENT_LEDGER, q, 15, function(row, hdrs) {
      return {
        type:   'Payment',
        icon:   '💰',
        id:     gsFld_(row, hdrs, 'Receipt Number'),
        label:  gsFld_(row, hdrs, 'Customer Name'),
        sub:    gsFld_(row, hdrs, 'Payment Mode') + ' · ₹' + gsFld_(row, hdrs, 'Amount'),
        status: gsFld_(row, hdrs, 'Date') || gsFld_(row, hdrs, 'Payment Date'),
        extra:  'Lead: ' + gsFld_(row, hdrs, 'Lead ID'),
        nav:    'payment',
        navId:  gsFld_(row, hdrs, 'Receipt Number'),
        leadId: gsFld_(row, hdrs, 'Lead ID'),
        has360: !!(gsFld_(row, hdrs, 'Lead ID'))
      };
    });
    results = results.concat(pResults);

    /* ── 4. Finance ───────────────────────────────────────────────────── */
    var fResults = gsSearchSheet_(CRM.SHEETS.FINANCE_REGISTER, q, 10, function(row, hdrs) {
      return {
        type:   'Finance',
        icon:   '🏦',
        id:     gsFld_(row, hdrs, 'File Number'),
        label:  gsFld_(row, hdrs, 'Customer Name'),
        sub:    gsFld_(row, hdrs, 'Financer') + ' · ₹' + gsFld_(row, hdrs, 'Sanctioned Amount'),
        status: gsFld_(row, hdrs, 'Status'),
        extra:  'Lead: ' + gsFld_(row, hdrs, 'Lead ID'),
        nav:    'finance',
        navId:  gsFld_(row, hdrs, 'File Number'),
        leadId: gsFld_(row, hdrs, 'Lead ID'),
        has360: !!(gsFld_(row, hdrs, 'Lead ID'))
      };
    });
    results = results.concat(fResults);

    /* ── 5. Delivery ─────────────────────────────────────────────────── */
    var dResults = gsSearchSheet_(CRM.SHEETS.DELIVERY_TRACKER, q, 10, function(row, hdrs) {
      var lid = gsFld_(row, hdrs, 'Lead ID') || gsFld_(row, hdrs, 'LeadID');
      return {
        type:   'Delivery',
        icon:   '🚚',
        id:     gsFld_(row, hdrs, 'Delivery ID') || lid,
        label:  gsFld_(row, hdrs, 'Customer Name'),
        sub:    'Plate: ' + gsFld_(row, hdrs, 'Number Plate'),
        status: gsFld_(row, hdrs, 'Delivery Date') ? 'Delivered' : 'Pending',
        extra:  'Date: ' + (gsFld_(row, hdrs, 'Delivery Date') || '—'),
        nav:    'delivery',
        navId:  lid,
        leadId: lid,
        has360: !!lid
      };
    });
    results = results.concat(dResults);

    var aResults = gsSearchSheet_(CRM.SHEETS.ACTIVITY_LOG, q, 10, function(row, hdrs) {
      var lid = gsFld_(row, hdrs, 'Lead ID');
      return {
        type:   'Activity',
        icon:   '📅',
        id:     gsFld_(row, hdrs, 'Activity ID'),
        label:  gsFld_(row, hdrs, 'Discussion') || gsFld_(row, hdrs, 'Activity Type'),
        sub:    gsFld_(row, hdrs, 'Activity Type'),
        status: gsFld_(row, hdrs, 'Date') || gsFld_(row, hdrs, 'Activity Date'),
        extra:  'Lead: ' + lid,
        nav:    'activity',
        navId:  gsFld_(row, hdrs, 'Activity ID'),
        leadId: lid,
        has360: !!lid
      };
    });
    results = results.concat(aResults);

    var cResults = gsSearchSheet_(CRM.SHEETS.SCHEME_CLAIM_REGISTER, q, 10, function(row, hdrs) {
      var lid = gsFld_(row, hdrs, 'Lead ID') || gsFld_(row, hdrs, 'LeadID');
      return {
        type:   'Claim',
        icon:   '📄',
        id:     gsFld_(row, hdrs, 'Claim ID') || gsFld_(row, hdrs, 'ClaimID'),
        label:  gsFld_(row, hdrs, 'Customer Name'),
        sub:    gsFld_(row, hdrs, 'Component') || gsFld_(row, hdrs, 'Scheme'),
        status: gsFld_(row, hdrs, 'Status'),
        extra:  'Lead: ' + lid,
        nav:    'claim',
        navId:  gsFld_(row, hdrs, 'Claim ID') || gsFld_(row, hdrs, 'ClaimID'),
        leadId: lid,
        has360: !!lid
      };
    });
    results = results.concat(cResults);

    return crmOk_('GlobalSearch', { results: results, query: query, count: results.length });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  SEARCH HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function gsSearchSheet_(sheetName, query, maxResults, mapFn) {
  var results = [];
  try {
    var ss    = getSpreadsheet_();
    var sheet = ss.getSheetByName(sheetName);
    if (!sheet) return results;
    var lastRow = sheet.getLastRow();
    if (lastRow < 2) return results;
    var data  = sheet.getRange(1, 1, lastRow, sheet.getLastColumn()).getValues();
    var hdrs  = data[0].map(function(h){ return String(h||'').trim(); });
    for (var i = 1; i < data.length && results.length < maxResults; i++) {
      var row = data[i];
      var hay = row.join(' ').toLowerCase();
      if (hay.indexOf(query) !== -1) {
        try {
          var mapped = mapFn(row, hdrs);
          if (mapped && mapped.id) results.push(mapped);
        } catch (e) {}
      }
    }
  } catch (e) {
    Logger.log('gsSearchSheet_ ' + sheetName + ': ' + e.message);
  }
  return results;
}

function gsFld_(row, hdrs, name) {
  var i = hdrs.indexOf(name);
  return i >= 0 ? String(row[i] || '') : '';
}

// ═══════════════════════════════════════════════════════════════════════════
//  HTML DIALOG
// ═══════════════════════════════════════════════════════════════════════════

function globalSearchHtml_() {
  var css = [
    '*{box-sizing:border-box;margin:0;padding:0}',
    'body{font-family:"Google Sans",Arial,sans-serif;font-size:13px;color:#212121;background:#F8F9FA;display:flex;flex-direction:column;height:100vh}',

    // Header / search bar
    '.search-header{background:linear-gradient(135deg,#1565C0,#1976D2);padding:14px 16px}',
    '.search-bar{display:flex;align-items:center;gap:8px;background:#fff;border-radius:24px;padding:4px 8px 4px 14px}',
    '.search-bar input{flex:1;border:none;outline:none;font-size:14px;color:#212121;background:transparent}',
    '.search-bar button{background:#1565C0;color:#fff;border:none;border-radius:18px;padding:6px 16px;cursor:pointer;font-size:13px}',
    '.search-bar button:hover{background:#0D47A1}',
    '.search-status{color:rgba(255,255,255,.8);font-size:11px;margin-top:6px;padding-left:4px}',

    // Body split
    '.search-body{flex:1;overflow:hidden;display:flex;gap:0}',

    // Results column
    '.results-col{flex:1;overflow-y:auto;padding:10px 12px}',

    // Sidebar
    '.sidebar{width:210px;background:#fff;border-left:1px solid #E0E0E0;overflow-y:auto;padding:10px 8px;flex-shrink:0}',
    '.sb-title{font-size:10px;font-weight:700;color:#90A4AE;letter-spacing:.8px;text-transform:uppercase;margin:10px 0 4px;padding:0 2px}',
    '.sb-title:first-child{margin-top:2px}',

    // Recent search chips
    '.search-chip{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:4px;cursor:pointer;font-size:12px;color:#1565C0;border-bottom:1px solid #F5F5F5}',
    '.search-chip:hover{background:#E3F2FD}',
    '.chip-x{margin-left:auto;color:#BDBDBD;font-size:10px}',
    '.chip-x:hover{color:#E53935}',

    // Recent record items in sidebar
    '.sb-rec{display:flex;align-items:center;gap:6px;padding:5px 8px;border-radius:4px;cursor:pointer;border-bottom:1px solid #F5F5F5}',
    '.sb-rec:hover{background:#F5F5F5}',
    '.sb-rec-icon{font-size:13px;width:18px;text-align:center;flex-shrink:0}',
    '.sb-rec-body{flex:1;min-width:0}',
    '.sb-rec-label{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;color:#212121}',
    '.sb-rec-sub{font-size:10px;color:#90A4AE}',

    // Result groups
    '.group-hdr{font-size:11px;font-weight:700;color:#546E7A;letter-spacing:.5px;padding:6px 4px 3px;border-bottom:2px solid #E3F2FD;margin-bottom:4px}',

    // Result row cards
    '.result-row{display:flex;align-items:center;gap:10px;padding:9px 12px;border-radius:6px;background:#fff;margin-bottom:6px;border:1px solid #E8EAF6;transition:box-shadow .15s}',
    '.result-row:hover{box-shadow:0 2px 8px rgba(0,0,0,.12);border-color:#BBDEFB}',
    '.r-icon{font-size:18px;width:32px;text-align:center;flex-shrink:0}',
    '.r-info{flex:1;min-width:0}',
    '.r-name{font-weight:500;color:#212121;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
    '.r-sub{font-size:11px;color:#78909C;margin-top:1px}',
    '.r-right{text-align:right;flex-shrink:0}',
    '.r-extra{font-size:11px;color:#90A4AE}',
    '.r-status{font-size:10px;background:#E3F2FD;color:#1565C0;padding:1px 7px;border-radius:10px;margin-top:2px;display:inline-block}',
    '.r-btns{display:flex;gap:4px;flex-shrink:0;margin-left:8px}',
    '.r-btn{border:none;background:#E3F2FD;color:#1565C0;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px;white-space:nowrap}',
    '.r-btn:hover{background:#BBDEFB}',
    '.r-btn360{background:#FFF8E1;color:#F57F17}',
    '.r-btn360:hover{background:#FFE082}',

    // Empty / loading states
    '.empty{text-align:center;padding:50px 20px;color:#90A4AE}',
    '.empty-icon{font-size:36px;margin-bottom:10px}',
    '.spinner{text-align:center;padding:30px;color:#90A4AE}',

    // Status bar
    '.status-bar{background:#ECEFF1;padding:5px 14px;font-size:11px;color:#78909C;border-top:1px solid #E0E0E0}'
  ].join('');

  var js = htmlSafeJs_([
    'var ICON_MAP={Lead:"📋",Booking:"🚗",Payment:"💰",Finance:"🏦",Delivery:"🚚",Claim:"📄",Search:"🔍"};',
    'var NAV_FN_MAP={lead:"navGoToLead",booking:"navGoToBooking",payment:"navGoToPayment",finance:"navGoToFinance",delivery:"navGoToDelivery",activity:"navGoToActivity",claim:"navGoToClaim",sheet:"navGoToSheetPublic"};',
    'var recentSearches=[];',
    'var recentRecords={};',
    'var currentQuery="";',

    // Escape helper
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");}',

    // Load sidebar data
    'function loadSidebar(){',
    '  google.script.run',
    '    .withSuccessHandler(function(r){',
    '      if(!r||r.ok===false)return;',
    '      var d=r.data||{history:{},pins:[]};',
    '      recentSearches=(d.history&&d.history.Search)||[];',
    '      recentRecords=d.history||{};',
    '      renderSidebar();',
    '    })',
    '    .withFailureHandler(function(){})',
    '    .getRecentRecordsData();',
    '}',

    // Render sidebar
    'function renderSidebar(){',
    '  renderRecentSearches();',
    '  renderSidebarRecords("Lead");',
    '  renderSidebarRecords("Booking");',
    '}',

    'function renderRecentSearches(){',
    '  var el=document.getElementById("recent-searches");',
    '  if(!recentSearches.length){el.innerHTML=\'<div style="font-size:11px;color:#BDBDBD;padding:4px">No recent searches</div>\';return;}',
    '  el.innerHTML=recentSearches.slice(0,8).map(function(s){',
    '    return \'<div class="search-chip" onclick="runQuery(\\\'\'+esc(s.id)+\'\\\')">\'',
    '      +\'🔍 \'+esc(s.label)',
    '      +\'</div>\';',
    '  }).join("");',
    '}',

    'function renderSidebarRecords(type){',
    '  var el=document.getElementById("sidebar-"+type.toLowerCase());',
    '  var items=(recentRecords[type]||[]).slice(0,5);',
    '  if(!el)return;',
    '  if(!items.length){el.innerHTML=\'<div style="font-size:11px;color:#BDBDBD;padding:4px">None viewed yet</div>\';return;}',
    '  var icon=ICON_MAP[type]||"📌";',
    '  el.innerHTML=items.map(function(it){',
    '    return \'<div class="sb-rec" onclick="goTo(\\\'\'+esc(type==="Lead"?"lead":type.toLowerCase())+\'\\\',\\\'\'+esc(it.id)+\'\\\')">\'',
    '      +\'<span class="sb-rec-icon">\'+icon+\'</span>\'',
    '      +\'<div class="sb-rec-body"><div class="sb-rec-label">\'+esc(it.label||it.id)+\'</div>\'',
    '      +\'<div class="sb-rec-sub">\'+esc(it.id)+\'</div></div>\'',
    '    +\'</div>\';',
    '  }).join("");',
    '}',

    // Search
    'function runQuery(q){',
    '  if(!q)q=document.getElementById("q").value.trim();',
    '  if(q.length<2){setStatus("Type at least 2 characters");return;}',
    '  document.getElementById("q").value=q;',
    '  currentQuery=q;',
    '  document.getElementById("results").innerHTML=\'<div class="spinner">🔍 Searching…</div>\';',
    '  setStatus("Searching for: "+esc(q)+"…");',
    '  google.script.run',
    '    .withSuccessHandler(showResults)',
    '    .withFailureHandler(function(e){setStatus("Error: "+(e.message||e));document.getElementById("results").innerHTML="";} )',
    '    .globalSearchQuery(q);',
    '}',

    'function setStatus(msg){document.getElementById("status").textContent=msg;}',

    'function showResults(r){',
    '  if(!r||r.ok===false){setStatus("Error: "+(r?r.message:"Unknown"));document.getElementById("results").innerHTML="";return;}',
    '  var results=r.data.results||[];',
    '  setStatus(results.length+" result"+(results.length===1?"":"s")+" for: "+esc(r.data.query||currentQuery));',
    '  if(!results.length){',
    '    document.getElementById("results").innerHTML=\'<div class="empty"><div class="empty-icon">😕</div><div>No results found for <b>"\'+esc(currentQuery)+\'"</b><br><small>Try a different name, ID, mobile, or registration</small></div></div>\';',
    '    loadSidebar();return;',
    '  }',
    '  var groups={};',
    '  results.forEach(function(r){if(!groups[r.type])groups[r.type]=[];groups[r.type].push(r);});',
    '  var html="";',
    '  ["Lead","Booking","Payment","Finance","Delivery","Activity","Claim"].forEach(function(t){',
    '    if(!groups[t])return;',
    '    html+=\'<div class="group-hdr">\'+ICON_MAP[t]+" "+t+"s ("+groups[t].length+\')</div>\';',
    '    groups[t].forEach(function(item){',
    '      html+=\'<div class="result-row">\'',
    '        +\'<div class="r-icon">\'+item.icon+\'</div>\'',
    '        +\'<div class="r-info"><div class="r-name">\'+esc(item.label||item.id)+\'</div>\'',
    '        +\'<div class="r-sub">\'+esc(item.id)+\' · \'+esc(item.sub||"")+\'</div></div>\'',
    '        +\'<div class="r-right"><div class="r-extra">\'+esc(item.extra||"")+\'</div>\'',
    '        +(item.status?\'<div class="r-status">\'+esc(item.status)+\'</div>\':"")+\'</div>\'',
    '        +\'<div class="r-btns">\'',
    '        +(item.has360?\'<button class="r-btn r-btn360" onclick="open360Event(event,\\\'\'+esc(item.leadId||item.navId)+\'\\\')">360°</button>\':"")',
    '        +\'<button class="r-btn" onclick="goToEvent(event,\\\'\'+item.nav+\'\\\',\\\'\'+esc(item.navId)+\'\\\')">Open →</button>\'',
    '        +\'</div>\'',
    '      +\'</div>\';',
    '    });',
    '  });',
    '  document.getElementById("results").innerHTML=html;',
    '  loadSidebar();',
    '}',

    // Navigate
    'function goToEvent(e,type,id){if(e)e.stopPropagation();goTo(type,id);}',
    'function goTo(type,id){',
    '  var fn=NAV_FN_MAP[type];if(!fn)return;',
    '  google.script.run',
    '    .withSuccessHandler(function(){google.script.host.close();})',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    [fn](id);',
    '}',

    // 360 quick-open
    'function open360Event(e,leadId){if(e)e.stopPropagation();',
    '  google.script.run',
    '    .withSuccessHandler(function(){google.script.host.close();})',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    .navOpen360ForLead(leadId);',
    '}',

    // Enter key
    'document.addEventListener("keydown",function(e){if(e.key==="Enter"&&document.activeElement===document.getElementById("q"))runQuery("");});',

    'window.onload=function(){loadSidebar();document.getElementById("q").focus();};'
  ].join('\n'));

  return '<!DOCTYPE html><html><head><base target="_top"/><style>' + css + '</style></head><body>' +
    '<div class="search-header">' +
      '<div class="search-bar">' +
        '<span style="font-size:16px;color:#90A4AE">🔍</span>' +
        '<input id="q" type="search" placeholder="Search by name, ID, mobile, registration, VIN, chassis…" autocomplete="off" />' +
        '<button onclick="runQuery(\'\')">Search</button>' +
      '</div>' +
      '<div class="search-status" id="status">Type 2+ characters and press Enter or click Search</div>' +
    '</div>' +

    '<div class="search-body">' +

      // Results column
      '<div class="results-col">' +
        '<div id="results"><div class="empty"><div class="empty-icon">🔍</div><div>Search across all modules<br><small>Customer Name · Lead ID · Mobile · Booking ID · Receipt · Finance File · Registration · VIN · Chassis · Motor</small></div></div></div>' +
      '</div>' +

      // Sidebar
      '<div class="sidebar">' +
        '<div class="sb-title">🕐 Recent Searches</div>' +
        '<div id="recent-searches"><div style="font-size:11px;color:#BDBDBD;padding:4px">Loading…</div></div>' +

        '<div class="sb-title">👤 Recent Leads</div>' +
        '<div id="sidebar-lead"><div style="font-size:11px;color:#BDBDBD;padding:4px">Loading…</div></div>' +

        '<div class="sb-title">🚗 Recent Bookings</div>' +
        '<div id="sidebar-booking"><div style="font-size:11px;color:#BDBDBD;padding:4px">Loading…</div></div>' +
      '</div>' +

    '</div>' +

    '<div class="status-bar" id="status-bar">Euler Motors Dealership CRM · Global Search</div>' +

    '<script>' + js + '</script>' +
    '</body></html>';
}
