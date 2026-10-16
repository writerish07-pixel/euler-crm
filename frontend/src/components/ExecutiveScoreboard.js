import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { periodParams } from "../lib/period";
import { Card, Table, Badge } from "./ui";

export function useMonthlyScoreboard(month, year) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let alive = true;
    get("/reports/monthly", periodParams({ month, year }))
      .then((d) => { if (alive) setRows(Array.isArray(d.byExecutive) ? d.byExecutive : []); })
      .catch(() => { if (alive) setRows([]); });
    return () => { alive = false; };
  }, [month, year]);
  return rows;
}

/** Per-executive volume for a picked month / YTD / all. */
export default function ExecutiveScoreboard({
  rows = [],
  title = "Executive scoreboard",
  subtitle = "",
  hygieneByExec = null,
  empty = "No executives in this period",
  children,
}) {
  const live = hygieneByExec || {};
  const showHygiene = Boolean(hygieneByExec);
  return (
    <Card className="p-5 mt-6" data-testid="exec-period-scoreboard">
      <h3 className="font-heading font-bold text-ink mb-1">{title}</h3>
      {subtitle ? <p className="text-xs text-ink-soft mb-3">{subtitle}</p> : null}
      {children}
      <Table
        rowKey="executive"
        empty={empty}
        columns={[
          { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
          { key: "leads", label: "Leads", align: "right" },
          { key: "bookings", label: "Books", align: "right" },
          { key: "deliveries", label: "Del.", align: "right" },
          { key: "conversion", label: "Book %", align: "right", render: (r) => `${r.conversion || 0}%` },
          { key: "deliveryConversion", label: "Del %", align: "right", render: (r) => `${r.deliveryConversion || 0}%` },
          ...(showHygiene ? [
            { key: "followupOverdue", label: "FU overdue", align: "right", render: (r) => {
              const n = live[r.executive]?.followupOverdue || 0;
              return n ? <Badge tone="bg-red-50 text-red-700 ring-red-600/20">{n}</Badge> : "—";
            } },
            { key: "pendingDeliveries", label: "Pending del.", align: "right", render: (r) => {
              const n = live[r.executive]?.pendingDeliveries || 0;
              return n ? <Badge tone="bg-amber-50 text-amber-700 ring-amber-600/20">{n}</Badge> : "—";
            } },
          ] : []),
        ]}
        rows={rows}
      />
    </Card>
  );
}
