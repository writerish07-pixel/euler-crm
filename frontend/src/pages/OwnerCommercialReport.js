import React, { useEffect, useState } from "react";
import { Coins, HandCoins, Building2, Receipt } from "lucide-react";
import { get } from "../lib/api";
import { inr, compactInr } from "../lib/format";
import { Card, PageHeader, StatCard, Table } from "../components/ui";

function KVRow({ label, value, tone }) {
  return (
    <div className="flex items-center justify-between py-2.5 border-b border-line last:border-0" data-testid={`ocr-${label.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`}>
      <span className="text-sm text-ink-soft">{label}</span>
      <span className={`font-mono font-semibold ${tone || "text-ink"}`}>{value}</span>
    </div>
  );
}

export default function OwnerCommercialReport() {
  const [d, setD] = useState(null);
  useEffect(() => { get("/reports/owner-commercial").then(setD).catch(() => {}); }, []);
  if (!d) return <div className="text-ink-faint text-sm">Loading report…</div>;
  const o = d.discountOwnership, c = d.claimPosition, a = d.averages;
  return (
    <div data-testid="owner-commercial-report">
      <PageHeader title="Owner Commercial Report" subtitle="Owner · discount ownership, claim position & executive usage" />
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
        <StatCard label="Total Bookings" value={o.totalBookings} icon={Receipt} tone="text-cobalt" />
        <StatCard label="OEM-Funded (company)" value={compactInr(o.oemFunded)} icon={Building2} tone="text-emerald-600" />
        <StatCard label="Your Share Given" value={compactInr(o.dealerShareGiven)} icon={HandCoins} tone="text-amber-600" />
        <StatCard label="OEM Receivable" value={compactInr(o.oemReceivable)} icon={Coins} tone="text-violet-600" />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Discount Cost Ownership</h3>
          <KVRow label="Your Own Share Given (dealer cost)" value={inr(o.dealerShareGiven)} tone="text-amber-600" />
          <KVRow label="OEM-Funded (company share)" value={inr(o.oemFunded)} tone="text-emerald-600" />
          <KVRow label="Total Discount Given" value={inr(o.totalDiscountGiven)} />
          <KVRow label="OEM Receivable (company share)" value={inr(o.oemReceivable)} tone="text-violet-600" />
          <KVRow label="Scheme Income Retained (absorbed)" value={inr(o.schemeIncomeRetained)} />
        </Card>
        <Card className="p-5">
          <h3 className="font-heading font-bold text-ink mb-3">Claim Position &amp; Averages</h3>
          <KVRow label="Pending Claims (count)" value={c.pendingClaims} />
          <KVRow label="Pending Claim Value" value={inr(c.pendingValue)} tone="text-red-600" />
          <KVRow label="Received Claim Value" value={inr(c.receivedValue)} tone="text-emerald-600" />
          <KVRow label="Scheme ROI (OEM % of total discount)" value={`${c.schemeRoiPct}%`} />
          <KVRow label="Average Claim Ageing (days)" value={c.avgClaimAgeingDays} />
          <KVRow label="Average Discount / Booking" value={inr(a.avgDiscountPerBooking)} />
          <KVRow label="Average Customer Payable" value={inr(a.avgCustomerPayable)} />
        </Card>
      </div>
      <h3 className="font-heading font-bold text-ink mb-3">Executive Discount Usage</h3>
      <Table rowKey="executive"
        columns={[
          { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
          { key: "bookings", label: "Bookings", align: "right" },
          { key: "totalDiscount", label: "Total Discount", align: "right", mono: true, render: (r) => inr(r.totalDiscount) },
          { key: "dealerDiscount", label: "Dealer Discount", align: "right", mono: true, render: (r) => inr(r.dealerDiscount) },
          { key: "oemDiscount", label: "OEM Discount", align: "right", mono: true, render: (r) => inr(r.oemDiscount) },
        ]}
        rows={d.byExecutive} empty="No bookings yet" />
    </div>
  );
}
