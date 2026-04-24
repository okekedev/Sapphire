import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Plus } from "lucide-react";
import { Button } from "@/shared/components/ui/button";
import { PageHeader } from "@/shared/components/page-header";
import { useAppStore } from "@/shared/stores/app-store";
import {
  listCustomers, listProspects, convertToJob, getPipelineSummary, listJobs,
} from "@/sales/api/sales";
import { salesKeys, opsKeys } from "@/shared/lib/query-keys";
import { KanbanBoard } from "@/sales/components/kanban-board";
import { NewLeadDialog } from "@/sales/components/new-lead-dialog";
import { cn } from "@/shared/lib/utils";

export default function SalesPage() {
  const business = useAppStore((s) => s.activeBusiness);
  const bizId = business?.id ?? "";
  const queryClient = useQueryClient();

  const [isRefreshing, setIsRefreshing] = useState(false);
  const [showNewLeadDialog, setShowNewLeadDialog] = useState(false);

  // ── Queries ──

  const prospectsQuery = useQuery({
    queryKey: salesKeys.prospects(bizId),
    queryFn: () => listProspects(bizId),
    enabled: !!bizId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const leadsQuery = useQuery({
    queryKey: salesKeys.leads(bizId),
    queryFn: () => listCustomers(bizId, { status: "prospect", limit: 100 }),
    enabled: !!bizId,
    refetchOnWindowFocus: true,
    staleTime: 30_000,
  });

  const jobsQuery = useQuery({
    queryKey: opsKeys.jobs(bizId),
    queryFn: () => listJobs(bizId),
    enabled: !!bizId,
    staleTime: 30_000,
  });

  // ── Mutations ──

  const convertMutation = useMutation({
    mutationFn: (args: { contactId: string; title: string; description?: string; estimate?: number }) =>
      convertToJob(bizId, args.contactId, args.title, args.description, args.estimate),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: salesKeys.leads(bizId) });
      queryClient.invalidateQueries({ queryKey: salesKeys.pipelineSummary(bizId) });
      queryClient.invalidateQueries({ queryKey: opsKeys.jobs(bizId) });
      queryClient.invalidateQueries({ queryKey: opsKeys.summary(bizId) });
      queryClient.invalidateQueries({ queryKey: opsKeys.customers(bizId) });
    },
  });

  const prospects = prospectsQuery.data?.prospects ?? [];
  const leads     = leadsQuery.data?.customers ?? [];
  const jobs      = jobsQuery.data?.jobs ?? [];

  return (
    <div className="space-y-4 p-6">
      <div className="flex items-center justify-between">
        <PageHeader title="Sales" description="Inbound call pipeline — qualify leads and convert to jobs" />
        <div className="flex items-center gap-1">
          <Button size="sm" className="h-7 text-xs" onClick={() => setShowNewLeadDialog(true)}>
            <Plus className="mr-1 h-3 w-3" /> New Lead
          </Button>
          <Button
            size="sm"
            variant="ghost"
            className="h-7 w-7 p-0"
            onClick={async () => {
              setIsRefreshing(true);
              await Promise.all([
                queryClient.invalidateQueries({ queryKey: salesKeys.prospects(bizId) }),
                queryClient.invalidateQueries({ queryKey: salesKeys.leads(bizId) }),
                queryClient.invalidateQueries({ queryKey: opsKeys.jobs(bizId) }),
              ]);
              setTimeout(() => setIsRefreshing(false), 600);
            }}
            disabled={isRefreshing}
            title="Refresh"
          >
            <RefreshCw className={cn("h-3.5 w-3.5", isRefreshing && "animate-spin")} />
          </Button>
        </div>
      </div>

      <KanbanBoard
        bizId={bizId}
        prospects={prospects}
        leads={leads}
        jobs={jobs}
        isLoading={prospectsQuery.isLoading || leadsQuery.isLoading || jobsQuery.isLoading}
      />

      {showNewLeadDialog && (
        <NewLeadDialog
          businessId={bizId}
          onClose={() => setShowNewLeadDialog(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: salesKeys.leads(bizId) });
            queryClient.invalidateQueries({ queryKey: salesKeys.pipelineSummary(bizId) });
          }}
        />
      )}
    </div>
  );
}
