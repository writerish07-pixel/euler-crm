/**
 * RelationshipEngineService – normalized relationship links for fast lookups.
 */

/** Safe config access — works even if Config.gs Phase 3 block is not yet deployed. */
function getPhase3TableConfig_(key, fallbackCols) {
  var cfg = CRM && CRM[key];
  if (cfg && cfg.COLS && cfg.COLS.length) return cfg;
  return { HEADER_ROW: 1, DATA_START: 2, COLS: fallbackCols };
}

var PHASE3_FALLBACKS_ = {
  BOOKING_REGISTER: [
    'BookingID', 'LeadID', 'CustomerName', 'Booking Date', 'Vehicle Model', 'Variant',
    'Booking Amount', 'Amount Received', 'Payment Mode', 'Finance Required', 'Exchange Required', 'CommercialSnapshotID',
    'Booking Status', 'Created By', 'Created Date', 'Last Updated'
  ],
  RELATIONSHIP_INDEX: [
    'LeadID', 'CustomerName', 'Mobile', 'BookingID', 'CommercialSnapshotID',
    'PaymentIDs', 'DeliveryID', 'ClaimID', 'LatestActivityID',
    'Current Status', 'Last Updated'
  ],
  BOOKING_STATUS_HISTORY: [
    'Timestamp', 'LeadID', 'BookingID', 'Old Status', 'New Status', 'Remark', 'Updated By'
  ],
  VEHICLE_ALLOCATION: [
    'AllocationID', 'LeadID', 'BookingID', 'VIN', 'Motor Number', 'Chassis Number', 'Allocated Date', 'Status', 'Remark'
  ],
  QUOTATION_SCHEMA: [
    'QuotationID', 'LeadID', 'BookingID', 'QuotationVersion', 'PriceVersion', 'SchemeVersion', 'CommercialTermsHash', 'Generated At'
  ],
  EXECUTIVE_SCORECARD: [
    'Executive', 'Assigned Leads', 'Today Activities', 'Pending Follow-ups', 'Bookings', 'Deliveries',
    'Outstanding Collections', 'Conversion %', 'Avg Discount', 'Avg Booking Value', 'Updated At'
  ],
  DEALER_DAILY_REGISTER: [
    'Date', 'Leads', 'Bookings', 'Payments Total', 'Cash', 'UPI', 'Finance',
    'Other Payments', 'Deliveries', 'Outstanding', 'Top Executive', 'Updated At'
  ]
};

function ensurePhase3Sheets_() {
  var ss = getSpreadsheet_();
  if (!CRM || !CRM.SHEETS) return;
  ensureSimpleTableSheet_(ss, CRM.SHEETS.BOOKING_REGISTER, getPhase3TableConfig_('BOOKING_REGISTER', PHASE3_FALLBACKS_.BOOKING_REGISTER).COLS, false);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.RELATIONSHIP_INDEX, getPhase3TableConfig_('RELATIONSHIP_INDEX', PHASE3_FALLBACKS_.RELATIONSHIP_INDEX).COLS, true);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.BOOKING_STATUS_HISTORY, getPhase3TableConfig_('BOOKING_STATUS_HISTORY', PHASE3_FALLBACKS_.BOOKING_STATUS_HISTORY).COLS, true);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.VEHICLE_ALLOCATION, getPhase3TableConfig_('VEHICLE_ALLOCATION', PHASE3_FALLBACKS_.VEHICLE_ALLOCATION).COLS, true);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.QUOTATION_SCHEMA, getPhase3TableConfig_('QUOTATION_SCHEMA', PHASE3_FALLBACKS_.QUOTATION_SCHEMA).COLS, true);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.EXECUTIVE_SCORECARD, getPhase3TableConfig_('EXECUTIVE_SCORECARD', PHASE3_FALLBACKS_.EXECUTIVE_SCORECARD).COLS, false);
  ensureSimpleTableSheet_(ss, CRM.SHEETS.DEALER_DAILY_REGISTER, getPhase3TableConfig_('DEALER_DAILY_REGISTER', PHASE3_FALLBACKS_.DEALER_DAILY_REGISTER).COLS, false);
}

