import React, { useState } from "react";
import { RefreshCcw } from "lucide-react";
import { toast } from "sonner";
import { post, apiErrorMessage } from "../lib/api";
import { Button } from "./ui";
import { useAuth } from "../context/AuthContext";

/** Owner-only: pull Coulson list prices into Price Master, then refresh the page. */
export default function OemPriceSyncButton({ onDone, testId = "oem-price-sync" }) {
  const { isOwner } = useAuth();
  const [busy, setBusy] = useState(false);
  if (!isOwner) return null;

  const sync = async () => {
    setBusy(true);
    try {
      const r = await post("/integrations/coulson/sync", {});
      if (r.ok) {
        const added = Number(r.liveModelsAdded || 0);
        const schemes = Number(r.schemesAdded || 0);
        const extra = [
          added ? `${added} new model${added === 1 ? "" : "s"}` : "",
          schemes ? `${schemes} scheme${schemes === 1 ? "" : "s"}` : "",
        ].filter(Boolean).join(" · ");
        toast.success(
          `Price Master updated from OEM · ${r.pricesUpdated || 0} list prices · ${r.inventoryCount || 0} in yard${extra ? ` · ${extra}` : ""}`,
        );
      } else {
        toast.error(r.reason === "not_configured"
          ? "Save the Coulson session in Settings first"
          : "OEM sync did not run");
      }
      if (onDone) onDone(r);
    } catch (e) {
      toast.error(apiErrorMessage(e, "Coulson sync failed"));
    } finally { setBusy(false); }
  };

  return (
    <Button data-testid={testId} onClick={sync} disabled={busy}>
      <RefreshCcw size={15} /> {busy ? "Syncing…" : "Sync from OEM"}
    </Button>
  );
}
