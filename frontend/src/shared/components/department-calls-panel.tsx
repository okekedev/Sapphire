/**
 * DepartmentCallsPanel — Reusable component that shows calls routed to a specific department.
 *
 * Embeddable in any department tab (Sales, Operations, Finance, etc.)
 * Shows calls with:
 *   - AI analysis badge (department_context + call_category)
 *   - Human review actions (confirm department, re-route)
 *   - "Process with AI" button to invoke department employee
 *   - Call details (summary, score, duration, recording)
 */
import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Phone,
  PhoneIncoming,
  PhoneOutgoing,
  Clock,
  Bot,
  ArrowRightLeft,
  Loader2,
  ChevronDown,
  ChevronRight,
  CheckCircle2,
  Tag,
} from "lucide-react";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listDepartmentCalls,
  rerouteCall,
  processCallWithAI,
  dispositionCall,
  type CallLogItem,
} from "@/marketing/api/tracking-routing";

// ── Helpers ──

function formatDuration(seconds: number | null): string {
  if (!seconds) return "—";
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function formatCategory(cat: string | null): string {
  if (!cat) return "Uncategorized";
  return cat
    .replace(/_/g, " ")
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

const DEPARTMENTS = ["Sales", "Operations", "Finance", "Marketing", "Admin"];

const CATEGORY_COLORS: Record<string, string> = {
  inquiry: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  quote_request: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",
  new_customer: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  job_request: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  service_request: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  payment_inquiry: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300",
  complaint: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300",
  general_inquiry: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400",
};

// ── Call Row (expandable) ──

function CallRow({
  call,
  businessId,
  department,
}: {
  call: CallLogItem;
  businessId: string;
  department: string;
}) {
  const [expanded, setExpanded] = useState(false);
  const [showReroute, setShowReroute] = useState(false);
  const queryClient = useQueryClient();

  const rerouteMutation = useMutation({
    mutationFn: (dept: string) => rerouteCall(businessId, call.id, dept),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["department-calls"] });
      setShowReroute(false);
    },
  });

  const processMutation = useMutation({
    mutationFn: () => processCallWithAI(businessId, call.id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["department-calls"] });
    },
  });

  const dispositionMutation = useMutation({
    mutationFn: (disp: string) => dispositionCall(businessId, call.id, disp),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["department-calls"] });
    },
  });

  const catColor = CATEGORY_COLORS[call.call_category || ""] || CATEGORY_COLORS.general_inquiry;

  return (
    <div className="border-b transition hover:bg-muted/30">
      {/* Main row */}
      <div
        className="flex items-center gap-3 px-4 py-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Expand icon */}
        {expanded ? (
          <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        ) : (
          <ChevronRight className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
        )}

        {/* Direction icon */}
        <div className="shrink-0">
          {call.status === "dropped" ? (
            <Phone className="h-4 w-4 text-red-500" />
          ) : call.routed_to ? (
            <PhoneIncoming className="h-4 w-4 text-emerald-500" />
          ) : (
            <PhoneOutgoing className="h-4 w-4 text-blue-500" />
          )}
        </div>

        {/* Caller info */}
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="font-medium text-sm truncate">
              {call.caller_name || call.caller_phone || "Unknown"}
            </span>
            {call.call_category && (
              <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold ${catColor}`}>
                <Tag className="h-2.5 w-2.5" />
                {formatCategory(call.call_category)}
              </span>
            )}
            {call.ai_processed && (
              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300 px-2 py-0.5 text-[10px] font-semibold">
                <CheckCircle2 className="h-2.5 w-2.5" />
                AI Processed
              </span>
            )}
          </div>
          {call.summary && (
            <p className="text-xs text-muted-foreground truncate mt-0.5">
              {call.summary}
            </p>
          )}
        </div>

        {/* Score */}
        {call.score && (
          <span className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold ${
            call.score.toLowerCase().includes("hot")
              ? "bg-red-100 text-red-700"
              : call.score.toLowerCase().includes("warm")
              ? "bg-amber-100 text-amber-700"
              : "bg-blue-100 text-blue-700"
          }`}>
            {call.score.split("—")[0].trim()}
          </span>
        )}

        {/* Duration */}
        <span className="shrink-0 text-xs text-muted-foreground flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatDuration(call.duration_s)}
        </span>

        {/* Date */}
        <span className="shrink-0 text-[11px] text-muted-foreground w-28 text-right">
          {formatDate(call.created_at)}
        </span>
      </div>

      {/* Expanded details */}
      {expanded && (
        <div className="px-4 pb-4 pl-12 space-y-3">
          {/* Call details */}
          <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs">
            <div><span className="text-muted-foreground">Phone:</span> <span className="font-mono">{call.caller_phone || "—"}</span></div>
            <div><span className="text-muted-foreground">Campaign:</span> {call.campaign_name || "Direct"}</div>
            <div><span className="text-muted-foreground">Department:</span> {call.department_context || call.routed_to || "Unrouted"}</div>
            <div><span className="text-muted-foreground">Category:</span> {formatCategory(call.call_category)}</div>
            {call.suggested_action && (
              <div className="col-span-2"><span className="text-muted-foreground">Suggested:</span> {call.suggested_action}</div>
            )}
            {call.next_step && (
              <div className="col-span-2"><span className="text-muted-foreground">Next step:</span> {call.next_step}</div>
            )}
          </div>

          {/* AI processing output */}
          {call.ai_processed && call.ai_process_output && (
            <div className="rounded-lg bg-emerald-50 dark:bg-emerald-950/30 border border-emerald-200 dark:border-emerald-800 p-3">
              <div className="flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300 mb-1.5">
                <Bot className="h-3.5 w-3.5" />
                AI Employee Output
              </div>
              <p className="text-xs text-emerald-800 dark:text-emerald-200 whitespace-pre-wrap">
                {call.ai_process_output}
              </p>
            </div>
          )}

          {/* Recording */}
          {call.recording_url && (
            <div>
              <audio controls className="h-8 w-full max-w-md" preload="none">
                <source src={call.recording_url} type="audio/mpeg" />
              </audio>
            </div>
          )}

          {/* Action buttons */}
          <div className="flex items-center gap-2 pt-1">
            {/* Process with AI */}
            {!call.ai_processed && (
              <Button
                size="sm"
                variant="default"
                className="h-7 text-xs gap-1.5"
                onClick={(e) => { e.stopPropagation(); processMutation.mutate(); }}
                disabled={processMutation.isPending}
              >
                {processMutation.isPending ? (
                  <Loader2 className="h-3 w-3 animate-spin" />
                ) : (
                  <Bot className="h-3 w-3" />
                )}
                Process with AI
              </Button>
            )}

            {/* Re-route */}
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs gap-1.5"
              onClick={(e) => { e.stopPropagation(); setShowReroute(!showReroute); }}
            >
              <ArrowRightLeft className="h-3 w-3" />
              Re-route
            </Button>

            {/* Disposition */}
            {call.disposition === "unreviewed" && (
              <>
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 text-xs"
                  onClick={(e) => { e.stopPropagation(); dispositionMutation.mutate("lead"); }}
                >
                  Mark Lead
                </Button>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-muted-foreground"
                  onClick={(e) => { e.stopPropagation(); dispositionMutation.mutate("spam"); }}
                >
                  Spam
                </Button>
              </>
            )}
          </div>

          {/* Re-route dropdown */}
          {showReroute && (
            <div className="flex items-center gap-2">
              <span className="text-xs text-muted-foreground">Move to:</span>
              {DEPARTMENTS.filter((d) => d !== department).map((d) => (
                <Button
                  key={d}
                  size="sm"
                  variant="outline"
                  className="h-6 text-[11px] px-2"
                  onClick={(e) => { e.stopPropagation(); rerouteMutation.mutate(d); }}
                  disabled={rerouteMutation.isPending}
                >
                  {d}
                </Button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Main Panel ──

export function DepartmentCallsPanel({
  department,
  maxHeight = "500px",
}: {
  department: string;
  maxHeight?: string;
}) {
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id;

  const callsQuery = useQuery({
    queryKey: ["department-calls", businessId, department],
    queryFn: () => listDepartmentCalls(businessId!, department, { limit: 50 }),
    enabled: !!businessId,
    refetchInterval: 30000, // Refresh every 30s
  });

  if (!businessId) return null;

  const calls = callsQuery.data?.calls || [];
  const total = callsQuery.data?.total || 0;

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <div className="flex items-center gap-2">
            <Phone className="h-4 w-4 text-muted-foreground" />
            <h3 className="text-sm font-semibold">
              {department} Calls
              <span className="ml-2 text-xs font-normal text-muted-foreground">
                {total} total
              </span>
            </h3>
          </div>
          {callsQuery.isRefetching && (
            <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
          )}
        </div>

        {callsQuery.isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : calls.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No calls routed to {department} yet. Inbound calls will appear here
            after AI analysis routes them to this department.
          </div>
        ) : (
          <div className="overflow-y-auto" style={{ maxHeight }}>
            {calls.map((call) => (
              <CallRow
                key={call.id}
                call={call}
                businessId={businessId}
                department={department}
              />
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