function ensureSimpleTableSheet_(ss, sheetName, cols, hidden) {
  if (!sheetName || !cols || !cols.length) return null;
  var sheet = ss.getSheetByName(sheetName);
  if (!sheet) sheet = ss.insertSheet(sheetName);
  var header = getHeaders_(sheet, 1);
  if (sheet.getLastRow() < 1 || !header.length) {
    sheet.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    sheet.setFrozenRows(1);
  } else {
    // Append missing columns only — never clear live data rows.
    cols.forEach(function (c) {
      if (findHeaderIndex_(header, c) < 0) {
        sheet.getRange(1, header.length + 1).setValue(c).setFontWeight('bold');
        header = getHeaders_(sheet, 1);
      }
    });
    sheet.setFrozenRows(1);
  }
  if (hidden) sheet.hideSheet(); else if (sheet.isSheetHidden()) sheet.showSheet();
  return sheet;
}

function findRowById_(sheet, idColName, idValue) {
  var headers = getHeaders_(sheet, 1);
  var idx = headers.indexOf(idColName) + 1;
  if (idx < 1) return -1;
  var lastRow = sheet.getLastRow();
  if (lastRow < 2) return -1;
  var vals = sheet.getRange(2, idx, lastRow - 1, 1).getValues();
  var want = String(idColName || '').toLowerCase() === 'date'
    ? formatDate_(idValue)
    : String(idValue || '').trim();
  for (var i = 0; i < vals.length; i++) {
    var cell = String(idColName || '').toLowerCase() === 'date'
      ? formatDate_(vals[i][0])
      : String(vals[i][0] || '').trim();
    if (cell === want) return i + 2;
  }
  return -1;
}

function upsertBookingRegister_(rowObj) {
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.BOOKING_REGISTER);
  var headers = getHeaders_(sheet, 1);
  var cols = getPhase3TableConfig_('BOOKING_REGISTER', PHASE3_FALLBACKS_.BOOKING_REGISTER).COLS;
  // Prefer writing by actual header names (supports old + newly appended columns).
  var bookingId = rowObj.BookingID || '';
  var leadId = rowObj.LeadID || '';
  var row = bookingId ? findRowById_(sheet, 'BookingID', bookingId) : -1;
  if (row < 0 && leadId) row = findRowById_(sheet, 'LeadID', leadId);
  if (row < 0) row = Math.max(sheet.getLastRow() + 1, 2);

  cols.forEach(function (c) {
    if (rowObj[c] === undefined) return;
    var col = findHeaderIndex_(headers, c) + 1;
    if (col > 0) setValueSafe_(sheet.getRange(row, col), rowObj[c]);
  });
  // Also write any extra keys present on the live sheet.
  Object.keys(rowObj).forEach(function (c) {
    if (cols.indexOf(c) >= 0) return;
    var col = findHeaderIndex_(headers, c) + 1;
    if (col > 0) setValueSafe_(sheet.getRange(row, col), rowObj[c]);
  });
  return row;
}

/** Update Finance Required / financer fields on Booking Register for a lead. */
function updateBookingRegisterFinanceFlag_(leadId, financeRequired, financerName, paymentMode) {
  leadId = String(leadId || '').trim();
  if (!leadId) return;
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.BOOKING_REGISTER);
  if (!sheet) return;
  var headers = getHeaders_(sheet, 1);
  var row = findRowById_(sheet, 'LeadID', leadId);
  if (row < 0) return;
  function set(name, val) {
    if (val === undefined || val === null) return;
    var col = findHeaderIndex_(headers, name) + 1;
    // setValueSafe_ prevents 'Reject input' rules on Booking Register columns from blocking writes.
    if (col > 0) setValueSafe_(sheet.getRange(row, col), val);
  }
  if (financeRequired !== undefined) set('Finance Required', financeRequired);
  if (paymentMode !== undefined) set('Payment Mode', paymentMode);
  // Optional financer column if present
  if (financerName !== undefined) set('Financer Name', financerName);
}

function appendBookingStatusHistory_(entry) {
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.BOOKING_STATUS_HISTORY);
  var row = [
    nowDateTime_(),
    entry.leadId || '',
    entry.bookingId || '',
    entry.oldStatus || '',
    entry.newStatus || '',
    entry.remark || '',
    getUserEmail_()
  ];
  var newRow = Math.max(sheet.getLastRow() + 1, 2);
  sheet.getRange(newRow, 1, 1, row.length).setValues([row]);
}

