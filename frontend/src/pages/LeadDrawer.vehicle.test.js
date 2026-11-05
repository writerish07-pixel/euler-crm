/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

const mockGet = jest.fn();
const mockPut = jest.fn();
const mockAuth = { current: { isOwner: true, isShowroomAdmin: false } };
jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("react-router-dom", () => ({ Link: ({ children }) => children }));
jest.mock("../lib/api", () => ({
  get: (...a) => mockGet(...a),
  put: (...a) => mockPut(...a),
  post: () => Promise.resolve({}),
  patch: () => Promise.resolve({}),
  del: () => Promise.resolve({}),
  apiErrorMessage: (e, fallback) => fallback,
  apiErrorDetail: () => ({}),
  downloadFile: () => Promise.resolve(),
}));
jest.mock("../context/AuthContext", () => ({ useAuth: () => mockAuth.current }));
jest.mock("./NewLeadDrawer", () => () => null);
jest.mock("./LeadWhatsApp", () => () => null);
jest.mock("../components/LeadDocuments", () => ({
  LeadDocsStrip: () => null, kycKinds: () => [], extraSupportReady: () => "",
  B2bGstinField: () => null, RefundChequePick: () => null, PrintDealSheetButton: () => null,
}));
jest.mock("../components/CallLink", () => () => null);
jest.mock("../components/CompleteFormatDrawer", () => () => null);
jest.mock("./BookEnquiryDrawer", () => () => null);
jest.mock("../components/SchemeCircularPic", () => () => null);
jest.mock("../components/TallyPackCheck", () => () => null);
jest.mock("./DealVerify", () => ({ DealVerifyCard: () => null }));

import { toast } from "sonner";
import { VehicleKV } from "./LeadDrawer";

const VARIANTS = {
  "Turbo Max": [{ priceId: "P1", variant: "Maxx (FB)", inYard: 2 }, { priceId: "P2", variant: "Maxx (PV)", inYard: 0 }],
  Storm: [{ priceId: "P3", variant: "Storm LR (PV) Reg C7 6.6kWh", inYard: 1 }],
};

async function mount(lead, onSaved = jest.fn()) {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<VehicleKV lead={lead} models={["Turbo Max", "Storm"]} leadId="LD1" onSaved={onSaved} />);
  });
  return { host, root, q: (id) => host.querySelector(`[data-testid="${id}"]`) };
}

function choose(select, value) {
  const setter = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value").set;
  setter.call(select, value);
  select.dispatchEvent(new Event("change", { bubbles: true }));
}

beforeEach(() => {
  mockGet.mockReset();
  mockPut.mockReset();
  toast.error.mockClear();
  mockGet.mockImplementation((url, params) => Promise.resolve(VARIANTS[params.model] || []));
  mockPut.mockResolvedValue({});
  mockAuth.current = { isOwner: true, isShowroomAdmin: false };
});

test("variant is a Price Master dropdown and changes with the model", async () => {
  const onSaved = jest.fn();
  const { root, host, q } = await mount({ interestedModel: "Turbo Max", variant: "Maxx (FB)" }, onSaved);
  await act(async () => { q("owner-field-variant-edit").click(); });
  await act(async () => { await Promise.resolve(); });
  const variant = q("vehicle-edit-variant");
  expect(variant.tagName).toBe("SELECT");
  expect(variant.textContent).toMatch(/Maxx \(PV\)/);
  expect(variant.textContent).toMatch(/2 in yard/);
  await act(async () => { choose(q("vehicle-edit-model"), "Storm"); });
  await act(async () => { await Promise.resolve(); });
  expect(mockGet).toHaveBeenLastCalledWith("/price-master/variants", { model: "Storm" });
  // A Turbo Max variant cannot stay selected on a Storm.
  expect(q("vehicle-edit-variant").value).toBe("");
  expect(q("vehicle-edit-save").disabled).toBe(true);
  await act(async () => { choose(q("vehicle-edit-variant"), "Storm LR (PV) Reg C7 6.6kWh"); });
  await act(async () => { q("vehicle-edit-save").click(); });
  await act(async () => { await Promise.resolve(); });
  expect(mockPut).toHaveBeenCalledWith("/leads/LD1/vehicle", { model: "Storm", variant: "Storm LR (PV) Reg C7 6.6kWh" });
  expect(onSaved).toHaveBeenCalled();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("showroom admin can edit; other roles only see the vehicle", async () => {
  mockAuth.current = { isOwner: false, isShowroomAdmin: true };
  let m = await mount({ interestedModel: "Turbo Max", variant: "Maxx (FB)" });
  expect(m.q("owner-field-variant-edit")).toBeTruthy();
  await act(async () => { m.root.unmount(); });
  m.host.remove();
  mockAuth.current = { isOwner: false, isShowroomAdmin: false };
  m = await mount({ interestedModel: "Turbo Max", variant: "Maxx (FB)" });
  expect(m.q("owner-field-variant-edit")).toBeNull();
  expect(m.host.textContent).toMatch(/Maxx \(FB\)/);
  await act(async () => { m.root.unmount(); });
  m.host.remove();
});
