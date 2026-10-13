import React, { useEffect, useState } from "react";
import { ShieldCheck, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { get, post, apiErrorMessage } from "../lib/api";
import { Badge, Button } from "./ui";
import { LeadDocsStrip } from "./LeadDocuments";

export default function TallyPackCheck({ leadId, canUpload = false, canCheck, documents, onChanged, showUpload = true }) {
  const allowCheck = canCheck ?? canUpload;
  const [row, setRow] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = () => {
    if (!leadId) return;
    Promise.resolve(get(`/leads/${leadId}/tally-pack`)).then(setRow).catch(() => setRow(null));
  };
  useEffect(() => { load(); }, [leadId]);

  const run = async () => {
    setBusy(true);
    try {
      const next = await post(`/leads/${leadId}/tally-pack/check`, {});
      setRow(next);
      if (next.ok) toast.success("Tally pack matches the file");
      else toast.error(`${next.errorCount || next.flagCount || 0} Tally pack gap(s)`);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Could not check the Tally pack"));
    } finally { setBusy(false); }
  };

  const flags = row?.flags || [];
  return (
    <div className="mt-4" data-testid="tally-pack-check">
      {showUpload && (
        <LeadDocsStrip
          leadId={leadId}
          kinds={["tally_invoice"]}
          canUploadKinds={canUpload ? ["tally_invoice"] : []}
          title="Tally pack (invoice + ledger + receipts ZIP)"
          documents={documents}
          onChanged={() => { load(); onChanged && onChanged(); }}
        />
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2">
        {allowCheck && (
          <Button data-testid="tally-pack-check-btn" className="!py-1.5 !px-2.5 text-xs"
            onClick={run} disabled={busy}>
            <ShieldCheck size={14} /> {busy ? "Checking…" : "Check Tally pack"}
          </Button>
        )}
        {row?.ok === true && (
          <Badge tone="bg-emerald-50 text-emerald-800 ring-emerald-600/20">Pack matches</Badge>
        )}
        {row?.ok === false && (
          <Badge tone="bg-amber-50 text-amber-900 ring-amber-600/20">
            {row.errorCount || flags.length} gap{(row.errorCount || flags.length) === 1 ? "" : "s"}
          </Badge>
        )}
        {row?.checkedAt && (
          <span className="text-[11px] text-ink-faint">Last check {String(row.checkedAt).slice(0, 16).replace("T", " ")}</span>
        )}
      </div>
      {flags.length > 0 && (
        <div className="mt-2 space-y-1" data-testid="tally-pack-flags">
          {flags.map((f) => (
            <div key={f.code + f.message} className="flex items-start gap-1.5 text-xs text-amber-900">
              <AlertCircle size={12} className="mt-0.5 shrink-0" />
              <span>{f.message}</span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
