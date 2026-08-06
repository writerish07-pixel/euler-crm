/**
 * PerformanceMonitorService – track execution times, warn on degradation.
 */

var PERF_THRESHOLDS = {
  payment: 15000,
  dashboard: 30000,
  search: 5000,
  validation: 45000,
  sync: 60000
};

function ensurePerformanceLogSheet_() {
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.PERFORMANCE_LOG);
  if (!sheet) {
    sheet = ss.insertSheet(CRM.SHEETS.PERFORMANCE_LOG);
    sheet.getRange(CRM.PERFORMANCE_LOG.HEADER_ROW, 1, 1, CRM.PERFORMANCE_LOG.COLS.length)
      .setValues([CRM.PERFORMANCE_LOG.COLS]).setFontWeight('bold');
    sheet.hideSheet();
  }
  return sheet;
}

/** Record one operation timing (aggregates daily in sheet). */
function recordPerf_(operation, ms) {
  try {
    var cache = CacheService.getScriptCache();
    var day = nowDate_();
    var key = 'perf_' + operation + '_' + day;
    var raw = cache.get(key);
    var stats = raw ? JSON.parse(raw) : { sum: 0, count: 0, max: 0 };
    stats.sum += ms;
    stats.count++;
    if (ms > stats.max) stats.max = ms;
    cache.put(key, JSON.stringify(stats), 86400);

    var threshold = PERF_THRESHOLDS[operation] || 30000;
    if (ms > threshold) {
      logAudit_('PERF_WARN', operation + ' took ' + ms + 'ms (threshold ' + threshold + 'ms)');
    }
  } catch (e) {}
}

/** Flush daily aggregates to Performance Log sheet. */
function flushDailyPerfStats_() {
  try {
    var cache = CacheService.getScriptCache();
    var day = nowDate_();
    var sheet = ensurePerformanceLogSheet_();
    Object.keys(PERF_THRESHOLDS).forEach(function (op) {
      var key = 'perf_' + op + '_' + day;
      var raw = cache.get(key);
      if (!raw) return;
      var stats = JSON.parse(raw);
      var avg = stats.count > 0 ? Math.round(stats.sum / stats.count) : 0;
      var threshold = PERF_THRESHOLDS[op] || 30000;
      var warn = stats.max > threshold ? 'YES' : '';
      sheet.appendRow([day, op, avg, stats.max, stats.count, warn]);
    });
  } catch (e) {
    logAudit_('PERF_FLUSH_WARN', e.message);
  }
}

function getPerfSummary_() {
  var summary = {};
  var day = nowDate_();
  var cache = CacheService.getScriptCache();
  Object.keys(PERF_THRESHOLDS).forEach(function (op) {
    var raw = cache.get('perf_' + op + '_' + day);
    if (!raw) return;
    var stats = JSON.parse(raw);
    summary[op] = {
      avgMs: stats.count > 0 ? Math.round(stats.sum / stats.count) : 0,
      maxMs: stats.max,
      count: stats.count
    };
  });
  return summary;
}
