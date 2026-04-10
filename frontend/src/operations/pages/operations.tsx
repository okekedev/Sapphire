import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Loader2,
  DollarSign,
  Briefcase,
  Users,
  ChevronDown,
  Send,
  Play,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  StickyNote,
  Download,
  Search,
  Pencil,
  Save,
  Phone,
  RefreshCw,
  BarChart2,
} from "lucide-react";
import { cn } from "@/shared/lib/utils";
import { MarkdownMessage } from "@/shared/components/ui/markdown-message";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { Input } from "@/shared/components/ui/input";
import { PageHeader } from "@/shared/components/page-header";
import { useAppStore } from "@/shared/stores/app-store";
import { listEmployees, listDepartments } from "@/shared/api/organization";
import { sendEmployeeChat } from "@/shared/api/chat";
import {
  listCustomers,
  createCustomer,
  listJobs,
  createJob,
  updateJob,
  getSalesSummary,
  type JobItem,
  type JobListResponse,
  type CustomerItem,
} from "@/sales/api/sales";
import { DeptLayout, type DeptSection } from "@/shared/components/layout/dept-layout";

// ── Helpers ──

function formatMoney(amount: number | null | undefined): string {
  if (!amount) return "$0";
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatDate(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

/** Strip priority/urgency prefixes like "HIGH PRIORITY:", "URGENT:", etc. */
function stripPriority(text: string): string {
  return text.replace(/^(HIGH PRIORITY|PRIORITY|URGENT|LOW PRIORITY|MEDIUM PRIORITY)\s*[:—\-]\s*/i, "").trim();
}

const STATUS_CONFIG: Record<string, { bg: string; label: string }> = {
  new: { bg: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300", label: "Not Started" },
  in_progress: { bg: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300", label: "In Progress" },
  completed: { bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300", label: "Completed" },
};

// ── Notes Section Component ──
// Always visible on the card. Shows existing notes from DB + input to add new ones.
// Sends to AI for cleanup, falls back to raw save if AI fails.

function NotesSection({
  job,
  businessId,
  employeeId,
  onUpdateNotes,
}: {
  job: JobItem;
  businessId: string;
  employeeId: string;
  onUpdateNotes: (notes: string) => void;
}) {
  const [noteInput, setNoteInput] = useState("");
  const [saving, setSaving] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleAddNote = async () => {
    const msg = noteInput.trim();
    if (!msg || saving) return;

    setSaving(true);
    setNoteInput("");

    const timestamp = new Date().toLocaleString("en-US", {
      month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
    });

    try {
      // Try AI cleanup first
      const jobContext = [
        `[You are a job documentation assistant. The user is a field worker (plumber, electrician, contractor, etc.) logging notes about a job in progress. Your role is to take their rough notes — typos, shorthand, voice-to-text — and clean them into clear, professional job documentation. Keep the worker's voice and facts. Don't add opinions, strategy, or recommendations. Just format what they said into clean notes. Use short paragraphs, bullet points for lists of work done, and bold for key details. 2-4 sentences max unless they gave you a lot of detail. Return ONLY the cleaned note text, no preamble.]`,
        `Job: ${job.title}`,
        `Customer: ${job.contact_name || "Unknown"}`,
        job.amount_quoted ? `Quote: $${job.amount_quoted.toLocaleString()}` : null,
        job.notes ? `Existing notes for context (do NOT repeat these):\n${job.notes}` : null,
      ].filter(Boolean).join("\n");

      const res = await sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages: [],
        user_message: `${jobContext}\n\nNew field note to clean up: ${msg}`,
      });

      const noteEntry = `**${timestamp}**\n${res.content}`;
      const updatedNotes = job.notes ? `${job.notes}\n\n---\n\n${noteEntry}` : noteEntry;
      onUpdateNotes(updatedNotes);
    } catch {
      // Fallback: save raw note directly (no AI formatting)
      const noteEntry = `**${timestamp}**\n${msg}`;
      const updatedNotes = job.notes ? `${job.notes}\n\n---\n\n${noteEntry}` : noteEntry;
      onUpdateNotes(updatedNotes);
    } finally {
      setSaving(false);
      inputRef.current?.focus();
    }
  };

  return (
    <div className="rounded-md border bg-muted/30 p-3 space-y-2">
      <p className="text-[11px] font-semibold text-muted-foreground flex items-center gap-1.5">
        <StickyNote className="h-3 w-3" /> Field Notes
      </p>

      {/* Existing notes from DB */}
      {job.notes ? (
        <div className="max-h-[200px] overflow-y-auto rounded-md bg-background/50 p-2.5">
          <div className="text-xs text-foreground/80 leading-relaxed [&_p]:my-1 [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_hr]:my-2 [&_hr]:border-border/50">
            <MarkdownMessage content={job.notes} />
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground italic">No notes yet</p>
      )}

      {/* Input to add new note */}
      <div className="flex gap-1.5">
        <Input
          ref={inputRef}
          value={noteInput}
          onChange={(e) => setNoteInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAddNote()}
          placeholder="Log work done, materials used, issues found..."
          className="text-xs h-7 flex-1"
          disabled={saving}
        />
        <Button
          size="sm"
          className="h-7 w-7 p-0"
          onClick={handleAddNote}
          disabled={!noteInput.trim() || saving}
        >
          {saving ? <Loader2 className="h-3 w-3 animate-spin" /> : <Send className="h-3 w-3" />}
        </Button>
      </div>
    </div>
  );
}

// ── Sales Handoff Section (collapsible) ──

function SalesSummarySection({ job }: { job: JobItem }) {
  const [expanded, setExpanded] = useState(false);

  // Combine call_summary + lead_notes into one clean summary
  const combinedSummary = [job.call_summary, job.lead_notes].filter(Boolean).join("\n\n");
  if (!combinedSummary) return null;

  return (
    <div className="rounded-md border border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-950/30 px-3 py-2">
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex items-center gap-1 w-full"
      >
        <ChevronDown className={cn("h-3 w-3 text-indigo-600 dark:text-indigo-400 transition-transform", expanded && "rotate-180")} />
        <span className="text-[10px] font-semibold uppercase text-indigo-600 dark:text-indigo-400">Sales Summary</span>
      </button>
      {expanded && (
        <div className="text-xs text-foreground/80 leading-relaxed mt-1.5 [&_p]:my-1 [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5">
          <MarkdownMessage content={stripPriority(combinedSummary)} />
        </div>
      )}
    </div>
  );
}

// ── Job Card Component ──

function JobCard({
  job,
  businessId,
  employeeId,
  onStatusChange,
  onUpdateNotes,
  onUpdateJob,
  isPending,
}: {
  job: JobItem;
  businessId: string;
  employeeId: string;
  onStatusChange: (status: string) => void;
  onUpdateNotes: (notes: string) => void;
  onUpdateJob: (payload: { title?: string; amount_quoted?: number }) => void;
  isPending: boolean;
}) {
  const [showEdit, setShowEdit] = useState(false);
  const [editTitle, setEditTitle] = useState(job.title);
  const [editAmount, setEditAmount] = useState(job.amount_quoted?.toString() || "");

  const statusStyle = STATUS_CONFIG[job.status] || { bg: "bg-gray-100 text-gray-700", label: job.status };

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardContent className="p-4 space-y-3">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <p className="font-semibold text-sm truncate">{job.title}</p>
            <p className="text-xs text-muted-foreground">{job.contact_name || "Unknown"}</p>
            {job.contact_phone && (
              <p className="text-[11px] text-muted-foreground flex items-center gap-1 mt-0.5">
                <Phone className="h-2.5 w-2.5" />
                {job.contact_phone}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-1 shrink-0 ml-2">
            <span className={cn("text-[10px] font-semibold rounded-full px-2 py-0.5", statusStyle.bg)}>
              {statusStyle.label}
            </span>
            {(job.source === "sales_pipeline" || job.source === "sales") && (
              <span className="text-[10px] font-medium rounded-full px-2 py-0.5 bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300">
                From Sales
              </span>
            )}
          </div>
        </div>

        {/* Details row */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {job.amount_quoted != null && (
            <span className="font-mono font-medium text-foreground">
              <span className="text-muted-foreground font-normal">Sales Quote:</span> {formatMoney(job.amount_quoted)}
            </span>
          )}
          <span><span className="text-muted-foreground">Date:</span> {formatDate(job.created_at)}</span>
          {job.started_at && <span>Started {formatDate(job.started_at)}</span>}
          {job.completed_at && <span>Done {formatDate(job.completed_at)}</span>}
        </div>

        {/* Sales summary — collapsible */}
        {(job.call_summary || job.lead_notes) && (
          <SalesSummarySection job={job} />
        )}

        {/* Notes — always visible, reads/writes directly to DB */}
        <NotesSection
          job={job}
          businessId={businessId}
          employeeId={employeeId}
          onUpdateNotes={onUpdateNotes}
        />

        {/* Edit form */}
        {showEdit && (
          <div className="space-y-2 rounded-md border p-3 bg-muted/30">
            <p className="text-[11px] font-semibold text-muted-foreground">Edit Job</p>
            <Input
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              placeholder="Job title"
              className="text-xs h-7"
            />
            <Input
              value={editAmount}
              onChange={(e) => setEditAmount(e.target.value)}
              placeholder="Quote amount"
              className="text-xs h-7 font-mono"
              type="number"
            />
            <div className="flex gap-1.5">
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={() => {
                  onUpdateJob({
                    title: editTitle,
                    amount_quoted: editAmount ? parseFloat(editAmount) : undefined,
                  });
                  setShowEdit(false);
                }}
              >
                <Save className="h-3 w-3 mr-1" /> Save
              </Button>
              <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowEdit(false)}>
                Cancel
              </Button>
            </div>
          </div>
        )}

        {/* Actions */}
        <div className="flex flex-wrap gap-1.5 pt-1">
          {job.status === "new" && (
            <Button
              size="sm"
              className="h-7 text-xs"
              onClick={() => onStatusChange("in_progress")}
              disabled={isPending}
            >
              <Play className="h-3 w-3 mr-1" /> Start Job
            </Button>
          )}
          {job.status === "in_progress" && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => onStatusChange("new")}
                disabled={isPending}
              >
                <ArrowLeft className="h-3 w-3 mr-1" /> Not Started
              </Button>
              <Button
                size="sm"
                className="h-7 text-xs"
                onClick={() => onStatusChange("completed")}
                disabled={isPending}
              >
                <CheckCircle2 className="h-3 w-3 mr-1" /> Complete
              </Button>
            </>
          )}
          {job.status === "completed" && (
            <>
              <Button
                size="sm"
                variant="outline"
                className="h-7 text-xs"
                onClick={() => onStatusChange("in_progress")}
                disabled={isPending}
              >
                <ArrowLeft className="h-3 w-3 mr-1" /> In Progress
              </Button>
              <Button
                size="sm"
                className="h-7 text-xs bg-violet-600 hover:bg-violet-700 text-white"
                onClick={() => onStatusChange("billing")}
                disabled={isPending}
              >
                <ArrowRight className="h-3 w-3 mr-1" /> Send to Billing
              </Button>
            </>
          )}
          {job.status !== "completed" && (
            <Button
              size="sm"
              variant="ghost"
              className="h-7 text-xs"
              onClick={() => setShowEdit(!showEdit)}
            >
              <Pencil className="h-3 w-3 mr-1" /> Edit
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── Customer Table ──

function CustomerTable({
  customers,
  isLoading,
  search,
  onSearchChange,
  visibleCount,
  onShowMore,
  total,
}: {
  customers: CustomerItem[];
  isLoading: boolean;
  search: string;
  onSearchChange: (v: string) => void;
  visibleCount: number;
  onShowMore: () => void;
  total: number;
}) {
  const handleExport = () => {
    const headers = ["Name", "Business", "Phone", "Email", "Status", "Jobs", "Revenue", "Created"];
    const rows = customers.map((c) => [
      c.full_name || "",
      c.company_name || "",
      c.phone || "",
      c.email || "",
      c.status,
      c.job_count.toString(),
      c.total_revenue.toString(),
      c.created_at,
    ]);
    const csv = [headers.join(","), ...rows.map((r) => r.map((v) => `"${v}"`).join(","))].join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `customers-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Card>
      <CardContent className="p-0">
        <div className="flex items-center justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">
            Customers
            <span className="ml-2 text-xs font-normal text-muted-foreground">{total} total</span>
          </h2>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="absolute left-2 top-1/2 -translate-y-1/2 h-3 w-3 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => onSearchChange(e.target.value)}
                placeholder="Search..."
                className="text-xs h-7 pl-7 w-48"
              />
            </div>
            <Button size="sm" variant="outline" className="h-7 text-xs" onClick={handleExport}>
              <Download className="h-3 w-3 mr-1" /> Export
            </Button>
          </div>
        </div>

        {isLoading ? (
          <div className="flex items-center justify-center py-12">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : customers.length === 0 ? (
          <div className="py-12 text-center text-sm text-muted-foreground">
            No customers yet. Customers are created when leads are converted.
          </div>
        ) : (
          <>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2 text-left">Name</th>
                    <th className="px-3 py-2 text-left">Business</th>
                    <th className="px-3 py-2 text-left">Phone</th>
                    <th className="px-3 py-2 text-left">Email</th>
                    <th className="px-3 py-2 text-left">Jobs</th>
                    <th className="px-3 py-2 text-left">Revenue</th>
                    <th className="px-3 py-2 text-left">Created</th>
                  </tr>
                </thead>
                <tbody>
                  {customers.slice(0, visibleCount).map((c) => (
                    <tr key={c.id} className="border-b transition hover:bg-muted/30">
                      <td className="px-3 py-2.5 font-medium">{c.full_name || "—"}</td>
                      <td className="px-3 py-2.5 text-xs">{c.company_name || "—"}</td>
                      <td className="px-3 py-2.5 text-xs font-mono">{c.phone || "—"}</td>
                      <td className="px-3 py-2.5 text-xs">{c.email || "—"}</td>
                      <td className="px-3 py-2.5 text-xs">{c.job_count}</td>
                      <td className="px-3 py-2.5 text-xs font-mono font-semibold text-emerald-600">
                        {formatMoney(c.total_revenue)}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-muted-foreground">{formatDate(c.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {customers.length > visibleCount && (
              <div className="px-4 py-3 border-t">
                <Button size="sm" variant="ghost" className="text-xs w-full" onClick={onShowMore}>
                  Show more ({customers.length - visibleCount} remaining)
                </Button>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

// ── New Job Form ──

function NewJobForm({
  customers,
  customersLoading,
  onSubmit,
  onCancel,
  isPending,
}: {
  customers: CustomerItem[];
  customersLoading: boolean;
  onSubmit: (data: { contact_id: string; title: string; description?: string; amount_quoted?: number }) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [contactId, setContactId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <p className="text-sm font-semibold">New Job</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <select
            value={contactId}
            onChange={(e) => setContactId(e.target.value)}
            className="h-8 rounded-md border bg-background px-2 text-sm"
          >
            <option value="">Select Customer...</option>
            {customersLoading && <option disabled>Loading...</option>}
            {customers.map((c) => (
              <option key={c.id} value={c.id}>
                {c.full_name || c.phone || c.email || "Unnamed"}
              </option>
            ))}
          </select>
          <Input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="Job title *"
            className="text-sm h-8"
          />
          <Input
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Description (optional)"
            className="text-sm h-8"
          />
          <Input
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            placeholder="Quote amount"
            className="text-sm h-8 font-mono"
            type="number"
          />
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="h-8"
            disabled={!contactId || !title || isPending}
            onClick={() =>
              onSubmit({
                contact_id: contactId,
                title,
                description: description || undefined,
                amount_quoted: amount ? parseFloat(amount) : undefined,
              })
            }
          >
            {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
            Create Job
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── New Customer Form ──

function NewCustomerForm({
  onSubmit,
  onCancel,
  isPending,
}: {
  onSubmit: (data: { full_name: string; company_name?: string; phone?: string; email?: string }) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [name, setName] = useState("");
  const [companyName, setCompanyName] = useState("");
  const [phone, setPhone] = useState("");
  const [email, setEmail] = useState("");

  return (
    <Card>
      <CardContent className="p-4 space-y-3">
        <p className="text-sm font-semibold">New Customer</p>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Full name *" className="text-sm h-8" />
          <Input value={companyName} onChange={(e) => setCompanyName(e.target.value)} placeholder="Business name" className="text-sm h-8" />
          <Input value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Phone" className="text-sm h-8" />
          <Input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" className="text-sm h-8" />
        </div>
        <div className="flex gap-2">
          <Button
            size="sm"
            className="h-8"
            disabled={!name || isPending}
            onClick={() => onSubmit({ full_name: name, company_name: companyName || undefined, phone: phone || undefined, email: email || undefined })}
          >
            {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5 mr-1" />}
            Add Customer
          </Button>
          <Button size="sm" variant="ghost" className="h-8" onClick={onCancel}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

// ── Pipeline Column ──

function PipelineColumn({
  title,
  count,
  jobs,
  businessId,
  employeeId,
  isLoading,
  onStatusChange,
  onUpdateNotes,
  onUpdateJob,
  pendingJobId,
}: {
  title: string;
  count: number;
  jobs: JobItem[];
  businessId: string;
  employeeId: string;
  isLoading: boolean;
  onStatusChange: (jobId: string, status: string) => void;
  onUpdateNotes: (jobId: string, notes: string) => void;
  onUpdateJob: (jobId: string, payload: { title?: string; amount_quoted?: number }) => void;
  pendingJobId: string | null;
}) {
  return (
    <div className="flex-1 min-w-[280px]">
      <div className="flex items-center gap-2 mb-3">
        <h3 className="text-sm font-semibold">{title}</h3>
        <span className="text-xs text-muted-foreground bg-muted rounded-full px-2 py-0.5">{count}</span>
      </div>
      {isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
        </div>
      ) : jobs.length === 0 ? (
        <div className="rounded-lg border border-dashed p-6 text-center text-xs text-muted-foreground">
          No jobs
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              businessId={businessId}
              employeeId={employeeId}
              onStatusChange={(status) => onStatusChange(job.id, status)}
              onUpdateNotes={(notes) => onUpdateNotes(job.id, notes)}
              onUpdateJob={(payload) => onUpdateJob(job.id, payload)}
              isPending={pendingJobId === job.id}
            />
          ))}
        </div>
      )}
    </div>
  );
}

// ── Main Page ──

export default function OperationsPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const queryClient = useQueryClient();

  const [showNewJob, setShowNewJob] = useState(false);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [customerSearch, setCustomerSearch] = useState("");
  const [customerVisible, setCustomerVisible] = useState(5);
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null);

  // ── Queries ──

  const summaryQuery = useQuery({
    queryKey: ["ops-summary", businessId],
    queryFn: () => getSalesSummary(businessId!),
    enabled: !!businessId,
  });

  const newJobsQuery = useQuery({
    queryKey: ["ops-jobs", businessId, "new"],
    queryFn: () => listJobs(businessId!, { status: "new", limit: 100 }),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const inProgressJobsQuery = useQuery({
    queryKey: ["ops-jobs", businessId, "in_progress"],
    queryFn: () => listJobs(businessId!, { status: "in_progress", limit: 100 }),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const completedJobsQuery = useQuery({
    queryKey: ["ops-jobs", businessId, "completed"],
    queryFn: () => listJobs(businessId!, { status: "completed", limit: 100 }),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const customersQuery = useQuery({
    queryKey: ["ops-customers", businessId, customerSearch],
    queryFn: () => listCustomers(businessId!, { status: "active_customer", search: customerSearch || undefined, limit: 200 }),
    enabled: !!businessId,
  });

  // All customers for the new job dropdown
  const allCustomersQuery = useQuery({
    queryKey: ["ops-all-customers", businessId],
    queryFn: () => listCustomers(businessId!, { limit: 200 }),
    enabled: !!businessId && showNewJob,
  });

  // Find Operations department + head employee (Dana)
  const departmentsQuery = useQuery({
    queryKey: ["ops-departments", businessId],
    queryFn: () => listDepartments(businessId!),
    enabled: !!businessId,
  });

  const opsDept = departmentsQuery.data?.find((d) => d.name === "Operations");

  const employeesQuery = useQuery({
    queryKey: ["ops-employees", businessId, opsDept?.id],
    queryFn: () => listEmployees({ business_id: businessId!, department_id: opsDept!.id }),
    enabled: !!businessId && !!opsDept?.id,
  });

  const dana = employeesQuery.data?.find((e) => e.is_head);

  // ── Mutations ──

  const invalidateJobs = () => {
    queryClient.invalidateQueries({ queryKey: ["ops-jobs"] });
    queryClient.invalidateQueries({ queryKey: ["ops-summary"] });
  };

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["ops-jobs"] }),
      queryClient.invalidateQueries({ queryKey: ["ops-summary"] }),
      queryClient.invalidateQueries({ queryKey: ["ops-customers"] }),
    ]);
    setTimeout(() => setIsRefreshing(false), 600);
  };

  const updateJobMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: string; status?: string; notes?: string; title?: string; amount_quoted?: number }) =>
      updateJob(businessId!, id, payload),
    onMutate: async (vars) => {
      setPendingJobId(vars.id);

      if (vars.status) {
        await queryClient.cancelQueries({ queryKey: ["ops-jobs"] });

        const prevNew = queryClient.getQueryData<JobListResponse>(["ops-jobs", businessId, "new"]);
        const prevProgress = queryClient.getQueryData<JobListResponse>(["ops-jobs", businessId, "in_progress"]);
        const prevCompleted = queryClient.getQueryData<JobListResponse>(["ops-jobs", businessId, "completed"]);

        const allJobs = [
          ...(prevNew?.jobs || []),
          ...(prevProgress?.jobs || []),
          ...(prevCompleted?.jobs || []),
        ];
        const job = allJobs.find((j) => j.id === vars.id);

        if (job) {
          const updatedJob = { ...job, status: vars.status };

          const removeFrom = (data: JobListResponse | undefined): JobListResponse => {
            if (!data) return { jobs: [], total: 0 };
            const filtered = data.jobs.filter((j) => j.id !== vars.id);
            return { ...data, jobs: filtered, total: filtered.length };
          };
          const addTo = (data: JobListResponse | undefined): JobListResponse => {
            if (!data) return { jobs: [updatedJob], total: 1 };
            return { ...data, jobs: [updatedJob, ...data.jobs.filter((j) => j.id !== vars.id)], total: data.jobs.filter((j) => j.id !== vars.id).length + 1 };
          };

          queryClient.setQueryData<JobListResponse>(["ops-jobs", businessId, "new"],
            vars.status === "new" ? addTo(prevNew) : removeFrom(prevNew));
          queryClient.setQueryData<JobListResponse>(["ops-jobs", businessId, "in_progress"],
            vars.status === "in_progress" ? addTo(prevProgress) : removeFrom(prevProgress));
          queryClient.setQueryData<JobListResponse>(["ops-jobs", businessId, "completed"],
            vars.status === "completed" ? addTo(prevCompleted) : removeFrom(prevCompleted));
        }

        return { prevNew, prevProgress, prevCompleted };
      }
      return {};
    },
    onError: (_err, vars, context: any) => {
      if (context?.prevNew !== undefined) {
        queryClient.setQueryData(["ops-jobs", businessId, "new"], context.prevNew);
        queryClient.setQueryData(["ops-jobs", businessId, "in_progress"], context.prevProgress);
        queryClient.setQueryData(["ops-jobs", businessId, "completed"], context.prevCompleted);
      }
    },
    onSettled: () => {
      setPendingJobId(null);
      invalidateJobs();
    },
  });

  const createJobMutation = useMutation({
    mutationFn: (payload: { contact_id: string; title: string; description?: string; amount_quoted?: number }) =>
      createJob(businessId!, payload),
    onSuccess: () => {
      invalidateJobs();
      setShowNewJob(false);
    },
  });

  const createCustomerMutation = useMutation({
    mutationFn: (payload: { full_name: string; phone?: string; email?: string }) =>
      createCustomer(businessId!, { ...payload, status: "active_customer" }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["ops-customers"] });
      queryClient.invalidateQueries({ queryKey: ["ops-all-customers"] });
      queryClient.invalidateQueries({ queryKey: ["ops-summary"] });
      setShowNewCustomer(false);
    },
  });

  const summary = summaryQuery.data;
  const newJobs = newJobsQuery.data?.jobs || [];
  const inProgressJobs = inProgressJobsQuery.data?.jobs || [];
  const completedJobs = completedJobsQuery.data?.jobs || [];
  const customers = customersQuery.data?.customers || [];
  const activeJobCount = newJobs.length + inProgressJobs.length;

  // ── Section content ──

  const jobsContent = (
    <div className="space-y-4">
      {/* Toolbar */}
      <div className="flex items-center gap-2 justify-end">
        <Button
          size="sm"
          variant="ghost"
          className="h-7 w-7 p-0"
          onClick={handleRefresh}
          disabled={isRefreshing}
          title="Refresh"
        >
          <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
        </Button>
        <Button size="sm" className="h-7 text-xs" onClick={() => setShowNewJob(!showNewJob)}>
          <Plus className="h-3 w-3 mr-1" /> New Job
        </Button>
        <Button size="sm" variant="outline" className="h-7 text-xs" onClick={() => setShowNewCustomer(!showNewCustomer)}>
          <Plus className="h-3 w-3 mr-1" /> New Customer
        </Button>
      </div>

      {showNewJob && (
        <NewJobForm
          customers={allCustomersQuery.data?.customers || []}
          customersLoading={allCustomersQuery.isLoading}
          onSubmit={(data) => createJobMutation.mutate(data)}
          onCancel={() => setShowNewJob(false)}
          isPending={createJobMutation.isPending}
        />
      )}

      {showNewCustomer && (
        <NewCustomerForm
          onSubmit={(data) => createCustomerMutation.mutate(data)}
          onCancel={() => setShowNewCustomer(false)}
          isPending={createCustomerMutation.isPending}
        />
      )}

      <div className="flex gap-6 overflow-x-auto pb-2">
        <PipelineColumn
          title="Not Started"
          count={newJobs.length}
          jobs={newJobs}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={newJobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          pendingJobId={pendingJobId}
        />
        <PipelineColumn
          title="In Progress"
          count={inProgressJobs.length}
          jobs={inProgressJobs}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={inProgressJobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          pendingJobId={pendingJobId}
        />
        <PipelineColumn
          title="Completed"
          count={completedJobs.length}
          jobs={completedJobs}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={completedJobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          pendingJobId={pendingJobId}
        />
      </div>

      <CustomerTable
        customers={customers}
        isLoading={customersQuery.isLoading}
        search={customerSearch}
        onSearchChange={(v) => { setCustomerSearch(v); setCustomerVisible(5); }}
        visibleCount={customerVisible}
        onShowMore={() => setCustomerVisible((prev) => prev + 10)}
        total={customersQuery.data?.total || 0}
      />
    </div>
  );

  const summaryContent = (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
            <DollarSign className="h-3.5 w-3.5" /> Job Value
          </div>
          <p className="mt-1 text-2xl font-bold">{formatMoney(summary?.total_quoted)}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
            <Briefcase className="h-3.5 w-3.5" /> Open Jobs
          </div>
          <p className="mt-1 text-2xl font-bold">{summary?.active_jobs || 0}</p>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="p-4">
          <div className="flex items-center gap-2 text-xs font-semibold text-muted-foreground uppercase">
            <Users className="h-3.5 w-3.5" /> Customers
          </div>
          <p className="mt-1 text-2xl font-bold">{summary?.total_customers || 0}</p>
        </CardContent>
      </Card>
    </div>
  );

  const sections: DeptSection[] = [
    {
      id: "jobs",
      label: "Jobs",
      icon: <Briefcase />,
      badge: activeJobCount > 0 ? activeJobCount : undefined,
      content: jobsContent,
    },
    {
      id: "summary",
      label: "Summary",
      icon: <BarChart2 />,
      content: summaryContent,
    },
  ];

  return (
    <div className="p-6 space-y-4">
      <PageHeader
        title="Operations"
        description="Job management, progress tracking, and customer operations"
      />
      <DeptLayout
        sections={sections}
        agentName="operations"
        businessId={businessId}
        pendingMessage={pendingChatMessage}
        onPendingConsumed={() => setPendingChatMessage(null)}
      />
    </div>
  );
}
