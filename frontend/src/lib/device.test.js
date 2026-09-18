import { isFragileAndroid, formatLocales, isNativeShell } from "./device";

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

describe("isNativeShell", () => {
  test("is false in a normal browser tab", () => {
    expect(isNativeShell({ origin: "https://euler-crm.onrender.com", protocol: "https:", capacitor: undefined })).toBe(false);
  });

  test("is true in the Capacitor Android/iOS WebView", () => {
    expect(isNativeShell({ origin: "https://localhost", protocol: "https:", capacitor: { isNativePlatform: () => true } })).toBe(true);
    expect(isNativeShell({ origin: "capacitor://localhost", protocol: "capacitor:", capacitor: undefined })).toBe(true);
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
