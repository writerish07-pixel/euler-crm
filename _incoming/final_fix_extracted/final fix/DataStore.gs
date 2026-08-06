/**
 * DataStore – single in-memory CRM snapshot with O(1) indexes.
 * All services read through here; no row-by-row sheet scans.
 */

var CRM_STORE = null;

/**
 * @typedef {Object} CrmStore
 * @property {Object} leads - byId, byMobile, byName, rows, headers, sheetRow
 * @property {Array} activities
 * @property {Array} payments
 * @property {Array} deliveries
 * @property {Object} commercial - byLeadId, rows, headers
 * @property {Object} paymentsByLead - leadId → total paid
 * @property {Object} lastActivityByLead - leadId → latest date string
 * @property {Object} deliveryByLead - leadId → {delivered, deliveryDate}
 */

/** Load full CRM state; pass true to force refresh. */
function loadCrmStore_(force) {
  if (!force && CRM_STORE) return CRM_STORE;
  CRM_STORE = buildCrmStore_();
  return CRM_STORE;
}

function invalidateCrmStore_() {
  CRM_STORE = null;
}

function buildCrmStore_() {
  var leads = readSheetData_(CRM.SHEETS.LEAD_REGISTER, CRM.LEAD.HEADER_ROW, CRM.LEAD.DATA_START);
  var activities = readSheetData_(CRM.SHEETS.ACTIVITY_LOG, CRM.ACTIVITY.HEADER_ROW, CRM.ACTIVITY.DATA_START);
  var payments = readSheetData_(CRM.SHEETS.PAYMENT_LEDGER, CRM.PAYMENT.HEADER_ROW, CRM.PAYMENT.DATA_START);
  var deliveries = readSheetData_(CRM.SHEETS.DELIVERY_TRACKER, CRM.DELIVERY.HEADER_ROW, CRM.DELIVERY.DATA_START);
  var commercial = readCommercialSheetData_();

  var leadIdx = indexLeads_(leads);
  var paymentsByLead = sumPaymentsByLead_(payments.rows, payments.headers);
  var lastActivityByLead = lastActivityDates_(activities.rows, activities.headers);
  var deliveryByLead = indexDeliveries_(deliveries.rows, deliveries.headers);
  var commercialDataStart = (CRM.COMMERCIAL && CRM.COMMERCIAL.DATA_START) || 2;
  var commercialByLead = indexCommercialByLead_(commercial.rows, commercial.headers, commercialDataStart);

  return {
    leads: leadIdx,
    activities: activities,
    payments: payments,
    deliveries: deliveries,
    commercial: commercialByLead,
    paymentsByLead: paymentsByLead,
    lastActivityByLead: lastActivityByLead,
    deliveryByLead: deliveryByLead
  };
}

