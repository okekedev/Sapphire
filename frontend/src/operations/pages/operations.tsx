import { useState, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Plus,
  Loader2,
  DollarSign,
  Briefcase,
  ChevronDown,
  Send,
  Play,
  CheckCircle2,
  ArrowRight,
  ArrowLeft,
  StickyNote,
  Pencil,
  Save,
  Phone,
  RefreshCw,
  Users,
  ClipboardList,
  MapPin,
  Calendar,
  UserCheck,
  FileText,
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
  listJobs,
  createJob,
  updateJob,
  type JobItem,
  type JobListResponse,
  type CustomerItem,
} from "@/sales/api/sales";
import { listTemplates } from "@/operations/api/job-templates";
import type { JobTemplate } from "@/operations/api/job-templates";
import { DeptLayout, type DeptSection } from "@/shared/components/layout/dept-layout";
import { StaffPanel } from "@/operations/components/staff-panel";
import { TemplateBuilder } from "@/operations/components/template-builder";
import { JobDispatchSheet } from "@/operations/components/job-dispatch-sheet";
import { TemplateFillSheet } from "@/operations/components/template-fill-sheet";
import { DispatchMap } from "@/operations/components/dispatch-map";

// ── Helpers ──

function formatMoney(amount: number | null | undefined): string {
  if (!amount) return "$0";
  return `$${amount.toLocaleString("en-US", { minimumFractionDigits: 0, maximumFractionDigits: 0 })}`;
}

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function stripPriority(text: string): string {
  return text.replace(/^(HIGH PRIORITY|PRIORITY|URGENT|LOW PRIORITY|MEDIUM PRIORITY)\s*[:—\-]\s*/i, "").trim();
}

