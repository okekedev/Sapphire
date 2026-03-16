import client from "./client";

// ── Types ──

export interface NgrokStatus {
  platform: "ngrok";
  connected: boolean;
  auth_token_preview: string | null;
  tunnel_url: string | null;
  tunnel_active: boolean;
  connected_at: string | null;
}

export interface NgrokConnectPayload {
  business_id: string;
  auth_token: string;
}

export interface NgrokConnectResponse {
  status: "connected";
  message: string;
}

export interface NgrokTunnelResponse {
  status: "running" | "stopped";
  tunnel_url?: string;
  webhook_base_url?: string;
  configured_numbers?: string[];
  message: string;
}

// ── API functions ──

export async function getNgrokStatus(businessId: string): Promise<NgrokStatus> {
  const res = await client.get("/ngrok/status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function connectNgrok(
  payload: NgrokConnectPayload,
): Promise<NgrokConnectResponse> {
  const res = await client.post("/ngrok/connect", payload);
  return res.data;
}

export async function disconnectNgrok(businessId: string): Promise<void> {
  await client.delete("/ngrok/disconnect", {
    params: { business_id: businessId },
  });
}

export async function startNgrokTunnel(
  businessId: string,
): Promise<NgrokTunnelResponse> {
  const res = await client.post("/ngrok/start-tunnel", null, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function stopNgrokTunnel(
  businessId: string,
): Promise<NgrokTunnelResponse> {
  const res = await client.post("/ngrok/stop-tunnel", null, {
    params: { business_id: businessId },
  });
  return res.data;
}
