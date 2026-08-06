/**
 * Delivery Tracker operations – mission-critical path decoupled from reporting.
 */

var DELIVERY_CHECKLIST_OPTIONS_ = ['Pending', 'Yes', 'No', 'Done'];

function findDeliverySheetRow_(sheet, leadId, headers) {
  leadId = String(leadId || '').trim();
  if (!leadId || !sheet) return -1;
  headers = headers || getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  var idCol = findHeaderIndex_(headers, 'Lead ID') + 1;
  if (idCol < 1) idCol = 1;
  var lastRow = sheet.getLastRow();
  if (lastRow < CRM.DELIVERY.DATA_START) return -1;
  var vals = sheet.getRange(CRM.DELIVERY.DATA_START, idCol, lastRow - CRM.DELIVERY.DATA_START + 1, 1).getValues();
  for (var i = 0; i < vals.length; i++) {
    if (String(vals[i][0] || '').trim() === leadId) return CRM.DELIVERY.DATA_START + i;
  }
  return -1;
}

function ensureDeliverySchema_() {
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!sheet) return;
  var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  var required = CRM.DELIVERY.COLS || [];
  var missing = required.filter(function (c) { return findHeaderIndex_(headers, c) < 0; });
  if (missing.length) {
    var startCol = Math.max(headers.length, 0) + 1;
    missing.forEach(function (col, i) {
      sheet.getRange(CRM.DELIVERY.HEADER_ROW, startCol + i).setValue(col).setFontWeight('bold');
    });
  }
  // Number Plate / Insurer / Invoice Number must NEVER be Yes/No validated.
  headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  ['Number Plate', 'Insurer Name', 'Invoice Number', 'Chassis Number', 'Feedback', 'Customer Name', 'Delivery ID'].forEach(function (name) {
    var col = findHeaderIndex_(headers, name) + 1;
    if (col > 0) {
      var lastRow = Math.max(sheet.getLastRow(), CRM.DELIVERY.DATA_START + 500);
      sheet.getRange(CRM.DELIVERY.DATA_START, col, lastRow - CRM.DELIVERY.DATA_START + 1, 1).clearDataValidations();
    }
  });
}

function readDeliveryRowByLeadId_(leadId) {
  leadId = String(leadId || '').trim();
  ensureDeliverySchema_();
  ensureDeliveryRow_(leadId);
  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
  if (!sheet) return null;
  var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  var row = findDeliverySheetRow_(sheet, leadId, headers);
  if (row < 0) return null;
  var data = sheet.getRange(row, 1, 1, sheet.getLastColumn()).getValues()[0];
  function val(name) {
    var idx = findHeaderIndex_(headers, name);
    return idx >= 0 ? data[idx] : '';
  }
  return {
    leadId: leadId,
    customerName: String(val('Customer Name') || ''),
    insurance: String(val('Insurance') || ''),
    insurerName: String(val('Insurer Name') || ''),
    registration: String(val('Registration') || ''),
    invoice: String(val('Invoice') || ''),
    invoiceNumber: String(val('Invoice Number') || ''),
    chassisNumber: String(val('Chassis Number') || ''),
    accessories: String(val('Accessories') || ''),
    rc: String(val('RC') || ''),
    numberPlate: String(val('Number Plate') || ''),
    pdi: String(val('PDI') || ''),
    delivered: String(val('Delivered') || ''),
    deliveryDate: formatDate_(val('Delivery Date')) || '',
    feedback: String(val('Feedback') || ''),
    deliveryId: String(val('Delivery ID') || '')
  };
}

function writeDeliveryRowFields_(sheet, row, headers, fields) {
  var map = {
    'Insurance': fields.insurance,
    'Insurer Name': fields.insurerName,
    'Registration': fields.registration,
    'Invoice': fields.invoice,
    'Invoice Number': fields.invoiceNumber,
    'Chassis Number': fields.chassisNumber,
    'Accessories': fields.accessories,
    'RC': fields.rc || 'Pending',
    'Number Plate': fields.numberPlate || '',
    'PDI': fields.pdi,
    'Delivery Date': formatDate_(fields.deliveryDate) || nowDate_(),
    'Feedback': fields.feedback || ''
  };
  Object.keys(map).forEach(function (name) {
    if (map[name] === undefined) return;
    var col = findHeaderIndex_(headers, name) + 1;
    if (col < 1) return;
    // Free-text columns: clear validation before write (fixes H2 Yes/No error).
    if (name === 'Number Plate' || name === 'Insurer Name' || name === 'Invoice Number' ||
        name === 'Chassis Number' || name === 'Feedback') {
      sheet.getRange(row, col).clearDataValidations();
    }
    sheet.getRange(row, col).setValue(map[name]);
  });
  var nameCol = findHeaderIndex_(headers, 'Customer Name') + 1;
  if (nameCol > 0 && fields.customerName) {
    sheet.getRange(row, nameCol).setValue(fields.customerName);
  }
}

