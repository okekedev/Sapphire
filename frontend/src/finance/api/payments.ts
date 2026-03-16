import client from "./client";

// ── Types ──

export type PaymentType = "subscription" | "one_time";
export type PaymentStatus = "pending" | "completed" | "failed" | "refunded";

export interface Payment {
  id: string;
  business_id: string;
  contact_id: string | null;
  lead_id: string | null;
  amount: number;
  payment_type: PaymentType;
  frequency: string | null;
  provider: string | null;
  status: PaymentStatus;
  billing_ref: Record<string, unknown> | null;
  notes: string | null;
  paid_at: string | null;
  created_at: string;
}

export interface PaymentCreatePayload {
  amount: number;
  payment_type?: PaymentType;
  frequency?: string;
  provider?: string;
  status?: PaymentStatus;
  billing_ref?: Record<string, unknown>;
  notes?: string;
  paid_at?: string;
  contact_id?: string;
  lead_id?: string;
}

export interface PaymentUpdatePayload extends Partial<PaymentCreatePayload> {}

// ── API calls ──

export async function listPayments(
  businessId: string,
  filters?: { contact_id?: string; lead_id?: string; status?: PaymentStatus },
): Promise<{ payments: Payment[]; total: number }> {
  const res = await client.get("/payments", {
    params: { business_id: businessId, ...filters, limit: 200 },
  });
  return res.data;
}

export async function createPayment(
  businessId: string,
  payload: PaymentCreatePayload,
): Promise<Payment> {
  const res = await client.post("/payments", payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function updatePayment(
  paymentId: string,
  businessId: string,
  payload: PaymentUpdatePayload,
): Promise<Payment> {
  const res = await client.patch(`/payments/${paymentId}`, payload, {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function deletePayment(
  paymentId: string,
  businessId: string,
): Promise<void> {
  await client.delete(`/payments/${paymentId}`, {
    params: { business_id: businessId },
  });
}
