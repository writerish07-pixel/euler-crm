/**
 * PricingService – single source of truth for Price Master access + pricing math.
 * No other module should read PRICE MASTER directly.
 */

function getPricingRows_() {
  // Booking path always reads live sheet data — never script cache.
  var ss = getSpreadsheet_();
  var sheet = ss.getSheetByName(CRM.SHEETS.PRICE_MASTER);
  if (!sheet) throw businessError_('PRICE MASTER sheet not found.', 'PRICE_MASTER_MISSING');
  var lastRow = sheet.getLastRow();
  var lastCol = sheet.getLastColumn();
  if (lastRow < CRM.PRICE_MASTER.DATA_START) {
    throw businessError_('PRICE MASTER is empty. Import active prices first.', 'PRICE_MASTER_EMPTY');
  }
  var headers = getHeaders_(sheet, CRM.PRICE_MASTER.HEADER_ROW);
  var numRows = lastRow - CRM.PRICE_MASTER.DATA_START + 1;
  var colCount = Math.max(lastCol, headers.length, (CRM.PRICE_MASTER.COLS || []).length);
  var rows = sheet.getRange(CRM.PRICE_MASTER.DATA_START, 1, numRows, colCount).getValues();
  return {
    headers: headers,
    rows: rows,
    dataStart: CRM.PRICE_MASTER.DATA_START,
    meta: {
      sheetName: sheet.getName(),
      spreadsheetId: ss.getId(),
      lastRow: lastRow,
      lastColumn: lastCol,
      headerRow: CRM.PRICE_MASTER.HEADER_ROW,
      dataRowCount: numRows,
      cacheUsed: false
    }
  };
}

function invalidatePriceMasterCache_() {
  try { CacheService.getScriptCache().remove('price_master_active_v1'); } catch (e) {}
}

// Public API wrappers (stable names requested for go-live).
function getActivePrice(model, variant, bookingDate) { return getActivePrice_(model, variant, bookingDate); }
function getPriceVersion(priceRow) { return getPriceVersion_(priceRow); }
function getCommercialBreakup(model, variant, bookingDate) { return getCommercialBreakup_(model, variant, bookingDate); }
function calculateGross(price) { return calculateGross_(price); }
function calculateNet(price, offer, finalExchangeValue) { return calculateNet_(price, offer, finalExchangeValue); }
function calculateOutstanding(commercialInput) { return calculateOutstanding_(commercialInput); }
function calculateTCS(price) { return calculateTCS_(price); }
function validatePrice(price) { return validatePrice_(price); }

function parsePricingRow_(headers, row, rowNumber) {
  function val(nameOrAliases) {
    var aliases = Array.isArray(nameOrAliases) ? nameOrAliases : [nameOrAliases];
    for (var i = 0; i < aliases.length; i++) {
      var idx = findHeaderIndex_(headers, aliases[i]);
      if (idx >= 0) return row[idx];
    }
    return '';
  }
  var model = String(val(['Model']) || '').trim();
  var variant = String(val(['Variant']) || '').trim();
  if (!model || !variant) return null;
  var status = String(val(['Status']) || 'active').trim().toLowerCase();
  // A blank/undated Effective From means "always in effect" (fromKey = 0), NOT a
  // reason to discard the row. Dealers routinely fill prices without dates; those
  // rows must still be usable, otherwise the booking finds no active price at all.
  var fromKey = normalizeDateKey_(val(['Effective From', 'Effective Date From', 'From Date'])) || 0;
  var toKey = normalizeDateKey_(val(['Effective To', 'Effective Date To', 'To Date'])) || 99991231;
  return {
    rowNumber: rowNumber,
    model: model,
    variant: variant,
    modelNorm: normalizePriceKey_(model),
    variantNorm: normalizePriceKey_(variant),
    bodyType: String(val(['Body Type', 'Battery Type']) || '').trim(),
    exShowroom: parseNumber_(val(['Ex Showroom Price', 'Ex Showroom'])),
    registrationRto: parseNumber_(val(['RTO', 'Registration', 'Registration / RTO'])),
    insurance: parseNumber_(val(['Insurance'])),
    accessories: parseNumber_(val(['Accessories'])),
    handlingCharges: parseNumber_(val(['Handling Charges', 'Handling'])),
    trc: parseNumber_(val(['TRC'])),
    fastag: parseNumber_(val(['Fastag'])),
    extendedWarranty: parseNumber_(val(['Extended Warranty', 'Warranty'])),
    otherCharges: parseNumber_(val(['Other Charges'])),
    gstPercent: parseNumber_(val(['GST %', 'GST'])),
    tcsApplicable: normalizeYesNo_(val(['TCS Applicable', 'TCS Rule'])),
    effectiveFrom: val(['Effective From', 'Effective Date From', 'From Date']),
    effectiveTo: val(['Effective To', 'Effective Date To', 'To Date']),
    effectiveFromKey: fromKey,
    effectiveToKey: toKey,
    priceVersion: String(val(['Price Version', 'Version']) || '').trim(),
    status: status,
    remarks: String(val(['Remarks']) || '').trim()
  };
}