function indexCommercialByLead_(rows, headers, dataStart) {
  var byLeadId = {};
  var rank = {}; // leadId -> current chosen rank (Active beats non-Active; later beats earlier)
  rows.forEach(function (row, i) {
    var leadId = String(rowVal_(row, headers, 'Lead ID')).trim();
    if (!leadId) return;
    var status = String(rowVal_(row, headers, 'Snapshot Status') || 'Active').trim();
    // Prefer Active; among same status prefer the later row (latest version).
    var thisRank = (status.toLowerCase() === 'active' ? 2000000 : 0) + i;
    if (byLeadId[leadId] && rank[leadId] >= thisRank) return;
    rank[leadId] = thisRank;

    var full = {
      leadId: leadId,
      bookingId: String(rowVal_(row, headers, 'Booking ID') || ''),
      snapshotId: String(rowVal_(row, headers, 'Snapshot ID') || ''),
      snapshotStatus: status,
      bookingDate: formatDate_(rowVal_(row, headers, 'Booking Date')),
      priceListVersion: rowVal_(row, headers, 'Price List Version'),
      priceEffectiveDate: formatDate_(rowVal_(row, headers, 'Price Effective Date')),
      model: rowVal_(row, headers, 'Vehicle Model'),
      variant: rowVal_(row, headers, 'Variant'),
    batteryType: rowVal_(row, headers, 'Body Type') || rowVal_(row, headers, 'Battery Type'),
    bodyType: rowVal_(row, headers, 'Body Type') || rowVal_(row, headers, 'Battery Type'),
      bookingAmount: parseNumber_(rowVal_(row, headers, 'Booking Amount')),
      bookingExecutive: rowVal_(row, headers, 'Booking Executive'),
      bookingMode: rowVal_(row, headers, 'Booking Mode'),
      financeRequired: rowVal_(row, headers, 'Finance Required'),
      exchangeRequired: rowVal_(row, headers, 'Exchange Required'),
      exShowroom: parseNumber_(rowVal_(row, headers, 'Ex Showroom Price')),
      accessories: parseNumber_(rowVal_(row, headers, 'Accessories')),
      insurance: parseNumber_(rowVal_(row, headers, 'Insurance')),
      registrationRto: parseNumber_(rowVal_(row, headers, 'Registration / RTO')),
      fastag: parseNumber_(rowVal_(row, headers, 'Fastag')),
      handlingCharges: parseNumber_(rowVal_(row, headers, 'Handling Charges')),
      trc: parseNumber_(rowVal_(row, headers, 'TRC')),
      extendedWarranty: parseNumber_(rowVal_(row, headers, 'Extended Warranty')),
      rsaAmc: parseNumber_(rowVal_(row, headers, 'RSA / AMC')),
      otherCharges: parseNumber_(rowVal_(row, headers, 'Other Charges')),
      gstPercent: parseNumber_(rowVal_(row, headers, 'GST %')),
      tcsApplicable: rowVal_(row, headers, 'TCS Applicable'),
      tcs: parseNumber_(rowVal_(row, headers, 'TCS')),
      consumerDiscount: parseNumber_(rowVal_(row, headers, 'Consumer Discount')),
      exchangeBonus: parseNumber_(rowVal_(row, headers, 'Exchange Bonus')),
      loyaltyBonus: parseNumber_(rowVal_(row, headers, 'Loyalty Bonus')),
      referralBonus: parseNumber_(rowVal_(row, headers, 'Referral Bonus')),
      dsaDiscount: parseNumber_(rowVal_(row, headers, 'DSA Discount') || rowVal_(row, headers, 'DSA Bonus')),
      additionalDiscount: parseNumber_(rowVal_(row, headers, 'Additional Discount')),
      oemExtraSupportReceived: parseNumber_(rowVal_(row, headers, 'OEM Extra Support Received')),
      oemExtraSupportPassed: parseNumber_(rowVal_(row, headers, 'OEM Extra Support Passed To Customer')),
      oemExtraSupportRetained: parseNumber_(rowVal_(row, headers, 'OEM Extra Support Retained')),
      totalDiscount: parseNumber_(rowVal_(row, headers, 'Total Discount')),
      benefitMode: String(rowVal_(row, headers, 'Benefit Mode') || '').trim() || 'Full Benefit',
      customerBenefitPassed: parseNumber_(rowVal_(row, headers, 'Customer Benefit Passed')),
      benefitPassedBreakup: String(rowVal_(row, headers, 'Benefit Passed Breakup') || '').trim(),
      oldVehicleBrand: rowVal_(row, headers, 'Old Vehicle Brand'),
      oldVehicleModel: rowVal_(row, headers, 'Old Vehicle Model'),
      oldVehicleRegistration: rowVal_(row, headers, 'Registration Number'),
      evaluatedExchangeValue: parseNumber_(rowVal_(row, headers, 'Evaluated Value')),
      finalExchangeValue: parseNumber_(rowVal_(row, headers, 'Final Exchange Value')),
      financer: rowVal_(row, headers, 'Financer'),
      loanAmount: parseNumber_(rowVal_(row, headers, 'Loan Amount')),
      downPayment: parseNumber_(rowVal_(row, headers, 'Down Payment')),
      grossVehicleCost: parseNumber_(rowVal_(row, headers, 'Gross Vehicle Cost')),
      grossInvoiceAmount: parseNumber_(rowVal_(row, headers, 'Gross Invoice Amount')),
      netVehicleCost: parseNumber_(rowVal_(row, headers, 'Net Vehicle Cost')),
      customerPayable: parseNumber_(rowVal_(row, headers, 'Customer Payable')),
      dealerMarginGrossInclGst: parseNumber_(rowVal_(row, headers, 'Dealer Margin Gross (Incl GST)')),
      dealerMarginGst: parseNumber_(rowVal_(row, headers, 'Dealer Margin GST (5%)')),
      dealerMarginNetExGst: parseNumber_(rowVal_(row, headers, 'Dealer Margin Net (Ex GST)')),
      bookingLocked: String(rowVal_(row, headers, 'Booking Locked') || ''),
      bookingLockReason: rowVal_(row, headers, 'Lock Reason'),
      createdAt: rowVal_(row, headers, 'Created At')
    };
    // Keep stored OEM Extra Support as typed — never auto-wipe on read.
    full.oemExtraSupportReceived = Math.max(0, num_(full.oemExtraSupportReceived));
    full.oemExtraSupportPassed = Math.max(0, Math.min(num_(full.oemExtraSupportPassed), full.oemExtraSupportReceived));
    full.oemExtraSupportRetained = round2_(Math.max(0, full.oemExtraSupportReceived - full.oemExtraSupportPassed));
    byLeadId[leadId] = {
      leadId: leadId, bookingId: full.bookingId, snapshotId: full.snapshotId,
      snapshotStatus: status,
      bookingDate: full.bookingDate, model: full.model, variant: full.variant,
      bookingExecutive: full.bookingExecutive,
      bookingAmount: full.bookingAmount, totalDiscount: full.totalDiscount,
      finalExchangeValue: full.finalExchangeValue, grossVehicleCost: full.grossVehicleCost,
      grossInvoiceAmount: full.grossInvoiceAmount, netVehicleCost: full.netVehicleCost,
      customerPayable: full.customerPayable, tcs: full.tcs,
      consumerDiscount: full.consumerDiscount, exchangeBonus: full.exchangeBonus,
      loyaltyBonus: full.loyaltyBonus, referralBonus: full.referralBonus,
      dsaDiscount: full.dsaDiscount, additionalDiscount: full.additionalDiscount,
      oemExtraSupportReceived: full.oemExtraSupportReceived,
      oemExtraSupportPassed: full.oemExtraSupportPassed,
      oemExtraSupportRetained: full.oemExtraSupportRetained,
      benefitMode: full.benefitMode, customerBenefitPassed: full.customerBenefitPassed,
      bookingLocked: full.bookingLocked,
      full: full,
      sheetRow: (dataStart || 2) + i
    };
  });
  return { headers: headers, rows: rows, byLeadId: byLeadId, dataStart: dataStart || 2 };
}

