import client from "./client";
import type {
  Department,
  Employee,
  EmployeeDetail,
  OrgChartNode,
  ProviderStatus,
} from "@/shared/types/organization";

// ── Provider Status ──

export async function getProviderStatus(businessId?: string): Promise<ProviderStatus> {
  const params = businessId ? { business_id: businessId } : {};
  const { data } = await client.get("/cli/provider", { params });
  return data;
}

export async function getCliStatus(): Promise<Record<string, unknown>> {
  const { data } = await client.get("/cli/status");
  return data;
}

export async function startClaudeLogin(businessId: string): Promise<{
  status: "already_authenticated" | "token_required" | "error";
  message?: string;
  instructions?: string;
}> {
  const { data } = await client.post("/cli/login", null, {
    params: { business_id: businessId },
  });
  return data;
}

export async function disconnectClaude(businessId: string): Promise<{
  status: string;
  message: string;
}> {
  const { data } = await client.delete("/cli/token", {
    params: { business_id: businessId },
  });
  return data;
}

// ── Departments ──

export async function listDepartments(businessId?: string): Promise<Department[]> {
  const params = businessId ? { business_id: businessId } : {};
  const { data } = await client.get("/organization/departments", { params });
  return data;
}

export async function createDepartment(payload: {
  business_id?: string;
  name: string;
  description?: string;
  icon?: string;
  display_order?: number;
}): Promise<Department> {
  const { data } = await client.post("/organization/departments", payload);
  return data;
}

export async function updateDepartment(
  id: string,
  payload: Partial<{ name: string; description: string; icon: string; display_order: number }>,
): Promise<Department> {
  const { data } = await client.patch(`/organization/departments/${id}`, payload);
  return data;
}

export async function deleteDepartment(id: string): Promise<void> {
  await client.delete(`/organization/departments/${id}`);
}

// ── Employees ──

export async function listEmployees(params?: {
  business_id?: string;
  department_id?: string;
  status?: string;
}): Promise<Employee[]> {
  const { data } = await client.get("/organization/employees", { params });
  return data;
}

export async function getEmployee(id: string): Promise<EmployeeDetail> {
  const { data } = await client.get(`/organization/employees/${id}`);
  return data;
}

export async function createEmployee(payload: {
  business_id?: string;
  department_id: string;
  name: string;
  title: string;
  file_stem: string;
  model_tier?: string;
  system_prompt: string;
  reports_to?: string;
  capabilities?: Record<string, unknown>;
  is_head?: boolean;
}): Promise<Employee> {
  const { data } = await client.post("/organization/employees", payload);
  return data;
}

export async function updateEmployee(
  id: string,
  payload: Partial<{
    department_id: string;
    name: string;
    title: string;
    model_tier: string;
    system_prompt: string;
    reports_to: string | null;
    status: string;
    capabilities: Record<string, unknown>;
    is_head: boolean;
  }>,
): Promise<Employee> {
  const { data } = await client.patch(`/organization/employees/${id}`, payload);
  return data;
}

export async function deactivateEmployee(id: string): Promise<void> {
  await client.delete(`/organization/employees/${id}`);
}

// ── Org Chart ──

export async function getOrgChart(businessId?: string): Promise<OrgChartNode[]> {
  const params = businessId ? { business_id: businessId } : {};
  const { data } = await client.get("/organization/org-chart", { params });
  return data;
}
