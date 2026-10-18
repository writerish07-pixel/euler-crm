/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url) === "/payments") return Promise.resolve([]);
    if (String(url) === "/masters") return Promise.resolve({ paymentModes: ["Cash", "UPI"] });
    return Promise.resolve({});
  },
  post: jest.fn(),
  del: jest.fn(),
  apiErrorMessage: (e, fallback) => fallback || String(e),
}));
jest.mock("../components/ReportActions", () => () => <div />);
jest.mock("../components/PeriodBar", () => () => <div />);
jest.mock("../lib/period", () => {
  const params = {};
  return {
    usePeriodState: () => ({ month: "", year: "", params, onChange: () => {} }),
  };
});
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ isOwner: false }),
}));

import Payments from "./Payments";

test("payment ledger asks for a lead ID so accounts can post a receipt", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<MemoryRouter><Payments /></MemoryRouter>);
  });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="payments-lead-jump"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="payments-jump-lead"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="payments-add-receipt"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
  host.remove();
});
