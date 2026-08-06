/**
 * MergeLeadService – merge duplicate leads (spelling / duplicate feed).
 * Keeps primary lead; moves activities/payments/delivery; archives secondary.
 */

/** Normalize company name for duplicate detection. */
function normalizeCustomerNameForMatch_(name) {
  var s = String(name || '').toUpperCase();
  s = s.replace(/\b(PRIVATE|PVT|LTD|LIMITED|LLP|INC|CORP|COMPANY|CO|TECH|TECHNOLOGIES)\b/g, ' ');
  s = s.replace(/[^A-Z0-9]/g, ' ');
  s = s.replace(/\s+/g, ' ').trim();
  return s;
}

/** Stronger key for grouping (first 12 chars of normalized name). */
function customerMatchKey_(name) {
  var n = normalizeCustomerNameForMatch_(name);
  if (!n) return '';
  var parts = n.split(' ').filter(function (p) { return p.length > 2; });
  if (parts.length === 0) return n.substring(0, 12);
  return parts.slice(0, 4).join(' ');
}

/**
 * Find groups of leads that may be the same customer.
 * @returns {Array<{key:string, leads:Object[]}>}
 */
function findDuplicateLeadGroups_() {
  var store = loadCrmStore_(true);
  var byKey = {};
  var byMobile = {};

  Object.keys(store.leads.byId).forEach(function (id) {
    var l = store.leads.byId[id];
    if (normalizeAccountStatus_(l.accountStatus) === ACCOUNT_STATUS.ARCHIVED) return;

    var key = customerMatchKey_(l.customerName);
    if (key) {
      if (!byKey[key]) byKey[key] = [];
      byKey[key].push(buildMergeLeadSummary_(id, store));
    }
    if (l.mobile) {
      if (!byMobile[l.mobile]) byMobile[l.mobile] = [];
      byMobile[l.mobile].push(id);
    }
  });

  var groups = [];
  var seen = {};

  Object.keys(byMobile).forEach(function (mob) {
    if (byMobile[mob].length < 2) return;
    var leads = byMobile[mob].map(function (id) {
      return buildMergeLeadSummary_(id, store);
    });
    var gkey = 'mob:' + mob;
    if (!seen[gkey]) {
      seen[gkey] = true;
      groups.push({ key: gkey, reason: 'Same mobile', leads: leads });
    }
  });

  Object.keys(byKey).forEach(function (key) {
    if (byKey[key].length < 2) return;
    var gkey = 'name:' + key;
    if (seen[gkey]) return;
    seen[gkey] = true;
    groups.push({ key: gkey, reason: 'Similar name', leads: byKey[key] });
  });

  groups.sort(function (a, b) {
    return b.leads.length - a.leads.length;
  });
  return groups;
}

function buildMergeLeadSummary_(leadId, store) {
  store = store || loadCrmStore_();
  var l = store.leads.byId[leadId];
  var paid = store.paymentsByLead[leadId] || 0;
  return {
    leadId: leadId,
    customerName: l ? l.customerName : '',
    mobile: l ? l.mobile : '',
    accountStatus: l ? normalizeAccountStatus_(l.accountStatus) : '',
    bookingAmount: l ? (l.bookingAmount || l.budget || 0) : 0,
    amountReceived: paid,
    outstanding: computeOutstanding_(leadId, store),
    createdDate: l ? l.createdDate : ''
  };
}

/** Public – list duplicate groups for merge dialog. */
function getDuplicateLeadGroups() {
  try {
    return findDuplicateLeadGroups_();
  } catch (err) {
    logAudit_('MERGE_GROUPS_ERROR', err.message);
    throw err;
  }
}

/**
 * Merge secondary lead into primary. Secondary is archived, not deleted.
 * @param {string} primaryId Lead to keep
 * @param {string} secondaryId Lead to merge away
 */
