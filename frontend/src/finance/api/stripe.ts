import client from "./client";

// ── Types ──

export interface StripeStatus {
  platform: "stripe";
  connected: boolean;
  status: string;
  account_name: string | null;
  account_id: string | null;
  connected_at: string | null;
}

export interface StripeConnectPayload {
  business_id: string;
  secret_key: string;
}

export interface StripeConnectResponse {
  connected: boolean;
  account_name: string;
  account_id: string;
  message: string;
}

// ── API calls ──

export async function getStripeStatus(businessId: string): Promise<StripeStatus> {
  const res = await client.get("/stripe/status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function connectStripe(payload: StripeConnectPayload): Promise<StripeConnectResponse> {
  const res = await client.post("/stripe/connect", payload);
  return res.data;
}

export async function disconnectStripe(businessId: string): Promise<{ status: string; message: string }> {
  const res = await client.delete("/stripe/disconnect", {
    params: { business_id: businessId },
  });
  return res.data;
}
