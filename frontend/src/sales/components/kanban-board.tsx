import { useNavigate } from "react-router-dom";
import { useState, useRef, useEffect } from "react";
import { PhoneIncoming, User, Trophy, ChevronRight, Loader2, UserPlus } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { cn, timeAgo } from "@/shared/lib/utils";
import { ScoreBadge } from "@/shared/components/ui/score-badge";
import { formatDuration } from "@/shared/lib/format";
import { qualifyProspect, convertToJob, assignLead, type ProspectItem, type CustomerItem, type JobItem } from "@/sales/api/sales";
import { salesKeys, opsKeys } from "@/shared/lib/query-keys";
import { usePermissions } from "@/shared/hooks/use-permissions";
import { listTeamMembers } from "@/admin/api/team";

interface KanbanBoardProps {
  bizId: string;
  prospects: ProspectItem[];
  leads: CustomerItem[];
  jobs: JobItem[];
  isLoading: boolean;
}

const COLUMN = "flex-1 min-w-[240px] max-w-sm";
const CARD = "rounded-xl border border-border bg-card p-3 shadow-sm hover:shadow-md transition-shadow cursor-pointer select-none";

// ── Column header ──
function ColHeader({
  icon, label, count, color, stat,
}: {
  icon: React.ReactNode;
  label: string;
  count: number;
  color: string;
  stat?: string;
}) {
  return (
    <div className="mb-3 flex items-center gap-2">
      <div className={cn("flex h-6 w-6 items-center justify-center rounded-md text-white", color)}>
        {icon}
      </div>
      <span className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">{label}</span>
      <span className="ml-auto rounded-full bg-muted px-1.5 py-0.5 text-[10px] font-semibold text-muted-foreground">{count}</span>
      {stat && (
        <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-[10px] font-semibold text-green-700 dark:bg-green-900/40 dark:text-green-300">
          {stat}
        </span>
      )}
    </div>
  );
}

// ── Prospect card (unreviewed calls) ──
function ProspectKanbanCard({ item, bizId }: { item: ProspectItem; bizId: string }) {
  const qc = useQueryClient();
  const qualify = useMutation({
    mutationFn: () => qualifyProspect(bizId, item.interaction_id, "lead"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: salesKeys.prospects(bizId) });
      qc.invalidateQueries({ queryKey: salesKeys.leads(bizId) });
    },
  });
  return (
    <div className={CARD}>
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <p className="text-sm font-medium leading-tight">{item.caller_name || "Unknown"}</p>
        <ScoreBadge score={item.score} />
      </div>
      {item.call_summary && (
        <p className="text-[11px] text-muted-foreground line-clamp-2 mb-2">{item.call_summary}</p>
      )}
      <div className="flex items-center justify-between">
        <span className="text-[10px] text-muted-foreground">
          {item.duration_s ? formatDuration(item.duration_s) : timeAgo(item.created_at)}
        </span>
        <button
          type="button"
          onClick={() => qualify.mutate()}
          disabled={qualify.isPending}
          className="flex items-center gap-0.5 rounded-md bg-primary/10 px-2 py-0.5 text-[10px] font-semibold text-primary hover:bg-primary/20 transition-colors disabled:opacity-50"
        >
          {qualify.isPending ? <Loader2 size={9} className="animate-spin" /> : <>Lead <ChevronRight size={9} /></>}
        </button>
      </div>
    </div>
  );
}

