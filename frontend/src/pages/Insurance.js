import React, { useEffect, useState, useCallback, useMemo } from "react";
import { Plus, Pencil, Trash2, Banknote, HandCoins, ShieldCheck } from "lucide-react";
import { toast } from "sonner";
import { get, post, put, del } from "../lib/api";
import { inr, fmtDate, todayISO } from "../lib/format";
import { PageHeader, Table, Badge, Button, Drawer, Field, Input, Select, Card } from "../components/ui";
import { useAuth } from "../context/AuthContext";

const VIEWS = [["all", "All Entries"], ["pending", "Pending"], ["overdue", "Overdue"]];

export default function Insurance() {
  const { isOwner } = useAuth();
  const [rows, setRows] = useState([]);
  const [rollup, setRollup] = useState([]);
  const [agents, setAgents] = useState([]);
  const [view, setView] = useState("all");
  const [agentFilter, setAgentFilter] = useState("");
  const [tab, setTab] = useState("register");
  const [edit, setEdit] = useState(null);
  const [masters, setMasters] = useState(null);
  const [delivered, setDelivered] = useState([]);
  const [receipt, setReceipt] = useState(false);

  const load = useCallback(() => {
    const q = { view, ...(agentFilter ? { agent_id: agentFilter } : {}) };
    get("/insurance", q).then(setRows).catch(() => {});
    get("/insurance/agents-rollup", { view }).then(setRollup).catch(() => {});
  }, [view, agentFilter]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    get("/masters").then(setMasters);
    get("/insurance-agents").then(setAgents).catch(() => setAgents([]));
    get("/leads").then((ls) => setDelivered(ls.filter(
      (l) => (l.deliveryStatus || "").toLowerCase() === "delivered"
        || (l.currentStatus || "").toLowerCase() === "delivered")));
  }, []);

  const expected = rows.reduce((s, r) => s + Number(r.expectedPayout || 0), 0);
  const received = rows.reduce((s, r) => s + Number(r.receivedPayout || 0), 0);
  const overdueCount = rows.filter((r) => r.overdue).length;

  const remove = async (r) => {
    if (!window.confirm("Delete entry?")) return;
    await del(`/insurance/${r.entryId}`);
    toast.success("Deleted");
    load();
  };
  // Staff can't see outstanding, so let them record against any entry; owner sees only pending ones.
  const outstandingRows = isOwner ? rows.filter((r) => Number(r.payoutOutstanding || 0) > 0.01) : rows;

  const columns = [
    { key: "customerName", label: "Customer", render: (r) => <span className="font-semibold">{r.customerName}</span> },
    { key: "insuranceAgentName", label: "Agent", render: (r) => (
      <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.insuranceAgentName || "— none —"}</Badge>
    ) },
    { key: "insuranceCompany", label: "Insurer" },
    { key: "insuranceAmount", label: "Premium", align: "right", mono: true, render: (r) => inr(r.insuranceAmount) },
    ...(isOwner ? [
      { key: "payoutRate", label: "Rate %", align: "right", render: (r) => (
        <span title={rateHint(r)}>{(Number(r.payoutRate) * 100).toFixed(1)}%</span>
      ) },
      { key: "expectedPayout", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expectedPayout) },
    ] : []),
    { key: "receivedPayout", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.receivedPayout)}</span> },
    ...(isOwner ? [
      { key: "payoutOutstanding", label: "Outstanding", align: "right", mono: true, render: (r) => <span className={r.payoutOutstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.payoutOutstanding)}</span> },
    ] : []),
    { key: "payoutDueBy", label: "Due By", render: (r) => (
      <span className={r.overdue ? "text-red-600 font-semibold" : ""}>{fmtDate(r.payoutDueBy) || "—"}</span>
    ) },
    { key: "status", label: "Status", render: (r) => (
      r.overdue ? <Badge tone="bg-red-50 text-red-700 ring-red-600/20">Overdue</Badge> : <Badge>{r.status || "Pending"}</Badge>
    ) },
    ...(isOwner ? [
      { key: "act", label: "", align: "right", render: (r) => (
        <div className="flex justify-end gap-2">
          <button data-testid={`edit-insurance-${r.entryId}`} onClick={(e) => { e.stopPropagation(); setEdit(r); }} className="text-ink-faint hover:text-cobalt"><Pencil size={15} /></button>
          <button data-testid={`delete-insurance-${r.entryId}`} onClick={(e) => { e.stopPropagation(); remove(r); }} className="text-ink-faint hover:text-red-600"><Trash2 size={15} /></button>
        </div>
      )},
    ] : []),
  ];

  return (
    <div data-testid="insurance-register">
      <PageHeader title="Insurance Payouts"
        subtitle={isOwner
          ? `${rows.length} entries · ${inr(received)} received of ${inr(expected)} expected${overdueCount ? ` · ${overdueCount} overdue` : ""}`
          : `${rows.length} entries · ${inr(received)} received`}
        actions={<div className="flex items-center gap-2">
          <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
            {[["register", "Register"], ["receipts", "Payout Receipts"]].map(([k, l]) => (
              <button key={k} data-testid={`ins-tab-${k}`} onClick={() => setTab(k)}
                className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${tab === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
            ))}
          </div>
          <Button variant="secondary" data-testid="record-payout-btn" onClick={() => setReceipt(true)}><HandCoins size={16} /> Record {isOwner ? "Payout" : "Received"}</Button>
          <Button data-testid="add-insurance-btn" onClick={() => setEdit({})}><Plus size={16} /> Add Entry</Button>
        </div>} />

      {tab === "receipts" ? (
        <PayoutReceiptLedger agents={agents} />
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-2 mb-4">
            <div className="flex gap-1 bg-white rounded-lg p-1 border border-line shadow-card">
              {VIEWS.map(([k, l]) => (
                <button key={k} data-testid={`ins-view-${k}`} onClick={() => setView(k)}
                  className={`px-3 py-1.5 text-xs font-medium rounded-md transition-colors ${view === k ? "bg-cobalt text-white" : "text-ink-soft hover:bg-zinc-100"}`}>{l}</button>
              ))}
            </div>
            <Select data-testid="ins-agent-filter" value={agentFilter} onChange={(e) => setAgentFilter(e.target.value)} className="max-w-xs">
              <option value="">All agents</option>
              {agents.map((a) => <option key={a.agentId} value={a.agentId}>{a.agentName}</option>)}
            </Select>
          </div>

          {rollup.length > 0 && (
            <Card className="p-5 mb-6" data-testid="insurance-by-agent">
              <h3 className="font-heading font-bold text-ink mb-1">By agent</h3>
              <p className="text-xs text-ink-soft mb-3">Received vs remaining for the current view</p>
              <Table
                rowKey="agentId"
                columns={[
                  { key: "agentName", label: "Agent", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.agentName}</Badge> },
                  { key: "entries", label: "Entries", align: "right" },
                  { key: "pendingEntries", label: "Pending", align: "right", render: (r) => r.pendingEntries ? <span className="text-amber-700 font-semibold">{r.pendingEntries}</span> : "—" },
                  { key: "overdueEntries", label: "Overdue", align: "right", render: (r) => r.overdueEntries ? <span className="text-red-600 font-semibold">{r.overdueEntries}</span> : "—" },
                  { key: "premium", label: "Premium", align: "right", mono: true, render: (r) => inr(r.premium) },
                  ...(isOwner ? [{ key: "expected", label: "Expected", align: "right", mono: true, render: (r) => inr(r.expected) }] : []),
                  { key: "received", label: "Received", align: "right", mono: true, render: (r) => <span className="text-emerald-600">{inr(r.received)}</span> },
                  ...(isOwner ? [{ key: "outstanding", label: "Remaining", align: "right", mono: true, render: (r) => <span className={r.outstanding > 0 ? "text-red-600 font-semibold" : ""}>{inr(r.outstanding)}</span> }] : []),
                ]}
                rows={rollup}
              />
            </Card>
          )}

          <Table
            rowKey="entryId"
            onRowClick={isOwner ? setEdit : undefined}
            columns={columns}
            rows={rows}
            empty={view === "all"
              ? "No insurance entries — created automatically when a vehicle is delivered"
              : `No ${view} payouts`}
          />
        </>
      )}

      {edit && <EntryDrawer row={edit} isOwner={isOwner} masters={masters} agents={agents} delivered={delivered}
        onClose={() => setEdit(null)} onSaved={() => { setEdit(null); load(); }} />}
      {receipt && <PayoutReceiptModal rows={outstandingRows} isOwner={isOwner}
        onClose={() => setReceipt(false)} onDone={() => { setReceipt(false); load(); }} />}
    </div>
  );
}

