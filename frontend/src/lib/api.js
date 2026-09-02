import axios from "axios";

// CRA inlines REACT_APP_* at build time. If the production build is made without
// frontend/.env.production the value is undefined and every call silently goes to
// "undefined/api" — surface that immediately instead of shipping a broken bundle.
const BASE = process.env.REACT_APP_BACKEND_URL;
if (!BASE) {
  // eslint-disable-next-line no-console
  console.error(
    "REACT_APP_BACKEND_URL is not set. The app cannot reach the API. " +
      "Set it in frontend/.env.production (or the host's build environment) and rebuild."
  );
}
export const api = axios.create({ baseURL: `${BASE || ""}/api` });

export const TOKEN_KEY = "euler_token";

api.interceptors.request.use((config) => {
  const token = localStorage.getItem(TOKEN_KEY);
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    const url = String(err.config?.url || "");
    const path = window.location.pathname || "";
    const isFormAuth = url.includes("/auth/login") || url.includes("/auth/change-password");
    if (err.response?.status === 401 && !isFormAuth
        && !path.startsWith("/login") && !path.startsWith("/share")) {
      localStorage.removeItem(TOKEN_KEY);
      window.location.href = "/login";
    }
    return Promise.reject(err);
  }
);

export const get = (url, params) => api.get(url, { params }).then((r) => r.data);
export const post = (url, body) => api.post(url, body).then((r) => r.data);
export const put = (url, body) => api.put(url, body).then((r) => r.data);
export const del = (url) => api.delete(url).then((r) => r.data);

export async function downloadFile(url, filename) {
  const res = await api.get(url, { responseType: "blob" });
  const blob = new Blob([res.data]);
  const link = document.createElement("a");
  link.href = window.URL.createObjectURL(blob);
  link.download = filename;
  link.click();
  window.URL.revokeObjectURL(link.href);
}
