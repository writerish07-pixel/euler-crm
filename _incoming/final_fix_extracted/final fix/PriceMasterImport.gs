/**
 * PriceMasterImport.gs
 * Source: Akar Euler New Price List 2026.xlsx (01-05-2026)
 * Columns: Body Type, Handling Charges, TRC (separate)
 * Run: CRM -> Admin -> Import Price Master 2026 (owner)
 */

var PRICE_MASTER_2026_SOURCE_ = 'Akar Euler New Price List 2026.xlsx';
var PRICE_MASTER_2026_VERSION_ = 'AKAR-2026-05';

var PRICE_MASTER_2026_ROWS_ = [
  ["Storm","Storm TR (DV260) Reg C7 3.3kWh","DV260",1009999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Regular Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (PV) Reg C7 3.3kWh","PV",975000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Regular Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (HD) Reg C7 3.3kWh","HD",999999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Regular Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (FB) Reg C7 3.3kWh","FB",950000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Regular Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (DV260) Reg C10 3.3kWh","DV260",1029999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Regular Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (PV) Reg C10 3.3kWh","PV",995000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Regular Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (HD) Reg C10 3.3kWh","HD",1029999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Regular Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (FB) Reg C10 3.3kWh","FB",980000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Regular Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (DV260) Reg C10 6.6kWh","DV260",1049999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (PV) Reg C10 6.6kWh","PV",1015000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (HD) Reg C10 6.6kWh","HD",1049999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (FB) Reg C10 6.6kWh","FB",1000000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (DV260) Arm C7 3.3kWh","DV260",1049999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Armoured Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (PV) Arm C7 3.3kWh","PV",1015000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Armoured Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (HD) Arm C7 3.3kWh","HD",1049999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Armoured Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (FB) Arm C7 3.3kWh","FB",1000000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Armoured Chimera 7 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (DV260) Arm C10 3.3kWh","DV260",1079999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Armoured Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (PV) Arm C10 3.3kWh","PV",1045000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Armoured Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (HD) Arm C10 3.3kWh","HD",1079999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Armoured Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (FB) Arm C10 3.3kWh","FB",1030000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Armoured Chimera 10 Home 3.3 kWh / 6 Hr"],
  ["Storm","Storm TR (DV260) Arm C10 6.6kWh","DV260",1099999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Armoured Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (PV) Arm C10 6.6kWh","PV",1065000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Armoured Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (HD) Arm C10 6.6kWh","HD",1099999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 HD Armoured Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (FB) Arm C10 6.6kWh","FB",1050000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 FB Armoured Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (DV260) Reg C7 6.6kWh","DV260",1019999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","STORM T1500 DV260 Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm TR (PV) Reg C7 6.6kWh","PV",985000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","STORM T1500 PV Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (PV) Reg C7 6.6kWh","PV",1410000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR PV Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (HD) Reg C7 6.6kWh","HD",1430000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR HD Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (FB) Reg C7 6.6kWh","FB",1390000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR FB Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (DV330) Reg C7 6.6kWh","DV330",1450000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR DV330 Regular Chimera 7 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (PV) Reg C10 6.6kWh","PV",1440000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR PV Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (HD) Reg C10 6.6kWh","HD",1460000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR HD Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (FB) Reg C10 6.6kWh","FB",1420000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR FB Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Storm","Storm LR (Storm LR) Reg C10 6.6kWh","Storm LR",1480000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"Yes","2026-05-01","","AKAR-2026-05","active","LR DV330 Regular Chimera 10 Home 6.6 kWh / 4 Hr"],
  ["Turbo Max","City (DAC)","DAC",599999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 City"],
  ["Turbo Max","City (FB)","FB",615000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 City"],
  ["Turbo Max","City (PV)","PV",640000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 City"],
  ["Turbo Max","City (HD)","HD",673000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 City"],
  ["Turbo Max","City (DV200)","DV200",675000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 City"],
  ["Turbo Max","Maxx (FB)","FB",760000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 Maxx"],
  ["Turbo Max","Maxx (PV)","PV",770000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 Maxx"],
  ["Turbo Max","Maxx (HD)","HD",808000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 Maxx"],
  ["Turbo Max","Maxx (DV200)","DV200",809999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 Maxx"],
  ["Turbo Max","FastCharge (FB)","FB",850000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 FastCharge"],
  ["Turbo Max","FastCharge (PV)","PV",860000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 FastCharge"],
  ["Turbo Max","FastCharge (HD)","HD",898000.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 FastCharge"],
  ["Turbo Max","FastCharge (DV200)","DV200",899999.0,15000.0,22000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Turbo 1000 FastCharge"],
  ["Hi-Load","XR (DV120)","DV120",471433.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","XR (DV170)","DV170",481634.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","XR (PV)","PV",456134.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","XR (HD)","HD",469394.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","XR (FB170)","FB170",448994.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","XR (FB120)","FB120",446953.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad)","HiLoad",430634.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad) @440834","HiLoad",440834.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad) @415334","HiLoad",415334.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad) @428594","HiLoad",428594.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad) @408193","HiLoad",408193.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR-NC (HiLoad) @406154","HiLoad",406154.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad)","HiLoad",496433.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad) @506635","HiLoad",506635.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad) @481134","HiLoad",481134.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad) @494393","HiLoad",494393.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad) @473994","HiLoad",473994.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Hi-Load","TR With GBT (HiLoad) @471954","HiLoad",471954.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiLoad"],
  ["Neo HiRange","XR","NA",438000.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Neo HiRange"],
  ["Neo HiRange","TR","NA",378000.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Neo HiRange"],
  ["Neo HiRange","SR","NA",309999.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","Neo HiRange"],
  ["Hi-Load","XR","NA",435000.0,10000.0,10000.0,0,0,3000.0,0,0,0,0,"No","2026-05-01","","AKAR-2026-05","active","HiCity"]
];

function menuImportPriceMaster2026() {
  if (typeof isSpreadsheetOwner_ === 'function' && !isSpreadsheetOwner_()) {
    SpreadsheetApp.getUi().alert('Only the spreadsheet owner can import Price Master.');
    return;
  }
  var ui = SpreadsheetApp.getUi();
  var ok = ui.alert('Import Price Master 2026',
    'This will:\n• Load ' + PRICE_MASTER_2026_ROWS_.length + ' price rows\n• Update Masters Models & Variants\n• Remove Colour dropdown\n\nContinue?',
    ui.ButtonSet.YES_NO);
  if (ok !== ui.Button.YES) return;
  var result = installPriceMaster2026_();
  ui.alert('Price Master imported', result.message, ui.ButtonSet.OK);
}

function installPriceMaster2026_() {
  setupPriceMaster_();
  var sheet = getSheet_(CRM.SHEETS.PRICE_MASTER);
  var last = sheet.getLastRow();
  if (last > CRM.PRICE_MASTER.DATA_START) {
    sheet.getRange(CRM.PRICE_MASTER.DATA_START, 1, last - CRM.PRICE_MASTER.DATA_START + 1, sheet.getLastColumn()).clearContent();
  }
  if (!PRICE_MASTER_2026_ROWS_.length) return { ok: false, message: 'No rows to import.' };
  sheet.getRange(CRM.PRICE_MASTER.DATA_START, 1, PRICE_MASTER_2026_ROWS_.length, PRICE_MASTER_2026_ROWS_[0].length)
    .setValues(PRICE_MASTER_2026_ROWS_);
  try { CacheService.getScriptCache().remove('price_master_active_v1'); } catch (e) {}
  try { invalidatePriceMasterCache_(); } catch (e2) {}
  try { syncPriceMasterMasters_(); } catch (e2) { Logger.log(e2.message); }
  logAudit_('PRICE_MASTER_IMPORT', PRICE_MASTER_2026_ROWS_.length + ' rows | ' + PRICE_MASTER_2026_VERSION_);
  return { ok: true, rows: PRICE_MASTER_2026_ROWS_.length, message: 'Imported ' + PRICE_MASTER_2026_ROWS_.length +
    ' price rows. Masters Models/Variants updated. Colour dropdown removed.' };
}

/** Replace Masters Models/Variants from price list; remove Colours section. */
function syncPriceMasterMasters_() {
  var models = [];
  var variants = [];
  var modelSeen = {};
  var variantSeen = {};
  PRICE_MASTER_2026_ROWS_.forEach(function (row) {
    var m = String(row[0] || "").trim();
    var v = String(row[1] || "").trim();
    if (m && !modelSeen[m]) { modelSeen[m] = true; models.push(m); }
    if (v && !variantSeen[v]) { variantSeen[v] = true; variants.push(v); }
  });
  models.sort();
  variants.sort();
  var merged = getMergedMasters_();
  merged.Models = models;
  merged.Variants = variants;
  delete merged.Colours;
  writeMastersSheet_(merged);
  try { refreshAllDropdowns_(); } catch (e) {}
}

function getPriceMaster2026Preview_() {
  return {
    source: PRICE_MASTER_2026_SOURCE_,
    version: PRICE_MASTER_2026_VERSION_,
    rowCount: PRICE_MASTER_2026_ROWS_.length,
    models: PRICE_MASTER_2026_ROWS_.reduce(function (m, r) {
      m[r[0]] = (m[r[0]] || 0) + 1;
      return m;
    }, {})
  };
}