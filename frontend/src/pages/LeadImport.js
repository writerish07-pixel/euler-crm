import React, { useState } from "react";
import { UploadCloud, FileSpreadsheet, Download, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { api } from "../lib/api";
import { Drawer, Button, Card, Badge } from "../components/ui";

const TEMPLATE_HEADERS = [
  "Customer Name", "Mobile", "Alternate Mobile", "Village", "City", "Lead Source",
  "Interested Model", "Variant", "Executive", "Current Status", "Priority", "Budget",
  "Remarks", "Finance Required", "Exchange Required",
];

export default function LeadImport({ onClose, onDone }) {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const downloadTemplate = () => {
    const sample = "Ramesh Kumar,9800000000,,Bassi,Jaipur,Walk-in,Storm,,Lokesh,New,Normal,120000,Interested in EMI,No,No";
    const csv = TEMPLATE_HEADERS.join(",") + "\n" + sample + "\n";
    const blob = new Blob([csv], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob); a.download = "euler_lead_import_template.csv"; a.click();
    URL.revokeObjectURL(a.href);
  };

  const onFile = async (f) => {
    if (!f) return;
    setFile(f); setPreview(null); setBusy(true);
    const fd = new FormData(); fd.append("file", f);
    try {
      const res = await api.post("/leads/import/preview", fd, { headers: { "Content-Type": "multipart/form-data" } });
      setPreview(res.data);
    } catch (e) { toast.error(e.response?.data?.detail || "Could not read file"); setFile(null); }
    finally { setBusy(false); }
  };

  const commit = async () => {
    if (!file) return;
    setBusy(true);
    const fd = new FormData(); fd.append("file", file);
    try {
      const res = await api.post("/leads/import/commit", fd, { headers: { "Content-Type": "multipart/form-data" } });
      toast.success(`${res.data.created} leads imported`);
      onDone();
    } catch (e) { toast.error(e.response?.data?.detail || "Import failed"); }
    finally { setBusy(false); }
  };

  return (
    <Drawer open onClose={onClose} width="max-w-2xl" title="Import Leads" subtitle="Bring older leads in from a spreadsheet (.xlsx or .csv)"
      footer={<div className="flex justify-between items-center">
        <Button variant="ghost" onClick={downloadTemplate}><Download size={15} /> Download template</Button>
        <div className="flex gap-2">
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          <Button data-testid="commit-import-btn" onClick={commit} disabled={!preview || busy || preview.rowCount === 0}>
            {busy ? "Importing…" : `Import ${preview?.rowCount || 0} leads`}
          </Button>
        </div>
      </div>}>
      <label data-testid="import-dropzone" className="flex flex-col items-center justify-center gap-2 border-2 border-dashed border-line rounded-xl py-10 cursor-pointer hover:border-cobalt hover:bg-cobalt-tint/30 transition-colors">
        <UploadCloud size={32} className="text-ink-faint" />
        <span className="text-sm font-medium text-ink">{file ? file.name : "Click to choose a .xlsx or .csv file"}</span>
        <span className="text-xs text-ink-faint">Columns are matched by header name — extra columns are ignored</span>
        <input data-testid="import-file-input" type="file" accept=".xlsx,.csv" className="hidden" onChange={(e) => onFile(e.target.files[0])} />
      </label>

      {busy && !preview && <p className="text-sm text-ink-faint mt-4 text-center">Reading file…</p>}

      {preview && (
        <div className="mt-5">
          <div className="flex items-center gap-2 mb-3">
            <CheckCircle2 size={16} className="text-emerald-500" />
            <span className="text-sm font-medium text-ink">{preview.rowCount} valid leads found</span>
            <Badge className="ml-auto">{preview.detectedHeaders.length} columns detected</Badge>
          </div>
          <Card className="overflow-hidden">
            <div className="overflow-x-auto max-h-72">
              <table className="w-full text-left text-sm">
                <thead className="bg-zinc-50 sticky top-0">
                  <tr>{["Customer", "Mobile", "City", "Model", "Executive", "Budget"].map((h) => <th key={h} className="px-3 py-2 text-[11px] uppercase tracking-wide text-ink-faint">{h}</th>)}</tr>
                </thead>
                <tbody>
                  {preview.sample.map((r, i) => (
                    <tr key={i} className="border-t border-zinc-100">
                      <td className="px-3 py-1.5 font-medium">{r.customerName}</td>
                      <td className="px-3 py-1.5 font-mono text-xs">{r.mobile || "—"}</td>
                      <td className="px-3 py-1.5">{r.city || "—"}</td>
                      <td className="px-3 py-1.5">{r.interestedModel || "—"}</td>
                      <td className="px-3 py-1.5">{r.executive || "—"}</td>
                      <td className="px-3 py-1.5 tabular">{r.budget || 0}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
          {preview.rowCount > preview.sample.length && <p className="text-xs text-ink-faint mt-2">Showing first {preview.sample.length} of {preview.rowCount} rows.</p>}
        </div>
      )}
    </Drawer>
  );
}