/**
 * Batch-read sheet data.
 * @returns {{headers: string[], rows: Array[], numCols: number}}
 */
/** Read Commercial Snapshot – read-only; never creates sheets on critical path. */
/**
 * Read the active Commercial Snapshot for ONE lead directly from the sheet,
 * bypassing the whole-store cache. Used by the Dealer Earnings self-heal when the
 * cached store hasn't indexed a just-written snapshot yet. Returns the parsed
 * `full` object (same shape as store.commercial.byLeadId[lead].full) or null.
 */
function readCommercialSnapshotForLead_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return null;
  var data = readCommercialSheetData_();
  var dataStart = (CRM.COMMERCIAL && CRM.COMMERCIAL.DATA_START) || 2;
  var indexed = indexCommercialByLead_(data.rows, data.headers, dataStart);
  var entry = indexed.byLeadId ? indexed.byLeadId[leadId] : null;
  return entry ? (entry.full || entry) : null;
}

function readCommercialSheetData_() {
  if (!CRM.SHEETS.COMMERCIAL_SNAPSHOT || !CRM.COMMERCIAL) {
    return { headers: [], rows: [], numCols: 0, dataStart: 2 };
  }
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!sheet) {
    return { headers: [], rows: [], numCols: 0, dataStart: CRM.COMMERCIAL.DATA_START || 2 };
  }
  return readSheetData_(CRM.SHEETS.COMMERCIAL_SNAPSHOT, CRM.COMMERCIAL.HEADER_ROW, CRM.COMMERCIAL.DATA_START);
}

