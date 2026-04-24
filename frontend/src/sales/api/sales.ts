/**
 * Sales API — customers, jobs, and sales summary endpoints.
 */
import client from "./client";

// ── Types ──

export interface CustomerItem {
  id: string;
  full_name: string | null;
  company_name?: string | null;
  phone: string | null;
  email: string | null;
  status: string; // prospect | active_customer | no_conversion | other
  source_channel: string | null;
  acquisition_campaign: string | null;
  total_revenue: number;
  job_count: number;
  notes: string | null;
  created_at: string;
  // Call context — populated for prospects from latest Sales interaction
  call_summary: string | null;
  transcript: string | null;
  call_category: string | null;
  suggested_action: string | null;
  score: string | null;
  duration_s: number | null;
  campaign_name: string | null;
  assigned_to?: string | null;
  assigned_user_name?: string | null;
}

export interface CustomerListResponse {
  customers: CustomerItem[];
  total: number;
}

export interface JobItem {
  id: string;
  contact_id: string;
  contact_name: string | null;
  contact_phone?: string | null;
  source?: string | null;  // "sales" when converted from lead
  title: string;
  description: string | null;
  status: string; // new | scheduled | dispatched | started | completed | billing
  notes: string | null;
  amount_quoted: number | null;
  amount_billed: number | null;
  // Template
  template_id?: string | null;
  template_data?: Record<string, unknown> | null;
  // Assignment + scheduling
  assigned_to?: string | null;
  assigned_staff_name?: string | null;
  assigned_staff_color?: string | null;
  service_address?: string | null;
  scheduled_at?: string | null;
  dispatched_at?: string | null;
  // Timestamps
  started_at: string | null;
  completed_at: string | null;
  created_at: string;
  // Call context — carried from Sales lead conversion via job.metadata_
  call_summary?: string | null;
  call_category?: string | null;
  suggested_action?: string | null;
  lead_notes?: string | null;
}

export interface JobListResponse {
  jobs: JobItem[];
  total: number;
}

export interface SalesSummary {
  total_prospects: number;
  total_customers: number;
  total_no_conversion: number;
  active_jobs: number;
  completed_jobs: number;
  total_revenue: number;
  total_quoted: number;
}

// ── API calls ──

export async function listCustomers(
  businessId: string,
  params?: { status?: string; search?: string; limit?: number; offset?: number },
): Promise<CustomerListResponse> {
  const res = await client.get("/sales/customers", {
    params: { business_id: businessId, ...params },
  });
  return res.data;
}

export async function createCustomer(
  businessId: string,
  payload: { full_name: string; company_name?: string; phone?: string; email?: string; status?: string; source_channel?: string; notes?: string },
): Promise<CustomerItem> {
  const res = await client.post("/sales/customers", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function assignLead(
  businessId: string,
  contactId: string,
  userId: string | null,
): Promise<CustomerItem> {
  const res = await client.patch(`/sales/customers/${contactId}`, { assigned_to: userId }, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updateCustomer(
  businessId: string,
  customerId: string,
  payload: { full_name?: string; phone?: string; email?: string; status?: string; notes?: string },
): Promise<CustomerItem> {
  const res = await client.patch(`/sales/customers/${customerId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function listJobs(
  businessId: string,
  params?: { contact_id?: string; status?: string; limit?: number; offset?: number },
): Promise<JobListResponse> {
  const res = await client.get("/sales/jobs", {
    params: { business_id: businessId, ...params },
  });
  return res.data;
}

export async function createJob(
  businessId: string,
  payload: { contact_id: string; title: string; description?: string; notes?: string; amount_quoted?: number; template_id?: string; service_address?: string },
): Promise<JobItem> {
  const res = await client.post("/sales/jobs", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updateJob(
  businessId: string,
  jobId: string,
  payload: { title?: string; description?: string; status?: string; notes?: string; amount_quoted?: number; amount_billed?: number; template_id?: string; template_data?: Record<string, unknown>; assigned_to?: string; service_address?: string; scheduled_at?: string },
): Promise<JobItem> {
  const res = await client.patch(`/sales/jobs/${jobId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function getSalesSummary(
  businessId: string,
): Promise<SalesSummary> {
  const res = await client.get("/sales/summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

// ── Pipeline types ──

export interface ProspectItem {
  interaction_id: string;
  contact_id: string | null;
  caller_name: string | null;
  caller_phone: string | null;
  call_summary: string | null;
  transcript: string | null;
  call_category: string | null;
  suggested_action: string | null;
  score: string | null;
  duration_s: number | null;
  recording_url: string | null;
  campaign_name: string | null;
  created_at: string;
}

export interface ProspectsResponse {
  prospects: ProspectItem[];
  total: number;
}

export interface QualifyResponse {
  status: string;
  decision: string;
  contact_id: string | null;
}

export interface ConvertToJobResponse {
  status: string;
  job_id: string;
  contact_id: string;
}

export interface PipelineSummary {
  new_count: number;
  lead_count: number;
  converted_count: number;
  prospect_to_lead_pct: number;
  lead_to_job_pct: number;
}

// ── Pipeline API calls ──

export async function listProspects(
  businessId: string,
): Promise<ProspectsResponse> {
  const res = await client.get("/sales/prospects", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function qualifyProspect(
  businessId: string,
  interactionId: string,
  decision: "lead" | "no_lead",
  reason?: string,
  leadSummary?: string,
): Promise<QualifyResponse> {
  const res = await client.patch(
    `/sales/prospects/${interactionId}/qualify`,
    { decision, reason, lead_summary: leadSummary },
    { params: { business_id: businessId } },
  );
  return res.data;
}

export async function convertToJob(
  businessId: string,
  contactId: string,
  title: string,
  description?: string,
  estimate?: number,
): Promise<ConvertToJobResponse> {
  const res = await client.post(
    `/sales/leads/${contactId}/convert`,
    { title, description, estimate },
    { params: { business_id: businessId } },
  );
  return res.data;
}

export async function getPipelineSummary(
  businessId: string,
): Promise<PipelineSummary> {
  const res = await client.get("/sales/pipeline-summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

// ── Review types ──


export interface ReviewItem {
  interaction_id: string;
  contact_id: string | null;
  caller_name: string | null;
  caller_phone: string | null;
  call_summary: string | null;
  lead_summary: string | null;
  no_lead_reason: string | null;
  no_conversion_reason: string | null;
  disposition: string; // lead | converted | other | no_conversion
  call_outcome: string; // "Lead" | "No Lead"
  lead_outcome: string | null; // "Converted" | "No Conversion" | "Pending" | null
  customer_type: string | null; // "new" | "returning" | null
  recording_url: string | null;
  duration_s: number | null;
  converted_job_id: string | null;
  created_at: string;
}

export interface ReviewResponse {
  items: ReviewItem[];
  total: number;
}

export async function listReviewed(
  businessId: string,
  params?: { disposition?: string; limit?: number; offset?: number },
): Promise<ReviewResponse> {
  const res = await client.get("/sales/review", {
    params: { business_id: businessId, ...params },
  });
  return res.data;
}

