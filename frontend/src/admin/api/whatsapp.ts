import client from "@/shared/api/client";

export async function registerWhatsAppSender(payload: {
  business_id: string;
  department_id: string;
  phone_number: string;
  display_name: string;
}): Promise<Record<string, unknown>> {
  const { data } = await client.post("/whatsapp/register", payload);
  return data;
}

export async function verifyWhatsAppSender(payload: {
  business_id: string;
  department_id: string;
  verification_code: string;
}): Promise<Record<string, unknown>> {
  const { data } = await client.post("/whatsapp/verify", payload);
  return data;
}

export async function refreshWhatsAppStatus(
  businessId: string,
  departmentId: string,
): Promise<Record<string, unknown>> {
  const { data } = await client.post("/whatsapp/refresh", null, {
    params: { business_id: businessId, department_id: departmentId },
  });
  return data;
}

export async function sendWhatsAppTest(
  businessId: string,
  departmentId: string,
): Promise<{ status: string }> {
  const { data } = await client.post("/whatsapp/test", null, {
    params: { business_id: businessId, department_id: departmentId },
  });
  return data;
}
