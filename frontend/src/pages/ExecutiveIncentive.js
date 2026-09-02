import React, { useCallback, useEffect, useState } from "react";
import { Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { get, put } from "../lib/api";
import { inr } from "../lib/format";
import { PageHeader, Card, Table, Button, Field, Input, Select, Badge } from "../components/ui";

function emptyLevel() {
  return { fromUnits: "", toUnits: "", amount: "" };
}

function levelsFromPlan(plan) {
  const rows = (plan?.levels || []).map((L) => ({
    fromUnits: L.fromUnits ?? "",
    toUnits: L.toUnits ?? "",
    amount: L.amount ?? "",
  }));
  return rows.length ? rows : [emptyLevel()];
}

export default function ExecutiveIncentive() {
  const [executive, setExecutive] = useState("");
  const [executives, setExecutives] = useState([]);
  const [minUnits, setMinUnits] = useState(0);
  const [levels, setLevels] = useState([emptyLevel()]);
  const [source, setSource] = useState("none");
  const [board, setBoard] = useState(null);
  const [busy, setBusy] = useState(false);

  const applyPlan = (plan) => {
    setMinUnits(plan?.minUnits || 0);
    setLevels(levelsFromPlan(plan));
    setSource(plan?.source || "none");
  };

  const loadRoster = useCallback(async () => {
    const [masters, b] = await Promise.all([
      get("/masters"),
      get("/executive-incentive/board"),
    ]);
    setBoard(b);
    const names = new Set();
    (masters.executives || []).forEach((n) => n && names.add(n));
    (b.executives || []).forEach((r) => r.executive && names.add(r.executive));
    const list = [...names].sort((a, b) => a.localeCompare(b, undefined, { sensitivity: "base" }));
    setExecutives(list);
    return list;
  }, []);

  useEffect(() => {
    loadRoster()
      .then((list) => {
        setExecutive((prev) => (prev && list.includes(prev) ? prev : (list[0] || "")));
      })
      .catch(() => toast.error("Could not load executive incentive"));
  }, [loadRoster]);

  useEffect(() => {
    if (!executive) {
      applyPlan({ minUnits: 0, levels: [], source: "none" });
      return;
    }
    get("/executive-incentive/plan", { executive })
      .then(applyPlan)
      .catch(() => toast.error("Could not load this executive’s incentive"));
  }, [executive]);

  const setLevel = (i, k) => (e) => {
    const v = e.target.value;
    setLevels((rows) => rows.map((r, idx) => (idx === i ? { ...r, [k]: v } : r)));
  };

  const save = async () => {
    if (!executive) return toast.error("Pick an executive first");
    setBusy(true);
    try {
      const body = {
        executive,
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
      toast.success(`Saved for ${executive}`);
      await loadRoster();
      const plan = await get("/executive-incentive/plan", { executive });
      applyPlan(plan);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not save");
    } finally { setBusy(false); }
  };

  return (
    <div data-testid="executive-incentive-page">
      <PageHeader
        title="Executive Incentive"
        subtitle="Owner and Sales GM set each executive’s min units, levels and ₹ per unit. Pick a person, set their ladder, then Save. Executives see only theirs on their dashboard — not the company Incentive Master."
        actions={<Button data-testid="save-exec-incentive" onClick={save} disabled={busy || !executive}>{busy ? "Saving…" : "Save"}</Button>}
      />

      <Card className="p-5 mb-6 max-w-xl">
        <Field label="Executive">
          <Select
            data-testid="exec-inc-person"
            value={executive}
            onChange={(e) => setExecutive(e.target.value)}
          >
            {!executives.length && <option value="">No executives yet</option>}
            {executives.map((n) => (
              <option key={n} value={n}>{n}</option>
            ))}
          </Select>
        </Field>
        <Field label="Min units to start incentive">
          <Input data-testid="exec-inc-min" type="number" min="0" value={minUnits}
            onChange={(e) => setMinUnits(e.target.value)} disabled={!executive} />
        </Field>
        <p className="text-xs text-ink-faint mt-2">Below this, ₹0 for this person. Once they hit a level, all of that month’s deliveries pay at that level’s rate.</p>
        {source === "shared" && (
          <p className="text-xs text-amber-700 mt-2">This is the old shared ladder. Save to make it {executive || "this executive"}’s own target.</p>
        )}
        {source === "none" && executive && (
          <p className="text-xs text-ink-soft mt-2">No ladder saved for {executive} yet.</p>
        )}
      </Card>

      <Card className="p-5 mb-6">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-heading font-bold text-ink">Levels for {executive || "…"}</h3>
          <Button variant="secondary" disabled={!executive} onClick={() => setLevels((r) => [...r, emptyLevel()])}>
            <Plus size={14} /> Add level
          </Button>
        </div>
        <div className="space-y-3">
          {levels.map((L, i) => (
            <div key={i} className="grid grid-cols-1 sm:grid-cols-4 gap-3 items-end">
              <Field label="From units">
                <Input type="number" min="1" value={L.fromUnits} onChange={setLevel(i, "fromUnits")}
                  data-testid={`exec-inc-from-${i}`} disabled={!executive} />
              </Field>
              <Field label="To units (blank = and above)">
                <Input type="number" min="1" value={L.toUnits} onChange={setLevel(i, "toUnits")}
                  data-testid={`exec-inc-to-${i}`} disabled={!executive} />
              </Field>
              <Field label="₹ per unit">
                <Input type="number" min="0" value={L.amount} onChange={setLevel(i, "amount")}
                  data-testid={`exec-inc-amt-${i}`} disabled={!executive} />
              </Field>
              <Button variant="secondary" disabled={!executive}
                onClick={() => setLevels((rows) => rows.filter((_, idx) => idx !== i))}>
                <Trash2 size={14} /> Remove
              </Button>
            </div>
          ))}
        </div>
      </Card>

      <Card className="p-0 overflow-hidden">
        <div className="p-5 pb-2">
          <h3 className="font-heading font-bold text-ink">This month</h3>
          <p className="text-xs text-ink-soft">{board?.month || "—"} · each person × their own ladder · tap a row to edit</p>
        </div>
        <Table
          rowKey="executive"
          empty="No executives yet"
          onRowClick={(r) => r.executive && setExecutive(r.executive)}
          columns={[
            { key: "executive", label: "Executive", render: (r) => (
              <span className="font-semibold">
                {r.executive}
                {r.executive === executive ? <span className="text-cobalt font-normal"> · editing</span> : null}
              </span>
            ) },
            { key: "units", label: "Units", align: "right" },
            { key: "hasOwnPlan", label: "Plan", render: (r) => (
              <Badge tone={r.hasOwnPlan ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20" : "bg-zinc-100 text-zinc-600 ring-zinc-500/20"}>
                {r.hasOwnPlan ? "Set" : "Not set"}
              </Badge>
            ) },
            { key: "amountPerUnit", label: "₹ / unit", align: "right", mono: true, render: (r) => inr(r.amountPerUnit) },
            { key: "total", label: "Incentive", align: "right", mono: true, render: (r) => inr(r.total) },
          ]}
          rows={board?.executives || []}
        />
      </Card>
    </div>
  );
}
