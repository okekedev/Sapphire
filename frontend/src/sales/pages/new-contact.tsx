import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, Loader2, Plus } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { createContact, type ContactStatus } from "@/marketing/api/contacts";
import { listOrganizations, createOrganization } from "@/marketing/api/organizations";

const STATUS_OPTIONS: { value: ContactStatus; label: string }[] = [
  { value: "new",             label: "New" },
  { value: "prospect",        label: "Prospect" },
  { value: "active_customer", label: "Customer" },
  { value: "no_conversion",   label: "No Conversion" },
];

export default function NewContactPage() {
  const navigate = useNavigate();
  const qc = useQueryClient();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";

  const [form, setForm] = useState({
    full_name: "",
    phone: "",
    email: "",
    status: "new" as ContactStatus,
    source_channel: "",
    organization_id: "",
    contact_role: "",
    notes: "",
  });

  // Inline org creation
  const [creatingOrg, setCreatingOrg] = useState(false);
  const [newOrgName, setNewOrgName] = useState("");

  const orgsQuery = useQuery({
    queryKey: ["organizations", businessId],
    queryFn: () => listOrganizations(businessId, { limit: 200 }),
    enabled: !!businessId,
  });
  const orgs = orgsQuery.data?.organizations ?? [];

  const createOrgMutation = useMutation({
    mutationFn: () => createOrganization(businessId, { name: newOrgName.trim() }),
    onSuccess: (org) => {
      qc.invalidateQueries({ queryKey: ["organizations", businessId] });
      setForm((f) => ({ ...f, organization_id: org.id }));
      setCreatingOrg(false);
      setNewOrgName("");
    },
  });

  const mutation = useMutation({
    mutationFn: () => createContact(businessId, {
      full_name:       form.full_name      || undefined,
      phone:           form.phone          || undefined,
      email:           form.email          || undefined,
      status:          form.status,
      source_channel:  form.source_channel || undefined,
      organization_id: form.organization_id || undefined,
      contact_role:    form.contact_role   || undefined,
      notes:           form.notes          || undefined,
    }),
    onSuccess: (contact) => navigate(`/contacts/${contact.id}`),
  });

  const set = (k: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [k]: e.target.value }));

  const inputCls = "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary transition-colors";
  const labelCls = "block text-xs font-medium text-muted-foreground mb-1";

  const canSubmit = !!form.organization_id;

  return (
    <div className="p-4 md:p-6 max-w-xl">
      <div className="mb-6 flex items-center gap-3">
        <button
          type="button"
          onClick={() => navigate("/contacts")}
          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted transition-colors"
        >
          <ArrowLeft size={16} />
        </button>
        <h1 className="text-lg font-semibold">New Contact</h1>
      </div>

      <Card>
        <CardContent className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className={labelCls}>Full Name</label>
              <input value={form.full_name} onChange={set("full_name")} className={inputCls} placeholder="Jane Smith" autoFocus />
            </div>
            <div>
              <label className={labelCls}>Phone</label>
              <input value={form.phone} onChange={set("phone")} className={inputCls} placeholder="+1 555 000 0000" />
            </div>
            <div>
              <label className={labelCls}>Email</label>
              <input type="email" value={form.email} onChange={set("email")} className={inputCls} placeholder="jane@example.com" />
            </div>
            <div>
              <label className={labelCls}>Status</label>
              <select value={form.status} onChange={set("status")} className={inputCls}>
                {STATUS_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
              </select>
            </div>
            <div>
              <label className={labelCls}>Source</label>
              <input value={form.source_channel} onChange={set("source_channel")} className={inputCls} placeholder="call, web, referral…" />
            </div>

            {/* Organization — required */}
            <div className="col-span-2">
              <div className="flex items-center justify-between mb-1">
                <label className="text-xs font-medium text-muted-foreground">
                  Organization <span className="text-destructive">*</span>
                </label>
                {!creatingOrg && (
                  <button
                    type="button"
                    onClick={() => setCreatingOrg(true)}
                    className="flex items-center gap-0.5 text-xs text-primary hover:underline"
                  >
                    <Plus size={11} /> New Org
                  </button>
                )}
              </div>
              {creatingOrg ? (
                <div className="flex gap-2">
                  <input
                    autoFocus
                    value={newOrgName}
                    onChange={(e) => setNewOrgName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter" && newOrgName.trim()) createOrgMutation.mutate(); if (e.key === "Escape") setCreatingOrg(false); }}
                    className={inputCls + " flex-1"}
                    placeholder="Organization name"
                  />
                  <Button
                    size="sm"
                    disabled={!newOrgName.trim() || createOrgMutation.isPending}
                    onClick={() => createOrgMutation.mutate()}
                  >
                    {createOrgMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
                  </Button>
                  <Button variant="ghost" size="sm" onClick={() => setCreatingOrg(false)}>Cancel</Button>
                </div>
              ) : (
                <select value={form.organization_id} onChange={set("organization_id")} className={inputCls}>
                  <option value="">— Select organization —</option>
                  {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              )}
            </div>

            {form.organization_id && (
              <div className="col-span-2">
                <label className={labelCls}>Role at Organization</label>
                <input value={form.contact_role} onChange={set("contact_role")} className={inputCls} placeholder="CEO, Property Manager, Decision Maker…" />
              </div>
            )}
            <div className="col-span-2">
              <label className={labelCls}>Notes</label>
              <textarea value={form.notes} onChange={set("notes")} rows={3} className={inputCls + " resize-none"} placeholder="Initial notes…" />
            </div>
          </div>

          {mutation.isError && (
            <p className="text-xs text-destructive">Failed to create contact. Please try again.</p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="ghost" size="sm" onClick={() => navigate("/contacts")}>Cancel</Button>
            <Button size="sm" disabled={mutation.isPending || !canSubmit} onClick={() => mutation.mutate()}>
              {mutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create Contact"}
            </Button>
          </div>
          {!canSubmit && (
            <p className="text-[11px] text-muted-foreground text-right -mt-2">Select or create an organization to continue</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
