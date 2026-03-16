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
  description: string | null;
  services: string | null;
  target_audience: string | null;
  online_presence: string | null;
  brand_voice: string | null;
  goals: string | null;
  competitive_landscape: string | null;
  profile_source: string | null;
}

/** The predefined profile fields in display order. */
export const PROFILE_FIELDS: { key: keyof CompanyProfile; label: string }[] = [
  { key: "description", label: "About" },
  { key: "services", label: "Services & Products" },
  { key: "target_audience", label: "Target Audience" },
  { key: "online_presence", label: "Online Presence" },
  { key: "brand_voice", label: "Brand Voice & Tone" },
  { key: "goals", label: "Goals & Priorities" },
  { key: "competitive_landscape", label: "Competitive Landscape" },
];

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

// ── Onboarding (conversational) ──

export interface SeedInfo {
  company_name: string;
  phone: string;
  city: string;
  industry: string;
  website: string;
  socials: string;
}

export interface OnboardingMessage {
  role: "user" | "assistant";
  content: string;
}

export interface OnboardingResponse {
  response: string;
  employee_name: string;
  employee_title: string;
  profile_updated: boolean;
  onboarding_complete: boolean;
  auth_error?: boolean;
  auth_error_type?: string; // "token_expired" | "not_connected"
}

export async function sendOnboardingMessage(
  businessId: string,
  userMessage: string,
  conversation: OnboardingMessage[],
  seedInfo?: SeedInfo,
): Promise<OnboardingResponse> {
  const res = await client.post<OnboardingResponse>(
    `/businesses/${businessId}/onboard`,
    {
      user_message: userMessage,
      conversation,
      seed_info: seedInfo,
    },
  );
  return res.data;
}

// ── Connected Accounts ──

export async function getAccounts(
  id: string,
): Promise<{
  accounts: Array<{
    id: string;
    platform: string;
    employee_id: string;
    status: string;
    connected_at: string;
  }>;
  total: number;
}> {
  const res = await client.get(`/businesses/${id}/accounts`);
  return res.data;
}

// ── Team Members ──

/** Tab paths available in the app. */
export const ALL_TABS = [
  { path: "/dashboard",          label: "Dashboard" },
  { path: "/lead-generation",    label: "Lead Generation" },
  { path: "/tracking-routing",   label: "Tracking & Routing" },
  { path: "/sales",              label: "Sales" },
  { path: "/operations",         label: "Operations" },
  { path: "/billing",            label: "Finance" },
  { path: "/reports",            label: "Reports" },
  { path: "/connections",        label: "Connections" },
  { path: "/organization",       label: "Organization" },
] as const;

export interface TeamMember {
  id: string;
  user_id: string;
  email: string;
  full_name: string;
  is_owner: boolean;
  /** null = access to all tabs (owners + members with full access) */
  allowed_tabs: string[] | null;
  joined_at: string;
}

export interface MyMembership {
  id: string;
  is_owner: boolean;
  /** null = access to all tabs (owner) */
  allowed_tabs: string[] | null;
}

export async function listMembers(businessId: string): Promise<TeamMember[]> {
  const res = await client.get<TeamMember[]>(`/businesses/${businessId}/members`);
  return res.data;
}

export async function getMyMembership(businessId: string): Promise<MyMembership> {
  const res = await client.get<MyMembership>(`/businesses/${businessId}/my-membership`);
  return res.data;
}

export async function inviteMember(
  businessId: string,
  email: string,
  allowedTabs: string[] | null,
): Promise<{ message: string }> {
  const res = await client.post(`/businesses/${businessId}/members`, {
    email,
    allowed_tabs: allowedTabs,
  });
  return res.data;
}

export async function updateMemberTabs(
  businessId: string,
  memberId: string,
  allowedTabs: string[] | null,
): Promise<{ message: string }> {
  const res = await client.patch(`/businesses/${businessId}/members/${memberId}`, {
    allowed_tabs: allowedTabs,
  });
  return res.data;
}

export async function removeMember(
  businessId: string,
  memberId: string,
): Promise<void> {
  await client.delete(`/businesses/${businessId}/members/${memberId}`);
}
