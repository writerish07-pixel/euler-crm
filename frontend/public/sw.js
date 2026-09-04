/* Euler CRM service worker.
 *
 * THE RULE THAT MATTERS: /api/* is NEVER cached. Every figure in this app —
 * outstanding, payable, scheme, finance — is live. A CRM that serves yesterday's
 * balance from cache is worse than one that fails honestly, and the resulting
 * "wrong numbers" bugs are near-impossible to diagnose from the outside.
 *
 * So: assets are cached (they are content-hashed and immutable), navigations
 * fall back to a cached shell so the app opens offline instead of showing the
 * browser's error page, and data always comes from the network.
 */
const VERSION = "euler-v3-mobile-login";
const SHELL = `${VERSION}-shell`;
const ASSETS = `${VERSION}-assets`;
const OFFLINE_URL = "/index.html";

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(SHELL)
      .then((c) => c.addAll([OFFLINE_URL, "/manifest.json", "/icon-192.png"]))
      // A missing file must not wedge the install and leave the app uninstallable.
      .catch(() => undefined)
      .then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(
        keys.filter((k) => !k.startsWith(VERSION)).map((k) => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// Let the page trigger an immediate update instead of waiting for a reload.
self.addEventListener("message", (event) => {
  if (event.data === "SKIP_WAITING") self.skipWaiting();
});

function isApi(url) {
  return url.pathname.startsWith("/api/") || url.pathname === "/api";
}

function isAsset(url) {
  // Never cache-first the worker or manifest — an installed phone would keep
  // last week's login form after a deploy.
  if (url.pathname === "/sw.js" || url.pathname === "/manifest.json") return false;
  return url.pathname.startsWith("/static/")
    || /\.(?:js|css|png|jpg|jpeg|svg|webp|ico|woff2?)$/i.test(url.pathname);
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") return;

  let url;
  try { url = new URL(request.url); } catch { return; }

  // 1. Live data — straight to the network, no cache, ever.
  if (isApi(url)) return;

  // 2. Navigations — network first so a deploy is picked up immediately;
  //    fall back to the cached shell so the app still opens with no signal.
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match(OFFLINE_URL).then(
        (r) => r || Response.error()
      ))
    );
    return;
  }

  // 3. Same-origin build assets — content-hashed, so cache-first is safe.
  if (url.origin === self.location.origin && isAsset(url)) {
    event.respondWith(
      caches.match(request).then((hit) => hit || fetch(request).then((res) => {
        if (res && res.status === 200) {
          const copy = res.clone();
          caches.open(ASSETS).then((c) => c.put(request, copy)).catch(() => undefined);
        }
        return res;
      }))
    );
    return;
  }

  // 4. Fonts (Google / Fontshare) — serve cached, refresh in the background.
  if (/fonts\.(googleapis|gstatic)\.com$|api\.fontshare\.com$/.test(url.hostname)) {
    event.respondWith(
      caches.match(request).then((hit) => {
        const net = fetch(request).then((res) => {
          if (res && (res.status === 200 || res.type === "opaque")) {
            const copy = res.clone();
            caches.open(ASSETS).then((c) => c.put(request, copy)).catch(() => undefined);
          }
          return res;
        }).catch(() => hit);
        return hit || net;
      })
    );
  }
});

self.addEventListener("push", (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch { data = {}; }
  const title = data.title || "Euler CRM";
  const body = data.body || "Open Approvals";
  const url = data.url || "/approvals";
  event.waitUntil(
    self.registration.showNotification(title, {
      body,
      icon: "/icon-192.png",
      badge: "/icon-192.png",
      data: { url },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const url = (event.notification.data && event.notification.data.url) || "/approvals";
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      for (const w of windows) {
        if (w.url && "focus" in w) {
          w.focus();
          if (w.navigate) w.navigate(url);
          return;
        }
      }
      if (self.clients.openWindow) return self.clients.openWindow(url);
    })
  );
});
