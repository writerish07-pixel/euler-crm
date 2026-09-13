import React, { useCallback, useEffect, useState } from "react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";

export default function Activities() {
  const [rows, setRows] = useState([]);
  const period = usePeriodState();
  const load = useCallback(() => get("/activities", period.params).then(setRows), [period.params]);
  useEffect(() => { load(); }, [load]);
  return (
    <div>
      <PageHeader title="Activity Log" subtitle={`${rows.length} logged interactions`}
        actions={<ReportActions onRefresh={load} />} />
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
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
