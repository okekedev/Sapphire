import client from "@/shared/api/client";

export interface DashboardActivity {
  interaction_id: string;
  contact_id: string | null;
  contact_name: string | null;
  type: string;
  direction: string | null;
  subject: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface DashboardSummary {
  unreviewed_calls: number;
  open_leads: number;
  overdue_jobs: number;
  recent_activity: DashboardActivity[];
}

export async function getDashboardSummary(businessId: string): Promise<DashboardSummary> {
  const res = await client.get("/dashboard/summary", {
    params: { business_id: businessId },
  });
  return res.data;
}
