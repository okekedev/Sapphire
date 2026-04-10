import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/shared/components/layout/app-shell";
import { useTheme } from "@/shared/hooks/use-theme";
import LoginPage from "@/shared/pages/login";
import RegisterPage from "@/shared/pages/register";
import AuthCallbackPage from "@/shared/pages/auth-callback";
import MarketingPage from "@/marketing/pages/marketing";
import AdminPage from "@/admin/pages/admin";
import CallReportsPage from "@/admin/pages/reports";
import BillingPage from "@/finance/pages/billing";
import ReportsPage from "@/finance/pages/reports";
import SalesPage from "@/sales/pages/sales";
import OperationsPage from "@/operations/pages/operations";
import ConnectionsPage from "@/connections/pages/connections";

import NarrativePage from "@/narrative/pages/narrative";


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
          <Route path="/auth/callback" element={<AuthCallbackPage />} />

          {/* Protected routes */}
          <Route element={<AppShell />}>
            <Route path="/narrative" element={<NarrativePage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/reports" element={<CallReportsPage />} />
            <Route path="/marketing/reports" element={<ReportsPage />} />
            <Route path="/marketing/*" element={<MarketingPage />} />
            <Route path="/sales" element={<SalesPage />} />
            <Route path="/operations" element={<OperationsPage />} />
            <Route path="/billing" element={<BillingPage />} />
            <Route path="/finance" element={<BillingPage />} />
            <Route path="/connections" element={<ConnectionsPage />} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
