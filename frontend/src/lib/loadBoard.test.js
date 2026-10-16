/**
 * @jest-environment jsdom
 */
import { loadBoard } from "./loadBoard";

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

test("sets the board payload", async () => {
  mockGet.mockResolvedValue({ kpis: { totalLeads: 4 } });
  const setData = jest.fn();
  const setErr = jest.fn();
  const data = await loadBoard("/dashboard", setData, setErr, "Could not load dashboard");
  expect(data.kpis.totalLeads).toBe(4);
  expect(setData).toHaveBeenCalledWith({ kpis: { totalLeads: 4 } });
  expect(setErr).toHaveBeenCalledWith("");
  expect(mockToast.error).not.toHaveBeenCalled();
});

test("does not sit on Loading when the board GET fails", async () => {
  mockGet.mockRejectedValue(new Error("timeout"));
  const setData = jest.fn();
  const setErr = jest.fn();
  const data = await loadBoard("/dashboard", setData, setErr, "Could not load dashboard");
  expect(data).toBeNull();
  expect(setData).not.toHaveBeenCalled();
  expect(setErr).toHaveBeenCalledWith("Could not load dashboard");
  expect(mockToast.error).toHaveBeenCalledWith("Could not load dashboard");
});
