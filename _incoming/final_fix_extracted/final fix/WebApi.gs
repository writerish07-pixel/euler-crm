/**
 * WebApi.gs — JSON REST bridge for the Euler CRM Web Portal.
 *
 * PURPOSE
 *   Expose EXISTING dialog / service entry points as JSON.
 *   No business logic lives here. Frontend is presentation-only.
 *
 * DEPLOY
 *   Deploy → New deployment → Web app
 *   Execute as: Me
 *   Who has access: Anyone with Google account (or your org)
 *   Copy the Web App URL into web-portal assets/js/config.js → API_BASE_URL
 *
 * CONTRACT
 *   POST { action: "saveLead", payload: {...} }
 *   GET  ?action=getDashboard
 *   Response always: { ok: boolean, data?: any, error?: { message, code } }
 */

function doGet(e) {
  return webApiHandle_(e, 'GET');
}

function doPost(e) {
  return webApiHandle_(e, 'POST');
}

/** CORS preflight for hosted static portal. */
function doOptions() {
  return webApiJson_({ ok: true }, 204);
}

function webApiHandle_(e, method) {
  e = e || {};
  try {
    var params = (e.parameter) || {};
    var body = {};
    if (e.postData && e.postData.contents) {
      try { body = JSON.parse(e.postData.contents); } catch (parseErr) {
        return webApiJson_({ ok: false, error: { message: 'Invalid JSON body', code: 'BAD_JSON' } }, 400);
      }
    }
    var action = String(body.action || params.action || '').trim();
    var payload = body.payload !== undefined ? body.payload : (body.data !== undefined ? body.data : params);
    if (payload && typeof payload === 'object' && payload.action) {
      // strip routing keys if client nested oddly
      payload = Object.assign({}, payload);
      delete payload.action;
    }
    if (!action) {
      return webApiJson_({
        ok: true,
        data: {
          service: 'Euler CRM Web API',
          version: (typeof getVersionTag_ === 'function' ? getVersionTag_() : '2.1'),
          method: method,
          hint: 'POST JSON { action, payload }'
        }
      });
    }
    var result = webApiDispatch_(action, payload || {}, method);
    return webApiJson_({ ok: true, data: result });
  } catch (err) {
    var msg = (err && err.message) ? err.message : String(err);
    var code = (err && err.errorCode) ? err.errorCode : 'ERROR';
    try {
      if (typeof logCrash_ === 'function') logCrash_('WebApi', action || 'unknown', err);
    } catch (logErr) {}
    return webApiJson_({ ok: false, error: { message: msg, code: code } }, 200);
  }
}

function webApiJson_(obj, status) {
  var out = ContentService.createTextOutput(JSON.stringify(obj));
  out.setMimeType(ContentService.MimeType.JSON);
  return out;
}

/**
 * Route table — maps portal actions → existing Apps Script functions only.
 */
