/**

 * Lead Register operations – mission-critical path decoupled from reporting.

 */



function createNewLead_(data) {
  var start = Date.now();
  var leadId = '';
  try {
    if (!data || !String(data.customerName || '').trim()) {
      throw fieldError_('Customer Name', 'Enter the customer name.', 'VALIDATION');
    }
    var mobile = normalizeMobile_(data.mobile);
    if (!mobile || !isValidMobile_(mobile)) {
      throw fieldError_('Mobile', 'Enter a valid 10-digit mobile number.', 'VALIDATION');
    }
    var existing = findLeadByMobileLight_(mobile);
    if (existing) {
      throw fieldError_('Mobile', 'Already used by lead ' + existing.leadId + ' (' + existing.customerName + ').', 'DUPLICATE');
    }

    leadId = generateId_('lead');
    data.mobile = mobile;
    data.createdDate = formatDate_(data.createdDate) || nowDate_();

    var leadSheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
    var leadRow = buildLeadRow_(leadId, data, { source: 'Form' });
    var newLeadRow = Math.max(leadSheet.getLastRow() + 1, CRM.LEAD.DATA_START);
    writeSheetRow_(leadSheet, newLeadRow, leadRow);

    var activityId = appendLeadCreateActivity_(leadId, data);
    SpreadsheetApp.flush();
    invalidateCrmStore_();

    // Return success to the dialog immediately. Full sync + dashboard refresh
    // often exceeds google.script.run client timeout (~30–45s) even when the
    // lead row is already saved — which caused false "Server timeout" alerts.
    var indexEntry = {
      LeadID: leadId,
      CustomerName: data.customerName || '',
      Mobile: data.mobile || '',
      LatestActivityID: activityId,
      'Current Status': 'New'
    };
    try {
      upsertRelationshipIndex_(indexEntry);
    } catch (idxErr) {
      Logger.log('createNewLead_ index: ' + idxErr.message);
    }
    runLeadCreateBackgroundTasks_(leadId, {
      customerName: data.customerName,
      mobile: data.mobile,
      activityId: activityId
    });

    return crmOk_('Lead created successfully', { leadId: leadId }, Date.now() - start, {
      module: 'Lead',
      function: 'createNewLead_'
    });
  } catch (err) {
    return crmFailStructured_('Lead', 'createNewLead_', 'commit', err, Date.now() - start);
  }
}

function appendLeadCreateActivity_(leadId, data) {
  var sheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  var now = new Date();
  var activityId = generateId_('activity');
  var activityType = normalizeActivityTypeForWrite_('Lead Created', { allowFallback: true, fallbackType: 'Note' });
  var activityDate = formatDate_(data.createdDate) || formatDate_(now);
  var row = [
    activityId,
    leadId,
    activityDate,
    formatTime_(now),
    activityType,
    'Lead created from CRM form',
    '',
    '',
    data.executive || '',
    data.customerName || '',
    data.mobile || '',
    data.interestedModel || ''
  ];
  var newRow = Math.max(sheet.getLastRow() + 1, CRM.ACTIVITY.DATA_START);
  writeSheetRow_(sheet, newRow, row);
  return activityId;
}

function runLeadCreateBackgroundTasks_(leadId, meta) {
  scheduleDeferredCrmSync_({
    leadId: leadId,
    dashboard: true,
    reason: 'lead_create',
    runEstimate: true,
    indexEntry: {
      LeadID: leadId,
      CustomerName: (meta && meta.customerName) || '',
      Mobile: (meta && meta.mobile) || '',
      LatestActivityID: (meta && meta.activityId) || '',
      'Current Status': 'New'
    }
  });
}



function buildLeadRow_(leadId, data, meta) {

  meta = meta || {};

  return CRM.LEAD.COLS.map(function (h) {

    switch (h) {

      case 'Lead ID': return leadId;

      case 'Created Date': return data.createdDate || nowDate_();

      case 'Customer Name': return data.customerName || '';

      case 'Mobile': return normalizeMobile_(data.mobile) || '';

      case 'Alternate Mobile': return normalizeMobile_(data.alternateMobile) || '';

      case 'Village': return data.village || '';

      case 'City': return data.city || '';

      case 'Lead Source': return data.leadSource || 'Walk-in';

      case 'Interested Model': return data.interestedModel || '';

      case 'Variant': return data.variant || '';

      case 'Colour': return data.colour || '';

      case 'Executive': return data.executive || '';

      case 'Current Status': return data.currentStatus || 'New';

      case 'Priority': return data.priority || 'Normal';

      case 'Budget': return data.budget || '';

      case 'Booking Status': return data.bookingStatus || '';

      case 'Booking Date': return data.bookingDate || '';

      case 'Booking Amount': return data.bookingAmount || '';

      case 'Finance Required': return data.financeRequired || '';

      case 'Exchange Required': return data.exchangeRequired || '';

      case 'Remarks': return data.remarks || '';

      case 'Account Status': return data.accountStatus || ACCOUNT_STATUS.ACTIVE;

      case 'Closed Date': return data.closedDate || '';

      case 'Close Reason': return data.closeReason || '';

      case 'Final Outstanding': return data.finalOutstanding !== undefined ? data.finalOutstanding : '';

      case 'Closed By': return data.closedBy || '';

      case 'Close Timestamp': return data.closeTimestamp || '';

      case 'Last Updated': return nowDateTime_();

      case 'Last Updated By': return meta.source || getUserEmail_();

      default: return '';

    }

  });

}



