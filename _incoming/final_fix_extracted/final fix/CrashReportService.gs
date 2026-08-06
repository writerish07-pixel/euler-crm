/**
 * CrashReportService – persistent exception logging.
 */

function ensureCrashReportSheet_() {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.CRASH_REPORT);
  if (!sheet) {
    sheet = ss.insertSheet(CRM.SHEETS.CRASH_REPORT);
    sheet.getRange(CRM.CRASH_REPORT.HEADER_ROW, 1, 1, CRM.CRASH_REPORT.COLS.length)
      .setValues([CRM.CRASH_REPORT.COLS]).setFontWeight('bold');
    sheet.hideSheet();
  }
  return sheet;
}

/**
 * Log uncaught exception to Crash Report sheet.
 */
function logCrash_(module, fnName, err, opts) {
  opts = opts || {};
  try {
    var sheet = ensureCrashReportSheet_();
    var row = [
      nowDateTime_(),
      getUserEmail_(),
      module || '',
      fnName || '',
      opts.leadId || '',
      opts.errorCode || 'EXCEPTION',
      String(err && err.message ? err.message : err).substring(0, 300),
      String(err && err.stack ? err.stack : '').substring(0, 1000),
      opts.executionMs !== undefined ? opts.executionMs : '',
      SpreadsheetApp.getActiveSpreadsheet().getId(),
      getVersionTag_()
    ];
    var newRow = Math.max(sheet.getLastRow() + 1, CRM.CRASH_REPORT.DATA_START);
    writeSheetRow_(sheet, newRow, row);
  } catch (logErr) {
    Logger.log('Crash log failed: ' + logErr.message);
    try { logAudit_('CRASH_LOG_FAIL', fnName + ': ' + (err && err.message)); } catch (e) {}
  }
}
