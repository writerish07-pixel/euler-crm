import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function Activities() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/activities").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Activity Log" subtitle={`${rows.length} logged interactions`} />
      <Table
        rowKey="activityId"
        columns={[
          { key: "activityId", label: "ID", mono: true },
          { key: "date", label: "Date", render: (r) => <span>{fmtDate(r.date)} <span className="text-ink-faint text-xs">{r.time}</span></span> },
          { key: "leadId", label: "Lead", mono: true },
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "activityType", label: "Type", render: (r) => <Badge>{r.activityType}</Badge> },
          { key: "discussion", label: "Discussion" },
          { key: "executive", label: "Executive" },
        ]}
        rows={rows}
      />
    </div>
  );
}
