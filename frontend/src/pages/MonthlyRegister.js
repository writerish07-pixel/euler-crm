import React, { useCallback, useEffect, useState } from "react";
import {
  Users, ClipboardList, Truck, Wallet, Landmark, ReceiptText,
  ShieldCheck, Coins, Ban, CalendarDays,
} from "lucide-react";
import { get } from "../lib/api";
import { inr, compactInr, num } from "../lib/format";
import { thisMonth, periodParams, periodLabel } from "../lib/period";
import { Card, PageHeader, StatCard, Table } from "../components/ui";
import PeriodBar from "../components/PeriodBar";
import { useAuth } from "../context/AuthContext";

function MetricGrid({ m, volumeOnly }) {
  if (!m) return null;
  return (
    <div className="grid grid-cols-2 lg:grid-cols-5 gap-3">
      <StatCard label="Leads" value={num(m.leads?.count)} sub={volumeOnly ? undefined : `${num(m.leads?.booked)} booked · ${num(m.leads?.lost)} lost`} icon={Users} />
      <StatCard label="Bookings" value={num(m.bookings?.count)} sub={volumeOnly ? undefined : compactInr(m.bookings?.amount)} icon={ClipboardList} tone="text-emerald-600" />
      <StatCard label="Deliveries" value={num(m.deliveries?.count)} icon={Truck} tone="text-teal-600" />
      {!volumeOnly && <StatCard label="Payments" value={compactInr(m.payments?.total)} sub={`${num(m.payments?.count)} receipts`} icon={Wallet} tone="text-cobalt" />}
      <StatCard label="Finance pending" value={compactInr(m.finance?.pending)} sub={`${num(m.finance?.files)} files · ${compactInr(m.finance?.received)} in`} icon={Landmark} tone="text-violet-600" />
      {!volumeOnly && (
        <>
          <StatCard label="Scheme eligible" value={compactInr(m.scheme?.eligible)} sub={`${compactInr(m.scheme?.received)} received`} icon={ReceiptText} />
          <StatCard label="Insurance" value={compactInr(m.insurance?.expected)} sub={`${compactInr(m.insurance?.received)} received`} icon={ShieldCheck} />
          <StatCard label="Extra income" value={compactInr(m.extraIncome?.total)} icon={Coins} tone="text-amber-600" />
          <StatCard label="Dealer earnings" value={compactInr(m.earnings?.total)} icon={Coins} tone="text-amber-700" />
          <StatCard label="Cancellations" value={num(m.cancellations?.count)} icon={Ban} tone="text-rose-600" />
        </>
      )}
    </div>
  );
}

function Cell({ label, value }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-ink-faint">{label}</div>
      <div className="font-heading font-bold tabular text-ink">{value}</div>
    </div>
  );
}

function Strip({ title, m, testId, volumeOnly }) {
  if (!m) return null;
  return (
    <Card className="p-4" data-testid={testId}>
      <h3 className="font-heading font-bold text-ink mb-3">{title}</h3>
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-sm">
        <Cell label="Leads" value={num(m.leads?.count)} />
        <Cell label="Bookings" value={num(m.bookings?.count)} />
        <Cell label="Deliveries" value={num(m.deliveries?.count)} />
        {!volumeOnly && <Cell label="Payments" value={compactInr(m.payments?.total)} />}
        <Cell label="Finance in" value={compactInr(m.finance?.received)} />
        {!volumeOnly && <Cell label="Scheme" value={compactInr(m.scheme?.eligible)} />}
        {!volumeOnly && <Cell label="Earnings" value={compactInr(m.earnings?.total)} />}
        {!volumeOnly && <Cell label="Cancelled" value={num(m.cancellations?.count)} />}
      </div>
    </Card>
  );
}

