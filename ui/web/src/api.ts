export type Capabilities = {
  prava_mode: string;
  home_merchant_mode: string;
  home_payment_mode: string;
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

import { clearSessionToken, isNative, loadSessionToken, saveSessionToken } from "./native";

const API_BASE = String(import.meta.env.VITE_RESTOCK_API_BASE_URL || "").replace(/\/$/, "");
const WEB_SESSION_KEY = "restock_session";

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

function webSessionStorage(): Storage | null {
  try {
    return typeof window === "undefined" ? null : window.sessionStorage;
  } catch {
    return null;
  }
}

export async function loadApiSessionToken(): Promise<string | null> {
  if (isNative()) return loadSessionToken();
  return webSessionStorage()?.getItem(WEB_SESSION_KEY) || null;
}

export async function storeApiSessionToken(token: string): Promise<void> {
  if (isNative()) {
    await saveSessionToken(token);
    return;
  }
  const storage = webSessionStorage();
  if (!storage) throw new Error("Session storage is unavailable");
  storage.setItem(WEB_SESSION_KEY, token);
}

export async function clearApiSessionToken(): Promise<void> {
  if (isNative()) {
    await clearSessionToken();
    return;
  }
  webSessionStorage()?.removeItem(WEB_SESSION_KEY);
}

async function requestHeaders(): Promise<Record<string, string>> {
  const token = await loadApiSessionToken() || (import.meta.env.DEV ? "restock-local-demo-token" : "");
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "Content-Type": "application/json",
  };
}

const endpoint = (path: string) => `${API_BASE}${path}`;

async function read<T>(path: string): Promise<T> {
  const response = await fetch(endpoint(path), { headers: await requestHeaders() });
  if (!response.ok) throw new ApiError(response.status, `${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

export const api = {
  login: async (password: string) => {
    const response = await fetch(endpoint("/api/v1/auth/login"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Sign in failed");
    await storeApiSessionToken(body.access_token);
    return body as { access_token: string; token_type: "bearer"; expires_in: number };
  },
  capabilities: () => read<Capabilities>("/capabilities"),
  notifications: () => read<Notification[]>("/api/v1/notifications/pending"),
  audit: () => read<AuditEntry[]>("/api/v1/audit"),
  action: async (runId: string, action: string, adjustedAmount?: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/actions`), {
      method: "POST",
      headers: await requestHeaders(),
      body: JSON.stringify({ action, adjusted_amount: adjustedAmount }),
    });
    if (!response.ok) throw new ApiError(response.status, (await response.json()).detail || "Action failed");
    return response.json();
  },
  approvalUrl: (runId: string) => read<{ approval_url: string }>(`/api/v1/workflows/${runId}/approval-url`),
  resume: async (runId: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/resume`), { method: "POST", headers: await requestHeaders() });
    if (!response.ok) throw new ApiError(response.status, (await response.json()).detail || "Resume failed");
    return response.json();
  },
};
