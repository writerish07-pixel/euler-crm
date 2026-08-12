import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function Bookings() {
  const { isField } = useAuth();
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/bookings").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Booking Register" subtitle={`${rows.length} bookings${isField ? " · field view" : ""}`} />
      <Table
        rowKey="bookingId"
        columns={[
          { key: "bookingId", label: "Booking ID", mono: true, render: (r) => <span className="font-semibold text-cobalt">{r.bookingId}</span> },
          { key: "leadId", label: "Lead", mono: true },
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
          { key: "bookingDate", label: "Date", render: (r) => fmtDate(r.bookingDate) },
          ...(!isField ? [
            { key: "bookingAmount", label: "Advance", align: "right", mono: true, render: (r) => inr(r.bookingAmount) },
            { key: "paymentMode", label: "Mode", render: (r) => <Badge>{r.paymentMode}</Badge> },
          ] : []),
          { key: "bookingStatus", label: "Status", render: (r) => <Badge>{r.bookingStatus}</Badge> },
        ]}
        rows={rows}
      />
    </div>
  );
}
