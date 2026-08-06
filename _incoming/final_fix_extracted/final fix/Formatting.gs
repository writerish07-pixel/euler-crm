/**
 * Conditional formatting rules.
 */

function applyAllConditionalFormatting_() {
  applyLeadRegisterFormatting_();
  applyDeliveryFormatting_();
  applyPaymentFormatting_();
  applyOutstandingReadOnlyStyling_();
  logAudit_('FORMATTING', 'Conditional formatting applied');
}

/** Visual lock: Outstanding columns look system-calculated (not editable). */
function applyOutstandingReadOnlyStyling_() {
  var lockedBg = '#ECEFF1';
  var lockedFg = '#455A64';
  var note = 'READ ONLY · LOCKED · System Calculated (Customer Payable − Payments Received)';

  function styleCols(sheetName, headerRow, dataStart, colNames) {
    try {
      var sheet = getSpreadsheet_().getSheetByName(sheetName);
      if (!sheet) return;
      var headers = getHeaders_(sheet, headerRow);
      var lastRow = Math.max(sheet.getLastRow(), dataStart);
      var numRows = Math.max(1, lastRow - dataStart + 1);
      colNames.forEach(function (name) {
        var col = findHeaderIndex_(headers, name) + 1;
        if (col < 1) return;
        sheet.getRange(headerRow, col)
          .setBackground(lockedBg).setFontColor(lockedFg).setFontWeight('bold')
          .setNote(note);
        sheet.getRange(dataStart, col, numRows, 1)
          .setBackground(lockedBg).setFontColor(lockedFg)
          .setNote(note);
      });
    } catch (e) {
      Logger.log('applyOutstandingReadOnlyStyling_ ' + sheetName + ': ' + e.message);
    }
  }

  styleCols(CRM.SHEETS.LEAD_REGISTER, CRM.LEAD.HEADER_ROW, CRM.LEAD.DATA_START, [
    'Outstanding Amount', 'Customer Outstanding', 'Final Outstanding', 'Company Outstanding'
  ]);
  styleCols(CRM.SHEETS.PAYMENT_LEDGER, CRM.PAYMENT.HEADER_ROW, CRM.PAYMENT.DATA_START, [
    'Outstanding Balance', 'Running Total'
  ]);
  styleCols(CRM.SHEETS.FINANCE_REGISTER, 1, 2, ['File Outstanding']);
  if (CRM.SHEETS.INSURANCE_REGISTER) {
    styleCols(CRM.SHEETS.INSURANCE_REGISTER,
      (CRM.INSURANCE_REGISTER && CRM.INSURANCE_REGISTER.HEADER_ROW) || 1,
      (CRM.INSURANCE_REGISTER && CRM.INSURANCE_REGISTER.DATA_START) || 2,
      ['Expected Payout', 'Payout Outstanding']);
  }
}

function applyLeadRegisterFormatting_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  sheet.clearConditionalFormatRules();
  var headers = CRM.LEAD.COLS;
  var rules = [];
  var dataStart = CRM.LEAD.DATA_START;
  var maxRow = dataStart + 5000;
  var numRows = maxRow - dataStart + 1;
  var fullRange = sheet.getRange(dataStart, 1, numRows, headers.length);

  var fuCol = colLetter_(headers.indexOf('Next Follow-up Date') + 1);
  var statusCol = headers.indexOf('Current Status') + 1;
  var outCol = headers.indexOf('Outstanding Amount') + 1;

  if (fuCol) {
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=AND($' + fuCol + dataStart + '<>"", $' + fuCol + dataStart + '=TODAY())')
      .setBackground(CRM.COLORS.TODAY_FOLLOWUP)
      .setRanges([fullRange])
      .build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenFormulaSatisfied('=AND($' + fuCol + dataStart + '<>"", $' + fuCol + dataStart + '<TODAY())')
      .setBackground(CRM.COLORS.OVERDUE_FOLLOWUP)
      .setRanges([fullRange])
      .build());
  }

  if (statusCol > 0) {
    var statusRange = sheet.getRange(dataStart, statusCol, numRows, 1);
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo('Delivered').setBackground(CRM.COLORS.DELIVERED).setRanges([statusRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo('Booked').setBackground(CRM.COLORS.BOOKED).setRanges([statusRange]).build());
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenTextEqualTo('Lost').setBackground(CRM.COLORS.LOST).setRanges([statusRange]).build());
  }

  if (outCol > 0) {
    var outRange = sheet.getRange(dataStart, outCol, numRows, 1);
    rules.push(SpreadsheetApp.newConditionalFormatRule()
      .whenNumberGreaterThan(0).setBackground(CRM.COLORS.PENDING_PAYMENT).setRanges([outRange]).build());
  }

  sheet.setConditionalFormatRules(rules);
}

function applyDeliveryFormatting_() {
  var sheet = getSheet_(CRM.SHEETS.DELIVERY_TRACKER);
  var delCol = CRM.DELIVERY.COLS.indexOf('Delivered') + 1;
  if (delCol > 0) {
    var range = sheet.getRange(CRM.DELIVERY.DATA_START, delCol, 5000, 1);
    var rules = [
      SpreadsheetApp.newConditionalFormatRule()
        .whenTextEqualTo('Yes').setBackground(CRM.COLORS.DELIVERED).setRanges([range]).build()
    ];
    sheet.setConditionalFormatRules(rules);
  }
}

function applyPaymentFormatting_() {
  var sheet = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  var outCol = CRM.PAYMENT.COLS.indexOf('Outstanding Balance') + 1;
  if (outCol > 0) {
    var range = sheet.getRange(CRM.PAYMENT.DATA_START, outCol, 5000, outCol);
    var rules = [
      SpreadsheetApp.newConditionalFormatRule()
        .whenNumberGreaterThan(0).setBackground(CRM.COLORS.PENDING_PAYMENT).setRanges([range]).build()
    ];
    sheet.setConditionalFormatRules(rules);
  }
}