function handleLeadRegisterEdit_(e) {

  if (!e || !e.range) return;

  var row = e.range.getRow();

  if (row < CRM.LEAD.DATA_START) return;



  var sheet = e.range.getSheet();

  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);

  var col = e.range.getColumn();

  var colName = headers[col - 1];

  var leadIdCol = headers.indexOf('Lead ID') + 1;

  var leadIdAtRow = String(sheet.getRange(row, leadIdCol).getValue() || '').trim();

  // Outstanding is system-calculated only — never manually editable.
  var outstandingLocked = [
    'Outstanding Amount', 'Customer Outstanding', 'Final Outstanding', 'Company Outstanding'
  ];
  if (outstandingLocked.indexOf(colName) >= 0) {
    if (e.oldValue !== undefined) {
      sheet.getRange(row, col).setValue(e.oldValue);
    } else {
      sheet.getRange(row, col).setValue('');
    }
    try {
      SpreadsheetApp.getUi().alert(
        'Outstanding is Read Only',
        'Outstanding is system-calculated (Customer Payable − Payments Received).\n\n' +
        'It cannot be edited manually by any role. Update payments or commercial terms instead.',
        SpreadsheetApp.getUi().ButtonSet.OK
      );
    } catch (uiErr) {}
    return;
  }



  if (leadIdAtRow && ['Interested Model', 'Variant', 'Booking Date', 'Booking Amount', 'Finance Required', 'Exchange Required'].indexOf(colName) >= 0) {

    var storeBefore = loadCrmStore_();

    var snap = storeBefore.commercial && storeBefore.commercial.byLeadId ? storeBefore.commercial.byLeadId[leadIdAtRow] : null;

    if (snap && String(snap.bookingLocked || '').toLowerCase() === 'yes') {
      if (e.oldValue !== undefined) {

        sheet.getRange(row, col).setValue(e.oldValue);

      } else {

        sheet.getRange(row, col).setValue('');

      }
      SpreadsheetApp.getUi().alert(

        'Booking Locked',

        'Commercial snapshot is locked for this booking. Owner override with reason is required.',

        SpreadsheetApp.getUi().ButtonSet.OK

      );

      return;

    }

  }



  if (colName === 'Mobile') {

    var mobile = normalizeMobile_(e.value);

    if (mobile && !isValidMobile_(mobile)) {

      showToast_('Mobile: Enter a valid 10-digit number.');

      return;

    }

    if (mobile) {

      invalidateCrmStore_();

      var existing = findLeadByMobileLight_(mobile) || findLeadByMobile_(mobile);

      if (existing && existing.row !== row) {

        var ui = SpreadsheetApp.getUi();

        var resp = ui.alert(

          'Duplicate Mobile Detected',

          'Mobile ' + mobile + ' already exists:\nLead ID: ' + existing.leadId + '\nCustomer: ' + existing.customerName,

          ui.ButtonSet.YES_NO

        );

        if (resp === ui.Button.YES) {
          sheet.getRange(row, col).clearContent();
          goToLead_(existing.leadId);

        }

      }

    }

  }



  if (colName === 'Lead ID' && !e.value) {
    var leadId = generateId_('lead');

    sheet.getRange(row, col).setValue(leadId);

    sheet.getRange(row, headers.indexOf('Created Date') + 1).setValue(nowDate_());

    ensureDeliveryRow_(leadId);
  }
  sheet.getRange(row, headers.indexOf('Last Updated') + 1).setValue(nowDateTime_());

  sheet.getRange(row, headers.indexOf('Last Updated By') + 1).setValue(getUserEmail_());
  invalidateCrmStore_();

  queuePostTransaction_([POST_TX.SYNC_COMPUTED], { dashboard: true });

  if (leadIdAtRow) {

    queuePostTransaction_([POST_TX.SYNC_COMPUTED], { leadId: leadIdAtRow, dashboard: true });

  }

}



function goToLead_(leadId) {
  if (typeof navGoToLead === 'function') {
    navGoToLead(leadId);
    return;
  }
  var found = findLeadById_(leadId);
  if (!found) { showAlert_('Lead not found: ' + leadId); return; }
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  sheet.activate();
  sheet.setActiveRange(sheet.getRange(found.row, 1));
}



function ensureDeliveryRow_(leadId, opts) {

  opts = opts || {};

  var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);

  if (!sheet) return;

  var data = sheet.getDataRange().getValues();

  for (var i = 1; i < data.length; i++) {

    if (data[i][0] === leadId) return;

  }

  var newRow = Math.max(sheet.getLastRow() + 1, CRM.DELIVERY.DATA_START);
  try {
    var lead = getLeadFromRegisterLight_(leadId);
    var row = [];
    CRM.DELIVERY.COLS.forEach(function (col) {
      if (col === 'Lead ID') row.push(leadId);
      else if (col === 'Customer Name') row.push(lead ? lead.customerName : '');
      else row.push('');
    });
    writeSheetRow_(sheet, newRow, row);
  } catch (e) {
    throw businessError_('Cannot write Delivery row: ' + e.message, 'WRITE_ERROR');
  }

}



/**

 * Import leads with dedup by mobile. Returns count + ID remap for dependents.

 * ROOT FIX: seenMobile stores leadId, not boolean.

 */

function batchImportLeads_(leads) {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);

  var rows = [];

  var deliveryRows = [];

  var seenMobile = {};

  var seenId = {};

  var leadIdRemap = {};

  var store = loadCrmStore_(true);



  leads.forEach(function (lead) {

    lead = sanitizeLeadForImport_(lead);

    lead.mobile = normalizeMobile_(lead.mobile);

    lead.accountStatus = lead.accountStatus || ACCOUNT_STATUS.ACTIVE;

    if (store.leads.byId[lead.leadId]) return;

    if (seenId[lead.leadId]) return;

    var existingByMobile = lead.mobile ? store.leads.byMobile[lead.mobile] : null;

    if (existingByMobile) {

      leadIdRemap[lead.leadId] = existingByMobile.leadId;

      return;

    }

    if (lead.mobile && seenMobile[lead.mobile]) {

      leadIdRemap[lead.leadId] = seenMobile[lead.mobile];

      return;

    }

    seenId[lead.leadId] = true;

    if (lead.mobile) seenMobile[lead.mobile] = lead.leadId;

    rows.push(buildLeadRow_(lead.leadId, lead, { source: 'Import' }));

    deliveryRows.push([lead.leadId]);

  });



  if (rows.length === 0) return { count: 0, remap: leadIdRemap };



  writeBatchData_(sheet, CRM.LEAD.DATA_START, rows);

  writeBatchData_(getSheet_(CRM.SHEETS.DELIVERY_TRACKER), CRM.DELIVERY.DATA_START, deliveryRows);
  invalidateCrmStore_();

  return { count: rows.length, remap: leadIdRemap };

}



function prepareLeadImport_(leads) {

  var seenMobile = {};

  var seenId = {};

  var remap = {};

  var filtered = [];

  var store = loadCrmStore_(true);

  leads.forEach(function (lead) {

    lead = sanitizeLeadForImport_(lead);

    lead.mobile = normalizeMobile_(lead.mobile);

    lead.accountStatus = lead.accountStatus || ACCOUNT_STATUS.ACTIVE;

    if (store.leads.byId[lead.leadId]) return;

    if (seenId[lead.leadId]) return;

    var existingByMobile = lead.mobile ? store.leads.byMobile[lead.mobile] : null;

    if (existingByMobile) {

      remap[lead.leadId] = existingByMobile.leadId;

      return;

    }

    if (lead.mobile && seenMobile[lead.mobile]) {

      remap[lead.leadId] = seenMobile[lead.mobile];

      return;

    }

    seenId[lead.leadId] = true;

    if (lead.mobile) seenMobile[lead.mobile] = lead.leadId;

    filtered.push(lead);

  });

  return { leads: filtered, remap: remap };

}



function writeBatchData_(sheet, startRow, values) {

  if (!values || values.length === 0) return;

  var numRows = values.length;

  var numCols = values[0].length;

  var targetRow = Math.max(sheet.getLastRow() + 1, startRow);

  sheet.getRange(targetRow, 1, numRows, numCols).setValues(values);

}



