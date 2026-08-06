/**
 * BackupService – versioned Drive backups + restore from registry.
 */

/** Business-critical sheets for lightweight fallback backup (lazy – CRM must be loaded). */
function getBackupCoreSheets_() {
  return [
    CRM.SHEETS.DASHBOARD, CRM.SHEETS.LEAD_REGISTER, CRM.SHEETS.ACTIVITY_LOG,
    CRM.SHEETS.PAYMENT_LEDGER, CRM.SHEETS.DELIVERY_TRACKER, CRM.SHEETS.MASTERS,
    CRM.SHEETS.DASHBOARD_DATA, CRM.SHEETS.SETTINGS
  ];
}

function ensureBackupRegistrySheet_() {
  var result = ensureHelperSheet_(CRM.SHEETS.BACKUP_REGISTRY, CRM.BACKUP_REGISTRY.COLS, true);
  return result.sheet;
}

function getNextBackupNumber_() {
  var sheet = ensureBackupRegistrySheet_();
  var last = sheet.getLastRow();
  if (last < CRM.BACKUP_REGISTRY.DATA_START) return 1;
  var val = sheet.getRange(last, 1).getValue();
  return (Number(val) || 0) + 1;
}

function hashSettings_() {
  try {
    return Utilities.computeDigest(Utilities.DigestAlgorithm.MD5,
      JSON.stringify(getSettings_())).map(function (b) {
      return ('0' + (b & 0xFF).toString(16)).slice(-2);
    }).join('').substring(0, 16);
  } catch (e) {
    return 'unknown';
  }
}

function hashProtection_() {
  return 'disabled';
}

function countTotalRows_() {
  var total = 0;
  getBackupCoreSheets_().forEach(function (name) {
    var sh = getSpreadsheet_().getSheetByName(name);
    if (!sh) return;
    var dataStart = name === CRM.SHEETS.LEAD_REGISTER ? CRM.LEAD.DATA_START : 2;
    total += Math.max(0, sh.getLastRow() - dataStart + 1);
  });
  return total;
}

/**
 * Fast full-spreadsheet backup via Drive copy (preferred).
 * @returns {{backup: Spreadsheet, sheetCount: number, method: string}}
 */
function createDriveCopyBackup_(name) {
  var ss = getSpreadsheet_();
  var file = DriveApp.getFileById(ss.getId());
  var copyFile = file.makeCopy(name);
  var backup = SpreadsheetApp.openById(copyFile.getId());
  return {
    backup: backup,
    sheetCount: backup.getSheets().length,
    method: 'drive_copy'
  };
}

/**
 * Fallback: copy core business sheets only (when Drive copy fails).
 */
function createCoreSheetsBackup_(name) {
  var ss = getSpreadsheet_();
  var backup = SpreadsheetApp.create(name);
  var sheetCount = 0;

  getBackupCoreSheets_().forEach(function (sheetName) {
    var src = ss.getSheetByName(sheetName);
    if (!src) return;
    sheetCount++;
    var dest = backup.insertSheet(sheetName);
    var lastRow = src.getLastRow();
    var lastCol = src.getLastColumn();
    if (lastRow > 0 && lastCol > 0) {
      src.getRange(1, 1, lastRow, lastCol).copyTo(dest.getRange(1, 1));
    }
    if ([CRM.SHEETS.DASHBOARD_DATA, CRM.SHEETS.SETTINGS].indexOf(sheetName) >= 0) {
      dest.hideSheet();
    }
  });

  var defaultSheet = backup.getSheetByName('Sheet1');
  if (defaultSheet && backup.getSheets().length > 1) {
    backup.deleteSheet(defaultSheet);
  }

  return {
    backup: backup,
    sheetCount: sheetCount,
    method: 'core_sheets'
  };
}

function registerBackupEntry_(backupNo, ts, backup, rowCount, sheetCount, settingsHash, protectionHash, notes, method) {
  var reg = ensureBackupRegistrySheet_();
  var noteText = (notes || '') + (method ? ' [' + method + ']' : '');
  reg.appendRow([
    backupNo, ts, CRM.VERSION, backup.getUrl(), backup.getId(),
    rowCount, sheetCount, settingsHash, protectionHash, noteText
  ]);
}

/**
 * Create versioned backup on Drive and register it.
 * Uses Drive makeCopy (fast); falls back to core-sheet copy if needed.
 * @param {string} [notes]
 */
