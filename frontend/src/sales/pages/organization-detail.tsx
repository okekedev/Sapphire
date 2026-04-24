import { useState } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Building2, Globe, Briefcase, Users, Pencil, Check, X, Loader2,
} from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { Card, CardContent } from "@/shared/components/ui/card";
import { Button } from "@/shared/components/ui/button";
import { getOrganization, updateOrganization } from "@/marketing/api/organizations";
import { listContacts, type Contact } from "@/marketing/api/contacts";
import { listJobs } from "@/sales/api/sales";
import { cn, timeAgo } from "@/shared/lib/utils";
import { STATUS_BADGE } from "@/shared/lib/contact-status";
import { orgKeys, contactKeys } from "@/shared/lib/query-keys";

// ── Inline editable field ─────────────────────────────
function EditableField({
  label, value, onSave, placeholder,
}: { label: string; value: string; onSave: (v: string) => void; placeholder?: string }) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value);
  return (
    <div>
      <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground mb-0.5">{label}</p>
      {editing ? (
        <div className="flex items-center gap-1.5">
          <input
            autoFocus
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => { if (e.key === "Enter") { onSave(draft); setEditing(false); } if (e.key === "Escape") setEditing(false); }}
            className="flex-1 rounded-md border border-border bg-background px-2 py-1 text-sm outline-none focus:border-primary"
            placeholder={placeholder}
          />
          <button type="button" onClick={() => { onSave(draft); setEditing(false); }} className="text-primary"><Check size={14} /></button>
          <button type="button" onClick={() => setEditing(false)} className="text-muted-foreground"><X size={14} /></button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => { setDraft(value); setEditing(true); }}
          className="group flex items-center gap-1.5 text-sm text-foreground hover:text-primary transition-colors"
        >
          <span>{value || <span className="text-muted-foreground italic">{placeholder ?? "—"}</span>}</span>
          <Pencil size={11} className="opacity-0 group-hover:opacity-100 transition-opacity" />
        </button>
      )}
    </div>
  );
}

