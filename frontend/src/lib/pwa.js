import { isFragileAndroid } from "./device";

const FRAGILE_SW_CLEARED = "euler_cleared_sw_v7";

/**
 * Service-worker registration and the online/offline signal.
 *
 * Registered in production only — in development a cached shell fights the dev
 * server and produces "why is my change not showing" confusion.
 */

/** Drop a stale worker/shell on OPPO/vivo so they cannot keep last week's
 *  crashing dashboard. Returns a promise that reloads once if a controller was live. */
export function dropFragileAndroidWorker({ reload = true } = {}) {
  if (typeof window === "undefined") return Promise.resolve(false);
  if (!isFragileAndroid()) return Promise.resolve(false);
  if (!("serviceWorker" in navigator)) return Promise.resolve(false);
  let already = false;
  try { already = Boolean(sessionStorage.getItem(FRAGILE_SW_CLEARED)); } catch { /* ignore */ }
  const hadController = Boolean(navigator.serviceWorker.controller);
  const mark = () => {
    try { sessionStorage.setItem(FRAGILE_SW_CLEARED, "1"); } catch { /* ignore */ }
  };
  const regs = navigator.serviceWorker.getRegistrations()
    .then((list) => Promise.all(list.map((r) => r.unregister())))
    .catch(() => undefined);
  const cache = (typeof caches !== "undefined"
    ? caches.keys().then((keys) => Promise.all(keys.map((k) => caches.delete(k))))
    : Promise.resolve())
    .catch(() => undefined);
  return Promise.all([regs, cache]).then(() => {
    mark();
    if (reload && !already && hadController) {
      window.location.reload();
      return true;
    }
    return false;
  });
}

export async function clearSiteDataAndReload() {
  try {
    try {
      sessionStorage.removeItem("euler_api_base");
      sessionStorage.removeItem(FRAGILE_SW_CLEARED);
    } catch { /* ignore */ }
    if ("serviceWorker" in navigator) {
      const list = await navigator.serviceWorker.getRegistrations();
      await Promise.all(list.map((r) => r.unregister()));
    }
    if (typeof caches !== "undefined") {
      const keys = await caches.keys();
      await Promise.all(keys.map((k) => caches.delete(k)));
    }
  } catch { /* ignore */ }
  window.location.replace(cacheBustHref());
}

/** ColorOS `location.reload()` often keeps the crashing JS. A new query string
 *  forces Chrome to fetch index.html again. */
export function cacheBustHref(href = typeof window !== "undefined" ? window.location.href : "/", now = Date.now()) {
  try {
    const u = new URL(href, "https://euler.local");
    u.searchParams.set("euler", String(now));
    return `${u.pathname}${u.search}${u.hash}`;
  } catch {
    return `/?euler=${now}`;
  }
}

function markUpdateReady() {
  window.__eulerUpdateReady = true;
  window.dispatchEvent(new Event("euler:update-ready"));
}

function watchRegistration(reg) {
  if (reg.waiting && navigator.serviceWorker.controller) markUpdateReady();
  reg.addEventListener("updatefound", () => {
    const next = reg.installing;
    if (!next) return;
    next.addEventListener("statechange", () => {
      if (next.state === "installed" && navigator.serviceWorker.controller) {
        markUpdateReady();
      }
    });
  });
}

export function registerServiceWorker() {
  if (process.env.NODE_ENV !== "production") return;
  if (!("serviceWorker" in navigator)) return;

  // Installed ColorOS/OriginOS shells keep a cached index.html that still
  // crashes on en-IN. Do not register a worker on those phones.
  if (isFragileAndroid()) {
    dropFragileAndroidWorker();
    return;
  }

  const check = () => {
    navigator.serviceWorker.getRegistration().then((reg) => {
      if (reg) reg.update().catch(() => undefined);
    });
  };

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      // A new build is live: take it on the next tap of the update bar rather
      // than swapping code under a form someone is part-way through filling in.
      watchRegistration(reg);
      reg.update().catch(() => undefined);
    }).catch(() => {
      // A failed registration must never break the app — it just means no
      // offline shell this session.
    });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "visible") check();
  });
}

export function applyUpdate() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.getRegistration().then((reg) => {
    if (reg?.waiting) reg.waiting.postMessage("SKIP_WAITING");
    window.location.reload();
  });
}

/** Pull-to-refresh / explicit reload. ColorOS and OriginOS abort a
 *  service-worker-handled navigate and then paint a blank document. */
export function shouldBypassSwNavigation(request) {
  if (!request || request.method !== "GET") return false;
  if (request.mode !== "navigate") return false;
  return request.cache === "reload" || request.cache === "no-cache";
}

/** Only reload on the login screen. Reloading after Sign In blanks OPPO/vivo. */
export function shouldReloadOnControllerChange({ flagged, alreadyReloaded, pathname } = {}) {
  if (!flagged || alreadyReloaded) return false;
  const path = String(pathname || "");
  return path === "/login" || path === "/login/";
}

/** On the login screen, take a waiting worker immediately so staff phones
 *  are not stuck on last week's sign-in code. */
export function primeLoginApp() {
  if (typeof window === "undefined") return;
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.getRegistration().then((reg) => {
    if (!reg) return;
    if (reg.waiting) {
      window.__eulerReloadOnController = true;
      reg.waiting.postMessage("SKIP_WAITING");
    }
    reg.update().catch(() => undefined);
  });
  navigator.serviceWorker.addEventListener("controllerchange", () => {
    if (!shouldReloadOnControllerChange({
      flagged: window.__eulerReloadOnController,
      alreadyReloaded: window.__eulerReloadedOnce,
      pathname: window.location.pathname,
    })) return;
    window.__eulerReloadedOnce = true;
    window.location.reload();
  });
}

function urlBase64ToUint8Array(b64) {
  const pad = "=".repeat((4 - (b64.length % 4)) % 4);
  const raw = atob((b64 + pad).replace(/-/g, "+").replace(/_/g, "/"));
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i += 1) out[i] = raw.charCodeAt(i);
  return out;
}

/** Subscribe for phone alerts. Never throws. Pass requestPermission only from a tap. */
export async function enableApproverPush({ requestPermission = true } = {}) {
  if (typeof window === "undefined") return { ok: false, reason: "ssr" };
  if (!("serviceWorker" in navigator) || !("PushManager" in window) || !("Notification" in window)) {
    return { ok: false, reason: "unsupported" };
  }
  try {
    const { get, post } = await import("./api");
    const vapid = await get("/push/vapid-public");
    if (!vapid?.publicKey) return { ok: false, reason: "no-key" };
    if (Notification.permission === "denied") return { ok: false, reason: "denied" };
    if (Notification.permission !== "granted") {
      if (!requestPermission) return { ok: false, reason: "prompt" };
      const perm = await Notification.requestPermission();
      if (perm !== "granted") return { ok: false, reason: perm };
    }
    const existing = await navigator.serviceWorker.getRegistration();
    if (!existing) return { ok: false, reason: "no-sw" };
    const reg = existing.installing || existing.waiting || existing.active
      ? existing
      : await navigator.serviceWorker.ready;
    let sub = await reg.pushManager.getSubscription();
    if (!sub) {
      sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(vapid.publicKey),
      });
    }
    await post("/push/subscribe", sub.toJSON());
    return { ok: true };
  } catch {
    return { ok: false, reason: "failed" };
  }
}