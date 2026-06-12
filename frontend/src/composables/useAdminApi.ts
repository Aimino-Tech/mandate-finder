import { API_BASE, request, requestRaw } from "./apiClient";

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

    getCRMConnections: () => request<Record<string, unknown>[]>("/crm/connections"),
    connectCRM: (data: Record<string, unknown>) =>
      request("/crm/connect", { method: "POST", body: JSON.stringify(data) }) as Promise<Record<string, unknown>>,
    disconnectCRM: (id: string) => requestRaw(`/crm/connections/${id}`, { method: "DELETE" }),
    updateFieldMapping: (id: string, mapping: Record<string, string>) =>
      request(`/crm/connections/${id}/field-mapping`, { method: "PUT", body: JSON.stringify({ field_mapping: mapping }) }),
    toggleAutoSync: (id: string, enabled: boolean) =>
      request(`/crm/connections/${id}/auto-sync`, { method: "PUT", body: JSON.stringify({ enabled }) }),
    retryFailedSyncs: () => request("/crm/sync/retry", { method: "POST" }) as Promise<{ results: Record<string, unknown>[] }>,
    getSyncHistory: () => request<{ entries: Record<string, unknown>[]; total: number }>("/crm/sync-history"),
  };
}