function webApiDispatch_(action, payload, method) {
  switch (String(action)) {

    // ── Meta / session ──────────────────────────────────────────────
    case 'ping':
      return { pong: true, at: nowDateTime_(), user: getUserEmail_() };
    case 'getSession':
      return {
        email: getUserEmail_(),
        isOwner: typeof isSpreadsheetOwner_ === 'function' ? isSpreadsheetOwner_() : false,
        companyName: (typeof getSettings_ === 'function' && getSettings_().companyName) || 'Euler Motors CRM',
        version: typeof getVersionTag_ === 'function' ? getVersionTag_() : ''
      };

    // ── Dashboard ───────────────────────────────────────────────────
    case 'getDashboard': {
      var store = loadCrmStore_(true);
      var metrics = computeDashboardMetrics_(store, false);
      return { metrics: metrics.metrics || metrics, generatedAt: nowDateTime_() };
    }
    // Company share board (bookings + retail) — safe for public GitHub link
    case 'getShareDashboard':
    case 'getBookingsDashboard':
      if (typeof getShareDashboard_ === 'function') return getShareDashboard_();
      throw businessError_('Share dashboard not available', 'MISSING_MODULE');

    // ── Leads ───────────────────────────────────────────────────────
    case 'getLeads':
    case 'getActiveLeads': {
      var list = typeof getActiveLeadsForPicker === 'function'
        ? getActiveLeadsForPicker(payload || {})
        : getActiveLeadsForPicker_(payload || {});
      // Optional stage filter (portal). Client also filters — this is belt-and-suspenders.
      var stage = String((payload && payload.stage) || '').trim().toLowerCase();
      if (stage && Array.isArray(list)) {
        list = list.filter(function (l) {
          var cs = String(l.currentStatus || '').toLowerCase();
          var ds = String(l.deliveryStatus || '').toLowerCase();
          var booked = !!(l.isBooked || cs === 'booked' || cs === 'delivered' ||
            Number(l.bookingAmount || 0) > 0 || String(l.bookingDate || '').trim() || String(l.bookingId || '').trim());
          var delivered = ds === 'delivered' || cs === 'delivered';
          if (stage === 'booking') return !booked && !delivered;
          if (stage === 'scheme') return booked && !delivered && !l.hasScheme;
          if (stage === 'payment') return booked && !delivered;
          if (stage === 'delivery') return booked && !delivered;
          if (stage === 'quotation') return !delivered;
          if (stage === 'activity') return !delivered;
          if (stage === 'close') return String(l.accountStatus || 'Active') === 'Active';
          return true;
        });
      }
      return list;
    }
    case 'searchLeads':
      if (typeof globalSearch_ === 'function') return globalSearch_(String(payload.q || payload.query || ''));
      if (typeof searchLeads_ === 'function') return searchLeads_(payload);
      return getActiveLeadsForPicker_({ activeOnly: false });
    case 'saveLead':
    case 'createLead':
      return createNewLeadFromDialog(payload);
    case 'getLeadContext':
      return typeof getUpdateLeadContext === 'function'
        ? getUpdateLeadContext(payload.leadId || payload)
        : { success: false, message: 'getUpdateLeadContext missing' };

    // ── Quotation ───────────────────────────────────────────────────
    case 'getQuotationContext':
      if (typeof getPriceAndSchemeForQuotation === 'function') {
        return getPriceAndSchemeForQuotation(
          payload.model, payload.variant, payload.quoteDate || payload.date
        );
      }
      throw businessError_('Quotation pricing API not available', 'MISSING_MODULE');
    case 'saveQuotation':
      return saveQuotationFromDialog(payload);

    // ── Booking ─────────────────────────────────────────────────────
    case 'getBookingContext':
      if (typeof getBookingLeadContext === 'function') return getBookingLeadContext(payload.leadId || payload);
      throw businessError_('getBookingLeadContext missing', 'MISSING_MODULE');
    case 'getPriceForBooking':
    case 'getPriceForBookingContext':
      if (typeof getPriceForBookingContext === 'function') {
        return getPriceForBookingContext(
          payload.leadId || payload,
          payload.variant || '',
          payload.bookingDate || payload.date || ''
        );
      }
      throw businessError_('getPriceForBookingContext missing', 'MISSING_MODULE');
    case 'convertBooking':
    case 'saveBooking':
      return saveBookingFromDialog(payload);

    // ── Price Structure (after booking) ─────────────────────────────
    case 'getPriceStructureContext':
      return getPriceStructureContext(payload.leadId || payload);
    case 'savePriceStructure':
      return savePriceStructureFromDialog(payload);

    // ── Scheme ──────────────────────────────────────────────────────
    case 'getSchemeContext':
      return getUpdateLeadContext(payload.leadId || payload);
    case 'getSchemeRules':
      if (payload.leadId && typeof getSchemeRulesForLeadDialog === 'function') {
        return getSchemeRulesForLeadDialog(payload.leadId);
      }
      return getSchemeRulesForDialog(payload.model, payload.variant, payload.bookingDate || '');
    case 'updateScheme':
    case 'saveScheme':
      if (typeof normalizeOemExtraSupportPayload_ === 'function') {
        payload = normalizeOemExtraSupportPayload_(payload || {});
      }
      var schemeResult = updateLeadFromDialog(payload);
      // Portal uses Web App deployment — force OEM register + earnings even if
      // the in-transaction amend path was skipped on an older deployment.
      if (schemeResult && schemeResult.success !== false &&
          payload && payload.leadId &&
          typeof forcePersistOemExtraSupportForLead_ === 'function') {
        try {
          var oemPersist = forcePersistOemExtraSupportForLead_(payload.leadId, payload);
          if (schemeResult.data && typeof schemeResult.data === 'object' && oemPersist) {
            Object.keys(oemPersist).forEach(function (k) { schemeResult.data[k] = oemPersist[k]; });
          }
        } catch (oemErr) {
          Logger.log('WebApi saveScheme OEM persist: ' + oemErr.message);
        }
      }
      return schemeResult;

    // ── Payment ─────────────────────────────────────────────────────
    case 'savePayment':
    case 'addPayment':
      if (payload.payments && typeof addPaymentsBatchFromDialog === 'function') {
        return addPaymentsBatchFromDialog(payload);
      }
      return addPaymentFromDialog(payload);

    // ── Finance ─────────────────────────────────────────────────────
    case 'getPendingFinanceFiles':
      return getPendingFinanceFilesForDialog();
    case 'saveFinanceReceipt':
    case 'recordFinancerReceipt':
      return recordFinanceFileReceiptFromDialog(payload);

    // ── Delivery ────────────────────────────────────────────────────
    case 'getDeliveryContext':
      return getDeliveryContextForDialog(payload.leadId || payload);
    case 'markDelivered':
      return markDeliveredFromDialog(payload);

    // ── Close lead ──────────────────────────────────────────────────
    case 'getCloseLeadContext':
      return getCloseLeadContextForDialog(payload.leadId || payload);
    case 'closeLead':
      return closeLeadFromDialog(payload);

    // ── Activity ────────────────────────────────────────────────────
    case 'saveActivity':
    case 'addActivity':
      return addActivityFromDialog(payload);

    // ── Customer 360 ────────────────────────────────────────────────
    case 'getCustomer360':
      if (typeof getCustomer360Data_ === 'function') return getCustomer360Data_(payload.leadId || payload);
      if (typeof buildCustomer360Payload_ === 'function') return buildCustomer360Payload_(payload.leadId || payload);
      throw businessError_('Customer 360 API not available', 'MISSING_MODULE');

    // ── Claims (thin wrappers) ──────────────────────────────────────
    case 'getOpenClaims':
      return getOpenClaimsForDialog();
    case 'getClaimContext':
      return getClaimContextForDialog(payload.claimId || payload);
    case 'settleClaim':
      return typeof settleClaimFromDialog === 'function'
        ? settleClaimFromDialog(payload) : settleClaimFromData_(payload);
    case 'updateClaimStatus':
      return updateClaimStatusFromDialog(payload);
    case 'addManualClaim':
      return addManualClaimFromDialog(payload);

    // ── Insurance ───────────────────────────────────────────────────
    case 'getInsuranceContext':
      return getInsuranceContextForDialog(payload.leadId || payload);
    case 'saveInsurance':
      return saveInsuranceEntryFromDialog(payload);
    case 'recordInsurancePayout':
      return recordInsurancePayoutFromDialog(payload);

    // ── Settings ────────────────────────────────────────────────────
    case 'getSettings': {
      var s = typeof getSettings_ === 'function' ? getSettings_() : {};
      // Portal-safe subset — never expose spreadsheet IDs or secrets
      return {
        companyName: s.companyName || '',
        financialYear: s.financialYear || '',
        webPortalUrl: s.webPortalUrl || '',
        version: typeof getVersionTag_ === 'function' ? getVersionTag_() : ''
      };
    }
    case 'saveSettings': {
      if (payload && payload.webPortalUrl != null && typeof saveSetting_ === 'function') {
        saveSetting_('webPortalUrl', String(payload.webPortalUrl).trim());
      }
      return saveSettingsFromDialog(payload || {});
    }

    // ── Masters (read-only lists for forms) ─────────────────────────
    case 'getMasters': {
      var masters = {};
      if (typeof getMergedMasters_ === 'function') masters = getMergedMasters_() || {};
      else if (typeof getMasters_ === 'function') masters = getMasters_() || {};
      // Model → variants from Price Master (same map as Sheet New Lead dialog)
      if (typeof getVariantOptionsByModel_ === 'function') {
        masters.variantByModel = getVariantOptionsByModel_();
      }
      return masters;
    }
    case 'getVariantsForModel':
      if (typeof getVariantOptionsForModel_ === 'function') {
        return getVariantOptionsForModel_(payload.model || payload);
      }
      return [];

    // ── Refresh (cold path — same as sheet portal) ──────────────────
    case 'refreshDashboard':
      if (typeof refreshDashboardNow === 'function') return refreshDashboardNow();
      if (typeof refreshCrmAfterDialogSave === 'function') return refreshCrmAfterDialogSave();
      return { success: true };

    default:
      throw businessError_('Unknown API action: ' + action, 'UNKNOWN_ACTION');
  }
}

/** Menu: open the static web portal URL from Settings. */
function menuOpenWebPortal() {
  var settings = typeof getSettings_ === 'function' ? getSettings_() : {};
  var url = String(settings.webPortalUrl || '').trim();
  if (!url) {
    SpreadsheetApp.getUi().alert(
      'Web Portal URL not set',
      '1. Deploy WebApi.gs as a Web App\n' +
      '2. Host the euler-crm-portal folder (or open index.html locally with API_BASE_URL set)\n' +
      '3. Save webPortalUrl in Settings, or set assets/js/config.js → API_BASE_URL',
      SpreadsheetApp.getUi().ButtonSet.OK
    );
    return;
  }
  var html = HtmlService.createHtmlOutput(
    '<script>window.open(' + JSON.stringify(url) + ');google.script.host.close();</script>'
  ).setWidth(1).setHeight(1);
  SpreadsheetApp.getUi().showModalDialog(html, 'Opening…');
}
