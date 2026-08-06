import React from "react";
import { X } from "lucide-react";

export const cx = (...a) => a.filter(Boolean).join(" ");

export function Card({ className, children, ...rest }) {
  return (
    <div className={cx("bg-white rounded-xl border border-line shadow-card", className)} {...rest}>
      {children}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions }) {
  return (
    <div className="flex items-start justify-between gap-4 mb-6">
      <div>
        <h1 className="font-heading text-2xl font-extrabold tracking-tight text-ink">{title}</h1>
        {subtitle && <p className="text-sm text-ink-soft mt-1">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}

export function Button({ variant = "primary", className, children, ...rest }) {
  const styles = {
    primary: "bg-cobalt text-white hover:bg-cobalt-hover shadow-sm",
    secondary: "bg-white text-ink ring-1 ring-inset ring-line hover:bg-zinc-50",
    ghost: "text-ink-soft hover:bg-zinc-100 hover:text-ink",
    danger: "bg-red-600 text-white hover:bg-red-700",
  };
  return (
    <button
      className={cx(
        "inline-flex items-center justify-center gap-1.5 rounded-lg px-3.5 py-2 text-sm font-medium transition-colors duration-150 disabled:opacity-50 disabled:pointer-events-none",
        styles[variant],
        className
      )}
      {...rest}
    >
      {children}
    </button>
  );
}

const STATUS_TONES = {
  New: "bg-blue-50 text-blue-700 ring-blue-600/20",
  Contacted: "bg-sky-50 text-sky-700 ring-sky-600/20",
  "Follow-up": "bg-violet-50 text-violet-700 ring-violet-600/20",
  "In Progress": "bg-amber-50 text-amber-700 ring-amber-600/20",
  Booked: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  "Finance Process": "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
  Delivered: "bg-teal-50 text-teal-700 ring-teal-600/20",
  Lost: "bg-red-50 text-red-700 ring-red-600/20",
  Active: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Closed: "bg-zinc-100 text-zinc-600 ring-zinc-500/20",
  Pending: "bg-amber-50 text-amber-700 ring-amber-600/20",
  Approved: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  Submitted: "bg-sky-50 text-sky-700 ring-sky-600/20",
  Received: "bg-teal-50 text-teal-700 ring-teal-600/20",
  Rejected: "bg-red-50 text-red-700 ring-red-600/20",
  Open: "bg-amber-50 text-amber-700 ring-amber-600/20",
  "Not Applicable": "bg-zinc-100 text-zinc-500 ring-zinc-400/20",
};

export function Badge({ children, tone, className }) {
  const t = tone || STATUS_TONES[children] || "bg-zinc-100 text-zinc-700 ring-zinc-500/20";
  return (
    <span className={cx("inline-flex items-center rounded-full px-2 py-0.5 text-xs font-semibold ring-1 ring-inset whitespace-nowrap", t, className)}>
      {children || "—"}
    </span>
  );
}

export function Table({ columns, rows, onRowClick, empty = "No records", rowKey }) {
  return (
    <Card className="overflow-hidden">
      <div className="overflow-x-auto">
        <table className="w-full text-left">
          <thead>
            <tr className="bg-zinc-50/80 border-b border-line">
              {columns.map((c) => (
                <th key={c.key} className={cx("px-4 py-2.5 text-[11px] font-semibold uppercase tracking-wider text-ink-faint whitespace-nowrap", c.align === "right" && "text-right")}>
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-4 py-12 text-center text-sm text-ink-faint">{empty}</td>
              </tr>
            )}
            {rows.map((row, i) => (
              <tr
                key={rowKey ? row[rowKey] : i}
                onClick={onRowClick ? () => onRowClick(row) : undefined}
                data-testid={rowKey ? `row-${row[rowKey]}` : undefined}
                className={cx("border-b border-zinc-100 last:border-0 transition-colors", onRowClick && "cursor-pointer hover:bg-cobalt-tint/50")}
              >
                {columns.map((c) => (
                  <td key={c.key} className={cx("px-4 py-2.5 text-sm text-ink align-middle whitespace-nowrap", c.align === "right" && "text-right tabular", c.mono && "font-mono text-[13px]")}>
                    {c.render ? c.render(row) : row[c.key] ?? "—"}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}

export function Drawer({ open, onClose, title, subtitle, children, width = "max-w-2xl", footer }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50">
      <div className="absolute inset-0 bg-ink/40 backdrop-blur-[2px]" onClick={onClose} data-testid="drawer-overlay" />
      <div className={cx("absolute inset-y-0 right-0 w-full bg-white shadow-drawer flex flex-col animate-drawer-in", width)}>
        <div className="flex items-start justify-between gap-4 px-6 py-4 border-b border-line shrink-0">
          <div>
            <h2 className="font-heading text-lg font-bold text-ink">{title}</h2>
            {subtitle && <p className="text-xs text-ink-soft mt-0.5">{subtitle}</p>}
          </div>
          <button onClick={onClose} data-testid="drawer-close" className="rounded-lg p-1.5 text-ink-faint hover:bg-zinc-100 hover:text-ink transition-colors">
            <X size={18} />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-6 py-5">{children}</div>
        {footer && <div className="border-t border-line px-6 py-3 bg-zinc-50/60 shrink-0">{footer}</div>}
      </div>
    </div>
  );
}

export function Field({ label, children }) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-ink-soft mb-1">{label}</span>
      {children}
    </label>
  );
}

const inputCls = "block w-full rounded-lg border-0 py-2 px-3 text-sm text-ink ring-1 ring-inset ring-line placeholder:text-ink-faint focus:ring-2 focus:ring-inset focus:ring-cobalt transition-shadow bg-white";

export function Input({ className, ...rest }) {
  return <input className={cx(inputCls, className)} {...rest} />;
}

export function Select({ className, children, ...rest }) {
  return (
    <select className={cx(inputCls, "pr-8", className)} {...rest}>
      {children}
    </select>
  );
}

export function StatCard({ label, value, sub, icon: Icon, tone = "text-cobalt" }) {
  return (
    <Card className="p-4 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <span className="text-xs font-medium text-ink-soft">{label}</span>
        {Icon && <Icon size={16} className={tone} />}
      </div>
      <div className="mt-2 font-heading text-2xl font-extrabold text-ink tabular">{value}</div>
      {sub && <div className="mt-1 text-xs text-ink-faint">{sub}</div>}
    </Card>
  );
}

export function Tabs({ tabs, active, onChange }) {
  return (
    <div className="flex gap-1 border-b border-line -mx-6 px-6 mb-5 overflow-x-auto">
      {tabs.map((t) => (
        <button
          key={t.key}
          data-testid={`tab-${t.key}`}
          onClick={() => onChange(t.key)}
          className={cx(
            "px-3 py-2.5 text-sm font-medium border-b-2 -mb-px transition-colors whitespace-nowrap",
            active === t.key ? "border-cobalt text-cobalt" : "border-transparent text-ink-soft hover:text-ink"
          )}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

export function Money({ value, className }) {
  const { inr } = require("../lib/format");
  return <span className={cx("font-mono tabular", className)}>{inr(value)}</span>;
}
