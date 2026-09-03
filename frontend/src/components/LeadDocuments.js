import React, { useEffect, useState } from "react";
import { Camera, FileUp, Download, Trash2, FileText, Image as ImageIcon } from "lucide-react";
import { toast } from "sonner";
import { api, del, get, uploadFile } from "../lib/api";

export const DOC_LABELS = {
  kyc_aadhaar_front: "Aadhaar front",
  kyc_aadhaar_back: "Aadhaar back",
  kyc_pan: "PAN",
  kyc_gst: "GST certificate",
  delivery_insurance: "Insurance copy",
  delivery_rto: "RTO / Registration",
  tally_invoice: "Tally GST invoice",
  refund_cheque: "Refund cheque",
};

const ACCEPT = "image/*,application/pdf";

/** Phone rear camera plus a separate file picker — iOS `capture` forces camera-only. */
export function CameraFilePick({ onFile, disabled, testId }) {
  const takeId = `${testId || "doc"}-camera`;
  const fileId = `${testId || "doc"}-file`;
  const onChange = (e) => {
    const f = e.target.files?.[0];
    e.target.value = "";
    if (f) onFile(f);
  };
  return (
    <div className="flex flex-wrap gap-1.5">
      <input id={takeId} type="file" accept="image/*" capture="environment" className="sr-only" disabled={disabled} onChange={onChange} />
      <input id={fileId} type="file" accept={ACCEPT} className="sr-only" disabled={disabled} onChange={onChange} />
      <label htmlFor={takeId} data-testid={takeId}
        className={`inline-flex items-center gap-1 rounded-lg ring-1 ring-inset ring-line px-2 py-1 text-[11px] font-medium ${disabled ? "opacity-50 pointer-events-none" : "bg-white text-ink hover:bg-zinc-50 cursor-pointer"}`}>
        <Camera size={12} /> Camera
      </label>
      <label htmlFor={fileId} data-testid={fileId}
        className={`inline-flex items-center gap-1 rounded-lg ring-1 ring-inset ring-line px-2 py-1 text-[11px] font-medium ${disabled ? "opacity-50 pointer-events-none" : "bg-white text-ink hover:bg-zinc-50 cursor-pointer"}`}>
        <FileUp size={12} /> File
      </label>
    </div>
  );
}

export async function openDocumentFile(documentId, filename) {
  const res = await api.get(`/documents/${documentId}/file`, { responseType: "blob" });
  const blob = new Blob([res.data], { type: res.headers["content-type"] || "application/octet-stream" });
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename || "document";
  a.target = "_blank";
  a.rel = "noopener";
  a.click();
  setTimeout(() => window.URL.revokeObjectURL(url), 4000);
}

function DocThumb({ doc }) {
  const [url, setUrl] = useState("");
  useEffect(() => {
    if (!doc?.documentId) return undefined;
    const ctype = String(doc.contentType || "");
    if (!ctype.startsWith("image/")) return undefined;
    let revoke = "";
    api.get(`/documents/${doc.documentId}/file`, { responseType: "blob" })
      .then((res) => {
        revoke = window.URL.createObjectURL(res.data);
        setUrl(revoke);
      })
      .catch(() => {});
    return () => { if (revoke) window.URL.revokeObjectURL(revoke); };
  }, [doc?.documentId, doc?.contentType]);
  if (url) return <img src={url} alt={doc.filename || "scan"} className="h-16 w-16 object-cover rounded-md ring-1 ring-line" />;
  return (
    <div className="h-16 w-16 rounded-md bg-zinc-50 ring-1 ring-line grid place-items-center text-ink-faint">
      {(doc.contentType || "").includes("pdf") ? <FileText size={18} /> : <ImageIcon size={18} />}
    </div>
  );
}

