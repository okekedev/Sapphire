import client from "./client";

// ── Types ──

export interface TwilioStatus {
  platform: "twilio";
  connected: boolean;
  account_sid: string | null;
  account_name: string | null;
  phone_number: string | null;
  twilio_status: string | null;   // "active" | "suspended" | etc.
  connected_at: string | null;
}

export interface TwilioNumber {
  sid: string;
  phone_number: string;           // E.164 format
  friendly_name: string;
  capabilities: {
    voice: boolean;
    sms: boolean;
    mms: boolean;
  };
}

export interface TwilioConnectPayload {
  business_id: string;
  account_sid: string;
  auth_token: string;
  phone_number?: string;          // Optional — can be set later
}

export interface TwilioAvailableNumber {
  phone_number: string;
  friendly_name: string;
  locality: string;
  region: string;
  capabilities: {
    voice: boolean;
    sms: boolean;
  };
}

export interface TwilioProvisionPayload {
  business_id: string;
  phone_number: string;           // E.164 number from search
  campaign_name: string;
  channel?: string;               // google_ads, facebook_ads, direct_mail, etc.
  ad_account_id?: string;
}

export interface TwilioProvisionResponse {
  tracking_number_id: string;
  phone_number: string;
  twilio_sid: string;
  campaign_name: string;
  channel: string;
  ad_account_id: string;
}

export interface TwilioConnectResponse {
  status: "connected";
  account_name: string | null;
  twilio_status: string | null;
}

// ── API functions ──

export async function getTwilioStatus(businessId: string): Promise<TwilioStatus> {
  const res = await client.get("/twilio/status", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function connectTwilio(
  payload: TwilioConnectPayload,
): Promise<TwilioConnectResponse> {
  const res = await client.post("/twilio/connect", payload);
  return res.data;
}

export async function disconnectTwilio(businessId: string): Promise<void> {
  await client.delete("/twilio/disconnect", {
    params: { business_id: businessId },
  });
}

export async function listTwilioNumbers(businessId: string): Promise<TwilioNumber[]> {
  const res = await client.get("/twilio/numbers", {
    params: { business_id: businessId },
  });
  return res.data.numbers ?? [];
}

export async function configureTwilioWebhook(
  businessId: string,
  numberSid: string,
): Promise<{ status: string; voice_url: string; status_callback_url: string }> {
  const res = await client.post(
    `/twilio/configure/${numberSid}`,
    null,
    { params: { business_id: businessId } },
  );
  return res.data;
}

export async function searchAvailableNumbers(
  businessId: string,
  options?: {
    country?: string;
    area_code?: string;
    contains?: string;
    limit?: number;
  },
): Promise<TwilioAvailableNumber[]> {
  const res = await client.get("/twilio/available-numbers", {
    params: { business_id: businessId, ...options },
  });
  return res.data.numbers ?? [];
}

export async function provisionTrackingNumber(
  payload: TwilioProvisionPayload,
): Promise<TwilioProvisionResponse> {
  const res = await client.post("/twilio/provision", payload);
  return res.data;
}


// ── A2P Campaign Status ──

export interface A2PStatusResponse {
  campaign_status: string;
  ready: boolean;
  campaign_id?: string;
  messaging_service_sid?: string;
  messaging_service_name?: string;
  detail?: string;
}

export async function getA2PStatus(businessId: string): Promise<A2PStatusResponse> {
  const res = await client.get("/twilio/a2p-status", {
    params: { business_id: businessId },
  });
  return res.data;
}


// ── Outbound Calling (WebRTC) ──

export interface ClientTokenResponse {
  token: string;
  identity: string;
}

export async function getClientToken(
  businessId: string,
): Promise<ClientTokenResponse> {
  const res = await client.get("/twilio/client-token", {
    params: { business_id: businessId },
  });
  return res.data;
}