/** Add Account Status columns to existing Lead Register if missing. */

function ensureLeadSchema_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var required = (CRM.LEAD.COLS || []).slice();
  // Always ensure close + single-truth commercial columns exist.
  [
    'Account Status', 'Closed Date', 'Close Reason',
    'Final Outstanding', 'Closed By', 'Close Timestamp',
    'Ex Showroom', 'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges',
    'TRC', 'Fastag', 'Extended Warranty', 'Other Charges', 'Gross Vehicle Cost', 'Customer Payable',
    'Financer Name', 'Finance File Number', 'Last Payment Mode', 'Total Received',
    'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Bonus', 'Additional Discount',
    'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount',
    'Customer Outstanding', 'Company Outstanding',
    'Insurer Name', 'Invoice Number', 'Chassis Number', 'Number Plate',
    'Insurance Status', 'Registration Status', 'Invoice Status', 'RC Status', 'PDI Status',
    'Dealer Earnings'
  ].forEach(function (c) {
    if (required.indexOf(c) < 0) required.push(c);
  });

  var missing = required.filter(function (c) { return findHeaderIndex_(headers, c) < 0; });
  if (missing.length > 0) {
    var startCol = headers.length + 1;
    missing.forEach(function (col, i) {
      sheet.getRange(CRM.LEAD.HEADER_ROW, startCol + i).setValue(col).setFontWeight('bold');
    });
    headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  }

  var acctCol = findHeaderIndex_(headers, 'Account Status') + 1;
  if (acctCol > 0) {
    var lastRow = sheet.getLastRow();
    if (lastRow >= CRM.LEAD.DATA_START) {
      var numRows = lastRow - CRM.LEAD.DATA_START + 1;
      var range = sheet.getRange(CRM.LEAD.DATA_START, acctCol, numRows, 1);
      var vals = range.getValues();
      var changed = false;
      for (var i = 0; i < vals.length; i++) {
        if (!vals[i][0]) { vals[i][0] = ACCOUNT_STATUS.ACTIVE; changed = true; }
      }
      if (changed) range.setValues(vals);
    }
  }
  invalidateCrmStore_();
}

/** Fast ensure of price columns used by Edit Lead / Price Structure / sync. */
function ensureLeadCommercialPriceColumns_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  if (!sheet) return;
  var needed = [
    'Ex Showroom', 'RTO', 'Insurance Amount', 'Accessories Amount', 'Handling Charges',
    'TRC', 'Fastag', 'Extended Warranty', 'Other Charges', 'Gross Vehicle Cost', 'Customer Payable',
    'Consumer Discount', 'Exchange Bonus', 'Loyalty Bonus', 'Referral Bonus', 'DSA Bonus',
    'Additional Discount', 'Total Discount', 'OEM Scheme Amount', 'Dealer Scheme Amount',
    'Customer Outstanding', 'Company Outstanding', 'Total Received', 'Outstanding Amount'
  ];
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var added = false;
  needed.forEach(function (name) {
    headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
    if (findHeaderIndex_(headers, name) < 0) {
      sheet.getRange(CRM.LEAD.HEADER_ROW, headers.length + 1).setValue(name).setFontWeight('bold');
      added = true;
    }
  });
  if (added) {
    try { invalidateCrmStore_(); } catch (e) {}
  }
}



function setLeadField_(sheet, row, headers, fieldName, value) {

  var col = headers.indexOf(fieldName) + 1;

  // setValueSafe_ bypasses 'Reject input' data validation on computed Lead Register columns.
  if (col > 0) setValueSafe_(sheet.getRange(row, col), value);

}



/** Close a lead – accounts team only via CRM menu. */

function closeLead_(data) {

  assertOperational_('write');

  var auditDetail = '';

  return runCriticalBusinessTransaction_({

    module: 'Lead',

    action: 'closeLead_',

    successMessage: 'Lead closed successfully',

    commitFn: function (setStep) {

      var lock = LockService.getDocumentLock();

      var locked = false;

      var leadId = '';

      try {

        setStep('lock');

        locked = lock.tryLock(10000);

        if (!locked) throw businessError_('Close lead is busy. Please retry.', 'LOCK_BUSY');



        leadId = String(data.leadId || '').trim();

        if (!leadId) throw fieldError_('Lead ID', 'Select a lead before closing.', 'VALIDATION');

        if (!data.reason) throw fieldError_('Close Reason', 'Select why this lead is being closed.', 'VALIDATION');

        if (!data.closeDate) throw fieldError_('Closing Date', 'Select the closing date.', 'VALIDATION');

        var rc = String(data.rc || '').trim();
        var numberPlate = String(data.numberPlate || '').trim();
        if (typeof validateCloseLeadRcFields_ === 'function') {
          validateCloseLeadRcFields_({ rc: rc, numberPlate: numberPlate });
        }



        setStep('validate');

        var found = findLeadById_(leadId);

        if (!found) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');

        var lead = found.lead;

        if (normalizeAccountStatus_(lead.accountStatus) === ACCOUNT_STATUS.CLOSED) {

          throw businessError_('Lead is already closed: ' + leadId, 'ALREADY_CLOSED');

        }



        setStep('write');
        var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);

        var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);

        var row = found.row;

        // Final Outstanding is always system-calculated — never accept manual input.
        var finalOut = computeOutstanding_(leadId, loadCrmStore_());

        if (isNaN(finalOut) || !isFinite(finalOut)) {

          throw fieldError_('Final Outstanding', 'Could not calculate outstanding for this lead.', 'VALIDATION');

        }



        setLeadField_(sheet, row, headers, 'Account Status', ACCOUNT_STATUS.CLOSED);

        setLeadField_(sheet, row, headers, 'Closed Date', formatDate_(data.closeDate));

        setLeadField_(sheet, row, headers, 'Close Reason', data.reason);

        setLeadField_(sheet, row, headers, 'Final Outstanding', finalOut);

        setLeadField_(sheet, row, headers, 'Number Plate', numberPlate);

        setLeadField_(sheet, row, headers, 'RC Status', rc);

        setLeadField_(sheet, row, headers, 'Closed By', getUserEmail_());

        setLeadField_(sheet, row, headers, 'Close Timestamp', nowDateTime_());

        if (data.remarks) {

          var remarksCol = headers.indexOf('Remarks') + 1;

          if (remarksCol > 0) {

            var existing = String(sheet.getRange(row, remarksCol).getValue() || '');

            var note = '[Closed ' + formatDate_(data.closeDate) + '] ' + data.remarks;

            sheet.getRange(row, remarksCol).setValue(existing ? existing + '\n' + note : note);

          }

        }

        setLeadField_(sheet, row, headers, 'Last Updated', nowDateTime_());

        setLeadField_(sheet, row, headers, 'Last Updated By', getUserEmail_());

        try {
          if (typeof ensureDeliverySchema_ === 'function') {
            ensureDeliverySchema_();
            if (typeof ensureDeliveryRow_ === 'function') ensureDeliveryRow_(leadId, { skipRelock: true });
            var delSheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.DELIVERY_TRACKER);
            if (delSheet && typeof findDeliverySheetRow_ === 'function' && typeof writeDeliveryRowFields_ === 'function') {
              var delHeaders = getHeaders_(delSheet, CRM.DELIVERY.HEADER_ROW);
              var delRow = findDeliverySheetRow_(delSheet, leadId, delHeaders);
              if (delRow > 0) writeDeliveryRowFields_(delSheet, delRow, delHeaders, { rc: rc, numberPlate: numberPlate });
            }
          }
        } catch (eDel) {
          Logger.log('closeLead_ delivery RC update: ' + eDel.message);
        }

        SpreadsheetApp.flush();

        auditDetail = leadId + ' | ' + data.reason + ' | Outstanding: ' + finalOut;

        return { leadId: leadId };

      } finally {
        if (locked) lock.releaseLock();

      }

    },

    context: {

      module: 'Lead',

      action: 'Lead Closed',

      auditAction: 'CLOSE_LEAD',

      get auditDetail() { return auditDetail; },

      perfOp: 'lead_close',

      sheets: [CRM.SHEETS.LEAD_REGISTER, CRM.SHEETS.DELIVERY_TRACKER]

    },

    postTasks: [

      POST_TX.SYNC_COUNTERS,

      POST_TX.INVALIDATE_STORE,

      POST_TX.SYNC_COMPUTED,

      POST_TX.AUDIT,

      POST_TX.TRANSACTION_OK,

      POST_TX.PERF

    ]

  });

}



