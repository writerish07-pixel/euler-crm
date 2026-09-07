/**
 * @jest-environment jsdom
 */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";

jest.mock("sonner", () => ({ toast: { error: jest.fn(), success: jest.fn() } }));
jest.mock("../lib/api", () => ({
  get: () => Promise.resolve({ shares: [], totalPct: 0 }),
  downloadFile: jest.fn(),
  postForm: jest.fn(),
  apiErrorMessage: () => "err",
}));

import LeadImport from "./LeadImport";

test("import drawer renders the upload dropzone", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(<LeadImport onClose={() => {}} onDone={() => {}} />);
  });
  expect(document.querySelector('[data-testid="import-dropzone"]')).toBeTruthy();
  expect(document.querySelector('[data-testid="download-template-btn"]')).toBeTruthy();
});