function isYesOrDone_(v) {
  var s = String(v || '').trim().toLowerCase();
  return s === 'yes' || s === 'done';
}

/**
 * Delivery rules:
 * - Insurance Yes + insurer name (mandatory)
 * - Registration Yes (mandatory)
 * - Invoice Yes + invoice number (mandatory)
 * - Chassis Number (mandatory)
 * - PDI must be Yes
 * - RC + Number Plate captured at Close Lead (not at delivery)
 */
function validateDeliveryReady_(fields) {
  if (!isYesOrDone_(fields.insurance)) {
    throw fieldError_('Insurance', 'Set Insurance to Yes before marking delivered.', 'VALIDATION');
  }
  if (!String(fields.insurerName || '').trim()) {
    throw fieldError_('Insurer Name', 'Enter the insurer name before delivery.', 'VALIDATION');
  }
  if (!isYesOrDone_(fields.registration)) {
    throw fieldError_('Registration', 'Set Registration to Yes before marking delivered.', 'VALIDATION');
  }
  if (!isYesOrDone_(fields.invoice)) {
    throw fieldError_('Invoice', 'Set Invoice to Yes before marking delivered.', 'VALIDATION');
  }
  if (!String(fields.invoiceNumber || '').trim()) {
    throw fieldError_('Invoice Number', 'Enter the invoice number before delivery.', 'VALIDATION');
  }
  if (!String(fields.chassisNumber || '').trim()) {
    throw fieldError_('Chassis Number', 'Enter the chassis number before delivery.', 'VALIDATION');
  }
  if (!isYesOrDone_(fields.pdi)) {
    throw fieldError_('PDI', 'Set PDI to Yes before marking delivered.', 'VALIDATION');
  }
}

/** RC + Number Plate mandatory when closing a lead account. */
function validateCloseLeadRcFields_(fields) {
  fields = fields || {};
  if (!isYesOrDone_(fields.rc)) {
    throw fieldError_('RC', 'Set RC to Yes or Done before closing the lead.', 'VALIDATION');
  }
  if (!String(fields.numberPlate || '').trim()) {
    throw fieldError_('Number Plate', 'Enter the number plate before closing the lead.', 'VALIDATION');
  }
}

/** PUBLIC — load RC / Number Plate for Close Lead dialog. */
function getCloseLeadContextForDialog(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead ID is required', errorCode: 'VALIDATION' };
    requireActiveLead_(leadId);
    var rc = 'Pending';
    var numberPlate = '';
    try {
      var delivery = readDeliveryRowByLeadId_(leadId);
      if (delivery) {
        if (delivery.rc) rc = delivery.rc;
        if (delivery.numberPlate) numberPlate = delivery.numberPlate;
      }
    } catch (eDel) {
      Logger.log('getCloseLeadContextForDialog delivery: ' + eDel.message);
    }
    var found = findLeadById_(leadId);
    if (found && found.row) {
      var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
      var headers = found.headers || getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
      var rowData = sheet.getRange(found.row, 1, 1, sheet.getLastColumn()).getValues()[0];
      var regRc = String(rowVal_(rowData, headers, 'RC Status') || '').trim();
      var regPlate = String(rowVal_(rowData, headers, 'Number Plate') || '').trim();
      if (regRc) rc = regRc;
      if (regPlate) numberPlate = regPlate;
    }
    var outstanding = 0;
    try {
      outstanding = typeof computeOutstanding_ === 'function'
        ? Number(computeOutstanding_(leadId, loadCrmStore_()) || 0)
        : 0;
    } catch (osErr) {
      Logger.log('getCloseLeadContextForDialog outstanding: ' + osErr.message);
    }
    return { success: true, rc: rc, numberPlate: numberPlate, outstanding: outstanding };
  } catch (e) {
    return {
      success: false,
      message: (e && e.message) || String(e),
      errorCode: (e && e.errorCode) || 'ERROR'
    };
  }
}

