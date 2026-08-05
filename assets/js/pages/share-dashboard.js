/**
 * Company share board — active bookings & retail (deliveries).
 * Standalone page: share.html (no CRM shell / no edit forms).
 */
(function () {
  'use strict';

  var REFRESH_MS = 3 * 60 * 1000;
  var root = document.getElementById('share-root');

  function esc(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function baseUrl() {
    var u = (window.CRM_CONFIG && window.CRM_CONFIG.API_BASE_URL) || '';
    return String(u).replace(/\/+$/, '');
  }

  function fmtDate(d) {
    var s = String(d || '');
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) {
      var p = s.slice(0, 10).split('-');
      return p[2] + '/' + p[1];
    }
    return s || '—';
  }

  async function fetchShare() {
    var url = baseUrl();
    if (!url) throw new Error('API_BASE_URL not set in assets/js/config.js');
    var res = await fetch(url, {
      method: 'POST',
      credentials: 'omit',
      redirect: 'follow',
      headers: { 'Content-Type': 'text/plain;charset=utf-8', Accept: 'application/json' },
      body: JSON.stringify({ action: 'getShareDashboard', payload: {} })
    });
    var text = await res.text();
    var json = JSON.parse(text);
    if (!json || json.ok === false) {
      var e = (json && json.error) || {};
      throw new Error(e.message || 'Failed to load share dashboard');
    }
    return json.data || {};
  }

  function rowsHtml(list, dateKey, badgeClass, badgeLabel, emptyMsg) {
    if (!list || !list.length) {
      return '<div class="empty-list">' + esc(emptyMsg || 'No records yet.') + '</div>';
    }
    return '<div class="list">' + list.map(function (r) {
      return '<div class="row">' +
        '<div class="row-date">' + esc(fmtDate(r[dateKey])) + '</div>' +
        '<div class="row-main">' +
          '<div class="row-name">' + esc(r.customerName || r.leadId || '—') + '</div>' +
          '<div class="row-sub">' + esc([r.model, r.variant].filter(Boolean).join(' · ') || '—') +
            (r.executive ? ' · ' + esc(r.executive) : '') + '</div>' +
        '</div>' +
        '<div class="row-badge ' + badgeClass + '">' + esc(badgeLabel) + '</div>' +
      '</div>';
    }).join('') + '</div>';
  }

  function chipsHtml(items) {
    if (!items || !items.length) return '';
    return '<div class="models">' + items.map(function (m) {
      return '<span class="chip">' + esc(m.model) + '<b>' + esc(m.count) + '</b></span>';
    }).join('') + '</div>';
  }

  function render(data) {
    var company = data.companyName || 'Euler Motors';
    var month = data.monthLabel || 'This month';
    var activeCount = data.activeBookings != null ? data.activeBookings : (data.bookings || []).length;
    var newThisMonth = data.monthlyBookings || 0;
    root.innerHTML =
      '<header class="share-hero">' +
        '<h1 class="share-brand"><span>' + esc(company) + '</span></h1>' +
        '<p class="share-tag">Active bookings &amp; retail for ' + esc(month) +
          ' — shared with the company team.</p>' +
        '<div class="share-meta">' +
          '<span class="share-pill"><span class="share-dot"></span> Live</span>' +
          '<span>Updated <strong>' + esc(data.generatedAt || '—') + '</strong></span>' +
          '<span>Today <strong>' + esc(data.today || '') + '</strong></span>' +
        '</div>' +
      '</header>' +

      '<section class="share-kpis" aria-label="Key numbers">' +
        '<article class="kpi book">' +
          '<div class="kpi-label">Active bookings</div>' +
          '<div class="kpi-value">' + esc(activeCount) + '</div>' +
          '<div class="kpi-hint">' + esc(newThisMonth) + ' new in ' + esc(month) + '</div>' +
        '</article>' +
        '<article class="kpi retail">' +
          '<div class="kpi-label">Retail · ' + esc(month) + '</div>' +
          '<div class="kpi-value">' + esc(data.monthlyRetail || 0) + '</div>' +
          '<div class="kpi-hint">Deliveries / retail this month</div>' +
        '</article>' +
        '<article class="kpi today">' +
          '<div class="kpi-label">Today bookings</div>' +
          '<div class="kpi-value">' + esc(data.todayBookings || 0) + '</div>' +
          '<div class="kpi-hint">Booked today</div>' +
        '</article>' +
        '<article class="kpi today">' +
          '<div class="kpi-label">Today retail</div>' +
          '<div class="kpi-value">' + esc(data.todayRetail || 0) + '</div>' +
          '<div class="kpi-hint">Delivered today</div>' +
        '</article>' +
      '</section>' +

      '<section class="share-grid">' +
        '<div class="panel">' +
          '<div class="panel-head"><h2>Bookings</h2><span>' + esc(activeCount) + ' active</span></div>' +
          chipsHtml(data.topBookingModels) +
          rowsHtml(data.bookings, 'bookingDate', '', 'Booked', 'No active bookings yet.') +
        '</div>' +
        '<div class="panel">' +
          '<div class="panel-head"><h2>Retail</h2><span>' + esc((data.retails || []).length) + ' MTD</span></div>' +
          chipsHtml(data.topRetailModels) +
          rowsHtml(data.retails, 'deliveryDate', 'retail', 'Retail', 'No records this month yet.') +
        '</div>' +
      '</section>' +

      '<footer class="share-foot">' +
        '<div>Read-only board · no customer mobiles shown</div>' +
        '<div><button type="button" id="btn-refresh">Refresh</button></div>' +
      '</footer>';

    var btn = document.getElementById('btn-refresh');
    if (btn) btn.addEventListener('click', load);
  }

  async function load() {
    root.innerHTML = '<p class="share-loading">Loading board…</p>';
    try {
      var data = await fetchShare();
      render(data);
    } catch (err) {
      root.innerHTML =
        '<p class="share-error">' + esc(err.message || err) + '</p>' +
        '<p class="share-loading">Deploy WebApi.gs with getShareDashboard, then refresh.</p>';
    }
  }

  load();
  setInterval(load, REFRESH_MS);
})();