const STATUS_CONFIG: Record<string, { bg: string; label: string }> = {
  new:        { bg: "bg-blue-100 text-blue-700 dark:bg-blue-950 dark:text-blue-300",       label: "Not Started" },
  scheduled:  { bg: "bg-cyan-100 text-cyan-700 dark:bg-cyan-950 dark:text-cyan-300",       label: "Scheduled" },
  dispatched: { bg: "bg-violet-100 text-violet-700 dark:bg-violet-950 dark:text-violet-300", label: "Dispatched" },
  started:    { bg: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",   label: "In Progress" },
  in_progress:{ bg: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",   label: "In Progress" },
  completed:  { bg: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300", label: "Completed" },
  billing:    { bg: "bg-purple-100 text-purple-700 dark:bg-purple-950 dark:text-purple-300", label: "Billing" },
};

// ── Notes Section ──

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
      const jobContext = [
        `[You are a job documentation assistant. The user is a field worker logging notes about a job. Clean their rough notes into professional documentation. Keep their voice. No opinions or strategy. Use bullets for lists. 2-4 sentences max unless lots of detail. Return ONLY the cleaned note text.]`,
        `Job: ${job.title}`,
        `Customer: ${job.contact_name || "Unknown"}`,
        job.amount_quoted ? `Quote: $${job.amount_quoted.toLocaleString()}` : null,
        job.notes ? `Existing notes (do NOT repeat):\n${job.notes}` : null,
      ].filter(Boolean).join("\n");

      const res = await sendEmployeeChat({
        business_id: businessId,
        employee_id: employeeId,
        messages: [],
        user_message: `${jobContext}\n\nNew field note: ${msg}`,
      });

      const noteEntry = `**${timestamp}**\n${res.content}`;
      onUpdateNotes(job.notes ? `${job.notes}\n\n---\n\n${noteEntry}` : noteEntry);
    } catch {
      const noteEntry = `**${timestamp}**\n${msg}`;
      onUpdateNotes(job.notes ? `${job.notes}\n\n---\n\n${noteEntry}` : noteEntry);
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
      {job.notes ? (
        <div className="max-h-[200px] overflow-y-auto rounded-md bg-background/50 p-2.5">
          <div className="text-xs text-foreground/80 leading-relaxed [&_p]:my-1 [&_ul]:ml-4 [&_ol]:ml-4 [&_li]:my-0.5 [&_hr]:my-2 [&_hr]:border-border/50">
            <MarkdownMessage content={job.notes} />
          </div>
        </div>
      ) : (
        <p className="text-[11px] text-muted-foreground italic">No notes yet</p>
      )}
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

// ── Sales Summary (collapsible) ──

function SalesSummarySection({ job }: { job: JobItem }) {
  const [expanded, setExpanded] = useState(false);
  const combinedSummary = [job.call_summary, job.lead_notes].filter(Boolean).join("\n\n");
  if (!combinedSummary) return null;

  return (
    <div className="rounded-md border border-indigo-200 dark:border-indigo-800 bg-indigo-50/50 dark:bg-indigo-950/30 px-3 py-2">
      <button onClick={() => setExpanded(!expanded)} className="flex items-center gap-1 w-full">
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

// ── Job Card ──

function JobCard({
  job,
  template,
  businessId,
  employeeId,
  onStatusChange,
  onUpdateNotes,
  onUpdateJob,
  onOpenDispatch,
  onOpenFillForm,
  isPending,
}: {
  job: JobItem;
  template: JobTemplate | null;
  businessId: string;
  employeeId: string;
  onStatusChange: (status: string) => void;
  onUpdateNotes: (notes: string) => void;
  onUpdateJob: (payload: { title?: string; amount_quoted?: number }) => void;
  onOpenDispatch: () => void;
  onOpenFillForm: () => void;
  isPending: boolean;
}) {
  const [showEdit, setShowEdit] = useState(false);
  const [editTitle, setEditTitle] = useState(job.title);
  const [editAmount, setEditAmount] = useState(job.amount_quoted?.toString() || "");

  const statusStyle = STATUS_CONFIG[job.status] || { bg: "bg-gray-100 text-gray-700", label: job.status };

  const hasTemplate = !!job.template_id && !!template;
  const needsDispatch = hasTemplate && template.requires_dispatch;

  // Check if required template fields are filled (for "Complete" gate)
  const requiredFieldIds = template?.schema.sections.flatMap(s =>
    s.fields.filter(f => f.required).map(f => f.id)
  ) ?? [];
  const filledData = job.template_data ?? {};
  const allRequiredFilled = requiredFieldIds.every(id => {
    const val = filledData[id];
    if (typeof val === "boolean") return val;
    if (Array.isArray(val)) return val.length > 0;
    return !!val && (typeof val !== "string" || val.trim() !== "");
  });
  const canComplete = !hasTemplate || requiredFieldIds.length === 0 || allRequiredFilled;

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
                <Phone className="h-2.5 w-2.5" />{job.contact_phone}
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
            {hasTemplate && (
              <span className="text-[10px] font-medium rounded-full px-2 py-0.5 bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                {template!.name}
              </span>
            )}
          </div>
        </div>

        {/* Details */}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
          {job.amount_quoted != null && (
            <span className="font-mono font-medium text-foreground">
              <span className="text-muted-foreground font-normal">Quote:</span> {formatMoney(job.amount_quoted)}
            </span>
          )}
          <span><span className="text-muted-foreground">Created:</span> {formatDate(job.created_at)}</span>
          {job.started_at && <span>Started {formatDate(job.started_at)}</span>}
          {job.completed_at && <span>Done {formatDate(job.completed_at)}</span>}
        </div>

        {/* Assignment / scheduling info */}
        {(job.assigned_to || job.service_address || job.scheduled_at) && (
          <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
            {job.assigned_to && (
              <span className="flex items-center gap-1.5 text-foreground/80">
                {job.assigned_staff_color && (
                  <span className="h-2 w-2 rounded-full shrink-0" style={{ backgroundColor: job.assigned_staff_color }} />
                )}
                <UserCheck className="h-3 w-3 text-muted-foreground" />
                {job.assigned_staff_name ?? "Assigned"}
              </span>
            )}
            {job.service_address && (
              <span className="flex items-center gap-1 text-muted-foreground">
                <MapPin className="h-3 w-3" />{job.service_address}
              </span>
            )}
            {job.scheduled_at && (
              <span className="flex items-center gap-1 text-muted-foreground">
                <Calendar className="h-3 w-3" />{formatDateTime(job.scheduled_at)}
              </span>
            )}
          </div>
        )}

        {/* Sales summary */}
        {(job.call_summary || job.lead_notes) && <SalesSummarySection job={job} />}

        {/* Notes */}
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
          {/* Fill form button — always shown if template has fields */}
          {hasTemplate && template!.schema.sections.some(s => s.fields.length > 0) && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs"
              onClick={onOpenFillForm}
            >
              <FileText className="h-3 w-3 mr-1" />
              {allRequiredFilled ? "View Form ✓" : "Fill Form"}
            </Button>
          )}

          {/* Status-based primary actions */}
          {job.status === "new" && (
            needsDispatch ? (
              <Button size="sm" className="h-7 text-xs" onClick={onOpenDispatch} disabled={isPending}>
                <Send className="h-3 w-3 mr-1" /> Assign & Dispatch
              </Button>
            ) : (
              <Button size="sm" className="h-7 text-xs" onClick={() => onStatusChange("started")} disabled={isPending}>
                <Play className="h-3 w-3 mr-1" /> Start Job
              </Button>
            )
          )}

          {job.status === "scheduled" && (
            <Button size="sm" className="h-7 text-xs" onClick={onOpenDispatch} disabled={isPending}>
              <Send className="h-3 w-3 mr-1" /> Dispatch
            </Button>
          )}

          {job.status === "dispatched" && (
            <Button size="sm" className="h-7 text-xs" onClick={() => onStatusChange("started")} disabled={isPending}>
              <Play className="h-3 w-3 mr-1" /> Mark Started
            </Button>
          )}

          {(job.status === "started" || job.status === "in_progress") && (
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
                disabled={isPending || !canComplete}
                title={!canComplete ? "Fill required form fields first" : undefined}
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
                onClick={() => onStatusChange("started")}
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

          {job.status !== "completed" && job.status !== "billing" && (
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setShowEdit(!showEdit)}>
              <Pencil className="h-3 w-3 mr-1" /> Edit
            </Button>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

// ── New Job Form ──

function NewJobForm({
  customers,
  customersLoading,
  templates,
  onSubmit,
  onCancel,
  isPending,
}: {
  customers: CustomerItem[];
  customersLoading: boolean;
  templates: JobTemplate[];
  onSubmit: (data: { contact_id: string; title: string; description?: string; amount_quoted?: number; template_id?: string }) => void;
  onCancel: () => void;
  isPending: boolean;
}) {
  const [contactId, setContactId] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [amount, setAmount] = useState("");
  const [templateId, setTemplateId] = useState("");

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
          {templates.length > 0 && (
            <select
              value={templateId}
              onChange={(e) => setTemplateId(e.target.value)}
              className="h-8 rounded-md border bg-background px-2 text-sm sm:col-span-2"
            >
              <option value="">No template</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}
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
                template_id: templateId || undefined,
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

// ── Pipeline Column ──

function PipelineColumn({
  title,
  count,
  jobs,
  templates,
  businessId,
  employeeId,
  isLoading,
  onStatusChange,
  onUpdateNotes,
  onUpdateJob,
  onOpenDispatch,
  onOpenFillForm,
  pendingJobId,
}: {
  title: string;
  count: number;
  jobs: JobItem[];
  templates: JobTemplate[];
  businessId: string;
  employeeId: string;
  isLoading: boolean;
  onStatusChange: (jobId: string, status: string) => void;
  onUpdateNotes: (jobId: string, notes: string) => void;
  onUpdateJob: (jobId: string, payload: { title?: string; amount_quoted?: number }) => void;
  onOpenDispatch: (jobId: string) => void;
  onOpenFillForm: (jobId: string) => void;
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
          {jobs.map((job) => {
            const template = job.template_id
              ? templates.find((t) => t.id === job.template_id) ?? null
              : null;
            return (
              <JobCard
                key={job.id}
                job={job}
                template={template}
                businessId={businessId}
                employeeId={employeeId}
                onStatusChange={(status) => onStatusChange(job.id, status)}
                onUpdateNotes={(notes) => onUpdateNotes(job.id, notes)}
                onUpdateJob={(payload) => onUpdateJob(job.id, payload)}
                onOpenDispatch={() => onOpenDispatch(job.id)}
                onOpenFillForm={() => onOpenFillForm(job.id)}
                isPending={pendingJobId === job.id}
              />
            );
          })}
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
  const [pendingJobId, setPendingJobId] = useState<string | null>(null);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [pendingChatMessage, setPendingChatMessage] = useState<string | null>(null);
  const [dispatchJobId, setDispatchJobId] = useState<string | null>(null);
  const [fillFormJobId, setFillFormJobId] = useState<string | null>(null);

  // ── Queries ──

  const jobsQuery = useQuery({
    queryKey: ["ops-jobs", businessId],
    queryFn: () => listJobs(businessId!, { limit: 200 }),
    enabled: !!businessId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const allJobs = jobsQuery.data?.jobs ?? [];

  // Client-side column buckets
  const newJobs        = allJobs.filter(j => j.status === "new" || j.status === "scheduled");
  const inProgressJobs = allJobs.filter(j => ["dispatched", "started", "in_progress"].includes(j.status));
  const completedJobs  = allJobs.filter(j => j.status === "completed");

  const allCustomersQuery = useQuery({
    queryKey: ["ops-all-customers", businessId],
    queryFn: () => listCustomers(businessId!, { limit: 200 }),
    enabled: !!businessId && showNewJob,
  });

  const templatesQuery = useQuery({
    queryKey: ["job-templates", businessId],
    queryFn: () => listTemplates(businessId!),
    enabled: !!businessId,
  });
  const templates = templatesQuery.data ?? [];

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

  const invalidateJobs = () => queryClient.invalidateQueries({ queryKey: ["ops-jobs", businessId] });

  const handleRefresh = async () => {
    setIsRefreshing(true);
    await queryClient.invalidateQueries({ queryKey: ["ops-jobs", businessId] });
    setTimeout(() => setIsRefreshing(false), 600);
  };

  const updateJobMutation = useMutation({
    mutationFn: ({ id, ...payload }: { id: string; status?: string; notes?: string; title?: string; amount_quoted?: number; template_data?: Record<string, unknown> }) =>
      updateJob(businessId!, id, payload),
    onMutate: async (vars) => {
      setPendingJobId(vars.id);
      if (vars.status) {
        await queryClient.cancelQueries({ queryKey: ["ops-jobs", businessId] });
        const prev = queryClient.getQueryData<JobListResponse>(["ops-jobs", businessId]);
        queryClient.setQueryData<JobListResponse>(["ops-jobs", businessId], (old) => {
          if (!old) return old;
          return { ...old, jobs: old.jobs.map(j => j.id === vars.id ? { ...j, status: vars.status! } : j) };
        });
        return { prev };
      }
      return {};
    },
    onError: (_err, _vars, context: { prev?: JobListResponse } | undefined) => {
      if (context?.prev) queryClient.setQueryData(["ops-jobs", businessId], context.prev);
    },
    onSettled: () => {
      setPendingJobId(null);
      invalidateJobs();
    },
  });

  const createJobMutation = useMutation({
    mutationFn: (payload: { contact_id: string; title: string; description?: string; amount_quoted?: number; template_id?: string }) =>
      createJob(businessId!, payload),
    onSuccess: () => { invalidateJobs(); setShowNewJob(false); },
  });

  const dispatchMutation = useMutation({
    mutationFn: ({ jobId, ...payload }: { jobId: string; assigned_to: string; service_address?: string; scheduled_at?: string }) =>
      updateJob(businessId!, jobId, payload),
    onSuccess: () => { invalidateJobs(); setDispatchJobId(null); },
  });

  const fillFormMutation = useMutation({
    mutationFn: ({ jobId, templateData }: { jobId: string; templateData: Record<string, unknown> }) =>
      updateJob(businessId!, jobId, { template_data: templateData }),
    onSuccess: () => { invalidateJobs(); setFillFormJobId(null); },
  });

  // Sheet data
  const dispatchJob     = dispatchJobId ? allJobs.find(j => j.id === dispatchJobId) ?? null : null;
  const dispatchTemplate = dispatchJob?.template_id ? templates.find(t => t.id === dispatchJob.template_id) ?? null : null;
  const fillFormJob     = fillFormJobId ? allJobs.find(j => j.id === fillFormJobId) ?? null : null;
  const fillFormTemplate = fillFormJob?.template_id ? templates.find(t => t.id === fillFormJob.template_id) ?? null : null;

  const activeJobCount = newJobs.length + inProgressJobs.length;
  const totalQuoted    = allJobs.reduce((sum, j) => sum + (j.amount_quoted || 0), 0);

  // ── Section content ──

  const jobsContent = (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-4 text-sm">
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <DollarSign className="h-3.5 w-3.5" />
            <span className="font-semibold text-foreground">{formatMoney(totalQuoted)}</span>
            <span className="text-xs">total quoted</span>
          </span>
          <span className="flex items-center gap-1.5 text-muted-foreground">
            <Briefcase className="h-3.5 w-3.5" />
            <span className="font-semibold text-foreground">{activeJobCount}</span>
            <span className="text-xs">open</span>
          </span>
        </div>
        <div className="flex items-center gap-2">
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
        </div>
      </div>

      {showNewJob && (
        <NewJobForm
          customers={allCustomersQuery.data?.customers || []}
          customersLoading={allCustomersQuery.isLoading}
          templates={templates}
          onSubmit={(data) => createJobMutation.mutate(data)}
          onCancel={() => setShowNewJob(false)}
          isPending={createJobMutation.isPending}
        />
      )}

      <div className="flex gap-6 overflow-x-auto pb-2">
        <PipelineColumn
          title="Not Started"
          count={newJobs.length}
          jobs={newJobs}
          templates={templates}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={jobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          onOpenDispatch={setDispatchJobId}
          onOpenFillForm={setFillFormJobId}
          pendingJobId={pendingJobId}
        />
        <PipelineColumn
          title="In Progress"
          count={inProgressJobs.length}
          jobs={inProgressJobs}
          templates={templates}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={jobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          onOpenDispatch={setDispatchJobId}
          onOpenFillForm={setFillFormJobId}
          pendingJobId={pendingJobId}
        />
        <PipelineColumn
          title="Completed"
          count={completedJobs.length}
          jobs={completedJobs}
          templates={templates}
          businessId={businessId}
          employeeId={dana?.id ?? ""}
          isLoading={jobsQuery.isLoading}
          onStatusChange={(jobId, status) => updateJobMutation.mutate({ id: jobId, status })}
          onUpdateNotes={(jobId, notes) => updateJobMutation.mutate({ id: jobId, notes })}
          onUpdateJob={(jobId, payload) => updateJobMutation.mutate({ id: jobId, ...payload })}
          onOpenDispatch={setDispatchJobId}
          onOpenFillForm={setFillFormJobId}
          pendingJobId={pendingJobId}
        />
      </div>
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
      id: "team",
      label: "Job Team",
      icon: <Users />,
      content: <StaffPanel businessId={businessId} />,
    },
    {
      id: "templates",
      label: "Templates",
      icon: <ClipboardList />,
      content: <TemplateBuilder businessId={businessId} />,
    },
  ];

  return (
    <div className="p-4 md:p-6 space-y-4">
      <PageHeader
        title="Jobs"
        description="Job pipeline, progress tracking, and field dispatch"
      />
      <DeptLayout
        sections={sections}
        agentName="operations"
        businessId={businessId}
        pendingMessage={pendingChatMessage}
        onPendingConsumed={() => setPendingChatMessage(null)}
      />

      {/* Route Planner — separate section below the main tabs */}
      <DispatchMap businessId={businessId} jobs={allJobs} />

      {/* Dispatch sheet */}
      {dispatchJob && (
        <JobDispatchSheet
          job={dispatchJob}
          template={dispatchTemplate}
          businessId={businessId}
          onDispatch={({ assigned_to, service_address, scheduled_at }) =>
            dispatchMutation.mutate({ jobId: dispatchJob.id, assigned_to, service_address, scheduled_at })
          }
          onClose={() => setDispatchJobId(null)}
          isPending={dispatchMutation.isPending}
        />
      )}

      {/* Fill form sheet */}
      {fillFormJob && fillFormTemplate && (
        <TemplateFillSheet
          template={fillFormTemplate}
          initialData={fillFormJob.template_data ?? undefined}
          onSave={(data) => fillFormMutation.mutate({ jobId: fillFormJob.id, templateData: data })}
          onClose={() => setFillFormJobId(null)}
          isPending={fillFormMutation.isPending}
        />
      )}
    </div>
  );
}