function rateHint(r) {
  const src = {
    "agent-slab": "from the agent's model slab",
    "agent-catch-all": "from the agent's catch-all slab",
    manual: "set manually by the owner",
    "legacy-default": "default rate — no agent slab matched",
  }[r.payoutRateSource];
  return src ? `${(Number(r.payoutRate) * 100).toFixed(1)}% — ${src}` : "";
}

function PayoutReceiptLedger({ agents }) {
  const [rows, setRows] = useState([]);
  const [agentId, setAgentId] = useState("");
  useEffect(() => {
    get("/insurance/receipts", agentId ? { agent_id: agentId } : {}).then(setRows).catch(() => setRows([]));
  }, [agentId]);
  const total = useMemo(() => rows.reduce((s, r) => s + Number(r.amount || 0), 0), [rows]);
  return (
    <div data-testid="insurance-receipt-ledger">
      <div className="flex items-center gap-3 mb-4">
        <Select data-testid="receipt-agent-filter" value={agentId} onChange={(e) => setAgentId(e.target.value)} className="max-w-xs">
          <option value="">All agents</option>
          {agents.map((a) => <option key={a.agentId} value={a.agentId}>{a.agentName}</option>)}
        </Select>
        <span className="text-sm text-ink-soft">{rows.length} receipts · <span className="font-mono font-semibold text-emerald-600">{inr(total)}</span></span>
      </div>
      <Table
        rowKey="receiptId"
        columns={[
          { key: "date", label: "Date", render: (r) => fmtDate(r.date) },
          { key: "insuranceAgentName", label: "Agent", render: (r) => <Badge tone="bg-indigo-50 text-indigo-700 ring-indigo-600/20">{r.insuranceAgentName || "— none —"}</Badge> },
          { key: "customerName", label: "Customer" },
          { key: "policyNumber", label: "Policy", mono: true, render: (r) => r.policyNumber || "—" },
          { key: "entryId", label: "Entry", mono: true },
          { key: "reference", label: "Reference / UTR", mono: true, render: (r) => r.reference || "—" },
          { key: "amount", label: "Amount", align: "right", mono: true, render: (r) => <span className="text-emerald-600 font-semibold">{inr(r.amount)}</span> },
        ]}
        rows={rows}
        empty="No payout receipts recorded yet"
      />
    </div>
  );
}