function readSheetData_(sheetName, headerRow, dataStart) {
  var sheet = getSheet_(sheetName);
  var headers = getHeaders_(sheet, headerRow);
  var lastRow = sheet.getLastRow();
  if (lastRow < dataStart || headers.length === 0) {
    return { headers: headers, rows: [], numCols: headers.length };
  }
  var numRows = lastRow - dataStart + 1;
  var numCols = headers.length;
  var rows = sheet.getRange(dataStart, 1, numRows, numCols).getValues();
  return { headers: headers, rows: rows, numCols: numCols, dataStart: dataStart };
}

function colIdx_(headers, name) {
  return headers.indexOf(name);
}

function rowVal_(row, headers, name) {
  var i = colIdx_(headers, name);
  if (i < 0 && typeof findHeaderIndex_ === 'function') i = findHeaderIndex_(headers, name);
  return i >= 0 ? row[i] : '';
}

function updateLeadRegisterFields_(leadId, fields) {
  leadId = String(leadId || '').trim();
  if (!leadId || !fields) return false;

  // Ensure commercial price columns exist BEFORE resolving headers.
  // Otherwise Ex Showroom / RTO / Insurance writes are silently skipped.
  try {
    if (typeof ensureLeadCommercialPriceColumns_ === 'function') {
      ensureLeadCommercialPriceColumns_();
    } else if (typeof ensureLeadSchema_ === 'function') {
      ensureLeadSchema_();
    }
  } catch (eSch) {}

  var store = loadCrmStore_();
  var row = store.leads && store.leads.sheetRow ? store.leads.sheetRow[leadId] : 0;
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  // Always use LIVE sheet headers (store cache may predate appended price columns).
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  if (!row) {
    var found = findLeadById_(leadId);
    if (!found) return false;
    row = found.row;
  }

  var cols = [];
  var missing = [];
  Object.keys(fields).forEach(function (name) {
    var col = findHeaderIndex_(headers, name) + 1;
    if (col > 0) cols.push({ col: col, val: fields[name] });
    else missing.push(name);
  });
  // Append any still-missing headers and retry those fields.
  if (missing.length) {
    missing.forEach(function (colName) {
      headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
      if (findHeaderIndex_(headers, colName) < 0) {
        sheet.getRange(CRM.LEAD.HEADER_ROW, headers.length + 1)
          .setValue(colName).setFontWeight('bold');
      }
    });
    headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
    missing.forEach(function (name) {
      var col = findHeaderIndex_(headers, name) + 1;
      if (col > 0) cols.push({ col: col, val: fields[name] });
    });
  }
  if (!cols.length) return true;
  var minCol = cols[0].col, maxCol = cols[0].col;
  cols.forEach(function (c) {
    if (c.col < minCol) minCol = c.col;
    if (c.col > maxCol) maxCol = c.col;
  });
  var width = maxCol - minCol + 1;
  var range = sheet.getRange(row, minCol, 1, width);
  var savedRules = null;
  try {
    try { savedRules = range.getDataValidations(); } catch (gv) { savedRules = null; }
    if (savedRules) { try { range.clearDataValidations(); } catch (cv) {} }
    var slice = range.getValues()[0];
    cols.forEach(function (c) { slice[c.col - minCol] = c.val; });
    range.setValues([slice]);
  } catch (batchErr) {
    cols.forEach(function (c) { setValueSafe_(sheet.getRange(row, c.col), c.val); });
  } finally {
    if (savedRules) { try { range.setDataValidations(savedRules); } catch (rv) {} }
  }
  return true;
}

