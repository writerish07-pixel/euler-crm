/**
 * DestructiveOpsService – confirm → backup → execute → validate → audit.
 */

/**
 * Run a destructive operation with mandatory safeguards.
 * @param {Object} opts
 * @param {string} opts.label Audit label
 * @param {string} opts.confirmTitle Dialog title
 * @param {string} opts.confirmMessage Dialog body
 * @param {Function} opts.fn Operation to execute
 * @param {boolean} [opts.skipValidation]
 * @returns {*}
 */
function runDestructiveOp_(opts) {
  opts = opts || {};
  var ui = SpreadsheetApp.getUi();
  var backupNote = opts.skipBackup
    ? '\n\nNo Drive backup will be created (faster). Use CRM → Backup Database first if you need a copy.'
    : '\n\nA backup will be created automatically before execution.';
  var resp = ui.alert(
    opts.confirmTitle || 'Confirm Operation',
    (opts.confirmMessage || 'This operation may modify production data.') + backupNote,
    ui.ButtonSet.YES_NO
  );
  if (resp !== ui.Button.YES) return { cancelled: true };

  var backup = null;
  var backupError = '';
  if (!opts.skipBackup) {
    try {
      backup = createVersionedBackup_('Pre-' + opts.label);
    } catch (be) {
      backupError = be.message || String(be);
      logCrash_('System', 'runDestructiveOp_.backup', be, { errorCode: 'BACKUP_FAIL' });
      var choice = ui.alert(
        'Backup Failed',
        'Automatic backup failed:\n\n' + backupError +
          '\n\n• Click NO to cancel this operation (recommended).\n' +
          '• Click YES to continue WITHOUT a backup (data risk).',
        ui.ButtonSet.YES_NO
      );
      if (choice !== ui.Button.YES) {
        throw new Error('Operation cancelled — backup could not be created. Try CRM → Backup Database first.');
      }
      logAudit_('BACKUP_SKIPPED', opts.label + ': ' + backupError);
    }
  } else {
    logAudit_('BACKUP_SKIPPED', opts.label + ': skipBackup=true');
  }

  var result = opts.fn();

  var valResult = { pass: 0, fail: 0 };
  if (!opts.skipValidation) {
    try {
      valResult = runValidationSilent_();
    } catch (ve) {
      valResult = { pass: 0, fail: 1, error: ve.message };
    }
  }

  var auditDetail = [
    'label=' + opts.label,
    'version=' + getVersionTag_(),
    backup ? 'backup=#' + backup.backupNo : 'backup=none',
    'validation=' + valResult.pass + '/' + (valResult.pass + valResult.fail)
  ].join(', ');

  logAudit_('DESTRUCTIVE_' + opts.label, auditDetail);
  logTransaction_('System', 'Destructive: ' + opts.label, {
    status: valResult.fail === 0 ? 'OK' : 'WARN',
    message: auditDetail
  });

  return {
    cancelled: false,
    result: result,
    backup: backup,
    validation: valResult
  };
}
