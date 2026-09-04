import React from "react";
import { Button, Field, Input } from "./ui";
import { thisMonth, thisYear } from "../lib/period";

/**
 * All | This month (MTD) | YTD | pick a month | pick a year.
 *
 * Existing list pages default to All so historic rows do not vanish.
 * The Monthly Register defaults to the current month.
 */
export default function PeriodBar({ month = "", year = "", onChange, showAll = true }) {
  const mtd = thisMonth();
  const ytd = thisYear();
  const mode = month ? "month" : year ? "year" : "all";
  const set = (next) => onChange({ month: next.month || "", year: next.year || "" });

  return (
    <div className="flex flex-wrap items-end gap-2 mb-4" data-testid="period-bar">
      {showAll && (
        <Button type="button" variant={mode === "all" ? "primary" : "secondary"}
          data-testid="period-all" onClick={() => set({ month: "", year: "" })}>
          All
        </Button>
      )}
      <Button type="button" variant={month === mtd ? "primary" : "secondary"}
        data-testid="period-mtd" onClick={() => set({ month: mtd, year: "" })}>
        This month
      </Button>
      <Button type="button" variant={!month && year === ytd ? "primary" : "secondary"}
        data-testid="period-ytd" onClick={() => set({ month: "", year: ytd })}>
        YTD
      </Button>
      <Field label="Month">
        <Input type="month" data-testid="period-month" value={month}
          onChange={(e) => set({ month: e.target.value, year: "" })} />
      </Field>
      <Field label="Year">
        <Input type="number" data-testid="period-year" min="2020" max="2099"
          placeholder="YYYY" value={year} className="w-[7rem]"
          onChange={(e) => set({ month: "", year: e.target.value })} />
      </Field>
    </div>
  );
}
