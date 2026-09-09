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
  put: jest.fn(() => Promise.resolve({})),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("./LeadDocuments", () => ({
  LocalKycBlock: () => <div data-testid="kyc-block" />,
  kycReady: () => "",
  uploadKycFiles: () => Promise.resolve(),
}));

import { put } from "../lib/api";
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
  expect(labels.some((t) => /OEM Extra Support/.test(t))).toBe(true);
  expect(drawer.querySelector('[data-testid="approval-oem-extra"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("approval drawer prefills OEM extra support and saves it on the request", async () => {
  put.mockClear();
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <CompleteFormatDrawer
        row={{
          requestId: "LR1", customerName: "Jitendra", existingLeadId: "LD1",
          mobile: "9636959028", interestedModel: "Turbo Max", variant: "Maxx (PV)",
          budget: 185000, oemExtraSupportReceived: 7000,
        }}
        onClose={() => {}}
        onSaved={() => {}}
      />,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  const extra = document.querySelector('[data-testid="approval-oem-extra"]');
  expect(extra).toBeTruthy();
  expect(extra.value).toBe("7000");
  await act(async () => {
    document.querySelector('[data-testid="save-approval-format-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(put).toHaveBeenCalledWith("/lead-requests/LR1", expect.objectContaining({
    budget: 185000,
    interestedModel: "Turbo Max",
    variant: "Maxx (PV)",
    oemExtraSupportReceived: 7000,
  }));
  await act(async () => { root.unmount(); });
  host.remove();
});
