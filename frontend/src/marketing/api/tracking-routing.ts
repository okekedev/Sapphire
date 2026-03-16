/**
 * Tracking & Routing API — call log + aggregation endpoints.
 */
import client from "./client";

// ── Types ──

export interface CallLogItem {
  id: string;
  contact_id: string | null;
  caller_name: string | null;
  caller_phone: string | null;
  campaign_name: string | null;
  channel: string | null;
  summary: string | null;
  routed_to: string | null;
  status: string | null; // completed | followup | dropped
  score: string | null;
  next_step: string | null;
  duration_s: number | null;
  recording_url: string | null;
  disposition: string; // unreviewed | lead | spam | other
  // Department context calling fields
  department_context: string | null; // Sales | Operations | Finance | Marketing | Admin
  call_category: string | null; // inquiry, job_request, payment_inquiry, etc.
  suggested_action: string | null;
  ai_processed: boolean;
  ai_process_output: string | null;
  created_at: string;
}

export interface CallLogResponse {
  calls: CallLogItem[];
  total: number;
}

export interface DepartmentSummaryItem {
  department: string;
  total_calls: number;
  avg_duration_s: number;
  completed_count: number;
  completed_pct: number;
  followup_count: number;
  top_campaign: string | null;
  top_campaign_count: number;
}

export interface CampaignSummaryItem {
  campaign_name: string;
  total_calls: number;
  completed_count: number;
  followup_count: number;
  dropped_count: number;
  avg_duration_s: number;
}

export interface DepartmentAttribution {
  department: string;
  call_count: number;
}

export interface PhoneLineSummary {
  id: string | null;
  tracking_number: string;
  twilio_number_sid: string | null;
  friendly_name: string | null;
  campaign_name?: string;
  channel: string | null;
  line_type: string;
  shaken_stir_status: string; // "unverified" | "pending" | "verified"
  total_calls: number;
  completed_count: number;
  followup_count: number;
  dropped_count: number;
  avg_duration_s: number;
  department_breakdown: DepartmentAttribution[];
}

export async function verifyPhoneLine(
  businessId: string,
  lineId: string,
): Promise<{ status: string; trust_product_status: string; phone_line_id: string; twilio_number: string }> {
  const res = await client.post(`/tracking-routing/phone-lines/${lineId}/verify`, null, {
    params: { business_id: businessId },
  });
  return res.data;
}

// ── API calls ──

export async function listCalls(
  businessId: string,
  params?: {
    limit?: number;
    offset?: number;
    campaign_name?: string;
    status?: string;
    hide_dispositioned?: boolean;
    sort_by?: string;
    sort_order?: string;
  },
): Promise<CallLogResponse> {
  const res = await client.get("/tracking-routing/calls", {
    params: { business_id: businessId, ...params },
  });
  return res.data;
}

export async function dispositionCall(
  businessId: string,
  callId: string,
  disposition: string,
): Promise<{ status: string; disposition: string; contact_id: string | null }> {
  const res = await client.patch(
    `/tracking-routing/calls/${callId}/disposition`,
    { disposition },
    { params: { business_id: businessId } },
  );
  return res.data;
}

// ── Department Context Calling ──

export async function listDepartmentCalls(
  businessId: string,
  department: string,
  params?: { limit?: number; offset?: number; include_unrouted?: boolean },
): Promise<CallLogResponse> {
  const res = await client.get("/tracking-routing/department-calls", {
    params: { business_id: businessId, department, ...params },
  });
  return res.data;
}

export async function rerouteCall(
  businessId: string,
  callId: string,
  department: string,
): Promise<{ status: string; department_context: string; previous_department: string | null }> {
  const res = await client.patch(
    `/tracking-routing/calls/${callId}/reroute`,
    { department },
    { params: { business_id: businessId } },
  );
  return res.data;
}

export interface ProcessCallResult {
  status: string;
  employee: string | null;
  department: string | null;
  output: string | null;
  message: string | null;
}

