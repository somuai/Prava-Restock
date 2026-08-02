export type Capabilities = {
  auth_mode?: string;
  google_auth_configured?: boolean;
  google_client_id?: string;
  reviewer_access_configured?: boolean;
  prava_mode: string;
  home_merchant_mode: string;
  home_catalog_operational?: boolean;
  home_onboarding_mode?: string;
  home_payment_mode: string;
  swiggy_catalog_mode?: string;
  teams_billing_mode: string;
  teams_checkout_runtime_configured?: boolean;
  teams_checkout_runtime_status?: string;
  teams_real_money_enabled?: boolean;
  real_money_enabled: boolean;
  slack_configured: boolean;
  waitlist_email_configured?: boolean;
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
  merchant?: string | null;
  currency?: string;
  proposed_amount?: string | null;
  modes?: Record<string, string>;
};

export type SandboxApprovalRequest = {
  track: "home" | "teams";
  action: "approve" | "renew_as_is" | "switch_plan";
};

export type SandboxApprovalHandoff = {
  run_id: string;
  state: "passkey_pending";
  approval_url: string;
  sandbox_otp: string;
  track: "home" | "teams";
  action: "approve" | "renew_as_is" | "switch_plan";
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
  reviewer_fixture?: boolean;
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
  merchant_address_ref?: string | null;
  quantity?: number | null;
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

export type MerchantAddress = {
  reference: string;
  label: string;
};

export type ZeptoConnection = {
  provider: "zepto";
  status: "not_connected" | "pending" | "connected" | "error" | "revoked";
  oauth_configured: boolean;
  history_import: "suggestions_only";
  last_verified_at?: string | null;
  token_expires_at?: string | null;
  updated_at?: string | null;
};

export type ZeptoHistorySuggestion = {
  merchant_sku_id: string;
  name: string;
  search_query: string;
};

export type MerchantCatalogProduct = {
  merchant: "zepto";
  merchant_sku_id: string;
  store_product_id: string;
  name: string;
  amount: string;
  currency: "INR";
  available_quantity: number;
  stock_status: "in_stock" | "out_of_stock";
  execution_mode: "real";
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
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(response.status, body.detail || `${path} returned ${response.status}`);
  }
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
  zeptoConnection: () => read<ZeptoConnection>("/api/v1/integrations/zepto/connection"),
  beginZeptoConnection: async () => {
    const response = await fetch(endpoint("/api/v1/integrations/zepto/connect"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Could not start Zepto connection");
    return body as { authorization_url: string };
  },
  zeptoAddresses: () => read<{ addresses: MerchantAddress[] }>("/api/v1/integrations/zepto/addresses"),
  zeptoProducts: (query: string, addressRef: string) => read<{ products: MerchantCatalogProduct[] }>(
    `/api/v1/integrations/zepto/products?query=${encodeURIComponent(query)}&address_ref=${encodeURIComponent(addressRef)}`,
  ),
  zeptoHistorySuggestions: () => read<{ suggestions: ZeptoHistorySuggestion[] }>("/api/v1/integrations/zepto/history/suggestions"),
  createHomeCatalogItem: async (input: {
    query: string;
    merchant_sku_id: string;
    merchant_address_ref: string;
    category?: "grocery" | "stationery" | "health" | "other";
    quantity?: number;
    typical_cadence_days?: number;
    price_threshold?: string;
  }) => {
    const response = await fetch(endpoint("/api/v1/items/home"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify(input),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Live Zepto item setup failed");
    return body as TrackedItem;
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
  sandboxApproval: async (input: SandboxApprovalRequest) => {
    const response = await fetch(endpoint("/api/v1/reviewer/sandbox-approval"), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
      body: JSON.stringify(input),
    });
    const body = await response.json();
    if (!response.ok) throw new ApiError(response.status, body.detail || "Sandbox approval failed");
    return body as SandboxApprovalHandoff;
  },
  paymentStatus: (runId: string) => read<{
    run_id: string;
    workflow_state: string;
    provider_status: string;
    resumable: boolean;
  }>(`/api/v1/workflows/${runId}/payment-status`),
  approvalUrl: (runId: string) => read<{ approval_url: string }>(`/api/v1/workflows/${runId}/approval-url`),
  resume: async (runId: string) => {
    const response = await fetch(endpoint(`/api/v1/workflows/${runId}/resume`), {
      method: "POST",
      credentials: "include",
      headers: await requestHeaders(),
    });
    if (!response.ok) throw new ApiError(response.status, (await response.json()).detail || "Resume failed");
    return response.json() as Promise<WorkflowRun>;
  },
};