function mergeLeads(primaryId, secondaryId) {
  assertOperational_('merge');
  return safeRun_('mergeLeads', function () {
    var preBackup = createVersionedBackup_('Pre-merge snapshot');
    var lock = LockService.getDocumentLock();
    var locked = false;
    var actCount = 0;
    var payCount = 0;
    var delCount = 0;

    try {
      locked = lock.tryLock(30000);
      if (!locked) throw new Error('Merge is busy. Please retry.');

      primaryId = String(primaryId || '').trim();
      secondaryId = String(secondaryId || '').trim();
      if (!primaryId || !secondaryId) throw new Error('Both Lead IDs are required');
      if (primaryId === secondaryId) throw new Error('Cannot merge a lead into itself');

      invalidateCrmStore_();
      var store = loadCrmStore_(true);
      var primary = store.leads.byId[primaryId];
      var secondary = store.leads.byId[secondaryId];
      if (!primary) throw new Error('Primary lead not found: ' + primaryId);
      if (!secondary) throw new Error('Secondary lead not found: ' + secondaryId);
      if (normalizeAccountStatus_(secondary.accountStatus) === ACCOUNT_STATUS.ARCHIVED) {
        throw new Error('Secondary lead is already archived: ' + secondaryId);
      }
      actCount = remapLeadIdInSheet_(CRM.SHEETS.ACTIVITY_LOG, CRM.ACTIVITY.HEADER_ROW,
        CRM.ACTIVITY.DATA_START, 'Lead ID', secondaryId, primaryId);
      payCount = remapLeadIdInSheet_(CRM.SHEETS.PAYMENT_LEDGER, CRM.PAYMENT.HEADER_ROW,
        CRM.PAYMENT.DATA_START, 'Lead ID', secondaryId, primaryId);
      delCount = mergeDeliveryRows_(primaryId, secondaryId);

      mergeLeadRegisterFields_(primaryId, secondaryId, store);
      archiveMergedLead_(secondaryId, primaryId, store);
    } finally {
      try {
      } catch (e) {}
      if (locked) {
        lock.releaseLock();
        locked = false;
      }
    }

    // Sync after lock released – avoids nested lock deadlock with syncAll_.
    syncComputedFields_({ dashboard: true });

    var val = runValidationSilent_();
    var summary = 'Merged ' + secondaryId + ' → ' + primaryId +
      ' | activities=' + actCount + ' payments=' + payCount + ' delivery=' + delCount +
      ' | backup=#' + preBackup.backupNo + ' | val=' + val.pass + '/' + (val.pass + val.fail);
    logAudit_('MERGE_LEADS', summary + ' [' + getVersionTag_() + ']');

    return {
      primaryId: primaryId,
      secondaryId: secondaryId,
      activitiesMoved: actCount,
      paymentsMoved: payCount,
      message: 'Merge complete. Kept ' + primaryId + '. ' + secondaryId + ' archived.'
    };
  });
}

/** Batch remap Lead ID column (one read + one write). */
function remapLeadIdInSheet_(sheetName, headerRow, dataStart, colName, fromId, toId) {
  var sheet = getSheet_(sheetName);
  var headers = getHeaders_(sheet, headerRow);
  var col = headers.indexOf(colName) + 1;
  if (col < 1) return 0;
  var lastRow = sheet.getLastRow();
  if (lastRow < dataStart) return 0;

  var range = sheet.getRange(dataStart, col, Math.max(0, lastRow - dataStart + 1), 1);
  var vals = range.getValues();
  var count = 0;
  for (var i = 0; i < vals.length; i++) {
    if (String(vals[i][0]).trim() === fromId) {
      vals[i][0] = toId;
      count++;
    }
  }
  if (count > 0) range.setValues(vals);
  return count;
}

function mergeDeliveryRows_(primaryId, secondaryId) {
  var sheet = getSheet_(CRM.SHEETS.DELIVERY_TRACKER);
  var data = sheet.getDataRange().getValues();
  var primaryIdx = -1;
  var secondaryIdx = -1;
  for (var i = 1; i < data.length; i++) {
    if (data[i][0] === primaryId) primaryIdx = i;
    if (data[i][0] === secondaryId) secondaryIdx = i;
  }
  if (secondaryIdx < 0) return 0;

  var numCols = data[secondaryIdx].length;
  if (primaryIdx < 0) {
    data[secondaryIdx][0] = primaryId;
    sheet.getRange(secondaryIdx + 1, 1, secondaryIdx + 1, numCols).setValues([data[secondaryIdx]]);
    return 1;
  }

  for (var c = 1; c < numCols; c++) {
    if (data[secondaryIdx][c] && !data[primaryIdx][c]) {
      data[primaryIdx][c] = data[secondaryIdx][c];
    }
  }
  data[secondaryIdx][0] = '';
  data[secondaryIdx][1] = '';
  sheet.getRange(primaryIdx + 1, 1, primaryIdx + 1, numCols).setValues([data[primaryIdx]]);
  sheet.getRange(secondaryIdx + 1, 1, secondaryIdx + 1, numCols).setValues([data[secondaryIdx]]);
  return 1;
}

