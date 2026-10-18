import React, { useState } from "react";
import { inr } from "../lib/format";
import { LeadDocsStrip } from "./LeadDocuments";
import TallyPackCheck from "./TallyPackCheck";

function unitLabel(u, i = 0) {
  const sno = u?.sno || i + 1;
  return `Unit ${sno}${u?.model ? ` · ${u.model}` : ""}`;
}

export function TallyInvoiceLinesTable({ lines, total, title }) {
  return (
    <div className="mb-3">
      {title ? <h2 className="text-[11px] font-semibold uppercase tracking-wide text-ink-soft mt-4 mb-1">{title}</h2> : null}
      <table className="w-full text-sm">
        <tbody>
          {(lines || []).map((ln) => (
            <tr key={ln.code + ln.label} className={ln.code === "taxableValue" ? "font-semibold" : ""}>
              <td>{ln.label}{ln.fundHint ? <span className="text-ink-faint text-xs ml-1">({ln.fundHint})</span> : null}</td>
              <td className="text-right font-mono num">{inr(ln.amount)}</td>
            </tr>
          ))}
          <tr className="font-semibold">
            <td>Tally GST invoice</td>
            <td className="text-right font-mono num">{inr(total)}</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}

export function TallyPackInvoiceSections({ summary }) {
  const units = summary?.units || [];
  const t = summary?.totals || {};
  if (units.length > 1) {
    return (
      <div data-testid="tally-invoice-per-unit">
        {units.map((u) => (
          <TallyInvoiceLinesTable
            key={u.sno}
            title={`A. Unit ${u.sno} Tally GST invoice${u.chassisNumber ? ` · ${u.chassisNumber}` : ""}${u.invoiceNumber ? ` · ${u.invoiceNumber}` : ""}`}
            lines={u.tallyInvoiceLines}
            total={u.tallyBillTotal}
          />
        ))}
        <p className="text-sm font-semibold flex justify-between mt-1">
          <span>Pack Tally GST total</span>
          <span className="font-mono num">{inr(t.tallyBillTotal)}</span>
        </p>
      </div>
    );
  }
  return (
    <TallyInvoiceLinesTable
      title="A. Tally GST invoice (vehicle without GST → discount → GST)"
      lines={summary?.tallyInvoiceLines}
      total={t.tallyBillTotal ?? t.netVehicleInclGst}
    />
  );
}

export default function TallyUnitBooks({
  leadId, units = [], canUpload = false, documents, onChanged, showCheck = true,
}) {
  const pack = (units || []).length > 1;
  const [ledSnos, setLedSnos] = useState(() => (pack ? [units[0]?.sno || 1] : []));
  const [allocation, setAllocation] = useState("separate");
  const selected = pack ? ledSnos : [];
  const ledgerSnos = allocation === "separate" && selected.length !== 1
    ? selected.slice(0, 1)
    : selected;

  return (
    <div data-testid="tally-unit-books">
      {pack ? (
        <>
          <p className="text-xs text-ink-soft mt-3">
            Each unit is its own Tally GST invoice. Upload one scan per unit. Ledger can club selected units or stay one-per-unit.
          </p>
          {units.map((u, i) => (
            <LeadDocsStrip
              key={u.sno || i + 1}
              leadId={leadId}
              kinds={["tally_invoice"]}
              canUploadKinds={canUpload ? ["tally_invoice"] : []}
              title={`${unitLabel(u, i)} · GST invoice ${u.tallyBillTotal != null ? `· ${inr(u.tallyBillTotal)}` : ""}`}
              documents={documents}
              unitSno={u.sno || i + 1}
              onChanged={onChanged}
            />
          ))}
          <div className="mt-3" data-testid="tally-ledger-picker">
            <div className="text-[10px] uppercase tracking-wide text-ink-faint mb-1">Tally customer ledger</div>
            <div className="flex flex-wrap gap-2 mb-2">
              {units.map((u, i) => {
                const sno = u.sno || i + 1;
                const checked = ledSnos.includes(sno);
                return (
                  <label key={sno} className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] ring-1 ring-inset ${checked ? "bg-cobalt-tint text-ink ring-cobalt/30" : "bg-white text-ink-soft ring-line"}`}>
                    <input type="checkbox" data-testid={`tally-ledger-unit-${sno}`} checked={checked}
                      onChange={() => setLedSnos((cur) => (cur.includes(sno) ? cur.filter((n) => n !== sno) : [...cur, sno].sort((a, b) => a - b)))} />
                    {unitLabel(u, i)}
                  </label>
                );
              })}
            </div>
            <div className="flex flex-wrap gap-4 text-xs mb-1">
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" name="tally-led-alloc" value="club" checked={allocation === "club"}
                  onChange={() => setAllocation("club")} />
                Combine across selected units
              </label>
              <label className="inline-flex items-center gap-1.5">
                <input type="radio" name="tally-led-alloc" value="separate" checked={allocation === "separate"}
                  onChange={() => setAllocation("separate")} />
                Separate — one unit
              </label>
            </div>
            <p className="text-[11px] text-ink-faint">
              {allocation === "separate"
                ? "The ledger posts only to the ticked unit."
                : "One customer ledger covering the selected units’ Tally GST totals."}
            </p>
            {ledgerSnos.length > 0 && (
              <LeadDocsStrip
                leadId={leadId}
                kinds={["tally_ledger"]}
                canUploadKinds={canUpload ? ["tally_ledger"] : []}
                title={allocation === "separate" || ledgerSnos.length === 1
                  ? `Ledger · Unit ${ledgerSnos[0]}`
                  : `Ledger · Units ${ledgerSnos.join("+")}`}
                documents={documents}
                unitSno={ledgerSnos.length === 1 ? ledgerSnos[0] : undefined}
                unitSnos={ledgerSnos}
                onChanged={onChanged}
              />
            )}
          </div>
        </>
      ) : (
        <LeadDocsStrip
          leadId={leadId}
          kinds={["tally_invoice", "tally_ledger"]}
          canUploadKinds={canUpload ? ["tally_invoice", "tally_ledger"] : []}
          title="Tally pack (invoice + ledger)"
          documents={documents}
          onChanged={onChanged}
        />
      )}
      {showCheck && (
        <TallyPackCheck leadId={leadId} canUpload={canUpload} showUpload={false} documents={documents} onChanged={onChanged} />
      )}
    </div>
  );
}
