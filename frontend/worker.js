// Minimal Worker entry for Cloudflare Workers Builds (frontend rootDir).
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

export default {
  async fetch(request, env) {
    if (!env.ASSETS) {
      return new Response("Euler CRM assets binding missing", { status: 500 });
    }
    const url = new URL(request.url);
    const res = await env.ASSETS.fetch(request);
    const path = url.pathname;
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
