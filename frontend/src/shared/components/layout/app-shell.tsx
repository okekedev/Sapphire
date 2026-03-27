import { Outlet, Navigate } from "react-router-dom";
import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2 } from "lucide-react";
import { Topbar } from "./topbar";
import { MainTabs } from "./main-tabs";
import { InstallPrompt } from "@/shared/components/pwa/install-prompt";
import { Spinner } from "@/shared/components/ui/spinner";
import { useAppStore } from "@/shared/stores/app-store";
import { listBusinesses, createBusiness, getMyMembership } from "@/shared/api/businesses";

// ── Create Business Form (shown on first login) ──

function CreateBusinessScreen() {
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const { setActiveBusiness, setBusinesses } = useAppStore();
  const queryClient = useQueryClient();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim()) return;
    setLoading(true);
    setError("");
    try {
      const biz = await createBusiness({ name: name.trim() });
      setBusinesses([biz]);
      setActiveBusiness(biz);
      queryClient.invalidateQueries({ queryKey: ["businesses"] });
    } catch (err: any) {
      setError(err?.response?.data?.detail ?? "Failed to create business. Please try again.");
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-6">
      <div className="w-full max-w-sm space-y-6">
        <div className="space-y-1 text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-xl bg-primary/10">
            <Building2 size={24} className="text-primary" />
          </div>
          <h1 className="text-2xl font-bold">Create your business</h1>
          <p className="text-sm text-muted-foreground">
            Set up your workspace to get started with Workforce.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <label className="text-sm font-medium" htmlFor="biz-name">
              Business name
            </label>
            <input
              id="biz-name"
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Acme Plumbing"
              className="w-full rounded-lg border border-input bg-background px-3 py-2 text-sm placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
              autoFocus
            />
          </div>

          {error && <p className="text-sm text-destructive">{error}</p>}

          <button
            type="submit"
            disabled={loading || !name.trim()}
            className="flex w-full items-center justify-center gap-2 rounded-lg bg-primary px-4 py-2.5 text-sm font-semibold text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
          >
            {loading ? <Spinner className="h-4 w-4" /> : "Get started"}
          </button>
        </form>
      </div>
    </div>
  );
}

// ── App Shell ──

export function AppShell() {
  const { accessToken, setBusinesses, setActiveBusiness, activeBusiness, setAllowedTabs } =
    useAppStore();

  const { data: businesses, isLoading: bizLoading } = useQuery({
    queryKey: ["businesses"],
    queryFn: listBusinesses,
    enabled: !!accessToken,
  });

  const { data: membership } = useQuery({
    queryKey: ["my-membership", activeBusiness?.id],
    queryFn: () => getMyMembership(activeBusiness!.id),
    enabled: !!activeBusiness?.id,
  });

  useEffect(() => {
    if (!businesses) return;
    setBusinesses(businesses);
    if (businesses.length > 0 && !activeBusiness) {
      const savedId = localStorage.getItem("current-business-id");
      const saved = savedId ? businesses.find((b) => b.id === savedId) : null;
      setActiveBusiness(saved ?? businesses[0]);
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

  // No business yet — show setup screen
  if (businesses && businesses.length === 0) {
    return <CreateBusinessScreen />;
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
