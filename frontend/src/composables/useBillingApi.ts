const API_BASE = "/api/v1";

function headers(): Record<string, string> {
  const h: Record<string, string> = { "Content-Type": "application/json" };
  const token = typeof localStorage !== "undefined" ? localStorage.getItem("admin_token") : null;
  if (token) h.Authorization = `Bearer ${token}`;
  return h;
}

async function request<T>(url: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { ...headers(), ...(options.headers as Record<string, string> || {}) },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const text = await res.text();
  return text ? JSON.parse(text) : (null as T);
}

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
