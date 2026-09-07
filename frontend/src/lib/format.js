import { formatLocales } from "./device";

/** ColorOS / OriginOS WebViews often ship without ICU for `en-IN` and throw
 *  RangeError the moment the dashboard calls Intl.NumberFormat("en-IN").
 *  On those phones skip `en-IN` entirely — some WebViews accept the tag then
 *  throw later on format() / toLocaleTimeString. */
export function resolveNumberLocale(IntlImpl = globalThis.Intl, ua) {
  if (!IntlImpl || typeof IntlImpl.NumberFormat !== "function") return null;
  for (const loc of formatLocales(ua)) {
    try {
      const fmt = new IntlImpl.NumberFormat(loc, { style: "currency", currency: "INR" });
      fmt.format(1);
      return loc;
    } catch {
      /* try the next locale */
    }
  }
  try {
    new IntlImpl.NumberFormat(undefined, { style: "currency", currency: "INR" }).format(1);
    return undefined;
  } catch {
    return null;
  }
}

export function resolveDateLocale(probe = new Date("2026-09-07T10:00:00"), ua) {
  for (const loc of formatLocales(ua)) {
    try {
      probe.toLocaleString(loc);
      return loc;
    } catch {
      /* try the next locale */
    }
  }
  return undefined;
}

let _numberLocale;
let _numberReady = false;
function numberLocale() {
  if (!_numberReady) {
    _numberLocale = resolveNumberLocale();
    _numberReady = true;
  }
  return _numberLocale;
}

let _dateLocale;
let _dateReady = false;
function dateLocale() {
  if (!_dateReady) {
    _dateLocale = resolveDateLocale();
    _dateReady = true;
  }
  return _dateLocale;
}

function fallbackInr(v, decimals) {
  const n = Number.isFinite(v) ? v : 0;
  const digits = decimals ?? 0;
  const body = digits > 0 ? n.toFixed(digits) : String(Math.round(n));
  return `₹${body}`;
}

export function formatInr(n, opts = {}, locale = numberLocale()) {
  const v = Number(n || 0);
  if (locale === null) return fallbackInr(v, opts.decimals);
  try {
    return new Intl.NumberFormat(locale, {
      style: "currency",
      currency: "INR",
      maximumFractionDigits: opts.decimals ?? 0,
      minimumFractionDigits: opts.decimals ?? 0,
    }).format(v);
  } catch {
    return fallbackInr(v, opts.decimals);
  }
}

export const inr = (n, opts = {}) => formatInr(n, opts);

export const num = (n) => {
  const v = Number(n || 0);
  const loc = numberLocale();
  if (loc === null) return String(Math.round(v));
  try {
    return new Intl.NumberFormat(loc).format(v);
  } catch {
    return String(Math.round(v));
  }
};

export const compactInr = (n) => {
  const v = Number(n || 0);
  if (Math.abs(v) >= 10000000) return `₹${(v / 10000000).toFixed(2)} Cr`;
  if (Math.abs(v) >= 100000) return `₹${(v / 100000).toFixed(2)} L`;
  if (Math.abs(v) >= 1000) return `₹${(v / 1000).toFixed(1)}K`;
  return inr(v);
};

export const ytdCount = (n) => `YTD ${num(n)}`;
export const ytdMoney = (n) => `YTD ${compactInr(n)}`;

function localeDate(dt, run, fallback) {
  try {
    return run(dateLocale());
  } catch {
    try {
      return run(undefined);
    } catch {
      return fallback;
    }
  }
}

export const fmtDate = (d, opts = { day: "2-digit", month: "short", year: "numeric" }) => {
  if (!d) return "—";
  const s = String(d).split("T")[0];
  const dt = new Date(s);
  if (isNaN(dt)) return s;
  return localeDate(
    dt,
    (loc) => dt.toLocaleDateString(loc, opts),
    s,
  );
};

export const fmtTime = (d, opts) => {
  if (!d) return "—";
  const dt = d instanceof Date ? d : new Date(d);
  if (isNaN(dt)) return "—";
  return localeDate(
    dt,
    (loc) => (opts ? dt.toLocaleTimeString(loc, opts) : dt.toLocaleTimeString(loc)),
    dt.toISOString().slice(11, 16),
  );
};

export const fmtWhen = (d) => {
  if (!d) return "—";
  const dt = d instanceof Date ? d : new Date(d);
  if (isNaN(dt)) return "—";
  return localeDate(
    dt,
    (loc) => dt.toLocaleString(loc),
    dt.toISOString().replace("T", " ").slice(0, 16),
  );
};

/** Local calendar date as YYYY-MM-DD for `<input type="date">` defaults. */
export const todayISO = () => {
  const d = new Date();
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
};

/** Last 10 digits of a mobile, or empty if the value is not a real number. */
export function digitsLast10(mobile) {
  const digits = String(mobile || "").replace(/\D/g, "");
  if (digits.length < 10) return "";
  return digits.slice(-10);
}

/** `tel:` href for the device dialer. Indian mobiles are dialled as +91. */
export function telHref(mobile) {
  const last10 = digitsLast10(mobile);
  if (!last10) return "";
  return `tel:+91${last10}`;
}
