import client from "./client";

// ── Types ──

export interface EmailSendPayload {
  contact_id: string;
  subject: string;
  body: string;
  from_address?: string;
  reply_to?: string;
  campaign_slug?: string;
}

export interface EmailSendResponse {
  sent: boolean;
  interaction_id: string;
  message_id: string;
}

export interface AIFollowupPayload {
  contact_id: string;
  lead_id?: string;
  tone?: string;
}

export interface AIFollowupResponse {
  draft: string;
  contact_name: string | null;
  contact_email: string | null;
}

export interface EmailThreadItem {
  id: string;
  direction: string | null;
  subject: string | null;
  body: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string | null;
  created_by: string | null;
}

// ── API Functions ──

export async function sendEmail(
  businessId: string,
  payload: EmailSendPayload,
): Promise<EmailSendResponse> {
  const res = await client.post("/email/send", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function generateAIFollowup(
  businessId: string,
  payload: AIFollowupPayload,
): Promise<AIFollowupResponse> {
  const res = await client.post("/email/ai-followup", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function getEmailThread(
  contactId: string,
  businessId: string,
): Promise<{ emails: EmailThreadItem[] }> {
  const res = await client.get(`/email/thread/${contactId}`, {
    params: { business_id: businessId },
  });
  return res.data;
}
