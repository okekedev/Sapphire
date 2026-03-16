export interface Department {
  id: string;
  business_id: string | null;
  name: string;
  description: string | null;
  icon: string | null;
  display_order: number;
  forward_number: string | null;
  enabled: boolean;
  created_at: string;
}

export interface DepartmentWithEmployees extends Department {
  employees: Employee[];
}

export interface Employee {
  id: string;
  business_id: string | null;
  department_id: string;
  name: string;
  title: string;
  file_stem: string;
  model_tier: "opus" | "sonnet" | "haiku";
  reports_to: string | null;
  status: "active" | "inactive";
  capabilities: Record<string, unknown> | null;
  is_head: boolean;
  job_skills: string | null;
  created_at: string;
  updated_at: string;
}

export interface EmployeeDetail extends Employee {
  system_prompt: string;
  department_name: string | null;
  supervisor_name: string | null;
}

export interface OrgChartNode {
  id: string;
  name: string;
  title: string;
  department: string;
  model_tier: "opus" | "sonnet" | "haiku";
  is_head: boolean;
  status: string;
  job_skills: string | null;
  children: OrgChartNode[];
}

// ── Templates ──

export interface OrgTemplate {
  id: string;
  user_id: string | null;
  name: string;
  description: string | null;
  is_system: boolean;
  employee_count: number;
  created_at: string;
  updated_at: string;
}

export interface OrgTemplateDetail extends OrgTemplate {
  template_data: {
    departments: Array<{
      name: string;
      description?: string;
      icon?: string;
      display_order?: number;
    }>;
    employees: Array<{
      file_stem: string;
      name: string;
      title: string;
      model_tier: string;
      department: string;
      is_head: boolean;
      reports_to: string | null;
    }>;
  };
}

export interface ApplyTemplateResponse {
  business_id: string;
  template_name: string;
  num_departments: number;
  num_employees: number;
  assistant_id: string;
}

export interface ProviderStatus {
  ready: boolean;
  installed: boolean;
  authenticated: boolean;
  version: string;
  message: string;
}

export type SetupStep = "connect" | "organization" | "template";

export interface SetupState {
  currentStep: SetupStep;
  claudeConnected: boolean;
  orgSeeded: boolean;
  templateChosen: boolean;
}
