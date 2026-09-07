/** ColorOS / OriginOS WebViews on OPPO, vivo, realme, OnePlus. These phones
 *  have shipped without ICU for `en-IN` and abort service-worker navigations. */
export function isFragileAndroid(ua = typeof navigator !== "undefined" ? navigator.userAgent : "") {
  const s = String(ua || "");
  if (!/Android/i.test(s)) return false;
  return /OPPO|Oppo|\bCPH\d|vivo|Vivo|iQOO|HeyTap|ColorOS|OriginOS|OnePlus|realme|Realme|Harmony/i.test(s);
}

export const SAFE_LOCALES = ["en-GB", "en"];
export const IN_LOCALES = ["en-IN", ...SAFE_LOCALES];

export function formatLocales(ua) {
  return isFragileAndroid(ua) ? SAFE_LOCALES : IN_LOCALES;
}
