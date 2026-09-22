/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const mockAuth = {
  isExecutive: true,
  isTl: false,
  user: { name: "Executive" },
  canSeeOwnerCommercials: false,
};

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: (url) => {
    const path = String(url || "");
    if (path.indexOf("price-master/variants") >= 0) {
      return Promise.resolve([{ priceId: "p1", variant: "Maxx (PV)", inYard: 1 }]);
    }
    if (path.indexOf("commercial/deal-preview") >= 0) {
      return Promise.resolve({ netToCx: 185000 });
    }
    if (path.indexOf("leads/mobile-matches") >= 0) {
      return Promise.resolve({
        mobile: "9876543210",
        existing: [{
          leadId: "LD26000001",
          customerName: "Ramesh",
          executive: "Executive",
          interestedModel: "Turbo Max",
          variant: "Maxx (PV)",
          currentStatus: "New",
        }],
        pending: [],
        code: "mobile_active_deal",
      });
    }
    return Promise.resolve({});
  },
  post: jest.fn(() => Promise.resolve({ leadId: "LD26000002" })),
  apiErrorMessage: (e, fallback) => fallback,
  apiErrorDetail: (e) => e?.response?.data?.detail || {},
}));
jest.mock("../components/LeadDocuments", () => ({
  LocalKycBlock: () => <div data-testid="kyc-block" />,
  LocalOemExtraBlock: ({ amount }) => (
    Number(amount) > 0 ? <div data-testid="oem-extra-proof-block" /> : null
  ),
  kycReady: jest.fn(() => "Attach Aadhaar front, Aadhaar back and PAN"),
  extraSupportReady: () => "",
  uploadKycFiles: () => Promise.resolve(),
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => mockAuth,
}));

import { post } from "../lib/api";
import NewLeadDrawer from "./NewLeadDrawer";

const MASTERS = {
  executives: ["Executive", "Amit"],
  leadSources: ["Walk-in"],
  models: ["Turbo Max"],
  priorities: ["Normal"],
};

async function renderDrawer(props = {}) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <NewLeadDrawer
        masters={MASTERS}
        onClose={() => {}}
        onCreated={() => {}}
        {...props}
      />,
    );
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

function setInput(el, value) {
  const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
  proto.set.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
  el.dispatchEvent(new Event("change", { bubbles: true }));
}

afterEach(() => {
  document.body.innerHTML = "";
  mockAuth.isExecutive = true;
  mockAuth.isTl = false;
  mockAuth.user = { name: "Executive" };
  post.mockClear();
});

test("executive create form shows OEM extra support and another-vehicle checkbox", async () => {
  const { root } = await renderDrawer();
  expect(document.querySelector('[data-testid="lead-oem-extra"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="another-vehicle-block"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="another-vehicle-check"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="another-vehicle-block"]').textContent).toMatch(/another unit/i);
  await act(async () => { root.unmount(); });
});

test("TL create form has the same extra-support and multi-unit controls", async () => {
  mockAuth.isExecutive = false;
  mockAuth.isTl = true;
  mockAuth.user = { name: "Team Leader" };
  const { root } = await renderDrawer();
  expect(document.querySelector('[data-testid="lead-oem-extra"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="another-vehicle-check"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="lead-executive"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
});

test("typing a known mobile lists existing units and save sends anotherVehicle", async () => {
  const { root } = await renderDrawer();
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-name"]'), "Ramesh");
    setInput(document.querySelector('[data-testid="lead-mobile"]'), "9876543210");
    setInput(document.querySelector('[data-testid="lead-budget"]'), "185000");
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 350)); });
  expect(document.querySelector('[data-testid="mobile-unit-list"]').textContent).toMatch(/LD26000001/);
  await act(async () => {
    document.querySelector('[data-testid="another-vehicle-check"] input').click();
  });
  await act(async () => {
    document.querySelector('[data-testid="save-lead-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(document.querySelector('[data-testid="kyc-copy-hint"]').textContent).toMatch(/copy from the first file/i);
  expect(post).toHaveBeenCalledWith("/leads", expect.objectContaining({
    customerName: "Ramesh",
    mobile: "9876543210",
    anotherVehicle: true,
  }));
  await act(async () => { root.unmount(); });
});