function upsertRelationshipIndex_(entry) {
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.RELATIONSHIP_INDEX);
  var cols = getPhase3TableConfig_('RELATIONSHIP_INDEX', PHASE3_FALLBACKS_.RELATIONSHIP_INDEX).COLS;
  var leadId = entry.LeadID || '';
  if (!leadId) return -1;
  var row = findRowById_(sheet, 'LeadID', leadId);
  if (row < 0) row = Math.max(sheet.getLastRow() + 1, 2);
  var existing = {};
  if (row <= sheet.getLastRow()) {
    var current = sheet.getRange(row, 1, 1, cols.length).getValues()[0];
    cols.forEach(function (c, i) { existing[c] = current[i]; });
  }
  cols.forEach(function (c) {
    if (entry[c] !== undefined && entry[c] !== null && entry[c] !== '') existing[c] = entry[c];
  });
  existing['Last Updated'] = nowDateTime_();
  var out = cols.map(function (c) { return existing[c] === undefined ? '' : existing[c]; });
  sheet.getRange(row, 1, 1, out.length).setValues([out]);
  return row;
}

/**
 * Link a booking to its lead in RelationshipIndex. Restored: BookingService called
 * this but it was never defined, so (being inside a try/catch) every booking
 * silently failed to register its BookingID — leaving RelationshipIndex, and
 * therefore navigation/Customer 360, blind to bookings.
 */
function appendRelationshipBooking_(leadId, bookingId, snapshotId) {
  if (!leadId || !bookingId) return;
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.RELATIONSHIP_INDEX);
  var row = findRowById_(sheet, 'LeadID', leadId);
  var entry = { LeadID: leadId, BookingID: bookingId };
  if (snapshotId) entry.CommercialSnapshotID = snapshotId;
  if (row < 0) { upsertRelationshipIndex_(entry); return; }
  var headers = getHeaders_(sheet, 1);
  var bi = headers.indexOf('BookingID') + 1;
  if (bi > 0) sheet.getRange(row, bi).setValue(bookingId);
  if (snapshotId) {
    var si = headers.indexOf('CommercialSnapshotID') + 1;
    if (si > 0) sheet.getRange(row, si).setValue(snapshotId);
  }
  var li = headers.indexOf('Last Updated') + 1;
  if (li > 0) sheet.getRange(row, li).setValue(nowDateTime_());
}

function appendRelationshipPayment_(leadId, paymentId) {
  if (!leadId || !paymentId) return;
  ensurePhase3Sheets_();
  var sheet = getSheet_(CRM.SHEETS.RELATIONSHIP_INDEX);
  var row = findRowById_(sheet, 'LeadID', leadId);
  if (row < 0) {
    upsertRelationshipIndex_({ LeadID: leadId, PaymentIDs: paymentId });
    return;
  }
  var headers = getHeaders_(sheet, 1);
  var idx = headers.indexOf('PaymentIDs') + 1;
  var old = String(sheet.getRange(row, idx).getValue() || '').trim();
  var list = old ? old.split(',') : [];
  if (list.indexOf(paymentId) < 0) list.push(paymentId);
  sheet.getRange(row, idx).setValue(list.filter(Boolean).join(','));
  sheet.getRange(row, headers.indexOf('Last Updated') + 1).setValue(nowDateTime_());
}

