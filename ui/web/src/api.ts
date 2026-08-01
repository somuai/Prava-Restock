export type Capabilities = {
  auth_mode?: string;
  google_auth_configured?: boolean;
  google_client_id?: string;
  reviewer_access_configured?: boolean;
  prava_mode: string;
  home_merchant_mode: string;
  home_payment_mode: string;
  teams_billing_mode: string;
  teams_checkout_runtime_configured?: boolean;
  teams_checkout_runtime_status?: string;
  teams_real_money_enabled?: boolean;
  real_money_enabled: boolean;
  slack_configured: boolean;
  whatsapp_configured: boolean;
  demo_mode: boolean;
};

export type Notification = {
  notification_id: string;
  run_id: string;
  item_id?: string;
  message: string;
  actions: string[];
  status: string;
  track?: "home" | "teams";
};

export type WorkflowRun = {
  run_id: string;
  item_id: string;
  state: string;
  updated_at?: string;
};

export type AuditEntry = {
  audit_id: string;
  event_type: string;
  payload: Record<string, unknown>;
  modes: Record<string, string>;
  created_at: string;
};

export type UserProfile = {
  user_id: string;
  display_name: string;
  monthly_cap: string;
  per_item_cap: string;
  per_transaction_cap: string;
  created_at: string;
  auth_providers?: string[];
};

export type TenantSummary = {
  tenant_id: string;
  name: string;
  kind: string;
  role?: string;
};

export type TrackedItem = {
  item_id: string;
  user_id: string;
  tenant_id?: string | null;
  name: string;
  track: "home" | "teams";
  trigger_type: "predicted" | "known_date";
  category: string;
  preferred_merchant: string;
  merchant_sku_id: string;
  currency: string;
  status: string;
  typical_cadence_days?: number | null;
  last_purchased_at?: string | null;
  last_purchase_amount?: string | null;
  price_threshold?: string | null;
  last_observed_price?: string | null;
  renewal_date?: string | null;
  current_plan_amount?: string | null;
  alternate_plan_amount?: string | null;
  alternate_plan_label?: string | null;
  renewal_method?: "hosted_link" | "manual_required" | null;
  hosted_payment_reference?: string | null;
  alternate_hosted_payment_reference?: string | null;
};

export type StarterTemplateId = "coffee" | "milk" | "toothpaste" | "detergent";

export type StarterTemplate = {
  name: string;
  description: string;
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
  return null;
}

export async function storeApiSessionToken(token: string): Promise<void> {
  if (isNative()) {
    await saveSessionToken(token);
  }
}

export async function clearApiSessionToken(): Promise<void> {
  if (isNative()) {
    await clearSessionToken();
    return;
  }
  webSessionStorage()?.removeItem(WEB_SESSION_KEY);
}

async function requestHeaders(): Promise<Record<string, string>> {
  const token = await loadApiSessionToken();
  return {
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    "Content-Type": "application/json",
  };
}

const endpoint = (path: string) => `${API_BASE}${path}`;

async function read<T>(path: string): Promise<T> {
  const response = await fetch(endpoint(path), {
    credentials: "include",
    headers: await requestHeaders(),
  });
  if (!response.ok) throw new ApiError(response.status, `${path} returned ${response.status}`);
  return response.json() as Promise<T>;
}

type AuthResponse = {
  access_token?: string;
  token_type?: "bearer";
  expires_in?: number;
};

async function acceptAuthResponse(response: Response): Promise<AuthResponse> {
  const body = await response.json();
  if (!response.ok) throw new ApiError(response.status, body.detail || "Sign in failed");
  if (body.access_token) await storeApiSessionToken(body.access_token);
  return body as AuthResponse;
}

export const api = {
  login: async (password: string) => {
    const response = await fetch(endpoint("/api/v1/auth/login"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password }),
    });
    return acceptAuthResponse(response);
  },
  googleLogin: async (credential: string) => {
    const response = await fetch(endpoint("/api/v1/auth/google"), {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ credential }),
    });
    return acceptAuthResponse(response);
  },
  googleLink: async (credential: string) => {
    const response = await fetch(endpoint("/api/v1/auth/google/link"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify({ credential }),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Google account linking failed");
    return body as { status: "linked"; provider: "google" };
  },
  logout: async () => {
    try {
      const response = await fetch(endpoint("/api/v1/auth/logout"), {
        method: "POST",
        credentials: "include",
        headers: await requestHeaders(),
      });
      if (!response.ok && response.status !== 401) {
        throw new ApiError(response.status, "Sign out failed");
      }
    } finally {
      await clearApiSessionToken();
    }
  },
  capabilities: () => read<Capabilities>("/capabilities"),
  me: () => read<UserProfile>("/api/v1/me"),
  tenants: () => read<TenantSummary[]>("/api/v1/tenants"),
  items: () => read<TrackedItem[]>("/api/v1/items"),
  starterItems: () => read<{ items: Record<StarterTemplateId, StarterTemplate> }>("/api/v1/onboarding/starter-items"),
  createStarterItems: async (templateIds: StarterTemplateId[]) => {
    const response = await fetch(endpoint("/api/v1/onboarding/starter-items"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify({ template_ids: templateIds }),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Starter pantry setup failed");
    return body as { created: number; existing: number; items: TrackedItem[] };
  },
  createTeamsSubscription: async (input: {
    vendor_name: string;
    invoice_id: string;
    hosted_payment_reference: string;
    alternate_hosted_payment_reference?: string;
    currency: string;
    renewal_date: string;
    current_plan_amount: string;
    alternate_plan_amount?: string;
    alternate_plan_label?: string;
  }) => {
    const response = await fetch(endpoint("/api/v1/items/teams"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify(input),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Subscription setup failed");
    return body as TrackedItem;
  },
  notifications: () => read<Notification[]>("/api/v1/notifications/pending"),
  workflows: () => read<WorkflowRun[]>("/api/v1/workflows"),
  audit: () => read<AuditEntry[]>("/api/v1/audit"),
  action: async (runId: string, action: string, adjustedAmount?: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/actions`), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify({ action, adjusted_amount: adjustedAmount }),
    });
    if (!response.ok) throw new ApiError(response.status, (await response.json()).detail || "Action failed");
    return response.json();
  },
  approvalUrl: (runId: string) => read<{ approval_url: string }>(`/api/v1/workflows/${runId}/approval-url`),
  resume: async (runId: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/resume`), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
    });
    if (!response.ok) throw new ApiError(response.status, (await response.json()).detail || "Resume failed");
    return response.json();
  },
};
