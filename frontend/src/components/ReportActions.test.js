/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  post: jest.fn(() => Promise.resolve({ recomputed: 3, failed: 0 })),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: true }),
}));

import { post } from "../lib/api";
import ReportActions from "./ReportActions";

test("refresh button calls onRefresh", async () => {
  const onRefresh = jest.fn(() => Promise.resolve());
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<ReportActions onRefresh={onRefresh} showRebuild />);
  });
  await act(async () => {
    host.querySelector('[data-testid="report-refresh-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); });
  expect(onRefresh).toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("rebuild posts then reloads", async () => {
  const onRefresh = jest.fn(() => Promise.resolve());
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<ReportActions onRefresh={onRefresh} showRebuild />);
  });
  await act(async () => {
    host.querySelector('[data-testid="report-rebuild-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(post).toHaveBeenCalledWith("/reports/rebuild", {});
  expect(onRefresh).toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});
