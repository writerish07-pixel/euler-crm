/**
 * @jest-environment jsdom
 */
import React from "react";
import { createRoot } from "react-dom/client";
import { act } from "react";
import DealFormatCard from "./DealFormatCard";

test("shows my total and auto additional when deal is below ex+rto+ins", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <DealFormatCard
        snapshot={{
          exShowroom: 785000, rto: 5500, insurance: 19000,
          priceTotal: 809500, additionalDiscount: 19500,
          needsOwnerApproval: true, netToCx: 809500, supportRequired: 19500,
        }}
        cxDemand={790000}
        readOnly
      />,
    );
  });
  expect(host.querySelector('[data-testid="deal-price-total"]').textContent).toMatch(/8,09,500|809,500|809500/);
  expect(host.querySelector('[data-testid="deal-additional"]').textContent).toMatch(/19,500|19500/);
  expect(host.querySelector('[data-testid="deal-owner-only"]')).toBeTruthy();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("exact deal has zero additional and no owner-only note", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <DealFormatCard
        snapshot={{
          exShowroom: 785000, rto: 5500, insurance: 19000,
          priceTotal: 809500, additionalDiscount: 0,
          needsOwnerApproval: false, netToCx: 809500, supportRequired: 0,
        }}
        cxDemand={809500}
        readOnly
      />,
    );
  });
  expect(host.querySelector('[data-testid="deal-additional"]').textContent).toMatch(/0/);
  expect(host.querySelector('[data-testid="deal-owner-only"]')).toBeFalsy();
  await act(async () => { root.unmount(); });
  host.remove();
});

test("staff deal format hides extra margin", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(
      <DealFormatCard
        snapshot={{
          exShowroom: 785000, rto: 5500, insurance: 19000,
          priceTotal: 809500, additionalDiscount: 0,
          needsOwnerApproval: true, netToCx: 809500, supportRequired: -10000,
          extraMargin: 10000,
        }}
        cxDemand={819500}
        readOnly
        showOwnerPnl={false}
      />,
    );
  });
  expect(host.querySelector('[data-testid="deal-support"]')).toBeFalsy();
  expect(host.textContent).not.toMatch(/Extra margin/i);
  await act(async () => { root.unmount(); });
  host.remove();
});

test("shows OEM scheme available with pass-on radios", async () => {
  const host = document.createElement("div");
  document.body.appendChild(host);
  const root = createRoot(host);
  const onPassOn = jest.fn();
  await act(async () => {
    root.render(
      <DealFormatCard
        snapshot={{
          exShowroom: 785000, rto: 5500, insurance: 19000,
          priceTotal: 809500, additionalDiscount: 0, netToCx: 809500,
          schemeMonth: "2026-09",
          schemeOffers: [{ key: "loyaltyBonus", label: "Loyalty Bonus", schemeAvailable: 10000 }],
          schemePassed: 10000,
        }}
        cxDemand={799500}
        passOn={{ loyaltyBonus: true }}
        onPassOn={onPassOn}
      />,
    );
  });
  expect(host.querySelector('[data-testid="deal-oem-scheme"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="deal-scheme-loyaltyBonus"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="pass-yes-loyaltyBonus"]')).toBeTruthy();
  expect(host.querySelector('[data-testid="deal-scheme-passed"]').textContent).toMatch(/10,000|10000/);
  await act(async () => { root.unmount(); });
  host.remove();
});
