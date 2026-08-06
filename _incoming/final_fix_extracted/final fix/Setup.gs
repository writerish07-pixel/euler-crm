/**
 * Sheet setup - creates all sheets with headers and structure.
 */

function setupAllSheets_() {
  var ss = getSpreadsheet_();
  var required = Object.values(CRM.SHEETS);
  if (required.indexOf(CRM.SHEETS.TRANSACTION_LOG) < 0) {
    required.push(CRM.SHEETS.TRANSACTION_LOG);
  }

  // Create all CRM sheets FIRST — a spreadsheet must always have at least one sheet
  ensureSheet_(ss, CRM.SHEETS.DASHBOARD, false);
  ensureSheet_(ss, CRM.SHEETS.LEAD_REGISTER, false);
  ensureSheet_(ss, CRM.SHEETS.ACTIVITY_LOG, false);
  ensureSheet_(ss, CRM.SHEETS.PAYMENT_LEDGER, false);
  ensureSheet_(ss, CRM.SHEETS.DELIVERY_TRACKER, false);
  ensureSheet_(ss, CRM.SHEETS.MASTERS, true);
  ensureSheet_(ss, CRM.SHEETS.DASHBOARD_DATA, true);
  ensureSheet_(ss, CRM.SHEETS.SETTINGS, true);
  ensureSheet_(ss, CRM.SHEETS.IMPORT_LOG, true);
  ensureSheet_(ss, CRM.SHEETS.AUDIT_LOG, true);
  ensureSheet_(ss, CRM.SHEETS.TRANSACTION_LOG, true);
  ensureSheet_(ss, CRM.SHEETS.COMMERCIAL_SNAPSHOT, true);
  ensureSheet_(ss, CRM.SHEETS.BOOKING_REGISTER, false);
  ensureSheet_(ss, CRM.SHEETS.RELATIONSHIP_INDEX, true);
  ensureSheet_(ss, CRM.SHEETS.BOOKING_STATUS_HISTORY, true);
  ensureSheet_(ss, CRM.SHEETS.VEHICLE_ALLOCATION, true);
  ensureSheet_(ss, CRM.SHEETS.QUOTATION_SCHEMA, true);
  ensureSheet_(ss, CRM.SHEETS.EXECUTIVE_SCORECARD, true);
  ensureSheet_(ss, CRM.SHEETS.DEALER_DAILY_REGISTER, true);
  ensureSheet_(ss, CRM.SHEETS.FINANCE_REGISTER, false);
  if (CRM.SHEETS.QUOTATION_LOG) ensureSheet_(ss, CRM.SHEETS.QUOTATION_LOG, false);
  ensureSheet_(ss, CRM.SHEETS.COMMERCIAL_AUDIT, true);
  ensureSheet_(ss, CRM.SHEETS.PRICE_MASTER, false);
  if (CRM.SHEETS.INSURANCE_REGISTER) ensureSheet_(ss, CRM.SHEETS.INSURANCE_REGISTER, false);
  ensureSheet_(ss, CRM.SHEETS.SCHEME_CLAIM_REGISTER, false);
  ensureSheet_(ss, CRM.SHEETS.OEM_CLAIM_DASHBOARD, false);
  ensureSheet_(ss, CRM.SHEETS.OWNER_COMMERCIAL_REPORT, false);
  ensureSheet_(ss, CRM.SHEETS.CLAIM_EXCEPTION, false);
  if (CRM.SHEETS.OEM_EXTRA_SUPPORT_REGISTER) ensureSheet_(ss, CRM.SHEETS.OEM_EXTRA_SUPPORT_REGISTER, false);

  // Remove default/legacy sheets
  var legacy = ss.getSheets().filter(function (s) {
    return required.indexOf(s.getName()) === -1;
  });
  legacy.forEach(function (s) {
    if (ss.getSheets().length > 1) ss.deleteSheet(s);
  });

  setupDashboard_();
  setupLeadRegister_();
  ensureLeadSchema_();
  setupActivityLog_();
  setupPaymentLedger_();
  setupDeliveryTracker_();
  setupMasters_();
  setupDashboardData_();
  setupSettings_();
  setupImportLog_();
  setupAuditLog_();
  setupTransactionLog_();
  setupCommercialSnapshot_();
  setupPriceMaster_();
  setupCommercialClaimSheets_();
  setupPhase3CoreSheets_();
  if (typeof ensureFinanceRegisterSheet_ === 'function') ensureFinanceRegisterSheet_();
  if (typeof ensureInsuranceRegisterSheet_ === 'function') ensureInsuranceRegisterSheet_();
  if (typeof ensureExtraIncomeRegisterSheet_ === 'function') ensureExtraIncomeRegisterSheet_();
  if (typeof ensureExtraIncomeAnalyticsSheet_ === 'function') ensureExtraIncomeAnalyticsSheet_();
  if (typeof ensureDealerEarningsRegisterSheet_ === 'function') ensureDealerEarningsRegisterSheet_();
  if (typeof ensureDealerEarningsAnalyticsSheet_ === 'function') ensureDealerEarningsAnalyticsSheet_();
  if (typeof ensureOemExtraSupportRegisterSheet_ === 'function') ensureOemExtraSupportRegisterSheet_();
  if (typeof ensureDeliverySchema_ === 'function') ensureDeliverySchema_();
  if (typeof ensurePaymentLedgerSchema_ === 'function') ensurePaymentLedgerSchema_();

  logAudit_('SETUP', 'All sheets created/reset');
}

