// Minimal Worker entry so Cloudflare Workers Builds always has a script
// entry-point. Static files are served via the ASSETS binding / assets config.
export default {
  async fetch(request, env) {
    if (env.ASSETS) {
      return env.ASSETS.fetch(request);
    }
    return new Response("Euler CRM assets binding missing", { status: 500 });
  },
};
