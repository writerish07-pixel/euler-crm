import React, { useEffect, useState } from "react";
import { Zap, RefreshCw } from "lucide-react";
import { get } from "../lib/api";
import { Card } from "../components/ui";

export default function Share() {
  const [d, setD] = useState(null);
  const load = () => get("/share/dashboard").then(setD).catch(() => {});
  useEffect(() => { load(); const t = setInterval(load, 180000); return () => clearInterval(t); }, []);

  if (!d) return <div className="min-h-screen grid place-items-center bg-app text-ink-faint">Loading…</div>;

  return (
    <div className="min-h-screen bg-app">
      <header className="border-b border-line bg-white">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center gap-2.5">
          <div className="h-9 w-9 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={20} fill="white" className="text-white" /></div>
          <div>
            <div className="font-heading font-extrabold text-ink leading-none">Euler Motors — Company Board</div>
            <div className="text-[11px] text-ink-faint mt-0.5">Read-only · {d.month}</div>
          </div>
          <button onClick={load} className="ml-auto text-ink-faint hover:text-ink transition-colors"><RefreshCw size={16} /></button>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-10">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-5">
          <Big label="Active Bookings" value={d.activeBookings} tone="text-emerald-600" sub={`${d.newThisMonth} new in ${d.month}`} />
          <Big label="Retail (this month)" value={d.retailThisMonth} tone="text-cobalt" sub="deliveries this month" />
          <Big label="New Bookings (MTD)" value={d.newThisMonth} tone="text-violet-600" sub={d.month} />
        </div>

        <Card className="p-6 mt-6">
          <h3 className="font-heading font-bold text-ink mb-4">Active Bookings by Model</h3>
          <div className="space-y-3">
            {d.byModel.length === 0 && <p className="text-sm text-ink-faint">No active bookings.</p>}
            {d.byModel.map((m) => {
              const max = Math.max(...d.byModel.map((x) => x.count), 1);
              return (
                <div key={m.model} className="flex items-center gap-3">
                  <span className="w-28 text-sm font-medium text-ink">{m.model}</span>
                  <div className="flex-1 h-6 bg-zinc-100 rounded-md overflow-hidden">
                    <div className="h-full bg-cobalt rounded-md transition-all" style={{ width: `${(m.count / max) * 100}%` }} />
                  </div>
                  <span className="w-8 text-right font-mono font-bold text-ink">{m.count}</span>
                </div>
              );
            })}
          </div>
        </Card>
        <p className="text-center text-xs text-ink-faint mt-8">Auto-refreshes every 3 minutes · No customer or staff data shown</p>
      </main>
    </div>
  );
}

function Big({ label, value, tone, sub }) {
  return (
    <Card className="p-6">
      <div className="text-sm font-medium text-ink-soft">{label}</div>
      <div className={`font-heading text-5xl font-extrabold tabular mt-2 ${tone}`}>{value}</div>
      <div className="text-xs text-ink-faint mt-2">{sub}</div>
    </Card>
  );
}
