import client from "@/shared/api/client";

export interface ContactForm {
  id: string;
  business_id: string;
  name: string;
  redirect_url: string | null;
  created_at: string;
}

export async function listForms(businessId: string): Promise<ContactForm[]> {
  const res = await client.get("/forms", { params: { business_id: businessId } });
  return res.data;
}

export async function createForm(
  businessId: string,
  payload: { name: string; redirect_url?: string },
): Promise<ContactForm> {
  const res = await client.post("/forms", payload, { params: { business_id: businessId } });
  return res.data;
}

export async function deleteForm(formId: string): Promise<void> {
  await client.delete(`/forms/${formId}`);
}

export function embedSnippet(formId: string): string {
  const base = window.location.origin;
  return `<div data-sapphire-form="${formId}"></div>\n<script src="${base}/api/v1/forms/${formId}/embed.js"></script>`;
}
