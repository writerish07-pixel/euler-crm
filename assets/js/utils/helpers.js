/**
 * Shared helpers — formatting, DOM, validation, drafts, debounce.
 */
(function (global) {
  'use strict';

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $all(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }

  function formatINR(n) {
    var x = Number(n);
    if (!isFinite(x)) return '—';
    return new Intl.NumberFormat('en-IN', {
      style: 'currency', currency: 'INR', maximumFractionDigits: 0
    }).format(x);
  }

  function formatNumber(n, digits) {
    var x = Number(n);
    if (!isFinite(x)) return '—';
    return new Intl.NumberFormat('en-IN', {
      maximumFractionDigits: digits == null ? 0 : digits
    }).format(x);
  }

  function formatPct(n) {
    var x = Number(n);
    if (!isFinite(x)) return '—';
    return (x <= 1 ? x * 100 : x).toFixed(1) + '%';
  }

  function todayISO() {
    var d = new Date();
    var m = String(d.getMonth() + 1).padStart(2, '0');
    var day = String(d.getDate()).padStart(2, '0');
    return d.getFullYear() + '-' + m + '-' + day;
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var ctx = this, args = arguments;
      clearTimeout(t);
      t = setTimeout(function () { fn.apply(ctx, args); }, ms || 300);
    };
  }

  function toast(message, type) {
    var host = document.getElementById('toast-host');
    if (!host) {
      host = document.createElement('div');
      host.id = 'toast-host';
      host.className = 'toast-host';
      document.body.appendChild(host);
    }
    var el = document.createElement('div');
    el.className = 'toast ' + (type || '');
    el.textContent = message;
    host.appendChild(el);
    setTimeout(function () {
      el.style.opacity = '0';
      el.style.transition = 'opacity .25s';
      setTimeout(function () { el.remove(); }, 280);
    }, 3200);
  }

  var overlayEl;
  function showLoading(show) {
    if (!overlayEl) {
      overlayEl = document.createElement('div');
      overlayEl.className = 'overlay';
      overlayEl.innerHTML = '<div class="spinner" aria-label="Loading"></div>';
      document.body.appendChild(overlayEl);
    }
    overlayEl.classList.toggle('show', !!show);
  }

  async function withLoading(promise) {
    showLoading(true);
    try { return await promise; }
    finally { showLoading(false); }
  }

  function confirmDialog(message, title) {
    return new Promise(function (resolve) {
      var ok = window.confirm((title ? title + '\n\n' : '') + message);
      resolve(ok);
    });
  }

  function readForm(form) {
    var data = {};
    var fd = new FormData(form);
    fd.forEach(function (v, k) {
      if (data[k] !== undefined) {
        if (!Array.isArray(data[k])) data[k] = [data[k]];
        data[k].push(v);
      } else {
        data[k] = v;
      }
    });
    $all('[data-number]', form).forEach(function (el) {
      if (el.name) data[el.name] = el.value === '' ? '' : Number(el.value);
    });
    return data;
  }

  function fillSelect(select, options, includeBlank) {
    if (!select) return;
    var html = includeBlank ? '<option value="">— Select —</option>' : '';
    (options || []).forEach(function (o) {
      var v = typeof o === 'string' ? o : (o.value != null ? o.value : o.label);
      var label = typeof o === 'string' ? o : (o.label != null ? o.label : o.value);
      html += '<option value="' + escapeAttr(v) + '">' + escapeHtml(label) + '</option>';
    });
    select.innerHTML = html;
  }

  function escapeHtml(s) {
    return String(s == null ? '' : s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/'/g, '&#39;'); }

  function draftKey(page) { return 'euler_draft_' + page; }
  function saveDraft(page, data) {
    try { localStorage.setItem(draftKey(page), JSON.stringify({ at: Date.now(), data: data })); } catch (e) {}
  }
  function loadDraft(page) {
    try {
      var raw = localStorage.getItem(draftKey(page));
      return raw ? JSON.parse(raw) : null;
    } catch (e) { return null; }
  }
  function clearDraft(page) {
    try { localStorage.removeItem(draftKey(page)); } catch (e) {}
  }

  function applyDraftToForm(form, page) {
    var d = loadDraft(page);
    if (!d || !d.data) return false;
    Object.keys(d.data).forEach(function (k) {
      var el = form.elements[k];
      if (!el) return;
      if (el.type === 'checkbox') el.checked = !!d.data[k];
      else el.value = d.data[k];
    });
    return true;
  }

  function wireAutoSave(form, page) {
    var save = debounce(function () {
      saveDraft(page, readForm(form));
    }, 600);
    form.addEventListener('input', save);
    form.addEventListener('change', save);
  }

  function setTheme(mode) {
    var dark = mode === 'dark';
    document.documentElement.classList.toggle('dark', dark);
    try {
      localStorage.setItem((global.CRM_CONFIG && global.CRM_CONFIG.THEME_KEY) || 'euler_crm_theme', dark ? 'dark' : 'light');
    } catch (e) {}
  }

  function initTheme() {
    var key = (global.CRM_CONFIG && global.CRM_CONFIG.THEME_KEY) || 'euler_crm_theme';
    var saved = null;
    try { saved = localStorage.getItem(key); } catch (e) {}
    if (saved === 'dark' || (!saved && window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches)) {
      document.documentElement.classList.add('dark');
    }
  }

  function handleApiError(err) {
    var msg = (err && err.message) || 'Something went wrong';
    if (err && err.code === 'OFFLINE') toast(msg, 'warn');
    else if (err && err.code === 'TIMEOUT') toast(msg + ' Tap retry.', 'warn');
    else toast(msg, 'err');
    return err;
  }

  global.CRM_UTIL = {
    $, $all, formatINR, formatNumber, formatPct, todayISO, debounce,
    toast, showLoading, withLoading, confirmDialog, readForm, fillSelect,
    escapeHtml, escapeAttr, saveDraft, loadDraft, clearDraft, applyDraftToForm,
    wireAutoSave, setTheme, initTheme, handleApiError
  };
})(window);
