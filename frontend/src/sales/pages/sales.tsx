import { useState, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Phone,
  MessageSquare,
  ChevronDown,
  Send,
  Loader2,
  CheckCircle2,
  XCircle,
  ArrowRight,
  Clock,
  User,
  Briefcase,
  Pencil,
  Plus,
  X,
  PhoneIncoming,
  UserPlus,
  ClipboardList,
  ChevronRight,
  MoreHorizontal,
  Download,
  DollarSign,
  StickyNote,
  Save,
  FileText,
  RefreshCw,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PageHeader } from "@/shared/components/page-header";
import { useAppStore } from "@/shared/stores/app-store";
import { listEmployees, listDepartments } from "@/shared/api/organization";
import { sendEmployeeChat, type ChatMessage } from "@/shared/api/chat";
import {
  listCustomers,
  createCustomer,
  updateCustomer,
  listProspects,
  qualifyProspect,
  convertToJob,
  getPipelineSummary,
  listReviewed,
  type ProspectItem,
  type CustomerItem,
  type PipelineSummary,
  type ReviewItem,
} from "@/sales/api/sales";

// ── Helpers ──

/** Strip priority/urgency prefixes like "HIGH PRIORITY:", "URGENT:", etc. */
function stripPriority(text: string): string {
  return text.replace(/^(HIGH PRIORITY|PRIORITY|URGENT|LOW PRIORITY|MEDIUM PRIORITY)\s*[:—\-]\s*/i, "").trim();
}

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

function formatDateShort(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
  });
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  return `${days}d ago`;
}

// ── Main Page ──

