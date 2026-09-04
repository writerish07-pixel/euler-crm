import {
  jwtExpired,
  shouldClearTokenOn401,
  writeStoredToken,
  readStoredToken,
  clearStoredToken,
  TOKEN_KEY,
} from "./authStorage";

function tokenWithExp(expSeconds) {
  const header = btoa(JSON.stringify({ alg: "HS256", typ: "JWT" }));
  const payload = btoa(JSON.stringify({ sub: "u1", exp: expSeconds }));
  return `${header}.${payload}.sig`;
}

describe("jwtExpired", () => {
  test("empty token is expired", () => {
    expect(jwtExpired("")).toBe(true);
    expect(jwtExpired(null)).toBe(true);
  });

  test("unreadable tokens are not treated as expired", () => {
    expect(jwtExpired("not-a-jwt")).toBe(false);
    expect(jwtExpired("a.!!!")).toBe(false);
  });

  test("exp in the past is expired", () => {
    expect(jwtExpired(tokenWithExp(1_700_000_000), 1_800_000_000_000)).toBe(true);
  });

  test("exp in the future is live", () => {
    expect(jwtExpired(tokenWithExp(2_000_000_000), 1_800_000_000_000)).toBe(false);
  });
});

describe("shouldClearTokenOn401", () => {
  test("login 401 does not wipe a session", () => {
    expect(shouldClearTokenOn401({
      url: "/auth/login", path: "/login", storedToken: "new", requestAuth: "Bearer old",
    })).toBe(false);
  });

  test("stale /auth/me must not wipe a token stored after it was sent", () => {
    expect(shouldClearTokenOn401({
      url: "/auth/me", path: "/", storedToken: "new-token", requestAuth: "Bearer old-token",
    })).toBe(false);
  });

  test("matching expired session on a protected page is cleared", () => {
    expect(shouldClearTokenOn401({
      url: "/auth/me", path: "/", storedToken: "same", requestAuth: "Bearer same",
    })).toBe(true);
  });
});

describe("token storage", () => {
  afterEach(() => clearStoredToken());

  test("round-trips a token", () => {
    expect(writeStoredToken("abc")).toBe(true);
    expect(readStoredToken()).toBe("abc");
    expect(window.localStorage.getItem(TOKEN_KEY)).toBe("abc");
    clearStoredToken();
    expect(readStoredToken()).toBe(null);
  });
});