export default function OrganizationDetailPage() {
  const { orgId } = useParams<{ orgId: string }>();
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const qc = useQueryClient();

  const orgQuery = useQuery({
    queryKey: orgKeys.detail(orgId!),
    queryFn: () => getOrganization(orgId!, businessId),
    enabled: !!orgId && !!businessId,
  });

  const contactsQuery = useQuery({
    queryKey: contactKeys.list(businessId, undefined, undefined),
    queryFn: () => listContacts(businessId, { organization_id: orgId, limit: 100 }),
    enabled: !!orgId && !!businessId,
  });

  const jobsQuery = useQuery({
    queryKey: ["org-jobs", orgId, businessId],
    queryFn: async () => {
      const contacts = contactsQuery.data?.contacts ?? [];
      if (contacts.length === 0) return { jobs: [], total: 0 };
      // Load jobs for all contacts in this org
      const allJobs = await Promise.all(
        contacts.map((c) => listJobs(businessId, { contact_id: c.id, limit: 50 }))
      );
      const jobs = allJobs.flatMap((r) => r.jobs);
      return { jobs, total: jobs.length };
    },
    enabled: !!orgId && !!businessId && contactsQuery.isSuccess,
  });

  const saveMutation = useMutation({
    mutationFn: (payload: Partial<{ name: string; domain: string; industry: string; website: string; notes: string; address_line1: string; city: string; state: string; zip_code: string; country: string }>) =>
      updateOrganization(orgId!, businessId, payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: orgKeys.detail(orgId!) }),
  });

  const org = orgQuery.data;
  const contacts: Contact[] = contactsQuery.data?.contacts ?? [];
  const jobs = jobsQuery.data?.jobs ?? [];

  const totalRevenue = jobs
    .filter((j) => j.amount_billed != null)
    .reduce((s, j) => s + (j.amount_billed ?? 0), 0);
  const totalQuoted = jobs
    .filter((j) => j.amount_quoted != null && j.amount_billed == null)
    .reduce((s, j) => s + (j.amount_quoted ?? 0), 0);

  if (orgQuery.isLoading) {
    return <div className="flex justify-center py-20"><Loader2 className="h-5 w-5 animate-spin text-muted-foreground" /></div>;
  }
  if (!org) {
    return <div className="p-6 text-center text-muted-foreground">Organization not found.</div>;
  }

  return (
    <div className="p-4 md:p-6">
      {/* Back + header */}
      <div className="mb-5 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/organizations")}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-muted">
          <Building2 className="h-4.5 w-4.5 text-muted-foreground" />
        </div>
        <div>
          <h1 className="text-lg font-semibold">{org.name}</h1>
          {org.domain && <p className="text-xs text-muted-foreground">{org.domain}</p>}
        </div>
      </div>

      <div className="flex flex-col gap-4 md:flex-row md:items-start md:gap-6">
        {/* Left: org info */}
        <div className="w-full md:w-64 md:shrink-0 space-y-4">
          <Card>
            <CardContent className="p-4 space-y-3">
              <EditableField label="Name" value={org.name} onSave={(v) => saveMutation.mutate({ name: v })} placeholder="Organization name" />
              <EditableField label="Domain" value={org.domain ?? ""} onSave={(v) => saveMutation.mutate({ domain: v })} placeholder="acme.com" />
              <EditableField label="Industry" value={org.industry ?? ""} onSave={(v) => saveMutation.mutate({ industry: v })} placeholder="Real Estate" />
              <EditableField label="Website" value={org.website ?? ""} onSave={(v) => saveMutation.mutate({ website: v })} placeholder="https://…" />
              {org.website && (
                <a href={org.website} target="_blank" rel="noopener noreferrer" className="flex items-center gap-1.5 text-xs text-primary hover:underline">
                  <Globe size={11} /> {org.website}
                </a>
              )}
              <div className="border-t border-border pt-3 space-y-2">
                <p className="text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">Address</p>
                <EditableField label="Street" value={org.address_line1 ?? ""} onSave={(v) => saveMutation.mutate({ address_line1: v })} placeholder="123 Main St" />
                <div className="grid grid-cols-2 gap-2">
                  <EditableField label="City" value={org.city ?? ""} onSave={(v) => saveMutation.mutate({ city: v })} placeholder="Austin" />
                  <EditableField label="State" value={org.state ?? ""} onSave={(v) => saveMutation.mutate({ state: v })} placeholder="TX" />
                  <EditableField label="ZIP" value={org.zip_code ?? ""} onSave={(v) => saveMutation.mutate({ zip_code: v })} placeholder="78701" />
                  <EditableField label="Country" value={org.country ?? ""} onSave={(v) => saveMutation.mutate({ country: v })} placeholder="US" />
                </div>
              </div>
              <EditableField label="Notes" value={org.notes ?? ""} onSave={(v) => saveMutation.mutate({ notes: v })} placeholder="Internal notes…" />
            </CardContent>
          </Card>

          {/* Stats */}
          <Card>
            <CardContent className="p-4 space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground flex items-center gap-1.5"><Users size={11} /> Contacts</span>
                <span className="font-semibold">{contacts.length}</span>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-muted-foreground flex items-center gap-1.5"><Briefcase size={11} /> Jobs</span>
                <span className="font-semibold">{jobs.length}</span>
              </div>
              {totalRevenue > 0 && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Billed</span>
                  <span className="font-semibold text-green-600">${totalRevenue.toLocaleString()}</span>
                </div>
              )}
              {totalQuoted > 0 && (
                <div className="flex items-center justify-between text-xs">
                  <span className="text-muted-foreground">Pipeline</span>
                  <span className="font-semibold text-amber-600">${totalQuoted.toLocaleString()}</span>
                </div>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Right: contacts list */}
        <div className="flex-1 min-w-0">
          <h2 className="mb-3 text-sm font-semibold">Contacts</h2>
          {contactsQuery.isLoading ? (
            <div className="flex justify-center py-8"><Loader2 className="h-4 w-4 animate-spin text-muted-foreground" /></div>
          ) : contacts.length === 0 ? (
            <Card>
              <CardContent className="py-8 text-center text-sm text-muted-foreground">
                No contacts linked to this organization.
                <br />
                <button
                  type="button"
                  onClick={() => navigate("/contacts/new")}
                  className="mt-2 text-primary hover:underline text-xs"
                >
                  Create a contact
                </button>
              </CardContent>
            </Card>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-border">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                    <th className="px-3 py-2.5 text-left">Name</th>
                    <th className="hidden px-3 py-2.5 text-left sm:table-cell">Role</th>
                    <th className="px-3 py-2.5 text-left">Status</th>
                    <th className="hidden px-3 py-2.5 text-left sm:table-cell">Phone</th>
                    <th className="px-3 py-2.5 text-left">Last Active</th>
                  </tr>
                </thead>
                <tbody>
                  {contacts.map((c) => {
                    const badge = STATUS_BADGE[c.status] ?? STATUS_BADGE.other;
                    return (
                      <tr
                        key={c.id}
                        className="cursor-pointer border-b last:border-0 transition hover:bg-muted/30"
                        onClick={() => navigate(`/contacts/${c.id}`)}
                      >
                        <td className="px-3 py-2.5 font-medium">{c.full_name ?? "Unknown"}</td>
                        <td className="hidden px-3 py-2.5 text-xs text-muted-foreground sm:table-cell">{c.contact_role ?? "—"}</td>
                        <td className="px-3 py-2.5">
                          <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", badge.cls)}>{badge.label}</span>
                        </td>
                        <td className="hidden px-3 py-2.5 font-mono text-xs text-muted-foreground sm:table-cell">{c.phone ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground">{timeAgo(c.updated_at)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Jobs section */}
          {jobs.length > 0 && (
            <div className="mt-6">
              <h2 className="mb-3 text-sm font-semibold">Jobs</h2>
              <div className="overflow-x-auto rounded-lg border border-border">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                      <th className="px-3 py-2.5 text-left">Title</th>
                      <th className="px-3 py-2.5 text-left">Contact</th>
                      <th className="px-3 py-2.5 text-left">Status</th>
                      <th className="px-3 py-2.5 text-right">Amount</th>
                    </tr>
                  </thead>
                  <tbody>
                    {jobs.map((j) => (
                      <tr key={j.id} className="border-b last:border-0">
                        <td className="px-3 py-2.5 font-medium">{j.title}</td>
                        <td className="px-3 py-2.5 text-xs text-muted-foreground">{j.contact_name ?? "—"}</td>
                        <td className="px-3 py-2.5 text-xs capitalize text-muted-foreground">{j.status.replace("_", " ")}</td>
                        <td className="px-3 py-2.5 text-right text-xs font-medium">
                          {j.amount_billed != null
                            ? <span className="text-green-600">${j.amount_billed.toLocaleString()}</span>
                            : j.amount_quoted != null
                            ? <span className="text-amber-600">${j.amount_quoted.toLocaleString()}</span>
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
