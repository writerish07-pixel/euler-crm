// Minimal Worker entry for Cloudflare Workers Builds (frontend rootDir).
const BACKEND = "https://euler-crm-production.up.railway.app";

function withNoStore(res) {
  const headers = new Headers(res.headers);
  headers.set("Cache-Control", "no-cache, no-store, must-revalidate");
  headers.set("Pragma", "no-cache");
  return new Response(res.body, {
    status: res.status,
    statusText: res.statusText,
    headers,
  });
}

function hopByHop() {
  return new Set([
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host",
  ]);
}

async function proxyApi(request, url) {
  const dest = new URL(url.pathname + url.search, BACKEND);
  const headers = new Headers();
  const skip = hopByHop();
  request.headers.forEach((value, key) => {
    if (!skip.has(key.toLowerCase())) headers.set(key, value);
  });
  const init = { method: request.method, headers, redirect: "follow" };
  if (request.method !== "GET" && request.method !== "HEAD") {
    init.body = request.body;
    init.duplex = "half";
  }
  try {
    const upstream = await fetch(dest, init);
    const out = new Headers(upstream.headers);
    out.set("Cache-Control", "no-store");
    return new Response(upstream.body, { status: upstream.status, headers: out });
  } catch {
    return new Response(JSON.stringify({ detail: "Could not reach the API" }), {
      status: 502,
      headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path === "/api" || path.startsWith("/api/") || path === "/health") {
      return proxyApi(request, url);
    }
    if (!env.ASSETS) {
      return new Response("Euler CRM assets binding missing", { status: 500 });
    }
    const res = await env.ASSETS.fetch(request);
    const type = res.headers.get("Content-Type") || "";
    // Installed phones keep a copy of the shell. If sw.js / HTML is cached by
    // the CDN, they never see a login fix. Hashed /static/* assets stay cacheable.
    if (
      path === "/sw.js"
      || path === "/manifest.json"
      || path === "/index.html"
      || type.includes("text/html")
    ) {
      return withNoStore(res);
    }
    return res;
  },
};
