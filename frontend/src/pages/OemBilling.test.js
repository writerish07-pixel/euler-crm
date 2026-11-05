/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockBilling = {
  current: {
    soldCount: 2,
    byDate: [
      { date: "2026-09-04", count: 1 },
      { date: "2026-09-05", count: 1 },
    ],
    counts: {
      pending_delivery: 1,
      created_from_oem: 1,
      matched_delivered: 0,
      needs_review: 0,
      unmatched: 0,
    },
    rows: [
      {
        chassis: "MD9PENDUI01",
        invoiceNumber: "INV-1",
        mobile: "9811100111",
        customerName: "Pending Person",
        model: "Turbo Max",
        variant: "Maxx (DV220)",
        billedBodyType: "DV220",
        availableBodyType: "FB",
        soldDate: "2026-09-04",
        undated: false,
        bucket: "pending_delivery",
        leadId: "LD-PEND-UI",
        crmStatus: "Booked",
      },
      {
        chassis: "MD9NEWUI01",
        invoiceNumber: "INV-2",
        mobile: "9811100222",
        customerName: "Created Person",
        model: "Hi-Load",
        variant: "XR",
        soldDate: "2026-09-05",
        undated: false,
        bucket: "created_from_oem",
        leadId: "LD-NEW-UI",
        crmStatus: "New",
        oemBillingCreated: true,
      },
    ],
    repair: {
      stubCount: 1,
      safeCount: 1,
      reviewCount: 0,
      pairs: [{
        action: "safe",
        reason: "unique mobile match",
        match: "mobile",
        stub: { leadId: "LD-NEW-UI", currentStatus: "New" },
        original: { leadId: "LD-ORIG-UI", currentStatus: "Booked" },
      }],
    },
  },
};

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
const mockGet = jest.fn();
const mockPost = jest.fn();
jest.mock("../lib/api", () => ({
  get: (...args) => mockGet(...args),
  post: (...args) => mockPost(...args),
  apiErrorMessage: (e, fallback) => fallback,
}));
jest.mock("../context/AuthContext", () => ({
  useAuth: () => ({ canEditCommercials: true, isOwner: true }),
}));
jest.mock("../components/LeadLink", () => ({
  useLeadDrawer: () => ({ openLead: jest.fn(), drawer: null }),
  LeadLink: ({ leadId }) => <button type="button" data-testid={`lead-link-${leadId}`}>{leadId}</button>,
}));

import { toast } from "sonner";
import OemBilling from "./OemBilling";

beforeEach(() => {
  toast.error.mockClear();
  toast.success.mockClear();
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) return Promise.resolve(mockBilling.current);
    if (String(url).includes("/masters")) return Promise.resolve({ models: [] });
    return Promise.resolve({});
  });
  mockPost.mockResolvedValue(mockBilling.current);
});

