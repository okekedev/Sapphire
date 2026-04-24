import client from "@/shared/api/client";

export interface MemberRole {
  id: string;
  name: string;
  description: string | null;
}

export interface TeamMember {
  id: string;       // BusinessMember id
  user_id: string;
  email: string;
  full_name: string | null;
  is_owner: boolean;
  roles: MemberRole[];
}

export interface Role {
  id: string;
  name: string;
  description: string | null;
  permissions: string[];
  is_system: boolean;
}

export async function listTeamMembers(bizId: string): Promise<TeamMember[]> {
  const res = await client.get("/team/members", { params: { business_id: bizId } });
  return res.data;
}

export async function listRoles(bizId: string): Promise<Role[]> {
  const res = await client.get("/team/roles", { params: { business_id: bizId } });
  return res.data;
}

export async function inviteMember(
  bizId: string,
  email: string,
  roleNames: string[],
): Promise<TeamMember> {
  const res = await client.post(
    "/team/members",
    { email, role_names: roleNames },
    { params: { business_id: bizId } },
  );
  return res.data;
}

export async function updateMemberRoles(
  bizId: string,
  memberId: string,
  roleNames: string[],
): Promise<TeamMember> {
  const res = await client.patch(
    `/team/members/${memberId}/roles`,
    { role_names: roleNames },
    { params: { business_id: bizId } },
  );
  return res.data;
}

export async function removeMember(bizId: string, memberId: string): Promise<void> {
  await client.delete(`/team/members/${memberId}`, { params: { business_id: bizId } });
}
