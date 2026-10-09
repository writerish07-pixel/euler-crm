/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  api: { post: jest.fn() },
  downloadFile: jest.fn(),
  post: jest.fn(),
  apiErrorMessage: (e, fallback) => fallback,
  bulkStallMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: true }),
}));

import { api } from "../lib/api";
import InsuranceMisUpload from "./InsuranceMisUpload";

test("review names unmatched payouts for the MIS month", async () => {
  api.post.mockResolvedValue({
    data: {
      suggestedMapping: {},
      targetFields: [],
      detectedHeaders: [],
      matched: [],
      unmatchedMis: [],
      unmatchedEntries: [
        { entryId: "INS-AUG", customerName: "August Only", policyNumber: "POL-A" },
      ],
      period: { months: ["2026-08"], source: "policyDate", label: "Aug 2026" },
      totals: { matched: 0, unmatchedEntries: 1, unmatchedMis: 0, misAmount: 0 },
    },
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<InsuranceMisUpload onClose={() => {}} onDone={() => {}} />);
  });
  const input = document.querySelector("input[type=\"file\"]");
  expect(input).toBeTruthy();
  const file = new File(["x"], "aug.csv", { type: "text/csv" });
  await act(async () => {
    Object.defineProperty(input, "files", { value: [file] });
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(document.querySelector('[data-testid="mis-period"]').textContent).toMatch(/Aug 2026/);
  expect(document.querySelector('[data-testid="mis-unmatched-register"]').textContent)
    .toMatch(/Aug 2026 register payout/);
  await act(async () => { root.unmount(); });
  host.remove();
});