/** Sync one lead's outstanding + audit columns after payment or commercial change. */
function syncLeadOutstandingForId_(leadId, store) {
  leadId = String(leadId || '').trim();
  if (!leadId) return false;
  store = store || loadCrmStore_(true);
  var outstanding = computeDashboardOutstanding_(leadId, store);
  return updateLeadRegisterFields_(leadId, {
    'Outstanding Amount': outstanding,
    'Last Updated': nowDateTime_(),
    'Last Updated By': getUserEmail_()
  });
}

function indexLeads_(leadData) {
  var h = leadData.headers;
  var byId = {};
  var byMobile = {};
  var byName = {};
  var sheetRow = {};

  leadData.rows.forEach(function (row, i) {
    var id = String(rowVal_(row, h, 'Lead ID')).trim();
    if (!id) return;
    var record = leadRecordFromRow_(row, h, CRM.LEAD.DATA_START + i);
    byId[id] = record;
    sheetRow[id] = CRM.LEAD.DATA_START + i;
    var mob = normalizeMobile_(record.mobile);
    if (mob && !byMobile[mob]) byMobile[mob] = record;
    var name = String(record.customerName || '').trim().toUpperCase();
    if (name && !byName[name]) byName[name] = record;
  });

  return {
    headers: h,
    rows: leadData.rows,
    byId: byId,
    byMobile: byMobile,
    byName: byName,
    sheetRow: sheetRow,
    dataStart: CRM.LEAD.DATA_START
  };
}

function leadRecordFromRow_(row, headers, sheetRowNum) {
  return {
    leadId: String(rowVal_(row, headers, 'Lead ID')).trim(),
    createdDate: formatDate_(rowVal_(row, headers, 'Created Date')),
    customerName: rowVal_(row, headers, 'Customer Name'),
    mobile: normalizeMobile_(rowVal_(row, headers, 'Mobile')),
    alternateMobile: normalizeMobile_(rowVal_(row, headers, 'Alternate Mobile')),
    village: rowVal_(row, headers, 'Village'),
    city: rowVal_(row, headers, 'City'),
    leadSource: rowVal_(row, headers, 'Lead Source'),
    interestedModel: rowVal_(row, headers, 'Interested Model'),
    variant: rowVal_(row, headers, 'Variant'),
    colour: rowVal_(row, headers, 'Colour'),
    executive: rowVal_(row, headers, 'Executive'),
    currentStatus: String(rowVal_(row, headers, 'Current Status') || ''),
    priority: rowVal_(row, headers, 'Priority'),
    budget: parseNumber_(rowVal_(row, headers, 'Budget')),
    bookingStatus: rowVal_(row, headers, 'Booking Status'),
    bookingDate: formatDate_(rowVal_(row, headers, 'Booking Date')),
    bookingAmount: parseNumber_(rowVal_(row, headers, 'Booking Amount')),
    financeRequired: rowVal_(row, headers, 'Finance Required'),
    exchangeRequired: rowVal_(row, headers, 'Exchange Required'),
    deliveryStatus: rowVal_(row, headers, 'Delivery Status'),
    deliveryDate: formatDate_(rowVal_(row, headers, 'Delivery Date')),
    financerName: rowVal_(row, headers, 'Financer Name'),
    financeFileNumber: rowVal_(row, headers, 'Finance File Number'),
    insurerName: rowVal_(row, headers, 'Insurer Name'),
    insuranceAmount: parseNumber_(rowVal_(row, headers, 'Insurance Amount')),
    nextFollowUpDate: formatDate_(rowVal_(row, headers, 'Next Follow-up Date')),
    accountStatus: normalizeAccountStatus_(rowVal_(row, headers, 'Account Status')),
    closedDate: formatDate_(rowVal_(row, headers, 'Closed Date')),
    closeReason: rowVal_(row, headers, 'Close Reason'),
    finalOutstanding: parseNumber_(rowVal_(row, headers, 'Final Outstanding')),
    // These columns exist on the Lead Register but were never parsed, so every
    // consumer that fell back to lead.customerPayable / lead.outstandingAmount
    // silently got 0 — which is why Scheme Update showed a blank Customer Payable
    // and Outstanding for a properly booked lead.
    customerPayable: parseNumber_(rowVal_(row, headers, 'Customer Payable')),
    outstandingAmount: parseNumber_(rowVal_(row, headers, 'Outstanding Amount')),
    grossVehicleCost: parseNumber_(rowVal_(row, headers, 'Gross Vehicle Cost')),
    closedBy: rowVal_(row, headers, 'Closed By'),
    closeTimestamp: rowVal_(row, headers, 'Close Timestamp'),
    remarks: rowVal_(row, headers, 'Remarks'),
    sheetRow: sheetRowNum
  };
}