export function DocSlot({ kind, doc, onLocalFile, localFile, uploadUrl, canUpload, canDownload = true, onChanged, extraFields }) {
  const [busy, setBusy] = useState(false);
  const label = DOC_LABELS[kind] || kind;
  const save = async (file) => {
    if (onLocalFile) {
      onLocalFile(file);
      return;
    }
    if (!uploadUrl) return;
    setBusy(true);
    try {
      await uploadFile(uploadUrl, file, { kind, ...(extraFields || {}) });
      toast.success(`${label} saved`);
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Upload failed");
    } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!doc?.documentId) return;
    if (!window.confirm(`Remove ${label}?`)) return;
    try {
      await del(`/documents/${doc.documentId}`);
      toast.success("Removed");
      onChanged && onChanged();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Could not remove");
    }
  };
  return (
    <div className="flex items-start gap-3 rounded-lg border border-line bg-white p-2.5" data-testid={`doc-slot-${kind}`}>
      {doc ? <DocThumb doc={doc} /> : (
        <div className="h-16 w-16 rounded-md bg-zinc-50 ring-1 ring-dashed ring-line grid place-items-center text-[10px] text-ink-faint text-center px-1">
          {localFile ? localFile.name : "No file"}
        </div>
      )}
      <div className="min-w-0 flex-1">
        <div className="text-xs font-semibold text-ink">{label}</div>
        <div className="text-[11px] text-ink-faint truncate">{doc?.filename || localFile?.name || "Photo or PDF, max 5 MB"}</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          {canUpload && <CameraFilePick onFile={save} disabled={busy} testId={`doc-${kind}`} />}
          {doc && canDownload && (
            <button type="button" className="inline-flex items-center gap-1 text-[11px] text-cobalt" data-testid={`doc-dl-${kind}`}
              onClick={() => openDocumentFile(doc.documentId, doc.filename).catch(() => toast.error("Download failed"))}>
              <Download size={12} /> Download
            </button>
          )}
          {doc && canUpload && (
            <button type="button" className="inline-flex items-center gap-1 text-[11px] text-red-600" onClick={remove}>
              <Trash2 size={12} /> Remove
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

export function LeadDocsStrip({ leadId, kinds, canUploadKinds = [], title, onChanged, documents, refreshKey }) {
  const [rows, setRows] = useState(documents || []);
  useEffect(() => { if (documents) setRows(documents); }, [documents]);
  useEffect(() => {
    if (!leadId) return undefined;
    let live = true;
    get(`/leads/${leadId}/documents`).then((d) => { if (live) setRows(Array.isArray(d) ? d : []); }).catch(() => { if (live) setRows([]); });
    return () => { live = false; };
  }, [leadId, refreshKey]);
  const byKind = {};
  (rows || []).forEach((d) => { byKind[d.kind] = d; });
  const shown = kinds || Object.keys(DOC_LABELS);
  return (
    <div className="mt-4" data-testid="lead-docs-strip">
      {title && <h4 className="font-heading font-bold text-ink text-sm mb-2">{title}</h4>}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {shown.map((kind) => (
          <DocSlot
            key={kind}
            kind={kind}
            doc={byKind[kind]}
            uploadUrl={leadId ? `/leads/${leadId}/documents` : ""}
            canUpload={canUploadKinds.includes(kind)}
            onChanged={() => {
              get(`/leads/${leadId}/documents`).then(setRows).catch(() => {});
              onChanged && onChanged();
            }}
          />
        ))}
      </div>
    </div>
  );
}

export function LocalKycBlock({ customerType, files, setFiles, gstin, onGstin }) {
  const kinds = customerType === "B2B"
    ? ["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "kyc_gst"]
    : ["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"];
  return (
    <div className="sm:col-span-2 space-y-2" data-testid="kyc-block">
      <div className="text-xs font-semibold text-ink">KYC documents</div>
      <p className="text-[11px] text-ink-soft">Aadhaar front &amp; back and PAN are required. B2B also needs GST. Phone camera uses the rear lens.</p>
      {customerType === "B2B" && (
        <label className="block">
          <span className="block text-xs font-medium text-ink-soft mb-1">GSTIN *</span>
          <input data-testid="lead-gstin" value={gstin} onChange={(e) => onGstin(e.target.value)}
            className="block w-full rounded-lg border-0 py-2 px-3 text-sm ring-1 ring-inset ring-line focus:ring-2 focus:ring-cobalt" />
        </label>
      )}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {kinds.map((kind) => (
          <DocSlot key={kind} kind={kind} localFile={files[kind]} onLocalFile={(f) => setFiles((prev) => ({ ...prev, [kind]: f }))} canUpload />
        ))}
      </div>
    </div>
  );
}

export async function uploadKycFiles(url, files) {
  const kinds = Object.keys(files).filter((k) => files[k]);
  for (const kind of kinds) {
    await uploadFile(url, files[kind], { kind });
  }
}

export function kycReady(customerType, files, gstin) {
  const need = customerType === "B2B"
    ? ["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan", "kyc_gst"]
    : ["kyc_aadhaar_front", "kyc_aadhaar_back", "kyc_pan"];
  if (need.some((k) => !files[k])) return "Attach Aadhaar front, Aadhaar back and PAN" + (customerType === "B2B" ? ", plus GST" : "");
  if (customerType === "B2B" && !String(gstin || "").trim()) return "Enter the GSTIN";
  return "";
}

export function RequestKycPreview({ documents = [] }) {
  if (!documents.length) return <span className="text-[11px] text-rose-700">No KYC yet</span>;
  return (
    <div className="flex flex-wrap gap-1.5">
      {documents.map((d) => (
        <button key={d.documentId} type="button" className="text-left" title={d.filename}
          onClick={() => openDocumentFile(d.documentId, d.filename).catch(() => toast.error("Could not open"))}>
          <DocThumb doc={d} />
          <div className="text-[10px] text-ink-faint truncate w-16">{DOC_LABELS[d.kind] || d.kind}</div>
        </button>
      ))}
    </div>
  );
}

export function RefundChequePick({ leadId, documentId, onUploaded }) {
  const [busy, setBusy] = useState(false);
  const save = async (file) => {
    setBusy(true);
    try {
      const row = await uploadFile(`/leads/${leadId}/documents`, file, { kind: "refund_cheque" });
      toast.success("Cheque scan saved");
      onUploaded(row.documentId);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Cheque upload failed");
    } finally { setBusy(false); }
  };
  return (
    <div data-testid="refund-cheque-pick">
      <div className="text-xs font-medium text-ink-soft mb-1">Cheque photo *</div>
      <CameraFilePick onFile={save} disabled={busy} testId="refund-cheque" />
      {documentId && <div className="text-[11px] text-emerald-700 mt-1">Cheque attached</div>}
    </div>
  );
}
