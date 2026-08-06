/**
 * TransactionLogService – append-only business operation log (hidden sheet).
 */

function ensureTransactionLogSheet_() {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.TRANSACTION_LOG);
  if (!sheet) {
    sheet = ss.insertSheet(CRM.SHEETS.TRANSACTION_LOG);
    sheet.getRange(CRM.TRANSACTION_LOG.HEADER_ROW, 1, 1, CRM.TRANSACTION_LOG.COLS.length)
      .setValues([CRM.TRANSACTION_LOG.COLS])
      .setFontWeight('bold');
    sheet.hideSheet();
  }
  return sheet;
}

/**
 * Write one transaction row.
 * @param {string} module e.g. Payment, Lead, Protection
 * @param {string} action e.g. Payment Saved
 * @param {Object} [opts]
 */
function logTransaction_(module, action, opts) {
  opts = opts || {};
  try {
    var sheet = ensureTransactionLogSheet_();
    var row = [
      nowDateTime_(),
      getUserEmail_(),
      module || '',
      action || '',
      opts.leadId || '',
      opts.executionMs !== undefined ? opts.executionMs : '',
      opts.status || 'OK',
      opts.errorCode || '',
      String(opts.message || '').substring(0, 500),
      getVersionTag_()
    ];
    var newRow = Math.max(sheet.getLastRow() + 1, CRM.TRANSACTION_LOG.DATA_START);
    writeSheetRow_(sheet, newRow, row);
  } catch (err) {
    Logger.log('Transaction log failed: ' + err.message);
    try { logAudit_('TX_LOG_ERROR', module + '/' + action + ': ' + err.message); } catch (e) {}
  }
}
