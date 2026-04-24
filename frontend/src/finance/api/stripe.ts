import client from "./client";

// ── Types ──

export interface StripeStatus {
  platform: "stripe";
  connected: boolean;
  status: string;
  account_name: string | null;
  account_id: string | null;
  connected_at: string | null;
}

export interface StripeConnectPayload {
  business_id: string;
  secret_key: string;
}

export interface StripeConnectResponse {
  connected: boolean;
  account_name: string;
  account_id: string;
  message: string;
}

// ── API calls ──

export async function getStripeStatus(businessId: string): Promise<StripeStatus> {
  const res = await client.get("/stripe/status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function connectStripe(payload: StripeConnectPayload): Promise<StripeConnectResponse> {
  const res = await client.post("/stripe/connect", payload);
  return res.data;
}

export async function disconnectStripe(businessId: string): Promise<{ status: string; message: string }> {
  const res = await client.delete("/stripe/disconnect", {
    params: { business_id: businessId },
  });
  return res.data;
}

export interface ImportResult {
  imported: number;
  updated: number;
  total: number;
  needs_org_review: Array<{
    contact_id: string;
    name: string;
    email: string | null;
    company: string;
  }>;
}

export async function importStripeCustomers(businessId: string): Promise<ImportResult> {
  const res = await client.post("/stripe/import-customers", null, {
    params: { business_id: businessId },
  });
  return res.data;
}

export interface OrgAssignment {
  contact_id: string;
  organization_id?: string;
  new_org_name?: string;
}

export async function assignOrganizations(
  businessId: string,
  assignments: OrgAssignment[],
): Promise<{ ok: boolean; assigned: number }> {
  const res = await client.post("/stripe/assign-orgs", {
    business_id: businessId,
    assignments,
  });
  return res.data;
}
