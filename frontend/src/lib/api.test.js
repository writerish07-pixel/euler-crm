import { api, apiBases, isRetryableNetworkError, originCanProxyApi, isHtmlApiBody, apiErrorMessage, postForm, post, isBulkMutationPath, bulkStallMessage } from "./api";

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

  test("does not treat Render as an API proxy", () => {
    expect(apiBases(
      "https://euler-crm-production.up.railway.app",
      "https://euler-crm.onrender.com",
    )).toEqual(["https://euler-crm-production.up.railway.app"]);
    expect(originCanProxyApi("https://crm.onrender.com")).toBe(false);
    expect(originCanProxyApi("https://euler-crm.workers.dev")).toBe(true);
  });
});

describe("isHtmlApiBody", () => {
  test("detects an SPA index.html body", () => {
    expect(isHtmlApiBody("<!DOCTYPE html><html><body>Euler CRM</body></html>")).toBe(true);
    expect(isHtmlApiBody({ outstanding: { customer: 1 } })).toBe(false);
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

  test("HTML payload is retryable so we can try another host", () => {
    expect(isRetryableNetworkError({ code: "ERR_BAD_PAYLOAD" })).toBe(true);
  });
});

describe("apiErrorMessage", () => {
  test("uses a string FastAPI detail", () => {
    expect(apiErrorMessage({ response: { data: { detail: "Pick an executive" } } })).toBe("Pick an executive");
  });

  test("joins a FastAPI 422 validation list so the toast is readable", () => {
    expect(apiErrorMessage({
      response: { data: { detail: [{ loc: ["body", "file"], msg: "Field required" }] } },
    })).toBe("Field required");
  });

  test("falls back when detail is missing", () => {
    expect(apiErrorMessage({ message: "Network Error" }, "Import failed")).toBe("Network Error");
  });
});

describe("postForm", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("import commit can skip fallback retry and use a long timeout", async () => {
    const spy = jest.spyOn(api, "post").mockResolvedValue({ data: { created: 1 } });
    await postForm("/leads/import/commit", { fake: true }, { timeout: 180000, retry: false });
    expect(spy).toHaveBeenCalledTimes(1);
    expect(spy.mock.calls[0][2]).toEqual({ timeout: 180000 });
  });

  test("retry false does not re-post on network error", async () => {
    const err = Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" });
    const spy = jest.spyOn(api, "post").mockRejectedValue(err);
    await expect(postForm("/leads/import/commit", {}, { retry: false })).rejects.toBe(err);
    expect(spy).toHaveBeenCalledTimes(1);
  });
});

describe("bulk mutations", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  test("allocate and import are bulk paths", () => {
    expect(isBulkMutationPath("/leads/allocate")).toBe(true);
    expect(isBulkMutationPath("/leads/import/commit")).toBe(true);
    expect(isBulkMutationPath("/insurance/mis/apply")).toBe(true);
    expect(isBulkMutationPath("/leads")).toBe(false);
  });

  test("allocate does not retry a dropped connection", async () => {
    const err = Object.assign(new Error("Network Error"), { code: "ERR_NETWORK" });
    const spy = jest.spyOn(api, "post").mockRejectedValue(err);
    await expect(post("/leads/allocate", { leadIds: ["L1"], executive: "Amit" })).rejects.toBe(err);
    expect(spy).toHaveBeenCalledTimes(1);
  });

  test("a dropped bulk call tells the desk not to tap again", () => {
    expect(bulkStallMessage({ message: "Network Error", code: "ERR_NETWORK" }))
      .toMatch(/still be finishing/i);
  });
});
