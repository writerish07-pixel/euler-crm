/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const mockGet = jest.fn();
const mockPost = jest.fn();
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  post: (...args) => mockPost(...args),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: true, isShowroomAdmin: true }),
}));

import Inventory from "./Inventory";

function jsonFor(url) {
  const path = String(url);
  if (path === "/inventory") return [{ chassis: "MD9YARD01", model: "Turbo Max", variant: "Maxx (PV)" }];
  if (path === "/inventory/transit") return [];
  if (path === "/inventory/held") return [];
  if (path === "/inventory/sold") {
    return [{ chassis: "MD9SOLD01", soldDate: "2026-10-14", customerName: "AMEERCHAND GURJAR" }];
  }
  if (path === "/inventory/received" || path.startsWith("/inventory/received?")) {
    return {
      rows: [{ chassis: "MD9RECV01", receivedDate: "2026-08-01", receivedMonth: "2026-08" }],
      byMonth: [{ month: "2026-08", count: 1 }],
      total: 1,
    };
  }
  if (path === "/inventory/need-to-order") return [];
  if (path === "/inventory/summary") {
    return { total: 1, transit: 0, held: 0, sold: 1, received: 1, needToOrder: 0 };
  }
  if (path === "/inventory/check") return { confirmed: false, today: "2026-10-24" };
  if (path === "/integrations/coulson") return { configured: true, lastSyncOk: true };
  return {};
}

beforeEach(() => {
  mockGet.mockReset();
  mockPost.mockReset();
  mockGet.mockImplementation((url) => Promise.resolve(jsonFor(url)));
});

test("inventory register has sold and received tabs", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<Inventory />); });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="inv-tab-sold"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="inv-tab-received"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="inv-card-sold"]')?.textContent).toContain("1");
  expect(host.querySelector('[data-testid="inv-card-received"]')?.textContent).toContain("1");

  await act(async () => {
    host.querySelector('[data-testid="inv-tab-sold"]').click();
  });
  expect(host.textContent).toContain("AMEERCHAND GURJAR");
  expect(host.textContent).toContain("MD9SOLD01");

  await act(async () => {
    host.querySelector('[data-testid="inv-tab-received"]').click();
  });
  expect(host.querySelector('[data-testid="inventory-received-month"]')).toBeTruthy();
  expect(host.textContent).toContain("MD9RECV01");
  await act(async () => { root.unmount(); });
  host.remove();
});
