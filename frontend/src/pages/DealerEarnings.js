import React, { useEffect, useState } from "react";
import { Coins } from "lucide-react";
import { get } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Table, Badge, StatCard } from "../components/ui";

export default function DealerEarnings() {
  const [data, setData] = useState({ rows: [], total: 0 });
  useEffect(() => { get("/dealer-earnings").then(setData); }, []);
  const { rows, total } = data;
  const margin = rows.reduce((s, r) => s + Number(r.dealerMarginNetExGst || 0), 0);
  const scheme = rows.reduce((s, r) => s + Number(r.dealerSchemeRetained || 0), 0);
  const oemExtra = rows.reduce((s, r) => s + Number(r.oemExtraSupportRetained || 0), 0);
  const funded = rows.reduce((s, r) => s + Number(r.dealerFundedBenefit || 0), 0);

  return (
    <div>
      <PageHeader title="Dealer Earnings" subtitle="Owner-only margin & retained-benefit analytics" />
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4 mb-6">
        <StatCard label="Total Dealer Earnings" value={inr(total)} icon={Coins} tone="text-amber-600" />
        <StatCard label="Dealer Margin (Net)" value={inr(margin)} tone="text-cobalt" />
        <StatCard label="Scheme Retained" value={inr(scheme)} tone="text-emerald-600" />
        <StatCard label="OEM Extra Retained" value={inr(oemExtra)} tone="text-amber-700" />
        <StatCard label="Dealer-Funded Benefit" value={funded ? `−${inr(funded)}` : inr(0)} tone="text-rose-600" />
      </div>
      <Table
        rowKey="leadId"
        columns={[
          { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
          { key: "model", label: "Vehicle", render: (r) => <div className="text-sm">{r.model}<div className="text-xs text-ink-faint">{r.variant}</div></div> },
          { key: "executive", label: "Executive" },
          { key: "dealerMarginNetExGst", label: "Margin (Net)", align: "right", mono: true, render: (r) => inr(r.dealerMarginNetExGst) },
          { key: "dealerSchemeRetained", label: "Scheme Retained", align: "right", mono: true, render: (r) => inr(r.dealerSchemeRetained) },
          { key: "oemExtraSupportRetained", label: "OEM Extra Retained", align: "right", mono: true,
            render: (r) => <span className="text-amber-700">{inr(r.oemExtraSupportRetained)}</span> },
          { key: "dealerInsuranceIncome", label: "Insurance Inc.", align: "right", mono: true, render: (r) => inr(r.dealerInsuranceIncome) },
          { key: "dealerFundedBenefit", label: "Dealer-Funded Benefit", align: "right", mono: true,
            render: (r) => {
              const v = Number(r.dealerFundedBenefit || 0);
              return <span className={v ? "text-rose-600" : ""}>{v ? `−${inr(v)}` : inr(0)}</span>;
            } },
          { key: "currentStage", label: "Stage", render: (r) => <Badge>{r.currentStage}</Badge> },
          { key: "totalDealerEarnings", label: "Total Earnings", align: "right", mono: true,
            render: (r) => <span className="font-bold text-amber-600">{inr(r.totalDealerEarnings)}</span> },
        ]}
        rows={rows}
      />
      <p className="text-xs text-ink-faint mt-3">
        Total Earnings = Margin + Scheme Retained + OEM Extra Retained + Insurance Income + extras − Dealer-Funded Benefit.
        OEM Extra Retained = Received − Passed.
      </p>
    </div>
  );
}
