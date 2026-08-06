/**
 * MasterDataService – repository for dropdowns and configurable business rules.
 */

function getMasterDataRepository_() {
  var masters = getMergedMasters_();
  var settings = getSettings_();
  return {
    dropdowns: {
      leadSources: masters['Lead Sources'] || [],
      models: masters['Models'] || [],
      variants: masters['Variants'] || [],
      colours: [],
      executives: masters['Executives'] || [],
      paymentModes: masters['Payment Modes'] || [],
      activityTypes: getActivityTypeMaster_(),
      status: masters['Status'] || [],
      priority: masters['Priority'] || []
    },
    modules: {
      priceMaster: getActivePriceMasterRecords_()
    },
    rules: {
      tcsRate: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_RATE || 0),
      tcsThreshold: Number(CRM.COMMERCIAL && CRM.COMMERCIAL.TCS_THRESHOLD || 0),
      leadPrefix: settings.leadPrefix || 'LD',
      receiptPrefix: settings.receiptPrefix || 'RC',
      bookingPrefix: settings.bookingPrefix || 'BK',
      ownerPriceOverrideEnabled: String(settings.ownerPriceOverrideEnabled || 'No').toLowerCase() === 'yes'
    },
    componentPolicy: (CRM.COMMERCIAL && CRM.COMMERCIAL.COMPONENT_POLICY) || {}
  };
}

function getMasterDropdown_(name) {
  var repo = getMasterDataRepository_();
  return repo.dropdowns[name] || [];
}

/** Build model -> variants map from active Price Master (fallback to Masters variants). */
function getVariantOptionsByModel_() {
  var map = {};
  try {
    var records = getActivePriceMasterRecords_();
    (records.rows || []).forEach(function (r) {
      var model = String(r.model || '').trim();
      var variant = String(r.variant || '').trim();
      if (!model || !variant) return;
      if (!map[model]) map[model] = [];
      if (map[model].indexOf(variant) < 0) map[model].push(variant);
    });
    Object.keys(map).forEach(function (model) {
      map[model].sort(function (a, b) { return a.localeCompare(b); });
    });
  } catch (e) {
    Logger.log('getVariantOptionsByModel_: ' + e.message);
  }
  return map;
}

/** Return variants for selected model (Price Master first, Masters fallback). */
function getVariantOptionsForModel_(model) {
  var m = String(model || '').trim();
  if (!m) return [];
  var byModel = getVariantOptionsByModel_();
  var direct = byModel[m] || [];
  if (direct.length) return direct;

  // Case-insensitive match fallback.
  var match = Object.keys(byModel).find(function (k) {
    return String(k).toLowerCase() === m.toLowerCase();
  });
  if (match && byModel[match]) return byModel[match];

  return getMergedMasters_()['Variants'] || [];
}

function getBusinessRule_(ruleName, defaultValue) {
  var repo = getMasterDataRepository_();
  if (repo.rules.hasOwnProperty(ruleName)) return repo.rules[ruleName];
  return defaultValue;
}

function getActivityTypeMaster_() {
  var masters = getMergedMasters_();
  var list = (masters['Activity Types'] || CRM.MASTERS.SECTIONS['Activity Types'] || []).slice();
  if (list.indexOf('Note') < 0) list.push('Note');
  return list;
}

function getFollowUpActivityTypes_() {
  var master = getActivityTypeMaster_();
  var allowed = ['Call', 'WhatsApp', 'Visit', 'Follow-up', 'Note'];
  return allowed.filter(function (t) {
    return master.some(function (m) { return String(m).toLowerCase() === String(t).toLowerCase(); });
  });
}

