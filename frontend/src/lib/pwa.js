/**
 * Service-worker registration and the online/offline signal.
 *
 * Registered in production only — in development a cached shell fights the dev
 * server and produces "why is my change not showing" confusion.
 */
export function registerServiceWorker() {
  if (process.env.NODE_ENV !== "production") return;
  if (!("serviceWorker" in navigator)) return;

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").then((reg) => {
      // A new build is live: take it on the next navigation rather than
      // swapping code under a form someone is part-way through filling in.
      reg.addEventListener("updatefound", () => {
        const next = reg.installing;
        if (!next) return;
        next.addEventListener("statechange", () => {
          if (next.state === "installed" && navigator.serviceWorker.controller) {
            window.__eulerUpdateReady = true;
            window.dispatchEvent(new Event("euler:update-ready"));
          }
        });
      });
    }).catch(() => {
      // A failed registration must never break the app — it just means no
      // offline shell this session.
    });
  });
}

export function applyUpdate() {
  if (!("serviceWorker" in navigator)) return;
  navigator.serviceWorker.getRegistration().then((reg) => {
    if (reg?.waiting) reg.waiting.postMessage("SKIP_WAITING");
    window.location.reload();
  });
}
