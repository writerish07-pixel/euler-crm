import { formatInr, num, resolveNumberLocale, resolveDateLocale, fmtDate, fmtTime } from "./format";

describe("resolveNumberLocale", () => {
  test("skips en-IN when the WebView throws RangeError", () => {
    function FakeNumberFormat(loc) {
      if (loc === "en-IN") throw new RangeError("Incorrect locale information provided");
      return { format: (n) => String(n) };
    }
    expect(resolveNumberLocale({ NumberFormat: FakeNumberFormat })).toBe("en-GB");
  });

  test("OPPO UA never probes en-IN even if NumberFormat would accept it", () => {
    const seen = [];
    function FakeNumberFormat(loc) {
      seen.push(loc);
      return { format: (n) => String(n) };
    }
    expect(resolveNumberLocale(
      { NumberFormat: FakeNumberFormat },
      "Mozilla/5.0 (Linux; Android 15; CPH2827) AppleWebKit/537.36 Chrome/131.0.0.0 Mobile Safari/537.36",
    )).toBe("en-GB");
    expect(seen).not.toContain("en-IN");
  });

  test("returns null when currency formatting is unavailable", () => {
    function Boom() {
      throw new RangeError("no ICU");
    }
    expect(resolveNumberLocale({ NumberFormat: Boom })).toBe(null);
  });
});

describe("formatInr", () => {
  test("does not throw when locale is null", () => {
    expect(formatInr(2500, {}, null)).toBe("₹2500");
  });

  test("num does not throw on ordinary numbers", () => {
    expect(typeof num(12)).toBe("string");
  });
});

describe("fmtDate / fmtTime", () => {
  test("fmtDate returns a string for an ISO date", () => {
    const s = fmtDate("2026-09-07");
    expect(s).toBeTruthy();
    expect(s).not.toBe("—");
  });

  test("fmtTime returns a string for an ISO datetime", () => {
    const s = fmtTime("2026-09-07T10:15:00");
    expect(s).toBeTruthy();
    expect(s).not.toBe("—");
  });
});

describe("resolveDateLocale", () => {
  test("skips en-IN when toLocaleString throws RangeError", () => {
    const probe = {
      toLocaleString(loc) {
        if (loc === "en-IN") throw new RangeError("Incorrect locale information provided");
        return "ok";
      },
    };
    expect(resolveDateLocale(probe)).toBe("en-GB");
  });
});
