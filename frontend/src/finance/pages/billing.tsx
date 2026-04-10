import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  DollarSign,
  TrendingUp,
  Repeat,
  Receipt,
  CreditCard,
  AlertCircle,
  Loader2,
  ExternalLink,
  CheckCircle2,
  Clock,
  XCircle,
  RefreshCw,
  Zap,
  MessageSquare,
  ChevronDown,
  ArrowRight,
  Wallet,
  X,
  Plug,
  Unplug,
  FileText,
} from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { PageHeader } from "@/shared/components/page-header";
import { useAppStore } from "@/shared/stores/app-store";
import {
  getStripeStatus,
  connectStripe,
  disconnectStripe,
  type StripeStatus,
} from "@/finance/api/stripe";
import {
  getRevenueSummary,
  listStripeInvoices,
  listStripeSubscriptions,
  type StripeInvoice,
  type StripeSubscription,
} from "@/finance/api/billing";
import { listJobs, type JobItem } from "@/sales/api/sales";
import { cn } from "@/shared/lib/utils";
import { DeptLayout, type DeptSection } from "@/shared/components/layout/dept-layout";

// ── Helpers ──

function formatCurrency(amount: number): string {
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCents(cents: number): string {
  return formatCurrency(cents / 100);
}

function formatMoney(amount: number | null | undefined): string {
  if (!amount) return "$0";
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatUnixDate(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString();
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function statusColor(status: string): string {
  switch (status) {
    case "completed":
    case "paid":
    case "active":
      return "text-green-600 bg-green-500/10";
    case "pending":
    case "open":
    case "past_due":
      return "text-amber-600 bg-amber-500/10";
    case "failed":
    case "void":
    case "uncollectible":
    case "canceled":
      return "text-red-600 bg-red-500/10";
    case "draft":
      return "text-muted-foreground bg-muted";
    default:
      return "text-muted-foreground bg-muted";
  }
}

function statusIcon(status: string) {
  switch (status) {
    case "completed":
    case "paid":
    case "active":
      return CheckCircle2;
    case "pending":
    case "open":
    case "past_due":
      return Clock;
    case "failed":
    case "void":
    case "uncollectible":
    case "canceled":
      return XCircle;
    default:
      return Clock;
  }
}

// ── Stripe Connection Gate ──

function StripeConnectionBanner({
  status,
  onConnect,
  onDisconnect,
}: {
  status: StripeStatus | undefined;
  onConnect: () => void;
  onDisconnect: () => void;
}) {
  if (!status) return null;

  if (status.connected) {
    return (
      <div className="flex items-center gap-3 rounded-lg border border-green-200 dark:border-green-900 bg-green-50/50 dark:bg-green-950/30 px-4 py-3">
        <div className="flex h-8 w-8 items-center justify-center rounded-full bg-green-500/10">
          <Zap className="h-4 w-4 text-green-600" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-green-700 dark:text-green-400">Stripe Connected</p>
          <p className="text-xs text-green-600/70 dark:text-green-500/70">{status.account_name || status.account_id}</p>
        </div>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={onConnect}>
            <RefreshCw className="h-3 w-3 mr-1" /> Reconnect
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs text-red-600 hover:text-red-700" onClick={onDisconnect}>
            <Unplug className="h-3 w-3 mr-1" /> Disconnect
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center justify-center rounded-lg border-2 border-dashed border-amber-300 dark:border-amber-800 bg-amber-50/50 dark:bg-amber-950/20 px-6 py-8">
      <CreditCard className="h-10 w-10 mb-3 text-amber-500 opacity-60" />
      <p className="text-sm font-semibold text-amber-700 dark:text-amber-400">Connect Stripe to get started</p>
      <p className="text-xs text-amber-600/70 dark:text-amber-500/60 mt-1 text-center max-w-sm">
        Link your Stripe account to enable invoicing, payment tracking, and revenue reporting.
      </p>
      <Button size="sm" className="mt-4 bg-violet-600 hover:bg-violet-700 text-white" onClick={onConnect}>
        <Plug className="h-3 w-3 mr-1" /> Connect Stripe
      </Button>
    </div>
  );
}

// ── Build full job summary for billing context ──

function buildJobSummary(job: JobItem): string {
  const parts: string[] = [];
  if (job.call_summary) parts.push(`**Customer Request:** ${job.call_summary}`);
  if (job.description && job.description !== job.call_summary) parts.push(`**Scope:** ${job.description}`);
  if (job.lead_notes && job.lead_notes !== job.call_summary && job.lead_notes !== job.description) parts.push(`**Sales Notes:** ${job.lead_notes}`);
  if (job.notes) parts.push(`**Work Notes:**\n${job.notes}`);
  if (job.amount_quoted) parts.push(`**Quoted:** $${job.amount_quoted.toLocaleString()}`);
  return parts.join("\n\n");
}

// ── Build the single display summary for the card ──

function buildDisplaySummary(job: JobItem): string {
  const parts: string[] = [];

  if (job.description) {
    parts.push(job.description);
  }

  if (job.call_summary && job.call_summary !== job.description) {
    parts.push(`**Customer request:** ${job.call_summary}`);
  }

  if (job.lead_notes && job.lead_notes !== job.call_summary && job.lead_notes !== job.description) {
    parts.push(`**Sales notes:** ${job.lead_notes}`);
  }

  if (job.notes) {
    parts.push(job.notes);
  }

  return parts.join("\n\n---\n\n");
}

// ── Billing Task Card (completed job needing invoice) ──

function BillingTaskCard({ job, onCreateInvoice, onChat }: {
  job: JobItem;
  onCreateInvoice: (job: JobItem) => void;
  onChat: (job: JobItem) => void;
}) {
  const summary = buildDisplaySummary(job);
  const [expanded, setExpanded] = useState(false);

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-2">
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm truncate">{job.title}</p>
            <p className="text-xs text-muted-foreground">{job.contact_name || "Unknown"}</p>
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0 ml-2">
            <span className="text-[10px] font-semibold rounded-full px-2 py-0.5 bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300">
              Needs Invoice
            </span>
          </div>
        </div>

        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {job.amount_quoted != null && (
            <span className="font-mono font-medium text-foreground">
              <span className="text-muted-foreground font-normal">Quote:</span> {formatMoney(job.amount_quoted)}
            </span>
          )}
          <span><span className="text-muted-foreground">Completed:</span> {formatDate(job.completed_at)}</span>
          {job.started_at && (
            <span><span className="text-muted-foreground">Started:</span> {formatDate(job.started_at)}</span>
          )}
        </div>

        {summary && (
          <div className="rounded-md border border-border bg-muted/30 px-3 py-1.5">
            <button
              onClick={() => setExpanded((v) => !v)}
              className="flex items-center gap-1.5 w-full py-1"
            >
              <ChevronDown className={cn("h-3 w-3 text-muted-foreground transition-transform shrink-0", expanded && "rotate-180")} />
              <span className="text-[10px] font-semibold uppercase text-muted-foreground">Job Summary</span>
            </button>
            {expanded && (
              <div className="pb-2 pl-4.5 text-xs text-foreground/80 leading-relaxed [&_p]:my-1 [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_hr]:my-2 [&_hr]:border-border/50">
                <MarkdownMessage content={summary} />
              </div>
            )}
          </div>
        )}

        <div className="flex gap-1.5 pt-1">
          <Button size="sm" className="h-7 text-xs" onClick={() => onCreateInvoice(job)}>
            <Receipt className="h-3 w-3 mr-1" /> Create Invoice
          </Button>
          <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => onChat(job)}>
            <MessageSquare className="h-3 w-3 mr-1" /> Chat
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Tasks Section (jobs sent to billing from Operations) ──

function BillingTasks({ businessId, onCreateInvoice, onChat }: {
  businessId: string;
  onCreateInvoice: (job: JobItem) => void;
  onChat: (job: JobItem) => void;
}) {
  const { data, isLoading } = useQuery({
    queryKey: ["billing-tasks", businessId],
    queryFn: () => listJobs(businessId, { status: "billing", limit: 100 }),
    enabled: !!businessId,
  });

  const tasks = data?.jobs || [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-24 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading tasks...
      </div>
    );
  }

  if (tasks.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-8 text-muted-foreground">
        <CheckCircle2 className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">No jobs waiting for billing</p>
        <p className="text-xs mt-1">Jobs will appear here when Operations sends them to Billing</p>
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {tasks.map((job) => (
        <BillingTaskCard key={job.id} job={job} onCreateInvoice={onCreateInvoice} onChat={onChat} />
      ))}
    </div>
  );
}

// ── One-Time Invoices Section ──

function OneTimeInvoices({ businessId }: { businessId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["billing-invoices-onetime", businessId],
    queryFn: () => listStripeInvoices(businessId, { limit: 50 }),
    enabled: !!businessId,
  });

  const invoices = (data?.invoices ?? []);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-20 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading invoices...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 justify-center py-6 text-muted-foreground">
        <AlertCircle className="h-4 w-4 text-amber-500" />
        <p className="text-sm">Could not load invoices from Stripe</p>
      </div>
    );
  }

  if (invoices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-muted-foreground">
        <Receipt className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">No invoices yet</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card divide-y divide-border">
      {invoices.map((inv: StripeInvoice) => {
        const StatusIcon = statusIcon(inv.status);
        return (
          <div key={inv.id} className="flex items-center gap-4 px-4 py-3">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${statusColor(inv.status)}`}>
              <StatusIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold">{formatCents(inv.amount_due)}</p>
                <Badge variant="outline" className="text-xs py-0 h-5">{inv.status}</Badge>
                {inv.number && <span className="text-xs text-muted-foreground">#{inv.number}</span>}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                {inv.customer_name || inv.customer_email}
              </p>
            </div>
            <span className="text-xs text-muted-foreground hidden sm:block">{formatUnixDate(inv.created)}</span>
            {inv.hosted_invoice_url && (
              <a href={inv.hosted_invoice_url} target="_blank" rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors" title="View invoice">
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Subscriptions Section ──

function SubscriptionList({ businessId }: { businessId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["billing-subscriptions", businessId],
    queryFn: () => listStripeSubscriptions(businessId, { limit: 50 }),
    enabled: !!businessId,
  });

  const subscriptions = data?.subscriptions ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-20 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading subscriptions...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex items-center gap-2 justify-center py-6 text-muted-foreground">
        <AlertCircle className="h-4 w-4 text-amber-500" />
        <p className="text-sm">Could not load subscriptions from Stripe</p>
      </div>
    );
  }

  if (subscriptions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-6 text-muted-foreground">
        <Repeat className="h-8 w-8 mb-2 opacity-30" />
        <p className="text-sm">No recurring billing set up</p>
      </div>
    );
  }

  return (
    <div className="rounded-lg border border-border bg-card divide-y divide-border">
      {subscriptions.map((sub: StripeSubscription) => {
        const StatusIcon = statusIcon(sub.status);
        return (
          <div key={sub.id} className="flex items-center gap-4 px-4 py-3">
            <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${statusColor(sub.status)}`}>
              <StatusIcon className="h-4 w-4" />
            </div>
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-semibold">
                  {formatCents(sub.amount)}/{sub.interval === "month" ? "mo" : sub.interval === "year" ? "yr" : sub.interval}
                </p>
                <Badge variant="outline" className="text-xs py-0 h-5">{sub.status}</Badge>
                {sub.cancel_at_period_end && (
                  <Badge variant="outline" className="text-xs py-0 h-5 text-amber-600 border-amber-200">Canceling</Badge>
                )}
              </div>
              {sub.plan_name && <p className="text-xs text-muted-foreground mt-0.5">{sub.plan_name}</p>}
            </div>
            <div className="text-right hidden sm:block">
              <p className="text-xs text-muted-foreground">Next: {formatUnixDate(sub.current_period_end)}</p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Main Billing Page ──

export default function BillingPage() {
  const { activeBusiness } = useAppStore();
  const businessId = activeBusiness?.id ?? "";
  const queryClient = useQueryClient();

  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null);

  // Stripe connect modal state
  const [showStripeModal, setShowStripeModal] = useState(false);
  const [stripeSecretKey, setStripeSecretKey] = useState("");
  const [stripeError, setStripeError] = useState<string | null>(null);

  const { data: stripeStatus, isLoading: stripeLoading } = useQuery({
    queryKey: ["stripe-status", businessId],
    queryFn: () => getStripeStatus(businessId),
    enabled: !!businessId,
  });

  const stripeConnectMutation = useMutation({
    mutationFn: () => connectStripe({ business_id: businessId, secret_key: stripeSecretKey.trim() }),
    onSuccess: () => {
      setShowStripeModal(false);
      setStripeSecretKey("");
      setStripeError(null);
      queryClient.invalidateQueries({ queryKey: ["stripe-status"] });
      queryClient.invalidateQueries({ queryKey: ["billing-summary"] });
    },
    onError: (err: unknown) => {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ?? "Failed to connect Stripe.";
      setStripeError(msg);
    },
  });

  const stripeDisconnectMutation = useMutation({
    mutationFn: () => disconnectStripe(businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["stripe-status"] });
      queryClient.invalidateQueries({ queryKey: ["billing-summary"] });
    },
  });

  const stripeConnected = stripeStatus?.connected ?? false;

  // Find Billing department + head employee (Quinn)
  // Jobs in billing status
  const { data: tasksData } = useQuery({
    queryKey: ["billing-tasks", businessId],
    queryFn: () => listJobs(businessId, { status: "billing", limit: 100 }),
    enabled: !!businessId,
  });
  const taskCount = tasksData?.jobs?.length ?? 0;

  // Invoice count for badge (unpaid = open status)
  const { data: invoicesData } = useQuery({
    queryKey: ["billing-invoices-onetime", businessId],
    queryFn: () => listStripeInvoices(businessId, { limit: 50 }),
    enabled: !!businessId && stripeConnected,
  });
  const unpaidCount = invoicesData?.invoices?.filter((inv: StripeInvoice) => inv.status === "open").length ?? 0;

  // Revenue summary
  const { data: revenueSummary } = useQuery({
    queryKey: ["billing-summary", businessId],
    queryFn: () => getRevenueSummary(businessId),
    enabled: !!businessId && stripeConnected,
  });

  // Task card actions → open chat with prefill (include full job context)
  const handleCreateInvoice = (job: JobItem) => {
    const amount = job.amount_quoted ? `$${job.amount_quoted.toLocaleString()}` : "TBD";
    const summary = buildJobSummary(job);
    const contextBlock = summary ? `\n\nCompleted Job Summary:\n${summary}` : "";
    setPendingChatMessage(
      `Create an invoice for job "${job.title}" — customer: ${job.contact_name || "Unknown"}, quoted amount: ${amount}. Job ID: ${job.id}${contextBlock}`
    );
  };

  const handleChatAboutJob = (job: JobItem) => {
    const amount = job.amount_quoted ? `$${job.amount_quoted.toLocaleString()}` : "TBD";
    const summary = buildJobSummary(job);
    const contextBlock = summary ? `\n\nCompleted Job Summary:\n${summary}` : "";
    setPendingChatMessage(
      `I want to discuss billing for job "${job.title}" — customer: ${job.contact_name || "Unknown"}, quoted amount: ${amount}. Job ID: ${job.id}${contextBlock}`
    );
  };

  if (stripeLoading) {
    return (
      <div className="flex flex-col h-full items-center justify-center gap-2 text-muted-foreground">
        <Loader2 className="h-6 w-6 animate-spin" />
        <p className="text-sm">Loading billing...</p>
      </div>
    );
  }

  // ── Section content ──

  const overviewContent = (
    <div className="space-y-6">
      {/* KPI cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <p className="text-xs text-muted-foreground">Monthly Revenue</p>
            </div>
            <p className="text-2xl font-bold text-green-600">
              {revenueSummary ? formatCurrency(revenueSummary.total_collected) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <DollarSign className="h-4 w-4 text-blue-500" />
              <p className="text-xs text-muted-foreground">YTD Revenue</p>
            </div>
            <p className="text-2xl font-bold text-blue-600">
              {revenueSummary ? formatCurrency(revenueSummary.total_collected) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Repeat className="h-4 w-4 text-purple-500" />
              <p className="text-xs text-muted-foreground">Recurring Revenue</p>
            </div>
            <p className="text-2xl font-bold text-purple-600">
              {revenueSummary ? formatCurrency(revenueSummary.mrr) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Wallet className="h-4 w-4 text-amber-500" />
              <p className="text-xs text-muted-foreground">One-Time Revenue</p>
            </div>
            <p className="text-2xl font-bold text-amber-600">
              {revenueSummary ? formatCurrency(revenueSummary.pending) : "—"}
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Stripe connection */}
      <div className="space-y-3">
        <p className="text-sm font-semibold flex items-center gap-2">
          <Zap className="h-4 w-4 text-primary" /> Stripe
        </p>
        <StripeConnectionBanner
          status={stripeStatus}
          onConnect={() => { setStripeError(null); setShowStripeModal(true); }}
          onDisconnect={() => stripeDisconnectMutation.mutate()}
        />
      </div>

      {/* Billing tasks (jobs from Operations) */}
      {taskCount > 0 && (
        <div className="space-y-3">
          <p className="text-sm font-semibold flex items-center gap-2">
            <ArrowRight className="h-4 w-4 text-primary" /> Pending Tasks
            <span className="text-xs font-normal text-muted-foreground">{taskCount} waiting</span>
          </p>
          <BillingTasks
            businessId={businessId}
            onCreateInvoice={handleCreateInvoice}
            onChat={handleChatAboutJob}
          />
        </div>
      )}

      {/* Stripe Connect Modal */}
      {showStripeModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="relative w-full max-w-md rounded-xl bg-background p-6 shadow-xl">
            <button className="absolute right-4 top-4 text-muted-foreground hover:text-foreground" onClick={() => setShowStripeModal(false)}>
              <X className="h-4 w-4" />
            </button>
            <h2 className="mb-1 text-lg font-semibold">Connect Stripe</h2>
            <p className="mb-5 text-sm text-muted-foreground">
              Enter your Stripe Secret Key. Find it in the{" "}
              <a href="https://dashboard.stripe.com/apikeys" target="_blank" rel="noreferrer" className="text-violet-600 underline">Stripe Dashboard</a>
              {" "}→ Developers → API keys.
            </p>
            <div className="space-y-4">
              <div>
                <label className="mb-1 block text-sm font-medium">Secret Key</label>
                <input
                  type="password"
                  placeholder="sk_live_... or sk_test_..."
                  value={stripeSecretKey}
                  onChange={(e) => setStripeSecretKey(e.target.value)}
                  className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm font-mono placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-ring"
                />
                <p className="mt-1 text-xs text-muted-foreground">Use a test key (sk_test_...) for testing. Never share this key.</p>
              </div>
              {stripeError && (
                <div className="flex items-start gap-2 rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-300">
                  <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
                  {stripeError}
                </div>
              )}
              <div className="flex justify-end gap-2 pt-2">
                <Button variant="outline" onClick={() => setShowStripeModal(false)} disabled={stripeConnectMutation.isPending}>Cancel</Button>
                <Button
                  onClick={() => stripeConnectMutation.mutate()}
                  disabled={!stripeSecretKey.trim() || stripeConnectMutation.isPending}
                  className="bg-violet-600 hover:bg-violet-700 text-white"
                >
                  {stripeConnectMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <CheckCircle2 className="mr-1 h-4 w-4" />}
                  {stripeConnectMutation.isPending ? "Connecting…" : "Connect"}
                </Button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );

  const invoicesContent = (
    <div className="space-y-4">
      {stripeConnected ? (
        <OneTimeInvoices businessId={businessId} />
      ) : (
        <div className="flex flex-col items-center justify-center py-6 text-muted-foreground">
          <Receipt className="h-8 w-8 mb-2 opacity-30" />
          <p className="text-sm">Connect Stripe to view invoices</p>
        </div>
      )}
    </div>
  );

  const subscriptionsContent = (
    <div className="space-y-4">
      {stripeConnected ? (
        <SubscriptionList businessId={businessId} />
      ) : (
        <div className="flex flex-col items-center justify-center py-6 text-muted-foreground">
          <Repeat className="h-8 w-8 mb-2 opacity-30" />
          <p className="text-sm">Connect Stripe to view recurring billing</p>
        </div>
      )}
    </div>
  );

  const sections: DeptSection[] = [
    {
      id: "overview",
      label: "Overview",
      icon: <DollarSign />,
      content: overviewContent,
    },
    {
      id: "invoices",
      label: "Invoices",
      icon: <FileText />,
      badge: unpaidCount > 0 ? unpaidCount : undefined,
      content: invoicesContent,
    },
    {
      id: "subscriptions",
      label: "Subscriptions",
      icon: <RefreshCw />,
      content: subscriptionsContent,
    },
  ];

  return (
    <div className="p-6 space-y-4">
      <PageHeader
        title="Billing"
        description="Invoicing, payments, and revenue tracking"
      />
      <DeptLayout
        sections={sections}
        agentName="billing"
        businessId={businessId}
        pendingMessage={pendingChatMessage}
        onPendingConsumed={() => setPendingChatMessage(null)}
      />
    </div>
  );
}
