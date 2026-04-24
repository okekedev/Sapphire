import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Users, Plus, Loader2, Search } from "lucide-react";
import { useAppStore } from "@/shared/stores/app-store";
import { PageHeader } from "@/shared/components/page-header";
import { Button } from "@/shared/components/ui/button";
import { Card, CardContent } from "@/shared/components/ui/card";
import { listContacts, type ContactStatus, type Contact } from "@/marketing/api/contacts";
import { cn, timeAgo } from "@/shared/lib/utils";
import { STATUS_BADGE } from "@/shared/lib/contact-status";
import { contactKeys } from "@/shared/lib/query-keys";

const STATUS_FILTERS: { value: ContactStatus | "all"; label: string }[] = [
  { value: "all",           label: "All" },
  { value: "prospect",      label: "Prospects" },
  { value: "active_customer", label: "Customers" },
  { value: "no_conversion", label: "No Conversion" },
  { value: "new",           label: "New" },
];


export default function ContactsPage() {
  const navigate = useNavigate();
  const business = useAppStore((s) => s.activeBusiness);
  const businessId = business?.id ?? "";
  const [filter, setFilter] = useState<ContactStatus | "all">("all");
  const [search, setSearch] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: contactKeys.list(businessId, filter, search),
    queryFn: () =>
      listContacts(businessId, {
        status: filter === "all" ? undefined : filter,
        search: search || undefined,
        limit: 150,
      }),
    enabled: !!businessId,
    staleTime: 30_000,
  });

  const contacts = data?.contacts ?? [];

  return (
    <div className="space-y-4 p-4 md:p-6">
      <div className="flex items-center justify-between">
        <PageHeader
          title="Contacts"
          description="All prospects, customers, and leads"
        />
        <Button
          size="sm"
          className="h-8 text-xs"
          onClick={() => navigate("/contacts/new")}
        >
          <Plus className="mr-1 h-3 w-3" /> New Contact
        </Button>
      </div>

      {/* Filters + Search */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="flex flex-wrap gap-1">
          {STATUS_FILTERS.map((f) => (
            <button
              key={f.value}
              type="button"
              onClick={() => setFilter(f.value)}
              className={cn(
                "rounded-full px-3 py-1 text-xs font-medium transition-colors",
                filter === f.value
                  ? "bg-primary text-primary-foreground"
                  : "bg-muted text-muted-foreground hover:text-foreground",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="relative ml-auto">
          <Search className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
          <input
            type="text"
            placeholder="Search name, phone, email…"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="h-8 rounded-lg border border-border bg-background pl-8 pr-3 text-xs outline-none focus:border-primary transition-colors w-52"
          />
        </div>
      </div>

      {/* Count */}
      <p className="text-xs text-muted-foreground">
        {isLoading ? "Loading…" : `${contacts.length} contact${contacts.length !== 1 ? "s" : ""}`}
      </p>

      {/* Table */}
      {isLoading ? (
        <div className="flex justify-center py-10">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : contacts.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            No contacts found
          </CardContent>
        </Card>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-border">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-xs uppercase tracking-wider text-muted-foreground">
                <th className="px-3 py-2.5 text-left">Name</th>
                <th className="hidden px-3 py-2.5 text-left sm:table-cell">Organization</th>
                <th className="px-3 py-2.5 text-left">Status</th>
                <th className="hidden px-3 py-2.5 text-left sm:table-cell">Phone</th>
                <th className="hidden px-3 py-2.5 text-left md:table-cell">Email</th>
                <th className="hidden px-3 py-2.5 text-left lg:table-cell">Source</th>
                <th className="px-3 py-2.5 text-left">Last Active</th>
              </tr>
            </thead>
            <tbody>
              {contacts.map((c: Contact) => {
                const badge = STATUS_BADGE[c.status] ?? STATUS_BADGE.other;
                return (
                  <tr
                    key={c.id}
                    className="cursor-pointer border-b last:border-0 transition hover:bg-muted/30"
                    onClick={() => navigate(`/contacts/${c.id}`)}
                  >
                    <td className="px-3 py-2.5">
                      <p className="font-medium">{c.full_name ?? "Unknown"}</p>
                      {c.phone && (
                        <p className="text-[11px] font-mono text-muted-foreground sm:hidden">{c.phone}</p>
                      )}
                    </td>
                    <td className="hidden px-3 py-2.5 text-xs text-muted-foreground sm:table-cell">
                      {c.organization_name ?? "—"}
                    </td>
                    <td className="px-3 py-2.5">
                      <span className={cn("rounded-full px-2 py-0.5 text-[11px] font-medium", badge.cls)}>
                        {badge.label}
                      </span>
                    </td>
                    <td className="hidden px-3 py-2.5 font-mono text-xs text-muted-foreground sm:table-cell">
                      {c.phone ?? "—"}
                    </td>
                    <td className="hidden px-3 py-2.5 text-xs text-muted-foreground md:table-cell">
                      {c.email ?? "—"}
                    </td>
                    <td className="hidden px-3 py-2.5 text-xs text-muted-foreground lg:table-cell">
                      {c.source_channel ?? "—"}
                    </td>
                    <td className="px-3 py-2.5 text-xs text-muted-foreground">
                      {timeAgo(c.updated_at)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
