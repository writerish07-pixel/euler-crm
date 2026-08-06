/**
 * Customer360Service.gs
 * Enterprise Customer 360 View — Euler Motors Dealership CRM v2.0
 *
 * Shows a complete 360-degree view of one customer:
 *   Lead · Booking · Payments · Finance · Delivery · Activity · Commercial · Claims · Timeline
 *
 * v2.0 Additions:
 *   ✔ Smart Breadcrumbs (clickable: Dashboard > Lead > Booking > Payment > Delivery > Claim)
 *   ✔ Quick Actions panel (8 one-click actions)
 *   ✔ Related Records panel (all linked entities at a glance)
 *   ✔ Everything inside the dialog is clickable
 *   ✔ Pin customer from within the 360 view
 *   ✔ Recent Records tracking on every open
 */

// ═══════════════════════════════════════════════════════════════════════════
//  MENU HANDLERS
// ═══════════════════════════════════════════════════════════════════════════

function menuShowCustomer360() {
  showCustomer360WithPicker_();
}

function menuShowCustomer360FromCell() {
  try {
    var cell  = SpreadsheetApp.getActiveSheet().getActiveCell();
    var value = String(cell.getValue()).trim();
    if (!value) {
      SpreadsheetApp.getUi().alert('Select a cell containing a Lead ID first.');
      return;
    }
    var leadId = value.replace(/=HYPERLINK\([^,]+,"([^"]+)"\)/i, '$1');
    showCustomer360Dialog_(leadId);
  } catch (e) {
    SpreadsheetApp.getUi().alert('Error: ' + e.message);
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  DIALOG BUILDERS
// ═══════════════════════════════════════════════════════════════════════════

function showCustomer360WithPicker_() {
  var opts     = { title: 'Customer 360 — Select Lead', width: 640, height: 460 };
  var bodyHtml = '<p style="margin:0 0 8px;color:#555;font-size:13px">Search and select a customer to open their 360 view.</p>';
  var saveJs   =
    'function doSave(){' +
    '  var lid=document.getElementById("leadId").value;' +
    '  if(!lid){setStatus("Select a lead first","#c0392b");return;}' +
    '  setSaving();' +
    '  google.script.run' +
    '    .withSuccessHandler(function(r){' +
    '      if(r&&r.ok===false){setStatus(r.message||"Error","#c0392b");resetSaving();return;}' +
    '      google.script.host.close();' +
    '    })' +
    '    .withFailureHandler(function(e){setStatus(e.message||e,"#c0392b");resetSaving();})' +
    '    .showCustomer360FromPicker(lid);' +
    '}';
  var html = dialogWithLeadPicker_(
    'Customer 360', '#1565C0', 'Open 360 View', bodyHtml, saveJs, opts
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Customer 360');
}

function showCustomer360FromPicker(leadId) {
  showCustomer360Dialog_(leadId);
  return crmOk_('Customer360', {});
}

function showCustomer360Dialog_(leadId) {
  var result = getCustomer360Data(leadId);
  if (!result || result.ok === false) {
    SpreadsheetApp.getUi().alert('Customer 360', result ? result.message : 'Lead not found: ' + leadId, SpreadsheetApp.getUi().ButtonSet.OK);
    return;
  }
  var data = result.data;
  // Track this view
  try { trackRecentRecord('Lead', leadId, data.lead['Customer Name'] || leadId, data.lead['Interested Model'] || ''); } catch (e) {}

  var html = HtmlService.createHtmlOutput(customer360Html_(data))
    .setWidth(800)
    .setHeight(640)
    .setSandboxMode(HtmlService.SandboxMode.IFRAME);
  SpreadsheetApp.getUi().showModalDialog(html, 'Customer 360 — ' + (data.lead['Customer Name'] || leadId));
}

// ═══════════════════════════════════════════════════════════════════════════
//  PUBLIC DATA API  (called via google.script.run)
// ═══════════════════════════════════════════════════════════════════════════

function getCustomer360Data(leadId) {
  try {
    var store = loadCrmStore_();
    var lid   = String(leadId || '').trim();
    if (!lid) return { ok: false, message: 'Lead ID required' };

    var lead  = store.leads && store.leads.byId ? store.leads.byId[lid] : null;
    if (!lead) return { ok: false, message: 'Lead not found: ' + lid };

    // Payments for this lead
    var payments = [];
    if (store.payments && store.payments.rows) {
      var ph = store.payments.headers;
      store.payments.rows.forEach(function(r) {
        var rLid = String(rowVal_(r, ph, 'Lead ID') || rowVal_(r, ph, 'LeadID') || '').trim();
        if (rLid === lid) {
          payments.push({
            'Receipt Number': rowVal_(r, ph, 'Receipt Number'),
            'Payment Date':   formatDate_(rowVal_(r, ph, 'Date') || rowVal_(r, ph, 'Payment Date')),
            'Amount':         rowVal_(r, ph, 'Amount'),
            'Payment Mode':   rowVal_(r, ph, 'Payment Mode'),
            'Narration':      rowVal_(r, ph, 'Narration')
          });
        }
      });
    }

    // Activities
    var activities = [];
    if (store.activities && store.activities.rows) {
      var ah = store.activities.headers;
      store.activities.rows.forEach(function(r) {
        var rLid = String(rowVal_(r, ah, 'Lead ID') || rowVal_(r, ah, 'LeadID') || '').trim();
        if (rLid === lid) {
          activities.push({
            'Activity ID':    rowVal_(r, ah, 'Activity ID'),
            'Activity Date':  formatDate_(rowVal_(r, ah, 'Date') || rowVal_(r, ah, 'Activity Date')),
            'Activity Type':  rowVal_(r, ah, 'Activity Type'),
            'Discussion':     rowVal_(r, ah, 'Discussion'),
            'Next Follow-up': formatDate_(rowVal_(r, ah, 'Next Follow-up Date')),
            'Executive':      rowVal_(r, ah, 'Executive')
          });
        }
      });
      activities = activities.slice(-10).reverse(); // last 10, newest first
    }

    // Delivery
    var delivery = store.deliveryByLead ? store.deliveryByLead[lid] : null;

    // Commercial / Booking
    var commercial = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[lid] : null;

    // Relationships
    var rels = {};
    try { rels = navGetRelationshipsForLead_(lid); } catch (e) {}

    return crmOk_('Customer360', {
      lead:       lead,
      payments:   payments,
      activities: activities,
      delivery:   delivery,
      commercial: commercial,
      rels:       rels,
      dealerEarnings: (typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_() &&
        typeof getDealerEarningsForLead_ === 'function')
        ? (getDealerEarningsForLead_(lid) || null)
        : null,
      isOwner: typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_()
    });
  } catch (e) {
    return { ok: false, message: e.message };
  }
}

// ═══════════════════════════════════════════════════════════════════════════
//  HTML BUILDER
// ═══════════════════════════════════════════════════════════════════════════

function customer360Html_(data) {
  var lead       = data.lead       || {};
  var payments   = data.payments   || [];
  var activities = data.activities || [];
  var delivery   = data.delivery   || {};
  var commercial = data.commercial || {};
  var rels       = data.rels       || {};
  var dealerEarnings = data.dealerEarnings || null;
  var isOwner    = !!data.isOwner;
  var leadId     = String(lead['Lead ID'] || lead.leadId || '');

  var fmt = function(v) { return v ? String(v) : '—'; };
  var fmtMoney = function(v) {
    var n = Number(v) || 0;
    return n ? '₹' + n.toLocaleString('en-IN') : '₹0';
  };

  // ── Breadcrumb trail ──────────────────────────────────────────────────
  var breadcrumbs = [
    { label: 'Dashboard', type: 'sheet', id: CRM.SHEETS.DASHBOARD },
    { label: 'Lead Register', type: 'sheet', id: CRM.SHEETS.LEAD_REGISTER },
    { label: (lead['Customer Name'] || leadId), type: 'Lead', id: leadId }
  ];
  if (rels.bookingId) breadcrumbs.push({ label: rels.bookingId, type: 'Booking', id: rels.bookingId });
  var breadcrumbHtml = breadcrumbs.map(function(b, i) {
    var icon = { Lead:'📋', Booking:'🚗', sheet:'📊' }[b.type] || '📌';
    var link = '<span class="bc-item" onclick="navTo(\'' + b.type + '\',\'' + b.id.replace(/'/g,"\\'") + '\')">' + icon + ' ' + esc360_(b.label) + '</span>';
    return (i < breadcrumbs.length - 1) ? link + '<span class="bc-sep">›</span>' : '<span class="bc-item bc-current">' + icon + ' ' + esc360_(b.label) + '</span>';
  }).join('');

  // ── Status badge ───────────────────────────────────────────────────────
  var statusColor = { 'Delivered': '#2E7D32', 'Booked': '#1565C0', 'New': '#E65100', 'Lost': '#616161', 'Closed': '#616161' };
  var status = String(lead['Current Status'] || 'New');
  var badgeColor = statusColor[status] || '#546E7A';

  // ── Customer info block ────────────────────────────────────────────────
  var custHtml =
    row2_('Lead ID',       clickable360_(leadId, 'Lead', leadId),     'Status',   '<span style="background:' + badgeColor + ';color:#fff;padding:2px 10px;border-radius:10px;font-size:11px">' + status + '</span>') +
    row2_('Customer Name', clickable360_(fmt(lead['Customer Name']), '360', leadId),                'Mobile',   clickable360_(fmt(lead['Mobile']), '360', leadId)) +
    row2_('Alt Mobile',    fmt(lead['Alternate Mobile']),             'City',     fmt(lead['City'])) +
    row2_('Village',       fmt(lead['Village']),                      'Source',   fmt(lead['Lead Source'])) +
    row2_('Executive',     fmt(lead['Executive']),                    'Priority', fmt(lead['Priority'])) +
    row2_('Created',       fmt(lead['Created Date']),                 'Updated',  fmt(lead['Last Updated']));

  // ── Vehicle interest ───────────────────────────────────────────────────
  var vehHtml =
    row2_('Model',    fmt(lead['Interested Model']), 'Variant', fmt(lead['Variant'])) +
    row2_('Budget',   fmt(lead['Budget']),           'Exchange Required', fmt(lead['Exchange Required'])) +
    row2_('Finance Required', fmt(lead['Finance Required']), 'Financer', fmt(lead['Financer Name'])) +
    row2_('Finance File', lead['Finance File Number'] ?
      clickable360_(fmt(lead['Finance File Number']), 'Finance', lead['Finance File Number']) : '—',
      'Insurer', fmt(lead['Insurer Name']));

  // ── Booking block ──────────────────────────────────────────────────────
  var bookHtml;
  if (commercial && commercial.bookingId) {
    bookHtml =
      row2_('Booking ID',   clickable360_(fmt(commercial.bookingId), 'Booking', commercial.bookingId), 'Booking Date', fmt(commercial.bookingDate)) +
      row2_('Booking Amt',  fmtMoney(commercial.bookingAmount),  'Mode',      fmt(commercial.bookingMode)) +
      row2_('Ex Showroom',  fmtMoney(commercial.exShowroom),     'Payable',   fmtMoney(lead['Customer Payable']));
  } else if (lead['Booking Status']) {
    bookHtml = row2_('Booking Status', fmt(lead['Booking Status']), 'Booking Date', fmt(lead['Booking Date'])) +
               row2_('Booking Amt', fmtMoney(lead['Booking Amount']), '', '');
  } else {
    bookHtml = '<div style="color:#90A4AE;font-size:12px">No booking yet</div>';
  }

  // ── Delivery checklist ─────────────────────────────────────────────────
  var chkItems = ['Insurance','Registration','Invoice','RC','PDI','Accessories'];
  var chkHtml = chkItems.map(function(item) {
    var val = delivery ? String(delivery[item.toLowerCase()] || delivery[item] || '') : '';
    var ok  = val && val.toLowerCase() !== 'pending' && val !== '' && val !== 'No';
    return '<span style="display:inline-flex;align-items:center;gap:4px;margin:2px 6px 2px 0;font-size:12px">' +
      (ok ? '✅' : '⬜') + ' ' + item + '</span>';
  }).join('');
  var delSummary = delivery && delivery['Delivery Date']
    ? '<br><span style="font-size:12px;color:#555">Delivered: ' + fmt(delivery['Delivery Date']) +
      (delivery['Number Plate'] ? ' · Plate: <b>' + fmt(delivery['Number Plate']) + '</b>' : '') + '</span>'
    : '<br><span style="font-size:12px;color:#E65100">Not delivered yet</span>';

  // ── Finance ────────────────────────────────────────────────────────────
  var finHtml =
    row2_('Finance Required', fmt(lead['Finance Required']),  'Financer', fmt(lead['Financer Name'])) +
    row2_('Finance File',     lead['Finance File Number'] ? clickable360_(fmt(lead['Finance File Number']), 'Finance', lead['Finance File Number']) : '—',
          'Outstanding',  fmtMoney(lead['Customer Outstanding']));

  // ── Payment rows ───────────────────────────────────────────────────────
  var payRows = payments.map(function(p) {
    return '<tr>' +
      '<td>' + fmt(p['Payment Date']) + '</td>' +
      '<td>' + clickable360_(fmt(p['Receipt Number']), 'Payment', p['Receipt Number']) + '</td>' +
      '<td>' + fmt(p['Payment Mode']) + '</td>' +
      '<td style="text-align:right;font-weight:500">' + fmtMoney(p['Amount']) + '</td>' +
    '</tr>';
  }).join('') || '<tr><td colspan="4" style="text-align:center;color:#90A4AE">No payments recorded</td></tr>';

  // ── Activity timeline ──────────────────────────────────────────────────
  var actRows = activities.slice(0, 10).map(function(a) {
    return '<tr>' +
      '<td>' + fmt(a['Activity Date']) + '</td>' +
      '<td>' + clickable360_(fmt(a['Activity ID']), 'Activity', a['Activity ID']) + '</td>' +
      '<td><span class="tag">' + fmt(a['Activity Type']) + '</span></td>' +
      '<td>' + fmt(a['Discussion']) + '</td>' +
      '<td>' + fmt(a['Next Follow-up']) + '</td>' +
    '</tr>';
  }).join('') || '<tr><td colspan="5" style="text-align:center;color:#90A4AE">No activities</td></tr>';

  // ── Commercial Summary ─────────────────────────────────────────────────
  var commHtml =
    row2_('Ex Showroom',     fmtMoney(lead['Ex Showroom']),         'Customer Payable', fmtMoney(lead['Customer Payable'])) +
    row2_('Consumer Disc',   fmtMoney(lead['Consumer Discount']),   'Exchange Bonus',   fmtMoney(lead['Exchange Bonus'])) +
    row2_('OEM Scheme',      fmtMoney(lead['OEM Scheme Amount']),   'Dealer Scheme',    fmtMoney(lead['Dealer Scheme Amount'])) +
    row2_('Total Received',  fmtMoney(lead['Total Received']),      'Outstanding',      fmtMoney(lead['Customer Outstanding'])) +
    row2_('Next Follow-up',  fmt(lead['Next Follow-up Date']),      'Last Activity',    fmt(lead['Last Activity']));

  // ── Dealer Earnings Summary (OWNER ONLY) ───────────────────────────────
  var earnHtml = '';
  if (isOwner) {
    var de = dealerEarnings || {};
    earnHtml =
      row2_('OEM Scheme Retained', clickable360_(fmtMoney(de.dealerSchemeRetained || de.dealerBenefitRetained), 'DealerEarnings', leadId),
            'Insurance Income', clickable360_(fmtMoney(de.dealerInsuranceIncome || de.insuranceIncome), 'DealerEarnings', leadId)) +
      row2_('Finance Incentive', clickable360_(fmtMoney(de.financeIncentive), 'DealerEarnings', leadId),
            'Accessories Margin', clickable360_(fmtMoney(de.accessoriesMargin), 'DealerEarnings', leadId)) +
      row2_('Exchange Margin', clickable360_(fmtMoney(de.exchangeMargin), 'DealerEarnings', leadId),
            'Other Income', clickable360_(fmtMoney(de.otherIncome), 'DealerEarnings', leadId)) +
      row2_('Total Dealer Earnings', clickable360_(fmtMoney(de.totalDealerEarnings || de.totalExtraIncome), 'DealerEarnings', leadId),
            'Claim Status', fmt(de.claimStatus || de.profitStatus));
  }
  // ── Related Records panel ─────────────────────────────────────────────
  var relItems = [
    { icon: '📋', label: 'Lead',     type: 'Lead',     id: leadId,          avail: !!leadId },
    { icon: '🚗', label: 'Booking',  type: 'Booking',  id: rels.bookingId,  avail: !!rels.bookingId },
    { icon: '💰', label: 'Payments', type: 'sheet',    id: CRM.SHEETS.PAYMENT_LEDGER, avail: payments.length > 0 },
    { icon: '🏦', label: 'Finance',  type: 'Finance',  id: lead['Finance File Number'], avail: !!(lead['Finance File Number']) },
    { icon: '🚚', label: 'Delivery', type: 'Delivery', id: leadId,          avail: !!(delivery && delivery['Delivery Date']) },
    { icon: '📄', label: 'Claims',   type: 'sheet',    id: CRM.SHEETS.SCHEME_CLAIM_REGISTER, avail: true },
    { icon: '📅', label: 'Activity', type: 'sheet',    id: CRM.SHEETS.ACTIVITY_LOG, avail: activities.length > 0 },
    { icon: '💼', label: 'Commercial', type: 'sheet',  id: CRM.SHEETS.COMMERCIAL_SNAPSHOT, avail: !!(commercial && commercial.bookingId) }
  ];
  if (isOwner) {
    relItems.push({
      icon: '📈', label: 'Earnings', type: 'DealerEarnings', id: leadId,
      avail: !!(dealerEarnings && (dealerEarnings.totalDealerEarnings || dealerEarnings.totalExtraIncome))
    });
  }
  var relHtml = relItems.map(function(r) {
    var cls = r.avail ? 'rel-btn rel-active' : 'rel-btn rel-inactive';
    var onclick = r.avail ? ' onclick="navTo(\'' + r.type + '\',\'' + String(r.id||'').replace(/'/g,"\\'") + '\')"' : '';
    return '<div class="' + cls + '"' + onclick + '>' + r.icon + '<br><span>' + r.label + '</span>' + (r.avail ? '' : '<br><span style="font-size:9px;color:#BDBDBD">—</span>') + '</div>';
  }).join('');

  // ── Quick Actions panel ───────────────────────────────────────────────
  var quickActions = [
    { icon: '✏️',  label: 'Edit Lead',       fn: 'menuUpdateLead',         arg: leadId,  server: true },
    { icon: '📅',  label: 'Add Activity',    fn: 'menuAddActivity',        arg: '',      server: true },
    { icon: '🚗',  label: 'Create Booking',  fn: 'menuConvertToBooking',   arg: '',      server: true },
    { icon: '💸',  label: 'Update Scheme',   fn: 'menuSchemeUpdate',       arg: '',      server: true },
    { icon: '💰',  label: 'Add Payment',     fn: 'menuAddPayment',         arg: '',      server: true },
    { icon: '🏦',  label: 'Finance Update',  fn: 'menuRecordFinancerReceipt', arg: '',   server: true },
    { icon: '🚚',  label: 'Mark Delivered',  fn: 'menuMarkDelivered',      arg: '',      server: true },
    { icon: '📌',  label: 'Pin Customer',    fn: 'doPinCustomer',          arg: '',      server: false }
  ];
  var qaHtml = quickActions.map(function(qa) {
    var onclick;
    if (!qa.server) {
      onclick = 'onclick="' + qa.fn + '()"';
    } else if (qa.arg) {
      onclick = 'onclick="runServerFn(\'' + qa.fn + '\',\'' + qa.arg + '\')"';
    } else {
      onclick = 'onclick="runServerFn(\'' + qa.fn + '\',null)"';
    }
    return '<button class="qa-btn" ' + onclick + '>' + qa.icon + '<span>' + qa.label + '</span></button>';
  }).join('');

  // ══════════════════════════════════════════════════════════════════════
  //  CSS
  // ══════════════════════════════════════════════════════════════════════
  var css = [
    '*{box-sizing:border-box;margin:0;padding:0}',
    'body{font-family:"Google Sans",Arial,sans-serif;font-size:13px;color:#212121;background:#F1F3F4;height:100vh;display:flex;flex-direction:column}',

    // Breadcrumb
    '.breadcrumb{background:#fff;border-bottom:1px solid #E0E0E0;padding:8px 14px;display:flex;align-items:center;flex-wrap:wrap;gap:2px;font-size:12px}',
    '.bc-item{color:#1565C0;cursor:pointer;padding:2px 4px;border-radius:3px}',
    '.bc-item:hover{background:#E3F2FD}',
    '.bc-current{color:#424242;cursor:default;font-weight:500}',
    '.bc-sep{color:#BDBDBD;padding:0 2px}',

    // Header
    '.c360-header{background:linear-gradient(135deg,#1565C0,#1976D2);color:#fff;padding:12px 16px;display:flex;align-items:center;justify-content:space-between}',
    '.c360-title{font-size:16px;font-weight:500}',
    '.c360-id{font-size:11px;opacity:.8;font-family:monospace}',
    '.c360-header-btns{display:flex;gap:6px}',
    '.hbtn{background:rgba(255,255,255,.15);border:none;color:#fff;padding:4px 10px;border-radius:4px;cursor:pointer;font-size:12px}',
    '.hbtn:hover{background:rgba(255,255,255,.25)}',

    // Layout
    '.c360-body{flex:1;overflow:hidden;display:flex;gap:0}',
    '.c360-main{flex:1;overflow-y:auto;padding:10px 12px}',
    '.c360-sidebar{width:200px;background:#fff;border-left:1px solid #E0E0E0;overflow-y:auto;padding:10px 8px;flex-shrink:0}',

    // Sections
    '.section{background:#fff;border-radius:6px;border:1px solid #E8EAF6;margin-bottom:8px}',
    '.sec-hdr{background:#1565C0;color:#fff;padding:6px 12px;font-size:11px;font-weight:700;letter-spacing:.8px;text-transform:uppercase;border-radius:5px 5px 0 0}',
    '.sec-body{padding:10px 12px}',

    // Data tables
    '.dtbl{width:100%;border-collapse:collapse;font-size:12px}',
    '.dtbl td{padding:4px 8px;border-bottom:1px solid #F5F5F5;vertical-align:top}',
    '.dtbl td:first-child{color:#78909C;width:130px;font-weight:500;white-space:nowrap}',
    '.dtbl td:nth-child(3){color:#78909C;width:130px;font-weight:500;white-space:nowrap}',

    // Payment / activity table
    '.ptbl{width:100%;border-collapse:collapse;font-size:12px}',
    '.ptbl th{background:#F5F5F5;padding:5px 8px;text-align:left;font-weight:600;font-size:11px;color:#546E7A}',
    '.ptbl td{padding:5px 8px;border-bottom:1px solid #F5F5F5}',
    '.ptbl tr:last-child td{border-bottom:none}',

    // Clickable values
    '.nav-link{color:#1565C0;cursor:pointer;text-decoration:underline dotted}',
    '.nav-link:hover{color:#0D47A1}',

    // Status tag
    '.tag{background:#E3F2FD;color:#1565C0;padding:1px 7px;border-radius:10px;font-size:11px}',

    // Sidebar sections
    '.sb-title{font-size:10px;font-weight:700;color:#90A4AE;letter-spacing:.8px;text-transform:uppercase;margin:8px 0 4px}',

    // Related records
    '.rel-grid{display:grid;grid-template-columns:1fr 1fr;gap:4px;margin-bottom:8px}',
    '.rel-btn{text-align:center;padding:8px 4px;border-radius:6px;font-size:11px;border:1px solid #E0E0E0;background:#fff;line-height:1.3}',
    '.rel-active{cursor:pointer;border-color:#BBDEFB;color:#1565C0}',
    '.rel-active:hover{background:#E3F2FD;box-shadow:0 1px 4px rgba(0,0,0,.1)}',
    '.rel-inactive{color:#BDBDBD;border-style:dashed}',

    // Quick Actions
    '.qa-grid{display:flex;flex-direction:column;gap:4px}',
    '.qa-btn{display:flex;align-items:center;gap:8px;padding:7px 8px;border-radius:5px;border:none;background:#F5F5F5;cursor:pointer;width:100%;text-align:left;font-size:12px;color:#212121}',
    '.qa-btn:hover{background:#E3F2FD;color:#1565C0}',
    '.qa-btn span{font-size:11px}'
  ].join('');

  // ══════════════════════════════════════════════════════════════════════
  //  JavaScript
  // ══════════════════════════════════════════════════════════════════════
  var js = htmlSafeJs_([
    'var LEAD_ID="' + leadId.replace(/"/g, '\\"') + '";',
    'var CUST_NAME="' + String(lead['Customer Name']||'').replace(/"/g, '\\"') + '";',
    'var CUST_MODEL="' + String(lead['Interested Model']||'').replace(/"/g, '\\"') + '";',

    // Navigate from within dialog — close dialog first, then navigate
    'function navTo(type,id){',
    '  if(!id||id==="—")return;',
    '  if(type==="360"){open360(id);return;}',
    '  var fnMap={',
    '    Lead:"navGoToLead",Booking:"navGoToBooking",Payment:"navGoToPayment",',
    '    Finance:"navGoToFinance",Delivery:"navGoToDelivery",Activity:"navGoToActivity",',
    '    Claim:"navGoToClaim",Commercial:"navGoToCommercialSnapshot",',
    '    DealerEarnings:"navGoToDealerEarnings",sheet:"navGoToSheetPublic"',
    '  };',
    '  var fn=fnMap[type];if(!fn)return;',
    '  google.script.run',
    '    .withSuccessHandler(function(){google.script.host.close();})',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    [fn](id);',
    '}',

    // Open 360 for another lead (mobile search link)
    'function open360(leadId){',
    '  google.script.run',
    '    .withSuccessHandler(function(){google.script.host.close();})',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    .navOpen360ForLead(leadId);',
    '}',

    // Run server function (Quick Actions)
    'function runServerFn(fn,arg){',
    '  google.script.host.close();',
    '  // Tiny delay so dialog fully closes before opening the next one',
    '  setTimeout(function(){',
    '    if(arg){google.script.run.withFailureHandler(function(){}).withSuccessHandler(function(){})[fn](arg);}',
    '    else{google.script.run.withFailureHandler(function(){}).withSuccessHandler(function(){})[fn]();}',
    '  },300);',
    '}',

    // Pin the customer
    'function doPinCustomer(){',
    '  google.script.run',
    '    .withSuccessHandler(function(){alert("📌 "+CUST_NAME+" pinned to Recent Records");} )',
    '    .withFailureHandler(function(e){alert(e.message||e);})',
    '    .pinRecord("Lead",LEAD_ID,CUST_NAME,CUST_MODEL);',
    '}',

    // Print summary — just prints the dialog
    'function printSummary(){window.print();}',

    // Click on phone number to find leads by mobile (calls global search)
    'function searchMobile(mobile){',
    '  google.script.host.close();',
    '  setTimeout(function(){google.script.run.withFailureHandler(function(){}).menuGlobalSearch();},300);',
    '}'
  ].join('\n'));

  // ══════════════════════════════════════════════════════════════════════
  //  ASSEMBLE HTML
  // ══════════════════════════════════════════════════════════════════════
  return '<!DOCTYPE html><html><head><base target="_top"/><style>' + css + '</style></head><body>' +

    // Breadcrumb
    '<div class="breadcrumb">' + breadcrumbHtml + '</div>' +

    // Header
    '<div class="c360-header">' +
      '<div><div class="c360-title">👤 ' + esc360_(lead['Customer Name'] || leadId) + '</div>' +
        '<div class="c360-id">' + esc360_(leadId) + ' · ' + esc360_(lead['Mobile'] || '') + ' · ' + esc360_(lead['Interested Model'] || '') + '</div></div>' +
      '<div class="c360-header-btns">' +
        '<button class="hbtn" onclick="doPinCustomer()">📌 Pin</button>' +
        '<button class="hbtn" onclick="printSummary()">🖨️ Print</button>' +
      '</div>' +
    '</div>' +

    // Main body with sidebar
    '<div class="c360-body">' +

      // ── Main content column ────────────────────────────────────────────
      '<div class="c360-main">' +

        // Customer Details
        '<div class="section"><div class="sec-hdr">Customer Details</div><div class="sec-body"><table class="dtbl">' + custHtml + '</table></div></div>' +

        // Vehicle Interest
        '<div class="section"><div class="sec-hdr">Vehicle & Finance Interest</div><div class="sec-body"><table class="dtbl">' + vehHtml + '</table></div></div>' +

        // Booking
        '<div class="section"><div class="sec-hdr">Booking</div><div class="sec-body"><table class="dtbl">' + bookHtml + '</table></div></div>' +

        // Delivery
        '<div class="section"><div class="sec-hdr">Delivery Checklist</div><div class="sec-body">' + chkHtml + delSummary + '</div></div>' +

        // Finance
        '<div class="section"><div class="sec-hdr">Finance</div><div class="sec-body"><table class="dtbl">' + finHtml + '</table></div></div>' +

        // Payments
        '<div class="section"><div class="sec-hdr">Payment History (' + payments.length + ')</div><div class="sec-body">' +
          '<table class="ptbl"><thead><tr><th>Date</th><th>Receipt #</th><th>Mode</th><th style="text-align:right">Amount</th></tr></thead>' +
          '<tbody>' + payRows + '</tbody></table></div></div>' +

        // Activities
        '<div class="section"><div class="sec-hdr">Activity Timeline (last 10)</div><div class="sec-body">' +
          '<table class="ptbl"><thead><tr><th>Date</th><th>Activity ID</th><th>Type</th><th>Discussion</th><th>Next F/U</th></tr></thead>' +
          '<tbody>' + actRows + '</tbody></table></div></div>' +

        // Commercial Summary
        '<div class="section"><div class="sec-hdr">Commercial Summary</div><div class="sec-body"><table class="dtbl">' + commHtml + '</table></div></div>' +

        (isOwner
          ? '<div class="section"><div class="sec-hdr">Dealer Earnings Summary (Owner Only)</div><div class="sec-body"><table class="dtbl">' + earnHtml + '</table></div></div>'
          : '') +

      '</div>' + // end c360-main

      // ── Sidebar ────────────────────────────────────────────────────────
      '<div class="c360-sidebar">' +

        '<div class="sb-title">⚡ Quick Actions</div>' +
        '<div class="qa-grid">' + qaHtml + '</div>' +

        '<div class="sb-title" style="margin-top:14px">🔗 Related Records</div>' +
        '<div class="rel-grid">' + relHtml + '</div>' +

      '</div>' + // end sidebar

    '</div>' + // end c360-body

    '<script>' + js + '</script>' +
    '</body></html>';
}

// ═══════════════════════════════════════════════════════════════════════════
//  HELPERS
// ═══════════════════════════════════════════════════════════════════════════

function esc360_(s) {
  return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function clickable360_(displayText, type, id) {
  if (!id || String(id).trim() === '' || String(id).trim() === '—') return displayText;
  var onclick = 'navTo(\'' + String(type).replace(/'/g, "\\'") + '\',\'' + String(id).replace(/'/g, "\\'") + '\')';
  return '<span class="nav-link" onclick="' + onclick + '">' + esc360_(displayText) + '</span>';
}

function row2_(label1, val1, label2, val2) {
  return '<tr>' +
    '<td>' + label1 + '</td><td>' + String(val1 || '—') + '</td>' +
    (label2 ? '<td>' + label2 + '</td><td>' + String(val2 || '—') + '</td>' : '<td></td><td></td>') +
    '</tr>';
}
