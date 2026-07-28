(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Masters</h1><p>Read-only lists used by forms. Editing masters stays in the spreadsheet / future admin API.</p></div></div>' +
      '<div id="masters" class="empty">Loadingâ€¦</div>';
    try {
      var m = await U.withLoading(CRM_API.getMasters());
      var keys = Object.keys(m || {}).filter(function (k) {
        return Array.isArray(m[k]);
      });
      if (!keys.length && m.SECTIONS) {
        keys = Object.keys(m.SECTIONS);
        m = m.SECTIONS;
      }
      if (!keys.length) {
        document.getElementById('masters').innerHTML = '<div class="empty">No master lists returned. Connect API_BASE_URL.</div>';
        return;
      }
      document.getElementById('masters').innerHTML = keys.map(function (k) {
        var items = (m[k] || []).map(function (x) {
          return '<li>' + U.escapeHtml(typeof x === 'string' ? x : (x.label || x.value || JSON.stringify(x))) + '</li>';
        }).join('');
        return '<div class="card card-pad" style="margin-bottom:12px;"><h3 style="margin:0 0 8px;font-size:14px;">' +
          U.escapeHtml(k) + '</h3><ul style="margin:0;padding-left:18px;font-size:13px;columns:2;">' + items + '</ul></div>';
      }).join('');
    } catch (err) {
      document.getElementById('masters').innerHTML = '<div class="empty">' + U.escapeHtml(err.message) + '</div>';
    }
  }
  CRM_BOOT.register('masters', { title: 'Masters', init: init });
})();
