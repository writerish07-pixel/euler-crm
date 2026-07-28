/**
 * SPA bootstrap + hash router.
 * Pages register with CRM_BOOT.register(id, { title, init }).
 * Staff open only index.html — all screens live inside it.
 */
(function (global) {
  'use strict';

  var pages = {};

  function scriptsOk() {
    return global.CRM_CONFIG && global.CRM_API && global.CRM_UTIL && global.CRM_SHELL;
  }

  /** Register a screen (called by each page module at load). */
  function register(id, options) {
    pages[String(id)] = options || {};
  }

  /**
   * Legacy helper — still works: registers under options.route or runs immediately if not SPA.
   * Prefer CRM_BOOT.register in new code.
   */
  function page(options) {
    options = options || {};
    if (options.route) {
      register(options.route, options);
      return;
    }
    // Fallback: run once (old multi-html mode)
    if (!scriptsOk()) {
      console.error('CRM boot: missing core scripts');
      return;
    }
    global.CRM_UTIL.initTheme();
    global.CRM_SHELL.render({ title: options.title, crumb: options.crumb || options.title });
    if (typeof options.init === 'function') {
      Promise.resolve(options.init()).catch(function (err) {
        global.CRM_UTIL.handleApiError(err);
      });
    }
  }

  function getRoute() {
    var raw = (location.hash || '').replace(/^#\/?/, '');
    if (!raw) return 'dashboard';
    var path = raw.split('?')[0].replace(/\.html$/i, '');
    // Map old file names
    var map = {
      'index': 'dashboard',
      'new_lead': 'new-lead',
      'close_lead': 'close-lead',
      'customer-360': 'customer360'
    };
    return map[path] || path || 'dashboard';
  }

  function getQuery() {
    var raw = (location.hash || '').replace(/^#\/?/, '');
    var qi = raw.indexOf('?');
    var out = {};
    if (qi < 0) return out;
    var qs = new URLSearchParams(raw.slice(qi + 1));
    qs.forEach(function (v, k) { out[k] = v; });
    return out;
  }

  function navigate(route, query) {
    var q = '';
    if (query && typeof query === 'object') {
      var parts = [];
      Object.keys(query).forEach(function (k) {
        if (query[k] != null && query[k] !== '') parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(query[k]));
      });
      if (parts.length) q = '?' + parts.join('&');
    }
    location.hash = '#/' + route + q;
  }

  async function show(route) {
    route = route || getRoute();
    var def = pages[route];
    if (!def) {
      def = pages.dashboard;
      route = 'dashboard';
    }
    if (!def) {
      var content = document.getElementById('page-content');
      if (content) content.innerHTML = '<div class="card card-pad empty">Unknown screen. Open Dashboard from the sidebar.</div>';
      return;
    }

    document.title = (def.title || route) + ' · Euler Motors CRM';
    global.CRM_SHELL.render({
      title: def.title || route,
      crumb: def.crumb || def.title || route,
      reset: true
    });

    // Expose query for pages that used URLSearchParams(location.search)
    global.CRM_ROUTE_QUERY = getQuery();

    if (typeof def.init === 'function') {
      try {
        await def.init();
      } catch (err) {
        if (global.CRM_UTIL) global.CRM_UTIL.handleApiError(err);
      }
    }
  }

  function start() {
    if (!scriptsOk()) {
      console.error('CRM SPA: core scripts missing');
      return;
    }
    global.CRM_UTIL.initTheme();
    if (!location.hash || location.hash === '#' || location.hash === '#/') {
      location.replace('#/dashboard');
    }
    window.addEventListener('hashchange', function () { show(getRoute()); });
    show(getRoute());
  }

  global.CRM_PAGES = pages;
  global.CRM_BOOT = { page: page, register: register };
  global.CRM_ROUTER = { start: start, show: show, navigate: navigate, getRoute: getRoute, getQuery: getQuery };
})(window);
