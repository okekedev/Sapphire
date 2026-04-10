import client from "@/shared/api/client";
import type { PhoneLine } from "@/marketing/api/contacts";

export interface AvailableNumber {
  phone_number: string;
  cost_monthly: number;
  country: string;
  capabilities: string[];
}

export async function listACSNumbers(businessId: string): Promise<PhoneLine[]> {
  const res = await client.get("/acs/numbers", {
    params: { business_id: businessId },
  });
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (res.data.numbers ?? []).map((n: any) => ({
    id: n.line_id,
    business_id: businessId,
    department_id: n.department_id ?? null,
    phone_number: n.phone_number,
    acs_number_sid: null,
    friendly_name: n.friendly_name ?? null,
    campaign_name: n.campaign_name,
    ad_account_id: null,
    channel: n.channel ?? null,
    line_type: n.line_type,
    shaken_stir_status: "unverified",
    active: true,
    created_at: "",
    updated_at: "",
  }));
}

export async function searchAvailableNumbers(
  areaCode: string,
  limit = 5,
): Promise<AvailableNumber[]> {
  const res = await client.get("/acs/available-numbers", {
    params: { area_code: areaCode, limit },
  });
  return res.data.numbers ?? [];
}

export async function provisionPhoneLine(
  businessId: string,
  areaCode: string,
  campaignName: string,
  lineType: "mainline" | "tracking",
): Promise<{ phone_number: string; line_id: string }> {
  const res = await client.post("/acs/provision", {
    business_id: businessId,
    area_code: areaCode,
    campaign_name: campaignName,
    line_type: lineType,
  });
  return res.data;
}

export async function releaseNumber(businessId: string, phoneNumber: string): Promise<void> {
  await client.delete(`/acs/numbers/${encodeURIComponent(phoneNumber)}`, {
    params: { business_id: businessId },
  });
}