export default function MonthlyRegister() {
  const { isField, isExecutive } = useAuth();
  const volumeOnly = isField;
  const [month, setMonth] = useState(thisMonth());
  const [year, setYear] = useState("");
  const [d, setD] = useState(null);
  const [err, setErr] = useState("");

  const load = useCallback(() => {
    get("/reports/monthly", periodParams({ month, year }))
      .then((r) => { setD(r); setErr(""); })
      .catch((e) => setErr(e?.response?.data?.detail || "Could not load the monthly register"));
  }, [month, year]);

  useEffect(() => { load(); }, [load]);

  const onChange = ({ month: m, year: y }) => { setMonth(m || ""); setYear(y || ""); };
  const selectedLabel = periodLabel({ month, year });
  const subtitle = volumeOnly
    ? "Volume and finance totals · no dealer commercials"
    : isExecutive
      ? "Your assigned leads · pick any month or year for MTD / YTD"
      : "Pick any month or year for MTD / YTD on leads, bookings, money, scheme and earnings";

  const columns = [
    { key: "month", label: "Month", mono: true,
      render: (r) => (
        <button type="button" className={`font-mono text-sm ${r.month === month ? "text-cobalt font-semibold" : "text-ink"}`}
          onClick={() => onChange({ month: r.month, year: "" })}>{r.month}</button>
      ) },
    { key: "leads", label: "Leads", align: "right", render: (r) => num(r.leads?.count) },
    { key: "bookings", label: "Bookings", align: "right", render: (r) => num(r.bookings?.count) },
    ...(!volumeOnly ? [{ key: "bookingAmt", label: "Booking ₹", align: "right", mono: true, render: (r) => inr(r.bookings?.amount) }] : []),
    { key: "deliveries", label: "Delivered", align: "right", render: (r) => num(r.deliveries?.count) },
    ...(!volumeOnly ? [
      { key: "payments", label: "Payments", align: "right", mono: true, render: (r) => inr(r.payments?.total) },
    ] : []),
    { key: "finance", label: "Finance in", align: "right", mono: true, render: (r) => inr(r.finance?.received) },
    ...(!volumeOnly ? [
      { key: "scheme", label: "Scheme", align: "right", mono: true, render: (r) => inr(r.scheme?.eligible) },
      { key: "earnings", label: "Earnings", align: "right", mono: true, render: (r) => inr(r.earnings?.total) },
    ] : []),
  ];

  return (
    <div data-testid="monthly-register">
      <PageHeader
        title="Monthly Register"
        subtitle={d?.scope?.note ? `${subtitle} · ${d.scope.note}` : subtitle}
        actions={<span className="text-xs text-ink-faint inline-flex items-center gap-1"><CalendarDays size={14} /> {d?.generatedAt ? `as of ${new Date(d.generatedAt).toLocaleString("en-IN")}` : ""}</span>}
      />
      <PeriodBar month={month} year={year} onChange={onChange} />
      {err && <Card className="p-4 mb-4 text-sm text-red-700">{err}</Card>}
      {!d && !err && <div className="text-sm text-ink-faint">Loading monthly register…</div>}
      {d && (
        <>
          <section className="mb-6" data-testid="monthly-selected">
            <h3 className="font-heading font-bold text-ink mb-3">Selected · {d.period?.label || selectedLabel}</h3>
            <MetricGrid m={d.selected} volumeOnly={volumeOnly} />
          </section>
          <div className="grid lg:grid-cols-2 gap-4 mb-6">
            <Strip title={`This month (MTD) · ${d.mtd?.period?.label || ""}`} m={d.mtd} testId="monthly-mtd" volumeOnly={volumeOnly} />
            <Strip title={`${d.ytd?.period?.label || "YTD"}`} m={d.ytd} testId="monthly-ytd" volumeOnly={volumeOnly} />
          </div>
          <section data-testid="monthly-by-month">
            <h3 className="font-heading font-bold text-ink mb-2">Month-wise · {d.focusYear}</h3>
            <p className="text-xs text-ink-soft mb-3">Click a month to open that register. Quiet months stay listed.</p>
            <Table
              rowKey="month"
              rows={d.byMonth || []}
              empty="No months in this year"
              columns={columns}
            />
          </section>
        </>
      )}
    </div>
  );
}
