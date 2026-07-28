/**
 * New Lead form â€” posts to saveLead API only.
 * Model â†’ Variant dependent (Price Master map from server, same as Sheet dialog).
 */
(function () {
  'use strict';

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>New Lead</h1><p>Creates a lead via the business engine. Drafts auto-save locally.</p></div></div>' +
      '<form id="lead-form" class="card card-pad" style="max-width:820px;">' +
        '<div class="form-grid">' +
          '<label class="field"><span>Created Date *</span><input name="createdDate" type="date" required /></label>' +
          '<label class="field"><span>Priority</span><select name="priority"></select></label>' +
          '<label class="field"><span>Customer Name *</span><input name="customerName" required autocomplete="name" /></label>' +
          '<label class="field"><span>Mobile *</span><input name="mobile" maxlength="10" inputmode="numeric" required /></label>' +
          '<label class="field"><span>Lead Source</span><select name="leadSource"></select></label>' +
          '<label class="field"><span>Executive</span><select name="executive"></select></label>' +
          '<label class="field"><span>Model</span><select name="interestedModel" id="model"></select></label>' +
          '<label class="field"><span>Variant</span><select name="variant" id="variant"></select></label>' +
          '<label class="field full"><span>Remarks</span><textarea name="remarks" rows="3"></textarea></label>' +
        '</div>' +
        '<div style="display:flex;gap:8px;margin-top:16px;">' +
          '<button type="submit" class="btn">Create Lead</button>' +
          '<button type="button" class="btn btn-secondary" id="btn-clear-draft">Clear draft</button>' +
        '</div>' +
      '</form>';

    var form = document.getElementById('lead-form');
    form.createdDate.value = U.todayISO();
    U.wireAutoSave(form, 'new-lead');

    var masters = {};
    try {
      CRM_API.clearCache();
      masters = await CRM_API.getMasters() || {};
    } catch (e) {
      U.handleApiError(e);
    }

    function opts(key) {
      return masters[key] || (masters.SECTIONS && masters.SECTIONS[key]) || [];
    }

    var variantByModel = masters.variantByModel || {};

    function listFromMap(model) {
      var m = String(model || '').trim();
      if (!m) return [];
      if (variantByModel[m] && variantByModel[m].length) return variantByModel[m].slice();
      var key = Object.keys(variantByModel).find(function (k) {
        return String(k).toLowerCase() === m.toLowerCase();
      });
      return (key && variantByModel[key]) ? variantByModel[key].slice() : [];
    }

    async function refreshVariants(preserve) {
      var keep = preserve ? String(form.variant.value || '') : '';
      var model = form.interestedModel.value;
      var list = listFromMap(model);

      // If map missing (old deployment), ask server for this model only
      if (!list.length && model) {
        try {
          var remote = await CRM_API.getVariantsForModel(model);
          if (Array.isArray(remote)) list = remote;
        } catch (err) { /* leave empty */ }
      }

      U.fillSelect(form.variant, list, true);
      if (keep && list.indexOf(keep) >= 0) form.variant.value = keep;
    }

    U.fillSelect(form.leadSource, opts('Lead Sources'), true);
    U.fillSelect(form.executive, opts('Executives'), true);
    U.fillSelect(form.priority, opts('Priority'), true);
    U.fillSelect(form.interestedModel, opts('Models'), true);
    U.fillSelect(form.variant, [], true);

    form.interestedModel.addEventListener('change', function () {
      refreshVariants(false);
    });

    U.applyDraftToForm(form, 'new-lead');
    await refreshVariants(true);

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var data = U.readForm(form);
      if (!/^\d{10}$/.test(String(data.mobile || ''))) {
        U.toast('Enter a valid 10-digit mobile number', 'warn');
        return;
      }
      try {
        var res = await U.withLoading(CRM_API.saveLead(data));
        var id = (res && res.data && res.data.leadId) || (res && res.leadId) || (res && res.data) || res;
        U.clearDraft('new-lead');
        U.toast('Lead created: ' + id, 'ok');
        form.reset();
        form.createdDate.value = U.todayISO();
        await refreshVariants(false);
      } catch (err) {
        U.handleApiError(err);
      }
    });

    document.getElementById('btn-clear-draft').addEventListener('click', async function () {
      U.clearDraft('new-lead');
      form.reset();
      form.createdDate.value = U.todayISO();
      await refreshVariants(false);
      U.toast('Draft cleared');
    });
  }

  CRM_BOOT.register('new-lead', { title: 'New Lead', init: init });
})();