/** PUBLIC — load existing Delivery Tracker row for Mark Delivered dialog. */
function getDeliveryContextForDialog(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead ID is required', errorCode: 'VALIDATION' };
    requireActiveLead_(leadId);
    ensureDeliverySchema_();
    ensureDeliveryRow_(leadId);
    var lead = getLeadFromRegisterLight_(leadId);
    var delivery = readDeliveryRowByLeadId_(leadId) || {};
    if (lead && !delivery.customerName) delivery.customerName = lead.customerName || '';
    // Prefer Delivery Tracker chassis; fall back to Lead Register if already saved.
    if (!delivery.chassisNumber) {
      try {
        var found = findLeadById_(leadId);
        if (found && found.row) {
          var lr = getSheet_(CRM.SHEETS.LEAD_REGISTER);
          var lh = found.headers || getHeaders_(lr, CRM.LEAD.HEADER_ROW);
          var rowData = lr.getRange(found.row, 1, 1, lr.getLastColumn()).getValues()[0];
          delivery.chassisNumber = String(rowVal_(rowData, lh, 'Chassis Number') || '').trim();
        }
      } catch (chErr) {}
    }
    var store = loadCrmStore_(true);
    var outstanding = computeOutstanding_(leadId, store);
    return {
      success: true,
      delivery: delivery,
      chassisNumber: delivery.chassisNumber || '',
      outstanding: outstanding,
      eligible: outstanding <= 0.01
    };
  } catch (e) {
    return {
      success: false,
      message: (e && e.message) || String(e),
      errorCode: (e && e.errorCode) || 'ERROR'
    };
  }
}

function markDelivered_(leadId, deliveryDate, feedback) {
  return markDeliveredFromData_({
    leadId: leadId,
    deliveryDate: deliveryDate,
    feedback: feedback
  });
}

function markDeliveredFromData_(data) {
  data = data || {};
  var leadId = String(data.leadId || '').trim();
  var postCtx = {
    module: 'Delivery',
    action: 'Marked Delivered',
    auditAction: 'MARK_DELIVERED',
    auditDetail: String(leadId),
    perfOp: 'delivery',
    sheets: [CRM.SHEETS.DELIVERY_TRACKER, CRM.SHEETS.LEAD_REGISTER],
    leadId: leadId
  };
  return runCriticalBusinessTransaction_({
    module: 'Delivery',
    action: 'markDeliveredFromData_',
    successMessage: 'Delivery recorded successfully',
    context: postCtx,
    commitFn: function (setStep) {
      var lock = LockService.getDocumentLock();
      var locked = false;
      try {
        setStep('lock');
        locked = lock.tryLock(10000);
        if (!locked) throw businessError_('Delivery update is busy. Please retry.', 'LOCK_BUSY');

        setStep('validate');
        if (!leadId) throw fieldError_('Lead ID', 'Select a lead before marking delivered.', 'VALIDATION');
        requireActiveLead_(leadId);
        ensureDeliverySchema_();
        ensureDeliveryRow_(leadId, { skipRelock: true });

        var store = loadCrmStore_(true);
        if (!isDeliveryEligible_(leadId, store)) {
          throw fieldError_('Outstanding Amount', 'Customer outstanding must be zero before delivery.', 'VALIDATION');
        }

        var fields = {
          insurance: data.insurance,
          insurerName: String(data.insurerName || '').trim(),
          registration: data.registration,
          invoice: data.invoice,
          invoiceNumber: String(data.invoiceNumber || '').trim(),
          chassisNumber: String(data.chassisNumber || data.chasisNumber || '').trim(),
          accessories: data.accessories || 'Pending',
          rc: 'Pending',
          numberPlate: '',
          pdi: data.pdi,
          deliveryDate: data.deliveryDate,
          feedback: data.feedback,
          customerName: (store.leads.byId[leadId] && store.leads.byId[leadId].customerName) || ''
        };
        validateDeliveryReady_(fields);

        setStep('write');
        var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
        if (!sheet) throw businessError_('Delivery Tracker not found', 'MISSING_SHEET');
        var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
        var row = findDeliverySheetRow_(sheet, leadId, headers);
        if (row < 0) throw businessError_('Delivery row not found for ' + leadId, 'NOT_FOUND');

        writeDeliveryRowFields_(sheet, row, headers, fields);

        var deliveryId = String(data.deliveryId || '').trim();
        if (!deliveryId) {
          var existingId = readDeliveryRowByLeadId_(leadId);
          deliveryId = (existingId && existingId.deliveryId) ? existingId.deliveryId : generateId_('delivery');
        }
        var delCol = findHeaderIndex_(headers, 'Delivered') + 1;
        var delIdCol = findHeaderIndex_(headers, 'Delivery ID') + 1;
        if (delCol > 0) sheet.getRange(row, delCol).setValue('Yes');
        if (delIdCol > 0) sheet.getRange(row, delIdCol).setValue(deliveryId);

        var delDate = formatDate_(fields.deliveryDate) || nowDate_();
        var customerOs = computeDashboardOutstanding_(leadId, store);
        var companyOs = computeCompanyOutstanding_(leadId, store);
        updateLeadRegisterFields_(leadId, {
          'Current Status': 'Delivered',
          'Delivery Status': 'Delivered',
          'Delivery Date': delDate,
          'Insurer Name': fields.insurerName,
          'Invoice Number': fields.invoiceNumber,
          'Chassis Number': fields.chassisNumber,
          'Insurance Status': fields.insurance,
          'Registration Status': fields.registration,
          'Invoice Status': fields.invoice,
          'RC Status': 'Pending',
          'PDI Status': fields.pdi,
          'Customer Outstanding': customerOs,
          'Company Outstanding': companyOs,
          'Final Outstanding': customerOs,
          'Outstanding Amount': customerOs,
          'Last Updated': nowDateTime_(),
          'Last Updated By': getUserEmail_()
        });

        upsertRelationshipIndex_({
          LeadID: leadId,
          DeliveryID: deliveryId,
          'Current Status': 'Delivered'
        });

        // COLD-PATH WORK MOVED OUT OF THE LOCK (this was the delivery-save
        // equivalent of the booking slowdown): incentive upsert, insurance upsert,
        // dealer-earnings upsert (which does loadCrmStore_(true) — a full workbook
        // rebuild), and the Finance Pending view rebuild all ran synchronously
        // inside the document lock, pushing delivery past the client timeout. They
        // are now queued for the deferred worker, which rebuilds earnings, claims,
        // insurance and views once, off the critical path. We stash what the worker
        // needs (insurer, dates) on the queue item.
        scheduleDeferredCrmSync_({
          leadId: leadId,
          reason: 'delivery',
          dashboard: true,
          deliveryDate: delDate,
          insurerName: fields.insurerName,
          insuranceStatus: fields.insurance
        });

        SpreadsheetApp.flush();
        return { leadId: leadId, deliveryId: deliveryId };
      } finally {
        if (locked) lock.releaseLock();
      }
    },
    postTasks: [
      POST_TX.INVALIDATE_STORE,
      POST_TX.AUDIT,
      POST_TX.TRANSACTION_OK,
      POST_TX.PERF
    ]
  });
}