function PayoutReceiptModal({ rows, isOwner, onClose, onDone }) {
  const [entryId, setEntryId] = useState("");
  const [form, setForm] = useState({ amount: "", date: todayISO(), reference: "" });
  const sel = rows.find((r) => r.entryId === entryId);
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const submit = async () => {
    if (!sel) return toast.error("Select an entry");
    if (!form.amount || +form.amount <= 0) return toast.error("Enter a valid amount");
    try {
      await post(`/insurance/${sel.entryId}/receipt`, { amount: +form.amount, date: form.date, reference: form.reference });
      toast.success("Payout recorded");
      onDone();
    } catch (e) { toast.error(e?.response?.data?.detail || "Failed"); }
  };
  return (
    <div className="fixed inset-0 z-[60] flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink/50 backdrop-blur-sm" onClick={onClose} />
      <Card className="relative w-full max-w-lg p-6 animate-fade-up">
        <h3 className="font-heading text-lg font-bold text-ink mb-1">Record Insurer Payout</h3>
        <p className="text-xs text-ink-soft mb-4">Money actually received from the insurance agent.</p>
        <Field label="Entry (agent · customer · outstanding)">
          <Select data-testid="payout-receipt-select" value={entryId} onChange={(e) => setEntryId(e.target.value)}>
            <option value="">— Select —</option>
            {rows.map((r) => (
              <option key={r.entryId} value={r.entryId}>
                {r.entryId} · {r.insuranceAgentName || "no agent"} · {r.customerName}
                {isOwner ? ` · ${inr(r.payoutOutstanding)}` : ""}
              </option>
            ))}
          </Select>
        </Field>
        {sel && (
          <div className="grid grid-cols-3 gap-3 mt-3">
            <Field label="Amount Received (₹)"><Input data-testid="payout-receipt-amount" type="number" value={form.amount} onChange={set("amount")} placeholder={isOwner ? String(sel.payoutOutstanding) : ""} /></Field>
            <Field label="Date"><Input type="date" value={form.date} onChange={set("date")} /></Field>
            <Field label="Reference / UTR"><Input value={form.reference} onChange={set("reference")} /></Field>
          </div>
        )}
        {sel && isOwner && <p className="text-xs text-ink-soft mt-2">Outstanding: <span className="font-mono font-semibold text-red-600">{inr(sel.payoutOutstanding)}</span></p>}
        <div className="flex justify-end gap-2 mt-5">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="save-payout-receipt-btn" onClick={submit}>Record {isOwner ? "Payout" : "Received"}</Button>
        </div>
      </Card>
    </div>
  );
}

