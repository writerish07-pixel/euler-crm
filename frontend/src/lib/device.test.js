import { isFragileAndroid, formatLocales } from "./device";

describe("isFragileAndroid", () => {
  test("matches OPPO A6 Pro and vivo Y300", () => {
    expect(isFragileAndroid(
      "Mozilla/5.0 (Linux; Android 15; CPH2827) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    )).toBe(true);
    expect(isFragileAndroid(
      "Mozilla/5.0 (Linux; Android 15; V2429) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36 vivo",
    )).toBe(true);
  });

  test("does not match desktop Chrome or Samsung", () => {
    expect(isFragileAndroid(
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    )).toBe(false);
    expect(isFragileAndroid(
      "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    )).toBe(false);
  });
});

describe("formatLocales", () => {
  test("skips en-IN on ColorOS / OriginOS", () => {
    expect(formatLocales("Linux; Android 15; CPH2827")).toEqual(["en-GB", "en"]);
  });

  test("keeps en-IN on other phones", () => {
    expect(formatLocales("Linux; Android 14; SM-S918B")).toEqual(["en-IN", "en-GB", "en"]);
  });
});
