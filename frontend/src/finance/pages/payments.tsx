import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Trash2,
  DollarSign,
  CreditCard,
  AlertCircle,
  Clock,
  RefreshCw,
  CheckCircle2,
  XCircle,
  Loader2,
  ExternalLink,
  Receipt,
  Repeat,
  TrendingUp,
  Wallet,
} from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { Badge } from "@/shared/components/ui/badge";
import { Card, CardContent } from "@/shared/components/ui/card";
import { PageHeader } from "@/shared/components/page-header";
import { DepartmentCallsPanel } from "@/shared/components/department-calls-panel";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listPayments,
  createPayment,
  deletePayment,
  type PaymentCreatePayload,
  type PaymentStatus,
} from "@/finance/api/payments";
import {
  getRevenueSummary,
  listStripeInvoices,
  listStripeSubscriptions,
  type StripeInvoice,
  type StripeSubscription,
} from "@/finance/api/billing";

// ── Helpers ──

function formatCurrency(amount: number): string {
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

function formatCents(cents: number): string {
  return formatCurrency(cents / 100);
}

function formatUnixDate(ts: number | null): string {
  if (!ts) return "—";
  return new Date(ts * 1000).toLocaleDateString();
}

function statusColor(status: PaymentStatus | string): string {
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
    case "refunded":
    case "draft":
      return "text-muted-foreground bg-muted";
    default:
      return "text-muted-foreground bg-muted";
  }
}

function statusIcon(status: PaymentStatus | string) {
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
    case "refunded":
      return RefreshCw;
    default:
      return Clock;
  }
}

type BillingTab = "invoices" | "subscriptions" | "payments";

// ── Tab Button ──

