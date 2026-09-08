/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { post } from "../lib/api";

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
    if (path === "/leads") {
      return Promise.resolve([
        {
          leadId: "L-NEW",
          customerName: "Unassigned New",
          mobile: "9000000001",
          currentStatus: "New",
          executive: "",
          accountStatus: "Active",
        },
        {
          leadId: "L-BOOK",
          customerName: "Amit Booked",
          mobile: "9000000002",
          currentStatus: "Booked",
          executive: "Amit",
          accountStatus: "Active",
        },
        {
          leadId: "L-FU",
          customerName: "Devang Follow-up",
          mobile: "9000000003",
          currentStatus: "Follow-up",
          executive: "Devang",
          accountStatus: "Active",
        },
      ]);
    }
    if (path === "/masters") return Promise.resolve({ executives: ["Amit", "Devang"] });
    return Promise.resolve({});
  },
  post: jest.fn(() => Promise.resolve({ movedCount: 1, skipped: [] })),
  put: () => Promise.resolve({}),
  apiErrorMessage: (err, fallback) => err?.message || fallback || "err",
  bulkStallMessage: (err, fallback) => err?.message || fallback || "err",
}));

jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canEditLeadSplit: true }),
}));

import Allocation from "./Allocation";

afterEach(() => {
  document.body.innerHTML = "";
});

async function renderAlloc() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(<Allocation />);
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return host;
}

function setSelect(el, value) {
  const desc = Object.getOwnPropertyDescriptor(window.HTMLSelectElement.prototype, "value");
  desc.set.call(el, value);
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

test("allocation split grid and lead table are capped with internal scroll", async () => {
  await renderAlloc();
  expect(document.querySelector('[data-testid="split-apply-btn"]')?.textContent).toMatch(/Apply to 400 unassigned/);
  expect(document.querySelector('[data-testid="split-grid-scroll"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="unassigned-note"]')?.textContent).toMatch(/Apply to unassigned/);
  expect(document.querySelector('[data-testid="table-scroll"]')).toBeTruthy();
});

test("status filter hides leads that are not in that pipeline step", async () => {
  const host = await renderAlloc();
  expect(host.querySelector('[data-testid="alloc-status"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Unassigned New/);
  expect(host.querySelector('[data-testid="pick-L-BOOK"]')).toBeNull();

  await act(async () => {
    setSelect(host.querySelector('[data-testid="alloc-filter"]'), "all");
  });
  expect(host.querySelector('[data-testid="pick-L-BOOK"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="pick-L-FU"]')).toBeTruthy();

  await act(async () => {
    setSelect(host.querySelector('[data-testid="alloc-status"]'), "Booked");
  });
  expect(host.querySelector('[data-testid="pick-L-BOOK"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="pick-L-NEW"]')).toBeNull();
  expect(host.querySelector('[data-testid="pick-L-FU"]')).toBeNull();
});

test("selected assigned leads can be reallocated to another executive", async () => {
  post.mockClear();
  await renderAlloc();
  await act(async () => {
    setSelect(document.querySelector('[data-testid="alloc-filter"]'), "all");
  });
  await act(async () => {
    document.querySelector('[data-testid="pick-L-BOOK"]').click();
  });
  expect(document.querySelector('[data-testid="alloc-btn"]')?.textContent).toMatch(/Reallocate 1/);
  await act(async () => {
    setSelect(document.querySelector('[data-testid="alloc-target"]'), "Devang");
  });
  await act(async () => {
    document.querySelector('[data-testid="alloc-btn"]').click();
    await Promise.resolve();
    await Promise.resolve();
  });
  expect(post).toHaveBeenCalledWith("/leads/allocate", {
    leadIds: ["L-BOOK"],
    executive: "Devang",
  });
});