export async function processCallWithAI(
  businessId: string,
  callId: string,
): Promise<ProcessCallResult> {
  const res = await client.post(
    `/tracking-routing/calls/${callId}/process`,
    {},
    { params: { business_id: businessId } },
  );
  return res.data;
}

export async function getDepartmentSummary(
  businessId: string,
): Promise<DepartmentSummaryItem[]> {
  const res = await client.get("/tracking-routing/department-summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function getCampaignSummary(
  businessId: string,
): Promise<CampaignSummaryItem[]> {
  const res = await client.get("/tracking-routing/campaign-summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function getPhoneLines(
  businessId: string,
): Promise<PhoneLineSummary[]> {
  const res = await client.get("/tracking-routing/tracking-number-summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

// ── Phone Settings ──

export interface DepartmentRoutingRule {
  name: string;
  department_id: string;
  forward_number: string | null;
  enabled: boolean;
  sms_enabled: boolean;
  whatsapp_enabled: boolean;
  whatsapp_sender_sid: string | null;
  whatsapp_sender_status: string;  // "none" | "CREATING" | "ONLINE" | "PENDING_VERIFICATION" | "VERIFYING" | etc
}

export interface PhoneSettingsRead {
  business_id: string;
  greeting_text: string | null;
  hold_message: string | null;
  voice_name: string;
  recording_enabled: boolean;
  transcription_enabled: boolean;
  forward_all_calls: boolean;
  default_forward_number: string | null;
  ring_timeout_s: number;
  business_hours_start: string | null;
  business_hours_end: string | null;
  business_timezone: string;
  after_hours_enabled: boolean;
  after_hours_action: string;  // "message" or "forward"
  after_hours_message: string | null;
  after_hours_forward_number: string | null;
  departments_config: DepartmentRoutingRule[] | null;
}

export interface PhoneSettingsUpdate {
  greeting_text?: string;
  hold_message?: string;
  voice_name?: string;
  recording_enabled?: boolean;
  transcription_enabled?: boolean;
  forward_all_calls?: boolean;
  default_forward_number?: string;
  ring_timeout_s?: number;
  business_hours_start?: string | null;
  business_hours_end?: string | null;
  business_timezone?: string;
  after_hours_enabled?: boolean;
  after_hours_action?: string;
  after_hours_message?: string;
  after_hours_forward_number?: string;
  departments_config?: DepartmentRoutingRule[];
}

export async function getPhoneSettings(
  businessId: string,
): Promise<PhoneSettingsRead> {
  const res = await client.get("/tracking-routing/settings", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updatePhoneSettings(
  businessId: string,
  payload: PhoneSettingsUpdate,
): Promise<PhoneSettingsRead> {
  const res = await client.put("/tracking-routing/settings", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function testGreetingCall(
  businessId: string,
  phoneNumber: string,
): Promise<{ status: string; call_sid: string; from: string; message?: string }> {
  const res = await client.post(
    "/tracking-routing/test-greeting",
    { phone_number: phoneNumber },
    { params: { business_id: businessId } },
  );
  return res.data;
}

// ── SHAKEN/STIR Trust Hub ──

export interface ShakenStirStatus {
  has_customer_profile: boolean;
  customer_profile_status: string | null;
  has_trust_product: boolean;
  trust_product_status: string | null;
  trust_product_sid: string | null;
  assigned_number_sids: string[];
  ready: boolean;
  error?: string;
}

export async function getShakenStirStatus(
  businessId: string,
): Promise<ShakenStirStatus> {
  const res = await client.get("/tracking-routing/shaken-stir/status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function setupShakenStir(
  businessId: string,
): Promise<ShakenStirStatus & { actions?: string[] }> {
  const res = await client.post(
    "/tracking-routing/shaken-stir/setup",
    {},
    { params: { business_id: businessId } },
  );
  return res.data;
}
