/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { amountLabel } from "./format";
import { isUnreportedWriteError } from "./actionErrors";
import { useDebouncedValue } from "./useDebounced";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;

describe("amountLabel", () => {
  test("reads a typed amount back so a missing zero is visible", () => {
    expect(amountLabel("Amount (₹)", "")).toBe("Amount (₹)");
    expect(amountLabel("Amount (₹)", "0")).toBe("Amount (₹)");
    expect(amountLabel("Amount (₹)", "abc")).toBe("Amount (₹)");
    const label = amountLabel("Amount (₹)", "150000");
    expect(label.startsWith("Amount (₹) · ")).toBe(true);
    expect(label.replace(/[^0-9]/g, "")).toBe("150000");
  });
});

describe("isUnreportedWriteError", () => {
  test("reports failed writes, not background reads", () => {
    expect(isUnreportedWriteError({ isAxiosError: true, config: { method: "post" } })).toBe(true);
    expect(isUnreportedWriteError({ isAxiosError: true, config: { method: "delete" } })).toBe(true);
    expect(isUnreportedWriteError({ isAxiosError: true, config: { method: "get" } })).toBe(false);
    expect(isUnreportedWriteError(new Error("not from the api"))).toBe(false);
    expect(isUnreportedWriteError(undefined)).toBe(false);
  });
});

describe("useDebouncedValue", () => {
  beforeEach(() => jest.useFakeTimers());
  afterEach(() => jest.useRealTimers());

  function Probe({ value, seen }) {
    seen.push(useDebouncedValue(value, 300));
    return null;
  }

  test("waits for typing to stop, but clears at once", () => {
    const host = document.createElement("div");
    const root = createRoot(host);
    const seen = [];
    act(() => { root.render(<Probe value="98" seen={seen} />); });
    act(() => { root.render(<Probe value="9876" seen={seen} />); });
    expect(seen[seen.length - 1]).toBe("98");
    act(() => { jest.advanceTimersByTime(300); });
    expect(seen[seen.length - 1]).toBe("9876");
    act(() => { root.render(<Probe value="" seen={seen} />); });
    expect(seen[seen.length - 1]).toBe("");
    act(() => root.unmount());
  });
});
