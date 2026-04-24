import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { AppShell } from "@/shared/components/layout/app-shell";
import { useTheme } from "@/shared/hooks/use-theme";
import LoginPage from "@/shared/pages/login";
import RegisterPage from "@/shared/pages/register";
import AuthCallbackPage from "@/shared/pages/auth-callback";
import MarketingPage from "@/marketing/pages/marketing";
import AdminPage from "@/admin/pages/admin";
import BillingPage from "@/finance/pages/billing";
import ReportsPage from "@/finance/pages/reports";
import SalesPage from "@/sales/pages/sales";
import ContactsPage from "@/sales/pages/contacts";
import ContactDetailPage from "@/sales/pages/contact-detail";
import OrganizationsPage from "@/sales/pages/organizations";
import OrganizationDetailPage from "@/sales/pages/organization-detail";
import NewContactPage from "@/sales/pages/new-contact";
import OperationsPage from "@/operations/pages/operations";
import ConnectionsPage from "@/connections/pages/connections";
import DashboardPage from "@/shared/pages/dashboard";
import NewClientPage from "@/shared/pages/new-client";
import NarrativePage from "@/narrative/pages/narrative";
import { CallActionPrompt } from "@/sales/components/call-action-prompt";


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
        <CallActionPrompt />
        <Routes>
          {/* Public routes */}
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/auth/callback" element={<AuthCallbackPage />} />

          {/* Protected routes */}
          <Route element={<AppShell />}>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/clients/new" element={<NewClientPage />} />
            <Route path="/narrative" element={<NarrativePage />} />
            <Route path="/admin" element={<AdminPage />} />
            <Route path="/reports" element={<ReportsPage />} />
            <Route path="/marketing/*" element={<MarketingPage />} />
            <Route path="/sales" element={<SalesPage />} />
            <Route path="/contacts" element={<ContactsPage />} />
            <Route path="/contacts/new" element={<NewContactPage />} />
            <Route path="/contacts/:contactId" element={<ContactDetailPage />} />
            <Route path="/organizations" element={<OrganizationsPage />} />
            <Route path="/organizations/:orgId" element={<OrganizationDetailPage />} />
            <Route path="/jobs" element={<OperationsPage />} />
            <Route path="/billing" element={<BillingPage />} />
            <Route path="/connections" element={<ConnectionsPage />} />
          </Route>

          {/* Catch-all */}
          <Route path="*" element={<Navigate to="/dashboard" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
