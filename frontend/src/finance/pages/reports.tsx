import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Users, DollarSign, Phone, Loader2, UserPlus, Briefcase,
  ChevronDown, TrendingUp, ArrowDownRight, CheckCircle2,
  PhoneIncoming, Download, Clock,
} from "lucide-react";
import {
  BarChart, Bar, XAxis, YAxis,
  Tooltip as RechartsTooltip, ResponsiveContainer, Cell, LabelList,
} from "recharts";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import { cn } from "@/shared/lib/utils";
import { useAppStore } from "@/shared/stores/app-store";
import { getPipelineFunnel, type FunnelStage, type CampaignAttribution } from "@/finance/api/reports";
import { listCalls } from "@/marketing/api/tracking-routing";

// ── Helpers ──

function formatMoney(amount: number): string {
  if (amount === 0) return "$0";
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

const STAGE_ICONS: Record<string, React.ReactNode> = {
  calls:          <Phone className="h-4 w-4" />,
  leads:          <UserPlus className="h-4 w-4" />,
  jobs_created:   <Briefcase className="h-4 w-4" />,
  jobs_completed: <CheckCircle2 className="h-4 w-4" />,
  revenue:        <DollarSign className="h-4 w-4" />,
};

const NEW_COLOR    = "#3b82f6";
const RETURN_COLOR = "#f59e0b";

// ── Funnel tooltip ──

function FunnelTooltip({ active, payload }: { active?: boolean; payload?: Array<{ payload: FunnelStage }> }) {
  if (!active || !payload?.length) return null;
  const stage = payload[0].payload;
  return (
    <div className="rounded-lg border border-border bg-popover p-3 shadow-lg text-sm">
      <p className="font-semibold mb-2">{stage.label}</p>
      <div className="space-y-1 text-xs">
        <div className="flex justify-between gap-6"><span className="text-muted-foreground">Total</span><span className="font-medium">{stage.total}</span></div>
        <div className="flex justify-between gap-6"><span style={{ color: NEW_COLOR }}>New Customers</span><span className="font-medium">{stage.new_customers}</span></div>
        <div className="flex justify-between gap-6"><span style={{ color: RETURN_COLOR }}>Returning</span><span className="font-medium">{stage.returning_customers}</span></div>
        <div className="border-t border-border my-1 pt-1 flex justify-between gap-6"><span className="text-muted-foreground">From Campaigns</span><span className="font-medium">{stage.from_campaigns}</span></div>
        <div className="flex justify-between gap-6"><span className="text-muted-foreground">Manual / Direct</span><span className="font-medium">{stage.manual}</span></div>
        {stage.revenue > 0 && (
          <div className="border-t border-border my-1 pt-1 flex justify-between gap-6">
            <span className="text-muted-foreground">Revenue</span>
            <span className="font-semibold text-emerald-600">{formatMoney(stage.revenue)}</span>
          </div>
        )}
        {stage.conversion_pct < 100 && (
          <div className="flex justify-between gap-6"><span className="text-muted-foreground">Conversion</span><span className="font-medium">{stage.conversion_pct}%</span></div>
        )}
      </div>
    </div>
  );
}

// ── Main Page ──

export default function ReportsPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const [days, setDays] = useState(30);

  const funnelQuery = useQuery({
    queryKey: ["reports-funnel", businessId, days],
    queryFn: () => getPipelineFunnel(businessId, days),
    enabled: !!businessId,
  });

  const callLogQuery = useQuery({
    queryKey: ["call-log", businessId],
    queryFn: () => listCalls(businessId, { limit: 200, sort_by: "date", sort_order: "desc" }),
    enabled: !!businessId,
    refetchInterval: 30_000,
  });

  const funnel    = funnelQuery.data;
  const stages    = funnel?.stages ?? [];
  const campaigns = funnel?.campaigns ?? [];
  const totals    = funnel?.totals ?? {};
  const calls     = callLogQuery.data?.calls ?? [];

  const chartData = stages.map((s) => ({
    ...s,
    new_val:    s.stage === "calls" ? s.total : s.new_customers,
    return_val: s.stage === "calls" ? 0 : s.returning_customers,
  }));

  const exportCSV = () => {
    if (!calls.length) return;
    const rows = calls.map((c) => ({
      "Call ID":     c.id,
      "Phone":       c.caller_phone || "",
      "Name":        c.caller_name  || "Unknown",
      "Reason":      c.summary || c.call_category || "",
      "Department":  c.routed_to || "Unrouted",
      "Duration (s)": c.duration_s ?? "",
      "Date":        new Date(c.created_at).toLocaleString(),
    }));
    const headers = Object.keys(rows[0]);
    const csv = [
      headers.join(","),
      ...rows.map((r) => headers.map((h) => `"${String((r as Record<string, unknown>)[h]).replace(/"/g, '""')}"`).join(",")),
    ].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href = url;
    a.download = `call-log-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6 p-6">
      <PageHeader
        title="Reports"
        description="Full-funnel: Tracking calls → Leads → Jobs → Revenue"
        actions={
          <div className="flex gap-2">
            {[7, 30, 90].map((d) => (
              <Button key={d} size="sm" variant={days === d ? "default" : "outline"} onClick={() => setDays(d)}>
                {d}d
              </Button>
            ))}
          </div>
        }
      />

      {/* ═══ PIPELINE FUNNEL CHART ═══ */}
      <Card>
        <CardContent className="p-6">
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="h-4 w-4 text-primary" />
            <h2 className="text-sm font-semibold uppercase tracking-wider text-muted-foreground">Pipeline Funnel</h2>
          </div>
          <p className="text-xs text-muted-foreground mb-5">
            Hover each bar for details. <span style={{ color: NEW_COLOR }}>Blue = new customers</span>, <span style={{ color: RETURN_COLOR }}>amber = returning</span>.
          </p>

          {funnelQuery.isLoading ? (
            <div className="flex items-center justify-center py-12"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>
          ) : stages.length === 0 || stages.every((s) => s.total === 0) ? (
            <div className="py-12 text-center text-sm text-muted-foreground">No pipeline data yet. Populates as calls come in through tracking numbers.</div>
          ) : (
            <div className="space-y-4">
              <ResponsiveContainer width="100%" height={280}>
                <BarChart data={chartData} barCategoryGap="25%" margin={{ top: 20, right: 10, left: 10, bottom: 0 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 11, fill: "hsl(var(--muted-foreground))" }} axisLine={false} tickLine={false} />
                  <YAxis hide />
                  <RechartsTooltip content={<FunnelTooltip />} cursor={{ fill: "hsl(var(--muted) / 0.3)" }} />
                  <Bar dataKey="new_val" stackId="a" fill={NEW_COLOR} name="New">
                    <LabelList dataKey="total" position="top" formatter={(val: unknown) => (val ? String(val) : "")} style={{ fontSize: 13, fontWeight: 700, fill: "hsl(var(--foreground))" }} />
                  </Bar>
                  <Bar dataKey="return_val" stackId="a" fill={RETURN_COLOR} radius={[4, 4, 0, 0]} name="Returning" />
                </BarChart>
              </ResponsiveContainer>

              <div className="flex items-center justify-center gap-1 flex-wrap">
                {stages.map((stage, i) => (
                  <div key={stage.stage} className="flex items-center gap-1">
                    <div className="flex items-center gap-1 rounded-md bg-muted/50 px-2.5 py-1">
                      {STAGE_ICONS[stage.stage]}
                      <span className="text-xs font-medium">{stage.total}</span>
                    </div>
                    {i < stages.length - 1 && (
                      <div className="flex items-center gap-0.5 px-1">
                        <ArrowDownRight className="h-3 w-3 text-muted-foreground/50" />
                        <span className="text-[10px] font-semibold text-muted-foreground">{stages[i + 1].conversion_pct}%</span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* ═══ KPI CARDS ═══ */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
        <KpiCard icon={<Phone className="h-3.5 w-3.5" />}      label="Calls"          value={totals.total_calls    ?? 0} />
        <KpiCard icon={<UserPlus className="h-3.5 w-3.5" />}   label="Leads"          value={totals.total_leads    ?? 0} />
        <KpiCard icon={<Briefcase className="h-3.5 w-3.5" />}  label="Jobs"           value={totals.total_jobs     ?? 0} />
        <KpiCard icon={<DollarSign className="h-3.5 w-3.5" />} label="Revenue"        value={formatMoney(totals.total_revenue     ?? 0)} />
        <KpiCard icon={<Users className="h-3.5 w-3.5" />}      label="New Rev."       value={formatMoney(totals.new_revenue       ?? 0)} color="text-blue-500" />
        <KpiCard icon={<Users className="h-3.5 w-3.5" />}      label="Returning Rev." value={formatMoney(totals.returning_revenue ?? 0)} color="text-amber-500" />
      </div>

      {/* ═══ CAMPAIGN ATTRIBUTION ═══ */}
      <CollapsibleSection title="Campaign Attribution" defaultOpen>
        {campaigns.length === 0 ? (
          <div className="py-10 text-center text-sm text-muted-foreground">No campaign data yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                  <th className="px-3 py-2 text-left">Campaign</th>
                  <th className="px-3 py-2 text-left">Channel</th>
                  <th className="px-3 py-2 text-right">Calls</th>
                  <th className="px-3 py-2 text-right">Leads</th>
                  <th className="px-3 py-2 text-right">Jobs</th>
                  <th className="px-3 py-2 text-right">Revenue</th>
                  <th className="px-3 py-2 text-right"><span style={{ color: NEW_COLOR }}>New</span></th>
                  <th className="px-3 py-2 text-right"><span style={{ color: RETURN_COLOR }}>Returning</span></th>
                </tr>
              </thead>
              <tbody>
                {campaigns.map((c) => (
                  <tr key={c.campaign_name} className="border-b transition hover:bg-muted/30">
                    <td className="px-3 py-2.5 font-semibold">{c.campaign_name}</td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">{c.channel || "—"}</td>
                    <td className="px-3 py-2.5 text-right">{c.calls}</td>
                    <td className="px-3 py-2.5 text-right">{c.leads}</td>
                    <td className="px-3 py-2.5 text-right">{c.jobs}</td>
                    <td className="px-3 py-2.5 text-right font-semibold text-emerald-600">{formatMoney(c.revenue)}</td>
                    <td className="px-3 py-2.5 text-right" style={{ color: NEW_COLOR }}>{c.new_customers}</td>
                    <td className="px-3 py-2.5 text-right" style={{ color: RETURN_COLOR }}>{c.returning_customers}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CollapsibleSection>

      {/* ═══ CALL LOG ═══ */}
      <CollapsibleSection
        title="Call Log"
        defaultOpen={false}
        action={
          calls.length > 0 ? (
            <button
              onClick={exportCSV}
              className="inline-flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
            >
              <Download size={12} /> Export CSV
            </button>
          ) : undefined
        }
      >
        {calls.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            <PhoneIncoming size={28} className="mx-auto mb-2 opacity-40" />
            <p>No calls yet. Calls appear here as they come in through your tracking numbers.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="min-w-full text-sm">
              <thead>
                <tr className="bg-muted/50 text-left text-xs font-medium text-muted-foreground">
                  <th className="px-3 py-2">Phone</th>
                  <th className="px-3 py-2">Name</th>
                  <th className="px-3 py-2">Reason</th>
                  <th className="px-3 py-2">Department</th>
                  <th className="px-3 py-2">Duration</th>
                  <th className="px-3 py-2">Time</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {calls.map((call) => (
                  <tr key={call.id} className="hover:bg-muted/30 transition-colors">
                    <td className="px-3 py-2 font-mono text-xs whitespace-nowrap">
                      {call.caller_phone
                        ? call.caller_phone.replace(/^\+1(\d{3})(\d{3})(\d{4})$/, "($1) $2-$3")
                        : "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {call.caller_name || <span className="text-muted-foreground">Unknown</span>}
                    </td>
                    <td className="px-3 py-2 max-w-[200px] truncate text-muted-foreground">
                      {call.summary || call.call_category || "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {call.routed_to ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-blue-50 dark:bg-blue-950 px-2 py-0.5 text-xs font-medium text-blue-700 dark:text-blue-300">
                          {call.routed_to}
                        </span>
                      ) : (
                        <span className="text-muted-foreground text-xs">Unrouted</span>
                      )}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      {call.duration_s != null ? (
                        <span className="inline-flex items-center gap-1">
                          <Clock size={11} />
                          {Math.floor(call.duration_s / 60)}:{String(call.duration_s % 60).padStart(2, "0")}
                        </span>
                      ) : "—"}
                    </td>
                    <td className="px-3 py-2 text-xs text-muted-foreground whitespace-nowrap">
                      {new Date(call.created_at).toLocaleString("en-US", {
                        month: "short", day: "numeric",
                        hour: "numeric", minute: "2-digit", hour12: true,
                      })}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CollapsibleSection>
    </div>
  );
}

// ── Sub-components ──

function KpiCard({ icon, label, value, color }: { icon: React.ReactNode; label: string; value: string | number; color?: string }) {
  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">{icon} {label}</div>
        <p className={cn("mt-1 text-2xl font-bold", color)}>{value}</p>
      </CardContent>
    </Card>
  );
}

function CollapsibleSection({
  title, defaultOpen = false, children, action,
}: {
  title: string; defaultOpen?: boolean; children: React.ReactNode; action?: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between px-4 py-3">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex flex-1 items-center gap-2 text-left"
          >
            <h2 className="text-sm font-semibold">{title}</h2>
            <ChevronDown size={14} className={cn("text-muted-foreground transition-transform duration-200", open && "rotate-180")} />
          </button>
          {action}
        </div>
        {open && <div className="border-t border-border">{children}</div>}
      </CardContent>
    </Card>
  );
}
