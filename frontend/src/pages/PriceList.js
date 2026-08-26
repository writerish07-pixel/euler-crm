import React, { useCallback, useEffect, useState } from "react";
import { Search, Copy, ChevronDown, AlertTriangle, RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { get } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Card, Badge, Button, Input, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";

// A price a salesperson can paste into WhatsApp without reformatting.
function quoteText(r, schemeMonth) {
  const lines = [
    `${r.model} ${r.variant}`.trim(),
    "",
    `Ex-showroom   ${inr(r.exShowroom)}`,
    `RTO           ${inr(r.rto)}`,
    `Insurance     ${inr(r.insurance)}`,
  ];
  if (r.otherCharges > 0) lines.push(`Other         ${inr(r.otherCharges)}`);
  if (r.tcsApplies) lines.push(`TCS (1%)      ${inr(r.tcs)}`);
  lines.push("", `On-road       ${inr(r.onRoad)}`);
  if (r.schemeAvailable > 0) {
    lines.push("", `Scheme available ${inr(r.schemeAvailable)} (${schemeMonth})`);
  }
  return lines.join("\n");
}

export default function PriceList() {
  const { isOwner } = useAuth();
  const [data, setData] = useState(null);
  const [model, setModel] = useState("");
  const [q, setQ] = useState("");
  const [open, setOpen] = useState({});
  const [models, setModels] = useState([]);

  const load = useCallback(() => {
    get("/price-list", { ...(model ? { model } : {}), q })
      .then(setData)
      .catch(() => toast.error("Could not load the price list"));
  }, [model, q]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { get("/masters").then((m) => setModels(m.models || [])).catch(() => {}); }, []);

  const copy = (r) => {
    const text = quoteText(r, data.schemeMonth);
    const done = () => toast.success("Price copied");
    if (navigator.clipboard?.writeText) {
      navigator.clipboard.writeText(text).then(done, () => toast.error("Could not copy"));
    } else {
      toast.error("Copying is not available on this browser");
    }
  };

  if (!data) return <div className="text-sm text-ink-faint">Loading price list…</div>;

  return (
    <div data-testid="price-list">
      <PageHeader
        title="Price List"
        subtitle={`${data.totalRows} vehicles · scheme shown for ${data.schemeMonth}`}
        actions={
          <Button variant="secondary" data-testid="price-list-refresh" onClick={load}>
            <RefreshCcw size={15} /> Refresh
          </Button>
        } />

      <div className="flex flex-wrap items-center gap-2 mb-5">
        <div className="relative flex-1 min-w-[12rem] max-w-sm">
          <Search size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-faint" />
          <Input data-testid="price-search" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="Model or variant" className="pl-8" />
        </div>
        <Select data-testid="price-model-filter" value={model} onChange={(e) => setModel(e.target.value)} className="max-w-xs">
          <option value="">All models</option>
          {models.map((m) => <option key={m}>{m}</option>)}
        </Select>
      </div>

      {isOwner && (data.tcsReview || []).length > 0 && (
        <Card className="p-3 mb-5 bg-amber-50 border-amber-200" data-testid="tcs-review">
          <div className="flex gap-2 text-sm text-amber-900">
            <AlertTriangle size={16} className="shrink-0 mt-0.5" />
            <div>
              <b>{data.tcsReview.length} row{data.tcsReview.length === 1 ? "" : "s"} cross ₹10,00,000 but have TCS turned off</b> in
              Price Master, so no TCS is billed on them. Shown without a TCS line here, because quoting a
              charge the app will not raise would be worse. Check them if that is not deliberate:{" "}
              <span className="font-mono text-xs">
                {data.tcsReview.map((t) => `${t.model} ${t.variant}`).join(" · ")}
              </span>
            </div>
          </div>
        </Card>
      )}

      {data.models.length === 0 && (
        <Card className="p-10 text-center text-sm text-ink-faint">No vehicle matches that search</Card>
      )}

      {data.models.map((g) => (
        <section key={g.model} className="mb-7" data-testid={`price-group-${g.model}`}>
          <div className="flex items-baseline gap-2 mb-2">
            <h2 className="font-heading font-bold text-ink text-lg">{g.model}</h2>
            <span className="text-xs text-ink-faint">{g.count} variant{g.count === 1 ? "" : "s"}</span>
          </div>

          <Card className="overflow-hidden">
            {g.rows.map((r) => {
              const isOpen = !!open[r.priceId];
              return (
                <div key={r.priceId} className="border-b border-zinc-100 last:border-0" data-testid={`price-row-${r.priceId}`}>
                  <button
                    onClick={() => setOpen((o) => ({ ...o, [r.priceId]: !o[r.priceId] }))}
                    className="w-full text-left px-4 py-3 hover:bg-zinc-50 transition-colors">
                    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
                      <span className="font-medium text-ink">{r.variant || "—"}</span>
                      {r.schemeAvailable > 0 && (
                        <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">
                          {inr(r.schemeAvailable)} scheme
                        </Badge>
                      )}
                      {r.tcsApplies && (
                        <Badge tone="bg-amber-50 text-amber-800 ring-amber-600/20">+TCS</Badge>
                      )}
                      <span className="ml-auto flex items-baseline gap-2">
                        <span className="font-mono font-bold text-ink tabular text-base">{inr(r.onRoad)}</span>
                        <ChevronDown size={15}
                          className={`text-ink-faint transition-transform ${isOpen ? "rotate-180" : ""}`} />
                      </span>
                    </div>
                    <div className="text-[11px] text-ink-faint mt-0.5">on-road</div>
                  </button>

                  {isOpen && (
                    <div className="px-4 pb-4 bg-zinc-50/60 border-t border-zinc-100">
                      <dl className="grid grid-cols-2 sm:grid-cols-4 gap-x-4 gap-y-2 pt-3 text-sm">
                        <Line k="Ex-showroom" v={r.exShowroom} />
                        <Line k="RTO" v={r.rto} />
                        <Line k="Insurance" v={r.insurance} />
                        {r.otherCharges > 0 && <Line k="Other charges" v={r.otherCharges} />}
                        {r.tcsApplies && <Line k="TCS (1%)" v={r.tcs} />}
                        <Line k="On-road" v={r.onRoad} strong />
                      </dl>
                      {r.schemeAvailable > 0 && (
                        <p className="text-xs text-ink-soft mt-3">
                          Scheme available this month:{" "}
                          <span className="font-mono font-semibold text-emerald-700">{inr(r.schemeAvailable)}</span>
                          {" "}— how much of it is passed is decided on the lead.
                        </p>
                      )}
                      <div className="mt-3">
                        <Button variant="secondary" data-testid={`copy-price-${r.priceId}`}
                          onClick={(e) => { e.stopPropagation(); copy(r); }}>
                          <Copy size={14} /> Copy price
                        </Button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </Card>
        </section>
      ))}

      <p className="text-xs text-ink-faint">
        Prices come from Price Master and update the moment the owner changes them. Accessories,
        handling and exchange are added per deal on the lead.
      </p>
    </div>
  );
}

function Line({ k, v, strong }) {
  return (
    <div>
      <dt className="text-[11px] uppercase tracking-wide text-ink-faint">{k}</dt>
      <dd className={`font-mono tabular ${strong ? "font-bold text-ink" : "text-ink-soft"}`}>{inr(v)}</dd>
    </div>
  );
}
