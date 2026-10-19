/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";

global.IS_REACT_ACT_ENVIRONMENT = true;

jest.mock("../lib/api", () => ({
  api: { get: jest.fn(() => Promise.resolve({ data: new Blob(), headers: {} })) },
  del: jest.fn(),
  get: jest.fn(),
  put: jest.fn(),
  uploadFile: jest.fn(),
  apiErrorMessage: (e, fallback) => fallback,
  downloadFile: jest.fn(() => Promise.resolve()),
  DOC_UPLOAD_TIMEOUT_MS: 90000,
}));

import { downloadFile } from "../lib/api";
import { openDocumentFile, RequestDealSheetPreview } from "./LeadDocuments";

test("openDocumentFile downloads through the API helper", async () => {
  downloadFile.mockClear();
  await openDocumentFile("DC88", "signed-sheet.pdf");
  expect(downloadFile).toHaveBeenCalledWith("/documents/DC88/file", "signed-sheet.pdf");
});

test("openDocumentFile rejects a missing id", async () => {
  downloadFile.mockClear();
  await expect(openDocumentFile("", "sheet.pdf")).rejects.toThrow(/missing/i);
  expect(downloadFile).not.toHaveBeenCalled();
});

test("deal sheet preview opens the uploaded scan", async () => {
  downloadFile.mockClear();
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <RequestDealSheetPreview
        documents={[{ documentId: "DC9", kind: "deal_sheet", filename: "sheet.pdf", contentType: "application/pdf" }]}
      />,
    );
  });
  const btn = host.querySelector('[data-testid="deal-sheet-preview"] button');
  expect(btn).toBeTruthy();
  await act(async () => { btn.click(); await Promise.resolve(); });
  expect(downloadFile).toHaveBeenCalledWith("/documents/DC9/file", "sheet.pdf");
  await act(async () => { root.unmount(); });
  host.remove();
});
