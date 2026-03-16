import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/shared/components/layout/app-shell";
import { useTheme } from "@/shared/hooks/use-theme";
import LoginPage from "@/shared/pages/login";
import RegisterPage from "@/shared/pages/register";
import MarketingPage from "@/marketing/pages/marketing";
import AdminPage from "@/admin/pages/admin";
import BillingPage from "@/finance/pages/billing";
import ReportsPage from "@/finance/pages/reports";
import SalesPage from "@/sales/pages/sales";
import OperationsPage from "@/operations/pages/operations";

import DashboardPage from "@/dashboard/pages/dashboard";
import ITPage from "@/it/pages/it";


const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export default function App() {
  useTheme();

  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />

          {/* Protected routes */}
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/it" element={<ITPage />} />
            <Route path="/marketing/reports" element={<ReportsPage />} />
            <Route path="/marketing/*" element={<MarketingPage />} />
            <Route path="/sales" element={<SalesPage />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/billing" element={<BillingPage />} />

          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
