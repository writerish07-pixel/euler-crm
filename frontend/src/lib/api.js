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

/** Railway first, then same-origin (Cloudflare Worker proxies /api). */
export function apiBases(configured = CONFIGURED, origin = pageOrigin()) {
  const out = [];
  const add = (b) => {
    const n = String(b || "").replace(/\/$/, "");
    if (n && !out.includes(n)) out.push(n);
  };
  add(configured);
  add(origin);
  return out.length ? out : [""];
}

export function isRetryableNetworkError(err) {
  if (!err) return false;
  const code = err.code || err.cause?.code;
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
  (r) => r,
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

export const uploadFile = (url, file, fields = {}) => {
  const fd = new FormData();
  fd.append("file", file);
  Object.entries(fields).forEach(([k, v]) => {
    if (v != null && v !== "") fd.append(k, String(v));
  });
  return withFallback(() => api.post(url, fd).then((r) => r.data));
};

export async function downloadFile(url, filename) {
  const data = await withFallback(() => api.get(url, { responseType: "blob" }).then((r) => r.data));
  const blob = new Blob([data]);
  const link = document.createElement("a");
  link.href = window.URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(link.href);
}