function sumPaymentsByLead_(rows, headers) {
  var totals = {};
  rows.forEach(function (row) {
    var id = String(rowVal_(row, headers, 'Lead ID')).trim();
    if (!id) return;
    totals[id] = (totals[id] || 0) + parseNumber_(rowVal_(row, headers, 'Amount'));
  });
  return totals;
}

function lastActivityDates_(rows, headers) {
  var latest = {};
  rows.forEach(function (row) {
    var id = String(rowVal_(row, headers, 'Lead ID')).trim();
    var d = formatDate_(rowVal_(row, headers, 'Date'));
    if (!id || !d) return;
    if (!latest[id] || d > latest[id]) latest[id] = d;
  });
  return latest;
}

function indexDeliveries_(rows, headers) {
  var map = {};
  rows.forEach(function (row) {
    var id = String(rowVal_(row, headers, 'Lead ID')).trim();
    if (!id) return;
    map[id] = {
      delivered: String(rowVal_(row, headers, 'Delivered') || ''),
      deliveryDate: formatDate_(rowVal_(row, headers, 'Delivery Date'))
    };
  });
  return map;
}

/** Customer payable minus payments — strict for payments; use computeDashboardOutstanding_ for reports. */
function computeOutstanding_(leadId, store) {
  return computeLeadOutstanding_(leadId, store);
}

function getLeadDealAmount_(lead) {
  if (!lead) return 0;
  var leadId = String(lead.leadId || '').trim();
  if (!leadId) return lead.bookingAmount || lead.budget || 0;
  return getCommercialPayable_(leadId, loadCrmStore_());
}

function parseNumber_(v) {
  if (v === '' || v === null || v === undefined) return 0;
  var n = Number(String(v).replace(/[^\d.-]/g, ''));
  return isNaN(n) ? 0 : n;
}

/** O(1) lead lookup by ID. */
function getLead_(leadId) {
  var light = getLeadFromRegisterLight_(leadId);
  if (light) return light;
  var store = loadCrmStore_();
  return store.leads.byId[String(leadId).trim()] || null;
}

