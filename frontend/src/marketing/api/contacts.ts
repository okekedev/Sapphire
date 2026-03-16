import client from "./client";

// ── Types ──

export type ContactStatus = "prospect" | "active_customer" | "churned";

export type InteractionType =
  | "call"
  | "email"
  | "form_submit"
  | "sms"
  | "fb_message"
  | "payment"
  | "note";

export interface Interaction {
  id: string;
  business_id: string;
  contact_id: string;
  type: InteractionType;
  direction: string | null;
  subject: string | null;
  body: string | null;
  metadata: Record<string, unknown> | null;
  created_by: string | null;
  created_at: string;
}

export interface Contact {
  id: string;
  business_id: string;
  full_name: string | null;
  phone: string | null;
  phone_verified: boolean;
  email: string | null;
  email_verified: boolean;
  status: ContactStatus;
  source_channel: string | null;
  campaign_id: string | null;
  utm_source: string | null;
  utm_medium: string | null;
  utm_campaign: string | null;
  stripe_customer_id: string | null;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  country: string | null;
  notes: string | null;
  created_at: string;
  updated_at: string;
  interactions?: Interaction[];
}

export interface CRMSummary {
  prospects: number;
  active_customers: number;
  churned: number;
  total: number;
  interactions_today: number;
}

export interface PhoneLine {
  id: string;
  business_id: string;
  department_id: string | null;
  twilio_number: string;
  twilio_number_sid: string | null;
  friendly_name: string | null;
  campaign_name?: string;
  ad_account_id: string | null;
  channel: string | null;
  line_type: string;
  shaken_stir_status: string; // "unverified" | "pending" | "verified"
  active: boolean;
  created_at: string;
  updated_at: string;
}

// ── Contact API ──

export async function getCRMSummary(businessId: string): Promise<CRMSummary> {
  const res = await client.get("/contacts/summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function listContacts(
  businessId: string,
  opts?: {
    status?: ContactStatus;
    search?: string;
    limit?: number;
    offset?: number;
  },
): Promise<{ contacts: Contact[]; total: number }> {
  const res = await client.get("/contacts", {
    params: {
      business_id: businessId,
      status: opts?.status,
      search: opts?.search,
      limit: opts?.limit ?? 100,
      offset: opts?.offset ?? 0,
    },
  });
  return res.data;
}

export async function getContact(
  contactId: string,
  businessId: string,
): Promise<Contact> {
  const res = await client.get(`/contacts/${contactId}`, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function createContact(
  businessId: string,
  payload: {
    full_name?: string;
    phone?: string;
    email?: string;
    status?: ContactStatus;
    source_channel?: string;
    notes?: string;
  },
): Promise<Contact> {
  const res = await client.post("/contacts", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updateContact(
  contactId: string,
  businessId: string,
  payload: Partial<{
    full_name: string;
    phone: string;
    phone_verified: boolean;
    email: string;
    email_verified: boolean;
    status: ContactStatus;
    source_channel: string;
    notes: string;
    stripe_customer_id: string;
    city: string;
    state: string;
    zip_code: string;
    country: string;
  }>,
): Promise<Contact> {
  const res = await client.patch(`/contacts/${contactId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updateContactStatus(
  contactId: string,
  businessId: string,
  status: ContactStatus,
): Promise<Contact> {
  const res = await client.patch(
    `/contacts/${contactId}/status`,
    { status },
    { params: { business_id: businessId } },
  );
  return res.data;
}

export async function deleteContact(
  contactId: string,
  businessId: string,
): Promise<void> {
  await client.delete(`/contacts/${contactId}`, {
    params: { business_id: businessId },
  });
}

export async function logInteraction(
  contactId: string,
  businessId: string,
  payload: {
    type: InteractionType;
    direction?: string;
    subject?: string;
    body?: string;
    metadata?: Record<string, unknown>;
  },
): Promise<Interaction> {
  const res = await client.post(
    `/contacts/${contactId}/interactions`,
    payload,
    { params: { business_id: businessId } },
  );
  return res.data;
}

// ── Phone Lines ──

export async function getPhoneLines(
  businessId: string,
): Promise<PhoneLine[]> {
  const res = await client.get("/phone-lines", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function createPhoneLine(
  businessId: string,
  payload: {
    twilio_number: string;
    campaign_name?: string;
    friendly_name?: string;
    channel?: string;
    ad_account_id?: string;
    department_id?: string;
    line_type?: string;
  },
): Promise<PhoneLine> {
  const res = await client.post("/phone-lines", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updatePhoneLine(
  businessId: string,
  phoneLineId: string,
  payload: {
    friendly_name?: string;
    campaign_name?: string;
    channel?: string;
    line_type?: string;
    department_id?: string | null;
    active?: boolean;
  },
): Promise<PhoneLine> {
  const res = await client.patch(`/phone-lines/${phoneLineId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function deletePhoneLine(
  businessId: string,
  phoneLineId: string,
): Promise<void> {
  await client.delete(`/phone-lines/${phoneLineId}`, {
    params: { business_id: businessId },
  });
}
