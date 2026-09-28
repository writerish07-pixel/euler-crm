/** ColorOS / OriginOS WebViews on OPPO, vivo, realme, OnePlus. These phones
 *  have shipped without ICU for `en-IN` and abort service-worker navigations. */
export function isFragileAndroid(ua = typeof navigator !== "undefined" ? navigator.userAgent : "") {
  const s = String(ua || "");
  if (!/Android/i.test(s)) return false;
  return /OPPO|Oppo|\bCPH\d|vivo|Vivo|iQOO|HeyTap|ColorOS|OriginOS|OnePlus|realme|Realme|Harmony/i.test(s);
}

/** Capacitor Android/iOS shell. The live website is unchanged; this is only
 *  true inside the store apps that wrap the same React build. */
export function isNativeShell({ origin, protocol, capacitor } = {}) {
  const cap = capacitor !== undefined
    ? capacitor
    : (typeof window !== "undefined" ? window.Capacitor : undefined);
  if (cap && typeof cap.isNativePlatform === "function" && cap.isNativePlatform()) return true;
  const proto = String(
    protocol !== undefined
      ? protocol
      : (typeof window !== "undefined" ? window.location?.protocol : "") || "",
  ).toLowerCase();
  if (proto === "capacitor:" || proto === "ionic:" || proto === "file:") return true;
  const o = String(
    origin !== undefined
      ? origin
      : (typeof window !== "undefined" ? window.location?.origin : "") || "",
  ).toLowerCase();
  if (o.startsWith("capacitor:") || o.startsWith("ionic:")) return true;
  return false;
}

export const SAFE_LOCALES = ["en-GB", "en"];
export const IN_LOCALES = ["en-IN", ...SAFE_LOCALES];

export function formatLocales(ua) {
  return isFragileAndroid(ua) ? SAFE_LOCALES : IN_LOCALES;
}
