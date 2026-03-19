import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plug,
  CheckCircle,
  XCircle,
  RefreshCw,
  Unplug,
  TestTube,
  ExternalLink,
  Loader2,
  Clock,
} from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import { StatusBadge } from "@/shared/components/status-badge";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listConnections,
  connectOAuth,
  disconnectPlatform,
  refreshPlatformToken,
  testConnection,
} from "@/shared/api/platforms";
import type { PlatformTestResult } from "@/shared/api/platforms";
import { PLATFORM_LABELS } from "@/shared/lib/constants";

// Platforms available for OAuth connection
const CONNECTABLE_PLATFORMS = [
  { key: "google_business_profile", label: "Google Business", description: "Local listings & reviews" },
  { key: "google_ads", label: "Google Ads", description: "Search & display advertising" },
  { key: "facebook", label: "Meta (FB + IG)", description: "Facebook Pages, Instagram, Ads" },
  { key: "bing", label: "Bing Ads", description: "Microsoft Advertising" },
  { key: "linkedin", label: "LinkedIn", description: "Company page & posts" },
] as const;

function formatExpiry(dateStr: string | null): string {
  if (!dateStr) return "No expiry";
  const d = new Date(dateStr);
  const now = new Date();
  const diffMs = d.getTime() - now.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 0) return "Expired";
  if (diffDays === 0) return "Expires today";
  if (diffDays === 1) return "Expires tomorrow";
  return `Expires in ${diffDays} days`;
}

export default function ConnectionsPage() {
  const activeBusiness = useAppStore((s) => s.activeBusiness);
  const businessId = activeBusiness?.id ?? "";
  const queryClient = useQueryClient();
  const [searchParams] = useSearchParams();
  const [successBanner, setSuccessBanner] = useState<string | null>(null);
  const [testResults, setTestResults] = useState<Record<string, PlatformTestResult | null>>({});
  const [testingPlatform, setTestingPlatform] = useState<string | null>(null);

  // Check for OAuth callback success
  useEffect(() => {
    const platform = searchParams.get("platform");
    const status = searchParams.get("status");
    if (platform && status === "success") {
      setSuccessBanner(`${PLATFORM_LABELS[platform] ?? platform} connected successfully!`);
      queryClient.invalidateQueries({ queryKey: ["connections"] });
      const timer = setTimeout(() => setSuccessBanner(null), 5000);
      return () => clearTimeout(timer);
    }
  }, [searchParams, queryClient]);

  const { data: connections, isLoading } = useQuery({
    queryKey: ["connections", businessId],
    queryFn: () => listConnections(businessId),
    enabled: !!businessId,
  });

  const connectMutation = useMutation({
    mutationFn: (platform: string) =>
      connectOAuth({ platform, business_id: businessId }),
    onSuccess: (data) => {
      window.location.href = data.auth_url;
    },
  });

  const disconnectMutation = useMutation({
    mutationFn: (platform: string) =>
      disconnectPlatform({ platform, business_id: businessId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const refreshMutation = useMutation({
    mutationFn: (platform: string) =>
      refreshPlatformToken({ platform, business_id: businessId }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["connections"] });
    },
  });

  const handleTest = async (platform: string) => {
    setTestingPlatform(platform);
    setTestResults((prev) => ({ ...prev, [platform]: null }));
    try {
      const result = await testConnection(platform, businessId);
      setTestResults((prev) => ({ ...prev, [platform]: result }));
    } catch {
      setTestResults((prev) => ({
        ...prev,
        [platform]: { platform, token_valid: false, error: "Test request failed" },
      }));
    } finally {
      setTestingPlatform(null);
    }
  };

  const connectedMap = new Map(
    (connections ?? []).map((c) => [c.platform, c])
  );

  if (!businessId) {
    return (
      <div className="flex h-64 items-center justify-center">
        <p className="text-muted-foreground">Select a business to manage connections.</p>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Connections"
        description="Connect your platforms so the automation platform can manage your marketing, analytics, and outreach."
      />

      {/* Success banner */}
      {successBanner && (
        <div className="mb-6 flex items-center gap-2 rounded-md bg-emerald-100 p-4 text-sm text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-300">
          <CheckCircle className="h-4 w-4" />
          {successBanner}
        </div>
      )}

      {/* OAuth Platforms */}
      <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
        Platform Integrations
      </h3>

      {isLoading ? (
        <div className="flex h-64 items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="space-y-4">
          {CONNECTABLE_PLATFORMS.map(({ key, label, description }) => {
            const conn = connectedMap.get(key);
            const isActive = conn?.status === "active";
            const result = testResults[key];

            return (
              <Card key={key}>
                <CardContent className="flex items-center justify-between p-5">
                  <div className="flex items-center gap-4">
                    <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${isActive ? "bg-emerald-100 dark:bg-emerald-900/30" : "bg-muted"}`}>
                      <Plug className={`h-5 w-5 ${isActive ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`} />
                    </div>
                    <div>
                      <p className="font-medium">{label}</p>
                      <p className="text-sm text-muted-foreground">{description}</p>
                      {conn && (
                        <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                          <StatusBadge status={conn.status} />
                          <span className="flex items-center gap-1">
                            <Clock className="h-3 w-3" />
                            {formatExpiry(conn.token_expires_at)}
                          </span>
                        </div>
                      )}
                      {/* Test result */}
                      {result && (
                        <div className={`mt-2 rounded-md p-2 text-xs ${result.token_valid ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/20 dark:text-emerald-300" : "bg-red-50 text-red-700 dark:bg-red-900/20 dark:text-red-300"}`}>
                          {result.token_valid ? (
                            <div className="flex flex-col gap-1">
                              <span className="flex items-center gap-1 font-medium">
                                <CheckCircle className="h-3 w-3" /> Token verified
                              </span>
                              {result.account_name && <span>Account: {result.account_name}</span>}
                              {result.email && <span>Email: {result.email}</span>}
                              {result.page_count !== undefined && (
                                <span>Pages: {result.page_count} {result.pages?.map((p) => p.name).join(", ")}</span>
                              )}
                            </div>
                          ) : (
                            <span className="flex items-center gap-1">
                              <XCircle className="h-3 w-3" /> {result.error ?? "Token invalid"}
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>

                  <div className="flex items-center gap-2">
                    {isActive ? (
                      <>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => handleTest(key)}
                          disabled={testingPlatform === key}
                        >
                          {testingPlatform === key ? (
                            <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                          ) : (
                            <TestTube className="mr-1 h-3 w-3" />
                          )}
                          Test
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={() => refreshMutation.mutate(key)}
                          disabled={refreshMutation.isPending}
                        >
                          <RefreshCw className={`mr-1 h-3 w-3 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
                          Refresh
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => disconnectMutation.mutate(key)}
                          disabled={disconnectMutation.isPending}
                          className="text-red-600 hover:text-red-700"
                        >
                          <Unplug className="mr-1 h-3 w-3" />
                          Disconnect
                        </Button>
                      </>
                    ) : (
                      <Button
                        size="sm"
                        onClick={() => connectMutation.mutate(key)}
                        disabled={connectMutation.isPending}
                      >
                        {connectMutation.isPending ? (
                          <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                        ) : (
                          <ExternalLink className="mr-1 h-3 w-3" />
                        )}
                        Connect
                      </Button>
                    )}
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}

    </div>
  );
}
