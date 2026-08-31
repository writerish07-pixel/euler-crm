import React from "react";
import { BrowserRouter, Routes, Route, Navigate, useLocation } from "react-router-dom";
import { Toaster } from "sonner";
import { AuthProvider, useAuth } from "./context/AuthContext";
import Layout from "./components/Layout";
import Login from "./pages/Login";
import Share from "./pages/Share";
import Dashboard from "./pages/Dashboard";
import ExecutiveDashboard from "./pages/ExecutiveDashboard";
import FieldDashboard from "./pages/FieldDashboard";
import AccountsDashboard from "./pages/AccountsDashboard";
import Leads from "./pages/Leads";
import PriceMaster from "./pages/PriceMaster";
import PriceList from "./pages/PriceList";
import Inventory from "./pages/Inventory";
import Cancellations from "./pages/Cancellations";
import SchemeMaster from "./pages/SchemeMaster";
import IncentiveMaster from "./pages/IncentiveMaster";
import Payments from "./pages/Payments";
import Deliveries from "./pages/Deliveries";
import Finance from "./pages/Finance";
import Insurance from "./pages/Insurance";
import Claims from "./pages/Claims";
import Activities from "./pages/Activities";
import DealerEarnings from "./pages/DealerEarnings";
import Quotations from "./pages/Quotations";
import Bookings from "./pages/Bookings";
import Settings from "./pages/Settings";
import InsurancePayoutReport from "./pages/InsurancePayoutReport";
import InsuranceAgents from "./pages/InsuranceAgents";
import Staff from "./pages/Staff";
import WhatsAppInbox from "./pages/WhatsAppInbox";
import EarningsReport from "./pages/EarningsReport";
import OwnerCommercialReport from "./pages/OwnerCommercialReport";
import OemClaimDashboard from "./pages/OemClaimDashboard";
import ClaimExceptions from "./pages/ClaimExceptions";
import ERPProductionAudit from "./pages/ERPProductionAudit";
import AuditLog from "./pages/AuditLog";
import OemFinance from "./pages/OemFinance";
import Allocation from "./pages/Allocation";

function homePath(auth) {
  // The OEM finance desk has exactly one page. Sending it anywhere else would
  // bounce off the API's 403 and look like a broken app.
  if (auth.isOemFinance) return "/oem-finance";
  if (auth.isAccounts) return "/accounts";
  if (auth.isField) return "/field";
  return "/";
}

function Protected({ children, ownerOnly, salesOnly, moneyDesk, financeView, fieldOk, fieldOnly, accountsHome, oemOk, dealDesk }) {
  const auth = useAuth();
  const { user, isOwner, isSalesStaff, isField, isMoneyDesk, isAccounts, canViewFinance, isOemFinance, canEditCommercials } = auth;
  const loc = useLocation();
  if (user === undefined) return <div className="min-h-screen grid place-items-center text-ink-faint">Loading…</div>;
  if (!user) return <Navigate to="/login" state={{ from: loc }} replace />;
  // An outside role reaches only the pages that name it. Everything else is a
  // redirect here and a 403 on the API — the browser is not the enforcement.
  if (isOemFinance && !oemOk) return <Navigate to="/oem-finance" replace />;
  if (ownerOnly && !isOwner) return <Navigate to={homePath(auth)} replace />;
  if (dealDesk && !canEditCommercials) return <Navigate to={homePath(auth)} replace />;
  if (fieldOnly && !isField && !isOwner) return <Navigate to={homePath(auth)} replace />;
  if (accountsHome && !isAccounts && !isOwner && !isSalesStaff) {
    return <Navigate to={homePath(auth)} replace />;
  }
  if (financeView && !canViewFinance) return <Navigate to={homePath(auth)} replace />;
  if (moneyDesk && !isMoneyDesk) return <Navigate to={homePath(auth)} replace />;
  if (salesOnly && !isSalesStaff && !(fieldOk && isField)) {
    return <Navigate to={homePath(auth)} replace />;
  }
  return <Layout>{children}</Layout>;
}