function setupPhase3CoreSheets_() {
  ensurePhase3Sheets_();
  try { if (typeof ensureQuotationLogSheet_ === 'function') ensureQuotationLogSheet_(); } catch (e) {}
}

/** Write headers for the claim register, audit, and exception sheets. */
function setupCommercialClaimSheets_() {
  if (CRM.CLAIM_REGISTER && CRM.CLAIM_REGISTER.COLS) {
    var reg = getSheet_(CRM.SHEETS.SCHEME_CLAIM_REGISTER);
    reg.getRange(CRM.CLAIM_REGISTER.HEADER_ROW, 1, 1, CRM.CLAIM_REGISTER.COLS.length)
      .setValues([CRM.CLAIM_REGISTER.COLS]).setFontWeight('bold');
    reg.setFrozenRows(CRM.CLAIM_REGISTER.HEADER_ROW);
  }
  if (CRM.COMMERCIAL_AUDIT && CRM.COMMERCIAL_AUDIT.COLS) {
    var aud = getSheet_(CRM.SHEETS.COMMERCIAL_AUDIT);
    aud.getRange(CRM.COMMERCIAL_AUDIT.HEADER_ROW, 1, 1, CRM.COMMERCIAL_AUDIT.COLS.length)
      .setValues([CRM.COMMERCIAL_AUDIT.COLS]).setFontWeight('bold');
  }
  if (CRM.CLAIM_EXCEPTION && CRM.CLAIM_EXCEPTION.COLS) {
    var exc = getSheet_(CRM.SHEETS.CLAIM_EXCEPTION);
    exc.getRange(CRM.CLAIM_EXCEPTION.HEADER_ROW, 1, 1, CRM.CLAIM_EXCEPTION.COLS.length)
      .setValues([CRM.CLAIM_EXCEPTION.COLS]).setFontWeight('bold');
  }
}

function setupTransactionLog_() {
  var sheet = getSheet_(CRM.SHEETS.TRANSACTION_LOG);
  sheet.getRange(CRM.TRANSACTION_LOG.HEADER_ROW, 1, 1, CRM.TRANSACTION_LOG.COLS.length)
    .setValues([CRM.TRANSACTION_LOG.COLS])
    .setFontWeight('bold');
}

function setupCommercialSnapshot_() {
  var sheet = getSheet_(CRM.SHEETS.COMMERCIAL_SNAPSHOT);
  if (!CRM.COMMERCIAL || !CRM.COMMERCIAL.COLS) return;
  if (typeof ensureCommercialSnapshotHeaders_ === 'function') {
    ensureCommercialSnapshotHeaders_();
    return;
  }
  sheet.getRange(CRM.COMMERCIAL.HEADER_ROW, 1, 1, CRM.COMMERCIAL.COLS.length)
    .setValues([CRM.COMMERCIAL.COLS])
    .setFontWeight('bold');
}

