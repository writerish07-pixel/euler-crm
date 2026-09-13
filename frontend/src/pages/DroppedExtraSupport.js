import React, { useCallback, useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, StatCard } from "../components/ui";
import { LeadLink, useLeadDrawer } from "../components/LeadLink";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";

export default function DroppedExtraSupport() {
  const [rows, setRows] = useState([]);
  const period = usePeriodState();
  const load = useCallback(() => get("/dropped-extra-support", period.params).then(setRows).catch(() => setRows([])), [period.params]);
  const { openLead, drawer } = useLeadDrawer(load);
  useEffect(() => { load(); }, [load]);
  const total = rows.reduce((s, r) => s + Number(r.droppedAmount || 0), 0);

  return (
    <div>
      <PageHeader title="Dropped Extra Support"
        subtitle="OEM Extra Support that was not approved and was taken off the claim register"
        actions={<ReportActions onRefresh={load} showRebuild />} />
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
      <div className="grid grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
        <StatCard label="Dropped lines" value={rows.length} />
        <StatCard label="Amount dropped" value={inr(total)} tone="text-rose-600" />
      </div>
      <Table
        rowKey="dropId"
        empty="No Extra Support has been dropped"
        columns={[
          { key: "customerName", label: "Customer", render: (r) => (
            r.leadId
              ? <LeadLink leadId={r.leadId} onOpen={openLead} subtitle={r.customerName} />
              : <span className="font-semibold">{r.customerName || "—"}</span>
          ) },
          { key: "model", label: "Vehicle" },
          { key: "droppedAmount", label: "Dropped", align: "right", mono: true,
            render: (r) => <span className="text-rose-700 font-semibold">{inr(r.droppedAmount)}</span> },
          { key: "claimReference", label: "OEM claim", mono: true },
          { key: "reason", label: "Reason" },
          { key: "droppedBy", label: "Dropped by" },
          { key: "droppedAt", label: "When", render: (r) => fmtDate(r.droppedAt) },
        ]}
        rows={rows}
      />
      {drawer}
    </div>
  );
}