function HomeRedirect() {
  const { isAccounts, isField, isExecutive, isOemFinance } = useAuth();
  if (isOemFinance) return <Navigate to="/oem-finance" replace />;
  if (isAccounts) return <Navigate to="/accounts" replace />;
  if (isField) return <Navigate to="/field" replace />;
  if (isExecutive) return <ExecutiveDashboard />;
  return <Dashboard />;
}

function AppRoutes() {
  const P = (el, opts = {}) => (
    <Protected
      ownerOnly={opts.ownerOnly}
      salesOnly={opts.salesOnly}
      moneyDesk={opts.moneyDesk}
      financeView={opts.financeView}
      fieldOk={opts.fieldOk}
      fieldOnly={opts.fieldOnly}
      accountsHome={opts.accountsHome}
      oemOk={opts.oemOk}
      dealDesk={opts.dealDesk}
    >
      {el}
    </Protected>
  );
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/share" element={<Share />} />
      <Route path="/" element={P(<HomeRedirect />)} />
      <Route path="/accounts" element={P(<AccountsDashboard />, { accountsHome: true })} />
      <Route path="/field" element={P(<FieldDashboard />, { fieldOnly: true })} />
      <Route path="/leads" element={P(<Leads />, { salesOnly: true, fieldOk: true })} />
      <Route path="/bookings" element={P(<Bookings />, { salesOnly: true, fieldOk: true })} />
      <Route path="/quotations" element={P(<Quotations />, { salesOnly: true })} />
      <Route path="/activities" element={P(<Activities />, { salesOnly: true })} />
      <Route path="/whatsapp" element={P(<WhatsAppInbox />, { salesOnly: true })} />
      {/* Every role that sees the funnel sees who is dropping out of it. The API
          scopes an executive to their own leads. */}
      <Route path="/cancellations" element={P(<Cancellations />, { fieldOk: true })} />
      {/* Owner too, so you can see exactly what the OEM sees before issuing a login. */}
      <Route path="/oem-finance" element={P(<OemFinance />, { oemOk: true })} />
      <Route path="/allocation" element={P(<Allocation />, { dealDesk: true })} />
      <Route path="/payments" element={P(<Payments />, { moneyDesk: true })} />
      <Route path="/finance" element={P(<Finance />, { financeView: true })} />
      <Route path="/insurance" element={P(<Insurance />, { moneyDesk: true })} />
      <Route path="/insurance-agents" element={P(<InsuranceAgents />, { ownerOnly: true })} />
      <Route path="/deliveries" element={P(<Deliveries />)} />
      <Route path="/claims" element={P(<Claims />, { moneyDesk: true })} />
      <Route path="/scheme-master" element={P(<SchemeMaster />, { salesOnly: true })} />
      <Route path="/incentive-master" element={P(<IncentiveMaster />, { salesOnly: true })} />
      <Route path="/dealer-earnings" element={P(<DealerEarnings />, { ownerOnly: true })} />
      <Route path="/insurance-report" element={P(<InsurancePayoutReport />, { ownerOnly: true })} />
      <Route path="/earnings-report" element={P(<EarningsReport />, { ownerOnly: true })} />
      <Route path="/owner-commercial" element={P(<OwnerCommercialReport />, { ownerOnly: true })} />
      <Route path="/oem-claim-dashboard" element={P(<OemClaimDashboard />, { ownerOnly: true })} />
      <Route path="/claim-exceptions" element={P(<ClaimExceptions />, { ownerOnly: true })} />
      <Route path="/erp-audit" element={P(<ERPProductionAudit />, { ownerOnly: true })} />
      <Route path="/audit-log" element={P(<AuditLog />, { ownerOnly: true })} />
      <Route path="/price-list" element={P(<PriceList />, { salesOnly: true, fieldOk: true })} />
      <Route path="/inventory" element={P(<Inventory />, { salesOnly: true, fieldOk: true })} />
      <Route path="/price-master" element={P(<PriceMaster />, { ownerOnly: true })} />
      <Route path="/staff" element={P(<Staff />, { ownerOnly: true })} />
      <Route path="/settings" element={P(<Settings />)} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster richColors position="bottom-right" duration={2500} />
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
