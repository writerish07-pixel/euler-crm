/**
 * Claims — update status + record OEM receipt (mirrors Spreadsheet Claims menu).
 * Settles per claim ID (one row per scheme component with company share).
 */
(function () {
  'use strict';

  function num(v) { var n = Number(v); return isFinite(n) ? n : 0; }

  async function init() {
    var U = CRM_UTIL;
    var root = document.getElementById('form-root');
    root.innerHTML =
      '<div class="page-header"><div><h1>Claims</h1>' +
      '<p>Update claim status or record OEM payment received. Each scheme component settles separately.</p></div></div>' +
      '<div class="card card-pad" style="max-width:720px;">' +
        '<label class="field"><span>Open claim *</span><select id="claimId"></select></label>' +
        '<div id="claimCtx" class="sheet-status" style="margin:8px 0;">Select a claim…</div>' +
        '<h4 class="sheet-h4">Update Status</h4>' +
        '<div class="form-grid">' +
          '<label class="field"><span>Status</span>' +
            '<select id="status">' +
              '<option>Pending</option><option>Submitted</option><option>Approved</option>' +
              '<option>Rejected</option><option>Not Applicable</option>' +
            '</select></label>' +
          '<label class="field"><span>Claim Reference</span><input id="statusRef" /></label>' +
          '<label class="field full"><span>Remarks</span><textarea id="statusRemarks" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin:12px 0;"><button type="button" class="btn btn-secondary" id="btn-status">Update Status</button></div>' +
        '<hr style="border:none;border-top:1px solid var(--border);margin:16px 0;" />' +
        '<h4 class="sheet-h4">Record Claim Received</h4>' +
        '<div class="form-grid">' +
          '<label class="field"><span>Received Date *</span><input id="receivedDate" type="date" /></label>' +
          '<label class="field"><span>Received Amount *</span><input id="receivedAmount" type="number" min="0" step="0.01" /></label>' +
          '<label class="field"><span>UTR / OEM Reference *</span><input id="reference" /></label>' +
          '<label class="field full"><span>Remarks</span><textarea id="settleRemarks" rows="2"></textarea></label>' +
        '</div>' +
        '<div style="margin-top:12px;"><button type="button" class="btn" id="btn-settle">Save Claim Receipt</button></div>' +
      '</div>';

    document.getElementById('receivedDate').value = U.todayISO();
    await reloadClaims();

    document.getElementById('claimId').addEventListener('change', onClaimChange);
    document.getElementById('btn-status').addEventListener('click', doStatus);
    document.getElementById('btn-settle').addEventListener('click', doSettle);
  }

  var CLAIMS = [];

  async function reloadClaims() {
    var U = CRM_UTIL;
    var sel = document.getElementById('claimId');
    CLAIMS = [];
    try {
      var res = await U.withLoading(CRM_API.getOpenClaims());
      var data = (res && res.data) || res || {};
      CLAIMS = data.claims || (Array.isArray(res) ? res : []) || [];
    } catch (err) {
      U.handleApiError(err);
    }
    sel.innerHTML = '<option value="">— Select —</option>' + CLAIMS.map(function (c) {
      return '<option value="' + String(c.claimId).replace(/"/g, '') + '">' +
        String(c.label || c.claimId).replace(/</g, '') + '</option>';
    }).join('');
    document.getElementById('claimCtx').textContent =
      CLAIMS.length ? (CLAIMS.length + ' open claim(s). Pick one.') : 'No open claims.';
  }

  function selected() {
    var id = document.getElementById('claimId').value;
    return CLAIMS.find(function (c) { return String(c.claimId) === String(id); }) || null;
  }

  async function onClaimChange() {
    var U = CRM_UTIL;
    var c = selected();
    var box = document.getElementById('claimCtx');
    if (!c) { box.textContent = 'Select a claim…'; return; }
    box.textContent = 'Loading ' + c.claimId + '…';
    try {
      var res = await CRM_API.getClaimContext(c.claimId);
      var data = (res && res.data) || res || {};
      var claim = data.claim || c;
      box.textContent =
        (claim.component ? claim.component + ' · ' : '') +
        (claim.customer || claim.leadId || '') +
        ' · Claim ₹' + num(claim.claimAmount) +
        ' · Status: ' + (claim.status || '');
      document.getElementById('status').value = claim.status || 'Pending';
      document.getElementById('statusRef').value = claim.reference || '';
      document.getElementById('receivedAmount').value = num(claim.receivedAmount || claim.claimAmount);
      document.getElementById('reference').value = claim.reference || '';
    } catch (err) {
      box.textContent = (c.label || c.claimId);
      document.getElementById('receivedAmount').value = num(c.claimAmount);
    }
  }

  async function doStatus() {
    var U = CRM_UTIL;
    var c = selected();
    if (!c) { U.toast('Select a claim', 'warn'); return; }
    try {
      var res = await U.withLoading(CRM_API.updateClaimStatus({
        claimId: c.claimId,
        status: document.getElementById('status').value,
        reference: document.getElementById('statusRef').value,
        remarks: document.getElementById('statusRemarks').value
      }));
      U.toast((res && res.message) || 'Status updated', 'ok');
      await reloadClaims();
    } catch (err) { U.handleApiError(err); }
  }

  async function doSettle() {
    var U = CRM_UTIL;
    var c = selected();
    if (!c) { U.toast('Select a claim', 'warn'); return; }
    var amt = num(document.getElementById('receivedAmount').value);
    var utr = String(document.getElementById('reference').value || '').trim();
    var dt = document.getElementById('receivedDate').value;
    if (!(amt > 0)) { U.toast('Enter received amount', 'warn'); return; }
    if (!utr) { U.toast('UTR / OEM reference is required', 'warn'); return; }
    if (!dt) { U.toast('Received date is required', 'warn'); return; }
    try {
      var res = await U.withLoading(CRM_API.settleClaim({
        claimId: c.claimId,
        receivedDate: dt,
        receivedAmount: amt,
        reference: utr,
        remarks: document.getElementById('settleRemarks').value
      }));
      U.toast((res && res.message) || 'Claim receipt saved', 'ok');
      await reloadClaims();
      document.getElementById('claimCtx').textContent = 'Receipt saved for ' + c.claimId;
    } catch (err) { U.handleApiError(err); }
  }

  CRM_BOOT.register('claims', { title: 'Claims', init: init });
})();
