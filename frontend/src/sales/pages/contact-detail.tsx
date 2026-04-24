import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Phone, Mail, PhoneCall, FileText, Briefcase,
  Loader2, Send, Pencil,
} from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { getContact, logInteraction, type Contact, type Interaction } from "@/marketing/api/contacts";
import { listJobs, type JobItem } from "@/sales/api/sales";
import { contactKeys } from "@/shared/lib/query-keys";
import { cn, timeAgo } from "@/shared/lib/utils";
import { ScoreBadge } from "@/shared/components/ui/score-badge";
import { STATUS_BADGE } from "@/shared/lib/contact-status";
import { formatDuration } from "@/shared/lib/format";
import { ContactEditSheet } from "@/sales/components/contact-edit-sheet";

// ── Job status badge ──────────────────────────────────
const JOB_STATUS: Record<string, { label: string; cls: string }> = {
  new: { label: "New", cls: "bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300" },
  in_progress: { label: "In Progress", cls: "bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300" },
  completed: { label: "Completed", cls: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300" },
  billed: { label: "Billed", cls: "bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300" },
};

// ── Timeline types ────────────────────────────────────
type TimelineItem =
  | { kind: "interaction"; data: Interaction; date: string }
  | { kind: "job"; data: JobItem; date: string };


// ── Timeline item ─────────────────────────────────────
function TimelineRow({ item }: { item: TimelineItem }) {
  if (item.kind === "job") {
    const j = item.data;
    const badge = JOB_STATUS[j.status] ?? JOB_STATUS.new;
    return (
      <div className="flex gap-3 py-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900/40">
          <Briefcase className="h-3.5 w-3.5 text-amber-600 dark:text-amber-400" />
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{j.title}</span>
            <span className={cn("rounded-full px-1.5 py-0.5 text-[10px] font-medium", badge.cls)}>
              {badge.label}
            </span>
          </div>
          {(j.amount_quoted != null || j.amount_billed != null) && (
            <p className="mt-0.5 text-xs text-muted-foreground">
              {j.amount_billed != null ? `Billed $${j.amount_billed.toLocaleString()}` :
               j.amount_quoted != null ? `Quoted $${j.amount_quoted.toLocaleString()}` : ""}
            </p>
          )}
          <p className="mt-0.5 text-[11px] text-muted-foreground">{timeAgo(item.date)}</p>
        </div>
      </div>
    );
  }

  const i = item.data;
  const meta = i.metadata as Record<string, unknown> | null ?? {};

  if (i.type === "call") {
    const summary = meta.summary as string ?? i.subject ?? "";
    const dept = meta.routed_to_department as string ?? meta.department_context as string ?? "";
    const duration = meta.duration_s as number;
    return (
      <div className="flex gap-3 py-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-blue-100 dark:bg-blue-900/40">
          <PhoneCall className="h-3.5 w-3.5 text-blue-600 dark:text-blue-400" />
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">Call</span>
            <ScoreBadge score={meta.score as string | number | null} />
            {dept && <span className="text-[10px] text-muted-foreground">→ {dept}</span>}
          </div>
          {summary && <p className="mt-0.5 text-xs text-muted-foreground line-clamp-2">{summary}</p>}
          <p className="mt-0.5 text-[11px] text-muted-foreground">
            {timeAgo(item.date)}{duration ? ` · ${formatDuration(duration)}` : ""}
          </p>
        </div>
      </div>
    );
  }

  if (i.type === "note") {
    return (
      <div className="flex gap-3 py-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-100 dark:bg-slate-800">
          <FileText className="h-3.5 w-3.5 text-slate-500" />
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <p className="text-xs text-foreground leading-relaxed">{i.body ?? ""}</p>
          <p className="mt-0.5 text-[11px] text-muted-foreground">{timeAgo(item.date)}</p>
        </div>
      </div>
    );
  }

  if (i.type === "email") {
    return (
      <div className="flex gap-3 py-3">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-100 dark:bg-violet-900/40">
          <Mail className="h-3.5 w-3.5 text-violet-600 dark:text-violet-400" />
        </div>
        <div className="min-w-0 flex-1 pt-0.5">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium">Email</span>
            {i.direction && (
              <span className="text-[10px] text-muted-foreground">{i.direction}</span>
            )}
          </div>
          {i.subject && <p className="mt-0.5 text-xs text-muted-foreground">{i.subject}</p>}
          <p className="mt-0.5 text-[11px] text-muted-foreground">{timeAgo(item.date)}</p>
        </div>
      </div>
    );
  }

  // Generic fallback
  return (
    <div className="flex gap-3 py-3">
      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
        <Phone className="h-3.5 w-3.5 text-muted-foreground" />
      </div>
      <div className="min-w-0 flex-1 pt-0.5">
        <span className="text-xs text-muted-foreground capitalize">{i.type}</span>
        {i.subject && <p className="text-sm">{i.subject}</p>}
        <p className="mt-0.5 text-[11px] text-muted-foreground">{timeAgo(item.date)}</p>
      </div>
    </div>
  );
}

// ── Add Note form ─────────────────────────────────────
function AddNoteForm({ contactId, businessId }: { contactId: string; businessId: string }) {
  const [note, setNote] = useState("");
  const qc = useQueryClient();
  const mutation = useMutation({
    mutationFn: () =>
      logInteraction(contactId, businessId, { type: "note", body: note }),
    onSuccess: () => {
      setNote("");
      qc.invalidateQueries({ queryKey: contactKeys.detail(contactId) });
    },
  });
  return (
    <form
      onSubmit={(e) => { e.preventDefault(); if (note.trim()) mutation.mutate(); }}
      className="flex gap-2 mt-3"
    >
      <input
        value={note}
        onChange={(e) => setNote(e.target.value)}
        placeholder="Add a note…"
        className="flex-1 rounded-lg border border-border bg-background px-3 py-1.5 text-xs outline-none focus:border-primary transition-colors"
        disabled={mutation.isPending}
      />
      <button
        type="submit"
        disabled={!note.trim() || mutation.isPending}
        className="rounded-lg bg-primary px-2.5 py-1.5 text-primary-foreground disabled:opacity-40 hover:bg-primary/90 transition-colors"
      >
        {mutation.isPending ? <Loader2 size={12} className="animate-spin" /> : <Send size={12} />}
      </button>
    </form>
  );
}

// ── Main component ────────────────────────────────────
export default function ContactDetailPage() {
  const { contactId } = useParams<{ contactId: string }>();
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const [showEdit, setShowEdit] = useState(false);

  const contactQuery = useQuery({
    queryKey: contactKeys.detail(contactId!),
    queryFn: () => getContact(contactId!, businessId),
    enabled: !!contactId && !!businessId,
  });

  const jobsQuery = useQuery({
    queryKey: contactKeys.jobs(contactId!, businessId),
    queryFn: () => listJobs(businessId, { contact_id: contactId }),
    enabled: !!contactId && !!businessId,
  });

  const contact: Contact | undefined = contactQuery.data;
  const interactions: Interaction[] = contact?.interactions ?? [];
  const jobs: JobItem[] = jobsQuery.data?.jobs ?? [];

  // Build unified sorted timeline
  const timeline: TimelineItem[] = [
    ...interactions.map((i) => ({ kind: "interaction" as const, data: i, date: i.created_at })),
    ...jobs.map((j) => ({ kind: "job" as const, data: j, date: j.created_at })),
  ].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());

  if (contactQuery.isLoading) {
    return (
      <div className="flex justify-center py-20">
        <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (!contact) {
    return (
      <div className="p-6 text-center text-muted-foreground">Contact not found.</div>
    );
  }

  const badge = STATUS_BADGE[contact.status] ?? STATUS_BADGE.new;

  return (
    <div className="p-4 md:p-6">
      {/* Back + header */}
      <div className="mb-4 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/contacts")}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-lg font-semibold md:text-xl">{contact.full_name ?? "Unknown"}</h1>
            <span className={cn("rounded-full px-2.5 py-0.5 text-[11px] font-medium", badge.cls)}>
              {badge.label}
            </span>
          </div>
        </div>
        <button
          type="button"
          onClick={() => setShowEdit(true)}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition-colors"
          title="Edit contact"
        >
          <Pencil size={15} />
        </button>
      </div>

      {showEdit && (
        <ContactEditSheet contact={contact} businessId={businessId} onClose={() => setShowEdit(false)} />
      )}

      {/* Two-column layout */}
      <div className="flex flex-col gap-4 md:flex-row md:gap-6 md:items-start">

        {/* Left: Contact info */}
        <div className="w-full md:w-64 md:shrink-0 space-y-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              {contact.phone && (
                <div className="flex items-center gap-2 text-sm">
                  <Phone className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="font-mono text-xs">{contact.phone}</span>
                </div>
              )}
              {contact.email && (
                <div className="flex items-center gap-2 text-sm">
                  <Mail className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
                  <span className="text-xs truncate">{contact.email}</span>
                </div>
              )}
              {contact.source_channel && (
                <div className="text-xs text-muted-foreground">
                  Source: <span className="text-foreground">{contact.source_channel}</span>
                </div>
              )}
              {jobs.length > 0 && (
                <div className="text-xs text-muted-foreground">
                  Jobs: <span className="font-medium text-foreground">{jobs.length}</span>
                  {" "}·{" "}Revenue:{" "}
                  <span className="font-medium text-foreground">
                    ${jobs
                      .filter((j) => j.amount_billed != null)
                      .reduce((sum, j) => sum + (j.amount_billed ?? 0), 0)
                      .toLocaleString()}
                  </span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: Activity timeline */}
        <div className="flex-1 min-w-0">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-sm font-semibold">Activity</h2>
          </div>

          <Card>
            <CardContent className="px-4 py-2">
              <AddNoteForm contactId={contact.id} businessId={businessId} />
              {timeline.length === 0 ? (
                <p className="py-8 text-center text-sm text-muted-foreground">No activity yet</p>
              ) : (
                <div className="divide-y divide-border">
                  {timeline.map((item, idx) => (
                    <TimelineRow key={item.kind + "-" + idx} item={item} />
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
