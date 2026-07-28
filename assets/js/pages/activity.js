(function () {
  'use strict';
  async function init() {
    var U = CRM_UTIL;
    var masters = {};
    try { masters = await CRM_API.getMasters() || {}; } catch (e) {}
    var types = masters['Activity Types'] || ['Call', 'Visit', 'Follow-up', 'WhatsApp', 'Email'];
    var execs = masters['Executives'] || [];

    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Add Activity</h1><p>Follow-ups on open leads. Outstanding shown for reference.</p></div></div>' +
      '<form id="a-form" class="card card-pad" style="max-width:720px;">' +
        '<div id="picker"></div>' +
        '<div id="ctx"></div>' +
        '<div class="form-grid">' +
          '<label class="field"><span>Activity Type *</span><select name="activityType"></select></label>' +
          '<label class="field"><span>Executive</span><select name="executive"></select></label>' +
          '<label class="field"><span>Next Follow-up</span><input name="nextFollowUp" type="date" /></label>' +
          '<label class="field full"><span>Discussion</span><textarea name="discussion" rows="4"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:14px;"><button type="submit" class="btn">Add Activity</button></div>' +
      '</form>';

    var form = document.getElementById('a-form');
    var ctxEl = document.getElementById('ctx');
    U.fillSelect(form.activityType, types, false);
    U.fillSelect(form.executive, execs, true);
    U.wireAutoSave(form, 'activity');
    CRM_CONTEXT.clear(ctxEl);

    var picker = await CRM_LEAD_PICKER.mount(document.getElementById('picker'), {
      activeOnly: true,
      stage: 'activity',
      onChange: async function (id) {
        if (!id) { CRM_CONTEXT.clear(ctxEl); return; }
        try {
          var ctx = await CRM_API.getSchemeContext(id);
          CRM_CONTEXT.render(ctxEl, ctx);
        } catch (err) {
          try {
            var b = await CRM_API.getBookingContext(id);
            CRM_CONTEXT.render(ctxEl, b);
          } catch (e2) {
            CRM_CONTEXT.clear(ctxEl);
          }
        }
      }
    });

    form.addEventListener('submit', async function (e) {
      e.preventDefault();
      var data = U.readForm(form);
      data.leadId = picker.getLeadId();
      if (!data.leadId) { U.toast('Select a lead', 'warn'); return; }
      try {
        var res = await U.withLoading(CRM_API.saveActivity(data));
        U.clearDraft('activity');
        var id = (res && res.data && res.data.activityId) || (res && res.activityId) || 'saved';
        U.toast('Activity added: ' + id, 'ok');
        form.discussion.value = '';
      } catch (err) { U.handleApiError(err); }
    });
  }
  CRM_BOOT.register('activity', { title: 'Activity', init: init });
})();