/** Fast single-lead read from Lead Register (no full CRM store). */
function getLeadFromRegisterLight_(leadId) {
  leadId = String(leadId || '').trim();
  if (!leadId) return null;
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    if (!sheet) return null;
    var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
    var idIdx = findHeaderIndex_(headers, 'Lead ID');
    if (idIdx < 0) return null;
    var lastRow = sheet.getLastRow();
    if (lastRow < CRM.LEAD.DATA_START) return null;
    var numRows = lastRow - CRM.LEAD.DATA_START + 1;
    var data = sheet.getRange(CRM.LEAD.DATA_START, 1, numRows, sheet.getLastColumn()).getValues();
    for (var i = 0; i < data.length; i++) {
      if (String(data[i][idIdx] || '').trim() === leadId) {
        return leadRecordFromRow_(data[i], headers, CRM.LEAD.DATA_START + i);
      }
    }
  } catch (e) {
    Logger.log('getLeadFromRegisterLight_: ' + e.message);
  }
  return null;
}

function findLeadById_(leadId) {
  var lead = getLead_(leadId);
  if (!lead) return null;
  return { row: lead.sheetRow, data: null, headers: loadCrmStore_().leads.headers, lead: lead };
}

function findLeadByMobile_(mobile) {
  mobile = normalizeMobile_(mobile);
  if (!mobile) return null;
  var light = findLeadByMobileLight_(mobile);
  if (light) return light;
  var store = loadCrmStore_();
  var lead = store.leads.byMobile[mobile];
  if (!lead) return null;
  return { row: lead.sheetRow, leadId: lead.leadId, customerName: lead.customerName, mobile: mobile };
}

/** Lightweight duplicate check – Mobile column only, no full store load. */
function findLeadByMobileLight_(mobile) {
  mobile = normalizeMobile_(mobile);
  if (!mobile) return null;
  try {
    var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.LEAD_REGISTER);
    if (!sheet) return null;
    var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
    var mobIdx = findHeaderIndex_(headers, 'Mobile');
    var idIdx = findHeaderIndex_(headers, 'Lead ID');
    var nameIdx = findHeaderIndex_(headers, 'Customer Name');
    if (mobIdx < 0) return null;
    var lastRow = sheet.getLastRow();
    if (lastRow < CRM.LEAD.DATA_START) return null;
    var numRows = lastRow - CRM.LEAD.DATA_START + 1;
    var mobVals = sheet.getRange(CRM.LEAD.DATA_START, mobIdx + 1, numRows, 1).getValues();
    for (var i = 0; i < mobVals.length; i++) {
      if (normalizeMobile_(mobVals[i][0]) !== mobile) continue;
      var row = CRM.LEAD.DATA_START + i;
      return {
        row: row,
        leadId: idIdx >= 0 ? String(sheet.getRange(row, idIdx + 1).getValue() || '').trim() : '',
        customerName: nameIdx >= 0 ? sheet.getRange(row, nameIdx + 1).getValue() : '',
        mobile: mobile
      };
    }
  } catch (e) {
    Logger.log('findLeadByMobileLight_: ' + e.message);
  }
  return null;
}

function searchLeads_(query, includeClosed) {
  var searchStart = Date.now();
  query = String(query || '').trim().toUpperCase();
  if (!query) return [];
  var store = loadCrmStore_();
  var results = [];
  var normQuery = normalizeMobile_(query);
  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    if (!includeClosed && !isActiveLead_(l)) return;
    if (includeClosed && normalizeAccountStatus_(l.accountStatus) === ACCOUNT_STATUS.ARCHIVED) return;
    var match = id.toUpperCase().indexOf(query) >= 0 ||
      String(l.customerName).toUpperCase().indexOf(query) >= 0 ||
      (normQuery && (l.mobile === normQuery || l.alternateMobile === normQuery)) ||
      String(l.mobile).indexOf(query) >= 0 ||
      String(l.alternateMobile).indexOf(query) >= 0;
    if (match) {
      results.push({
        leadId: id, customerName: l.customerName, mobile: l.mobile,
        accountStatus: l.accountStatus, row: l.sheetRow
      });
    }
  });
  recordPerf_('search', Date.now() - searchStart);
  return results.slice(0, 25);
}

function batchGetLeadData_() {
  var store = loadCrmStore_();
  return { headers: store.leads.headers, rows: store.leads.rows };
}
