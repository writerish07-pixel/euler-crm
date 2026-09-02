import React, { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Warehouse } from "lucide-react";
import { get } from "../lib/api";
import { Card, Table } from "./ui";

/** Available yard stock — same numbers on every staff dashboard. */
export default function YardStockCard() {
  const [summary, setSummary] = useState(null);
  useEffect(() => {
    get("/inventory/summary").then(setSummary).catch(() => setSummary({ total: 0, rows: [] }));
  }, []);
  const rows = (summary?.rows || []).slice(0, 8);
  return (
    <Card className="p-5" data-testid="yard-stock-card">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <Warehouse size={16} className="text-cobalt" />
          <h3 className="font-heading font-bold text-ink">Available inventory</h3>
        </div>
        <Link to="/inventory" className="text-xs font-semibold text-cobalt hover:underline">
          {summary?.total ?? 0} in yard
        </Link>
      </div>
      <Table
        rowKey="id"
        empty="No yard stock yet"
        rows={rows.map((r, i) => ({ ...r, id: `${r.model}|${r.variant}|${i}` }))}
        columns={[
          { key: "model", label: "Model", render: (r) => <span className="font-semibold">{r.model}</span> },
          { key: "variant", label: "Variant" },
          { key: "count", label: "Qty", align: "right", mono: true },
        ]}
      />
    </Card>
  );
}