// ── Lead card (qualified, not yet converted) ──
function LeadKanbanCard({
  item,
  bizId,
  teamMembers,
  canAssign,
}: {
  item: CustomerItem;
  bizId: string;
  teamMembers: { user_id: string; full_name: string | null; email: string }[];
  canAssign: boolean;
}) {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [assignOpen, setAssignOpen] = useState(false);
  const assignRef = useRef<HTMLDivElement>(null);

  // Close assign dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (assignRef.current && !assignRef.current.contains(e.target as Node)) {
        setAssignOpen(false);
      }
    }
    if (assignOpen) document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [assignOpen]);

  const convert = useMutation({
    mutationFn: () => convertToJob(bizId, item.id, item.call_summary || item.full_name || "New Job"),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: salesKeys.leads(bizId) });
      qc.invalidateQueries({ queryKey: opsKeys.jobs(bizId) });
    },
  });

  const assign = useMutation({
    mutationFn: (userId: string | null) => assignLead(bizId, item.id, userId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: salesKeys.leads(bizId) });
      setAssignOpen(false);
    },
  });

  return (
    <div className={cn(CARD)} onClick={() => navigate(`/contacts/${item.id}`)}>
      <div className="flex items-start justify-between gap-2 mb-1.5">
        <p className="text-sm font-medium leading-tight">{item.full_name || "Unknown"}</p>
        <ScoreBadge score={item.score} />
      </div>
      {item.call_summary && (
        <p className="text-[11px] text-muted-foreground line-clamp-2 mb-1.5">{item.call_summary}</p>
      )}
      {/* Assigned rep */}
      {item.assigned_user_name && (
        <p className="text-[10px] text-primary font-medium mb-1.5">
          Assigned: {item.assigned_user_name}
        </p>
      )}
      <div className="flex items-center justify-between gap-1">
        <span className="text-[10px] font-mono text-muted-foreground truncate">{item.phone || ""}</span>
        <div className="flex items-center gap-1 shrink-0">
          {/* Assign button */}
          {canAssign && (
            <div ref={assignRef} className="relative" onClick={(e) => e.stopPropagation()}>
              <button
                type="button"
                onClick={() => setAssignOpen((v) => !v)}
                className="flex items-center gap-0.5 rounded-md bg-muted px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground hover:bg-muted/80 transition-colors"
                title="Assign rep"
              >
                <UserPlus size={9} />
              </button>
              {assignOpen && (
                <div className="absolute bottom-full right-0 mb-1 z-50 w-44 rounded-xl border border-border bg-card shadow-lg overflow-hidden">
                  <div className="px-2.5 py-1.5 text-[9px] font-semibold uppercase tracking-wider text-muted-foreground border-b border-border">
                    Assign to
                  </div>
                  {item.assigned_to && (
                    <button
                      type="button"
                      onClick={() => assign.mutate(null)}
                      className="w-full px-2.5 py-1.5 text-left text-[11px] text-muted-foreground hover:bg-muted transition-colors"
                    >
                      Unassign
                    </button>
                  )}
                  {teamMembers.map((m) => (
                    <button
                      key={m.user_id}
                      type="button"
                      onClick={() => assign.mutate(m.user_id)}
                      className={cn(
                        "w-full px-2.5 py-1.5 text-left text-[11px] hover:bg-muted transition-colors",
                        item.assigned_to === m.user_id ? "text-primary font-medium" : "text-foreground",
                      )}
                    >
                      {m.full_name || m.email}
                    </button>
                  ))}
                </div>
              )}
            </div>
          )}
          <button
            type="button"
            onClick={(e) => { e.stopPropagation(); convert.mutate(); }}
            disabled={convert.isPending}
            className="flex items-center gap-0.5 rounded-md bg-green-100 px-2 py-0.5 text-[10px] font-semibold text-green-700 hover:bg-green-200 transition-colors disabled:opacity-50 dark:bg-green-900/40 dark:text-green-300"
          >
            {convert.isPending ? <Loader2 size={9} className="animate-spin" /> : <>Convert <ChevronRight size={9} /></>}
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Won card (converted to job) ──
function WonKanbanCard({ item }: { item: JobItem }) {
  const navigate = useNavigate();
  return (
    <div className={cn(CARD, "opacity-85")} onClick={() => navigate(`/contacts/${item.contact_id}`)}>
      <p className="text-sm font-medium leading-tight mb-1">{item.title}</p>
      <p className="text-[11px] text-muted-foreground mb-1.5">{item.contact_name || "—"}</p>
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold text-green-600">
          {item.amount_billed != null
            ? `$${item.amount_billed.toLocaleString()}`
            : item.amount_quoted != null
              ? `$${item.amount_quoted.toLocaleString()}`
              : "—"}
        </span>
        <span className="text-[10px] text-muted-foreground">{timeAgo(item.created_at)}</span>
      </div>
    </div>
  );
}

// ── Main board ──────────────────────────────────────────
export function KanbanBoard({ bizId, prospects, leads, jobs, isLoading }: KanbanBoardProps) {
  const { can } = usePermissions();
  const canAssign = can("assign_leads");

  // Load team members for assign dropdown (only if user can assign)
  const { data: teamMembers = [] } = useQuery({
    queryKey: ["team-members", bizId],
    queryFn: () => listTeamMembers(bizId),
    enabled: !!bizId && canAssign,
    staleTime: 2 * 60_000,
  });

  const wonJobs = jobs.filter((j) => j.status === "completed" || j.status === "billed");

  // Conversion rate: won / (won + active leads) — excludes unreviewed (not yet qualified)
  const totalQualified = wonJobs.length + leads.length;
  const conversionRate = totalQualified > 0
    ? `${Math.round((wonJobs.length / totalQualified) * 100)}%`
    : null;

  if (isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="flex gap-4 overflow-x-auto pb-4">
      {/* Unreviewed */}
      <div className={COLUMN}>
        <ColHeader icon={<PhoneIncoming size={12} />} label="Unreviewed" count={prospects.length} color="bg-blue-500" />
        <div className="space-y-2">
          {prospects.length === 0
            ? <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">No new calls</p>
            : prospects.map((p) => <ProspectKanbanCard key={p.interaction_id} item={p} bizId={bizId} />)
          }
        </div>
      </div>

      {/* Leads */}
      <div className={COLUMN}>
        <ColHeader icon={<User size={12} />} label="Leads" count={leads.length} color="bg-violet-500" />
        <div className="space-y-2">
          {leads.length === 0
            ? <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">No active leads</p>
            : leads.map((l) => (
                <LeadKanbanCard
                  key={l.id}
                  item={l}
                  bizId={bizId}
                  teamMembers={teamMembers}
                  canAssign={canAssign}
                />
              ))
          }
        </div>
      </div>

      {/* Won */}
      <div className={COLUMN}>
        <ColHeader
          icon={<Trophy size={12} />}
          label="Won"
          count={wonJobs.length}
          color="bg-green-500"
          stat={conversionRate ?? undefined}
        />
        <div className="space-y-2">
          {wonJobs.length === 0
            ? <p className="rounded-xl border border-dashed border-border px-3 py-6 text-center text-xs text-muted-foreground">No won jobs yet</p>
            : wonJobs.slice(0, 20).map((j) => <WonKanbanCard key={j.id} item={j} />)
          }
        </div>
      </div>
    </div>
  );
}
