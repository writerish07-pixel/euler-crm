import React, { useState, useEffect } from "react";
import { NavLink, Link, useLocation } from "react-router-dom";
import {
  LayoutDashboard, Users, ClipboardList, Wallet, Truck, Landmark,
  ShieldCheck, FileText, Percent, Trophy, Tag, ReceiptText,
  Coins, Activity, Search, Zap, Settings as SettingsIcon, LogOut, Download, TrendingUp,
  BarChart3, ShieldAlert, PieChart, ScrollText, Calculator, Map, Menu, X, Handshake, UserCog,
  MessageCircle, SlidersHorizontal, Ban, Landmark as LandmarkIcon, UserCheck, Warehouse, Bell,
  FileCheck, Scale,
} from "lucide-react";
import { toast } from "sonner";
import { cx, Button } from "./ui";
import { useAuth } from "../context/AuthContext";
import ConnectionBar from "./ConnectionBar";
import { downloadFile, get } from "../lib/api";

const NAV = [
  { section: "Overview", items: [
    { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, salesOnly: true },
    { to: "/gm", label: "Sales GM Dashboard", icon: BarChart3, ownerOnly: true },
    { to: "/field", label: "Field Dashboard", icon: Map, fieldHome: true },
    { to: "/accounts", label: "Accounts Dashboard", icon: Calculator, accountsHome: true },
  ]},
  { section: "Sales Pipeline", pipeline: true, items: [
    { to: "/leads", label: "Lead Register", icon: Users },
    { to: "/approvals", label: "Approvals", icon: Bell, salesOnly: true, approvals: true },
    { to: "/bookings", label: "Bookings", icon: ClipboardList },
    { to: "/quotations", label: "Quotations", icon: FileText, salesOnly: true },
    { to: "/activities", label: "Activity Log", icon: Activity, salesOnly: true },
    { to: "/whatsapp", label: "WhatsApp", icon: MessageCircle, salesOnly: true },
    { to: "/cancellations", label: "Cancellations", icon: Ban },
    { to: "/allocation", label: "Lead Allocation", icon: UserCheck, dealDesk: true },
  ]},
  { section: "Money", items: [
    { to: "/payments", label: "Payment Ledger", icon: Wallet, moneyDesk: true },
    { to: "/finance", label: "Finance Register", icon: Landmark, financeView: true },
    { to: "/oem-finance", label: "OEM Finance View", icon: LandmarkIcon, ownerOnly: true },
    { to: "/insurance", label: "Insurance Payouts", icon: ShieldCheck, moneyDesk: true },
    { to: "/insurance-agents", label: "Insurance Agents", icon: Handshake, ownerOnly: true },
    { to: "/insurance-report", label: "Payout Report", icon: TrendingUp, ownerOnly: true },
  ]},
  { section: "Fulfilment", items: [{ to: "/deliveries", label: "Delivery Tracker", icon: Truck }] },
  { section: "OEM & Commercial", items: [
    // Two different registers, deliberately named apart: the first is the dealer's
    // own scheme entitlement, the second is Euler's claim workflow mirrored in.
    { to: "/claims", label: "Scheme Claim Register", icon: ReceiptText, moneyDesk: true },
    { to: "/oem-claims", label: "OEM Claim Settlements", icon: FileCheck, moneyDesk: true },
    { to: "/scheme-master", label: "Scheme Master", icon: Percent, salesOnly: true },
    { to: "/incentive-master", label: "Incentive Master", icon: Trophy, ownerOnly: true },
    { to: "/executive-incentive", label: "Executive Incentive", icon: Trophy, ownerOnly: true },
    { to: "/dealer-earnings", label: "Dealer Earnings", icon: Coins, ownerOnly: true },
    { to: "/earnings-report", label: "Earnings Report", icon: TrendingUp, ownerOnly: true },
  ]},
  { section: "Owner Reports", ownerOnly: true, items: [
    { to: "/owner-commercial", label: "Owner Commercial", icon: BarChart3, ownerOnly: true },
    { to: "/oem-claim-dashboard", label: "OEM Claim Dashboard", icon: PieChart, ownerOnly: true },
    { to: "/claim-exceptions", label: "Claim Exceptions", icon: ShieldAlert, ownerOnly: true },
    { to: "/claim-reconciliation", label: "Claim Reconciliation", icon: Scale, ownerOnly: true },
    { to: "/audit-log", label: "Audit Trail", icon: ScrollText, ownerOnly: true },
    { to: "/erp-audit", label: "ERP Production Audit", icon: ShieldCheck, ownerOnly: true },
  ]},
  { section: "Catalogue & Admin", items: [
    { to: "/price-list", label: "Price List", icon: Tag, salesOnly: true },
    { to: "/inventory", label: "Yard Inventory", icon: Warehouse },
    { to: "/price-master", label: "Price Master", icon: SlidersHorizontal, ownerOnly: true },
    { to: "/staff", label: "Staff & Reports", icon: UserCog, ownerOnly: true },
    { to: "/settings", label: "Settings", icon: SettingsIcon },
  ]},
];

