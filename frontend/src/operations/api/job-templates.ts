import client from "@/shared/api/client";

export type FieldType = "text" | "checkbox" | "checklist" | "signature" | "photo" | "number" | "url";

export interface TemplateField {
  id: string;
  type: FieldType;
  label: string;
  required?: boolean;
  items?: string[];  // for checklist type
}

export interface TemplateSection {
  title: string;
  fields: TemplateField[];
}

export interface TemplateSchema {
  sections: TemplateSection[];
}

export interface JobTemplate {
  id: string;
  business_id: string;
  name: string;
  description: string | null;
  requires_scheduling: boolean;
  requires_assignment: boolean;
  requires_dispatch: boolean;
  schema: TemplateSchema;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateTemplateRequest {
  business_id: string;
  name: string;
  description?: string;
  requires_scheduling?: boolean;
  requires_assignment?: boolean;
  requires_dispatch?: boolean;
  schema?: TemplateSchema;
}

export interface UpdateTemplateRequest {
  name?: string;
  description?: string;
  requires_scheduling?: boolean;
  requires_assignment?: boolean;
  requires_dispatch?: boolean;
  schema?: TemplateSchema;
  is_active?: boolean;
}

export async function listTemplates(businessId: string): Promise<JobTemplate[]> {
  const res = await client.get<JobTemplate[]>("/operations/job-templates", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function createTemplate(data: CreateTemplateRequest): Promise<JobTemplate> {
  const res = await client.post<JobTemplate>("/operations/job-templates", data);
  return res.data;
}

export async function updateTemplate(id: string, data: UpdateTemplateRequest): Promise<JobTemplate> {
  const res = await client.patch<JobTemplate>(`/operations/job-templates/${id}`, data);
  return res.data;
}

export async function deleteTemplate(id: string): Promise<void> {
  await client.delete(`/operations/job-templates/${id}`);
}