function TabButton({
  active,
  label,
  icon: Icon,
  onClick,
}: {
  active: boolean;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
        active
          ? "border-foreground text-foreground"
          : "border-transparent text-muted-foreground hover:text-foreground"
      }`}
    >
      <Icon className="h-4 w-4" />
      {label}
    </button>
  );
}

// ── New Payment Form ──

function NewPaymentForm({
  onSubmit,
  onCancel,
  isLoading,
}: {
  onSubmit: (data: PaymentCreatePayload) => void;
  onCancel: () => void;
  isLoading: boolean;
}) {
  const [amount, setAmount] = useState("");
  const [paymentType, setPaymentType] = useState<"one_time" | "subscription">("one_time");
  const [frequency, setFrequency] = useState("monthly");
  const [provider, setProvider] = useState("");
  const [notes, setNotes] = useState("");

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!amount || parseFloat(amount) <= 0) return;
    onSubmit({
      amount: parseFloat(amount),
      payment_type: paymentType,
      frequency: paymentType === "subscription" ? frequency : undefined,
      provider: provider.trim() || undefined,
      notes: notes.trim() || undefined,
    });
  };

  return (
    <form onSubmit={handleSubmit} className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Amount *</label>
          <input
            autoFocus
            type="number"
            min="0.01"
            step="0.01"
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            placeholder="0.00"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </div>
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Type</label>
          <select
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={paymentType}
            onChange={(e) => setPaymentType(e.target.value as "one_time" | "subscription")}
          >
            <option value="one_time">One-time</option>
            <option value="subscription">Subscription</option>
          </select>
        </div>
      </div>

      {paymentType === "subscription" && (
        <div>
          <label className="mb-1 block text-xs text-muted-foreground">Frequency</label>
          <select
            className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
            value={frequency}
            onChange={(e) => setFrequency(e.target.value)}
          >
            <option value="monthly">Monthly</option>
            <option value="quarterly">Quarterly</option>
            <option value="annual">Annual</option>
          </select>
        </div>
      )}

      <div>
        <label className="mb-1 block text-xs text-muted-foreground">Provider</label>
        <input
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="e.g. stripe, cash, zelle"
          value={provider}
          onChange={(e) => setProvider(e.target.value)}
        />
      </div>

      <div>
        <label className="mb-1 block text-xs text-muted-foreground">Notes</label>
        <textarea
          className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm resize-none focus:outline-none focus:ring-1 focus:ring-ring"
          placeholder="Optional notes"
          rows={2}
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
        />
      </div>

      <div className="flex gap-2 justify-end">
        <Button type="button" variant="ghost" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" size="sm" disabled={isLoading || !amount}>
          {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : "Add Payment"}
        </Button>
      </div>
    </form>
  );
}

// ── Invoices Tab ──

function InvoicesTab({ businessId }: { businessId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["billing-invoices", businessId],
    queryFn: () => listStripeInvoices(businessId, { limit: 50 }),
    enabled: !!businessId,
  });

  const invoices = data?.invoices ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading invoices from Stripe...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2 text-amber-500" />
        <p className="text-sm">Could not load Stripe invoices</p>
        <p className="text-xs mt-1">Make sure Stripe is connected on the Connections page.</p>
      </div>
    );
  }

  if (invoices.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Receipt className="h-10 w-10 mb-3 opacity-30" />
        <p className="text-sm">No invoices found in Stripe</p>
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
                {inv.number && (
                  <span className="text-xs text-muted-foreground">#{inv.number}</span>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5 truncate">
                {inv.customer_name || inv.customer_email}
              </p>
            </div>
            <span className="text-xs text-muted-foreground hidden sm:block">
              {formatUnixDate(inv.created)}
            </span>
            {inv.hosted_invoice_url && (
              <a
                href={inv.hosted_invoice_url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="View invoice"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── Subscriptions Tab ──

function SubscriptionsTab({ businessId }: { businessId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["billing-subscriptions", businessId],
    queryFn: () => listStripeSubscriptions(businessId, { limit: 50 }),
    enabled: !!businessId,
  });

  const subscriptions = data?.subscriptions ?? [];

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Loading subscriptions from Stripe...
      </div>
    );
  }

  if (isError) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <AlertCircle className="h-8 w-8 mb-2 text-amber-500" />
        <p className="text-sm">Could not load Stripe subscriptions</p>
        <p className="text-xs mt-1">Make sure Stripe is connected on the Connections page.</p>
      </div>
    );
  }

  if (subscriptions.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
        <Repeat className="h-10 w-10 mb-3 opacity-30" />
        <p className="text-sm">No subscriptions found in Stripe</p>
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
                  <Badge variant="outline" className="text-xs py-0 h-5 text-amber-600 border-amber-200">
                    Canceling
                  </Badge>
                )}
              </div>
              {sub.plan_name && (
                <p className="text-xs text-muted-foreground mt-0.5">{sub.plan_name}</p>
              )}
            </div>
            <div className="text-right hidden sm:block">
              <p className="text-xs text-muted-foreground">
                Period ends {formatUnixDate(sub.current_period_end)}
              </p>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ── Payments Tab (manual records) ──

function PaymentsTab({ businessId }: { businessId: string }) {
  const queryClient = useQueryClient();
  const [showForm, setShowForm] = useState(false);

  const { data, isLoading, isError } = useQuery({
    queryKey: ["payments", businessId],
    queryFn: () => listPayments(businessId),
    enabled: !!businessId,
  });

  const createMutation = useMutation({
    mutationFn: (payload: PaymentCreatePayload) => createPayment(businessId, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payments", businessId] });
      queryClient.invalidateQueries({ queryKey: ["billing-summary", businessId] });
      setShowForm(false);
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (paymentId: string) => deletePayment(paymentId, businessId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["payments", businessId] });
      queryClient.invalidateQueries({ queryKey: ["billing-summary", businessId] });
    },
  });

  const payments = data?.payments ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          Manual payment records (cash, check, Zelle, etc.)
        </p>
        <Button size="sm" onClick={() => setShowForm(!showForm)}>
          <Plus className="mr-1 h-4 w-4" />
          Record Payment
        </Button>
      </div>

      {showForm && (
        <NewPaymentForm
          onSubmit={(data) => createMutation.mutate(data)}
          onCancel={() => setShowForm(false)}
          isLoading={createMutation.isPending}
        />
      )}

      {isLoading ? (
        <div className="flex items-center justify-center h-40 text-muted-foreground text-sm">
          Loading payments...
        </div>
      ) : isError ? (
        <div className="flex items-center gap-2 justify-center h-40 text-destructive text-sm">
          <AlertCircle className="h-4 w-4" /> Failed to load payments
        </div>
      ) : payments.length === 0 && !showForm ? (
        <div className="flex flex-col items-center justify-center py-12 text-muted-foreground">
          <CreditCard className="h-10 w-10 mb-3 opacity-30" />
          <p className="text-sm">No manual payments recorded yet.</p>
        </div>
      ) : (
        <div className="rounded-lg border border-border bg-card divide-y divide-border">
          {payments.map((payment) => {
            const StatusIcon = statusIcon(payment.status);
            return (
              <div key={payment.id} className="group flex items-center gap-4 px-4 py-3">
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full ${statusColor(payment.status)}`}>
                  <StatusIcon className="h-4 w-4" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <p className="text-sm font-semibold">{formatCurrency(payment.amount)}</p>
                    <Badge variant="outline" className="text-xs py-0 h-5">
                      {payment.payment_type === "subscription"
                        ? `${payment.frequency ?? "recurring"} sub`
                        : "one-time"}
                    </Badge>
                    {payment.provider && (
                      <span className="text-xs text-muted-foreground">{payment.provider}</span>
                    )}
                  </div>
                  {payment.notes && (
                    <p className="text-xs text-muted-foreground mt-0.5 truncate">{payment.notes}</p>
                  )}
                </div>
                <span className="text-xs text-muted-foreground hidden sm:block">
                  {payment.paid_at
                    ? new Date(payment.paid_at).toLocaleDateString()
                    : new Date(payment.created_at).toLocaleDateString()}
                </span>
                <button
                  onClick={() => deleteMutation.mutate(payment.id)}
                  className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive transition-opacity"
                  title="Delete payment"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </button>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