function getActivePrice_(model, variant, bookingDate) {
  var modelNorm = normalizePriceKey_(model);
  var variantNorm = normalizePriceKey_(variant);
  var when = normalizeDateKey_(bookingDate || nowDate_());
  if (!when) when = normalizeDateKey_(nowDate_());
  if (!modelNorm) {
    throw fieldError_('Interested Model', 'Model is required for price lookup.', 'VALIDATION');
  }
  if (!variantNorm) {
    throw fieldError_('Variant', 'Variant is required for price lookup.', 'VALIDATION');
  }

  invalidatePriceMasterCache_();
  var data = getPricingRows_();
  var matches = [];
  var scanned = 0;
  var rejected = { parseFailed: 0, status: 0, model: 0, variant: 0, date: 0 };
  var rejectionSamples = [];

  data.rows.forEach(function (row, i) {
    scanned++;
    var rowNum = data.dataStart + i;
    var rec = parsePricingRow_(data.headers, row, rowNum);
    if (!rec) {
      rejected.parseFailed++;
      if (rejectionSamples.length < 5) {
        rejectionSamples.push({ row: rowNum, reason: 'PARSE_FAILED', model: String(row[0] || ''), variant: String(row[1] || '') });
      }
      return;
    }
    if (rec.status && rec.status !== 'active') {
      rejected.status++;
      if (rejectionSamples.length < 8) {
        rejectionSamples.push({ row: rowNum, reason: 'STATUS', status: rec.status, model: rec.model, variant: rec.variant });
      }
      return;
    }
    if (rec.modelNorm !== modelNorm) {
      rejected.model++;
      return;
    }
    if (rec.variantNorm !== variantNorm) {
      rejected.variant++;
      return;
    }
    if (!(rec.effectiveFromKey <= when && rec.effectiveToKey >= when)) {
      rejected.date++;
      if (rejectionSamples.length < 8) {
        rejectionSamples.push({
          row: rowNum, reason: 'DATE', model: rec.model, variant: rec.variant,
          effectiveFromKey: rec.effectiveFromKey, effectiveToKey: rec.effectiveToKey, bookingDateKey: when
        });
      }
      return;
    }
    matches.push(rec);
  });

  if (!matches.length) {
    Logger.log('PRICING_LOOKUP miss: ' + model + ' / ' + variant + ' scanned=' + scanned);
    throw businessError_(
      'No active price found for this Model + Variant. Scanned ' + scanned + ' rows. ' +
      'Rejected: parse=' + rejected.parseFailed + ', status=' + rejected.status +
      ', model=' + rejected.model + ', variant=' + rejected.variant + ', date=' + rejected.date + '.',
      'PRICE_NOT_FOUND'
    );
  }
  if (matches.length > 1) {
    throw businessError_('Multiple active prices found for this Model + Variant. Fix PRICE MASTER duplicates.', 'PRICE_DUPLICATE');
  }
  return matches[0];
}

function getPriceVersion_(priceRow) {
  return String((priceRow && priceRow.priceVersion) || '');
}

function calculateGross_(price) {
  return round2_(
    num_(price.exShowroom) + num_(price.accessories) + num_(price.insurance) +
    num_(price.registrationRto) + num_(price.handlingCharges) + num_(price.trc) +
    num_(price.fastag) + num_(price.extendedWarranty) + num_(price.otherCharges)
  );
}

function calculateTCS_(price) {
  var gross = calculateGross_(price);
  return String(price.tcsApplicable || 'No').toLowerCase() === 'yes' ? calculateTcs_(gross) : 0;
}

function calculateNet_(price, offer, finalExchangeValue) {
  var totals = calcPriceTotals_(price, offer || {}, finalExchangeValue || 0);
  return totals.netVehicleCost;
}

function calculateOutstanding_(commercialInput) {
  var input = commercialInput || {};
  var totals = calcPriceTotals_(input.price || {}, input.offer || {}, input.finalExchangeValue || 0);
  return calcOutstanding_(totals.customerPayable, input.bookingAmount || 0, input.paymentsReceived || 0);
}

