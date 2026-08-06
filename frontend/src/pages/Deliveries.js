import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

const Chip = ({ ok, label }) => (
  <span className={`inline-flex items-center rounded-md px-1.5 py-0.5 text-[10px] font-semibold ring-1 ring-inset mr-1 ${ok ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-50 text-ink-faint ring-line"}`}>
    {label}{ok ? " ✓" : ""}
  </span>
);

export default function Deliveries() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/deliveries").then(setRows); }, []);
  const isOk = (v) => ["done", "yes", "true", "completed"].includes(String(v || "").toLowerCase());
  return (
    <div>
      <PageHeader title="Delivery Tracker" subtitle={`${rows.length} bookings in fulfilment`} />
      <Table
        rowKey="leadId"
        columns={[
          { key: "leadId", label: "Lead", mono: true },
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
          { key: "checklist", label: "Checklist", render: (r) => (
            <div className="flex flex-wrap">
              <Chip ok={isOk(r.insurance)} label="INS" />
              <Chip ok={isOk(r.registration)} label="REG" />
              <Chip ok={isOk(r.invoice)} label="INV" />
              <Chip ok={isOk(r.rc)} label="RC" />
              <Chip ok={isOk(r.pdi)} label="PDI" />
            </div>
          )},
          { key: "delivered", label: "Delivered", render: (r) => <Badge tone={isOk(r.delivered) ? "bg-teal-50 text-teal-700 ring-teal-600/20" : "bg-amber-50 text-amber-700 ring-amber-600/20"}>{isOk(r.delivered) ? "Delivered" : "Pending"}</Badge> },
          { key: "deliveryDate", label: "Date", render: (r) => fmtDate(r.deliveryDate) },
          { key: "chassisNumber", label: "Chassis", mono: true },
        ]}
        rows={rows}
        empty="No bookings in fulfilment"
      />
    </div>
  );
}
