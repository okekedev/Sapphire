import client from "./client";

export interface Organization {
  id: string;
  business_id: string;
  name: string;
  domain: string | null;
  industry: string | null;
  website: string | null;
  notes: string | null;
  address_line1: string | null;
  city: string | null;
  state: string | null;
  zip_code: string | null;
  country: string | null;
  created_at: string;
  updated_at: string;
  contact_count: number;
}

export async function listOrganizations(
  businessId: string,
  opts?: { search?: string; limit?: number; offset?: number },
): Promise<{ organizations: Organization[]; total: number }> {
  const res = await client.get("/organizations", {
    params: {
      business_id: businessId,
      search: opts?.search,
      limit: opts?.limit ?? 100,
      offset: opts?.offset ?? 0,
    },
  });
  return res.data;
}

export async function getOrganization(
  orgId: string,
  businessId: string,
): Promise<Organization> {
  const res = await client.get(`/organizations/${orgId}`, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function createOrganization(
  businessId: string,
  payload: { name: string; domain?: string; industry?: string; website?: string; notes?: string; address_line1?: string; city?: string; state?: string; zip_code?: string; country?: string },
): Promise<Organization> {
  const res = await client.post("/organizations", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updateOrganization(
  orgId: string,
  businessId: string,
  payload: Partial<{ name: string; domain: string; industry: string; website: string; notes: string; address_line1: string; city: string; state: string; zip_code: string; country: string }>,
): Promise<Organization> {
  const res = await client.patch(`/organizations/${orgId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function deleteOrganization(
  orgId: string,
  businessId: string,
): Promise<void> {
  await client.delete(`/organizations/${orgId}`, {
    params: { business_id: businessId },
  });
}
