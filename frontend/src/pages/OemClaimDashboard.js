import React, { useEffect, useState } from "react";
import { Receipt, Building2, HandCoins, AlertTriangle } from "lucide-react";
import { get } from "../lib/api";
import { inr, compactInr } from "../lib/format";
import { Card, PageHeader, StatCard, Table, Badge } from "../components/ui";

export default function OemClaimDashboard() {
  const [d, setD] = useState(null);
  useEffect(() => { get("/reports/oem-claim-dashboard").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Loading dashboard…</div>;
  const v = d.valueSummary;
  return (
    <div data-testid="oem-claim-dashboard">
      <PageHeader title="OEM Claim Dashboard" subtitle="Owner · company-share claim position across all bookings" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Bookings" value={d.bookings} icon={Receipt} tone="text-cobalt" />
        <StatCard label="Eligible Claim (company)" value={compactInr(v.eligibleClaim)} icon={Building2} tone="text-emerald-600" />
        <StatCard label="Your Own Share" value={compactInr(v.yourOwnShare)} icon={HandCoins} tone="text-amber-600" />
        <StatCard label="OEM Liability (unpaid)" value={compactInr(v.oemLiability)} icon={AlertTriangle} tone="text-red-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Claim Status Summary</h3>
          <Table rowKey="status"
            columns={[
              { key: "status", label: "Status", render: (r) => <Badge>{r.status}</Badge> },
              { key: "bookings", label: "Bookings", align: "right" },
              { key: "value", label: "Claim Value", align: "right", mono: true, render: (r) => inr(r.value) },
            ]}
            rows={d.statusSummary} empty="No claims" />
        </Card>
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Value Summary</h3>
          <div className="space-y-2.5">
            {[
              ["Total Discount Given (full scheme)", v.totalDiscountGiven, "text-ink"],
              ["Eligible Claim (company share)", v.eligibleClaim, "text-emerald-600"],
              ["Euler Company Share", v.companyShare, "text-violet-600"],
              ["Your Own Share (non-claimable)", v.yourOwnShare, "text-amber-600"],
              ["OEM Liability (eligible not received)", v.oemLiability, "text-red-600"],
            ].map(([label, val, tone]) => (
              <div key={label} className="flex items-center justify-between py-2 border-b border-line last:border-0">
                <span className="text-sm text-ink-soft">{label}</span>
                <span className={`font-mono font-semibold ${tone}`}>{inr(val)}</span>
              </div>
            ))}
          </div>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div>
          <h3 className="font-heading font-bold text-ink mb-3">Monthly</h3>
          <Table rowKey="month"
            columns={[
              { key: "month", label: "Month", render: (r) => <span className="font-semibold">{r.month}</span> },
              { key: "bookings", label: "Bkgs", align: "right" },
              { key: "claim", label: "Claim", align: "right", mono: true, render: (r) => inr(r.claim) },
            ]}
            rows={d.monthly} empty="—" />
        </div>
        <div>
          <h3 className="font-heading font-bold text-ink mb-3">Scheme-wise</h3>
          <Table rowKey="scheme"
            columns={[
              { key: "scheme", label: "Scheme", render: (r) => <span className="font-semibold">{r.scheme}</span> },
              { key: "count", label: "Cnt", align: "right" },
              { key: "value", label: "Claim", align: "right", mono: true, render: (r) => inr(r.value) },
            ]}
            rows={d.schemeWise} empty="—" />
        </div>
        <div>
          <h3 className="font-heading font-bold text-ink mb-3">Executive-wise</h3>
          <Table rowKey="executive"
            columns={[
              { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
              { key: "bookings", label: "Bkgs", align: "right" },
              { key: "claim", label: "Claim", align: "right", mono: true, render: (r) => inr(r.claim) },
            ]}
            rows={d.executiveWise} empty="—" />
        </div>
      </div>
    </div>
  );
}