// The OEM's finance desk is an OUTSIDE party. Rather than filtering the normal
// nav — which shows anything not explicitly flagged, so a new unflagged page
// would appear for them — they get their own short list.
const OEM_NAV = [
  { section: "OEM", items: [
    { to: "/oem-finance", label: "Retail Finance", icon: Landmark, end: true },
    { to: "/settings", label: "My Password", icon: SettingsIcon },
  ]},
];

function Sidebar({ isOwner, isAccounts, isSalesStaff, isField, isMoneyDesk, canViewFinance, isOemFinance, canEditCommercials, isSalesGm, canApproveLeads, isExecutive, pendingApprovals, open, onNavigate, onClose }) {
  const deskLabel = isOemFinance ? "OEM finance desk"
    : isAccounts ? "Accounts desk" : isField ? "Field desk" : isSalesGm ? "Sales GM desk" : "EV Dealership";
  const nav = isOemFinance ? OEM_NAV : NAV;
  return (
    <aside
      data-testid="app-sidebar"
      className={cx(
        "fixed inset-y-0 left-0 z-50 w-64 flex flex-col border-r border-line bg-white transition-transform duration-200 ease-out",
        "lg:translate-x-0 lg:z-40",
        open ? "translate-x-0 shadow-drawer" : "-translate-x-full lg:translate-x-0",
      )}
    >
      <div className="h-16 flex items-center gap-2.5 px-5 border-b border-line shrink-0">
        <div className="h-9 w-9 rounded-lg bg-cobalt flex items-center justify-center"><Zap size={20} className="text-white" fill="white" /></div>
        <div className="min-w-0 flex-1">
          <div className="font-heading font-extrabold text-ink leading-none tracking-tight">Euler CRM</div>
          <div className="text-[10px] uppercase tracking-widest text-ink-faint mt-0.5">{deskLabel}</div>
        </div>
        <button
          type="button"
          data-testid="sidebar-close"
          onClick={onClose}
          className="lg:hidden rounded-lg p-2 text-ink-faint hover:bg-zinc-100 hover:text-ink"
          aria-label="Close menu"
        >
          <X size={18} />
        </button>
      </div>
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-5 overscroll-contain">
        {nav.map((group) => {
          if (group.ownerOnly && !isOwner) return null;
          if (group.pipeline && !isSalesStaff && !isField) return null;
          const items = group.items.filter((i) => {
            if (i.ownerOnly && !isOwner) return false;
            if (i.salesOnly && !isSalesStaff) return false;
            if (i.moneyDesk && !isMoneyDesk) return false;
            if (i.financeView && !canViewFinance) return false;
            if (i.dealDesk && !canEditCommercials) return false;
            if (i.accountsHome && !isAccounts && !isOwner) return false;
            if (i.fieldHome && !isField && !isOwner) return false;
            if (i.gmHome && !isSalesGm && !isOwner) return false;
            if (i.approvals && !canApproveLeads && !isExecutive) return false;
            return true;
          });
          if (!items.length) return null;
          return (
            <div key={group.section}>
              <div className="px-3 mb-1.5 text-[10px] font-semibold uppercase tracking-widest text-ink-faint">{group.section}</div>
              <div className="space-y-0.5">
                {items.map((item) => (
                  <NavLink key={item.to} to={item.to} end={item.end}
                    data-testid={`nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                    onClick={onNavigate}
                    className={({ isActive }) => cx("group flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-sm font-medium transition-colors", isActive ? "bg-cobalt-tint text-cobalt" : "text-ink-soft hover:bg-zinc-100 hover:text-ink")}>
                    <item.icon size={17} className="shrink-0" />
                    <span className="truncate">{item.label}</span>
                    {item.approvals && pendingApprovals > 0 && (
                      <span className="ml-auto text-[10px] font-bold tabular bg-red-50 text-red-700 px-1.5 py-0.5 rounded-full">{pendingApprovals}</span>
                    )}
                    {item.ownerOnly && <span className="ml-auto text-[9px] font-bold uppercase text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded">Owner</span>}
                  </NavLink>
                ))}
              </div>
            </div>
          );
        })}
      </nav>
      <div className="px-5 py-3 border-t border-line text-[11px] text-ink-faint shrink-0"><span className="font-mono">v2.4</span> · Full-stack</div>
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
  const connected = s.enabled && s.canWrite;
  const hardFail = connected && s.health?.hardFailure === true;
  let tone, dot, label, title;
  if (s.envSafety?.writeBlocked) {
    tone = "bg-sky-50 text-sky-700 ring-sky-600/20"; dot = "bg-sky-500"; label = "Preview · Writes Blocked";
    title = s.envSafety.blockReason || "Preview is isolated from the production Google Sheet — writes are blocked by design.";
  } else if (hardFail) {
    tone = "bg-red-50 text-red-700 ring-red-600/20"; dot = "bg-red-500"; label = "Sync Error";
    title = `Last sheet write failed: ${s.health?.lastError || "unknown"}`;
  } else if (connected) {
    tone = "bg-emerald-50 text-emerald-700 ring-emerald-600/20"; dot = "bg-emerald-500 animate-pulse"; label = "Sheet Synced";
    title = s.health?.lastError && s.health?.lastErrorClass === "sheet_shape"
      ? `Connected. A side tab or pending column was skipped: ${s.health.lastError}`
      : (s.health?.lastWriteAt ? `Last write ${new Date(s.health.lastWriteAt).toLocaleString("en-IN")}` : "Connected — writes flow to your Google Sheet");
  } else {
    tone = "bg-amber-50 text-amber-700 ring-amber-600/20"; dot = "bg-amber-500"; label = "Sync Off";
    title = s.reason || "Google Sheet sync not enabled";
  }
  const short = hardFail ? "Err" : (connected ? "OK" : "Off");
  return (
    <div data-testid="sync-badge" title={title} className={cx("flex items-center gap-2 rounded-full ring-1 ring-inset px-2.5 sm:px-3 py-1.5", tone)}>
      <span className={cx("h-1.5 w-1.5 rounded-full shrink-0", dot)} />
      <span className="text-xs font-medium whitespace-nowrap sm:hidden">{short}</span>
      <span className="text-xs font-medium whitespace-nowrap hidden sm:inline">{label}</span>
    </div>
  );
}

function Topbar({ onMenuOpen }) {
  const { user, logout, isAccounts, isField } = useAuth();
  const [menu, setMenu] = useState(false);
  const [dl, setDl] = useState(false);
  const exportXlsx = async () => {
    setDl(true);
    try { await downloadFile("/export", `euler_crm_export_${new Date().toISOString().slice(0, 10)}.xlsx`); toast.success("Export downloaded"); }
    catch { toast.error("Export failed"); } finally { setDl(false); }
  };
  const initials = (user?.name || user?.email || "U").slice(0, 2).toUpperCase();
  return (
    <header className="sticky top-0 z-30 flex h-14 sm:h-16 items-center gap-2 sm:gap-4 border-b border-line bg-white/80 backdrop-blur px-3 sm:px-6">
      <button
        type="button"
        data-testid="mobile-menu-btn"
        onClick={onMenuOpen}
        className="lg:hidden shrink-0 rounded-lg p-2 text-ink hover:bg-zinc-100"
        aria-label="Open menu"
      >
        <Menu size={20} />
      </button>
      <div className="relative flex-1 min-w-0 max-w-md">
        <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint pointer-events-none" />
        <input
          placeholder="Search…"
          className="w-full rounded-lg bg-zinc-100 border-0 py-2 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint focus:ring-2 focus:ring-cobalt focus:bg-white transition-all"
        />
      </div>
      <div className="ml-auto flex items-center gap-1.5 sm:gap-3 shrink-0">
        {!isAccounts && !isField && (
          <Button
            variant="secondary"
            data-testid="export-btn"
            onClick={exportXlsx}
            disabled={dl}
            className="!px-2.5 sm:!px-3.5"
          >
            <Download size={15} />
            <span className="hidden sm:inline">{dl ? "Exporting…" : "Export"}</span>
          </Button>
        )}
        <SyncBadge />
        <div className="relative">
          <button data-testid="user-menu" onClick={() => setMenu((m) => !m)} className="h-9 w-9 rounded-full bg-ink flex items-center justify-center text-white text-sm font-bold font-heading">{initials}</button>
          {menu && (
            <div className="absolute right-0 mt-2 w-52 bg-white rounded-xl border border-line shadow-drawer py-1.5 z-50">
              <div className="px-3 py-2 border-b border-line">
                <div className="text-sm font-semibold text-ink truncate">{user?.name || "User"}</div>
                <div className="text-xs text-ink-faint truncate">{user?.loginId || user?.email}</div>
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
  const { isOwner, isAccounts, isSalesStaff, isField, isMoneyDesk, canViewFinance, isOemFinance, canEditCommercials, isSalesGm, canApproveLeads, isExecutive } = useAuth();
  const [navOpen, setNavOpen] = useState(false);
  const [pendingApprovals, setPendingApprovals] = useState(0);
  const location = useLocation();

  useEffect(() => {
    if (!canApproveLeads && !isExecutive) return undefined;
    let live = true;
    const load = () => get("/lead-requests/summary").then((d) => {
      if (live) setPendingApprovals(Number(d?.pending || 0));
    }).catch(() => {});
    load();
    const t = setInterval(load, 30000);
    return () => { live = false; clearInterval(t); };
  }, [canApproveLeads, isExecutive, location.pathname]);

  // Close mobile drawer on route change
  useEffect(() => { setNavOpen(false); }, [location.pathname]);

  // Lock body scroll while mobile menu is open
  useEffect(() => {
    if (!navOpen) return undefined;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => { document.body.style.overflow = prev; };
  }, [navOpen]);

  return (
    <div className="min-h-screen bg-app" data-testid="app-shell">
      {/* Mobile backdrop */}
      {navOpen && (
        <button
          type="button"
          data-testid="sidebar-backdrop"
          aria-label="Close menu"
          className="fixed inset-0 z-40 bg-ink/40 backdrop-blur-[2px] lg:hidden"
          onClick={() => setNavOpen(false)}
        />
      )}

      <Sidebar
        isOwner={isOwner}
        isAccounts={isAccounts}
        isSalesStaff={isSalesStaff}
        isField={isField}
        isMoneyDesk={isMoneyDesk}
        canViewFinance={canViewFinance}
        isOemFinance={isOemFinance}
        canEditCommercials={canEditCommercials}
        isSalesGm={isSalesGm}
        canApproveLeads={canApproveLeads}
        isExecutive={isExecutive}
        pendingApprovals={pendingApprovals}
        open={navOpen}
        onClose={() => setNavOpen(false)}
        onNavigate={() => setNavOpen(false)}
      />

      <div className="lg:ml-64 flex flex-col min-h-screen min-w-0">
        <ConnectionBar />
        <Topbar onMenuOpen={() => setNavOpen(true)} />
        {/* NOTE: `animate-fade-up` uses `animation-fill-mode: both`, so this element
            keeps a `transform` after the animation ends. A transformed element is the
            containing block for `position: fixed` DESCENDANTS — so any overlay rendered
            inside a page would size itself against <main> (as tall as the whole list)
            instead of the viewport, pushing its footer buttons off screen.
            Every drawer and modal therefore portals to <body> via ui.js `Portal`.
            If you add a new overlay, portal it too. */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 pb-[calc(1rem+env(safe-area-inset-bottom))] animate-fade-up min-w-0 overflow-x-hidden">{children}</main>
      </div>
    </div>
  );
}
