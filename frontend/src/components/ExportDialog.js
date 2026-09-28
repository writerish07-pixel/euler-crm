import React, { useEffect, useMemo, useState } from "react";
import { Download } from "lucide-react";
import { toast } from "sonner";
import { Button, Field, Input, Modal, Select } from "./ui";
import PeriodBar from "./PeriodBar";
import { downloadFile, get, apiErrorMessage } from "../lib/api";

function tabFromPath(pathname, catalog) {
  const p = String(pathname || "/").replace(/\/$/, "") || "/";
  const map = catalog?.pathToTab || {};
  if (p.startsWith("/oem-claims")) return "oem_claims";
  return map[p] || catalog?.fallbackTab || "leads";
}

function defaultsFor(tab) {
  return (tab?.columns || []).filter((c) => c.default).map((c) => c.key);
}

export default function ExportDialog({ open, onClose, pathname }) {
  const [catalog, setCatalog] = useState(null);
  const [tabKey, setTabKey] = useState("leads");
  const [month, setMonth] = useState("");
  const [year, setYear] = useState("");
  const [status, setStatus] = useState("all");
  const [q, setQ] = useState("");
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [mapped, setMapped] = useState(true);

  useEffect(() => {
    if (!open) return undefined;
    let alive = true;
    get("/export/catalog")
      .then((c) => {
        if (!alive) return;
        setCatalog(c);
        const key = tabFromPath(pathname, c);
        const path = String(pathname || "/").replace(/\/$/, "") || "/";
        const known = !!(c.pathToTab && (c.pathToTab[path] || path.startsWith("/oem-claims")));
        setMapped(known || path === "/leads");
        setTabKey(key);
        const tab = (c.tabs || []).find((t) => t.key === key);
        setPicked(defaultsFor(tab));
        setStatus("all");
        setQ("");
        setMonth("");
        setYear("");
      })
      .catch((e) => toast.error(apiErrorMessage(e, "Could not load export options")));
    return () => { alive = false; };
  }, [open, pathname]);

  const tab = useMemo(
    () => (catalog?.tabs || []).find((t) => t.key === tabKey) || null,
    [catalog, tabKey],
  );

  const onTabChange = (key) => {
    setTabKey(key);
    const next = (catalog?.tabs || []).find((t) => t.key === key);
    setPicked(defaultsFor(next));
    setStatus("all");
  };

  const toggle = (key) => {
    setPicked((prev) => (prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]));
  };

  const selectDefaults = () => setPicked(defaultsFor(tab));
  const selectAll = () => setPicked((tab?.columns || []).map((c) => c.key));

  const download = async () => {
    if (!tab) return;
    if (!picked.length) return toast.error("Pick at least one column");
    setBusy(true);
    try {
      const params = {
        tab: tab.key,
        columns: picked.join(","),
        ...(month ? { month } : {}),
        ...(!month && year ? { year } : {}),
        ...(status && status !== "all" ? { status } : {}),
        ...(q.trim() ? { q: q.trim() } : {}),
      };
      const stamp = new Date().toISOString().slice(0, 10);
      await downloadFile("/export", `euler_${tab.key}_${stamp}.xlsx`, params);
      toast.success(`Exported ${tab.label}`);
      onClose();
    } catch (e) {
      toast.error(apiErrorMessage(e, "Export failed"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={open} onClose={onClose} width="max-w-xl" testid="export-dialog">
      <div className="p-4 sm:p-5 border-b border-line">
        <h3 className="font-heading font-bold text-ink">Export</h3>
        <p className="text-xs text-ink-soft mt-1">
          Downloads the register you are on. Choose period, status, search and columns
          so the file matches what you are looking at — not the whole Lead Register.
        </p>
      </div>
      <div className="p-4 sm:p-5 space-y-4 overflow-y-auto min-h-0">
        {!mapped && (
          <p className="text-xs text-amber-800 bg-amber-50 ring-1 ring-inset ring-amber-200 rounded-lg px-3 py-2"
            data-testid="export-fallback-note">
            This screen has no row list of its own, so the picker opens on the Lead Register.
            Switch the register below, or open that tab and tap Export there.
          </p>
        )}
        <Field label="Register">
          <Select data-testid="export-tab" value={tabKey} onChange={(e) => onTabChange(e.target.value)}>
            {(catalog?.tabs || []).map((t) => (
              <option key={t.key} value={t.key}>{t.label}</option>
            ))}
          </Select>
        </Field>
        {tab?.hasPeriod && (
          <PeriodBar
            month={month}
            year={year}
            onChange={({ month: m, year: y }) => { setMonth(m || ""); setYear(y || ""); }}
          />
        )}
        {tab?.statuses?.length ? (
          <Field label={tab.statusField === "paymentMode" ? "Payment mode" : "Status"}>
            <Select data-testid="export-status" value={status} onChange={(e) => setStatus(e.target.value)}>
              <option value="all">All</option>
              {tab.statuses.map((s) => <option key={s} value={s}>{s}</option>)}
            </Select>
          </Field>
        ) : null}
        {tab?.hasSearch && (
          <Field label="Search (name, id, mobile…)">
            <Input data-testid="export-q" value={q} onChange={(e) => setQ(e.target.value)}
              placeholder="Optional filter" />
          </Field>
        )}
        <div>
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium text-ink-soft">Columns on this tab</span>
            <div className="flex gap-2">
              <button type="button" className="text-[11px] text-cobalt font-semibold" onClick={selectDefaults}
                data-testid="export-cols-default">Shown on screen</button>
              <button type="button" className="text-[11px] text-cobalt font-semibold" onClick={selectAll}
                data-testid="export-cols-all">All fields</button>
            </div>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5 max-h-48 overflow-y-auto pr-1"
            data-testid="export-columns">
            {(tab?.columns || []).map((c) => (
              <label key={c.key} className="flex items-center gap-2 text-sm text-ink">
                <input
                  type="checkbox"
                  data-testid={`export-col-${c.key}`}
                  checked={picked.includes(c.key)}
                  onChange={() => toggle(c.key)}
                />
                {c.label}
              </label>
            ))}
          </div>
        </div>
        <p className="text-[11px] text-ink-faint">
          {month ? `Period ${month}` : year ? `Period ${year}` : "All dates"}
          {status && status !== "all" ? ` · ${status}` : ""}
          {q.trim() ? ` · “${q.trim()}”` : ""}
          {` · ${picked.length} column${picked.length === 1 ? "" : "s"}`}
        </p>
      </div>
      <div className="p-4 sm:p-5 border-t border-line flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onClose}>Cancel</Button>
        <Button type="button" data-testid="export-confirm" onClick={download} disabled={busy || !tab}>
          <Download size={15} />
          {busy ? "Exporting…" : "Download Excel"}
        </Button>
      </div>
    </Modal>
  );
}