function EntryDrawer({ row, isOwner, masters, agents = [], delivered = [], onClose, onSaved }) {
  const isNew = !row.entryId;
  const defaultAgent = agents.find((a) => a.isDefault);
  const [form, setForm] = useState({
    leadId: row.leadId || "", customerName: row.customerName || "", mobile: row.mobile || "",
    model: row.model || "", variant: row.variant || "", insuranceCompany: row.insuranceCompany || "",
    insuranceAgentId: row.insuranceAgentId || (isNew && defaultAgent ? defaultAgent.agentId : ""),
    policyNumber: row.policyNumber || "", insuranceAmount: row.insuranceAmount || 0,
    payoutRate: row.payoutRateSource === "manual" && row.payoutRate ? Number(row.payoutRate) * 100 : 0,
    receivedPayout: row.receivedPayout || 0,
    policyDate: row.policyDate || todayISO(), insuranceExecutive: row.insuranceExecutive || "", remarks: row.remarks || "",
  });
  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const [rateTouched, setRateTouched] = useState(row.payoutRateSource === "manual");

  // Mirrors backend resolve_insurance_payout_rate: agent slab, then catch-all.
  const slabRate = (agentId, model, variant) => {
    const agent = agents.find((a) => a.agentId === agentId);
    if (!agent) return null;
    const fam = familyOf(model, variant);
    const hit = (agent.slabs || []).find((s) => s.modelFamily === fam)
      || (agent.slabs || []).find((s) => s.modelFamily === "*");
    return hit ? Number(hit.payoutRatePct) : null;
  };
  const autoRate = slabRate(form.insuranceAgentId, form.model, form.variant);
  const effectiveRate = rateTouched && Number(form.payoutRate) > 0
    ? Number(form.payoutRate)
    : (autoRate ?? legacyRate(form.model, form.variant));

  const pickLead = (e) => {
    const id = e.target.value;
    const l = delivered.find((x) => x.leadId === id);
    setForm((f) => ({ ...f, leadId: id,
      customerName: l ? l.customerName : f.customerName, mobile: l ? l.mobile : f.mobile,
      model: l ? l.interestedModel : f.model, variant: l ? l.variant : f.variant,
      insuranceAgentId: l && l.insuranceAgentId ? l.insuranceAgentId : f.insuranceAgentId }));
  };
  const setRate = (e) => { setRateTouched(true); setForm((f) => ({ ...f, payoutRate: e.target.value })); };
  const premium = Number(form.insuranceAmount) || 0;
  const expected = Math.round(premium * (effectiveRate / 100));
  const outstanding = Math.max(0, expected - (Number(form.receivedPayout) || 0));

  const save = async () => {
    if (!form.customerName) return toast.error("Customer name required");
    const body = { ...form, insuranceAmount: +form.insuranceAmount,
      payoutRate: rateTouched ? +form.payoutRate : 0, receivedPayout: +form.receivedPayout };
    try {
      if (isNew) await post("/insurance", body); else await put(`/insurance/${row.entryId}`, body);
      toast.success(isNew ? "Entry added" : "Entry updated"); onSaved();
    } catch (e) { toast.error(e?.response?.data?.detail || "Save failed"); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-xl" title={isNew ? "Add Insurance Entry" : "Insurance Entry"}
      footer={<div className="flex justify-end gap-2"><Button variant="secondary" onClick={onClose}>Cancel</Button><Button data-testid="save-insurance-btn" onClick={save}><Banknote size={15} /> Save</Button></div>}>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Delivered Lead">
          <Select data-testid="ins-lead-select" value={form.leadId} onChange={pickLead}>
            <option value="">— Manual (no lead) —</option>
            {delivered.map((l) => <option key={l.leadId} value={l.leadId}>{l.leadId} · {l.customerName} · {l.interestedModel}</option>)}
          </Select>
        </Field>
        <Field label="Customer Name *"><Input data-testid="ins-customer" value={form.customerName} onChange={set("customerName")} /></Field>
        <Field label="Insurance Agent">
          <Select data-testid="ins-agent-select" value={form.insuranceAgentId} onChange={set("insuranceAgentId")}>
            <option value="">— None —</option>
            {agents.filter((a) => (a.status || "Active").toLowerCase() === "active" || a.agentId === form.insuranceAgentId)
              .map((a) => <option key={a.agentId} value={a.agentId}>{a.agentName}</option>)}
          </Select>
        </Field>
        <Field label="Insurer"><Input value={form.insuranceCompany} onChange={set("insuranceCompany")} /></Field>
        <Field label="Policy Number"><Input value={form.policyNumber} onChange={set("policyNumber")} /></Field>
        <Field label="Premium (₹)"><Input data-testid="ins-premium" type="number" value={form.insuranceAmount} onChange={set("insuranceAmount")} /></Field>
        {isOwner && (
          <Field label="Payout Rate (%) — blank uses the agent slab">
            <Input data-testid="ins-rate" type="number" value={rateTouched ? form.payoutRate : ""}
              placeholder={String(effectiveRate)} onChange={setRate} />
          </Field>
        )}
        <Field label="Received Payout (₹)"><Input type="number" value={form.receivedPayout} onChange={set("receivedPayout")} /></Field>
        <Field label="Policy Date"><Input type="date" value={form.policyDate || ""} onChange={set("policyDate")} /></Field>
        <Field label="Insurance Executive"><Select value={form.insuranceExecutive} onChange={set("insuranceExecutive")}><option value="">—</option>{(masters?.executives || []).map((x) => <option key={x}>{x}</option>)}</Select></Field>
        <Field label="Model"><Input value={form.model} onChange={set("model")} /></Field>
        <div className="col-span-2"><Field label="Remarks"><Input value={form.remarks} onChange={set("remarks")} /></Field></div>
      </div>
      {isOwner && (
        <Card className="p-4 mt-4 bg-cobalt-tint/40 border-cobalt/20">
          <div className="flex items-center gap-2 text-xs text-ink-soft mb-3">
            <ShieldCheck size={14} />
            {rateTouched && Number(form.payoutRate) > 0
              ? `${effectiveRate}% — set manually, overrides the agent slab`
              : autoRate != null
                ? `${effectiveRate}% — from the selected agent's slab`
                : `${effectiveRate}% — default rate, no agent selected`}
          </div>
          <div className="grid grid-cols-3 gap-3 text-center">
            <div><div className="text-[11px] text-ink-faint uppercase">Expected Payout</div><div className="font-mono font-bold text-ink">{inr(expected)}</div></div>
            <div><div className="text-[11px] text-ink-faint uppercase">Received</div><div className="font-mono font-bold text-emerald-600">{inr(form.receivedPayout)}</div></div>
            <div><div className="text-[11px] text-ink-faint uppercase">Outstanding</div><div className="font-mono font-bold text-cobalt">{inr(outstanding)}</div></div>
          </div>
        </Card>
      )}
    </Drawer>
  );
}

// Mirrors commercial.normalize_scheme_model_key for the drawer's live preview.
function familyOf(model, variant) {
  const s = String(model || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  const v = String(variant || "").toLowerCase().replace(/[^a-z0-9]/g, "");
  if (s.includes("storm") || s.includes("strom")) return "storm";
  if (s.includes("turbo") || s.includes("tyrbo")) return "turbo";
  if (s.includes("hirange") || s.includes("highrange")) return "hirange";
  if (s.includes("hicity")) return "hicity";
  if (s.includes("hiload")) return (v === "xr" || v.includes("hicity")) ? "hicity" : "hiload";
  return s;
}

function legacyRate(model, variant) {
  const fam = familyOf(model, variant);
  return (fam === "storm" || fam === "turbo") ? 49 : 36.5;
}
