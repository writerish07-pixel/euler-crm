import React, { useState } from "react";
import { UploadCloud, Download, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "../lib/api";
import { inr } from "../lib/format";
import { Drawer, Button, Card, Badge, Select } from "../components/ui";
import { useAuth } from "../context/AuthContext";

export default function InsuranceMisUpload({ onClose, onDone }) {
  const { isOwner } = useAuth();
  const [file, setFile] = useState(null);
  const [data, setData] = useState(null);
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("upload");
  const [picked, setPicked] = useState({});

  const downloadTemplate = async () => {
    try {
      await downloadFile("/insurance/mis/template", "insurance_agent_mis_template.xlsx");
    } catch {
      toast.error("Could not download template");
    }
  };

  const runPreview = async (f, mp) => {
    const fd = new FormData();
    fd.append("file", f);
    if (mp) fd.append("mapping", JSON.stringify(mp));
    return api.post("/insurance/mis/preview", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    }).then((r) => r.data);
  };

  const onFile = async (f) => {
    if (!f) return;
    setFile(f);
    setBusy(true);
    try {
      const res = await runPreview(f, null);
      setData(res);
      setMapping(res.suggestedMapping || {});
      const next = {};
      (res.matched || []).forEach((r) => { next[r.entryId] = !r.misApproved; });
      setPicked(next);
      setStep("review");
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not read file");
      setFile(null);
    } finally { setBusy(false); }
  };

  const changeMap = async (field, header) => {
    const mp = { ...mapping, [field]: header };
    setMapping(mp);
    if (!file) return;
    setBusy(true);
    try {
      const res = await runPreview(file, mp);
      setData((d) => ({ ...d, ...res, suggestedMapping: d.suggestedMapping }));
      const next = {};
      (res.matched || []).forEach((r) => { next[r.entryId] = !r.misApproved; });
      setPicked(next);
    } catch { /* keep */ } finally { setBusy(false); }
  };

  const selected = (data?.matched || []).filter((r) => picked[r.entryId]);

  const saveMatches = async () => {
    if (!selected.length) return toast.error("Tick the rows to save");
    setBusy(true);
    try {
      const r = await api.post("/insurance/mis/apply", {
        items: selected.map((row) => ({
          entryId: row.entryId,
          misAmount: row.misAmount,
          reference: row.reference,
          policyNumber: row.policyNumber,
        })),
      });
      toast.success(`MIS filled on ${r.data.filled} payout${r.data.filled === 1 ? "" : "s"}`);
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Could not save MIS");
    } finally { setBusy(false); }
  };

  const approveSelected = async () => {
    if (!selected.length) return toast.error("Tick the payouts to approve");
    setBusy(true);
    try {
      const r = await api.post("/insurance/mis/approve", {
        entryIds: selected.map((row) => row.entryId),
        items: selected.map((row) => ({
          entryId: row.entryId,
          misAmount: row.misAmount,
          reference: row.reference,
        })),
      });
      toast.success(`${r.data.approved} payout${r.data.approved === 1 ? "" : "s"} marked as mapped`);
      onDone();
    } catch (e) {
      toast.error(e.response?.data?.detail || "Approve failed");
    } finally { setBusy(false); }
  };

  const toggleAll = (on) => {
    const next = { ...picked };
    (data?.matched || []).forEach((r) => { next[r.entryId] = on && !r.misApproved; });
    setPicked(next);
  };

  return (
    <Drawer open onClose={onClose} width="max-w-5xl" title="Upload agent MIS"
      subtitle="Match the file to payouts already in this app. Mapped means the row is on the MIS — not that money arrived."
      footer={<div className="flex justify-between items-center gap-2">
        <Button variant="ghost" data-testid="mis-template-btn" onClick={downloadTemplate}>
          <Download size={15} /> Download template
        </Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" data-testid="mis-save-matches-btn"
            onClick={saveMatches} disabled={step !== "review" || busy || !selected.length}>
            Save matches
          </Button>
          <Button data-testid="mis-approve-btn" onClick={approveSelected}
            disabled={step !== "review" || busy || !selected.length}>
            {busy ? "Working…" : `Mark ${selected.length} mapped`}
          </Button>
        </div>
      </div>}>
      {step === "upload" && (
        <label data-testid="mis-dropzone"
          className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-line rounded-xl py-12 cursor-pointer hover:border-cobalt hover:bg-cobalt-tint/30 transition-colors">
          <UploadCloud size={32} className="text-ink-faint" />
          <div className="text-sm font-medium text-ink">Drop the agent's MIS (.xlsx or .csv)</div>
          <div className="text-xs text-ink-faint">Chassis is the unique key — we fetch customer, policy and payout from that vehicle</div>
          <input type="file" accept=".xlsx,.xls,.csv" className="hidden"
            onChange={(e) => onFile(e.target.files?.[0])} />
        </label>
      )}

      {step === "review" && data && (
        <div className="space-y-4" data-testid="mis-review">
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
            <Stat k="Matched" v={data.totals?.matched} />
            <Stat k="Not in this MIS" v={data.totals?.unmatchedEntries} tone="text-rose-700" />
            <Stat k="Not in register" v={data.totals?.unmatchedMis} tone="text-amber-700" />
            <Stat k="MIS total" v={inr(data.totals?.misAmount)} />
            {isOwner && <Stat k="Difference" v={inr(data.totals?.difference)}
              tone={Number(data.totals?.difference) ? "text-amber-700" : ""} />}
          </div>

          <Card className="p-3">
            <div className="text-xs font-semibold uppercase tracking-wide text-ink-faint mb-2">Column map</div>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
              {(data.targetFields || []).map((f) => (
                <label key={f.field} className="text-xs text-ink-soft">
                  {f.label}{f.field === "misAmount" ? " *" : ""}
                  <Select className="mt-1" value={mapping[f.field] || ""}
                    onChange={(e) => changeMap(f.field, e.target.value)}>
                    <option value="">— skip —</option>
                    {(data.detectedHeaders || []).map((h) => <option key={h}>{h}</option>)}
                  </Select>
                </label>
              ))}
            </div>
          </Card>

          <div className="flex items-center justify-between">
            <div className="text-sm font-semibold text-ink">Matched payouts</div>
            <div className="flex gap-2 text-xs">
              <button type="button" className="text-cobalt" onClick={() => toggleAll(true)}>Select all</button>
              <button type="button" className="text-ink-faint" onClick={() => toggleAll(false)}>Clear</button>
            </div>
          </div>
          <div className="overflow-x-auto border border-line rounded-lg">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="bg-zinc-50 text-[11px] uppercase tracking-wide text-ink-faint">
                  <th className="px-3 py-2 w-10" />
                  <th className="px-3 py-2">Customer</th>
                  <th className="px-3 py-2">Chassis</th>
                  <th className="px-3 py-2">Policy</th>
                  <th className="px-3 py-2 text-right">MIS</th>
                  {isOwner && <th className="px-3 py-2 text-right">Expected</th>}
                  {isOwner && <th className="px-3 py-2 text-right">Diff</th>}
                  <th className="px-3 py-2">Match</th>
                </tr>
              </thead>
              <tbody>
                {(data.matched || []).map((r) => (
                  <tr key={r.entryId} className="border-t border-zinc-100" data-testid={`mis-row-${r.entryId}`}>
                    <td className="px-3 py-2">
                      <input type="checkbox" data-testid={`mis-check-${r.entryId}`}
                        checked={!!picked[r.entryId]} disabled={!!r.misApproved}
                        onChange={(e) => setPicked((p) => ({ ...p, [r.entryId]: e.target.checked }))} />
                    </td>
                    <td className="px-3 py-2">
                      <div className="font-medium">{r.registerCustomer || r.customerName}</div>
                      <div className="text-[11px] text-ink-faint">{r.entryId}{r.leadId ? ` · ${r.leadId}` : ""}</div>
                    </td>
                    <td className="px-3 py-2 font-mono text-xs">{r.chassisNumber || r.registerChassis || "—"}</td>
                    <td className="px-3 py-2 font-mono text-xs">{r.policyNumber || r.registerPolicy || "—"}</td>
                    <td className="px-3 py-2 text-right font-mono">{inr(r.misAmount)}</td>
                    {isOwner && <td className="px-3 py-2 text-right font-mono">{inr(r.expectedPayout)}</td>}
                    {isOwner && (
                      <td className={`px-3 py-2 text-right font-mono ${Number(r.difference) ? "text-amber-700 font-semibold" : ""}`}>
                        {inr(r.difference)}
                      </td>
                    )}
                    <td className="px-3 py-2">
                      {r.misApproved
                        ? <Badge tone="bg-emerald-50 text-emerald-700 ring-emerald-600/20">Approved</Badge>
                        : <Badge>{r.matchKey}</Badge>}
                    </td>
                  </tr>
                ))}
                {(data.matched || []).length === 0 && (
                  <tr><td colSpan={isOwner ? 8 : 6} className="px-3 py-8 text-center text-ink-faint">No rows matched a payout entry</td></tr>
                )}
              </tbody>
            </table>
          </div>

          {(data.unmatchedEntries || []).length > 0 && (
            <Card className="p-3 bg-rose-50 border-rose-200" data-testid="mis-unmatched-register">
              <div className="flex gap-2 text-sm text-rose-900 mb-2">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                {data.unmatchedEntries.length} register payout{data.unmatchedEntries.length === 1 ? "" : "s"} not on this MIS — send to the agent
              </div>
              <ul className="text-xs text-rose-900 space-y-1">
                {data.unmatchedEntries.slice(0, 20).map((r) => (
                  <li key={r.entryId}>{r.customerName || "—"}
                    {r.chassisNumber ? ` · ${r.chassisNumber}` : ""}
                    {r.policyNumber ? ` · ${r.policyNumber}` : ""}
                    {r.leadId ? ` · ${r.leadId}` : ""}</li>
                ))}
              </ul>
            </Card>
          )}

          {(data.unmatchedMis || []).length > 0 && (
            <Card className="p-3 bg-amber-50 border-amber-200" data-testid="mis-unmatched">
              <div className="flex gap-2 text-sm text-amber-900 mb-2">
                <AlertTriangle size={16} className="shrink-0 mt-0.5" />
                {data.unmatchedMis.length} MIS row{data.unmatchedMis.length === 1 ? "" : "s"} did not match
              </div>
              <ul className="text-xs text-amber-900 space-y-1">
                {data.unmatchedMis.slice(0, 12).map((r, i) => (
                  <li key={i}>Row {r.row}: {r.chassisNumber || r.customerName || r.policyNumber || "—"}
                    {r.registerCustomer ? ` · ${r.registerCustomer}` : ""}{r.leadId ? ` · ${r.leadId}` : ""} · {r.reason}</li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </Drawer>
  );
}

function Stat({ k, v, tone }) {
  return (
    <Card className="p-3">
      <div className="text-[11px] uppercase tracking-wide text-ink-faint">{k}</div>
      <div className={`text-lg font-bold tabular ${tone || "text-ink"}`}>{v ?? "—"}</div>
    </Card>
  );
}
