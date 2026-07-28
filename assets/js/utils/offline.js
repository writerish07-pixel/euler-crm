/**
 * Online/offline banner + global error redirect helper.
 */
(function () {
  'use strict';
  function sync() {
    if (!navigator.onLine) {
      if (location.pathname.indexOf('offline') < 0) {
        // soft banner only — don't force navigate mid-form
        if (window.CRM_UTIL) CRM_UTIL.toast('You appear to be offline', 'warn');
      }
    }
  }
  window.addEventListener('offline', sync);
  window.addEventListener('online', function () {
    if (window.CRM_UTIL) CRM_UTIL.toast('Back online', 'ok');
  });
})();
