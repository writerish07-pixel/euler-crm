import React, { useEffect, useState } from "react";
import { get } from "../lib/api";
import { inr, fmtDate } from "../lib/format";
import { PageHeader, Table, Badge } from "../components/ui";

export default function SchemeMaster() {
  const [rows, setRows] = useState([]);
  useEffect(() => { get("/scheme-master").then(setRows); }, []);
  return (
    <div>
      <PageHeader title="Scheme Master" subtitle="Monthly OEM consumer scheme matrix — dealer vs company share" />
      <Table
        rowKey="schemeId"
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "component", label: "Component", render: (r) => <Badge tone="bg-violet-50 text-violet-700 ring-violet-600/20">{r.component}</Badge> },
          { key: "dealerShare", label: "Dealer Share", align: "right", mono: true, render: (r) => inr(r.dealerShare) },
          { key: "companyShare", label: "Company Share", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.companyShare)}</span> },
          { key: "totalBenefit", label: "Total Benefit", align: "right", mono: true, render: (r) => inr(r.totalBenefit) },
          { key: "circularRef", label: "Circular", mono: true },
          { key: "effectiveTo", label: "Valid To", render: (r) => fmtDate(r.effectiveTo) },
          { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
        ]}
        rows={rows}
      />
    </div>
  );
}
