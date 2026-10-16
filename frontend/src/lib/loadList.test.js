/**
 * @jest-environment jsdom
 */
import { loadList } from "./loadList";

const mockGet = jest.fn();
const mockToast = { error: jest.fn() };

jest.mock("./api", () => ({
  get: (...args) => mockGet(...args),
  apiErrorMessage: (_e, fallback) => fallback || "failed",
}));

jest.mock("sonner", () => ({
  toast: { error: (...args) => mockToast.error(...args) },
}));

beforeEach(() => {
  mockGet.mockReset();
  mockToast.error.mockReset();
});

test("sets rows from a successful list", async () => {
  mockGet.mockResolvedValue([{ leadId: "LD1" }]);
  const setRows = jest.fn();
  const rows = await loadList("/leads", setRows, { status: "all" }, "Could not load leads");
  expect(rows).toEqual([{ leadId: "LD1" }]);
  expect(setRows).toHaveBeenCalledWith([{ leadId: "LD1" }]);
  expect(mockToast.error).not.toHaveBeenCalled();
});

test("toasts and shows empty instead of looking like no records", async () => {
  mockGet.mockRejectedValue(new Error("timeout"));
  const setRows = jest.fn();
  const rows = await loadList("/leads", setRows, {}, "Could not load leads");
  expect(rows).toEqual([]);
  expect(setRows).toHaveBeenCalledWith([]);
  expect(mockToast.error).toHaveBeenCalledWith("Could not load leads");
});