function refreshExecutiveScorecard_() {
  ensurePhase3Sheets_();
  var store = loadCrmStore_(true);
  var byExec = {};
  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    var ex = String(l.executive || 'Unassigned');
    if (!byExec[ex]) byExec[ex] = { leads: 0, bookings: 0, deliveries: 0, outstanding: 0, discountTotal: 0, bookingTotal: 0, actsToday: 0, followup: 0 };
    byExec[ex].leads++;
    if (String(l.bookingStatus || '').toLowerCase().indexOf('book') >= 0) byExec[ex].bookings++;
    if (String(l.currentStatus || '').toLowerCase() === 'delivered') byExec[ex].deliveries++;
    byExec[ex].outstanding += computeOutstanding_(id, store);
  });
  var today = nowDate_();
  store.activities.rows.forEach(function (r) {
    var leadId = String(rowVal_(r, store.activities.headers, 'Lead ID') || '').trim();
    var ex = String(rowVal_(r, store.activities.headers, 'Executive') || '');
    if (!byExec[ex]) byExec[ex] = { leads: 0, bookings: 0, deliveries: 0, outstanding: 0, discountTotal: 0, bookingTotal: 0, actsToday: 0, followup: 0 };
    if (formatDate_(rowVal_(r, store.activities.headers, 'Date')) === today) byExec[ex].actsToday++;
    if (leadId && store.leads.byId[leadId] && formatDate_(store.leads.byId[leadId].nextFollowUpDate) <= today) byExec[ex].followup++;
  });
  Object.keys(store.commercial.byLeadId || {}).forEach(function (leadId) {
    var c = store.commercial.byLeadId[leadId];
    var lead = store.leads.byId[leadId] || {};
    var ex = String(c.bookingExecutive || lead.executive || 'Unassigned');
    if (!byExec[ex]) byExec[ex] = { leads: 0, bookings: 0, deliveries: 0, outstanding: 0, discountTotal: 0, bookingTotal: 0, actsToday: 0, followup: 0 };
    byExec[ex].discountTotal += Number(c.totalDiscount || 0);
    byExec[ex].bookingTotal += Number(c.bookingAmount || 0);
  });
  var rows = Object.keys(byExec).sort().map(function (ex) {
    var d = byExec[ex];
    var conv = d.leads > 0 ? d.bookings / d.leads : 0;
    var avgDisc = d.bookings > 0 ? d.discountTotal / d.bookings : 0;
    var avgBook = d.bookings > 0 ? d.bookingTotal / d.bookings : 0;
    return [ex, d.leads, d.actsToday, d.followup, d.bookings, d.deliveries, round2_(d.outstanding), conv, round2_(avgDisc), round2_(avgBook), nowDateTime_()];
  });
  var sheet = getSheet_(CRM.SHEETS.EXECUTIVE_SCORECARD);
  var scoreCols = getPhase3TableConfig_('EXECUTIVE_SCORECARD', PHASE3_FALLBACKS_.EXECUTIVE_SCORECARD).COLS;
  sheet.getRange(2, 1, Math.max(sheet.getMaxRows() - 1, 1), scoreCols.length).clearContent();
  if (rows.length) sheet.getRange(2, 1, rows.length, rows[0].length).setValues(rows);
}

function refreshDealerDailyRegister_() {
  ensurePhase3Sheets_();
  var store = loadCrmStore_(true);
  var date = nowDate_();
  var leadsToday = 0;
  var bookingsToday = 0;
  var deliveriesToday = 0;
  var outstanding = 0;
  var byExecBookings = {};
  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    if (formatDate_(l.createdDate) === date) leadsToday++;
    if (formatDate_(l.bookingDate) === date) {
      bookingsToday++;
      var ex = String(l.executive || 'Unassigned');
      byExecBookings[ex] = (byExecBookings[ex] || 0) + 1;
    }
    outstanding += computeOutstanding_(id, store);
  });
  var paymentsToday = computePaymentsByMode_(store, date, date);
  Object.keys(store.deliveryByLead).forEach(function (id) {
    if (formatDate_(store.deliveryByLead[id].deliveryDate) === date) deliveriesToday++;
  });
  var topExec = topKey_(byExecBookings);
  var row = [
    date, leadsToday, bookingsToday, round2_(paymentsToday.total),
    round2_(paymentsToday.cash), round2_(paymentsToday.upi), round2_(paymentsToday.finance),
    round2_(paymentsToday.other), deliveriesToday, round2_(outstanding), topExec, nowDateTime_()
  ];
  var sheet = getSheet_(CRM.SHEETS.DEALER_DAILY_REGISTER);
  var target = findRowById_(sheet, 'Date', date);
  if (target < 0) target = Math.max(sheet.getLastRow() + 1, CRM.DEALER_DAILY_REGISTER.DATA_START);
  sheet.getRange(target, 1, 1, row.length).setValues([row]);
}