function setupPriceMaster_() {
  if (!CRM.PRICE_MASTER || !CRM.PRICE_MASTER.COLS) return;
  var sheet = getSheet_(CRM.SHEETS.PRICE_MASTER);
  sheet.getRange(CRM.PRICE_MASTER.HEADER_ROW, 1, 1, CRM.PRICE_MASTER.COLS.length)
    .setValues([CRM.PRICE_MASTER.COLS])
    .setFontWeight('bold')
    .setBackground('#E1F5FE');
  sheet.setFrozenRows(CRM.PRICE_MASTER.HEADER_ROW);
}

function ensureSheet_(ss, name, hidden) {
  var sheet = ss.getSheetByName(name);
  if (!sheet) sheet = ss.insertSheet(name);
  sheet.clear();
  if (hidden) sheet.hideSheet();
  return sheet;
}

function setupDashboard_() {
  var sheet = getSheet_(CRM.SHEETS.DASHBOARD);
  sheet.clear();
  var settings = getSettings_();

  sheet.getRange('A1').setValue(settings.companyName + ' — CRM Dashboard').setFontSize(18).setFontWeight('bold');
  sheet.getRange('A2').setValue('Last Updated:').setFontWeight('bold');
  sheet.getRange('B2').setValue('');

  var metrics = [
    ['TODAY', ''],
    ['Today\'s Leads', ''],
    ['Today\'s Follow-ups', ''],
    ['Today\'s Bookings', ''],
    ['Today\'s Deliveries', ''],
    ['', ''],
    ['PENDING', ''],
    ['Pending Deliveries', ''],
    ['Pending Follow-ups', ''],
    ['Pending Payments', ''],
    ['', ''],
    ['MONTHLY', ''],
    ['Monthly Leads', ''],
    ['Monthly Bookings', ''],
    ['Monthly Deliveries', ''],
    ['Conversion %', ''],
    ['', ''],
    ['INSIGHTS', ''],
    ['Top Source', ''],
    ['Top Model', ''],
    ['Revenue (Month)', ''],
    ['', ''],
    ['PAYMENTS (MONTH)', ''],
    ['Cash', ''],
    ['UPI', ''],
    ['Finance', ''],
    ['Other', ''],
    ['Outstanding (Total Customer)', ''],
    ['Customer Outstanding', ''],
    ['Company Outstanding (OEM schemes)', ''],
    ['Finance Overdue (past delivery SLA)', ''],
    ['— Finance Outstanding (financer pays)', ''],
    ['INSURANCE (PAYOUT)', ''],
    ['— Insurance Premium Total', ''],
    ['— Expected Insurer Payout', ''],
    ['— Received from Insurer', ''],
    ['— Payout Outstanding', ''],
    ['', ''],
    ['MODEL PERFORMANCE', '']
  ];

  sheet.getRange(4, 1, metrics.length, 2).setValues(metrics);
  sheet.getRange('A4:A42').setFontWeight('bold');
  sheet.getRange('B19').setNumberFormat('0.0%');
  sheet.getRange('B24').setNumberFormat('#,##0');
  sheet.getRange('B27:B35').setNumberFormat('#,##0');
  sheet.getRange('B37:B40').setNumberFormat('#,##0');

  sheet.getRange('D1').setValue('Recent Activities').setFontWeight('bold');
  sheet.getRange('D2:I2').setValues([['Date', 'Lead ID', 'Customer', 'Type', 'Discussion', 'Executive']]);
  sheet.getRange('D2:I2').setFontWeight('bold').setBackground('#E8EAF6');
  sheet.getRange('D3:I12').clearContent();

  sheet.setColumnWidth(1, 200);
  sheet.setColumnWidth(2, 120);
  sheet.setFrozenRows(2);
}

function setupLeadRegister_() {
  var sheet = getSheet_(CRM.SHEETS.LEAD_REGISTER);
  sheet.clear();

  sheet.getRange('A1').setValue('SEARCH').setFontWeight('bold').setBackground('#FFF9C4');
  sheet.getRange('B1').setValue('Lead ID');
  sheet.getRange('C1').setValue('Mobile');
  sheet.getRange('D1').setValue('Customer Name');
  sheet.getRange('E1').setValue('→ Use CRM menu > Search Lead, or filter column below');

  sheet.getRange(CRM.LEAD.HEADER_ROW, 1, 1, CRM.LEAD.COLS.length)
    .setValues([CRM.LEAD.COLS])
    .setFontWeight('bold')
    .setBackground('#E3F2FD')
    .setWrap(true);

  sheet.setFrozenRows(CRM.LEAD.HEADER_ROW);
  for (var c = 1; c <= CRM.LEAD.COLS.length; c++) {
    sheet.setColumnWidth(c, c <= 3 ? 110 : 95);
  }
  sheet.setColumnWidth(3, 150);
  sheet.setColumnWidth(27, 200);
}