function handleDeliveryTrackerEdit_(e) {
  if (!e || !e.range) return;
  var row = e.range.getRow();
  if (row < CRM.DELIVERY.DATA_START) return;
  var sheet = e.range.getSheet();
  var headers = getHeaders_(sheet, CRM.DELIVERY.HEADER_ROW);
  var colName = headers[e.range.getColumn() - 1] || CRM.DELIVERY.COLS[e.range.getColumn() - 1];
  var leadId = sheet.getRange(row, 1).getValue();

  if (colName === 'Delivered' && e.value === 'Yes' && leadId) {
    updateLeadRegisterFields_(leadId, {
      'Current Status': 'Delivered',
      'Delivery Status': 'Delivered',
      'Last Updated': nowDateTime_(),
      'Last Updated By': getUserEmail_()
    });
  }

  // Sync late RC / Number Plate / Chassis / Invoice updates back to Lead Register.
  if (leadId && (colName === 'Number Plate' || colName === 'RC' || colName === 'Insurer Name' ||
      colName === 'Invoice Number' || colName === 'Chassis Number')) {
    var map = {};
    if (colName === 'Number Plate') map['Number Plate'] = e.value;
    if (colName === 'RC') map['RC Status'] = e.value;
    if (colName === 'Insurer Name') map['Insurer Name'] = e.value;
    if (colName === 'Invoice Number') map['Invoice Number'] = e.value;
    if (colName === 'Chassis Number') map['Chassis Number'] = e.value;
    map['Last Updated'] = nowDateTime_();
    updateLeadRegisterFields_(leadId, map);
  }

  invalidateCrmStore_();
  queuePostTransaction_([POST_TX.SYNC_COMPUTED], { dashboard: true });
}

function getPendingDeliveries_(store) {
  store = store || loadCrmStore_();
  var count = 0;
  Object.keys(store.deliveryByLead).forEach(function (id) {
    if (store.deliveryByLead[id].delivered !== 'Yes') count++;
  });
  return count;
}

function deliveryChecklistOptionsHtml_() {
  return buildSelectOptionsHtml_(DELIVERY_CHECKLIST_OPTIONS_, true);
}
