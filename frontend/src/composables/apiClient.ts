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
    headers: { ...headers(), ...((options.headers as Record<string, string>) || {}) },
  });
  if (!res.ok) throw new Error(`API error ${res.status}`);
  const text = await res.text();
  return text ? JSON.parse(text) : (null as T);
}

async function requestRaw(url: string, options: RequestInit = {}) {
  return fetch(`${API_BASE}${url}`, {
    ...options,
    headers: { ...headers(), ...((options.headers as Record<string, string>) || {}) },
  });
}

export { API_BASE, headers, request, requestRaw };
