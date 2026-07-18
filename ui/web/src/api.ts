export type Capabilities = {
  prava_mode: string;
  home_merchant_mode: string;
  teams_billing_mode: string;
  real_money_enabled: boolean;
  slack_configured: boolean;
  whatsapp_configured: boolean;
  demo_mode: boolean;
};

export type Notification = {
  notification_id: string;
  run_id: string;
  message: string;
  actions: string[];
  status: string;
  track?: "home" | "teams";
};

export type AuditEntry = {
  audit_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  modes: Record<string, string>;
  created_at: string;
};

import { loadSessionToken } from "./native";

const API_BASE = String(import.meta.env.VITE_RESTOCK_API_BASE_URL || "").replace(/\/$/, "");

async function requestHeaders(): Promise<Record<string, string>> {
  const token = await loadSessionToken() || import.meta.env.VITE_RESTOCK_API_TOKEN || "restock-local-demo-token";
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

const endpoint = (path: string) => `${API_BASE}${path}`;

async function read<T>(path: string): Promise<T> {
  const response = await fetch(endpoint(path), { headers: await requestHeaders() });
  if (!response.ok) throw new Error(`${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  capabilities: () => read<Capabilities>("/capabilities"),
  notifications: () => read<Notification[]>("/api/v1/notifications/pending"),
  audit: () => read<AuditEntry[]>("/api/v1/audit"),
  action: async (runId: string, action: string, adjustedAmount?: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/actions`), {
      method: "POST",
      headers: await requestHeaders(),
      body: JSON.stringify({ action, adjusted_amount: adjustedAmount }),
    });
    if (!response.ok) throw new Error((await response.json()).detail || "Action failed");
    return response.json();
  },
  approvalUrl: (runId: string) => read<{ approval_url: string }>(`/api/v1/workflows/${runId}/approval-url`),
  resume: async (runId: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/resume`), { method: "POST", headers: await requestHeaders() });
    if (!response.ok) throw new Error((await response.json()).detail || "Resume failed");
    return response.json();
  },
};