// ── Main Finance Page ──

export default function PaymentsPage() {
  const { activeBusiness } = useAppStore();
  const businessId = activeBusiness?.id ?? "";
  const [activeTab, setActiveTab] = useState<BillingTab>("invoices");

  const { data: summary } = useQuery({
    queryKey: ["billing-summary", businessId],
    queryFn: () => getRevenueSummary(businessId),
    enabled: !!businessId,
  });

  if (!businessId) {
    return (
      <div className="flex flex-col h-full items-center justify-center gap-2 text-muted-foreground">
        <DollarSign className="h-8 w-8" />
        <p className="text-sm">No business selected</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Finance"
        description="Revenue tracking, Stripe invoices, subscriptions, and payment records"
      />

      {/* Summary cards */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <TrendingUp className="h-4 w-4 text-green-500" />
              <p className="text-xs text-muted-foreground">Total Collected</p>
            </div>
            <p className="text-2xl font-bold text-green-600">
              {summary ? formatCurrency(summary.total_collected) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Clock className="h-4 w-4 text-amber-500" />
              <p className="text-xs text-muted-foreground">Outstanding</p>
            </div>
            <p className="text-2xl font-bold text-amber-600">
              {summary ? formatCurrency(summary.pending) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Repeat className="h-4 w-4 text-blue-500" />
              <p className="text-xs text-muted-foreground">Monthly Recurring</p>
            </div>
            <p className="text-2xl font-bold text-blue-600">
              {summary ? formatCurrency(summary.mrr) : "—"}
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-5">
            <div className="flex items-center gap-2 mb-1">
              <Wallet className="h-4 w-4 text-purple-500" />
              <p className="text-xs text-muted-foreground">Active Subscriptions</p>
            </div>
            <p className="text-2xl font-bold">
              {summary ? summary.active_subscriptions : "—"}
            </p>
            {summary?.stripe_connected && summary.stripe_balance != null && (
              <p className="text-xs text-muted-foreground mt-1">
                Stripe balance: {formatCurrency(summary.stripe_balance)}
              </p>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Tab bar */}
      <div className="flex border-b border-border">
        <TabButton
          active={activeTab === "invoices"}
          label="Invoices"
          icon={Receipt}
          onClick={() => setActiveTab("invoices")}
        />
        <TabButton
          active={activeTab === "subscriptions"}
          label="Subscriptions"
          icon={Repeat}
          onClick={() => setActiveTab("subscriptions")}
        />
        <TabButton
          active={activeTab === "payments"}
          label="Payments"
          icon={CreditCard}
          onClick={() => setActiveTab("payments")}
        />
      </div>

      {/* Tab content */}
      {activeTab === "invoices" && <InvoicesTab businessId={businessId} />}
      {activeTab === "subscriptions" && <SubscriptionsTab businessId={businessId} />}
      {activeTab === "payments" && <PaymentsTab businessId={businessId} />}

      {/* ═══ DEPARTMENT CALLS ═══ */}
      <DepartmentCallsPanel department="Finance" />
    </div>
  );
}
