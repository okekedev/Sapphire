import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus, Loader2, Search, X } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import {
  listOrganizations,
  createOrganization,
  type Organization,
} from "@/marketing/api/organizations";
import { cn } from "@/shared/lib/utils";
import { orgKeys } from "@/shared/lib/query-keys";

// ── Create dialog ──────────────────────────────────────
function CreateOrgDialog({
  businessId,
  onClose,
}: {
  businessId: string;
  onClose: () => void;
}) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [domain, setDomain] = useState("");
  const [industry, setIndustry] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      createOrganization(businessId, {
        name,
        domain: domain || undefined,
        industry: industry || undefined,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: orgKeys.list(businessId) });
      onClose();
    },
  });

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="w-full max-w-md rounded-xl border border-border bg-card shadow-xl">
        <div className="flex items-center justify-between border-b border-border px-5 py-4">
          <h2 className="text-sm font-semibold">New Organization</h2>
          <button type="button" onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <X size={15} />
          </button>
        </div>
        <form
          onSubmit={(e) => { e.preventDefault(); if (name.trim()) mutation.mutate(); }}
          className="space-y-4 p-5"
        >
          <div>
            <label className="mb-1 block text-xs font-medium text-muted-foreground">Name *</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Acme Property Management"
              className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
              required
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Domain</label>
              <input
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
                placeholder="acme.com"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
              />
            </div>
            <div>
              <label className="mb-1 block text-xs font-medium text-muted-foreground">Industry</label>
              <input
                value={industry}
                onChange={(e) => setIndustry(e.target.value)}
                placeholder="Real Estate"
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:border-primary transition-colors"
              />
            </div>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="ghost" size="sm" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" size="sm" disabled={!name.trim() || mutation.isPending}>
              {mutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Create"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

// ── Main page ──────────────────────────────────────────
export default function OrganizationsPage() {
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const [search, setSearch] = useState("");
  const [creating, setCreating] = useState(false);

  const { data, isLoading } = useQuery({
    queryKey: orgKeys.list(businessId, search),
    queryFn: () => listOrganizations(businessId, { search: search || undefined }),
    enabled: !!businessId,
    staleTime: 30_000,
  });

  const orgs = data?.organizations ?? [];

  return (
    <div className="space-y-4 p-4 md:p-6">
      {creating && (
        <CreateOrgDialog businessId={businessId} onClose={() => setCreating(false)} />
      )}

      <div className="flex items-center justify-between">
        <PageHeader title="Organizations" description="B2B accounts and company groups" />
        <Button size="sm" className="h-8 text-xs" onClick={() => setCreating(true)}>
          <Plus className="mr-1 h-3 w-3" /> New Org
        </Button>
      </div>

      {/* Search */}
      <div className="relative max-w-xs">
        <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
        <input
          type="text"
          placeholder="Search organizations…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="h-8 w-full rounded-lg border border-border bg-background pl-8 pr-3 text-xs outline-none focus:border-primary transition-colors"
        />
      </div>

      <p className="text-xs text-muted-foreground">
        {isLoading ? "Loading…" : `${orgs.length} organization${orgs.length !== 1 ? "s" : ""}`}
      </p>

      {isLoading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : orgs.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No organizations yet. Create one to group B2B contacts.
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2.5 text-left">Organization</th>
                <th className="hidden px-3 py-2.5 text-left sm:table-cell">Domain</th>
                <th className="hidden px-3 py-2.5 text-left md:table-cell">Industry</th>
                <th className="px-3 py-2.5 text-right">Contacts</th>
              </tr>
            </thead>
            <tbody>
              {orgs.map((org: Organization) => (
                <tr
                  key={org.id}
                  className="cursor-pointer border-b last:border-0 transition hover:bg-muted/30"
                  onClick={() => navigate(`/contacts?organization_id=${org.id}`)}
                >
                  <td className="px-3 py-2.5">
                    <div className="flex items-center gap-2">
                      <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-muted">
                        <Building2 className="h-3.5 w-3.5 text-muted-foreground" />
                      </div>
                      <div>
                        <p className="font-medium">{org.name}</p>
                        {org.domain && (
                          <p className="text-[11px] text-muted-foreground sm:hidden">{org.domain}</p>
                        )}
                      </div>
                    </div>
                  </td>
                  <td className="hidden px-3 py-2.5 text-xs text-muted-foreground sm:table-cell">
                    {org.domain ?? "—"}
                  </td>
                  <td className="hidden px-3 py-2.5 text-xs text-muted-foreground md:table-cell">
                    {org.industry ?? "—"}
                  </td>
                  <td className="px-3 py-2.5 text-right text-xs font-medium">
                    {org.contact_count}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