export default function SalesPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id;
  const queryClient = useQueryClient();

  const [chatOpen, setChatOpen] = useState(false);
  const [chatPrefill, setChatPrefill] = useState("");
  const [callsOpen, setCallsOpen] = useState(false);
  const [leadsOpen, setLeadsOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [showAddLead, setShowAddLead] = useState(false);
  const [newLead, setNewLead] = useState({ full_name: "", phone: "", email: "", notes: "" });

  const [isRefreshing, setIsRefreshing] = useState(false);

  // Review section state
  const [reviewFilter, setReviewFilter] = useState<string | undefined>();
  const [reviewLimit, setReviewLimit] = useState(5);

  // ── Queries ──

  const pipelineQuery = useQuery({
    queryKey: ["sales-pipeline-summary", businessId],
    queryFn: () => getPipelineSummary(businessId!),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  // Prefetch pipeline data so it's instant when section opens
  const prospectsQuery = useQuery({
    queryKey: ["sales-prospects", businessId],
    queryFn: () => listProspects(businessId!),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const leadsQuery = useQuery({
    queryKey: ["sales-leads", businessId],
    queryFn: () => listCustomers(businessId!, { status: "prospect", limit: 100 }),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  // Review — lazy loaded, paginated
  const reviewQuery = useQuery({
    queryKey: ["sales-review", businessId, reviewFilter, reviewLimit],
    queryFn: () => listReviewed(businessId!, { disposition: reviewFilter, limit: reviewLimit }),
    enabled: !!businessId && reviewOpen,
  });

  // Find Sales department + head employee
  const departmentsQuery = useQuery({
    queryKey: ["sales-departments", businessId],
    queryFn: () => listDepartments(businessId!),
    enabled: !!businessId,
  });

  const salesDept = departmentsQuery.data?.find((d) => d.name === "Sales");

  const employeesQuery = useQuery({
    queryKey: ["sales-employees", businessId, salesDept?.id],
    queryFn: () => listEmployees({ business_id: businessId!, department_id: salesDept!.id }),
    enabled: !!businessId && !!salesDept?.id,
  });

  const jordan = employeesQuery.data?.find((e) => e.is_head);

  // ── Mutations ──

  const qualifyMutation = useMutation({
    mutationFn: (args: { interactionId: string; decision: "lead" | "no_lead"; reason?: string; leadSummary?: string }) =>
      qualifyProspect(businessId!, args.interactionId, args.decision, args.reason, args.leadSummary),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-prospects"] });
      queryClient.invalidateQueries({ queryKey: ["sales-leads"] });
      queryClient.invalidateQueries({ queryKey: ["sales-pipeline-summary"] });
      queryClient.invalidateQueries({ queryKey: ["sales-review"] });
    },
  });

  const convertMutation = useMutation({
    mutationFn: (args: { contactId: string; title: string; description?: string; estimate?: number }) =>
      convertToJob(businessId!, args.contactId, args.title, args.description, args.estimate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-leads"] });
      queryClient.invalidateQueries({ queryKey: ["sales-pipeline-summary"] });
      queryClient.invalidateQueries({ queryKey: ["sales-review"] });
      // Cross-department: new job created → invalidate Operations queries
      queryClient.invalidateQueries({ queryKey: ["ops-jobs"] });
      queryClient.invalidateQueries({ queryKey: ["ops-summary"] });
      queryClient.invalidateQueries({ queryKey: ["ops-customers"] });
    },
  });

  const updateNotesMutation = useMutation({
    mutationFn: (args: { contactId: string; notes: string }) =>
      updateCustomer(businessId!, args.contactId, { notes: args.notes }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-leads"] });
    },
  });

  const createLeadMutation = useMutation({
    mutationFn: () =>
      createCustomer(businessId!, {
        full_name: newLead.full_name,
        phone: newLead.phone || undefined,
        email: newLead.email || undefined,
        status: "prospect",
        source_channel: "manual",
        notes: newLead.notes || undefined,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sales-leads"] });
      queryClient.invalidateQueries({ queryKey: ["sales-pipeline-summary"] });
      setShowAddLead(false);
      setNewLead({ full_name: "", phone: "", email: "", notes: "" });
    },
  });

  if (!businessId) {
    return (
      <div className="p-6">
        <PageHeader title="Sales" description="Select a business to view sales pipeline" />
      </div>
    );
  }

  const pipeline = pipelineQuery.data;
  const prospects = prospectsQuery.data?.prospects || [];
  const leads = leadsQuery.data?.customers || [];
  const reviewItems = reviewQuery.data?.items || [];
  const reviewTotal = reviewQuery.data?.total || 0;

  return (
    <div className="space-y-6 p-6">
      <div className="flex items-center justify-between">
        <PageHeader
          title="Sales"
          description="Inbound call pipeline — qualify leads and convert to jobs"
        />
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={async () => {
            setIsRefreshing(true);
            await Promise.all([
              queryClient.invalidateQueries({ queryKey: ["sales-prospects"] }),
              queryClient.invalidateQueries({ queryKey: ["sales-leads"] }),
              queryClient.invalidateQueries({ queryKey: ["sales-pipeline-summary"] }),
              queryClient.invalidateQueries({ queryKey: ["sales-review"] }),
            ]);
            setTimeout(() => setIsRefreshing(false), 600);
          }}
          disabled={isRefreshing}
          title="Refresh"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
        </Button>
      </div>

      {/* ═══ PIPELINE KPIs ═══ */}
      <div className="grid grid-cols-3 gap-4">
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
              <Phone className="h-3.5 w-3.5" /> New
            </div>
            <p className="mt-1 text-2xl font-bold">{pipeline?.new_count || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
              <User className="h-3.5 w-3.5" /> Leads
            </div>
            <p className="mt-1 text-2xl font-bold">{pipeline?.lead_count || 0}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
              <Briefcase className="h-3.5 w-3.5" /> Converted
            </div>
            <p className="mt-1 text-2xl font-bold">{pipeline?.converted_count || 0}</p>
          </CardContent>
        </Card>
      </div>

      {/* ═══ CHAT — JORDAN ═══ */}
      <CollapsibleSection
        icon={<MessageSquare size={18} />}
        title={jordan ? `Chat — ${jordan.name}` : "Chat — Sales Director"}
        subtitle={jordan ? jordan.title : undefined}
        open={chatOpen}
        onToggle={() => setChatOpen((v) => !v)}
      >
        {jordan ? (
          <ChatSection
            businessId={businessId}
            employeeId={jordan.id}
            employeeName={jordan.name}
            prefill={chatPrefill}
            onPrefillConsumed={() => setChatPrefill("")}
          />
        ) : (
          <p className="py-4 text-sm text-muted-foreground">
            No Sales director found. Create a Sales department head to enable chat.
          </p>
        )}
      </CollapsibleSection>

      {/* ═══ CALLS — UNREVIEWED INBOUND ═══ */}
      <CollapsibleSection
        icon={<Phone size={18} />}
        title="Calls"
        subtitle={`${prospects.length} unreviewed`}
        open={callsOpen}
        onToggle={() => setCallsOpen((v) => !v)}
      >
        <div className="space-y-3">
          {prospectsQuery.isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : prospects.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No unreviewed calls
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
              {prospects.map((p) => (
                <ProspectCard
                  key={p.interaction_id}
                  prospect={p}
                  onQualify={(decision, reason, leadSummary) =>
                    qualifyMutation.mutate({
                      interactionId: p.interaction_id,
                      decision,
                      reason,
                      leadSummary,
                    })
                  }
                  isPending={qualifyMutation.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* ═══ LEADS — QUALIFIED PROSPECTS ═══ */}
      <CollapsibleSection
        icon={<User size={18} />}
        title="Leads"
        subtitle={`${leads.length} active`}
        open={leadsOpen}
        onToggle={() => setLeadsOpen((v) => !v)}
        action={
          <Button
            size="sm"
            variant="ghost"
            className="h-7 text-xs"
            onClick={(e) => {
              e.stopPropagation();
              setShowAddLead(!showAddLead);
            }}
          >
            {showAddLead ? <X className="h-3.5 w-3.5" /> : <Plus className="h-3.5 w-3.5" />}
          </Button>
        }
      >
        <div className="space-y-3">
          {/* Manual Add Lead form */}
          {showAddLead && (
            <Card>
              <CardContent className="p-4 space-y-3">
                <p className="text-[11px] font-semibold text-muted-foreground uppercase">Add Lead Manually</p>
                <Input
                  value={newLead.full_name}
                  onChange={(e) => setNewLead({ ...newLead, full_name: e.target.value })}
                  placeholder="Name *"
                  className="text-xs h-8"
                />
                <Input
                  value={newLead.email}
                  onChange={(e) => setNewLead({ ...newLead, email: e.target.value })}
                  placeholder="Email"
                  className="text-xs h-8"
                />
                <Input
                  value={newLead.phone}
                  onChange={(e) => setNewLead({ ...newLead, phone: e.target.value })}
                  placeholder="Phone"
                  className="text-xs h-8 font-mono"
                />
                <textarea
                  value={newLead.notes}
                  onChange={(e) => setNewLead({ ...newLead, notes: e.target.value })}
                  placeholder="Notes / context"
                  className="w-full rounded-md border bg-background px-3 py-2 text-xs min-h-[50px] resize-none outline-none focus:border-primary"
                />
                <Button
                  size="sm"
                  className="h-7 w-full text-xs"
                  onClick={() => createLeadMutation.mutate()}
                  disabled={!newLead.full_name.trim() || createLeadMutation.isPending}
                >
                  {createLeadMutation.isPending ? (
                    <Loader2 className="h-3 w-3 animate-spin" />
                  ) : (
                    <>
                      <Plus className="mr-1 h-3 w-3" /> Add Lead
                    </>
                  )}
                </Button>
              </CardContent>
            </Card>
          )}

          {leadsQuery.isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : leads.length === 0 && !showAddLead ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No active leads
              </CardContent>
            </Card>
          ) : (
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
              {leads.map((lead) => (
                <LeadCard
                  key={lead.id}
                  lead={lead}
                  businessId={businessId!}
                  employeeId={jordan?.id ?? ""}
                  onConvert={(title, description, estimate) =>
                    convertMutation.mutate({ contactId: lead.id, title, description, estimate })
                  }
                  onUpdateNotes={(notes) =>
                    updateNotesMutation.mutate({ contactId: lead.id, notes })
                  }
                  isPending={convertMutation.isPending || updateNotesMutation.isPending}
                />
              ))}
            </div>
          )}
        </div>
      </CollapsibleSection>

      {/* ═══ REVIEW — HISTORICAL DECISIONS ═══ */}
      <CollapsibleSection
        icon={<ClipboardList size={18} />}
        title="Review"
        subtitle={`${reviewTotal} reviewed`}
        open={reviewOpen}
        onToggle={() => setReviewOpen((v) => !v)}
      >
        <div className="space-y-4">
          {/* Filter pills + Export */}
          <div className="flex items-center justify-between">
            <div className="flex gap-1.5">
              {[
                { key: undefined, label: "All" },
                { key: "converted", label: "Converted" },
                { key: "lead", label: "Leads" },
                { key: "other", label: "No Lead" },
                { key: "no_conversion", label: "No Conversion" },
              ].map((f) => (
                <button
                  key={f.key || "all"}
                  onClick={() => { setReviewFilter(f.key); setReviewLimit(5); }}
                  className={cn(
                    "rounded-md px-2.5 py-1 text-[11px] font-medium transition",
                    reviewFilter === f.key
                      ? "bg-primary text-primary-foreground"
                      : "text-muted-foreground hover:bg-muted",
                  )}
                >
                  {f.label}
                </button>
              ))}
            </div>
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={() => exportReviewCSV(reviewItems)}
              disabled={reviewItems.length === 0}
            >
              <Download className="mr-1.5 h-3 w-3" /> Export CSV
            </Button>
          </div>

          {/* Review table */}
          {reviewQuery.isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
            </div>
          ) : reviewItems.length === 0 ? (
            <div className="py-8 text-center text-sm text-muted-foreground">
              No reviewed calls yet
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">Phone</th>
                    <th className="px-3 py-2 text-left">Call Outcome</th>
                    <th className="px-3 py-2 text-left">Lead Outcome</th>
                    <th className="px-3 py-2 text-left">Customer</th>
                    <th className="px-3 py-2 text-left">Context</th>
                    <th className="px-3 py-2 text-left">Date</th>
                  </tr>
                </thead>
                <tbody>
                  {reviewItems.map((item) => (
                    <ReviewRow key={item.interaction_id} item={item} />
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Load more */}
          {reviewItems.length < reviewTotal && (
            <div className="flex justify-center">
              <Button
                size="sm"
                variant="outline"
                className="text-xs"
                onClick={() => setReviewLimit((prev) => prev + 10)}
                disabled={reviewQuery.isFetching}
              >
                {reviewQuery.isFetching ? (
                  <Loader2 className="mr-1.5 h-3 w-3 animate-spin" />
                ) : (
                  <MoreHorizontal className="mr-1.5 h-3 w-3" />
                )}
                Load more ({reviewTotal - reviewItems.length} remaining)
              </Button>
            </div>
          )}
        </div>
      </CollapsibleSection>
    </div>
  );
}

// ── Collapsible Section ──

function CollapsibleSection({
  icon,
  title,
  subtitle,
  open,
  onToggle,
  action,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  subtitle?: string;
  open: boolean;
  onToggle: () => void;
  action?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-border bg-card">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between px-5 py-4 text-left transition-colors hover:bg-muted/50"
      >
        <span className="flex items-center gap-2.5">
          <span className="text-primary">{icon}</span>
          <span className="font-semibold">{title}</span>
          {subtitle && (
            <span className="text-xs text-muted-foreground">{subtitle}</span>
          )}
        </span>
        <span className="flex items-center gap-2">
          {action}
          <ChevronDown
            size={16}
            className={cn(
              "text-muted-foreground transition-transform duration-200",
              open && "rotate-180",
            )}
          />
        </span>
      </button>
      {open && <div className="border-t border-border px-5 py-5">{children}</div>}
    </div>
  );
}

// ── Chat Section (with prefill support) ──

function ChatSection({
  businessId,
  employeeId,
  employeeName,
  prefill,
  onPrefillConsumed,
}: {
  businessId: string;
  employeeId: string;
  employeeName: string;
  prefill?: string;
  onPrefillConsumed?: () => void;
}) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Handle prefill from pipeline cards
  useEffect(() => {
    if (prefill) {
      setInput(prefill);
      onPrefillConsumed?.();
    }
  }, [prefill, onPrefillConsumed]);

  const mutation = useMutation({
    mutationFn: (userMessage: string) =>
      sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages,
        user_message: userMessage,
      }),
    onSuccess: (data, userMessage) => {
      setMessages((prev) => [
        ...prev,
        { role: "user", content: userMessage },
        { role: "assistant", content: data.content },
      ]);
    },
  });

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages, mutation.isPending]);

  const handleSend = () => {
    const trimmed = input.trim();
    if (!trimmed || mutation.isPending) return;
    setInput("");
    mutation.mutate(trimmed);
  };

  return (
    <div className="flex flex-col">
      <div ref={scrollRef} className="max-h-96 min-h-[200px] overflow-y-auto space-y-3 mb-4">
        {messages.length === 0 && !mutation.isPending && (
          <div className="flex flex-col items-center justify-center py-12 text-center">
            <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-primary/10">
              <MessageSquare size={20} className="text-primary" />
            </div>
            <p className="text-sm font-medium">Chat with {employeeName}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Discuss leads, get recommendations, or ask about pipeline strategy.
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div
            key={i}
            className={cn(
              "flex",
              msg.role === "user" ? "justify-end" : "justify-start",
            )}
          >
            <div
              className={cn(
                "max-w-[80%] rounded-lg px-4 py-2.5 text-sm leading-relaxed",
                msg.role === "user"
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted",
              )}
            >
              {msg.role === "assistant" && (
                <p className="mb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {employeeName}
                </p>
              )}
              {msg.role === "assistant" ? (
                <MarkdownMessage content={msg.content} />
              ) : (
                <p>{msg.content}</p>
              )}
            </div>
          </div>
        ))}

        {mutation.isPending && (
          <div className="flex justify-start">
            <div className="flex items-center gap-2 rounded-lg bg-muted px-4 py-3">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              <span className="text-xs text-muted-foreground">Thinking...</span>
            </div>
          </div>
        )}
      </div>

      <div className="flex gap-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleSend()}
          placeholder={`Ask ${employeeName}...`}
          className="text-sm"
          disabled={mutation.isPending}
        />
        <Button
          size="sm"
          onClick={handleSend}
          disabled={!input.trim() || mutation.isPending}
        >
          <Send className="h-3.5 w-3.5" />
        </Button>
      </div>
    </div>
  );
}

// ── Prospect Card (New column) ──

function ProspectCard({
  prospect,
  onQualify,
  onDiscuss,
  isPending,
}: {
  prospect: ProspectItem;
  onQualify: (decision: "lead" | "no_lead", reason?: string, leadSummary?: string) => void;
  isPending: boolean;
}) {
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);
  const [showNoLeadInput, setShowNoLeadInput] = useState(false);
  const [noLeadReason, setNoLeadReason] = useState(
    prospect.call_category === "spam" ? "Spam / robocall" : "",
  );

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <p className="font-semibold text-sm">{prospect.caller_name || "Unknown Caller"}</p>
            <p className="text-xs text-muted-foreground font-mono">{prospect.caller_phone || "—"}</p>
          </div>
          <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
            {prospect.duration_s != null && (
              <span className="flex items-center gap-1">
                <Clock className="h-3 w-3" /> {formatDuration(prospect.duration_s)}
              </span>
            )}
            <span>{timeAgo(prospect.created_at)}</span>
          </div>
        </div>

        {/* Transcript — expandable */}
        {prospect.transcript && (
          <div className="text-xs">
            <button
              onClick={() => setTranscriptExpanded(!transcriptExpanded)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors mb-1"
            >
              <FileText className="h-3 w-3" />
              <span>Transcript</span>
              <ChevronDown className={cn("h-3 w-3 transition-transform", transcriptExpanded && "rotate-180")} />
            </button>
            {transcriptExpanded && (
              <div className="rounded-md border bg-muted/30 p-3 max-h-[300px] overflow-y-auto">
                <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{prospect.transcript}</p>
              </div>
            )}
          </div>
        )}

        {/* Summary */}
        {prospect.call_summary && (
          <div className="text-xs">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Summary</p>
            <p className="text-foreground/80 leading-relaxed">{prospect.call_summary}</p>
          </div>
        )}

        {/* Audio player */}
        {prospect.recording_url && (
          <audio
            controls
            src={prospect.recording_url}
            className="w-full h-8"
            preload="none"
          />
        )}

        {/* No-Lead reason input */}
        {showNoLeadInput && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Why not a lead?</p>
            <Input
              value={noLeadReason}
              onChange={(e) => setNoLeadReason(e.target.value)}
              placeholder="AI-suggested reason — edit if needed"
              className="text-xs h-8"
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                variant="destructive"
                className="h-7 text-xs"
                onClick={() => onQualify("no_lead", noLeadReason)}
                disabled={isPending}
              >
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Confirm No Lead"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowNoLeadInput(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Actions */}
        {!showNoLeadInput && (
          <div className="flex gap-2">
            <Button
              size="sm"
              className="h-7 flex-1 text-xs"
              onClick={() => onQualify("lead", undefined, prospect.call_summary || undefined)}
              disabled={isPending}
            >
              {isPending ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                <>
                  <CheckCircle2 className="mr-1 h-3 w-3" /> Lead
                </>
              )}
            </Button>
            <Button
              size="sm"
              variant="outline"
              className="h-7 flex-1 text-xs"
              onClick={() => setShowNoLeadInput(true)}
              disabled={isPending}
            >
              <XCircle className="mr-1 h-3 w-3" /> No Lead
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Lead Card (Leads column) ──

function LeadCard({
  lead,
  businessId,
  employeeId,
  onConvert,
  onUpdateNotes,
  isPending,
}: {
  lead: CustomerItem;
  businessId: string;
  employeeId: string;
  onConvert: (title: string, description?: string, estimate?: number) => void;
  onUpdateNotes: (notes: string) => void;
  isPending: boolean;
}) {
  const [showConvert, setShowConvert] = useState(false);
  const [showNotes, setShowNotes] = useState(false);
  const [showMiniChat, setShowMiniChat] = useState(false);
  const [notesExpanded, setNotesExpanded] = useState(false);
  const [transcriptExpanded, setTranscriptExpanded] = useState(false);
  const [notesText, setNotesText] = useState(lead.notes || "");
  const [chatInput, setChatInput] = useState("");
  const [chatMessages, setChatMessages] = useState<{ role: "user" | "assistant"; content: string }[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const chatEndRef = useRef<HTMLDivElement>(null);
  const chatInputRef = useRef<HTMLInputElement>(null);
  const [jobEstimate, setJobEstimate] = useState("");
  const [jobTitle, setJobTitle] = useState(() => {
    if (lead.call_category && lead.full_name) {
      return `${lead.call_category} — ${lead.full_name}`;
    }
    return `Service for ${lead.full_name || "Customer"}`;
  });
  const [jobDescription, setJobDescription] = useState(() => {
    // Clean summary — just the call context, not the full AI chat log
    const parts: string[] = [];
    if (lead.call_summary) parts.push(lead.call_summary);
    if (lead.suggested_action) parts.push(`Next step: ${lead.suggested_action}`);
    if (lead.campaign_name) parts.push(`Source: ${lead.campaign_name}`);
    return parts.join("\n") || "";
  });

  // Keep notesText in sync with lead.notes when it changes externally
  useEffect(() => {
    setNotesText(lead.notes || "");
  }, [lead.notes]);

  // Auto-scroll chat to bottom
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [chatMessages]);

  // Focus chat input when mini-chat opens
  useEffect(() => {
    if (showMiniChat) chatInputRef.current?.focus();
  }, [showMiniChat]);

  const handleMiniChatSend = async () => {
    const msg = chatInput.trim();
    if (!msg || chatLoading) return;

    const userMsg = { role: "user" as const, content: msg };
    setChatMessages((prev) => [...prev, userMsg]);
    setChatInput("");
    setChatLoading(true);

    // Build lead context to prepend to the user message
    const leadContext = [
      `[Lead context — keep responses concise, 2-4 sentences, markdown formatting]`,
      `Lead: ${lead.full_name || "Unknown"}`,
      lead.phone ? `Phone: ${lead.phone}` : null,
      lead.call_summary ? `Call summary: ${lead.call_summary}` : null,
      lead.transcript ? `Transcript:\n${lead.transcript}` : null,
      lead.suggested_action ? `Recommendation: ${lead.suggested_action}` : null,
      lead.notes ? `Existing notes:\n${lead.notes}` : null,
    ].filter(Boolean).join("\n");

    try {
      const res = await sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages: chatMessages.map((m) => ({ role: m.role, content: m.content })),
        user_message: `${leadContext}\n\nQuestion: ${msg}`,
      });

      const assistantMsg = { role: "assistant" as const, content: res.content };
      setChatMessages((prev) => [...prev, assistantMsg]);

      // Append to notes as markdown
      const timestamp = new Date().toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
      const noteEntry = `**${timestamp}** — _${msg}_\n${res.content}`;
      const updatedNotes = lead.notes ? `${lead.notes}\n\n---\n\n${noteEntry}` : noteEntry;
      onUpdateNotes(updatedNotes);
    } catch {
      setChatMessages((prev) => [...prev, { role: "assistant", content: "Sorry, something went wrong. Try again." }]);
    } finally {
      setChatLoading(false);
    }
  };

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div>
            <p className="font-semibold text-sm">{lead.full_name || "Unknown"}</p>
            <p className="text-xs text-muted-foreground font-mono">{lead.phone || "—"}</p>
          </div>
          <span className="text-[11px] text-muted-foreground">{formatDateShort(lead.created_at)}</span>
        </div>

        {/* Summary (with expandable transcript) */}
        {(lead.call_summary || lead.transcript) && (
          <div className="text-xs space-y-1.5">
            <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Summary</p>
            {lead.call_summary && (
              <p className="text-foreground/80 leading-relaxed">{lead.call_summary}</p>
            )}
            {lead.transcript && (
              <>
                <button
                  onClick={() => setTranscriptExpanded(!transcriptExpanded)}
                  className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors"
                >
                  <FileText className="h-3 w-3" />
                  <span>View transcript</span>
                  <ChevronDown className={cn("h-3 w-3 transition-transform", transcriptExpanded && "rotate-180")} />
                </button>
                {transcriptExpanded && (
                  <div className="rounded-md border bg-muted/30 p-3 max-h-[300px] overflow-y-auto">
                    <p className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">{lead.transcript}</p>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* Notes — expandable */}
        {lead.notes && (
          <div className="text-xs">
            <button
              onClick={() => setNotesExpanded(!notesExpanded)}
              className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground hover:text-foreground transition-colors mb-1"
            >
              <StickyNote className="h-3 w-3" />
              <span>Notes</span>
              <ChevronDown className={cn("h-3 w-3 transition-transform", notesExpanded && "rotate-180")} />
            </button>
            {notesExpanded && (
              <div className="rounded-md border bg-muted/30 p-3 max-h-[200px] overflow-y-auto">
                <div className="text-xs text-foreground/80 leading-relaxed whitespace-pre-wrap">
                  <MarkdownMessage content={lead.notes!} />
                </div>
              </div>
            )}
          </div>
        )}

        {/* Recommendation */}
        {lead.suggested_action && (
          <div className="rounded-md bg-blue-50 dark:bg-blue-950/50 px-3 py-2">
            <p className="text-[10px] font-semibold uppercase text-blue-600 dark:text-blue-400 mb-0.5">
              Recommendation
            </p>
            <p className="text-xs text-blue-700 dark:text-blue-300">{stripPriority(lead.suggested_action)}</p>
          </div>
        )}

        {/* Mini Chat */}
        {showMiniChat && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <div className="flex items-center justify-between">
              <p className="text-[11px] font-semibold text-muted-foreground">Quick Notes</p>
              <button onClick={() => setShowMiniChat(false)} className="text-muted-foreground hover:text-foreground">
                <X className="h-3 w-3" />
              </button>
            </div>
            {chatMessages.length > 0 && (
              <div className="max-h-[200px] overflow-y-auto space-y-2">
                {chatMessages.map((m, i) => (
                  <div key={i} className={cn("text-xs rounded-md px-2.5 py-1.5", m.role === "user" ? "bg-primary/10 text-foreground" : "bg-background border text-foreground/80")}>
                    {m.role === "assistant" ? <MarkdownMessage content={m.content} /> : <p>{m.content}</p>}
                  </div>
                ))}
                {chatLoading && (
                  <div className="flex items-center gap-1.5 text-xs text-muted-foreground px-2.5 py-1.5">
                    <Loader2 className="h-3 w-3 animate-spin" /> Thinking...
                  </div>
                )}
                <div ref={chatEndRef} />
              </div>
            )}
            <div className="flex gap-1.5">
              <Input
                ref={chatInputRef}
                value={chatInput}
                onChange={(e) => setChatInput(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleMiniChatSend()}
                placeholder="Ask about this lead..."
                className="text-xs h-7 flex-1"
                disabled={chatLoading}
              />
              <Button
                size="sm"
                className="h-7 w-7 p-0"
                onClick={handleMiniChatSend}
                disabled={!chatInput.trim() || chatLoading}
              >
                <Send className="h-3 w-3" />
              </Button>
            </div>
          </div>
        )}

        {/* Manual Notes editor */}
        {showNotes && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Edit Notes</p>
            <textarea
              value={notesText}
              onChange={(e) => setNotesText(e.target.value)}
              placeholder="Add notes about this lead..."
              className="w-full rounded-md border bg-background px-3 py-2 text-xs min-h-[60px] resize-none outline-none focus:border-primary"
              autoFocus
            />
            <div className="flex gap-2">
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  onUpdateNotes(notesText);
                  setShowNotes(false);
                }}
                disabled={isPending}
              >
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <><Save className="mr-1 h-3 w-3" /> Save</>}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowNotes(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Convert form */}
        {showConvert && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Convert to Job</p>
            <div className="flex items-center gap-1.5">
              <Pencil className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <Input
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="Job title (AI-generated — edit if needed)"
                className="text-xs h-8"
              />
            </div>
            <textarea
              value={jobDescription}
              onChange={(e) => setJobDescription(e.target.value)}
              placeholder="Description (AI-generated — edit if needed)"
              className="w-full rounded-md border bg-background px-3 py-2 text-xs min-h-[60px] resize-none outline-none focus:border-primary"
            />
            <div className="flex items-center gap-1.5">
              <DollarSign className="h-3 w-3 text-muted-foreground flex-shrink-0" />
              <Input
                type="number"
                value={jobEstimate}
                onChange={(e) => setJobEstimate(e.target.value)}
                placeholder="Estimate amount (optional)"
                className="text-xs h-8"
                min="0"
                step="0.01"
              />
            </div>
            <div className="flex gap-2">
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={() => onConvert(jobTitle, jobDescription || undefined, jobEstimate ? parseFloat(jobEstimate) : undefined)}
                disabled={!jobTitle.trim() || isPending}
              >
                {isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : "Create Job"}
              </Button>
              <Button
                size="sm"
                variant="ghost"
                className="h-7 text-xs"
                onClick={() => setShowConvert(false)}
              >
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Actions */}
        {!showConvert && !showNotes && !showMiniChat && (
          <div className="flex gap-2">
            <Button
              size="sm"
              className="h-7 flex-1 text-xs"
              onClick={() => setShowConvert(true)}
              disabled={isPending}
            >
              <ArrowRight className="mr-1 h-3 w-3" /> Convert to Job
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setShowNotes(true)}
              title="Edit notes"
            >
              <StickyNote className="h-3 w-3" />
            </Button>
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setShowMiniChat(true)}
              title="Quick AI notes"
            >
              <MessageSquare className="h-3 w-3" />
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// ── Review Row ──

const CALL_OUTCOME_STYLES: Record<string, { bg: string }> = {
  Lead: { bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  "No Lead": { bg: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400" },
};

const LEAD_OUTCOME_STYLES: Record<string, { bg: string }> = {
  Converted: { bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300" },
  "No Conversion": { bg: "bg-red-100 text-red-700 dark:bg-red-950 dark:text-red-300" },
  Pending: { bg: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300" },
};

function buildContextText(item: ReviewItem): string {
  const parts: string[] = [];
  if (item.call_summary) parts.push(item.call_summary);
  if (item.lead_summary) parts.push(`Lead: ${item.lead_summary}`);
  if (item.no_lead_reason) parts.push(`No-lead: ${item.no_lead_reason}`);
  if (item.no_conversion_reason) parts.push(`No-conversion: ${item.no_conversion_reason}`);
  return parts.join(" | ") || "—";
}

function exportReviewCSV(items: ReviewItem[]) {
  const headers = ["Name", "Phone", "Call Outcome", "Lead Outcome", "Customer", "Context", "Date"];
  const rows = items.map((item) => [
    item.caller_name || "",
    item.caller_phone || "",
    item.call_outcome || "",
    item.lead_outcome || "",
    item.customer_type ? (item.customer_type === "returning" ? "Returning" : "New") : "",
    buildContextText(item).replace(/"/g, '""'),
    item.created_at ? new Date(item.created_at).toLocaleDateString() : "",
  ]);
  const csv = [
    headers.join(","),
    ...rows.map((r) => r.map((c) => `"${c}"`).join(",")),
  ].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `sales-review-${new Date().toISOString().slice(0, 10)}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

function ReviewRow({ item }: { item: ReviewItem }) {
  const [expanded, setExpanded] = useState(false);
  const callStyle = CALL_OUTCOME_STYLES[item.call_outcome] || CALL_OUTCOME_STYLES["No Lead"];
  const leadStyle = item.lead_outcome ? LEAD_OUTCOME_STYLES[item.lead_outcome] : null;

  return (
    <>
      <tr
        className="border-b transition hover:bg-muted/30 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        <td className="px-3 py-2.5">
          <span className="font-medium text-sm">{item.caller_name || "Unknown"}</span>
        </td>
        <td className="px-3 py-2.5 text-xs font-mono text-muted-foreground">
          {item.caller_phone || "—"}
        </td>
        <td className="px-3 py-2.5">
          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", callStyle.bg)}>
            {item.call_outcome}
          </span>
        </td>
        <td className="px-3 py-2.5">
          {leadStyle ? (
            <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", leadStyle.bg)}>
              {item.lead_outcome}
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-3 py-2.5">
          {item.customer_type === "returning" ? (
            <span className="rounded-full bg-violet-100 px-2 py-0.5 text-[10px] font-semibold text-violet-700 dark:bg-violet-950 dark:text-violet-300">
              Returning
            </span>
          ) : item.customer_type === "new" ? (
            <span className="rounded-full bg-sky-100 px-2 py-0.5 text-[10px] font-semibold text-sky-700 dark:bg-sky-950 dark:text-sky-300">
              New
            </span>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground max-w-[250px] truncate">
          {buildContextText(item)}
        </td>
        <td className="px-3 py-2.5 text-xs text-muted-foreground">
          {formatDateShort(item.created_at)}
        </td>
      </tr>
      {expanded && (
        <tr className="border-b bg-muted/20">
          <td colSpan={7} className="px-4 py-3 space-y-2">
            {item.call_summary && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Call Summary</p>
                <p className="text-xs leading-relaxed">{item.call_summary}</p>
              </div>
            )}
            {item.lead_summary && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">Lead Context</p>
                <p className="text-xs leading-relaxed">{item.lead_summary}</p>
              </div>
            )}
            {item.no_lead_reason && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">No-Lead Reason</p>
                <p className="text-xs leading-relaxed">{item.no_lead_reason}</p>
              </div>
            )}
            {item.no_conversion_reason && (
              <div>
                <p className="text-[10px] font-semibold uppercase text-muted-foreground mb-0.5">No-Conversion Reason</p>
                <p className="text-xs leading-relaxed">{item.no_conversion_reason}</p>
              </div>
            )}
            <div className="flex items-center gap-4 text-[11px] text-muted-foreground">
              {item.duration_s != null && (
                <span className="flex items-center gap-1">
                  <Clock className="h-3 w-3" /> {formatDuration(item.duration_s)}
                </span>
              )}
              {item.converted_job_id && (
                <span className="text-primary font-medium">Job: {item.converted_job_id.slice(0, 8)}...</span>
              )}
            </div>
            {item.recording_url && (
              <audio controls src={item.recording_url} className="w-full h-8" preload="none" />
            )}
          </td>
        </tr>
      )}
    </>
  );
}
