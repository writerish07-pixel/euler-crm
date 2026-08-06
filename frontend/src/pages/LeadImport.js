import React, { useState } from "react";
import { UploadCloud, Download, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Drawer, Button, Card, Badge, Field, Select } from "../components/ui";

const TEMPLATE_HEADERS = [
  "Customer Name", "Mobile", "Alternate Mobile", "Village", "City", "Lead Source",
  "Interested Model", "Variant", "Executive", "Current Status", "Priority", "Budget",
  "Remarks", "Finance Required", "Exchange Required",
];

export default function LeadImport({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [data, setData] = useState(null); // {detectedHeaders, targetFields, suggestedMapping, sample, rowCount}
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("upload"); // upload -> map

  const downloadTemplate = () => {
    const sample = "Ramesh Kumar,9800000000,,Bassi,Jaipur,Walk-in,Storm,,Lokesh,New,Normal,120000,Interested in EMI,No,No";
    const csv = TEMPLATE_HEADERS.join(",") + "\n" + sample + "\n";
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "euler_lead_import_template.csv"; a.click();
    URL.revokeObjectURL(a.href);
  };

  const runPreview = async (f, mp) => {
    const fd = new FormData(); fd.append("file", f);
    if (mp) fd.append("mapping", JSON.stringify(mp));
    return api.post("/leads/import/preview", fd, { headers: { "Content-Type": "multipart/form-data" } }).then((r) => r.data);
  };

  const onFile = async (f) => {
    if (!f) return;
    setFile(f); setBusy(true);
    try {
      const res = await runPreview(f, null);
      setData(res); setMapping(res.suggestedMapping || {}); setStep("map");
    } catch (e) { toast.error(e.response?.data?.detail || "Could not read file"); setFile(null); }
    finally { setBusy(false); }
  };

  const changeMap = async (field, header) => {
    const mp = { ...mapping, [field]: header };
    setMapping(mp);
    setBusy(true);
    try { const res = await runPreview(file, mp); setData((d) => ({ ...d, sample: res.sample, rowCount: res.rowCount })); }
    catch { /* keep old */ } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", file); fd.append("mapping", JSON.stringify(mapping));
    try {
      const res = await api.post("/leads/import/commit", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${res.data.created} leads imported`);
      onDone();
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-3xl" title="Import Leads" subtitle="Bring older leads in from any spreadsheet (.xlsx or .csv)"
      footer={<div className="flex justify-between items-center">
        <Button variant="ghost" onClick={downloadTemplate}><Download size={15} /> Download template</Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="commit-import-btn" onClick={commit} disabled={step !== "map" || busy || !data?.rowCount}>
            {busy ? "Working…" : `Import ${data?.rowCount || 0} leads`}
          </Button>
        </div>
      </div>}>
      {step === "upload" && (
        <label data-testid="import-dropzone" className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-line rounded-xl py-12 cursor-pointer hover:border-cobalt hover:bg-cobalt-tint/30 transition-colors">
          <UploadCloud size={32} className="text-ink-faint" />
          <span className="text-sm font-medium text-ink">{busy ? "Reading…" : "Click to choose a .xlsx or .csv file"}</span>
          <span className="text-xs text-ink-faint">Any column names work — you'll match them in the next step</span>
          <input data-testid="import-file-input" type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => onFile(e.target.files[0])} />
        </label>
      )}

      {step === "map" && data && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 size={16} className="text-emerald-500" />
            <span className="text-sm font-medium text-ink">{file?.name}</span>
            <Badge className="ml-auto">{data.detectedHeaders.length} columns · {data.rowCount} rows</Badge>
            <button onClick={() => { setStep("upload"); setData(null); setFile(null); }} className="text-xs text-cobalt hover:underline">Change file</button>
          </div>

          <h4 className="font-heading font-bold text-ink text-sm mb-2">Match your columns</h4>
          <p className="text-xs text-ink-soft mb-3">We auto-matched by name. Adjust any that are wrong. "Customer Name" is required.</p>
          <Card className="p-4 mb-5">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              {data.targetFields.map((t) => (
                <div key={t.field} className="flex items-center gap-3">
                  <span className="w-40 text-sm text-ink-soft shrink-0">{t.label}{t.field === "customerName" && <span className="text-red-500"> *</span>}</span>
                  <Select data-testid={`map-${t.field}`} value={mapping[t.field] || ""} onChange={(e) => changeMap(t.field, e.target.value)} className="flex-1">
                    <option value="">— skip —</option>
                    {data.detectedHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                  </Select>
                </div>
              ))}
            </div>
          </Card>

          <h4 className="font-heading font-bold text-ink text-sm mb-2">Preview</h4>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto max-h-60">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50 sticky top-0">
                  <tr>{["Customer", "Mobile", "City", "Model", "Executive", "Budget"].map((h) => <th key={h} className="px-3 py-2 text-[11px] uppercase tracking-wide text-ink-faint">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {data.sample.map((r, i) => (
                    <tr key={i} className="border-t border-zinc-100">
                      <td className="px-3 py-1.5 font-medium">{r.customerName || <span className="text-red-400">missing</span>}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.mobile || "—"}</td>
                      <td className="px-3 py-1.5">{r.city || "—"}</td>
                      <td className="px-3 py-1.5">{r.interestedModel || "—"}</td>
                      <td className="px-3 py-1.5">{r.executive || "—"}</td>
                      <td className="px-3 py-1.5 tabular">{r.budget || 0}</td>
                    </tr>
                  ))}
                  {data.sample.length === 0 && <tr><td colSpan={6} className="px-3 py-6 text-center text-ink-faint">No valid rows with this mapping</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </Drawer>
  );
}
