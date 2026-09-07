import axios from "axios";
import {
  TOKEN_KEY,
  readStoredToken,
  clearStoredToken,
  requestAuthHeader,
  shouldClearTokenOn401,
} from "./authStorage";

// CRA inlines REACT_APP_* at build time. If the production build is made without
// frontend/.env.production the value is undefined and every call silently goes to
// "undefined/api" — surface that immediately instead of shipping a broken bundle.
const CONFIGURED = String(process.env.REACT_APP_BACKEND_URL || "").replace(/\/$/, "");
if (!CONFIGURED) {
  // eslint-disable-next-line no-console
  console.error(
    "REACT_APP_BACKEND_URL is not set. The app cannot reach the API. " +
      "Set it in frontend/.env.production (or the host's build environment) and rebuild."
  );
}

const REMEMBER_KEY = "euler_api_base";

export function pageOrigin() {
  if (typeof window === "undefined") return "";
  try {
    return String(window.location.origin || "").replace(/\/$/, "");
  } catch {
    return "";
  }
}

/** Railway first, then same-origin only when that host actually proxies /api
 *  (Cloudflare Worker). Render's SPA rewrite serves index.html for /api/* and
 *  OPPO/vivo then crash reading dashboard.outstanding.customer on a string. */
export function originCanProxyApi(origin = "") {
  const o = String(origin || "").toLowerCase();
  if (!o) return false;
  if (o.includes("onrender.com")) return false;
  if (o.includes("github.io")) return false;
  return true;
}

export function apiBases(configured = CONFIGURED, origin = pageOrigin()) {
  const out = [];
  const add = (b) => {
    const n = String(b || "").replace(/\/$/, "");
    if (n && !out.includes(n)) out.push(n);
  };
  add(configured);
  if (originCanProxyApi(origin)) add(origin);
  return out.length ? out : [""];
}

export function isHtmlApiBody(data) {
  if (typeof data !== "string") return false;
  const s = data.trimStart().slice(0, 32).toLowerCase();
  return s.startsWith("<!doctype") || s.startsWith("<html") || s.startsWith("<");
}

export function isRetryableNetworkError(err) {
  if (!err) return false;
  const code = err.code || err.cause?.code;
  if (code === "ERR_BAD_PAYLOAD") return true;
  if (code === "ECONNABORTED" || code === "ERR_NETWORK" || code === "ERR_CANCELED") {
    return err.code !== "ERR_CANCELED";
  }
  if (!err.response) return true;
  return [502, 503, 504].includes(err.response.status);
}

function readRemembered() {
  try {
    return String(window.sessionStorage.getItem(REMEMBER_KEY) || "").replace(/\/$/, "");
  } catch {
    return "";
  }
}

function remember(base) {
  try {
    window.sessionStorage.setItem(REMEMBER_KEY, String(base || ""));
  } catch {
    /* private mode */
  }
}

function orderBases() {
  const all = apiBases();
  const preferred = readRemembered();
  if (preferred && all.includes(preferred)) {
    return [preferred, ...all.filter((b) => b !== preferred)];
  }
  return all;
}

export const api = axios.create({ timeout: 25000 });

function applyBase(base) {
  api.defaults.baseURL = `${base || ""}/api`;
}

applyBase(orderBases()[0] || CONFIGURED || "");

export { TOKEN_KEY };

api.interceptors.request.use((config) => {
  const token = readStoredToken();
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => {
    if (r?.config?.responseType === "blob") return r;
    const type = String(r?.headers?.["content-type"] || r?.headers?.["Content-Type"] || "");
    if (type.includes("text/html") || isHtmlApiBody(r.data)) {
      const err = new Error("API returned a web page instead of data");
      err.code = "ERR_BAD_PAYLOAD";
      err.config = r.config;
      return Promise.reject(err);
    }
    return r;
  },
  (err) => {
    if (err.response?.status === 401) {
      const url = String(err.config?.url || "");
      const path = window.location.pathname || "";
      if (shouldClearTokenOn401({
        url,
        path,
        storedToken: readStoredToken(),
        requestAuth: requestAuthHeader(err.config),
      })) {
        clearStoredToken();
        window.location.href = "/login";
      }
    }
    return Promise.reject(err);
  }
);

async function withFallback(run) {
  const bases = orderBases();
  let last;
  for (const base of bases) {
    applyBase(base);
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const data = await run();
        remember(base);
        return data;
      } catch (err) {
        last = err;
        if (err?.response && !isRetryableNetworkError(err)) throw err;
        if (attempt === 0 && isRetryableNetworkError(err)) {
          await new Promise((r) => setTimeout(r, 350));
          continue;
        }
        break;
      }
    }
  }
  throw last;
}

export const get = (url, params) => withFallback(() => api.get(url, { params }).then((r) => r.data));
export const post = (url, body) => withFallback(() => api.post(url, body).then((r) => r.data));
export const put = (url, body) => withFallback(() => api.put(url, body).then((r) => r.data));
export const del = (url) => withFallback(() => api.delete(url).then((r) => r.data));

/** Multipart POST. Let the browser set Content-Type with the boundary — a
 *  hardcoded `multipart/form-data` header has none, and FastAPI then 422s. */
export const postForm = (url, formData) => withFallback(() => api.post(url, formData).then((r) => r.data));

export function apiErrorMessage(err, fallback = "Request failed") {
  const data = err?.response?.data;
  const detail = data && typeof data === "object" && !(typeof Blob !== "undefined" && data instanceof Blob)
    ? data.detail
    : (typeof data === "string" ? data : null);
  if (typeof detail === "string" && detail.trim()) return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((x) => {
      if (typeof x === "string") return x;
      if (x && typeof x === "object") return x.msg || x.message || x.detail || "";
      return "";
    }).filter(Boolean);
    if (parts.length) return parts.join(" · ");
  }
  if (detail && typeof detail === "object") {
    return detail.msg || detail.message || fallback;
  }
  return err?.message || fallback;
}

export const uploadFile = (url, file, fields = {}) => {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(fields).forEach(([k, v]) => {
    if (v != null && v !== "") fd.append(k, String(v));
  });
  return postForm(url, fd);
};

async function messageFromBlobError(err, fallback) {
  const data = err?.response?.data;
  if (typeof Blob === "undefined" || !(data instanceof Blob)) {
    return apiErrorMessage(err, fallback);
  }
  try {
    const parsed = JSON.parse(await data.text());
    return apiErrorMessage({ response: { data: parsed } }, fallback);
  } catch {
    return apiErrorMessage(err, fallback);
  }
}

export async function downloadFile(url, filename) {
  try {
    const data = await withFallback(() => api.get(url, { responseType: "blob" }).then((r) => r.data));
    const type = String(data?.type || "");
    if (type.includes("application/json") || type.includes("text/html")) {
      let text = "";
      try { text = await data.text(); } catch { /* empty */ }
      let parsed = null;
      try { parsed = JSON.parse(text); } catch { /* not json */ }
      const msg = parsed
        ? apiErrorMessage({ response: { data: parsed } }, "Download failed")
        : "Could not download file";
      throw Object.assign(new Error(msg), { response: { data: parsed || { detail: msg } } });
    }
    const blob = data instanceof Blob ? data : new Blob([data]);
    const link = document.createElement("a");
    link.href = window.URL.createObjectURL(blob);
    link.download = filename;
    link.click();
    window.URL.revokeObjectURL(link.href);
  } catch (err) {
    const msg = await messageFromBlobError(err, "Could not download file");
    throw Object.assign(new Error(msg), { response: { data: { detail: msg } }, cause: err });
  }
}
