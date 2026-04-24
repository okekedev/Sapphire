import { useState, useEffect } from "react";
import { X, Loader2 } from "lucide-react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Button } from "@/shared/components/ui/button";
import { updateContact, type Contact, type ContactStatus } from "@/marketing/api/contacts";
import { listOrganizations } from "@/marketing/api/organizations";
import { contactKeys } from "@/shared/lib/query-keys";

const STATUS_OPTIONS: { value: ContactStatus; label: string }[] = [
  { value: "new",             label: "New" },
  { value: "prospect",        label: "Prospect" },
  { value: "active_customer", label: "Customer" },
  { value: "no_conversion",   label: "No Conversion" },
  { value: "churned",         label: "Churned" },
  { value: "other",           label: "Other" },
];

interface ContactEditSheetProps {
  contact: Contact;
  businessId: string;
  onClose: () => void;
}

export function ContactEditSheet({ contact, businessId, onClose }: ContactEditSheetProps) {
  const qc = useQueryClient();

  const [form, setForm] = useState({
    full_name:    contact.full_name    ?? "",
    phone:        contact.phone        ?? "",
    email:        contact.email        ?? "",
    status:       contact.status,
    source_channel: contact.source_channel ?? "",
    organization_id: contact.organization_id ?? "",
    contact_role: contact.contact_role ?? "",
    address_line1: contact.address_line1 ?? "",
    city:         contact.city         ?? "",
    state:        contact.state        ?? "",
    zip_code:     contact.zip_code     ?? "",
    country:      contact.country      ?? "",
    birthday:     contact.birthday     ?? "",
    notes:        contact.notes        ?? "",
  });

  const orgsQuery = useQuery({
    queryKey: ["organizations", businessId],
    queryFn: () => listOrganizations(businessId, { limit: 200 }),
    enabled: !!businessId,
  });
  const orgs = orgsQuery.data?.organizations ?? [];

  // Close on Escape
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const mutation = useMutation({
    mutationFn: () => updateContact(contact.id, businessId, {
      full_name:       form.full_name    || undefined,
      phone:           form.phone        || undefined,
      email:           form.email        || undefined,
      status:          form.status,
      source_channel:  form.source_channel || undefined,
      organization_id: form.organization_id || null,
      contact_role:    form.contact_role || null,
      address_line1:   form.address_line1 || undefined,
      city:            form.city         || undefined,
      state:           form.state        || undefined,
      zip_code:        form.zip_code     || undefined,
      country:         form.country      || undefined,
      birthday:        form.birthday     || undefined,
      notes:           form.notes        || undefined,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: contactKeys.detail(contact.id) });
      qc.invalidateQueries({ queryKey: contactKeys.list(businessId) });
      onClose();
    },
  });

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  const inputCls = "w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary transition-colors";
  const labelCls = "block text-xs font-medium text-muted-foreground mb-1";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-md flex-col bg-card shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold">Edit Contact</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={16} />
          </button>
        </div>

        {/* Form */}
        <div className="flex-1 overflow-y-auto px-5 py-4 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div className="col-span-2">
              <label className={labelCls}>Full Name</label>
              <input value={form.full_name} onChange={set("full_name")} className={inputCls} placeholder="Jane Smith" />
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
                {STATUS_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>{o.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className={labelCls}>Source</label>
              <input value={form.source_channel} onChange={set("source_channel")} className={inputCls} placeholder="call, web, referral…" />
            </div>
            <div className="col-span-2">
              <label className={labelCls}>Organization</label>
              <select value={form.organization_id} onChange={set("organization_id")} className={inputCls}>
                <option value="">— None —</option>
                {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
              </select>
            </div>
            {form.organization_id && (
              <div className="col-span-2">
                <label className={labelCls}>Role at Organization</label>
                <input value={form.contact_role} onChange={set("contact_role")} className={inputCls} placeholder="CEO, Property Manager, Decision Maker…" />
              </div>
            )}
          </div>

          <div className="border-t border-border pt-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Address</p>
            <div className="space-y-3">
              <div>
                <label className={labelCls}>Street</label>
                <input value={form.address_line1} onChange={set("address_line1")} className={inputCls} placeholder="123 Main St" />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className={labelCls}>City</label>
                  <input value={form.city} onChange={set("city")} className={inputCls} placeholder="Austin" />
                </div>
                <div>
                  <label className={labelCls}>State</label>
                  <input value={form.state} onChange={set("state")} className={inputCls} placeholder="TX" />
                </div>
                <div>
                  <label className={labelCls}>ZIP</label>
                  <input value={form.zip_code} onChange={set("zip_code")} className={inputCls} placeholder="78701" />
                </div>
                <div>
                  <label className={labelCls}>Country</label>
                  <input value={form.country} onChange={set("country")} className={inputCls} placeholder="US" />
                </div>
              </div>
            </div>
          </div>

          <div className="border-t border-border pt-3">
            <p className="text-xs font-semibold text-muted-foreground uppercase tracking-wider mb-3">Other</p>
            <div className="space-y-3">
              <div>
                <label className={labelCls}>Birthday</label>
                <input type="date" value={form.birthday} onChange={set("birthday")} className={inputCls} />
              </div>
              <div>
                <label className={labelCls}>Notes</label>
                <textarea value={form.notes} onChange={set("notes")} rows={3} className={inputCls + " resize-none"} placeholder="Internal notes about this contact…" />
              </div>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 border-t border-border px-5 py-4">
          <Button variant="ghost" size="sm" onClick={onClose}>Cancel</Button>
          <Button size="sm" disabled={mutation.isPending} onClick={() => mutation.mutate()}>
            {mutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save Changes"}
          </Button>
        </div>
      </div>
    </div>
  );
}
