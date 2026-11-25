/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockGet = jest.fn();
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  apiErrorMessage: (e, fallback) => fallback,
}));

import OemPdiPendingCard from "./OemPdiPendingCard";

const PAYLOAD = {
  counts: { total: 2, onLead: 1, delivered: 1, notInCrm: 1 },
  rows: [
    { chassis: "MD9PDI1001", oemModel: "Turbo", oemVariant: "Range Maxx", soldDate: "2026-08-14",
      leadId: "LD26000501", customerName: "Delivered Single", crmStatus: "Delivered", deliveredInCrm: true },
    { chassis: "MD9PDI1003", oemModel: "Hi-Load", oemVariant: "SR", soldDate: "2026-09-02",
      leadId: "", customerName: "", crmStatus: "", deliveredInCrm: false },
  ],
};

async function render(props) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<OemPdiPendingCard {...props} />); });
  await act(async () => { await Promise.resolve(); });
  return { host, root };
}

afterEach(() => { document.body.innerHTML = ""; });

test("shows OEM PDI-pending counts and lists rows on demand", async () => {
  mockGet.mockResolvedValue(PAYLOAD);
  const onOpenLead = jest.fn();
  const { host, root } = await render({ onOpenLead });
  expect(mockGet).toHaveBeenCalledWith("/oem-pdi-pending");
  expect(host.querySelector('[data-testid="oem-pdi-total"]').textContent).toBe("2");
  expect(host.querySelector('[data-testid="oem-pdi-delivered"]').textContent).toBe("1");
  expect(host.textContent).not.toMatch(/MD9PDI1001/);
  await act(async () => { host.querySelector('[data-testid="oem-pdi-toggle"]').click(); });
  expect(host.textContent).toMatch(/MD9PDI1001/);
  expect(host.textContent).toMatch(/Not in CRM/);
  const leadBtn = Array.from(host.querySelectorAll("button")).find((b) => /LD26000501/.test(b.textContent));
  await act(async () => { leadBtn.click(); });
  expect(onOpenLead).toHaveBeenCalledWith("LD26000501");
  await act(async () => { root.unmount(); });
});

test("a load failure shows a message instead of empty counts", async () => {
  mockGet.mockRejectedValue(new Error("boom"));
  const { host, root } = await render({});
  expect(host.textContent).toMatch(/Could not load OEM PDI pending/);
  expect(host.querySelector('[data-testid="oem-pdi-toggle"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
});
