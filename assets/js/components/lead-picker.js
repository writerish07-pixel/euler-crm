/**
 * Lead picker — client-side filter (like Sheet dialog) + stage exclusion.
 * Stages mirror Spreadsheet CRM menus:
 *   booking  → hide already booked / delivered
 *   scheme   → only booked, hide if scheme already updated
 *   payment  → booked (or any with outstanding)
 *   delivery → hide already delivered
 *   close    → active leads for accounts close
 *   activity → active open leads
 */
(function (global) {
  'use strict';

  function passesStage(l, stage) {
    if (!stage) return true;
    var cs = String(l.currentStatus || '').toLowerCase();
    var ds = String(l.deliveryStatus || '').toLowerCase();
    var booked = !!(l.isBooked || cs === 'booked' || cs === 'delivered' ||
      Number(l.bookingAmount || 0) > 0 || String(l.bookingDate || '').trim() || String(l.bookingId || '').trim());
    var delivered = ds === 'delivered' || cs === 'delivered';
    var hasScheme = !!l.hasScheme;

    if (stage === 'booking') {
      return !booked && !delivered;
    }
    if (stage === 'scheme') {
      return booked && !delivered && !hasScheme;
    }
    if (stage === 'quotation') {
      return !delivered;
    }
    if (stage === 'payment') {
      return booked && !delivered;
    }
    if (stage === 'delivery') {
      return booked && !delivered;
    }
    if (stage === 'close') {
      return String(l.accountStatus || 'Active') === 'Active';
    }
    if (stage === 'activity') {
      return !delivered && String(l.accountStatus || 'Active') === 'Active';
    }
    return true;
  }

  function matchesQuery(l, q) {
    if (!q) return true;
    var key = String(l.searchKey || [
      l.leadId, l.customerName || l.name, l.mobile, l.model || l.interestedModel, l.variant
    ].join(' ')).toUpperCase();
    return key.indexOf(q.toUpperCase()) >= 0;
  }

  async function mountLeadPicker(container, options) {
    options = options || {};
    var U = global.CRM_UTIL;
    var API = global.CRM_API;
    var stage = options.stage || '';

    container.innerHTML =
      '<label class="field full">' +
        '<span>Lead *</span>' +
        '<input type="search" data-role="q" placeholder="Type name, mobile or lead ID…" autocomplete="off" />' +
        '<select data-role="lead" size="8" style="margin-top:6px;min-height:160px;"></select>' +
        '<input type="hidden" name="' + (options.name || 'leadId') + '" data-role="hidden" />' +
      '</label>' +
      '<div data-role="meta" style="font-size:12px;color:var(--muted);margin-top:4px;"></div>';

    var qEl = container.querySelector('[data-role="q"]');
    var sel = container.querySelector('[data-role="lead"]');
    var hidden = container.querySelector('[data-role="hidden"]');
    var meta = container.querySelector('[data-role="meta"]');
    var allLeads = [];
    var visible = [];

    async function load() {
      try {
        var res = await API.getLeads({
          activeOnly: options.activeOnly !== false,
          stage: stage
        });
        allLeads = Array.isArray(res) ? res : (res && (res.leads || res.items)) || [];
        // Client-side stage filter (works even if API is older deployment)
        allLeads = allLeads.filter(function (l) { return passesStage(l, stage); });
        applyFilter();
      } catch (err) {
        U.handleApiError(err);
        allLeads = [];
        visible = [];
        render();
      }
    }

    function applyFilter() {
      var q = (qEl.value || '').trim();
      visible = allLeads.filter(function (l) { return matchesQuery(l, q); });
      render();
    }

    function render() {
      if (!visible.length) {
        sel.innerHTML = '<option value="">' +
          (allLeads.length ? 'No match for search' : 'No eligible leads for this step') +
          '</option>';
        hidden.value = '';
        meta.textContent = allLeads.length
          ? ('0 of ' + allLeads.length + ' eligible · refine search')
          : (stage ? ('No leads pending for “' + stage + '”') : 'No leads');
        return;
      }
      sel.innerHTML = visible.map(function (l) {
        var id = l.leadId || l.id || '';
        var label = [
          id,
          l.customerName || l.name || '',
          l.mobile || '',
          l.interestedModel || l.model || '',
          l.currentStatus || ''
        ].filter(Boolean).join(' · ');
        return '<option value="' + U.escapeAttr(id) + '">' + U.escapeHtml(label) + '</option>';
      }).join('');

      if (options.preselect && visible.some(function (l) {
        return String(l.leadId || l.id) === String(options.preselect);
      })) {
        sel.value = options.preselect;
        hidden.value = options.preselect;
      } else {
        // Don't auto-select first — user must pick (prevents wrong context)
        sel.selectedIndex = -1;
        hidden.value = '';
      }
      meta.textContent = visible.length + ' of ' + allLeads.length + ' eligible lead(s)';
    }

    function emitChange() {
      hidden.value = sel.value;
      if (typeof options.onChange === 'function') {
        var lead = visible.find(function (l) { return String(l.leadId || l.id) === sel.value; }) ||
          allLeads.find(function (l) { return String(l.leadId || l.id) === sel.value; });
        options.onChange(sel.value, lead);
      }
    }

    sel.addEventListener('change', emitChange);
    qEl.addEventListener('input', U.debounce(applyFilter, 120));

    await load();

    return {
      getLeadId: function () { return hidden.value || sel.value; },
      getLead: function () {
        var id = hidden.value || sel.value;
        return allLeads.find(function (l) { return String(l.leadId || l.id) === id; });
      },
      reload: load,
      stage: stage
    };
  }

  global.CRM_LEAD_PICKER = { mount: mountLeadPicker, passesStage: passesStage };
})(window);
