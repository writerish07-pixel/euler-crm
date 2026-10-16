/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: () => Promise.resolve([
    {
      leadId: "LD1", customerName: "Ramesh", executive: "Ravi",
      dealVerifyAmount: 500000, totalReceived: 10000, customerPayable: 486933,
      dealVerifyMismatch: true, dealVerifyMismatchKind: "over",
      dealVerifyStatus: "answered",
    },
  ]),
  post: jest.fn(() => Promise.resolve({})),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("react-router-dom", () => ({ Link: ({ children }) => children }));
jest.mock("../components/ReportActions", () => () => null);

import DealVerify, { DealVerifyCard } from "./DealVerify";

test("mismatch register lists paid-more-than-receipts", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<DealVerify />); });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(host.querySelector('[data-testid="deal-verify-page"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Ramesh/);
  expect(host.textContent).toMatch(/Paid more than receipts/i);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("lead card highlights mismatch", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <DealVerifyCard
        booked
        canManage
        lead={{
          leadId: "LD1", dealVerifyMismatch: true, dealVerifyMismatchKind: "over",
          dealVerifyAmount: 500000, totalReceived: 10000, dealVerifyStatus: "answered",
        }}
      />,
    );
  });
  expect(host.querySelector('[data-testid="deal-verify-mismatch"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Paid more than receipts/i);
  await act(async () => { root.unmount(); });
  host.remove();
});
