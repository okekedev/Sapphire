import client from "./client";

// ── Types ──

export interface StripeInvoice {
  id: string;
  number: string | null;
  customer_id: string;
  customer_name: string;
  customer_email: string;
  amount_due: number;       // cents
  amount_paid: number;      // cents
  currency: string;
  status: string;           // draft, open, paid, void, uncollectible
  hosted_invoice_url: string;
  invoice_pdf: string;
  due_date: number | null;  // unix timestamp
  created: number;          // unix timestamp
  paid_at: number | null;   // unix timestamp
}

export interface StripeSubscription {
  id: string;
  customer_id: string;
  status: string;           // active, past_due, canceled, etc.
  plan_name: string;
  amount: number;           // cents
  currency: string;
  interval: string;         // month, year
  current_period_start: number;
  current_period_end: number;
  cancel_at_period_end: boolean;
  created: number;
}

export interface StripeCustomer {
  id: string;
  name: string;
  email: string;
  phone: string;
  created: number;
}

export interface RevenueSummary {
  total_collected: number;
  pending: number;
  mrr: number;
  active_subscriptions: number;
  stripe_balance: number | null;
  stripe_connected: boolean;
}

// ── API functions ──

export async function getRevenueSummary(businessId: string): Promise<RevenueSummary> {
  const res = await client.get("/billing/revenue-summary", {
    params: { business_id: businessId },
  });
  return res.data;
}

export async function listStripeInvoices(
  businessId: string,
  opts?: { limit?: number; status?: string },
): Promise<{ invoices: StripeInvoice[]; has_more: boolean }> {
  const res = await client.get("/billing/invoices", {
    params: { business_id: businessId, ...opts },
  });
  return res.data;
}

export async function listStripeSubscriptions(
  businessId: string,
  opts?: { limit?: number; status?: string },
): Promise<{ subscriptions: StripeSubscription[]; has_more: boolean }> {
  const res = await client.get("/billing/subscriptions", {
    params: { business_id: businessId, ...opts },
  });
  return res.data;
}

export async function listStripeCustomers(
  businessId: string,
  opts?: { search?: string; limit?: number },
): Promise<{ customers: StripeCustomer[]; has_more: boolean }> {
  const res = await client.get("/billing/customers", {
    params: { business_id: businessId, ...opts },
  });
  return res.data;
}
