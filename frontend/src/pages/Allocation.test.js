/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    const path = String(url || "");
    if (path.indexOf("allocation/summary") >= 0) {
      return Promise.resolve({
        activeLeads: 498,
        unassigned: 400,
        executives: [{ executive: "Amit", total: 20, open: 10, booked: 10 }],
        split: {
          shares: [
            { executive: "Amit", pct: 50 },
            { executive: "Devang", pct: 50 },
          ],
          totalPct: 100,
        },
        executiveMatches: [],
      });
    }
    if (path === "/leads") return Promise.resolve([]);
    if (path === "/masters") return Promise.resolve({ executives: ["Amit", "Devang"] });
    return Promise.resolve({});
  },
  post: () => Promise.resolve({}),
  put: () => Promise.resolve({}),
  apiErrorMessage: (err, fallback) => err?.message || fallback || "err",
}));

jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canEditLeadSplit: true }),
}));

import Allocation from "./Allocation";

test("allocation split grid and lead table are capped with internal scroll", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(<Allocation />);
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(document.querySelector('[data-testid="split-apply-btn"]')?.textContent).toMatch(/Apply to 400 unassigned/);
  expect(document.querySelector('[data-testid="split-grid-scroll"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="unassigned-note"]')?.textContent).toMatch(/Apply to unassigned/);
  expect(document.querySelector('[data-testid="table-scroll"]')).toBeTruthy();
});
