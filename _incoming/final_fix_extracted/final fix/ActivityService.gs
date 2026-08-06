/**
 * Activity Log operations – mission-critical path decoupled from reporting.
 */

function addActivity_(data) {
  var postCtx = {
    module: 'Activity',
    action: 'Activity Added',
    auditAction: 'ADD_ACTIVITY',
    auditDetail: '',
    perfOp: 'activity',
    sheets: [CRM.SHEETS.ACTIVITY_LOG, CRM.SHEETS.LEAD_REGISTER]
  };
  return runCriticalBusinessTransaction_({
    module: 'Activity',
    action: 'addActivity_',
    successMessage: 'Activity added successfully',
    context: postCtx,
    commitFn: function (setStep) {
      var lock = LockService.getDocumentLock();
      var locked = false;
      var activityId = '';
      try {
        setStep('lock');
        // Re-entrancy guard: booking records its "Booking converted" activity while
        // already holding the document lock. Apps Script locks aren't re-entrant, so
        // a nested tryLock(10000) blocked ~10s per booking. Callers already inside a
        // lock pass skipLock:true.
        if (data.skipLock) {
          locked = false;
        } else {
          locked = lock.tryLock(10000);
          if (!locked) throw businessError_('Activity save is busy. Please retry.', 'LOCK_BUSY');
        }

        setStep('write_mode');
        setStep('validate');
        var lead = getLead_(data.leadId);
        if (!lead) throw businessError_('Lead ID not found: ' + data.leadId, 'NOT_FOUND');
        requireActiveLead_(data.leadId);
        postCtx.leadId = data.leadId;

        setStep('generateId');
        var sheet = getSpreadsheet_().getSheetByName(CRM.SHEETS.ACTIVITY_LOG);
        if (!sheet) throw businessError_('Activity Log not found', 'MISSING_SHEET');
        activityId = generateId_('activity');
        var now = new Date();

        setStep('write');
        var row = [
          activityId, data.leadId,
          data.date || formatDate_(now), data.time || formatTime_(now),
          normalizeActivityTypeForWrite_(data.activityType || 'Call', { allowFallback: false }), data.discussion || '',
          data.nextFollowUp || '', data.reminder || '',
          data.executive || lead.executive || '',
          lead.customerName, lead.mobile, lead.interestedModel
        ];
        var newRow = Math.max(sheet.getLastRow() + 1, CRM.ACTIVITY.DATA_START);
        writeSheetRow_(sheet, newRow, row);

        if (data.nextFollowUp) {
          updateLeadFollowUpCritical_(data.leadId, data.nextFollowUp);
        }

        SpreadsheetApp.flush();
        postCtx.auditDetail = activityId + ' for ' + data.leadId;
        upsertRelationshipIndex_({
          LeadID: data.leadId,
          LatestActivityID: activityId,
          'Current Status': 'In Progress'
        });
        return { activityId: activityId, leadId: data.leadId };
      } finally {
        if (locked) lock.releaseLock();
      }
    },
    postTasks: data.skipPostTasks ? [] : [
      POST_TX.SYNC_COUNTERS,
      POST_TX.INVALIDATE_STORE,
      POST_TX.SYNC_COMPUTED,
      POST_TX.AUDIT,
      POST_TX.TRANSACTION_OK,
      POST_TX.PERF
    ]
  });
}

function updateLeadFollowUpCritical_(leadId, followUpDate) {
  var found = findLeadById_(leadId);
  if (!found) return;
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  var fuIdx = found.headers.indexOf('Next Follow-up Date') + 1;
  if (fuIdx > 0) sheet.getRange(found.row, fuIdx).setValue(followUpDate);
}

function handleActivityLogEdit_(e) {
  if (!e || !e.range) return;
  var row = e.range.getRow();
  if (row < CRM.ACTIVITY.DATA_START) return;
  var sheet = e.range.getSheet();
  var col = e.range.getColumn();
  var actCols = CRM.ACTIVITY.COLS;
  var idCol = actCols.indexOf('Activity ID') + 1;
  var leadCol = actCols.indexOf('Lead ID') + 1;
  var dateCol = actCols.indexOf('Date') + 1;
  var timeCol = actCols.indexOf('Time') + 1;
  var fuCol = actCols.indexOf('Next Follow-up') + 1;

  if (col === leadCol && e.value) {
    invalidateCrmStore_();
    if (!getLead_(e.value)) {
      showToast_('Lead ID not found: ' + e.value);
      return;
    }
  }

  if (col === idCol && !e.value) {
    sheet.getRange(row, idCol).setValue(generateId_('activity'));
    sheet.getRange(row, dateCol).setValue(nowDate_());
    sheet.getRange(row, timeCol).setValue(formatTime_(new Date()));
  }

  if (col === leadCol || col === fuCol) {
    var leadId = sheet.getRange(row, leadCol).getValue();
    var nextFu = sheet.getRange(row, fuCol).getValue();
    if (leadId && nextFu) updateLeadFollowUp_(leadId, nextFu);
  }

  invalidateCrmStore_();
  queuePostTransaction_([POST_TX.SYNC_COMPUTED], { dashboard: true });
}

function updateLeadFollowUp_(leadId, followUpDate) {
  updateLeadFollowUpCritical_(leadId, followUpDate);
  invalidateCrmStore_();
}

function batchImportActivities_(activities, leadIdRemap) {
  var sheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  var settings = getSettings_();
  var counter = settings.nextActivityCounter;
  leadIdRemap = leadIdRemap || {};
  invalidateCrmStore_();
  var store = loadCrmStore_();

  var rows = activities.map(function (a) {
    a = sanitizeActivityForImport_(a);
    var leadId = resolveLeadId_(a.leadId, leadIdRemap);
    var lead = store.leads.byId[leadId];
    var id = 'AC26' + String(counter++).padStart(6, '0');
    return [
      id, leadId, a.date || nowDate_(), a.time || '',
      normalizeActivityTypeForWrite_(a.activityType, { allowFallback: true, fallbackType: 'Note' }), a.discussion || '',
      a.nextFollowUp || '', a.reminder || '', a.executive || '',
      lead ? lead.customerName : '',
      lead ? lead.mobile : '',
      lead ? lead.interestedModel : ''
    ];
  });

  saveSetting_('nextActivityCounter', counter);
  if (rows.length === 0) return 0;
  writeBatchData_(sheet, CRM.ACTIVITY.DATA_START, rows);
  invalidateCrmStore_();
  return rows.length;
}

function getRecentActivities_(limit) {
  limit = limit || 10;
  var store = loadCrmStore_();
  var h = store.activities.headers;
  var acts = store.activities.rows.map(function (row) {
    return [rowVal_(row, h, 'Activity ID'), rowVal_(row, h, 'Lead ID'),
      rowVal_(row, h, 'Date'), rowVal_(row, h, 'Time'), rowVal_(row, h, 'Activity Type'),
      rowVal_(row, h, 'Discussion'), rowVal_(row, h, 'Next Follow-up'),
      rowVal_(row, h, 'Reminder'), rowVal_(row, h, 'Executive')];
  });
  return acts.slice(-limit).reverse();
}
