(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Settings</h1><p>Portal configuration. Spreadsheet IDs are never shown here.</p></div></div>' +
      '<form id="set-form" class="card card-pad" style="max-width:720px;">' +
        '<div class="form-grid">' +
          '<label class="field full"><span>Company Name</span><input name="companyName" /></label>' +
          '<label class="field full"><span>Web Portal URL (for Sheet menu)</span><input name="webPortalUrl" placeholder="https://…/index.html" /></label>' +
        '</div>' +
        '<div style="margin-top:14px;display:flex;gap:8px;">' +
          '<button type="submit" class="btn">Save Settings</button>' +
          '<button type="button" class="btn btn-secondary" id="btn-ping">Ping API</button>' +
        '</div>' +
        '<p id="api-status" style="font-size:12px;color:var(--muted);margin-top:12px;"></p>' +
      '</form>' +
      '<div class="card card-pad" style="margin-top:14px;max-width:720px;">' +
        '<h3 style="margin:0 0 8px;font-size:14px;">Local API endpoint</h3>' +
        '<p style="font-size:13px;color:var(--muted);margin:0 0 8px;">Set in <code>assets/js/config.js</code> â†’ <code>API_BASE_URL</code></p>' +
        '<code id="api-url" style="font-size:12px;word-break:break-all;"></code>' +
      '</div>';

    document.getElementById('api-url').textContent = (window.CRM_CONFIG && CRM_CONFIG.API_BASE_URL) || '(empty â€” demo mode)';
    var form = document.getElementById('set-form');
    try {
      var s = await CRM_API.getSettings();
      if (s) {
        if (s.companyName) form.companyName.value = s.companyName;
        if (s.webPortalUrl) form.webPortalUrl.value = s.webPortalUrl;
      }
    } catch (err) { U.handleApiError(err); }

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      try {
        await U.withLoading(CRM_API.saveSettings(U.readForm(form)));
        U.toast('Settings saved', 'ok');
      } catch (err) { U.handleApiError(err); }
    });

    document.getElementById('btn-ping').addEventListener('click', async function () {
      try {
        var r = await U.withLoading(CRM_API.ping());
        document.getElementById('api-status').textContent = 'OK Â· ' + JSON.stringify(r);
        U.toast('API reachable', 'ok');
      } catch (err) {
        document.getElementById('api-status').textContent = err.message;
        U.handleApiError(err);
      }
    });
  }
  CRM_BOOT.register('settings', { title: 'Settings', init: init });
})();