function createVersionedBackup_(notes) {
  var start = Date.now();
  var ss = getSpreadsheet_();
  var backupNo = getNextBackupNumber_();
  var ts = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd HH:mm:ss');
  var name = ss.getName() + ' v' + backupNo + ' ' + ts;

  var result;
  var lastError = '';

  try {
    result = createDriveCopyBackup_(name);
  } catch (driveErr) {
    lastError = driveErr.message || String(driveErr);
    logAudit_('BACKUP_DRIVE_COPY_WARN', lastError);
    try {
      result = createCoreSheetsBackup_(name);
    } catch (coreErr) {
      logCrash_('System', 'createVersionedBackup_', coreErr, { errorCode: 'BACKUP_FAIL' });
      throw new Error(
        'Backup failed. Drive copy: ' + lastError + '. Core copy: ' + (coreErr.message || coreErr) +
        '\n\nCheck Drive storage space and script permissions, then retry CRM → Backup Database.'
      );
    }
  }

  var backup = result.backup;
  var rowCount = countTotalRows_();
  var settingsHash = hashSettings_();
  var protectionHash = hashProtection_();

  registerBackupEntry_(backupNo, ts, backup, rowCount, result.sheetCount,
    settingsHash, protectionHash, notes, result.method);

  logAudit_('BACKUP', 'v' + backupNo + ' ' + backup.getUrl() + ' method=' + result.method);
  logTransaction_('System', 'Backup Created', {
    status: 'OK',
    executionMs: Date.now() - start,
    message: 'Backup #' + backupNo + ' rows=' + rowCount + ' method=' + result.method
  });

  return {
    backupNo: backupNo,
    url: backup.getUrl(),
    id: backup.getId(),
    rowCount: rowCount,
    sheetCount: result.sheetCount,
    settingsHash: settingsHash,
    protectionHash: protectionHash,
    method: result.method
  };
}

function backupDatabase_() {
  var result = createVersionedBackup_('Manual backup');
  SpreadsheetApp.getUi().alert(
    'Backup Created',
    'Backup #' + result.backupNo + '\n' + result.url + '\n\nRows: ' + result.rowCount +
    '\nMethod: ' + result.method + '\nVersion: ' + CRM.VERSION,
    SpreadsheetApp.getUi().ButtonSet.OK
  );
}

function menuBackupDatabase() {
  backupDatabase_();
}

function listBackups_() {
  var sheet = ensureBackupRegistrySheet_();
  var last = sheet.getLastRow();
  if (last < CRM.BACKUP_REGISTRY.DATA_START) return [];
  var numRows = last - CRM.BACKUP_REGISTRY.DATA_START + 1;
  var data = sheet.getRange(CRM.BACKUP_REGISTRY.DATA_START, 1, numRows, 10).getValues();
  return data.map(function (row) {
    return {
      backupNo: row[0],
      timestamp: row[1],
      version: row[2],
      url: row[3],
      spreadsheetId: row[4],
      rowCount: row[5],
      notes: row[9]
    };
  });
}

/**
 * Restore data from a registered backup (values only – overwrites current sheets).
 */
function restoreBackup_(backupNo) {
  backupNo = Number(backupNo);
  var backups = listBackups_();
  var entry = backups.filter(function (b) { return Number(b.backupNo) === backupNo; })[0];
  if (!entry) throw new Error('Backup #' + backupNo + ' not found in registry');

  var ui = SpreadsheetApp.getUi();
  var confirm = ui.alert(
    'Restore Backup #' + backupNo,
    'This will OVERWRITE current CRM data with backup from ' + entry.timestamp + '.\n\nA new backup of current state will be created first.\n\nContinue?',
    ui.ButtonSet.YES_NO
  );
  if (confirm !== ui.Button.YES) return { cancelled: true };

  clearMaintenanceAndReadOnly_();
  createVersionedBackup_('Pre-restore snapshot before #' + backupNo);

  var backupSs = SpreadsheetApp.openById(entry.spreadsheetId);

  Object.values(CRM.SHEETS).forEach(function (sheetName) {
    if (sheetName.indexOf('Obs ') === 0) return;
    var src = backupSs.getSheetByName(sheetName);
    var dest = getSpreadsheet_().getSheetByName(sheetName);
    if (!src || !dest) return;
    dest.clear();
    var lastRow = src.getLastRow();
    var lastCol = src.getLastColumn();
    if (lastRow > 0 && lastCol > 0) {
      src.getRange(1, 1, lastRow, lastCol).copyTo(dest.getRange(1, 1));
    }
  });

  invalidateCrmStore_();
  syncComputedFields_({ dashboard: true });

  logTransaction_('System', 'Backup Restored', {
    status: 'OK',
    message: 'Restored backup #' + backupNo + ' from ' + entry.timestamp
  });
  logAudit_('RESTORE', 'Backup #' + backupNo);

  ui.alert('Restore Complete', 'Restored backup #' + backupNo + ' from ' + entry.timestamp, ui.ButtonSet.OK);
  return { backupNo: backupNo, timestamp: entry.timestamp };
}

function menuRestoreBackup() {
  return crmRun_('System', 'Restore Backup', function () {
    var backups = listBackups_();
    if (backups.length === 0) {
      SpreadsheetApp.getUi().alert('No backups in registry. Create one via Backup Database first.');
      return { empty: true };
    }
    var recent = backups.slice(-5).reverse();
    var msg = 'Enter Backup Number to restore:\n\nRecent backups:\n' +
      recent.map(function (b) {
        return '#' + b.backupNo + ' — ' + b.timestamp + (b.notes ? ' (' + b.notes + ')' : '');
      }).join('\n');
    var ui = SpreadsheetApp.getUi();
    var resp = ui.prompt('Restore Backup', msg, ui.ButtonSet.OK_CANCEL);
    if (resp.getSelectedButton() !== ui.Button.OK) return { cancelled: true };
    var no = Number(resp.getResponseText().trim());
    if (!no) throw new Error('Invalid backup number');
    return restoreBackup_(no);
  });
}
