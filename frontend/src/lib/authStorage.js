export const TOKEN_KEY = "euler_token";

/** localStorage in a home-screen app can throw (private mode, quota). Never crash login. */
export function readStoredToken() {
  try {
    return window.localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function writeStoredToken(token) {
  try {
    window.localStorage.setItem(TOKEN_KEY, token);
    return true;
  } catch {
    return false;
  }
}

export function clearStoredToken() {
  try {
    window.localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* ignore */
  }
}

/**
 * True when the JWT `exp` is already past (with a few seconds of skew).
 * Opaque / unreadable tokens return false so the API remains the source of truth.
 */
export function jwtExpired(token, nowMs = Date.now(), skewMs = 5000) {
  if (!token || typeof token !== "string") return true;
  const parts = token.split(".");
  if (parts.length < 2) return false;
  try {
    const b64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const pad = "=".repeat((4 - (b64.length % 4)) % 4);
    const payload = JSON.parse(atob(b64 + pad));
    if (typeof payload.exp !== "number") return false;
    return payload.exp * 1000 < nowMs + skewMs;
  } catch {
    return false;
  }
}

export function requestAuthHeader(config) {
  const headers = config?.headers;
  if (!headers) return "";
  if (typeof headers.get === "function") return String(headers.get("Authorization") || "");
  return String(headers.Authorization || headers.authorization || "");
}

/**
 * A 401 must not wipe a token that was stored *after* this request was sent.
 * That race is common on a slow phone: stale /auth/me returns after a fresh login.
 */
export function shouldClearTokenOn401({ url, path, storedToken, requestAuth }) {
  const u = String(url || "");
  const p = String(path || "");
  if (u.includes("/auth/login") || u.includes("/auth/change-password")) return false;
  if (p.startsWith("/login") || p.startsWith("/share")) return false;
  if (storedToken && requestAuth && requestAuth !== `Bearer ${storedToken}`) return false;
  return true;
}
