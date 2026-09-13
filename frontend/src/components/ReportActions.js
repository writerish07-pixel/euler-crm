import React, { useState } from "react";
import { RefreshCcw, RotateCcw } from "lucide-react";
import { toast } from "sonner";
import { post, apiErrorMessage } from "../lib/api";
import { Button } from "./ui";
import { useAuth } from "../context/AuthContext";

/** Refresh always reloads. Rebuild recomputes commercial leads, then reloads. */
export default function ReportActions({
  onRefresh,
  showRebuild = false,
  refreshTestId = "report-refresh-btn",
  rebuildTestId = "report-rebuild-btn",
}) {
  const { isOwner } = useAuth();
  const [refreshing, setRefreshing] = useState(false);
  const [rebuilding, setRebuilding] = useState(false);
  const busy = refreshing || rebuilding;

  const refresh = async () => {
    if (!onRefresh) return;
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      setRefreshing(false);
    }
  };

  const rebuild = async () => {
    setRebuilding(true);
    try {
      const r = await post("/reports/rebuild", {});
      const n = r.recomputed || 0;
      toast.success(n ? `Rebuilt ${n} deal${n === 1 ? "" : "s"}` : "Rebuild finished");
      if (r.failed) toast.error(`${r.failed} deal${r.failed === 1 ? "" : "s"} failed to rebuild`);
      if (onRefresh) await onRefresh();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Rebuild failed"));
    } finally {
      setRebuilding(false);
    }
  };

  return (
    <div className="flex flex-wrap gap-2" data-testid="report-actions">
      <Button type="button" variant="secondary" data-testid={refreshTestId}
        onClick={refresh} disabled={busy || !onRefresh}>
        <RefreshCcw size={15} className={refreshing ? "animate-spin" : ""} />
        {refreshing ? "Refreshing…" : "Refresh"}
      </Button>
      {showRebuild && isOwner && (
        <Button type="button" variant="secondary" data-testid={rebuildTestId}
          onClick={rebuild} disabled={busy}>
          <RotateCcw size={15} className={rebuilding ? "animate-spin" : ""} />
          {rebuilding ? "Rebuilding…" : "Rebuild"}
        </Button>
      )}
    </div>
  );
}