test("OEM billing tab shows pending delivery without asking for chassis", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<OemBilling />);
  });
  await act(async () => { await Promise.resolve(); });
  expect(host.querySelector('[data-testid="oem-billing"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="oem-bill-card-pending"]').textContent).toMatch(/1/);
  expect(host.querySelector('[data-testid="oem-billing-sync"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="oem-billing-relink"]')).toBeTruthy();
  expect(host.textContent).toMatch(/Pending Person/);
  expect(host.textContent).toMatch(/Created Person/);
  expect(host.querySelector('[data-testid="oem-bill-by-date"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="oem-bill-day-2026-09-04"]').textContent).toMatch(/1/);
  expect(host.textContent).toMatch(/billed DV220 · available FB/);
  expect(host.textContent).not.toMatch(/Select chassis/i);
  await act(async () => {
    host.querySelector('[data-testid="oem-bill-day-2026-09-04"]').click();
  });
  expect(host.textContent).toMatch(/Pending Person/);
  expect(host.textContent).not.toMatch(/Created Person/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("OEM billing refresh waits for the reload to finish", async () => {
  let resolveLoad;
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return new Promise((resolve) => { resolveLoad = () => resolve(mockBilling.current); });
    }
    return Promise.resolve({});
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<OemBilling />); });
  await act(async () => { resolveLoad(); await Promise.resolve(); });
  mockGet.mockClear();
  let resolveRefresh;
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return new Promise((resolve) => { resolveRefresh = () => resolve(mockBilling.current); });
    }
    return Promise.resolve({});
  });
  await act(async () => {
    host.querySelector('[data-testid="report-refresh-btn"]').click();
  });
  expect(host.querySelector('[data-testid="report-refresh-btn"]').textContent).toMatch(/Refreshing/);
  await act(async () => { resolveRefresh(); await Promise.resolve(); });
  expect(host.querySelector('[data-testid="report-refresh-btn"]').textContent).toMatch(/Refresh/);
  expect(mockGet).toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("OEM billing load failure toasts instead of pretending billed files are zero", async () => {
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return Promise.reject(Object.assign(new Error("timeout of 25000ms exceeded"), { code: "ECONNABORTED" }));
    }
    return Promise.resolve({});
  });
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<OemBilling />);
  });
  await act(async () => { await Promise.resolve(); });
  await act(async () => { await Promise.resolve(); });
  expect(toast.error).toHaveBeenCalled();
  expect(host.querySelector('[data-testid="oem-billing-load-error"]')).toBeTruthy();
  expect(host.textContent).not.toMatch(/No OEM-billed files waiting to be marked delivered/);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("Needs review offers link / add-unit / new lead and explains blocked choices", async () => {
  const reviewRow = {
    chassis: "MD9EVDAD26K217971", invoiceNumber: "AF-122-I26270264", mobile: "9024073526",
    customerName: "Mukesh sharma", model: "Turbo Max", variant: "Maxx (PV)",
    soldDate: "2026-11-03", undated: false, bucket: "needs_review", leadId: "",
    reviewReason: "more than one lead matches this Sold row",
    candidateLeads: [
      { leadId: "LD26000949", currentStatus: "Booked", model: "Turbo Max", variant: "Maxx (FB)",
        chassis: "", vehicleCount: 1, modelMatches: true, canLink: true, linkBlockedReason: "",
        canAddUnit: false, addUnitBlockedReason: "No chassis on this file yet — use Link", recommended: true },
      { leadId: "LD26000062", currentStatus: "Delivered", model: "Storm", variant: "Storm LR (PV)",
        chassis: "", vehicleCount: 1, modelMatches: false, canLink: false,
        linkBlockedReason: "Different vehicle model from the OEM invoice",
        canAddUnit: false, addUnitBlockedReason: "Delivered file — a repeat purchase stays a separate lead" },
    ],
  };
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return Promise.resolve({ soldCount: 1, byDate: [], counts: { needs_review: 1 }, rows: [reviewRow], repair: {} });
    }
    return Promise.resolve({});
  });
  mockPost.mockResolvedValue({ ok: true, leadId: "LD26000949", vehicleCount: 1 });
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<OemBilling />); });
  await act(async () => { await Promise.resolve(); });
  const q = (id) => host.querySelector(`[data-testid="${id}"]`);
  expect(q("oem-review-MD9EVDAD26K217971")).toBeTruthy();
  expect(host.textContent).toMatch(/Suggested/);
  expect(host.textContent).toMatch(/Different vehicle from the OEM invoice/);
  expect(host.textContent).toMatch(/repeat purchase stays a separate lead/);
  expect(q("oem-review-link-MD9EVDAD26K217971-LD26000949").disabled).toBe(false);
  expect(q("oem-review-link-MD9EVDAD26K217971-LD26000062").disabled).toBe(true);
  expect(q("oem-review-unit-MD9EVDAD26K217971-LD26000062").disabled).toBe(true);
  expect(q("oem-review-create-MD9EVDAD26K217971")).toBeTruthy();
  await act(async () => { q("oem-review-link-MD9EVDAD26K217971-LD26000949").click(); });
  await act(async () => { await Promise.resolve(); });
  expect(mockPost).toHaveBeenCalledWith("/oem-billing/resolve",
    { chassis: "MD9EVDAD26K217971", leadId: "LD26000949", action: "link" }, { retry: false });
  expect(toast.success).toHaveBeenCalledWith("Linked to LD26000949");
  confirm.mockRestore();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("Needs review offers Replace when a file holds another model's chassis", async () => {
  const reviewRow = {
    chassis: "MD9EVDAD26K217971", invoiceNumber: "AF-122-I26270264", mobile: "9024073526",
    customerName: "Mukesh sharma", model: "Turbo Max", variant: "Maxx (PV)",
    soldDate: "2026-11-03", undated: false, bucket: "needs_review", leadId: "",
    reviewReason: "LD26000949 holds MD9EMSDL26E217037, which OEM billed as Storm — replace it with this chassis",
    candidateLeads: [
      { leadId: "LD26000949", currentStatus: "Booked", model: "Turbo Max", variant: "Maxx (FB)",
        chassis: "MD9EMSDL26E217037", vehicleCount: 1, modelMatches: true, canLink: false,
        linkBlockedReason: "Holds MD9EMSDL26E217037, which OEM billed as Storm — use Replace",
        canAddUnit: false, addUnitBlockedReason: "This file holds the wrong vehicle — use Replace",
        canReplace: true, wrongChassis: { chassis: "MD9EMSDL26E217037", model: "Storm" }, recommended: true },
    ],
  };
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return Promise.resolve({ soldCount: 1, byDate: [], counts: { needs_review: 1 }, rows: [reviewRow], repair: {} });
    }
    return Promise.resolve({});
  });
  mockPost.mockResolvedValue({ ok: true, leadId: "LD26000949", chassis: "MD9EVDAD26K217971",
    removedChassis: "MD9EMSDL26E217037", action: "replace" });
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<OemBilling />); });
  await act(async () => { await Promise.resolve(); });
  const q = (id) => host.querySelector(`[data-testid="${id}"]`);
  expect(q("oem-review-wrong-MD9EVDAD26K217971-LD26000949").textContent).toMatch(/billed as Storm/);
  await act(async () => { q("oem-review-replace-MD9EVDAD26K217971-LD26000949").click(); });
  await act(async () => { await Promise.resolve(); });
  expect(confirm.mock.calls[0][0]).toMatch(/replace chassis MD9EMSDL26E217037 \(Storm\)/);
  expect(mockPost).toHaveBeenCalledWith("/oem-billing/resolve",
    { chassis: "MD9EVDAD26K217971", leadId: "LD26000949", action: "replace" }, { retry: false });
  expect(toast.success).toHaveBeenCalledWith("Replaced MD9EMSDL26E217037 with MD9EVDAD26K217971 on LD26000949");
  confirm.mockRestore();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("Not in CRM row can be linked by hand to an open lead found by search", async () => {
  jest.useFakeTimers();
  const row = {
    chassis: "MD9EVDAD26K217971", invoiceNumber: "AF-122-I26270264", mobile: "9024073526",
    customerName: "Mukesh sharma", model: "Turbo Max", variant: "Maxx (PV)",
    soldDate: "2026-11-03", undated: false, bucket: "unmatched", leadId: "",
  };
  mockGet.mockImplementation((url) => {
    if (String(url).includes("/oem-billing")) {
      return Promise.resolve({ soldCount: 1, byDate: [], counts: { unmatched: 1 }, rows: [row], repair: {} });
    }
    if (url === "/leads") {
      return Promise.resolve([
        { leadId: "LD26000949", customerName: "Mukesh Sharma", mobile: "9024073526",
          interestedModel: "Turbo Max", variant: "Maxx (FB)", currentStatus: "Booked", accountStatus: "Active" },
        { leadId: "LD26000062", customerName: "mukesh sharma", mobile: "9024073526",
          interestedModel: "Storm", currentStatus: "Delivered", deliveryStatus: "Delivered",
          accountStatus: "Active", chassisNumber: "MD9EMSDL26E217037" },
      ]);
    }
    return Promise.resolve({});
  });
  mockPost.mockResolvedValue({ ok: true, leadId: "LD26000949", vehicleCount: 1 });
  const confirm = jest.spyOn(window, "confirm").mockReturnValue(true);
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => { root.render(<OemBilling />); });
  await act(async () => { await Promise.resolve(); });
  const q = (id) => host.querySelector(`[data-testid="${id}"]`);
  await act(async () => { q("oem-manual-open-MD9EVDAD26K217971").click(); });
  await act(async () => { jest.advanceTimersByTime(350); await Promise.resolve(); await Promise.resolve(); });
  expect(mockGet).toHaveBeenCalledWith("/leads", { q: "9024073526", limit: 25 });
  // Delivered Storm file is not offered — open leads only.
  expect(q("oem-manual-hit-MD9EVDAD26K217971-LD26000062")).toBeNull();
  await act(async () => { q("oem-manual-link-MD9EVDAD26K217971-LD26000949").click(); });
  await act(async () => { await Promise.resolve(); });
  expect(mockPost).toHaveBeenCalledWith("/oem-billing/resolve",
    { chassis: "MD9EVDAD26K217971", leadId: "LD26000949", action: "link", manual: true }, { retry: false });
  confirm.mockRestore();
  jest.useRealTimers();
  await act(async () => { root.unmount(); });
  host.remove();
});
