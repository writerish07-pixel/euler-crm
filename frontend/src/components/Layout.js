import React, { useState, useEffect } from "react";
import { NavLink, Link } from "react-router-dom";
import {
  LayoutDashboard, Users, ClipboardList, Wallet, Truck, Landmark,
  ShieldCheck, FileText, Percent, Trophy, Tag, ReceiptText,
  Coins, Activity, Search, Zap, Settings as SettingsIcon, LogOut, Download, TrendingUp,
  BarChart3, ShieldAlert, PieChart, ScrollText,
} from "lucide-react";
import { toast } from "sonner";
import { cx, Button } from "./ui";
import { useAuth } from "../context/AuthContext";
import { downloadFile, get } from "../lib/api";

const NAV = [
  { section: "Overview", items: [{ to: "/", label: "Dashboard", icon: LayoutDashboard, end: true }] },
  { section: "Sales Pipeline", items: [
    { to: "/leads", label: "Lead Register", icon: Users },
    { to: "/bookings", label: "Bookings", icon: ClipboardList },
    { to: "/quotations", label: "Quotations", icon: FileText },
    { to: "/activities", label: "Activity Log", icon: Activity },
  ]},
  { section: "Money", items: [
    { to: "/payments", label: "Payment Ledger", icon: Wallet },
    { to: "/finance", label: "Finance Register", icon: Landmark },
    { to: "/insurance", label: "Insurance Payouts", icon: ShieldCheck },
    { to: "/insurance-report", label: "Payout Report", icon: TrendingUp, ownerOnly: true },
  ]},
  { section: "Fulfilment", items: [{ to: "/deliveries", label: "Delivery Tracker", icon: Truck }] },
  { section: "OEM & Commercial", items: [
    { to: "/claims", label: "OEM Claims", icon: ReceiptText },
    { to: "/scheme-master", label: "Scheme Master", icon: Percent },
    { to: "/incentive-master", label: "Incentive Master", icon: Trophy },
    { to: "/dealer-earnings", label: "Dealer Earnings", icon: Coins, ownerOnly: true },
    { to: "/earnings-report", label: "Earnings Report", icon: TrendingUp, ownerOnly: true },
  ]},
  { section: "Owner Reports", ownerOnly: true, items: [
    { to: "/owner-commercial", label: "Owner Commercial", icon: BarChart3, ownerOnly: true },
    { to: "/oem-claim-dashboard", label: "OEM Claim Dashboard", icon: PieChart, ownerOnly: true },
    { to: "/claim-exceptions", label: "Claim Exceptions", icon: ShieldAlert, ownerOnly: true },
    { to: "/audit-log", label: "Audit Trail", icon: ScrollText, ownerOnly: true },
    { to: "/erp-audit", label: "ERP Production Audit", icon: ShieldCheck, ownerOnly: true },
  ]},
  { section: "Catalogue & Admin", items: [
    { to: "/price-master", label: "Price Master", icon: Tag },
    { to: "/settings", label: "Settings", icon: SettingsIcon },
  ]},
];

