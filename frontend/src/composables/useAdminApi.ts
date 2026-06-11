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

async function requestRaw(url: string, options: RequestInit = {}) {
  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { ...headers(), ...(options.headers as Record<string, string> || {}) },
  });
}

export function useAdminApi() {
  return {
    getDashboard: (days = 30) => request<Record<string, { date: string; value: number }[]>>(`/admin/dashboard?days=${days}`),
    getPipeline: (days = 30) => request<Record<string, { date: string; value: number }[]>>(`/admin/pipeline?days=${days}`),
    getPipelineSources: (days = 30) => request<{ sources: Record<string, { date: string; value: number }[]>; totals: Record<string, number> }>(`/admin/pipeline/sources?days=${days}`),
    getHealth: (days = 7) => request<Record<string, { date: string; value: number }[]>>(`/admin/health?days=${days}`),
    getHealthCurrent: () => request<Record<string, number>>("/admin/health/current"),
    recordMetric: (metricType: string, value: number, source?: string) =>
      request("/admin/metrics", {
        method: "POST",
        body: JSON.stringify({ metric_type: metricType, value, source }),
      }),
    getApiKeys: () => request<{ api_keys: Record<string, unknown>[]; total: number }>("/admin/api-keys"),
    getExportUrl: (metricType: string, days = 30) => `${API_BASE}/admin/export?metric_type=${metricType}&days=${days}`,
    getAlerts: () => request<Record<string, unknown>[]>("/admin/alerts"),
    createAlert: (data: Record<string, unknown>) =>
      request("/admin/alerts", { method: "POST", body: JSON.stringify(data) }) as Promise<Record<string, unknown>>,
    updateAlert: (id: string, data: Record<string, unknown>) =>
      request(`/admin/alerts/${id}`, { method: "PUT", body: JSON.stringify(data) }) as Promise<Record<string, unknown>>,
    deleteAlert: (id: string) => requestRaw(`/admin/alerts/${id}`, { method: "DELETE" }),
    getCampaigns: () => request<Record<string, unknown>[]>("/outreach/campaigns"),
    createCampaign: (data: Record<string, unknown>) =>
      request("/outreach/campaigns", { method: "POST", body: JSON.stringify(data) }) as Promise<Record<string, unknown>>,
    approveCampaign: (id: string) => request(`/outreach/campaigns/${id}/approve`, { method: "POST" }),
    sendCampaign: (id: string) => request(`/outreach/campaigns/${id}/send`, { method: "POST" }),
    pauseCampaign: (id: string) => request(`/outreach/campaigns/${id}/pause`, { method: "POST" }),
    resumeCampaign: (id: string) => request(`/outreach/campaigns/${id}/resume`, { method: "POST" }),
    getTemplates: () => request<Record<string, unknown>[]>("/outreach/templates"),
    createTemplate: (data: Record<string, unknown>) =>
      request("/outreach/templates", { method: "POST", body: JSON.stringify(data) }) as Promise<Record<string, unknown>>,
  };
}