function mergeLeadRegisterFields_(primaryId, secondaryId, store) {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var pRow = store.leads.sheetRow[primaryId];
  var sRow = store.leads.sheetRow[secondaryId];
  if (!pRow || !sRow) return;

  var sec = store.leads.byId[secondaryId];
  var numCols = headers.length;
  var pVals = sheet.getRange(pRow, 1, pRow, numCols).getValues()[0];
  var sVals = sheet.getRange(sRow, 1, sRow, numCols).getValues()[0];

  var fillIfEmpty = [
    'Alternate Mobile', 'Village', 'City', 'Interested Model', 'Variant', 'Colour',
    'Executive', 'Finance Required', 'Remarks'
  ];
  fillIfEmpty.forEach(function (field) {
    var col = headers.indexOf(field);
    if (col < 0) return;
    if (!pVals[col] && sVals[col]) pVals[col] = sVals[col];
  });

  var bookCol = headers.indexOf('Booking Amount');
  if (bookCol >= 0) {
    var pBook = parseNumber_(pVals[bookCol]);
    var sBook = parseNumber_(sVals[bookCol]);
    if (sBook > pBook) pVals[bookCol] = sBook;
  }

  var remCol = headers.indexOf('Remarks');
  if (remCol >= 0) {
    var note = '[Merged ' + secondaryId + ' ' + (sec.customerName || '') + ' on ' + nowDate_() + ']';
    var existing = String(pVals[remCol] || '');
    pVals[remCol] = existing ? existing + '\n' + note : note;
  }

  var lastUpCol = headers.indexOf('Last Updated');
  var lastByCol = headers.indexOf('Last Updated By');
  if (lastUpCol >= 0) pVals[lastUpCol] = nowDateTime_();
  if (lastByCol >= 0) pVals[lastByCol] = getUserEmail_();

  sheet.getRange(pRow, 1, pRow, numCols).setValues([pVals]);
}

function archiveMergedLead_(secondaryId, primaryId, store) {
  store = store || loadCrmStore_();
  var sRow = store.leads.sheetRow[secondaryId];
  if (!sRow) return;

  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var headers = getHeaders_(sheet, CRM.LEAD.HEADER_ROW);
  var numCols = headers.length;
  var vals = sheet.getRange(sRow, 1, sRow, numCols).getValues()[0];

  function setField(name, value) {
    var col = headers.indexOf(name);
    if (col >= 0) vals[col] = value;
  }

  setField('Account Status', ACCOUNT_STATUS.ARCHIVED);
  setField('Close Reason', 'Merged into ' + primaryId);
  setField('Closed Date', nowDate_());
  setField('Closed By', getUserEmail_());
  setField('Close Timestamp', nowDateTime_());

  var remCol = headers.indexOf('Remarks');
  if (remCol >= 0) {
    var existing = String(vals[remCol] || '');
    var note = '[Archived – merged into ' + primaryId + ']';
    vals[remCol] = existing ? existing + '\n' + note : note;
  }

  sheet.getRange(sRow, 1, sRow, numCols).setValues([vals]);
}

/** Preview merge without writing. */
function getMergePreview(primaryId, secondaryId) {
  primaryId = String(primaryId || '').trim();
  secondaryId = String(secondaryId || '').trim();
  if (!primaryId || !secondaryId) throw new Error('Both Lead IDs are required');
  if (primaryId === secondaryId) throw new Error('Cannot merge a lead into itself');
  var store = loadCrmStore_(true);
  var primary = store.leads.byId[primaryId];
  var secondary = store.leads.byId[secondaryId];
  if (!primary) throw new Error('Primary lead not found: ' + primaryId);
  if (!secondary) throw new Error('Secondary lead not found: ' + secondaryId);
  return {
    primary: buildMergeLeadSummary_(primaryId, store),
    secondary: buildMergeLeadSummary_(secondaryId, store),
    activityCount: countLeadIdInStore_(store, secondaryId, 'activity'),
    paymentCount: countLeadIdInStore_(store, secondaryId, 'payment')
  };
}

function countLeadIdInStore_(store, leadId, kind) {
  var count = 0;
  if (kind === 'payment') {
    store.payments.rows.forEach(function (row) {
      if (String(rowVal_(row, store.payments.headers, 'Lead ID')).trim() === leadId) count++;
    });
    return count;
  }
  store.activities.rows.forEach(function (row) {
    if (String(rowVal_(row, store.activities.headers, 'Lead ID')).trim() === leadId) count++;
  });
  return count;
}

function mergeLeadsFromDialog(data) {
  if (!data || !data.primaryId || !data.secondaryId) {
    throw new Error('Keep Lead ID and Merge Lead ID are both required');
  }
  var result = mergeLeads(data.primaryId, data.secondaryId);
  return crmOk_(result.message, result);
}