function Sidebar({ isOwner }) {
  return (
    <aside className="w-64 fixed inset-y-0 left-0 z-40 flex flex-col border-r border-line bg-white">
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line shrink-0">
        <div className="h-9 w-9 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={20} className="text-white" fill="white" /></div>
        <div>
          <div className="font-heading font-extrabold text-ink leading-none tracking-tight">Euler CRM</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-faint mt-0.5">EV Dealership</div>
        </div>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5">
        {NAV.map((group) => {
          const items = group.items.filter((i) => !i.ownerOnly || isOwner);
          if (!items.length) return null;
          return (
            <div key={group.section}>
              <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">{group.section}</div>
              <div className="space-y-0.5">
                {items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                    className={({ isActive }) => cx("group flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "bg-cobalt-tint text-cobalt" : "text-ink-soft hover:bg-zinc-100 hover:text-ink")}>
                    <item.icon size={17} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                    {item.ownerOnly && <span className="ml-auto text-[9px] font-bold uppercase text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Owner</span>}
                  </NavLink>
                ))}
              </div>
            </div>
          );
        })}
      </nav>
      <div className="px-5 py-3 border-t border-line text-[11px] text-ink-faint shrink-0"><span className="font-mono">v2.2</span> · Full-stack</div>
    </aside>
  );
}

function SyncBadge() {
  const [s, setS] = useState(null);
  useEffect(() => {
    let live = true;
    const load = () => get("/integrations/gsheets").then((d) => { if (live) setS(d); }).catch(() => {});
    load();
    const t = setInterval(load, 60000);
    return () => { live = false; clearInterval(t); };
  }, []);
  if (!s) return null;
  const failed = s.enabled && s.health?.lastWriteOk === false;
  let tone, dot, label, title;
  if (s.envSafety?.writeBlocked) {
    tone = "bg-sky-50 text-sky-700 ring-sky-600/20"; dot = "bg-sky-500"; label = "Preview · Writes Blocked";
    title = s.envSafety.blockReason || "Preview is isolated from the production Google Sheet — writes are blocked by design.";
  } else if (failed) {
    tone = "bg-red-50 text-red-700 ring-red-600/20"; dot = "bg-red-500"; label = "Sync Error";
    title = `Last sheet write failed: ${s.health?.lastError || "unknown"}`;
  } else if (s.enabled && s.canWrite) {
    tone = "bg-emerald-50 text-emerald-700 ring-emerald-600/20"; dot = "bg-emerald-500 animate-pulse"; label = "Sheet Synced";
    title = s.health?.lastWriteAt ? `Last write ${new Date(s.health.lastWriteAt).toLocaleString("en-IN")}` : "Connected — writes flow to your Google Sheet";
  } else {
    tone = "bg-amber-50 text-amber-700 ring-amber-600/20"; dot = "bg-amber-500"; label = "Sync Off";
    title = s.reason || "Google Sheet sync not enabled";
  }
  return (
    <div data-testid="sync-badge" title={title} className={cx("flex items-center gap-2 rounded-full px-3 py-1.5 ring-1 ring-inset", tone)}>
      <span className={cx("h-1.5 w-1.5 rounded-full", dot)} />
      <span className="text-xs font-medium">{label}</span>
    </div>
  );
}

function Topbar() {
  const { user, logout } = useAuth();
  const [menu, setMenu] = useState(false);
  const [dl, setDl] = useState(false);
  const exportXlsx = async () => {
    setDl(true);
    try { await downloadFile("/export", `euler_crm_export_${new Date().toISOString().slice(0, 10)}.xlsx`); toast.success("Export downloaded"); }
    catch { toast.error("Export failed"); } finally { setDl(false); }
  };
  const initials = (user?.name || user?.email || "U").slice(0, 2).toUpperCase();
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-4 border-b border-line bg-white/80 backdrop-blur px-6">
      <div className="relative flex-1 max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint" />
        <input placeholder="Search…" className="w-full rounded-lg bg-zinc-100 border-0 py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint focus:ring-2 focus:ring-cobalt focus:bg-white transition-all" />
      </div>
      <div className="ml-auto flex items-center gap-3">
        <Button variant="secondary" data-testid="export-btn" onClick={exportXlsx} disabled={dl}><Download size={15} /> {dl ? "Exporting…" : "Export"}</Button>
        <SyncBadge />
        <div className="relative">
          <button data-testid="user-menu" onClick={() => setMenu((m) => !m)} className="h-9 w-9 rounded-full bg-ink flex items-center justify-center text-white text-sm font-bold font-heading">{initials}</button>
          {menu && (
            <div className="absolute right-0 mt-2 w-52 bg-white rounded-xl border border-line shadow-drawer py-1.5 z-50">
              <div className="px-3 py-2 border-b border-line">
                <div className="text-sm font-semibold text-ink truncate">{user?.name || "User"}</div>
                <div className="text-xs text-ink-faint truncate">{user?.email}</div>
                <div className="text-[10px] uppercase font-bold text-cobalt mt-1">{user?.role}</div>
              </div>
              <Link to="/settings" data-testid="change-password-menu" onClick={() => setMenu(false)}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-ink hover:bg-zinc-50 transition-colors">
                Change password
              </Link>
              <button data-testid="logout-btn" onClick={logout} className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors"><LogOut size={15} /> Sign out</button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}

export default function Layout({ children }) {
  const { isOwner } = useAuth();
  return (
    <div className="min-h-screen bg-app">
      <Sidebar isOwner={isOwner} />
      <div className="ml-64 flex flex-col min-h-screen">
        <Topbar />
        <main className="flex-1 p-6 lg:p-8 animate-fade-up">{children}</main>
      </div>
    </div>
  );
}
