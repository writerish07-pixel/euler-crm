/**
 * App shell — sidebar + topbar (SPA). Nav uses hash routes: #/dashboard
 */
(function (global) {
  'use strict';

  var NAV = [
    { section: 'Overview' },
    { route: 'dashboard', label: 'Dashboard', icon: '▣' },
    { section: 'Pipeline' },
    { route: 'leads', label: 'Leads', icon: '◎' },
    { route: 'new-lead', label: 'New Lead', icon: '+' },
    { route: 'quotation', label: 'Quotation', icon: '₹' },
    { route: 'booking', label: 'Booking', icon: '✓' },
    { route: 'scheme', label: 'Scheme', icon: '◈' },
    { section: 'Operations' },
    { route: 'payment', label: 'Payment', icon: '₹' },
    { route: 'finance', label: 'Finance', icon: '🏦' },
    { route: 'delivery', label: 'Delivery', icon: '🚚' },
    { route: 'activity', label: 'Activity', icon: '☎' },
    { route: 'close-lead', label: 'Close Lead', icon: '✕' },
    { section: 'Insights' },
    { route: 'customer360', label: 'Customer 360', icon: '◉' },
    { route: 'reports', label: 'Reports', icon: '▦' },
    { section: 'Admin' },
    { route: 'masters', label: 'Masters', icon: '☰' },
    { route: 'settings', label: 'Settings', icon: '⚙' }
  ];

  var shellBuilt = false;

  function currentRoute() {
    if (global.CRM_ROUTER && typeof global.CRM_ROUTER.getRoute === 'function') {
      return global.CRM_ROUTER.getRoute();
    }
    var h = (location.hash || '#/dashboard').replace(/^#\/?/, '').split('?')[0];
    return h || 'dashboard';
  }

  function renderShell(options) {
    options = options || {};
    var route = currentRoute();
    var title = options.title || document.title || 'CRM';
    var crumb = options.crumb || title;

    var root = document.getElementById('app-root');
    if (!root) return;

    if (!shellBuilt) {
      var navHtml = NAV.map(function (item) {
        if (item.section) return '<div class="section">' + item.section + '</div>';
        return '<a data-route="' + item.route + '" href="#/' + item.route + '"><span>' + item.icon + '</span><span>' + item.label + '</span></a>';
      }).join('');

      root.innerHTML =
        '<div class="sidebar-backdrop" id="sidebar-backdrop"></div>' +
        '<aside class="sidebar" id="sidebar">' +
          '<div class="brand">' +
            '<div class="name">' + ((global.CRM_CONFIG && global.CRM_CONFIG.APP_NAME) || 'Euler Motors CRM') + '</div>' +
            '<div class="sub">' + ((global.CRM_CONFIG && global.CRM_CONFIG.APP_TAGLINE) || 'Dealer Portal') + '</div>' +
          '</div>' +
          '<nav class="nav">' + navHtml + '</nav>' +
        '</aside>' +
        '<div class="main">' +
          '<header class="topbar">' +
            '<div style="display:flex;align-items:center;gap:10px;">' +
              '<button type="button" class="btn btn-ghost" id="menu-toggle" aria-label="Menu" style="display:none;">☰</button>' +
              '<div class="crumb">CRM / <strong id="crumb-title">' + crumb + '</strong></div>' +
            '</div>' +
            '<div class="topbar-actions">' +
              '<input type="search" id="global-search" placeholder="Search leads… (Ctrl+K)" ' +
                'style="width:220px;border:1px solid var(--border);border-radius:8px;padding:7px 10px;background:var(--card);color:var(--text);font-size:13px;" />' +
              '<button type="button" class="btn btn-secondary" id="theme-toggle" title="Toggle theme">◐</button>' +
              '<span id="user-chip" style="font-size:12px;color:var(--muted);padding:0 6px;">—</span>' +
            '</div>' +
          '</header>' +
          '<div class="content" id="page-content"></div>' +
          '<footer class="footer">Euler Motors · Dealer Management Portal · Open <b>index.html</b> only — one app for all staff</footer>' +
        '</div>';

      shellBuilt = true;
      wireShell();
      loadSessionChip();
    }

    var crumbEl = document.getElementById('crumb-title');
    if (crumbEl) crumbEl.textContent = crumb;
    document.title = title + ' · Euler Motors CRM';

    // Active nav
    var links = document.querySelectorAll('.nav a[data-route]');
    for (var i = 0; i < links.length; i++) {
      links[i].classList.toggle('active', links[i].getAttribute('data-route') === route);
    }

    // Ensure mount points exist for page scripts
    var content = document.getElementById('page-content');
    if (content && options.reset !== false) {
      content.innerHTML = '<div id="page-body"><div id="form-root"></div><div id="dash-root"></div></div>';
    }
  }

  function wireShell() {
    var U = global.CRM_UTIL;
    U.initTheme();

    var toggle = document.getElementById('theme-toggle');
    if (toggle) {
      toggle.addEventListener('click', function () {
        var dark = !document.documentElement.classList.contains('dark');
        U.setTheme(dark ? 'dark' : 'light');
      });
    }

    var menuBtn = document.getElementById('menu-toggle');
    var sidebar = document.getElementById('sidebar');
    var backdrop = document.getElementById('sidebar-backdrop');
    function syncMobile() {
      if (!menuBtn) return;
      if (window.innerWidth <= 960) menuBtn.style.display = '';
      else {
        menuBtn.style.display = 'none';
        sidebar.classList.remove('open');
        backdrop.classList.remove('show');
      }
    }
    syncMobile();
    window.addEventListener('resize', syncMobile);
    if (menuBtn) {
      menuBtn.addEventListener('click', function () {
        sidebar.classList.toggle('open');
        backdrop.classList.toggle('show');
      });
    }
    if (backdrop) {
      backdrop.addEventListener('click', function () {
        sidebar.classList.remove('open');
        backdrop.classList.remove('show');
      });
    }

    var search = document.getElementById('global-search');
    if (search) {
      search.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') {
          var q = search.value.trim();
          if (q) location.hash = '#/leads?q=' + encodeURIComponent(q);
        }
      });
    }
    document.addEventListener('keydown', function (e) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        if (search) search.focus();
      }
    });
  }

  async function loadSessionChip() {
    var chip = document.getElementById('user-chip');
    if (!chip || !global.CRM_API) return;
    try {
      var s = await global.CRM_API.getSession();
      chip.textContent = (s && (s.email || s.companyName)) || 'Signed in';
      if (s && s.companyName) {
        var brand = document.querySelector('.sidebar .brand .name');
        if (brand) brand.textContent = s.companyName;
      }
    } catch (e) {
      chip.textContent = global.CRM_API.isConfigured() ? 'API error' : 'Demo mode';
    }
  }

  function setCrumb(text) {
    var el = document.getElementById('crumb-title');
    if (el) el.textContent = text;
  }

  global.CRM_SHELL = {
    render: renderShell,
    currentRoute: currentRoute,
    setCrumb: setCrumb,
    NAV: NAV,
    resetShell: function () { shellBuilt = false; }
  };
})(window);
