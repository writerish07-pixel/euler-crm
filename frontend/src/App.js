import React from "react";
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Leads from "./pages/Leads";
import PriceMaster from "./pages/PriceMaster";
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

export default function App() {
  return (
    <BrowserRouter>
      <Toaster richColors position="top-right" />
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/leads" element={<Leads />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/quotations" element={<Quotations />} />
          <Route path="/activities" element={<Activities />} />
          <Route path="/payments" element={<Payments />} />
          <Route path="/finance" element={<Finance />} />
          <Route path="/insurance" element={<Insurance />} />
          <Route path="/deliveries" element={<Deliveries />} />
          <Route path="/claims" element={<Claims />} />
          <Route path="/scheme-master" element={<SchemeMaster />} />
          <Route path="/incentive-master" element={<IncentiveMaster />} />
          <Route path="/dealer-earnings" element={<DealerEarnings />} />
          <Route path="/price-master" element={<PriceMaster />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}
