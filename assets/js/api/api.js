/**
 * API client — sole transport to the business engine.
 * Today: Apps Script Web App. Tomorrow: FastAPI. Same contract.
 */
(function (global) {
  'use strict';

  var cache = new Map();
  var inflight = new Map();

  function baseUrl() {
    var u = (global.CRM_CONFIG && global.CRM_CONFIG.API_BASE_URL) || '';
    return String(u).replace(/\/+$/, '');
  }

  function isConfigured() {
    return !!baseUrl();
  }

  function timeoutMs() {
    return (global.CRM_CONFIG && global.CRM_CONFIG.REQUEST_TIMEOUT_MS) || 45000;
  }

  function ApiError(message, code, raw) {
    var err = new Error(message || 'Request failed');
    err.name = 'ApiError';
    err.code = code || 'ERROR';
    err.raw = raw;
    return err;
  }

  async function request(action, payload, options) {
    options = options || {};
    var method = (options.method || 'POST').toUpperCase();
    var url = baseUrl();
    var key = action + '::' + JSON.stringify(payload || {});

    if (!url) {
      if (global.CRM_CONFIG && global.CRM_CONFIG.ALLOW_DEMO) {
        return demoResponse_(action, payload);
      }
      throw ApiError(
        'API_BASE_URL is not set. Deploy WebApi.gs and paste the Web App URL into assets/js/config.js.',
        'NO_API'
      );
    }

    if (options.cache && method === 'GET' && cache.has(key)) {
      return cache.get(key);
    }
    if (options.dedupe !== false && inflight.has(key)) {
      return inflight.get(key);
    }

    var controller = new AbortController();
    var timer = setTimeout(function () { controller.abort(); }, timeoutMs());

    var promise = (async function () {
      try {
        // Apps Script Web Apps: use text/plain to avoid CORS preflight.
        // Same JSON body; Content-Type application/json triggers OPTIONS which GAS rejects.
        var fetchOpts = {
          method: method,
          signal: controller.signal,
          credentials: 'omit',
          redirect: 'follow',
          headers: { 'Content-Type': 'text/plain;charset=utf-8', 'Accept': 'application/json' }
        };
        if (method === 'GET') {
          var qs = new URLSearchParams({ action: action });
          if (payload && typeof payload === 'object') {
            Object.keys(payload).forEach(function (k) {
              if (payload[k] != null && payload[k] !== '') qs.set(k, String(payload[k]));
            });
          }
          url = url + (url.indexOf('?') >= 0 ? '&' : '?') + qs.toString();
        } else {
          fetchOpts.body = JSON.stringify({ action: action, payload: payload || {} });
        }

        var res = await fetch(url, fetchOpts);
        var text = await res.text();
        var trimmed = String(text || '').trim();
        if (!trimmed) {
          throw ApiError('Empty response from API', 'BAD_RESPONSE');
        }
        if (trimmed.charAt(0) === '<') {
          var htmlMsg = 'Apps Script returned HTML instead of JSON.';
          if (/Script function not found:\s*do(Get|Post)/i.test(trimmed)) {
            htmlMsg = 'WebApi.gs is not in this deployment (doGet/doPost missing). Paste WebApi.gs into Apps Script, then Deploy → Manage deployments → New version.';
          } else if (/Authorization|Sign in|accounts\.google/i.test(trimmed)) {
            htmlMsg = 'Apps Script requires login. Redeploy Web App with access: Anyone.';
          }
          throw ApiError(htmlMsg, 'GAS_HTML');
        }
        var json;
        try {
          json = JSON.parse(trimmed);
        } catch (parseErr) {
          throw ApiError('Invalid JSON from server', 'BAD_RESPONSE');
        }
        if (!json || json.ok === false) {
          var e = (json && json.error) || {};
          throw ApiError(e.message || 'Request failed', e.code || 'ERROR', json);
        }
        var data = json.data;
        // Normalize Apps Script structured failures that still return HTTP 200 + ok:true
        if (data && data.success === false) {
          var msg = (data.error && data.error.message) || data.message || 'Operation failed';
          var code = (data.error && data.error.code) || 'BUSINESS';
          throw ApiError(msg, code, data);
        }
        if (options.cache) cache.set(key, data);
        return data;
      } catch (err) {
        if (err.name === 'AbortError') throw ApiError('Request timed out. Please retry.', 'TIMEOUT');
        if (err.name === 'ApiError') throw err;
        if (!navigator.onLine) throw ApiError('You appear to be offline.', 'OFFLINE');
        if (location.protocol === 'file:') {
          throw ApiError(
            'Cannot call API from file://. Run a local server in euler-crm-portal (npx serve .) then open http://localhost:3000',
            'FILE_PROTOCOL'
          );
        }
        throw ApiError(
          (err.message || 'Network error') +
            ' — Check API_BASE_URL, WebApi.gs deployment (doGet/doPost), and Web App access = Anyone.',
          'NETWORK',
          err
        );
      } finally {
        clearTimeout(timer);
        inflight.delete(key);
      }
    })();

    inflight.set(key, promise);
    return promise;
  }

  function demoResponse_(action) {
    if (action === 'ping' || action === 'getSession') {
      return { email: 'demo@local', companyName: 'Euler Motors CRM (Demo)', version: 'demo' };
    }
    if (action === 'getDashboard') {
      return {
        metrics: {
          todayLeads: 0, todayBookings: 0, todayDeliveries: 0,
          pendingDeliveries: 0, pendingPayments: 0, outstanding: 0,
          customerOutstanding: 0, financeOutstanding: 0, financeOverdueCount: 0,
          monthlyLeads: 0, monthlyBookings: 0, monthlyDeliveries: 0, conversion: 0,
          paymentsCash: 0, paymentsUpi: 0, paymentsFinance: 0, paymentsOther: 0,
          revenue: 0
        },
        generatedAt: new Date().toISOString()
      };
    }
    if (action === 'getLeads' || action === 'getActiveLeads') return [];
    if (action === 'getMasters') return {};
    if (action === 'getSettings') return { companyName: 'Euler Motors CRM', webPortalUrl: '' };
    return { success: true, demo: true };
  }

  function clearCache() { cache.clear(); }

  var api = {
    isConfigured: isConfigured,
    clearCache: clearCache,
    request: request,

    ping: function () { return request('ping', {}, { method: 'GET' }); },
    getSession: function () { return request('getSession', {}, { method: 'GET', cache: true }); },
    getDashboard: function () { return request('getDashboard', {}); },
    refreshDashboard: function () { return request('refreshDashboard', {}); },

    getLeads: function (opts) {
      // Never cache lead lists — stage eligibility changes after each save
      return request('getLeads', opts || {}, { cache: false });
    },
    searchLeads: function (q) { return request('searchLeads', { q: q }); },
    saveLead: function (payload) { return request('saveLead', payload); },
    getLeadContext: function (leadId) { return request('getLeadContext', { leadId: leadId }); },

    getQuotationContext: function (p) { return request('getQuotationContext', p); },
    saveQuotation: function (p) { return request('saveQuotation', p); },

    getBookingContext: function (leadId) { return request('getBookingContext', { leadId: leadId }); },
    getPriceForBooking: function (p) { return request('getPriceForBooking', p); },
    convertBooking: function (p) { return request('convertBooking', p); },

    getSchemeContext: function (leadId) { return request('getSchemeContext', { leadId: leadId }); },
    getSchemeRules: function (p) { return request('getSchemeRules', p); },
    updateScheme: function (p) { return request('updateScheme', p); },

    getPriceStructureContext: function (leadId) {
      return request('getPriceStructureContext', { leadId: leadId });
    },
    savePriceStructure: function (p) { return request('savePriceStructure', p); },

    savePayment: function (p) { return request('savePayment', p); },

    getPendingFinanceFiles: function () { return request('getPendingFinanceFiles', {}); },
    saveFinanceReceipt: function (p) { return request('saveFinanceReceipt', p); },

    getDeliveryContext: function (leadId) { return request('getDeliveryContext', { leadId: leadId }); },
    markDelivered: function (p) { return request('markDelivered', p); },

    getCloseLeadContext: function (leadId) { return request('getCloseLeadContext', { leadId: leadId }); },
    closeLead: function (p) { return request('closeLead', p); },

    saveActivity: function (p) { return request('saveActivity', p); },
    getCustomer360: function (leadId) { return request('getCustomer360', { leadId: leadId }); },

    getMasters: function () { return request('getMasters', {}, { cache: true }); },
    getVariantsForModel: function (model) {
      return request('getVariantsForModel', { model: model });
    },
    getSettings: function () { return request('getSettings', {}); },
    saveSettings: function (p) { return request('saveSettings', p); },

    getOpenClaims: function () { return request('getOpenClaims', {}); },
    getClaimContext: function (claimId) { return request('getClaimContext', { claimId: claimId }); },
    settleClaim: function (p) { return request('settleClaim', p); },
    updateClaimStatus: function (p) { return request('updateClaimStatus', p); }
  };

  global.CRM_API = api;
})(window);
