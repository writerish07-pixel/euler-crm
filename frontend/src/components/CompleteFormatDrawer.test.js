/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    if (String(url).indexOf("/masters") >= 0) {
      return Promise.resolve({ models: ["Turbo Max", "Storm"] });
    }
    if (String(url).indexOf("price-master/variants") >= 0) {
      return Promise.resolve([{ priceId: "p1", variant: "Maxx (PV)", inYard: 2 }]);
    }
    return Promise.resolve({});
  },
  put: () => Promise.resolve({}),
}));
jest.mock("./LeadDocuments", () => ({
  LocalKycBlock: () => <div data-testid="kyc-block" />,
  kycReady: () => "",
  uploadKycFiles: () => Promise.resolve(),
}));

import CompleteFormatDrawer from "./CompleteFormatDrawer";

test("approval drawer has model and variant selects above Deal format", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <CompleteFormatDrawer
        row={{ requestId: "LR1", customerName: "Jitendra", existingLeadId: "LD1", mobile: "9636959028" }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const drawer = document.querySelector('[data-testid="drawer-root"]');
  expect(drawer).toBeTruthy();
  expect(drawer.querySelector('[data-testid="approval-model"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="approval-variant"]')).toBeTruthy();
  expect(drawer.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  const labels = Array.from(drawer.querySelectorAll("label")).map((el) => el.textContent);
  expect(labels.some((t) => /Model/.test(t))).toBe(true);
  expect(labels.some((t) => /Variant/.test(t))).toBe(true);
  await act(async () => { root.unmount(); });
  host.remove();
});
