/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => {
  const post = jest.fn(() => Promise.resolve({ ok: true, errorCount: 0, flags: [] }));
  return {
    get: () => Promise.resolve({
      ok: false,
      errorCount: 1,
      flags: [{ code: "receipt_missing", message: "Payment ₹50,000 has no matching receipt in the ZIP" }],
    }),
    post,
    apiErrorMessage: (e, fallback) => fallback,
  };
});
jest.mock("./LeadDocuments", () => ({
  LeadDocsStrip: () => <div data-testid="tally-pack-upload">upload</div>,
}));

import { post } from "../lib/api";
import TallyPackCheck from "./TallyPackCheck";

async function render() {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(<TallyPackCheck leadId="LD1" canUpload />);
  });
  await act(async () => { await Promise.resolve(); await Promise.resolve(); });
  return { host, root };
}

test("shows pack gaps and can re-check", async () => {
  const { host, root } = await render();
  expect(host.textContent).toMatch(/no matching receipt/);
  const btn = host.querySelector('[data-testid="tally-pack-check-btn"]');
  expect(btn).toBeTruthy();
  await act(async () => { btn.click(); await Promise.resolve(); });
  expect(post).toHaveBeenCalledWith("/leads/LD1/tally-pack/check", {});
  await act(async () => { root.unmount(); });
});
