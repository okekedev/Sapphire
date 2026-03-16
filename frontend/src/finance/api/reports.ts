/**
 * Reports API — campaign ROI, customer lifecycle, department performance.
 */
import client from "./client";

// ── Types ──

export interface CampaignROIItem {
  campaign_name: string;
  calls_generated: number;
  contacts_created: number;
  customers_converted: number;
  revenue_attributed: number;
  conversion_rate: number;
  avg_deal_size: number;
}

export interface CustomerLifecycleItem {
  contact_id: string;
  contact_name: string | null;
  contact_phone: string | null;
  contact_email: string | null;
  first_call_date: string | null;
  first_invoice_date: string | null;
  is_new_customer: boolean;
  lifetime_revenue: number;
  status: string | null;
}

export interface DepartmentPerformanceItem {
  department: string;
  calls_handled: number;
  contacts_generated: number;
  revenue_attributed: number;
  avg_duration_s: number;
}

// ── API calls ──

export async function getCampaignROI(
  businessId: string,
  days: number = 30,
): Promise<CampaignROIItem[]> {
  const res = await client.get("/reports/campaign-roi", {
    params: { business_id: businessId, days },
  });
  return res.data;
}

export async function getCustomerLifecycle(
  businessId: string,
): Promise<CustomerLifecycleItem[]> {
  const res = await client.get("/reports/customer-lifecycle", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function getDepartmentPerformance(
  businessId: string,
  days: number = 30,
): Promise<DepartmentPerformanceItem[]> {
  const res = await client.get("/reports/department-performance", {
    params: { business_id: businessId, days },
  });
  return res.data;
}

// ── Pipeline Funnel ──

export interface FunnelStage {
  stage: string;
  label: string;
  total: number;
  new_customers: number;
  returning_customers: number;
  from_campaigns: number;
  manual: number;
  revenue: number;
  conversion_pct: number;
}

export interface CampaignAttribution {
  campaign_name: string;
  channel: string | null;
  calls: number;
  leads: number;
  jobs: number;
  revenue: number;
  new_customers: number;
  returning_customers: number;
}

export interface PipelineFunnelResponse {
  stages: FunnelStage[];
  campaigns: CampaignAttribution[];
  totals: Record<string, number>;
  period_days: number;
}

export async function getPipelineFunnel(
  businessId: string,
  days: number = 30,
): Promise<PipelineFunnelResponse> {
  const res = await client.get("/reports/pipeline-funnel", {
    params: { business_id: businessId, days },
  });
  return res.data;
}