function normalizeActivityTypeForWrite_(activityType, opts) {
  opts = opts || {};
  var allowFallback = opts.allowFallback !== false;
  var fallbackType = opts.fallbackType || 'Note';
  var master = getActivityTypeMaster_();
  var aliases = {
    'lead created': 'Note',
    'booking created': 'Booking',
    'system': 'Note',
    'create': 'Note',
    'import': 'Note',
    'new lead': 'Note'
  };
  var raw = String(activityType || '').trim();
  if (!raw) {
    if (allowFallback) return fallbackType;
    throw fieldError_('Activity Type', 'Select an activity type. Allowed: ' + master.join(', '), 'VALIDATION');
  }

  var direct = matchMasterValue_(raw, master);
  if (direct) return direct;

  var mapped = aliases[raw.toLowerCase()];
  if (mapped && matchMasterValue_(mapped, master)) return mapped;

  if (allowFallback && matchMasterValue_(fallbackType, master)) return fallbackType;
  throw fieldError_('Activity Type', 'Invalid value "' + raw + '". Allowed: ' + master.join(', '), 'VALIDATION');
}

function assertActivityTypeValid_(activityType) {
  return normalizeActivityTypeForWrite_(activityType, { allowFallback: false });
}

function getPriceMasterRecordForBooking_(model, variant, bookingDate) {
  return getActivePrice_(model, variant, bookingDate);
}

function validatePriceMasterLookup_(model, variant, bookingDate) {
  try {
    return { ok: true, record: getActivePrice_(model, variant, bookingDate) };
  } catch (e) {
    return { ok: false, errorCode: e.errorCode || 'PRICE_MASTER_INVALID', message: e.message };
  }
}

function getActivePriceMasterRecords_() {
  // Dropdown/catalog cache only — booking lookups NEVER use this; they call getActivePrice_().
  var cache = CacheService.getScriptCache();
  var key = 'price_master_active_v1';
  var cached = cache.get(key);
  if (cached) {
    try { return JSON.parse(cached); } catch (e) { cache.remove(key); }
  }

  var out = { rows: [], byModelVariant: {} };
  var data;
  try {
    data = getPricingRows_();
  } catch (e) {
    return out;
  }

  data.rows.forEach(function (row, i) {
    var rec = parsePricingRow_(data.headers, row, data.dataStart + i);
    if (!rec) return;
    if (rec.status && rec.status !== 'active') return;
    out.rows.push(rec);
    var keyMv = rec.modelNorm + '|' + rec.variantNorm;
    if (!out.byModelVariant[keyMv]) out.byModelVariant[keyMv] = [];
    out.byModelVariant[keyMv].push(rec);
  });

  Object.keys(out.byModelVariant).forEach(function (k) {
    out.byModelVariant[k].sort(function (a, b) {
      if (a.effectiveFromKey !== b.effectiveFromKey) return b.effectiveFromKey - a.effectiveFromKey;
      return String(b.priceVersion || '').localeCompare(String(a.priceVersion || ''));
    });
  });

  try {
    cache.put(key, JSON.stringify(out), Number((CRM.PRICE_MASTER && CRM.PRICE_MASTER.CACHE_TTL_SEC) || 300));
  } catch (ce) {}
  return out;
}

/** Certification/legacy wrapper — delegates to PricingService.parsePricingRow_. */
function parsePriceMasterRow_(headers, row) {
  return parsePricingRow_(headers, row, 0);
}

/** Diagnostic helper to audit why Price Master prefill fails for a lead. */
function auditBookingPricePrefill_(leadId, bookingDate) {
  var lead = getLead_(leadId);
  if (!lead) return { ok: false, error: 'Lead not found: ' + leadId };
  var dateKey = normalizeDateKey_(bookingDate || nowDate_());
  var all = getActivePriceMasterRecords_();
  var mk = normalizePriceKey_(lead.interestedModel || '');
  var vk = normalizePriceKey_(lead.variant || '');
  var key = mk + '|' + vk;
  var rows = all.byModelVariant[key] || [];
  var inDate = rows.filter(function (r) {
    return r.effectiveFromKey <= dateKey && r.effectiveToKey >= dateKey;
  });
  return {
    ok: inDate.length > 0,
    leadId: lead.leadId,
    model: lead.interestedModel || '',
    variant: lead.variant || '',
    lookupKey: key,
    activeRowsTotal: all.rows.length,
    modelVariantRows: rows.length,
    dateMatches: inDate.length,
    sample: inDate.slice(0, 3)
  };
}
