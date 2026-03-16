import { Outlet, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Topbar } from "./topbar";
import { MainTabs } from "./main-tabs";
import { InstallPrompt } from "@/shared/components/pwa/install-prompt";
import { Spinner } from "@/shared/components/ui/spinner";
import { useAppStore } from "@/shared/stores/app-store";
import { listBusinesses, getMyMembership } from "@/shared/api/businesses";

export function AppShell() {
  const { accessToken, setBusinesses, setActiveBusiness, activeBusiness, setAllowedTabs } =
    useAppStore();

  const { data: businesses, isLoading: bizLoading } = useQuery({
    queryKey: ["businesses"],
    queryFn: listBusinesses,
    enabled: !!accessToken,
  });

  // Load current user's tab permissions whenever the active business changes
  const { data: membership } = useQuery({
    queryKey: ["my-membership", activeBusiness?.id],
    queryFn: () => getMyMembership(activeBusiness!.id),
    enabled: !!activeBusiness?.id,
  });

  useEffect(() => {
    if (businesses && businesses.length > 0) {
      setBusinesses(businesses);
      if (!activeBusiness) {
        // Restore previously selected business, or fall back to first
        const savedId = localStorage.getItem("current-business-id");
        const saved = savedId ? businesses.find((b) => b.id === savedId) : null;
        setActiveBusiness(saved ?? businesses[0]);
      }
    }
  }, [businesses, setBusinesses, setActiveBusiness, activeBusiness]);

  useEffect(() => {
    if (membership) {
      setAllowedTabs(membership.allowed_tabs);
    }
  }, [membership, setAllowedTabs]);

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  if (bizLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background">
      <Topbar />
      <MainTabs />
      <main className="mx-auto max-w-7xl p-6">
        <Outlet />
      </main>
      <InstallPrompt />
    </div>
  );
}
