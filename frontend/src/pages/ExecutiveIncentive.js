import React, { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Card, Table, Button, Field, Input } from "../components/ui";

function emptyLevel() {
  return { fromUnits: "", toUnits: "", amount: "" };
}

export default function ExecutiveIncentive() {
  const [minUnits, setMinUnits] = useState(0);
  const [levels, setLevels] = useState([emptyLevel()]);
  const [board, setBoard] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const plan = await get("/executive-incentive/plan");
    setMinUnits(plan.minUnits || 0);
    setLevels((plan.levels || []).length
      ? plan.levels.map((L) => ({
        fromUnits: L.fromUnits ?? "",
        toUnits: L.toUnits ?? "",
        amount: L.amount ?? "",
      }))
      : [emptyLevel()]);
    const b = await get("/executive-incentive/board");
    setBoard(b);
  }, []);
  useEffect(() => { load().catch(() => toast.error("Could not load executive incentive")); }, [load]);

  const setLevel = (i, k) => (e) => {
    const v = e.target.value;
    setLevels((rows) => rows.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  };

  const save = async () => {
    setBusy(true);
    try {
      const body = {
        minUnits: Number(minUnits) || 0,
        levels: levels
          .filter((L) => Number(L.fromUnits) > 0)
          .map((L) => ({
            fromUnits: Number(L.fromUnits),
            toUnits: L.toUnits === "" || L.toUnits == null ? null : Number(L.toUnits),
            amount: Number(L.amount) || 0,
          })),
      };
      await put("/executive-incentive/plan", body);
      toast.success("Executive incentive saved");
      await load();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="executive-incentive-page">
      <PageHeader
        title="Executive Incentive"
        subtitle="You set min units, levels and ₹ per unit. Executives see this on their dashboard — not the company Incentive Master."
        actions={<Button data-testid="save-exec-incentive" onClick={save} disabled={busy}>{busy ? "Saving…" : "Save"}</Button>}
      />

      <Card className="p-5 mb-6 max-w-xl">
        <Field label="Min units to start incentive">
          <Input data-testid="exec-inc-min" type="number" min="0" value={minUnits}
            onChange={(e) => setMinUnits(e.target.value)} />
        </Field>
        <p className="text-xs text-ink-faint mt-2">Below this, ₹0. Once they hit a level, all of that month’s deliveries pay at that level’s rate.</p>
      </Card>

      <Card className="p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-heading font-bold text-ink">Levels</h3>
          <Button variant="secondary" onClick={() => setLevels((r) => [...r, emptyLevel()])}>
            <Plus size={14} /> Add level
          </Button>
        </div>
        <div className="space-y-3">
          {levels.map((L, i) => (
            <div key={i} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
              <Field label="From units">
                <Input type="number" min="1" value={L.fromUnits} onChange={setLevel(i, "fromUnits")}
                  data-testid={`exec-inc-from-${i}`} />
              </Field>
              <Field label="To units (blank = and above)">
                <Input type="number" min="1" value={L.toUnits} onChange={setLevel(i, "toUnits")}
                  data-testid={`exec-inc-to-${i}`} />
              </Field>
              <Field label="₹ per unit">
                <Input type="number" min="0" value={L.amount} onChange={setLevel(i, "amount")}
                  data-testid={`exec-inc-amt-${i}`} />
              </Field>
              <Button variant="secondary" onClick={() => setLevels((rows) => rows.filter((_, idx) => idx !== i))}>
                <Trash2 size={14} /> Remove
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <div className="p-5 pb-2">
          <h3 className="font-heading font-bold text-ink">This month</h3>
          <p className="text-xs text-ink-soft">{board?.month || "—"} · delivered units × current level</p>
        </div>
        <Table
          rowKey="executive"
          empty="No deliveries this month"
          columns={[
            { key: "executive", label: "Executive", render: (r) => <span className="font-semibold">{r.executive}</span> },
            { key: "units", label: "Units", align: "right" },
            { key: "amountPerUnit", label: "₹ / unit", align: "right", mono: true, render: (r) => inr(r.amountPerUnit) },
            { key: "total", label: "Incentive", align: "right", mono: true, render: (r) => inr(r.total) },
          ]}
          rows={board?.executives || []}
        />
      </Card>
    </div>
  );
}