function validatePrice_(price) {
  var required = ['exShowroom', 'insurance', 'registrationRto', 'tcsApplicable', 'priceVersion'];
  var missing = required.filter(function (k) {
    return price[k] === undefined || price[k] === null || price[k] === '';
  });
  if (missing.length) {
    throw businessError_('Pricing is incomplete. Missing: ' + missing.join(', '), 'PRICE_INCOMPLETE');
  }
  // A matched Price Master row must yield clean, finite numbers. A cell stored as
  // text (e.g. "7,00,000" or "₹7,00,000") must never slip through as NaN/zero and
  // silently zero out Gross / Outstanding — fail loudly with the offending field.
  var numericFields = ['exShowroom', 'insurance', 'registrationRto', 'accessories',
    'handlingCharges', 'trc', 'fastag', 'extendedWarranty', 'otherCharges', 'gstPercent'];
  var bad = numericFields.filter(function (k) {
    return typeof price[k] !== 'number' || !isFinite(price[k]);
  });
  if (bad.length) {
    throw businessError_('Price Master has non-numeric values in: ' + bad.join(', ') +
      '. Fix these cells (remove commas / currency symbols / text) and retry.', 'PRICE_NON_NUMERIC');
  }
  if (!(price.exShowroom > 0)) {
    throw businessError_('Ex Showroom price is zero or invalid for this Model + Variant. ' +
      'Correct the Price Master row before booking.', 'PRICE_EX_SHOWROOM_ZERO');
  }
}

function getCommercialBreakup_(model, variant, bookingDate) {
  var rec = getActivePrice_(model, variant, bookingDate);
  var price = {
    exShowroom: rec.exShowroom,
    insurance: rec.insurance,
    registrationRto: rec.registrationRto,
    accessories: rec.accessories,
    handlingCharges: rec.handlingCharges,
    trc: rec.trc,
    fastag: rec.fastag,
    extendedWarranty: rec.extendedWarranty,
    otherCharges: rec.otherCharges,
    gstPercent: rec.gstPercent,
    tcsApplicable: rec.tcsApplicable,
    priceVersion: rec.priceVersion,
    effectiveFrom: rec.effectiveFrom,
    bodyType: rec.bodyType,
    priceMasterRowId: rec.rowNumber
  };
  validatePrice_(price);
  return {
    price: price,
    grossVehicleCost: calculateGross_(price),
    tcs: calculateTCS_(price),
    priceVersion: getPriceVersion_(rec),
    priceMasterRowId: rec.rowNumber
  };
}

function traceBookingPricingFlow_(leadId, bookingDate) {
  var lead = getLead_(leadId);
  if (!lead) return { ok: false, error: 'Lead not found: ' + leadId };
  var trace = {
    leadId: lead.leadId,
    model: lead.interestedModel || '',
    variant: lead.variant || '',
    bookingDate: bookingDate || nowDate_()
  };
  try {
    var breakup = getCommercialBreakup_(trace.model, trace.variant, trace.bookingDate);
    trace.lookup = {
      priceVersion: breakup.priceVersion,
      priceMasterRowId: breakup.priceMasterRowId,
      grossVehicleCost: breakup.grossVehicleCost,
      tcs: breakup.tcs
    };
    var outstanding = calculateOutstanding_({
      price: breakup.price,
      offer: {},
      finalExchangeValue: 0,
      bookingAmount: Number(lead.bookingAmount || 0),
      paymentsReceived: Number((loadCrmStore_().paymentsByLead[lead.leadId]) || 0)
    });
    trace.outstanding = outstanding;
    trace.ok = true;
  } catch (e) {
    trace.ok = false;
    trace.errorCode = e.errorCode || 'ERROR';
    trace.error = e.message;
  }
  logAudit_('PRICING_TRACE', JSON.stringify(trace));
  return trace;
}

