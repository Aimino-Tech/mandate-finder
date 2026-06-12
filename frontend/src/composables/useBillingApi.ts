import { request } from "./apiClient";

export function useBillingApi() {
  let _plans: Record<string, unknown>[] | null = null;

  async function getPlans(force = false): Promise<Record<string, unknown>[]> {
    if (!force && _plans) return _plans;
    _plans = await request<Record<string, unknown>[]>("/billing/plans");
    return _plans;
  }

  return {
    getPlans,
    getSubscription: () => request<Record<string, unknown> | null>("/billing/subscription"),
    subscribe: (planId: string, paymentMethodId?: string) =>
      request<Record<string, unknown>>("/billing/subscribe", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId, stripe_payment_method_id: paymentMethodId || null }),
      }),
    getPortalUrl: () => request<{ url: string }>("/billing/portal", { method: "POST" }),
    getInvoices: () => request<Record<string, unknown>[]>("/billing/invoices"),
    cancel: () => request<Record<string, unknown>>("/billing/cancel", { method: "POST" }),
    upgrade: (planId: string) =>
      request<Record<string, unknown>>("/billing/upgrade", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      }),
    downgrade: (planId: string) =>
      request<Record<string, unknown>>("/billing/downgrade", {
        method: "POST",
        body: JSON.stringify({ plan_id: planId }),
      }),
  };
}
