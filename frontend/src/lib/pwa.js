/**
 * Service-worker registration and the online/offline signal.
 *
 * Registered in production only — in development a cached shell fights the dev
 * server and produces "why is my change not showing" confusion.
 */
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