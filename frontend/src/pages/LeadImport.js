import React, { useState } from "react";
import { UploadCloud, Download, CheckCircle2, AlertTriangle } from "lucide-react";
import { toast } from "sonner";
import { api, downloadFile } from "../lib/api";
import { Drawer, Button, Card, Badge, Select } from "../components/ui";

export default function LeadImport({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [data, setData] = useState(null); // {detectedHeaders, targetFields, suggestedMapping, sample, rowCount, validCount, errorCount, errors}
  const [mapping, setMapping] = useState({});
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState("upload"); // upload -> map

  const downloadTemplate = async () => {
    try {
      await downloadFile("/leads/import/template", "euler_lead_upload_template.xlsx");
    } catch {
      toast.error("Could not download template");
    }
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
    try { const res = await runPreview(file, mp); setData((d) => ({ ...d, ...res, suggestedMapping: d.suggestedMapping })); }
    catch { /* keep old */ } finally { setBusy(false); }
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", file); fd.append("mapping", JSON.stringify(mapping));
    try {
      const res = await api.post("/leads/import/commit", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const { created, skipped } = res.data;
      if (created) {
        toast.success(skipped ? `${created} leads imported · ${skipped} skipped` : `${created} leads imported`);
      } else {
        toast.error("No leads imported — fix the listed rows and upload again");
      }
      if (created) onDone();
      else setData((d) => ({ ...d, errors: res.data.errors || d.errors }));
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  const validCount = data?.validCount ?? 0;

  return (
    <Drawer open onClose={onClose} width="max-w-3xl" title="Import Leads" subtitle="Bulk upload from the Euler template (.xlsx) or any spreadsheet (.csv)"
      footer={<div className="flex justify-between items-center">
        <Button variant="ghost" data-testid="download-template-btn" onClick={downloadTemplate}><Download size={15} /> Download template</Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="commit-import-btn" onClick={commit} disabled={step !== "map" || busy || !validCount}>
            {busy ? "Working…" : `Import ${validCount} lead${validCount === 1 ? "" : "s"}`}
          </Button>
        </div>
      </div>}>
      {step === "upload" && (
        <>
          <label data-testid="import-dropzone" className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-line rounded-xl py-12 cursor-pointer hover:border-cobalt hover:bg-cobalt-tint/30 transition-colors">
            <UploadCloud size={32} className="text-ink-faint" />
            <span className="text-sm font-medium text-ink">{busy ? "Reading…" : "Click to choose a .xlsx or .csv file"}</span>
            <span className="text-xs text-ink-faint">Any column names work — you'll match them in the next step</span>
            <input data-testid="import-file-input" type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => onFile(e.target.files[0])} />
          </label>
          <p className="text-xs text-ink-soft mt-4">
            Download the template first — its Lead Source, Executive, Model, Variant, Priority and Status
            columns are dropdowns built from your Settings and Price Master, so uploaded values always match the app.
          </p>
        </>
      )}

      {step === "map" && data && (
        <div>
          <div className="flex items-center gap-2 mb-4">
            <CheckCircle2 size={16} className="text-emerald-500" />
            <span className="text-sm font-medium text-ink">{file?.name}</span>
            <Badge className="ml-auto">{data.detectedHeaders.length} columns · {data.rowCount} rows</Badge>
            <button onClick={() => { setStep("upload"); setData(null); setFile(null); }} className="text-xs text-cobalt hover:underline">Change file</button>
          </div>

          <div className="grid grid-cols-2 gap-3 mb-5">
            <Card className="p-3">
              <div className="text-[11px] uppercase tracking-wide text-ink-faint">Ready to import</div>
              <div className="text-xl font-bold text-emerald-600 tabular">{data.validCount}</div>
            </Card>
            <Card className="p-3">
              <div className="text-[11px] uppercase tracking-wide text-ink-faint">Needs correction</div>
              <div className={`text-xl font-bold tabular ${data.errorCount ? "text-red-600" : "text-ink-faint"}`}>{data.errorCount}</div>
            </Card>
          </div>

          <h4 className="font-heading font-bold text-ink text-sm mb-2">Match your columns</h4>
          <p className="text-xs text-ink-soft mb-3">We auto-matched by name. Adjust any that are wrong. "Customer Name" and "Mobile" are required.</p>
          <Card className="p-4 mb-5">
            <div className="grid grid-cols-2 gap-x-6 gap-y-3">
              {data.targetFields.map((t) => (
                <div key={t.field} className="flex items-center gap-3">
                  <span className="w-40 text-sm text-ink-soft shrink-0">
                    {t.label}{(data.requiredFields || []).includes(t.field) && <span className="text-red-500"> *</span>}
                  </span>
                  <Select data-testid={`map-${t.field}`} value={mapping[t.field] || ""} onChange={(e) => changeMap(t.field, e.target.value)} className="flex-1">
                    <option value="">— skip —</option>
                    {data.detectedHeaders.map((h) => <option key={h} value={h}>{h}</option>)}
                  </Select>
                </div>
              ))}
            </div>
          </Card>

          {(data.errors || []).length > 0 && (
            <>
              <h4 className="font-heading font-bold text-ink text-sm mb-2 flex items-center gap-1.5">
                <AlertTriangle size={15} className="text-red-500" /> Rows that will be skipped
              </h4>
              <p className="text-xs text-ink-soft mb-2">Fix these in your sheet and upload again — the rest still import.</p>
              <Card className="overflow-hidden mb-5" data-testid="import-errors">
                <div className="overflow-x-auto max-h-56">
                  <table className="w-full text-left text-sm">
                    <thead className="bg-zinc-50 sticky top-0">
                      <tr>{["Row", "Customer", "Problem"].map((h) => <th key={h} className="px-3 py-2 text-[11px] uppercase tracking-wide text-ink-faint">{h}</th>)}</tr>
                    </thead>
                    <tbody>
                      {data.errors.map((e) => (
                        <tr key={`${e.row}-${e.mobile}`} className="border-t border-zinc-100 align-top">
                          <td className="px-3 py-1.5 font-mono text-xs">{e.row}</td>
                          <td className="px-3 py-1.5">{e.customerName || "—"}</td>
                          <td className="px-3 py-1.5 text-red-600">{e.errors.join(" · ")}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </Card>
            </>
          )}

          <h4 className="font-heading font-bold text-ink text-sm mb-2">Preview</h4>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto max-h-60">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50 sticky top-0">
                  <tr>{["Customer", "Mobile", "Lead Date", "Source", "Model", "Variant", "Executive", "Status"].map((h) => <th key={h} className="px-3 py-2 text-[11px] uppercase tracking-wide text-ink-faint">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {data.sample.map((r, i) => (
                    <tr key={i} className={`border-t border-zinc-100 ${r.__errors?.length ? "bg-red-50/60" : ""}`}>
                      <td className="px-3 py-1.5 font-medium">{r.customerName || <span className="text-red-400">missing</span>}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.mobile || <span className="text-red-400">missing</span>}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.createdDate || "—"}</td>
                      <td className="px-3 py-1.5">{r.leadSource || "—"}</td>
                      <td className="px-3 py-1.5">{r.interestedModel || "—"}</td>
                      <td className="px-3 py-1.5">{r.variant || "—"}</td>
                      <td className="px-3 py-1.5">{r.executive || "—"}</td>
                      <td className="px-3 py-1.5">{r.currentStatus || "—"}</td>
                    </tr>
                  ))}
                  {data.sample.length === 0 && <tr><td colSpan={8} className="px-3 py-6 text-center text-ink-faint">No valid rows with this mapping</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </Drawer>
  );
}
