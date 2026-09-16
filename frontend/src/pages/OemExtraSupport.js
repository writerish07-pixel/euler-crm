import React, { useCallback, useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, StatCard, Badge } from "../components/ui";
import { LeadLink, useLeadDrawer } from "../components/LeadLink";
import PeriodBar from "../components/PeriodBar";
import ReportActions from "../components/ReportActions";
import { usePeriodState } from "../lib/period";
import { openDocumentFile } from "../components/LeadDocuments";
import { toast } from "sonner";

export default function OemExtraSupport() {
  const [rows, setRows] = useState([]);
  const period = usePeriodState();
  const load = useCallback(
    () => get("/oem-extra-support", period.params).then(setRows).catch(() => setRows([])),
    [period.params],
  );
  const { openLead, drawer } = useLeadDrawer(load);
  useEffect(() => { load(); }, [load]);
  const received = rows.reduce((s, r) => s + Number(r.oemExtraSupportReceived || 0), 0);
  const passed = rows.reduce((s, r) => s + Number(r.oemExtraSupportPassed || 0), 0);
  const retained = rows.reduce((s, r) => s + Number(r.oemExtraSupportRetained || 0), 0);

  return (
    <div>
      <PageHeader title="OEM Extra Support"
        subtitle="Received / Passed / Retained for every lead with extra support — same register as the old sheet"
        actions={<ReportActions onRefresh={load} showRebuild />} />
      <PeriodBar month={period.month} year={period.year} onChange={period.onChange} />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Leads" value={rows.length} />
        <StatCard label="Received" value={inr(received)} tone="text-amber-700" />
        <StatCard label="Passed to customer" value={inr(passed)} />
        <StatCard label="Retained" value={inr(retained)} tone="text-emerald-700" />
      </div>
      <Table
        rowKey="leadId"
        empty="No OEM Extra Support on this period"
        columns={[
          { key: "customerName", label: "Customer", render: (r) => (
            r.leadId
              ? <LeadLink leadId={r.leadId} onOpen={openLead} subtitle={r.customerName} />
              : <span className="font-semibold">{r.customerName || "—"}</span>
          ) },
          { key: "model", label: "Vehicle", render: (r) => (
            <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div>
          ) },
          { key: "executive", label: "Executive" },
          { key: "bookingDate", label: "Booked", render: (r) => fmtDate(r.bookingDate) },
          { key: "oemExtraSupportReceived", label: "Received", align: "right", mono: true,
            render: (r) => <span className="text-amber-700 font-semibold">{inr(r.oemExtraSupportReceived)}</span> },
          { key: "oemExtraSupportPassed", label: "Passed", align: "right", mono: true,
            render: (r) => inr(r.oemExtraSupportPassed) },
          { key: "oemExtraSupportRetained", label: "Retained", align: "right", mono: true,
            render: (r) => <span className="text-emerald-700">{inr(r.oemExtraSupportRetained)}</span> },
          { key: "chassisNumber", label: "Chassis", mono: true },
          { key: "invoiceNumber", label: "Invoice", mono: true },
          { key: "claimReference", label: "OEM claim", mono: true },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status || "Open"}</Badge> },
          { key: "proof", label: "ASM / RM email", render: (r) => (
            r.hasProof && r.proofDocumentId
              ? <button type="button" className="text-xs text-cobalt"
                  onClick={() => openDocumentFile(r.proofDocumentId, r.proofFilename).catch(() => toast.error("Could not open"))}>
                  {r.proofFilename || "Open"}
                </button>
              : <span className="text-[11px] text-rose-700">Missing</span>
          ) },
        ]}
        rows={rows}
      />
      {drawer}
    </div>
  );
}
