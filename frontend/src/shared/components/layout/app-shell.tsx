import { Outlet, Navigate } from "react-router-dom";
import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { Topbar } from "./topbar";
import { InstallPrompt } from "@/shared/components/pwa/install-prompt";
import { Spinner } from "@/shared/components/ui/spinner";
import { useAppStore } from "@/shared/stores/app-store";
import { listBusinesses } from "@/shared/api/businesses";
import { getMe } from "@/shared/api/auth";

export function AppShell() {
  const { accessToken, setActiveBusiness, activeBusiness, setRolesAndPermissions } = useAppStore();

  const { data: businesses, isLoading: bizLoading } = useQuery({
    queryKey: ["businesses"],
    queryFn: listBusinesses,
    enabled: !!accessToken,
  });

  // Load user roles + permissions once on mount
  const { data: me } = useQuery({
    queryKey: ["me"],
    queryFn: getMe,
    enabled: !!accessToken,
    staleTime: 5 * 60_000, // 5 min — roles don't change mid-session
  });

  useEffect(() => {
    if (businesses && businesses.length > 0 && !activeBusiness) {
      setActiveBusiness(businesses[0]);
    }
  }, [businesses, activeBusiness, setActiveBusiness]);

  useEffect(() => {
    if (me) setRolesAndPermissions(me.roles, me.permissions);
  }, [me, setRolesAndPermissions]);

  if (!accessToken) return <Navigate to="/login" replace />;

  if (bizLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <Spinner className="h-8 w-8" />
      </div>
    );
  }

  if (businesses && businesses.length === 0) {
    return <Navigate to="/clients/new" replace />;
  }

  return (
    <div className="min-h-screen bg-background">
      <Topbar />
      <main className="mx-auto max-w-7xl">
        <Outlet />
      </main>
      <InstallPrompt />
    </div>
  );
}