function setupActivityLog_() {
  var sheet = getSheet_(CRM.SHEETS.ACTIVITY_LOG);
  sheet.getRange(1, 1, 1, CRM.ACTIVITY.COLS.length)
    .setValues([CRM.ACTIVITY.COLS])
    .setFontWeight('bold')
    .setBackground('#E8F5E9');
  sheet.setFrozenRows(1);
}

function setupPaymentLedger_() {
  var sheet = getSheet_(CRM.SHEETS.PAYMENT_LEDGER);
  sheet.getRange(1, 1, 1, CRM.PAYMENT.COLS.length)
    .setValues([CRM.PAYMENT.COLS])
    .setFontWeight('bold')
    .setBackground('#FFF3E0');
  sheet.setFrozenRows(1);
}

function setupDeliveryTracker_() {
  var sheet = getSheet_(CRM.SHEETS.DELIVERY_TRACKER);
  sheet.getRange(1, 1, 1, CRM.DELIVERY.COLS.length)
    .setValues([CRM.DELIVERY.COLS])
    .setFontWeight('bold')
    .setBackground('#F3E5F5');
  sheet.setFrozenRows(1);
}

function setupMasters_() {
  writeMastersSheet_(getMergedMasters_());
}

function setupDashboardData_() {
  var sheet = getSheet_(CRM.SHEETS.DASHBOARD_DATA);
  sheet.getRange('A1').setValue('Last Refresh');
  sheet.getRange('A3').setValue('Today Leads');
  sheet.getRange('A4').setValue('Today Followups');
  sheet.getRange('A5').setValue('Today Bookings');
  sheet.getRange('A6').setValue('Today Deliveries');
  sheet.getRange('A8').setValue('Pending Deliveries');
  sheet.getRange('A9').setValue('Pending Followups');
  sheet.getRange('A10').setValue('Pending Payments');
  sheet.getRange('A12').setValue('Monthly Leads');
  sheet.getRange('A13').setValue('Monthly Bookings');
  sheet.getRange('A14').setValue('Monthly Deliveries');
  sheet.getRange('A15').setValue('Conversion');
  sheet.getRange('A17').setValue('Top Source');
  sheet.getRange('A18').setValue('Top Model');
  sheet.getRange('A19').setValue('Revenue');
  sheet.getRange('A21').setValue('Payments Cash');
  sheet.getRange('A22').setValue('Payments UPI');
  sheet.getRange('A23').setValue('Payments Finance');
  sheet.getRange('A24').setValue('Payments Other');
  sheet.getRange('A26').setValue('Outstanding');
  sheet.getRange('A29').setValue('Recent Activities Header');
}

function setupSettings_() {
  var sheet = getSheet_(CRM.SHEETS.SETTINGS);
  var defaults = CRM.SETTINGS_DEFAULTS;
  var rows = Object.keys(defaults).map(function (k) {
    return [k, defaults[k]];
  });
  sheet.getRange(1, 1, 1, 2).setValues([['Key', 'Value']]).setFontWeight('bold');
  sheet.getRange(2, 1, rows.length, 2).setValues(rows);
}

function setupImportLog_() {
  var sheet = getSheet_(CRM.SHEETS.IMPORT_LOG);
  sheet.getRange(1, 1, 1, 4).setValues([['Timestamp', 'Category', 'Count', 'Details']]).setFontWeight('bold');
}

function setupAuditLog_() {
  var sheet = getSheet_(CRM.SHEETS.AUDIT_LOG);
  sheet.getRange(1, 1, 1, 4).setValues([['Timestamp', 'User', 'Action', 'Details']]).setFontWeight('bold');
}

function setupFormulas_() {
  clearComputedFormulas_();
  refreshAllDropdowns_();
}

function applyDataValidations_() {
  refreshAllDropdowns_();
}
