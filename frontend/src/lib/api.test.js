import { apiBases, isRetryableNetworkError } from "./api";

describe("apiBases", () => {
  test("Railway first, then the page origin", () => {
    expect(apiBases("https://euler-crm-production.up.railway.app", "https://app.example"))
      .toEqual([
        "https://euler-crm-production.up.railway.app",
        "https://app.example",
      ]);
  });

  test("does not duplicate when already on Railway", () => {
    expect(apiBases("https://host", "https://host")).toEqual(["https://host"]);
  });
});

describe("isRetryableNetworkError", () => {
  test("no response is a network miss", () => {
    expect(isRetryableNetworkError({ message: "Network Error" })).toBe(true);
  });

  test("timeout is retryable", () => {
    expect(isRetryableNetworkError({ code: "ECONNABORTED" })).toBe(true);
  });

  test("401 is not retried on another host", () => {
    expect(isRetryableNetworkError({ response: { status: 401 } })).toBe(false);
  });

  test("502 is retryable", () => {
    expect(isRetryableNetworkError({ response: { status: 502 } })).toBe(true);
  });
});
