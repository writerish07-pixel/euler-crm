/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

const mockAuth = {
  isExecutive: true,
  isTl: false,
  isTeamLead: false,
  isSalesGm: false,
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
      return Promise.resolve({
        netToCx: 185000,
        schemeMonth: "2026-09",
        schemeOffers: [{ key: "loyaltyBonus", label: "Loyalty Bonus", schemeAvailable: 10000 }],
        schemePassed: 0,
        additionalDiscount: 5000,
      });
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
  downloadPost: jest.fn(() => Promise.resolve()),
  apiErrorMessage: (e, fallback) => fallback,
  apiErrorDetail: (e) => e?.response?.data?.detail || {},
}));
jest.mock("../components/LeadDocuments", () => ({
  LocalKycBlock: () => <div data-testid="kyc-block" />,
  LocalOemExtraBlock: ({ amount }) => (
    Number(amount) > 0 ? <div data-testid="oem-extra-proof-block" /> : null
  ),
  kycReady: jest.fn(() => "Attach Aadhaar front, Aadhaar back and PAN"),
  extraSupportReady: jest.fn((amount, _files, _docs, opts) => {
    if (opts && opts.copyFromSibling) return "";
    if (!(Number(amount) > 0)) return "";
    return "Attach the OEM Extra Support confirmation email from Siddharth Dubey (ASM) or Siddharth Sharma (RM)";
  }),
  dealSheetReady: jest.fn(() => ""),
  LocalDealSheetBlock: () => <div data-testid="deal-sheet-block" />,
  PrintDealSheetButton: ({ onPrint }) => (
    <button type="button" data-testid="print-deal-sheet-btn" onClick={onPrint}>Print deal sheet</button>
  ),
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
  mockAuth.isTeamLead = false;
  mockAuth.isSalesGm = false;
  mockAuth.user = { name: "Executive" };
  post.mockClear();
});

test("executive can create a walk-in enquiry without Cx Demand", async () => {
  const { root } = await renderDrawer();
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-name"]'), "Walk In");
    setInput(document.querySelector('[data-testid="lead-mobile"]'), "9876500011");
  });
  await act(async () => {
    document.querySelector('[data-testid="save-lead-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(document.querySelector('[data-testid="save-lead-btn"]').textContent).toMatch(/Create Lead/);
  expect(post).toHaveBeenCalledWith("/leads", expect.objectContaining({
    customerName: "Walk In",
    mobile: "9876500011",
    budget: 0,
  }));
  await act(async () => { root.unmount(); });
});

test("executive create form is name, mobile, model until Cx Demand needs approval", async () => {
  const { root } = await renderDrawer();
  expect(document.querySelector('[data-testid="lead-name"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="lead-mobile"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="lead-model"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="kyc-block"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="deal-sheet-block"]')).toBeFalsy();
  expect(document.querySelector('[data-testid="same-order-check"]')).toBeFalsy();
  expect(document.querySelector('[data-testid="save-lead-btn"]').textContent).toMatch(/Create Lead/);
  await act(async () => { root.unmount(); });
});

test("TL create form includes own name on the executive dropdown", async () => {
  mockAuth.isExecutive = false;
  mockAuth.isTeamLead = true;
  mockAuth.user = { name: "Create TL" };
  const { root } = await renderDrawer();
  expect(document.querySelector('[data-testid="deal-format-card"]')).toBeTruthy();
  const exec = document.querySelector('[data-testid="lead-executive"]');
  expect(exec).toBeTruthy();
  expect(exec.textContent).toMatch(/Create TL/);
  await act(async () => { root.unmount(); });
});

test("typing a known mobile lists existing units and save sends anotherVehicle", async () => {
  const { root } = await renderDrawer();
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-name"]'), "Ramesh");
    setInput(document.querySelector('[data-testid="lead-mobile"]'), "9876543210");
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

test("another vehicle on a known mobile still creates without deal or KYC", async () => {
  const { root } = await renderDrawer({
    initial: { anotherVehicle: true, siblingLeadId: "LD26000001", customerName: "Ramesh", mobile: "9876543210" },
  });
  await act(async () => { await new Promise((r) => setTimeout(r, 350)); });
  expect(document.querySelector('[data-testid="another-vehicle-block"]')).toBeTruthy();
  await act(async () => {
    document.querySelector('[data-testid="save-lead-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(post).toHaveBeenCalledWith("/leads", expect.objectContaining({
    anotherVehicle: true,
    customerName: "Ramesh",
    mobile: "9876543210",
  }));
  await act(async () => { root.unmount(); });
});

test("executive discounted create shows print and upload deal sheet", async () => {
  const { root } = await renderDrawer();
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-name"]'), "Storm Buyer");
    setInput(document.querySelector('[data-testid="lead-mobile"]'), "9928700255");
    const model = document.querySelector('[data-testid="lead-model"]');
    model.value = "Turbo Max";
    model.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  await act(async () => {
    const variant = document.querySelector('[data-testid="lead-variant"]');
    variant.value = "Maxx (PV)";
    variant.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-budget"]'), "945000");
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(document.querySelector('[data-testid="deal-sheet-block"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="print-deal-sheet-btn"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="save-lead-btn"]').textContent).toMatch(/Send for approval/);
  expect(document.body.textContent).toMatch(/Request a lead/);
  expect(document.body.textContent).toMatch(/Sent for owner or GM approval/);
  await act(async () => { root.unmount(); });
});

test("same-order pack is mutex with another vehicle and save sends units", async () => {
  mockAuth.isExecutive = false;
  mockAuth.isTl = false;
  mockAuth.user = { name: "Owner" };
  const { root } = await renderDrawer();
  await act(async () => {
    setInput(document.querySelector('[data-testid="lead-name"]'), "Fleet Pack");
    document.querySelector('[data-testid="same-order-check"] input').click();
  });
  expect(document.querySelector('[data-testid="same-order-units"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="another-vehicle-check"] input').disabled).toBe(true);
  await act(async () => {
    const model = document.querySelector('[data-testid="same-order-model-2"]');
    model.value = "Turbo Max";
    model.dispatchEvent(new Event("change", { bubbles: true }));
  });
  await act(async () => {
    document.querySelector('[data-testid="save-lead-btn"]').click();
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  expect(post).toHaveBeenCalledWith("/leads", expect.objectContaining({
    sameOrderMultiUnit: true,
    anotherVehicle: false,
    units: expect.arrayContaining([expect.objectContaining({ model: "Turbo Max" })]),
  }));
  await act(async () => { root.unmount(); });
});