/**
 * Scheme Update — commercial offers only (staff). Owner may also edit customer fields.
 * Validates fully before any sheet write; nothing is logged if any step fails.
 */
function updateLeadFromDialog_(data) {
  return updateSchemeFromDialog_(data);
}

function updateSchemeFromDialog_(data) {
  var explicitOemInput = !!(data && (
    data.oemExtraSupportReceived != null ||
    data.oemExtraSupportPassed != null ||
    data.oemExtraSupportRetained != null ||
    data.oemExtraSupport != null ||
    data.extraSupport != null ||
    data.extraSupportReceived != null ||
    data.extraSupportPassed != null ||
    data['OEM Extra Support Received'] != null ||
    data['OEM Extra Support Passed To Customer'] != null
  ));
  if (typeof normalizeOemExtraSupportPayload_ === 'function') {
    data = normalizeOemExtraSupportPayload_(data || {});
  }
  var ctx = {
    module: 'Lead',
    action: 'updateSchemeFromDialog_',
    auditAction: 'SCHEME_UPDATE',
    get auditDetail() { return ctx.leadId || ''; },
    perfOp: 'scheme_update',
    sheets: [CRM.SHEETS.LEAD_REGISTER, CRM.SHEETS.COMMERCIAL_SNAPSHOT]
  };
  return runCriticalBusinessTransaction_({
    module: 'Lead',
    action: 'updateSchemeFromDialog_',
    successMessage: 'Scheme updated successfully',
    context: ctx,
    commitFn: function (setStep) {
      var lock = LockService.getDocumentLock();
      var locked = false;
      var leadId = String(data.leadId || '').trim();
      var offerResult = null;
      var offerChanged = false;
      try {
        setStep('lock');
        locked = lock.tryLock(10000);
        if (!locked) throw businessError_('Scheme update is busy. Please retry.', 'LOCK_BUSY');

        setStep('validate');
        ctx.leadId = leadId;
        var lead = getLeadFromRegisterLight_(leadId);
        if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');
        requireActiveLead_(leadId);

        var store = loadCrmStore_(true);
        var snap = store.commercial && store.commercial.byLeadId ? store.commercial.byLeadId[leadId] : null;
        if (!snap) {
          throw fieldError_('Booking', 'Lead is not booked yet. Use Convert to Booking first.', 'VALIDATION');
        }

        var newOffers = {
          consumerDiscount: Number(data.consumerDiscount || 0),
          exchangeBonus: Number(data.exchangeBonus || 0),
          loyaltyBonus: Number(data.loyaltyBonus || 0),
          referralBonus: Number(data.referralBonus || 0),
          dsaDiscount: Number(data.dsaDiscount || 0),
          additionalDiscount: Number(data.additionalDiscount || 0),
          oemExtraSupportReceived: Number(
            data.oemExtraSupportReceived != null ? data.oemExtraSupportReceived :
            (data.oemExtraSupport != null ? data.oemExtraSupport : 0)
          ),
          oemExtraSupportPassed: Number(data.oemExtraSupportPassed || 0),
          oemExtraSupportRetained: 0,
          benefitMode: typeof normalizeBenefitMode_ === 'function'
            ? normalizeBenefitMode_(data.benefitMode || 'Full Benefit')
            : String(data.benefitMode || 'Full Benefit'),
          customerBenefitPassed: Number(data.customerBenefitPassed != null ? data.customerBenefitPassed : 0),
          benefitPassedBreakup: String(data.benefitPassedBreakup || '')
        };
        // Re-normalize Extra Support after Number() coercion (portal may send strings).
        if (typeof normalizeOemExtraSupportPayload_ === 'function') {
          var _oes = normalizeOemExtraSupportPayload_({
            oemExtraSupportReceived: newOffers.oemExtraSupportReceived,
            oemExtraSupportPassed: newOffers.oemExtraSupportPassed
          });
          newOffers.oemExtraSupportReceived = Number(_oes.oemExtraSupportReceived || 0);
          newOffers.oemExtraSupportPassed = Number(_oes.oemExtraSupportPassed || 0);
          newOffers.oemExtraSupportRetained = Number(_oes.oemExtraSupportRetained || 0);
        }
        var full = snap.full || snap;

        // Cap / resolve Benefit Passed against eligible offers (server-side authority).
        var eligibleSum = newOffers.consumerDiscount + newOffers.exchangeBonus + newOffers.loyaltyBonus +
          newOffers.referralBonus + newOffers.dsaDiscount + newOffers.additionalDiscount;
        if (newOffers.benefitMode === 'No Benefit') {
          newOffers.customerBenefitPassed = 0;
          newOffers.benefitPassedBreakup = '';
        } else if (newOffers.benefitMode === 'Partial Benefit') {
          newOffers.customerBenefitPassed = Math.max(0, Math.min(Number(newOffers.customerBenefitPassed || 0), eligibleSum));
        } else {
          newOffers.customerBenefitPassed = eligibleSum;
        }
        newOffers.oemExtraSupportReceived = Math.max(0, Number(newOffers.oemExtraSupportReceived || 0));
        newOffers.oemExtraSupportPassed = Math.max(0, Math.min(
          Number(newOffers.oemExtraSupportPassed || 0),
          newOffers.oemExtraSupportReceived
        ));
        newOffers.oemExtraSupportRetained = round2_(
          Math.max(0, newOffers.oemExtraSupportReceived - newOffers.oemExtraSupportPassed)
        );

        var schemeModel = (data.interestedModel != null ? data.interestedModel : null) ||
          full.model || full.vehicleModel || lead.interestedModel || '';
        var schemeVariant = (data.variant != null ? data.variant : null) ||
          full.variant || lead.variant || '';
        var schemeBookingDate = full.bookingDate || lead.bookingDate || nowDate_();
        if (typeof validateSchemeOffersForVehicle_ === 'function') {
          validateSchemeOffersForVehicle_(schemeModel, schemeVariant, schemeBookingDate, newOffers);
        }

        var oemChanged = Math.abs(Number(full.oemExtraSupportReceived || 0) - Number(newOffers.oemExtraSupportReceived || 0)) > 0.01 ||
          Math.abs(Number(full.oemExtraSupportPassed || 0) - Number(newOffers.oemExtraSupportPassed || 0)) > 0.01 ||
          Math.abs(Number(full.oemExtraSupportRetained || 0) - Number(newOffers.oemExtraSupportRetained || 0)) > 0.01;

        offerChanged = ['consumerDiscount', 'exchangeBonus', 'loyaltyBonus', 'referralBonus', 'dsaDiscount', 'additionalDiscount', 'oemExtraSupportReceived', 'oemExtraSupportPassed', 'oemExtraSupportRetained', 'benefitMode', 'customerBenefitPassed', 'benefitPassedBreakup'].some(function (k) {
          if (k === 'benefitMode') {
            var prevMode = typeof normalizeBenefitMode_ === 'function'
              ? normalizeBenefitMode_(full.benefitMode) : String(full.benefitMode || 'Full Benefit');
            return prevMode !== newOffers.benefitMode;
          }
          if (k === 'customerBenefitPassed') {
            var prevPassed = typeof resolveCustomerBenefitPassed_ === 'function'
              ? resolveCustomerBenefitPassed_(full) : Number(full.customerBenefitPassed || 0);
            return Math.abs(prevPassed - Number(newOffers.customerBenefitPassed || 0)) > 0.01;
          }
          if (k === 'benefitPassedBreakup') {
            return String(full.benefitPassedBreakup || '') !== String(newOffers.benefitPassedBreakup || '');
          }
          return Math.abs(Number(full[k] || 0) - Number(newOffers[k] || 0)) > 0.01;
        });

        var owner = typeof isSpreadsheetOwner_ === 'function' && isSpreadsheetOwner_();
        var customerFields = {};
        if (owner && data.editCustomer) {
          var mobile = normalizeMobile_(data.mobile || lead.mobile);
          if (mobile && !isValidMobile_(mobile)) {
            throw fieldError_('Mobile', 'Enter a valid 10-digit mobile number.', 'VALIDATION');
          }
          if (mobile && mobile !== String(lead.mobile || '')) {
            var existing = findLeadByMobileLight_(mobile);
            if (existing && String(existing.leadId) !== leadId) {
              throw fieldError_('Mobile', 'Already used by lead ' + existing.leadId + '.', 'DUPLICATE');
            }
          }
          if (!String(data.customerName || '').trim()) {
            throw fieldError_('Customer Name', 'Enter the customer name.', 'VALIDATION');
          }
          customerFields = {
            'Customer Name': String(data.customerName || '').trim() || lead.customerName,
            'Mobile': mobile || lead.mobile,
            'Lead Source': data.leadSource != null ? data.leadSource : lead.leadSource,
            'Interested Model': data.interestedModel != null ? data.interestedModel : lead.interestedModel,
            'Variant': data.variant != null ? data.variant : lead.variant,
            'Executive': data.executive != null ? data.executive : lead.executive,
            'Priority': data.priority != null ? data.priority : lead.priority,
            'Next Follow-up Date': formatDate_(data.nextFollowUpDate) || '',
            'Remarks': data.remarks != null ? data.remarks : (lead.remarks || '')
          };
        }

        if (!offerChanged && !oemChanged && !Object.keys(customerFields).length) {
          throw businessError_('No changes to save.', 'VALIDATION');
        }

        setStep('amend');
        if (offerChanged || oemChanged) {
          offerResult = amendCommercialSnapshot_(leadId, newOffers, 'Scheme update via CRM', getUserEmail_());
        }

        setStep('write');
        var writeFields = {};
        Object.keys(customerFields).forEach(function (k) { writeFields[k] = customerFields[k]; });
        if (offerChanged || oemChanged) {
          // Avoid loadCrmStore_(true) here — full workbook rebuild was the main
          // Scheme Update timeout. Truth fields come from the just-amended snapshot.
          invalidateCrmStore_();
          var truthSnap = null;
          try {
            truthSnap = typeof getLatestCommercialSnapshotForLead_ === 'function'
              ? getLatestCommercialSnapshotForLead_(leadId) : null;
          } catch (tsErr) {}
          if (!truthSnap && typeof readCommercialSnapshotForLead_ === 'function') {
            try { truthSnap = readCommercialSnapshotForLead_(leadId); } catch (rsErr) {}
          }
          if (typeof buildLeadCommercialTruthFields_ !== 'function') {
            throw businessError_(
              'CRM Utils.gs is outdated — missing buildLeadCommercialTruthFields_. Copy Utils.gs from final fix, Save, reload, retry.',
              'MISSING_MODULE'
            );
          }
          var truth = buildLeadCommercialTruthFields_(leadId, null, truthSnap);
          Object.keys(truth).forEach(function (k) {
            if (truth[k] !== undefined) writeFields[k] = truth[k];
          });
        }
        if (Object.keys(writeFields).length) {
          writeFields['Last Updated'] = nowDateTime_();
          writeFields['Last Updated By'] = getUserEmail_();
          updateLeadRegisterFields_(leadId, writeFields);
        }

        // Persist OEM Extra Support immediately into register + dealer earnings.
        // Do NOT wait for deferred sync — that path was dropping Extra Support.
        if (offerChanged || oemChanged || explicitOemInput) {
          var oesRecv = Number(newOffers.oemExtraSupportReceived || 0);
          var oesPass = Number(newOffers.oemExtraSupportPassed || 0);
          var oesRet = Number(newOffers.oemExtraSupportRetained || 0);
          try {
            if (typeof upsertOemExtraSupportCase_ === 'function') {
              upsertOemExtraSupportCase_({
                'Lead ID': leadId,
                'Booking ID': (offerResult && offerResult.bookingId) || (full && full.bookingId) || '',
                'Customer Name': lead.customerName || '',
                'Vehicle Model': schemeModel,
                'Variant': schemeVariant,
                'Booking Date': formatDate_(schemeBookingDate) || '',
                'OEM Extra Support Received': oesRecv,
                'OEM Extra Support Passed To Customer': oesPass,
                'OEM Extra Support Retained': oesRet
              }, { remarks: oesRecv > 0 ? 'Scheme Update' : 'Scheme Update (no Extra Support)' });
            }
          } catch (eOesImmediate) {
            Logger.log('oem extra support immediate upsert: ' + eOesImmediate.message);
          }
          try {
            if (typeof upsertDealerEarningsForLead_ === 'function') {
              upsertDealerEarningsForLead_(leadId, {
                reason: 'scheme_update_oem_extra',
                oemExtraSupportReceived: oesRecv,
                oemExtraSupportPassed: oesPass,
                oemExtraSupportRetained: oesRet,
                rebuildAnalytics: false
              });
            }
          } catch (eEarnImmediate) {
            Logger.log('dealer earnings immediate oem upsert: ' + eEarnImmediate.message);
          }
        }

        setStep('claim');
        // Claim rebuild stays deferred; OEM Extra Support already written above.
        SpreadsheetApp.flush();
        scheduleDeferredCrmSync_({ leadId: leadId, reason: 'scheme_update', dashboard: true });
        return {
          leadId: leadId,
          offerAmended: offerChanged,
          explicitOemInput: explicitOemInput,
          snapshotId: offerResult && offerResult.snapshotId,
          oemExtraSupportReceived: Number(newOffers.oemExtraSupportReceived || 0),
          oemExtraSupportPassed: Number(newOffers.oemExtraSupportPassed || 0),
          oemExtraSupportRetained: Number(newOffers.oemExtraSupportRetained || 0)
        };
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

/* ═══════════════════════════════════════════════════════════════════════════
 * Edit Lead — spreadsheet CRM menu only (correct wrong saved details).
 * ═══════════════════════════════════════════════════════════════════════════ */

function showEditLeadDialog_() {
  var m = getMergedMasters_();
  var variantByModel = getVariantOptionsByModel_();
  var seedLeads = getActiveLeadsForPickerLight_({ activeOnly: false });
  var html = createDialogOutput_(
    dialogBaseCss_('#6A1B9A') + '<style>' + leadPickerCss_() + '</style>' +
    '<h3>Edit Lead</h3>' +
    '<p style="font-size:12px;color:#666;">Correct wrongly saved lead details. Does not change scheme or price.</p>' +
    leadPickerHtml_({ showClosedCheckbox: true, activeOnly: false, label: 'Lead *' }) +
    '<div id="editStatus" style="font-size:12px;color:#666;margin:6px 0;">Pick a lead…</div>' +
    '<label>Customer Name *</label><input id="customerName" />' +
    '<label>Mobile *</label><input id="mobile" maxlength="10" />' +
    '<label>Lead Source</label><select id="leadSource">' + buildSelectOptionsHtml_(m['Lead Sources']) + '</select>' +
    '<label>Model</label><select id="interestedModel">' + buildSelectOptionsHtml_(m['Models'], true) + '</select>' +
    '<label>Variant</label><select id="variant"></select>' +
    '<label>Executive</label><select id="executive">' + buildSelectOptionsHtml_(m['Executives'], true) + '</select>' +
    '<label>Priority</label><select id="priority">' + buildSelectOptionsHtml_(m['Priority']) + '</select>' +
    '<label>Finance Required</label><select id="financeRequired"><option value="">—</option><option>Yes</option><option>No</option></select>' +
    '<label>Exchange Required</label><select id="exchangeRequired"><option value="">—</option><option>Yes</option><option>No</option></select>' +
    '<label>Next Follow-up Date</label><input id="nextFollowUpDate" type="date" />' +
    '<label>Remarks</label><textarea id="remarks" rows="2"></textarea>' +
    '<label>Account Status</label><select id="accountStatus">' +
      '<option>Active</option><option>Closed</option><option>Cancelled</option></select>' +
    '<button class="btn" id="btn" type="button" onclick="doSave()">Save Lead Changes</button>' +
    htmlScript_(dialogClientHelpersJs_()) +
    htmlScript_('window.__LEAD_CACHE_SEEDED=' + jsonForHtml_(seedLeads) + ';') +
    htmlScript_('var VARIANT_BY_MODEL=' + jsonForHtml_(variantByModel) + ';') +
    htmlScript_(leadPickerClientJs_(false, 'activity')) +
    htmlScript_(editLeadDialogClientJs_()),
    420,
    700
  );
  SpreadsheetApp.getUi().showModalDialog(html, 'Edit Lead');
}

function editLeadDialogClientJs_() {
  return [
    'function el(id){return document.getElementById(id);}',
    'function setVal(id,v){var x=el(id);if(x)x.value=(v===undefined||v===null)?"":v;}',
    'function esc(s){return String(s||"").replace(/&/g,"&amp;").replace(/\\u003c/g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}',
    'function setVariantOptions(list,cur){',
    '  var sel=el("variant");var opts=["<option value=\\"\\"></option>"];',
    '  (list||[]).forEach(function(v){opts.push("<option value=\\""+esc(v)+"\\""+(String(v)===String(cur)?" selected":"")+">"+esc(v)+"</option>");});',
    '  sel.innerHTML=opts.join("");',
    '}',
    'function refreshVariants(cur){',
    '  var model=el("interestedModel").value||"";',
    '  var list=VARIANT_BY_MODEL[model]||[];',
    '  if(!list.length&&model){var mk=Object.keys(VARIANT_BY_MODEL).find(function(k){return String(k).toLowerCase()===String(model).toLowerCase();});if(mk)list=VARIANT_BY_MODEL[mk]||[];}',
    '  setVariantOptions(list,cur);',
    '}',
    'function loadLead(id){',
    '  el("editStatus").textContent="Loading…";',
    '  google.script.run.withSuccessHandler(function(res){',
    '    if(!res||res.success===false){el("editStatus").textContent=(res&&res.message)||"Failed";return;}',
    '    var l=res.lead||{};',
    '    setVal("customerName",l.customerName);setVal("mobile",l.mobile);',
    '    setVal("leadSource",l.leadSource);setVal("interestedModel",l.interestedModel||l.model);',
    '    refreshVariants(l.variant);setVal("variant",l.variant);',
    '    setVal("executive",l.executive);setVal("priority",l.priority);',
    '    setVal("financeRequired",l.financeRequired);setVal("exchangeRequired",l.exchangeRequired);',
    '    setVal("nextFollowUpDate",l.nextFollowUpDate);setVal("remarks",l.remarks);',
    '    setVal("accountStatus",l.accountStatus||"Active");',
    '    el("editStatus").textContent="Editing "+(l.leadId||id)+" — "+(l.accountStatus||"Active");',
    '  }).withFailureHandler(function(e){el("editStatus").textContent=parseServerError(e);}).getEditLeadContext(id);',
    '}',
    'window.onLeadPicked=function(l){loadLead(l.leadId);};',
    'el("interestedModel").addEventListener("change",function(){refreshVariants("");});',
    'function doSave(){',
    '  if(!validateLeadPick())return;',
    '  var b=el("btn");b.disabled=true;b.textContent="Saving…";',
    '  var d={leadId:getPickedLeadId(),customerName:el("customerName").value,mobile:el("mobile").value,',
    '    leadSource:el("leadSource").value,interestedModel:el("interestedModel").value,variant:el("variant").value,',
    '    executive:el("executive").value,priority:el("priority").value,financeRequired:el("financeRequired").value,',
    '    exchangeRequired:el("exchangeRequired").value,nextFollowUpDate:el("nextFollowUpDate").value,',
    '    remarks:el("remarks").value,accountStatus:el("accountStatus").value};',
    '  google.script.run.withSuccessHandler(function(res){',
    '    b.disabled=false;b.textContent="Save Lead Changes";',
    '    if(res&&res.success===false){alert(parseServerError(res));return;}',
    '    alert((res&&res.message)||"Lead updated");kickDeferredCrmRefresh(function(){google.script.host.close();});',
    '  }).withFailureHandler(function(e){b.disabled=false;b.textContent="Save Lead Changes";alert(parseServerError(e));})',
    '  .saveEditLeadFromDialog(d);',
    '}'
  ].join('');
}

function getEditLeadContext(leadId) {
  try {
    leadId = String(leadId || '').trim();
    if (!leadId) return { success: false, message: 'Lead required' };
    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) return { success: false, message: 'Lead not found: ' + leadId };
    return {
      success: true,
      lead: {
        leadId: lead.leadId,
        customerName: lead.customerName || '',
        mobile: lead.mobile || '',
        leadSource: lead.leadSource || '',
        interestedModel: lead.interestedModel || lead.model || '',
        model: lead.interestedModel || lead.model || '',
        variant: lead.variant || '',
        executive: lead.executive || '',
        priority: lead.priority || '',
        financeRequired: lead.financeRequired || '',
        exchangeRequired: lead.exchangeRequired || '',
        nextFollowUpDate: formatDate_(lead.nextFollowUpDate) || '',
        remarks: lead.remarks || '',
        accountStatus: normalizeAccountStatus_(lead.accountStatus) || 'Active',
        currentStatus: lead.currentStatus || ''
      }
    };
  } catch (e) {
    return { success: false, message: (e && e.message) || String(e) };
  }
}

function saveEditLeadFromDialog(data) {
  try {
    data = data || {};
    var leadId = String(data.leadId || '').trim();
    if (!leadId) {
      return crmFailStructured_('Lead', 'saveEditLeadFromDialog', 'validate',
        businessError_('Lead is required', 'VALIDATION'), 0);
    }
    if (typeof requireExistingLead_ === 'function') requireExistingLead_(leadId);
    else requireActiveLead_(leadId);

    var lead = getLeadFromRegisterLight_(leadId);
    if (!lead) throw businessError_('Lead not found: ' + leadId, 'NOT_FOUND');

    var name = String(data.customerName || '').trim();
    if (!name) throw fieldError_('Customer Name', 'Enter the customer name.', 'VALIDATION');
    var mobile = normalizeMobile_(data.mobile || lead.mobile);
    if (!mobile || !isValidMobile_(mobile)) {
      throw fieldError_('Mobile', 'Enter a valid 10-digit mobile number.', 'VALIDATION');
    }
    if (mobile !== String(lead.mobile || '')) {
      var existing = findLeadByMobileLight_(mobile);
      if (existing && String(existing.leadId) !== leadId) {
        throw fieldError_('Mobile', 'Already used by lead ' + existing.leadId + '.', 'DUPLICATE');
      }
    }

    var newStatus = normalizeAccountStatus_(data.accountStatus || lead.accountStatus || 'Active');
    if (newStatus === ACCOUNT_STATUS.ARCHIVED) {
      throw businessError_('Cannot set Archived from Edit Lead. Use Merge / Admin tools.', 'VALIDATION');
    }

    var newModel = data.interestedModel != null ? String(data.interestedModel).trim() : (lead.interestedModel || '');
    var newVariant = data.variant != null ? String(data.variant).trim() : (lead.variant || '');
    var oldModel = String(lead.interestedModel || lead.model || '').trim();
    var oldVariant = String(lead.variant || '').trim();
    var modelOrVariantChanged =
      newModel.toLowerCase() !== oldModel.toLowerCase() ||
      newVariant.toLowerCase() !== oldVariant.toLowerCase();

    var fields = {
      'Customer Name': name,
      'Mobile': mobile,
      'Lead Source': data.leadSource != null ? data.leadSource : (lead.leadSource || ''),
      'Interested Model': newModel,
      'Variant': newVariant,
      'Executive': data.executive != null ? data.executive : (lead.executive || ''),
      'Priority': data.priority != null ? data.priority : (lead.priority || ''),
      'Finance Required': data.financeRequired != null ? data.financeRequired : (lead.financeRequired || ''),
      'Exchange Required': data.exchangeRequired != null ? data.exchangeRequired : (lead.exchangeRequired || ''),
      'Next Follow-up Date': formatDate_(data.nextFollowUpDate) || '',
      'Remarks': data.remarks != null ? data.remarks : (lead.remarks || ''),
      'Account Status': newStatus,
      'Last Updated': nowDateTime_(),
      'Last Updated By': getUserEmail_()
    };

    var priceNote = '';
    // Always push commercial price onto Lead Register when model/variant known.
    // (Previously only on model/variant *change* — re-saves left Ex Showroom blank.)
    try {
      ensureLeadCommercialPriceColumns_();
      var booked = typeof isLeadAlreadyBooked_ === 'function' ? isLeadAlreadyBooked_(lead) : false;
      var snap = null;
      try {
        if (typeof getLatestCommercialSnapshotForLead_ === 'function') {
          snap = getLatestCommercialSnapshotForLead_(leadId);
        }
      } catch (eSnap) {}
      if (snap && snap.full && typeof snap.full === 'object') snap = snap.full;

      var bookingDate = formatDate_((snap && snap.bookingDate) || lead.bookingDate) || nowDate_();
      var pm = null;
      if (newModel && newVariant) {
        try {
          pm = typeof getActivePrice_ === 'function'
            ? getActivePrice_(newModel, newVariant, bookingDate) : null;
        } catch (ePm) { pm = null; }
      }

      var snapEx = snap ? Number(snap.exShowroom || 0) : 0;
      var pmEx = pm ? Number(pm.exShowroom || 0) : 0;
      var needPriceRefresh = modelOrVariantChanged || !(snapEx > 0);

      if (needPriceRefresh && pmEx > 0) {
        if (booked && typeof amendCommercialSnapshot_ === 'function') {
          var priceChanges = {
            model: newModel,
            variant: newVariant,
            exShowroom: pmEx,
            priceListVersion: pm.priceVersion || '',
            priceEffectiveDate: pm.effectiveFrom || '',
            priceMasterRowId: pm.rowNumber || pm.priceMasterRowId || ''
          };
          // If snapshot has no other charges yet, seed from Price Master too.
          if (!(snapEx > 0) || !(Number(snap.insurance || 0) > 0 || Number(snap.registrationRto || 0) > 0)) {
            priceChanges.insurance = Number((snap && snap.insurance) || pm.insurance || 0);
            priceChanges.registrationRto = Number((snap && snap.registrationRto) || pm.registrationRto || 0);
            priceChanges.accessories = Number((snap && snap.accessories) || pm.accessories || 0);
            priceChanges.handlingCharges = Number((snap && snap.handlingCharges) || pm.handlingCharges || 0);
            priceChanges.trc = Number((snap && snap.trc) || pm.trc || 0);
            priceChanges.fastag = Number((snap && snap.fastag) || pm.fastag || 0);
            priceChanges.extendedWarranty = Number((snap && snap.extendedWarranty) || pm.extendedWarranty || 0);
            priceChanges.otherCharges = Number((snap && snap.otherCharges) || pm.otherCharges || 0);
            priceChanges.gstPercent = Number((snap && snap.gstPercent) || pm.gstPercent || 0);
            priceChanges.tcsApplicable = normalizeYesNo_((snap && snap.tcsApplicable) || pm.tcsApplicable || 'No');
          }
          if (snap || booked) {
            try {
              amendCommercialSnapshot_(leadId, priceChanges,
                'Edit Lead: sync Ex Showroom / price to Lead Register', getUserEmail_());
              invalidateCrmStore_();
              snap = typeof getLatestCommercialSnapshotForLead_ === 'function'
                ? getLatestCommercialSnapshotForLead_(leadId) : snap;
              if (snap && snap.full) snap = snap.full;
            } catch (eAmend) {
              // No snapshot yet (unbooked) — still write Price Master estimate to Lead Register.
              Logger.log('edit lead amend: ' + eAmend.message);
            }
          }
        }
      }

      // Authoritative Lead Register price write from snapshot, else Price Master.
      if (typeof buildLeadCommercialTruthFields_ === 'function') {
        var truthSnap = snap;
        if ((!truthSnap || !(Number(truthSnap.exShowroom || 0) > 0)) && pmEx > 0) {
          truthSnap = {
            model: newModel,
            variant: newVariant,
            bookingDate: bookingDate,
            exShowroom: pmEx,
            insurance: Number((snap && snap.insurance) || (pm && pm.insurance) || 0),
            registrationRto: Number((snap && snap.registrationRto) || (pm && pm.registrationRto) || 0),
            accessories: Number((snap && snap.accessories) || (pm && pm.accessories) || 0),
            handlingCharges: Number((snap && snap.handlingCharges) || (pm && pm.handlingCharges) || 0),
            trc: Number((snap && snap.trc) || (pm && pm.trc) || 0),
            fastag: Number((snap && snap.fastag) || (pm && pm.fastag) || 0),
            extendedWarranty: Number((snap && snap.extendedWarranty) || (pm && pm.extendedWarranty) || 0),
            otherCharges: Number((snap && snap.otherCharges) || (pm && pm.otherCharges) || 0),
            gstPercent: Number((snap && snap.gstPercent) || (pm && pm.gstPercent) || 0),
            tcsApplicable: normalizeYesNo_((snap && snap.tcsApplicable) || (pm && pm.tcsApplicable) || 'No'),
            consumerDiscount: Number((snap && snap.consumerDiscount) || 0),
            exchangeBonus: Number((snap && snap.exchangeBonus) || 0),
            loyaltyBonus: Number((snap && snap.loyaltyBonus) || 0),
            referralBonus: Number((snap && snap.referralBonus) || 0),
            dsaDiscount: Number((snap && snap.dsaDiscount) || 0),
            additionalDiscount: Number((snap && snap.additionalDiscount) || 0),
            bookingAmount: Number(lead.bookingAmount || 0)
          };
        }
        if (truthSnap && (Number(truthSnap.exShowroom || 0) > 0 || booked)) {
          var truth = buildLeadCommercialTruthFields_(leadId, null, truthSnap);
          Object.keys(truth).forEach(function (k) {
            if (truth[k] !== undefined) fields[k] = truth[k];
          });
          if (Number(truthSnap.exShowroom || 0) > 0) {
            fields['Ex Showroom'] = Number(truthSnap.exShowroom);
          }
          priceNote = ' · Ex Showroom ₹' + Math.round(Number(fields['Ex Showroom'] || 0)).toLocaleString('en-IN');
        } else if (newModel && newVariant && !(pmEx > 0)) {
          priceNote = ' · No Price Master row for ' + newModel + ' / ' + newVariant;
        }
      }

      if (booked && modelOrVariantChanged && typeof upsertBookingRegister_ === 'function') {
        try {
          var bookingId = (snap && snap.bookingId) || lead.bookingId || '';
          if (bookingId) {
            upsertBookingRegister_({
              BookingID: bookingId,
              LeadID: leadId,
              'Vehicle Model': newModel,
              Variant: newVariant,
              'Last Updated': nowDateTime_()
            });
          }
        } catch (eBk) {}
      }
    } catch (ePrice) {
      Logger.log('saveEditLeadFromDialog price refresh: ' + ePrice.message);
      priceNote = ' · Price sync failed: ' + ePrice.message;
    }

    updateLeadRegisterFields_(leadId, fields);
    try {
      logAudit_('LEAD_EDIT', leadId + ' | ' + name + ' | ' + mobile +
        ' | ' + newModel + '/' + newVariant + ' | status=' + newStatus + priceNote);
    } catch (aErr) {}
    invalidateCrmStore_();
    scheduleDeferredCrmSync_({ leadId: leadId, reason: 'lead_edit', dashboard: true });
    SpreadsheetApp.flush();
    return crmOk_('Lead ' + leadId + ' updated' + priceNote, {
      leadId: leadId,
      accountStatus: newStatus,
      model: newModel,
      variant: newVariant,
      exShowroom: fields['Ex Showroom']
    });
  } catch (e) {
    return crmFailStructured_('Lead', 'saveEditLeadFromDialog', 'handler', e, 0);
  }
}
