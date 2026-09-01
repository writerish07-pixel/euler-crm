/** Same login the Coulson dealer portal uses in the browser.

Coulson's SPA is:

  POST https://euler-auth.eulerlogistics.com/api/v1/login
  Authorization: Basic btoa(`${username}:${password}:coulson`)

Euler's CORS list includes https://euler-crm.onrender.com, so Settings can
call this directly instead of hoping Railway's urllib POST looks like fetch.
*/

export const COULSON_AUTH_LOGIN = "https://euler-auth.eulerlogistics.com/api/v1/login";
export const COULSON_APP = "coulson";

export function coulsonBasicToken(username, password) {
  const raw = `${username}:${password}:${COULSON_APP}`;
  try {
    return btoa(raw);
  } catch {
    // btoa throws on characters > 255; this matches what a UTF-8 browser would need.
    return btoa(unescape(encodeURIComponent(raw)));
  }
}

export async function coulsonPortalLogin(username, password) {
  const user = String(username || "").trim();
  const pw = String(password || "").trim();
  if (!user || !pw) {
    const err = new Error("Coulson username and password are required");
    err.code = "missing";
    throw err;
  }
  const res = await fetch(COULSON_AUTH_LOGIN, {
    method: "POST",
    headers: {
      Authorization: `Basic ${coulsonBasicToken(user, pw)}`,
      "Access-Control-Allow-Origin": "*",
    },
  });
  let payload = {};
  try {
    payload = await res.json();
  } catch {
    payload = {};
  }
  if (!payload.success) {
    const err = new Error(payload.message || res.statusText || "Coulson login failed");
    err.status = res.status;
    err.code = "rejected";
    throw err;
  }
  const token = payload.data && payload.data.token;
  if (!token) {
    const err = new Error("Coulson login returned no token");
    err.code = "rejected";
    throw err;
  }
  return token;
}

/** CORS / network failures look like TypeError Failed to fetch — not a bad password. */
export function isCoulsonNetworkError(err) {
  if (!err) return false;
  if (err.code === "rejected" || err.code === "missing") return false;
  const m = String(err.message || "").toLowerCase();
  return err.name === "TypeError" || m.includes("failed to fetch") || m.includes("network");
}
