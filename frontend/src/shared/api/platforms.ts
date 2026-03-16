import client from "./client";

export interface PlatformConnection {
  id: string;
  platform: string;
  auth_method: string;
  status: string;
  external_account_id: string | null;
  token_expires_at: string | null;
  scopes: string | null;
  connected_at: string;
}

// Note: Backend wraps responses in { data: ... } via Envelope
export async function listConnections(businessId: string): Promise<PlatformConnection[]> {
  const res = await client.get("/platforms/connections", {
    params: { business_id: businessId },
  });
  return res.data.data; // Envelope unwrap
}

export async function connectApiKey(data: { platform: string; business_id: string; api_key: string }): Promise<PlatformConnection> {
  const res = await client.post("/platforms/connect/api-key", data);
  return res.data.data; // Envelope unwrap
}

export async function connectOAuth(data: { platform: string; business_id: string }): Promise<{ auth_url: string; state: string }> {
  const res = await client.post("/platforms/connect/oauth", data);
  return res.data.data; // Envelope unwrap
}

export async function disconnectPlatform(data: { platform: string; business_id: string }): Promise<{ platform: string; status: string }> {
  const res = await client.post("/platforms/disconnect", data);
  return res.data.data; // Envelope unwrap
}

export async function refreshPlatformToken(data: { platform: string; business_id: string }): Promise<{ platform: string; status: string }> {
  const res = await client.post("/platforms/refresh", data);
  return res.data.data; // Envelope unwrap
}

export interface PlatformTestResult {
  platform: string;
  token_valid: boolean;
  account_name?: string;
  account_id?: string;
  email?: string;
  pages?: { id: string; name: string; category?: string }[];
  page_count?: number;
  scope?: string;
  expires_in?: string;
  error?: string;
  message?: string;
}

export async function testConnection(platform: string, businessId: string): Promise<PlatformTestResult> {
  const res = await client.get(`/platforms/test/${platform}`, {
    params: { business_id: businessId },
  });
  return res.data.data; // Envelope unwrap
}

// ── Claude CLI Connection Status ──

export interface CliConnectionStatus {
  platform: "claude_cli";
  status: "active" | "expired" | "disconnected";
  installed: boolean;
  version: string;
  connected_at: string | null;
  message: string;
}

export async function getCliConnectionStatus(businessId: string): Promise<CliConnectionStatus> {
  const res = await client.get("/cli/connection-status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function disconnectCli(businessId: string): Promise<{ status: string; message: string }> {
  const res = await client.delete("/cli/token", {
    params: { business_id: businessId },
  });
  return res.data;
}
