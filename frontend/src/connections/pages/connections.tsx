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
  Terminal,
  Phone,
  X,
  Zap,
  Play,
  Square,
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
  getCliConnectionStatus,
  disconnectCli,
} from "@/shared/api/platforms";
import type { PlatformTestResult } from "@/shared/api/platforms";
import {
  getTwilioStatus,
  connectTwilio,
  disconnectTwilio,
} from "@/admin/api/twilio";
import {
  getStripeStatus,
  connectStripe,
  disconnectStripe,
} from "@/finance/api/stripe";
import {
  getNgrokStatus,
  connectNgrok,
  disconnectNgrok,
  startNgrokTunnel,
  stopNgrokTunnel,
} from "@/shared/api/ngrok";
import { PLATFORM_LABELS } from "@/shared/lib/constants";
import { ClaudeTerminalModal } from "@/shared/components/claude-terminal-modal";

// Platforms available for OAuth connection
const CONNECTABLE_PLATFORMS = [
  { key: "facebook", label: "Facebook", description: "Pages, Instagram, Messenger" },
  { key: "google_search_console", label: "Search Console", description: "Search analytics & indexing" },
  { key: "google_analytics", label: "Google Analytics", description: "GA4 traffic & conversions" },
  { key: "google_business_profile", label: "Google Business", description: "Local listings & reviews" },
  { key: "youtube", label: "YouTube", description: "Channel management & uploads" },
  { key: "linkedin", label: "LinkedIn", description: "Company page & posts" },
  { key: "gmail", label: "Gmail", description: "Send & read emails" },
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
  const [showTerminal, setShowTerminal] = useState(false);

  // Twilio state
  const [showTwilioModal, setShowTwilioModal] = useState(false);
  const [twilioAccountSid, setTwilioAccountSid] = useState("");
  const [twilioAuthToken, setTwilioAuthToken] = useState("");
  const [twilioPhone, setTwilioPhone] = useState("");
  const [twilioError, setTwilioError] = useState<string | null>(null);

  // Stripe state
  const [showStripeModal, setShowStripeModal] = useState(false);
  const [stripeSecretKey, setStripeSecretKey] = useState("");
  const [stripeError, setStripeError] = useState<string | null>(null);

  // Ngrok state
  const [showNgrokModal, setShowNgrokModal] = useState(false);
  const [ngrokAuthToken, setNgrokAuthToken] = useState("");
  const [ngrokError, setNgrokError] = useState<string | null>(null);

  // Twilio status query
  const { data: twilioStatus, isLoading: twilioLoading } = useQuery({
    queryKey: ["twilio-status", businessId],
    queryFn: () => getTwilioStatus(businessId),
    enabled: !!businessId,
  });

  const twilioConnectMutation = useMutation({
    mutationFn: () =>
      connectTwilio({
        business_id: businessId,
        account_sid: twilioAccountSid.trim(),
        auth_token: twilioAuthToken.trim(),
        phone_number: twilioPhone.trim() || undefined,
      }),
    onSuccess: () => {
      setShowTwilioModal(false);
      setTwilioAccountSid("");
      setTwilioAuthToken("");
      setTwilioPhone("");
      setTwilioError(null);
      queryClient.invalidateQueries({ queryKey: ["twilio-status"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Failed to connect Twilio account.";
      setTwilioError(msg);
    },
  });

  const twilioDisconnectMutation = useMutation({
    mutationFn: () => disconnectTwilio(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["twilio-status"] });
    },
  });

  // Stripe status query
  const { data: stripeStatus, isLoading: stripeLoading } = useQuery({
    queryKey: ["stripe-status", businessId],
    queryFn: () => getStripeStatus(businessId),
    enabled: !!businessId,
  });

  const stripeConnectMutation = useMutation({
    mutationFn: () =>
      connectStripe({
        business_id: businessId,
        secret_key: stripeSecretKey.trim(),
      }),
    onSuccess: () => {
      setShowStripeModal(false);
      setStripeSecretKey("");
      setStripeError(null);
      queryClient.invalidateQueries({ queryKey: ["stripe-status"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Failed to connect Stripe account.";
      setStripeError(msg);
    },
  });

  const stripeDisconnectMutation = useMutation({
    mutationFn: () => disconnectStripe(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stripe-status"] });
    },
  });


  // Ngrok status query
  const { data: ngrokStatus, isLoading: ngrokLoading } = useQuery({
    queryKey: ["ngrok-status", businessId],
    queryFn: () => getNgrokStatus(businessId),
    enabled: !!businessId,
  });

  const ngrokConnectMutation = useMutation({
    mutationFn: () =>
      connectNgrok({
        business_id: businessId,
        auth_token: ngrokAuthToken.trim(),
      }),
    onSuccess: () => {
      setShowNgrokModal(false);
      setNgrokAuthToken("");
      setNgrokError(null);
      queryClient.invalidateQueries({ queryKey: ["ngrok-status"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Failed to connect ngrok.";
      setNgrokError(msg);
    },
  });

  const ngrokDisconnectMutation = useMutation({
    mutationFn: () => disconnectNgrok(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ngrok-status"] });
    },
  });

  const ngrokStartTunnelMutation = useMutation({
    mutationFn: () => startNgrokTunnel(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ngrok-status"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })
        ?.response?.data?.detail ?? "Failed to start tunnel.";
      setNgrokError(msg);
    },
  });

  const ngrokStopTunnelMutation = useMutation({
    mutationFn: () => stopNgrokTunnel(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ngrok-status"] });
    },
  });

  // Claude CLI connection status
  const { data: cliStatus, isLoading: cliLoading } = useQuery({
    queryKey: ["cli-status", businessId],
    queryFn: () => getCliConnectionStatus(businessId),
    enabled: !!businessId,
  });

  const cliDisconnectMutation = useMutation({
    mutationFn: () => disconnectCli(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["cli-status"] });
    },
  });

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

      {/* Claude CLI Card */}
      <div className="mb-6">
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          AI Provider
        </h3>
        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <div className="flex items-center gap-4">
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                cliStatus?.status === "active"
                  ? "bg-amber-100 dark:bg-amber-900/30"
                  : "bg-muted"
              }`}>
                <Terminal className={`h-5 w-5 ${
                  cliStatus?.status === "active"
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-muted-foreground"
                }`} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">Claude CLI</p>
                  {cliStatus?.version && (
                    <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] font-mono text-muted-foreground">
                      v{cliStatus.version}
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  Powers all AI employees via Claude Max subscription
                </p>
                {cliStatus && !cliLoading && (
                  <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <StatusBadge status={cliStatus.status} />
                    {cliStatus.connected_at && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Connected {new Date(cliStatus.connected_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              {cliLoading ? (
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              ) : cliStatus?.status === "active" ? (
                <>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setShowTerminal(true)}
                  >
                    <RefreshCw className="mr-1 h-3 w-3" />
                    Reconnect
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => cliDisconnectMutation.mutate()}
                    disabled={cliDisconnectMutation.isPending}
                    className="text-red-600 hover:text-red-700"
                  >
                    <Unplug className="mr-1 h-3 w-3" />
                    Disconnect
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  onClick={() => setShowTerminal(true)}
                  className="bg-amber-600 hover:bg-amber-700 text-white"
                >
                  <Terminal className="mr-1 h-3 w-3" />
                  {cliStatus?.status === "expired" ? "Reconnect" : "Connect"}
                </Button>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Developer Tools — ngrok */}
      <div className="mb-6">
        <h3 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wide">
          Developer Tools
        </h3>
        <Card>
          <CardContent className="flex items-center justify-between p-5">
            <div className="flex items-center gap-4">
              <div className={`flex h-10 w-10 items-center justify-center rounded-lg ${
                ngrokStatus?.connected
                  ? "bg-green-100 dark:bg-green-900/30"
                  : "bg-muted"
              }`}>
                <Zap className={`h-5 w-5 ${
                  ngrokStatus?.connected
                    ? "text-green-600 dark:text-green-400"
                    : "text-muted-foreground"
                }`} />
              </div>
              <div>
                <div className="flex items-center gap-2">
                  <p className="font-medium">ngrok</p>
                  {ngrokStatus?.tunnel_url && ngrokStatus?.tunnel_active && (
                    <span className="rounded-full bg-green-100 dark:bg-green-900/30 px-2 py-0.5 text-[10px] font-mono text-green-700 dark:text-green-300">
                      Tunnel Active
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground">
                  Local tunnel for Twilio webhooks — exposes localhost to the internet for call testing
                </p>
                {ngrokStatus && !ngrokLoading && (
                  <div className="mt-1 flex items-center gap-3 text-xs text-muted-foreground">
                    <StatusBadge status={ngrokStatus.connected ? "active" : "disconnected"} />
                    {ngrokStatus.tunnel_url && ngrokStatus.tunnel_active && (
                      <span className="font-mono text-green-600 dark:text-green-400 truncate max-w-[250px]">
                        {ngrokStatus.tunnel_url}
                      </span>
                    )}
                    {ngrokStatus.connected_at && (
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        Connected {new Date(ngrokStatus.connected_at).toLocaleDateString()}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="flex items-center gap-2">
              {ngrokLoading ? (
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              ) : ngrokStatus?.connected ? (
                <>
                  {ngrokStatus?.tunnel_active ? (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => ngrokStopTunnelMutation.mutate()}
                      disabled={ngrokStopTunnelMutation.isPending}
                    >
                      {ngrokStopTunnelMutation.isPending ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : (
                        <Square className="mr-1 h-3 w-3" />
                      )}
                      Stop Tunnel
                    </Button>
                  ) : (
                    <Button
                      variant="outline"
                      size="sm"
                      onClick={() => ngrokStartTunnelMutation.mutate()}
                      disabled={ngrokStartTunnelMutation.isPending}
                      className="text-green-600 border-green-300 hover:bg-green-50 dark:hover:bg-green-900/20"
                    >
                      {ngrokStartTunnelMutation.isPending ? (
                        <Loader2 className="mr-1 h-3 w-3 animate-spin" />
                      ) : (
                        <Play className="mr-1 h-3 w-3" />
                      )}
                      {ngrokStartTunnelMutation.isPending ? "Starting…" : "Start Tunnel"}
                    </Button>
                  )}
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      setNgrokError(null);
                      setShowNgrokModal(true);
                    }}
                  >
                    <RefreshCw className="mr-1 h-3 w-3" />
                    Update Token
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => ngrokDisconnectMutation.mutate()}
                    disabled={ngrokDisconnectMutation.isPending}
                    className="text-red-600 hover:text-red-700"
                  >
                    <Unplug className="mr-1 h-3 w-3" />
                    Disconnect
                  </Button>
                </>
              ) : (
                <Button
                  size="sm"
                  onClick={() => {
                    setNgrokError(null);
                    setShowNgrokModal(true);
                  }}
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  <Zap className="mr-1 h-3 w-3" />
                  Connect
                </Button>
              )}
            </div>
          </CardContent>
          {/* Tunnel error shown on card (not just inside modal) */}
          {ngrokError && !showNgrokModal && (
            <div className="mx-6 mb-4 flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
              <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
              {ngrokError}
              <button
                onClick={() => setNgrokError(null)}
                className="ml-auto text-red-400 hover:text-red-600"
              >
                <X className="h-3 w-3" />
              </button>
            </div>
          )}
        </Card>
      </div>

      {/* ngrok Connect Modal */}
      {showNgrokModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="relative w-full max-w-md rounded-xl bg-background p-6 shadow-xl">
            <button
              className="absolute right-4 top-4 text-muted-foreground hover:text-foreground"
              onClick={() => setShowNgrokModal(false)}
            >
              <X className="h-4 w-4" />
            </button>
            <h2 className="mb-1 text-lg font-semibold">Connect ngrok</h2>
            <p className="mb-5 text-sm text-muted-foreground">
              Enter your ngrok auth token. Find it in the{" "}
              <a
                href="https://dashboard.ngrok.com/get-started/your-authtoken"
                target="_blank"
                rel="noreferrer"
                className="text-green-600 underline"
              >
                ngrok Dashboard
              </a>{" "}
              → Your Authtoken.
            </p>

            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Auth Token</label>
                <input
                  type="password"
                  placeholder="Paste your ngrok auth token"
                  value={ngrokAuthToken}
                  onChange={(e) => setNgrokAuthToken(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground">
                  Creates a public URL that routes Twilio webhooks to your local server for testing.
                </p>
              </div>

              {ngrokError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                  <XCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  {ngrokError}
                </div>
              )}

              <div className="flex justify-end gap-2 pt-2">
                <Button
                  variant="outline"
                  onClick={() => setShowNgrokModal(false)}
                  disabled={ngrokConnectMutation.isPending}
                >
                  Cancel
                </Button>
                <Button
                  onClick={() => ngrokConnectMutation.mutate()}
                  disabled={
                    !ngrokAuthToken.trim() ||
                    ngrokConnectMutation.isPending
                  }
                  className="bg-green-600 hover:bg-green-700 text-white"
                >
                  {ngrokConnectMutation.isPending ? (
                    <Loader2 className="mr-1 h-4 w-4 animate-spin" />
                  ) : (
                    <CheckCircle className="mr-1 h-4 w-4" />
                  )}
                  {ngrokConnectMutation.isPending ? "Connecting…" : "Connect"}
                </Button>
              </div>
            </div>
          </div>
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

      {/* Claude CLI Terminal Modal */}
      <ClaudeTerminalModal
        isOpen={showTerminal}
        onClose={() => setShowTerminal(false)}
        businessId={businessId}
        onAuthenticated={() => {
          setShowTerminal(false);
          queryClient.invalidateQueries({ queryKey: ["cli-status"] });
        }}
      />
    </div>
  );
}
