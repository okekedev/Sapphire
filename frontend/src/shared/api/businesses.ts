import client from "./client";
import type { Business } from "@/shared/types/business";

export async function listBusinesses(): Promise<Business[]> {
  const res = await client.get<Business[]>("/businesses");
  return res.data;
}

export async function createBusiness(data: {
  name: string;
  website?: string;
  industry?: string;
}): Promise<Business> {
  const res = await client.post<Business>("/businesses", data);
  return res.data;
}

export async function getBusiness(id: string): Promise<Business> {
  const res = await client.get<Business>(`/businesses/${id}`);
  return res.data;
}

export async function updateBusiness(
  id: string,
  data: { name?: string; website?: string; industry?: string },
): Promise<Business> {
  const res = await client.patch<Business>(`/businesses/${id}`, data);
  return res.data;
}

// ── Company Profile (predefined columns on businesses table) ──

export interface CompanyProfile {
  narrative: string | null;
}

export async function getCompanyProfile(
  id: string,
): Promise<CompanyProfile> {
  const res = await client.get<CompanyProfile>(`/businesses/${id}/company-profile`);
  return res.data;
}

export async function saveCompanyProfile(
  id: string,
  profile: Partial<CompanyProfile>,
): Promise<CompanyProfile> {
  const res = await client.put<CompanyProfile>(`/businesses/${id}/company-profile`, profile);
  return res.data;
}

// Team member management is in admin/api/team.ts (RBAC roles system)
