import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PhoneCall, Target, Wrench, Phone, Mail, FileText, Loader2 } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { PageHeader } from "@/shared/components/page-header";
import { Card, CardContent } from "@/shared/components/ui/card";
import { getDashboardSummary, type DashboardActivity } from "@/shared/api/dashboard";
import { cn, timeAgo } from "@/shared/lib/utils";
import { dashboardKeys } from "@/shared/lib/query-keys";


function ActivityIcon({ type }: { type: string }) {
  const cls = "h-3.5 w-3.5";
  if (type === "call") return <PhoneCall className={cn(cls, "text-blue-500")} />;
  if (type === "email") return <Mail className={cn(cls, "text-violet-500")} />;
  if (type === "note") return <FileText className={cn(cls, "text-amber-500")} />;
  return <Phone className={cn(cls, "text-muted-foreground")} />;
}

function ActivityFeed({ items }: { items: DashboardActivity[] }) {
  if (items.length === 0) {
    return (
      <p className="py-6 text-center text-sm text-muted-foreground">No recent activity</p>
    );
  }
  return (
    <div className="divide-y divide-border">
      {items.map((item) => {
        const meta = item.metadata as Record<string, unknown> | null;
        const summary = (meta?.summary as string) ?? item.subject ?? item.type;
        return (
          <div key={item.interaction_id} className="flex items-start gap-3 py-3">
            <div className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-muted">
              <ActivityIcon type={item.type} />
            </div>
            <div className="min-w-0 flex-1">
              <p className="truncate text-sm font-medium">
                {item.contact_name ?? "Unknown caller"}
              </p>
              {summary && (
                <p className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">{summary}</p>
              )}
            </div>
            <span className="shrink-0 text-[11px] text-muted-foreground">
              {timeAgo(item.created_at)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function DashboardPage() {
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const user = useAppStore((s) => s.user);

  const { data, isLoading } = useQuery({
    queryKey: dashboardKeys.summary(businessId),
    queryFn: () => getDashboardSummary(businessId),
    enabled: !!businessId,
    refetchInterval: 30_000,
  });

  const greeting = () => {
    const h = new Date().getHours();
    if (h < 12) return "Good morning";
    if (h < 17) return "Good afternoon";
    return "Good evening";
  };

  const actionCards = [
    {
      icon: <PhoneCall className="h-5 w-5 text-blue-500" />,
      label: "Unreviewed Calls",
      count: data?.unreviewed_calls ?? 0,
      description: "New calls waiting for review",
      action: "Review",
      href: "/sales",
      color: "border-blue-200 dark:border-blue-900",
    },
    {
      icon: <Target className="h-5 w-5 text-violet-500" />,
      label: "Open Leads",
      count: data?.open_leads ?? 0,
      description: "Prospects not yet converted",
      action: "Follow Up",
      href: "/sales",
      color: "border-violet-200 dark:border-violet-900",
    },
    {
      icon: <Wrench className="h-5 w-5 text-amber-500" />,
      label: "Jobs Overdue",
      count: data?.overdue_jobs ?? 0,
      description: "Jobs open for more than 7 days",
      action: "View Jobs",
      href: "/jobs",
      color: "border-amber-200 dark:border-amber-900",
    },
  ];

  return (
    <div className="space-y-6 p-4 md:p-6">
      {/* Greeting */}
      <div>
        <h1 className="text-xl font-semibold md:text-2xl">
          {greeting()}{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-0.5 text-sm text-muted-foreground">
          {new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" })}
        </p>
      </div>

      {/* Action cards */}
      {isLoading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {actionCards.map((card) => (
            <Card
              key={card.label}
              className={cn("border transition-shadow hover:shadow-md", card.color)}
            >
              <CardContent className="p-5">
                <div className="flex items-start justify-between">
                  <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-muted">
                    {card.icon}
                  </div>
                  <span className="text-2xl font-bold tabular-nums">{card.count}</span>
                </div>
                <p className="mt-3 text-sm font-medium">{card.label}</p>
                <p className="mt-0.5 text-xs text-muted-foreground">{card.description}</p>
                <button
                  type="button"
                  onClick={() => navigate(card.href)}
                  className="mt-4 w-full rounded-lg border border-border bg-background px-3 py-1.5 text-xs font-medium transition-colors hover:bg-muted"
                >
                  {card.action}
                </button>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Recent activity */}
      <div>
        <h2 className="mb-3 text-sm font-semibold text-muted-foreground uppercase tracking-wider">
          Recent Activity
        </h2>
        <Card>
          <CardContent className="px-4 py-2">
            {isLoading ? (
              <div className="flex justify-center py-6">
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              </div>
            ) : (
              <ActivityFeed items={data?.recent_activity ?? []} />
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
