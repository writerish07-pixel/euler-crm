/**
 * @jest-environment jsdom
 */
import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { Table, PANEL_MAX_H } from "./ui";

test("tables cap height and scroll inside the window by default", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  await act(async () => {
    createRoot(host).render(
      <Table
        columns={[{ key: "n", label: "N" }]}
        rows={Array.from({ length: 40 }, (_, i) => ({ n: i }))}
        rowKey="n"
      />,
    );
  });
  const pane = document.querySelector('[data-testid="table-scroll"]');
  expect(pane).toBeTruthy();
  expect(pane.style.maxHeight).toBe(PANEL_MAX_H);
});
