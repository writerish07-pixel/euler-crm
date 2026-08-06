import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function IncentiveMaster() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/incentive-master").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Incentive Master" subtitle="Executive retail incentive slabs" />
      <Table
        rowKey="incentiveId"
        columns={[
          { key: "productCategory", label: "Category", render: (r) => <span className="font-semibold">{r.productCategory}</span> },
          { key: "incentivePerRetail", label: "Per Retail", align: "right", mono: true, render: (r) => inr(r.incentivePerRetail) },
          { key: "minRetails", label: "Min Retails", align: "right" },
          { key: "maxSlab", label: "Max Slab", align: "right", mono: true, render: (r) => inr(r.maxSlab) },
          { key: "circularRef", label: "Circular", mono: true },
          { key: "effectiveTo", label: "Valid To", render: (r) => fmtDate(r.effectiveTo) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
        ]}
        rows={rows}
      />
      <p className="text-xs text-ink-faint mt-3">{rows[0]?.notes}</p>
    </div>
  );
}