/** Full pricing data-layer audit — run from Apps Script dropdown. */
function auditPricingDataLayer(leadId, model, variant, bookingDate) {
  leadId = String(leadId || 'LD26000158').trim();
  bookingDate = bookingDate || nowDate_();
  var expectedHeaders = (CRM.PRICE_MASTER && CRM.PRICE_MASTER.COLS) || [];
  var out = {
    task1_getPricingRows: null,
    task2_headers: null,
    task3_parsedSample: null,
    task4_cacheCompare: null,
    task5_findHeaderIndex: null,
    task6_normalizeKeys: null,
    task7_activePrice: null,
    ok: false
  };

  // Resolve lead keys for task 6.
  var lead = getLead_(leadId);
  var leadModel = model || (lead && lead.interestedModel) || '';
  var leadVariant = variant || (lead && lead.variant) || '';

  // TASK 1 — live sheet read (no cache).
  var live = getPricingRows_();
  out.task1_getPricingRows = live.meta || {};

  // TASK 2 — header diff.
  var headerDiff = [];
  expectedHeaders.forEach(function (h) {
    var idx = findHeaderIndex_(live.headers, h);
    if (idx < 0) headerDiff.push({ expected: h, found: false });
    else headerDiff.push({ expected: h, found: true, actual: live.headers[idx], index: idx });
  });
  live.headers.forEach(function (h, i) {
    if (!h) return;
    var known = expectedHeaders.some(function (exp) { return findHeaderIndex_([h], exp) >= 0; });
    if (!known) headerDiff.push({ expected: null, found: true, actual: h, index: i, extra: true });
  });
  out.task2_headers = { headers: live.headers, diff: headerDiff };

  // TASK 3 — first 5 parsed rows.
  var parsedSample = [];
  for (var i = 0; i < Math.min(5, live.rows.length); i++) {
    var rec = parsePricingRow_(live.headers, live.rows[i], live.dataStart + i);
    if (!rec) {
      parsedSample.push({ row: live.dataStart + i, parseFailed: true });
      continue;
    }
    parsedSample.push({
      row: rec.rowNumber,
      model: rec.model,
      variant: rec.variant,
      exShowroom: rec.exShowroom,
      registrationRto: rec.registrationRto,
      insurance: rec.insurance,
      accessories: rec.accessories,
      handlingCharges: rec.handlingCharges,
      trc: rec.trc,
      fastag: rec.fastag,
      extendedWarranty: rec.extendedWarranty,
      otherCharges: rec.otherCharges,
      gstPercent: rec.gstPercent,
      tcsApplicable: rec.tcsApplicable,
      priceVersion: rec.priceVersion,
      status: rec.status,
      effectiveFromKey: rec.effectiveFromKey,
      effectiveToKey: rec.effectiveToKey,
      undefinedFields: ['exShowroom', 'registrationRto', 'insurance', 'accessories', 'handlingCharges', 'trc', 'fastag', 'extendedWarranty', 'otherCharges', 'gstPercent'].filter(function (k) {
        return rec[k] === undefined;
      })
    });
  }
  out.task3_parsedSample = parsedSample;

  // TASK 4 — cache vs live (booking path uses live only).
  var cacheHit = false;
  var cachedRows = null;
  try {
    var cached = CacheService.getScriptCache().get('price_master_active_v1');
    cacheHit = !!cached;
    if (cached) cachedRows = JSON.parse(cached).rows ? JSON.parse(cached).rows.length : 0;
  } catch (e) {}
  out.task4_cacheCompare = {
    bookingPathUsesCache: false,
    cacheHit: cacheHit,
    cachedRowCount: cachedRows,
    liveRowCount: live.rows.length,
    cacheStaleRisk: cacheHit && cachedRows !== live.rows.length
  };

  // TASK 5 — findHeaderIndex checks.
  out.task5_findHeaderIndex = expectedHeaders.map(function (h) {
    return { header: h, index: findHeaderIndex_(live.headers, h) };
  });

  // TASK 6 — normalize keys lead vs price master.
  var modelNorm = normalizePriceKey_(leadModel);
  var variantNorm = normalizePriceKey_(leadVariant);
  var pmMatches = [];
  live.rows.forEach(function (row, idx) {
    var rec = parsePricingRow_(live.headers, row, live.dataStart + idx);
    if (!rec) return;
    if (rec.modelNorm === modelNorm && rec.variantNorm === variantNorm) pmMatches.push(rec);
  });
  out.task6_normalizeKeys = {
    lead: { model: leadModel, variant: leadVariant, modelNorm: modelNorm, variantNorm: variantNorm },
    priceMasterMatches: pmMatches.map(function (r) {
      return { row: r.rowNumber, model: r.model, variant: r.variant, modelNorm: r.modelNorm, variantNorm: r.variantNorm };
    }),
    keysMatch: pmMatches.length > 0
  };

  // TASK 7 — active price with rejection detail.
  try {
    var price = getActivePrice_(leadModel, leadVariant, bookingDate);
    out.task7_activePrice = {
      ok: true,
      rowNumber: price.rowNumber,
      model: price.model,
      variant: price.variant,
      exShowroom: price.exShowroom,
      priceVersion: price.priceVersion,
      gross: calculateGross_(price)
    };
    out.ok = true;
  } catch (e) {
    out.task7_activePrice = { ok: false, error: e.message, errorCode: e.errorCode || 'ERROR' };
  }

  Logger.log(JSON.stringify(out, null, 2));
  logAudit_('PRICING_DATA_LAYER_AUDIT', JSON.stringify(out));
  return out;
}

function runAuditPricingDataLayer() {
  return auditPricingDataLayer('LD26000158', '', '', '2026-07-09');
}
