import { shouldBypassSwNavigation, shouldReloadOnControllerChange } from "./pwa";

describe("shouldBypassSwNavigation", () => {
  test("pull-to-refresh navigations are not intercepted", () => {
    expect(shouldBypassSwNavigation({ method: "GET", mode: "navigate", cache: "reload" })).toBe(true);
    expect(shouldBypassSwNavigation({ method: "GET", mode: "navigate", cache: "no-cache" })).toBe(true);
  });

  test("ordinary navigations still go through the worker", () => {
    expect(shouldBypassSwNavigation({ method: "GET", mode: "navigate", cache: "default" })).toBe(false);
  });

  test("API and asset fetches are not treated as reloads", () => {
    expect(shouldBypassSwNavigation({ method: "GET", mode: "cors", cache: "reload" })).toBe(false);
    expect(shouldBypassSwNavigation({ method: "POST", mode: "navigate", cache: "reload" })).toBe(false);
  });
});

describe("shouldReloadOnControllerChange", () => {
  test("reloads only on the login screen", () => {
    expect(shouldReloadOnControllerChange({
      flagged: true, alreadyReloaded: false, pathname: "/login",
    })).toBe(true);
  });

  test("does not reload after sign-in (OPPO/vivo blank screen)", () => {
    expect(shouldReloadOnControllerChange({
      flagged: true, alreadyReloaded: false, pathname: "/",
    })).toBe(false);
  });

  test("does not reload twice", () => {
    expect(shouldReloadOnControllerChange({
      flagged: true, alreadyReloaded: true, pathname: "/login",
    })).toBe(false);
  });
});
