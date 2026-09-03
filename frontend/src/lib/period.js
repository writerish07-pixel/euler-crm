import { useCallback, useMemo, useState } from "react";

/** Shared month/year period for registers. Empty month+year = all time. */

export function thisMonth() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
}

export function thisYear() {
  return String(new Date().getFullYear());
}

export function periodParams({ month, year } = {}) {
  if (month) return { month };
  if (year && /^\d{4}$/.test(String(year))) return { year };
  return {};
}

export function periodLabel({ month, year } = {}) {
  if (month) return month;
  if (year) return year;
  return "All";
}

export function usePeriodState(initialMonth = "", initialYear = "") {
  const [month, setMonth] = useState(initialMonth);
  const [year, setYear] = useState(initialYear);
  const params = useMemo(() => periodParams({ month, year }), [month, year]);
  const onChange = useCallback(({ month: m, year: y }) => {
    setMonth(m || "");
    setYear(y || "");
  }, []);
  return { month, year, params, onChange };
}
