// Minimal Worker entry for Cloudflare Workers Builds (frontend rootDir).
export default {
  async fetch(request, env) {
    if (env.ASSETS) {
      return env.ASSETS.fetch(request);
    }
    return new Response("Euler CRM assets binding missing", { status: 500 });
  },
};
