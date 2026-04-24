import client from "@/shared/api/client";

export interface StaffMember {
  id: string;
  business_id: string;
  first_name: string;
  last_name: string | null;
  phone: string | null;
  email: string | null;
  role: "admin" | "dispatcher" | "technician";
  color: string;
  is_active: boolean;
  created_at: string;
}

export interface CreateStaffRequest {
  business_id: string;
  first_name: string;
  last_name?: string;
  phone?: string;
  email?: string;
  role?: "admin" | "dispatcher" | "technician";
  color?: string;
}

export interface UpdateStaffRequest {
  first_name?: string;
  last_name?: string;
  phone?: string;
  email?: string;
  role?: "admin" | "dispatcher" | "technician";
  color?: string;
  is_active?: boolean;
}

export async function listStaff(businessId: string, includeInactive = false): Promise<StaffMember[]> {
  const res = await client.get<StaffMember[]>("/operations/staff", {
    params: { business_id: businessId, include_inactive: includeInactive },
  });
  return res.data;
}

export async function createStaff(data: CreateStaffRequest): Promise<StaffMember> {
  const res = await client.post<StaffMember>("/operations/staff", data);
  return res.data;
}

export async function updateStaff(id: string, data: UpdateStaffRequest): Promise<StaffMember> {
  const res = await client.patch<StaffMember>(`/operations/staff/${id}`, data);
  return res.data;
}

export async function deleteStaff(id: string): Promise<void> {
  await client.delete(`/operations/staff/${id}`);
}
